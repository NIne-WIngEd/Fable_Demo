"""Personal-development boundary checks; SQL calls are not engine qualification.

Canonical upstream contracts, enrolled-owner signatures and encrypted objects
are real here. The SQL recorder and evidence authority responses are controlled
fixtures for denial/rollback/failure injection. Selected-engine persistence is
covered separately by integration/test_selected_governed_development.py.
"""
import base64
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from cognitive_kernel.formation_contracts import FormationEvidenceRef
from cognitive_kernel.formation_sources import RegisteredFormationSource
from cognitive_kernel.memory_contracts import MemoryUnitEnvelope
from cognitive_kernel.projection_contracts import ProjectionVersion

from flora.selected.governed_development import XTDBGovernedPersonalDevelopment
from flora.selected.object_store import EncryptedObjectPlane, LocalObjectBackend
from flora.selected.owner_authorization import (
    Ed25519OwnerActionVerifier, OwnerActionProof, owner_action_message,
)
from flora.selected.personal_state import activation_request


@contextmanager
def observe_private_opens(opened, after_open=None, *, before_open=None):
    """Observe actual AEAD opens, including reads through copied guard views."""
    original = AESGCM.decrypt
    def decrypt(cipher, nonce, sealed, aad):
        object_id = aad.decode().rsplit(":", 1)[1]
        opened.append(object_id)
        if before_open is not None:
            before_open(object_id)
        plaintext = original(cipher, nonce, sealed, aad)
        if after_open is not None:
            after_open(object_id)
        return plaintext
    with patch.object(AESGCM, "decrypt", new=decrypt):
        yield


class _Cursor:
    def __init__(self, rows):
        names = tuple(rows[0]) if rows else ()
        self.description = [SimpleNamespace(name=name) for name in names]
        self.rows = [tuple(row[name] for name in names) for row in rows]

    def fetchall(self):
        return self.rows


class _SQLCalls:
    def __init__(self):
        self.rows, self.calls = {}, []
        self.adapters = SimpleNamespace(types={"text": SimpleNamespace(oid=25)},
                                        register_dumper=lambda *_: None)

    @contextmanager
    def transaction(self):
        snapshot = deepcopy(self.rows)
        try:
            yield
        except Exception:
            self.rows = snapshot
            raise

    def execute(self, statement, parameters):
        self.calls.append((statement, parameters))
        table = re.search(r"(?:FROM|INTO) (\w+)", statement).group(1)
        if statement.startswith("INSERT"):
            names = re.search(r"\(([^)]+)\) VALUES", statement).group(1).split(", ")
            row = dict(zip(names, parameters))
            self.rows[(table, row["_id"])] = row
            return _Cursor([])
        row = self.rows.get((table, parameters[0]))
        if statement.startswith("ASSERT NOT"):
            if row is not None:
                raise ValueError("synthetic immutable absence assertion failed")
            return _Cursor([])
        if statement.startswith("ASSERT EXISTS"):
            fields = re.findall(r"AND (\w+) = %s", statement)
            if row is None or any(row[field] != value for field, value in zip(fields, parameters[1:])):
                raise ValueError("synthetic head compare-and-swap failed")
            return _Cursor([])
        return _Cursor([row] if row else [])


class _Log:
    def __init__(self, scope):
        self.scope, self.events = scope, []

    def replay(self):
        return self.events.copy()


class _Registry:
    def __init__(self, scope, namespace):
        self.scope, self.authority_namespace_id = scope, namespace
        self.sources, self.raw_references, self.raw_records = {}, {}, {}

    def lookup(self, ref_id):
        return self.sources.get(ref_id)

    def raw_reference(self, object_ref):
        return self.raw_references.get(object_ref)

    def raw_metadata(self, object_ref):
        return self.raw_records.get(object_ref)


class _Policy:
    def __init__(self, registry):
        self.registry = registry
        self.scope, self.authority_namespace_id = registry.scope, registry.authority_namespace_id
        self.allowed = set()
        self.purposes = []

    def permits(self, source, purpose):
        self.purposes.append(purpose)
        return (source.evidence.ref_id, purpose) in self.allowed


class _Authority:
    def __init__(self, scope, namespace):
        self.scope, self.authority_namespace_id = scope, namespace
        self.versions, self.relations, self.current = {}, {}, {}

    def load_version(self, version_id):
        return deepcopy(self.versions[version_id])

    def load_evidence_relation(self, relation_id):
        return deepcopy(self.relations[relation_id])

    def load_current(self, claim_id):
        return deepcopy(self.current[claim_id])


class GovernedDevelopmentContractTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.scope = ProductHostScope.create(product_id="friday",
            host_instance_id="fictional-development-host", schema_version="1.0.0",
            encryption_domain="fictional-development-key")
        self.namespace = "fictional-development-authority"
        self.objects = EncryptedObjectPlane(scope=self.scope, key=b"d" * 32,
                                           backend=LocalObjectBackend(self.directory.name))
        self.references, self.proofs = {}, {}
        self.log, self.connection = _Log(self.scope), _SQLCalls()
        self.registry = _Registry(self.scope, self.namespace)
        self.policy = _Policy(self.registry)
        self.claims = _Authority(self.scope, self.namespace)
        self.key = Ed25519PrivateKey.generate()
        self.verifier = Ed25519OwnerActionVerifier(scope=self.scope,
            owner_public_key=self.key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw),
            proofs=self.proofs)
        self.state = self.new_state()
        self.source_one = self.event(b"fictional source one")
        self.source_two = self.event(b"fictional source two")
        self.register_source(self.source_one)
        self.register_source(self.source_two)
        self.policy.allowed.update((event.event_id, "personal_judgment")
                                   for event in (self.source_one, self.source_two))

    def new_state(self):
        return XTDBGovernedPersonalDevelopment(scope=self.scope,
            authority_namespace_id=self.namespace, connection=self.connection,
            registry=self.registry, policy=self.policy)

    def inputs(self):
        return dict(claims=self.claims, log=self.log, objects=self.objects,
                    references=self.references)

    def identity(self):
        return dict(subject_type="owner", subject_id=self.scope.host_instance_id,
                    projection_id="fictional-owner-state")

    def event(self, content, *, event_type="observation", parents=(), timestamp="2026-09-29T10:00:00Z"):
        raw = self.objects.put(content)
        self.references[raw.object_id] = raw
        event = ExperienceEvent.create(event_type=event_type, scope=self.scope,
            occurred_at=timestamp, content_digest=raw.plaintext_sha256,
            provenance=ProvenanceReference.create(provenance_type="derived_inference",
                source_reference_ids=(raw.object_id,), derivation_activity_id="fictional-ingress",
                responsible_component="fictional-contract-test"),
            retention_class="ordinary_experience", storage_tier="raw_buffer",
            payload_reference=raw.object_id, parent_event_ids=parents)
        self.log.events.append(event)
        return event

    def register_source(self, event):
        source = RegisteredFormationSource.create(evidence=FormationEvidenceRef(
            ref_id=event.event_id, scope=self.scope, authority_namespace_id=self.namespace,
            content_digest=event.content_digest, role="historical_experience", modality="text",
            parent_refs=event.parent_event_ids), object_ref=event.payload_reference)
        self.registry.sources[event.event_id] = source
        self.registry.raw_references[event.payload_reference] = self.references[event.payload_reference]
        cipher = self.objects.backend.get_object(self.objects.namespace, event.payload_reference)
        self.registry.raw_records[event.payload_reference] = {
            "object_namespace": self.objects.namespace, "ciphertext_size": len(cipher),
            "ciphertext_sha256": hashlib.sha256(cipher).hexdigest()}
        return source

    def version(self, generation, *, source=None, claim_ids=(), previous=None, episodes=(),
                produced_at="2026-09-29T11:00:00Z"):
        source = source or self.source_one
        content = self.objects.put(f"fictional supplied state {generation}".encode())
        self.references[content.object_id] = content
        version_id = f"fictional-state-v{generation}"
        sources = claim_ids if claim_ids else (source.event_id,)
        envelope = MemoryUnitEnvelope.create(scope=self.scope, record_id=version_id,
            record_type="projection_version", authority_namespace_id=self.namespace,
            host_or_cluster_id=self.scope.host_instance_id, authority_role="registered_projection",
            deployment_profile="single_workstation", created_at=produced_at,
            valid_from=produced_at, valid_to=None,
            transaction_time=produced_at, logical_clock=generation,
            source_records=sources, generation=generation, state="committed",
            data_classification="highly_sensitive", retention_class="authoritative_source",
            deletion_state="active", provenance_digest="a" * 64, content_digest=content.plaintext_sha256,
            writer="fictional-updater", workflow_or_request_id="fictional-request",
            idempotency_namespace=self.namespace, idempotency_key=version_id,
            supersedes=() if previous is None else (previous,))
        version = ProjectionVersion.create(envelope=envelope, projection_id="fictional-owner-state",
            version_id=version_id, projection_type="owner_model", subject_type="owner",
            subject_id=self.scope.host_instance_id, modalities=("symbolic",), generation=generation,
            source_evidence_ids=() if claim_ids else (source.event_id,), source_claim_version_ids=claim_ids,
            source_episode_ids=episodes, valid_from=produced_at, valid_to=None,
            produced_at=produced_at, projection_state="candidate",
            responsible_component="supplied-test-candidate", model_id=None, model_version=None,
            content_digest=content.plaintext_sha256, supersedes_version_id=previous)
        return version, content

    def put(self, version, content, previous=None):
        self.state.put_candidate(version, content=content,
            expected_previous_version_id=previous, **self.inputs())

    def approval(self, record, expected=None):
        event = self.event(activation_request(record, expected_active_version_id=expected),
            event_type="state_activation_approval", timestamp="2026-09-29T12:00:00Z")
        self.proofs[event.event_id] = OwnerActionProof(action="state_activation", event_id=event.event_id,
            event_sha256=event.event_sha256,
            signature_base64=base64.b64encode(self.key.sign(owner_action_message(event, "state_activation"))).decode())
        return event

    def activate(self, version, expected=None):
        event = self.approval(version.metadata_record() if isinstance(version, ProjectionVersion) else version, expected)
        result = self.state.activate(**self.identity(), approval_event_id=event.event_id,
            expected_active_version_id=expected, verifier=self.verifier, **self.inputs())
        return result, event

    def read(self):
        return self.state.read_active(**self.identity(), verifier=self.verifier, **self.inputs())

    def two_states(self):
        first, content = self.version(1)
        self.put(first, content)
        self.activate(first)
        second, content = self.version(2, source=self.source_two, previous=first.version_id)
        self.put(second, content, first.version_id)
        self.activate(second, first.version_id)
        return first, second

    def rollback(self, first, second):
        return self.state.register_rollback(rollback_id="fictional-rollback-one",
            version_id="fictional-restored-v3", target_version_id=first.version_id,
            expected_active_version_id=second.version_id, expected_latest_version_id=second.version_id,
            produced_at="2026-09-29T12:00:00Z", verifier=self.verifier, **self.inputs())

    def test_candidate_and_formation_permission_do_not_authorize_judgment(self):
        first, content = self.version(1)
        self.policy.allowed = {(self.source_one.event_id, "memory_formation")}
        with self.assertRaisesRegex(ValueError, "not currently permitted"):
            self.put(first, content)
        self.assertFalse(self.connection.rows)
        self.policy.allowed.add((self.source_one.event_id, "personal_judgment"))
        self.put(first, content)
        with self.assertRaises(KeyError):
            self.read()
        self.assertEqual(set(self.policy.purposes), {"personal_judgment"})

    def test_signed_activation_is_atomic_retry_safe_and_revalidated_after_restart(self):
        first, content = self.version(1)
        self.put(first, content)
        activated, approval = self.activate(first)
        self.assertEqual(activated.content, b"fictional supplied state 1")
        replay = self.state.activate(**self.identity(), approval_event_id=approval.event_id,
            expected_active_version_id=None, verifier=self.verifier, **self.inputs())
        self.assertEqual(replay, activated)
        self.state = self.new_state()
        self.assertEqual(self.read(), activated)
        self.policy.allowed.remove((self.source_one.event_id, "personal_judgment"))
        with self.assertRaisesRegex(ValueError, "not currently permitted"):
            self.read()

    def test_parent_permission_and_mid_read_revocation_are_enforced(self):
        child = self.event(b"fictional derivative", parents=(self.source_one.event_id,))
        self.register_source(child)
        self.policy.allowed.add((child.event_id, "personal_judgment"))
        first, content = self.version(1, source=child)
        self.policy.allowed.remove((self.source_one.event_id, "personal_judgment"))
        with self.assertRaisesRegex(ValueError, "not currently permitted"):
            self.put(first, content)
        self.policy.allowed.add((self.source_one.event_id, "personal_judgment"))
        opened = []
        def revoke_on_read(object_id):
            if object_id == self.source_one.payload_reference:
                self.policy.allowed.discard((self.source_one.event_id, "personal_judgment"))
        with observe_private_opens(opened, revoke_on_read):
            with self.assertRaisesRegex(ValueError, "authority changed during read"):
                self.put(first, content)
        self.assertIn(self.source_one.payload_reference, opened)
        self.assertNotIn(content.object_id, opened)

    def test_rollback_restores_exact_target_as_candidate_then_requires_new_signed_approval(self):
        first, second = self.two_states()
        restored = self.rollback(first, second)
        self.assertEqual(restored.content, b"fictional supplied state 1")
        self.assertEqual(restored.record["supersedes_version_id"], second.version_id)
        self.assertEqual(restored.record["envelope"]["rollback_reference"], first.version_id)
        self.assertEqual(self.read().record["version_id"], second.version_id)
        activated, _ = self.activate(restored.record, second.version_id)
        self.assertEqual(activated.record["version_id"], "fictional-restored-v3")
        self.assertEqual(self.read().content, b"fictional supplied state 1")

    def test_rollback_can_replace_revoked_active_state_but_never_restore_revoked_target(self):
        first, second = self.two_states()
        self.policy.allowed.remove((self.source_two.event_id, "personal_judgment"))
        with self.assertRaisesRegex(ValueError, "not currently permitted"):
            self.read()
        restored = self.rollback(first, second)
        self.activate(restored.record, second.version_id)
        self.assertEqual(self.read().content, b"fictional supplied state 1")
        self.policy.allowed.remove((self.source_one.event_id, "personal_judgment"))
        with self.assertRaisesRegex(ValueError, "not currently permitted"):
            self.read()

    def test_revoked_target_and_unactivated_target_cannot_be_restored(self):
        first, second = self.two_states()
        self.policy.allowed.remove((self.source_one.event_id, "personal_judgment"))
        with self.assertRaisesRegex(ValueError, "not currently permitted"):
            self.rollback(first, second)
        self.policy.allowed.add((self.source_one.event_id, "personal_judgment"))
        key = self.state._history_key(first.projection_id, first.version_id)
        self.connection.rows.pop(("flora_personal_state_activation_receipts", key))
        with self.assertRaisesRegex(ValueError, "actual governed activation"):
            self.rollback(first, second)

    def test_interrupted_rollback_binding_is_unusable_until_exact_retry_finishes(self):
        first, second = self.two_states()
        original_insert = self.state._insert_receipt
        def fail_binding(table, key, record):
            if table == "flora_personal_state_rollback_candidates":
                raise RuntimeError("injected binding failure")
            return original_insert(table, key, record)
        self.state._insert_receipt = fail_binding
        with self.assertRaisesRegex(RuntimeError, "injected"):
            self.rollback(first, second)
        with self.assertRaisesRegex(ValueError, "immutable target binding"):
            self.state.read_latest_candidate(**self.identity(), **self.inputs())
        self.assertEqual(self.read().record["version_id"], second.version_id)
        self.state._insert_receipt = original_insert
        restored = self.rollback(first, second)
        self.assertEqual(self.rollback(first, second), restored)
        self.activate(restored.record, second.version_id)
        self.assertEqual(self.read().record["version_id"], "fictional-restored-v3")

    def test_supplied_outcome_revision_preserves_causal_lineage_and_stays_inactive(self):
        first, content = self.version(1)
        self.put(first, content)
        self.activate(first)
        decision = self.event(b"fictional supplied decision", event_type="decision",
                              parents=(self.source_one.event_id,), timestamp="2026-09-29T12:00:00Z")
        outcome = self.event(b"fictional separately observed outcome", event_type="outcome",
                             parents=(decision.event_id,), timestamp="2026-09-29T12:30:00Z")
        for event in (decision, outcome):
            self.register_source(event)
            self.policy.allowed.add((event.event_id, "personal_judgment"))
        revision, content = self.version(2, source=outcome, previous=first.version_id,
                                        produced_at="2026-09-29T13:00:00Z")
        self.policy.allowed.remove((decision.event_id, "personal_judgment"))
        with self.assertRaisesRegex(ValueError, "not currently permitted"):
            self.state.register_outcome_revision(version=revision, content=content,
                decision_event_id=decision.event_id, outcome_event_id=outcome.event_id,
                verifier=self.verifier, **self.inputs())
        self.policy.allowed.add((decision.event_id, "personal_judgment"))
        self.state.register_outcome_revision(version=revision, content=content,
            decision_event_id=decision.event_id, outcome_event_id=outcome.event_id,
            verifier=self.verifier, **self.inputs())
        latest = self.state.read_latest_candidate(**self.identity(), **self.inputs())
        self.assertEqual(latest.record["source_evidence_ids"], [outcome.event_id])
        self.assertEqual(latest.record["supersedes_version_id"], first.version_id)
        self.assertEqual(self.read().record["version_id"], first.version_id)

    def test_superseded_claim_target_is_not_resurrected(self):
        for number in (1, 2):
            version_id, relation_id = f"claim-v{number}", f"relation-v{number}"
            self.claims.versions[version_id] = {
                "claim_id": "fictional-claim", "claim_version_id": version_id,
                "adjudication_state": "accepted", "evidence_relation_ids": [relation_id],
                "envelope": {"scope": self.scope.metadata_record(),
                             "authority_namespace_id": self.namespace,
                             "source_records": [self.source_one.event_id]}}
            self.claims.relations[relation_id] = {"evidence_record_id": self.source_one.event_id,
                                                 "target_record_id": version_id,
                                                 "target_record_type": "claim_version"}
        projection = {"claim_id": "fictional-claim", "current_claim_version_id": "claim-v1",
            "projection_id": "claim-projection", "validity_state": "current", "deletion_state": "active",
            "conflict_state": "none", "adjudication_state": "accepted"}
        self.claims.current["fictional-claim"] = projection
        first, content = self.version(1, claim_ids=("claim-v1",))
        self.put(first, content)
        self.activate(first)
        second, content = self.version(2, source=self.source_two, previous=first.version_id)
        self.put(second, content, first.version_id)
        self.activate(second, first.version_id)
        projection["current_claim_version_id"] = "claim-v2"
        with self.assertRaisesRegex(ValueError, "superseded claim"):
            self.rollback(first, second)

    def test_claim_head_race_cannot_open_an_unpermitted_new_source(self):
        for number, event in ((1, self.source_one), (2, self.source_two)):
            version_id, relation_id = f"race-claim-v{number}", f"race-relation-v{number}"
            self.claims.versions[version_id] = {
                "claim_id": "race-claim", "claim_version_id": version_id,
                "adjudication_state": "accepted", "evidence_relation_ids": [relation_id],
                "envelope": {"scope": self.scope.metadata_record(),
                    "authority_namespace_id": self.namespace, "source_records": [event.event_id]}}
            self.claims.relations[relation_id] = {"evidence_record_id": event.event_id,
                "target_record_id": version_id, "target_record_type": "claim_version"}
        projection = {"claim_id": "race-claim", "current_claim_version_id": "race-claim-v1",
            "projection_id": "race-projection", "validity_state": "current", "deletion_state": "active",
            "conflict_state": "none", "adjudication_state": "accepted"}
        self.claims.current["race-claim"] = projection
        self.policy.allowed.remove((self.source_two.event_id, "personal_judgment"))
        original_load = self.claims.load_current
        reads, opened = [], []
        def advance_head(claim_id):
            reads.append(claim_id)
            if len(reads) == 2:
                projection["current_claim_version_id"] = "race-claim-v2"
            return original_load(claim_id)
        self.claims.load_current = advance_head
        first, content = self.version(1, claim_ids=("race-claim-v1",))
        with observe_private_opens(opened):
            with self.assertRaisesRegex(PermissionError, "not permitted before raw read"):
                self.put(first, content)
        self.assertNotIn(self.source_two.payload_reference, opened)

    def test_stale_and_unsigned_approval_and_episode_self_promotion_fail(self):
        first, content = self.version(1)
        self.put(first, content)
        approval = self.approval(first.metadata_record())
        self.proofs.clear()
        with self.assertRaisesRegex(ValueError, "independently authorized"):
            self.state.activate(**self.identity(), approval_event_id=approval.event_id,
                expected_active_version_id=None, verifier=self.verifier, **self.inputs())
        self.activate(first)
        second, content = self.version(2, source=self.source_two, previous=first.version_id)
        self.put(second, content, first.version_id)
        approval = self.approval(second.metadata_record(), "absent-active-version")
        with self.assertRaisesRegex(ValueError, "stale active"):
            self.state.activate(**self.identity(), approval_event_id=approval.event_id,
                expected_active_version_id="absent-active-version", verifier=self.verifier, **self.inputs())
        episode_version, content = self.version(3, source=self.source_two, previous=second.version_id,
                                                episodes=("unaccepted-episode",))
        with self.assertRaisesRegex(ValueError, "episode lineage"):
            self.put(episode_version, content, second.version_id)


if __name__ == "__main__":
    unittest.main()
