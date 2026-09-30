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
        phased = replace(plan, phase_bindings={
            ("case", phase, arm): replace(plan.arm_bindings[arm],
                model_artifact_sha256=("7" if phase == "before" else "8") * 64)
            for phase in ("before", "after") for arm in ARMS})
        self.assertEqual(_plan_from_record(json.loads(json.dumps(_plan_record(phased)))).digest(), phased.digest())
        anchored = replace(phased, preregistration_sha256="9" * 64)
        stored_anchor = json.loads(json.dumps(_plan_record(anchored)))
        self.assertEqual(_plan_from_record(stored_anchor).digest(), anchored.digest())
        self.assertNotEqual(anchored.digest(), phased.digest())
        changed_anchor = replace(anchored, preregistration_sha256="a" * 64)
        self.assertNotEqual(changed_anchor.digest(), anchored.digest())
        with self.assertRaisesRegex(ValueError, "complete observed"):
            replace(plan, preregistration_sha256="9" * 64).validate()

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

    def test_provider_attempt_cannot_open_through_generic_recorded_route(self):
        store = object.__new__(XTDBComparisonCustody)
        store.registry = SimpleNamespace(lookup=lambda event: SimpleNamespace(object_ref="private-object"))
        store.raw_custody = SimpleNamespace(read=lambda *_: self.fail("generic comparison opened provider audit bytes"))
        for kind in ("comparison_artifact", "provider_attempt_artifact", "phase_snapshot_artifact", "experiment_manifest_artifact"):
            store.log = SimpleNamespace(replay=lambda: [SimpleNamespace(event_id="attempt", event_type=kind)])
            with self.subTest(kind=kind), self.assertRaisesRegex(PermissionError, "separately authorized audit"):
                store.load_recorded("attempt")

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

    def test_preregistration_controls_never_open_through_generic_artifact_read(self):
        store = object.__new__(XTDBComparisonCustody)
        for kind in ("preregistration_anchor", "preregistration_slot", "preregistration_final_binding"):
            store.metadata = lambda run, artifact_id, kind=kind: ComparisonArtifact({"kind": kind})
            store._read_authorized = lambda **_: self.fail("generic route opened private control")
            with self.subTest(kind=kind), self.assertRaisesRegex(PermissionError, "dedicated recovery"):
                store.read(run_id="run", artifact_id="control", permissions=None, purpose="comparison_review")

    def test_durable_anchor_requires_actual_final_authority_even_when_omitted(self):
        store = object.__new__(XTDBComparisonCustody)
        store.metadata = lambda run, artifact_id: ComparisonArtifact({"kind": "preregistration_anchor"})
        for supplied in (None, True, SimpleNamespace(authorize_plan=lambda **_: True)):
            with self.subTest(supplied=type(supplied).__name__), self.assertRaisesRegex(PermissionError, "actual final"):
                store.require_final_authority(run_id="run", final_authority=supplied)

    def test_committed_unindexed_anchor_cannot_be_treated_as_legacy(self):
        store = object.__new__(XTDBComparisonCustody)
        store.metadata = lambda *_: None
        store._key = lambda *_: "anchor-key"
        event = SimpleNamespace(provenance=SimpleNamespace(derivation_activity_id="comparison:anchor-key"))
        store.log = SimpleNamespace(replay_committed=lambda: [SimpleNamespace(event=event)])
        with self.assertRaisesRegex(PermissionError, "reconciliation"):
            store.require_final_authority(run_id="run")

    def test_anchor_denies_context_before_history_or_private_reads(self):
        store = object.__new__(XTDBComparisonCustody)
        store.metadata = lambda *_: ComparisonArtifact({"kind": "preregistration_anchor"})
        policy = object.__new__(SelectedRunEvidencePolicy)
        policy.custody, policy.run_id, policy.final_authority = store, "run", None
        policy.authorize_history = lambda **_: self.fail("unsealed evaluation reached private history")
        with self.assertRaisesRegex(PermissionError, "actual final"):
            policy.authorize_context(case_id="case", phase="before", history=None,
                                     context=None, arm="general_model_memory")

    def test_original_inputs_cannot_register_under_an_arbitrary_anchor_port(self):
        store = object.__new__(XTDBComparisonCustody)
        with self.assertRaisesRegex(PermissionError, "actual canonical anchor"):
            store.register_preregistered_inputs(run_id="run", preregistration=SimpleNamespace(),
                histories={}, questions={}, occurred_at="2026-09-30T00:00:00Z")


class NativeCustodyReadOrderTest(unittest.IsolatedAsyncioTestCase):
    async def test_runner_refuses_unsealed_or_duck_typed_anchor_before_prepare(self):
        import test_comparison_run as fixtures
        f = fixtures.PairedComparisonContractTest()
        await f.asyncSetUp()
        self.addCleanup(f.doCleanups)
        phased = replace(f.plan, phase_bindings={
            (case.case_id, phase, arm): f.plan.arm_bindings[arm]
            for case in f.plan.protocol.cases for phase in ("before", "after") for arm in ARMS},
            preregistration_sha256="9" * 64)
        f.policy.authorize_history = lambda **_: self.fail("anchored run reached original reads")
        with self.assertRaisesRegex(PermissionError, "actual selected final"):
            await f.run_fixture(plan=phased)
        store = object.__new__(XTDBComparisonCustody)
        store.metadata = lambda *_: ComparisonArtifact({"kind": "preregistration_anchor"})
        policy = object.__new__(SelectedRunEvidencePolicy)
        policy.custody, policy.run_id, policy.final_authority = store, "run", None
        with self.assertRaisesRegex(PermissionError, "actual final"):
            # Even removing the anchor field from the caller's plan cannot
            # opt the actual anchored selected run into the legacy path.
            await f.run_fixture(evidence_policy=policy)
        self.assertTrue(all(not adapter.preparations for adapter in f.adapters.values()))

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
        # This test exercises legacy native private-read ordering. Anchored
        # lifecycle and omission refusal are covered by the separate cases.
        store.preregistration_metadata = lambda _: None
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
