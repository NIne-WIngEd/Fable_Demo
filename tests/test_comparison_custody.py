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
    evaluation_purpose, SelectedRunEvidencePolicy,
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


class NativeCustodyReadOrderTest(unittest.IsolatedAsyncioTestCase):
    async def test_revoked_phase_fails_before_private_decision_or_output_read(self):
        import test_comparison_run as fixtures
        f = fixtures.PairedComparisonContractTest()
        await f.asyncSetUp()
        self.addCleanup(f.doCleanups)
        run = await f.run_fixture()
        request = f.adapters["flora_full"].requests[0]
        result = await f.adapters["flora_full"].execute(request)
        _, log = f.policy.recorded[result.decision.event.event_id]
        store = object.__new__(XTDBComparisonCustody)
        store.scope, store.log = f.scope, log
        def metadata(run_id, artifact_id):
            if artifact_id == "plan":
                return ComparisonArtifact({"event_id": "fixture-plan-event", "metadata": {"plan_sha256": run.plan.digest()}})
            if artifact_id.startswith("history:"):
                _, case_id, phase = artifact_id.split(":")
                history = f.histories[(case_id, phase)]
                return ComparisonArtifact({"metadata": {"history_sha256": history.digest(),
                    "source_event_ids": list(history.event_ids)}})
            if artifact_id.startswith("question:"):
                return ComparisonArtifact({"content_sha256": fixtures.digest(request.question)})
            raise AssertionError("revoked phase progressed into private context lookup")
        store.metadata = metadata
        reads = []
        def forbidden_read(event_id):
            reads.append(event_id)
            raise AssertionError("revoked phase opened private output")
        store.load_recorded = forbidden_read
        policy = object.__new__(SelectedRunEvidencePolicy)
        policy.custody, policy.run_id, policy.requires_native_result = store, "run", True
        policy.native_lineage = SimpleNamespace(history_for=lambda case, phase: f.histories[(case, phase)])
        policy.authorize_history = lambda **fields: False
        with self.assertRaises(PermissionError):
            store.save_run(run_id="run", run=run, occurred_at="2026-09-29T15:00:00Z",
                execution_records={(request.case_id, request.phase, "flora_full"): (request, result)},
                evidence_policy=policy)
        self.assertEqual(reads, [])


if __name__ == "__main__":
    unittest.main()
