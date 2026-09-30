"""Selected-adapter boundary fixtures; not selected-backend qualification.

The injected comparison transcript records immutable encrypted artifact calls.
The production adapter itself always uses selected comparison custody.
"""

import base64
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from cryptography.exceptions import InvalidSignature

from cognitive_kernel.canonical import canonical_json_bytes
from cognitive_kernel.contracts import ProductHostScope
from flora.selected.assessment_custody import (
    XTDBAssessmentCustody, assessment_artifact_id, assessment_purpose, assessment_rating_id,
)
from flora.selected.comparison_custody import ComparisonArtifact
from flora.selected.object_store import EncryptedObjectPlane, LocalObjectBackend
import test_blind_assessment as fixture_support
import test_sealed_analysis as analysis_fixture


class ComparisonTranscript:
    """Call/custody fixture only; neither XTDB nor a replacement datastore."""

    def __init__(self, root, fixture):
        self.scope = ProductHostScope.create(product_id="friday", host_instance_id="fictional-assessment-host",
            schema_version="1.0.0", encryption_domain="fictional-assessment-custody")
        self.authority_namespace_id = "fictional-comparison-authority"
        self.objects = EncryptedObjectPlane(scope=self.scope, key=b"r" * 32,
            backend=LocalObjectBackend(root))
        self.fixture, self.records, self.raws, self.sources = fixture, {}, {}, {}
        self.key_opens, self.on_key_read = 0, None
        self.on_read = None
        self.registry = SimpleNamespace(lookup=lambda event_id: self.sources.get(event_id))
        self._put(run_id="run", artifact_id="plan", kind="plan", content=canonical_json_bytes(fixture.run.plan.protocol.record()),
            parents=(), metadata={"plan_sha256": fixture.run.plan.digest()}, occurred_at="fixture-time")
        self._put(run_id="run", artifact_id="run", kind="run", content=b"fictional supplied full run receipts",
            parents=(), metadata={"plan_sha256": fixture.run.plan.digest()}, occurred_at="fixture-time")
        self._put(run_id="run", artifact_id="blind_pack", kind="blind_pack", content=canonical_json_bytes(fixture.pack),
            parents=(), metadata={"public_pack_sha256": fixture.spec.review_pack_sha256}, occurred_at="fixture-time")
        self._put(run_id="run", artifact_id="blind_key", kind="blind_key", content=canonical_json_bytes(fixture.key),
            parents=(), metadata={}, occurred_at="fixture-time")

    def _put(self, *, run_id, artifact_id, kind, content, parents, metadata, occurred_at):
        raw = self.objects.put(content)
        record = {"event_id": f"fictional-event-{len(self.records)}", "kind": kind,
            "content_sha256": raw.plaintext_sha256, "object_id": raw.object_id,
            "parent_event_ids": list(parents), "metadata": metadata}
        prior = self.records.get((run_id, artifact_id))
        if prior is not None:
            candidate = {**record, "event_id": prior.event_id}
            if prior.record != candidate:
                raise ValueError("fictional call recorder refused immutable artifact replacement")
            return prior
        artifact = ComparisonArtifact(record)
        self.records[(run_id, artifact_id)] = artifact
        self.raws[raw.object_id] = raw
        self.sources[artifact.event_id] = SimpleNamespace(ref_id=artifact.event_id, object_ref=raw.object_id)
        return artifact

    def metadata(self, run_id, artifact_id):
        return self.records.get((run_id, artifact_id))

    def read(self, *, run_id, artifact_id, permissions, purpose):
        artifact = self.metadata(run_id, artifact_id)
        if artifact.record["kind"] == "blind_key":
            raise PermissionError("private key requires sealed assessment release")
        if not permissions.permits(self.sources[artifact.event_id], purpose):
            raise PermissionError("fictional current source-purpose permission denied")
        content = self.objects.get(self.raws[artifact.record["object_id"]])
        if self.on_read:
            self.on_read(artifact_id)
        if not permissions.permits(self.sources[artifact.event_id], purpose):
            raise PermissionError("fictional current source-purpose permission withdrawn")
        return content

    def recover_run(self, *, run_id, permissions, purpose):
        self.read(run_id=run_id, artifact_id="run", permissions=permissions, purpose=purpose)
        return self.fixture.run

    def export_review(self, *, run_id, permissions):
        return json.loads(self.read(run_id=run_id, artifact_id="blind_pack", permissions=permissions, purpose="comparison_review"))

    def _read_private_key_for_sealed_assessment(self, *, run_id, permissions):
        artifact = self.metadata(run_id, "blind_key")
        source = self.sources[artifact.event_id]
        if not permissions.permits(source, "comparison_unblind"):
            raise PermissionError("fictional unblind grant missing")
        self.key_opens += 1
        content = self.objects.get(self.raws[artifact.record["object_id"]])
        if self.on_key_read:
            self.on_key_read(self.key_opens)
        if not permissions.permits(source, "comparison_unblind"):
            raise PermissionError("fictional unblind grant withdrawn")
        return content


class CurrentPermissionFixture:
    def __init__(self, store):
        self.scope, self.authority_namespace_id = store.scope, store.authority_namespace_id
        self.denied_purposes = set()
        self.denied_sources = set()

    def permits(self, source, purpose):
        return source is not None and purpose not in self.denied_purposes and (source.ref_id, purpose) not in self.denied_sources


class AssessmentCustodyContractTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.fixture = fixture_support.BlindAssessmentContractTest()
        self.fixture.setUp()
        self.store = ComparisonTranscript(Path(self.directory.name) / "objects", self.fixture)
        self.permissions = CurrentPermissionFixture(self.store)
        self.adapter = XTDBAssessmentCustody(comparison_custody=self.store, signature_authority=self.fixture.authority)
        self.spec = self.fixture.spec
        self.adapter.register_spec(run_id="run", spec=self.spec, permissions=self.permissions, occurred_at="fixture-time")

    def _fill(self):
        for pair in self.fixture.pack["pairs"]:
            rating = self._rating(pair)
            self.adapter.submit_rating(run_id="run", collection_id=self.spec.collection_id, rating=rating,
                proof=self.fixture.reviewer_key.sign(rating.message()), permissions=self.permissions, occurred_at="fixture-time")

    def _rating(self, pair):
        return replace(self.fixture._rating(pair), rating_id=assessment_rating_id("run", self.spec.collection_id,
            pair["pair_id"], self.fixture.reviewer.reviewer_id))

    def _seal(self):
        time = "2026-09-29T10:02:00.000000Z"
        message = self.adapter.prepare_seal_message(run_id="run", collection_id=self.spec.collection_id,
            sealed_at=time, permissions=self.permissions)
        proof = self.fixture.coordinator_key.sign(message)
        return self.adapter.seal_collection(run_id="run", collection_id=self.spec.collection_id, sealed_at=time,
            proof=proof, permissions=self.permissions, occurred_at="fixture-time")

    def test_encrypted_spec_ratings_seal_recover_and_release_only_after_verification(self):
        with self.assertRaises(PermissionError):
            self.adapter.release_private_key(run_id="run", collection_id=self.spec.collection_id, permissions=self.permissions)
        self.assertEqual(self.store.key_opens, 0)
        self._fill()
        self._seal()
        restarted = XTDBAssessmentCustody(comparison_custody=self.store, signature_authority=self.fixture.authority)
        self.assertTrue(restarted.recover_collection(run_id="run", collection_id=self.spec.collection_id,
            permissions=self.permissions).sealed)
        self.assertEqual(restarted.release_private_key(run_id="run", collection_id=self.spec.collection_id,
            permissions=self.permissions), self.fixture.key)
        summary = restarted.aggregate_after_seal(run_id="run", collection_id=self.spec.collection_id, permissions=self.permissions)
        self.assertEqual(summary["acceptance_decision"], "not_evaluated")
        self.assertEqual(summary["total_attempts"], 18)

    def _prepare_analysis_custody(self):
        analysis_fixture.bind_fictional_analysis(self.fixture, analysis_fixture.fictional_analysis_spec())
        self.store = ComparisonTranscript(Path(self.directory.name) / "analysis-objects", self.fixture)
        self.permissions = CurrentPermissionFixture(self.store)
        self.adapter = XTDBAssessmentCustody(comparison_custody=self.store, signature_authority=self.fixture.authority)
        self.spec = self.fixture.spec
        self.adapter.register_spec(run_id="run", spec=self.spec, permissions=self.permissions, occurred_at="fixture-time")
        self._fill()
        self._seal()

    def test_explicit_analysis_after_seal_preserves_descriptives_and_no_part1_qualification(self):
        self._prepare_analysis_custody()
        # This transcript is an arithmetic/orchestration fixture, not selected
        # services. The actual typed terminal fence is exercised separately.
        with patch.object(self.adapter, "_assert_analysis_release_permissions", self.adapter._assert_release_permissions):
            report = self.adapter.analyze_after_seal(run_id="run", collection_id=self.spec.collection_id,
                permissions=self.permissions)
        self.assertEqual(report["metrics"][0]["possible_pairs"], 3)
        self.assertFalse(report["part1_qualified"])
        self.assertEqual(report["descriptives"]["acceptance_decision"], "not_evaluated")

    def test_release_withdrawal_after_slow_analysis_prevents_report_return(self):
        self._prepare_analysis_custody()
        from flora.selected import assessment_custody as module
        original = module.analyze_sealed_assessment
        for purpose in (assessment_purpose("run", self.spec.collection_id), "comparison_review", "comparison_unblind"):
            self.permissions.denied_purposes.clear()
            completed = []
            def withdraw_after_analysis(**fields):
                report = original(**fields)
                completed.append(report["schema"])
                self.permissions.denied_purposes.add(purpose)
                return report
            with self.subTest(purpose=purpose), patch.object(module, "analyze_sealed_assessment", withdraw_after_analysis), \
                    patch.object(self.adapter, "_assert_analysis_release_permissions", self.adapter._assert_release_permissions):
                with self.assertRaises(PermissionError):
                    self.adapter.analyze_after_seal(run_id="run", collection_id=self.spec.collection_id,
                        permissions=self.permissions)
            self.assertEqual(completed, ["flora-sealed-assessment-analysis-report-v1"])

    def test_retry_preserves_exact_rating_and_changed_rating_is_immutable(self):
        pair = self.fixture.pack["pairs"][0]
        rating = self._rating(pair)
        fields = dict(run_id="run", collection_id=self.spec.collection_id, rating=rating,
            proof=self.fixture.reviewer_key.sign(rating.message()), permissions=self.permissions, occurred_at="fixture-time")
        first = self.adapter.submit_rating(**fields)
        self.assertEqual(first, self.adapter.submit_rating(**fields))
        modified = replace(rating, labels={**rating.labels, "reason_fit": "prefer_left"})
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.adapter.submit_rating(**{**fields, "rating": modified, "proof": self.fixture.reviewer_key.sign(modified.message())})
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self._seal()
        self.assertEqual(self.store.key_opens, 0)

    def test_public_comparison_read_never_releases_key_even_with_grant(self):
        with self.assertRaisesRegex(PermissionError, "sealed assessment"):
            self.store.read(run_id="run", artifact_id="blind_key", permissions=self.permissions, purpose="comparison_unblind")
        self.assertEqual(self.store.key_opens, 0)

    def test_blind_collection_does_not_read_labeled_run_before_seal(self):
        # Producer registration has already completed with local run access.
        # Reviewer intake/recovery must now work without that purpose.
        self.permissions.denied_purposes.add("comparison_local_recovery")
        self._fill()
        self._seal()
        self.assertTrue(self.adapter.recover_collection(run_id="run", collection_id=self.spec.collection_id,
            permissions=self.permissions).sealed)
        self.assertEqual(self.store.key_opens, 0)

    def test_missing_or_self_declared_unsigned_seal_cannot_open_key(self):
        self._fill()
        collection = self.adapter.recover_collection(run_id="run", collection_id=self.spec.collection_id, permissions=self.permissions)
        forged = json.loads(collection.export_bytes())
        forged["seal"] = {"message": {"sealed_at": "2026-09-29T10:02:00.000000Z"},
            "coordinator_approval": self.spec.coordinator.record(), "proof_base64": base64.b64encode(b"x" * 64).decode(),
            "proof_sha256": hashlib.sha256(b"x" * 64).hexdigest()}
        self.store._put(run_id="run", artifact_id=assessment_artifact_id(self.spec.collection_id, "seal"),
            kind="assessment_seal", content=canonical_json_bytes(forged), parents=(),
            metadata={"collection_id": self.spec.collection_id}, occurred_at="fixture-time")
        with self.assertRaises(InvalidSignature):
            self.adapter.release_private_key(run_id="run", collection_id=self.spec.collection_id, permissions=self.permissions)
        self.assertEqual(self.store.key_opens, 0)

    def test_seal_cannot_disagree_with_actual_individual_durable_ratings(self):
        self._fill()
        self._seal()
        pair = self.fixture.pack["pairs"][0]
        artifact_id = assessment_artifact_id(self.spec.collection_id, "rating", pair_id=pair["pair_id"], reviewer_id=self.fixture.reviewer.reviewer_id)
        artifact = self.store.metadata("run", artifact_id)
        body = json.loads(self.store.objects.get(self.store.raws[artifact.record["object_id"]]))
        body["record"]["rating"]["labels"]["reason_fit"] = "prefer_left"
        # Test a changed physical reference; actual selected metadata also
        # refuses immutable registry/event substitution before this layer.
        raw = self.store.objects.put(canonical_json_bytes(body))
        self.store.raws[artifact.record["object_id"]] = raw
        with self.assertRaises(InvalidSignature):
            self.adapter.release_private_key(run_id="run", collection_id=self.spec.collection_id, permissions=self.permissions)
        self.assertEqual(self.store.key_opens, 0)

    def test_current_assessment_review_and_unblind_permissions_all_required(self):
        self._fill()
        self._seal()
        for purpose in (assessment_purpose("run", self.spec.collection_id), "comparison_review", "comparison_unblind"):
            self.permissions.denied_purposes = {purpose}
            with self.subTest(purpose=purpose), self.assertRaises(PermissionError):
                self.adapter.release_private_key(run_id="run", collection_id=self.spec.collection_id, permissions=self.permissions)

    def test_permission_withdrawal_during_last_key_io_prevents_return(self):
        self._fill()
        self._seal()
        def withdraw(count):
            if count == 2:
                self.permissions.denied_purposes.add(assessment_purpose("run", self.spec.collection_id))
        self.store.on_key_read = withdraw
        with self.assertRaisesRegex(PermissionError, "withdrawn before release"):
            self.adapter.release_private_key(run_id="run", collection_id=self.spec.collection_id, permissions=self.permissions)

    def test_scope_unknown_collection_and_frozen_reference_mismatches_rejected(self):
        wrong = CurrentPermissionFixture(self.store)
        wrong.scope = replace(self.store.scope, host_instance_id="other-host")
        with self.assertRaisesRegex(ValueError, "crosses host"):
            self.adapter.recover_collection(run_id="run", collection_id=self.spec.collection_id, permissions=wrong)
        with self.assertRaises(ValueError):
            self.adapter.recover_collection(run_id="run", collection_id="unknown-collection", permissions=self.permissions)
        changed = replace(self.spec, threshold_spec=b"not frozen threshold bytes")
        with self.assertRaises(ValueError):
            self.adapter.register_spec(run_id="run", spec=changed, permissions=self.permissions, occurred_at="fixture-time")

    def test_custom_rating_identity_cannot_collide_across_assignments(self):
        rating = replace(self._rating(self.fixture.pack["pairs"][0]), rating_id="caller-shared-rating-id")
        with self.assertRaisesRegex(ValueError, "derived from its exact"):
            self.adapter.submit_rating(run_id="run", collection_id=self.spec.collection_id, rating=rating,
                proof=self.fixture.reviewer_key.sign(rating.message()), permissions=self.permissions, occurred_at="fixture-time")

    def test_earlier_rating_revoked_during_later_read_prevents_unsealed_recovery(self):
        self._fill()
        assignments = self.spec.assignments
        first_id = assessment_artifact_id(self.spec.collection_id, "rating", pair_id=assignments[0][0], reviewer_id=assignments[0][1])
        second_id = assessment_artifact_id(self.spec.collection_id, "rating", pair_id=assignments[1][0], reviewer_id=assignments[1][1])
        source_id = self.store.metadata("run", first_id).event_id
        def revoke(artifact_id):
            if artifact_id == second_id:
                self.permissions.denied_sources.add((source_id, assessment_purpose("run", self.spec.collection_id)))
        self.store.on_read = revoke
        with self.assertRaisesRegex(PermissionError, "withdrawn during collection"):
            self.adapter.recover_collection(run_id="run", collection_id=self.spec.collection_id, permissions=self.permissions)


if __name__ == "__main__":
    unittest.main()
