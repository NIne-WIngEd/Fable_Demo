"""Actual native paired-run custody, with fictional producer outputs/proofs.

Selected engines/permissions/runtime/lineage/custody are real. Supplied checkpoint,
phase receipts, output and usage are fixtures; no learned advantage is measured.
"""
import asyncio
import base64
from copy import copy
from dataclasses import replace
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import traceback
from types import SimpleNamespace
import unittest
import uuid

from cognitive_kernel.claim_contracts import CanonicalTaggedValue
from cognitive_kernel.canonical import canonical_json_bytes, canonical_sha256
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
from flora.selected.native_arm import FrozenNativeArmPlan, NativeArmAdapter, NativeInvocationEntry, NativeWorkerCompletion
from flora.selected.native_reads import InitializedNativeSessionFactory, NativeReadManifest, SelectedNativeReadServices
from flora.selected.native_writer_guard import NativeWriterConfiguration, NativeWriterGuard, VerifiedNativeWriterOwnership
from flora.selected.bounded_xtdb_reads import BoundedXTDBReadConfiguration, BoundedXTDBReadOpener, ExplicitXTDBReadCredentials
from flora.comparison_run import _context_bytes
import psycopg
from psycopg.conninfo import conninfo_to_dict


def fixture(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_ROOT = Path(__file__).resolve().parents[1]
_runtime = fixture("flora_native_comparison_backend_fixture", Path(__file__).parent / "test_selected_runtime_bridge.py")
_phase = fixture("flora_native_comparison_phase_fixture", _ROOT / "test_selected_judgment_lineage.py")
_native = fixture("flora_native_comparison_process_fixture", _ROOT / "native_contract_fixture.py")


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
        context = f.runtime._context(context_plan)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        # The subprocess relays existing fictional fixture receipts. No model
        # is trained or inferred by this process-transport contract test.
        worker = _native.worker_fixture.worker_fixture(temporary.name,
            "import sys,json,hashlib\nraw=sys.stdin.buffer.read()\nr=json.loads(raw)\n"
            "sys.stdout.write(json.dumps({'invocation_id':r['invocation_id'],"
            "'worker_request_sha256':hashlib.sha256(raw).hexdigest(),"
            "'qualified_output_event_id':r['output_event'],'meter':r['meter']}))\n",
            scope=f.scope, namespace=f.namespace)
        owner_config = NativeWriterConfiguration(f.scope, f.namespace, "native-comparison-fixture-owner",
            psycopg.__version__, "a" * 64, 5000)
        owner_verifier = SimpleNamespace(verify_native_writer=lambda *, request, receipt:
            VerifiedNativeWriterOwnership("fixture-owner-qualifier", "fixture-owner-qualification",
                canonical_sha256(request), hashlib.sha256(receipt).hexdigest(), True))
        writer_guard = NativeWriterGuard(connection=f.connection, configuration=owner_config,
            verifier=owner_verifier, qualification_receipt=b"supplied fictional exclusive-owner proof",
            qualifier_id="fixture-owner-qualifier", qualification_id="fixture-owner-qualification")
        read_manifest = NativeReadManifest(f.scope, f.namespace, "2" * 64, "3" * 64, 1, 60000, 5000,
            allow_current_fixture_route=True)
        parameters = conninfo_to_dict(f.connection.info.dsn)
        opener = BoundedXTDBReadOpener(configuration=BoundedXTDBReadConfiguration(f.connection.info.hostaddr,
            int(f.connection.info.port), f.connection.info.dbname, f.connection.info.user, psycopg.__version__,
            2, 5000, 60000), credentials=ExplicitXTDBReadCredentials(parameters.get("password") or "explicit-fixture-trust"))
        bridge = object.__new__(_native.NativeContractFixture)
        bridge.runtime, bridge.scope, bridge.namespace = f.runtime, f.scope, f.namespace
        bridge.read_hook, bridge.binder_hook = None, None
        factory = InitializedNativeSessionFactory(artifact_sha256="2" * 64, configuration_sha256="3" * 64,
            connection_opener=opener, bind_initialized=bridge._bind, backend_read_timeout_ms=5000)
        reads = SelectedNativeReadServices(manifest=read_manifest, factory=factory)
        worker.manifest = replace(worker.manifest, read_service_artifact_sha256=reads.artifact_sha256,
            read_service_configuration_sha256=reads.configuration_sha256,
            writer_guard_artifact_sha256=writer_guard.artifact_sha256,
            writer_guard_configuration_sha256=writer_guard.configuration_sha256)
        key = _native.Ed25519PrivateKey.generate()
        payload = {"schema": "fictional-worker-qualification-v1", "manifest": worker.manifest.manifest_sha256}
        worker.qualification_receipt = canonical_json_bytes({"payload": payload,
            "signature": base64.b64encode(key.sign(canonical_json_bytes(payload))).decode()})
        worker.verifier = _native.worker_fixture.FictionalWorkerQualifier(key.public_key())
        frozen = FrozenNativeArmPlan(f.scope, f.namespace, "flora_full", worker.manifest.manifest_sha256,
            tuple(NativeInvocationEntry("case", phase, "paired-native-" + phase, context_plan,
                hashlib.sha256(_context_bytes(context)).hexdigest()) for phase in ("before", "after")))
        bindings["flora_full"] = replace(bindings["flora_full"], lineage_sha256=frozen.lineage_sha256)
        plan = replace(plan, arm_bindings=bindings)
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
            grant(f.registry.lookup(custody.metadata("native-run", f"history:{case_id}:{phase}").event_id),
                evaluation_purpose("native-run", case_id, phase))
        history_authority = SelectedRunEvidencePolicy(custody=custody, run_id="native-run", permissions=f.policy)
        verifier = NativeJudgmentLineageVerifier(runtime=f.runtime, history_authority=history_authority,
            run_plan_sha256=plan.digest(), history_for=lambda case, phase: histories[(case, phase)],
            invocation_id_for=lambda request, result: "paired-native-" + request.phase,
            phase_receipt_for=lambda snapshot: _phase.fictional_phase_receipt(snapshot, f.qualification_key))
        policy = SelectedRunEvidencePolicy(custody=custody, run_id="native-run", permissions=f.policy,
                                           native_lineage=verifier)
        judgments = {phase: f.runtime.judge(plan=context_plan, task=question, invocation_id="paired-native-" + phase)
            for phase in ("before", "after")}
        # Existing receipts are recovered; the passive callbacks cannot infer.
        for binding in f.runtime.bindings.values():
            binding.adapter.invoke = lambda *_: self.fail("passive fixture invoked inference")
        bridge.lineage = verifier
        def bind_actual_history(runtime, lineage):
            owner = copy(runtime.state_approval_verifier)
            owner.proofs = copy(owner.proofs)
            owner.proofs.custody = runtime.private
            runtime.state_approval_verifier = owner
            owned = copy(custody)
            owned._physical_custody = getattr(custody, "_physical_custody", custody)
            owned.connection, owned.registry, owned.objects = runtime.sources.connection, runtime.sources, runtime.objects
            owned.raw_custody = type(custody.raw_custody)(registry=runtime.sources, objects=runtime.objects)
            lineage.history_authority = SelectedRunEvidencePolicy(custody=owned, run_id="native-run",
                permissions=runtime.source_policy)
        bridge.read_hook = bind_actual_history
        class PhaseMeter(_native.FixtureMeter):
            def payload(self, request):
                judgment = judgments[request.phase]
                return {"schema": "fictional-native-meter-v1", "run_plan": request.plan.digest(),
                    "case_id": request.case_id, "phase": request.phase,
                    "invocation_id": judgment.execution.invocation.invocation_id,
                    "input_sha256": judgment.execution.invocation.input_sha256,
                    "output_sha256": hashlib.sha256(judgment.execution.result.output).hexdigest(),
                    "usage": vars(self.usage)}
        meter = PhaseMeter(SimpleNamespace())
        meter.usage = MeasuredUsage("fictional-feature", 5, 10, 5, 0)
        class Codec(_native.FixtureWorkerCodec):
            def encode_request(self, *, frozen, entry, request):
                return canonical_json_bytes({"invocation_id": entry.invocation_id,
                    "output_event": judgments[request.phase].execution.output_record.event.event_id,
                    "meter": base64.b64encode(meter.receipt(request)).decode(),
                    "question_sha256": hashlib.sha256(request.question).hexdigest(),
                    "context_sha256": hashlib.sha256(_context_bytes(request.context)).hexdigest(),
                    "frozen_arm_sha256": frozen.lineage_sha256})
        codec = Codec(SimpleNamespace())
        native = NativeArmAdapter(run_id="native-run", run_plan=plan, frozen=frozen, custody=custody,
            worker=worker, codec=codec, reads=reads, meter=meter, writer_guard=writer_guard)
        def traced_boundary(original, stage):
            async def traced(*args, **kwargs):
                try:
                    return await original(*args, **kwargs)
                except (Exception, asyncio.CancelledError) as error:
                    # Structural diagnostics only: no exception message, local
                    # values, request data, context, output or proof payloads.
                    frames = [{"file": frame.filename, "function": frame.name, "line": frame.lineno}
                              for frame in traceback.extract_tb(error.__traceback__)]
                    print(canonical_json_bytes({"native_fixture_stage": stage,
                        "exception_class": type(error).__name__, "traceback": frames}).decode(),
                        file=sys.stderr, flush=True)
                    raise
            return traced
        native.prepare = traced_boundary(native.prepare, "prepare")
        native.execute = traced_boundary(native.execute, "execute")
        async def exercise():
            try:
                return await run_paired(plan=plan, histories=histories, questions={"case": question},
                    adapters={"flora_full": native}, evidence_policy=policy)
            finally:
                await reads.aclose()
        run = asyncio.run(exercise())
        executions = native.execution_records
        native_attempts = [attempt for attempt in run.attempts if attempt.arm == "flora_full"]
        self.assertEqual([attempt.status for attempt in native_attempts], ["success"] * 2,
            [{"phase": attempt.phase, "status": attempt.status, "elapsed_ms": attempt.elapsed_ms}
             for attempt in native_attempts])
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
        private_reads = []
        def forbidden_private_read(event_id):
            private_reads.append(event_id)
            raise AssertionError("revoked native phase opened private decision bytes")
        custody.load_recorded = forbidden_private_read
        with self.assertRaises((ValueError, PermissionError)):
            custody.save_run(run_id="native-run", run=run, occurred_at=f.fabric._time(),
                             execution_records=executions, evidence_policy=policy)
        self.assertEqual(private_reads, [])


if __name__ == "__main__":
    unittest.main()
