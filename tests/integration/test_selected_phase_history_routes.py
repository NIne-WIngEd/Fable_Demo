"""Real selected phase replacement/recovery; fictional producer bytes only."""
import base64
from copy import copy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

from cognitive_kernel.canonical import canonical_json_bytes, canonical_sha256
from cognitive_kernel.projection_contracts import ProjectionVersion
from flora.comparison_run import (
    ArmBinding, ArmResult, ExecutionRequest, HistorySnapshot, MeasuredUsage,
    SourceMaterial, _context_bytes, _validate_result,
)
from flora.selected.artifact_registry import ArtifactManifest
from flora.selected.comparison_custody import XTDBComparisonCustody, SelectedRunEvidencePolicy, evaluation_purpose
from flora.selected.context import ContextPlan, StateRoute
from flora.selected.formation_context import register_experience_source
from flora.selected.formation_policy import FormationPermissionAction, formation_permission_payload
from flora.selected.judgment_lineage import NativeJudgmentLineageVerifier
from flora.selected.personal_state import activation_request
from flora.selected.native_arm import FrozenNativeArmPlan, NativeInvocationEntry, NativePhaseSnapshotBinding
from flora.selected.phase_snapshots import FrozenPhaseUpdatePolicy, XTDBPhaseSnapshotCustody, _TABLE
from flora.selected.phase_routes import SelectedPhaseLineageRouter, SelectedPhaseRoute


def fixture(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_ROOT = Path(__file__).resolve().parents[1]
_rf = fixture("flora_phase_selected_runtime_fixture", Path(__file__).parent / "test_selected_runtime_bridge.py")
_lf = fixture("flora_phase_selected_lineage_fixture", _ROOT / "test_selected_judgment_lineage.py")
_cf = fixture("flora_phase_selected_comparator_fixture", _ROOT / "comparator_fixtures.py")


class FictionalUpdateExclusionQualifier(_lf.FictionalPhaseQualifier):
    """Signed supplied policy mechanics; no real trained update is inspected."""
    def verify_phase_update_policy(self, *, request, receipt):
        wrapper = json.loads(receipt)
        payload = wrapper["payload"]
        self.public_key.verify(base64.b64decode(wrapper["signature"], validate=True), canonical_json_bytes(payload))
        if payload["schema"] != "fictional-phase-update-exclusion-v1" or payload["request_sha256"] != canonical_sha256(request):
            raise PermissionError("fictional producer receipt does not bind this exact exclusion")
        return {**payload, "schema": "flora-qualified-phase-update-exclusion-v1",
            "receipt_sha256": hashlib.sha256(receipt).hexdigest()}


class SelectedPhaseHistoryRoutesTest(unittest.TestCase):
    def setUp(self):
        self.f = _rf.SelectedExperimentRuntimeIntegrationTest()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def eval_grant(self, source, purpose):
        f = self.f
        action = FormationPermissionAction.create(scope=f.scope, authority_namespace_id=f.namespace,
            action_id="phase-eval-" + str(f.fabric.clock), source_ref_id=source.evidence.ref_id,
            source_registration_sha256=source.registration_sha256, purpose=purpose, decision="allow", generation=1,
            previous_action_sha256=None, authorization_ref="fictional-enrolled-owner", authorized_at=f.fabric._time())
        event, raw = f.fabric._append(formation_permission_payload(action), event_type="formation_permission_action",
            parents=(source.evidence.ref_id,), at=action.authorized_at, provenance="generated_reconstruction")
        f.private.register_formation_permission(action=action, request_event_id=event.event_id, raw=raw, log=f.log, objects=f.objects)
        f._persist_proof(event, "formation_permission")
        f.policy.apply(action, request_event_id=event.event_id, log=f.log, objects=f.objects,
            references=f.references, verifier=f.owner_verifier)

    def next_state(self, previous, accepted, source):
        f = self.f
        raw, at = f.objects.put(b"fictional actual approved replacement state"), f.fabric._time()
        envelope = _rf._semantic_fixture.fixture_envelope(f.scope, f.namespace, "phase-owner-v2", "projection_version",
            "registered_projection", (accepted.claim_version_id,), at=at, digest=raw.plaintext_sha256)
        version = ProjectionVersion.create(envelope=envelope, projection_id=previous.projection_id,
            version_id="phase-owner-v2", projection_type="owner_model", subject_type="owner",
            subject_id=f.scope.host_instance_id, modalities=("symbolic",), generation=2,
            source_claim_version_ids=(accepted.claim_version_id,), valid_from=at, valid_to=None, produced_at=at,
            projection_state="candidate", responsible_component="fictional-supplied-state", model_id=None,
            model_version=None, content_digest=raw.plaintext_sha256, supersedes_version_id=previous.version_id)
        f.private.record(artifact_id=version.version_id, kind="projection", contract=version.metadata_record(),
            attachments=(("content", raw),), parent_event_ids=(source.event_id,), log=f.log, objects=f.objects,
            occurred_at=f.fabric._time(), expected_revision=len(f.log.replay())-1)
        f.state.put_candidate(version, content=raw, claims=f.claims, log=f.log, objects=f.objects,
            references=f.references, expected_previous_version_id=previous.version_id)
        approval, approval_raw = f.fabric._append(activation_request(version.metadata_record(),
            expected_active_version_id=previous.version_id), event_type="state_activation_approval")
        f.private.register_approval(approval_event_id=approval.event_id, candidate=version,
            expected_active_version_id=previous.version_id, raw=approval_raw, log=f.log, objects=f.objects)
        f._persist_proof(approval, "state_activation")
        registered = register_experience_source(event_id=approval.event_id, raw=approval_raw, registry=f.registry,
            log=f.log, objects=f.objects, role="generated_reconstruction", modality="structured")
        f._judgment_permission(registered)
        f.state.activate(subject_type=version.subject_type, subject_id=version.subject_id, projection_id=version.projection_id,
            approval_event_id=approval.event_id, expected_active_version_id=previous.version_id, claims=f.claims,
            log=f.log, objects=f.objects, references=f.references, verifier=f.owner_verifier)
        return version

    def test_actual_claim_state_and_artifact_replacement_keeps_before_route_and_live_withdrawal(self):
        f = self.f
        original = f.fabric._source(b"fictional before evidence")
        correction = f.fabric._source(b"fictional corrected evidence", correction_parent=original.event_id)
        for event in (original, correction):
            f._judgment_permission(f.registry.lookup(event.event_id))
        bundle, store = f.fabric._bundle(original, prefix="phase-original")
        bound, at = f.fabric._prepare(bundle, store)
        adjudication = _rf._semantic_fixture.fixture_adjudication(bound, at=at)
        f.fabric.semantic_proof.approve_fixture(adjudication, bound)
        accepted = f.fabric._admit(bound, adjudication, store)
        f.qualifier = _lf.FictionalPhaseQualifier(f.qualification_key.public_key())
        f._artifact("memory_formation")
        f._artifact("personality_judgment")
        previous_state = f._state_activation(accepted, original)
        old_bindings = dict(f.bindings)
        plan = ContextPlan(request_id="phase-exact-plan", purpose="personal_judgment",
            exact_claim_ids=(accepted.claim_id,), minimum_claims=1,
            state_routes=(StateRoute("owner", f.scope.host_instance_id, previous_state.projection_id),))
        materials = [SourceMaterial(event, f.objects.get(f.references.get(event.payload_reference))) for event in (original, correction)]
        histories, question, run_plan = _cf.inputs(f.scope.host_instance_id, actual_sources=materials)
        comparison = XTDBComparisonCustody(scope=f.scope, authority_namespace_id=f.namespace,
            connection=f.connection, registry=f.registry, objects=f.objects, log=f.log)
        comparison.register_inputs(run_id="phase-run", plan=run_plan, histories=histories,
            questions={"case": question}, occurred_at=f.fabric._time())
        for phase in ("before", "after"):
            for event_id in histories[("case", phase)].event_ids + (comparison.metadata("phase-run", "history:case:"+phase).event_id,):
                self.eval_grant(f.registry.lookup(event_id), evaluation_purpose("phase-run", "case", phase))
        authority = SelectedRunEvidencePolicy(custody=comparison, run_id="phase-run", permissions=f.policy)
        def lineage():
            return NativeJudgmentLineageVerifier(runtime=f.runtime, run_plan_sha256=run_plan.digest(), history_authority=authority,
                history_for=lambda case, phase: histories[(case, phase)], invocation_id_for=lambda request, result: "phase-task-"+request.phase,
                phase_receipt_for=lambda request: _lf.fictional_phase_receipt(request, f.qualification_key))
        custody = XTDBPhaseSnapshotCustody(runtime=f.runtime, run_id="phase-run", run_plan_sha256=run_plan.digest(), clock=f.fabric._time)
        before = custody.capture(snapshot_id="before-snapshot", case_id="case", phase="before", arm="flora_full",
            plan=plan, lineage=lineage(), history=histories[("case", "before")])
        f._judgment_permission(f.registry.lookup(custody.metadata(before.snapshot_id)["event_id"]))
        # Exercise a real canonical append and registered encrypted payload,
        # then inject only the missing final XTDB metadata index write.
        class InterruptFinalIndex:
            def __init__(self, connection):
                self.connection = connection
            def __getattr__(self, name):
                return getattr(self.connection, name)
            def execute(self, sql, parameters):
                if sql.startswith("INSERT INTO " + _TABLE + " "):
                    raise RuntimeError("injected final phase index interruption")
                return self.connection.execute(sql, parameters)
        custody.connection = InterruptFinalIndex(f.connection)
        with self.assertRaisesRegex(RuntimeError, "index interruption"):
            custody.capture(snapshot_id="orphan-before-snapshot", case_id="case", phase="before", arm="flora_full",
                plan=plan, lineage=lineage(), history=histories[("case", "before")])
        custody.connection = f.connection
        orphan_intent = custody.intent("orphan-before-snapshot")
        orphan_event = custody._event_for_intent(orphan_intent)
        self.assertIsNone(custody.metadata("orphan-before-snapshot"))
        # Capture itself cannot manufacture this independently signed grant.
        with self.assertRaises(PermissionError):
            custody.reconcile(snapshot_id="orphan-before-snapshot", history=histories[("case", "before")],
                history_authority=authority, historical_bindings=old_bindings,
                invocation_id_for=lambda request, result: "phase-task-"+request.phase)
        f._judgment_permission(f.registry.lookup(orphan_event.event_id))
        canonical_before_repair = tuple(f.log.replay())
        repaired = custody.reconcile(snapshot_id="orphan-before-snapshot", history=histories[("case", "before")],
            history_authority=authority, historical_bindings=old_bindings,
            invocation_id_for=lambda request, result: "phase-task-"+request.phase)
        self.assertEqual(repaired.snapshot_sha256, orphan_intent["snapshot_sha256"])
        self.assertEqual(tuple(f.log.replay()), canonical_before_repair)
        self.assertEqual(custody.metadata(repaired.snapshot_id)["event_id"], orphan_event.event_id)
        corrected_bundle, corrected_store = f.fabric._bundle(correction, prefix="phase-corrected", correction_of=accepted.claim_version_id)
        corrected, at = f.fabric._prepare(corrected_bundle, corrected_store, identity=bound.interpretation.candidate.identity)
        previous = _rf._semantic_fixture.fixture_projection(f.claims.load_current(accepted.claim_id))
        decision = _rf._semantic_fixture.fixture_adjudication(corrected, at=at, conflict_id="phase-correction-conflict")
        conflict = _rf._semantic_fixture.fixture_conflict(corrected, decision, previous)
        f.fabric.semantic_proof.approve_fixture(decision, corrected)
        updated = f.fabric._admit(corrected, decision, corrected_store, expected_previous=previous, conflict=conflict)
        self.next_state(previous_state, updated, correction)
        role, payload = "personality_judgment", b"fictional distinct after checkpoint"
        checkpoint = Path(f.fabric.directory.name) / "after-personality.checkpoint"
        checkpoint.write_bytes(payload)
        manifest = ArtifactManifest(f.scope, "fictional-personality-after", role, "fictional-repo", "fictional-branch", "a"*40,
            hashlib.sha256(payload).hexdigest(), len(payload), f.codec.input_contract_id, f.codec.input_contract_sha256,
            f.codec.output_contract_id, f.codec.output_contract_sha256)
        q = {"schema":"fictional-qualification-v1", "qualifier_id":"fictional-independent-qualifier",
            "qualification_id":"fictional-qualified-personality-after", "manifest_sha256":manifest.manifest_sha256, "runtime_allowed":True}
        receipt = canonical_json_bytes({"payload":q,"signature":base64.b64encode(f.qualification_key.sign(canonical_json_bytes(q))).decode()})
        f.artifacts.admit(manifest=manifest, checkpoint_path=checkpoint, external_receipt=receipt, verifier=f.qualifier,
            expected_previous_artifact_id="fictional-personality_judgment", expected_previous_generation=1)
        f.bindings[role] = replace(f.bindings[role], checkpoint_path=checkpoint)
        f._bind_services(f.connection)
        custody = XTDBPhaseSnapshotCustody(runtime=f.runtime, run_id="phase-run", run_plan_sha256=run_plan.digest(), clock=f.fabric._time)
        after = custody.capture(snapshot_id="after-snapshot", case_id="case", phase="after", arm="flora_full",
            plan=plan, lineage=lineage(), history=histories[("case", "after")])
        f._judgment_permission(f.registry.lookup(custody.metadata(after.snapshot_id)["event_id"]))
        def route(snapshot, bindings):
            return SelectedPhaseRoute(custody=custody, snapshot_id=snapshot.snapshot_id,
                history=histories[("case", snapshot.record["phase"])], history_authority=authority,
                historical_bindings=bindings, invocation_id_for=lambda request, result: "phase-task-"+request.phase)
        old, new = route(before, old_bindings), route(after, f.bindings)
        self.assertEqual(old.runtime.claims.load_current(accepted.claim_id)["current_claim_version_id"], accepted.claim_version_id)
        self.assertEqual(new.runtime.claims.load_current(accepted.claim_id)["current_claim_version_id"], updated.claim_version_id)
        self.assertNotEqual(old.runtime._context(plan).receipt_record(), new.runtime._context(plan).receipt_record())
        self.assertNotEqual(old.runtime._resolve(role)[1].checkpoint_sha256, new.runtime._resolve(role)[1].checkpoint_sha256)
        self.assertEqual(f.claims.load_current(accepted.claim_id)["current_claim_version_id"], updated.claim_version_id)
        f._judgment_permission(f.registry.lookup(original.event_id), "revoke")
        original_get, calls = f.objects.backend.get_object, []
        def forbidden(namespace, object_id):
            calls.append(object_id)
            raise AssertionError("withdrawal must precede phase private read")
        f.objects.backend.get_object = forbidden
        try:
            with self.assertRaises((ValueError, PermissionError)):
                route(before, old_bindings)
            with self.assertRaises((ValueError, PermissionError)):
                old.runtime._context(plan)
            self.assertEqual(calls, [])
        finally:
            f.objects.backend.get_object = original_get

    def test_strict_router_recovers_distinct_actual_native_arm_invocations_on_all_phase_routes(self):
        """Four physical routes and signed supplied outputs; no learned result."""
        f = self.f
        original = f.fabric._source(b"fictional strict-router original evidence")
        correction = f.fabric._source(b"fictional strict-router correction", correction_parent=original.event_id)
        for event in (original, correction):
            f._judgment_permission(f.registry.lookup(event.event_id))
        bundle, store = f.fabric._bundle(original, prefix="strict-router-original")
        bound, at = f.fabric._prepare(bundle, store)
        adjudication = _rf._semantic_fixture.fixture_adjudication(bound, at=at)
        f.fabric.semantic_proof.approve_fixture(adjudication, bound)
        accepted = f.fabric._admit(bound, adjudication, store)
        f.qualifier = FictionalUpdateExclusionQualifier(f.qualification_key.public_key())
        f._artifact("memory_formation")
        f._artifact("personality_judgment")
        plan = ContextPlan(request_id="strict-router-exact-context", purpose="personal_judgment",
            exact_claim_ids=(accepted.claim_id,), minimum_claims=1)
        context = f.runtime._context(plan)
        context_sha256 = hashlib.sha256(_context_bytes(context)).hexdigest()
        histories, question, run_plan = _cf.inputs(f.scope.host_instance_id,
            actual_sources=[SourceMaterial(event, f.objects.get(f.references.get(event.payload_reference)))
                for event in (original, correction)])
        run_id, snapshots, frozen_arms = "strict-router-run", {}, {}
        for arm in ("flora_full", "same_evidence_ablation"):
            entries = []
            for phase in ("before", "after"):
                binding = NativePhaseSnapshotBinding(run_id, "strict-router-" + arm + "-" + phase, arm)
                snapshots[("case", phase, arm)] = binding
                entries.append(NativeInvocationEntry("case", phase, "strict-task-" + arm + "-" + phase,
                    plan, context_sha256, binding))
            frozen_arms[arm] = FrozenNativeArmPlan(f.scope, f.namespace, arm, "a" * 64, tuple(entries))
        actual_sha = f.runtime._resolve("personality_judgment")[1].checkpoint_sha256
        bindings = dict(run_plan.arm_bindings)
        for arm, frozen in frozen_arms.items():
            bindings[arm] = ArmBinding(f.bindings["personality_judgment"].adapter.adapter_id, actual_sha,
                frozen.lineage_sha256, "fictional-supplied-phase-update-policy")
        run_plan = replace(run_plan, arm_bindings=bindings)
        comparison = XTDBComparisonCustody(scope=f.scope, authority_namespace_id=f.namespace,
            connection=f.connection, registry=f.registry, objects=f.objects, log=f.log)
        comparison.register_inputs(run_id=run_id, plan=run_plan, histories=histories,
            questions={"case": question}, occurred_at=f.fabric._time())
        for phase in ("before", "after"):
            metadata = comparison.metadata(run_id, "history:case:" + phase)
            for event_id in histories[("case", phase)].event_ids + (metadata.event_id,):
                self.eval_grant(f.registry.lookup(event_id), evaluation_purpose(run_id, "case", phase))
        authority = SelectedRunEvidencePolicy(custody=comparison, run_id=run_id, permissions=f.policy)
        capture_lineage = NativeJudgmentLineageVerifier(runtime=f.runtime, run_plan_sha256=run_plan.digest(),
            history_authority=authority, history_for=lambda case, phase: histories[(case, phase)],
            invocation_id_for=lambda request, result: "capture-only-not-an-execution",
            phase_receipt_for=lambda request: _lf.fictional_phase_receipt(request, f.qualification_key))
        custody = XTDBPhaseSnapshotCustody(runtime=f.runtime, run_id=run_id,
            run_plan_sha256=run_plan.digest(), clock=f.fabric._time)
        captured = {}
        for phase in ("before", "after"):
            for arm in ("flora_full", "same_evidence_ablation"):
                kwargs = {}
                if phase == "after" and arm == "same_evidence_ablation":
                    before = captured[("before", "flora_full")]
                    policy = FrozenPhaseUpdatePolicy("withhold_personal_judgment_update", before.snapshot_id,
                        before.snapshot_sha256, (correction.event_id,))
                    actual_lineage = capture_lineage.context_lineage(case_id="case", phase=phase,
                        history=histories[("case", phase)], context=f.runtime._context(plan))
                    artifact = f.runtime._resolve("personality_judgment")[1]
                    request = {"schema": "flora-phase-update-exclusion-request-v1",
                        "scope": f.scope.metadata_record(), "authority_namespace_id": f.namespace,
                        "run_id": run_id, "run_plan_sha256": run_plan.digest(), "case_id": "case",
                        "phase": phase, "arm": arm, "history_sha256": histories[("case", phase)].digest(),
                        "context_lineage_sha256": actual_lineage.lineage_sha256, "update_policy": policy.record(),
                        "artifact_manifest_sha256": artifact.manifest_sha256}
                    payload = {"schema": "fictional-phase-update-exclusion-v1",
                        "request_sha256": canonical_sha256(request), "artifact_manifest_sha256": artifact.manifest_sha256,
                        "qualifier_id": artifact.qualifier_id, "qualification_id": artifact.qualification_id, "allowed": True}
                    receipt = canonical_json_bytes({"payload": payload,
                        "signature": base64.b64encode(f.qualification_key.sign(canonical_json_bytes(payload))).decode()})
                    kwargs = {"update_policy": policy, "update_receipt": receipt}
                snapshot = custody.capture(snapshot_id=snapshots[("case", phase, arm)].snapshot_id,
                    case_id="case", phase=phase, arm=arm, plan=plan, lineage=capture_lineage,
                    history=histories[("case", phase)], **kwargs)
                captured[(phase, arm)] = snapshot
                f._judgment_permission(f.registry.lookup(custody.metadata(snapshot.snapshot_id)["event_id"]))
        roles = {binding.snapshot_id: dict(f.bindings) for binding in snapshots.values()}
        arguments = dict(custody=custody, run_plan=run_plan, histories=histories, history_authority=authority,
            bindings_by_snapshot=roles, snapshots=snapshots, frozen_native_arms=frozen_arms)
        router = SelectedPhaseLineageRouter(**arguments)
        result_policy = SelectedRunEvidencePolicy(custody=comparison, run_id=run_id,
            permissions=f.policy, native_lineage=router)
        judgments, requests, results = {}, {}, {}
        for phase in ("before", "after"):
            for arm in ("flora_full", "same_evidence_ablation"):
                route = router.route_for(case_id="case", phase=phase, arm=arm)
                entry = frozen_arms[arm].entry("case", phase)
                judged = route.runtime.judge(plan=route.snapshot.plan, task=question, invocation_id=entry.invocation_id)
                judgments[(phase, arm)] = judged
                requests[(phase, arm)] = ExecutionRequest("case", phase, question, f.scope,
                    histories[("case", phase)].digest(), histories[("case", phase)].event_ids,
                    judged.context, run_plan.binding_for("case", phase, arm), run_plan)
                # These counters are supplied contract data, not measured model performance.
                results[(phase, arm)] = ArmResult(judged.execution.result.output, judged.delivery, judged.decision,
                    MeasuredUsage(run_plan.protocol.feature_engine_id, 1, 1, 1, 0))
                qualified = router.verify_native_result(requests[(phase, arm)], results[(phase, arm)], arm=arm)
                self.assertEqual(qualified, judged.execution.output_record)
                # Mirror the actual native adapter's explicit comparison
                # enrollment after independent recovered execution proof.
                # Runtime private invocation custody alone is not enrollment
                # in the separate comparison source registry.
                for recorded in (judged.delivery, qualified, judged.decision):
                    route.check_live()
                    comparison.register_recorded(recorded)
                route.check_live()
        for binding in f.bindings.values():
            binding.adapter.invoke = lambda *_: self.fail("passive strict-router verification invoked inference")
        before_passive = tuple(f.log.replay())
        for key, request in requests.items():
            phase, arm = key
            qualified = result_policy.verify_native_result(request, results[key], arm=arm)
            self.assertEqual(qualified, judgments[key].execution.output_record)
            _validate_result(results[key], request, result_policy, arm=arm)
        self.assertEqual(tuple(f.log.replay()), before_passive)
        self.assertNotEqual(judgments[("after", "flora_full")].decision,
            judgments[("after", "same_evidence_ablation")].decision)
        with self.assertRaises(ValueError):
            router.verify_native_result(requests[("after", "same_evidence_ablation")],
                results[("after", "flora_full")], arm="same_evidence_ablation")
        with self.assertRaises(PermissionError):
            router.verify_native_result(requests[("after", "flora_full")],
                results[("after", "flora_full")], arm="same_evidence_ablation")
        wrong = {key: dict(value) for key, value in roles.items()}
        first_id = snapshots[("case", "before", "flora_full")].snapshot_id
        wrong[first_id]["personality_judgment"] = replace(wrong[first_id]["personality_judgment"],
            checkpoint_path=wrong[first_id]["memory_formation"].checkpoint_path)
        with self.assertRaises(ValueError):
            SelectedPhaseLineageRouter(**{**arguments, "bindings_by_snapshot": wrong}).route_for(
                case_id="case", phase="before", arm="flora_full")
        f._judgment_permission(f.registry.lookup(original.event_id), "revoke")
        original_get, private_fetches = f.objects.backend.get_object, []
        def forbidden(namespace, object_id):
            private_fetches.append(object_id)
            raise AssertionError("strict-router withdrawal must precede private ciphertext read")
        f.objects.backend.get_object = forbidden
        try:
            for phase, arm in requests:
                with self.assertRaises((ValueError, PermissionError)):
                    router.verify_native_result(requests[(phase, arm)], results[(phase, arm)], arm=arm)
            self.assertEqual(private_fetches, [])
        finally:
            f.objects.backend.get_object = original_get


if __name__ == "__main__":
    unittest.main()
