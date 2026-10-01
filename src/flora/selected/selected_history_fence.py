"""Explicit selected history metadata, with actual manifest and live rights.

The proof covers the held original history and nominated external closure. It
does not audit unrelated Kurrent entries. Full initial AEAD authentication and
the default whole-stream readers remain separate. No positive allow is reused.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from types import FunctionType

from cognitive_kernel.canonical import canonical_json_bytes, require_identifier
from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent

from ..comparison_run import HistorySnapshot, SourceMaterial
from .comparison_custody import (
    SelectedRunEvidencePolicy, XTDBComparisonCustody,
    SelectedComparisonArtifactMetadata, evaluation_purpose, _ARTIFACTS, _json,
)
from .experience import KurrentExperienceLog
from .formation_registry import CanonicalSourceCommitment
from .history_fence import CurrentHistorySource, _committed_record, _source_record, _reference_record
from .judgment_lineage import _INTERNAL_EVENT_TYPES
from .source_closure import (
    _ClosureMetadataSample, _ReaderBinding, _native_snapshot,
    _require_native_contracts, _commitment_bytes, _LOOKUP, _LOOKUP_CODE,
)


DOMAIN = "selected-history-metadata-v1"
_TARGETED_METADATA = XTDBComparisonCustody.metadata_selected
_TARGETED_METADATA_CODE = _TARGETED_METADATA.__code__
_HELD_LAYOUTS = tuple((cls, tuple(cls.__dataclass_fields__)) for cls in (
    ProductHostScope, ProvenanceReference, ExperienceEvent, SourceMaterial, HistorySnapshot))
_HELD_SHAPES = tuple((cls, tuple(vars(cls).items())) for cls, _ in _HELD_LAYOUTS)
_HELD_CODES = tuple((function, function.__code__) for cls, shape in _HELD_SHAPES
    for _, value in shape for function in (value.__func__ if isinstance(value, (classmethod, staticmethod)) else value,)
    if isinstance(function, FunctionType))


def _held_snapshot(value):
    """Read native held bytes/fields without invoking metadata callbacks."""
    cls = type(value)
    if value is None or cls is str or cls is int or cls is bool or cls is bytes:
        return value
    if cls is tuple:
        return tuple(_held_snapshot(item) for item in value)
    if type(cls) is not type:
        raise PermissionError("selected history held metadata has a nonnative class")
    fields = next((fields for owner, fields in _HELD_LAYOUTS if cls is owner), None)
    if fields is None:
        raise PermissionError("selected history needs native immutable held metadata")
    values = object.__getattribute__(value, "__dict__")
    if (type(values) is not dict or any(type(name) is not str for name in values)
            or set(values) != set(fields)):
        raise PermissionError("selected held history field layout changed")
    return cls, tuple((name, _held_snapshot(values[name])) for name in fields)


def _require_held_contracts():
    """Pure native shape checks before any postterminal held-field access."""
    if _HELD_LAYOUTS is not _NATIVE_HELD_LAYOUTS or _HELD_SHAPES is not _NATIVE_HELD_SHAPES:
        raise PermissionError("selected history held layout binding changed")
    for name, function, code in _HELD_HELPERS:
        if globals().get(name) is not function or function.__code__ is not code:
            raise PermissionError("selected history held helper binding changed")
    for cls, shape in _HELD_SHAPES:
        current = vars(cls)
        extra = "__slotnames__" not in dict(shape) and "__slotnames__" in current
        if (len(current) != len(shape) + int(extra)
                or any(current.get(name) is not value for name, value in shape)
                or extra and (type(current["__slotnames__"]) is not list or current["__slotnames__"])):
            raise PermissionError("selected history held native contract shape changed")
    if any(function.__code__ is not code for function, code in _HELD_CODES):
        raise PermissionError("selected history held native contract code changed")


@dataclass(frozen=True)
class SelectedCurrentHistoryAuthority:
    """Same-call observation in the named domain, never a later read grant."""
    domain: str
    run_id: str
    case_id: str
    phase: str
    history_sha256: str
    manifest_sha256: str
    artifact_event_sha256: str
    sources: tuple[CurrentHistorySource, ...] = field(repr=False)


def verify_selected_history_metadata(*, policy, case_id, phase, history,
        source_purposes=(), final_current=None) -> SelectedCurrentHistoryAuthority:
    """Fresh exact physical reads and one terminal compound XTDB observation.

    Every held original keeps its evaluation-purpose check. Additional source
    purposes share this call's final fence; a callback cannot revoke an earlier
    original after a separate source proof has already returned.
    """
    if (not isinstance(policy, SelectedRunEvidencePolicy) or type(history) is not HistorySnapshot
            or type(policy.history_metadata_domain) is not str or policy.history_metadata_domain != DOMAIN):
        raise TypeError("selected history requires its explicitly selected policy/domain")
    cap = policy.maximum_history_sources
    if type(cap) is not int or cap < 2:
        raise ValueError("selected history source cap must include its manifest")
    if (type(history.sources) is not tuple or not history.sources
            or len(history.sources) + 1 > cap):
        raise PermissionError("selected held history exceeds its explicit source cap")
    custody, permissions = policy.custody, policy.permissions
    if type(custody) is not XTDBComparisonCustody or type(custody.log) is not KurrentExperienceLog:
        raise TypeError("selected history requires actual selected physical owners")
    registry, log, objects = custody.registry, custody.log, custody.objects
    if (getattr(log.lookup_committed, "__func__", None) is not _LOOKUP
            or getattr(log.lookup_committed, "__self__", None) is not log
            or _LOOKUP.__code__ is not _LOOKUP_CODE):
        raise TypeError("selected history requires its native exact physical lookup")
    connection = custody.connection
    scope, namespace, run_id = custody.scope, custody.authority_namespace_id, policy.run_id
    custody_digest, registry_digest, permission_digest = (custody.scope_digest,
        registry.scope_digest, permissions.scope_digest)
    object_namespace, raw_custody = objects.namespace, custody.raw_custody
    _require_native_contracts()
    _require_held_contracts()
    scope_signature, held_signature = _native_snapshot(scope), _held_snapshot(history)
    history_digest = history.digest()
    purpose = evaluation_purpose(run_id, case_id, phase)
    artifact_id = f"history:{case_id}:{phase}"
    if type(source_purposes) is not tuple or len(source_purposes) > cap:
        raise ValueError("selected additional purposes must be a bounded tuple")
    distinct_purposes = {purpose}
    for identifiers, additional_purpose in source_purposes:
        if (type(identifiers) is not tuple or not identifiers or len(identifiers) > cap
                or any(type(event_id) is not str for event_id in identifiers)
                or len(set(identifiers)) != len(identifiers) or type(additional_purpose) is not str
                or require_identifier(additional_purpose, "purpose") != additional_purpose):
            raise ValueError("selected additional source purpose is malformed")
        for event_id in identifiers:
            if require_identifier(event_id, "source_event_id") != event_id:
                raise ValueError("selected additional source ID is noncanonical")
        distinct_purposes.add(additional_purpose)
    native = custody.metadata_selected
    if (getattr(native, "__func__", None) is not _TARGETED_METADATA
            or getattr(native, "__self__", None) is not custody
            or _TARGETED_METADATA.__code__ is not _TARGETED_METADATA_CODE):
        raise TypeError("selected history requires its actual targeted artifact reader")
    client, stream = log.client, log.stream
    readers = tuple(_ReaderBinding.capture(owner, name) for owner, names in (
        (policy, ("authorize_history_metadata",)),
        (custody, ("_key", "metadata", "metadata_selected")),
        (registry, ("_key", "_fetch", "_decode", "lookup", "lookup_commitment", "raw_metadata", "raw_reference")),
        (permissions, ("_key", "_fetch", "_decode", "_head", "_stored_action", "current_action", "permits")),
        (log, ("lookup_committed", "replay", "replay_committed")),
        (client, ("get_stream",)), (connection, ("execute",))) for name in names)
    snapshot_function, snapshot_code = _held_snapshot, _held_snapshot.__code__
    def binding():
        if _held_snapshot is not snapshot_function or snapshot_function.__code__ is not snapshot_code:
            raise PermissionError("selected history pure held binding changed")
        _require_native_contracts()
        _require_held_contracts()
        for reader in readers:
            reader.verify()
        if (policy.custody is not custody or policy.permissions is not permissions
                or type(policy.run_id) is not str or policy.run_id != run_id
                or type(policy.history_metadata_domain) is not str or policy.history_metadata_domain != DOMAIN
                or type(policy.maximum_history_sources) is not int or policy.maximum_history_sources != cap
                or custody.registry is not registry or custody.log is not log or custody.objects is not objects
                or custody.raw_custody is not raw_custody
                or custody.connection is not connection or registry.connection is not connection
                or permissions.connection is not connection or permissions.registry is not registry
                or type(custody.scope_digest) is not str or custody.scope_digest != custody_digest
                or type(registry.scope_digest) is not str or registry.scope_digest != registry_digest
                or type(permissions.scope_digest) is not str or permissions.scope_digest != permission_digest
                or type(objects.namespace) is not str or objects.namespace != object_namespace
                or log.client is not client or type(log.stream) is not str or log.stream != stream
                or type(custody.authority_namespace_id) is not str or custody.authority_namespace_id != namespace
                or type(registry.authority_namespace_id) is not str or registry.authority_namespace_id != namespace
                or type(permissions.authority_namespace_id) is not str or permissions.authority_namespace_id != namespace
                or any(_native_snapshot(value) != scope_signature for value in (
                    custody.scope, registry.scope, permissions.scope, log.scope, objects.scope, history.scope))
                or snapshot_function(history) != held_signature):
            raise PermissionError("selected history actual owner, configuration or held inputs changed")
    binding()
    sampled = _ClosureMetadataSample(binding_guard=binding, registry=registry,
        permissions=permissions, comparison=custody,
        maximum_rows=2 * cap * (1 + len(distinct_purposes)) + 1)
    binding()
    manifest = custody.metadata_selected(run_id, artifact_id)
    binding()
    if type(manifest) is not SelectedComparisonArtifactMetadata:
        raise PermissionError("selected history lacks its actual registered manifest")
    artifact, record = manifest.artifact, manifest.artifact.record
    outer = record["metadata"]
    if (record["kind"] != "history" or outer["case_id"] != case_id or outer["phase"] != phase
            or outer["evaluation_purpose"] != purpose or outer["history_sha256"] != history_digest
            or tuple(outer["source_event_ids"]) != history.event_ids
            or tuple(record["parent_event_ids"]) != history.event_ids
            or artifact.event_id in history.event_ids):
        raise PermissionError("selected history differs from registered phase manifest")
    record_bytes = canonical_json_bytes(record)
    sampled._remember("comparison", _ARTIFACTS, manifest.row_key, True, custody, "record_sha256", {
        "_id": manifest.row_key, "scope_digest": manifest.row_scope_digest,
        "record_sha256": manifest.row_record_sha256, "record_json": manifest.row_record_json})
    # Manifest source/raw metadata is sampled, without inventing a use grant.
    manifest_commitment = sampled.local_registry.lookup_commitment(artifact.event_id)
    binding()
    if manifest_commitment != manifest.commitment:
        raise PermissionError("selected manifest registered physical locator changed")
    all_commitments = {artifact.event_id: manifest_commitment}
    material = {artifact.event_id: _commitment_bytes(manifest_commitment)}
    physical_entries = {artifact.event_id: manifest.committed}
    purpose_ids = {purpose: set(history.event_ids)}
    for identifiers, additional_purpose in source_purposes:
        purpose_ids.setdefault(additional_purpose, set()).update(identifiers)
    scheduled = set(history.event_ids) | {artifact.event_id}
    scheduled.update(event_id for ids in purpose_ids.values() for event_id in ids)
    if len(scheduled) > cap:
        raise PermissionError("selected history closure exceeds its source cap")

    def physical(commitment):
        entry = log.lookup_committed(event_id=commitment.source.evidence.ref_id,
            event_sha256=commitment.event_sha256, stream_position=commitment.stream_position,
            expected_recorded_at=commitment.recorded_at)
        binding()
        source, event = commitment.source, entry.event
        evidence = source.evidence
        if (event.scope != scope or evidence.scope != scope
                or evidence.authority_namespace_id != namespace or event.event_id != evidence.ref_id
                or event.payload_reference != source.object_ref or event.content_digest != evidence.content_digest
                or event.parent_event_ids != evidence.parent_refs or event.occurred_at != evidence.observed_at):
            raise PermissionError("selected history physical source differs from its registration")
        return entry

    # Discover only nominated parents. The manifest's parents are the held
    # originals; its own evaluation grant is deliberately not required.
    pending = list(sorted(scheduled - {artifact.event_id}))
    while pending:
        event_id = pending.pop()
        if event_id in all_commitments:
            continue
        commitment = sampled.local_registry.lookup_commitment(event_id)
        binding()
        if type(commitment) is not CanonicalSourceCommitment:
            raise PermissionError("selected history source has no registered physical locator")
        commitment.validate()
        if commitment.source.evidence.ref_id != event_id:
            raise PermissionError("selected history registered source differs from nomination")
        parents = set(commitment.source.evidence.parent_refs)
        if event_id in parents:
            raise PermissionError("selected history source contains a parent cycle")
        if event_id in history.event_ids and not parents.issubset(history.event_ids):
            raise PermissionError("selected history original parent is outside its phase")
        new_ids = parents - scheduled
        if len(scheduled) + len(new_ids) > cap:
            raise PermissionError("selected history closure exceeds its source cap")
        scheduled.update(new_ids)
        pending.extend(sorted(parents - set(all_commitments)))
        all_commitments[event_id], material[event_id] = commitment, _commitment_bytes(commitment)
        physical_entries[event_id] = physical(commitment)
    positions = {}
    for event_id, commitment in all_commitments.items():
        position = commitment.stream_position
        if position in positions:
            raise PermissionError("selected history has ambiguous physical positions")
        positions[position] = event_id
        for parent in commitment.source.evidence.parent_refs:
            if parent not in all_commitments or all_commitments[parent].stream_position >= position:
                raise PermissionError("selected history parent is not earlier than its child")
    # Expand each current purpose to its registered parents within the same cap.
    for ids in purpose_ids.values():
        pending = list(ids)
        while pending:
            parents = set(all_commitments[pending.pop()].source.evidence.parent_refs) - ids
            ids.update(parents)
            pending.extend(parents)
    references, captured, action_signatures = [], [], {}
    for original in history.sources:
        event_id = original.event.event_id
        commitment, entry = all_commitments[event_id], physical_entries[event_id]
        source = commitment.source
        if (entry.event != original.event or entry.event.event_type in _INTERNAL_EVENT_TYPES
                or entry.stream_position >= manifest.committed.stream_position):
            raise PermissionError("selected original lacks exact original-before-manifest custody")
        raw = sampled.local_registry.raw_metadata(source.object_ref)
        reference = sampled.local_registry.raw_reference(source.object_ref)
        binding()
        if (raw is None or reference is None or reference.scope != scope
                or reference.object_id != source.object_ref
                or reference.plaintext_sha256 != original.event.content_digest
                or reference.size != len(original.plaintext) or raw["object_namespace"] != objects.namespace
                or raw["plaintext_sha256"] != original.event.content_digest
                or raw["size"] != len(original.plaintext)):
            raise PermissionError("selected original lacks exact durable raw metadata")
        registered, action = sampled.observe_source(event_id, purpose)
        binding()
        if registered != source:
            raise PermissionError("selected original registration changed")
        references.append({"event_id": event_id, "registration_sha256": source.registration_sha256,
                           "event_sha256": original.event.event_sha256})
        captured.append(CurrentHistorySource(event_id, source.registration_sha256,
            original.event.event_sha256, action.action_sha256, canonical_json_bytes(_source_record(source)),
            canonical_json_bytes(raw), canonical_json_bytes(_reference_record(reference)),
            canonical_json_bytes(action.metadata_record()), canonical_json_bytes(_committed_record(entry))))
    body = _json({"schema": "flora-comparison-history-manifest-v1", "case_id": case_id,
        "phase": phase, "history_sha256": history_digest, "sources": references})
    body_digest = hashlib.sha256(body).hexdigest()
    manifest_reference = sampled.local_registry.raw_reference(record["object_id"])
    binding()
    if (body_digest != record["content_sha256"] or body_digest != manifest.committed.event.content_digest
            or manifest_reference is None or manifest_reference.scope != scope
            or manifest_reference.object_id != record["object_id"]
            or manifest_reference.plaintext_sha256 != body_digest or manifest_reference.size != len(body)):
        raise PermissionError("selected history reconstruction differs from exact manifest custody")
    for selected_purpose, ids in sorted(purpose_ids.items()):
        for event_id in sorted(ids):
            source, action = sampled.observe_source(event_id, selected_purpose)
            binding()
            if source != all_commitments[event_id].source:
                raise PermissionError("selected source registration changed during purpose observation")
            action_signatures[event_id, selected_purpose] = _native_snapshot(action)
            if permissions.permits(source, selected_purpose) is not True:
                raise PermissionError("selected history current source purpose was withdrawn")
            binding()
    # Re-read locators/physical records after actual permission callbacks.
    current_manifest = custody.metadata_selected(run_id, artifact_id)
    binding()
    if (current_manifest is None or canonical_json_bytes(current_manifest.artifact.record) != record_bytes
            or current_manifest.row_record_json != manifest.row_record_json
            or _commitment_bytes(current_manifest.commitment) != material[artifact.event_id]):
        raise PermissionError("selected history manifest changed during current verification")
    for event_id in sorted(all_commitments):
        if event_id == artifact.event_id:
            continue
        current = registry.lookup_commitment(event_id)
        binding()
        if current is None or _commitment_bytes(current) != material[event_id]:
            raise PermissionError("selected history registered physical locator changed")
        physical(current)
    for selected_purpose, ids in sorted(purpose_ids.items()):
        for event_id in sorted(ids):
            if permissions.permits(all_commitments[event_id].source, selected_purpose) is not True:
                raise PermissionError("selected history final source purpose was withdrawn")
            binding()
            current_action = permissions.current_action(event_id, selected_purpose)
            binding()
            if _native_snapshot(current_action) != action_signatures[event_id, selected_purpose]:
                raise PermissionError("selected history source grant changed during current verification")
    if final_current is not None:
        if not callable(final_current):
            raise TypeError("selected compound history needs an actual final callback")
        final_current()
        binding()
    proof = SelectedCurrentHistoryAuthority(DOMAIN, run_id, case_id, phase,
        history_digest, body_digest, record["event_sha256"], tuple(captured))
    binding()
    sampled.verify_final_current_rows()
    binding()
    return proof


def authorize_selected_history_metadata(**inputs) -> bool:
    """Policy dispatch; operational backend failures still propagate."""
    try:
        verify_selected_history_metadata(**inputs)
        return True
    except (ValueError, PermissionError, KeyError, TypeError, AttributeError):
        return False


def selected_phase_member(*, registry, log, permissions, originals,
                          maximum_sources, event_id) -> bool:
    """Fresh bounded ancestry classification; never a source-purpose grant.

    Nominated controls may only lead to this held phase's real original IDs.
    Signed approval semantics remain the separate state controller's job.
    The finite metadata view is discarded after this one predicate call.
    """
    if (type(log) is not KurrentExperienceLog or type(originals) is not dict
            or type(maximum_sources) is not int or maximum_sources < 1):
        raise TypeError("selected phase membership requires its actual bounded owners")
    if (getattr(log.lookup_committed, "__func__", None) is not _LOOKUP
            or getattr(log.lookup_committed, "__self__", None) is not log
            or _LOOKUP.__code__ is not _LOOKUP_CODE):
        raise TypeError("selected phase membership requires its native exact physical lookup")
    if type(event_id) is not str or require_identifier(event_id, "event_id") != event_id:
        return False
    if any(type(key) is not str for key in originals):
        raise TypeError("selected phase originals require exact primitive identifier keys")
    scope, namespace, connection = registry.scope, registry.authority_namespace_id, registry.connection
    client, stream = log.client, log.stream
    _require_native_contracts()
    _require_held_contracts()
    scope_signature = _native_snapshot(scope)
    original_signature = tuple(sorted((key, _held_snapshot(event)) for key, event in originals.items()))
    readers = tuple(_ReaderBinding.capture(owner, name) for owner, names in (
        (registry, ("lookup_commitment", "_fetch", "_decode", "lookup", "raw_metadata", "raw_reference")),
        (log, ("lookup_committed", "replay", "replay_committed")),
        (connection, ("execute",)), (client, ("get_stream",))) for name in names)
    def binding():
        _require_native_contracts()
        _require_held_contracts()
        for reader in readers:
            reader.verify()
        if any(type(key) is not str for key in originals):
            raise PermissionError("selected phase original identifier key changed")
        if (registry.connection is not connection or permissions.connection is not connection
                or permissions.registry is not registry or log.client is not client
                or type(log.stream) is not str or log.stream != stream
                or type(registry.authority_namespace_id) is not str or registry.authority_namespace_id != namespace
                or type(permissions.authority_namespace_id) is not str or permissions.authority_namespace_id != namespace
                or any(_native_snapshot(value) != scope_signature for value in (
                    registry.scope, log.scope, permissions.scope))
                or tuple(sorted((key, _held_snapshot(event)) for key, event in originals.items())) != original_signature):
            raise PermissionError("selected phase membership actual owner or originals changed")
    binding()
    sampled = _ClosureMetadataSample(binding_guard=binding, registry=registry,
        permissions=permissions, maximum_rows=2 * maximum_sources)
    scheduled, pending, commitments, entries = {event_id}, [event_id], {}, {}
    try:
        while pending:
            current_id = pending.pop()
            if current_id in commitments:
                continue
            commitment = sampled.local_registry.lookup_commitment(current_id)
            binding()
            if type(commitment) is not CanonicalSourceCommitment:
                return False
            commitment.validate()
            source, evidence = commitment.source, commitment.source.evidence
            entry = log.lookup_committed(event_id=current_id, event_sha256=commitment.event_sha256,
                stream_position=commitment.stream_position, expected_recorded_at=commitment.recorded_at)
            binding()
            event = entry.event
            if (evidence.ref_id != current_id or event.scope != scope
                    or event.payload_reference != source.object_ref or event.content_digest != evidence.content_digest
                    or event.parent_event_ids != evidence.parent_refs or event.occurred_at != evidence.observed_at):
                return False
            commitments[current_id], entries[current_id] = commitment, entry
            if event.event_type not in _INTERNAL_EVENT_TYPES:
                if originals.get(current_id) != event:
                    return False
                continue
            if event.event_type in {"comparison_artifact", "provider_attempt_artifact",
                    "phase_snapshot_artifact", "experiment_manifest_artifact"}:
                return False
            if not event.parent_event_ids:
                if event.event_type != "state_activation_approval":
                    return False
                continue
            if current_id in event.parent_event_ids:
                return False
            new_ids = set(event.parent_event_ids) - scheduled
            if len(scheduled) + len(new_ids) > maximum_sources:
                return False
            scheduled.update(new_ids)
            pending.extend(sorted(set(event.parent_event_ids) - set(commitments)))
        if len({entry.stream_position for entry in entries.values()}) != len(entries):
            return False
        for current_id, entry in entries.items():
            if entry.event.event_type not in _INTERNAL_EVENT_TYPES:
                continue
            if any(parent not in entries or entries[parent].stream_position >= entry.stream_position
                    for parent in entry.event.parent_event_ids):
                return False
        for current_id, commitment in commitments.items():
            current = registry.lookup_commitment(current_id)
            binding()
            if current is None or _commitment_bytes(current) != _commitment_bytes(commitment):
                return False
            log.lookup_committed(event_id=current_id, event_sha256=current.event_sha256,
                stream_position=current.stream_position, expected_recorded_at=current.recorded_at)
            binding()
        sampled.verify_final_current_rows()
        binding()
        return True
    except (ValueError, PermissionError, KeyError, TypeError, AttributeError):
        return False


_NATIVE_HELD_LAYOUTS, _NATIVE_HELD_SHAPES = _HELD_LAYOUTS, _HELD_SHAPES
_HELD_HELPERS = tuple((function.__name__, function, function.__code__)
    for function in (_held_snapshot, _require_held_contracts))
