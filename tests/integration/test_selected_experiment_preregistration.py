"""Actual two-stage selected chronology; all producer bytes are fictional.

This verifies custody/routing mechanics, not learning, quality, or readiness
for the FloRA experiment. Nothing in this fixture trains either missing model.
"""
import base64
import asyncio
from copy import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import time
import unittest
import psycopg

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cognitive_kernel.canonical import canonical_json_bytes, canonical_sha256
from cognitive_kernel.contracts import ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from flora.comparator import encoded, sha
from flora.comparison_run import ArmResult, ExecutionRequest, MeasuredUsage, SourceMaterial, _validate_result
from flora.selected.artifact_registry import ArtifactManifest
from flora.selected.comparison_custody import XTDBComparisonCustody, SelectedRunEvidencePolicy, evaluation_purpose
from flora.selected.context import ContextPlan, StateRoute
from flora.selected.experiment_runtime import FloRAExperimentRuntime
from flora.selected.experiment_manifests import (
    CohortEntry, SelectedSourceAuthority, SplitIsolationRule, XTDBExperimentManifestCustody,
    cohort_source_purpose, manifest_purpose,
)
from flora.selected.experiment_preregistration import (
    CaptureSlotDeclaration, ExperimentPreregistration, NativeArmDeclaration,
    XTDBExperimentPreregistrationCustody, preregistration_purpose,
)
from flora.selected.formation_context import register_experience_source
from flora.selected.native_worker import NativeWorkerManifest
from flora.selected.native_reads import (
    InitializedNativeSessionFactory, NativeReadManifest, NativeReadSession, SelectedNativeReadServices,
)
from flora.selected.judgment_context import RegisteredJudgmentContextPolicy
from flora.selected.judgment_lineage import NativeJudgmentLineageVerifier
from flora.selected.personal_artifact_custody import DurablePersonalReferences
from flora.selected.phase_routes import SelectedPhaseLineageRouter, derive_preregistered_ablation_runtime
from flora.selected.phase_snapshots import (
    FrozenPhaseUpdatePolicy, PreregisteredPhaseCaptureLineageVerifier, XTDBPhaseSnapshotCustody,
)

import test_selected_phase_history_routes as support


def public(key):
    return key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


class FictionalPreregisteredQualifier(support._lf.FictionalPhaseQualifier):
    """Independent signed fixture allow-list; it inspects no learned update."""
    update_allowed = True
    def _signed(self, request, receipt, schema):
        wrapper = json.loads(receipt)
        payload = wrapper["payload"]
        self.public_key.verify(base64.b64decode(wrapper["signature"], validate=True), canonical_json_bytes(payload))
        if payload["schema"] != schema or payload["request_sha256"] != canonical_sha256(request):
            raise PermissionError("fictional signed qualification changed the exact anchored request")
        return payload

    def verify_preregistered_update(self, *, request, receipt):
        if not self.update_allowed:
            raise PermissionError("fictional independent update qualification withdrawn")
        payload = self._signed(request, receipt, "fictional-preregistered-update-v1")
        return {**payload, "schema": "flora-qualified-preregistered-update-v1", "receipt_sha256": sha(receipt)}

    def verify_phase_update_policy(self, *, request, receipt):
        payload = self._signed(request, receipt, "fictional-anchored-update-exclusion-v1")
        return {**payload, "schema": "flora-qualified-phase-update-exclusion-v2", "receipt_sha256": sha(receipt)}


class SelectedPreregisteredPhaseRoutesTest(unittest.TestCase):
    def setUp(self):
        self.base = support.SelectedPhaseHistoryRoutesTest()
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.f = self.base.f

    def grant(self, event_id, purpose):
        source = self.f.registry.lookup(event_id)
        for parent_id in source.evidence.parent_refs:
            self.grant(parent_id, purpose)
        if not self.f.policy.permits(source, purpose):
            self.base.eval_grant(source, purpose)

    def control_grants(self, store):
        """Explicit enrolled owner actions after each actual control append."""
        for kind in ("anchor", "before_seal", "update_gate", "update", "final_seal"):
            record = store._metadata(kind)
            if record is not None:
                for operation in ("capture", "read"):
                    self.grant(record.event_id, preregistration_purpose(store.run_id, operation))
        for slot in store.spec.slots:
            record = store._metadata("slot", slot.snapshot_id)
            if record is not None:
                for operation in ("capture", "read"):
                    self.grant(record.event_id, preregistration_purpose(store.run_id, operation))

    def signed(self, payload):
        return canonical_json_bytes({"payload": payload, "signature": base64.b64encode(
            self.f.qualification_key.sign(canonical_json_bytes(payload))).decode()})

    def replace_personality(self):
        f, role = self.f, "personality_judgment"
        payload = b"fictional new checkpoint produced only after the canonical update gate"
        checkpoint = Path(f.fabric.directory.name) / "preregistered-after-personality.checkpoint"
        checkpoint.write_bytes(payload)
        manifest = ArtifactManifest(f.scope, "fictional-preregistered-after-personality", role,
            "fictional-repo", "fictional-branch", "a" * 40, sha(payload), len(payload),
            f.codec.input_contract_id, f.codec.input_contract_sha256, f.codec.output_contract_id, f.codec.output_contract_sha256)
        receipt = self.signed({"schema": "fictional-qualification-v1", "qualifier_id": "fictional-independent-qualifier",
            "qualification_id": "fictional-preregistered-after-qualified", "manifest_sha256": manifest.manifest_sha256,
            "runtime_allowed": True})
        f.artifacts.admit(manifest=manifest, checkpoint_path=checkpoint, external_receipt=receipt,
            verifier=f.qualifier, expected_previous_artifact_id="fictional-personality_judgment", expected_previous_generation=1)
        f.bindings[role] = replace(f.bindings[role], checkpoint_path=checkpoint)
        # Retain every actual source/state/custody controller. Only the actual
        # producer port changes; no live Claim or artifact head is rewound.
        f.runtime.bindings[role] = f.bindings[role]

    def test_anchor_before_seal_actual_head_update_after_capture_final_seal_and_four_routes(self):
        started = time.monotonic()
        def completed(label):
            print(f"[history-preregistration] {label}: elapsed={time.monotonic() - started:.3f}s", flush=True)
        phase_labels = {
            ("before", "flora_full"): "before-full",
            ("before", "same_evidence_ablation"): "before-ablation",
            ("after", "flora_full"): "after-full",
            ("after", "same_evidence_ablation"): "after-ablation",
        }
        f, run_id, exp = self.f, "preregistered-phase-run", "preregistered-phase-exp"
        original = f.fabric._source(b"fictional two-stage before evidence")
        correction = f.fabric._source(b"fictional two-stage corrected evidence", correction_parent=original.event_id)
        training = f.fabric._source(b"independent fictional recipe input, excluded from heldout history")
        for event in (original, correction):
            f._judgment_permission(f.registry.lookup(event.event_id))
        bundle, candidates = f.fabric._bundle(original, prefix="preregistered-original")
        bound, at = f.fabric._prepare(bundle, candidates)
        adjudication = support._rf._semantic_fixture.fixture_adjudication(bound, at=at)
        f.fabric.semantic_proof.approve_fixture(adjudication, bound)
        accepted = f.fabric._admit(bound, adjudication, candidates)
        f.qualifier = FictionalPreregisteredQualifier(f.qualification_key.public_key())
        f._artifact("memory_formation")
        f._artifact("personality_judgment")
        old_bindings = dict(f.bindings)
        old_state = f._state_activation(accepted, original)
        completed("source-and-baseline-setup-complete")
        context_plan = ContextPlan("preregistered-exact-selection", "personal_judgment",
            exact_claim_ids=(accepted.claim_id,), minimum_claims=1,
            state_routes=(StateRoute("owner", f.scope.host_instance_id, old_state.projection_id),))
        histories, question, design_plan = support._cf.inputs(f.scope.host_instance_id,
            actual_sources=[SourceMaterial(event, f.objects.get(f.references.get(event.payload_reference)))
                for event in (original, correction)])
        question_event = f.fabric._source(question)
        originals = (training, original, correction, question_event)
        local = SelectedSourceAuthority(f.registry, f.log, f.policy, f.objects)
        for event in originals:
            for operation in ("capture", "read"):
                self.grant(event.event_id, manifest_purpose(exp, operation))
            self.grant(event.event_id, cohort_source_purpose(exp, "training" if event == training else "heldout"))
        for phase in ("before", "after"):
            for event_id in histories[("case", phase)].event_ids + (question_event.event_id,):
                self.grant(event_id, evaluation_purpose(run_id, "case", phase))
        lineage_key, result_key = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
        manifests = XTDBExperimentManifestCustody(experiment_id=exp, local=local, authorities=(local,),
            connection=f.connection, control_anchor_event_id=training.event_id,
            lineage_public_key=public(lineage_key), approved_lineage_key_sha256=sha(public(lineage_key)),
            qualification_public_key=public(result_key), approved_qualification_key_sha256=sha(public(result_key)),
            part1_validator=None, clock=f.fabric._time)
        entries = tuple(CohortEntry("entry-" + str(index), local.authority_id, event.event_id,
            "training" if event == training else "heldout", "recipe-family" if event == training else "heldout-family",
            "fixture-generator", "a" * 64, "recipe-scenario" if event == training else "heldout-scenario", (),
            "recipe-person" if event == training else "heldout-person", "host",
            "question" if event == question_event else "authorized_history") for index, event in enumerate(originals))
        rules = (SplitIsolationRule("heldout", "training", tuple(sorted({"source_family", "scenario_ancestry",
            "person_family", "source_ancestry"})), ("generator_family",)),)
        cohort_body = {"entries": [entry.record() for entry in entries], "rules": [rule.record() for rule in rules],
            "bindings": {entry.entry_id: local.binding(entry.event_id) for entry in entries}}
        claim = {"schema": "flora-cohort-lineage-attestation-v1", "experiment_id": exp,
            "enrolled_key_sha256": sha(public(lineage_key)), "actual_family_ancestry_verified": True,
            "cohort_sha256": canonical_sha256(cohort_body)}
        cohort = manifests.register_cohort(cohort_id="cohort", entries=entries, rules=rules,
            lineage_claim=claim, lineage_proof=lineage_key.sign(encoded(claim)))
        completed("cohort-registered")
        self.grant(cohort["event_id"], manifest_purpose(exp, "read"))
        recipe = manifests.register_recipe(recipe_id="recipe", cohort_id="cohort",
            code_files=(("tests/integration/test_selected_experiment_preregistration.py", Path(__file__).read_bytes()),),
            dependency_lock=b"fictional fixture lock: no model training", role_contracts=(("personality", b"supplied producer port"),),
            source_choices=(("entry-0", "eligible"),), stop_defer_contract=b"supplied fixture stop/defer contract")
        completed("recipe-registered")
        self.grant(recipe["event_id"], manifest_purpose(exp, "read"))
        comparison = XTDBComparisonCustody(scope=f.scope, authority_namespace_id=f.namespace,
            connection=f.connection, registry=f.registry, objects=f.objects, log=f.log)
        store = XTDBExperimentPreregistrationCustody(comparison=comparison, manifests=manifests,
            cohort_id="cohort", recipe_id="recipe", permissions=f.policy, clock=f.fabric._time)
        design, selection = b"supplied fictional baseline design", b"supplied exact two-stage selection contract"
        protocol = replace(design_plan.protocol, baseline_design_sha256=sha(design), builder_recipe_sha256=recipe["content_sha256"])
        worker = NativeWorkerManifest(f.scope, f.namespace, "fictional-worker",
            *("a" * 64 for _ in range(8)), 4096, 4096, 1024, 1000, 100, 8192)
        baseline_roles = {role: f.runtime._resolve(role)[1] for role in old_bindings}
        arms = ("flora_full", "same_evidence_ablation")
        slots = tuple(CaptureSlotDeclaration("case", phase, arm, "v2-" + phase + "-" + arm,
            "capture-" + phase + "-" + arm, "evaluation-" + phase + "-" + arm, sha(selection),
            "withhold_personal_judgment_update" if phase == "after" and arm == "same_evidence_ablation" else "full_update")
            for phase in ("before", "after") for arm in arms)
        spec = ExperimentPreregistration(f.scope, f.namespace, run_id, protocol, {"case": sha(question)},
            20000, 20000, 1, "contract_fixture", support._cf.configuration(), design,
            {arm: NativeArmDeclaration(arm, worker, f.bindings["personality_judgment"].adapter.adapter_id,
                "fixture-supplied-update") for arm in arms}, baseline_roles,
            {role: b"supplied role qualification contract" for role in old_bindings}, selection,
            b"supplied exact update contract", b"supplied before role nomination", slots,
            {("case", phase): "provider-" + phase for phase in ("before", "after")},
            {"case": "before-separate-probe"}, {"case": ("actual-fixture-update",)})
        for record in (cohort, recipe):
            for operation in ("capture", "read"):
                self.grant(record["event_id"], preregistration_purpose(run_id, operation))
        anchor = store.register(spec=spec, histories=histories, questions={"case": question})
        completed("anchor-registered")
        self.control_grants(store)
        self.assertIsNone(store._metadata("final_seal"))
        self.assertNotIn("phase_bindings", store.recover_control(kind="anchor"))
        self.assertNotIn("run_plan_sha256", store.recover_control(kind="anchor"))
        store.register_original_inputs(occurred_at=f.fabric._time())
        completed("original-inputs-registered")
        for phase in ("before", "after"):
            self.grant(comparison.metadata(run_id, "history:case:" + phase).event_id,
                evaluation_purpose(run_id, "case", phase))
        archive = XTDBPhaseSnapshotCustody(runtime=f.runtime, run_id=run_id, preregistration=anchor,
            clock=f.fabric._time)
        store.bind_phase_custody(archive)
        authority = anchor.history_authority()
        def lineage(slot, runtime=None):
            return PreregisteredPhaseCaptureLineageVerifier(runtime=runtime or f.runtime, preregistration=anchor,
                snapshot_id=slot.snapshot_id, case_id=slot.case_id, phase=slot.phase, arm=slot.arm,
                history_for=anchor.history_for,
                phase_receipt_for=lambda request: support._lf.fictional_phase_receipt(request, f.qualification_key))
        captured, bindings = {}, {}
        def capture(slot, *, ports, **kwargs):
            store.bind_historical_bindings(snapshot_id=slot.snapshot_id, bindings=ports)
            bindings[slot.snapshot_id] = ports
            snapshot = archive.capture(snapshot_id=slot.snapshot_id, case_id=slot.case_id,
                phase=slot.phase, arm=slot.arm, plan=context_plan, lineage=lineage(slot),
                history=histories[(slot.case_id, slot.phase)], **kwargs)
            captured[(slot.phase, slot.arm)] = snapshot
            event_id = archive.metadata(slot.snapshot_id)["event_id"]
            f._judgment_permission(f.registry.lookup(event_id))
            for operation in ("capture", "read"):
                self.grant(event_id, preregistration_purpose(run_id, operation))
            store.publish_capture(snapshot_id=slot.snapshot_id)
            self.control_grants(store)
            completed(phase_labels[(slot.phase, slot.arm)] + "-capture-published")
            return snapshot
        after_slot = next(slot for slot in slots if slot.phase == "after")
        with self.assertRaisesRegex(PermissionError, "before seal"):
            archive.capture(snapshot_id=after_slot.snapshot_id, case_id="case", phase="after", arm=after_slot.arm,
                plan=context_plan, lineage=lineage(after_slot), history=histories[("case", "after")])
        for slot in slots:
            if slot.phase == "before":
                snapshot = capture(slot, ports=old_bindings)
                self.assertIsNone(archive.run_plan_sha256)
                self.assertEqual(snapshot.record["preregistration_sha256"], anchor.preregistration_sha256)
                self.assertNotIn("run_plan_sha256", snapshot.record)
                route = archive.capture_route(snapshot_id=slot.snapshot_id, history_authority=authority,
                    historical_bindings=old_bindings)
                with self.assertRaisesRegex(PermissionError, "capture-only"):
                    route.runtime.judge(plan=context_plan, task=question, invocation_id=slot.evaluation_invocation_id)
        before_seal = store.seal_before()
        completed("before-seal-committed")
        self.control_grants(store)
        probe = archive.before_probe_route(snapshot_id=captured[("before", "flora_full")].snapshot_id,
            case_id="case", historical_bindings=old_bindings)
        probe_adapter = old_bindings["personality_judgment"].adapter
        probe_count = len(probe_adapter.invocations)
        for task, invocation_id in ((b"changed task", "before-separate-probe"),
                                    (question, "evaluation-before-flora_full")):
            with self.assertRaises(PermissionError):
                probe.runtime.judge(plan=context_plan, task=task, invocation_id=invocation_id)
        self.assertEqual(len(probe_adapter.invocations), probe_count)
        probe_run = probe.runtime.judge(plan=context_plan, task=question, invocation_id="before-separate-probe")
        self.assertEqual(probe_run.execution.invocation.invocation_id, "before-separate-probe")
        completed("before-probe-complete")
        gate = store.begin_update()
        completed("update-gate-committed")
        self.control_grants(store)
        with self.assertRaises(PermissionError):
            probe.runtime.judge(plan=context_plan, task=question, invocation_id="before-separate-probe")
        original_before_bytes = encoded(captured[("before", "flora_full")].record)
        # Genuine actual selected Claim, approved state and artifact heads move
        # only now, after the real before seal and canonical update gate.
        changed_bundle, changed_candidates = f.fabric._bundle(correction, prefix="preregistered-corrected",
            correction_of=accepted.claim_version_id)
        changed, at = f.fabric._prepare(changed_bundle, changed_candidates, identity=bound.interpretation.candidate.identity)
        previous = support._rf._semantic_fixture.fixture_projection(f.claims.load_current(accepted.claim_id))
        decision = support._rf._semantic_fixture.fixture_adjudication(changed, at=at, conflict_id="preregistered-correction-conflict")
        conflict = support._rf._semantic_fixture.fixture_conflict(changed, decision, previous)
        f.fabric.semantic_proof.approve_fixture(decision, changed)
        updated = f.fabric._admit(changed, decision, changed_candidates, expected_previous=previous, conflict=conflict)
        new_state = self.base.next_state(old_state, updated, correction)
        self.replace_personality()
        completed("selected-head-replacement-complete")
        raw = f.objects.put(b"fictional receipt identifies these real moved heads; no learned model claim")
        update_event = ExperienceEvent.create(event_type="observation", scope=f.scope, occurred_at=f.fabric._time(),
            content_digest=raw.plaintext_sha256, provenance=ProvenanceReference.create(provenance_type="derived_inference",
                source_reference_ids=(gate.event_id,), derivation_activity_id="actual-fixture-update",
                responsible_component="fictional-producer"), retention_class="ordinary_experience", storage_tier="raw_buffer",
            parent_event_ids=(gate.event_id,), payload_reference=raw.object_id)
        f.log.append(update_event, expected_revision=len(f.log.replay()) - 1)
        register_experience_source(event_id=update_event.event_id, raw=raw, registry=f.registry, log=f.log,
            objects=f.objects, role="derived_inference", modality="structured")
        for operation in ("capture", "read"):
            self.grant(update_event.event_id, preregistration_purpose(run_id, operation))
        position = next(item.stream_position for item in f.log.replay_committed() if item.event == update_event)
        update_request = {"schema": "flora-preregistered-update-request-v1", "scope": f.scope.metadata_record(),
            "authority_namespace_id": f.namespace, "run_id": run_id, "preregistration_sha256": anchor.preregistration_sha256,
            "before_seal_event_id": before_seal.event_id, "before_seal_record_sha256": before_seal.record["record_sha256"],
            "update_gate_event_id": gate.event_id, "update_gate_event_sha256": gate.record["event_sha256"],
            "update_contract_sha256": sha(spec.update_contract), "actual_update_events": [{"event_id": update_event.event_id,
                "event_sha256": update_event.event_sha256, "stream_position": position, "event_type": update_event.event_type}]}
        receipts = {role: self.signed({"schema": "fictional-preregistered-update-v1", "role": role,
            "request_sha256": canonical_sha256({**update_request, "role": role,
                "role_policy_contract_sha256": sha(spec.role_policy_contracts[role])}),
            "qualifier_id": spec.baseline_roles[role].qualifier_id, "allowed": True,
            "authorized_before_execution": True}) for role in old_bindings}
        store.record_update(update_event_ids=(update_event.event_id,), receipts=receipts)
        completed("qualified-update-recorded")
        self.control_grants(store)
        for slot in slots:
            if slot.phase != "after":
                continue
            ports, kwargs = dict(f.bindings), {}
            if slot.arm == "same_evidence_ablation":
                before = captured[("before", "flora_full")]
                policy = FrozenPhaseUpdatePolicy("withhold_personal_judgment_update", before.snapshot_id,
                    before.snapshot_sha256, (correction.event_id,))
                def current():
                    anchor.authorize_slot_capture(snapshot_id=slot.snapshot_id, case_id="case", phase="after",
                        arm=slot.arm, history=histories[("case", "after")], plan=context_plan)
                    archive.authorize(snapshot_id=before.snapshot_id, history=histories[("case", "before")],
                        history_authority=authority)
                    archive._sources_now(histories[("case", "after")].event_ids, claim_ids=(accepted.claim_id,))
                derived = derive_preregistered_ablation_runtime(custody=archive, before_snapshot=before,
                    personality_binding=old_bindings["personality_judgment"], authority_guard=current)
                actual = lineage(slot, derived).context_lineage(case_id="case", phase="after",
                    history=histories[("case", "after")], context=derived._context(context_plan, authority_guard=current),
                    authority_guard=current)
                artifact = derived._resolve("personality_judgment", authority_guard=current)[1]
                request = {"schema": "flora-phase-update-exclusion-request-v2", "scope": f.scope.metadata_record(),
                    "authority_namespace_id": f.namespace, "run_id": run_id, "preregistration_sha256": anchor.preregistration_sha256,
                    "case_id": "case", "phase": "after", "arm": slot.arm,
                    "history_sha256": histories[("case", "after")].digest(), "context_lineage_sha256": actual.lineage_sha256,
                    "update_policy": policy.record(), "artifact_manifest_sha256": artifact.manifest_sha256}
                receipt = self.signed({"schema": "fictional-anchored-update-exclusion-v1",
                    "request_sha256": canonical_sha256(request), "artifact_manifest_sha256": artifact.manifest_sha256,
                    "qualifier_id": artifact.qualifier_id, "qualification_id": artifact.qualification_id, "allowed": True})
                ports["personality_judgment"] = old_bindings["personality_judgment"]
                kwargs = {"update_policy": policy, "update_receipt": receipt,
                    "ablation_personality_binding": old_bindings["personality_judgment"]}
            capture(slot, ports=ports, **kwargs)
        self.assertEqual(encoded(archive.recover(snapshot_id=captured[("before", "flora_full")].snapshot_id,
            history=histories[("case", "before")], history_authority=authority).record), original_before_bytes)
        final = store.finalize()
        completed("final-seal-committed")
        self.control_grants(store)
        store.register_final_inputs(final_authority=final, occurred_at=f.fabric._time())
        completed("final-inputs-registered")
        self.assertEqual(final.plan.preregistration_sha256, anchor.preregistration_sha256)
        snapshots = {(slot.case_id, slot.phase, slot.arm): final.native_plans[slot.arm].entry(slot.case_id, slot.phase).phase_snapshot
            for slot in slots}
        history_authority = SelectedRunEvidencePolicy(custody=comparison, run_id=run_id, permissions=f.policy,
            final_authority=final)
        router = SelectedPhaseLineageRouter(custody=archive, run_plan=final.plan, histories=histories,
            history_authority=history_authority, bindings_by_snapshot=bindings, snapshots=snapshots,
            frozen_native_arms=final.native_plans, final_authority=final)
        native_policy = SelectedRunEvidencePolicy(custody=comparison, run_id=run_id, permissions=f.policy,
            native_lineage=router, final_authority=final)
        retained = router.route_for(case_id="case", phase="after", arm="flora_full")
        final_adapter = f.bindings["personality_judgment"].adapter
        count = len(final_adapter.invocations)
        f.qualifier.update_allowed = False
        try:
            with self.assertRaisesRegex(PermissionError, "independent update qualification"):
                retained.runtime.judge(plan=context_plan, task=question,
                    invocation_id="evaluation-after-flora_full")
        finally:
            f.qualifier.update_allowed = True
        self.assertEqual(len(final_adapter.invocations), count)
        requests, results = {}, {}
        for slot in slots:
            route = router.route_for(case_id="case", phase=slot.phase, arm=slot.arm)
            expected = accepted.claim_version_id if slot.phase == "before" else updated.claim_version_id
            self.assertEqual(route.runtime.claims.load_current(accepted.claim_id)["current_claim_version_id"], expected)
            actual_checkpoint = route.runtime._resolve("personality_judgment")[1].checkpoint_sha256
            self.assertEqual(actual_checkpoint, baseline_roles["personality_judgment"].checkpoint_sha256
                if slot.phase == "before" or slot.arm == "same_evidence_ablation"
                else f.runtime._resolve("personality_judgment")[1].checkpoint_sha256)
            judged = route.runtime.judge(plan=context_plan, task=question, invocation_id=slot.evaluation_invocation_id)
            request = ExecutionRequest("case", slot.phase, question, f.scope, histories[("case", slot.phase)].digest(),
                histories[("case", slot.phase)].event_ids, judged.context, final.plan.binding_for("case", slot.phase, slot.arm), final.plan)
            result = ArmResult(judged.execution.result.output, judged.delivery, judged.decision,
                MeasuredUsage(final.plan.protocol.feature_engine_id, 1, 1, 1, 0))
            qualified = router.verify_native_result(request, result, arm=slot.arm)
            for record in (judged.delivery, qualified, judged.decision):
                route.check_live()
                comparison.register_recorded(record)
            requests[(slot.phase, slot.arm)], results[(slot.phase, slot.arm)] = request, result
            completed(phase_labels[(slot.phase, slot.arm)] + "-result-qualified")
        for binding in f.bindings.values():
            binding.adapter.invoke = lambda *_: self.fail("passive final recovery invoked a model")
        canonical_before_recovery = tuple(f.log.replay())
        for key, request in requests.items():
            _validate_result(results[key], request, native_policy, arm=key[1])
        self.assertEqual(tuple(f.log.replay()), canonical_before_recovery)
        completed("passive-result-recovery-complete")
        # Exercise production fresh owned SELECT-only readers on actual v2
        # archives/final seals. Initialized codecs/producers are still supplied
        # fictional ports; no inference or index repair can run in the reader.
        opened = []
        def opener(*, read_timeout_ms):
            self.assertEqual(read_timeout_ms, 5000)
            connection = psycopg.connect(f.connection.info.dsn, autocommit=True, connect_timeout=5)
            opened.append(connection)
            return connection
        def binder(connection):
            registry, policy, claims, candidates = map(copy, (f.registry, f.policy, f.claims, f.candidates))
            for service in (registry, policy, claims, candidates):
                service.connection = connection
            policy.registry = registry
            state, artifacts, personal = map(copy, (f.state, f.artifacts, f.private))
            for service in (state, artifacts, personal):
                service.connection = connection
            state.registry, state.policy = registry, policy
            references = DurablePersonalReferences(custody=personal, originals=registry)
            owner = copy(f.owner_verifier)
            owner.proofs = copy(owner.proofs)
            owner.proofs.custody = personal
            admission = copy(f.admission)
            admission.authority, admission.candidates = claims, candidates
            runtime = FloRAExperimentRuntime(artifacts=artifacts, bindings=f.bindings, claims=claims,
                sources=registry, source_policy=policy, candidates=candidates, admission=admission,
                state=state, log=f.log, objects=f.objects, references=references,
                context_policy=RegisteredJudgmentContextPolicy(claims=claims, state=state, log=f.log,
                    registry=registry, permissions=policy), state_approval_verifier=owner, clock=f.fabric._time)
            runtime.private.register = lambda *_: self.fail("passive final reader tried to register private custody")
            metadata_final = final.bind_read_connection(connection)
            owned_archive = XTDBPhaseSnapshotCustody(runtime=runtime, run_id=run_id,
                preregistration=metadata_final.store.anchor, clock=f.fabric._time)
            owned_final = final.bind_read_connection(connection, phase_custody=owned_archive,
                historical_bindings_by_snapshot=bindings)
            owned_final.store.comparison._physical_custody = comparison
            owned_archive = owned_final.store.phase_custody
            evidence = SelectedRunEvidencePolicy(custody=owned_final.store.comparison, run_id=run_id,
                permissions=policy, final_authority=owned_final)
            representative = NativeJudgmentLineageVerifier(runtime=runtime, run_plan_sha256=final.plan.digest(),
                history_authority=evidence, history_for=owned_final.store.anchor.history_for,
                invocation_id_for=lambda request, result: "not-a-phase-authority",
                phase_receipt_for=lambda request: (_ for _ in ()).throw(PermissionError("phase proof must come from exact archive")))
            def resolve(*, entry, request, artifact_permissions):
                archive_view = copy(owned_archive)
                archive_view.artifact_permissions = artifact_permissions
                # Archive source permission remains separate from the installed
                # model-context original-only predicates on runtime.source_policy.
                archive_view.artifact_source_policy = copy(owned_archive.artifact_source_policy)
                archive_view.artifact_source_policy.permissions = artifact_permissions
                archive_view.artifact_source_policy.state = copy(owned_archive.artifact_source_policy.state)
                archive_view.artifact_source_policy.state.policy = artifact_permissions
                return support.SelectedPhaseRoute(custody=archive_view, snapshot_id=entry.phase_snapshot.snapshot_id,
                    history=histories[(entry.case_id, entry.phase)], history_authority=representative.history_authority,
                    historical_bindings=bindings[entry.phase_snapshot.snapshot_id], final_authority=owned_final,
                    invocation_id_for=lambda *_: entry.invocation_id)
            return NativeReadSession(runtime, representative, (connection,), resolve)
        factory = InitializedNativeSessionFactory(artifact_sha256="2" * 64, configuration_sha256="3" * 64,
            connection_opener=opener, bind_initialized=binder, backend_read_timeout_ms=5000)
        manifest = NativeReadManifest(f.scope, f.namespace, "2" * 64, "3" * 64, 1, 60000, 5000,
            allow_current_fixture_route=False)
        async def owned_reads():
            reads = SelectedNativeReadServices(manifest=manifest, factory=factory)
            try:
                for slot in slots:
                    entry = final.native_plans[slot.arm].entry(slot.case_id, slot.phase)
                    prepared = await reads.prepare_context(entry)
                    self.assertEqual(prepared, requests[(slot.phase, slot.arm)].context)
                    self.assertTrue(await reads.authorize_evaluation(entry=entry,
                        request=requests[(slot.phase, slot.arm)]))
            finally:
                await reads.aclose()
        asyncio.run(owned_reads())
        self.assertEqual(len(opened), 8)
        self.assertTrue(all(connection.closed for connection in opened))
        self.assertEqual(tuple(f.log.replay()), canonical_before_recovery)
        completed("owned-passive-readers-complete")
        self.assertEqual(f.claims.load_current(accepted.claim_id)["current_claim_version_id"], updated.claim_version_id)
        from flora.selected.personal_state import _ACTIVE
        self.assertEqual(f.state._fetch(_ACTIVE, f.state._head_id("owner", f.scope.host_instance_id,
            old_state.projection_id))["version_id"], new_state.version_id)
        f._judgment_permission(f.registry.lookup(original.event_id), "revoke")
        original_get, calls = f.objects.backend.get_object, []
        def forbidden(namespace, object_id):
            calls.append(object_id)
            raise AssertionError("withdrawn original reached private ciphertext")
        f.objects.backend.get_object = forbidden
        try:
            for slot in slots:
                with self.assertRaises((ValueError, PermissionError)):
                    router.route_for(case_id="case", phase=slot.phase, arm=slot.arm)
            self.assertEqual(calls, [])
            completed("withdrawal-denial-complete")
        finally:
            f.objects.backend.get_object = original_get


if __name__ == "__main__":
    unittest.main()
