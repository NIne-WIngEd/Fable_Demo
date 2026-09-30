"""Private experiment/limited-builder manifests on the selected memory fabric.

No corpus, synthetic host, target, threshold, model or qualification is generated.
Shape checks are not qualification; independently supplied signed receipts and
actual source material remain required at their respective boundaries.
"""
from __future__ import annotations

import base64
from copy import copy
from dataclasses import dataclass, field
import json
from pathlib import PurePosixPath
from typing import Callable, Protocol

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cognitive_kernel.canonical import canonical_sha256, normalize_timestamp, require_sha256
from cognitive_kernel.contracts import ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent

from ..comparator import encoded, identifier, sha
from .claims import _dml_placeholder, _record_json, _rows, configure_xtdb_connection
from .formation_context import register_experience_source
from .formation_registry import RegisteredEncryptedFormationCustody
from .judgment_lineage import _INTERNAL_EVENT_TYPES
from .object_store import EncryptedObjectPlane

_TABLE = "flora_experiment_manifest_artifacts"
_EVENT = "experiment_manifest_artifact"
_SPLITS = frozenset({"training", "pilot", "heldout", "transfer"})
_AXES = frozenset({"source_family", "generator_family", "scenario_ancestry", "person_family", "source_ancestry"})
_KINDS = frozenset({"cohort", "recipe", "linked_case", "part1", "transfer"})


def manifest_purpose(experiment_id: str, operation: str) -> str:
    identifier(experiment_id, "experiment_id")
    if operation not in {"capture", "read", "qualification"}:
        raise ValueError("unknown manifest operation")
    return "experiment_manifest_" + operation + ":" + canonical_sha256(experiment_id)


def cohort_source_purpose(experiment_id: str, split: str) -> str:
    identifier(experiment_id, "experiment_id")
    if split not in _SPLITS:
        raise ValueError("unknown cohort split")
    return "experiment_cohort_" + split + ":" + canonical_sha256(experiment_id)


class _GuardedBackend:
    def __init__(self, backend, check):
        self.backend, self.check = backend, check
    def __getattr__(self, name):
        return getattr(self.backend, name)
    def get_object(self, namespace, object_id):
        self.check()
        value = self.backend.get_object(namespace, object_id)
        self.check()  # Ciphertext is still sealed: reject before AEAD decrypt.
        return value
    def put_if_absent(self, namespace, object_id, value):
        self.check()
        self.backend.put_if_absent(namespace, object_id, value)
        self.check()


class _GuardedObjects:
    def __init__(self, objects, check):
        self.objects, self.check = copy(objects), check
        self.objects.backend = _GuardedBackend(objects.backend, check)
    def __copy__(self):
        return type(self)(self.objects, self.check)
    @property
    def backend(self):
        return self.objects.backend
    @backend.setter
    def backend(self, value):
        self.objects.backend = value
    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "objects"), name)
    def get(self, raw):
        self.check()
        # A restored instance-bound method may still point to the original
        # unguarded plane after copy(). Execute the actual codec on this facade
        # so its backend fence remains between ciphertext fetch and AEAD.
        value = EncryptedObjectPlane.get(self, raw)
        self.check()
        return value
    def put(self, value):
        self.check()
        raw = EncryptedObjectPlane.put(self, value)
        self.check()
        return raw
    def recover_reference(self, **kwargs):
        self.check()
        raw = EncryptedObjectPlane.recover_reference(self, **kwargs)
        self.check()
        return raw


@dataclass(frozen=True)
class SelectedSourceAuthority:
    """Actual isolated host registry/log/permission plane; no foreign grant proxy."""
    registry: object = field(repr=False)
    log: object = field(repr=False)
    permissions: object = field(repr=False)
    objects: object = field(repr=False)

    def __post_init__(self):
        if (self.registry.scope != self.log.scope or self.registry.scope != self.permissions.scope
                or self.registry.scope != self.objects.scope
                or self.registry.authority_namespace_id != self.permissions.authority_namespace_id):
            raise ValueError("source authority crosses host or namespace")

    @property
    def authority_id(self):
        return canonical_sha256([self.registry.scope.metadata_record(), self.registry.authority_namespace_id])

    def binding(self, event_id: str, *, original: bool = True) -> dict:
        """Metadata only, including actual transitive committed source lineage."""
        identifier(event_id, "source event ID")
        if not isinstance(original, bool):
            raise ValueError("source original flag must be explicit")
        committed = {entry.event.event_id: entry for entry in self.log.replay_committed()}
        pending, bindings = [event_id], {}
        while pending:
            current = pending.pop()
            if current in bindings:
                continue
            entry, source = committed.get(current), self.registry.lookup(current)
            raw = None if source is None else self.registry.raw_reference(source.object_ref)
            if entry is None or entry.recorded_at is None or source is None or raw is None:
                raise ValueError("manifest source lacks committed selected metadata")
            event = entry.event
            if (event.scope != self.registry.scope or source.evidence.scope != event.scope or raw.scope != event.scope
                    or source.evidence.authority_namespace_id != self.registry.authority_namespace_id
                    or event.payload_reference != raw.object_id or event.content_digest != raw.plaintext_sha256
                    or source.evidence.content_digest != event.content_digest
                    or source.evidence.recorded_at != normalize_timestamp(entry.recorded_at.isoformat())
                    or tuple(source.evidence.parent_refs) != event.parent_event_ids
                    or (original and event.event_type in (_INTERNAL_EVENT_TYPES | {_EVENT}))):
                raise ValueError("source is not exact registered original evidence")
            bindings[current] = {"event_id": current, "event_sha256": event.event_sha256,
                "registration_sha256": source.registration_sha256, "content_sha256": raw.plaintext_sha256,
                "object_id": raw.object_id, "parent_event_ids": list(event.parent_event_ids),
                "event_type": event.event_type, "source_role": source.evidence.role,
                "provenance_type": event.provenance.provenance_type,
                "stream_position": entry.stream_position,
                "recorded_at": normalize_timestamp(entry.recorded_at.isoformat())}
            pending.extend(event.parent_event_ids)
        return {"authority_id": self.authority_id, "scope": self.registry.scope.metadata_record(),
            "authority_namespace_id": self.registry.authority_namespace_id, "event_id": event_id,
            "original": original, "closure": [bindings[key] for key in sorted(bindings)]}

    def gate(self, gate: dict) -> None:
        if set(gate) != {"authority_id", "event_id", "purpose", "original", "binding_sha256"}:
            raise ValueError("source gate fields changed")
        require_sha256(gate["authority_id"], "authority_id")
        require_sha256(gate["binding_sha256"], "binding_sha256")
        identifier(gate["purpose"], "source use purpose")
        actual = self.binding(gate["event_id"], original=gate["original"])
        source = self.registry.lookup(gate["event_id"])
        if (gate["authority_id"] != self.authority_id or canonical_sha256(actual) != gate["binding_sha256"]
                or self.permissions.permits(source, gate["purpose"]) is not True):
            raise PermissionError("manifest source lineage or current purpose changed")

    def read(self, gate: dict) -> bytes:
        self.gate(gate)
        binding = self.binding(gate["event_id"], original=gate["original"])
        if any(item["event_type"] in (_INTERNAL_EVENT_TYPES | {_EVENT}) for item in binding["closure"]):
            raise PermissionError("private internal material requires its dedicated typed custody reader")
        source = self.registry.lookup(gate["event_id"])
        check = lambda: self.gate(gate)
        reader = RegisteredEncryptedFormationCustody(registry=self.registry,
            objects=_GuardedObjects(self.objects, check))
        value = reader.read(self.registry.scope, source.object_ref)
        self.gate(gate)
        return value


@dataclass(frozen=True)
class CohortEntry:
    entry_id: str
    authority_id: str
    event_id: str
    split: str
    source_family: str
    generator_family: str
    generator_sha256: str
    scenario_root: str
    scenario_parents: tuple[str, ...]
    person_family: str
    person_role: str
    usage_role: str

    def record(self):
        for name in ("entry_id", "event_id", "source_family", "generator_family", "scenario_root",
                     "person_family", "person_role", "usage_role"):
            identifier(getattr(self, name), name)
        require_sha256(self.authority_id, "authority_id")
        require_sha256(self.generator_sha256, "generator_sha256")
        if self.split not in _SPLITS or tuple(sorted(set(self.scenario_parents))) != self.scenario_parents:
            raise ValueError("cohort split or scenario ancestry is noncanonical")
        for value in self.scenario_parents:
            identifier(value, "scenario parent")
        return {**vars(self), "scenario_parents": list(self.scenario_parents)}


@dataclass(frozen=True)
class SplitIsolationRule:
    left: str
    right: str
    disjoint_axes: tuple[str, ...]
    shared_axes: tuple[str, ...]

    def record(self):
        if (self.left not in _SPLITS or self.right not in _SPLITS or self.left >= self.right
                or set(self.disjoint_axes) & set(self.shared_axes)
                or set(self.disjoint_axes) | set(self.shared_axes) != _AXES
                or tuple(sorted(set(self.disjoint_axes))) != self.disjoint_axes
                or tuple(sorted(set(self.shared_axes))) != self.shared_axes):
            raise ValueError("each split pair must explicitly partition disjoint and shared lineage axes")
        return {"left": self.left, "right": self.right,
            "disjoint_axes": list(self.disjoint_axes), "shared_axes": list(self.shared_axes)}


def validate_cohort(entries: tuple[CohortEntry, ...], rules: tuple[SplitIsolationRule, ...], bindings: dict) -> None:
    if not entries or len({entry.entry_id for entry in entries}) != len(entries):
        raise ValueError("cohort has empty or reused entry IDs")
    splits = sorted({entry.split for entry in entries})
    required = {(left, right) for i, left in enumerate(splits) for right in splits[i + 1:]}
    by_pair = {}
    for rule in rules:
        rule.record()
        if (rule.left, rule.right) in by_pair:
            raise ValueError("split isolation rule is duplicated")
        by_pair[(rule.left, rule.right)] = rule
    if set(by_pair) != required:
        raise ValueError("cohort needs a frozen rule for every present split pair")
    def axes(entry):
        binding = bindings[entry.entry_id]
        return {"source_family": {entry.source_family}, "generator_family": {entry.generator_family},
            "scenario_ancestry": {entry.scenario_root, *entry.scenario_parents}, "person_family": {entry.person_family},
            "source_ancestry": {value for source in binding["closure"] for value in (
                canonical_sha256([binding["authority_id"], source["event_id"]]), "content:" + source["content_sha256"])}}
    for entry in entries:
        entry.record()
    for i, left in enumerate(entries):
        for right in entries[i + 1:]:
            if left.split == right.split:
                continue
            rule = by_pair[tuple(sorted((left.split, right.split)))]
            for axis in rule.disjoint_axes:
                if axes(left)[axis] & axes(right)[axis]:
                    raise ValueError("cohort leaks declared-disjoint " + axis + " across splits")


class Part1ResultValidator(Protocol):
    """Independent semantic result authority, including actual assessment seal.

    Must verify native/ablation/comparator qualifications, phase exclusions,
    frozen protocol/rubric/threshold, signed blind collection, all failures,
    budgets, and the supplied acceptance decision. No implementation is invented.
    """
    artifact_sha256: str
    def verify(self, *, claim: dict, materials: dict[str, bytes]) -> bool: ...


class Part1MaterialReader(Protocol):
    """Explicit typed custody; a source-purpose grant alone cannot open controls."""
    artifact_sha256: str
    @property
    def binding_sha256(self) -> str: ...
    def read(self, *, name: str, authority: SelectedSourceAuthority, gate: dict) -> bytes: ...


@dataclass(frozen=True)
class RegisteredPart1Material:
    """Trusted deployment route, bound again by the independent signed result.

    The controller is an actual selected custody instance, not an inference
    callback. Phase history and its current authority are supplied unchanged.
    """
    name: str
    authority_id: str
    event_id: str
    kind: str
    parameters: tuple[tuple[str, str], ...]
    controller: object = field(repr=False, compare=False)
    history: object | None = field(default=None, repr=False, compare=False)
    history_authority: object | None = field(default=None, repr=False, compare=False)
    historical_bindings: dict | None = field(default=None, repr=False, compare=False)

    def record(self):
        identifier(self.name, "material name")
        identifier(self.event_id, "material event")
        require_sha256(self.authority_id, "material authority")
        expected = {"comparison": {"run_id", "artifact_id", "artifact_kind", "custody_purpose"},
            "assessment_spec": {"run_id", "collection_id"}, "assessment_seal": {"run_id", "collection_id"},
            "phase_snapshot": {"snapshot_id", "invocation_id"}, "provider_observation": {"task_id"}}
        if (self.kind not in expected or tuple(sorted(self.parameters)) != self.parameters
                or len(dict(self.parameters)) != len(self.parameters)
                or set(dict(self.parameters)) != expected[self.kind]):
            raise ValueError("unknown or noncanonical typed material route")
        for _, value in self.parameters:
            identifier(value, "material locator")
        if self.kind == "phase_snapshot":
            from .experiment_runtime import RuntimeRoleBinding
            if (self.history is None or self.history_authority is None or self.historical_bindings is None
                    or set(self.historical_bindings) != {"memory_formation", "personality_judgment"}):
                raise ValueError("phase material needs actual frozen history, authority and historical producer bindings")
            history_sha256 = require_sha256(self.history.digest(), "phase history")
            bindings = {}
            for role, binding in self.historical_bindings.items():
                if type(binding) is not RuntimeRoleBinding:
                    raise TypeError("historical producer binding must use the actual runtime contract")
                contracts = {name: getattr(binding.codec, name) for name in (
                    "input_contract_id", "input_contract_sha256", "output_contract_id", "output_contract_sha256")}
                for label, value in contracts.items():
                    (require_sha256 if label.endswith("sha256") else identifier)(value, label)
                identifier(binding.adapter.adapter_id, "producer adapter")
                bindings[role] = {"checkpoint_path": str(binding.checkpoint_path), **contracts,
                    "adapter_id": binding.adapter.adapter_id, "execution_location": binding.adapter.execution_location}
        elif self.history is not None or self.history_authority is not None or self.historical_bindings is not None:
            raise ValueError("non-phase material cannot add a history authority")
        else:
            history_sha256, bindings = None, None
        return {"name": self.name, "authority_id": self.authority_id, "event_id": self.event_id,
            "kind": self.kind, "parameters": [list(value) for value in self.parameters],
            "history_sha256": history_sha256, "historical_bindings": bindings}


class RegisteredPart1MaterialReader:
    """Concrete dispatcher for the implemented selected private custody paths.

    This authenticates storage routes and current controller permission. It
    does not decide result quality or implement producer qualification codecs.
    Unknown kinds and generic blind-key routes fail before plaintext access.
    """
    def __init__(self, *, routes: tuple[RegisteredPart1Material, ...], artifact_sha256: str):
        self.artifact_sha256 = require_sha256(artifact_sha256, "material reader artifact")
        if not routes or len({route.name for route in routes}) != len(routes):
            raise ValueError("typed material routes must be nonempty and unique")
        self.routes = {route.name: route for route in routes}
        self._records = {route.name: route.record() for route in routes}

    @property
    def binding_sha256(self):
        records = {name: route.record() for name, route in self.routes.items()}
        if records != self._records:
            raise PermissionError("enrolled private material routes changed")
        return canonical_sha256(records)

    @staticmethod
    def _comparison(controller, authority, check):
        from .comparison_custody import XTDBComparisonCustody
        if (type(controller) is not XTDBComparisonCustody or controller.registry is not authority.registry
                or controller.log is not authority.log or controller.objects is not authority.objects
                or controller.scope != authority.registry.scope
                or controller.authority_namespace_id != authority.registry.authority_namespace_id):
            raise PermissionError("typed comparison route crosses actual registered host custody")
        guarded = copy(controller)
        guarded.objects = _GuardedObjects(controller.objects, check)
        guarded.raw_custody = RegisteredEncryptedFormationCustody(registry=controller.registry, objects=guarded.objects)
        return guarded

    def read(self, *, name, authority, gate):
        route = self.routes.get(name)
        if (route is None or route.authority_id != authority.authority_id
                or route.event_id != gate["event_id"] or gate["authority_id"] != authority.authority_id):
            raise PermissionError("qualification material has no exact registered private route")
        frozen_digest = self.binding_sha256
        parameters = dict(route.parameters)
        def check():
            if self.binding_sha256 != frozen_digest:
                raise PermissionError("private material route changed during use")
            authority.gate(gate)
        check()
        controller = route.controller
        if route.kind == "comparison":
            allowed = {"plan", "run", "blind_pack", "history", "question", "context", "output", "rejected_output"}
            if parameters["artifact_kind"] not in allowed:
                raise PermissionError("comparison private kind requires a dedicated qualified route")
            selected = self._comparison(controller, authority, check)
            def controller_gate():
                check()
                artifact = selected.metadata(parameters["run_id"], parameters["artifact_id"])
                if (artifact is None or artifact.event_id != route.event_id
                        or artifact.record["kind"] != parameters["artifact_kind"]):
                    raise PermissionError("comparison material locator differs from exact registered artifact")
            controller_gate()
            value = selected.read(run_id=parameters["run_id"], artifact_id=parameters["artifact_id"],
                permissions=authority.permissions, purpose=parameters["custody_purpose"])
            controller_gate()
        elif route.kind in {"assessment_spec", "assessment_seal"}:
            from .assessment_custody import XTDBAssessmentCustody, assessment_artifact_id
            if type(controller) is not XTDBAssessmentCustody:
                raise PermissionError("assessment route needs the actual selected seal controller")
            selected = copy(controller)
            selected.comparison = self._comparison(controller.comparison, authority, check)
            kind = "spec" if route.kind == "assessment_spec" else "seal"
            artifact_id = assessment_artifact_id(parameters["collection_id"], kind)
            artifact = selected.comparison.metadata(parameters["run_id"], artifact_id)
            if (artifact is None or artifact.event_id != route.event_id or artifact.record["kind"] != route.kind):
                raise PermissionError("assessment route differs from its exact immutable collection artifact")
            collection = selected.recover_collection(run_id=parameters["run_id"], collection_id=parameters["collection_id"],
                permissions=authority.permissions)
            if not collection.sealed:
                raise PermissionError("Part1 assessment material requires an independently authenticated actual seal")
            value = selected._read(run_id=parameters["run_id"], collection_id=parameters["collection_id"],
                kind=kind, permissions=authority.permissions)
            # Seal/rating permissions are separate from this artifact's grant.
            if not selected.recover_collection(run_id=parameters["run_id"], collection_id=parameters["collection_id"],
                    permissions=authority.permissions).sealed:
                raise PermissionError("actual assessment seal became unavailable during qualification")
            check()
            if selected.comparison.metadata(parameters["run_id"], artifact_id) != artifact:
                raise PermissionError("assessment artifact changed during seal recovery")
        elif route.kind == "phase_snapshot":
            from .phase_snapshots import XTDBPhaseSnapshotCustody
            from .phase_routes import SelectedPhaseRoute
            if (type(controller) is not XTDBPhaseSnapshotCustody or controller.runtime.sources is not authority.registry
                    or controller.runtime.log is not authority.log or controller.runtime.objects is not authority.objects
                    or controller.scope != authority.registry.scope
                    or controller.authority_namespace_id != authority.registry.authority_namespace_id):
                raise PermissionError("phase route crosses actual host custody")
            selected, runtime = copy(controller), copy(controller.runtime)
            runtime.objects = _GuardedObjects(authority.objects, check)
            selected.runtime = runtime
            record = selected.metadata(parameters["snapshot_id"])
            if record is None or record["event_id"] != route.event_id:
                raise PermissionError("phase material differs from exact registered snapshot")
            qualified = SelectedPhaseRoute(custody=selected, snapshot_id=parameters["snapshot_id"], history=route.history,
                history_authority=route.history_authority, historical_bindings=route.historical_bindings,
                invocation_id_for=lambda *args: parameters["invocation_id"])
            value = encoded(qualified.snapshot.record)
            qualified.check_live()
        elif route.kind == "provider_observation":
            from .provider_attempt_custody import XTDBProviderAttemptCustody, audit_purpose
            if (type(controller) is not XTDBProviderAttemptCustody or controller.registry is not authority.registry
                    or controller.log is not authority.log or controller.objects is not authority.objects
                    or controller.permissions is not authority.permissions):
                raise PermissionError("provider route crosses actual observed-attempt custody")
            selected = copy(controller)
            selected.objects = _GuardedObjects(authority.objects, check)
            record = selected._metadata(parameters["task_id"], "observation")
            if record is None or record["event_id"] != route.event_id:
                raise PermissionError("provider material differs from exact signed observation")
            selected.recover(task_id=parameters["task_id"])
            value = selected._read_source(route.event_id, audit_purpose(selected.run_id))
            if selected._metadata(parameters["task_id"], "observation") != record:
                raise PermissionError("provider observed-attempt metadata changed")
        else:
            raise PermissionError("private qualification material kind is unavailable")
        check()
        binding = authority.binding(route.event_id, original=gate["original"])
        source = next(item for item in binding["closure"] if item["event_id"] == route.event_id)
        if not isinstance(value, bytes) or sha(value) != source["content_sha256"]:
            raise ValueError("typed recovery bytes differ from exact registered material")
        check()
        return value


class XTDBExperimentManifestCustody:
    def __init__(self, *, experiment_id: str, local: SelectedSourceAuthority,
                 authorities: tuple[SelectedSourceAuthority, ...], connection, control_anchor_event_id: str,
                 lineage_public_key: bytes, approved_lineage_key_sha256: str,
                 qualification_public_key: bytes, approved_qualification_key_sha256: str,
                 part1_validator: Part1ResultValidator | None, clock: Callable[[], str],
                 part1_material_reader: Part1MaterialReader | None = None):
        identifier(experiment_id, "experiment_id")
        identifier(control_anchor_event_id, "control_anchor_event_id")
        if (sha(lineage_public_key) != require_sha256(approved_lineage_key_sha256, "lineage key")
                or sha(qualification_public_key) != require_sha256(approved_qualification_key_sha256, "qualification key")
                or lineage_public_key == qualification_public_key):
            raise PermissionError("lineage and result keys need distinct independent enrollment")
        self.experiment_id, self.local, self.connection = experiment_id, local, connection
        self.authorities = {authority.authority_id: authority for authority in authorities}
        if len(self.authorities) != len(authorities) or self.authorities.get(local.authority_id) is not local:
            raise ValueError("source authorities must be exact and unique, including local custody")
        self.scope, self.namespace = local.registry.scope, local.registry.authority_namespace_id
        self.scope_digest = canonical_sha256([self.scope.metadata_record(), self.namespace, experiment_id])
        self.lineage_key, self.qualification_key = Ed25519PublicKey.from_public_bytes(lineage_public_key), Ed25519PublicKey.from_public_bytes(qualification_public_key)
        self.lineage_key_sha256, self.qualification_key_sha256 = sha(lineage_public_key), sha(qualification_public_key)
        self.part1_validator, self.clock = part1_validator, clock
        self.part1_material_reader = part1_material_reader
        self.material_reader_sha256 = None if part1_material_reader is None else require_sha256(part1_material_reader.artifact_sha256, "material reader artifact")
        self.material_routes_sha256 = None if part1_material_reader is None else require_sha256(part1_material_reader.binding_sha256, "material routes")
        self.validator_sha256 = None if part1_validator is None else require_sha256(part1_validator.artifact_sha256, "result validator artifact")
        self.anchor = self._gate(local.authority_id, control_anchor_event_id, manifest_purpose(experiment_id, "capture"), original=True)
        configure_xtdb_connection(connection)

    def _gate(self, authority_id, event_id, purpose, *, original=True):
        authority = self.authorities.get(authority_id)
        if authority is None:
            raise ValueError("manifest has no actual enrolled selected source authority")
        binding = authority.binding(event_id, original=original)
        gate = {"authority_id": authority_id, "event_id": event_id, "purpose": purpose,
            "original": original, "binding_sha256": canonical_sha256(binding)}
        authority.gate(gate)
        return gate

    def _check_gates(self, gates):
        for gate in gates:
            authority = self.authorities.get(gate["authority_id"])
            if authority is None:
                raise PermissionError("source authority is no longer enrolled")
            authority.gate(gate)

    def _id(self, kind, manifest_id):
        if kind not in _KINDS:
            raise ValueError("unknown private manifest kind")
        identifier(manifest_id, "manifest_id")
        return canonical_sha256([self.scope_digest, kind, manifest_id])

    def metadata(self, kind, manifest_id):
        key = self._id(kind, manifest_id)
        rows = _rows(self.connection.execute(f"SELECT * FROM {_TABLE} FOR VALID_TIME ALL WHERE _id = %s", (key,)))
        if len(rows) > 1:
            raise ValueError("manifest has ambiguous immutable rows")
        if not rows:
            return None
        row, record = rows[0], json.loads(str(rows[0]["record_json"]))
        if (row["_id"] != key or row["scope_digest"] != self.scope_digest
                or record["schema"] != "flora-experiment-manifest-index-v1" or record["kind"] != kind
                or record["manifest_id"] != manifest_id or record["scope"] != self.scope.metadata_record()
                or record["namespace"] != self.namespace or record["experiment_id"] != self.experiment_id
                or row["record_sha256"] != record["record_sha256"]
                or canonical_sha256({k: v for k, v in record.items() if k != "record_sha256"}) != record["record_sha256"]):
            raise ValueError("manifest immutable metadata changed")
        source = self.local.registry.lookup(record["event_id"])
        event = next((event for event in self.local.log.replay() if event.event_id == record["event_id"]), None)
        raw = None if source is None else self.local.registry.raw_reference(source.object_ref)
        if (source is None or event is None or raw is None or event.event_type != _EVENT
                or event.scope != self.scope or event.provenance.responsible_component != "experiment_manifest_custody"
                or event.provenance.derivation_activity_id != "experiment_manifest:" + key + ":" + canonical_sha256({
                    "source_gates": record["source_gates"], "dependencies": record["dependencies"]})
                or event.event_sha256 != record["event_sha256"] or event.payload_reference != record["object_id"]
                or event.content_digest != record["content_sha256"] or raw.object_id != record["object_id"]
                or raw.plaintext_sha256 != record["content_sha256"]
                or source.registration_sha256 != record["registration_sha256"]
                or list(event.parent_event_ids) != record["parent_event_ids"]
                or tuple(source.evidence.parent_refs) != event.parent_event_ids):
            raise ValueError("manifest lacks exact Kurrent/XTDB/encrypted-object lineage")
        return record

    def _dependency(self, kind, manifest_id):
        self.recover(kind=kind, manifest_id=manifest_id)
        record = self.metadata(kind, manifest_id)
        return {"kind": kind, "manifest_id": manifest_id, "record_sha256": record["record_sha256"]}

    def _check_dependencies(self, dependencies, *, require_read=True):
        for dependency in dependencies:
            record = self.metadata(dependency["kind"], dependency["manifest_id"])
            if record is None or record["record_sha256"] != dependency["record_sha256"]:
                raise PermissionError("manifest dependency changed or disappeared")
            self._check_gates(record["source_gates"])
            if require_read:
                source = self.local.registry.lookup(record["event_id"])
                if self.local.permissions.permits(source, manifest_purpose(self.experiment_id, "read")) is not True:
                    raise PermissionError("private manifest dependency read is not currently allowed")

    def _save(self, kind, manifest_id, payload, gates, dependencies=()):
        gates = sorted({encoded(gate): gate for gate in (self.anchor, *gates)}.values(), key=encoded)
        dependencies = list(dependencies)
        def check():
            self._check_gates(gates)
            self._check_dependencies(dependencies)
            self._check_gates(gates)  # Dependencies may perform slow independent checks.
        check()
        body = {"schema": "flora-private-experiment-manifest-v1", "experiment_id": self.experiment_id,
            "kind": kind, "manifest_id": manifest_id, "payload": payload}
        content, key = encoded(body), self._id(kind, manifest_id)
        guard_sha256 = canonical_sha256({"source_gates": gates, "dependencies": dependencies})
        activity_prefix = "experiment_manifest:" + key + ":"
        prior = self.metadata(kind, manifest_id)
        if prior is not None:
            if (prior["content_sha256"] != sha(content) or prior["source_gates"] != gates or prior["dependencies"] != dependencies):
                raise ValueError("private manifest identity is immutable")
            check()
            return prior
        objects = _GuardedObjects(self.local.objects, check)
        raw = objects.put(content)
        parents = {gate["event_id"] for gate in gates if gate["authority_id"] == self.local.authority_id}
        parents.update(self.metadata(dep["kind"], dep["manifest_id"])["event_id"] for dep in dependencies)
        parents = tuple(sorted(parents))
        events = self.local.log.replay()
        existing = [event for event in events if event.provenance.derivation_activity_id.startswith(activity_prefix)]
        if len(existing) > 1:
            raise ValueError("manifest has duplicate canonical appends")
        if existing:
            event = existing[0]
            if (event.scope != self.scope or event.event_type != _EVENT or event.content_digest != raw.plaintext_sha256
                    or event.payload_reference != raw.object_id or event.parent_event_ids != parents
                    or event.provenance.derivation_activity_id != activity_prefix + guard_sha256):
                raise ValueError("manifest retry differs from canonical append")
        else:
            event = ExperienceEvent.create(event_type=_EVENT, scope=self.scope, occurred_at=normalize_timestamp(self.clock()),
                content_digest=raw.plaintext_sha256, provenance=ProvenanceReference.create(provenance_type="derived_inference",
                    source_reference_ids=parents, derivation_activity_id=activity_prefix + guard_sha256,
                    responsible_component="experiment_manifest_custody"), retention_class="ordinary_experience",
                storage_tier="raw_buffer", parent_event_ids=parents, payload_reference=raw.object_id)
            check()
            self.local.log.append(event, expected_revision=len(events) - 1)
        source = register_experience_source(event_id=event.event_id, raw=raw, registry=self.local.registry,
            log=self.local.log, objects=objects, role="derived_inference", modality="structured")
        record = {"schema": "flora-experiment-manifest-index-v1", "scope": self.scope.metadata_record(),
            "namespace": self.namespace, "experiment_id": self.experiment_id, "kind": kind, "manifest_id": manifest_id,
            "event_id": event.event_id, "event_sha256": event.event_sha256, "object_id": raw.object_id,
            "content_sha256": raw.plaintext_sha256, "registration_sha256": source.registration_sha256,
            "parent_event_ids": list(parents), "source_gates": gates, "dependencies": dependencies}
        record["record_sha256"] = canonical_sha256(record)
        values = {"_id": key, "scope_digest": self.scope_digest, "record_sha256": record["record_sha256"], "record_json": _record_json(record)}
        check()
        with self.connection.transaction():
            self.connection.execute(f"ASSERT NOT EXISTS (SELECT 1 FROM {_TABLE} FOR VALID_TIME ALL WHERE _id = %s::text)", (key,))
            self.connection.execute(f"INSERT INTO {_TABLE} ({', '.join(values)}) VALUES ("
                + ", ".join(_dml_placeholder(value) for value in values.values()) + ")", tuple(values.values()))
        check()
        return record

    def recover(self, *, kind, manifest_id):
        record = self.metadata(kind, manifest_id)
        if record is None:
            raise ValueError("private manifest is absent")
        def check():
            if self.metadata(kind, manifest_id) != record:
                raise PermissionError("manifest changed during private recovery")
            self._check_gates(record["source_gates"])
            self._check_dependencies(record["dependencies"])
            source = self.local.registry.lookup(record["event_id"])
            if self.local.permissions.permits(source, manifest_purpose(self.experiment_id, "read")) is not True:
                raise PermissionError("private manifest read is not currently authorized")
            self._check_gates(record["source_gates"])
        check()
        reader = RegisteredEncryptedFormationCustody(registry=self.local.registry, objects=_GuardedObjects(self.local.objects, check))
        source = self.local.registry.lookup(record["event_id"])
        body = json.loads(reader.read(self.scope, source.object_ref))
        if (set(body) != {"schema", "experiment_id", "kind", "manifest_id", "payload"}
                or body["schema"] != "flora-private-experiment-manifest-v1" or body["experiment_id"] != self.experiment_id
                or body["kind"] != kind or body["manifest_id"] != manifest_id or sha(encoded(body)) != record["content_sha256"]):
            raise ValueError("private manifest body differs from exact registered identity")
        for dep in record["dependencies"]:
            self.recover(kind=dep["kind"], manifest_id=dep["manifest_id"])
        self._revalidate(kind, body["payload"])
        check()
        return body["payload"]

    def _lineage_verify(self, claim, proof):
        self.lineage_key.verify(proof, encoded(claim))
        if (claim.get("schema") != "flora-cohort-lineage-attestation-v1"
                or claim.get("experiment_id") != self.experiment_id
                or claim.get("enrolled_key_sha256") != self.lineage_key_sha256
                or claim.get("actual_family_ancestry_verified") is not True):
            raise PermissionError("cohort has no independent exact family-lineage qualification")

    def register_cohort(self, *, cohort_id: str, entries: tuple[CohortEntry, ...], rules: tuple[SplitIsolationRule, ...],
                        lineage_claim: dict | None = None, lineage_proof: bytes | None = None):
        bindings, gates = {}, []
        for entry in entries:
            entry.record()
            gate = self._gate(entry.authority_id, entry.event_id, cohort_source_purpose(self.experiment_id, entry.split))
            gates.append(gate)
            bindings[entry.entry_id] = self.authorities[entry.authority_id].binding(entry.event_id)
        validate_cohort(entries, rules, bindings)
        cohort = {"entries": [entry.record() for entry in entries], "rules": [rule.record() for rule in rules], "bindings": bindings}
        qualified = lineage_claim is not None or lineage_proof is not None
        if qualified:
            if lineage_claim is None or not isinstance(lineage_proof, bytes) or not lineage_proof:
                raise ValueError("cohort qualification requires actual claim and signature")
            self._lineage_verify(lineage_claim, lineage_proof)
            if lineage_claim.get("cohort_sha256") != canonical_sha256(cohort):
                raise ValueError("family qualification differs from exact cohort/source/rule binding")
        return self._save("cohort", cohort_id, {"cohort": cohort,
            "status": "lineage_qualified" if qualified else "shape_only",
            "lineage_claim": lineage_claim, "lineage_proof_base64": None if lineage_proof is None else base64.b64encode(lineage_proof).decode()}, gates)

    def register_recipe(self, *, recipe_id, cohort_id, code_files: tuple[tuple[str, bytes], ...], dependency_lock: bytes,
                        role_contracts: tuple[tuple[str, bytes], ...], source_choices: tuple[tuple[str, str], ...],
                        stop_defer_contract: bytes):
        cohort = self.recover(kind="cohort", manifest_id=cohort_id)
        by_id = {entry["entry_id"]: entry for entry in cohort["cohort"]["entries"]}
        entry_ids = set(by_id)
        if (not code_files or not role_contracts or not dependency_lock or not stop_defer_contract
                or len({path for path, _ in code_files}) != len(code_files)
                or len({role for role, _ in role_contracts}) != len(role_contracts)
                or len({entry_id for entry_id, _ in source_choices}) != len(source_choices)
                or not source_choices or any(entry_id not in entry_ids or decision not in {"eligible", "stop", "defer"}
                    for entry_id, decision in source_choices)):
            raise ValueError("recipe needs exact code/dependency/role and source-choice/stop/defer contracts")
        if any(decision == "eligible" and by_id[entry_id]["split"] not in {"training", "pilot"}
                for entry_id, decision in source_choices):
            raise PermissionError("heldout/transfer material cannot become recipe training by a choice label")
        def blob(value):
            if not isinstance(value, bytes) or not value:
                raise ValueError("recipe has no actual contract bytes")
            return {"sha256": sha(value), "base64": base64.b64encode(value).decode()}
        for path, _ in code_files:
            if (not isinstance(path, str) or not path or "\\" in path or any(ord(c) < 32 for c in path)
                    or path.startswith("/") or ".." in path.split("/") or PurePosixPath(path).as_posix() != path):
                raise ValueError("recipe code paths must be repository-relative")
        for role, _ in role_contracts:
            identifier(role, "artifact role")
        dep = self._dependency("cohort", cohort_id)
        payload = {"cohort_id": cohort_id, "cohort_sha256": self.metadata("cohort", cohort_id)["content_sha256"],
            "code_files": [[path, blob(value)] for path, value in code_files], "dependency_lock": blob(dependency_lock),
            "role_contracts": [[role, blob(value)] for role, value in role_contracts],
            "source_choices": [list(choice) for choice in source_choices], "stop_defer_contract": blob(stop_defer_contract),
            "status": "recipe_prepared_not_builder_export_qualified"}
        return self._save("recipe", recipe_id, payload, self.metadata("cohort", cohort_id)["source_gates"], (dep,))

    def register_linked_case(self, *, case_id, recipe_id, split, input_entry_ids: tuple[str, ...], proposal: bytes,
                             resolution: str, target_entry_id: str | None = None, outcome_entry_id: str | None = None,
                             target_authority_entry_id: str | None = None, alternatives: tuple[bytes, ...] = ()):
        recipe = self.recover(kind="recipe", manifest_id=recipe_id)
        cohort = self.recover(kind="cohort", manifest_id=recipe["cohort_id"])
        entries = {entry["entry_id"]: entry for entry in cohort["cohort"]["entries"]}
        if (split not in _SPLITS or not input_entry_ids or tuple(sorted(set(input_entry_ids))) != input_entry_ids
                or not isinstance(proposal, bytes) or not proposal or resolution not in {"unresolved", "accepted", "rejected", "deferred", "abstained"}
                or any(entry_id not in entries or entries[entry_id]["split"] != split for entry_id in input_entry_ids)
                or any(entry_id is not None and (entry_id not in entries or entries[entry_id]["split"] != split)
                    for entry_id in (target_entry_id, outcome_entry_id, target_authority_entry_id))
                or any(not isinstance(value, bytes) or not value for value in alternatives)):
            raise ValueError("linked builder case crosses actual cohort split or lacks proposed operation")
        if resolution in {"accepted", "rejected"} and (target_entry_id is None or outcome_entry_id is None):
            raise ValueError("resolved case needs actual target and outcome source references")
        payload = {"recipe_id": recipe_id, "recipe_sha256": self.metadata("recipe", recipe_id)["content_sha256"],
            "split": split, "input_entry_ids": list(input_entry_ids), "proposal_base64": base64.b64encode(proposal).decode(),
            "target_entry_id": target_entry_id, "outcome_entry_id": outcome_entry_id, "resolution": resolution,
            "target_authority_entry_id": target_authority_entry_id,
            "alternatives_base64": [base64.b64encode(value).decode() for value in alternatives],
            "source_person_roles": {key: entries[key]["person_role"] for key in sorted(set(input_entry_ids) |
                {entry_id for entry_id in (target_entry_id, outcome_entry_id, target_authority_entry_id) if entry_id is not None})},
            "status": "shape_only", "training_eligible": False, "evaluation_eligible": False}
        return self._save("linked_case", case_id, payload, self.metadata("recipe", recipe_id)["source_gates"],
            (self._dependency("recipe", recipe_id),))

    def _verify_part1(self, payload):
        claim, proof = payload["claim"], base64.b64decode(payload["proof_base64"], validate=True)
        self.qualification_key.verify(proof, encoded(claim))
        required = {"schema", "experiment_id", "cohort_sha256", "recipe_sha256", "protocol_sha256", "plan_sha256",
            "enrolled_key_sha256", "validator_artifact_sha256", "material_reader_artifact_sha256", "material_routes_sha256",
            "accepted", "failure_inclusive", "materials"}
        if (set(claim) != required or claim["schema"] != "flora-part1-result-qualification-v1"
                or claim["experiment_id"] != self.experiment_id or claim["enrolled_key_sha256"] != self.qualification_key_sha256
                or claim["accepted"] is not True or claim["failure_inclusive"] is not True
                or self.part1_validator is None or self.part1_validator.artifact_sha256 != self.validator_sha256
                or claim["validator_artifact_sha256"] != self.validator_sha256
                or claim["material_reader_artifact_sha256"] != self.material_reader_sha256
                or claim["material_routes_sha256"] != self.material_routes_sha256):
            raise PermissionError("Part1 has no independent signed qualified actual result")
        for name in ("cohort_sha256", "recipe_sha256", "protocol_sha256", "plan_sha256", "validator_artifact_sha256"):
            require_sha256(claim[name], name)
        if not isinstance(claim["materials"], dict) or not claim["materials"]:
            raise ValueError("Part1 material inventory is absent")
        self._check_gates(tuple(claim["materials"].values()))
        materials, private_names = {}, set()
        for name, gate in claim["materials"].items():
            identifier(name, "Part1 material name")
            if gate["purpose"] != manifest_purpose(self.experiment_id, "qualification"):
                raise PermissionError("Part1 material lacks its independent qualification purpose")
            authority = self.authorities.get(gate["authority_id"])
            if authority is None:
                raise PermissionError("Part1 actual source authority is absent")
            binding = authority.binding(gate["event_id"], original=gate["original"])
            private = any(item["event_type"] in (_INTERNAL_EVENT_TYPES | {_EVENT}) for item in binding["closure"])
            if private:
                private_names.add(name)
                reader = self.part1_material_reader
                if (type(reader) is not RegisteredPart1MaterialReader
                        or reader.artifact_sha256 != self.material_reader_sha256
                        or reader.binding_sha256 != self.material_routes_sha256):
                    raise PermissionError("internal Part1 material needs actual registered typed custody")
                materials[name] = reader.read(name=name, authority=authority, gate=gate)
            else:
                materials[name] = authority.read(gate)
        if (not {"sealed_assessment", "assessment_spec", "result", "rubric", "thresholds", "native_artifacts", "phase_snapshots"}.issubset(materials)
                or self.part1_validator.verify(claim=claim, materials=materials) is not True):
            raise PermissionError("actual sealed assessment/result/artifact lineage does not qualify Part1")
        # Semantic validation can be slow. Its success cannot freeze the
        # independent controller purposes, seals or producer qualifications.
        for name in sorted(private_names):
            gate = claim["materials"][name]
            if self.part1_material_reader.read(name=name, authority=self.authorities[gate["authority_id"]], gate=gate) != materials[name]:
                raise PermissionError("typed result material changed during independent validation")
        self._check_gates(tuple(claim["materials"].values()))
        if self.part1_validator.artifact_sha256 != self.validator_sha256:
            raise PermissionError("result validator changed during qualification")
        if self.part1_material_reader is not None and (self.part1_material_reader.artifact_sha256 != self.material_reader_sha256
                or self.part1_material_reader.binding_sha256 != self.material_routes_sha256):
            raise PermissionError("typed result material routes changed during qualification")

    def register_part1_qualification(self, *, qualification_id, cohort_id, recipe_id, claim: dict, proof: bytes):
        cohort = self.recover(kind="cohort", manifest_id=cohort_id)
        recipe = self.recover(kind="recipe", manifest_id=recipe_id)
        if (cohort["status"] != "lineage_qualified" or recipe["cohort_id"] != cohort_id
                or claim.get("cohort_sha256") != self.metadata("cohort", cohort_id)["content_sha256"]
                or claim.get("recipe_sha256") != self.metadata("recipe", recipe_id)["content_sha256"]):
            raise PermissionError("Part1 qualification differs from exact qualified cohort/recipe")
        payload = {"cohort_id": cohort_id, "recipe_id": recipe_id, "claim": claim,
            "proof_base64": base64.b64encode(proof).decode(), "status": "independently_qualified_part1"}
        self._verify_part1(payload)
        gates = (*self.metadata("cohort", cohort_id)["source_gates"], *claim["materials"].values())
        return self._save("part1", qualification_id, payload, gates,
            (self._dependency("cohort", cohort_id), self._dependency("recipe", recipe_id)))

    def register_transfer_readiness(self, *, readiness_id, qualification_id, transfer_cohort_id,
                                    transfer_rules: tuple[SplitIsolationRule, ...],
                                    transfer_claim: dict | None = None, transfer_proof: bytes | None = None,
                                    builder_export_qualification: dict | None = None):
        part1 = self.recover(kind="part1", manifest_id=qualification_id)
        training = self.recover(kind="cohort", manifest_id=part1["cohort_id"])
        transfer = self.recover(kind="cohort", manifest_id=transfer_cohort_id)
        if transfer["status"] != "lineage_qualified":
            raise PermissionError("transfer cohort has no independently qualified family lineage")
        entries = [CohortEntry(**{**entry, "scenario_parents": tuple(entry["scenario_parents"])}) for entry in transfer["cohort"]["entries"]]
        if any(entry.split != "transfer" for entry in entries):
            raise ValueError("transfer cohort contains nontransfer sources")
        previous_entries = [CohortEntry(**{**entry, "scenario_parents": tuple(entry["scenario_parents"])})
            for entry in training["cohort"]["entries"]]
        previous_rules = [SplitIsolationRule(rule["left"], rule["right"], tuple(rule["disjoint_axes"]), tuple(rule["shared_axes"]))
            for rule in training["cohort"]["rules"]]
        combined_bindings = {**training["cohort"]["bindings"], **transfer["cohort"]["bindings"]}
        if len(combined_bindings) != len(previous_entries) + len(entries):
            raise ValueError("transfer reused a cohort entry identity")
        validate_cohort(tuple(previous_entries + entries), tuple(previous_rules) + transfer_rules, combined_bindings)
        # Every cross-cohort sharing rule is explicit. A shared identity-neutral
        # source pack need not be falsely labelled a private cross-host leak.
        # Whether those rules suffice for the actual transfer claim remains an
        # independently signed qualification, not a shape-validation conclusion.
        for left in training["cohort"]["entries"]:
            for right in transfer["cohort"]["entries"]:
                lb, rb = training["cohort"]["bindings"][left["entry_id"]], transfer["cohort"]["bindings"][right["entry_id"]]
                if lb["scope"]["host_instance_id"] == rb["scope"]["host_instance_id"]:
                    raise PermissionError("builder transfer must use a distinct host")
        if builder_export_qualification is not None:
            raise ValueError("actual FBM export qualifier is a separate producer dependency; no bare readiness claim")
        qualified = transfer_claim is not None or transfer_proof is not None
        if qualified:
            if transfer_claim is None or not isinstance(transfer_proof, bytes) or not transfer_proof:
                raise ValueError("transfer eligibility needs an actual independent claim and signature")
            self.lineage_key.verify(transfer_proof, encoded(transfer_claim))
            expected = {"schema": "flora-transfer-lineage-attestation-v1", "experiment_id": self.experiment_id,
                "part1_sha256": self.metadata("part1", qualification_id)["content_sha256"],
                "transfer_cohort_sha256": self.metadata("cohort", transfer_cohort_id)["content_sha256"],
                "transfer_rules_sha256": canonical_sha256([rule.record() for rule in transfer_rules]),
                "enrolled_key_sha256": self.lineage_key_sha256,
                "family_isolation_qualified": True, "first_host_private_derivatives_excluded": True}
            if transfer_claim != expected:
                raise PermissionError("transfer qualification differs from actual families/policy/Part1 bindings")
        payload = {"qualification_id": qualification_id, "transfer_cohort_id": transfer_cohort_id,
            "recipe_id": part1["recipe_id"], "status": "inputs_prepared_builder_export_qualification_missing" if qualified else "transfer_policy_prepared_unqualified",
            "transfer_rules": [rule.record() for rule in transfer_rules],
            "transfer_claim": transfer_claim, "transfer_proof_base64": None if transfer_proof is None else base64.b64encode(transfer_proof).decode(),
            "execution_ready": False, "training_eligible": False}
        gates = (*self.metadata("part1", qualification_id)["source_gates"], *self.metadata("cohort", transfer_cohort_id)["source_gates"])
        return self._save("transfer", readiness_id, payload, gates,
            (self._dependency("part1", qualification_id), self._dependency("cohort", transfer_cohort_id)))

    def _revalidate(self, kind, payload):
        if kind == "cohort":
            cohort = payload["cohort"]
            entries = tuple(CohortEntry(**{**entry, "scenario_parents": tuple(entry["scenario_parents"])}) for entry in cohort["entries"])
            rules = tuple(SplitIsolationRule(rule["left"], rule["right"], tuple(rule["disjoint_axes"]), tuple(rule["shared_axes"])) for rule in cohort["rules"])
            validate_cohort(entries, rules, cohort["bindings"])
            if payload["status"] == "lineage_qualified":
                self._lineage_verify(payload["lineage_claim"], base64.b64decode(payload["lineage_proof_base64"], validate=True))
                if payload["lineage_claim"]["cohort_sha256"] != canonical_sha256(cohort):
                    raise ValueError("cohort qualification changed frozen exact material")
            elif payload["status"] != "shape_only":
                raise ValueError("unknown cohort qualification status")
        elif kind == "part1":
            self._verify_part1(payload)
        elif kind == "linked_case":
            if payload["training_eligible"] is not False or payload["evaluation_eligible"] is not False:
                raise ValueError("shape-only case cannot grant builder training eligibility")
        elif kind == "transfer":
            if payload["execution_ready"] is not False:
                raise ValueError("transfer metadata is not an actual qualified FBM export")
            if payload["transfer_claim"] is not None:
                self.lineage_key.verify(base64.b64decode(payload["transfer_proof_base64"], validate=True), encoded(payload["transfer_claim"]))
