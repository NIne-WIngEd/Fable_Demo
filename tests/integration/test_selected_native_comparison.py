"""Actual native paired-run custody, with fictional producer outputs/proofs.

Selected engines/permissions/runtime/lineage/custody are real. Supplied checkpoint,
phase receipts, output and usage are fixtures; no learned advantage is measured.
"""
import asyncio
from dataclasses import replace
import hashlib
import importlib.util
from pathlib import Path
import sys
import unittest
import uuid

from cognitive_kernel.claim_contracts import CanonicalTaggedValue
from cognitive_kernel.formation_context_planner import FormationPlanningRequest
from flora.comparison_run import (
    ArmBinding, ArmResult, HistorySnapshot, MeasuredUsage, PairedRunPlan,
    SourceMaterial, run_paired,
)
from flora.evaluation_protocol import ARMS, EvaluationCase, EvaluationProtocol
from flora.selected.comparison_custody import SelectedRunEvidencePolicy, XTDBComparisonCustody, evaluation_purpose
from flora.selected.context import ContextPlan, StateRoute
from flora.selected.experiment_runtime import SuppliedClaimAdmission
from flora.selected.formation_policy import FormationPermissionAction, formation_permission_payload
from flora.selected.judgment_lineage import NativeJudgmentLineageVerifier


def fixture(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_ROOT = Path(__file__).resolve().parents[1]
_runtime = fixture("flora_native_comparison_backend_fixture", Path(__file__).parent / "test_selected_runtime_bridge.py")
_phase = fixture("flora_native_comparison_phase_fixture", _ROOT / "test_selected_judgment_lineage.py")


class SelectedNativeComparisonIntegrationTest(unittest.TestCase):
    def test_actual_phase_context_execution_parent_and_private_run_custody(self):
        f = _runtime.SelectedExperimentRuntimeIntegrationTest()
        f.setUp()
        self.addCleanup(f.doCleanups)
        original = f.fabric._source(b"fictional native comparison original")
        f._judgment_permission(f.registry.lookup(original.event_id))
        bundle, _ = f.fabric._bundle(original, prefix="paired-native-fixture")
        f.qualifier = _phase.FictionalPhaseQualifier(f.qualification_key.public_key())
        f._artifact("memory_formation", bundle)
        f._artifact("personality_judgment")
        formed = f.runtime.form_experience(request=FormationPlanningRequest(scope=f.scope,
            authority_namespace_id=f.namespace, experience_refs=(original.event_id,)),
            invocation_id="paired-formation", value_resolver=_runtime._fabric_fixture._Values(f.scope, f.namespace, {
                "value-one": CanonicalTaggedValue.create(type_tag="text", value="fictional one"),
                "value-two": CanonicalTaggedValue.create(type_tag="text", value="fictional two")}))
        adapter = _runtime._semantic_fixture.FixtureSemanticAdapter(at=f.fabric._time())
        proposal = formed.bundle.proposals[0].proposal_id
        bound = f.admission.prepare(bundle_id=formed.bundle.bundle_id, proposal_id=proposal, adapter=adapter,
            log=f.log, objects=f.objects, source_store=formed.prepared.store)
        adjudication = _runtime._semantic_fixture.fixture_adjudication(bound, at=f.fabric._time())
        f.fabric.semantic_proof.approve_fixture(adjudication, bound)
        accepted = f.runtime.admit_proposal(formed, SuppliedClaimAdmission(proposal, adapter, adjudication, f.fabric.semantic_proof))
        state = f._state_activation(accepted, original)
        context_plan = ContextPlan(request_id="paired-native-context", purpose="personal_judgment",
            exact_claim_ids=(accepted.claim_id,), minimum_claims=1,
            state_routes=(StateRoute("owner", f.scope.host_instance_id, state.projection_id),))
        later = f.fabric._source(b"fictional unrelated later correction", correction_parent=original.event_id)
        f._judgment_permission(f.registry.lookup(later.event_id))
        sources = tuple(SourceMaterial(event, f.objects.get(f.references.get(event.payload_reference)))
                        for event in (original, later))
        histories = {("case", "before"): HistorySnapshot(f.scope, sources[:1]),
                     ("case", "after"): HistorySnapshot(f.scope, sources)}
        question = b"Same fictional native decision task?"
        case = EvaluationCase("case", f.scope.host_instance_id, "irrelevant_correction", "heldout",
            histories[("case", "before")].digest(), histories[("case", "after")].digest(), "a" * 64, later.event_id)
        protocol = EvaluationProtocol("paired-native-fixture", "b" * 64, "2026-09-29T00:00:00Z",
            "fictional-feature", 100, 60000, (case,), "c" * 64, "d" * 64, "e" * 64, "f" * 64,
            ("fictional-unused-transfer-host",))
        artifact = f.runtime._resolve("personality_judgment")[1]
        bindings = {arm: ArmBinding("fixture-unused-producer", "1" * 64, "2" * 64, "fixture-unused") for arm in ARMS}
        bindings["flora_full"] = ArmBinding("fictional-supplied-output-adapter", artifact.checkpoint_sha256,
                                           "3" * 64, "fictional-fixed-output-no-learning")
        plan = PairedRunPlan(protocol, bindings, 100, 20000, 1, {"case": hashlib.sha256(question).hexdigest()})
        custody = XTDBComparisonCustody(scope=f.scope, authority_namespace_id=f.namespace, connection=f.connection,
            registry=f.registry, objects=f.objects, log=f.log)
        custody.register_inputs(run_id="native-run", plan=plan, histories=histories,
                                questions={"case": question}, occurred_at=f.fabric._time())

        def grant(source, purpose, decision="allow"):
            prior = f.policy.current_action(source.evidence.ref_id, purpose)
            prior_event = None if prior is None else f.policy._stored_action(prior.action_id)["request_event_id"]
            action = FormationPermissionAction.create(scope=f.scope, authority_namespace_id=f.namespace,
                action_id="pair-grant-" + uuid.uuid4().hex, source_ref_id=source.evidence.ref_id,
                source_registration_sha256=source.registration_sha256, purpose=purpose, decision=decision,
                generation=1 if prior is None else prior.generation + 1,
                previous_action_sha256=None if prior is None else prior.action_sha256,
                authorization_ref="fictional-enrolled-owner", authorized_at=f.fabric._time())
            event, raw = f.fabric._append(formation_permission_payload(action), event_type="formation_permission_action",
                parents=(source.evidence.ref_id,) if prior is None else (source.evidence.ref_id, prior_event),
                at=action.authorized_at, provenance="owner_attested_canonical")
            f.private.register_formation_permission(action=action, request_event_id=event.event_id,
                raw=raw, log=f.log, objects=f.objects)
            f._persist_proof(event, "formation_permission")
            f.policy.apply(action, request_event_id=event.event_id, log=f.log, objects=f.objects,
                references=f.references, verifier=f.owner_verifier)

        for (case_id, phase), history in histories.items():
            for event_id in history.event_ids:
                grant(f.registry.lookup(event_id), evaluation_purpose("native-run", case_id, phase))
        history_authority = SelectedRunEvidencePolicy(custody=custody, run_id="native-run", permissions=f.policy)
        verifier = NativeJudgmentLineageVerifier(runtime=f.runtime, history_authority=history_authority,
            run_plan_sha256=plan.digest(), history_for=lambda case, phase: histories[(case, phase)],
            invocation_id_for=lambda request, result: "paired-native-" + request.phase,
            phase_receipt_for=lambda snapshot: _phase.fictional_phase_receipt(snapshot, f.qualification_key))
        policy = SelectedRunEvidencePolicy(custody=custody, run_id="native-run", permissions=f.policy,
                                           native_lineage=verifier)
        executions = {}
        class SuppliedFixtureNativeArm:
            async def prepare(self, request):
                return f.runtime._context(context_plan)
            async def execute(self, request):
                actual = f.runtime.judge(plan=context_plan, task=request.question,
                                         invocation_id="paired-native-" + request.phase)
                for recorded in (actual.delivery, actual.execution.output_record, actual.decision):
                    custody.register_recorded(recorded)
                custody.register_context(run_id="native-run", context=actual.context,
                                         delivery=actual.delivery, occurred_at=f.fabric._time())
                # Explicit fake metering fixture; production metering is external.
                result = ArmResult(actual.execution.result.output, actual.delivery, actual.decision,
                                   MeasuredUsage("fictional-feature", 5, 10, 5, 0))
                executions[(request.case_id, request.phase, "flora_full")] = (request, result)
                return result
        run = asyncio.run(run_paired(plan=plan, histories=histories, questions={"case": question},
            adapters={"flora_full": SuppliedFixtureNativeArm()}, evidence_policy=policy))
        self.assertEqual([attempt.status for attempt in run.attempts if attempt.arm == "flora_full"], ["success"] * 2)
        self.assertEqual(sum(attempt.status == "unavailable" for attempt in run.attempts), 4)
        for request, result in executions.values():
            self.assertNotIn(request.context.items[1].approval_event_id, request.authorized_event_ids)
            self.assertEqual(policy.verify_native_result(request, result).event.event_type, "qualified_model_output")
        with self.assertRaisesRegex(ValueError, "independent current execution lineage"):
            custody.save_run(run_id="native-run", run=run, occurred_at=f.fabric._time())
        changed = dict(executions)
        key = ("case", "before", "flora_full")
        request, result = changed[key]
        changed[key] = (replace(request, question=b"different task"), result)
        with self.assertRaisesRegex(ValueError, "frozen successful attempt"):
            custody.save_run(run_id="native-run", run=run, occurred_at=f.fabric._time(),
                             execution_records=changed, evidence_policy=policy)
        custody.save_run(run_id="native-run", run=run, occurred_at=f.fabric._time(),
                         execution_records=executions, evidence_policy=policy)
        self.assertIsNotNone(custody.metadata("native-run", "run"))
        # A fresh denial blocks replay acceptance, not just subsequent inference.
        f._judgment_permission(f.registry.lookup(original.event_id), "revoke")
        with self.assertRaises((ValueError, PermissionError)):
            custody.save_run(run_id="native-run", run=run, occurred_at=f.fabric._time(),
                             execution_records=executions, evidence_policy=policy)


if __name__ == "__main__":
    unittest.main()
