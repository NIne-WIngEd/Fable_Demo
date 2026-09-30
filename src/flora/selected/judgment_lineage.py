"""Independent native context/phase lineage for the paired FloRA experiment.

Original user evidence stays distinct from internal state approvals and qualified
execution receipts. Exact source membership is necessary, but does not certify
that an artifact/state was trained without future-phase data. The actual artifact
qualifier must attest its frozen phase source/training snapshot separately.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Callable, Protocol

from cryptography.exceptions import InvalidSignature, InvalidTag
from cognitive_kernel.canonical import canonical_sha256, require_identifier, require_sha256
from cognitive_kernel.contracts import ProductHostScope

from ..evaluation_protocol import PHASES
from .artifact_registry import RuntimeWiringManifest
from .context import LocalContext
from .decision_outcome import RecordedEvent
from .experiment_runtime import FloRAExperimentRuntime, RoleReadiness, RuntimeBlocked
from .source_native import read_current_source_manifest


def _artifact_record(artifact: RuntimeWiringManifest) -> dict[str, object]:
    return {**vars(artifact), "scope": artifact.scope.metadata_record()}


class PhaseHistoryAuthority(Protocol):
    def authorize_history(self, *, case_id: str, phase: str, history: Any) -> bool: ...


@dataclass(frozen=True)
class OriginalEvidenceBinding:
    event_id: str
    event_sha256: str
    content_sha256: str
    registration_sha256: str
    role: str
    parent_event_ids: tuple[str, ...]


@dataclass(frozen=True)
class ClaimLineageBinding:
    claim_id: str
    version_id: str
    version_sha256: str
    current_projection_id: str
    current_projection_sha256: str
    evidence_relations: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True)
class PersonalStateLineageBinding:
    subject_type: str
    subject_id: str
    projection_id: str
    version_id: str
    projection_sha256: str
    content_sha256: str
    activation_receipt_sha256: str
    source_claim_version_ids: tuple[str, ...]
    source_evidence_ids: tuple[str, ...]
    source_episode_ids: tuple[str, ...]
    approval_event_id: str
    approval_event_sha256: str
    approval_registration_sha256: str


@dataclass(frozen=True)
class AcceptedEpisodeLineageBinding:
    episode_id: str
    episode_sha256: str
    candidate_episode_sha256: str
    publication_receipt_sha256: str
    publication_record_sha256: str
    acceptance_request_sha256: str
    candidate_artifact_sha256: str
    summary_content_sha256: str
    full_content_sha256: str
    member_claim_version_ids: tuple[str, ...]
    original_event_ids: tuple[str, ...]
    acceptance_event_id: str
    acceptance_event_sha256: str
    acceptance_registration_sha256: str


@dataclass(frozen=True)
class InternalEvidenceBinding:
    record_type: str
    event_id: str
    event_sha256: str
    content_sha256: str
    registration_sha256: str
    governing_state_version_id: str


@dataclass(frozen=True)
class PhaseArtifactSnapshotRequest:
    scope: ProductHostScope
    authority_namespace_id: str
    case_id: str
    phase: str
    run_plan_sha256: str
    authorized_history_sha256: str
    authorized_original_event_ids: tuple[str, ...]
    context_lineage_sha256: str
    artifact: RuntimeWiringManifest

    def record(self) -> dict[str, object]:
        self.scope.validate()
        if self.phase not in PHASES:
            raise ValueError("unknown experiment phase")
        for name in ("authority_namespace_id", "case_id"):
            value = getattr(self, name)
            if require_identifier(value, name) != value:
                raise ValueError("phase snapshot identifiers must be canonical")
        for name in ("run_plan_sha256", "authorized_history_sha256", "context_lineage_sha256"):
            value = getattr(self, name)
            if require_sha256(value, name) != value:
                raise ValueError("phase snapshot digests must be canonical")
        if (tuple(sorted(set(self.authorized_original_event_ids))) != self.authorized_original_event_ids
                or not self.authorized_original_event_ids or self.artifact.scope != self.scope):
            raise ValueError("phase snapshot source/artifact scope is invalid")
        return {"schema": "flora-phase-artifact-snapshot-request-v1", "scope": self.scope.metadata_record(),
            **{name: getattr(self, name) for name in self.__dataclass_fields__ if name not in {"scope", "artifact"}},
            "artifact": _artifact_record(self.artifact)}

    @property
    def request_sha256(self) -> str:
        return canonical_sha256(self.record())


@dataclass(frozen=True)
class VerifiedPhaseArtifactSnapshot:
    """Adapter result from the actual role's independently trusted qualifier.

    The producer's receipt remains opaque. ``allowed_for_phase`` must cover
    private training, updater/source lineage, exclusions and the exact active
    state snapshot in this request, not just context source membership.
    """
    qualifier_id: str
    qualification_id: str
    artifact_manifest_sha256: str
    request_sha256: str
    receipt_sha256: str
    training_source_snapshot_sha256: str
    allowed_for_phase: bool

    def validate(self, request: PhaseArtifactSnapshotRequest, receipt: bytes) -> None:
        if (not isinstance(receipt, bytes) or not receipt
                or self.qualifier_id != request.artifact.qualifier_id
                or self.qualification_id != request.artifact.qualification_id
                or self.artifact_manifest_sha256 != request.artifact.manifest_sha256
                or self.request_sha256 != request.request_sha256
                or self.receipt_sha256 != hashlib.sha256(receipt).hexdigest()
                or self.allowed_for_phase is not True):
            raise ValueError("artifact phase snapshot is denied or differs from exact request")
        for name in ("receipt_sha256", "training_source_snapshot_sha256", "request_sha256",
                     "artifact_manifest_sha256"):
            value = getattr(self, name)
            if require_sha256(value, name) != value:
                raise ValueError("artifact phase snapshot has a noncanonical digest")


@dataclass(frozen=True)
class JudgmentContextLineage:
    scope: ProductHostScope
    authority_namespace_id: str
    case_id: str
    phase: str
    authorized_history_sha256: str
    context_receipt_sha256: str
    context_item_hashes: tuple[tuple[str, str, str, str, str | None], ...]
    originals: tuple[OriginalEvidenceBinding, ...]
    internal: tuple[InternalEvidenceBinding, ...]
    claims: tuple[ClaimLineageBinding, ...]
    personal_state: tuple[PersonalStateLineageBinding, ...]
    artifacts: tuple[RuntimeWiringManifest, ...]
    episodes: tuple[AcceptedEpisodeLineageBinding, ...] = ()
    phase_snapshots: tuple[VerifiedPhaseArtifactSnapshot, ...] = ()

    def record(self, *, include_phase_snapshots: bool = True) -> dict[str, object]:
        record = {"schema": "flora-judgment-context-lineage-v1", "scope": self.scope.metadata_record(),
            "authority_namespace_id": self.authority_namespace_id, "case_id": self.case_id,
            "phase": self.phase, "authorized_history_sha256": self.authorized_history_sha256,
            "context_receipt_sha256": self.context_receipt_sha256, "context_item_hashes": self.context_item_hashes,
            "originals": [vars(item) for item in self.originals], "internal": [vars(item) for item in self.internal],
            "claims": [vars(item) for item in self.claims], "personal_state": [vars(item) for item in self.personal_state],
            "episodes": [vars(item) for item in self.episodes],
            "artifacts": [_artifact_record(item) for item in self.artifacts]}
        if include_phase_snapshots:
            record["phase_snapshots"] = [vars(item) for item in self.phase_snapshots]
        return record

    @property
    def lineage_sha256(self) -> str:
        return canonical_sha256(self.record())

    @property
    def original_event_ids(self) -> tuple[str, ...]:
        return tuple(item.event_id for item in self.originals)


@dataclass(frozen=True)
class VerifiedNativeJudgmentResult:
    context_lineage: JudgmentContextLineage
    qualified_output: RecordedEvent
    delivery_event_id: str
    decision_event_id: str
    invocation_id: str


_INTERNAL_EVENT_TYPES = frozenset({
    "state_activation_approval", "private_personal_artifact", "formation_permission_action",
    "formation_context_delivery", "context_delivery", "qualified_model_input", "qualified_model_output",
    "qualified_model_attempt_failure", "decision",
    "episode_acceptance",
    "comparison_artifact", "provider_attempt_artifact", "phase_snapshot_artifact", "experiment_manifest_artifact",
})


class NativeJudgmentLineageVerifier:
    """Trusted evidence-policy bridge; inference output supplies no authority.

    ``history_for`` and ``invocation_id_for`` are independently frozen/registered
    lookups. ``phase_receipt_for`` supplies actual producer receipts; verification
    is performed by each role's qualification verifier itself.
    """
    def __init__(self, *, runtime: FloRAExperimentRuntime, history_authority: PhaseHistoryAuthority,
                 run_plan_sha256: str,
                 phase_receipt_for: Callable[[PhaseArtifactSnapshotRequest], bytes],
                 history_for: Callable[[str, str], Any], invocation_id_for: Callable[[Any, Any], str]):
        if require_sha256(run_plan_sha256, "run_plan_sha256") != run_plan_sha256:
            raise ValueError("lineage verifier needs the exact frozen run-plan digest")
        if not callable(getattr(history_authority, "authorize_history", None)) or not all(
                callable(item) for item in (phase_receipt_for, history_for, invocation_id_for)):
            raise TypeError("lineage verifier requires independently supplied authority/lookups")
        self.runtime, self.history_authority, self.run_plan_sha256 = runtime, history_authority, run_plan_sha256
        self.phase_receipt_for, self.history_for, self.invocation_id_for = phase_receipt_for, history_for, invocation_id_for

    def _claim(self, claim_id: str, version_id: str) -> ClaimLineageBinding:
        runtime = self.runtime
        manifest = read_current_source_manifest(claim_id=claim_id, authority=runtime.claims, log=runtime.log)
        current = runtime.claims.load_current(claim_id)
        version = runtime.claims.load_version(version_id)
        if (manifest.claim_version_id != version_id or current["current_claim_version_id"] != version_id
                or runtime.context_policy.allow_claim(claim_id, "personal_judgment") is not True):
            raise ValueError("native lineage cites unavailable/superseded Claim authority")
        relations = tuple(sorted((item.relation_id,
            runtime.claims.load_evidence_relation(item.relation_id)["relation_sha256"], item.event_id)
            for item in manifest.sources))
        if (version["envelope"]["scope"] != runtime.scope.metadata_record()
                or version["envelope"]["authority_namespace_id"] != runtime.authority_namespace_id):
            raise ValueError("native Claim lineage crosses host authority")
        return ClaimLineageBinding(claim_id, version_id, version["version_sha256"], current["projection_id"],
                                   current["projection_sha256"], relations)

    def context_lineage(self, *, case_id: str, phase: str, history: Any,
                        context: LocalContext,
                        authority_guard: Callable[[], None] | None = None) -> JudgmentContextLineage:
        runtime = self.runtime
        def guard():
            from .comparison_custody import SelectedRunEvidencePolicy
            authorize = (self.history_authority.authorize_history_metadata
                         if isinstance(self.history_authority, SelectedRunEvidencePolicy)
                         else self.history_authority.authorize_history)
            if authorize(case_id=case_id, phase=phase, history=history) is not True:
                raise PermissionError("native phase history was withdrawn before private I/O")
            if authority_guard is not None:
                authority_guard()
        from .experiment_runtime import _AuthorizedRuntimeReads
        if (phase not in PHASES or history.scope != runtime.scope
                or context.plan.purpose != "personal_judgment"
                or self.history_authority.authorize_history(case_id=case_id, phase=phase, history=history) is not True):
            raise PermissionError("native lineage lacks independently authorized phase history")
        history_digest = history.digest()
        history_events = {item.event.event_id: item.event for item in history.sources}
        if any(event.event_type in _INTERNAL_EVENT_TYPES for event in history_events.values()):
            raise ValueError("internal approvals/execution cannot become shared original user history")
        expected = context.receipt_record()
        prepared = runtime._prepare_current_context(context.plan, authority_guard=guard)
        if prepared.context.receipt_record() != expected:
            raise ValueError("native context content/value/current authority differs from prepared input")
        objects = _AuthorizedRuntimeReads(runtime.objects, prepared.metadata_current)
        approval_verifier = runtime._guarded_state_verifier(objects)
        claims, states, internal, accepted_episodes = {}, {}, {}, {}
        source_roots = set()
        events = {event.event_id: event for event in runtime.log.replay()}
        for item in context.items:
            if item.kind == "claim":
                if item.control_event_ids:
                    raise ValueError("Claim context cannot introduce internal episode controls")
                claim = self._claim(item.record_id, item.version_id)
                if item.projection_sha256 != claim.current_projection_sha256:
                    raise ValueError("native context Claim projection digest differs")
                claims[claim.version_id] = claim
                source_roots.update(event_id for _, _, event_id in claim.evidence_relations)
            elif item.kind.startswith("state:"):
                subject_type = item.kind.removeprefix("state:")
                routes = [route for route in context.plan.state_routes if route.subject_type == subject_type
                          and route.projection_id == item.record_id]
                if len(routes) != 1:
                    raise ValueError("personal-state lineage lacks one exact subject route")
                route = routes[0]
                active = runtime.state.read_active(subject_type=route.subject_type, subject_id=route.subject_id,
                    projection_id=route.projection_id, claims=runtime.claims, log=runtime.log, objects=objects,
                    references=runtime.references, verifier=approval_verifier)
                state = active.record
                if (state["version_id"] != item.version_id or state["projection_sha256"] != item.projection_sha256
                        or hashlib.sha256(item.content).hexdigest() != state["content_digest"]
                        or active.content != item.content or active.approval_event_id != item.approval_event_id):
                    raise ValueError("native context differs from exact active personal state")
                episode_controls = set()
                for episode_id in state["source_episode_ids"]:
                    episodes = runtime.state.episodes
                    if episodes is None:
                        raise ValueError("episode-derived comparison lacks governed accepted episode authority")
                    episode_lineage = episodes.current_lineage(episode_id, claims=runtime.claims, log=runtime.log)
                    episode, publication, request, source_ids, published = episode_lineage
                    accepted = episodes.read_accepted(episode_id, claims=runtime.claims, log=runtime.log,
                        objects=objects, references=runtime.references)
                    control = events.get(publication.acceptance_event_id)
                    registered_control = runtime.sources.lookup(publication.acceptance_event_id)
                    if (accepted.record != episode.metadata_record() or accepted.publication != publication
                            or episodes.current_lineage(episode_id, claims=runtime.claims, log=runtime.log) != episode_lineage
                            or control is None or registered_control is None or control.event_type != "episode_acceptance"
                            or registered_control.object_ref != control.payload_reference
                            or registered_control.evidence.content_digest != control.content_digest
                            or runtime.context_policy.allow_event(control.event_id, "personal_judgment") is not True):
                        raise ValueError("episode-derived comparison lost exact accepted publication/control authority")
                    episode_controls.add(control.event_id)
                    original_ids = tuple(sorted(set(source_ids) - {control.event_id}))
                    accepted_episodes[episode_id] = AcceptedEpisodeLineageBinding(episode_id, episode.episode_sha256,
                        publication.candidate_sha256, publication.receipt_sha256, published["record_sha256"],
                        request.request_sha256, request.candidate_artifact_sha256, episode.summary_content_digest,
                        episode.full_content_digest, episode.member_claim_version_ids, original_ids,
                        control.event_id, control.event_sha256, registered_control.registration_sha256)
                    internal[control.event_id] = InternalEvidenceBinding("episode_acceptance", control.event_id,
                        control.event_sha256, control.content_digest, registered_control.registration_sha256, item.version_id)
                    source_roots.update(original_ids)
                    for version_id in episode.member_claim_version_ids:
                        record = runtime.claims.load_version(version_id)
                        claims[version_id] = self._claim(record["claim_id"], version_id)
                if set(item.control_event_ids) != episode_controls:
                    raise ValueError("native state control IDs differ from accepted episode publications")
                receipt = runtime.state._history(route.projection_id, item.version_id)
                approval = events.get(active.approval_event_id)
                registration = runtime.sources.lookup(active.approval_event_id)
                if (approval is None or approval.event_type != "state_activation_approval" or registration is None
                        or runtime.context_policy.allow_event(approval.event_id, "personal_judgment") is not True
                        or registration.object_ref != approval.payload_reference
                        or registration.evidence.content_digest != approval.content_digest
                        or receipt["approval_event_id"] != approval.event_id
                        or receipt["approval_event_sha256"] != approval.event_sha256):
                    raise ValueError("internal approval lacks exact accepted registered state lineage")
                states[item.version_id] = PersonalStateLineageBinding(route.subject_type, route.subject_id,
                    route.projection_id, item.version_id, state["projection_sha256"], state["content_digest"],
                    receipt["record_sha256"], tuple(state["source_claim_version_ids"]),
                    tuple(state["source_evidence_ids"]), tuple(state["source_episode_ids"]), approval.event_id, approval.event_sha256,
                    registration.registration_sha256)
                internal[approval.event_id] = InternalEvidenceBinding("state_activation_approval", approval.event_id,
                    approval.event_sha256, approval.content_digest, registration.registration_sha256, item.version_id)
                for version_id in state["source_claim_version_ids"]:
                    record = runtime.claims.load_version(version_id)
                    claim = self._claim(record["claim_id"], version_id)
                    claims[version_id] = claim
                    source_roots.update(event_id for _, _, event_id in claim.evidence_relations)
                source_roots.update(state["source_evidence_ids"])
                # Additional source records cannot quietly influence state.
                source_roots.update(set(state["envelope"]["source_records"])
                                    - set(state["source_claim_version_ids"]) - set(state["source_episode_ids"]))
                # Approvals are audit records, but an approval's actual source
                # parents must still be part of this phase's shared originals.
                source_roots.update(registration.evidence.parent_refs)
            else:
                raise ValueError("unsupported native context item lineage")
            source_roots.update(item.source_event_ids)
        delivered_originals = {event_id for item in context.items for event_id in item.source_event_ids}
        delivered_controls = {event_id for item in context.items for event_id in item.control_event_ids}
        if (delivered_originals.intersection(internal) or not delivered_controls.issubset(internal)
                or set(context.source_event_ids) != delivered_originals | set(internal)):
            raise ValueError("native context contains undeclared or mislabeled source/approval IDs")
        originals, pending = {}, list(source_roots)
        while pending:
            event_id = pending.pop()
            if event_id in originals:
                continue
            source, event = runtime.sources.lookup(event_id), events.get(event_id)
            if (event_id in internal or source is None or event is None
                    or event.event_type in _INTERNAL_EVENT_TYPES or history_events.get(event_id) != event
                    or event.scope != runtime.scope or source.evidence.authority_namespace_id != runtime.authority_namespace_id
                    or source.object_ref != event.payload_reference or source.evidence.content_digest != event.content_digest
                    or source.evidence.parent_refs != event.parent_event_ids
                    or runtime.context_policy.allow_event(event_id, "personal_judgment") is not True):
                raise ValueError("original evidence closure exceeds frozen phase history or source authority")
            originals[event_id] = OriginalEvidenceBinding(event_id, event.event_sha256, event.content_digest,
                source.registration_sha256, source.evidence.role, source.evidence.parent_refs)
            pending.extend(source.evidence.parent_refs)
        artifacts = tuple(runtime._resolve(role, authority_guard=guard)[1]
                          for role in ("memory_formation", "personality_judgment"))
        item_hashes = tuple((item["kind"], item["record_id"], item["version_id"], item["content_sha256"],
                             item["claim_value_sha256"]) for item in expected["items"])
        lineage = JudgmentContextLineage(runtime.scope, runtime.authority_namespace_id, case_id, phase, history_digest,
            expected["receipt_sha256"], item_hashes, tuple(originals[key] for key in sorted(originals)),
            tuple(internal[key] for key in sorted(internal)), tuple(claims[key] for key in sorted(claims)),
            tuple(states[key] for key in sorted(states)), artifacts,
            episodes=tuple(accepted_episodes[key] for key in sorted(accepted_episodes)))
        snapshots = []
        for artifact in artifacts:
            qualifier = runtime.bindings[artifact.role].qualification_verifier
            verify_phase = getattr(qualifier, "verify_phase_snapshot", None)
            if not callable(verify_phase):
                raise RuntimeBlocked((RoleReadiness(
                    artifact.role, False, ("actual_qualifier_phase_snapshot_adapter",)),))
            request = PhaseArtifactSnapshotRequest(runtime.scope, runtime.authority_namespace_id, case_id, phase,
                self.run_plan_sha256, history_digest, tuple(sorted(history_events)),
                canonical_sha256(lineage.record(include_phase_snapshots=False)), artifact)
            opaque_receipt = self.phase_receipt_for(request)
            verified = verify_phase(request=request, receipt=opaque_receipt)
            if not isinstance(verified, VerifiedPhaseArtifactSnapshot):
                raise TypeError("actual artifact qualifier returned no bound phase snapshot")
            verified.validate(request, opaque_receipt)
            snapshots.append(verified)
            if self.history_authority.authorize_history(case_id=case_id, phase=phase, history=history) is not True:
                raise PermissionError("frozen phase history authority changed during producer verification")
        # Phase verification may involve slow producer I/O. Current context,
        # original registration/permission and artifact generation are fresh.
        prepared.revalidate()
        if history.digest() != history_digest:
            raise ValueError("phase history/current context changed during artifact verification")
        for original in originals.values():
            source = runtime.sources.lookup(original.event_id)
            if (source is None or source.registration_sha256 != original.registration_sha256
                    or runtime.context_policy.allow_event(original.event_id, "personal_judgment") is not True):
                raise PermissionError("original source authority changed during lineage verification")
        if tuple(runtime._resolve(artifact.role, authority_guard=guard)[1] for artifact in artifacts) != artifacts:
            raise ValueError("artifact role changed during phase snapshot verification")
        if self.history_authority.authorize_history(case_id=case_id, phase=phase, history=history) is not True:
            raise PermissionError("frozen phase history authority changed before lineage return")
        return JudgmentContextLineage(**{**vars(lineage), "phase_snapshots": tuple(snapshots)})

    def authorize_context(self, *, case_id: str, phase: str, history: Any,
                          context: LocalContext, arm: str,
                          authority_guard: Callable[[], None] | None = None) -> bool:
        if arm not in {"flora_full", "same_evidence_ablation"}:
            return False
        try:
            self.context_lineage(case_id=case_id, phase=phase, history=history, context=context,
                                 authority_guard=authority_guard)
        except (ValueError, TypeError, KeyError, PermissionError, InvalidSignature, InvalidTag, RuntimeBlocked):
            return False
        return True

    def verify_native_result_details(self, request: Any, result: Any, *,
                                     reconcile: bool = True,
                                     authority_guard: Callable[[], None] | None = None) -> VerifiedNativeJudgmentResult:
        history = self.history_for(request.case_id, request.phase)
        if (request.scope != self.runtime.scope or request.plan.digest() != self.run_plan_sha256
                or history.digest() != request.authorized_history_sha256
                or tuple(history.event_ids) != request.authorized_event_ids):
            raise ValueError("native result differs from independently frozen phase history")
        lineage = self.context_lineage(case_id=request.case_id, phase=request.phase, history=history,
                                       context=request.context, authority_guard=authority_guard)
        invocation_id = self.invocation_id_for(request, result)
        def guard():
            from .comparison_custody import SelectedRunEvidencePolicy
            authorize = (self.history_authority.authorize_history_metadata
                         if isinstance(self.history_authority, SelectedRunEvidencePolicy)
                         else self.history_authority.authorize_history)
            if authorize(case_id=request.case_id,
                    phase=request.phase, history=history) is not True:
                raise PermissionError("native phase history was withdrawn before execution recovery")
            if authority_guard is not None:
                authority_guard()
        actual = self.runtime.recover_judgment(plan=request.context.plan, task=request.question,
                                              invocation_id=invocation_id, reconcile=reconcile,
                                              authority_guard=guard)
        if (actual.context.receipt_record() != request.context.receipt_record()
                or actual.execution.result.output != result.output or actual.delivery != result.delivery
                or actual.decision != result.decision
                or actual.execution.invocation.artifact.checkpoint_sha256 != request.binding.model_artifact_sha256
                or actual.decision.event.provenance.responsible_component != request.binding.producer_component):
            raise ValueError("native result does not match actual qualified execution and context")
        # Recovery/proof I/O must not outrun a changed phase source/state.
        if self.context_lineage(case_id=request.case_id, phase=request.phase, history=history,
                                context=request.context, authority_guard=authority_guard).lineage_sha256 != lineage.lineage_sha256:
            raise ValueError("native phase lineage changed during result verification")
        return VerifiedNativeJudgmentResult(lineage, actual.execution.output_record, actual.delivery.event.event_id,
                                            actual.decision.event.event_id, invocation_id)

    def verify_native_result(self, request: Any, result: Any, *, arm: str = "flora_full") -> RecordedEvent:
        """Runner hook: return precisely the extra verified output parent."""
        if arm != "flora_full":
            raise PermissionError("native ablation requires the actual arm-specific selected phase route")
        return self.verify_native_result_details(request, result).qualified_output
