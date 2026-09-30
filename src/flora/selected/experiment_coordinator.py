"""Registered prepared-history experiment orchestration, without model defaults.

Control stages are encrypted comparison artifacts, never inference inputs. This
connects existing selected controllers; it does not invent cohorts, future live
outcomes, producer exports, ratings, thresholds, or an accepted Part 1 result.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from copy import copy, deepcopy
from dataclasses import dataclass, field
import json
import secrets
from types import MappingProxyType
from typing import Callable, Mapping

from cognitive_kernel.canonical import canonical_sha256, normalize_timestamp

from ..comparator import GeneralMemoryArmAdapter, encoded, identifier, sha
from ..comparison_run import ArmStopped, HistorySnapshot, PairedRun, PairedRunPlan, run_paired, validate_run
from ..evaluation_protocol import ARMS
from .assessment_custody import XTDBAssessmentCustody, assessment_artifact_id
from .comparison_custody import XTDBComparisonCustody, SelectedRunEvidencePolicy, evaluation_purpose, _plan_record
from .experiment_manifests import SelectedSourceAuthority, XTDBExperimentManifestCustody, _GuardedObjects, manifest_purpose
from .formation_registry import RegisteredEncryptedFormationCustody
from .native_arm import FrozenNativeArmPlan, NativeArmAdapter
from .native_reads import SelectedNativeReadServices
from .experiment_runtime import RuntimeBlocked
from .phase_routes import SelectedPhaseLineageRouter
from .provider_attempt_custody import XTDBProviderAttemptCustody


_NATIVE_ARMS = frozenset({"flora_full", "same_evidence_ablation"})


def coordinator_purpose(experiment_id: str, run_id: str, operation: str) -> str:
    identifier(experiment_id, "experiment_id")
    identifier(run_id, "run_id")
    if operation not in {"capture", "read"}:
        raise ValueError("unknown experiment coordinator purpose")
    return "experiment_coordinator_" + operation + ":" + canonical_sha256([experiment_id, run_id])


@dataclass(frozen=True)
class CoordinatorOutcome:
    status: str
    artifact_id: str
    reasons: tuple[str, ...] = ()
    run: PairedRun | None = field(default=None, repr=False)
    part1_accepted: bool = False


class _GuardedLog:
    def __init__(self, log, check):
        self.log, self.check = log, check
    def __getattr__(self, name):
        return getattr(self.log, name)
    def append(self, event, *, expected_revision):
        # The caller calculated revisions and constructed the event already.
        self.check()
        value = self.log.append(event, expected_revision=expected_revision)
        self.check()
        return value


def _attach_private_fence(runtime, check):
    """Attach copied planes to an exclusively owned/copied runtime only."""
    runtime.objects = _GuardedObjects(runtime.objects, check)
    runtime.artifacts = copy(runtime.artifacts)
    runtime.artifacts.objects = runtime.objects
    runtime.private = copy(runtime.private)
    runtime.private.runtime = runtime
    runtime.references = copy(runtime.references)
    runtime.references.runtime_custody = runtime.private
    verifier = copy(runtime.state_approval_verifier)
    proofs = getattr(verifier, "proofs", None)
    if proofs is not None and hasattr(proofs, "objects"):
        verifier.proofs = copy(proofs)
        verifier.proofs.objects = runtime.objects
    runtime.state_approval_verifier = verifier


class _CohortFencedSessionFactory:
    """Add custody gates on a native service's actual owned read connection."""
    def __init__(self, coordinator, reads):
        self.coordinator, self.reads, self.original = coordinator, reads, reads.factory
        self.artifact_sha256 = self.original.artifact_sha256
        self.configuration_sha256 = self.original.configuration_sha256

    @contextmanager
    def open_initialized_read_session(self):
        with self.original.open_initialized_read_session() as session:
            self.reads._check_session(session)
            check = self.coordinator._owned_base_fence(session.connections[0])
            check()
            # _check_session proved these services use this exclusively owned
            # connection. Rebind attributes, never the shared encrypted plane.
            _attach_private_fence(session.runtime, check)
            history = session.lineage.history_authority
            if not isinstance(history, SelectedRunEvidencePolicy):
                raise PermissionError("coordinator native reads require actual selected history authority")
            history.custody.objects = _GuardedObjects(history.custody.objects, check)
            history.custody.raw_custody = RegisteredEncryptedFormationCustody(
                registry=history.custody.registry, objects=history.custody.objects)
            check()
            yield session
            check()


class RegisteredExperimentCoordinator:
    """One frozen host slice with explicit supplied producer/provider services.

    Inputs, cohort, recipe and paired plan must already be registered. Frozen
    after histories are prepared material, not a promise to discover a future
    outcome under this digest. No grants are created by this coordinator.
    """
    def __init__(self, *, manifests: XTDBExperimentManifestCustody, cohort_id: str,
                 recipe_id: str, comparison: XTDBComparisonCustody,
                 evidence: SelectedRunEvidencePolicy, assessment: XTDBAssessmentCustody,
                 plan: PairedRunPlan, histories: Mapping[tuple[str, str], HistorySnapshot],
                 questions: Mapping[str, bytes], native_plans: Mapping[str, FrozenNativeArmPlan],
                 history_entry_ids: Mapping[tuple[str, str], tuple[str, ...]],
                 question_entry_ids: Mapping[str, str],
                 provider_task_ids: Mapping[tuple[str, str], str],
                 clock: Callable[[], str], phase_router: SelectedPhaseLineageRouter | None = None,
                 provider_custody: XTDBProviderAttemptCustody | None = None, final_authority=None):
        if (not isinstance(manifests, XTDBExperimentManifestCustody)
                or not isinstance(comparison, XTDBComparisonCustody)
                or not isinstance(evidence, SelectedRunEvidencePolicy)
                or not isinstance(assessment, XTDBAssessmentCustody)
                or not isinstance(plan, PairedRunPlan)):
            raise TypeError("coordinator requires actual selected controllers and paired plan")
        identifier(cohort_id, "cohort_id")
        identifier(recipe_id, "recipe_id")
        local = manifests.local
        if (local.registry is not comparison.registry or local.log is not comparison.log
                or local.objects is not comparison.objects or manifests.connection is not comparison.connection
                or evidence.custody is not comparison or evidence.permissions is not local.permissions
                or assessment.comparison is not comparison
                or comparison.scope != manifests.scope or comparison.authority_namespace_id != manifests.namespace):
            raise ValueError("coordinator controllers do not share exact physical host custody")
        plan.validate()
        actual_final = comparison.require_final_authority(run_id=evidence.run_id, plan=plan,
            final_authority=final_authority)
        if actual_final is not None:
            if (actual_final.store.manifests is not manifests or actual_final.store.cohort_id != cohort_id
                    or actual_final.store.recipe_id != recipe_id or actual_final.native_plans != native_plans
                    or actual_final.store.spec.provider_task_ids != provider_task_ids
                    or evidence.final_authority is not actual_final):
                raise ValueError("coordinator differs from actual sealed preregistration services")
        self.final_authority = actual_final
        expected = {(case.case_id, phase) for case in plan.protocol.cases for phase in ("before", "after")}
        cases = {case.case_id for case in plan.protocol.cases}
        if (plan.phase_bindings is None or set(histories) != expected
                or set(questions) != cases or set(history_entry_ids) != expected
                or set(question_entry_ids) != cases or set(provider_task_ids) != expected
                or set(native_plans) != _NATIVE_ARMS
                or any(case.host_id != comparison.scope.host_instance_id for case in plan.protocol.cases)):
            raise ValueError("coordinator needs the complete exact frozen phase matrix")
        for value in provider_task_ids.values():
            identifier(value, "provider_task_id")
        if len(set(provider_task_ids.values())) != len(expected):
            raise ValueError("provider task IDs must be distinct and canonical")
        for arm, native in native_plans.items():
            if not isinstance(native, FrozenNativeArmPlan):
                raise TypeError("native role plans must be actual frozen native plans")
            native.record()
            if (native.arm != arm or native.scope != comparison.scope
                    or native.authority_namespace_id != comparison.authority_namespace_id
                    or {(entry.case_id, entry.phase) for entry in native.entries} != expected
                    or any(entry.phase_snapshot is None or entry.phase_snapshot.run_id != evidence.run_id
                           or plan.binding_for(entry.case_id, entry.phase, arm).lineage_sha256 != native.lineage_sha256
                           for entry in native.entries)):
                raise ValueError("native invocation/phase lineage differs from the frozen paired plan")
        invocation_ids = [entry.invocation_id for native in native_plans.values() for entry in native.entries]
        if len(set(invocation_ids)) != len(invocation_ids):
            raise ValueError("separate native arm attempts need distinct frozen invocation IDs")
        if phase_router is not None:
            if (not isinstance(phase_router, SelectedPhaseLineageRouter)
                    or phase_router is not evidence.native_lineage
                    or phase_router.custody.run_id != evidence.run_id
                    or phase_router.run_plan.digest() != plan.digest()
                    or phase_router.histories != histories
                    or phase_router.runtime.sources is not local.registry
                    or phase_router.runtime.log is not local.log
                    or not isinstance(phase_router.history_authority, SelectedRunEvidencePolicy)
                    or phase_router.history_authority.custody is not comparison
                    or phase_router.history_authority.run_id != evidence.run_id
                    or phase_router.history_authority.permissions is not local.permissions
                    or evidence.requires_native_result is not True
                    or phase_router.custody.artifact_permissions.connection is not local.permissions.connection):
                raise ValueError("phase router differs from actual registered controller identities")
            phase_router.record()
            for arm, native in native_plans.items():
                for entry in native.entries:
                    key = (entry.case_id, entry.phase, arm)
                    if (phase_router.snapshots[key] != entry.phase_snapshot
                            or phase_router.frozen_native_arms[arm] != native):
                        raise ValueError("phase router differs from frozen native invocation IDs")
        elif evidence.native_lineage is not None:
            raise ValueError("coordinator needs its exact phase-aware router, not a single current verifier")
        if provider_custody is not None and (
                not isinstance(provider_custody, XTDBProviderAttemptCustody)
                or provider_custody.comparison is not comparison or provider_custody.evidence is not evidence
                or provider_custody.permissions is not local.permissions):
            raise ValueError("provider ledger differs from actual selected run custody")
        self.manifests, self.comparison, self.evidence, self.assessment = manifests, comparison, evidence, assessment
        self.plan, self.run_id, self.clock = plan, evidence.run_id, clock
        self.histories, self.questions = MappingProxyType(dict(histories)), MappingProxyType(dict(questions))
        self.native_plans = MappingProxyType(dict(native_plans))
        self.phase_router, self.provider_custody = phase_router, provider_custody
        self.history_entry_ids = MappingProxyType({key: tuple(value) for key, value in history_entry_ids.items()})
        self.question_entry_ids, self.provider_task_ids = MappingProxyType(dict(question_entry_ids)), MappingProxyType(dict(provider_task_ids))
        self.cohort_id, self.recipe_id = cohort_id, recipe_id
        self._controllers = (local.registry, local.log, local.objects, local.permissions, comparison.connection)
        self._manifest_records = {"cohort": manifests.metadata("cohort", cohort_id),
                                  "recipe": manifests.metadata("recipe", recipe_id)}
        if any(value is None for value in self._manifest_records.values()):
            raise ValueError("coordinator cohort or recipe is not actually registered")
        self._input_records = {key: comparison.metadata(self.run_id, key) for key in (
            "plan", *(f"history:{case}:{phase}" for case, phase in sorted(expected)),
            *(f"question:{case}" for case in sorted(cases)))}
        if any(value is None for value in self._input_records.values()):
            raise ValueError("coordinator inputs are not actually registered")
        self._source_gates = []
        for (case, phase), history in self.histories.items():
            history.content()
            if (history.scope != comparison.scope
                    or self._input_records[f"history:{case}:{phase}"].record["metadata"]["history_sha256"] != history.digest()
                    or tuple(self._input_records[f"history:{case}:{phase}"].record["metadata"]["source_event_ids"]) != history.event_ids):
                raise ValueError("coordinator history differs from exact registered originals")
            self._source_gates.extend(manifests._gate(local.authority_id, event_id,
                evaluation_purpose(self.run_id, case, phase)) for event_id in history.event_ids)
        if (self._input_records["plan"].record["metadata"]["plan_sha256"] != plan.digest()
                or self._input_records["plan"].record["content_sha256"] != sha(encoded(_plan_record(plan)))
                or any(sha(question) != plan.question_sha256_by_case[case]
                       or self._input_records[f"question:{case}"].record["content_sha256"] != sha(question)
                       for case, question in self.questions.items())):
            raise ValueError("coordinator plan/question differs from registered custody")
        self._base_current()
        cohort = manifests.recover(kind="cohort", manifest_id=cohort_id)
        recipe = manifests.recover(kind="recipe", manifest_id=recipe_id)
        if recipe["cohort_id"] != cohort_id:
            raise ValueError("limited builder recipe belongs to another cohort")
        if plan.protocol.builder_recipe_sha256 != self._manifest_records["recipe"]["content_sha256"]:
            raise ValueError("protocol does not bind the actual registered limited-builder recipe")
        entries = {entry["entry_id"]: entry for entry in cohort["cohort"]["entries"]}
        for key, ids in self.history_entry_ids.items():
            if (len(set(ids)) != len(ids) or any(entry not in entries for entry in ids)
                    or tuple(entries[entry]["event_id"] for entry in ids) != self.histories[key].event_ids
                    or any(entries[entry]["authority_id"] != local.authority_id
                           or entries[entry]["usage_role"] != "authorized_history" for entry in ids)):
                raise ValueError("history is not exactly mapped to actual local cohort entries")
        for case, entry_id in self.question_entry_ids.items():
            entry = entries.get(entry_id)
            if (entry is None or entry["authority_id"] != local.authority_id or entry["usage_role"] != "question"
                    or local.registry.lookup(entry["event_id"]).evidence.content_digest != sha(self.questions[case])):
                raise ValueError("question has no exact actual local cohort source")
        self._record = self._configuration_record()
        self.binding_sha256 = canonical_sha256(self._record)
        self._started = False

    def _configuration_record(self):
        record = {"schema": "flora-registered-experiment-coordinator-v1", "experiment_id": self.manifests.experiment_id,
            "run_id": self.run_id, "scope": self.comparison.scope.metadata_record(),
            "authority_namespace_id": self.comparison.authority_namespace_id,
            "plan_sha256": self.plan.digest(), "phase_bindings": self.plan.phase_binding_record(),
            "manifests": {kind: {"manifest_id": record["manifest_id"], "record_sha256": record["record_sha256"]}
                          for kind, record in self._manifest_records.items()},
            "registered_inputs": {key: record.record["record_sha256"] for key, record in self._input_records.items()},
            "history_entries": [{"case_id": case, "phase": phase, "entry_ids": list(value)}
                                for (case, phase), value in sorted(self.history_entry_ids.items())],
            "question_entries": dict(self.question_entry_ids),
            "native_plans": {arm: native.record() for arm, native in sorted(self.native_plans.items())},
            "provider_tasks": [{"case_id": case, "phase": phase, "task_id": task}
                               for (case, phase), task in sorted(self.provider_task_ids.items())],
            "phase_router_sha256": None if self.phase_router is None else self.phase_router.binding_sha256,
            "mode": "prepared_history" if self.final_authority is None else "prepared_synthetic_two_stage",
            "part1_accepted": False}
        if self.final_authority is not None:
            record["schema"] = "flora-registered-experiment-coordinator-v2"
            record["final_binding"] = {
                "preregistration_sha256": self.final_authority.preregistration_sha256,
                "final_plan_sha256": self.final_authority.final_plan_sha256,
                "record_sha256": self.final_authority._record.record["record_sha256"]}
        return json.loads(encoded(record))

    def record(self):
        if self._configuration_record() != self._record:
            raise PermissionError("coordinator frozen configuration changed")
        return deepcopy(self._record)

    def _base_current(self):
        local = self.manifests.local
        if (self._controllers != (local.registry, local.log, local.objects, local.permissions, self.comparison.connection)
                or self.comparison.registry is not local.registry or self.comparison.log is not local.log
                or self.comparison.objects is not local.objects or self.evidence.custody is not self.comparison
                or self.evidence.permissions is not local.permissions or self.assessment.comparison is not self.comparison):
            raise PermissionError("actual coordinator controller identity changed")
        for kind, frozen in self._manifest_records.items():
            actual = self.manifests.metadata(kind, frozen["manifest_id"])
            if actual != frozen:
                raise PermissionError("coordinator manifest dependency changed")
            self.manifests._check_gates(actual["source_gates"])
            self.manifests._check_dependencies(actual["dependencies"])
            source = self.manifests.local.registry.lookup(actual["event_id"])
            if self.manifests.local.permissions.permits(source, manifest_purpose(self.manifests.experiment_id, "read")) is not True:
                raise PermissionError("coordinator manifest read was withdrawn")
        for artifact_id, frozen in self._input_records.items():
            if self.comparison.metadata(self.run_id, artifact_id) != frozen:
                raise PermissionError("coordinator exact registered inputs changed")
        self.manifests._check_gates(self._source_gates)
        self.comparison.require_final_authority(run_id=self.run_id, plan=self.plan,
            final_authority=self.final_authority)
        # Slow dependency/registry checks must be followed by all foreign and
        # local original-purpose gates, not an earlier allow result.
        for frozen in self._manifest_records.values():
            self.manifests._check_gates(frozen["source_gates"])
        self.manifests._check_gates(self._source_gates)

    def _current(self, *, operation=None, parents=(), qualified=False):
        self.record()
        self._base_current()
        if qualified:
            if self.phase_router is None:
                raise PermissionError("actual qualified phase router is absent")
            if self.final_authority is not None:
                self.final_authority.authorize_plan(plan=self.plan, metadata_only=False)
            router = self._guarded_router()
            for case, phase in sorted(self.histories):
                for arm in sorted(_NATIVE_ARMS):
                    route = router.route_for(case_id=case, phase=phase, arm=arm)
                    entry = self.native_plans[arm].entry(case, phase)
                    from ..comparison_run import _context_bytes
                    if (route.snapshot.plan != entry.context_plan
                            or sha(_context_bytes(route.runtime._context(route.snapshot.plan))) != entry.context_sha256):
                        raise PermissionError("phase context differs from frozen native plan")
                    route.check_live()
        if operation is not None:
            purpose = coordinator_purpose(self.manifests.experiment_id, self.run_id, operation)
            for event_id in parents:
                source = self.manifests.local.registry.lookup(event_id)
                if self.manifests.local.permissions.permits(source, purpose) is not True:
                    raise PermissionError("coordinator control purpose is not currently authorized")
        self._base_current()  # Qualifications and own grants may be slow.

    def _guarded_router(self):
        router = copy(self.phase_router)
        custody = copy(router.custody)
        runtime = copy(custody.runtime)
        _attach_private_fence(runtime, self._base_current)
        custody.runtime = runtime
        router.custody, router.runtime = custody, runtime
        history = copy(router.history_authority)
        history.custody = self._guarded_comparison(self._base_current)
        router.history_authority = history
        return router

    def _owned_base_fence(self, connection):
        # These concrete services read the same actual selected database using
        # the native reader's owned SELECT-only connection. Foreign authorities
        # on separate databases need a supplied multi-connection port instead.
        manifests = copy(self.manifests)
        authorities = {}
        for authority_id, original in self.manifests.authorities.items():
            if (getattr(original.registry, "connection", self.manifests.connection) is not self.manifests.connection
                    or getattr(original.permissions, "connection", self.manifests.connection) is not self.manifests.connection):
                raise PermissionError("cohort dependencies need separately owned backend read ports")
            registry, permissions = copy(original.registry), copy(original.permissions)
            registry.connection = permissions.connection = connection
            permissions.registry = registry
            authority = SelectedSourceAuthority(registry, original.log, permissions, original.objects)
            authorities[authority_id] = authority
        manifests.connection, manifests.authorities = connection, authorities
        manifests.local = authorities[self.manifests.local.authority_id]
        selected = copy(self.comparison)
        selected.connection, selected.registry = connection, manifests.local.registry
        selected.raw_custody = RegisteredEncryptedFormationCustody(registry=selected.registry, objects=selected.objects)
        evidence = copy(self.evidence)
        evidence.custody, evidence.permissions = selected, manifests.local.permissions
        assessment = copy(self.assessment)
        assessment.comparison = selected
        owned = copy(self)
        owned.manifests, owned.comparison, owned.evidence, owned.assessment = manifests, selected, evidence, assessment
        owned._controllers = (manifests.local.registry, manifests.local.log, manifests.local.objects,
                              manifests.local.permissions, connection)
        if self.final_authority is not None:
            owned.final_authority = self.final_authority.bind_read_connection(connection)
            evidence.final_authority = owned.final_authority
        return owned._base_current

    def _guarded_comparison(self, check):
        selected = copy(self.comparison)
        selected.objects = _GuardedObjects(self.comparison.objects, check)
        selected.raw_custody = RegisteredEncryptedFormationCustody(registry=selected.registry, objects=selected.objects)
        selected.log = _GuardedLog(self.comparison.log, check)
        return selected

    def _put(self, *, artifact_id, stage, payload, parents=(), qualified=False):
        if stage not in {"binding", "preflight", "running", "completed", "interrupted", "sealed_assessment"}:
            raise ValueError("unknown coordinator stage")
        identifier(artifact_id, "artifact_id")
        base = tuple(record["event_id"] for record in self._manifest_records.values()) + (self._input_records["plan"].event_id,)
        parents = tuple(sorted(set((*base, *parents))))
        body = {"schema": "flora-experiment-coordinator-stage-v1", "binding_sha256": self.binding_sha256,
                "stage": stage, "qualified_phases_required": qualified, "payload": payload, "part1_accepted": False}
        def check():
            self._current(operation="capture", parents=parents, qualified=qualified)
        check()
        selected = self._guarded_comparison(check)
        artifact = selected._put(run_id=self.run_id, artifact_id=artifact_id, kind="coordinator_" + stage,
            content=encoded(body), parents=parents, metadata={"binding_sha256": self.binding_sha256, "stage": stage,
            "qualified_phases_required": qualified, "part1_accepted": False}, occurred_at=normalize_timestamp(self.clock()))
        check()
        return artifact

    def prepare(self):
        return self._put(artifact_id="coordinator:binding", stage="binding", payload=self.record())

    def recover_stage(self, *, artifact_id):
        artifact = self.comparison.metadata(self.run_id, artifact_id)
        if (artifact is None or artifact.record["kind"] not in {"coordinator_" + stage for stage in (
                "binding", "preflight", "running", "completed", "interrupted", "sealed_assessment")}
                or artifact.record["metadata"].get("binding_sha256") != self.binding_sha256):
            raise PermissionError("control artifact is outside this exact registered coordinator")
        qualified = artifact.record["metadata"]["qualified_phases_required"]
        def check():
            if self.comparison.metadata(self.run_id, artifact_id) != artifact:
                raise PermissionError("coordinator stage metadata changed")
            self._current(operation="read", parents=(artifact.event_id,), qualified=qualified)
        check()
        selected = self._guarded_comparison(check)
        body = json.loads(selected._read_authorized(run_id=self.run_id, artifact_id=artifact_id,
            permissions=self.manifests.local.permissions,
            purpose=coordinator_purpose(self.manifests.experiment_id, self.run_id, "read")))
        if (body["binding_sha256"] != self.binding_sha256 or body["stage"] != artifact.record["metadata"]["stage"]
                or body["schema"] != "flora-experiment-coordinator-stage-v1"
                or body["qualified_phases_required"] is not qualified or body["part1_accepted"] is not False):
            raise ValueError("coordinator stage body differs from its exact registered control")
        check()
        return body

    def readiness(self, *, adapters: Mapping[str, object]):
        """Fresh preflight, without executing models or inventing readiness."""
        self._current()
        if set(adapters) - ARMS:
            raise ValueError("unknown execution arm")
        reasons = []
        if self.phase_router is None:
            reasons.append("missing_phase_router")
        if self.provider_custody is None:
            reasons.append("missing_provider_attempt_custody")
        if any(getattr(authority.registry, "connection", self.manifests.connection) is not self.manifests.connection
               or getattr(authority.permissions, "connection", self.manifests.connection) is not self.manifests.connection
               for authority in self.manifests.authorities.values()):
            reasons.append("missing_owned_cohort_backend_port")
        for arm in sorted(_NATIVE_ARMS):
            adapter = adapters.get(arm)
            if adapter is None:
                reasons.append("missing_adapter:" + arm)
                continue
            if (not isinstance(adapter, NativeArmAdapter) or adapter.custody is not self.comparison
                    or adapter.run_id != self.run_id or adapter.run_plan.digest() != self.plan.digest()
                    or adapter.frozen != self.native_plans[arm]):
                raise ValueError("native adapter differs from actual registered frozen coordinator")
            for name in ("worker", "codec", "reads", "meter"):
                if getattr(adapter, name) is None:
                    reasons.append("missing_native_port:" + arm + ":" + name)
            if all(getattr(adapter, name) is not None for name in ("worker", "codec", "reads", "meter")):
                if not isinstance(adapter.reads, SelectedNativeReadServices):
                    reasons.append("missing_owned_selected_reader:" + arm)
                try:
                    adapter._available()
                except ArmStopped:
                    reasons.append("native_route_unavailable:" + arm)
        comparator = adapters.get("general_model_memory")
        if comparator is None:
            reasons.append("missing_adapter:general_model_memory")
        elif (not isinstance(comparator, GeneralMemoryArmAdapter)
                or comparator.attempt_custody is not self.provider_custody
                or comparator.task_id_for is None
                or getattr(comparator.recorder, "custody", None) is not self.comparison
                or getattr(comparator.recorder, "run_id", None) != self.run_id
                or any(self.plan.binding_for(case, phase, "general_model_memory").lineage_sha256
                       != comparator.configuration.digest() for case, phase in self.histories)):
            raise ValueError("comparator differs from exact actual provider/custody configuration")
        if not reasons:
            try:
                self._current(qualified=True)
            except (PermissionError, ValueError, KeyError, RuntimeBlocked):
                reasons.append("phase_qualification_unavailable")
        payload = {"status": "preflight_blocked" if reasons else "supplied_ports_ready",
                   "reasons": sorted(set(reasons)), "attempted": False, "behavioral_result": "not_collected"}
        artifact_id = "coordinator:preflight:" + canonical_sha256(payload)
        self._put(artifact_id=artifact_id, stage="preflight", payload=payload,
            parents=(self._required_binding().event_id,))
        return CoordinatorOutcome(payload["status"], artifact_id, tuple(payload["reasons"]))

    def _required_binding(self):
        artifact = self.comparison.metadata(self.run_id, "coordinator:binding")
        if artifact is None or artifact.record["metadata"].get("binding_sha256") != self.binding_sha256:
            raise ValueError("coordinator binding has not been registered")
        return artifact

    def _partial_receipts(self):
        """Registered metadata only; these are not accepted execution records."""
        invocations = {entry.invocation_id: (entry.case_id, entry.phase, arm)
                       for arm, frozen in self.native_plans.items() for entry in frozen.entries}
        private = None if self.phase_router is None else self.phase_router.runtime.private
        native = []
        for event in self.comparison.log.replay():
            invocation = event.provenance.derivation_activity_id
            if (event.scope != self.comparison.scope or invocation not in invocations
                    or event.provenance.responsible_component != "flora-qualified-runtime"
                    or event.event_type not in {"qualified_model_input", "qualified_model_output", "qualified_model_attempt_failure"}):
                continue
            case, phase, arm = invocations[invocation]
            if event.provenance.model_id != self.plan.binding_for(case, phase, arm).model_artifact_sha256:
                raise ValueError("partial canonical receipt names a different frozen checkpoint")
            indexed = None if private is None else private._fetch(private.records, private._key(event.event_type, invocation))
            if indexed is not None and (
                    indexed["schema"] != "flora-runtime-private-step-v1" or indexed["event_id"] != event.event_id
                    or indexed["event_sha256"] != event.event_sha256 or indexed["invocation_id"] != invocation
                    or indexed["stage"] != event.event_type or indexed["raw"]["object_id"] != event.payload_reference
                    or indexed["raw"]["plaintext_sha256"] != event.content_digest):
                raise ValueError("partial receipt differs from authenticated runtime-private metadata")
            native.append({"event_id": event.event_id, "event_sha256": event.event_sha256, "kind": event.event_type,
                "invocation_id": invocation, "private_metadata_registered": indexed is not None,
                "private_metadata_sha256": None if indexed is None else indexed["record_sha256"],
                "custody_state": "private_registered" if indexed is not None else "canonical_only"})
        provider = []
        if self.provider_custody is not None:
            for (case, phase), task in sorted(self.provider_task_ids.items()):
                for kind in ("task", "authorization", "observation"):
                    record = self.provider_custody._metadata(task, kind)
                    if record is not None:
                        provider.append({"case_id": case, "phase": phase, "task_id": task,
                                         "kind": kind, "event_id": record["event_id"], "record_sha256": record["record_sha256"]})
        return {"native": sorted(native, key=lambda value: value["event_id"]), "provider": provider,
                "accepted_execution": False}

    def _execution_adapters(self, adapters, check):
        prepared = {}
        for arm, original in adapters.items():
            adapter = copy(original)
            if arm in _NATIVE_ARMS:
                adapter.custody = self._guarded_comparison(check)
                reads = copy(original.reads)
                reads.factory = _CohortFencedSessionFactory(self, original.reads)
                for method_name in ("prepare_context", "authorize_context", "recover_judgment", "verify_native_result"):
                    method = getattr(reads, method_name)
                    async def current_call(*args, _method=method, **kwargs):
                        check()
                        value = await _method(*args, **kwargs)
                        check()
                        return value
                    setattr(reads, method_name, current_call)
                adapter.reads = reads
            else:
                adapter.recorder = copy(original.recorder)
                adapter.recorder.custody = self._guarded_comparison(check)
                disclosure = copy(original.disclosure)
                authorize = original.disclosure.authorize
                def authorize_checked(*args, **kwargs):
                    check()
                    value = authorize(*args, **kwargs)
                    check()
                    return value
                disclosure.authorize = authorize_checked
                adapter.disclosure = adapter.recorder.disclosure = disclosure
                task_id_for = original.task_id_for
                def exact_task(request):
                    check()
                    task = task_id_for(request)
                    if task != self.provider_task_ids[(request.case_id, request.phase)]:
                        raise PermissionError("provider task differs from frozen coordinator dispatch ID")
                    return task
                adapter.task_id_for = exact_task
            prepare, execute = adapter.prepare, adapter.execute
            async def prepare_checked(request, _prepare=prepare):
                check()
                value = await _prepare(request)
                check()
                return value
            async def execute_checked(request, _execute=execute):
                check()
                value = await _execute(request)
                check()
                return value
            adapter.prepare, adapter.execute = prepare_checked, execute_checked
            prepared[arm] = adapter
        return prepared

    async def execute(self, *, adapters: Mapping[str, object]):
        if self._started or self.comparison.metadata(self.run_id, "coordinator:running") is not None:
            raise ValueError("frozen run already started; explicit interrupted recovery is required")
        readiness = self.readiness(adapters=adapters)
        if readiness.status != "supplied_ports_ready":
            return readiness
        self._started = True
        running = self._put(artifact_id="coordinator:running", stage="running",
            payload={"status": "started", "execution_nonce": secrets.token_hex(16), "attempted": True},
            parents=(self._required_binding().event_id, self.comparison.metadata(self.run_id, readiness.artifact_id).event_id),
            qualified=True)
        def check():
            self._current(operation="capture", parents=tuple(running.record["parent_event_ids"]), qualified=True)
        selected = self._guarded_comparison(check)
        policy = copy(self.evidence)
        policy.custody = selected
        actual_adapters = self._execution_adapters(adapters, check)
        try:
            run = await run_paired(plan=self.plan, histories=self.histories, questions=self.questions,
                adapters=actual_adapters, evidence_policy=policy)
            check()
            executions = {key: value for arm in _NATIVE_ARMS for key, value in actual_adapters[arm].execution_records.items()}
            selected.save_run(run_id=self.run_id, run=run, occurred_at=self.clock(),
                execution_records=executions, evidence_policy=policy)
            validate_run(run)
            retained = self.comparison.metadata(self.run_id, "run")
            artifact = self._put(artifact_id="coordinator:completed", stage="completed",
                payload={"status": "completed_custody", "attempts": [attempt.receipt() for attempt in run.attempts],
                         "registered_run_sha256": retained.record["record_sha256"], "partial_receipts": self._partial_receipts(),
                         "behavioral_result": "not_collected"}, parents=(running.event_id, retained.event_id), qualified=True)
            return CoordinatorOutcome("completed_custody", artifact.record["artifact_id"], run=run)
        except asyncio.CancelledError:
            # Do not resume reads, inference, or custody writes after cancellation.
            # The already durable running marker is reconciled explicitly later.
            raise
        except Exception as error:
            code = ("authority_withdrawn" if isinstance(error, PermissionError) else
                    "custody_validation_failed" if isinstance(error, ValueError) else
                    "coordinator_timeout" if isinstance(error, TimeoutError) else "execution_port_failure")
            self._put(artifact_id="coordinator:interrupted", stage="interrupted",
                payload={"status": "attempted_failure", "reason": code, "partial_receipts": self._partial_receipts(),
                         "behavioral_result": "not_collected"}, parents=(running.event_id,))
            raise

    def recover_interrupted(self):
        """Explicit metadata reconciliation; it never reruns an invocation."""
        running = self.comparison.metadata(self.run_id, "coordinator:running")
        if running is None or self.comparison.metadata(self.run_id, "coordinator:completed") is not None:
            raise ValueError("no interrupted registered run is awaiting reconciliation")
        self.recover_stage(artifact_id="coordinator:running")
        prior = self.comparison.metadata(self.run_id, "coordinator:interrupted")
        if prior is not None:
            self.recover_stage(artifact_id="coordinator:interrupted")
            return prior
        return self._put(artifact_id="coordinator:interrupted", stage="interrupted",
            payload={"status": "interrupted_custody", "reason": "explicit_recovery", "partial_receipts": self._partial_receipts(),
                     "behavioral_result": "not_collected"}, parents=(running.event_id,))

    def bind_sealed_assessment(self, *, collection_id: str):
        identifier(collection_id, "collection_id")
        completed = self.recover_stage(artifact_id="coordinator:completed")
        retained = self.comparison.metadata(self.run_id, "run")
        if completed["payload"]["registered_run_sha256"] != retained.record["record_sha256"]:
            raise PermissionError("completed run custody changed before assessment binding")
        def check():
            self._current(qualified=True)
        selected = self._guarded_comparison(check)
        assessment = copy(self.assessment)
        assessment.comparison = selected
        collection = assessment.recover_collection(run_id=self.run_id, collection_id=collection_id,
            permissions=self.manifests.local.permissions)
        if not collection.sealed:
            raise PermissionError("assessment has no actual independently authenticated seal")
        references = {kind: self.comparison.metadata(self.run_id, artifact_id) for kind, artifact_id in {
            "run": "run", "blind_pack": "blind_pack", "spec": assessment_artifact_id(collection_id, "spec"),
            "seal": assessment_artifact_id(collection_id, "seal")}.items()}
        if any(artifact is None for artifact in references.values()) or collection.spec.plan_sha256 != self.plan.digest():
            raise ValueError("assessment does not bind exact stored run and material")
        check()
        artifact = self._put(artifact_id="coordinator:assessment:" + collection_id, stage="sealed_assessment",
            payload={"status": "externally_sealed", "collection_id": collection_id,
                     "spec_sha256": collection.spec.digest(), "result_materials": {
                         kind: {"artifact_id": value.record["artifact_id"], "event_id": value.event_id,
                                "record_sha256": value.record["record_sha256"]} for kind, value in references.items()},
                     "part1_qualification": "not_accepted"},
            parents=tuple(value.event_id for value in references.values()), qualified=True)
        return CoordinatorOutcome("externally_sealed", artifact.record["artifact_id"])
