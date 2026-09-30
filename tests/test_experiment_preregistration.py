"""Fictional row/log contracts with actual encrypted two-stage controls.

These checks do not train, qualify or claim the success of a personal model.
Actual phase producer qualification is tested separately by phase custody.
"""
from dataclasses import replace
import inspect
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from flora.comparator import BaselineConfiguration, MemoryConfiguration, ProviderConfiguration, sha
from cognitive_kernel.canonical import canonical_sha256
from cognitive_kernel.contracts import ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from flora.selected.artifact_registry import RuntimeWiringManifest
from flora.selected.comparison_custody import SelectedRunEvidencePolicy, evaluation_purpose
from flora.selected.experiment_coordinator import RegisteredExperimentCoordinator, coordinator_purpose
from flora.selected.experiment_preregistration import (
    CaptureSlotDeclaration, ExperimentPreregistration, NativeArmDeclaration,
    RegisteredExperimentFinalBinding, XTDBExperimentPreregistrationCustody, preregistration_purpose,
)
from flora.selected.native_worker import NativeWorkerManifest
from flora.selected.experiment_runtime import RuntimeRoleBinding
from flora.selected.phase_snapshots import XTDBPhaseSnapshotCustody
from flora.selected.phase_routes import ObservedPhaseBinding
from flora.selected.context import ContextPlan
from flora.selected.native_reads import ReadOnlyNativeSQLConnection
import test_experiment_coordinator as support


class PreregistrationContractsTest(unittest.TestCase):
    def setUp(self):
        self.f = support.CoordinatorContractTest("test_exact_frozen_binding_and_dedicated_recovery_without_qualification")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.local, self.scope = self.f.local, self.f.scope
        self.run_id = "two-stage-run"
        self.store = XTDBExperimentPreregistrationCustody(comparison=self.f.comparison, manifests=self.f.f.store,
            cohort_id="cohort", recipe_id="recipe", permissions=self.local.permissions, clock=self.f.clock)
        self.design = b"supplied fictional comparator design"
        protocol = replace(self.f.plan.protocol, baseline_design_sha256=sha(self.design))
        provider = ProviderConfiguration("fictional-provider", "feature", "fixture-model", ("fixture-model",),
            "https://example.invalid/test", b"{}", "2" * 64, "3" * 64)
        memory = MemoryConfiguration("4" * 64, "5" * 64, "6" * 64, "7" * 64, 2, 64, 8, 4, 10, 16, 1)
        comparator = BaselineConfiguration(provider, memory, b"supplied system instruction")
        worker = NativeWorkerManifest(self.scope, self.local.registry.authority_namespace_id, "fictional-worker",
            *("a" * 64 for _ in range(8)), 4096, 4096, 1024, 1000, 100, 8192)
        roles = {role: RuntimeWiringManifest(self.scope, role, "fixture-" + role, "b" * 64, 1,
            "c" * 64, "input-" + role, "d" * 64, "output-" + role, "e" * 64,
            "qualification-" + role, "qualifier-" + role) for role in ("memory_formation", "personality_judgment")}
        selection = b"supplied exact selection contract"
        arms = ("flora_full", "same_evidence_ablation")
        self.spec = ExperimentPreregistration(self.scope, self.local.registry.authority_namespace_id, self.run_id,
            protocol, {"case": sha(self.f.question)}, 32, 4096, 2, "contract_fixture", comparator, self.design,
            {arm: NativeArmDeclaration(arm, worker, "fixture-producer", "supplied-update") for arm in arms},
            roles, {role: b"supplied role qualification policy" for role in roles}, selection,
            b"supplied observed producer update policy", b"supplied actual baseline nomination policy",
            tuple(CaptureSlotDeclaration("case", phase, arm, "capture-" + phase + "-" + arm,
                "capture-invocation-" + phase + "-" + arm, "evaluation-" + phase + "-" + arm,
                sha(selection), "withhold_personal_judgment_update" if phase == "after" and arm == "same_evidence_ablation" else "full_update")
                for phase in ("before", "after") for arm in arms),
            {("case", phase): "provider-task-" + phase for phase in ("before", "after")},
            {"case": "before-live-probe"}, {"case": ("producer-update",)})
        for event in self.local.log.replay():
            for phase in ("before", "after"):
                self.local.permissions.allowed.add((event.event_id, evaluation_purpose(self.run_id, "case", phase)))
        self.grant("capture")

    def grant(self, operation):
        for event in self.local.log.replay():
            self.local.permissions.allowed.add((event.event_id, preregistration_purpose(self.run_id, operation)))

    def register(self, **changes):
        kwargs = dict(spec=self.spec, histories=self.f.histories, questions={"case": self.f.question})
        kwargs.update(changes)
        anchor = self.store.register(**kwargs)
        self.grant("capture")
        self.grant("read")
        return anchor

    def revoke_foreign(self):
        self.f.revoke_foreign()

    def phase_fixture(self, *, before_only=False):
        """Explicitly patched observation/qualifier port, no model execution."""
        anchor = self.register()
        self.update_proof_allowed = True
        def verify(request, receipt):
            if not self.update_proof_allowed or receipt != b"fictional independent producer proof":
                return None
            role = request["role"]
            return {"schema": "flora-qualified-preregistered-update-v1", "role": role,
                "request_sha256": canonical_sha256(request), "receipt_sha256": sha(receipt),
                "qualifier_id": self.spec.baseline_roles[role].qualifier_id, "allowed": True,
                "authorized_before_execution": True}
        verifier = SimpleNamespace(verify_preregistered_update=lambda *, request, receipt: verify(request, receipt))
        binding = RuntimeRoleBinding("fictional-never-opened-path", object(), verifier, object(), object())
        bindings = {role: binding for role in self.spec.baseline_roles}
        phase = object.__new__(XTDBPhaseSnapshotCustody)
        phase.preregistration = anchor
        phase.run_id = self.run_id
        phase.connection = self.f.f.connection
        phase.artifact_permissions = self.local.permissions
        phase.runtime = SimpleNamespace(sources=self.local.registry, log=self.local.log, objects=self.local.objects,
            source_policy=self.local.permissions, bindings=bindings, artifacts=SimpleNamespace(objects=self.local.objects),
            private=SimpleNamespace(), references=SimpleNamespace(), state_approval_verifier=SimpleNamespace())
        phase._fixture_captures = {}
        self.phase = phase
        self.store.bind_phase_custody(phase, historical_bindings_by_snapshot={slot.snapshot_id: bindings for slot in self.spec.slots
            if not before_only or slot.phase == "before"})
        def metadata(selected, snapshot_id):
            pair = selected._fixture_captures.get(snapshot_id)
            return None if pair is None else pair[0]
        def route(selected, *, snapshot_id, history_authority, historical_bindings):
            self.assertEqual(historical_bindings, bindings)
            return SimpleNamespace(observed_binding=lambda: selected._fixture_captures[snapshot_id][1])
        for target, method in (("metadata", metadata), ("capture_route", route)):
            selected = patch.object(XTDBPhaseSnapshotCustody, target, method)
            selected.start()
            self.addCleanup(selected.stop)
        return anchor

    def capture(self, slot):
        self.store.anchor.authorize_slot_capture(snapshot_id=slot.snapshot_id, case_id=slot.case_id,
            phase=slot.phase, arm=slot.arm, history=self.f.histories[(slot.case_id, slot.phase)])
        event = self.f.original(("fictional capture " + slot.snapshot_id).encode())
        metadata = {"run_id": self.run_id, "snapshot_id": slot.snapshot_id, "case_id": slot.case_id,
            "phase": slot.phase, "arm": slot.arm, "snapshot_sha256": event.content_digest,
            "event_id": event.event_id, "event_sha256": event.event_sha256,
            "preregistration_sha256": self.store.anchor.preregistration_sha256}
        metadata["record_sha256"] = canonical_sha256(metadata)
        roles = dict(self.spec.baseline_roles)
        if slot.phase == "after" and slot.arm == "flora_full":
            roles["personality_judgment"] = replace(roles["personality_judgment"], checkpoint_sha256="f" * 64, generation=2)
        personal = roles["personality_judgment"]
        observation = ObservedPhaseBinding(self.run_id, self.store.anchor.preregistration_sha256,
            slot.snapshot_id, event.content_digest, event.event_id, event.event_sha256, slot.case_id, slot.phase, slot.arm,
            ContextPlan("fixture-context-" + slot.phase, "personal_judgment", exact_claim_ids=("fixture-claim",)),
            "7" * 64, "8" * 64, "fixture-producer", personal.checkpoint_sha256, personal.manifest_sha256, roles)
        self.phase._fixture_captures[slot.snapshot_id] = (metadata, observation)
        self.grant("capture")
        self.grant("read")
        result = self.store.publish_capture(snapshot_id=slot.snapshot_id)
        self.grant("capture")
        self.grant("read")
        return result

    def sealed_before(self):
        self.phase_fixture()
        for slot in self.spec.slots:
            if slot.phase == "before":
                self.capture(slot)
        before = self.store.seal_before()
        self.grant("capture")
        self.grant("read")
        return before

    def updated(self):
        self.sealed_before()
        gate = self.store.begin_update()
        self.grant("capture")
        self.grant("read")
        raw = self.local.objects.put(b"fictional producer activation receipt only")
        event = ExperienceEvent.create(event_type="observation", scope=self.scope, occurred_at=self.f.clock(),
            content_digest=raw.plaintext_sha256, provenance=ProvenanceReference.create(provenance_type="derived_inference",
                source_reference_ids=(gate.event_id,), derivation_activity_id="producer-update", responsible_component="fictional-producer"),
            retention_class="ordinary_experience", storage_tier="raw_buffer", parent_event_ids=(gate.event_id,), payload_reference=raw.object_id)
        self.local.log.append(event, expected_revision=len(self.local.log.replay()) - 1)
        self.local.registry.register(event, raw, "derived_inference")
        self.grant("capture")
        self.grant("read")
        self.update_event = event
        result = self.store.record_update(update_event_ids=(event.event_id,),
            receipts={role: b"fictional independent producer proof" for role in self.spec.baseline_roles})
        self.grant("capture")
        self.grant("read")
        return result

    def test_anchor_freezes_design_without_unknown_after_hashes(self):
        anchor = self.register()
        body = self.store.recover_control(kind="anchor")
        self.assertEqual(body, self.spec.record())
        self.assertEqual(self.store.artifact_id("anchor"), "preregistration")
        self.assertEqual(anchor.history_for("case", "before"), self.f.histories[("case", "before")])
        self.assertNotIn("phase_bindings", body)
        self.assertNotIn("run_plan_sha256", body)
        self.assertEqual(self.register().event_id, anchor.event_id)

    def test_contract_changes_and_duplicate_capture_identity_are_rejected(self):
        self.register()
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.register(spec=replace(self.spec, update_contract=b"changed update policy"))
        with self.assertRaisesRegex(ValueError, "distinct"):
            replace(self.spec, before_probe_invocation_ids={"case": self.spec.slots[0].evaluation_invocation_id}).record()

    def test_full_slot_matrix_mandatory_and_unknown_history_stops(self):
        with self.assertRaisesRegex(ValueError, "complete"):
            replace(self.spec, slots=self.spec.slots[:-1]).record()
        anchor = self.register()
        with self.assertRaises(PermissionError):
            anchor.history_for("unknown", "before")
        slot = self.spec.slots[0]
        with self.assertRaisesRegex(PermissionError, "original history"):
            anchor.authorize_slot_capture(snapshot_id=slot.snapshot_id, case_id=slot.case_id,
                phase=slot.phase, arm=slot.arm, history=self.f.histories[("case", "after")])

    def test_after_capture_and_update_do_not_proceed_before_actual_seal(self):
        anchor = self.register()
        slot = next(slot for slot in self.spec.slots if slot.phase == "after")
        with self.assertRaisesRegex(PermissionError, "before seal"):
            anchor.authorize_slot_capture(snapshot_id=slot.snapshot_id, case_id=slot.case_id,
                phase=slot.phase, arm=slot.arm, history=self.f.histories[("case", "after")])
        with self.assertRaises(PermissionError):
            self.store.begin_update()
        with self.assertRaises(PermissionError):
            self.store.finalize()
        with self.assertRaises(PermissionError):
            self.store.recover_final_binding()

    def test_before_probe_has_separate_declared_identity(self):
        anchor = self.register()
        self.assertTrue(anchor.authorize_before_probe(case_id="case", invocation_id="before-live-probe",
            history=self.f.histories[("case", "before")]))
        with self.assertRaises(PermissionError):
            anchor.authorize_before_probe(case_id="case", invocation_id=self.spec.slots[0].evaluation_invocation_id,
                history=self.f.histories[("case", "before")])

    def test_original_input_registration_uses_actual_typed_anchor_before_final_plan(self):
        anchor = self.register()
        self.store.register_original_inputs(occurred_at=self.f.clock())
        self.assertIsNone(self.f.comparison.metadata(self.run_id, "plan"))
        self.grant("capture")
        self.grant("read")
        for phase in ("before", "after"):
            history = self.f.comparison.metadata(self.run_id, "history:case:" + phase)
            for event in self.local.log.replay():
                self.local.permissions.allowed.add((event.event_id, evaluation_purpose(self.run_id, "case", phase)))
            self.assertIsNotNone(history)
            self.assertEqual(history.record["metadata"]["history_sha256"], self.f.histories[("case", phase)].digest())
            self.assertTrue(anchor.authorize_inputs(protocol=self.spec.protocol, histories=self.f.histories,
                questions={"case": self.f.question}))
        with self.assertRaisesRegex(PermissionError, "actual final binding"):
            self.f.comparison.register_inputs(run_id=self.run_id, plan=self.f.plan, histories=self.f.histories,
                questions={"case": self.f.question}, occurred_at=self.f.clock())

    def test_withdrawn_foreign_dependency_blocks_control_before_decrypt(self):
        self.register()
        self.revoke_foreign()
        with patch.object(AESGCM, "decrypt", side_effect=AssertionError("opened plaintext")) as opened:
            with self.assertRaises(PermissionError):
                self.store.recover_control(kind="anchor")
            opened.assert_not_called()

    def test_cipher_fetch_withdrawal_blocks_inner_aead(self):
        self.register()
        backend = self.local.objects.backend
        original = backend.get_object
        def withdraw_on_owned_fetch(*args, **kwargs):
            value = original(*args, **kwargs)
            if any(frame.function == "get" and frame.filename.endswith("object_store.py") for frame in inspect.stack()):
                self.revoke_foreign()
            return value
        with patch.object(backend, "get_object", side_effect=withdraw_on_owned_fetch), patch.object(AESGCM, "decrypt", side_effect=AssertionError("opened plaintext")) as opened:
            with self.assertRaises(PermissionError):
                self.store.recover_control(kind="anchor")
            opened.assert_not_called()

    def test_slow_clock_withdrawal_blocks_canonical_anchor_append(self):
        count = len(self.local.log.replay())
        def withdraw():
            self.revoke_foreign()
            return self.f.clock()
        self.store.clock = withdraw
        with self.assertRaises(PermissionError):
            self.register()
        self.assertEqual(len(self.local.log.replay()), count)
        self.assertIsNone(self.store._metadata("anchor"))

    def test_missing_phase_controller_does_not_invent_capture(self):
        self.register()
        with self.assertRaisesRegex(PermissionError, "unavailable"):
            self.store.publish_capture(snapshot_id=self.spec.slots[0].snapshot_id)
        self.assertIsNone(self.store._metadata("slot", self.spec.slots[0].snapshot_id))

    def test_before_seal_requires_both_actual_slots_and_baseline_nomination(self):
        self.phase_fixture()
        before = [slot for slot in self.spec.slots if slot.phase == "before"]
        self.capture(before[0])
        with self.assertRaisesRegex(PermissionError, "complete"):
            self.store.seal_before()
        self.capture(before[1])
        sealed = self.store.seal_before()
        self.assertGreater(self.store._canonical(sealed).stream_position,
            max(self.store._canonical(self.store._metadata("slot", slot.snapshot_id)).stream_position for slot in before))
        with self.assertRaisesRegex(PermissionError, "already frozen"):
            self.store.anchor.authorize_slot_capture(snapshot_id=before[0].snapshot_id, case_id="case", phase="before",
                arm=before[0].arm, history=self.f.histories[("case", "before")])

    def test_before_seal_needs_no_after_checkpoint_file_or_ports(self):
        self.phase_fixture(before_only=True)
        before = [slot for slot in self.spec.slots if slot.phase == "before"]
        for slot in before:
            self.capture(slot)
        self.store.seal_before()
        self.assertEqual(set(self.store.historical_bindings), {slot.snapshot_id for slot in before})
        after = next(slot for slot in self.spec.slots if slot.phase == "after")
        with self.assertRaisesRegex(PermissionError, "producer ports are unavailable"):
            self.store._observation(after.snapshot_id)

    def test_after_update_marker_without_independent_producer_proof_is_denied(self):
        self.sealed_before()
        self.store.begin_update()
        self.grant("capture")
        self.grant("read")
        with self.assertRaisesRegex(PermissionError, "post-seal execution"):
            self.store.record_update(update_event_ids=(self.f.correction.event_id,),
                receipts={role: b"fictional independent producer proof" for role in self.spec.baseline_roles})
        with self.assertRaisesRegex(PermissionError, "independently qualified update"):
            slot = next(slot for slot in self.spec.slots if slot.phase == "after")
            self.store.anchor.authorize_slot_capture(snapshot_id=slot.snapshot_id, case_id="case", phase="after",
                arm=slot.arm, history=self.f.histories[("case", "after")])

    def test_actual_postgate_update_receipt_is_requalified_before_after_capture(self):
        self.updated()
        slot = next(slot for slot in self.spec.slots if slot.phase == "after")
        self.capture(slot)
        self.update_proof_allowed = False
        with self.assertRaisesRegex(PermissionError, "no longer qualifies"):
            self.store._observation(slot.snapshot_id)

    def complete_captures(self):
        self.updated()
        for slot in self.spec.slots:
            if slot.phase == "after":
                self.capture(slot)

    def test_finalizer_consumes_all_slots_derives_unknown_after_and_seals_once(self):
        self.complete_captures()
        final = self.store.finalize()
        self.grant("capture")
        self.grant("read")
        self.assertEqual(final.plan.preregistration_sha256, self.spec.preregistration_sha256)
        self.assertNotEqual(final.plan.binding_for("case", "before", "flora_full").model_artifact_sha256,
            final.plan.binding_for("case", "after", "flora_full").model_artifact_sha256)
        self.assertEqual(len(final._record.record["metadata"]["slot_records"]), len(self.spec.slots))
        for native in final.native_plans.values():
            for entry in native.entries:
                self.assertEqual(entry.phase_snapshot.record()["schema"], "flora-native-phase-snapshot-binding-v2")
        self.store.register_final_inputs(final_authority=final, occurred_at=self.f.clock())
        self.assertEqual(self.f.comparison.metadata(self.run_id, "plan").record["metadata"]["plan_sha256"], final.plan.digest())
        final.require_evaluation(plan=final.plan, case_id="case", phase="after", arm="flora_full",
            invocation_id=final.native_plans["flora_full"].entry("case", "after").invocation_id)
        with self.assertRaisesRegex(PermissionError, "predeclared"):
            final.require_evaluation(plan=final.plan, case_id="case", phase="after", arm="flora_full", invocation_id="not-declared")
        self.assertFalse(self.store.recover_control(kind="final_seal")["part1_accepted"])
        count = len(self.local.log.replay())
        self.assertEqual(self.store.recover_final_binding().final_plan_sha256, final.final_plan_sha256)
        self.assertEqual(len(self.local.log.replay()), count)

    def test_coordinator_requires_actual_final_authority_for_durable_anchored_run(self):
        self.complete_captures()
        final = self.store.finalize()
        self.grant("capture")
        self.grant("read")
        self.store.register_final_inputs(final_authority=final, occurred_at=self.f.clock())
        evidence = SelectedRunEvidencePolicy(custody=self.f.comparison, run_id=self.run_id,
            permissions=self.local.permissions, final_authority=final)
        kwargs = dict(manifests=self.f.f.store, cohort_id="cohort", recipe_id="recipe", comparison=self.f.comparison,
            evidence=evidence, assessment=self.f.assessment, plan=final.plan, histories=self.f.histories,
            questions={"case": self.f.question}, native_plans=final.native_plans,
            history_entry_ids={("case", "before"): ("entry-0",), ("case", "after"): ("entry-0", "entry-correction")},
            question_entry_ids={"case": "entry-question"}, provider_task_ids=self.spec.provider_task_ids, clock=self.f.clock)
        with self.assertRaisesRegex(PermissionError, "actual final binding"):
            RegisteredExperimentCoordinator(**kwargs)
        coordinator = RegisteredExperimentCoordinator(**kwargs, final_authority=final)
        for event in self.local.log.replay():
            self.local.permissions.allowed.add((event.event_id, coordinator_purpose("exp", self.run_id, "capture")))
        coordinator.prepare()
        self.assertEqual(coordinator.record()["mode"], "prepared_synthetic_two_stage")
        self.assertEqual(coordinator.record()["final_binding"]["preregistration_sha256"], self.spec.preregistration_sha256)

    def test_real_class_cannot_reattach_changed_plan_or_native_map_to_seal(self):
        self.complete_captures()
        final = self.store.finalize()
        with self.assertRaisesRegex(PermissionError, "sealed plan"):
            RegisteredExperimentFinalBinding(self.store, replace(final.plan, context_token_budget=final.plan.context_token_budget + 1),
                final.native_plans, final._record)
        changed = dict(final.native_plans)
        native = changed["flora_full"]
        changed["flora_full"] = replace(native, entries=(replace(native.entries[0], invocation_id="substituted"), *native.entries[1:]))
        with self.assertRaisesRegex(PermissionError, "canonical payload"):
            RegisteredExperimentFinalBinding(self.store, final.plan, changed, final._record)
        old = final.plan
        final.plan = replace(old, context_byte_budget=old.context_byte_budget + 1)
        with self.assertRaises(PermissionError):
            final.authorize_plan(plan=final.plan, metadata_only=True)

    def test_owned_metadata_final_reader_uses_its_connection_and_never_guesses_producer_ports(self):
        self.complete_captures()
        final = self.store.finalize()
        read = ReadOnlyNativeSQLConnection(self.f.f.connection, read_timeout_ms=1000)
        owned = final.bind_read_connection(read)
        self.assertIs(owned.store.comparison.connection, read)
        self.assertIs(owned.store.manifests.connection, read)
        self.assertIs(owned.store.phase_custody.connection, read)
        self.assertIs(owned.store.permissions.connection, read)
        with patch.object(AESGCM, "decrypt", side_effect=AssertionError("opened plaintext")) as opened:
            self.assertTrue(owned.authorize_plan(plan=final.plan, metadata_only=True))
            opened.assert_not_called()
        with self.assertRaisesRegex(PermissionError, "cannot open producer proofs"):
            owned.authorize_plan(plan=final.plan, metadata_only=False)
        full = final.bind_read_connection(read, phase_custody=owned.store.phase_custody,
            historical_bindings_by_snapshot=self.store.historical_bindings)
        context_policy = owned.store.phase_custody.runtime.source_policy
        self.assertIsNot(full.store.permissions, context_policy)
        with patch.object(context_policy, "permits", side_effect=AssertionError("native context policy recursed")):
            self.assertTrue(full.authorize_plan(plan=final.plan, metadata_only=True))
        self.revoke_foreign()
        with self.assertRaises(PermissionError):
            owned.authorize_plan(plan=final.plan, metadata_only=True)

    def test_final_dispatch_rejects_producer_update_proof_withdrawal(self):
        self.complete_captures()
        final = self.store.finalize()
        self.grant("read")
        slot = self.spec.slots[0]
        final.authorize_evaluation(plan=final.plan, case_id=slot.case_id, phase=slot.phase, arm=slot.arm,
            invocation_id=slot.evaluation_invocation_id)
        self.update_proof_allowed = False
        with self.assertRaisesRegex(PermissionError, "no longer qualifies"):
            final.authorize_evaluation(plan=final.plan, case_id=slot.case_id, phase=slot.phase, arm=slot.arm,
                invocation_id=slot.evaluation_invocation_id)

    def test_signed_observed_provider_capture_has_separate_evaluation_boundary(self):
        self.complete_captures()
        final = self.store.finalize()
        self.grant("read")
        source = self.f.histories[("case", "before")].event_ids[0]
        self.local.permissions.allowed.remove((source, evaluation_purpose(self.run_id, "case", "before")))
        self.update_proof_allowed = False
        self.assertTrue(final.authorize_attempt_capture(plan=final.plan, case_id="case", phase="before",
            arm="general_model_memory", invocation_id="provider-task-before"))
        with self.assertRaises(PermissionError):
            final.authorize_evaluation(plan=final.plan, case_id="case", phase="before",
                arm="general_model_memory", invocation_id="provider-task-before")
        with self.assertRaises(PermissionError):
            final.authorize_attempt_capture(plan=final.plan, case_id="case", phase="before",
                arm="flora_full", invocation_id="provider-task-before")

    def test_orphan_final_binding_requires_explicit_repair_without_extra_append(self):
        self.complete_captures()
        original = self.f.f.connection.execute
        key = self.f.comparison._key(self.run_id, "final_binding")
        def fail_final_index(query, params):
            if query.startswith("INSERT") and params[0] == key:
                raise RuntimeError("fixture lost final binding index write")
            return original(query, params)
        with patch.object(self.f.f.connection, "execute", side_effect=fail_final_index), self.assertRaises(RuntimeError):
            self.store.finalize()
        count = len(self.local.log.replay())
        with self.assertRaisesRegex(PermissionError, "reconciliation"):
            self.store.finalize()
        self.grant("capture")
        final = self.store.finalize(reconcile=True)
        self.assertEqual(len(self.local.log.replay()), count)
        self.assertEqual(final.preregistration_sha256, self.spec.preregistration_sha256)

    def test_orphan_anchor_requires_explicit_authenticated_reconciliation(self):
        original = self.f.f.connection.execute
        def fail_anchor_index(query, params):
            if query.startswith("INSERT") and params[0] == self.f.comparison._key(self.run_id, "preregistration"):
                raise RuntimeError("fixture lost anchor index write")
            return original(query, params)
        with patch.object(self.f.f.connection, "execute", side_effect=fail_anchor_index), self.assertRaises(RuntimeError):
            self.register()
        before = len(self.local.log.replay())
        with self.assertRaisesRegex(PermissionError, "explicit"):
            self.register()
        self.grant("capture")
        anchor = self.register(reconcile=True)
        self.assertEqual(len(self.local.log.replay()), before)
        self.assertEqual(anchor.preregistration_sha256, self.spec.preregistration_sha256)

    def test_orphan_before_seal_blocks_progress_and_explicit_repair_does_not_reappend(self):
        self.phase_fixture()
        for slot in self.spec.slots:
            if slot.phase == "before":
                self.capture(slot)
        original = self.f.f.connection.execute
        key = self.f.comparison._key(self.run_id, self.store.artifact_id("before_seal"))
        def fail_before_index(query, params):
            if query.startswith("INSERT") and params[0] == key:
                raise RuntimeError("fixture lost before seal index write")
            return original(query, params)
        with patch.object(self.f.f.connection, "execute", side_effect=fail_before_index), self.assertRaises(RuntimeError):
            self.store.seal_before()
        before = len(self.local.log.replay())
        with self.assertRaisesRegex(PermissionError, "reconciliation"):
            self.store.begin_update()
        self.grant("capture")
        self.store.seal_before(reconcile=True)
        self.assertEqual(len(self.local.log.replay()), before)


if __name__ == "__main__":
    unittest.main()
