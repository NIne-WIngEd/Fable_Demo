"""Native adapter proof mechanics with supplied fictional fixture outputs.

No trained model, genuine meter counters, actual deployment factory or backend
qualification is represented here. Actual selected classes validate the fixture
receipts; the separate physical-backend gates qualify physical store behavior.
"""
import base64
from copy import copy
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cognitive_kernel.canonical import canonical_json_bytes
from flora.comparison_run import ArmBinding, MeasuredUsage, PairedRunPlan, _context_bytes
from flora.evaluation_protocol import ARMS, EvaluationCase, EvaluationProtocol
from flora.selected.artifact_registry import XTDBModelArtifactRegistry
from flora.selected.experiment_runtime import FloRAExperimentRuntime
from flora.selected.formation_admission import XTDBFormationClaimAdmission
from flora.selected.governed_development import XTDBGovernedPersonalDevelopment
from flora.selected.judgment_context import RegisteredJudgmentContextPolicy
from flora.selected.native_arm import (
    FrozenNativeArmPlan, NativeArmAdapter, NativeInvocationEntry, NativeWorkerCompletion, VerifiedNativeUsage,
)
from flora.selected.native_reads import (
    InitializedNativeSessionFactory, NativeReadManifest, NativeReadSession, SelectedNativeReadServices,
)
from flora.selected.personal_artifact_custody import DurablePersonalReferences, XTDBPersonalArtifactCustody


def sha(value):
    return hashlib.sha256(value).hexdigest()


def fixture_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parent / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


lineage_fixture = fixture_module("flora_native_runtime_lineage_fixture", "test_selected_judgment_lineage.py")
worker_fixture = fixture_module("flora_native_process_fixture", "test_native_worker.py")


class FixtureRawReadConnection:
    def __init__(self, owner):
        self.owner, self.adapters, self.closed = owner, owner.f.connection.adapters, False
    def execute(self, sql, parameters):
        return self.owner.f.connection.execute(sql, parameters)
    def close(self):
        self.closed = True
        self.owner.closed_connections.append(self)


class FixtureCustody:
    """Records registration order only; real custody is separately qualified."""
    def __init__(self, scope, namespace):
        self.scope, self.authority_namespace_id = scope, namespace
        self.registrations, self.contexts = [], []
    def register_recorded(self, value):
        self.registrations.append(value)
    def register_context(self, **kwargs):
        self.contexts.append(kwargs)


class FixtureWorkerCodec:
    artifact_sha256 = "1" * 64
    def __init__(self, fixture):
        self.fixture, self.change_completion = fixture, False
        self.delay_encode = 0
    def encode_request(self, *, frozen, entry, request):
        if self.delay_encode:
            import time
            time.sleep(self.delay_encode)
        return canonical_json_bytes({"invocation_id": entry.invocation_id,
            "output_event": self.fixture.judgment.execution.output_record.event.event_id,
            "meter": base64.b64encode(self.fixture.meter.receipt(request)).decode(),
            "question_sha256": sha(request.question), "context_sha256": sha(_context_bytes(request.context)),
            "frozen_arm_sha256": frozen.lineage_sha256})
    def decode_completion(self, output):
        body = json.loads(output)
        return NativeWorkerCompletion("changed-invocation" if self.change_completion else body["invocation_id"],
            body["worker_request_sha256"], body["qualified_output_event_id"], base64.b64decode(body["meter"], validate=True))


class FixtureMeter:
    artifact_sha256, configuration_sha256 = "4" * 64, "5" * 64
    def __init__(self, fixture):
        self.fixture, self.key = fixture, Ed25519PrivateKey.generate()
        self.callback, self.invalid = None, False
        # Deliberately supplied fictional values. They are not actual model work.
        self.usage = MeasuredUsage("fixture-feature-engine", 4, 8, 3, 0)
    def payload(self, request):
        judgment = self.fixture.judgment
        return {"schema": "fictional-native-meter-v1", "run_plan": request.plan.digest(),
            "case_id": request.case_id, "phase": request.phase,
            "invocation_id": judgment.execution.invocation.invocation_id,
            "input_sha256": judgment.execution.invocation.input_sha256,
            "output_sha256": sha(judgment.execution.result.output), "usage": vars(self.usage)}
    def receipt(self, request):
        payload = self.payload(request)
        return canonical_json_bytes({"payload": payload,
            "signature": base64.b64encode(self.key.sign(canonical_json_bytes(payload))).decode()})
    def verify_usage(self, *, request, entry, observation, completion, judgment):
        body = json.loads(completion.metering_receipt)
        self.key.public_key().verify(base64.b64decode(body["signature"], validate=True), canonical_json_bytes(body["payload"]))
        if body["payload"] != self.payload(request) or observation.output_sha256 != sha(observation.output):
            raise ValueError("fictional metering receipt changed")
        if self.callback:
            self.callback()
        return VerifiedNativeUsage(self.usage, self.artifact_sha256, self.configuration_sha256,
            "f" * 64 if self.invalid else observation.observation_sha256, observation.request_sha256,
            entry.invocation_id, judgment.execution.invocation.input_sha256,
            sha(judgment.execution.result.output), sha(completion.metering_receipt))


class NativeContractFixture:
    def __init__(self, directory):
        self.test = lineage_fixture.SelectedJudgmentLineageTest()
        self.test.setUp()
        self.f, self.runtime = self.test.fixture, self.test.runtime
        self.scope, self.namespace = self.f.scope, self.f.namespace
        self.histories, self.context_plan = self.test.histories, self.test.plan
        self.context = self.runtime._context(self.context_plan)
        self.question = b"fixture common question"
        self.opened_connections, self.closed_connections = [], []
        self.read_hook, self.binder_hook = None, None
        # Component authority mechanics are not a response-latency benchmark.
        # Allow concurrent CI CPU contention without changing the real pilot.
        self.read_manifest = NativeReadManifest(self.scope, self.namespace, "2" * 64, "3" * 64, 1, 15000, 1000,
                                               allow_current_fixture_route=True)
        self.factory = InitializedNativeSessionFactory(artifact_sha256="2" * 64, configuration_sha256="3" * 64,
            connection_opener=self._open, bind_initialized=self._bind, backend_read_timeout_ms=1000)
        self.reads = SelectedNativeReadServices(manifest=self.read_manifest, factory=self.factory)
        self.worker = worker_fixture.worker_fixture(directory,
            "import sys,json,hashlib\nraw=sys.stdin.buffer.read()\nr=json.loads(raw)\n"
            "sys.stdout.write(json.dumps({'invocation_id':r['invocation_id'],"
            "'worker_request_sha256':hashlib.sha256(raw).hexdigest(),"
            "'qualified_output_event_id':r['output_event'],'meter':r['meter']},sort_keys=True,separators=(',',':')))\n",
            scope=self.scope, namespace=self.namespace)
        self.worker.manifest = replace(self.worker.manifest,
            read_service_artifact_sha256=self.reads.artifact_sha256,
            read_service_configuration_sha256=self.reads.configuration_sha256)
        key = Ed25519PrivateKey.generate()
        payload = {"schema": "fictional-worker-qualification-v1", "manifest": self.worker.manifest.manifest_sha256}
        self.worker.qualification_receipt = canonical_json_bytes({"payload": payload,
            "signature": base64.b64encode(key.sign(canonical_json_bytes(payload))).decode()})
        self.worker.verifier = worker_fixture.FictionalWorkerQualifier(key.public_key())
        self.frozen = FrozenNativeArmPlan(self.scope, self.namespace, "flora_full", self.worker.manifest.manifest_sha256,
            tuple(NativeInvocationEntry("case-one", phase, "native-fixture-" + phase,
                self.context_plan, sha(_context_bytes(self.context))) for phase in ("before", "after")))
        case = EvaluationCase("case-one", self.scope.host_instance_id, "relevant_correction", "heldout",
            self.histories[("case-one", "before")].digest(), self.histories[("case-one", "after")].digest(),
            "a" * 64, self.histories[("case-one", "after")].event_ids[-1])
        protocol = EvaluationProtocol("fixture-native-protocol", "b" * 64, "2026-09-29T00:00:00Z",
            "fixture-feature-engine", 32, 15000, (case,), "c" * 64, "d" * 64, "e" * 64, "f" * 64,
            ("fixture-transfer-host",))
        bindings = {arm: ArmBinding("fictional-producer-" + str(i), str(i + 1) * 64,
            str(i + 4) * 64, "fictional-mechanism") for i, arm in enumerate(sorted(ARMS))}
        bindings["flora_full"] = ArmBinding("fictional-supplied-output-adapter",
            self.f.manifests["personality_judgment"].checkpoint_sha256, self.frozen.lineage_sha256, "fictional-mechanism")
        self.plan = PairedRunPlan(protocol, bindings, 32, 10000, 0, {"case-one": sha(self.question)})
        self.lineage = self.test._verifier(run_plan_sha256=self.plan.digest(),
            invocation_id_for=lambda request, result: self.frozen.entry(request.case_id, request.phase).invocation_id)
        self.judgment = self.runtime.judge(plan=self.context_plan, task=self.question, invocation_id="native-fixture-after")
        self.context = self.judgment.context
        # All later paths must recover supplied receipts, never call inference.
        for binding in self.runtime.bindings.values():
            binding.adapter.invoke = lambda *_: (_ for _ in ()).throw(AssertionError("reader invoked inference"))
        self.codec, self.meter = FixtureWorkerCodec(self), FixtureMeter(self)
        self.custody = FixtureCustody(self.scope, self.namespace)
        self.adapter = self.new_adapter()

    def new_adapter(self, **changes):
        inputs = dict(run_id="native-fixture-run", run_plan=self.plan, frozen=self.frozen,
            custody=self.custody, worker=self.worker, codec=self.codec, reads=self.reads, meter=self.meter,
            allow_unregistered_fixture_run=True)
        inputs.update(changes)
        return NativeArmAdapter(**inputs)

    def _open(self, *, read_timeout_ms):
        if read_timeout_ms != 1000:
            raise ValueError("fixture read timeout changed")
        connection = FixtureRawReadConnection(self)
        self.opened_connections.append(connection)
        return connection

    def _bind(self, connection):
        if self.binder_hook:
            self.binder_hook(connection)
        def plane(value):
            cloned = copy(value)
            cloned.connection = connection
            return cloned
        sources, claims = plane(self.runtime.sources), plane(self.runtime.claims)
        candidates, artifacts = plane(self.runtime.candidates), plane(self.runtime.artifacts)
        policy = plane(self.runtime.source_policy)
        policy.registry = sources
        state = XTDBGovernedPersonalDevelopment(scope=self.scope, authority_namespace_id=self.namespace,
            connection=connection, registry=sources, policy=policy)
        custody = XTDBPersonalArtifactCustody(scope=self.scope, authority_namespace_id=self.namespace, connection=connection)
        references = DurablePersonalReferences(custody=custody, originals=sources)
        context_policy = RegisteredJudgmentContextPolicy(claims=claims, state=state, log=self.runtime.log,
            registry=sources, permissions=policy)
        runtime = FloRAExperimentRuntime(artifacts=artifacts, bindings=self.runtime.bindings, claims=claims, sources=sources,
            source_policy=policy, candidates=candidates, admission=XTDBFormationClaimAdmission(authority=claims, candidates=candidates),
            state=state, log=self.runtime.log, objects=self.runtime.objects, references=references,
            context_policy=context_policy, state_approval_verifier=self.runtime.state_approval_verifier, clock=self.runtime.clock)
        lineage = copy(self.lineage)
        lineage.runtime = runtime
        if self.read_hook:
            self.read_hook(runtime, lineage)
        return NativeReadSession(runtime, lineage, (connection,))

    async def close(self):
        await self.reads.aclose()
        self.test.doCleanups()
