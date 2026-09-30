"""Fictional selected row/log contracts with actual local encrypted controls.

These tests do not exercise a learned model or produce a behavioral result.
"""
import asyncio
from dataclasses import replace
import inspect
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cognitive_kernel.contracts import ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from flora.comparator import encoded, sha
from flora.comparison_run import ArmBinding, HistorySnapshot, PairedRunPlan, SourceMaterial
from flora.evaluation_protocol import ARMS, EvaluationCase, EvaluationProtocol
from flora.selected.assessment_custody import XTDBAssessmentCustody
from flora.selected.comparison_custody import SelectedRunEvidencePolicy, XTDBComparisonCustody, evaluation_purpose
from flora.selected.context import ContextPlan
from flora.selected.experiment_coordinator import RegisteredExperimentCoordinator, coordinator_purpose
from flora.selected.experiment_manifests import CohortEntry, cohort_source_purpose, manifest_purpose
from flora.selected.native_arm import FrozenNativeArmPlan, NativeInvocationEntry, NativePhaseSnapshotBinding

import test_experiment_manifests as support


class CoordinatorContractTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.f = support.ExperimentManifestContractsTest("test_cohort_shape_does_not_qualify_and_private_foreign_ids_are_not_local_parents")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        local, scope = self.f.authorities[0], self.f.authorities[0].registry.scope
        self.local, self.scope = local, scope
        self.clock = lambda: "2026-09-30T00:00:00Z"
        self.correction = self.original(b"Fictional correction only")
        self.question = b"Fictional question only"
        self.question_event = self.original(self.question)
        self.entries = (self.f.entries[0], self.f.entries[1],
            replace(self.f.entries[0], entry_id="entry-correction", event_id=self.correction.event_id),
            replace(self.f.entries[0], entry_id="entry-question", event_id=self.question_event.event_id, usage_role="question"))
        cohort = self.f.store.register_cohort(cohort_id="cohort", entries=self.entries, rules=self.f.rules)
        self.f.grant_read(cohort)
        recipe = self.f.store.register_recipe(recipe_id="recipe", cohort_id="cohort",
            code_files=(("src/flora/selected/supplied_fixture.py", b"# Fictional procedure only\n"),),
            dependency_lock=b"fictional dependency lock", role_contracts=(("personality", b"supplied producer interface"),),
            source_choices=(("entry-0", "eligible"), ("entry-1", "stop")), stop_defer_contract=b"supplied stop policy")
        self.f.grant_read(recipe)
        self.comparison = self.comparison_store()
        originals = (SourceMaterial(self.f.events[0], self.local.objects.get(self.local.registry.raw_reference(self.f.events[0].payload_reference))),)
        self.histories = {("case", "before"): HistorySnapshot(scope, originals),
            ("case", "after"): HistorySnapshot(scope, originals + (SourceMaterial(self.correction, b"Fictional correction only"),))}
        case = EvaluationCase("case", scope.host_instance_id, "relevant_correction", "heldout",
            self.histories[("case", "before")].digest(), self.histories[("case", "after")].digest(), "c" * 64,
            self.correction.event_id)
        protocol = EvaluationProtocol("protocol", "d" * 64, self.clock(), "feature", 16, 1000,
            (case,), "e" * 64, "f" * 64, "1" * 64, recipe["content_sha256"], ("other-host",))
        self.native = {arm: FrozenNativeArmPlan(scope, self.local.registry.authority_namespace_id, arm, "a" * 64,
            tuple(NativeInvocationEntry("case", phase, "invocation-" + arm + "-" + phase,
                ContextPlan("context-" + phase, "personal_judgment", exact_claim_ids=("fixture-claim",)), "7" * 64,
                NativePhaseSnapshotBinding("run", "snapshot-" + arm + "-" + phase, arm))
                for phase in ("before", "after"))) for arm in ("flora_full", "same_evidence_ablation")}
        arm_bindings = {arm: ArmBinding("fixture-producer", "3" * 64,
            self.native[arm].lineage_sha256 if arm in self.native else "4" * 64, "explicit-update") for arm in ARMS}
        self.plan = PairedRunPlan(protocol, arm_bindings, 32, 4096, 2, {"case": sha(self.question)},
            phase_bindings={("case", phase, arm): binding for arm, binding in arm_bindings.items() for phase in ("before", "after")})
        configuration = patch("flora.selected.comparison_custody.configure_xtdb_connection")
        configuration.start()
        self.addCleanup(configuration.stop)
        registration = patch("flora.selected.comparison_custody.register_experience_source", self.f.register_source)
        registration.start()
        self.addCleanup(registration.stop)
        self.comparison.register_inputs(run_id="run", plan=self.plan, histories=self.histories,
            questions={"case": self.question}, occurred_at=self.clock())
        self.evidence = SelectedRunEvidencePolicy(custody=self.comparison, run_id="run", permissions=self.local.permissions)
        self.assessment = XTDBAssessmentCustody(comparison_custody=self.comparison, signature_authority=object())
        for (case_id, phase), history in self.histories.items():
            for event in history.event_ids:
                self.local.permissions.allowed.add((event, evaluation_purpose("run", case_id, phase)))
        self.grant_all("capture")
        self.coordinator = self.new_coordinator()

    def comparison_store(self):
        with patch("flora.selected.comparison_custody.configure_xtdb_connection"):
            return XTDBComparisonCustody(scope=self.scope, authority_namespace_id=self.local.registry.authority_namespace_id,
                connection=self.f.connection, registry=self.local.registry, objects=self.local.objects, log=self.local.log)

    def original(self, content):
        raw = self.local.objects.put(content)
        event = ExperienceEvent.create(event_type="observation", scope=self.scope, occurred_at="2020-01-01T00:00:00Z",
            content_digest=raw.plaintext_sha256, provenance=ProvenanceReference.create(provenance_type="generated_reconstruction",
                source_reference_ids=("fictional-coordinator-source",), derivation_activity_id="coordinator-fixture",
                responsible_component="synthetic-test"), retention_class="ordinary_experience", storage_tier="raw_buffer",
            payload_reference=raw.object_id)
        self.local.log.append(event, expected_revision=len(self.local.log.replay()) - 1)
        self.local.registry.register(event, raw, "generated_reconstruction")
        for purpose in (manifest_purpose("exp", "capture"), manifest_purpose("exp", "read"), cohort_source_purpose("exp", "training")):
            self.local.permissions.allowed.add((event.event_id, purpose))
        return event

    def grant_all(self, operation):
        purpose = coordinator_purpose("exp", "run", operation)
        for event in self.local.log.replay():
            self.local.permissions.allowed.add((event.event_id, purpose))

    def new_coordinator(self, **changes):
        values = dict(manifests=self.f.store, cohort_id="cohort", recipe_id="recipe", comparison=self.comparison,
            evidence=self.evidence, assessment=self.assessment, plan=self.plan, histories=self.histories,
            questions={"case": self.question}, native_plans=self.native,
            history_entry_ids={("case", "before"): ("entry-0",), ("case", "after"): ("entry-0", "entry-correction")},
            question_entry_ids={"case": "entry-question"},
            provider_task_ids={("case", phase): "provider-" + phase for phase in ("before", "after")}, clock=self.clock)
        values.update(changes)
        return RegisteredExperimentCoordinator(**values)

    def prepared(self):
        self.coordinator.prepare()
        self.grant_all("capture")
        self.grant_all("read")

    def revoke_foreign(self):
        self.f.authorities[1].permissions.allowed.remove((self.f.events[1].event_id, cohort_source_purpose("exp", "heldout")))

    def test_exact_frozen_binding_and_dedicated_recovery_without_qualification(self):
        self.prepared()
        body = self.coordinator.recover_stage(artifact_id="coordinator:binding")
        self.assertEqual(body["payload"], self.coordinator.record())
        self.assertFalse(body["part1_accepted"])
        self.assertEqual(body["payload"]["mode"], "prepared_history")
        self.assertIs(self.comparison.log, self.local.log)
        self.assertIs(self.comparison.objects, self.local.objects)
        self.assertIsNone(self.coordinator.phase_router)
        self.assertEqual(self.coordinator.prepare().event_id, self.comparison.metadata("run", "coordinator:binding").event_id)

    async def test_missing_ports_are_durable_blocked_preflight_not_a_run(self):
        self.prepared()
        outcome = await self.coordinator.execute(adapters={})
        self.assertEqual(outcome.status, "preflight_blocked")
        self.assertIsNone(outcome.run)
        self.assertFalse(outcome.part1_accepted)
        self.assertEqual(len(outcome.reasons), 5)
        self.assertIn("missing_phase_router", outcome.reasons)
        self.assertIn("missing_provider_attempt_custody", outcome.reasons)
        self.assertIsNone(self.comparison.metadata("run", "run"))
        self.assertIsNone(self.comparison.metadata("run", "coordinator:running"))
        self.grant_all("read")
        body = self.coordinator.recover_stage(artifact_id=outcome.artifact_id)
        self.assertFalse(body["payload"]["attempted"])

    def test_same_scope_equivalent_controller_does_not_pass_actual_identity(self):
        another = self.comparison_store()
        for changes in ({"comparison": another},
                        {"assessment": XTDBAssessmentCustody(comparison_custody=another, signature_authority=object())}):
            with self.subTest(changes=tuple(changes)), self.assertRaisesRegex(ValueError, "physical host"):
                self.new_coordinator(**changes)

    def test_complete_phase_bindings_and_registered_recipe_are_required(self):
        with self.assertRaisesRegex(ValueError, "phase matrix"):
            self.new_coordinator(plan=replace(self.plan, phase_bindings=None))
        with self.assertRaisesRegex(ValueError, "registered custody"):
            self.new_coordinator(plan=replace(self.plan, protocol=replace(self.plan.protocol, builder_recipe_sha256="9" * 64)))

    def test_different_native_entry_or_provider_task_cannot_move_into_binding(self):
        changed = dict(self.native)
        native = changed["flora_full"]
        changed["flora_full"] = replace(native, entries=(replace(native.entries[0], invocation_id="different"), native.entries[1]))
        with self.assertRaisesRegex(ValueError, "lineage"):
            self.new_coordinator(native_plans=changed)
        with self.assertRaisesRegex(ValueError, "distinct"):
            self.new_coordinator(provider_task_ids={("case", phase): "same" for phase in ("before", "after")})

    def test_history_and_question_exact_cohort_mapping_required(self):
        with self.assertRaisesRegex(ValueError, "cohort entries"):
            self.new_coordinator(history_entry_ids={("case", phase): ("entry-1",) for phase in ("before", "after")})
        with self.assertRaisesRegex(ValueError, "cohort source"):
            self.new_coordinator(question_entry_ids={"case": "entry-correction"})

    def test_control_artifact_cannot_use_generic_comparison_reader(self):
        self.prepared()
        with patch.object(AESGCM, "decrypt", side_effect=AssertionError("plaintext opened")) as opened:
            with self.assertRaisesRegex(PermissionError, "dedicated recovery"):
                self.comparison.read(run_id="run", artifact_id="coordinator:binding",
                    permissions=self.local.permissions, purpose=coordinator_purpose("exp", "run", "read"))
            opened.assert_not_called()

    def test_already_withdrawn_foreign_source_stops_before_private_control_read(self):
        self.prepared()
        self.revoke_foreign()
        with patch.object(AESGCM, "decrypt", side_effect=AssertionError("plaintext opened")) as opened:
            with self.assertRaises(PermissionError):
                self.coordinator.recover_stage(artifact_id="coordinator:binding")
            opened.assert_not_called()

    def test_withdrawal_at_actual_cipher_fetch_blocks_AEAD(self):
        self.prepared()
        artifact = self.comparison.metadata("run", "coordinator:binding")
        target = artifact.record["object_id"]
        backend = self.local.objects.backend
        get = backend.get_object
        fired, target_decrypts = [], []
        decrypt = AESGCM.decrypt
        def fetch(namespace, object_id):
            cipher = get(namespace, object_id)
            if object_id == target and any(frame.function == "get" and frame.filename.endswith("object_store.py") for frame in inspect.stack()):
                self.revoke_foreign()
                fired.append(True)
            return cipher
        def track(cipher_self, nonce, cipher, aad):
            if fired:
                target_decrypts.append(True)
            return decrypt(cipher_self, nonce, cipher, aad)
        with patch.object(backend, "get_object", fetch), patch.object(AESGCM, "decrypt", track):
            with self.assertRaises(PermissionError):
                self.coordinator.recover_stage(artifact_id="coordinator:binding")
        self.assertEqual(fired, [True])
        self.assertEqual(target_decrypts, [])

    def test_clock_withdrawal_happens_before_canonical_stage_append(self):
        self.prepared()
        before = len(self.local.log.replay())
        def clock():
            self.revoke_foreign()
            return self.clock()
        self.coordinator.clock = clock
        with self.assertRaises(PermissionError):
            self.coordinator.readiness(adapters={})
        self.assertEqual(len(self.local.log.replay()), before)

    def test_capture_is_separate_from_evaluation_and_no_grants_are_created(self):
        purpose = coordinator_purpose("exp", "run", "capture")
        self.local.permissions.allowed = {entry for entry in self.local.permissions.allowed if entry[1] != purpose}
        prior = set(self.local.permissions.allowed)
        with self.assertRaisesRegex(PermissionError, "control purpose"):
            self.coordinator.prepare()
        self.assertEqual(self.local.permissions.allowed, prior)
        self.assertIsNone(self.comparison.metadata("run", "coordinator:binding"))

    def test_controller_mutation_and_configuration_mutation_fail_closed(self):
        self.prepared()
        with patch.object(self.assessment, "comparison", self.comparison_store()):
            with self.assertRaisesRegex(PermissionError, "identity"):
                self.coordinator.recover_stage(artifact_id="coordinator:binding")
        self.plan.phase_bindings[("case", "before", "flora_full")] = replace(self.plan.arm_bindings["flora_full"], model_artifact_sha256="6" * 64)
        with self.assertRaisesRegex(PermissionError, "configuration"):
            self.coordinator.record()

    def test_running_marker_cannot_be_reexecuted_or_blindly_called_completed(self):
        self.prepared()
        artifact = self.coordinator._put(artifact_id="coordinator:running", stage="running",
            payload={"status": "started", "execution_nonce": "fictional-nonce", "attempted": True},
            parents=(self.comparison.metadata("run", "coordinator:binding").event_id,))
        self.grant_all("read")
        self.grant_all("capture")
        with self.assertRaisesRegex(ValueError, "already started"):
            asyncio.run(self.coordinator.execute(adapters={}))
        recovered = self.coordinator.recover_interrupted()
        self.assertEqual(recovered.record["kind"], "coordinator_interrupted")
        self.assertIsNone(self.comparison.metadata("run", "run"))
        self.assertFalse(self.coordinator._partial_receipts()["accepted_execution"])
        self.assertIn(artifact.event_id, recovered.record["parent_event_ids"])

    def test_partial_receipts_use_registered_native_metadata_not_accepted_arm_records(self):
        self.prepared()
        invocation = self.native["flora_full"].entry("case", "after").invocation_id
        raw = self.local.objects.put(b"private fictional failed input")
        event = ExperienceEvent.create(event_type="qualified_model_input", scope=self.scope,
            occurred_at=self.clock(), content_digest=raw.plaintext_sha256,
            provenance=ProvenanceReference.create(provenance_type="derived_inference", source_reference_ids=(self.correction.event_id,),
                derivation_activity_id=invocation, responsible_component="flora-qualified-runtime", model_id="3" * 64),
            retention_class="ordinary_experience", storage_tier="raw_buffer", parent_event_ids=(self.correction.event_id,), payload_reference=raw.object_id)
        self.local.log.append(event, expected_revision=len(self.local.log.replay()) - 1)
        self.local.registry.register(event, raw, "derived_inference")
        partial = self.coordinator._partial_receipts()
        self.assertEqual(partial["native"][0]["event_id"], event.event_id)
        self.assertFalse(partial["accepted_execution"])
        self.assertNotIn("private fictional", str(partial))

    def test_unregistered_native_input_and_real_attempt_failure_retain_private_metadata(self):
        from flora.selected.decision_outcome import RecordedEvent
        from flora.selected.experiment_runtime import _RuntimePrivateCustody
        self.prepared()
        invocation = self.native["flora_full"].entry("case", "after").invocation_id
        runtime = SimpleNamespace(scope=self.scope, authority_namespace_id=self.local.registry.authority_namespace_id,
            claims=SimpleNamespace(connection=self.f.connection), objects=self.local.objects, log=self.local.log)
        private = _RuntimePrivateCustody(runtime)
        captured = []
        parents = (self.correction.event_id,)
        for kind, payload in (("qualified_model_input", b"fictional private input"),
                              ("qualified_model_attempt_failure", b"fictional failure receipt")):
            raw = self.local.objects.put(payload)
            event = ExperienceEvent.create(event_type=kind, scope=self.scope, occurred_at=self.clock(),
                content_digest=raw.plaintext_sha256, provenance=ProvenanceReference.create(provenance_type="derived_inference",
                    source_reference_ids=parents, derivation_activity_id=invocation,
                    responsible_component="flora-qualified-runtime", model_id="3" * 64),
                retention_class="ordinary_experience", storage_tier="raw_buffer", parent_event_ids=parents, payload_reference=raw.object_id)
            self.local.log.append(event, expected_revision=len(self.local.log.replay()) - 1)
            private.register(RecordedEvent(event, raw), invocation, kind)
            self.assertIsNone(self.local.registry.lookup(event.event_id))
            captured.append(event.event_id)
            parents = (event.event_id,)
        with patch.object(self.coordinator, "phase_router", SimpleNamespace(runtime=SimpleNamespace(private=private))), \
                patch.object(AESGCM, "decrypt", side_effect=AssertionError("partial custody opened plaintext")):
            partial = self.coordinator._partial_receipts()
        self.assertEqual({item["event_id"] for item in partial["native"]}, set(captured))
        self.assertTrue(all(item["private_metadata_registered"] for item in partial["native"]))
        self.assertTrue(all(item["custody_state"] == "private_registered" for item in partial["native"]))
        self.assertFalse(partial["accepted_execution"])

    def test_foreign_source_fence_is_inside_copied_phase_runtime_cipher_reads(self):
        self.prepared()
        runtime = SimpleNamespace(objects=self.local.objects, artifacts=SimpleNamespace(objects=self.local.objects),
            private=SimpleNamespace(runtime=None), references=SimpleNamespace(runtime_custody=None),
            state_approval_verifier=SimpleNamespace(proofs=SimpleNamespace(objects=self.local.objects)))
        router = SimpleNamespace(custody=SimpleNamespace(runtime=runtime), runtime=runtime,
            history_authority=self.evidence)
        with patch.object(self.coordinator, "phase_router", router):
            fenced = self.coordinator._guarded_router()
        self.assertIs(runtime.objects, self.local.objects)
        self.assertIs(runtime.artifacts.objects, self.local.objects)
        target = self.comparison.metadata("run", "coordinator:binding").record["object_id"]
        raw = self.local.registry.raw_reference(target)
        get = self.local.objects.backend.get_object
        def fetch(namespace, object_id):
            cipher = get(namespace, object_id)
            if object_id == target and any(frame.function == "get" and frame.filename.endswith("object_store.py") for frame in inspect.stack()):
                self.revoke_foreign()
            return cipher
        with patch.object(self.local.objects.backend, "get_object", fetch), \
                patch.object(AESGCM, "decrypt", side_effect=AssertionError("revoked phase bytes decrypted")):
            with self.assertRaises(PermissionError):
                fenced.runtime.objects.get(raw)

    def test_owned_cohort_fence_uses_owned_metadata_connection_and_current_foreign_grants(self):
        self.prepared()
        connection = support.FixtureConnection()
        connection.records = self.f.connection.records
        fence = self.coordinator._owned_base_fence(connection)
        with patch.object(self.f.connection, "execute", side_effect=AssertionError("shared connection used")), \
                patch.object(connection, "execute", wraps=connection.execute) as owned_reads:
            fence()
            self.assertGreater(owned_reads.call_count, 0)
            self.revoke_foreign()
            with self.assertRaises(PermissionError):
                fence()

    async def test_mechanical_failed_run_preserves_six_attempts_and_is_not_Part1(self):
        # Orchestration-only supplied unavailable ports. There is no producer
        # admission, model execution, behavioral test, or readiness evidence.
        from flora.comparison_run import ArmStopped
        self.prepared()
        ready = replace(self.coordinator.readiness(adapters={}), status="supplied_ports_ready", reasons=())
        async def unavailable(request):
            raise ArmStopped("unavailable")
        native_ports = {arm: SimpleNamespace(prepare=unavailable, execute=AsyncMock(), execution_records={}) for arm in self.native}
        # This fictional row port cannot satisfy the real selected-engine
        # terminal metadata fence. Supply an explicit fixture predicate only
        # for this unavailable-denominator custody check, never a model result.
        def fixture_history_metadata(*, case_id, phase, history):
            return (history == self.histories[(case_id, phase)]
                and all(self.local.permissions.permits(self.local.registry.lookup(event_id),
                    evaluation_purpose("run", case_id, phase)) for event_id in history.event_ids))
        with patch.object(self.coordinator, "readiness", return_value=ready), patch.object(self.coordinator, "_current"), \
                patch.object(self.coordinator, "_execution_adapters", return_value=native_ports), \
                patch.object(self.evidence, "authorize_history_metadata", side_effect=fixture_history_metadata):
            outcome = await self.coordinator.execute(adapters={})
        self.assertEqual(outcome.status, "completed_custody")
        self.assertEqual(len(outcome.run.attempts), 6)
        self.assertEqual({attempt.status for attempt in outcome.run.attempts}, {"unavailable"})
        self.assertEqual(len(self.comparison.metadata("run", "run").record["metadata"]["matrix"]), 6)
        self.assertFalse(outcome.part1_accepted)
        for adapter in native_ports.values():
            adapter.execute.assert_not_called()
        self.grant_all("read")
        with patch.object(self.coordinator, "_current"):
            body = self.coordinator.recover_stage(artifact_id=outcome.artifact_id)
        self.assertEqual(body["payload"]["behavioral_result"], "not_collected")

    async def test_interrupted_failure_sanitized_and_exact_recovery_idempotent(self):
        self.prepared()
        ready = replace(self.coordinator.readiness(adapters={}), status="supplied_ports_ready", reasons=())
        with patch.object(self.coordinator, "readiness", return_value=ready), patch.object(self.coordinator, "_current"), \
                patch.object(self.coordinator, "_execution_adapters", return_value={}), \
                patch("flora.selected.experiment_coordinator.run_paired", AsyncMock(side_effect=RuntimeError("private prompts and private exception payload"))):
            with self.assertRaises(RuntimeError):
                await self.coordinator.execute(adapters={})
            self.grant_all("read")
            body = self.coordinator.recover_stage(artifact_id="coordinator:interrupted")
            self.assertEqual(body["payload"]["reason"], "execution_port_failure")
            self.assertNotIn("private prompts", str(body))
            prior = self.comparison.metadata("run", "coordinator:interrupted")
            before = len(self.local.log.replay())
            self.assertEqual(self.coordinator.recover_interrupted(), prior)
            self.assertEqual(len(self.local.log.replay()), before)

    async def test_cancellation_does_not_resume_custody_writes(self):
        # Deliberate orchestration-only patch. No readiness, model, provider or
        # empirical result is claimed by this cancellation fixture.
        self.prepared()
        preflight = self.coordinator.readiness(adapters={})
        ready = replace(preflight, status="supplied_ports_ready", reasons=())
        before = len(self.local.log.replay())
        with patch.object(self.coordinator, "readiness", return_value=ready), \
                patch.object(self.coordinator, "_current"), \
                patch.object(self.coordinator, "_execution_adapters", return_value={}), \
                patch("flora.selected.experiment_coordinator.run_paired", AsyncMock(side_effect=asyncio.CancelledError)):
            with self.assertRaises(asyncio.CancelledError):
                await self.coordinator.execute(adapters={})
        self.assertEqual(len(self.local.log.replay()), before + 1)
        self.assertIsNotNone(self.comparison.metadata("run", "coordinator:running"))
        self.assertIsNone(self.comparison.metadata("run", "coordinator:completed"))
        self.assertIsNone(self.comparison.metadata("run", "coordinator:interrupted"))


if __name__ == "__main__":
    unittest.main()
