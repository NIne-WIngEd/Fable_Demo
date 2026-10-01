"""Actual XTDB registrations and bounded Kurrent target proofs.

These are custody/availability and scoped permission cases using generated
fictional sources and signed fictional-owner actions. They exercise no model
inference, and an exact target proof does not certify the integrity of unrelated
stream records. The optional closure route certifies a terminal metadata sample,
not a continuing permission lease or authorization to open private bytes.
"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import base64
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from kurrentdbclient import KurrentDBClient, NewEvent, StreamState
import psycopg

from cognitive_kernel.canonical import normalize_timestamp
from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from flora.selected.experience import KurrentExperienceLog, encode_event, event_uuid
from flora.selected.formation_context import register_experience_source
from flora.selected.formation_registry import XTDBFormationSourceRegistry
from flora.selected.formation_policy import (
    FormationPermissionAction, XTDBFormationPermissionPolicy,
    formation_permission_payload,
)
from flora.selected.object_store import EncryptedObjectPlane, LocalObjectBackend
from flora.selected.owner_authorization import (
    Ed25519OwnerActionVerifier, OwnerActionProof, owner_action_message,
)
from flora.selected.source_closure import SelectedSourceClosureResolver


class SelectedExactCommitmentIntegrationTest(unittest.TestCase):
    def setUp(self):
        suffix = uuid.uuid4().hex
        self.scope = ProductHostScope.create(
            product_id="friday", host_instance_id=f"fictional-exact-source-{suffix}",
            schema_version="1.0.0", encryption_domain=f"integration-exact-{suffix}")
        self.namespace = f"flora-exact-source-{suffix}"
        self.dsn = os.environ.get("XTDB_DSN", "postgresql://xtdb@127.0.0.1:5432/xtdb")
        self.connection = psycopg.connect(self.dsn, autocommit=True)
        self.addCleanup(self.connection.close)
        self.client = KurrentDBClient(os.environ.get(
            "KURRENTDB_URI", "kurrentdb://127.0.0.1:2113?tls=false"))
        self.addCleanup(self.client.close)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.objects = EncryptedObjectPlane(scope=self.scope, key=b"x" * 32,
            backend=LocalObjectBackend(Path(self.directory.name) / "objects"))
        self.log = KurrentExperienceLog(scope=self.scope, client=self.client)
        self.registry = XTDBFormationSourceRegistry(scope=self.scope,
            authority_namespace_id=self.namespace, connection=self.connection)
        self.permissions = XTDBFormationPermissionPolicy(scope=self.scope,
            authority_namespace_id=self.namespace, connection=self.connection,
            registry=self.registry)
        self.signer = Ed25519PrivateKey.generate()
        self.proofs, self.grants = {}, {}
        self.verifier = Ed25519OwnerActionVerifier(scope=self.scope,
            owner_public_key=self.signer.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw),
            proofs=self.proofs)
        self.revision = -1
        self.counter = 0

    def _make_event(self, label, *, parents=()):
        self.counter += 1
        raw = self.objects.put(f"generated fictional {label} {self.counter}".encode())
        event = ExperienceEvent.create(
            event_type="observation", scope=self.scope,
            occurred_at=f"2020-01-01T00:00:{self.counter:02d}Z",
            content_digest=raw.plaintext_sha256,
            provenance=ProvenanceReference.create(
                provenance_type="generated_reconstruction",
                source_reference_ids=(f"fictional-exact-item-{self.counter}",),
                derivation_activity_id="selected-exact-commitment-integration",
                responsible_component="synthetic-test"),
            retention_class="ordinary_experience", storage_tier="raw_buffer",
            payload_reference=raw.object_id, parent_event_ids=parents)
        return event, raw

    def _append(self, label, *, parents=()):
        event, raw = self._make_event(label, parents=parents)
        self.log.append(event, expected_revision=self.revision)
        self.revision += 1
        return event, raw

    def _register(self, event, raw):
        return register_experience_source(
            event_id=event.event_id, raw=raw, registry=self.registry, log=self.log,
            objects=self.objects, role="generated_reconstruction", modality="text",
            subject_ref="fictional-source-person", source_item_ref=raw.object_id)

    def _permission(self, source, decision="allow"):
        """Actually signed fictional-owner action and selected-engine CAS."""
        previous = self.grants.get(source.evidence.ref_id)
        action = FormationPermissionAction.create(
            scope=self.scope, authority_namespace_id=self.namespace,
            action_id=f"fictional-exact-grant-{uuid.uuid4().hex}",
            source_ref_id=source.evidence.ref_id,
            source_registration_sha256=source.registration_sha256,
            purpose="memory_formation", decision=decision,
            generation=1 if previous is None else previous[0].generation + 1,
            previous_action_sha256=None if previous is None else previous[0].action_sha256,
            authorization_ref=f"fictional-owner-proof-{uuid.uuid4().hex}",
            authorized_at=datetime.now(timezone.utc).isoformat())
        raw = self.objects.put(formation_permission_payload(action))
        parents = (source.evidence.ref_id,) + (
            () if previous is None else (previous[1].event_id,))
        event = ExperienceEvent.create(
            event_type="formation_permission_action", scope=self.scope,
            occurred_at=action.authorized_at, content_digest=raw.plaintext_sha256,
            provenance=ProvenanceReference.create(
                provenance_type="derived_inference", source_reference_ids=parents,
                derivation_activity_id=action.action_id, responsible_component="synthetic-test"),
            retention_class="ordinary_experience", storage_tier="raw_buffer",
            parent_event_ids=parents, payload_reference=raw.object_id)
        self.log.append(event, expected_revision=self.revision)
        self.revision += 1
        register_experience_source(event_id=event.event_id, raw=raw, registry=self.registry,
            log=self.log, objects=self.objects, role="derived_inference", modality="structured")
        self.proofs[event.event_id] = OwnerActionProof(
            "formation_permission", event.event_id, event.event_sha256,
            base64.b64encode(self.signer.sign(
                owner_action_message(event, "formation_permission"))).decode("ascii"))
        self.permissions.apply(action, request_event_id=event.event_id,
            log=self.log, objects=self.objects, references=self.registry, verifier=self.verifier)
        self.grants[source.evidence.ref_id] = (action, event)
        return action

    def _registered_source(self):
        # Put the registered source away from the beginning and head. No model
        # chooses these positions; the actual registration binds its locator.
        self._append("unrelated prefix")
        event, raw = self._append("registered source")
        source = register_experience_source(
            event_id=event.event_id, raw=raw, registry=self.registry, log=self.log,
            objects=self.objects, role="generated_reconstruction", modality="text",
            subject_ref="fictional-source-person", source_item_ref=raw.object_id)
        commitment = self.registry.lookup_commitment(event.event_id)
        self.assertIsNotNone(commitment)
        self.assertEqual(commitment.source, source)
        self.assertEqual(commitment.stream_position, 1)
        self.assertEqual(commitment.event_sha256, event.event_sha256)
        return event, commitment

    def _lookup(self, commitment, **changes):
        arguments = dict(event_id=commitment.source.evidence.ref_id,
                         event_sha256=commitment.event_sha256,
                         stream_position=commitment.stream_position,
                         expected_recorded_at=commitment.recorded_at)
        return self.log.lookup_committed(**(arguments | changes))

    def _granted_parent_and_child(self):
        parent, raw = self._append("registered parent")
        parent_source = self._register(parent, raw)
        child, raw = self._append("registered child", parents=(parent.event_id,))
        child_source = self._register(child, raw)
        self._permission(parent_source)
        self._permission(child_source)
        return parent, child, parent_source

    def _resolver(self):
        return SelectedSourceClosureResolver(registry=self.registry, log=self.log,
            permissions=self.permissions, maximum_sources=2)

    def test_persisted_locator_resolves_exact_source_after_unrelated_tail(self):
        event, commitment = self._registered_source()
        for index in range(12):
            self._append(f"unrelated tail {index}")

        # Reopen the physical XTDB connection. The locator comes from durable
        # rows, rather than a registration returned by a caller's RAM map.
        with psycopg.connect(self.dsn, autocommit=True) as connection:
            registry = XTDBFormationSourceRegistry(scope=self.scope,
                authority_namespace_id=self.namespace, connection=connection)
            reopened = registry.lookup_commitment(event.event_id)
            self.assertEqual(reopened, commitment)
            self.assertIsNone(registry.lookup_commitment("missing-fictional-source"))
            self.assertEqual(registry.get(reopened.source.object_ref).plaintext_sha256,
                             event.content_digest)

        first, second = self._lookup(reopened), self._lookup(reopened)
        self.assertEqual(first, second)
        self.assertEqual(first.event, event)
        self.assertEqual(first.stream_position, 1)
        self.assertEqual(normalize_timestamp(first.recorded_at.isoformat()),
                         reopened.recorded_at)
        self.assertNotEqual(first.recorded_at, datetime.fromisoformat(event.occurred_at))
        self.assertEqual(self.client.get_current_version(self.log.stream), 13)

    def test_missing_wrong_position_digest_and_time_fail_against_actual_records(self):
        event, commitment = self._registered_source()
        self._append("unrelated successor")
        self.assertEqual(self._lookup(commitment).event, event)
        changed_time = normalize_timestamp((datetime.fromisoformat(commitment.recorded_at)
                                           + timedelta(days=1)).isoformat())
        # Preserve the short event-ID prefix to require full digest equality.
        changed_digest = event.event_sha256[:-1] + (
            "0" if event.event_sha256[-1] != "0" else "1")
        for changes in ({"stream_position": 0}, {"stream_position": 2},
                        {"stream_position": 3}, {"expected_recorded_at": changed_time},
                        {"event_sha256": changed_digest}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self._lookup(commitment, **changes)
        self.assertEqual(self._lookup(commitment).event, event)

    def test_well_formed_false_locator_still_needs_independent_physical_proof(self):
        event, commitment = self._registered_source()
        self._append("unrelated successor")
        # Structural metadata validation does not establish physical presence.
        # This modified descriptor is deliberately not written into the registry.
        false_locator = replace(commitment, stream_position=2)
        false_locator.validate()
        with self.assertRaises(ValueError):
            self._lookup(false_locator)
        self.assertEqual(self.registry.lookup_commitment(event.event_id), commitment)
        self.assertEqual(self._lookup(commitment).event, event)

    def test_soft_delete_and_reappend_reject_stale_position_and_commit_time(self):
        event, commitment = self._registered_source()
        self._append("unrelated tail before deletion")
        self.assertEqual(self._lookup(commitment).event, event)
        self.client.delete_stream(self.log.stream, current_version=self.revision)
        with self.assertRaises(ValueError):
            self._lookup(commitment)

        # Kurrent soft deletion preserves event numbering. Reopening therefore
        # creates a later position, not a new generation at position zero. A
        # fresh first event avoids an all-duplicate append being idempotent.
        reopening, _ = self._make_event("reopening stream")
        self.client.append_to_stream(
            self.log.stream, current_version=StreamState.ANY,
            events=[NewEvent(type="FableExperienceV1", data=encode_event(reopening),
                             id=event_uuid(reopening)),
                    NewEvent(type="FableExperienceV1", data=encode_event(event),
                             id=event_uuid(event))])
        # append_to_stream returns a global commit position, not the per-stream
        # event number required by the registered locator and bounded read.
        reappended_position = self.client.get_current_version(self.log.stream)
        self.assertIs(type(reappended_position), int)
        self.assertGreater(reappended_position, self.revision)
        rows = self.client.get_stream(stream_name=self.log.stream,
            stream_position=reappended_position, limit=1, resolve_links=False)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].stream_position, reappended_position)
        later_recorded_at = normalize_timestamp(rows[0].recorded_at.isoformat())
        self.assertNotEqual(later_recorded_at, commitment.recorded_at)

        # XTDB still contains the original registration; it cannot replace the
        # fresh Kurrent proof, even after the immutable codec has been warmed.
        self.assertEqual(self.registry.lookup_commitment(event.event_id), commitment)
        with self.assertRaises(ValueError):
            self._lookup(commitment)
        with self.assertRaisesRegex(ValueError, "commit time changed"):
            self._lookup(commitment, stream_position=reappended_position)
        current = self._lookup(commitment, stream_position=reappended_position,
                               expected_recorded_at=later_recorded_at)
        self.assertEqual(current.event, event)
        self.assertEqual(current.stream_position, reappended_position)
        # This new target proof does not amend the immutable source registration.
        self.assertEqual(self.registry.lookup_commitment(event.event_id), commitment)

    def test_selected_parent_closure_checks_actual_grants_and_later_withdrawal(self):
        parent, child, parent_source = self._granted_parent_and_child()
        for index in range(3):
            self._append(f"unrelated closure tail {index}")
        resolver = self._resolver()
        proof = resolver.resolve(source_event_ids=(child.event_id,), purpose="memory_formation")
        self.assertEqual(proof.domain, "selected-source-closure-v1")
        self.assertEqual(proof.purpose, "memory_formation")
        self.assertEqual(proof.nominated_event_ids, (child.event_id,))
        commitments = {entry.source.evidence.ref_id: entry for entry in proof.commitments}
        self.assertEqual(set(commitments), {parent.event_id, child.event_id})
        self.assertLess(commitments[parent.event_id].stream_position,
                        commitments[child.event_id].stream_position)
        self.assertEqual({action.source_ref_id for action in proof.grant_actions},
                         {parent.event_id, child.event_id})
        self.assertTrue(all(action.decision == "allow" for action in proof.grant_actions))

        self._permission(parent_source, "revoke")
        self.assertEqual(self.permissions.current_action(parent.event_id,
            "memory_formation").decision, "revoke")
        # Reusing the resolver and its earlier proof does not reuse permission.
        with self.assertRaises(PermissionError):
            resolver.resolve(source_event_ids=(child.event_id,), purpose="memory_formation")

    def test_selected_closure_rejects_actual_parent_revocation_during_physical_read(self):
        parent, child, parent_source = self._granted_parent_and_child()
        child_position = self.registry.lookup_commitment(child.event_id).stream_position
        actual_read = self.client.get_stream
        changed = False
        child_reads = 0

        def read(*args, **kwargs):
            nonlocal changed, child_reads
            rows = actual_read(*args, **kwargs)
            if (kwargs.get("stream_position") == child_position
                    and kwargs.get("limit") == 1):
                child_reads += 1
                if child_reads == 2:
                    changed = True
                    self._permission(parent_source, "revoke")
            return rows

        # The callback still executes Kurrent's physical read. It injects a
        # signed action committed to real Kurrent/XTDB before the second child
        # read returns, after the initial current grant checks have succeeded.
        with patch.object(self.client, "get_stream", side_effect=read):
            with self.assertRaises(PermissionError):
                self._resolver().resolve(source_event_ids=(child.event_id,),
                                         purpose="memory_formation")
        self.assertTrue(changed)
        self.assertEqual(child_reads, 2)
        self.assertEqual(self.permissions.current_action(parent.event_id,
            "memory_formation").decision, "revoke")


if __name__ == "__main__":
    unittest.main()
