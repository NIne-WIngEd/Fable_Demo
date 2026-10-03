"""Held-history data for one caller-owned selected authority boundary.

This contributor collects exact metadata and phase ancestry. It issues no
proof, performs no terminal observation, and retains no permission result.
The caller must reobserve physical material and fence the shared sample.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from types import FunctionType

from cognitive_kernel.canonical import canonical_json_bytes, require_identifier

from ..comparison_run import HistorySnapshot
from . import selected_history_fence as held_contracts
from . import source_closure as source_contracts
from . import selected_phase_authority as phase_contracts
from .comparison_custody import (
    ComparisonArtifact, SelectedComparisonArtifactMetadata, XTDBComparisonCustody,
    _ARTIFACTS, _json, evaluation_purpose,
)
from .experience import CommittedExperience
from .formation_policy import XTDBFormationPermissionPolicy
from .formation_registry import CanonicalSourceCommitment
from .judgment_lineage import _INTERNAL_EVENT_TYPES
from .selected_context_fence import SelectedContextMetadataSample
from .selected_history_fence import _held_snapshot, _require_held_contracts
from .selected_phase_authority import _FunctionBinding, _identity_seal, _verify_identity
from .source_closure import (
    _ReaderBinding, _commitment_bytes, _native_snapshot, _require_native_contracts,
)


_PERMITS = XTDBFormationPermissionPolicy.permits
_PERMITS_CODE = _PERMITS.__code__
_TARGETED = XTDBComparisonCustody.metadata_selected
_TARGETED_CODE = _TARGETED.__code__
_FUNCTION_BINDING_CLASS = _FunctionBinding
_FORBIDDEN = frozenset({"comparison_artifact", "provider_attempt_artifact",
    "phase_snapshot_artifact", "experiment_manifest_artifact"})
_MEMBERSHIP_BINDINGS = (("_FORBIDDEN", _FORBIDDEN), ("_INTERNAL_EVENT_TYPES", _INTERNAL_EVENT_TYPES))
_IMPORTED = tuple((module, name, getattr(module, name), getattr(module, name).__code__)
    for module, names in ((held_contracts, ("_held_snapshot", "_require_held_contracts")),
        (source_contracts, ("_native_snapshot", "_require_native_contracts", "_commitment_bytes")),
        (phase_contracts, ("_identity_seal", "_verify_identity")))
    for name in names)
_NATIVE_SHAPES = tuple((cls, tuple(vars(cls).items())) for cls in (
    ComparisonArtifact, SelectedComparisonArtifactMetadata, CommittedExperience, _FunctionBinding))
_NATIVE_CODES = tuple((function, function.__code__) for cls, shape in _NATIVE_SHAPES
    for _, value in shape
    for function in (value.__func__ if isinstance(value, (classmethod, staticmethod)) else value,)
    if isinstance(function, FunctionType))
_EXTERNAL_HELPERS = tuple((name, function, function.__code__) for name, function in (
    ("canonical_json_bytes", canonical_json_bytes), ("require_identifier", require_identifier),
    ("_json", _json), ("evaluation_purpose", evaluation_purpose)))


def _require_contribution_contracts():
    """Finite pure code/shape checks, including helpers used by membership."""
    _require_native_contracts()
    _require_held_contracts()
    if _FunctionBinding is not _FUNCTION_BINDING_CLASS:
        raise PermissionError("selected history contributor native function binding changed")
    if any(globals().get(name) is not value for name, value in _MEMBERSHIP_BINDINGS):
        raise PermissionError("selected history contributor phase classification changed")
    for module, name, function, code in _IMPORTED:
        if (getattr(module, name) is not function or globals().get(name) is not function
                or function.__code__ is not code):
            raise PermissionError("selected history contributor helper changed")
    for name, function, code in _LOCAL_HELPERS:
        if globals().get(name) is not function or function.__code__ is not code:
            raise PermissionError("selected history contributor pure code changed")
    for name, function, code in _EXTERNAL_HELPERS:
        if globals().get(name) is not function or function.__code__ is not code:
            raise PermissionError("selected history contributor external helper changed")
    for cls, shape in _NATIVE_SHAPES + _CONTRIBUTION_SHAPE:
        current = vars(cls)
        extra = "__slotnames__" not in dict(shape) and "__slotnames__" in current
        if (len(current) != len(shape) + int(extra)
                or any(current.get(name) is not value for name, value in shape)
                or extra and (type(current["__slotnames__"]) is not list or current["__slotnames__"])):
            raise PermissionError("selected history contributor native shape changed")
    if any(function.__code__ is not code for function, code in _NATIVE_CODES + _CONTRIBUTION_CODES):
        raise PermissionError("selected history contributor native code changed")
    if (XTDBFormationPermissionPolicy.permits is not _PERMITS or _PERMITS.__code__ is not _PERMITS_CODE
            or XTDBComparisonCustody.metadata_selected is not _TARGETED
            or _TARGETED.__code__ is not _TARGETED_CODE):
        raise PermissionError("selected history contributor actual native reader changed")


def _entry_signature(entry):
    if type(entry) is not CommittedExperience:
        raise PermissionError("selected history contributor lacks native committed material")
    fields = object.__getattribute__(entry, "__dict__")
    if (type(fields) is not dict or any(type(key) is not str for key in fields)
            or set(fields) != {"event", "stream_position", "recorded_at"}
            or type(fields["stream_position"]) is not int
            or fields["recorded_at"] is not None and type(fields["recorded_at"]) is not datetime):
        raise PermissionError("selected history contributor committed fields changed")
    return _held_snapshot(fields["event"]), fields["stream_position"], fields["recorded_at"]


def _manifest_signature(manifest):
    if type(manifest) is not SelectedComparisonArtifactMetadata or type(manifest.artifact) is not ComparisonArtifact:
        raise PermissionError("selected history lacks its actual registered manifest")
    if (type(manifest.artifact.record) is not dict
            or any(type(key) is not str for key in manifest.artifact.record)
            or any(type(getattr(manifest, name)) is not str for name in (
                "row_key", "row_scope_digest", "row_record_sha256", "row_record_json"))
            or type(manifest.commitment) is not CanonicalSourceCommitment):
        raise PermissionError("selected history manifest fields are not native metadata")
    _native_snapshot(manifest.commitment)
    return (canonical_json_bytes(manifest.artifact.record), manifest.row_key,
        manifest.row_scope_digest, manifest.row_record_sha256, manifest.row_record_json,
        _commitment_bytes(manifest.commitment), _entry_signature(manifest.committed))


class SelectedHistoryContribution:
    """Data-only H contribution; the root collector verifies private issuance."""

    def __init__(self, origin, sample, physical):
        # The caller-owned binding verifies the privately issued origin before
        # we look inside it, and binds all actual physical reader callbacks.
        physical.binding()
        _require_contribution_contracts()
        if (type(sample) is not SelectedContextMetadataSample or type(origin.history) is not HistorySnapshot
                or type(origin.custody) is not XTDBComparisonCustody
                or type(origin.permissions) is not XTDBFormationPermissionPolicy
                or sample.registry is not origin.registry or sample.comparison is not origin.custody
                or sample.permissions is not origin.runtime.source_policy
                or sample.state is not origin.runtime.state):
            raise TypeError("selected history contribution needs the actual shared owners")
        cap, history = origin.cap, origin.history
        if (type(cap) is not int or cap < 2 or type(history.sources) is not tuple
                or not history.sources or len(history.sources) + 1 > cap):
            raise PermissionError("selected held history exceeds its explicit source cap")
        held = _held_snapshot(history)
        ids = history.event_ids
        if (type(ids) is not tuple or any(type(event_id) is not str for event_id in ids)
                or len(set(ids)) != len(ids) or ids != origin.event_ids):
            raise PermissionError("selected history original identifiers changed")
        for event_id in ids:
            if require_identifier(event_id, "event_id") != event_id:
                raise PermissionError("selected history original identifier is noncanonical")
        run_id, case_id, phase = origin.authority.run_id, origin.case_id, origin.phase
        for value, name in ((run_id, "run_id"), (case_id, "case_id"), (phase, "phase")):
            if type(value) is not str or require_identifier(value, name) != value:
                raise PermissionError("selected history contribution identity is noncanonical")
        digest = history.digest()
        physical.binding()
        if digest != origin.history_sha256:
            raise PermissionError("selected history contribution held bytes changed")
        purpose, artifact_id = evaluation_purpose(run_id, case_id, phase), f"history:{case_id}:{phase}"
        self.origin, self.sample, self.physical = origin, sample, physical
        self.evaluation_purpose, self.original_ids = purpose, ids
        self._cap, self._artifact_id, self._run_id = cap, artifact_id, run_id
        readers = tuple(_ReaderBinding.capture(physical, name) for name in (
            "binding", "entry", "commitment", "adopt", "closure", "contains",
            "captured_entry", "captured_commitment"))
        reader_seals = tuple((reader, _identity_seal(reader)) for reader in readers)
        captured_material = None
        self._guard_binding = None

        def guard():
            for reader, reader_seal in reader_seals:
                _verify_identity(reader, reader_seal, _ReaderBinding)
                reader.verify()
            physical.binding()
            if (self.origin is not origin or self.sample is not sample or self.physical is not physical
                    or self._guard is not guard
                    or type(self.evaluation_purpose) is not str or self.evaluation_purpose != purpose
                    or self.original_ids is not ids or type(self._cap) is not int or self._cap != cap
                    or type(self._artifact_id) is not str or self._artifact_id != artifact_id
                    or type(self._run_id) is not str or self._run_id != run_id
                    or sample.registry is not origin.registry or sample.comparison is not origin.custody
                    or sample.permissions is not origin.runtime.source_policy
                    or sample.state is not origin.runtime.state or _held_snapshot(history) != held):
                raise PermissionError("selected history contribution actual basis changed")
            if (captured_material is not None
                    and (type(self.manifest_id) is not str or self.manifest_id != captured_material[0]
                        or self._manifest_signature is not captured_material[1]
                        or self._evaluation_ids is not captured_material[2])):
                raise PermissionError("selected history captured contribution changed")

        self._guard = guard
        self.binding()
        manifest = origin.custody.metadata_selected(run_id, artifact_id)
        self.binding()
        signature = _manifest_signature(manifest)
        self.binding()
        record, manifest_id = manifest.artifact.record, manifest.artifact.event_id
        outer = record["metadata"]
        if (record["kind"] != "history" or outer["case_id"] != case_id or outer["phase"] != phase
                or outer["evaluation_purpose"] != purpose or outer["history_sha256"] != digest
                or tuple(outer["source_event_ids"]) != ids or tuple(record["parent_event_ids"]) != ids
                or manifest_id in ids):
            raise PermissionError("selected history differs from registered phase manifest")
        self.manifest_id = manifest_id
        self._manifest_signature = signature
        sample._remember("comparison", _ARTIFACTS, manifest.row_key, True, origin.custody, "record_sha256", {
            "_id": manifest.row_key, "scope_digest": manifest.row_scope_digest,
            "record_sha256": manifest.row_record_sha256, "record_json": manifest.row_record_json})
        self.binding()
        commitment = sample.local_registry.lookup_commitment(manifest_id)
        self.binding()
        if commitment != manifest.commitment:
            raise PermissionError("selected manifest registered physical locator changed")
        physical.adopt(commitment, manifest.committed)
        self.binding()
        # Reserve one H slot for its manifest, independently of any C domain.
        physical.closure(ids, maximum_sources=cap - 1)
        self.binding()
        scheduled, pending = set(ids), list(ids)
        while pending:
            event_id = pending.pop()
            current = physical.captured_commitment(event_id)
            if type(current) is not CanonicalSourceCommitment:
                raise PermissionError("selected history source has no captured physical locator")
            _native_snapshot(current)
            parents = current.source.evidence.parent_refs
            if event_id in parents:
                raise PermissionError("selected history source contains a parent cycle")
            if event_id in ids and not set(parents).issubset(ids):
                raise PermissionError("selected history original parent is outside its phase")
            new = set(parents) - scheduled
            if len(scheduled) + len(new) + 1 > cap:
                raise PermissionError("selected history closure exceeds its source cap")
            scheduled.update(new)
            pending.extend(new)
        if manifest_id in scheduled or len(scheduled) + 1 > cap:
            raise PermissionError("selected history closure exceeds its manifest-inclusive source cap")
        self._evaluation_ids = tuple(sorted(scheduled))
        sample.prime_source_purposes(((ids, purpose, cap - 1),), raw_object_ids=(record["object_id"],))
        self.binding()
        references, positions = [], {manifest.committed.stream_position: manifest_id}
        for original in history.sources:
            event_id = original.event.event_id
            entry, current = physical.captured_entry(event_id), physical.captured_commitment(event_id)
            _entry_signature(entry)
            _native_snapshot(current)
            source = current.source
            if (entry.event != original.event or entry.event.event_type in _INTERNAL_EVENT_TYPES
                    or entry.stream_position >= manifest.committed.stream_position
                    or entry.stream_position in positions):
                raise PermissionError("selected original lacks exact original-before-manifest custody")
            positions[entry.stream_position] = event_id
            for parent in entry.event.parent_event_ids:
                parent_entry = physical.captured_entry(parent)
                _entry_signature(parent_entry)
                if parent_entry.stream_position >= entry.stream_position:
                    raise PermissionError("selected history parent is not earlier than its child")
            raw = sample.local_registry.raw_metadata(source.object_ref)
            reference = sample.local_registry.raw_reference(source.object_ref)
            self.binding()
            if (raw is None or reference is None or reference.scope != history.scope
                    or reference.object_id != source.object_ref
                    or reference.plaintext_sha256 != original.event.content_digest
                    or reference.size != len(original.plaintext) or raw["object_namespace"] != origin.custody.objects.namespace
                    or raw["plaintext_sha256"] != original.event.content_digest or raw["size"] != len(original.plaintext)):
                raise PermissionError("selected original lacks exact durable raw metadata")
            references.append({"event_id": event_id, "registration_sha256": source.registration_sha256,
                "event_sha256": original.event.event_sha256})
        body = _json({"schema": "flora-comparison-history-manifest-v1", "case_id": case_id,
            "phase": phase, "history_sha256": digest, "sources": references})
        body_digest = hashlib.sha256(body).hexdigest()
        reference = sample.local_registry.raw_reference(record["object_id"])
        self.binding()
        if (body_digest != record["content_sha256"] or body_digest != manifest.committed.event.content_digest
                or reference is None or reference.scope != history.scope or reference.object_id != record["object_id"]
                or reference.plaintext_sha256 != body_digest or reference.size != len(body)):
            raise PermissionError("selected history reconstruction differs from exact manifest custody")
        # Seal data identities in the existing pure guard after collection.
        captured_material = self.manifest_id, self._manifest_signature, self._evaluation_ids
        self._guard_binding = _FunctionBinding.capture(guard)
        self.binding()

    def binding(self):
        """Pure owner/configuration/held checks, safe after the joint fence."""
        _require_contribution_contracts()
        if self._guard_binding is not None:
            if type(self._guard_binding) is not _FunctionBinding or self._guard_binding.function is not self._guard:
                raise PermissionError("selected history contributor pure guard changed")
            self._guard_binding.verify()
        self._guard()

    def validate_permissions(self):
        """Run actual canonical H rights against this call's shared sample."""
        self.binding()
        for event_id in self._evaluation_ids:
            commitment = self.physical.captured_commitment(event_id)
            source, _ = self.sample.observe_source(event_id, self.evaluation_purpose)
            self.binding()
            if source != commitment.source:
                raise PermissionError("selected history evaluation registration changed")
            # origin.permissions is the native ungated algorithm. The sample
            # keeps the gated runtime policy as its actual owner for C checks.
            if _PERMITS(self.sample.local_permissions, source, self.evaluation_purpose) is not True:
                raise PermissionError("selected history current evaluation purpose was withdrawn")
            self.binding()

    def reobserve_manifest(self):
        """Recheck actual manifest before the caller's final physical pass."""
        self.binding()
        current = self.origin.custody.metadata_selected(self._run_id, self._artifact_id)
        self.binding()
        if _manifest_signature(current) != self._manifest_signature:
            raise PermissionError("selected history manifest changed during current verification")
        self.binding()

    def member(self, event_id):
        """Pure captured ancestry classification; no permission success cache."""
        try:
            self.binding()
            if type(event_id) is not str or require_identifier(event_id, "event_id") != event_id:
                return False
            scheduled, pending, entries = {event_id}, [event_id], {}
            while pending:
                current_id = pending.pop()
                if current_id in entries:
                    continue
                if self.physical.contains(current_id) is not True:
                    return False
                entry = self.physical.captured_entry(current_id)
                commitment = self.physical.captured_commitment(current_id)
                _entry_signature(entry)
                _native_snapshot(commitment)
                event, source = entry.event, commitment.source
                evidence = source.evidence
                if (evidence.ref_id != current_id or event.event_id != current_id
                        or event.scope != self.origin.history.scope or evidence.scope != event.scope
                        or evidence.authority_namespace_id != self.origin.namespace
                        or event.payload_reference != source.object_ref or event.content_digest != evidence.content_digest
                        or event.parent_event_ids != evidence.parent_refs or event.occurred_at != evidence.observed_at):
                    return False
                entries[current_id] = entry
                if event.event_type not in _INTERNAL_EVENT_TYPES:
                    if self.origin.originals.get(current_id) != event:
                        return False
                    continue  # Exact originals are leaves for phase membership.
                if event.event_type in _FORBIDDEN:
                    return False
                parents = event.parent_event_ids
                if not parents:
                    if event.event_type != "state_activation_approval":
                        return False
                    continue
                if current_id in parents:
                    return False
                new = set(parents) - scheduled
                if len(scheduled) + len(new) > self._cap:
                    return False
                scheduled.update(new)
                pending.extend(set(parents) - set(entries))
            if len({entry.stream_position for entry in entries.values()}) != len(entries):
                return False
            for entry in entries.values():
                if entry.event.event_type in _INTERNAL_EVENT_TYPES and any(
                        parent not in entries or entries[parent].stream_position >= entry.stream_position
                        for parent in entry.event.parent_event_ids):
                    return False
            self.binding()
            return True
        except (ValueError, PermissionError, KeyError, TypeError, AttributeError):
            return False


_LOCAL_HELPERS = tuple((function.__name__, function, function.__code__)
    for function in (_require_contribution_contracts, _entry_signature, _manifest_signature))
_CONTRIBUTION_SHAPE = ((SelectedHistoryContribution, tuple(vars(SelectedHistoryContribution).items())),)
_CONTRIBUTION_CODES = tuple((function, function.__code__)
    for _, shape in _CONTRIBUTION_SHAPE for _, function in shape if isinstance(function, FunctionType))
