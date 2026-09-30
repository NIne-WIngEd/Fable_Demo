"""Failure-inclusive paired execution and blinded review, without model stand-ins.

Adapters own selected-stack context preparation and real inference. A separately
trusted evidence policy authorizes original sources and verifies recorded events.
This runner checks observable contracts; it does not certify judgment quality.
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
import hashlib
import inspect
import json
import math
import random
import secrets
import time
from typing import Mapping, Protocol

from cognitive_kernel.canonical import require_sha256
from cognitive_kernel.contracts import ProductHostScope
from cognitive_kernel.experience import ExperienceEvent

from .evaluation_protocol import ARMS, PHASES, EvaluationProtocol
from .selected.context import LocalContext
from .selected.decision_outcome import RecordedEvent


def _bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _integer(value: int, label: str, *, positive: bool = False) -> None:
    if (isinstance(value, bool) or not isinstance(value, int)
            or value < (1 if positive else 0)):
        raise ValueError(f"{label} must be a {'positive' if positive else 'nonnegative'} integer")


@dataclass(frozen=True)
class SourceMaterial:
    event: ExperienceEvent
    plaintext: bytes = field(repr=False)

    def record(self) -> dict:
        self.event.validate()
        if (not isinstance(self.plaintext, bytes)
                or _sha(self.plaintext) != self.event.content_digest):
            raise ValueError("original source content differs from its Experience event")
        return {"event": self.event.metadata_record(),
                "plaintext_base64": base64.b64encode(self.plaintext).decode("ascii")}


@dataclass(frozen=True)
class HistorySnapshot:
    scope: ProductHostScope
    sources: tuple[SourceMaterial, ...] = field(repr=False)

    def content(self) -> bytes:
        self.scope.validate()
        if not self.sources or len(set(self.event_ids)) != len(self.sources):
            raise ValueError("history needs unique original source events")
        if any(source.event.scope != self.scope for source in self.sources):
            raise ValueError("original history crosses host scope")
        return _bytes({"schema": "flora-authorized-history-v1",
                       "scope": self.scope.metadata_record(),
                       "sources": [source.record() for source in self.sources]})

    @property
    def event_ids(self) -> tuple[str, ...]:
        return tuple(source.event.event_id for source in self.sources)

    def digest(self) -> str:
        return _sha(self.content())


class RunEvidencePolicy(Protocol):
    """Trusted local authority; never supplied by an inference result."""

    def authorize_history(self, *, case_id: str, phase: str,
                          history: HistorySnapshot) -> bool: ...
    def verify_recorded(self, recorded: RecordedEvent) -> bool: ...


@dataclass(frozen=True)
class ArmBinding:
    producer_component: str
    model_artifact_sha256: str
    lineage_sha256: str
    update_mechanism: str

    def validate(self) -> None:
        if not self.producer_component or not self.update_mechanism:
            raise ValueError("arm needs a producer and explicit update mechanism")
        require_sha256(self.model_artifact_sha256, "model artifact")
        require_sha256(self.lineage_sha256, "arm lineage")


@dataclass(frozen=True)
class PairedRunPlan:
    protocol: EvaluationProtocol
    arm_bindings: Mapping[str, ArmBinding]
    context_token_budget: int
    context_byte_budget: int
    feature_call_budget: int
    question_sha256_by_case: Mapping[str, str]
    evidence_kind: str = "contract_fixture"
    phase_bindings: Mapping[tuple[str, str, str], ArmBinding] | None = None
    preregistration_sha256: str | None = None

    def validate(self) -> None:
        self.protocol.validate()
        if set(self.arm_bindings) != ARMS:
            raise ValueError("plan needs exactly the three frozen arms")
        for binding in self.arm_bindings.values():
            if not isinstance(binding, ArmBinding):
                raise ValueError("invalid arm binding")
            binding.validate()
        for label in ("context_token_budget", "context_byte_budget"):
            _integer(getattr(self, label), label, positive=True)
        _integer(self.feature_call_budget, "feature_call_budget")
        if set(self.question_sha256_by_case) != {case.case_id for case in self.protocol.cases}:
            raise ValueError("plan needs independently frozen question hashes for every case")
        for question_sha256 in self.question_sha256_by_case.values():
            require_sha256(question_sha256, "question_sha256")
        if self.evidence_kind not in {"contract_fixture", "synthetic", "consenting_real_host"}:
            raise ValueError("unknown evidence kind")
        if self.phase_bindings is not None:
            expected = {(c.case_id, phase, arm) for c in self.protocol.cases for phase in PHASES for arm in ARMS}
            if set(self.phase_bindings) != expected:
                raise ValueError("phase bindings require the complete exact case/phase/arm matrix")
            for binding in self.phase_bindings.values():
                if not isinstance(binding, ArmBinding):
                    raise ValueError("invalid phase arm binding")
                binding.validate()
        if self.preregistration_sha256 is not None:
            require_sha256(self.preregistration_sha256, "preregistration_sha256")
            if self.phase_bindings is None:
                raise ValueError("preregistered final plans require complete observed phase bindings")

    def binding_for(self, case_id: str, phase: str, arm: str) -> ArmBinding:
        if (phase not in PHASES or arm not in ARMS
                or case_id not in {c.case_id for c in self.protocol.cases}):
            raise ValueError("unknown binding task")
        return self.arm_bindings[arm] if self.phase_bindings is None else self.phase_bindings[(case_id, phase, arm)]

    def phase_binding_record(self) -> list[dict]:
        return [{"case_id": case, "phase": phase, "arm": arm, "binding": vars(binding)}
                for (case, phase, arm), binding in sorted((self.phase_bindings or {}).items())]

    def digest(self) -> str:
        self.validate()
        material = {"schema": "flora-paired-run-plan-v1",
                            "protocol": self.protocol.record(),
                            "bindings": {arm: vars(binding) for arm, binding
                                         in self.arm_bindings.items()},
                            "context_token_budget": self.context_token_budget,
                            "context_byte_budget": self.context_byte_budget,
                            "feature_call_budget": self.feature_call_budget,
                            "question_sha256_by_case": dict(self.question_sha256_by_case),
                            "evidence_kind": self.evidence_kind}
        if self.phase_bindings is not None:
            material["schema"] = "flora-paired-run-plan-v2"
            material["phase_bindings"] = self.phase_binding_record()
        if self.preregistration_sha256 is not None:
            material["schema"] = "flora-paired-run-plan-v3"
            material["preregistration_sha256"] = self.preregistration_sha256
        return _sha(_bytes(material))


@dataclass(frozen=True)
class MeasuredUsage:
    """Cumulative observed usage for preparation plus execution, not estimates."""

    feature_engine_id: str
    context_tokens: int
    input_tokens: int
    output_tokens: int
    feature_calls: int
    cost_microunits: int | None = None
    currency: str | None = None

    def validate(self) -> None:
        if not self.feature_engine_id:
            raise ValueError("usage needs an engine identity")
        for label in ("context_tokens", "input_tokens", "output_tokens", "feature_calls"):
            _integer(getattr(self, label), label)
        if (self.cost_microunits is None) != (self.currency is None):
            raise ValueError("cost and currency must both be known or unavailable")
        if self.cost_microunits is not None:
            _integer(self.cost_microunits, "cost_microunits")
            if (not isinstance(self.currency, str) or len(self.currency) != 3
                    or not self.currency.isascii() or not self.currency.isupper()
                    or not self.currency.isalpha()):
                raise ValueError("known cost needs a three-letter currency code")


@dataclass(frozen=True)
class PreparationRequest:
    case_id: str
    phase: str
    question: bytes = field(repr=False)
    history: HistorySnapshot = field(repr=False)
    plan: PairedRunPlan = field(repr=False)
    authenticated_history: object | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class ExecutionRequest:
    case_id: str
    phase: str
    question: bytes = field(repr=False)
    scope: ProductHostScope
    authorized_history_sha256: str
    authorized_event_ids: tuple[str, ...]
    context: LocalContext = field(repr=False)
    binding: ArmBinding
    plan: PairedRunPlan = field(repr=False)
    authenticated_history: object | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class ArmResult:
    output: bytes = field(repr=False)
    delivery: RecordedEvent = field(repr=False)
    decision: RecordedEvent = field(repr=False)
    usage: MeasuredUsage


class ArmAdapter(Protocol):
    async def prepare(self, request: PreparationRequest) -> LocalContext: ...
    async def execute(self, request: ExecutionRequest) -> ArmResult: ...


class ArmStopped(Exception):
    """Expected stop without exposing a private provider message in receipts."""

    def __init__(self, status: str, usage: MeasuredUsage | None = None):
        if status not in {"refused", "unavailable"}:
            raise ValueError("expected stops are refused or unavailable")
        super().__init__(status)
        self.status = status
        self.usage = usage


class ArmExecutionFailure(ArmStopped):
    """A rejected/failed execution with independently verified observed usage.

    Adapters attach usage only after their trusted metering proof succeeds.
    Exception detail never becomes a receipt or a displayed provider message.
    """
    def __init__(self, status: str, usage: MeasuredUsage):
        if status not in {"invalid_result", "failed"}:
            raise ValueError("observed failures must be invalid_result or failed")
        usage.validate()
        Exception.__init__(self, status)
        self.status, self.usage = status, usage


@dataclass(frozen=True)
class RunAttempt:
    case_id: str
    host_id: str
    arm: str
    phase: str
    plan_sha256: str
    authorized_history_sha256: str
    authorized_event_ids: tuple[str, ...]
    common_input_sha256: str
    context_sha256: str | None
    status: str
    elapsed_ms: int
    usage: MeasuredUsage | None
    output_sha256: str | None
    decision_event_id: str | None
    lineage_sha256: str
    output: bytes | None = field(default=None, repr=False)

    def receipt(self) -> dict:
        # Private lineage metadata; do not attach to a blinded review pack.
        return {key: value for key, value in vars(self).items() if key != "output"} | {
            "usage": vars(self.usage) if self.usage is not None else None,
            "schema": "flora-run-attempt-v1",
        }


@dataclass(frozen=True)
class PairedRun:
    plan: PairedRunPlan = field(repr=False)
    attempts: tuple[RunAttempt, ...]
    questions: Mapping[str, bytes] = field(repr=False)


def _context_bytes(context: LocalContext) -> bytes:
    return _bytes({"receipt": context.receipt_record(), "content": [
        base64.b64encode(item.content).decode("ascii") for item in context.items]})


def _authorize_context(*, policy: RunEvidencePolicy, case_id: str, phase: str,
                       history: HistorySnapshot, context: LocalContext, arm: str,
                       authenticated_history=None, plan=None, question=None) -> None:
    if not isinstance(context, LocalContext):
        raise ValueError("prepared context is not a selected context")
    originals_only = set(context.source_event_ids).issubset(history.event_ids)
    # Internal approvals belong to native authority, never shared user history.
    if arm == "general_model_memory" and not originals_only:
        raise ValueError("baseline context exceeds original phase evidence")
    authorize = getattr(policy, "authorize_context", None)
    if callable(authorize):
        extra = {} if authenticated_history is None else dict(
            authenticated_history=authenticated_history, plan=plan, question=question)
        if authorize(case_id=case_id, phase=phase, history=history, context=context, arm=arm, **extra) is not True:
            raise PermissionError("prepared context lacks current independent phase lineage")
    elif not originals_only:
        raise ValueError("internal native context requires independent phase lineage")


def _validate_result(result: ArmResult, request: ExecutionRequest,
                     policy: RunEvidencePolicy, *, arm: str = "general_model_memory") -> None:
    if not isinstance(result.usage, MeasuredUsage):
        raise ValueError("execution needs observed usage metadata")
    result.usage.validate()
    if result.usage.feature_engine_id != request.plan.protocol.feature_engine_id:
        raise ValueError("feature engine differs from frozen protocol")
    if not isinstance(result.output, bytes) or not result.output:
        raise ValueError("successful execution needs actual output")
    for recorded in (result.delivery, result.decision):
        if not isinstance(recorded, RecordedEvent):
            raise ValueError("execution needs selected recorded-event references")
        recorded.event.validate()
        if (recorded.event.scope != request.scope or recorded.raw.scope != request.scope
                or recorded.event.content_digest != recorded.raw.plaintext_sha256
                or not policy.verify_recorded(recorded)):
            raise ValueError("execution lacks independently verified selected event evidence")
    delivery = result.delivery.event
    decision = result.decision.event
    context_material = _bytes(request.context.receipt_record())
    if (delivery.event_type != "context_delivery"
            or delivery.content_digest != _sha(context_material)
            or tuple(delivery.parent_event_ids) != request.context.source_event_ids):
        raise ValueError("delivery is not the exact selected context")
    consumed = (delivery.event_id,) + request.context.source_event_ids
    if (tuple(decision.parent_event_ids) != consumed
            or (arm in {"flora_full", "same_evidence_ablation"}
                and getattr(policy, "requires_native_result", False) is True)):
        # A native decision also cites the exact qualified execution output.
        # Keep this proof; do not flatten it into shared original evidence.
        verify_native = getattr(policy, "verify_native_result", None)
        if arm not in {"flora_full", "same_evidence_ablation"} or not callable(verify_native):
            raise ValueError("unexpected decision parents lack native execution authority")
        if "arm" in inspect.signature(verify_native).parameters:
            qualified = verify_native(request, result, arm=arm)
        elif arm == "flora_full":
            qualified = verify_native(request, result)
        else:
            raise ValueError("native ablation requires explicit arm-bound execution authority")
        if (not isinstance(qualified, RecordedEvent)
                or qualified.event.event_type != "qualified_model_output"
                or qualified.event.scope != request.scope or qualified.raw.scope != request.scope
                or qualified.event.content_digest != qualified.raw.plaintext_sha256
                or not policy.verify_recorded(qualified)):
            raise ValueError("native execution parent lacks independently verified custody")
        qualified.event.validate()
        consumed = (qualified.event.event_id,) + consumed
    material = _bytes({"schema": "flora-decision-v1",
                       "verdict_base64": base64.b64encode(result.output).decode("ascii"),
                       "consumed_event_ids": list(consumed),
                       "model_artifact_sha256": request.binding.model_artifact_sha256})
    if (decision.event_type != "decision" or tuple(decision.parent_event_ids) != consumed
            or decision.content_digest != _sha(material)
            or decision.provenance.model_id != request.binding.model_artifact_sha256
            or decision.provenance.responsible_component != request.binding.producer_component):
        raise ValueError("output is not the exact context-bound recorded verdict")


async def run_paired(
    *, plan: PairedRunPlan, histories: Mapping[tuple[str, str], HistorySnapshot],
    questions: Mapping[str, bytes], adapters: Mapping[str, ArmAdapter],
    evidence_policy: RunEvidencePolicy,
) -> PairedRun:
    """Run all six attempts per case; preserve failures in their denominator.

    Absent adapters record unavailable. Preparation/execution are jointly timed.
    Async adapters must cooperate with cancellation; blocking inference belongs
    in separately terminable workers. No external API is called by this module.
    """
    plan.validate()
    if plan.preregistration_sha256 is not None:
        from .selected.comparison_custody import SelectedRunEvidencePolicy
        if not isinstance(evidence_policy, SelectedRunEvidencePolicy):
            raise PermissionError("anchored evaluation requires actual selected final authority")
    final_check = getattr(evidence_policy, "require_final_authority", None)
    if callable(final_check):
        final_check(plan=plan)
    digest = plan.digest()
    if set(adapters) - ARMS:
        raise ValueError("unknown execution arm")
    expected = {(case.case_id, phase) for case in plan.protocol.cases for phase in PHASES}
    if set(histories) != expected or set(questions) != {case.case_id for case in plan.protocol.cases}:
        raise ValueError("inputs differ from frozen case/phase matrix")
    # Validate every original before any adapter sees plaintext.
    from .selected.comparison_custody import SelectedRunEvidencePolicy
    from .selected.object_store import EncryptedObjectPlane
    from .selected.authenticated_history import AuthenticatedSelectedHistory, current_authenticated_history
    authenticated_histories = {}
    for case in plan.protocol.cases:
        if not isinstance(questions[case.case_id], bytes) or not questions[case.case_id]:
            raise ValueError("case needs common question bytes")
        if _sha(questions[case.case_id]) != plan.question_sha256_by_case[case.case_id]:
            raise ValueError("actual question differs from the frozen question binding")
        before, after = (histories[(case.case_id, phase)] for phase in ("before", "after"))
        if before.scope != after.scope or before.scope.host_instance_id != case.host_id:
            raise ValueError("case history crosses isolated host scope")
        if (after.sources[:len(before.sources)] != before.sources
                or case.intervention_event_id not in after.event_ids
                or case.intervention_event_id in before.event_ids):
            raise ValueError("before/after original event lineage differs from intervention")
        for phase, history in (("before", before), ("after", after)):
            if history.digest() != getattr(case, f"{phase}_history_sha256"):
                raise PermissionError("original history is changed or independently unauthorized")
            # Coordinators can deliberately supply guarded shallow copies
            # with independent controllers. Keep their full-auth route; an
            # adapter owned by the original policy cannot consume that copy's
            # issuance or unwrap its private-I/O guards.
            if (isinstance(evidence_policy, SelectedRunEvidencePolicy)
                    and type(evidence_policy.custody.objects) is EncryptedObjectPlane):
                authenticated_histories[(case.case_id, phase)] = AuthenticatedSelectedHistory(
                    policy=evidence_policy, plan=plan, case_id=case.case_id, phase=phase, history=history)
            elif not evidence_policy.authorize_history(case_id=case.case_id, phase=phase, history=history):
                raise PermissionError("original history is changed or independently unauthorized")
    attempts = []
    for case in plan.protocol.cases:
        for phase in ("before", "after"):
            history = histories[(case.case_id, phase)]
            question = questions[case.case_id]
            authenticated_history = authenticated_histories.get((case.case_id, phase))
            shared_context = None
            for arm in ("flora_full", "general_model_memory", "same_evidence_ablation"):
                started = time.monotonic()
                context = None
                context_sha256 = None
                result = None
                usage = None
                status = "unavailable"
                adapter = adapters.get(arm)
                binding = plan.binding_for(case.case_id, phase, arm)

                def authorize_live() -> None:
                    if (plan.digest() != digest
                            or _sha(question) != plan.question_sha256_by_case[case.case_id]
                            or history.digest() != getattr(case, f"{phase}_history_sha256")):
                        raise ArmStopped("refused")
                    if authenticated_history is not None:
                        current_authenticated_history(authenticated_history, policy=evidence_policy,
                            plan=plan, case_id=case.case_id, phase=phase, question=question, history=history)
                    elif not evidence_policy.authorize_history(case_id=case.case_id, phase=phase, history=history):
                        raise ArmStopped("refused")

                try:
                    authorize_live()
                    if adapter is None or (arm == "same_evidence_ablation" and shared_context is None):
                        raise ArmStopped("unavailable")

                    async def operation() -> ArmResult:
                        nonlocal context, context_sha256, shared_context
                        if arm == "same_evidence_ablation":
                            context = shared_context
                        else:
                            context = await adapter.prepare(PreparationRequest(
                                case.case_id, phase, question, history, plan, authenticated_history))
                        _authorize_context(policy=evidence_policy, case_id=case.case_id, phase=phase,
                                           history=history, context=context, arm=arm,
                                           authenticated_history=authenticated_history, plan=plan, question=question)
                        material = _context_bytes(context)
                        if len(material) > plan.context_byte_budget:
                            raise ValueError("prepared context violates byte budget")
                        context_sha256 = _sha(material)
                        if not context.sufficient_by_declared_count:
                            raise ArmStopped("unavailable")
                        authorize_live()
                        if arm == "flora_full":
                            shared_context = context
                        return await adapter.execute(ExecutionRequest(
                            case.case_id, phase, question, history.scope,
                            history.digest(), history.event_ids, context, binding, plan, authenticated_history))

                    result = await asyncio.wait_for(
                        operation(), timeout=plan.protocol.wall_time_budget_ms / 1000)
                    if not isinstance(result, ArmResult):
                        result = None
                        raise ValueError("adapter returned an invalid result contract")
                    usage = result.usage
                    authorize_live()
                    request = ExecutionRequest(case.case_id, phase, question, history.scope,
                                               history.digest(), history.event_ids,
                                               context, binding, plan, authenticated_history)
                    _authorize_context(policy=evidence_policy, case_id=case.case_id, phase=phase,
                                       history=history, context=context, arm=arm,
                                       authenticated_history=authenticated_history, plan=plan, question=question)
                    _validate_result(result, request, evidence_policy, arm=arm)
                    status = "success"
                    if (usage.output_tokens > plan.protocol.response_token_budget
                            or usage.context_tokens > plan.context_token_budget
                            or usage.input_tokens > plan.context_token_budget
                            or usage.feature_calls > plan.feature_call_budget):
                        status = "budget_exceeded"
                except ArmStopped as stop:
                    status = stop.status
                    if stop.usage is not None:
                        usage = stop.usage
                    if usage is not None:
                        try:
                            usage.validate()
                        except ValueError:
                            status, usage = "invalid_result", None
                except TimeoutError:
                    status = "timeout"
                except (ValueError, PermissionError):
                    status = "invalid_result"
                except Exception:
                    # Provider/adapter exception text may contain private input.
                    status = "failed"
                if status != "success" and usage is None and adapter is not None:
                    # A cancelled adapter may already have authenticated actual
                    # usage. This failure-only hook reads cached metadata; it
                    # must not perform inference, reopen data or repair custody.
                    stop_usage = getattr(adapter, "measured_stop_usage", None)
                    if callable(stop_usage):
                        try:
                            usage = stop_usage(case_id=case.case_id, phase=phase,
                                plan_sha256=digest, context_sha256=context_sha256)
                        except Exception:
                            usage = None
                if usage is not None:
                    try:
                        if not isinstance(usage, MeasuredUsage):
                            raise ValueError("invalid usage contract")
                        usage.validate()
                    except (ValueError, TypeError):
                        usage, status = None, "invalid_result"
                elapsed = math.ceil((time.monotonic() - started) * 1000)
                if status == "success" and elapsed > plan.protocol.wall_time_budget_ms:
                    status = "budget_exceeded"
                output = result.output if result is not None and isinstance(result.output, bytes) else None
                recorded_decision = result.decision if result is not None else None
                decision_id = (recorded_decision.event.event_id
                               if isinstance(recorded_decision, RecordedEvent) else None)
                attempts.append(RunAttempt(
                    case.case_id, case.host_id, arm, phase, digest, history.digest(),
                    history.event_ids, _sha(_bytes({
                        "history_sha256": history.digest(), "question_sha256": _sha(question)})),
                    context_sha256,
                    status, elapsed, usage, _sha(output) if output is not None else None,
                    decision_id,
                    binding.lineage_sha256,
                    output))
    if plan.digest() != digest:
        raise ValueError("execution plan changed during run")
    run = PairedRun(plan, tuple(attempts), dict(questions))
    validate_run(run)
    return run


def validate_run(run: PairedRun) -> None:
    """Reject missing failures, altered questions and substituted receipt lineage."""
    run.plan.validate()
    cases = {case.case_id: case for case in run.plan.protocol.cases}
    expected = {(case_id, phase, arm) for case_id in cases
                for phase in PHASES for arm in ARMS}
    observed = {}
    for attempt in run.attempts:
        key = (attempt.case_id, attempt.phase, attempt.arm)
        if key not in expected or key in observed:
            raise ValueError("unexpected or duplicate run attempt")
        case = cases[attempt.case_id]
        question = run.questions.get(attempt.case_id)
        if not isinstance(question, bytes) or not question:
            raise ValueError("run question was lost or changed")
        if _sha(question) != run.plan.question_sha256_by_case[attempt.case_id]:
            raise ValueError("run question differs from its frozen binding")
        history = getattr(case, f"{attempt.phase}_history_sha256")
        if (attempt.plan_sha256 != run.plan.digest()
                or attempt.host_id != case.host_id
                or attempt.authorized_history_sha256 != history
                or attempt.common_input_sha256 != _sha(_bytes({
                    "history_sha256": history, "question_sha256": _sha(question)}))
                or attempt.lineage_sha256 != run.plan.binding_for(attempt.case_id, attempt.phase, attempt.arm).lineage_sha256):
            raise ValueError("run input or lineage was changed")
        if attempt.status not in {"success", "unavailable", "refused", "failed", "timeout",
                                  "invalid_result", "budget_exceeded"}:
            raise ValueError("unknown run status")
        _integer(attempt.elapsed_ms, "elapsed_ms")
        if attempt.usage is not None:
            attempt.usage.validate()
        if attempt.output is not None and _sha(attempt.output) != attempt.output_sha256:
            raise ValueError("run output differs from its receipt")
        if attempt.status == "success":
            usage = attempt.usage
            if (usage is None or attempt.output is None or not attempt.decision_event_id
                    or attempt.context_sha256 is None
                    or usage.feature_engine_id != run.plan.protocol.feature_engine_id
                    or usage.output_tokens > run.plan.protocol.response_token_budget
                    or usage.context_tokens > run.plan.context_token_budget
                    or usage.input_tokens > run.plan.context_token_budget
                    or usage.feature_calls > run.plan.feature_call_budget
                    or attempt.elapsed_ms > run.plan.protocol.wall_time_budget_ms):
                raise ValueError("success receipt lacks measured in-budget evidence")
        observed[key] = attempt
    if set(observed) != expected:
        raise ValueError("run matrix is incomplete; failed attempts must remain")
    for case_id in cases:
        for phase in PHASES:
            full = observed[(case_id, phase, "flora_full")]
            ablation = observed[(case_id, phase, "same_evidence_ablation")]
            records = [observed[(case_id, phase, arm)] for arm in ARMS]
            if len({record.authorized_event_ids for record in records}) != 1:
                raise ValueError("original authorized event set differs across arms")
            if (ablation.context_sha256 is not None
                    and ablation.context_sha256 != full.context_sha256):
                raise ValueError("native-update ablation received different actual context")


def run_summary(run: PairedRun) -> dict:
    """Descriptive operational report only; no behavioral scores are inferred."""
    validate_run(run)
    groups = {}
    for attempt in run.attempts:
        key = f"{attempt.host_id}/{attempt.arm}"
        group = groups.setdefault(key, {"attempts": 0, "statuses": {},
                                       "elapsed_ms": [], "known_costs": {},
                                       "unavailable_cost_attempts": 0,
                                       "observed_usage_attempts": 0,
                                       "input_tokens": 0, "output_tokens": 0,
                                       "feature_calls": 0})
        group["attempts"] += 1
        group["statuses"][attempt.status] = group["statuses"].get(attempt.status, 0) + 1
        group["elapsed_ms"].append(attempt.elapsed_ms)
        if attempt.usage is not None:
            group["observed_usage_attempts"] += 1
            group["input_tokens"] += attempt.usage.input_tokens
            group["output_tokens"] += attempt.usage.output_tokens
            group["feature_calls"] += attempt.usage.feature_calls
        if attempt.usage is None or attempt.usage.cost_microunits is None:
            group["unavailable_cost_attempts"] += 1
        else:
            currency = attempt.usage.currency
            group["known_costs"][currency] = group["known_costs"].get(currency, 0) + attempt.usage.cost_microunits
    return {"schema": "flora-operational-run-summary-v1",
            "plan_sha256": run.plan.digest(), "evidence_kind": run.plan.evidence_kind,
            "groups": groups, "behavioral_assessment": "not_collected"}


class ReviewUsePolicy(Protocol):
    def allow_review(self, *, host_id: str, case_id: str,
                     output_sha256: str) -> bool: ...
    def allow_question(self, *, host_id: str, case_id: str,
                       question_sha256: str) -> bool: ...


def create_blind_review(run: PairedRun, *, policy: ReviewUsePolicy,
                        rng: random.Random | None = None) -> tuple[dict, dict]:
    """Return reviewer content and a SEPARATE private identity key.

    The public pack has no arm, host, case, phase, lineage, diagnostics, cost or
    receipts. Content itself remains authorized personal material, not publishable
    by default. Human assessment and unblinding happen outside this function.
    """
    validate_run(run)
    rng = rng or random.SystemRandom()
    by_key = {(item.case_id, item.phase, item.arm): item for item in run.attempts}
    public = {"schema": "flora-blind-review-v1", "pairs": []}
    private = {"schema": "flora-blind-review-key-v1", "plan_sha256": run.plan.digest(),
               "pairs": {}, "excluded_pairs": 0}
    for case in run.plan.protocol.cases:
        for phase in ("before", "after"):
            full = by_key[(case.case_id, phase, "flora_full")]
            for other in ("general_model_memory", "same_evidence_ablation"):
                baseline = by_key[(case.case_id, phase, other)]
                if full.status != "success" or baseline.status != "success":
                    private["excluded_pairs"] += 1
                    continue
                values = [full, baseline]
                if not policy.allow_question(
                    host_id=case.host_id, case_id=case.case_id,
                    question_sha256=_sha(run.questions[case.case_id])):
                    raise PermissionError("review question is not independently authorized")
                if not all(policy.allow_review(host_id=value.host_id, case_id=value.case_id,
                                               output_sha256=value.output_sha256)
                           for value in values):
                    raise PermissionError("review output is not independently authorized")
                rng.shuffle(values)
                pair_id = secrets.token_hex(16)
                public["pairs"].append({"pair_id": pair_id,
                                        "question": run.questions[case.case_id].decode("utf-8"),
                                        "left": values[0].output.decode("utf-8"),
                                        "right": values[1].output.decode("utf-8")})
                private["pairs"][pair_id] = {"case_id": case.case_id, "host_id": case.host_id,
                                             "phase": phase,
                                             "left": values[0].arm, "right": values[1].arm,
                                             "left_output_sha256": values[0].output_sha256,
                                             "right_output_sha256": values[1].output_sha256}
    rng.shuffle(public["pairs"])
    private["public_pack_sha256"] = _sha(_bytes(public))
    return public, private
