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
from .artifact_registry import XTDBModelArtifactRegistry
from .claims import XTDBClaimAuthority
from .experiment_runtime import FloRAExperimentRuntime
from .governed_development import XTDBGovernedPersonalDevelopment
from .governed_episodes import XTDBGovernedEpisodes
from .judgment_context import RegisteredJudgmentContextPolicy
from .judgment_lineage import NativeJudgmentLineageVerifier
from .personal_state import _ACTIVE, _VERSIONS
from .personal_artifact_custody import _SourceAuthorizedObjectReads, DurableOwnerProofLookup
from .source_native import _require_available
from .phase_snapshots import SelectedPhaseSnapshot, XTDBPhaseSnapshotCustody, verify_update_policy, PhaseAuthorizedObjectReads


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


class PhaseJudgmentRuntime(FloRAExperimentRuntime):
    """Only judgment/recovery is allowed on this immutable experiment route."""
    def form_experience(self, *args, **kwargs):
        raise PermissionError("phase judgment route cannot run formation or updates")
    admit_proposal = form_experience
    activate_personal_state = form_experience
    run_cycle = form_experience


class _QualifiedPhaseLineage(NativeJudgmentLineageVerifier):
    """Existing actual lineage with the arm's independent update proof too."""
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


class SelectedPhaseRoute:
    """Concrete runtime and lineage, independently rebound on each recovery."""
    def __init__(self, *, custody: XTDBPhaseSnapshotCustody, snapshot_id: str,
                 history, history_authority, historical_bindings, invocation_id_for):
        snapshot = custody.recover(snapshot_id=snapshot_id, history=history, history_authority=history_authority)
        r, live = snapshot.record, custody.runtime
        captured_metadata = custody.metadata(snapshot_id)
        def source_gate():
            if snapshot.snapshot_sha256 != captured_metadata["snapshot_sha256"]:
                raise PermissionError("phase route private immutable manifest changed")
            return custody.authorize(snapshot_id=snapshot_id, history=history,
                history_authority=history_authority, expected=captured_metadata)
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
        runtime = PhaseJudgmentRuntime(artifacts=artifacts, bindings=historical_bindings, claims=claims,
            sources=live.sources, source_policy=live.source_policy, candidates=live.candidates,
            admission=admission, state=state, log=live.log, objects=guarded_objects, references=live.original_references,
            context_policy=context_policy, state_approval_verifier=approval_verifier, clock=live.clock)
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
        lineage = _QualifiedPhaseLineage(runtime=runtime, history_authority=phase_history_authority,
            run_plan_sha256=r["run_plan_sha256"], history_for=history_for,
            invocation_id_for=invocation_id_for, phase_receipt_for=receipt_for)
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
        self.check_live()

    def check_live(self):
        # The constructor authenticated the immutable body and actual selected
        # view. Every model/context use revalidates its actual records/proofs;
        # this fence only needs fresh canonical metadata and live permissions.
        return self._source_gate()


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
                 history_authority, bindings_by_snapshot, snapshots, frozen_native_arms):
        from ..comparison_run import PairedRunPlan
        from .native_arm import NativePhaseSnapshotBinding, FrozenNativeArmPlan
        from .experiment_runtime import RuntimeRoleBinding
        from .comparison_custody import SelectedRunEvidencePolicy
        if not isinstance(custody, XTDBPhaseSnapshotCustody) or not isinstance(run_plan, PairedRunPlan):
            raise TypeError("phase router needs actual selected custody and a frozen paired plan")
        run_plan.validate()
        if (not isinstance(history_authority, SelectedRunEvidencePolicy)
                or history_authority.run_id != custody.run_id
                or history_authority.custody.scope != custody.scope
                or history_authority.custody.authority_namespace_id != custody.authority_namespace_id
                or history_authority.custody.connection is not custody.connection
                or history_authority.permissions.connection is not custody.connection):
            raise TypeError("strict phase router requires actual same-run selected evaluation authority")
        expected = {(case.case_id, phase, arm) for case in run_plan.protocol.cases
            for phase in ("before", "after") for arm in ("flora_full", "same_evidence_ablation")}
        if (set(snapshots) != expected or custody.run_plan_sha256 != run_plan.digest()
                or any(case.host_id != custody.scope.host_instance_id for case in run_plan.protocol.cases)
                or set(histories) != {(case, phase) for case, phase, _ in expected}):
            raise ValueError("phase router lacks the exact complete host/case/phase/arm configuration")
        for key, binding in snapshots.items():
            if not isinstance(binding, NativePhaseSnapshotBinding):
                raise TypeError("phase router requires typed predeclared native snapshot bindings")
            binding.record()
            if binding.run_id != custody.run_id or binding.arm != key[2]:
                raise ValueError("phase snapshot binding crosses frozen run/native arm")
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
        return {"schema": "flora-selected-phase-lineage-router-v1", "scope": self.runtime.scope.metadata_record(),
            "authority_namespace_id": self.runtime.authority_namespace_id, "run_id": self.custody.run_id,
            "run_plan_sha256": self.run_plan_sha256,
            "frozen_native_arms": {arm: frozen.record() for arm, frozen in self.frozen_native_arms.items()},
            "entries": [{"case_id": case, "phase": phase, "arm": arm,
                "snapshot": binding.record(), "history_sha256": self.histories[(case, phase)].digest(),
                "arm_binding": vars(self.run_plan.binding_for(case, phase, arm)),
                "producer_configurations": {role: self._role_configuration(value) for role, value in self.bindings_by_snapshot[binding.snapshot_id].items()}}
                for (case, phase, arm), binding in sorted(self.snapshots.items())]}

    def record(self):
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
        def invocation_id_for(request, result):
            return entry.invocation_id
        route = SelectedPhaseRoute(custody=self.custody, snapshot_id=binding.snapshot_id,
            history=self.history_for(case_id, phase), history_authority=self.history_authority,
            historical_bindings=self.bindings_by_snapshot[binding.snapshot_id], invocation_id_for=invocation_id_for)
        r = route.snapshot.record
        from ..comparison_run import _context_bytes
        import hashlib
        actual_context = route.runtime._context(route.snapshot.plan, authority_guard=route.check_live)
        if (r["run_id"] != binding.run_id or r["case_id"] != case_id or r["phase"] != phase or r["arm"] != arm
                or r["run_plan_sha256"] != self.run_plan_sha256
                or entry.context_plan != route.snapshot.plan
                or hashlib.sha256(_context_bytes(actual_context)).hexdigest() != entry.context_sha256
                or route.runtime._resolve("personality_judgment", authority_guard=route.check_live)[1].checkpoint_sha256
                != self.run_plan.binding_for(case_id, phase, arm).model_artifact_sha256):
            raise PermissionError("actual phase route differs from the frozen tuple/producer checkpoint")
        return route

    def authorize_context(self, *, case_id, phase, history, context, arm):
        route = self.route_for(case_id=case_id, phase=phase, arm=arm)
        if (history != route.history or context.plan != route.snapshot.plan
                or context.receipt_record() != route.snapshot.record["context_receipt"]):
            raise PermissionError("phase router context differs from the exact captured actual input")
        return route.lineage.authorize_context(case_id=case_id, phase=phase, history=history,
            context=context, arm=arm, authority_guard=route.check_live)

    def verify_native_result(self, request, result, *, arm):
        if (request.plan.digest() != self.run_plan_sha256 or request.scope != self.runtime.scope
                or request.binding != self.run_plan.binding_for(request.case_id, request.phase, arm)):
            raise PermissionError("phase router native request differs from its frozen plan/arm binding")
        route = self.route_for(case_id=request.case_id, phase=request.phase, arm=arm)
        if (request.context.plan != route.snapshot.plan
                or request.context.receipt_record() != route.snapshot.record["context_receipt"]):
            raise PermissionError("phase router native execution changed the actual captured context")
        actual = route.lineage.verify_native_result_details(request, result, reconcile=False,
            authority_guard=route.check_live)
        route.check_live()
        return actual.qualified_output
