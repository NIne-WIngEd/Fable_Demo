"""Derived custody contract tests; SQL/record-time fixtures are not engines."""
from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from flora.selected.experience import CommittedExperience
from flora.selected.governed_development import _version_from_record
from flora.selected.owner_authorization import Ed25519OwnerActionVerifier
from flora.selected.personal_artifact_custody import (
    DurableOwnerProofLookup, DurablePersonalReferences, XTDBPersonalArtifactCustody,
    _SourceAuthorizedObjectReads,
)
import test_governed_development as fixture_helpers


class PersonalArtifactCustodyContractTest(unittest.TestCase):
    def setUp(self):
        # Reuse the private fixture constructor, not its test methods/results.
        self.fixture = fixture_helpers.GovernedDevelopmentContractTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        f.log.replay_committed = lambda: tuple(CommittedExperience(event, position,
            datetime(2026, 9, 29, 14, tzinfo=timezone.utc)) for position, event in enumerate(f.log.events))
        def append(event, *, expected_revision):
            if expected_revision != len(f.log.events) - 1:
                raise ValueError("synthetic stale append")
            f.log.events.append(event)
        f.log.append = append
        self.custody = self.new_custody()
        self.references = DurablePersonalReferences(custody=self.custody, originals=f.registry)
        self.public_key = f.key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    def new_custody(self):
        f = self.fixture
        return XTDBPersonalArtifactCustody(scope=f.scope, authority_namespace_id=f.namespace,
                                         connection=f.connection)

    def test_withdrawal_during_cipher_fetch_stops_before_plaintext_decryption(self):
        f = self.fixture
        raw = f.objects.put(b"private source guard fixture")
        allowed = [True]
        original = f.objects.backend.get_object
        def withdraw(namespace, object_id):
            sealed = original(namespace, object_id)
            allowed[0] = False
            return sealed
        reader = _SourceAuthorizedObjectReads(f.objects, lambda: allowed[0])
        with patch.object(f.objects.backend, "get_object", side_effect=withdraw), patch(
                "flora.selected.object_store.AESGCM", side_effect=AssertionError("revoked ciphertext was decrypted")):
            with self.assertRaises(PermissionError):
                reader.get(raw)
        self.assertIs(reader.objects.backend.backend, f.objects.backend)

    def test_reference_recovery_obeys_current_gate_before_decryption(self):
        f = self.fixture
        raw = f.objects.put(b"private reference fixture")
        reader = _SourceAuthorizedObjectReads(f.objects, lambda: False)
        with patch("flora.selected.object_store.AESGCM", side_effect=AssertionError("revoked reference was decrypted")):
            with self.assertRaises(PermissionError):
                reader.recover_reference(object_id=raw.object_id, plaintext_sha256=raw.plaintext_sha256)

    def test_nested_current_gates_both_fence_the_actual_cipher_fetch(self):
        f = self.fixture
        raw = f.objects.put(b"nested authority fixture")
        allowed = [True]
        original = f.objects.backend.get_object
        def withdraw(namespace, object_id):
            sealed = original(namespace, object_id)
            allowed[0] = False
            return sealed
        inner = _SourceAuthorizedObjectReads(f.objects, lambda: True)
        outer = _SourceAuthorizedObjectReads(inner, lambda: allowed[0])
        with patch.object(f.objects.backend, "get_object", side_effect=withdraw), patch(
                "flora.selected.object_store.AESGCM", side_effect=AssertionError("nested gate allowed decryption")):
            with self.assertRaises(PermissionError):
                outer.get(raw)

    def inputs(self):
        f = self.fixture
        return dict(claims=f.claims, log=f.log, objects=f.objects, references=self.references)

    def record(self, version, raw, artifact_id="fictional-private-state-v1"):
        f = self.fixture
        return self.custody.record(artifact_id=artifact_id, kind="projection",
            contract=version.metadata_record(), attachments=(("content", raw),),
            parent_event_ids=version.source_evidence_ids, log=f.log, objects=f.objects,
            occurred_at="2026-09-29T13:00:00Z", expected_revision=len(f.log.events) - 1)

    def approval_custody(self, version, expected=None):
        f = self.fixture
        event = f.approval(version.metadata_record(), expected)
        self.custody.register_approval(approval_event_id=event.event_id, candidate=version,
            expected_active_version_id=expected, raw=f.references[event.payload_reference],
            log=f.log, objects=f.objects)
        self.custody.record_owner_proof(proof=f.proofs[event.event_id], owner_public_key=self.public_key,
            log=f.log, objects=f.objects, occurred_at="2026-09-29T13:00:00Z",
            expected_revision=len(f.log.events) - 1)
        return event

    def durable_verifier(self):
        f = self.fixture
        proofs = DurableOwnerProofLookup(custody=self.custody, log=f.log, objects=f.objects,
                                        owner_public_key=self.public_key)
        return Ed25519OwnerActionVerifier(scope=f.scope, owner_public_key=self.public_key, proofs=proofs)

    def test_projection_approval_and_proof_recover_without_caller_maps(self):
        f = self.fixture
        version, raw = f.version(1)
        registered = self.record(version, raw)
        f.state.put_candidate(version, content=raw, **self.inputs())
        approval = self.approval_custody(version)
        f.references.clear()
        f.proofs.clear()
        self.custody = self.new_custody()
        self.references = DurablePersonalReferences(custody=self.custody, originals=f.registry)
        recovered = self.custody.read(registered.artifact_id, log=f.log, objects=f.objects)
        self.assertEqual(recovered.contract, version.metadata_record())
        self.assertEqual(dict(recovered.content)["content"], b"fictional supplied state 1")
        self.assertEqual(self.references.get(raw.object_id), raw)
        active = f.state.activate(**f.identity(), approval_event_id=approval.event_id,
            expected_active_version_id=None, verifier=self.durable_verifier(), **self.inputs())
        self.assertEqual(active.content, b"fictional supplied state 1")
        self.assertEqual(f.state.read_active(**f.identity(), verifier=self.durable_verifier(),
            **self.inputs()), active)

    def test_append_before_index_failure_reconciles_from_canonical_event(self):
        f = self.fixture
        version, raw = f.version(1)
        original_insert = self.custody._insert
        def fail_artifact(table, key, record):
            if table == "flora_private_personal_artifacts":
                raise RuntimeError("injected post-append index failure")
            original_insert(table, key, record)
        self.custody._insert = fail_artifact
        with self.assertRaisesRegex(RuntimeError, "post-append"):
            self.record(version, raw)
        event = f.log.events[-1]
        self.custody = self.new_custody()
        with self.assertRaises(KeyError):
            self.custody.read("fictional-private-state-v1", log=f.log, objects=f.objects)
        recovered = self.custody.reconcile_event(event.event_id, log=f.log, objects=f.objects)
        self.assertEqual(recovered.artifact_id, "fictional-private-state-v1")
        self.assertEqual(dict(self.custody.read(recovered.artifact_id,
            log=f.log, objects=f.objects).content)["content"], b"fictional supplied state 1")
        self.assertEqual(self.custody.reconcile_event(event.event_id, log=f.log, objects=f.objects), recovered)

    def test_exact_projection_retry_and_wrong_contract_do_not_mutate_lineage(self):
        f = self.fixture
        version, raw = f.version(1)
        initial_revision = len(f.log.events) - 1
        first = self.record(version, raw)
        retry = self.custody.record(artifact_id=first.artifact_id, kind="projection",
            contract=version.metadata_record(), attachments=(("content", raw),),
            parent_event_ids=version.source_evidence_ids, log=f.log, objects=f.objects,
            occurred_at="2026-09-29T13:00:00Z", expected_revision=initial_revision)
        self.assertEqual(retry, first)
        self.assertEqual(len(f.log.events), initial_revision + 2)
        other, other_raw = f.version(2, source=f.source_two, previous=version.version_id)
        with self.assertRaisesRegex(ValueError, "reused before append"):
            self.record(other, other_raw, first.artifact_id)
        self.assertEqual(len(f.log.events), initial_revision + 2)
        with self.assertRaisesRegex(ValueError, "differs from its exact contract"):
            self.record(version, other_raw, "wrong-private-content")

    def test_missing_event_and_wrong_enrolled_key_fail_before_private_reads(self):
        f = self.fixture
        version, raw = f.version(1)
        recorded = self.record(version, raw)
        event = f.log.events.pop()
        opened = []
        original_get = f.objects.backend.get_object
        f.objects.backend.get_object = lambda namespace, object_id: (
            opened.append(object_id), original_get(namespace, object_id))[1]
        with self.assertRaisesRegex(ValueError, "canonical event binding"):
            self.custody.read(recorded.artifact_id, log=f.log, objects=f.objects)
        self.assertEqual(opened, [])
        f.log.events.append(event)
        approval = self.approval_custody(version)
        opened.clear()
        wrong_key = Ed25519PrivateKey.generate().public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        lookup = DurableOwnerProofLookup(custody=self.custody, log=f.log, objects=f.objects,
                                        owner_public_key=wrong_key)
        with self.assertRaisesRegex(ValueError, "current enrolled key"):
            lookup.get(approval.event_id)
        self.assertEqual(opened, [])

    def test_revoked_source_blocks_derived_candidate_content_before_open(self):
        f = self.fixture
        version, raw = f.version(1)
        self.record(version, raw)
        f.policy.allowed.remove((f.source_one.event_id, "personal_judgment"))
        opened = []
        original_get = f.objects.backend.get_object
        f.objects.backend.get_object = lambda namespace, object_id: (
            opened.append(object_id), original_get(namespace, object_id))[1]
        with self.assertRaisesRegex(ValueError, "not currently permitted"):
            f.state.put_candidate(version, content=raw, **self.inputs())
        self.assertEqual(opened, [])

    def test_rollback_contract_is_durable_and_keeps_exact_target_bytes(self):
        f = self.fixture
        first, raw = f.version(1)
        self.record(first, raw)
        f.state.put_candidate(first, content=raw, **self.inputs())
        approval = self.approval_custody(first)
        f.state.activate(**f.identity(), approval_event_id=approval.event_id,
                         expected_active_version_id=None, verifier=self.durable_verifier(), **self.inputs())
        second, raw = f.version(2, source=f.source_two, previous=first.version_id)
        self.record(second, raw, "fictional-private-state-v2")
        f.state.put_candidate(second, content=raw, expected_previous_version_id=first.version_id, **self.inputs())
        approval = self.approval_custody(second, first.version_id)
        f.state.activate(**f.identity(), approval_event_id=approval.event_id,
                         expected_active_version_id=first.version_id,
                         verifier=self.durable_verifier(), **self.inputs())
        restored = f.state.register_rollback(rollback_id="fictional-rollback",
            version_id="fictional-restored-v3", target_version_id=first.version_id,
            expected_active_version_id=second.version_id, expected_latest_version_id=second.version_id,
            produced_at="2026-09-29T12:00:00Z", verifier=self.durable_verifier(), **self.inputs())
        version = _version_from_record(restored.record)
        raw = self.references.get(self.custody.read("fictional-private-state-v1",
            log=f.log, objects=f.objects).references[0][1].object_id)
        self.record(version, raw, "fictional-private-rollback-v3")
        f.references.clear()
        f.proofs.clear()
        self.custody = self.new_custody()
        restored_artifact = self.custody.read("fictional-private-rollback-v3", log=f.log, objects=f.objects)
        self.assertEqual(restored_artifact.contract["envelope"]["rollback_reference"], first.version_id)
        self.assertEqual(restored_artifact.contract["supersedes_version_id"], second.version_id)
        self.assertEqual(dict(restored_artifact.content)["content"], b"fictional supplied state 1")


if __name__ == "__main__":
    unittest.main()
