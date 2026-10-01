"""Current selected history metadata after actual initial custody authentication.

This helper opens no ciphertext or plaintext. It binds held original bytes to
the actual immutable registered manifest, then resolves current scoped source
and purpose authority. It never treats outer history metadata as proof of the
manifest's encrypted content, and never retains a positive allow decision.
"""
from __future__ import annotations

from copy import copy, deepcopy
from dataclasses import dataclass, field
import hashlib
from types import MethodType
from typing import Any

from cognitive_kernel.canonical import canonical_json_bytes, normalize_timestamp
from ..comparison_run import HistorySnapshot
from . import formation_policy as permission_readers
from . import formation_registry as source_readers
from .formation_policy import XTDBFormationPermissionPolicy
from .formation_registry import XTDBFormationSourceRegistry
from .phase_source_fence import OneGuardSelectedMetadata


# Capture genuine functions once. A later class patch is a callback, not a new
# definition of the native reader eligible for the terminal-row optimization.
_NATIVE_SOURCE_READERS = tuple((name, getattr(XTDBFormationSourceRegistry, name))
    for name in ("_key", "_fetch", "_decode", "lookup", "raw_metadata", "raw_reference"))
_NATIVE_PERMISSION_READERS = tuple((name, getattr(XTDBFormationPermissionPolicy, name))
    for name in ("_key", "_fetch", "_decode", "_head", "_stored_action", "current_action"))
_NATIVE_DECODERS = ((source_readers, "_evidence_from_record", source_readers._evidence_from_record),
    (permission_readers, "_action_from_record", permission_readers._action_from_record))


def _second_pass_readers(registry, permissions):
    """Capture actual delegates; only unmodified native readers can sample."""
    delegates = tuple((service, name, getattr(service, name))
        for service, readers in ((registry, _NATIVE_SOURCE_READERS),
                                 (permissions, _NATIVE_PERMISSION_READERS))
        for name, _ in readers)
    decoders = tuple((module, name, getattr(module, name)) for module, name, _ in _NATIVE_DECODERS)
    native = (type(registry) is XTDBFormationSourceRegistry
        and type(permissions) is XTDBFormationPermissionPolicy
        and all(name not in vars(service) and isinstance(getattr(service, name), MethodType)
            and getattr(service, name).__self__ is service
            and getattr(service, name).__func__ is function
            for service, readers in ((registry, _NATIVE_SOURCE_READERS),
                                     (permissions, _NATIVE_PERMISSION_READERS))
            for name, function in readers)
        and all(getattr(module, name) is function for module, name, function in _NATIVE_DECODERS))
    return native, delegates, decoders


@dataclass(frozen=True)
class CurrentHistorySource:
    event_id: str
    registration_sha256: str
    event_sha256: str
    grant_sha256: str
    source_metadata: bytes = field(repr=False)
    raw_metadata: bytes = field(repr=False)
    raw_reference: bytes = field(repr=False)
    grant_metadata: bytes = field(repr=False)
    committed_metadata: bytes = field(repr=False)


@dataclass(frozen=True)
class CurrentHistoryAuthority:
    """An observation of this fenced call, not permission for a later call."""
    run_id: str
    case_id: str
    phase: str
    history_sha256: str
    manifest_sha256: str
    artifact_event_sha256: str
    sources: tuple[CurrentHistorySource, ...] = field(repr=False)


def _source_record(source):
    return {"evidence": source.evidence.metadata_record(), "object_ref": source.object_ref,
            "registration_sha256": source.registration_sha256}


def _reference_record(reference):
    return None if reference is None else {"scope": reference.scope.metadata_record(),
        "object_id": reference.object_id, "plaintext_sha256": reference.plaintext_sha256,
        "size": reference.size}


def _committed_record(entry):
    if entry.recorded_at is None or entry.recorded_at.tzinfo is None or entry.recorded_at.utcoffset() is None:
        raise ValueError("history source has no actual aware canonical commit time")
    return {"event": entry.event.metadata_record(), "stream_position": entry.stream_position,
            "recorded_at": normalize_timestamp(entry.recorded_at.isoformat(), "recorded_at")}


def _committed(log):
    entries = log.replay_committed()
    result = {}
    positions = set()
    for entry in entries:
        entry.event.validate()
        if (entry.event.event_id in result or entry.stream_position in positions
                or isinstance(entry.stream_position, bool) or not isinstance(entry.stream_position, int)
                or entry.stream_position < 0):
            raise ValueError("history canonical commits are duplicate or malformed")
        _committed_record(entry)
        result[entry.event.event_id] = entry
        positions.add(entry.stream_position)
    return result


def _sampled(service):
    """Only one pass's actual metadata rows; no allow or plaintext cache."""
    result = copy(service)
    actual_fetch = result._fetch
    rows = {}
    def fetch(*args, **kwargs):
        key = (args, tuple(sorted(kwargs.items())))
        if key not in rows:
            rows[key] = deepcopy(actual_fetch(*args, **kwargs))
        return deepcopy(rows[key])
    result._fetch = fetch
    return result


def verify_current_history_metadata(*, policy: Any, case_id: str, phase: str,
                                    history: HistorySnapshot) -> CurrentHistoryAuthority:
    """Check one history with its own fresh sample and mandatory terminal fence."""
    return _verify_current_history_metadata(policy=policy, case_id=case_id,
        phase=phase, history=history)


def _verify_current_history_metadata(*, policy, case_id, phase, history,
                                     source_purposes=(), after_sources=None):
    """Bind held history to real manifest content and fresh selected authority.

    Full register/recover/authorize_history performs initial private custody
    authentication. This current fence is for already held immutable history;
    it grants no new read and never accepts a caller's standalone digest.
    """
    # Local imports let the selected policy delegate without an import cycle.
    from .comparison_custody import SelectedRunEvidencePolicy, XTDBComparisonCustody, evaluation_purpose, _json
    if not isinstance(policy, SelectedRunEvidencePolicy) or not isinstance(history, HistorySnapshot):
        raise TypeError("history fence requires actual selected policy and typed history")
    custody, permissions = policy.custody, policy.permissions
    if (not isinstance(custody, XTDBComparisonCustody)
            or not isinstance(custody.registry, XTDBFormationSourceRegistry)
            or not isinstance(permissions, XTDBFormationPermissionPolicy)):
        raise TypeError("history fence requires actual registered selected metadata services")
    registry, log, objects = custody.registry, custody.log, custody.objects
    native_second_pass, reader_delegates, decoder_delegates = _second_pass_readers(registry, permissions)
    canonical_readers = (log.replay, log.replay_committed, custody.metadata)
    run_id, scope, namespace = policy.run_id, custody.scope, custody.authority_namespace_id
    scope_record = canonical_json_bytes(scope.metadata_record())
    purpose = evaluation_purpose(run_id, case_id, phase)
    history_digest = history.digest()  # Checks every held plaintext digest and scope.
    artifact_id = f"history:{case_id}:{phase}"

    def bindings():
        if (policy.custody is not custody or policy.permissions is not permissions or policy.run_id != run_id
                or custody.registry is not registry or custody.log is not log or custody.objects is not objects
                or (log.replay, log.replay_committed, custody.metadata) != canonical_readers
                or permissions.registry is not registry
                or canonical_json_bytes(scope.metadata_record()) != scope_record
                or not scope == custody.scope == history.scope == registry.scope == log.scope
                    == objects.scope == permissions.scope
                or not namespace == custody.authority_namespace_id == registry.authority_namespace_id
                    == permissions.authority_namespace_id
                or any(getattr(service, name) != method for service, name, method in reader_delegates)
                or any(getattr(module, name) is not decoder for module, name, decoder in decoder_delegates)):
            raise PermissionError("history current selected authority crosses scope or changed")
    bindings()
    artifact = custody.metadata(run_id, artifact_id)
    if artifact is None:
        raise PermissionError("history has no registered current manifest")
    artifact_record = canonical_json_bytes(artifact.record)
    record, outer = artifact.record, artifact.record["metadata"]
    if (record["kind"] != "history" or outer["case_id"] != case_id or outer["phase"] != phase
            or outer["evaluation_purpose"] != purpose or outer["history_sha256"] != history_digest
            or tuple(outer["source_event_ids"]) != history.event_ids
            or tuple(record["parent_event_ids"]) != history.event_ids):
        raise PermissionError("history differs from registered phase manifest metadata")
    entries = _committed(log)
    manifest_entry = entries.get(artifact.event_id)
    if manifest_entry is None or manifest_entry.event.event_sha256 != record["event_sha256"]:
        raise PermissionError("history manifest has no exact canonical commit")
    sampled = OneGuardSelectedMetadata(registry=registry, permissions=permissions,
        comparison=custody if source_purposes else None)
    # One finite call-local selected sample for the exact held source DAG.
    # The manifest reference is metadata only; this does not invent a grant
    # for its private contents or retain an allow across a later boundary.
    if source_purposes:
        sampled.observe_comparison_artifact(run_id=run_id, artifact_id=artifact_id, artifact=artifact)
        sampled.prime_source_purposes(((history.event_ids, purpose), *source_purposes),
            raw_object_ids=(record["object_id"],))
    else:
        sampled.prime_sources(history.event_ids, purpose)
        sampled.prime_raw_references((record["object_id"],))
    local_registry, local_permissions = sampled.local_registry, sampled.local_permissions
    references, captured = [], []
    event_ids = set(history.event_ids)
    for material in history.sources:
        event_id = material.event.event_id
        entry, source = entries.get(event_id), local_registry.lookup(event_id)
        if entry is None or source is None:
            raise PermissionError("history original is absent from actual canonical registration")
        evidence = source.evidence
        committed_record = _committed_record(entry)
        if (entry.event != material.event or entry.event.scope != scope
                or entry.stream_position >= manifest_entry.stream_position
                or evidence.ref_id != event_id or evidence.scope != scope
                or evidence.authority_namespace_id != namespace
                or evidence.content_digest != material.event.content_digest
                or evidence.observed_at != material.event.occurred_at
                or evidence.recorded_at != committed_record["recorded_at"]
                or evidence.parent_refs != material.event.parent_event_ids
                or source.object_ref != material.event.payload_reference
                or not set(evidence.parent_refs).issubset(event_ids)
                or any(entries[parent].stream_position >= entry.stream_position for parent in evidence.parent_refs)):
            raise PermissionError("history original lacks exact scoped causal phase closure")
        raw, raw_reference = local_registry.raw_metadata(source.object_ref), local_registry.raw_reference(source.object_ref)
        if (raw is None or raw_reference is None or raw_reference.scope != scope
                or raw_reference.object_id != source.object_ref
                or raw_reference.plaintext_sha256 != material.event.content_digest
                or raw_reference.size != len(material.plaintext)
                or raw["object_namespace"] != objects.namespace
                or raw["plaintext_sha256"] != material.event.content_digest
                or raw["size"] != len(material.plaintext)):
            raise PermissionError("history original lacks exact durable raw-reference metadata")
        if local_permissions.permits(source, purpose) is not True:
            raise PermissionError("history original/parent purpose permission was withdrawn")
        _, action = sampled.observe_source(event_id, purpose)
        if (action is None or action.decision != "allow"
                or action.source_registration_sha256 != source.registration_sha256):
            raise PermissionError("history original lacks its current exact purpose grant")
        references.append({"event_id": event_id, "registration_sha256": source.registration_sha256,
                           "event_sha256": material.event.event_sha256})
        captured.append(CurrentHistorySource(event_id, source.registration_sha256,
            material.event.event_sha256, action.action_sha256, canonical_json_bytes(_source_record(source)),
            canonical_json_bytes(raw), canonical_json_bytes(_reference_record(raw_reference)),
            canonical_json_bytes(action.metadata_record()), canonical_json_bytes(committed_record)))
    body = {"schema": "flora-comparison-history-manifest-v1", "case_id": case_id,
            "phase": phase, "history_sha256": history_digest, "sources": references}
    body_bytes = _json(body)  # Exactly the custody writer's encoding, not a new schema.
    body_digest = hashlib.sha256(body_bytes).hexdigest()
    if (body_digest != record["content_sha256"]
            or body_digest != manifest_entry.event.content_digest):
        raise PermissionError("history reconstruction differs from actual manifest content digest")
    manifest_raw = local_registry.raw_reference(record["object_id"])
    if (manifest_raw is None or manifest_raw.scope != scope or manifest_raw.object_id != record["object_id"]
            or manifest_raw.plaintext_sha256 != body_digest or manifest_raw.size != len(body_bytes)):
        raise PermissionError("history reconstructed manifest lacks exact durable raw-reference metadata")

    # Keep both real artifact reads and canonical replays. Native metadata
    # decoders can reuse this call's observed rows for the redundant second
    # pass: the terminal SQL below checks every row together after callbacks.
    # Any custom delegate retains the original uncached second pass.
    bindings()
    current_artifact = custody.metadata(run_id, artifact_id)
    if current_artifact is None or canonical_json_bytes(current_artifact.record) != artifact_record:
        raise PermissionError("history manifest metadata changed during current verification")
    if source_purposes:
        sampled.observe_comparison_artifact(run_id=run_id, artifact_id=artifact_id, artifact=current_artifact)
    current_entries = _committed(log)
    current_manifest_entry = current_entries.get(artifact.event_id)
    if current_manifest_entry is None or _committed_record(current_manifest_entry) != _committed_record(manifest_entry):
        raise PermissionError("history manifest canonical authority changed during current verification")
    bindings()
    # Adding an instance alias of the same bound native function compares
    # equal, but it is still an override and must retain the uncached pass.
    native_second_pass = native_second_pass and _second_pass_readers(registry, permissions)[0]
    current_registry = local_registry if native_second_pass else registry
    for snapshot in captured:
        source = current_registry.lookup(snapshot.event_id)
        entry = current_entries.get(snapshot.event_id)
        if (source is None or entry is None
                or canonical_json_bytes(_source_record(source)) != snapshot.source_metadata
                or canonical_json_bytes(_committed_record(entry)) != snapshot.committed_metadata
                or canonical_json_bytes(current_registry.raw_metadata(source.object_ref)) != snapshot.raw_metadata
                or canonical_json_bytes(_reference_record(current_registry.raw_reference(source.object_ref))) != snapshot.raw_reference):
            raise PermissionError("history source/parent current authority changed during verification")
    if history.digest() != history_digest:
        raise PermissionError("held history changed during current verification")
    bindings()
    # Current grants follow all potentially slow artifact/source/raw-reference
    # reads above. A denial introduced by those reads cannot precede acceptance.
    for snapshot in captured:
        if native_second_pass:
            action = local_permissions.current_action(snapshot.event_id, purpose)
        else:
            action = permissions.current_action(snapshot.event_id, purpose)
        if (action is None or action.decision != "allow"
                or canonical_json_bytes(action.metadata_record()) != snapshot.grant_metadata):
            raise PermissionError("history source/parent grant changed after current metadata verification")
    bindings()
    # A final grant callback for one original can withdraw an earlier grant.
    # Observe all actual sampled source/raw/action/head rows together after
    # those callbacks, rather than return another sequential cached allow.
    if after_sources is not None:
        after_sources(sampled)
        bindings()
    sampled.verify_final_current_rows()
    bindings()
    return CurrentHistoryAuthority(run_id, case_id, phase, history_digest, body_digest,
                                   record["event_sha256"], tuple(captured))


def authorize_history_metadata(*, policy: Any, case_id: str, phase: str, history: HistorySnapshot) -> bool:
    """Selected policy delegation; an operational backend failure still raises."""
    try:
        verify_current_history_metadata(policy=policy, case_id=case_id, phase=phase, history=history)
        return True
    except (ValueError, PermissionError, KeyError, TypeError, AttributeError):
        return False


from .comparison_custody import SelectedRunEvidencePolicy, XTDBComparisonCustody
_NATIVE_POLICY_HISTORY_METADATA = SelectedRunEvidencePolicy.authorize_history_metadata
_NATIVE_PERMITS = XTDBFormationPermissionPolicy.permits
_NATIVE_PUBLIC_METADATA_FENCE = authorize_history_metadata
_NATIVE_VERIFY_METADATA_FENCE = verify_current_history_metadata
_NATIVE_CUSTODY_READERS = tuple((name, getattr(XTDBComparisonCustody, name))
    for name in ("_key", "metadata"))


def supports_combined_history_metadata(policy):
    """Only genuine native decoders share a fresh, single guard's row sample."""
    if type(policy) is not SelectedRunEvidencePolicy:
        return False
    custody = policy.custody
    registry, permissions = policy.custody.registry, policy.permissions
    method = policy.authorize_history_metadata
    return (type(custody) is XTDBComparisonCustody
        and all(name not in vars(custody) and isinstance(getattr(custody, name), MethodType)
            and getattr(custody, name).__self__ is custody
            and getattr(custody, name).__func__ is native
            for name, native in _NATIVE_CUSTODY_READERS)
        and "authorize_history_metadata" not in vars(policy)
        and isinstance(method, MethodType) and method.__self__ is policy
        and method.__func__ is _NATIVE_POLICY_HISTORY_METADATA
        and authorize_history_metadata is _NATIVE_PUBLIC_METADATA_FENCE
        and verify_current_history_metadata is _NATIVE_VERIFY_METADATA_FENCE
        and _second_pass_readers(registry, permissions)[0]
        and "permits" not in vars(permissions)
        and isinstance(permissions.permits, MethodType)
        and permissions.permits.__self__ is permissions
        and permissions.permits.__func__ is _NATIVE_PERMITS)


def verify_history_and_external_metadata(*, policy, case_id, phase, history,
                                        source_ids, purpose, final_current):
    """Fresh native history/external checks; the last callback precedes the fence.

    No sample is supplied by a caller or retained after this call. Single-
    purpose callers keep their existing uncached, always-fenced route.
    """
    if not supports_combined_history_metadata(policy):
        raise PermissionError("combined history guard requires genuine native delegates")
    if policy.history_metadata_domain == "selected-history-metadata-v1":
        from .selected_history_fence import verify_selected_history_metadata
        return verify_selected_history_metadata(policy=policy, case_id=case_id,
            phase=phase, history=history, source_purposes=((source_ids, purpose),),
            final_current=final_current)
    def after_sources(sample):
        for event_id in source_ids:
            if sample.local_permissions.permits(sample.local_registry.lookup(event_id), purpose) is not True:
                raise PermissionError("comparator result lost current external source authority")
        final_current()
        if not supports_combined_history_metadata(policy):
            raise PermissionError("combined history guard native delegates changed")
    return _verify_current_history_metadata(policy=policy, case_id=case_id, phase=phase,
        history=history, source_purposes=((source_ids, purpose),), after_sources=after_sources)
