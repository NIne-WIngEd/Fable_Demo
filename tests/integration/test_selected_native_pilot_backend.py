"""Selected-native synthetic intake/recovery; supplied producer fixtures only."""
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import sys
import unittest

from cognitive_kernel.claim_contracts import CanonicalTaggedValue
from cognitive_kernel.formation_context_planner import FormationPlanningRequest
from cognitive_kernel.formation_contracts import FormationProposal, MemoryProposalBundle
from flora.comparison_run import HistorySnapshot, SourceMaterial
from flora.pilot_ingress import materialize_before
from flora.selected.context import ContextPlan, StateRoute
from flora.selected.experiment_runtime import SuppliedClaimAdmission
from flora.selected.formation_context import prepare_selected_formation, register_experience_source
from flora.selected.judgment_lineage import NativeJudgmentLineageVerifier
from flora.selected.pilot_lifecycle import (
    NativeBeforeReference, NativeFormationReference, NativePilotPhaseSnapshotServices,
    apply_native_intervention, verify_native_before,
)
from flora.selected.phase_routes import PhaseSnapshotReference
from flora.selected.phase_snapshots import XTDBPhaseSnapshotCustody


def fixture(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_TESTS = Path(__file__).resolve().parents[1]
_runtime = fixture("flora_native_pilot_backend_runtime_fixture", Path(__file__).parent / "test_selected_runtime_bridge.py")
_phase = fixture("flora_native_pilot_backend_phase_fixture", _TESTS / "test_selected_judgment_lineage.py")
_PUBLIC = _TESTS.parent / "data/synthetic_pilot/v1.json"


class SelectedNativePilotBackendTest(unittest.TestCase):
    def build_before(self, intervention):
        f = _runtime.SelectedExperimentRuntimeIntegrationTest()
        f.setUp()
        self.addCleanup(f.doCleanups)
        public = json.loads(_PUBLIC.read_text())
        host, case_id = f.scope.host_instance_id.rsplit("-", 1)
        public["host_id"] = host
        selected = next(item for item in public["cases"] if item["intervention"] == intervention)
        selected["case_id"] = case_id
        path = Path(f.fabric.directory.name) / "native-pilot.json"
        path.write_text(json.dumps(public))
        checkpoint = materialize_before(path=path, case_id=case_id, scope=f.scope, log=f.log, objects=f.objects)
        originals = f.log.replay()
        for event in originals:
            raw = checkpoint.references[event.payload_reference]
            source = register_experience_source(event_id=event.event_id, raw=raw, registry=f.registry,
                log=f.log, objects=f.objects, role="generated_reconstruction", modality="text")
            f.fabric._permission(source, "allow")
            action, permission_event = f.fabric.grants[source.evidence.ref_id]
            f.private.register_formation_permission(action=action, request_event_id=permission_event.event_id,
                raw=f.fabric.raw_refs[permission_event.payload_reference], log=f.log, objects=f.objects)
            f._persist_proof(permission_event, "formation_permission")
            f._judgment_permission(source)
        request = FormationPlanningRequest(scope=f.scope, authority_namespace_id=f.namespace,
                                           experience_refs=(originals[0].event_id,))
        prepared = prepare_selected_formation(request=request, registry=f.registry, objects=f.objects,
                                             permits=f.policy.permits)
        # Exact fictional supplied output, never model inference or a quality
        # target. No extra unqualified candidate events are appended here.
        packet = prepared.assembled.packet
        bundle = MemoryProposalBundle(scope=f.scope, authority_namespace_id=f.namespace,
            bundle_id="native-pilot-fixture-template", experience_refs=packet.experience_refs,
            context_digest=packet.content_digest(), model_artifact_digest="a" * 64,
            inference_run_id="fixture-template-only", proposals=(FormationProposal(
                proposal_id="native-pilot-fixture-proposal", kind="preference", domain="host",
                subject_ref=f.scope.host_instance_id, value_ref="value-one",
                evidence_refs=(originals[0].event_id,), epistemic_status="reconstruction"),))
        f.qualifier = _phase.FictionalPhaseQualifier(f.qualification_key.public_key())
        f._artifact("memory_formation", bundle)
        f._artifact("personality_judgment")
        formed = f.runtime.form_experience(request=request, invocation_id="native-pilot-formation",
            value_resolver=_runtime._fabric_fixture._Values(f.scope, f.namespace,
                {"value-one": CanonicalTaggedValue.create(type_tag="text", value="fictional supplied preference")}))
        semantic = _runtime._semantic_fixture.FixtureSemanticAdapter(at=f.fabric._time())
        bound = f.admission.prepare(bundle_id=formed.bundle.bundle_id,
            proposal_id=formed.bundle.proposals[0].proposal_id, adapter=semantic,
            log=f.log, objects=f.objects, source_store=formed.prepared.store)
        adjudication = _runtime._semantic_fixture.fixture_adjudication(bound, at=f.fabric._time())
        f.fabric.semantic_proof.approve_fixture(adjudication, bound)
        accepted = f.runtime.admit_proposal(formed, SuppliedClaimAdmission(
            formed.bundle.proposals[0].proposal_id, semantic, adjudication, f.fabric.semantic_proof))
        state = f._state_activation(accepted, originals[0])
        plan = ContextPlan("native-pilot-before-context", "personal_judgment",
            exact_claim_ids=(accepted.claim_id,), state_routes=(StateRoute("owner", f.scope.host_instance_id,
                state.projection_id),), minimum_claims=1)
        task = selected["prompt"].encode()
        judgment = f.runtime.judge(plan=plan, task=task, invocation_id="native-pilot-judgment")
        history = HistorySnapshot(f.scope, tuple(SourceMaterial(event,
            f.objects.get(checkpoint.references[event.payload_reference])) for event in originals))
        histories = {(case_id, "before"): history}
        lineage = NativeJudgmentLineageVerifier(runtime=f.runtime,
            history_authority=_phase.FrozenHistoryAuthority(histories), run_plan_sha256="9" * 64,
            history_for=lambda case, phase: histories[(case, phase)],
            invocation_id_for=lambda *_: "native-pilot-judgment",
            phase_receipt_for=lambda value: _phase.fictional_phase_receipt(value, f.qualification_key))
        reference = NativeBeforeReference((NativeFormationReference(request, formed.bundle.bundle_id,
            "native-pilot-formation"),), plan, task, "native-pilot-judgment")
        return f, path, checkpoint, reference, lineage, judgment

    def test_actual_native_before_tail_then_correction_without_internal_history(self):
        f, path, checkpoint, reference, lineage, judgment = self.build_before("relevant_correction")
        initial = len(f.log.replay())
        verified = verify_native_before(path=path, checkpoint=checkpoint, reference=reference,
                                        runtime=f.runtime, lineage=lineage)
        self.assertEqual(len(f.log.replay()), initial)
        self.assertEqual(verified.native_decision_event_id, judgment.decision.event.event_id)
        self.assertGreater(len(verified.canonical_prefix), len(verified.original_event_ids))
        transition = apply_native_intervention(path=path, checkpoint=checkpoint, reference=reference,
            runtime=f.runtime, lineage=lineage, occurred_at=f.fabric._time())
        self.assertEqual(transition.after_history.event_ids[:-1], verified.original_event_ids)
        self.assertNotIn(judgment.decision.event.event_id, transition.after_history.event_ids)
        self.assertEqual(transition.intervention.event.provenance.provenance_type, "generated_reconstruction")
        self.assertGreater(transition.intervention.event.occurred_at, transition.original_observed_at)
        with self.assertRaisesRegex(ValueError, "unsupported or unbound"):
            apply_native_intervention(path=path, checkpoint=checkpoint, reference=reference,
                runtime=f.runtime, lineage=lineage, occurred_at=f.fabric._time())

    def test_actual_native_outcome_audit_unknown_tail_and_permission_withdrawal(self):
        f, path, checkpoint, reference, lineage, judgment = self.build_before("observed_outcome")
        before = verify_native_before(path=path, checkpoint=checkpoint, reference=reference,
                                      runtime=f.runtime, lineage=lineage)
        transition = apply_native_intervention(path=path, checkpoint=checkpoint, reference=reference,
            runtime=f.runtime, lineage=lineage, occurred_at=f.fabric._time())
        self.assertEqual(transition.outcome_audit.event.parent_event_ids,
                         (judgment.decision.event.event_id, transition.intervention.event.event_id))
        self.assertNotIn(transition.outcome_audit.event.event_id, transition.after_history.event_ids)
        self.assertEqual(transition.after_history.event_ids[:-1], before.original_event_ids)
        # Independent case: a real native decision does not authorize arbitrary
        # additional canonical data or a newly revoked original.
        f, path, checkpoint, reference, lineage, _ = self.build_before("irrelevant_correction")
        f.fabric._append(b"unsupported tail must stop", event_type="observation")
        with self.assertRaisesRegex(ValueError, "unsupported or unbound"):
            verify_native_before(path=path, checkpoint=checkpoint, reference=reference,
                                 runtime=f.runtime, lineage=lineage)
        f._judgment_permission(f.registry.lookup(next(iter(checkpoint.event_by_source_id.values()))), "revoke")
        with self.assertRaises((PermissionError, ValueError)):
            verify_native_before(path=path, checkpoint=checkpoint, reference=reference,
                                 runtime=f.runtime, lineage=lineage)

    def test_phase_withdrawal_at_native_cipher_read_blocks_later_private_reads(self):
        f, path, checkpoint, reference, lineage, _ = self.build_before("irrelevant_correction")
        private = f.runtime.private
        target = private._fetch(private.records,
            private._key("qualified_model_input", reference.judgment_invocation_id))["raw"]["object_id"]
        backend, triggered, late = f.objects.backend, [], []
        get = backend.get_object
        def withdrawing_get(namespace, object_id):
            if not lineage.history_authority.allowed:
                late.append(object_id)
            result = get(namespace, object_id)
            if object_id == target:
                triggered.append(object_id)
                lineage.history_authority.allowed = False
            return result
        backend.get_object = withdrawing_get
        self.addCleanup(setattr, backend, "get_object", get)
        with self.assertRaisesRegex(PermissionError, "phase permission was withdrawn"):
            verify_native_before(path=path, checkpoint=checkpoint, reference=reference,
                                 runtime=f.runtime, lineage=lineage)
        self.assertEqual(triggered, [target])
        self.assertEqual(late, [])

    def test_actual_typed_phase_snapshot_and_grant_proof_join_before_tail_only(self):
        f, path, checkpoint, reference, lineage, judgment = self.build_before("relevant_correction")
        history = lineage.history_for(checkpoint.case_id, "before")
        custody = XTDBPhaseSnapshotCustody(runtime=f.runtime, run_id="native-pilot-phase-fixture",
            run_plan_sha256=lineage.run_plan_sha256, clock=f.fabric._time)
        snapshot = custody.capture(snapshot_id="native-before-phase-fixture", case_id=checkpoint.case_id,
            phase="before", arm="flora_full", plan=reference.context_plan, lineage=lineage, history=history)
        metadata = custody.metadata(snapshot.snapshot_id)
        source = f.registry.lookup(metadata["event_id"])
        f._judgment_permission(source)
        typed = PhaseSnapshotReference(custody.run_id, snapshot.snapshot_id, metadata["snapshot_sha256"],
            metadata["event_id"], checkpoint.case_id, "before", "flora_full")
        reference = replace(reference, phase_snapshots=(typed,))
        services = NativePilotPhaseSnapshotServices(custody,
            {snapshot.snapshot_id: f.runtime.bindings}, lambda *_: reference.judgment_invocation_id)
        initial = len(f.log.replay())
        with self.assertRaisesRegex(ValueError, "explicit actual selected routes"):
            verify_native_before(path=path, checkpoint=checkpoint, reference=reference,
                runtime=f.runtime, lineage=lineage)
        verified = verify_native_before(path=path, checkpoint=checkpoint, reference=reference,
            runtime=f.runtime, lineage=lineage, phase_snapshot_services=services)
        self.assertEqual(len(f.log.replay()), initial)
        self.assertIn(typed.event_id, dict(verified.canonical_prefix))
        self.assertNotIn(typed.event_id, verified.original_event_ids)
        self.assertEqual(verified.native_decision_event_id, judgment.decision.event.event_id)
        f._judgment_permission(source, "revoke")
        with self.assertRaises((PermissionError, ValueError)):
            verify_native_before(path=path, checkpoint=checkpoint, reference=reference,
                runtime=f.runtime, lineage=lineage, phase_snapshot_services=services)


if __name__ == "__main__":
    unittest.main()
