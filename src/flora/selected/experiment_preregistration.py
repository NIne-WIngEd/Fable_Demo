"""Two-stage prepared-synthetic experiment custody, before unknown updates.

The immutable anchor freezes the experiment, contracts and capture/evaluation
identities. Actual qualified captures supply later checkpoints/context hashes.
No model, update, rubric, threshold, source or outcome is generated here.
"""
from __future__ import annotations

from copy import copy, deepcopy
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import json
from types import MappingProxyType
from typing import Callable, Mapping

from cognitive_kernel.canonical import canonical_sha256, normalize_timestamp, require_sha256
from cognitive_kernel.contracts import ProductHostScope

from ..comparator import BaselineConfiguration, encoded, identifier, positive, sha
from ..comparison_run import ArmBinding, HistorySnapshot, PairedRunPlan, _context_bytes
from ..evaluation_protocol import EvaluationProtocol
from .artifact_registry import RuntimeWiringManifest
from .comparison_custody import ComparisonArtifact, SelectedRunEvidencePolicy, XTDBComparisonCustody, evaluation_purpose
from .context import ContextPlan
from .experiment_coordinator import _GuardedLog, _attach_private_fence
from .experiment_manifests import XTDBExperimentManifestCustody, _GuardedObjects, manifest_purpose
from .formation_registry import RegisteredEncryptedFormationCustody
from .native_arm import FrozenNativeArmPlan, NativeInvocationEntry, NativePhaseSnapshotBinding
from .native_worker import NativeWorkerManifest

_NATIVE = frozenset({"flora_full", "same_evidence_ablation"})
_ROLES = frozenset({"memory_formation", "personality_judgment"})
_KINDS = frozenset({"anchor", "slot", "before_seal", "update_gate", "update", "final_seal"})


def preregistration_purpose(run_id: str, operation: str) -> str:
    identifier(run_id, "run_id")
    if operation not in {"capture", "read"}:
        raise ValueError("unknown preregistration operation")
    return "experiment_preregistration_" + operation + ":" + canonical_sha256(run_id)


@dataclass(frozen=True)
class CaptureSlotDeclaration:
    case_id: str
    phase: str
    arm: str
    snapshot_id: str
    capture_invocation_id: str
    evaluation_invocation_id: str
    selection_contract_sha256: str
    update_mode: str

    def record(self):
        for name in ("case_id", "snapshot_id", "capture_invocation_id", "evaluation_invocation_id"):
            identifier(getattr(self, name), name)
        require_sha256(self.selection_contract_sha256, "selection contract")
        expected = "withhold_personal_judgment_update" if self.phase == "after" and self.arm == "same_evidence_ablation" else "full_update"
        if self.phase not in {"before", "after"} or self.arm not in _NATIVE or self.update_mode != expected:
            raise ValueError("capture slot has an invalid exact native phase/update policy")
        return {"schema": "flora-experiment-capture-slot-v1", **vars(self)}


@dataclass(frozen=True)
class NativeArmDeclaration:
    arm: str
    worker: NativeWorkerManifest
    producer_component: str
    update_mechanism: str

    def record(self):
        if self.arm not in _NATIVE or not isinstance(self.worker, NativeWorkerManifest):
            raise TypeError("native declaration requires an actual worker contract")
        identifier(self.producer_component, "producer_component")
        identifier(self.update_mechanism, "update_mechanism")
        return {"arm": self.arm, "worker": self.worker.record(), "producer_component": self.producer_component,
                "update_mechanism": self.update_mechanism}


@dataclass(frozen=True)
class ExperimentPreregistration:
    scope: ProductHostScope
    authority_namespace_id: str
    run_id: str
    protocol: EvaluationProtocol
    question_sha256_by_case: Mapping[str, str]
    context_token_budget: int
    context_byte_budget: int
    feature_call_budget: int
    evidence_kind: str
    comparator: BaselineConfiguration = field(repr=False)
    baseline_design_contract: bytes = field(repr=False)
    native_arms: Mapping[str, NativeArmDeclaration]
    baseline_roles: Mapping[str, RuntimeWiringManifest]
    role_policy_contracts: Mapping[str, bytes] = field(repr=False)
    selection_contract: bytes = field(repr=False)
    update_contract: bytes = field(repr=False)
    baseline_nomination_contract: bytes = field(repr=False)
    slots: tuple[CaptureSlotDeclaration, ...]
    provider_task_ids: Mapping[tuple[str, str], str]
    before_probe_invocation_ids: Mapping[str, str]
    update_invocation_ids: Mapping[str, tuple[str, ...]]

    def record(self):
        self.scope.validate()
        identifier(self.authority_namespace_id, "authority_namespace_id")
        identifier(self.run_id, "run_id")
        if not isinstance(self.protocol, EvaluationProtocol) or not isinstance(self.comparator, BaselineConfiguration):
            raise TypeError("preregistration needs actual protocol and comparator contracts")
        self.protocol.validate()
        expected = {(case.case_id, phase, arm) for case in self.protocol.cases
                    for phase in ("before", "after") for arm in _NATIVE}
        cases = {case.case_id for case in self.protocol.cases}
        if (self.evidence_kind not in {"contract_fixture", "synthetic"}
                or any(case.host_id != self.scope.host_instance_id for case in self.protocol.cases)
                or set(self.question_sha256_by_case) != cases
                or set(self.native_arms) != _NATIVE or set(self.baseline_roles) != _ROLES
                or set(self.role_policy_contracts) != _ROLES
                or set(self.before_probe_invocation_ids) != cases or set(self.update_invocation_ids) != cases
                or set(self.provider_task_ids) != {(case, phase) for case in cases for phase in ("before", "after")}
                or {(slot.case_id, slot.phase, slot.arm) for slot in self.slots} != expected
                or len(self.slots) != len(expected)):
            raise ValueError("preregistration requires one complete prepared synthetic host slice")
        for value in self.question_sha256_by_case.values():
            require_sha256(value, "question hash")
        positive(self.context_token_budget, "context_token_budget")
        positive(self.context_byte_budget, "context_byte_budget")
        if isinstance(self.feature_call_budget, bool) or not isinstance(self.feature_call_budget, int) or self.feature_call_budget < 0:
            raise ValueError("feature call budget must be nonnegative")
        contracts = {"baseline_design": self.baseline_design_contract, "selection": self.selection_contract,
                     "update": self.update_contract, "baseline_nomination": self.baseline_nomination_contract,
                     **{"role:" + role: contract for role, contract in self.role_policy_contracts.items()}}
        if any(not isinstance(value, bytes) or not value for value in contracts.values()):
            raise ValueError("preregistration requires actual supplied policy/selection contract bytes")
        if (sha(self.baseline_design_contract) != self.protocol.baseline_design_sha256
                or self.comparator.provider.feature_engine_id != self.protocol.feature_engine_id):
            raise ValueError("preregistration comparator differs from frozen protocol/design")
        for arm, declaration in self.native_arms.items():
            declaration.record()
            if (declaration.arm != arm or declaration.worker.scope != self.scope
                    or declaration.worker.authority_namespace_id != self.authority_namespace_id):
                raise ValueError("native worker declaration crosses exact host scope")
        for role, artifact in self.baseline_roles.items():
            if not isinstance(artifact, RuntimeWiringManifest) or artifact.role != role or artifact.scope != self.scope:
                raise TypeError("baseline roles need actual typed scoped runtime references")
            for name in ("manifest_sha256", "checkpoint_sha256", "input_contract_sha256", "output_contract_sha256"):
                require_sha256(getattr(artifact, name), name)
            for name in ("artifact_id", "input_contract_id", "output_contract_id", "qualification_id", "qualifier_id"):
                identifier(getattr(artifact, name), name)
            positive(artifact.generation, "baseline generation")
        for slot in self.slots:
            slot.record()
            if slot.selection_contract_sha256 != sha(self.selection_contract):
                raise ValueError("capture slot changed the frozen selection contract")
        all_ids = [slot.snapshot_id for slot in self.slots] + [slot.capture_invocation_id for slot in self.slots] + [slot.evaluation_invocation_id for slot in self.slots]
        all_ids += list(self.provider_task_ids.values()) + list(self.before_probe_invocation_ids.values())
        all_ids += [value for values in self.update_invocation_ids.values() for value in values]
        if len(set(all_ids)) != len(all_ids) or any(not values for values in self.update_invocation_ids.values()):
            raise ValueError("capture/probe/update/evaluation/task identities must be distinct and predeclared")
        for value in all_ids:
            identifier(value, "declared identity")
        return json.loads(encoded({"schema": "flora-experiment-preregistration-v1", "scope": self.scope.metadata_record(),
            "authority_namespace_id": self.authority_namespace_id, "run_id": self.run_id,
            "protocol": self.protocol.record(), "question_sha256_by_case": dict(self.question_sha256_by_case),
            "context_token_budget": self.context_token_budget, "context_byte_budget": self.context_byte_budget,
            "feature_call_budget": self.feature_call_budget, "evidence_kind": self.evidence_kind,
            "comparator": self.comparator.record(), "native_arms": {arm: declaration.record() for arm, declaration in self.native_arms.items()},
            "baseline_roles": {role: {**vars(artifact), "scope": artifact.scope.metadata_record()} for role, artifact in self.baseline_roles.items()},
            "contracts": {name: {"sha256": sha(value), "base64": __import__("base64").b64encode(value).decode()} for name, value in contracts.items()},
            "slots": [slot.record() for slot in sorted(self.slots, key=lambda item: (item.case_id, item.phase, item.arm))],
            "provider_tasks": [{"case_id": case, "phase": phase, "task_id": value} for (case, phase), value in sorted(self.provider_task_ids.items())],
            "before_probe_invocation_ids": dict(self.before_probe_invocation_ids),
            "update_invocation_ids": {case: list(values) for case, values in self.update_invocation_ids.items()},
            "mode": "prepared_synthetic_two_stage"}))

    @property
    def preregistration_sha256(self):
        return canonical_sha256(self.record())

    def slot(self, snapshot_id):
        matches = [slot for slot in self.slots if slot.snapshot_id == snapshot_id]
        if len(matches) != 1:
            raise PermissionError("capture identity is outside the immutable preregistration")
        return matches[0]


class PreregisteredHistoryAuthority(SelectedRunEvidencePolicy):
    """Actual original history authority before a final paired plan exists."""
    def __init__(self, anchor):
        super().__init__(custody=anchor.store._guarded_comparison(anchor.store._current),
                         run_id=anchor.run_id, permissions=anchor.store.permissions)
        self.anchor = anchor
    def authorize_history_metadata(self, *, case_id, phase, history):
        self.anchor.store._current()
        actual = super().authorize_history_metadata(case_id=case_id, phase=phase, history=history)
        self.anchor.store._current()
        return actual
    def authorize_history(self, *, case_id, phase, history):
        self.anchor.store._current()
        actual = super().authorize_history(case_id=case_id, phase=phase, history=history)
        self.anchor.store._current()
        return actual
    def bind_private_guard(self, source_gate):
        selected = copy(self)
        def check():
            self.anchor.store._current()
            if source_gate() is not True:
                raise PermissionError("preregistered history private source guard denied")
            self.anchor.store._current()
        selected.custody = self.anchor.store._guarded_comparison(check)
        return selected


class RegisteredExperimentPreregistration:
    def __init__(self, store, spec, record):
        body = {"schema": "flora-experiment-preregistration-control-v1", "kind": "anchor",
                "preregistration_sha256": spec.preregistration_sha256, "payload": spec.record()}
        if (store.spec.record() != spec.record() or store._metadata("anchor") != record
                or record.record["kind"] != store.control_kind("anchor")
                or record.record["metadata"]["preregistration_sha256"] != spec.preregistration_sha256
                or record.record["content_sha256"] != sha(encoded(body))):
            raise PermissionError("actual preregistration differs from its canonical frozen anchor")
        self.store, self.spec, self._record = store, spec, record
        self.preregistration_sha256, self.run_id = spec.preregistration_sha256, spec.run_id
        self.scope, self.authority_namespace_id, self.protocol = spec.scope, spec.authority_namespace_id, spec.protocol
    @property
    def event_id(self):
        return self._record.event_id
    def history_authority(self):
        self.store._current()
        return PreregisteredHistoryAuthority(self)
    def history_for(self, case_id, phase):
        self.store._current()
        try:
            return self.store.histories[(case_id, phase)]
        except KeyError as error:
            raise PermissionError("history is outside the declared anchor") from error
    def authorize_inputs(self, *, protocol, histories, questions):
        return self.store._authorize_inputs(protocol, histories, questions)
    def authorize_slot_capture(self, **kwargs):
        return self.store._authorize_slot(capture=True, **kwargs)
    def authorize_slot_use(self, **kwargs):
        return self.store._authorize_slot(capture=False, **kwargs)
    def publish_capture(self, *, snapshot_id):
        return self.store.publish_capture(snapshot_id=snapshot_id)
    def authorize_before_probe(self, *, case_id, invocation_id, history):
        self.store._current()
        if (self.spec.before_probe_invocation_ids.get(case_id) != invocation_id
                or history != self.store.histories[(case_id, "before")]
                or self.store._stage("update_gate") is not None or self.store._stage("final_seal") is not None):
            raise PermissionError("before probe changed declared identity/history or passed its allowed stage")
        self.store._deny_evaluation_attempts()
        return True


class RegisteredExperimentFinalBinding:
    def __init__(self, store, plan, native_plans, record):
        if (not isinstance(store, XTDBExperimentPreregistrationCustody) or store.anchor is None
                or not isinstance(plan, PairedRunPlan) or set(native_plans) != _NATIVE
                or any(not isinstance(value, FrozenNativeArmPlan) for value in native_plans.values())
                or store._metadata("final_seal") != record
                or record.record["kind"] != store.control_kind("final_seal")
                or plan.digest() != record.record["metadata"]["final_plan_sha256"]
                or plan.preregistration_sha256 != store.anchor.preregistration_sha256):
            raise PermissionError("actual final authority differs from its canonical sealed plan")
        payload = store._final_payload(plan, native_plans, record.record["metadata"]["slot_records"])
        body = {"schema": "flora-experiment-preregistration-control-v1", "kind": "final_seal",
                "preregistration_sha256": store.anchor.preregistration_sha256, "payload": payload}
        if sha(encoded(body)) != record.record["content_sha256"]:
            raise PermissionError("actual final authority native plans differ from sealed canonical payload")
        self.store, self.plan, self.native_plans, self._record = store, plan, MappingProxyType(dict(native_plans)), record
        self.preregistration_sha256, self.final_plan_sha256 = store.anchor.preregistration_sha256, plan.digest()
        self.run_id, self.scope, self.authority_namespace_id = store.run_id, store.scope, store.namespace
    def authorize_plan(self, *, plan, histories=None, questions=None, metadata_only=False):
        if getattr(self, "_metadata_read_binding", False) and not metadata_only:
            raise PermissionError("owned metadata authority cannot open producer proofs")
        self.store._current()
        payload = self.store._final_payload(self.plan, self.native_plans, self._record.record["metadata"]["slot_records"])
        body = {"schema": "flora-experiment-preregistration-control-v1", "kind": "final_seal",
                "preregistration_sha256": self.preregistration_sha256, "payload": payload}
        if (self.store._metadata("final_seal") != self._record or plan.digest() != self.final_plan_sha256
                or self.final_plan_sha256 != self._record.record["metadata"]["final_plan_sha256"]
                or sha(encoded(body)) != self._record.record["content_sha256"]
                or plan.preregistration_sha256 != self.preregistration_sha256):
            raise PermissionError("final plan differs from its single assigned observed seal")
        if histories is not None or questions is not None:
            self.store._authorize_inputs(plan.protocol, histories, questions)
        self.store._verify_slot_table(private=not metadata_only)
        self.store._current()
        return True
    def authorize_slot_use(self, **kwargs):
        self.authorize_plan(plan=self.plan, metadata_only=True)
        reference = self.store._authorize_slot(capture=False, **kwargs)
        captured = self.store._metadata("slot", kwargs["snapshot_id"])
        expected = self._record.record["metadata"]["slot_records"].get(kwargs["snapshot_id"])
        if captured is None or captured.record["record_sha256"] != expected:
            raise PermissionError("final seal does not bind this exact observed capture")
        return reference
    def require_evaluation(self, *, plan, case_id, phase, arm, invocation_id):
        self.authorize_plan(plan=plan, metadata_only=True)
        if arm in _NATIVE:
            expected = next(slot.evaluation_invocation_id for slot in self.store.spec.slots
                            if (slot.case_id, slot.phase, slot.arm) == (case_id, phase, arm))
        elif arm == "general_model_memory":
            expected = self.store.spec.provider_task_ids[(case_id, phase)]
        else:
            raise PermissionError("unknown final evaluation arm")
        if invocation_id != expected:
            raise PermissionError("evaluation did not use its predeclared frozen identity")
        return True
    def authorize_evaluation(self, *, plan, case_id, phase, arm, invocation_id):
        """Outer dispatch/acceptance gate requalifies actual private proofs.

        Inner raw-I/O guards use require_evaluation instead: recursively opening
        every captured proof while decrypting that proof would be invalid.
        """
        self.require_evaluation(plan=plan, case_id=case_id, phase=phase, arm=arm, invocation_id=invocation_id)
        self.authorize_plan(plan=plan, metadata_only=False)
        self.require_evaluation(plan=plan, case_id=case_id, phase=phase, arm=arm, invocation_id=invocation_id)
        return True
    def authorize_attempt_capture(self, *, plan, case_id, phase, arm, invocation_id):
        """Identity/custody gate for an already observed signed provider call.

        Independent local attempt-capture consent is checked by the actual
        ledger. This never permits dispatch, inference or result acceptance.
        Evaluation/external disclosure may have been withdrawn meanwhile.
        """
        self.authorize_capture_custody(plan=plan)
        if (arm != "general_model_memory" or self.store.spec.provider_task_ids.get((case_id, phase)) != invocation_id):
            raise PermissionError("observed provider capture changed exact final task identity")
        return True

    def authorize_capture_custody(self, *, plan):
        """Metadata-first custody gate before the exact private task is read."""
        payload = self.store._final_payload(self.plan, self.native_plans, self._record.record["metadata"]["slot_records"])
        body = {"schema": "flora-experiment-preregistration-control-v1", "kind": "final_seal",
                "preregistration_sha256": self.preregistration_sha256, "payload": payload}
        if (plan.digest() != self.final_plan_sha256 or plan.preregistration_sha256 != self.preregistration_sha256
                or self.final_plan_sha256 != self._record.record["metadata"]["final_plan_sha256"]
                or sha(encoded(body)) != self._record.record["content_sha256"]
                or self.store._metadata("final_seal") != self._record):
            raise PermissionError("capture custody changed exact sealed run identity")
        self.store._current(include_evaluation=False)
        self.store._verify_slot_table(private=False, include_evaluation=False)
        self.store._current(include_evaluation=False)
        return True
    def bind_read_connection(self, connection, *, phase_custody=None, historical_bindings_by_snapshot=None):
        """Rebind metadata guards to an actual owned SELECT-only connection.

        Full producer qualification remains the supplied session/outer adapter's
        job. This does not guess how to clone external codecs or model ports.
        Independently located source databases require their own owned reader.
        """
        from .native_reads import ReadOnlyNativeSQLConnection
        from .experiment_manifests import SelectedSourceAuthority
        if not isinstance(connection, ReadOnlyNativeSQLConnection):
            raise TypeError("final read guard requires an actual owned native SQL connection")
        original = self.store
        manifests = copy(original.manifests)
        authorities = {}
        for authority_id, actual in original.manifests.authorities.items():
            if (getattr(actual.registry, "connection", original.comparison.connection) is not original.comparison.connection
                    or getattr(actual.permissions, "connection", original.comparison.connection) is not original.comparison.connection):
                raise PermissionError("final source closure needs separate owned backend readers")
            registry, permissions = copy(actual.registry), copy(actual.permissions)
            registry.connection = permissions.connection = connection
            permissions.registry = registry
            authorities[authority_id] = SelectedSourceAuthority(registry, actual.log, permissions, actual.objects)
        manifests.connection, manifests.authorities = connection, authorities
        manifests.local = authorities[original.manifests.local.authority_id]
        selected = copy(original.comparison)
        selected.connection, selected.registry = connection, manifests.local.registry
        selected.raw_custody = RegisteredEncryptedFormationCustody(registry=selected.registry, objects=selected.objects)
        owned = copy(original)
        owned.comparison, owned.manifests, owned.permissions = selected, manifests, manifests.local.permissions
        owned._controllers = (selected.registry, selected.log, selected.objects, owned.permissions, connection)
        owned.anchor = RegisteredExperimentPreregistration(owned, owned.spec, original.anchor._record)
        if original.phase_custody is not None:
            phase = copy(original.phase_custody)
            phase.connection, phase.preregistration = connection, owned.anchor
            phase.runtime = copy(phase.runtime)
            phase.runtime.sources, phase.runtime.source_policy = selected.registry, owned.permissions
            phase.artifact_permissions = copy(original.phase_custody.artifact_permissions)
            phase.artifact_permissions.connection, phase.artifact_permissions.registry = connection, selected.registry
            owned.phase_custody = phase
        result = RegisteredExperimentFinalBinding(owned, self.plan, self.native_plans, self._record)
        if phase_custody is None:
            if historical_bindings_by_snapshot is not None:
                raise ValueError("historical read ports require their actual owned phase controller")
            result._metadata_read_binding = True
        else:
            from .phase_snapshots import XTDBPhaseSnapshotCustody
            from .experiment_runtime import RuntimeRoleBinding
            phase_runtime = phase_custody.runtime
            if (not isinstance(phase_custody, XTDBPhaseSnapshotCustody) or phase_custody.connection is not connection
                    or phase_custody.run_id != self.run_id or phase_custody.preregistration is None
                    or phase_custody.preregistration.preregistration_sha256 != self.preregistration_sha256
                    or phase_runtime.log is not original.comparison.log
                    or phase_runtime.sources.scope != self.scope
                    or phase_runtime.sources.authority_namespace_id != self.authority_namespace_id
                    or phase_runtime.sources.connection is not connection
                    or phase_runtime.source_policy.registry is not phase_runtime.sources
                    or phase_runtime.source_policy.connection is not connection
                    or phase_runtime.objects.scope != self.scope
                    or phase_runtime.objects.namespace != original.comparison.objects.namespace
                    or historical_bindings_by_snapshot is None
                    or set(historical_bindings_by_snapshot) != {slot.snapshot_id for slot in original.spec.slots}
                    or any(set(roles) != _ROLES or any(not isinstance(binding, RuntimeRoleBinding) for binding in roles.values())
                           for roles in historical_bindings_by_snapshot.values())):
                raise PermissionError("full proof reader lacks exact initialized owned phase/producer services")
            # Native context guards may later wrap their own runtime policy.
            # Final metadata predicates must use an independent actual policy
            # view on this same owned connection, never that mutable wrapper.
            independent_permissions = copy(phase_runtime.source_policy)
            independent_permissions.registry = phase_runtime.sources
            local = SelectedSourceAuthority(phase_runtime.sources, phase_runtime.log, independent_permissions, phase_runtime.objects)
            authorities[local.authority_id] = local
            manifests.local = local
            selected.registry, selected.objects = local.registry, local.objects
            selected.raw_custody = RegisteredEncryptedFormationCustody(registry=selected.registry, objects=selected.objects)
            owned.permissions = local.permissions
            owned._controllers = (local.registry, local.log, local.objects, local.permissions, connection)
            phase = copy(phase_custody)
            phase.preregistration = owned.anchor
            owned.phase_custody = phase
            owned.historical_bindings = {key: MappingProxyType(dict(value)) for key, value in historical_bindings_by_snapshot.items()}
            result._metadata_read_binding = False
        result.authorize_plan(plan=self.plan, metadata_only=True)
        return result


class XTDBExperimentPreregistrationCustody:
    def __init__(self, *, comparison: XTDBComparisonCustody, manifests: XTDBExperimentManifestCustody,
                 cohort_id: str, recipe_id: str, permissions, clock: Callable[[], str]):
        if (not isinstance(comparison, XTDBComparisonCustody) or not isinstance(manifests, XTDBExperimentManifestCustody)
                or comparison.registry is not manifests.local.registry or comparison.log is not manifests.local.log
                or comparison.objects is not manifests.local.objects or comparison.connection is not manifests.connection
                or permissions is not manifests.local.permissions):
            raise ValueError("preregistration needs exact actual selected controllers and owner policy")
        identifier(cohort_id, "cohort_id")
        identifier(recipe_id, "recipe_id")
        self.comparison, self.manifests, self.permissions, self.clock = comparison, manifests, permissions, clock
        self.scope, self.namespace = comparison.scope, comparison.authority_namespace_id
        self.cohort_id, self.recipe_id = cohort_id, recipe_id
        self.dependencies = {kind: manifests.metadata(kind, value) for kind, value in (("cohort", cohort_id), ("recipe", recipe_id))}
        if any(record is None for record in self.dependencies.values()):
            raise ValueError("preregistration cohort/recipe must already be registered")
        self.phase_custody = None
        self.spec = self.anchor = self.run_id = None
        self._spec_record = self._histories_record = self._questions_record = None
        self._source_gates = ()
        self._controllers = (comparison.registry, comparison.log, comparison.objects, permissions, comparison.connection)
        self._repair_target = ContextVar("flora_preregistration_repair_" + str(id(self)), default=None)

    @staticmethod
    def artifact_id(kind, snapshot_id=None):
        if kind not in _KINDS or (kind == "slot") != (snapshot_id is not None):
            raise ValueError("unknown preregistration control identity")
        if snapshot_id is not None:
            identifier(snapshot_id, "snapshot_id")
        if kind == "anchor":
            return "preregistration"
        if kind == "final_seal":
            return "final_binding"
        return "preregistration:" + kind + (":" + snapshot_id if snapshot_id is not None else "")

    @staticmethod
    def control_kind(kind):
        return "preregistration_final_binding" if kind == "final_seal" else "preregistration_" + kind

    def _metadata(self, kind, snapshot_id=None):
        return self.comparison.metadata(self.run_id, self.artifact_id(kind, snapshot_id))

    def _stage(self, kind, snapshot_id=None):
        """A committed append without its index cannot permit a later stage."""
        record = self._metadata(kind, snapshot_id)
        activity = "comparison:" + self.comparison._key(self.run_id, self.artifact_id(kind, snapshot_id))
        committed = [item for item in self.comparison.log.replay_committed()
                     if item.event.provenance.derivation_activity_id == activity]
        if record is None and committed and self._repair_target.get() != (kind, snapshot_id):
            raise PermissionError("canonical preregistration stage requires explicit index reconciliation")
        if record is not None:
            self._canonical(record)
        return record

    @contextmanager
    def _repair(self, kind, snapshot_id, enabled):
        # Only an explicit repair operation can temporarily observe its own
        # missing index. Other incomplete stages continue to block every route.
        token = self._repair_target.set((kind, snapshot_id) if enabled else None)
        try:
            yield
        finally:
            self._repair_target.reset(token)

    def _current(self, *, operation=None, parents=(), include_evaluation=True):
        local = self.manifests.local
        if (self._controllers != (local.registry, local.log, local.objects, self.permissions, self.comparison.connection)
                or self.comparison.registry is not local.registry or self.comparison.log is not local.log
                or self.comparison.objects is not local.objects or self.permissions is not local.permissions):
            raise PermissionError("preregistration actual controller identity changed")
        for kind, frozen in self.dependencies.items():
            current = self.manifests.metadata(kind, frozen["manifest_id"])
            if current != frozen:
                raise PermissionError("preregistration dependency changed")
            self.manifests._check_gates(current["source_gates"])
            self.manifests._check_dependencies(current["dependencies"])
            if self.permissions.permits(local.registry.lookup(current["event_id"]), manifest_purpose(self.manifests.experiment_id, "read")) is not True:
                raise PermissionError("preregistration dependency read was withdrawn")
        if include_evaluation:
            self.manifests._check_gates(self._source_gates)
        if self.spec is not None and (self.spec.record() != self._spec_record
                or {key: history.digest() for key, history in self.histories.items()} != self._histories_record
                or {key: sha(value) for key, value in self.questions.items()} != self._questions_record):
            raise PermissionError("immutable preregistration/source configuration changed")
        if self.anchor is not None and self._metadata("anchor") != self.anchor._record:
            raise PermissionError("canonical preregistration anchor changed")
        if operation is not None:
            for event_id in parents:
                if self.permissions.permits(local.registry.lookup(event_id), preregistration_purpose(self.run_id, operation)) is not True:
                    raise PermissionError("preregistration control purpose is not currently allowed")
        for frozen in self.dependencies.values():
            self.manifests._check_gates(frozen["source_gates"])
        if include_evaluation:
            self.manifests._check_gates(self._source_gates)

    def _guarded_comparison(self, check):
        selected = copy(self.comparison)
        selected.objects = _GuardedObjects(selected.objects, check)
        selected.raw_custody = RegisteredEncryptedFormationCustody(registry=selected.registry, objects=selected.objects)
        selected.log = _GuardedLog(selected.log, check)
        return selected

    def _canonical(self, artifact):
        found = [item for item in self.comparison.log.replay_committed() if item.event.event_id == artifact.event_id]
        if len(found) != 1 or found[0].event.event_sha256 != artifact.record["event_sha256"]:
            raise PermissionError("preregistration control lacks exact committed canonical position")
        return found[0]

    def _put(self, kind, payload, *, parents=(), snapshot_id=None, reconcile=False, metadata=None):
        artifact_id = self.artifact_id(kind, snapshot_id)
        base = tuple(record["event_id"] for record in self.dependencies.values())
        if self.anchor is not None and kind != "anchor":
            base += (self.anchor.event_id,)
        parents = tuple(sorted(set((*base, *parents))))
        body = {"schema": "flora-experiment-preregistration-control-v1", "kind": kind,
                "preregistration_sha256": self.spec.preregistration_sha256, "payload": payload}
        prior = self._metadata(kind, snapshot_id)
        activity = "comparison:" + self.comparison._key(self.run_id, artifact_id)
        orphan = any(item.event.provenance.derivation_activity_id == activity for item in self.comparison.log.replay_committed())
        if prior is None and orphan and not reconcile:
            raise PermissionError("canonical preregistration append needs explicit index reconciliation")
        def check():
            self._current(operation="capture", parents=parents)
        check()
        result = self._guarded_comparison(check)._put(run_id=self.run_id, artifact_id=artifact_id,
            kind=self.control_kind(kind), content=encoded(body), parents=parents,
            metadata={"preregistration_sha256": self.spec.preregistration_sha256, "kind": kind, **(metadata or {})},
            occurred_at=normalize_timestamp(self.clock()))
        check()
        return result

    def register(self, *, spec: ExperimentPreregistration, histories, questions, reconcile=False):
        if not isinstance(spec, ExperimentPreregistration):
            raise TypeError("preregistration requires the actual typed immutable experiment")
        spec.record()
        if spec.scope != self.scope or spec.authority_namespace_id != self.namespace:
            raise ValueError("preregistration crosses actual selected host")
        expected = {(case.case_id, phase) for case in spec.protocol.cases for phase in ("before", "after")}
        if set(histories) != expected or set(questions) != set(spec.question_sha256_by_case):
            raise ValueError("preregistration source matrix differs from prepared protocol")
        if self.spec is not None and spec.record() != self._spec_record:
            raise ValueError("registered preregistration is immutable")
        self.spec, self.run_id = spec, spec.run_id
        self.histories, self.questions = MappingProxyType(dict(histories)), MappingProxyType(dict(questions))
        self._spec_record = spec.record()
        self._histories_record = {key: history.digest() for key, history in histories.items()}
        self._questions_record = {key: sha(value) for key, value in questions.items()}
        if any(self._questions_record[case] != digest for case, digest in spec.question_sha256_by_case.items()):
            raise ValueError("preregistration shared question differs from frozen source")
        gates = []
        for case in spec.protocol.cases:
            before, after = histories[(case.case_id, "before")], histories[(case.case_id, "after")]
            if (before.scope != self.scope or after.scope != self.scope
                    or after.sources[:len(before.sources)] != before.sources
                    or before.digest() != case.before_history_sha256 or after.digest() != case.after_history_sha256
                    or case.intervention_event_id in before.event_ids or case.intervention_event_id not in after.event_ids):
                raise ValueError("prepared original history does not match exact preregistration")
            for phase, history in (("before", before), ("after", after)):
                for source in history.sources:
                    gate = self.manifests._gate(self.manifests.local.authority_id, source.event.event_id,
                        evaluation_purpose(self.run_id, case.case_id, phase))
                    binding = self.manifests.local.binding(source.event.event_id)
                    item = next(item for item in binding["closure"] if item["event_id"] == source.event.event_id)
                    if item["content_sha256"] != sha(source.plaintext) or item["event_sha256"] != source.event.event_sha256:
                        raise ValueError("preregistration original lacks exact actual source custody")
                    gates.append(gate)
        self._source_gates = tuple(gates)
        self._current()
        cohort = self.manifests.recover(kind="cohort", manifest_id=self.cohort_id)
        entries = cohort["cohort"]["entries"]
        for history in histories.values():
            for source in history.sources:
                matches = [entry for entry in entries if entry["authority_id"] == self.manifests.local.authority_id
                           and entry["event_id"] == source.event.event_id and entry["usage_role"] == "authorized_history"]
                if len(matches) != 1:
                    raise ValueError("prepared history lacks one exact actual local cohort source")
        for case, content in questions.items():
            matches = [entry for entry in entries if entry["authority_id"] == self.manifests.local.authority_id
                       and entry["usage_role"] == "question"
                       and self.manifests.local.registry.lookup(entry["event_id"]).evidence.content_digest == sha(content)]
            if len(matches) != 1:
                raise ValueError("prepared question lacks one exact actual local cohort source")
            for phase in ("before", "after"):
                gates.append(self.manifests._gate(self.manifests.local.authority_id, matches[0]["event_id"],
                             evaluation_purpose(self.run_id, case, phase)))
        self._source_gates = tuple(gates)
        self._current()
        recipe = self.manifests.recover(kind="recipe", manifest_id=self.recipe_id)
        if recipe["cohort_id"] != self.cohort_id or spec.protocol.builder_recipe_sha256 != self.dependencies["recipe"]["content_sha256"]:
            raise ValueError("preregistration does not bind its actual registered recipe")
        self._deny_evaluation_attempts()
        if self.comparison.metadata(self.run_id, "plan") is not None and self._metadata("anchor") is None:
            raise PermissionError("legacy final plan already occupies this run before preregistration")
        record = self._put("anchor", self._spec_record, reconcile=reconcile)
        self.anchor = RegisteredExperimentPreregistration(self, spec, record)
        return self.anchor

    def _authorize_inputs(self, protocol, histories, questions):
        self._current()
        if (not isinstance(protocol, EvaluationProtocol) or protocol.digest() != self.spec.protocol.digest()
                or histories is None or questions is None
                or {key: history.digest() for key, history in histories.items()} != self._histories_record
                or {key: sha(value) for key, value in questions.items()} != self._questions_record):
            raise PermissionError("registered original inputs differ from immutable preregistration")
        self._current()
        return True

    def register_original_inputs(self, *, occurred_at):
        """Explicit actual custody step after anchor capture consent is granted."""
        if self.anchor is None:
            raise PermissionError("original input registration requires the canonical anchor")
        def check():
            self._current(operation="capture", parents=(self.anchor.event_id,))
        check()
        selected = self._guarded_comparison(check)
        result = selected.register_preregistered_inputs(run_id=self.run_id, preregistration=self.anchor,
            histories=self.histories, questions=self.questions, occurred_at=occurred_at)
        check()
        return result

    def register_final_inputs(self, *, final_authority, occurred_at):
        if (not isinstance(final_authority, RegisteredExperimentFinalBinding)
                or final_authority.store is not self):
            raise TypeError("final input registration requires this actual registered final authority")
        final_authority.authorize_plan(plan=final_authority.plan, metadata_only=False)
        def check():
            final_authority.authorize_plan(plan=final_authority.plan, metadata_only=True)
            self._current(operation="capture", parents=(final_authority._record.event_id,))
        check()
        result = self._guarded_comparison(check).register_inputs(run_id=self.run_id, plan=final_authority.plan,
            histories=self.histories, questions=self.questions, occurred_at=occurred_at, final_authority=final_authority)
        check()
        return result

    def bind_phase_custody(self, phase_custody, *, historical_bindings_by_snapshot=None):
        from .phase_snapshots import XTDBPhaseSnapshotCustody
        if (not isinstance(phase_custody, XTDBPhaseSnapshotCustody) or self.anchor is None
                or phase_custody.preregistration is not self.anchor
                or phase_custody.runtime.sources is not self.comparison.registry
                or phase_custody.runtime.log is not self.comparison.log
                or phase_custody.runtime.objects is not self.comparison.objects
                or phase_custody.connection is not self.comparison.connection):
            raise ValueError("phase custody is not the actual controller bound to this canonical anchor")
        if self.phase_custody is not None and self.phase_custody is not phase_custody:
            raise ValueError("preregistration phase controller is immutable")
        historical_bindings_by_snapshot = historical_bindings_by_snapshot or {}
        self.phase_custody = phase_custody
        if not hasattr(self, "historical_bindings"):
            self.historical_bindings = {}
        for snapshot_id, bindings in historical_bindings_by_snapshot.items():
            self.bind_historical_bindings(snapshot_id=snapshot_id, bindings=bindings)
        self._current()

    def bind_historical_bindings(self, *, snapshot_id, bindings):
        """Enroll actual configured producer ports once their files exist.

        Future checkpoint hashes are never guessed in the anchor. The actual
        capture route subsequently qualifies these files and frozen contracts.
        """
        from .experiment_runtime import RuntimeRoleBinding
        self._current()
        self.spec.slot(snapshot_id)
        if (self.phase_custody is None or set(bindings) != _ROLES
                or any(not isinstance(binding, RuntimeRoleBinding) for binding in bindings.values())):
            raise TypeError("capture observation requires actual historical bindings for both roles")
        previous = self.historical_bindings.get(snapshot_id)
        frozen = MappingProxyType(dict(bindings))
        if previous is not None and previous != frozen:
            raise ValueError("enrolled historical producer bindings are immutable per capture")
        self.historical_bindings[snapshot_id] = frozen
        self._current()

    def _authorize_slot(self, *, capture, snapshot_id, case_id, phase, arm, history, plan=None):
        self._current()
        if self.anchor is None:
            raise PermissionError("capture requires a registered immutable anchor")
        slot = self.spec.slot(snapshot_id)
        if ((slot.case_id, slot.phase, slot.arm) != (case_id, phase, arm)
                or history != self.histories[(case_id, phase)]):
            raise PermissionError("phase use changed exact declared slot or original history")
        if plan is not None:
            if not isinstance(plan, ContextPlan) or plan.purpose != "personal_judgment":
                raise TypeError("capture selection requires an actual personal context plan")
            plan.validate()
        before, gate, update, final = (self._stage(kind) for kind in ("before_seal", "update_gate", "update", "final_seal"))
        if capture:
            self._deny_evaluation_attempts()
            if self._metadata("slot", snapshot_id) is not None or final is not None:
                raise PermissionError("declared capture slot is already frozen")
            if phase == "before" and (before is not None or gate is not None):
                raise PermissionError("before capture cannot follow sealed-before/update")
            if phase == "after" and (before is None or gate is None or update is None):
                raise PermissionError("after capture requires canonical before seal and independently qualified update")
        self._current()
        return {"preregistration_sha256": self.anchor.preregistration_sha256, "anchor_event_id": self.anchor.event_id,
                "slot": slot.record(), "before_seal_event_id": None if before is None else before.event_id,
                "update_gate_event_id": None if gate is None else gate.event_id,
                "update_event_id": None if update is None else update.event_id}

    def _deny_evaluation_attempts(self):
        if self.spec is None:
            return
        evaluation_ids = {slot.evaluation_invocation_id for slot in self.spec.slots}
        for entry in self.comparison.log.replay_committed():
            event = entry.event
            if (event.provenance.derivation_activity_id in evaluation_ids
                    and event.event_type in {"qualified_model_input", "qualified_model_output", "qualified_model_attempt_failure", "decision"}):
                raise PermissionError("frozen paired evaluation already ran before final seal")
        for artifact_id in ("coordinator:running", "coordinator:interrupted", "run"):
            if self.comparison.metadata(self.run_id, artifact_id) is not None:
                raise PermissionError("same run already has attempted evaluation custody")
        from .provider_attempt_custody import _TABLE as provider_table
        from .claims import _rows
        for task in self.spec.provider_task_ids.values():
            key = canonical_sha256([self.comparison.scope_digest, self.run_id, task, "task"])
            if _rows(self.comparison.connection.execute(f"SELECT * FROM {provider_table} FOR VALID_TIME ALL WHERE _id = %s", (key,))):
                raise PermissionError("provider evaluation task already exists before final seal")

    def _observation(self, snapshot_id):
        if self.phase_custody is None:
            raise PermissionError("actual qualified phase capture controller is unavailable")
        if snapshot_id not in self.historical_bindings:
            raise PermissionError("actual historical producer ports are unavailable for this capture")
        slot = self.spec.slot(snapshot_id)
        history = self.histories[(slot.case_id, slot.phase)]
        if slot.phase == "after":
            self._verify_update()
        metadata = self.phase_custody.metadata(snapshot_id)
        if metadata is None:
            raise PermissionError("declared slot has no actual registered capture")
        self._authorize_slot(capture=False, snapshot_id=snapshot_id, case_id=slot.case_id, phase=slot.phase, arm=slot.arm, history=history)
        # The phase owner reconstructs historical selected authority and actual
        # producer qualifications, not a shape-only stored body.
        custody = copy(self.phase_custody)
        custody.runtime = copy(custody.runtime)
        _attach_private_fence(custody.runtime, self._current)
        capture_route = custody.capture_route(snapshot_id=snapshot_id, history_authority=self.anchor.history_authority(),
            historical_bindings=self.historical_bindings[snapshot_id])
        observation = capture_route.observed_binding()
        from .phase_routes import ObservedPhaseBinding
        if not isinstance(observation, ObservedPhaseBinding):
            raise TypeError("capture route returned no actual typed qualified observation")
        self._current()
        if (observation.snapshot_id != snapshot_id or observation.case_id != slot.case_id
                or observation.phase != slot.phase or observation.arm != slot.arm
                or observation.run_id != self.run_id
                or observation.preregistration_sha256 != self.anchor.preregistration_sha256
                or observation.producer_component != self.spec.native_arms[slot.arm].producer_component):
            raise PermissionError("qualified capture observation differs from exact declared slot")
        for role, artifact in observation.artifacts.items():
            baseline = self.spec.baseline_roles[role]
            if (artifact.scope != self.scope or artifact.role != role
                    or any(getattr(artifact, name) != getattr(baseline, name) for name in
                           ("input_contract_id", "input_contract_sha256", "output_contract_id", "output_contract_sha256", "qualifier_id"))):
                raise PermissionError("actual captured producer changed frozen role qualification contracts")
        return metadata, observation

    def publish_capture(self, *, snapshot_id, reconcile=False):
        slot = self.spec.slot(snapshot_id)
        existing = self._metadata("slot", snapshot_id)
        metadata, observation = self._observation(snapshot_id)
        if existing is None:
            self._authorize_slot(capture=True, snapshot_id=snapshot_id, case_id=slot.case_id, phase=slot.phase,
                arm=slot.arm, history=self.histories[(slot.case_id, slot.phase)], plan=observation.context_plan)
        capture = next((item for item in self.comparison.log.replay_committed() if item.event.event_id == metadata["event_id"]), None)
        anchor = self._canonical(self.anchor._record)
        if capture is None or capture.stream_position <= anchor.stream_position:
            raise PermissionError("actual phase capture does not follow preregistration anchor")
        parents = [metadata["event_id"]]
        if slot.phase == "after":
            before, update = self._metadata("before_seal"), self._metadata("update")
            if before is None or update is None or capture.stream_position <= self._canonical(update).stream_position:
                raise PermissionError("after capture does not follow sealed-before/qualified update")
            parents += [before.event_id, update.event_id]
        payload = {"slot": slot.record(), "capture_metadata": metadata, "observed": observation.record()}
        return self._put("slot", payload, parents=tuple(parents), snapshot_id=snapshot_id, reconcile=reconcile,
            metadata={"snapshot_id": snapshot_id, "snapshot_sha256": metadata["snapshot_sha256"],
                      "capture_record_sha256": metadata["record_sha256"], "capture_event_id": metadata["event_id"],
                      "observed_sha256": canonical_sha256(observation.record())})

    def reconcile_slot(self, *, snapshot_id):
        return self.publish_capture(snapshot_id=snapshot_id, reconcile=True)

    def seal_before(self, *, reconcile=False):
        with self._repair("before_seal", None, reconcile):
            return self._seal_before(reconcile=reconcile)

    def _seal_before(self, *, reconcile):
        self._current()
        self._deny_evaluation_attempts()
        slots = [slot for slot in self.spec.slots if slot.phase == "before"]
        records = {slot.snapshot_id: self._metadata("slot", slot.snapshot_id) for slot in slots}
        if any(record is None for record in records.values()) or self._metadata("update_gate") is not None:
            raise PermissionError("complete canonical before slots must precede update authorization")
        for slot in slots:
            metadata, observed = self._observation(slot.snapshot_id)
            if records[slot.snapshot_id].record["metadata"]["observed_sha256"] != canonical_sha256(observed.record()):
                raise PermissionError("sealed-before capture observation changed")
            for role, artifact in observed.artifacts.items():
                if artifact != self.spec.baseline_roles[role]:
                    raise PermissionError("before capture changed the frozen actual baseline role nomination")
        payload = {"slot_records": {key: value.record["record_sha256"] for key, value in records.items()},
                   "status": "before_captures_sealed", "learned_update": "not_performed"}
        return self._put("before_seal", payload, parents=tuple(record.event_id for record in records.values()),
            reconcile=reconcile, metadata={"slot_records": payload["slot_records"]})

    def begin_update(self, *, reconcile=False):
        self._current()
        self._deny_evaluation_attempts()
        before = self._stage("before_seal")
        if before is None or self._metadata("final_seal") is not None:
            raise PermissionError("update requires canonical before seal and no final assignment")
        return self._put("update_gate", {"before_seal_sha256": before.record["record_sha256"],
            "update_contract_sha256": sha(self.spec.update_contract), "update_invocation_ids": dict(self.spec.update_invocation_ids),
            "status": "producer_update_authorized", "learned_update": "not_proven"},
            parents=(before.event_id,), reconcile=reconcile,
            metadata={"before_seal_sha256": before.record["record_sha256"]})

    def record_update(self, *, update_event_ids: tuple[str, ...], receipts: Mapping[str, bytes], reconcile=False):
        self._current()
        self._deny_evaluation_attempts()
        before, gate = self._stage("before_seal"), self._stage("update_gate")
        if before is None or gate is None or self.phase_custody is None:
            raise PermissionError("update needs actual canonical authorization and producer qualifier ports")
        if (not update_event_ids or tuple(sorted(set(update_event_ids))) != update_event_ids
                or set(receipts) != _ROLES or any(not isinstance(value, bytes) or not value for value in receipts.values())):
            raise ValueError("update requires exact actual receipt IDs and independent proofs for both roles")
        committed = {entry.event.event_id: entry for entry in self.comparison.log.replay_committed()}
        position = self._canonical(gate).stream_position
        allowed_invocations = {value for values in self.spec.update_invocation_ids.values() for value in values}
        events = []
        for event_id in update_event_ids:
            entry = committed.get(event_id)
            if (entry is None or entry.stream_position <= position or entry.event.scope != self.scope
                    or entry.event.provenance.derivation_activity_id not in allowed_invocations
                    or entry.event.event_type == "comparison_artifact"):
                raise PermissionError("producer update receipt did not occur under predeclared post-seal execution")
            events.append({"event_id": event_id, "event_sha256": entry.event.event_sha256,
                           "stream_position": entry.stream_position, "event_type": entry.event.event_type})
        request = {"schema": "flora-preregistered-update-request-v1", "scope": self.scope.metadata_record(),
            "authority_namespace_id": self.namespace, "run_id": self.run_id, "preregistration_sha256": self.anchor.preregistration_sha256,
            "before_seal_event_id": before.event_id, "before_seal_record_sha256": before.record["record_sha256"],
            "update_gate_event_id": gate.event_id, "update_gate_event_sha256": gate.record["event_sha256"],
            "update_contract_sha256": sha(self.spec.update_contract), "actual_update_events": events}
        verified = {}
        for role in sorted(_ROLES):
            binding = self.phase_custody.runtime.bindings[role]
            method = getattr(binding.qualification_verifier, "verify_preregistered_update", None)
            if not callable(method):
                raise PermissionError("actual producer has no preregistered update qualification adapter")
            role_request = {**request, "role": role, "role_policy_contract_sha256": sha(self.spec.role_policy_contracts[role])}
            self._current()
            result = method(request=role_request, receipt=receipts[role])
            self._current()
            expected = {"schema": "flora-qualified-preregistered-update-v1", "role": role,
                "request_sha256": canonical_sha256(role_request), "receipt_sha256": sha(receipts[role]),
                "qualifier_id": self.spec.baseline_roles[role].qualifier_id, "allowed": True,
                "authorized_before_execution": True}
            if result != expected:
                raise PermissionError("independent producer did not prove actual authorized update execution")
            verified[role] = result
        payload = {"request": request, "verified": verified,
                   "receipts_base64": {role: __import__("base64").b64encode(value).decode() for role, value in receipts.items()}}
        return self._put("update", payload, parents=(gate.event_id, *update_event_ids), reconcile=reconcile,
            metadata={"update_event_ids": list(update_event_ids), "update_request_sha256": canonical_sha256(request)})

    def _verify_update(self):
        """Recheck external producer proof; an indexed marker is not learning."""
        payload = self.recover_control(kind="update")
        request = payload["request"]
        before, gate = self._stage("before_seal"), self._stage("update_gate")
        expected = {"schema": "flora-preregistered-update-request-v1", "scope": self.scope.metadata_record(),
            "authority_namespace_id": self.namespace, "run_id": self.run_id,
            "preregistration_sha256": self.anchor.preregistration_sha256,
            "before_seal_event_id": before.event_id, "before_seal_record_sha256": before.record["record_sha256"],
            "update_gate_event_id": gate.event_id, "update_gate_event_sha256": gate.record["event_sha256"],
            "update_contract_sha256": sha(self.spec.update_contract), "actual_update_events": request["actual_update_events"]}
        if request != expected or set(payload["verified"]) != _ROLES or set(payload["receipts_base64"]) != _ROLES:
            raise PermissionError("qualified update receipt changed its exact canonical authorization")
        allowed = {value for values in self.spec.update_invocation_ids.values() for value in values}
        committed = {item.event.event_id: item for item in self.comparison.log.replay_committed()}
        for value in request["actual_update_events"]:
            item = committed.get(value["event_id"])
            if (item is None or item.stream_position <= self._canonical(gate).stream_position
                    or item.event.scope != self.scope or item.event.provenance.derivation_activity_id not in allowed
                    or value != {"event_id": item.event.event_id, "event_sha256": item.event.event_sha256,
                                 "stream_position": item.stream_position, "event_type": item.event.event_type}):
                raise PermissionError("actual update execution lost its exact post-gate canonical position")
        for role in sorted(_ROLES):
            method = getattr(self.phase_custody.runtime.bindings[role].qualification_verifier, "verify_preregistered_update", None)
            if not callable(method):
                raise PermissionError("actual update qualification port is unavailable")
            receipt = __import__("base64").b64decode(payload["receipts_base64"][role], validate=True)
            role_request = {**request, "role": role, "role_policy_contract_sha256": sha(self.spec.role_policy_contracts[role])}
            self._current()
            result = method(request=role_request, receipt=receipt)
            self._current()
            if result != payload["verified"][role] or result != {"schema": "flora-qualified-preregistered-update-v1", "role": role,
                "request_sha256": canonical_sha256(role_request), "receipt_sha256": sha(receipt),
                "qualifier_id": self.spec.baseline_roles[role].qualifier_id, "allowed": True, "authorized_before_execution": True}:
                raise PermissionError("independent current producer no longer qualifies actual update")

    def _verify_slot_table(self, *, private, include_evaluation=True):
        records, observations = {}, {}
        before, update = self._metadata("before_seal"), self._metadata("update")
        if before is None or update is None:
            raise PermissionError("final binding requires sealed before captures and qualified actual update")
        # One immutable canonical replay inside this guard, never a lease/cache
        # spanning a raw-I/O boundary. Every SQL/source/grant predicate stays
        # fresh when the next independent guard begins.
        committed = tuple(self.comparison.log.replay_committed())
        by_id = {item.event.event_id: item for item in committed}
        if len(by_id) != len(committed):
            raise PermissionError("preregistration canonical control events are ambiguous")
        def canonical(record):
            item = by_id.get(record.event_id)
            if item is None or item.event.event_sha256 != record.record["event_sha256"]:
                raise PermissionError("preregistration control lacks its exact canonical event")
            return item
        before_position, update_position = canonical(before).stream_position, canonical(update).stream_position
        if private:
            self._verify_update()
        for slot in self.spec.slots:
            record = self._metadata("slot", slot.snapshot_id)
            metadata = None if self.phase_custody is None else self.phase_custody.metadata(slot.snapshot_id)
            if (record is None or metadata is None or record.record["metadata"]["capture_record_sha256"] != metadata["record_sha256"]
                    or record.record["metadata"]["snapshot_sha256"] != metadata["snapshot_sha256"]):
                raise PermissionError("entire canonical declared capture table is not complete and exact")
            capture = by_id.get(metadata["event_id"])
            if (capture is None or capture.event.event_sha256 != metadata["event_sha256"]
                    or slot.phase == "before" and canonical(record).stream_position >= before_position
                    or slot.phase == "after" and capture.stream_position <= update_position):
                raise PermissionError("actual capture/seal/update canonical ordering changed")
            records[slot.snapshot_id] = record
            if private:
                payload = self.recover_control(kind="slot", snapshot_id=slot.snapshot_id)
                actual_metadata, observation = self._observation(slot.snapshot_id)
                if (canonical_sha256(observation.record()) != record.record["metadata"]["observed_sha256"]
                        or canonical_sha256(payload) != canonical_sha256({"slot": slot.record(), "capture_metadata": actual_metadata, "observed": observation.record()})):
                    raise PermissionError("actual qualified capture changed after slot publication")
                observations[slot.snapshot_id] = observation
        self._current(include_evaluation=include_evaluation)
        return records, observations

    def _final_payload(self, plan, native, slot_records):
        return {"final_plan_sha256": plan.digest(), "preregistration_sha256": self.anchor.preregistration_sha256,
            "slot_records": dict(slot_records), "native_plans": {arm: frozen.record() for arm, frozen in native.items()},
            "phase_bindings": plan.phase_binding_record(), "status": "observed_final_binding_sealed", "part1_accepted": False}

    def finalize(self, *, reconcile=False):
        with self._repair("final_seal", None, reconcile):
            return self._finalize(reconcile=reconcile, recovery=False)

    def recover_final_binding(self):
        """Passive exact final authority recovery; never recapture or append."""
        return self._finalize(reconcile=False, recovery=True)

    def _finalize(self, *, reconcile, recovery):
        self._current()
        if recovery:
            if self._stage("final_seal") is None:
                raise PermissionError("final authority has no actual sealed binding to recover")
        else:
            self._deny_evaluation_attempts()
        records, observations = self._verify_slot_table(private=True)
        native, bindings = {}, {}
        baseline = ArmBinding(self.spec.comparator.producer_component, self.spec.comparator.provider.digest(),
            self.spec.comparator.digest(), "original_source_memory")
        for arm in sorted(_NATIVE):
            declaration = self.spec.native_arms[arm]
            slots = [slot for slot in self.spec.slots if slot.arm == arm]
            entries = []
            for slot in slots:
                observed = observations[slot.snapshot_id]
                metadata = self.phase_custody.metadata(slot.snapshot_id)
                reference = NativePhaseSnapshotBinding(run_id=self.run_id, snapshot_id=slot.snapshot_id, arm=arm,
                    preregistration_sha256=self.anchor.preregistration_sha256,
                    snapshot_sha256=metadata["snapshot_sha256"], event_id=metadata["event_id"], event_sha256=metadata["event_sha256"])
                entries.append(NativeInvocationEntry(slot.case_id, slot.phase, slot.evaluation_invocation_id,
                    observed.context_plan, observed.context_sha256, reference))
            frozen = FrozenNativeArmPlan(self.scope, self.namespace, arm, declaration.worker.manifest_sha256, tuple(entries))
            native[arm] = frozen
            for slot in slots:
                checkpoint = observations[slot.snapshot_id].artifacts["personality_judgment"].checkpoint_sha256
                bindings[(slot.case_id, slot.phase, arm)] = ArmBinding(declaration.producer_component, checkpoint,
                    frozen.lineage_sha256, declaration.update_mechanism)
        for case, phase in self.histories:
            bindings[(case, phase, "general_model_memory")] = baseline
        defaults = {arm: bindings[(self.spec.protocol.cases[0].case_id, "before", arm)] for arm in (*sorted(_NATIVE), "general_model_memory")}
        plan = PairedRunPlan(self.spec.protocol, defaults, self.spec.context_token_budget, self.spec.context_byte_budget,
            self.spec.feature_call_budget, self.spec.question_sha256_by_case, self.spec.evidence_kind, bindings,
            preregistration_sha256=self.anchor.preregistration_sha256)
        plan.validate()
        # Identical original evidence and captured selected context are required
        # across native full/withheld arms; no favorable recapture/subset chosen.
        for case, phase in self.histories:
            left = native["flora_full"].entry(case, phase)
            right = native["same_evidence_ablation"].entry(case, phase)
            if left.context_sha256 != right.context_sha256:
                raise PermissionError("native ablation changed actual captured context rather than only frozen update policy")
        payload = self._final_payload(plan, native, {key: value.record["record_sha256"] for key, value in records.items()})
        before, update = self._metadata("before_seal"), self._metadata("update")
        if recovery:
            final = self._stage("final_seal")
            if canonical_sha256(self.recover_control(kind="final_seal")) != canonical_sha256(payload):
                raise PermissionError("final observed binding changed during current recovery")
            self._current()
            return RegisteredExperimentFinalBinding(self, plan, native, final)
        final = self._put("final_seal", payload, parents=(before.event_id, update.event_id, *(record.event_id for record in records.values())),
            reconcile=reconcile, metadata={"final_plan_sha256": plan.digest(), "slot_records": payload["slot_records"]})
        return RegisteredExperimentFinalBinding(self, plan, native, final)

    def recover_control(self, *, kind, snapshot_id=None):
        record = self._metadata(kind, snapshot_id)
        if record is None or record.record["kind"] != self.control_kind(kind):
            raise PermissionError("preregistration control is unavailable")
        def check():
            if self._metadata(kind, snapshot_id) != record:
                raise PermissionError("preregistration control changed during private read")
            self._current(operation="read", parents=(record.event_id,))
        check()
        content = self._guarded_comparison(check)._read_authorized(run_id=self.run_id,
            artifact_id=self.artifact_id(kind, snapshot_id), permissions=self.permissions,
            purpose=preregistration_purpose(self.run_id, "read"))
        body = json.loads(content)
        if (body["schema"] != "flora-experiment-preregistration-control-v1" or body["kind"] != kind
                or body["preregistration_sha256"] != self.anchor.preregistration_sha256):
            raise ValueError("private preregistration control differs from actual anchor")
        check()
        return body["payload"]
