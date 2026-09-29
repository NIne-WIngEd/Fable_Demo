"""Actual selected backend lineage wiring; fictional producer outputs/proofs.

This certifies no learned behavior or actual exclusion of training data. The
qualified fixture receipts only exercise the independent phase-proof boundary.
"""
from dataclasses import replace
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

import psycopg
from cognitive_kernel.claim_contracts import CanonicalTaggedValue
from cognitive_kernel.formation_context_planner import FormationPlanningRequest
from flora.comparison_run import HistorySnapshot, SourceMaterial
from flora.selected.context import ContextPlan, StateRoute
from flora.selected.experiment_runtime import SuppliedClaimAdmission
from flora.selected.judgment_lineage import NativeJudgmentLineageVerifier


def _fixture(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_ROOT = Path(__file__).resolve().parents[1]
_lineage_fixture = _fixture("flora_lineage_exact_unit_fixture", _ROOT / "test_selected_judgment_lineage.py")
_runtime_fixture = _fixture("flora_lineage_exact_backend_fixture", Path(__file__).parent / "test_selected_runtime_bridge.py")


class SelectedJudgmentLineageIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.fabric = _runtime_fixture.SelectedExperimentRuntimeIntegrationTest()
        self.fabric.setUp()
        self.addCleanup(self.fabric.doCleanups)

    def test_exact_approved_native_state_history_output_recreation_and_revocation(self):
        f = self.fabric
        original = f.fabric._source(b"fictional lineage fixture source")
        f._judgment_permission(f.registry.lookup(original.event_id))
        bundle, _ = f.fabric._bundle(original, prefix="lineage-fixture")
        f.qualifier = _lineage_fixture.FictionalPhaseQualifier(f.qualification_key.public_key())
        f._artifact("memory_formation", bundle)
        f._artifact("personality_judgment")
        formed = f.runtime.form_experience(request=FormationPlanningRequest(scope=f.scope,
            authority_namespace_id=f.namespace, experience_refs=(original.event_id,)),
            invocation_id="lineage-formation", value_resolver=_runtime_fixture._fabric_fixture._Values(
                f.scope, f.namespace, {"value-one": CanonicalTaggedValue.create(type_tag="text", value="fictional one"),
                                      "value-two": CanonicalTaggedValue.create(type_tag="text", value="fictional two")}))
        at, proposal_id = f.fabric._time(), formed.bundle.proposals[0].proposal_id
        adapter = _runtime_fixture._semantic_fixture.FixtureSemanticAdapter(at=at)
        bound = f.admission.prepare(bundle_id=formed.bundle.bundle_id, proposal_id=proposal_id,
            adapter=adapter, log=f.log, objects=f.objects, source_store=formed.prepared.store)
        adjudication = _runtime_fixture._semantic_fixture.fixture_adjudication(bound, at=at)
        f.fabric.semantic_proof.approve_fixture(adjudication, bound)
        accepted = f.runtime.admit_proposal(formed, SuppliedClaimAdmission(
            proposal_id, adapter, adjudication, f.fabric.semantic_proof))
        version = f._state_activation(accepted, original)
        plan = ContextPlan(request_id="selected-lineage-plan", purpose="personal_judgment",
            exact_claim_ids=(accepted.claim_id,), minimum_claims=1,
            state_routes=(StateRoute("owner", f.scope.host_instance_id, version.projection_id),))
        judged = f.runtime.judge(plan=plan, task=b"same lineage task", invocation_id="lineage-native-call")
        history = HistorySnapshot(f.scope, (SourceMaterial(original,
            f.objects.get(f.references.get(original.payload_reference))),))
        histories = {("case-one", "after"): history}
        request = SimpleNamespace(scope=f.scope, case_id="case-one", phase="after", context=judged.context,
            question=b"same lineage task", authorized_history_sha256=history.digest(), authorized_event_ids=history.event_ids,
            plan=SimpleNamespace(digest=lambda: "9" * 64),
            binding=SimpleNamespace(producer_component="fictional-supplied-output-adapter",
                model_artifact_sha256=judged.execution.invocation.artifact.checkpoint_sha256))
        result = SimpleNamespace(output=judged.execution.result.output, delivery=judged.delivery, decision=judged.decision)

        def verifier():
            return NativeJudgmentLineageVerifier(runtime=f.runtime, run_plan_sha256="9" * 64,
                history_authority=_lineage_fixture.FrozenHistoryAuthority(histories),
                history_for=lambda case, phase: histories[(case, phase)],
                invocation_id_for=lambda request, result: "lineage-native-call",
                phase_receipt_for=lambda snapshot: _lineage_fixture.fictional_phase_receipt(snapshot, f.qualification_key))

        verified = verifier().verify_native_result_details(request, result)
        self.assertEqual(verified.context_lineage.original_event_ids, (original.event_id,))
        self.assertEqual(verified.context_lineage.internal[0].event_id, judged.context.items[1].approval_event_id)
        self.assertEqual(verified.qualified_output, judged.execution.output_record)
        with self.assertRaises(ValueError):
            verifier().verify_native_result(request, SimpleNamespace(**{**vars(result), "output": b"changed"}))
        dsn = f.connection.info.dsn
        f.connection.close()
        reopened = psycopg.connect(dsn, autocommit=True)
        self.addCleanup(reopened.close)
        f._bind_services(reopened)
        self.assertEqual(verifier().verify_native_result_details(request, result), verified)
        f._judgment_permission(f.registry.lookup(original.event_id), "revoke")
        self.assertFalse(verifier().authorize_context(case_id="case-one", phase="after", history=history,
                                                      context=judged.context, arm="flora_full"))
        with self.assertRaises((ValueError, PermissionError)):
            verifier().verify_native_result(request, result)


if __name__ == "__main__":
    unittest.main()
