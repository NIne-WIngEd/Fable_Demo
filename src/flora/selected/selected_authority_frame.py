"""Fresh shared data for one issued selected-context authority boundary.

Only a pair of privately issued native gates with the same physical origin
may compose here. Data and sampled rows are shared, never a positive allow.
Each byte boundary constructs its own frame; the final XTDB observation joins
all held-history, context, Claim and governed-state dependencies.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import FunctionType, MethodType
from weakref import ref

from cognitive_kernel.canonical import canonical_json_bytes

from .claims import XTDBClaimAuthority, _CURRENT, _HEAD
from .experience import CommittedExperience
from .formation_policy import XTDBFormationPermissionPolicy
from .formation_registry import CanonicalSourceCommitment
from .governed_development import XTDBGovernedPersonalDevelopment
from .selected_context import (SelectedContextLogView, SelectedContextSources,
    SelectedJudgmentContextPolicy, _SELECTED_EVENT_PREDICATE, _require_policy_contracts)
from .selected_context_fence import SelectedContextMetadataSample
from .selected_history_fence import _held_snapshot, _require_held_contracts
from .source_closure import _ReaderBinding, _native_snapshot, _require_native_contracts
from . import selected_phase_authority as phase_contracts
from . import context_guard as context_contracts
from .selected_phase_authority import _FunctionBinding, selected_phase_authority
from .selected_history_contribution import SelectedHistoryContribution


# Weak identity seals retain captured material, never a permission answer. They
# keep replacement objects from being dereferenced before their native checks.
_OWNERS = {}


def _identity(owner):
    fields = object.__getattribute__(owner, "__dict__")
    if type(fields) is not dict or any(type(key) is not str for key in fields):
        raise PermissionError("shared frame owner fields are not native")
    return type(owner), id(fields), tuple((key, type(value), id(value))
        for key, value in fields.items())


def _register_owner(owner):
    key = id(owner)
    def discard(dead):
        current = _OWNERS.get(key)
        if current is not None and current[0] is dead:
            del _OWNERS[key]
    _OWNERS[key] = ref(owner, discard), _identity(owner)


def _verify_owner(owner):
    registered = _OWNERS.get(id(owner))
    if (registered is None or registered[0]() is not owner
            or type(owner) is not registered[1][0]):
        raise PermissionError("shared frame captured owner fields changed")
    current, expected = _identity(owner), registered[1]
    if (current[1] != expected[1] or len(current[2]) != len(expected[2])
            or any(name != old_name or cls is not old_cls or identity != old_identity
                for (name, cls, identity), (old_name, old_cls, old_identity)
                in zip(current[2], expected[2]))):
        raise PermissionError("shared frame captured owner fields changed")


def _set_owned(owner, **changes):
    _verify_owner(owner)
    fields = object.__getattribute__(owner, "__dict__")
    fields.update(changes)
    _register_owner(owner)


def _register_binding(binding):
    _register_owner(binding)
    if type(binding) is _FunctionBinding:
        for nested in binding.nested:
            _register_binding(nested)
        for _, value in binding.closure:
            if type(value) is tuple and all(type(item) is _ReaderBinding for item in value):
                for reader in value:
                    _register_binding(reader)


def _verify_binding(binding):
    _verify_owner(binding)
    if type(binding) is _FunctionBinding:
        for nested in binding.nested:
            _verify_binding(nested)
        for _, value in binding.closure:
            if type(value) is tuple and all(type(item) is _ReaderBinding for item in value):
                for reader in value:
                    _verify_binding(reader)
    elif type(binding) is not _ReaderBinding:
        raise PermissionError("shared frame captured binding is not native")
    binding.verify()


def _native_context_binding(function):
    """Known pure context closures, including the underlying wrapper guard."""
    if (type(function) is not FunctionType or function.__code__ not in _BINDING_CODES
            or function.__globals__ is not context_contracts.__dict__):
        raise TypeError("shared frame requires its native context binding guard")
    cells = dict(zip(function.__code__.co_freevars, function.__closure__ or ()))
    nested_name = _BINDING_NESTED.get(function.__code__)
    if nested_name is not None:
        _native_context_binding(cells[nested_name].cell_contents)
    elif (cells["native_guard"].cell_contents is not _require_native_contracts
            or cells["snapshot"].cell_contents is not _native_snapshot):
        raise TypeError("shared frame requires native pure snapshot helpers")


def _capture_context_binding(function, opaque_codes):
    """Seal native pure closures without adopting opaque callback internals.

    A prepared guard closes over an independent authority callable. Its exact
    identity stays bound by the native closure and owner reader, but counters
    and other state inside that callable are allowed to evolve when it runs.
    Only the known nested pure context guards are recursively sealed here.
    """
    _native_context_binding(function)
    cells = tuple((cell, cell.cell_contents) for cell in function.__closure__ or ())
    named = dict(zip(function.__code__.co_freevars, function.__closure__ or ()))
    nested_name = _BINDING_NESTED.get(function.__code__)
    nested_function = None if nested_name is None else named[nested_name].cell_contents
    opaque_codes.extend((value, value.__code__) for _, value in cells
        if type(value) is FunctionType and value is not nested_function)
    nested = (() if nested_name is None else
        (_capture_context_binding(nested_function, opaque_codes),))
    return _FunctionBinding(function, function.__code__, cells,
        tuple((name, function.__globals__.get(name, phase_contracts._ABSENT))
            for name in set(function.__code__.co_names)), nested)


def shared_phase_origin(permissions, policy):
    """Validate dual issuance before callbacks, without metadata/private I/O.

    Fully unissued consumers retain their old explicit path. Once either port
    is issued, both must still be issued and bind exactly the same origin.
    """
    _require_frame_contracts()
    permission = selected_phase_authority(permissions, "permits")
    event = selected_phase_authority(policy, "allow_event")
    if permission is None and event is None:
        return None
    if permission is None or event is None:
        raise PermissionError("shared authority frame needs both privately issued native gates")
    permission.verify()
    event.verify()
    if permission._origin is not event._origin:
        raise PermissionError("shared authority frame phase origins differ")
    return permission._origin


def _entry_snapshot(entry):
    """Native physical fields only; no JSON/metadata callback after a fence."""
    _require_held_contracts()
    if type(entry) is not CommittedExperience:
        raise PermissionError("shared frame needs an exact native physical entry")
    fields = object.__getattribute__(entry, "__dict__")
    if (type(fields) is not dict or any(type(key) is not str for key in fields)
            or set(fields) != {"event", "stream_position", "recorded_at"}
            or type(fields["stream_position"]) is not int
            or type(fields["recorded_at"]) is not datetime
            or fields["recorded_at"].tzinfo is not timezone.utc):
        raise PermissionError("shared frame physical entry has nonnative fields")
    recorded = fields["recorded_at"]
    return (_held_snapshot(fields["event"]), fields["stream_position"],
        (recorded.year, recorded.month, recorded.day, recorded.hour,
         recorded.minute, recorded.second, recorded.microsecond))


class _FramePhysicalData:
    """Captured exact targets; the first and final physical reads stay owned."""

    def __init__(self, *, origin, sample, binding_guard):
        self.origin, self.sample, self._binding_guard = origin, sample, binding_guard
        self._commitments, self._entries, self._signatures, self._positions = {}, {}, {}, {}
        self._material = ()
        _register_owner(self)

    def binding(self):
        _require_frame_contracts()
        _verify_owner(self)
        self._binding_guard()
        if (any(type(values) is not dict or any(type(key) is not str for key in values)
                for values in (self._commitments, self._entries, self._signatures))
                or type(self._positions) is not dict
                or any(type(key) is not int or type(value) is not str
                       for key, value in self._positions.items())):
            raise PermissionError("shared frame physical maps are not native")
        keys = tuple(row[0] for row in self._material)
        if (set(self._entries) != set(keys) or set(self._commitments) != set(keys)
                or set(self._signatures) != set(keys)
                or len(self._positions) != len(keys)):
            raise PermissionError("shared frame physical target set changed")
        for event_id, commitment_id, entry_id, signature, position in self._material:
            commitment, entry = self._commitments[event_id], self._entries[event_id]
            if (id(commitment) != commitment_id or id(entry) != entry_id
                    or type(self._signatures[event_id]) is not tuple
                    or self._signatures[event_id] is not signature
                    or self._positions.get(position) != event_id
                    or _native_snapshot(commitment) != signature[0]
                    or _entry_snapshot(entry) != signature[1]):
                raise PermissionError("shared frame captured physical material changed")

    def contains(self, event_id):
        _require_frame_contracts()
        _verify_owner(self)
        if type(self._entries) is not dict or any(type(key) is not str for key in self._entries):
            raise PermissionError("shared frame physical keys changed")
        return type(event_id) is str and event_id in self._entries

    def captured_commitment(self, event_id):
        if not self.contains(event_id):
            raise PermissionError("shared frame membership expanded outside captured material")
        return self._commitments[event_id]

    def captured_entry(self, event_id):
        if not self.contains(event_id):
            raise PermissionError("shared frame membership expanded outside captured material")
        return self._entries[event_id]

    def commitment(self, event_id):
        self.entry(event_id)
        return self._commitments[event_id]

    def entry(self, event_id):
        self.binding()
        if type(event_id) is not str:
            raise PermissionError("shared physical nomination must be native text")
        if event_id not in self._entries:
            commitment = self.sample.local_registry.lookup_commitment(event_id)
            self.binding()
            if type(commitment) is not CanonicalSourceCommitment:
                raise PermissionError("shared physical nomination lacks its exact registration")
            commitment.validate()
            if commitment.source.evidence.ref_id != event_id:
                raise PermissionError("shared physical nomination changed its source ID")
            entry = self.origin.log.lookup_committed(event_id=event_id,
                event_sha256=commitment.event_sha256,
                stream_position=commitment.stream_position,
                expected_recorded_at=commitment.recorded_at)
            self.binding()
            self.adopt(commitment, entry)
        return self._entries[event_id]

    def adopt(self, commitment, committed):
        """Retain an actual manifest read without inventing a second first pass."""
        self.binding()
        if type(commitment) is not CanonicalSourceCommitment:
            raise PermissionError("shared physical material lost its native commitment")
        commitment.validate()
        entry_signature = _entry_snapshot(committed)
        evidence, event = commitment.source.evidence, committed.event
        event_id = evidence.ref_id
        if (type(event_id) is not str or _native_snapshot(event.scope) != self.origin.scope
                or _native_snapshot(evidence.scope) != self.origin.scope
                or evidence.authority_namespace_id != self.origin.namespace
                or event.event_id != event_id or event.event_sha256 != commitment.event_sha256
                or committed.stream_position != commitment.stream_position
                or event.payload_reference != commitment.source.object_ref
                or event.content_digest != evidence.content_digest
                or event.parent_event_ids != evidence.parent_refs
                or event.occurred_at != evidence.observed_at):
            raise PermissionError("shared physical event differs from registered evidence")
        signature = _native_snapshot(commitment), entry_signature
        position = commitment.stream_position
        if position in self._positions and self._positions[position] != event_id:
            raise PermissionError("shared physical material has ambiguous positions")
        if event_id in self._signatures and self._signatures[event_id] != signature:
            raise PermissionError("shared physical material changed within its boundary")
        self._positions[position] = event_id
        self._commitments[event_id], self._entries[event_id] = commitment, committed
        self._signatures[event_id] = signature
        _set_owned(self, _material=tuple((key, id(self._commitments[key]),
            id(self._entries[key]), self._signatures[key], self._commitments[key].stream_position)
            for key in sorted(self._entries)))
        self.binding()

    def closure(self, ids, maximum_sources):
        """Collect a complete separately capped DAG, checking before expansion."""
        self.binding()
        if (type(ids) is not tuple or not ids or type(maximum_sources) is not int
                or maximum_sources < 1 or any(type(value) is not str for value in ids)
                or len(set(ids)) != len(ids) or len(ids) > maximum_sources):
            raise PermissionError("shared physical closure lacks a finite native nomination")
        scheduled, complete, active = set(ids), set(), set()
        pending = [(event_id, False) for event_id in reversed(ids)]
        while pending:
            event_id, exiting = pending.pop()
            if exiting:
                active.remove(event_id)
                complete.add(event_id)
                continue
            if event_id in complete:
                continue
            if event_id in active:
                raise PermissionError("shared physical closure contains a cycle")
            commitment = self.commitment(event_id)
            parents = commitment.source.evidence.parent_refs
            if type(parents) is not tuple or any(type(value) is not str for value in parents):
                raise PermissionError("shared physical closure has nonnative parents")
            later = set(parents) - scheduled
            if len(scheduled) + len(later) > maximum_sources:
                raise PermissionError("shared physical closure exceeds its own source cap")
            scheduled.update(later)
            active.add(event_id)
            pending.append((event_id, True))
            pending.extend((parent, False) for parent in reversed(parents))
        for event_id in complete:
            commitment = self._commitments[event_id]
            if any(self._commitments[parent].stream_position >= commitment.stream_position
                    for parent in commitment.source.evidence.parent_refs):
                raise PermissionError("shared physical parent is not earlier than its child")
        self.binding()
        return tuple(sorted(complete))

    def reobserve(self, *, observed_manifest):
        """Re-read original locators and exact physical targets after callbacks."""
        self.binding()
        if type(observed_manifest) is not str or observed_manifest not in self._entries:
            raise PermissionError("shared frame manifest second observation is absent")
        for event_id in sorted(self._entries):
            # H just re-read and compared the actual manifest locator/entry.
            if event_id == observed_manifest:
                continue
            self.binding()
            current = self.origin.registry.lookup_commitment(event_id)
            self.binding()
            if (current is None or _native_snapshot(current) != self._signatures[event_id][0]):
                raise PermissionError("shared physical source locator changed after callbacks")
            entry = self.origin.log.lookup_committed(event_id=event_id,
                event_sha256=current.event_sha256, stream_position=current.stream_position,
                expected_recorded_at=current.recorded_at)
            self.binding()
            if _entry_snapshot(entry) != self._signatures[event_id][1]:
                raise PermissionError("shared physical target changed after callbacks")
        self.binding()


class SharedSelectedAuthorityFrame:
    """One call's data contributors and one joint terminal row observation."""

    def __init__(self, *, log, policy, claims, state, binding_guard, origin):
        _require_frame_contracts()
        _require_policy_contracts()
        if (type(log) is not SelectedContextLogView
                or type(policy) is not SelectedJudgmentContextPolicy
                or type(claims) is not XTDBClaimAuthority
                or type(state) is not XTDBGovernedPersonalDevelopment
                or type(binding_guard) is not FunctionType):
            raise TypeError("shared frame needs its actual supported selected context owners")
        _native_context_binding(binding_guard)
        self.log, self.policy, self.claims, self.state = log, policy, claims, state
        self.origin, self._binding_guard = origin, binding_guard
        opaque_codes = []
        self._guard_binding = _capture_context_binding(binding_guard, opaque_codes)
        self._guard_codes = tuple(opaque_codes)
        self._permission_descriptor = selected_phase_authority(policy.permissions, "permits")
        self._event_descriptor = selected_phase_authority(policy, "allow_event")
        self._sources, self._resolver, self._original = log.sources, log.resolver, log._original
        if (type(self._sources) is not SelectedContextSources
                or type(self._sources.event_ids) is not tuple
                or any(type(value) is not str for value in self._sources.event_ids)
                or type(self._sources.maximum_sources) is not int):
            raise PermissionError("shared frame needs exact finite context nominations")
        self._context_ids, self._context_cap = self._sources.event_ids, self._sources.maximum_sources
        self._closed, self._finishing, self._checking = False, False, False
        self.history, self.sample = None, None
        ports = (
            (log, ("scope", "resolver", "sources", "purpose", "_original", "_policy_binding_guard", "replay", "_configuration")),
            (self._sources, ("event_ids", "maximum_sources")),
            (self._resolver, ("registry", "log", "permissions", "maximum_sources", "resolve", "_require_configuration")),
            (policy, ("registry", "permissions", "claims", "state", "log", "purpose", "allow_claim", "allow_state", "allow_event")),
            (claims, ("scope", "authority_namespace_id", "connection", "_fetch_record", "load_current", "load_version", "load_evidence_relation")),
            (state, ("scope", "authority_namespace_id", "connection", "registry", "policy", "episodes", "_fetch", "_history", "_immutable")))
        self._readers = tuple(_ReaderBinding.capture(owner, name)
            for owner, names in ports for name in names)
        _register_binding(self._guard_binding)
        for reader in self._readers:
            _register_binding(reader)
        _register_owner(self)
        self._base_bindings()
        # Retain the existing explicit metadata-row cap. H, C, Claim versions,
        # evidence, state approvals and rollback targets all consume this cap.
        sample = SelectedContextMetadataSample(state=state,
            binding_guard=self._base_bindings, registry=policy.registry,
            permissions=policy.permissions, claims=claims, comparison=origin.custody,
            maximum_rows=4096)
        _register_owner(sample)
        _set_owned(self, sample=sample)
        physical = _FramePhysicalData(origin=origin, sample=sample,
            binding_guard=self._base_bindings)
        _set_owned(self, physical=physical)
        history = SelectedHistoryContribution(origin, sample, physical)
        _register_owner(history)
        _register_binding(history._guard_binding)
        _set_owned(self, history=history)
        nominations = ((origin.event_ids, self.history.evaluation_purpose, origin.cap - 1),
            (self._context_ids, policy.purpose, self._context_cap))
        self.sample.prime_source_purposes(nominations)
        closure = self.physical.closure(self._context_ids, self._context_cap)
        events = tuple(self.physical.captured_entry(event_id).event
            for event_id in sorted(closure,
                key=lambda value: self.physical.captured_commitment(value).stream_position))
        _set_owned(self, _context_closure=closure, context_events=events, _local_readers=(),
            _context_material=tuple(_held_snapshot(event) for event in events))
        # Only local views compose phase semantics. The real runtime policy and
        # state.policy remain the actual gated controllers used by the sample.
        def permits(current, source, purpose):
            self.binding()
            self.history.validate_permissions()
            if not self.history.member(source.evidence.ref_id):
                return False
            result = XTDBFormationPermissionPolicy.permits(current, source, purpose) is True
            self.binding()
            return result
        self.sample.local_permissions.permits = MethodType(permits, self.sample.local_permissions)
        local_reader = _ReaderBinding.capture(self.sample.local_permissions, "permits")
        _register_binding(local_reader)
        _set_owned(self, _local_readers=(local_reader,))
        self.history.validate_permissions()
        for event_id in self._context_closure:
            source, _ = self.sample.observe_source(event_id, policy.purpose)
            if (source != self.physical.captured_commitment(event_id).source
                    or self.sample.local_permissions.permits(source, policy.purpose) is not True):
                raise PermissionError("shared context source purpose or phase membership refused")
        self.binding()

    def _base_bindings(self):
        """Pure original-owner checks, also safe during sample construction."""
        _require_frame_contracts()
        _verify_owner(self)
        if self._closed:
            raise PermissionError("shared authority frame was discarded")
        # This flag exists only while native pure binding checks are on the
        # stack. It is cleared before every authority or transport callback.
        if self._checking:
            return
        if self.sample is not None:
            _verify_owner(self.sample)
        self._permission_descriptor.verify()
        self._event_descriptor.verify()
        if (self._permission_descriptor._origin is not self.origin
                or self._event_descriptor._origin is not self.origin):
            raise PermissionError("shared authority frame lost its exact native origin")
        _verify_binding(self._guard_binding)
        if any(type(function) is not FunctionType or function.__code__ is not code
               for function, code in self._guard_codes):
            raise PermissionError("shared frame independent callback code changed")
        for reader in self._readers:
            _verify_binding(reader)
        self._binding_guard()
        if (self.policy.log is not self.log or self.policy.claims is not self.claims
                or self.policy.state is not self.state or self.policy.registry is not self.origin.registry
                or self.policy.permissions is not self.origin.runtime.source_policy
                or self.state.policy is not self.policy.permissions
                or self.state.registry is not self.origin.registry
                or self._original is not self.log._original
                or type(self._original) is not tuple or len(self._original) != 3
                or any(value is not expected for value, expected in zip(self._original,
                    (self.origin.registry, self.origin.log, self.policy.permissions)))
                or self.log.sources is not self._sources or self.log.resolver is not self._resolver
                or self._sources.event_ids is not self._context_ids
                or type(self._sources.maximum_sources) is not int
                or self._sources.maximum_sources != self._context_cap
                or self._resolver.maximum_sources != self._context_cap
                or self._resolver.registry is not self.origin.registry
                or self._resolver.log is not self.origin.log
                or self._resolver.permissions is not self.policy.permissions
                or self.log.purpose != self.policy.purpose
                or self.state.episodes is not None):
            raise PermissionError("shared authority frame actual domain/owner/cap changed")

    def binding(self):
        self._base_bindings()
        _set_owned(self, _checking=True)
        try:
            if self.history is not None:
                _verify_owner(self.history)
                _verify_binding(self.history._guard_binding)
                self.history.binding()
            for reader in getattr(self, "_local_readers", ()):
                _verify_binding(reader)
            if hasattr(self, "physical"):
                self.physical.binding()
            if (hasattr(self, "_context_material")
                    and tuple(_held_snapshot(event) for event in self.context_events) != self._context_material):
                raise PermissionError("shared authority frame captured context changed")
        finally:
            _set_owned(self, _checking=False)

    def metadata_view(self):
        """Canonical predicates over this frame's captured data, no proof return."""
        self.binding()
        claims, state, log, policy = context_contracts._metadata_view(claims=self.claims, state=self.state,
            log=self.log, policy=self.policy, source_sample=self.sample,
            captured_events=self.context_events)
        original_claim_reader = claims._fetch_record
        def claim_read(*args, **kwargs):
            self.binding()
            if kwargs.get("table") in {_CURRENT, _HEAD}:
                return self.sample.local_claims._fetch_record(*args, **kwargs)
            return original_claim_reader(*args, **kwargs)
        claims._fetch_record = claim_read
        def replay():
            self.binding()
            return list(self.context_events)
        log.replay = replay
        def allow_event(current, event_id, purpose):
            self.binding()
            self.history.validate_permissions()
            result = (self.history.member(event_id)
                and _SELECTED_EVENT_PREDICATE(current, event_id, purpose) is True)
            self.binding()
            return result
        policy.allow_event = MethodType(allow_event, policy)
        readers = tuple(_ReaderBinding.capture(owner, name) for owner, names in (
            (claims, ("_fetch_record",)), (state, ("_fetch", "registry", "policy")),
            (log, ("replay",)), (policy, ("allow_event", "allow_claim", "allow_state"))) for name in names)
        for reader in readers:
            _register_binding(reader)
        _set_owned(self, _local_readers=self._local_readers + readers)
        self.binding()
        return claims, state, log, policy

    def observe_nominations(self, material):
        self.binding()
        self.sample.observe_claim_nominations(material["claims"])
        self.sample.observe_state_nominations(self.state, material["states"])
        for claim_id, expected in material["claims"]:
            if canonical_json_bytes(self.sample.local_claims.load_current(claim_id)) != canonical_json_bytes(expected["current"]):
                raise PermissionError("shared initial current Claim changed")
        if material["episodes"]:
            raise PermissionError("shared context frame has an unsupported episode domain")
        self.binding()

    def observe_authorities(self, prepared):
        self.binding()
        self.sample.observe_claim_authorities(prepared.claim_authorities)
        self.sample.observe_state_authorities(self.state, prepared.state_authorities)
        for captured in prepared.claim_authorities:
            if canonical_json_bytes(self.sample.local_claims.load_current(captured.claim_id)) != captured.current_record:
                raise PermissionError("shared prepared current Claim changed")
        if prepared.episode_authorities:
            raise PermissionError("shared context frame has an unsupported episode domain")
        self.binding()

    def finish(self, authority_guard=None):
        """Independent callbacks, exact physical re-observation, joint final row fence."""
        self.binding()
        if self._finishing:
            raise PermissionError("shared authority frame cannot finalize recursively")
        _set_owned(self, _finishing=True)
        try:
            if authority_guard is not None:
                if not callable(authority_guard) or authority_guard() is not None:
                    raise PermissionError("shared independent authority guard refused")
            self.binding()
            self.history.validate_permissions()
            self.history.reobserve_manifest()
            self.binding()
            self.physical.reobserve(observed_manifest=self.history.manifest_id)
            self.binding()
            self.sample.verify_final_current_rows()
            self.binding()
        finally:
            # A refused callback may already have changed fields; closing must
            # still discard the frame without dereferencing those replacements.
            object.__getattribute__(self, "__dict__")["_closed"] = True


def create_shared_selected_frame(*, log, policy, claims, state, binding_guard):
    """Opt in only through two verified native producer descriptors."""
    _require_frame_contracts()
    if type(log) is not SelectedContextLogView:
        return None
    origin = shared_phase_origin(policy.permissions, policy)
    if origin is None:
        return None
    return SharedSelectedAuthorityFrame(log=log, policy=policy, claims=claims,
        state=state, binding_guard=binding_guard, origin=origin)


def _require_frame_contracts():
    for name, value in _NATIVE_NAMES:
        if globals().get(name) is not value:
            raise PermissionError("shared frame native dependency identity changed")
    for module, name, function, code in _PRODUCERS:
        if getattr(module, name) is not function or function.__code__ is not code:
            raise PermissionError("shared frame native producer/composition helper changed")
    phase_contracts._require_descriptor_contracts()
    context_contracts._require_shared_context_contracts()
    for name, function, code in _PURE:
        if globals().get(name) is not function or function.__code__ is not code:
            raise PermissionError("shared selected frame helper code changed")
    for cls, shape in _SHAPES:
        current = vars(cls)
        extra = "__slotnames__" not in dict(shape) and "__slotnames__" in current
        if (len(current) != len(shape) + int(extra)
                or any(current.get(name) is not value for name, value in shape)
                or extra and (type(current["__slotnames__"]) is not list or current["__slotnames__"])):
            raise PermissionError("shared selected frame native class changed")
    if any(function.__code__ is not code for function, code in _CODES):
        raise PermissionError("shared selected frame native class code changed")
    for name, function, code in _EXTERNAL:
        if globals().get(name) is not function or function.__code__ is not code:
            raise PermissionError("shared selected frame native dependency changed")


_PURE = tuple((function.__name__, function, function.__code__) for function in (
    _identity, _register_owner, _verify_owner, _set_owned, _register_binding, _verify_binding,
    _native_context_binding, _capture_context_binding,
    shared_phase_origin, _entry_snapshot, create_shared_selected_frame, _require_frame_contracts))
_SHAPES = tuple((cls, tuple(vars(cls).items())) for cls in (
    _FramePhysicalData, SharedSelectedAuthorityFrame, SelectedContextSources, CommittedExperience))
_CODES = tuple((value, value.__code__) for _, shape in _SHAPES
    for _, value in shape if type(value) is FunctionType)
_EXTERNAL = tuple((function.__name__, function, function.__code__) for function in (
    _held_snapshot, _require_held_contracts, _native_snapshot, _require_native_contracts,
    _require_policy_contracts, selected_phase_authority)) + (("_SELECTED_EVENT_PREDICATE", _SELECTED_EVENT_PREDICATE,
                                  _SELECTED_EVENT_PREDICATE.__code__),)
_PRODUCERS = tuple((module, name, getattr(module, name), getattr(module, name).__code__)
    for module, names in ((phase_contracts, ("selected_phase_authority", "_require_descriptor_contracts")),
        (context_contracts, ("_metadata_view", "_require_shared_context_contracts"))) for name in names)
_BINDING_CODES = tuple(code for function, name in (
    (context_contracts._shared_metadata_frame, "frame_bindings"),
    (context_contracts._selected_binding_guard, "current"),
    (context_contracts.prepare_current_context, "initial_bindings"),
    (context_contracts.PreparedCurrentContext.metadata_current, "bindings"))
    for code in function.__code__.co_consts if type(code).__name__ == "code" and code.co_name == name)
_BINDING_NESTED = {code: name for code in _BINDING_CODES for function_name, name in (
    ("frame_bindings", "binding_guard"), ("initial_bindings", "bindings_current"),
    ("bindings", "actual_bindings")) if code.co_name == function_name}
_NATIVE_NAMES = tuple((cls.__name__, cls) for cls in (
    _FramePhysicalData, SharedSelectedAuthorityFrame, SelectedHistoryContribution,
    SelectedContextMetadataSample, SelectedContextLogView, SelectedContextSources,
    SelectedJudgmentContextPolicy, XTDBClaimAuthority, XTDBGovernedPersonalDevelopment,
    XTDBFormationPermissionPolicy, CanonicalSourceCommitment, CommittedExperience,
    _FunctionBinding, _ReaderBinding)) + (("phase_contracts", phase_contracts),
        ("context_contracts", context_contracts), ("_OWNERS", _OWNERS))
