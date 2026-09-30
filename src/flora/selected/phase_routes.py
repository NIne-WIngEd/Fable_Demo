"""Concrete historical selected views with live source and quarantine barriers.

Only logical experiment read heads are pinned. No canonical production head is
rewound. Immutable versions, evidence, approvals, publications and qualifications
are fetched from the actual selected stores for every use. Producer checkpoint
bytes and exclusion proofs are supplied by their independent model workstream.
"""
from __future__ import annotations

import base64
from copy import copy, deepcopy
from dataclasses import dataclass
import json
from types import MappingProxyType

from cognitive_kernel.canonical import canonical_sha256, require_identifier, require_sha256

from . import artifact_registry as artifact_module
from . import governed_episodes as episode_module
from .artifact_registry import RuntimeWiringManifest, XTDBModelArtifactRegistry
from .claims import XTDBClaimAuthority
from .experiment_runtime import FloRAExperimentRuntime
from .governed_development import XTDBGovernedPersonalDevelopment
from .governed_episodes import XTDBGovernedEpisodes
from .judgment_context import RegisteredJudgmentContextPolicy
from .judgment_lineage import NativeJudgmentLineageVerifier
from .personal_state import _ACTIVE, _VERSIONS
from .personal_artifact_custody import _SourceAuthorizedObjectReads, DurableOwnerProofLookup
from .source_native import _require_available
from .phase_snapshots import (SelectedPhaseSnapshot, XTDBPhaseSnapshotCustody, verify_update_policy,
    PhaseAuthorizedObjectReads, PreregisteredPhaseCaptureLineageVerifier, PreregisteredPhaseArtifactSnapshotRequest)


def _clone(cls, original):
    result = object.__new__(cls)
    result.__dict__.update(original.__dict__)
    result._live = original
    return result


class PinnedClaimAuthority(XTDBClaimAuthority):
    """Pinned historically admitted projections; present quarantine always wins."""
    def _check_claim(self, claim_id):
        value = self._pins.get(claim_id)
        if value is None:
            raise PermissionError("Claim is outside the frozen phase authority")
        present = self._live.load_current(claim_id)
        _require_available(present, claim_id)
        if present["validity_state"] != "current":
            raise PermissionError("live Claim authority no longer permits phase use")
        # Exact physical historical occurrence, not a caller-declared hash.
        history = self._live.current_history(claim_id)
        if not any({key: item[key] for key in value["projection"]} == value["projection"] for item in history):
            raise ValueError("pinned Claim projection never occurred in actual XTDB history")
        if self._live.load_version(value["version"]["claim_version_id"]) != value["version"]:
            raise ValueError("pinned Claim immutable version changed")
        for relation in value["relations"]:
            if self._live.load_evidence_relation(relation["relation_id"]) != relation:
                raise ValueError("pinned Claim immutable evidence changed")
        return value

    def load_current(self, claim_id, *, as_of=None):
        if as_of is not None:
            raise PermissionError("phase view has one exact snapshot, not an arbitrary time selector")
        return deepcopy(self._check_claim(claim_id)["projection"])

    def load_version(self, claim_version_id):
        found = [value for value in self._pins.values() if value["version"]["claim_version_id"] == claim_version_id]
        if len(found) != 1:
            raise PermissionError("Claim version is outside the frozen phase authority")
        return deepcopy(self._check_claim(found[0]["claim_id"])["version"])

    def load_evidence_relation(self, relation_id):
        found = [(value, relation) for value in self._pins.values() for relation in value["relations"] if relation["relation_id"] == relation_id]
        if len(found) != 1:
            raise PermissionError("Claim evidence is outside the frozen phase authority")
        self._check_claim(found[0][0]["claim_id"])
        return deepcopy(found[0][1])

    def put_identity(self, *args, **kwargs):
        raise PermissionError("phase Claim views cannot mutate production authority")
    put_version = put_identity
    put_current = put_identity
    put_evidence_relation = put_identity


class PinnedPersonalState(XTDBGovernedPersonalDevelopment):
    """Existing governed reader over exact actual historical activation heads."""
    def _fetch(self, table, row_id, *, all_valid=False):
        if table == _ACTIVE:
            value = self._pins.get(row_id)
            if value is None:
                return None
            route = value["route"]
            if self._live._history(route["projection_id"], value["version"]["version_id"]) != value["activation"]:
                raise ValueError("pinned state actual activation receipt changed")
            actual = self._live._fetch(_VERSIONS, self._live._version_id(value["version"]["version_id"]), all_valid=True)
            if actual is None or json.loads(str(actual["record_json"])) != value["version"]:
                raise ValueError("pinned state immutable version changed")
            # A removed active authority is not resurrected. A genuine later
            # approved version may replace it without invalidating this phase.
            if self._live._fetch(_ACTIVE, row_id) is None:
                raise PermissionError("live personal-state authority was removed")
            return deepcopy(value["head"])
        return self._live._fetch(table, row_id, all_valid=all_valid)

    def put_candidate(self, *args, **kwargs):
        raise PermissionError("phase state views cannot mutate production authority")
    activate = put_candidate
    register_rollback = put_candidate
    register_outcome_revision = put_candidate


class PinnedAcceptedEpisodes(XTDBGovernedEpisodes):
    """Existing governed publication reader over an exact accepted episode."""
    def _head(self, thread_id):
        value = self._pins.get(thread_id)
        if value is None:
            return None
        actual = self._live._immutable(episode_module._ACCEPTED, self._live._key("accepted-episode", value["episode_id"]))
        if actual != value["publication"]:
            raise ValueError("pinned episode actual publication changed")
        if self._live._head(thread_id) is None:
            raise PermissionError("live accepted-episode authority was removed")
        return deepcopy(value["head"])

    def put_candidate(self, *args, **kwargs):
        raise PermissionError("phase episode views cannot publish production authority")
    accept = put_candidate


class PinnedArtifactRegistry(XTDBModelArtifactRegistry):
    """Exact admitted historical role; actual qualifications still reverify."""
    def _fetch(self, table, key):
        if table == artifact_module._CURRENT:
            found = [value for value in self._pins.values() if self._key("role", value["role"]) == key]
            if len(found) != 1:
                return None
            value = found[0]
            admission = self._live._fetch(artifact_module._ADMISSIONS, self._live._key("artifact", value["head"]["artifact_id"]))
            if admission != value["admission"]:
                raise ValueError("pinned artifact immutable admission changed")
            qualification = self._live._fetch(artifact_module._QUALIFICATIONS, self._live._key("qualification", admission["qualification_id"]))
            if qualification != value["qualification"]:
                raise ValueError("pinned artifact actual qualification custody changed")
            if self._live._fetch(artifact_module._CURRENT, key) is None:
                raise PermissionError("live artifact role was withdrawn")
            return deepcopy(value["head"])
        return self._live._fetch(table, key)

    def admit(self, *args, **kwargs):
        raise PermissionError("phase artifact views cannot admit production roles")


class _AblationCaptureArtifactRegistry(PinnedArtifactRegistry):
    """Only the exact before personality head is pinned for after capture."""
    def _fetch(self, table, key):
        if (table == artifact_module._CURRENT
                and key != self._key("role", "personality_judgment")):
            return self._live._fetch(table, key)
        return super()._fetch(table, key)


def derive_preregistered_ablation_runtime(*, custody, before_snapshot, personality_binding, authority_guard):
    """Keep after memory authority and exact retained before personality bytes."""
    from .experiment_runtime import RuntimeRoleBinding
    if (custody.preregistration is None or not isinstance(personality_binding, RuntimeRoleBinding)
            or before_snapshot.record.get("preregistration_sha256") != custody.preregistration_sha256
            or before_snapshot.record["phase"] != "before" or before_snapshot.record["arm"] != "flora_full"):
        raise PermissionError("ablation capture lacks the actual qualified same-anchor before role")
    live = custody.runtime
    artifacts = _clone(_AblationCaptureArtifactRegistry, live.artifacts)
    artifacts._pins = {item["role"]: deepcopy(item) for item in before_snapshot.record["artifacts"]
        if item["role"] == "personality_judgment"}
    objects = PhaseAuthorizedObjectReads(live.objects, lambda: (authority_guard(), True)[1])
    artifacts.objects = objects
    bindings = dict(live.bindings)
    bindings["personality_judgment"] = personality_binding
    runtime = FloRAExperimentRuntime(artifacts=artifacts, bindings=bindings, claims=live.claims,
        sources=live.sources, source_policy=live.source_policy, candidates=live.candidates, admission=live.admission,
        state=live.state, log=live.log, objects=objects, references=live.original_references,
        context_policy=live.context_policy, state_approval_verifier=live.state_approval_verifier,
        clock=live.clock, vector=live.vector, graph=live.graph)
    runtime._resolve("personality_judgment", authority_guard=authority_guard)
    return runtime


class PhaseJudgmentRuntime(FloRAExperimentRuntime):
    """Only judgment/recovery is allowed on this immutable experiment route."""
    def form_experience(self, *args, **kwargs):
        raise PermissionError("phase judgment route cannot run formation or updates")
    admit_proposal = form_experience
    activate_personal_state = form_experience
    run_cycle = form_experience


class PhaseCaptureRuntime(PhaseJudgmentRuntime):
    """Historical observation before final sealing has no native dispatch."""
    def judge(self, *args, **kwargs):
        raise PermissionError("capture-only phase route cannot execute before actual final binding")
    recover_judgment = judge
    recover_formation = judge


class PreregisteredBeforeProbeRuntime(PhaseJudgmentRuntime):
    """One exact archived before probe, separate from paired evaluation."""
    def _require_probe(self, *, plan, task, invocation_id):
        anchor, record = self._probe_anchor, self._probe_record
        self._probe_source_gate()
        anchor.authorize_before_probe(case_id=record["case_id"], invocation_id=invocation_id,
            history=self._probe_history)
        if (plan != self._probe_context_plan or not isinstance(task, bytes)
                or task != anchor.store.questions[record["case_id"]]):
            raise PermissionError("before probe changed the exact archived context or shared question")
        self._probe_source_gate()

    def judge(self, *, plan, task, invocation_id):
        guard = lambda: self._require_probe(plan=plan, task=task, invocation_id=invocation_id)
        guard()
        result = super().judge(plan=plan, task=task, invocation_id=invocation_id, authority_guard=guard)
        guard()
        return result

    def recover_judgment(self, *, plan, task, invocation_id, reconcile=False, authority_guard=None):
        if reconcile:
            raise PermissionError("archived before probe recovery cannot repair invocation custody")
        def guard():
            self._require_probe(plan=plan, task=task, invocation_id=invocation_id)
            if authority_guard is not None:
                authority_guard()
        guard()
        result = super().recover_judgment(plan=plan, task=task, invocation_id=invocation_id,
            reconcile=False, authority_guard=guard)
        guard()
        return result


class FinalizedPhaseJudgmentRuntime(PhaseJudgmentRuntime):
    """Native use requires the actual sealed plan and its exact invocation."""
    def _require_final_execution(self, *, plan, task, invocation_id):
        import hashlib
        authority, record = self._final_authority, self._final_phase_record
        self._final_source_gate()
        authority.require_evaluation(plan=authority.plan, case_id=record["case_id"],
            phase=record["phase"], arm=record["arm"], invocation_id=invocation_id)
        if (plan != self._final_context_plan or not isinstance(task, bytes)
                or hashlib.sha256(task).hexdigest() != authority.plan.question_sha256_by_case[record["case_id"]]):
            raise PermissionError("final phase execution changed the sealed context/task")
        self._final_source_gate()

    def _qualify_final_execution(self, *, plan, task, invocation_id):
        self._require_final_execution(plan=plan, task=task, invocation_id=invocation_id)
        authority, record = self._final_authority, self._final_phase_record
        authority.authorize_evaluation(plan=authority.plan, case_id=record["case_id"], phase=record["phase"],
            arm=record["arm"], invocation_id=invocation_id)
        self._require_final_execution(plan=plan, task=task, invocation_id=invocation_id)

    def judge(self, *, plan, task, invocation_id):
        qualify = lambda: self._qualify_final_execution(plan=plan, task=task, invocation_id=invocation_id)
        qualify()
        actual = super().judge(plan=plan, task=task, invocation_id=invocation_id,
            authority_guard=lambda: self._require_final_execution(plan=plan, task=task, invocation_id=invocation_id),
            dispatch_guard=qualify)
        qualify()
        return actual

    def recover_judgment(self, *, plan, task, invocation_id, reconcile=False, authority_guard=None):
        if reconcile:
            raise PermissionError("final phase evaluation recovery cannot repair invocation custody")
        self._qualify_final_execution(plan=plan, task=task, invocation_id=invocation_id)
        def guard():
            self._require_final_execution(plan=plan, task=task, invocation_id=invocation_id)
            if authority_guard is not None:
                authority_guard()
        actual = super().recover_judgment(plan=plan, task=task, invocation_id=invocation_id,
            reconcile=False, authority_guard=guard)
        guard()
        self._qualify_final_execution(plan=plan, task=task, invocation_id=invocation_id)
        return actual


class _QualifiedUpdateProof:
    """Actual anchored context plus the arm's independently verified update."""
    def context_lineage(self, **kwargs):
        self._phase_source_gate()
        actual = super().context_lineage(**kwargs)
        self._phase_source_gate()
        verified = verify_update_policy(runtime=self.runtime,
            snapshot_record=self._phase_record, receipt=self._phase_update_receipt,
            authority_guard=self._phase_source_gate)
        if verified != self._phase_record["verified_update_exclusion"]:
            raise PermissionError("actual producer update-exclusion authority changed")
        self._phase_source_gate()
        return actual


class _QualifiedCapturePhaseLineage(_QualifiedUpdateProof, PreregisteredPhaseCaptureLineageVerifier):
    pass


class _QualifiedPhaseLineage(_QualifiedUpdateProof, NativeJudgmentLineageVerifier):
    """Final execution identity reuses exact earlier anchored capture proofs."""
    def _phase_request(self, **kwargs):
        anchor = getattr(self, "_preregistered_capture", None)
        if anchor is None:
            return super()._phase_request(**kwargs)
        if (kwargs["case_id"], kwargs["phase"]) != (anchor["case_id"], anchor["phase"]):
            raise PermissionError("final lineage crosses the exact prior capture slot")
        return PreregisteredPhaseArtifactSnapshotRequest(self.runtime.scope, self.runtime.authority_namespace_id,
            kwargs["case_id"], kwargs["phase"], anchor["arm"], anchor["snapshot_id"], anchor["preregistration_sha256"],
            kwargs["history_digest"], kwargs["original_event_ids"], kwargs["context_lineage_sha256"], kwargs["artifact"])


@dataclass(frozen=True)
class ObservedPhaseBinding:
    """Metadata from an actual qualified route; construction grants no authority."""
    run_id: str
    preregistration_sha256: str
    snapshot_id: str
    snapshot_sha256: str
    event_id: str
    event_sha256: str
    case_id: str
    phase: str
    arm: str
    context_plan: object
    context_sha256: str
    context_lineage_sha256: str
    producer_component: str
    checkpoint_sha256: str
    artifact_manifest_sha256: str
    artifacts: object

    def record(self):
        from .phase_snapshots import plan_record
        for name in ("run_id", "snapshot_id", "event_id", "case_id", "producer_component"):
            require_identifier(getattr(self, name), name)
        for name in ("preregistration_sha256", "snapshot_sha256", "event_sha256", "context_sha256",
                     "context_lineage_sha256", "checkpoint_sha256", "artifact_manifest_sha256"):
            require_sha256(getattr(self, name), name)
        if self.phase not in {"before", "after"} or self.arm not in {"flora_full", "same_evidence_ablation"}:
            raise ValueError("observed binding has an unknown phase/native arm")
        if (set(self.artifacts) != {"memory_formation", "personality_judgment"}
                or any(not isinstance(value, RuntimeWiringManifest) or value.role != role
                    for role, value in self.artifacts.items())
                or self.artifacts["personality_judgment"].checkpoint_sha256 != self.checkpoint_sha256
                or self.artifacts["personality_judgment"].manifest_sha256 != self.artifact_manifest_sha256):
            raise ValueError("observed binding lacks exact typed actual producer artifacts")
        from .judgment_lineage import _artifact_record
        return {"schema": "flora-observed-phase-binding-v1", **vars(self), "context_plan": plan_record(self.context_plan),
            "artifacts": {role: _artifact_record(value) for role, value in self.artifacts.items()}}


class SelectedPhaseRoute:
    """Concrete runtime and lineage, independently rebound on each recovery."""
    def __init__(self, *, custody: XTDBPhaseSnapshotCustody, snapshot_id: str,
                 history, history_authority, historical_bindings, invocation_id_for, final_authority=None):
        preregistered = custody.preregistration is not None
        if final_authority is not None:
            from .experiment_preregistration import RegisteredExperimentFinalBinding
            if (not preregistered or not isinstance(final_authority, RegisteredExperimentFinalBinding)
                    or final_authority.preregistration_sha256 != custody.preregistration_sha256):
                raise TypeError("phase route needs actual matching registered final binding")
            initial = custody.metadata(snapshot_id)
            if initial is None:
                raise PermissionError("final phase route lacks its actual sealed snapshot")
            final_authority.authorize_slot_use(snapshot_id=snapshot_id, case_id=initial["case_id"],
                phase=initial["phase"], arm=initial["arm"], history=history)
            final_authority.authorize_plan(plan=final_authority.plan, metadata_only=False)
            final_authority.authorize_slot_use(snapshot_id=snapshot_id, case_id=initial["case_id"],
                phase=initial["phase"], arm=initial["arm"], history=history)
        snapshot = custody.recover(snapshot_id=snapshot_id, history=history, history_authority=history_authority)
        r, live = snapshot.record, custody.runtime
        if final_authority is not None:
            final_authority.authorize_slot_use(snapshot_id=snapshot_id, case_id=r["case_id"],
                phase=r["phase"], arm=r["arm"], history=history, plan=snapshot.plan)
        captured_metadata = custody.metadata(snapshot_id)
        def source_gate():
            if snapshot.snapshot_sha256 != captured_metadata["snapshot_sha256"]:
                raise PermissionError("phase route private immutable manifest changed")
            custody.authorize(snapshot_id=snapshot_id, history=history,
                history_authority=history_authority, expected=captured_metadata)
            if final_authority is not None:
                final_authority.authorize_slot_use(snapshot_id=snapshot_id, case_id=r["case_id"],
                    phase=r["phase"], arm=r["arm"], history=history, plan=snapshot.plan)
            return True
        guarded_objects = PhaseAuthorizedObjectReads(live.objects, source_gate)
        claims = _clone(PinnedClaimAuthority, live.claims)
        claims._pins = {value["claim_id"]: deepcopy(value) for value in r["claims"]}
        state = _clone(PinnedPersonalState, live.state)
        state._pins = {state._head_id(**value["route"]): deepcopy(value) for value in r["states"]}
        if r["episodes"]:
            if live.state.episodes is None:
                raise ValueError("pinned episodes require actual governed episode service")
            episodes = _clone(PinnedAcceptedEpisodes, live.state.episodes)
            episodes._pins = {value["thread_id"]: deepcopy(value) for value in r["episodes"]}
            state.episodes = episodes
        else:
            state.episodes = None
        artifacts = _clone(PinnedArtifactRegistry, live.artifacts)
        artifacts._pins = {value["role"]: deepcopy(value) for value in r["artifacts"]}
        artifacts.objects = guarded_objects
        context_policy = RegisteredJudgmentContextPolicy(claims=claims, state=state, log=live.log,
            registry=live.sources, permissions=live.source_policy)
        admission = copy(live.admission)
        admission.authority = claims
        approval_verifier = copy(live.state_approval_verifier)
        proofs = getattr(approval_verifier, "proofs", None)
        if isinstance(proofs, DurableOwnerProofLookup):
            lookup = copy(proofs)
            lookup.objects = guarded_objects
            approval_verifier.proofs = lookup
        runtime_type = (PhaseCaptureRuntime if preregistered and final_authority is None
                        else FinalizedPhaseJudgmentRuntime if preregistered else PhaseJudgmentRuntime)
        runtime = runtime_type(artifacts=artifacts, bindings=historical_bindings, claims=claims,
            sources=live.sources, source_policy=live.source_policy, candidates=live.candidates,
            admission=admission, state=state, log=live.log, objects=guarded_objects, references=live.original_references,
            context_policy=context_policy, state_approval_verifier=approval_verifier, clock=live.clock)
        if final_authority is not None:
            runtime._final_authority, runtime._final_phase_record = final_authority, r
            runtime._final_context_plan, runtime._final_source_gate = snapshot.plan, source_gate
        receipts = {value["request_sha256"]: base64.b64decode(value["receipt_base64"], validate=True) for value in r["producer_receipts"]}
        def receipt_for(request):
            value = receipts.get(request.request_sha256)
            if value is None:
                raise PermissionError("producer phase proof is outside exact captured request")
            return value
        def history_for(case_id, phase):
            if (case_id, phase) != (r["case_id"], r["phase"]):
                raise PermissionError("phase route cannot resolve another case/phase")
            return history
        phase_history_authority = custody._checked_history_authority(history_authority,
            lambda: custody._phase_metadata_gate(snapshot_id, captured_metadata))
        if preregistered and final_authority is None:
            lineage = _QualifiedCapturePhaseLineage(runtime=runtime, preregistration=custody.preregistration,
                snapshot_id=snapshot_id, case_id=r["case_id"], phase=r["phase"], arm=r["arm"],
                history_for=history_for, phase_receipt_for=receipt_for)
            lineage.history_authority = phase_history_authority
        else:
            lineage = _QualifiedPhaseLineage(runtime=runtime, history_authority=phase_history_authority,
                run_plan_sha256=r["run_plan_sha256"] if not preregistered else final_authority.final_plan_sha256,
                history_for=history_for, invocation_id_for=invocation_id_for, phase_receipt_for=receipt_for)
            if preregistered:
                lineage._preregistered_capture = r
        update_receipt = None if r["update_receipt_base64"] is None else base64.b64decode(r["update_receipt_base64"], validate=True)
        lineage._phase_record, lineage._phase_update_receipt, lineage._phase_source_gate = r, update_receipt, source_gate
        context = runtime._context(snapshot.plan)
        actual = lineage.context_lineage(case_id=r["case_id"], phase=r["phase"], history=history, context=context)
        if (canonical_sha256(actual.record()) != r["context_lineage_sha256"]
                or context.receipt_record() != r["context_receipt"]):
            raise ValueError("actual pinned context/producer proof differs from captured phase")
        self.custody, self.snapshot, self.history, self.history_authority = custody, snapshot, history, history_authority
        self._captured_metadata = captured_metadata
        self._source_gate = source_gate
        self.runtime, self.lineage = runtime, lineage
        self.final_authority = final_authority
        self.check_live()

    def check_live(self):
        # The constructor authenticated the immutable body and actual selected
        # view. Every model/context use revalidates its actual records/proofs;
        # this fence only needs fresh canonical metadata and live permissions.
        return self._source_gate()

    def guard_live(self):
        """Raise-only authority guard; Boolean source predicates stay separate."""
        self.check_live()

    def observed_binding(self):
        """Reconstruct and qualify actual historical bytes before sealing."""
        if self.custody.preregistration is None:
            raise PermissionError("observed capture binding requires actual preregistration")
        from ..comparison_run import _context_bytes
        import hashlib
        self.check_live()
        context = self.runtime._context(self.snapshot.plan, authority_guard=self.guard_live)
        lineage = self.lineage.context_lineage(case_id=self.snapshot.record["case_id"], phase=self.snapshot.record["phase"],
            history=self.history, context=context, authority_guard=self.guard_live)
        binding, manifest = self.runtime._resolve("personality_judgment", authority_guard=self.guard_live)
        artifacts = MappingProxyType({role: self.runtime._resolve(role, authority_guard=self.guard_live)[1]
            for role in ("memory_formation", "personality_judgment")})
        metadata = self.custody.metadata(self.snapshot.snapshot_id)
        if (lineage.lineage_sha256 != self.snapshot.record["context_lineage_sha256"]
                or context.receipt_record() != self.snapshot.record["context_receipt"]
                or metadata != self._captured_metadata):
            raise PermissionError("observed actual phase binding changed")
        value = ObservedPhaseBinding(self.custody.run_id, self.custody.preregistration_sha256,
            self.snapshot.snapshot_id, self.snapshot.snapshot_sha256, metadata["event_id"], metadata["event_sha256"],
            metadata["case_id"], metadata["phase"], metadata["arm"], self.snapshot.plan,
            hashlib.sha256(_context_bytes(context)).hexdigest(), lineage.lineage_sha256,
            binding.adapter.adapter_id, manifest.checkpoint_sha256, manifest.manifest_sha256, artifacts)
        value.record()
        self.check_live()
        return value


class SelectedBeforeProbeRoute(SelectedPhaseRoute):
    """Actual pinned before-full services with an exact predeclared probe."""
    def __init__(self, *, custody, snapshot_id, case_id, historical_bindings):
        if custody.preregistration is None:
            raise PermissionError("before probe needs the actual registered anchor")
        anchor = custody.preregistration
        declaration = anchor.spec.slot(snapshot_id)
        if (declaration.case_id, declaration.phase, declaration.arm) != (case_id, "before", "flora_full"):
            raise PermissionError("before probe must use the same-case declared before-full snapshot")
        history = anchor.history_for(case_id, "before")
        probe_id = anchor.spec.before_probe_invocation_ids[case_id]
        anchor.authorize_before_probe(case_id=case_id, invocation_id=probe_id, history=history)
        super().__init__(custody=custody, snapshot_id=snapshot_id, history=history,
            history_authority=anchor.history_authority(), historical_bindings=historical_bindings,
            invocation_id_for=lambda *_: (_ for _ in ()).throw(PermissionError("before probe has no paired execution authority")))
        if not isinstance(self.runtime, PhaseCaptureRuntime):
            raise TypeError("before probe requires an actual capture-only historical runtime")
        self.runtime.__class__ = PreregisteredBeforeProbeRuntime
        self.runtime._probe_anchor, self.runtime._probe_record = anchor, self.snapshot.record
        self.runtime._probe_history, self.runtime._probe_context_plan = history, self.snapshot.plan
        self.runtime._probe_source_gate = self.check_live
        self.runtime._require_probe(plan=self.snapshot.plan, task=anchor.store.questions[case_id], invocation_id=probe_id)


@dataclass(frozen=True)
class PhaseSnapshotReference:
    run_id: str
    snapshot_id: str
    snapshot_sha256: str
    event_id: str
    case_id: str
    phase: str
    arm: str

    def record(self):
        for name in ("run_id", "snapshot_id", "event_id", "case_id"):
            if require_identifier(getattr(self, name), name) != getattr(self, name):
                raise ValueError("phase snapshot reference identifier is not canonical")
        require_sha256(self.snapshot_sha256, "snapshot_sha256")
        if self.phase not in {"before", "after"} or self.arm not in {"flora_full", "same_evidence_ablation"}:
            raise ValueError("phase snapshot reference has an unknown arm/phase")
        return {"schema": "flora-phase-snapshot-reference-v1", **vars(self)}


def recognize_phase_snapshot(*, reference: PhaseSnapshotReference, event, custody,
                             history, history_authority, historical_bindings, invocation_id_for):
    """Recognize one qualified internal artifact, never a broad type allowance."""
    reference.record()
    metadata = custody.metadata(reference.snapshot_id)
    if (metadata is None or custody.run_id != reference.run_id
            or any(metadata[name] != getattr(reference, name) for name in ("snapshot_sha256", "event_id", "case_id", "phase", "arm"))
            or metadata["event_sha256"] != event.event_sha256 or event.event_id != reference.event_id
            or event.event_type != "phase_snapshot_artifact"):
        raise PermissionError("lifecycle snapshot reference differs from actual registered internal artifact")
    route = SelectedPhaseRoute(custody=custody, snapshot_id=reference.snapshot_id, history=history,
        history_authority=history_authority, historical_bindings=historical_bindings, invocation_id_for=invocation_id_for)
    route.check_live()
    return reference


class SelectedPhaseLineageRouter:
    """Actual case/phase/arm routes; a header digest alone grants no authority."""
    def __init__(self, *, custody: XTDBPhaseSnapshotCustody, run_plan, histories,
                 history_authority, bindings_by_snapshot, snapshots, frozen_native_arms, final_authority=None):
        from ..comparison_run import PairedRunPlan
        from .native_arm import NativePhaseSnapshotBinding, FrozenNativeArmPlan
        from .experiment_runtime import RuntimeRoleBinding
        from .comparison_custody import SelectedRunEvidencePolicy
        if not isinstance(custody, XTDBPhaseSnapshotCustody) or not isinstance(run_plan, PairedRunPlan):
            raise TypeError("phase router needs actual selected custody and a frozen paired plan")
        run_plan.validate()
        preregistered = custody.preregistration is not None
        if preregistered:
            from .experiment_preregistration import RegisteredExperimentFinalBinding
            if (not isinstance(final_authority, RegisteredExperimentFinalBinding)
                    or final_authority.run_id != custody.run_id
                    or final_authority.scope != custody.scope
                    or final_authority.authority_namespace_id != custody.authority_namespace_id
                    or final_authority.preregistration_sha256 != custody.preregistration_sha256
                    or run_plan.preregistration_sha256 != custody.preregistration_sha256
                    or final_authority.final_plan_sha256 != run_plan.digest()
                    or {arm: value.record() for arm, value in final_authority.native_plans.items()}
                    != {arm: value.record() for arm, value in frozen_native_arms.items()}):
                raise TypeError("preregistered native router requires the actual exact final observed binding")
            final_authority.authorize_plan(plan=run_plan, metadata_only=False)
        elif final_authority is not None or getattr(run_plan, "preregistration_sha256", None) is not None:
            raise PermissionError("legacy final-plan capture cannot impersonate preregistered snapshots")
        if (not isinstance(history_authority, SelectedRunEvidencePolicy)
                or history_authority.run_id != custody.run_id
                or history_authority.custody.scope != custody.scope
                or history_authority.custody.authority_namespace_id != custody.authority_namespace_id
                or history_authority.custody.connection is not custody.connection
                or history_authority.permissions.connection is not custody.connection):
            raise TypeError("strict phase router requires actual same-run selected evaluation authority")
        expected = {(case.case_id, phase, arm) for case in run_plan.protocol.cases
            for phase in ("before", "after") for arm in ("flora_full", "same_evidence_ablation")}
        if (set(snapshots) != expected or (not preregistered and custody.run_plan_sha256 != run_plan.digest())
                or any(case.host_id != custody.scope.host_instance_id for case in run_plan.protocol.cases)
                or set(histories) != {(case, phase) for case, phase, _ in expected}):
            raise ValueError("phase router lacks the exact complete host/case/phase/arm configuration")
        for key, binding in snapshots.items():
            if not isinstance(binding, NativePhaseSnapshotBinding):
                raise TypeError("phase router requires typed predeclared native snapshot bindings")
            binding.record()
            if binding.run_id != custody.run_id or binding.arm != key[2]:
                raise ValueError("phase snapshot binding crosses frozen run/native arm")
            if preregistered and getattr(binding, "preregistration_sha256", None) != custody.preregistration_sha256:
                raise ValueError("native entry lacks its exact preregistration capture reference")
        ids = {binding.snapshot_id for binding in snapshots.values()}
        if len(ids) != len(expected) or set(bindings_by_snapshot) != ids:
            raise ValueError("phase router needs distinct exact snapshot role configurations")
        for roles in bindings_by_snapshot.values():
            if set(roles) != {"memory_formation", "personality_judgment"} or any(not isinstance(value, RuntimeRoleBinding) for value in roles.values()):
                raise TypeError("phase router needs both actual producer RuntimeRoleBindings for every snapshot")
        for history in histories.values():
            if history.scope != custody.scope:
                raise ValueError("phase router history crosses actual selected owner scope")
        if set(frozen_native_arms) != {"flora_full", "same_evidence_ablation"}:
            raise ValueError("strict phase router needs both actual frozen native arm headers")
        entries = {}
        for arm, frozen in frozen_native_arms.items():
            if not isinstance(frozen, FrozenNativeArmPlan):
                raise TypeError("phase router native deployment header is not an actual frozen arm plan")
            frozen.record()
            if (frozen.arm != arm or frozen.scope != custody.scope
                    or frozen.authority_namespace_id != custody.authority_namespace_id
                    or {(entry.case_id, entry.phase) for entry in frozen.entries} != set(histories)):
                raise ValueError("phase router native header crosses exact scope/cases/phases")
            for entry in frozen.entries:
                key = (entry.case_id, entry.phase, arm)
                if (entry.phase_snapshot != snapshots[key]
                        or run_plan.binding_for(*key).lineage_sha256 != frozen.lineage_sha256):
                    raise ValueError("phase router native entry/snapshot/lineage differs from frozen plan")
                entries[key] = entry
        self.custody, self.run_plan, self.history_authority = custody, run_plan, history_authority
        self.final_authority = final_authority
        self.runtime = custody.runtime  # scope anchor; never the judgment read route
        self.run_plan_sha256 = run_plan.digest()
        self.histories = MappingProxyType(dict(histories))
        self.snapshots = MappingProxyType(dict(snapshots))
        self.frozen_native_arms = MappingProxyType(dict(frozen_native_arms))
        self.entries = MappingProxyType(entries)
        self.bindings_by_snapshot = MappingProxyType({key: MappingProxyType(dict(value)) for key, value in bindings_by_snapshot.items()})
        self._record = self._configuration_record()

    @staticmethod
    def _role_configuration(binding):
        codec = binding.codec
        record = {name: getattr(codec, name) for name in (
            "input_contract_id", "input_contract_sha256", "output_contract_id", "output_contract_sha256")}
        for name in ("input_contract_id", "output_contract_id"):
            require_identifier(record[name], name)
        for name in ("input_contract_sha256", "output_contract_sha256"):
            require_sha256(record[name], name)
        record.update(adapter_id=binding.adapter.adapter_id, execution_location=binding.adapter.execution_location)
        require_identifier(record["adapter_id"], "adapter_id")
        require_identifier(record["execution_location"], "execution_location")
        # Class references describe the configured ports; independently
        # qualified deployment/producer proofs establish their authority.
        record["qualification_adapter"] = type(binding.qualification_verifier).__module__ + ":" + type(binding.qualification_verifier).__qualname__
        record["execution_adapter"] = type(binding.execution_verifier).__module__ + ":" + type(binding.execution_verifier).__qualname__
        return record

    def _configuration_record(self):
        record = {"schema": "flora-selected-phase-lineage-router-v1", "scope": self.runtime.scope.metadata_record(),
            "authority_namespace_id": self.runtime.authority_namespace_id, "run_id": self.custody.run_id,
            "run_plan_sha256": self.run_plan_sha256,
            "frozen_native_arms": {arm: frozen.record() for arm, frozen in self.frozen_native_arms.items()},
            "entries": [{"case_id": case, "phase": phase, "arm": arm,
                "snapshot": binding.record(), "history_sha256": self.histories[(case, phase)].digest(),
                "arm_binding": vars(self.run_plan.binding_for(case, phase, arm)),
                "producer_configurations": {role: self._role_configuration(value) for role, value in self.bindings_by_snapshot[binding.snapshot_id].items()}}
                for (case, phase, arm), binding in sorted(self.snapshots.items())]}
        if self.final_authority is not None:
            record["schema"] = "flora-selected-phase-lineage-router-v2"
            record["final_binding"] = {"preregistration_sha256": self.final_authority.preregistration_sha256,
                "final_plan_sha256": self.final_authority.final_plan_sha256,
                "event_id": self.final_authority._record.event_id,
                "event_sha256": self.final_authority._record.record["event_sha256"],
                "record_sha256": self.final_authority._record.record["record_sha256"]}
        return record

    def record(self):
        if self.final_authority is not None:
            self.final_authority.authorize_plan(plan=self.run_plan, metadata_only=True)
        if self.run_plan.digest() != self.run_plan_sha256 or self._configuration_record() != self._record:
            raise PermissionError("phase router frozen configuration changed")
        return deepcopy(self._record)

    @property
    def binding_sha256(self):
        return canonical_sha256(self.record())

    def history_for(self, case_id, phase):
        self.record()
        value = self.histories.get((case_id, phase))
        if value is None:
            raise PermissionError("phase router history is outside its frozen cases")
        return value

    def route_for(self, *, case_id, phase, arm):
        self.record()
        binding = self.snapshots.get((case_id, phase, arm))
        if binding is None:
            raise PermissionError("phase router has no frozen native case/phase/arm")
        entry = self.entries[(case_id, phase, arm)]
        if self.final_authority is not None:
            self.final_authority.require_evaluation(plan=self.run_plan, case_id=case_id, phase=phase,
                arm=arm, invocation_id=entry.invocation_id)
        def invocation_id_for(request, result):
            return entry.invocation_id
        route = SelectedPhaseRoute(custody=self.custody, snapshot_id=binding.snapshot_id,
            history=self.history_for(case_id, phase), history_authority=self.history_authority,
            historical_bindings=self.bindings_by_snapshot[binding.snapshot_id], invocation_id_for=invocation_id_for,
            final_authority=self.final_authority)
        r = route.snapshot.record
        from ..comparison_run import _context_bytes
        import hashlib
        actual_context = route.runtime._context(route.snapshot.plan, authority_guard=route.guard_live)
        capture_identity_matches = (r.get("run_plan_sha256") == self.run_plan_sha256 if self.final_authority is None else
            r.get("preregistration_sha256") == self.final_authority.preregistration_sha256
            and route.snapshot.snapshot_sha256 == binding.snapshot_sha256
            and route._captured_metadata["event_id"] == binding.event_id
            and route._captured_metadata["event_sha256"] == binding.event_sha256)
        if (r["run_id"] != binding.run_id or r["case_id"] != case_id or r["phase"] != phase or r["arm"] != arm
                or not capture_identity_matches
                or entry.context_plan != route.snapshot.plan
                or hashlib.sha256(_context_bytes(actual_context)).hexdigest() != entry.context_sha256
                or route.runtime._resolve("personality_judgment", authority_guard=route.guard_live)[1].checkpoint_sha256
                != self.run_plan.binding_for(case_id, phase, arm).model_artifact_sha256):
            raise PermissionError("actual phase route differs from the frozen tuple/producer checkpoint")
        return route

    def authorize_context(self, *, case_id, phase, history, context, arm):
        route = self.route_for(case_id=case_id, phase=phase, arm=arm)
        if (history != route.history or context.plan != route.snapshot.plan
                or context.receipt_record() != route.snapshot.record["context_receipt"]):
            raise PermissionError("phase router context differs from the exact captured actual input")
        return route.lineage.authorize_context(case_id=case_id, phase=phase, history=history,
            context=context, arm=arm, authority_guard=route.guard_live)

    def verify_native_result(self, request, result, *, arm):
        if (request.plan.digest() != self.run_plan_sha256 or request.scope != self.runtime.scope
                or request.binding != self.run_plan.binding_for(request.case_id, request.phase, arm)):
            raise PermissionError("phase router native request differs from its frozen plan/arm binding")
        route = self.route_for(case_id=request.case_id, phase=request.phase, arm=arm)
        if (request.context.plan != route.snapshot.plan
                or request.context.receipt_record() != route.snapshot.record["context_receipt"]):
            raise PermissionError("phase router native execution changed the actual captured context")
        actual = route.lineage.verify_native_result_details(request, result, reconcile=False,
            authority_guard=route.guard_live)
        route.check_live()
        return actual.qualified_output
