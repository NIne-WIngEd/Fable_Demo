"""Native paired-arm orchestration around externally qualified producer ports.

Inference belongs to a terminable worker. Async selected-store read services,
the actual producer codec, phase/export adapter and independent meter must be
supplied; this module does not install an inference model or guess usage.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
import hashlib
from types import MappingProxyType
from typing import Mapping, Protocol

from cognitive_kernel.canonical import canonical_sha256, require_identifier, require_sha256
from cognitive_kernel.contracts import ProductHostScope

from ..comparison_run import (
    ArmExecutionFailure, ArmResult, ArmStopped, ExecutionRequest, MeasuredUsage,
    PairedRunPlan, PreparationRequest, _context_bytes,
)
from .comparison_custody import XTDBComparisonCustody
from .context import ContextPlan, LocalContext
from .experiment_runtime import JudgmentRun
from .judgment_lineage import VerifiedNativeJudgmentResult
from .native_worker import (
    NativeWorkerDispatchDenied, NativeWorkerFailure, NativeWorkerObservation,
    QualifiedNativeProcessWorker, OwnedPassiveReads,
)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest(value: str, name: str) -> None:
    if require_sha256(value, name) != value:
        raise ValueError(name + " must be canonical")


@dataclass(frozen=True)
class NativePhaseSnapshotBinding:
    """Predeclared immutable archive identity, without a run-digest cycle.

    The snapshot body itself contains the run-plan digest. Its content/event
    hashes therefore cannot also participate in that same digest. Selected
    custody independently authenticates those hashes on every route opening.
    """
    run_id: str
    snapshot_id: str
    arm: str

    def record(self) -> dict:
        for name in ("run_id", "snapshot_id"):
            value = getattr(self, name)
            if require_identifier(value, name) != value:
                raise ValueError("native phase snapshot identifiers must be canonical")
        if self.arm not in {"flora_full", "same_evidence_ablation"}:
            raise ValueError("native phase snapshot has an unknown arm")
        return {"schema": "flora-native-phase-snapshot-binding-v1", **vars(self)}


@dataclass(frozen=True)
class NativeInvocationEntry:
    case_id: str
    phase: str
    invocation_id: str
    context_plan: ContextPlan = field(repr=False)
    context_sha256: str
    phase_snapshot: NativePhaseSnapshotBinding | None = None

    def record(self) -> dict:
        for name in ("case_id", "invocation_id"):
            value = getattr(self, name)
            if require_identifier(value, name) != value:
                raise ValueError("native invocation identifiers must be canonical")
        if self.phase not in {"before", "after"} or self.context_plan.purpose != "personal_judgment":
            raise ValueError("native invocation needs the actual phase and personal-judgment context")
        self.context_plan.validate()
        _digest(self.context_sha256, "context_sha256")
        if self.phase_snapshot is not None:
            if not isinstance(self.phase_snapshot, NativePhaseSnapshotBinding):
                raise TypeError("native invocation requires a typed phase snapshot binding")
            self.phase_snapshot.record()
        return asdict(self)


@dataclass(frozen=True)
class FrozenNativeArmPlan:
    scope: ProductHostScope
    authority_namespace_id: str
    arm: str
    worker_manifest_sha256: str
    entries: tuple[NativeInvocationEntry, ...] = field(repr=False)

    def record(self) -> dict:
        self.scope.validate()
        if (self.arm not in {"flora_full", "same_evidence_ablation"}
                or require_identifier(self.authority_namespace_id, "authority_namespace_id") != self.authority_namespace_id
                or not self.entries
                or any(e.phase_snapshot is not None and e.phase_snapshot.arm != self.arm for e in self.entries)
                or len({(e.case_id, e.phase) for e in self.entries}) != len(self.entries)
                or len({e.invocation_id for e in self.entries}) != len(self.entries)):
            raise ValueError("native arm needs unique frozen per-case/phase invocation IDs")
        _digest(self.worker_manifest_sha256, "worker_manifest_sha256")
        return {"schema": "flora-frozen-native-arm-v1", "scope": self.scope.metadata_record(),
            "authority_namespace_id": self.authority_namespace_id, "arm": self.arm,
            "worker_manifest_sha256": self.worker_manifest_sha256,
            "entries": [e.record() for e in sorted(self.entries, key=lambda e: (e.case_id, e.phase))]}

    @property
    def lineage_sha256(self) -> str:
        # The outer run-plan digest includes this lineage. Keeping the run digest
        # out of this record avoids a circular hash.
        return canonical_sha256(self.record())

    def entry(self, case_id: str, phase: str) -> NativeInvocationEntry:
        candidates = [e for e in self.entries if (e.case_id, e.phase) == (case_id, phase)]
        if len(candidates) != 1:
            raise ValueError("native task has no unique frozen invocation")
        return candidates[0]


@dataclass(frozen=True)
class NativeWorkerCompletion:
    invocation_id: str
    worker_request_sha256: str
    qualified_output_event_id: str
    metering_receipt: bytes = field(repr=False)


class NativeWorkerCodec(Protocol):
    artifact_sha256: str
    def encode_request(self, *, frozen: FrozenNativeArmPlan, entry: NativeInvocationEntry,
                       request: ExecutionRequest) -> bytes: ...
    def decode_completion(self, output: bytes) -> NativeWorkerCompletion: ...


class QualifiedAsyncNativeReadServices(Protocol):
    """Actual selected runtime/lineage reads with externally qualified ownership.

    Producer implementation must call actual runtime context/recovery and actual
    NativeJudgmentLineageVerifier. Reads use fresh or exclusively owned bounded
    backend connections. Cancelled reads cannot later invoke inference or commit
    custody writes. There is deliberately no inline/to-thread inference default.
    """
    artifact_sha256: str
    configuration_sha256: str
    async def prepare_context(self, entry: NativeInvocationEntry) -> LocalContext: ...
    async def authorize_context(self, *, entry: NativeInvocationEntry,
                                request: PreparationRequest | ExecutionRequest,
                                context: LocalContext, arm: str) -> bool: ...
    async def recover_judgment(self, *, entry: NativeInvocationEntry,
                               request: ExecutionRequest) -> JudgmentRun: ...
    async def verify_native_result(self, *, entry: NativeInvocationEntry, request: ExecutionRequest,
                                   result: ArmResult) -> VerifiedNativeJudgmentResult: ...


@dataclass(frozen=True)
class VerifiedNativeUsage:
    usage: MeasuredUsage
    meter_artifact_sha256: str
    meter_configuration_sha256: str
    worker_observation_sha256: str
    worker_request_sha256: str
    invocation_id: str
    native_input_sha256: str
    native_output_sha256: str
    metering_receipt_sha256: str


class NativeUsageVerifier(Protocol):
    artifact_sha256: str
    configuration_sha256: str
    def verify_usage(self, *, request: ExecutionRequest, entry: NativeInvocationEntry,
                     observation: NativeWorkerObservation, completion: NativeWorkerCompletion,
                     judgment: JudgmentRun) -> VerifiedNativeUsage: ...


class NativeObservedTimeout(ArmStopped):
    """A timeout after the independent metering receipt was already verified."""
    def __init__(self, usage: MeasuredUsage):
        usage.validate()
        Exception.__init__(self, "timeout")
        self.status, self.usage = "timeout", usage


class NativeArmAdapter:
    """One frozen native arm; ablation needs the actual archived exclusion route.

    Registration follows awaited recovery, meter proof and fresh phase checks.
    Selected writes remain small synchronous custody calls with bounded database
    driver timeouts; no detached cancelled read task owns the write continuation.
    Interrupted registration can leave provisional receipts, never an accepted
    execution record. A later accepted run requires independent save_run checks.
    """
    def __init__(self, *, run_id: str, run_plan: PairedRunPlan, frozen: FrozenNativeArmPlan,
                 custody: XTDBComparisonCustody, worker: QualifiedNativeProcessWorker | None,
                 codec: NativeWorkerCodec | None, reads: QualifiedAsyncNativeReadServices | None,
                 meter: NativeUsageVerifier | None):
        if require_identifier(run_id, "run_id") != run_id:
            raise ValueError("native adapter needs a canonical run ID")
        run_plan.validate()
        frozen.record()
        if (frozen.scope != custody.scope or frozen.authority_namespace_id != custody.authority_namespace_id
                or any(run_plan.binding_for(e.case_id, e.phase, frozen.arm).lineage_sha256
                       != frozen.lineage_sha256 for e in frozen.entries)
                or {(e.case_id, e.phase) for e in frozen.entries}
                != {(c.case_id, p) for c in run_plan.protocol.cases for p in ("before", "after")}
                or any(c.host_id != frozen.scope.host_instance_id for c in run_plan.protocol.cases)):
            raise ValueError("native arm differs from exact frozen host/run lineage")
        self.run_id, self.run_plan, self.frozen, self.custody = run_id, run_plan, frozen, custody
        self.worker, self.codec, self.reads, self.meter = worker, codec, reads, meter
        self._run_sha256, self._lineage_sha256 = run_plan.digest(), frozen.lineage_sha256
        self._deadlines: dict[tuple[str, str], float] = {}
        self._executions: dict[tuple[str, str, str], tuple[ExecutionRequest, ArmResult]] = {}
        self._in_flight: set[tuple[str, str]] = set()
        self._attempted: set[tuple[str, str]] = set()
        self._observed_usage: dict[tuple[str, str], MeasuredUsage] = {}
        self._observed_context: dict[tuple[str, str], str] = {}
        self._passive_reads = OwnedPassiveReads()

    @property
    def execution_records(self) -> Mapping[tuple[str, str, str], tuple[ExecutionRequest, ArmResult]]:
        return MappingProxyType(dict(self._executions))

    @property
    def observed_usage(self) -> Mapping[tuple[str, str], MeasuredUsage]:
        # External runner cancellation may occur just before our own deadline.
        # Known usage remains available for an explicit measured stop receipt.
        return MappingProxyType(dict(self._observed_usage))

    def measured_stop_usage(self, *, case_id: str, phase: str, plan_sha256: str,
                            context_sha256: str | None) -> MeasuredUsage | None:
        """Failure-only runner bridge for a meter proof completed before cancellation."""
        key = (case_id, phase)
        if (plan_sha256 != self._run_sha256 or context_sha256 is None
                or self._observed_context.get(key) != context_sha256):
            return None
        return self._observed_usage.get(key)

    def _available(self) -> None:
        if self.worker is None or self.codec is None or self.reads is None or self.meter is None:
            raise ArmStopped("unavailable")
        if self.frozen.arm == "same_evidence_ablation":
            from .native_reads import SelectedNativeReadServices
            if (not isinstance(self.reads, SelectedNativeReadServices)
                    or self.reads.manifest.allow_current_fixture_route
                    or any(entry.phase_snapshot is None
                           or entry.phase_snapshot.arm != "same_evidence_ablation" for entry in self.frozen.entries)):
                raise ArmStopped("unavailable")
        manifest = self.worker.manifest
        if (manifest.scope != self.frozen.scope or manifest.authority_namespace_id != self.frozen.authority_namespace_id
                or manifest.manifest_sha256 != self.frozen.worker_manifest_sha256
                or self.codec.artifact_sha256 != manifest.codec_artifact_sha256
                or self.reads.artifact_sha256 != manifest.read_service_artifact_sha256
                or self.reads.configuration_sha256 != manifest.read_service_configuration_sha256
                or self.meter.artifact_sha256 != manifest.meter_artifact_sha256
                or self.meter.configuration_sha256 != manifest.meter_configuration_sha256):
            raise ValueError("native ports differ from independently qualified worker manifest")

    def _check(self, request: PreparationRequest | ExecutionRequest, context: LocalContext | None = None):
        self._available()
        entry = self.frozen.entry(request.case_id, request.phase)
        if (self.run_plan.digest() != self._run_sha256 or request.plan.digest() != self._run_sha256
                or self.frozen.lineage_sha256 != self._lineage_sha256
                or _sha(request.question) != self.run_plan.question_sha256_by_case[request.case_id]):
            raise ValueError("native task changed frozen plan/question lineage")
        if isinstance(request, PreparationRequest):
            case = next(c for c in self.run_plan.protocol.cases if c.case_id == request.case_id)
            if (request.history.scope != self.frozen.scope
                    or request.history.digest() != getattr(case, request.phase + "_history_sha256")):
                raise ValueError("native preparation changed frozen host/history")
        if isinstance(request, ExecutionRequest):
            case = next(c for c in self.run_plan.protocol.cases if c.case_id == request.case_id)
            if (request.scope != self.frozen.scope
                    or request.binding != self.run_plan.binding_for(request.case_id, request.phase, self.frozen.arm)
                    or request.authorized_history_sha256 != getattr(case, request.phase + "_history_sha256")):
                raise ValueError("native execution changed frozen host/binding/history")
        if context is not None:
            if (not isinstance(context, LocalContext) or context.plan != entry.context_plan
                    or _sha(_context_bytes(context)) != entry.context_sha256
                    or len(_context_bytes(context)) > self.run_plan.context_byte_budget):
                raise ValueError("native context differs from its exact frozen input")
        return entry

    def _deadline(self, key: tuple[str, str]) -> float:
        deadline = self._deadlines.get(key)
        if deadline is None:
            raise ValueError("native execution has no prepared deadline")
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError
        return deadline

    async def _authorize(self, entry, request, context, deadline):
        self._check(request, context)
        async with asyncio.timeout_at(deadline):
            allowed = await self.reads.authorize_context(entry=entry, request=request, context=context, arm=self.frozen.arm)
        if allowed is not True:
            raise ArmStopped("refused")
        self._check(request, context)
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError

    async def prepare(self, request: PreparationRequest) -> LocalContext:
        entry = self._check(request)
        key = (entry.case_id, entry.phase)
        if key in self._in_flight or key in self._executions or key in self._deadlines:
            raise ValueError("native invocation cannot be prepared twice")
        deadline = asyncio.get_running_loop().time() + self.run_plan.protocol.wall_time_budget_ms / 1000
        self._deadlines[key] = deadline
        async with asyncio.timeout_at(deadline):
            await self._passive_reads.run(self.worker.verify_identity)
            context = await self.reads.prepare_context(entry)
            self._check(request, context)
            await self._authorize(entry, request, context, deadline)
            return context

    async def execute(self, request: ExecutionRequest) -> ArmResult:
        entry = self._check(request, request.context)
        key = (entry.case_id, entry.phase)
        if key in self._in_flight or key in self._attempted:
            raise ValueError("native invocation already executing or accepted")
        deadline = self._deadline(key)
        self._in_flight.add(key)
        # One frozen invocation includes its encoder/preflight. Cancellation
        # cannot reopen that same task while its passive callback still runs.
        self._attempted.add(key)
        usage = None
        try:
            await self._authorize(entry, request, request.context, deadline)
            async with asyncio.timeout_at(deadline):
                body = await self._passive_reads.run(self.codec.encode_request,
                    frozen=self.frozen, entry=entry, request=request)
            async def authorize_dispatch():
                try:
                    await self._authorize(entry, request, request.context, deadline)
                except ArmStopped as exc:
                    if exc.status == "refused":
                        raise NativeWorkerDispatchDenied("refused") from None
                    raise
            observation = await self.worker.run(request=body, deadline=deadline,
                authorize_dispatch=authorize_dispatch)
            await self._authorize(entry, request, request.context, deadline)
            async with asyncio.timeout_at(deadline):
                completion = await self._passive_reads.run(self.codec.decode_completion,
                    observation.output)
            if (not isinstance(completion, NativeWorkerCompletion) or completion.invocation_id != entry.invocation_id
                    or completion.worker_request_sha256 != observation.request_sha256
                    or not isinstance(completion.metering_receipt, bytes) or not completion.metering_receipt):
                raise ValueError("worker completion lost its exact invocation/request/meter receipt")
            async with asyncio.timeout_at(deadline):
                actual = await self.reads.recover_judgment(entry=entry, request=request)
            if (not isinstance(actual, JudgmentRun) or actual.context.receipt_record() != request.context.receipt_record()
                    or actual.execution.invocation.invocation_id != entry.invocation_id
                    or actual.execution.invocation.operation != "native_judgment"
                    or actual.execution.output_record.event.event_id != completion.qualified_output_event_id
                    or actual.execution.invocation.scope != request.scope
                    or actual.execution.invocation.authority_namespace_id != self.frozen.authority_namespace_id
                    or actual.execution.invocation.artifact.checkpoint_sha256 != request.binding.model_artifact_sha256):
                raise ValueError("worker completion differs from actual recovered native execution")
            async with asyncio.timeout_at(deadline):
                verified = await self._passive_reads.run(self.meter.verify_usage, request=request, entry=entry,
                    observation=observation, completion=completion, judgment=actual)
            if (not isinstance(verified, VerifiedNativeUsage)
                    or verified.meter_artifact_sha256 != self.meter.artifact_sha256
                    or verified.meter_configuration_sha256 != self.meter.configuration_sha256
                    or verified.worker_observation_sha256 != observation.observation_sha256
                    or verified.worker_request_sha256 != observation.request_sha256
                    or verified.invocation_id != entry.invocation_id
                    or verified.native_input_sha256 != actual.execution.invocation.input_sha256
                    or verified.native_output_sha256 != _sha(actual.execution.result.output)
                    or verified.metering_receipt_sha256 != _sha(completion.metering_receipt)):
                raise ValueError("native metering proof does not bind exact worker/runtime execution")
            verified.usage.validate()
            if verified.usage.feature_engine_id != request.plan.protocol.feature_engine_id:
                raise ValueError("native metering has the wrong frozen feature engine")
            usage = verified.usage
            self._observed_usage[key] = usage
            self._observed_context[key] = _sha(_context_bytes(request.context))
            result = ArmResult(actual.execution.result.output, actual.delivery, actual.decision, usage)
            async with asyncio.timeout_at(deadline):
                proof = await self.reads.verify_native_result(entry=entry, request=request, result=result)
            if (not isinstance(proof, VerifiedNativeJudgmentResult) or proof.invocation_id != entry.invocation_id
                    or proof.qualified_output != actual.execution.output_record
                    or proof.delivery_event_id != actual.delivery.event.event_id
                    or proof.decision_event_id != actual.decision.event.event_id
                    or proof.context_lineage.scope != request.scope
                    or proof.context_lineage.authority_namespace_id != self.frozen.authority_namespace_id
                    or proof.context_lineage.case_id != request.case_id or proof.context_lineage.phase != request.phase
                    or proof.context_lineage.authorized_history_sha256 != request.authorized_history_sha256
                    or proof.context_lineage.context_receipt_sha256 != request.context.receipt_record()["receipt_sha256"]):
                raise ValueError("native result has no exact independently recovered phase proof")
            # No detached read task owns these writes. Each synchronous selected
            # boundary follows an awaited fresh permission/deadline check.
            for recorded in (actual.delivery, actual.execution.output_record, actual.decision):
                await self._authorize(entry, request, request.context, deadline)
                self.custody.register_recorded(recorded)
            await self._authorize(entry, request, request.context, deadline)
            self.custody.register_context(run_id=self.run_id, context=actual.context, delivery=actual.delivery,
                                         occurred_at=actual.delivery.event.occurred_at)
            await self._authorize(entry, request, request.context, deadline)
            self._executions[(entry.case_id, entry.phase, self.frozen.arm)] = (request, result)
            return result
        except NativeWorkerFailure as exc:
            if exc.receipt.reason == "timeout":
                raise TimeoutError from None
            if exc.receipt.reason == "dispatch_refused":
                raise ArmStopped("refused") from None
            raise
        except ArmStopped as exc:
            if usage is not None:
                raise ArmStopped(exc.status, usage) from None
            raise
        except TimeoutError:
            if usage is not None:
                raise NativeObservedTimeout(usage) from None
            raise
        except (ValueError, PermissionError):
            if usage is not None:
                raise ArmExecutionFailure("invalid_result", usage) from None
            raise
        except Exception:
            if usage is not None:
                raise ArmExecutionFailure("failed", usage) from None
            raise
        finally:
            self._in_flight.discard(key)
