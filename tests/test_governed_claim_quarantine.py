"""Governed quarantine transaction mechanics, no selected backend evidence.

Actual canonical contracts/crypto/raw objects are used. SQL is a deterministic
call recorder; real XTDB/Kurrent/derived cleanup qualification is separate.
"""
import base64
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cognitive_kernel.canonical import canonical_sha256
from cognitive_kernel.contracts import ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from flora.selected.claim_controller import XTDBClaimSequenceController
from flora.selected.formation_context import register_experience_source
from flora.selected.governed_quarantine import XTDBGovernedClaimQuarantine
from flora.selected.owner_authorization import Ed25519OwnerActionVerifier, OwnerActionProof, owner_action_message
from flora.selected.revocation import revocation_request
from flora.selected.source_native import read_current_source_manifest

spec = importlib.util.spec_from_file_location("flora_quarantine_admission_fixture",
    Path(__file__).parent / "test_selected_formation_admission.py")
_fixture = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = _fixture
spec.loader.exec_module(_fixture)


class GovernedClaimQuarantineTest(unittest.TestCase):
    def setUp(self):
        self.f = _fixture.SelectedFormationAdmissionTest()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        bound = self.f._bound()
        verdict = _fixture.fixture_adjudication(bound)
        self.f.verifier.approve_fixture(verdict, bound)
        self.accepted = self.f._admit(bound, verdict)
        self.prior = _fixture.fixture_projection(self.f.authority.load_current(self.accepted.claim_id))
        self.controller = XTDBGovernedClaimQuarantine(self.f.authority)
        self.key, self.proofs = Ed25519PrivateKey.generate(), {}
        self.verifier = Ed25519OwnerActionVerifier(scope=self.f.scope,
            owner_public_key=self.key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw), proofs=self.proofs)

    def _request(self, *, parents=None, at="2026-09-29T14:00:00Z", raw_bytes=None):
        # Extra unrelated canonical events ensure Kurrent position is not the
        # next Claim authority sequence.
        for number in range(3):
            event = ExperienceEvent.create(event_type="observation", scope=self.f.scope,
                occurred_at="2026-09-29T12:00:00Z", content_digest=hashlib.sha256(str(number).encode()).hexdigest(),
                provenance=ProvenanceReference.create(provenance_type="generated_reconstruction",
                    source_reference_ids=("noise-source-" + str(len(self.f.log.replay())),),
                    derivation_activity_id="quarantine-noise-" + str(number), responsible_component="fixture"),
                retention_class="ordinary_experience", storage_tier="raw_buffer")
            self.f.log.append(event, expected_revision=len(self.f.log.replay()) - 1)
        row = self.f.authority._fetch_record(table="fable_claim_versions",
            row_id=self.f.authority._row_id(self.prior.current_claim_version_id), all_valid=True)
        raw = self.f.objects.put(revocation_request(self.prior) if raw_bytes is None else raw_bytes)
        event = ExperienceEvent.create(event_type="deletion_request", scope=self.f.scope, occurred_at=at,
            content_digest=raw.plaintext_sha256, payload_reference=raw.object_id,
            parent_event_ids=(row["experience_event_id"],) if parents is None else parents,
            provenance=ProvenanceReference.create(provenance_type="generated_reconstruction",
                source_reference_ids=(raw.object_id,), derivation_activity_id="quarantine-owner-fixture",
                responsible_component="fixture-owner"), retention_class="ordinary_experience", storage_tier="raw_buffer")
        self.f.log.append(event, expected_revision=len(self.f.log.replay()) - 1)
        self.f.log.entries[-1] = replace(self.f.log.entries[-1], recorded_at=datetime(2026, 9, 29, 14, 1, tzinfo=timezone.utc))
        register_experience_source(event_id=event.event_id, raw=raw, registry=self.f.registry,
            log=self.f.log, objects=self.f.objects, role="generated_reconstruction", modality="structured")
        self.proofs[event.event_id] = OwnerActionProof("claim_quarantine", event.event_id, event.event_sha256,
            base64.b64encode(self.key.sign(owner_action_message(event, "claim_quarantine"))).decode())
        return event

    def _apply(self, event, **changes):
        values = dict(prior=self.prior, request_event_id=event.event_id, log=self.f.log,
            objects=self.f.objects, references=self.f.registry, verifier=self.verifier)
        values.update(changes)
        return self.controller.apply(**values)

    def test_atomic_pending_head_separate_sequences_retry_and_temporal_cleanup_request(self):
        event = self._request()
        receipt = self._apply(event)
        self.assertEqual(receipt.store_sequence, 2)
        self.assertGreater(receipt.event_stream_position, receipt.store_sequence)
        self.assertEqual(receipt.projection.source_position, 2)
        self.assertEqual(receipt.projection.deletion_state, "pending")
        self.assertEqual(self.f.authority.load_current(self.prior.claim_id), receipt.projection.metadata_record())
        with self.assertRaisesRegex(ValueError, "active, resolved"):
            read_current_source_manifest(claim_id=self.prior.claim_id, authority=self.f.authority, log=self.f.log)
        snapshot = deepcopy(self.f.connection.rows)
        self.controller = XTDBGovernedClaimQuarantine(self.f.authority)
        self.assertEqual(self._apply(event), receipt)
        self.assertEqual(self.f.connection.rows, snapshot)
        cleanup = self.controller.cleanup(receipt)
        self.assertEqual(cleanup["projection_sha256"], receipt.projection.projection_sha256)
        self.assertEqual(XTDBClaimSequenceController(self.f.authority).prepare().sequence, 3)

    def test_failure_rolls_back_counter_current_head_and_immutable_receipt(self):
        event = self._request()
        snapshot = deepcopy(self.f.connection.rows)
        self.f.connection.failure_table = "flora_governed_claim_quarantine_receipts"
        with self.assertRaisesRegex(RuntimeError, "insert failure"):
            self._apply(event)
        self.assertEqual(self.f.connection.rows, snapshot)
        self.assertEqual(self._apply(event).store_sequence, 2)

    def test_bad_owner_proof_and_wrong_exact_request_fail_before_request_plaintext_read(self):
        event = self._request()
        self.proofs[event.event_id] = replace(self.proofs[event.event_id], action="state_activation")
        reads, original = [], self.f.objects.get
        self.f.objects.get = lambda raw: (reads.append(raw.object_id), original(raw))[1]
        with self.assertRaises(PermissionError):
            self._apply(event)
        self.assertFalse(reads)
        other = self._request(raw_bytes=b"different control payload")
        reads.clear()  # Authorized fixture ingress read is outside apply.
        with self.assertRaisesRegex(ValueError, "digest/time differs"):
            self._apply(other)
        self.assertFalse(reads)

    def test_missing_prior_source_parent_future_or_stale_request_refused(self):
        with self.assertRaisesRegex(ValueError, "actual prior source parent"):
            self._apply(self._request(parents=()))
        with self.assertRaisesRegex(ValueError, "scope/type/digest/time"):
            self._apply(self._request(at="2026-09-29T15:00:00Z"))
        with self.assertRaisesRegex(ValueError, "time-invalid predecessor"):
            self._apply(self._request(at="2026-09-29T12:05:00Z"))

    def test_counter_cas_and_untracked_current_inventory_fence(self):
        event = self._request()
        key = ("fable_claim_heads", "other-untracked-head")
        row = {"_id": key[1], "scope_digest": self.f.authority.scope_digest, "source_position": 2}
        self.f.connection.rows[key] = row
        with self.assertRaisesRegex(ValueError, "untracked store sequence"):
            self._apply(event)
        del self.f.connection.rows[key]
        self.f.connection.before_transaction = lambda: self.f.connection.rows.update({key: row})
        with self.assertRaisesRegex(ValueError, "absence assertion failed"):
            self._apply(event)
        self.assertEqual(self.f.authority.load_current(self.prior.claim_id), self.prior.metadata_record())
        del self.f.connection.rows[key]
        allocation = XTDBClaimSequenceController(self.f.authority).prepare()
        with self.assertRaisesRegex(ValueError, "exact counter"):
            XTDBClaimSequenceController(self.f.authority).assert_allocation(replace(allocation, sequence=9))

    def test_changed_head_conflicting_second_request_and_receipt_mutation_refused(self):
        first = self._request()
        receipt = self._apply(first)
        second = self._request(at="2026-09-29T14:00:30Z")
        with self.assertRaisesRegex(ValueError, "stale/unavailable"):
            self._apply(second)
        key = ("flora_governed_claim_quarantine_receipts", self.f.authority._row_id(first.event_id))
        row = self.f.connection.rows[key]
        record = json.loads(row["record_json"])
        record["receipt"]["event_stream_position"] += 1
        record.pop("record_sha256")
        record["record_sha256"] = canonical_sha256(record)
        row.update(record_json=json.dumps(record), record_sha256=record["record_sha256"])
        with self.assertRaisesRegex(ValueError, "receipt lacks exact"):
            self._apply(first)
        self.assertEqual(self.f.authority.load_current(self.prior.claim_id), receipt.projection.metadata_record())


if __name__ == "__main__":
    unittest.main()
