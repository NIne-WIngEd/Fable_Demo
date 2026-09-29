"""Custody helper/read-barrier contracts, not selected-backend qualification."""

from dataclasses import replace
import hashlib
import json
from types import SimpleNamespace
import unittest

from flora.comparison_run import ArmBinding, PairedRunPlan
from flora.evaluation_protocol import ARMS, EvaluationCase, EvaluationProtocol
from flora.selected.comparison_custody import (
    ComparisonArtifact, XTDBComparisonCustody, _plan_from_record, _plan_record,
    evaluation_purpose,
)


class ComparisonCustodyContractTest(unittest.TestCase):
    def test_plan_round_trip_preserves_frozen_questions_and_arm_lineage(self):
        case = EvaluationCase("case", "host", "relevant_correction", "heldout",
                              "a" * 64, "b" * 64, "c" * 64, "correction")
        protocol = EvaluationProtocol("protocol", "d" * 64, "2026-09-29T00:00:00Z",
                                      "feature", 16, 1000, (case,), "e" * 64,
                                      "f" * 64, "1" * 64, "2" * 64, ("other-host",))
        plan = PairedRunPlan(protocol,
                            {arm: ArmBinding("producer", "3" * 64, "4" * 64, "explicit-update")
                             for arm in ARMS}, 32, 4096, 2, {"case": "5" * 64})
        stored = json.loads(json.dumps(_plan_record(plan)))
        self.assertEqual(_plan_from_record(stored).digest(), plan.digest())
        stored["question_sha256_by_case"]["case"] = "6" * 64
        self.assertNotEqual(_plan_from_record(stored).digest(), plan.digest())

    def test_phase_specific_permission_never_reuses_after_scope_for_before(self):
        self.assertNotEqual(evaluation_purpose("run", "case", "before"),
                            evaluation_purpose("run", "case", "after"))
        with self.assertRaises(ValueError):
            evaluation_purpose("Run", "case", "before")

    def test_read_checks_current_authority_again_after_raw_io(self):
        content = b"fictional encrypted custody content"
        artifact = ComparisonArtifact({"event_id": "event", "kind": "output",
                                       "content_sha256": hashlib.sha256(content).hexdigest()})
        store = object.__new__(XTDBComparisonCustody)
        store.scope = "fixture-scope"
        store.metadata = lambda run, artifact_id: artifact
        source = SimpleNamespace(object_ref="object")
        store.registry = SimpleNamespace(lookup=lambda event: source)
        class CurrentPermission:
            allowed = True
            def permits(self, source, purpose):
                return self.allowed
        permission = CurrentPermission()
        def read(scope, object_ref):
            permission.allowed = False
            return content
        store.raw_custody = SimpleNamespace(read=read)
        with self.assertRaisesRegex(PermissionError, "withdrawn"):
            store.read(run_id="run", artifact_id="artifact", permissions=permission,
                       purpose="comparison_review")

    def test_private_key_never_opens_through_reviewer_or_external_purpose(self):
        store = object.__new__(XTDBComparisonCustody)
        store.metadata = lambda run, artifact_id: ComparisonArtifact({"kind": "blind_key"})
        for purpose in ("comparison_review", "comparison_external:provider", "comparison_unblind"):
            with self.subTest(purpose=purpose), self.assertRaisesRegex(PermissionError, "sealed assessment"):
                store.read(run_id="run", artifact_id="blind_key", permissions=None, purpose=purpose)

    def test_orchestrator_manifest_never_becomes_phase_inference_input(self):
        store = object.__new__(XTDBComparisonCustody)
        purpose = evaluation_purpose("run", "case", "before")
        for kind in ("plan", "run", "blind_pack", "blind_key"):
            store.metadata = lambda run, artifact_id, kind=kind: ComparisonArtifact({"kind": kind})
            with self.subTest(kind=kind), self.assertRaises(PermissionError):
                store.read(run_id="run", artifact_id=kind, permissions=None, purpose=purpose)

    def test_assessment_closure_grant_cannot_open_labeled_ancestor_artifacts(self):
        store = object.__new__(XTDBComparisonCustody)
        for kind in ("plan", "run", "context", "history", "question", "output", "rejected_output", "blind_pack"):
            store.metadata = lambda run, artifact_id, kind=kind: ComparisonArtifact({"kind": kind})
            with self.subTest(kind=kind), self.assertRaisesRegex(PermissionError, "source-closure"):
                store.read(run_id="run", artifact_id=kind, permissions=None,
                           purpose="comparison_assessment:collection")


if __name__ == "__main__":
    unittest.main()
