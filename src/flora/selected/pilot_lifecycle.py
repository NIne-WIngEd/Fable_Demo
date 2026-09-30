"""Native synthetic-pilot transition on the selected canonical fabric.

This is intake/recovery orchestration. It neither invents a verdict nor performs
an update. Producer phase exclusions and the after/ablation exports are required
separately; a verified before transition does not establish learned behavior.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Awaitable, Callable, Mapping

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cognitive_kernel.canonical import canonical_json_bytes, canonical_sha256, normalize_timestamp
from cognitive_kernel.contracts import ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from cognitive_kernel.formation_context_planner import FormationPlanningRequest

from ..comparison_run import HistorySnapshot, SourceMaterial
from ..pilot_fixture import case_history_digest, load_pilot
from ..pilot_ingress import PilotCheckpoint
from .context import ContextPlan
from .decision_outcome import RecordedEvent
from .experiment_runtime import FloRAExperimentRuntime, RuntimeRoleBinding, _AuthorizedRuntimeReads
from .judgment_lineage import NativeJudgmentLineageVerifier
from .owner_authorization import Ed25519OwnerActionVerifier, OwnerActionProof
from .personal_artifact_custody import DurableOwnerProofLookup, approval_artifact_id, owner_proof_artifact_id
from .personal_state import _ACTIVE
from .phase_routes import PhaseSnapshotReference, recognize_phase_snapshot
from .phase_snapshots import XTDBPhaseSnapshotCustody


@dataclass(frozen=True)
class NativeFormationReference:
    request: FormationPlanningRequest
    bundle_id: str
    invocation_id: str


@dataclass(frozen=True)
class NativeBeforeReference:
    """Exact externally executed stages, never supplied output/validation bytes."""
    formations: tuple[NativeFormationReference, ...]
    context_plan: ContextPlan
    task: bytes = field(repr=False)
    judgment_invocation_id: str
    phase_snapshots: tuple[PhaseSnapshotReference, ...] = ()


@dataclass(frozen=True)
class NativePilotPhaseSnapshotServices:
    """Explicit actual archived routes; no default model or qualification."""
    custody: XTDBPhaseSnapshotCustody = field(repr=False)
    bindings_by_snapshot_id: Mapping[str, Mapping[str, RuntimeRoleBinding]] = field(repr=False)
    invocation_id_for: Callable = field(repr=False)


@dataclass(frozen=True)
class VerifiedNativePilotBefore:
    case_id: str
    original_history_sha256: str
    canonical_prefix: tuple[tuple[str, str], ...]
    original_event_ids: tuple[str, ...]
    native_decision_event_id: str
    phase_lineage_sha256: str

    @property
    def receipt_sha256(self):
        return canonical_sha256({"schema": "flora-native-pilot-before-v1", **vars(self)})


@dataclass(frozen=True)
class NativePilotTransition:
    before: VerifiedNativePilotBefore
    after_history: HistorySnapshot = field(repr=False)
    intervention: RecordedEvent
    outcome_audit: RecordedEvent | None
    original_observed_at: str


def _source_guard(runtime, history):
    """Original-only closure/current permission; metadata checked before bytes."""
    expected_ids = set(history.event_ids)
    current = {event.event_id: event for event in runtime.log.replay()}
    for source in history.sources:
        event = source.event
        registered = runtime.sources.lookup(event.event_id)
        if (current.get(event.event_id) != event or registered is None
                or registered.evidence.role != "generated_reconstruction"
                or registered.object_ref != event.payload_reference
                or registered.evidence.content_digest != event.content_digest
                or registered.evidence.parent_refs != event.parent_event_ids
                or not set(event.parent_event_ids).issubset(expected_ids)
                or runtime.source_policy.permits(registered, "personal_judgment") is not True):
            raise PermissionError("native pilot original source is no longer permitted")
    return True


def _read_artifact(runtime, artifact_id, history, guard=None):
    custody = runtime.original_references.custody
    current = guard or (lambda: _source_guard(runtime, history))
    def source_authorizer():
        # Current-context callbacks succeed with None; custody's distinct
        # source predicate requires True after that fresh callback completes.
        current()
        return True
    return custody.read(artifact_id, log=runtime.log, objects=_AuthorizedRuntimeReads(runtime.objects, current),
                        source_authorizer=source_authorizer)


def _guarded_owner_verifier(runtime, objects):
    enrolled = runtime.state_approval_verifier
    if not isinstance(enrolled, Ed25519OwnerActionVerifier) or enrolled.scope != runtime.scope:
        raise TypeError("native pilot requires the existing enrolled owner verifier")
    public = enrolled.key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    proofs = DurableOwnerProofLookup(custody=runtime.original_references.custody, log=runtime.log,
                                    objects=objects, owner_public_key=public)
    return Ed25519OwnerActionVerifier(scope=runtime.scope, owner_public_key=public, proofs=proofs)


def _proof(runtime, event, action, history, guard=None):
    """Actual durable proof, with the runtime's independently enrolled key."""
    enrolled = runtime.state_approval_verifier
    if not isinstance(enrolled, Ed25519OwnerActionVerifier) or enrolled.scope != runtime.scope:
        raise TypeError("native pilot requires the existing enrolled owner verifier")
    artifact = _read_artifact(runtime, owner_proof_artifact_id(event.event_id), history, guard)
    public = enrolled.key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    if (artifact.kind != "owner_action_proof"
            or artifact.contract["action"] != action
            or artifact.contract["event_id"] != event.event_id
            or artifact.contract["event_sha256"] != event.event_sha256
            or artifact.contract["owner_public_key_sha256"] != hashlib.sha256(public).hexdigest()):
        raise ValueError("native pilot owner proof is not bound to enrolled action")
    proof = OwnerActionProof(**json.loads(dict(artifact.content)["proof"]))
    verifier = Ed25519OwnerActionVerifier(scope=runtime.scope, owner_public_key=public,
                                         proofs={event.event_id: proof})
    if verifier._verify(event, action) is not True:
        raise PermissionError("native pilot action lacks its enrolled owner signature")
    return artifact.event.event_id


def verify_native_before(*, path, checkpoint: PilotCheckpoint,
                         reference: NativeBeforeReference,
                         runtime: FloRAExperimentRuntime,
                         lineage: NativeJudgmentLineageVerifier,
                         phase_snapshot_services: NativePilotPhaseSnapshotServices | None = None) -> VerifiedNativePilotBefore:
    """Read-only exact before recovery; any unrecognized canonical tail stops.

    Permission requests/proofs are verified through durable selected custody and
    the current policy. Current state/episodes and native receipts are recovered
    through their actual services. No event-type allowlist confers authority.
    """
    if not isinstance(runtime, FloRAExperimentRuntime) or not isinstance(lineage, NativeJudgmentLineageVerifier):
        raise TypeError("native pilot needs actual selected runtime and lineage services")
    if lineage.runtime is not runtime or runtime.scope != checkpoint.scope:
        raise ValueError("native pilot crosses selected runtime/phase scope")
    record = load_pilot(path)
    case = next(item for item in record["cases"] if item["case_id"] == checkpoint.case_id)
    if (not isinstance(reference, NativeBeforeReference)
            or reference.task != case["prompt"].encode()
            or reference.context_plan.purpose != "personal_judgment"
            or len({item.invocation_id for item in reference.formations}) != len(reference.formations)
            or len({item.bundle_id for item in reference.formations}) != len(reference.formations)
            or not isinstance(reference.phase_snapshots, tuple)
            or any(not isinstance(item, PhaseSnapshotReference) for item in reference.phase_snapshots)):
        raise ValueError("native pilot needs the exact fictional task and unique native stage references")
    original_ids = tuple(checkpoint.event_by_source_id.values())
    replay = runtime.log.replay()
    if (checkpoint.scope.host_instance_id != f"{record['host_id']}-{checkpoint.case_id}"
            or checkpoint.history_sha256 != case_history_digest(record, checkpoint.case_id, "before")
            or tuple(checkpoint.event_by_source_id) != tuple(case["before_event_ids"])
            or tuple(event.event_id for event in replay[:len(original_ids)]) != original_ids):
        raise ValueError("native pilot before has changed its exact original prefix")
    history = lineage.history_for(checkpoint.case_id, "before")
    if (not isinstance(history, HistorySnapshot) or history.scope != runtime.scope
            or history.event_ids != original_ids
            or lineage.history_authority.authorize_history(case_id=checkpoint.case_id,
                phase="before", history=history) is not True):
        raise PermissionError("native pilot needs independently authorized original-only before history")
    by_source = {item["id"]: item for item in record["events"]}
    for position, (source_id, source) in enumerate(zip(case["before_event_ids"], history.sources)):
        expected = by_source[source_id]
        event = source.event
        if (event != replay[position]
                or source.plaintext != expected["text"].encode()
                or event.occurred_at != normalize_timestamp(expected["at"])
                or event.event_type != "observation" or event.parent_event_ids
                or event.provenance.provenance_type != "generated_reconstruction"
                or event.provenance.source_reference_ids != (source_id,)
                or event.provenance.responsible_component != "flora-synthetic-pilot"):
            raise ValueError("native pilot original differs from its fictional fixture")
    phase = None
    permission_snapshots = []
    def guard():
        if lineage.history_authority.authorize_history(case_id=checkpoint.case_id,
                phase="before", history=history) is not True:
            raise PermissionError("native pilot before phase permission was withdrawn")
        _source_guard(runtime, history)
        for source_id, purpose, action in permission_snapshots:
            if runtime.source_policy.current_action(source_id, purpose) != action:
                raise PermissionError("native pilot control permission changed during private recovery")
        if phase is not None:
            for claim in phase.claims:
                current = runtime.claims.load_current(claim.claim_id)
                if (current["current_claim_version_id"] != claim.version_id
                        or current["projection_sha256"] != claim.current_projection_sha256
                        or runtime.context_policy.allow_claim(claim.claim_id, "personal_judgment") is not True):
                    raise PermissionError("native pilot Claim changed during private recovery")
            for state in phase.personal_state:
                head = runtime.state._fetch(_ACTIVE, runtime.state._head_id(
                    state.subject_type, state.subject_id, state.projection_id))
                if (head is None or head["version_id"] != state.version_id
                        or head["approval_event_id"] != state.approval_event_id
                        or runtime.context_policy.allow_state(state.subject_type, state.subject_id,
                            state.projection_id, "personal_judgment") is not True):
                    raise PermissionError("native pilot state changed during private recovery")
            for episode in phase.episodes:
                live = runtime.state.episodes.current_lineage(episode.episode_id,
                    claims=runtime.claims, log=runtime.log)
                if live[4]["record_sha256"] != episode.publication_record_sha256:
                    raise PermissionError("native pilot episode changed during private recovery")
    guard()
    known = set(original_ids)
    for supplied in reference.formations:
        guard()
        if (supplied.request.scope != runtime.scope
                or supplied.request.authority_namespace_id != runtime.authority_namespace_id
                or not set(supplied.request.experience_refs).issubset(original_ids)):
            raise ValueError("native before formation reaches outside original history")
        formed = runtime.recover_formation(request=supplied.request, bundle_id=supplied.bundle_id,
                                          invocation_id=supplied.invocation_id, reconcile=False, authority_guard=guard)
        guard()
        if not set(formed.prepared.assembled.packet.experience_refs).issubset(original_ids):
            raise ValueError("native before formation introduced internal shared history")
        known.update(item.event.event_id for item in (formed.delivery, formed.execution.input_record,
                     formed.execution.output_record, formed.candidate))
    if not reference.formations:
        raise ValueError("native pilot requires actual qualified formation receipts")
    guard()
    judgment = runtime.recover_judgment(plan=reference.context_plan, task=reference.task,
                                      invocation_id=reference.judgment_invocation_id, reconcile=False,
                                      authority_guard=guard)
    guard()
    phase = lineage.context_lineage(case_id=checkpoint.case_id, phase="before", history=history,
                                   context=judgment.context, authority_guard=guard)
    known.update(item.event.event_id for item in (judgment.delivery, judgment.execution.input_record,
                 judgment.execution.output_record, judgment.decision))
    controls = set()
    guarded_objects = _AuthorizedRuntimeReads(runtime.objects, guard)
    guarded_owner = _guarded_owner_verifier(runtime, guarded_objects)
    for route in reference.context_plan.state_routes:
        guard()
        active = runtime.state.read_active(subject_type=route.subject_type, subject_id=route.subject_id,
            projection_id=route.projection_id, claims=runtime.claims, log=runtime.log, objects=guarded_objects,
            references=runtime.references, verifier=guarded_owner)
        guard()
        artifact = _read_artifact(runtime, active.record["version_id"], history, guard)
        if artifact.kind != "projection" or artifact.contract != active.record:
            raise ValueError("native pilot active projection has no exact private candidate")
        known.add(artifact.event.event_id)
        approval = _read_artifact(runtime, approval_artifact_id(active.approval_event_id), history, guard)
        if approval.kind != "state_activation_approval" or approval.event.event_id != active.approval_event_id:
            raise ValueError("native pilot state approval has no exact typed custody")
        known.add(approval.event.event_id)
        known.add(_proof(runtime, approval.event, "state_activation", history, guard))
        controls.add(approval.event.event_id)
        for episode_id in active.record["source_episode_ids"]:
            if runtime.state.episodes is None:
                raise ValueError("native pilot episode requires actual governed publication")
            episode, publication, request, _, _ = runtime.state.episodes.current_lineage(
                episode_id, claims=runtime.claims, log=runtime.log)
            runtime.state.episodes.read_accepted(episode_id, claims=runtime.claims, log=runtime.log,
                                               objects=guarded_objects, references=runtime.references)
            candidate = _read_artifact(runtime, request.candidate_artifact_id, history, guard)
            if candidate.kind != "episode" or candidate.contract["episode_id"] != episode.episode_id:
                raise ValueError("native pilot episode lost candidate custody")
            known.update((candidate.event.event_id, publication.acceptance_event_id))
            controls.add(publication.acceptance_event_id)
    replay_by_id = {event.event_id: event for event in replay}
    if reference.phase_snapshots:
        services = phase_snapshot_services
        if (not isinstance(services, NativePilotPhaseSnapshotServices)
                or not isinstance(services.custody, XTDBPhaseSnapshotCustody)
                or services.custody.runtime is not runtime
                or services.custody.run_plan_sha256 != lineage.run_plan_sha256
                or not callable(services.invocation_id_for)
                or len({item.snapshot_id for item in reference.phase_snapshots}) != len(reference.phase_snapshots)
                or len({item.event_id for item in reference.phase_snapshots}) != len(reference.phase_snapshots)):
            raise ValueError("native pilot snapshots require unique explicit actual selected routes")
        for snapshot in reference.phase_snapshots:
            guard()
            if (not isinstance(snapshot, PhaseSnapshotReference)
                    or snapshot.case_id != checkpoint.case_id or snapshot.phase != "before"
                    or snapshot.run_id != services.custody.run_id
                    or snapshot.snapshot_id not in services.bindings_by_snapshot_id):
                raise ValueError("native pilot snapshot differs from its exact before case and route")
            event = replay_by_id.get(snapshot.event_id)
            if event is None:
                raise ValueError("native pilot snapshot is absent from the exact canonical before prefix")
            recognized = recognize_phase_snapshot(reference=snapshot, event=event, custody=services.custody,
                history=history, history_authority=lineage.history_authority,
                historical_bindings=services.bindings_by_snapshot_id[snapshot.snapshot_id],
                invocation_id_for=services.invocation_id_for)
            guard()
            if recognized != snapshot:
                raise ValueError("native pilot snapshot recognizer returned a different typed reference")
            known.add(event.event_id)
            controls.add(event.event_id)
    for source_id in (*original_ids, *sorted(controls)):
        for purpose in ("memory_formation", "personal_judgment"):
            action = runtime.source_policy.current_action(source_id, purpose)
            if action is None:
                continue
            source = runtime.sources.lookup(source_id)
            permission_snapshots.append((source_id, purpose, action))
            stored = runtime.source_policy._stored_action(action.action_id)
            event = replay_by_id.get(stored["request_event_id"] if stored else "")
            if (source is None or event is None or action.decision != "allow"
                    or stored["request_event_sha256"] != event.event_sha256
                    or runtime.source_policy.permits(source, purpose) is not True):
                raise PermissionError("native pilot control permission is stale or unapplied")
            permission_id = "formation-permission-" + canonical_sha256([event.event_id])[:48]
            permission = _read_artifact(runtime, permission_id, history, guard)
            if permission.kind != "formation_permission_action" or permission.contract != action.metadata_record():
                raise ValueError("native pilot permission differs from actual policy/custody")
            known.update((event.event_id, _proof(runtime, event, "formation_permission", history, guard)))
    # Strict typed coverage, including siblings such as owner proofs/candidates.
    # A caller cannot hide an unexpected event behind a real final decision.
    for event in replay[len(original_ids):]:
        if event.event_id not in known or event.scope != runtime.scope or not set(event.parent_event_ids).issubset(known):
            raise ValueError("native pilot canonical tail contains an unsupported or unbound event")
    guard()
    if lineage.context_lineage(case_id=checkpoint.case_id, phase="before", history=history,
                              context=judgment.context, authority_guard=guard).lineage_sha256 != phase.lineage_sha256:
        raise ValueError("native pilot before phase changed during typed recovery")
    guard()
    if runtime.log.replay() != replay:
        raise ValueError("native pilot canonical prefix changed during before validation")
    return VerifiedNativePilotBefore(checkpoint.case_id, history.digest(),
        tuple((event.event_id, event.event_sha256) for event in replay), original_ids,
        judgment.decision.event.event_id, phase.lineage_sha256)


def apply_native_intervention(*, path, checkpoint: PilotCheckpoint, reference: NativeBeforeReference,
                              runtime: FloRAExperimentRuntime, lineage: NativeJudgmentLineageVerifier,
                              occurred_at: str,
                              phase_snapshot_services: NativePilotPhaseSnapshotServices | None = None) -> NativePilotTransition:
    """Verify the genuine before run, then append a synthetic original and audit.

    Historical observation time is payload metadata. Canonical causal time is
    current; the physical Kurrent commit time is never supplied/backdated here.
    The audit outcome is not promoted into the shared original history.
    """
    before = verify_native_before(path=path, checkpoint=checkpoint, reference=reference,
                                  runtime=runtime, lineage=lineage, phase_snapshot_services=phase_snapshot_services)
    record = load_pilot(path)
    case = next(item for item in record["cases"] if item["case_id"] == checkpoint.case_id)
    source = next(item for item in record["events"] if item["id"] == case["intervention_event_id"])
    at = normalize_timestamp(occurred_at)
    replay = runtime.log.replay()
    if (tuple((event.event_id, event.event_sha256) for event in replay) != before.canonical_prefix
            or at < max(event.occurred_at for event in replay)):
        raise ValueError("native pilot intervention cannot precede its actual canonical before run")
    history = lineage.history_for(checkpoint.case_id, "before")
    if (not isinstance(history, HistorySnapshot) or history.scope != runtime.scope
            or history.digest() != before.original_history_sha256
            or history.event_ids != before.original_event_ids):
        raise ValueError("native pilot intervention changed its verified original before history")
    def authorize_append(stage):
        def phase_current():
            if lineage.history_authority.authorize_history(case_id=checkpoint.case_id,
                    phase="before", history=history) is not True:
                raise PermissionError("native pilot before permission changed before " + stage + " append")
        phase_current()
        _source_guard(runtime, history)
        # Source metadata/permission lookups can be slow. The phase check that
        # preceded them cannot authorize the later canonical append.
        phase_current()
    authorize_append("intervention")
    payload = canonical_json_bytes({"schema": "flora-synthetic-intervention-v1", "source_id": source["id"],
        "observed_at": normalize_timestamp(source["at"]), "kind": source["kind"], "text": source["text"]})
    parents = () if case["intervention"] == "observed_outcome" else (
        checkpoint.event_by_source_id["mira-2022-family" if case["intervention"] == "relevant_correction"
                                      else "mira-2021-coffee"],)
    raw = runtime.objects.put(payload)
    event = ExperienceEvent.create(event_type="observation" if not parents else "correction",
        scope=runtime.scope, occurred_at=at, content_digest=raw.plaintext_sha256,
        provenance=ProvenanceReference.create(provenance_type="generated_reconstruction",
            source_reference_ids=(source["id"],), derivation_activity_id="flora-native-synthetic-pilot-v1",
        responsible_component="flora-synthetic-pilot"), retention_class="ordinary_experience",
        storage_tier="raw_buffer", payload_reference=raw.object_id, parent_event_ids=parents)
    authorize_append("intervention")
    runtime.log.append(event, expected_revision=len(replay) - 1)
    authorize_append("intervention")  # A slow commit cannot accept a withdrawn transition.
    intervention = RecordedEvent(event, raw)
    audit = None
    if case["intervention"] == "observed_outcome":
        authorize_append("outcome audit")
        audit_raw = runtime.objects.put(canonical_json_bytes({"schema": "flora-synthetic-outcome-audit-v1",
            "original_observation_event_id": event.event_id, "before_decision_event_id": before.native_decision_event_id,
            "observed_at": normalize_timestamp(source["at"]), "causal_claim": "none", "fictional": True}))
        audit_event = ExperienceEvent.create(event_type="outcome", scope=runtime.scope, occurred_at=at,
            content_digest=audit_raw.plaintext_sha256, provenance=ProvenanceReference.create(
                provenance_type="generated_reconstruction", source_reference_ids=(source["id"],),
                derivation_activity_id="flora-native-synthetic-pilot-v1", responsible_component="flora-synthetic-pilot"),
            retention_class="ordinary_experience", storage_tier="raw_buffer", payload_reference=audit_raw.object_id,
            parent_event_ids=(before.native_decision_event_id, event.event_id))
        authorize_append("outcome audit")
        runtime.log.append(audit_event, expected_revision=len(replay))
        authorize_append("outcome audit")
        audit = RecordedEvent(audit_event, audit_raw)
    after_history = HistorySnapshot(runtime.scope, (*history.sources, SourceMaterial(event, payload)))
    return NativePilotTransition(before, after_history, intervention, audit, normalize_timestamp(source["at"]))


async def run_native_pilot_transition(*, path, checkpoint: PilotCheckpoint,
        runtime: FloRAExperimentRuntime, lineage: NativeJudgmentLineageVerifier,
        before_executor: Callable[[PilotCheckpoint], Awaitable[NativeBeforeReference]],
        occurred_at: Callable[[], str],
        phase_snapshot_services: NativePilotPhaseSnapshotServices | None = None) -> NativePilotTransition:
    """Usable supplied-services entry point; inference belongs to the producer.

    The executor must use the qualified native worker route and return exact
    persisted references. Returning convincing text or a supplied verdict does
    not satisfy independent recovery. This entry point does not score a result.
    """
    reference = await before_executor(checkpoint)
    if not isinstance(reference, NativeBeforeReference):
        raise TypeError("native pilot executor must return exact persisted stage references")
    return apply_native_intervention(path=path, checkpoint=checkpoint, reference=reference,
        runtime=runtime, lineage=lineage, occurred_at=occurred_at(), phase_snapshot_services=phase_snapshot_services)
