"""Bounded current source/parent proof in an explicitly selected domain.

This metadata-only path does not audit unrelated stream entries, claim heads,
scientific phases, or model relevance. Existing default/replay/history readers
are unchanged. Successful observations grant no lease for a later byte read.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from types import FunctionType, GetSetDescriptorType, MethodType

from cognitive_kernel.canonical import canonical_json_bytes, require_identifier
from cognitive_kernel.contracts import ProductHostScope
from cognitive_kernel.formation_contracts import FormationEvidenceRef
from cognitive_kernel.formation_sources import RegisteredFormationSource

from .experience import KurrentExperienceLog
from .formation_policy import FormationPermissionAction, XTDBFormationPermissionPolicy, _action_from_record
from .formation_registry import CanonicalSourceCommitment, XTDBFormationSourceRegistry, _evidence_from_record
from .phase_source_fence import OneGuardSelectedMetadata
from .claims import _rows


_DOMAIN = "selected-source-closure-v1"
_LOOKUP = KurrentExperienceLog.lookup_committed
_LOOKUP_CODE = _LOOKUP.__code__
_NATIVE_LAYOUTS = {cls: tuple(cls.__dataclass_fields__) for cls in (
    ProductHostScope, FormationEvidenceRef, RegisteredFormationSource,
    CanonicalSourceCommitment, FormationPermissionAction)}
_CONTRACT_SHAPES = tuple((cls, tuple(vars(cls).items())) for cls in _NATIVE_LAYOUTS)
_CONTRACT_CODES = tuple((function, function.__code__) for cls, shape in _CONTRACT_SHAPES
    for _, value in shape for function in (value.__func__ if isinstance(value, (classmethod, staticmethod)) else value,)
    if isinstance(function, FunctionType))
_ROWS_CODE = _rows.__code__
_ROWS_FUNCTION = _rows
_ABSENT = object()
_ROWS_GLOBALS = tuple((name, _rows.__globals__.get(name, _ABSENT))
                     for name in ("dict", "zip"))


def _require_native_contracts():
    """Finite native class bindings; this never invokes a contract method."""
    for name, function, code in _PURE_FUNCTIONS:
        if globals().get(name) is not function or function.__code__ is not code:
            raise PermissionError("selected source closure pure helper binding changed")
    for cls, shape in _CONTRACT_SHAPES + _PURE_CLASS_SHAPES:
        current = vars(cls)
        extra = "__slotnames__" not in dict(shape) and "__slotnames__" in current
        if (len(current) != len(shape) + int(extra)
                or any(current.get(name) is not value for name, value in shape)
                or extra and (type(current["__slotnames__"]) is not list or current["__slotnames__"])):
            raise PermissionError("selected source closure native contract binding changed")
    if any(function.__code__ is not code for function, code in _CONTRACT_CODES + _PURE_CLASS_CODES):
        raise PermissionError("selected source closure native contract code changed")
    if _rows is not _ROWS_FUNCTION or _rows.__code__ is not _ROWS_CODE:
        raise PermissionError("selected source closure row reader code changed")
    if any(_rows.__globals__.get(name, _ABSENT) is not value for name, value in _ROWS_GLOBALS):
        raise PermissionError("selected source closure row reader global changed")


def _native_snapshot(value):
    """Primitive tuples from native instance dictionaries, without callbacks."""
    cls = type(value)
    if value is None or cls is str or cls is int or cls is bool:
        return value
    if cls is tuple:
        return tuple(_native_snapshot(item) for item in value)
    if type(cls) is not type:
        raise PermissionError("selected source closure observation has a nonnative metadata class")
    fields = _NATIVE_LAYOUTS.get(cls)
    if fields is None:
        raise PermissionError("selected source closure observation is not native metadata")
    values = object.__getattribute__(value, "__dict__")
    if (type(values) is not dict or any(type(name) is not str for name in values)
            or set(values) != set(fields)):
        raise PermissionError("selected source closure native metadata fields changed")
    return cls, tuple((name, _native_snapshot(values[name])) for name in fields)


def _descriptor(cls, name):
    for base in cls.__mro__:
        if name in vars(base):
            return vars(base)[name]
    return _ABSENT


def _raw_code(value):
    if type(value) is MethodType:
        return value.__func__.__code__
    if type(value) is FunctionType:
        return value.__code__
    return None


@dataclass(frozen=True)
class _ReaderBinding:
    owner: object
    owner_class: type
    name: str
    dictionary: object
    instance_value: object
    descriptor: object
    descriptor_code: object
    instance_code: object
    dictionary_descriptor: object
    attribute_descriptor: object
    fallback_descriptor: object

    @classmethod
    def capture(cls, owner, name):
        owner_class = type(owner)
        dictionary_descriptor = _descriptor(owner_class, "__dict__")
        if dictionary_descriptor is not _ABSENT and type(dictionary_descriptor) is not GetSetDescriptorType:
            raise TypeError("selected source closure needs ordinary reader instance dictionaries")
        try:
            dictionary = object.__getattribute__(owner, "__dict__")
        except AttributeError:
            dictionary = None
        if dictionary is not None and type(dictionary) is not dict:
            raise TypeError("selected source closure reader dictionary is not ordinary")
        if dictionary is not None and any(type(name) is not str for name in dictionary):
            raise TypeError("selected source closure reader dictionary keys are not ordinary")
        instance_value = _ABSENT if dictionary is None else dictionary.get(name, _ABSENT)
        descriptor = _descriptor(owner_class, name)
        return cls(owner, owner_class, name, dictionary, instance_value, descriptor,
            _raw_code(descriptor), _raw_code(instance_value), dictionary_descriptor,
            _descriptor(owner_class, "__getattribute__"), _descriptor(owner_class, "__getattr__"))

    def verify(self):
        owner_class = type(self.owner)
        if (owner_class is not self.owner_class
                or _descriptor(owner_class, "__dict__") is not self.dictionary_descriptor
                or _descriptor(owner_class, "__getattribute__") is not self.attribute_descriptor
                or _descriptor(owner_class, "__getattr__") is not self.fallback_descriptor
                or _descriptor(owner_class, self.name) is not self.descriptor
                or _raw_code(self.descriptor) is not self.descriptor_code):
            raise PermissionError("selected source closure actual reader binding changed")
        try:
            current = object.__getattribute__(self.owner, "__dict__")
        except AttributeError:
            current = None
        if current is not None and (type(current) is not dict or any(type(name) is not str for name in current)):
            raise PermissionError("selected source closure actual reader dictionary changed")
        instance_value = _ABSENT if current is None else current.get(self.name, _ABSENT)
        if (current is not self.dictionary or instance_value is not self.instance_value
                or _raw_code(instance_value) is not self.instance_code):
            raise PermissionError("selected source closure actual reader binding changed")


class _ClosureMetadataSample(OneGuardSelectedMetadata):
    """New selected domain only; old default fences keep their implementation."""

    def __init__(self, *, binding_guard, **kwargs):
        self._closure_binding_guard = binding_guard
        registry, permissions = kwargs["registry"], kwargs["permissions"]
        self._selected_owner_bindings = tuple((name, owner) for name, owner in (
            ("registry", registry), ("permissions", permissions),
            ("claims", kwargs.get("claims")), ("comparison", kwargs.get("comparison")))
            if owner is not None)
        self._selected_scope_snapshot = _native_snapshot(registry.scope)
        self._selected_connection = registry.connection
        self._selected_namespace = registry.authority_namespace_id
        self._selected_scope_digests = tuple((owner, owner.scope_digest)
            for _, owner in self._selected_owner_bindings)
        ports = {"registry": ("_fetch", "lookup", "raw_metadata", "raw_reference"),
            "permissions": ("_fetch", "permits", "current_action", "_head", "_stored_action"),
            "claims": ("_fetch_record", "load_current"),
            "comparison": ("_key", "metadata")}
        self._selected_reader_bindings = tuple(_ReaderBinding.capture(owner, port)
            for name, owner in self._selected_owner_bindings for port in ports[name])
        super().__init__(**kwargs)

    def _bindings(self):
        # The context subclass invokes this after its terminal statement too.
        # The older generic guard calls scope.metadata_record()/JSON helpers;
        # those are callbacks and must not run after selected rows were fenced.
        self._closure_binding_guard()
        _require_native_contracts()
        for reader in self._selected_reader_bindings:
            reader.verify()
        for name, owner in self._selected_owner_bindings:
            if object.__getattribute__(self, name) is not owner:
                raise PermissionError("selected metadata fence actual owner changed")
            fields = object.__getattribute__(owner, "__dict__")
            if (fields.get("connection") is not self._selected_connection
                    or _native_snapshot(fields.get("scope")) != self._selected_scope_snapshot
                    or type(fields.get("authority_namespace_id")) is not str
                    or fields["authority_namespace_id"] != self._selected_namespace):
                raise PermissionError("selected metadata fence actual scope/connection changed")
            if name in ("permissions", "comparison") and fields.get("registry") is not self.registry:
                raise PermissionError("selected metadata fence registered owner changed")
        for owner, digest in self._selected_scope_digests:
            fields = object.__getattribute__(owner, "__dict__")
            if type(fields.get("scope_digest")) is not str or fields["scope_digest"] != digest:
                raise PermissionError("selected metadata fence scope digest changed")
        if (self.connection is not self._selected_connection
                or type(self.namespace) is not str or self.namespace != self._selected_namespace):
            raise PermissionError("selected metadata fence selected basis changed")

    def verify_final_current_rows(self):
        """One terminal basis, followed only by guarded primitive comparisons.

        Unlike the older generic fence, this new domain requires the stored
        record_json string to remain exact. Even a formatting-only rewrite is
        rejected. No JSON or contract metadata helper runs after SQL callbacks.
        """
        self._bindings()
        if not self._observations:
            raise PermissionError("terminal selected source closure has no observed rows")
        grouped, expected = {}, {}
        for item in self._observations.values():
            group = item.kind, item.table, item.immutable, item.scope_digest, item.digest_column
            grouped.setdefault(group, []).append(item)
        terms, parameters = [], []
        for (kind, table, immutable, scope_digest, column), items in sorted(grouped.items()):
            tag = kind + ":" + table + (":all" if immutable else ":current")
            keys = sorted(item.key for item in items)
            temporal = " FOR VALID_TIME ALL" if immutable else ""
            terms.append(f"SELECT '{tag}' AS fence_kind, _id, scope_digest, "
                f"{column} AS fence_sha256, record_json FROM {table}{temporal} "
                "WHERE scope_digest = %s AND _id IN (" + ", ".join("%s::text" for _ in keys) + ")")
            parameters.extend((scope_digest, *keys))
            for item in items:
                row = self._sampled_rows[(kind, table, item.key, immutable)]
                if type(row["record_json"]) is not str:
                    raise TypeError("selected source closure requires exact record_json text")
                expected[(tag, item.key)] = item.scope_digest, item.digest, row["record_json"]
        sql = "SELECT * FROM (" + " UNION ALL ".join(terms) + f") AS flora_current_metadata_fence LIMIT {len(expected) + 1}"
        cursor = self.connection.execute(sql, tuple(parameters))
        self._closure_binding_guard()
        values = _rows(cursor)
        self._closure_binding_guard()
        if len(values) != len(expected):
            raise PermissionError("terminal current selected source closure has missing/ambiguous rows")
        seen = set()
        for row in values:
            if (type(row) is not dict or any(type(name) is not str for name in row)
                    or any(type(row.get(name)) is not str for name in (
                    "fence_kind", "_id", "scope_digest", "fence_sha256", "record_json"))):
                raise PermissionError("terminal current selected source closure returned nonprimitive metadata")
            key = row["fence_kind"], row["_id"]
            if key not in expected or key in seen:
                raise PermissionError("terminal current selected source closure has unexpected/duplicate rows")
            seen.add(key)
            if (row["scope_digest"], row["fence_sha256"], row["record_json"]) != expected[key]:
                raise PermissionError("terminal current source/grant selected metadata changed")
        self._closure_binding_guard()


@dataclass(frozen=True)
class SelectedSourceClosureProof:
    """Same-call metadata observations, never authorization after return."""

    domain: str
    purpose: str
    nominated_event_ids: tuple[str, ...]
    commitments: tuple[CanonicalSourceCommitment, ...]
    grant_actions: tuple[FormationPermissionAction, ...]


def _commitment_bytes(commitment: CanonicalSourceCommitment) -> bytes:
    commitment.validate()
    return canonical_json_bytes({
        "source": {"evidence": commitment.source.evidence.metadata_record(),
                   "object_ref": commitment.source.object_ref,
                   "registration_sha256": commitment.source.registration_sha256},
        "event_sha256": commitment.event_sha256,
        "stream_position": commitment.stream_position,
        "recorded_at": commitment.recorded_at,
    })


def _commitment_copy(material: bytes) -> CanonicalSourceCommitment:
    record = json.loads(material)
    source = RegisteredFormationSource.create(
        evidence=_evidence_from_record(record["source"]["evidence"]),
        object_ref=record["source"]["object_ref"])
    if source.registration_sha256 != record["source"]["registration_sha256"]:
        raise PermissionError("selected source closure copy lost registration binding")
    result = CanonicalSourceCommitment(source, record["event_sha256"],
                                       record["stream_position"], record["recorded_at"])
    result.validate()
    return result


class SelectedSourceClosureResolver:
    """Selected evidence closure with fresh grants and one terminal row basis.

    The positive source cap is a caller-owned resource limit. The cap covers
    all nominated sources and discovered parents before their reads. Zero
    memory turns skip this resolver. Its finite metadata samples are discarded
    after each call; predicate answers are never cached.
    """

    domain = _DOMAIN

    def __init__(self, *, registry: XTDBFormationSourceRegistry,
                 log: KurrentExperienceLog,
                 permissions: XTDBFormationPermissionPolicy,
                 maximum_sources: int):
        if (not isinstance(registry, XTDBFormationSourceRegistry)
                or type(log) is not KurrentExperienceLog
                or not isinstance(permissions, XTDBFormationPermissionPolicy)):
            raise TypeError("selected source closure requires actual selected services")
        self.registry, self.log, self.permissions = registry, log, permissions
        self.maximum_sources = maximum_sources
        self._require_configuration()

    def _require_configuration(self):
        if type(self.maximum_sources) is not int or self.maximum_sources < 1:
            raise ValueError("selected source closure requires a positive source cap")
        registry, log, permissions = self.registry, self.log, self.permissions
        if (registry.scope != log.scope or permissions.scope != registry.scope
                or permissions.registry is not registry
                or permissions.connection is not registry.connection
                or permissions.authority_namespace_id != registry.authority_namespace_id
                or permissions.scope_digest != registry.scope_digest):
            raise ValueError("selected source closure crosses actual owner or authority")
        lookup = log.lookup_committed
        if (getattr(lookup, "__func__", None) is not _LOOKUP
                or getattr(lookup, "__self__", None) is not log
                or _LOOKUP.__code__ is not _LOOKUP_CODE):
            raise TypeError("selected source closure needs the exact physical lookup protocol")

    def resolve(self, *, source_event_ids: tuple[str, ...],
                purpose: str) -> SelectedSourceClosureProof:
        """Observe selected physical targets and fence their authority metadata.

        Every physical target is freshly read twice. Actual current purpose
        predicates run before and after that second pass. The terminal SQL
        observes source/raw/current-head/immutable-action rows together after
        callbacks. Kurrent reads and XTDB's final basis are separate observations,
        not a cross-plane transaction. Later bytes need a new current-use barrier.
        """
        self._require_configuration()
        if (type(source_event_ids) is not tuple or not source_event_ids
                or len(source_event_ids) > self.maximum_sources):
            raise ValueError("selected source closure needs a nonempty finite source tuple within its cap")
        for event_id in source_event_ids:
            if require_identifier(event_id, "source_event_id") != event_id:
                raise ValueError("selected source closure source ID must be canonical")
        if len(set(source_event_ids)) != len(source_event_ids):
            raise ValueError("selected source closure nominations must be unique")
        if require_identifier(purpose, "purpose") != purpose:
            raise ValueError("selected source closure purpose must be canonical")

        registry, log, permissions = self.registry, self.log, self.permissions
        pure_guard, pure_guard_code = _require_native_contracts, _require_native_contracts.__code__
        maximum_sources = self.maximum_sources
        scope, namespace = registry.scope, registry.authority_namespace_id
        _require_native_contracts()
        scope_record = _native_snapshot(scope)
        log_scope, permission_scope = log.scope, permissions.scope
        connection, scope_digest = registry.connection, registry.scope_digest
        client, stream = log.client, log.stream
        services = ((self, ("resolve", "_require_configuration", "domain")),
                    (registry, ("_key", "_fetch", "_decode", "lookup", "lookup_commitment", "raw_metadata")),
                    (permissions, ("_key", "_fetch", "_decode", "_head", "_stored_action", "current_action", "permits")),
                    (log, ("lookup_committed", "replay", "replay_committed")),
                    (client, ("get_stream",)), (connection, ("execute",)))
        readers = tuple(_ReaderBinding.capture(owner, name)
                        for owner, names in services for name in names)
        def require_binding():
            if pure_guard.__code__ is not pure_guard_code:
                raise PermissionError("selected source closure pure guard code changed")
            pure_guard()
            for reader in readers:
                reader.verify()
            own = object.__getattribute__(self, "__dict__")
            source_fields = object.__getattribute__(registry, "__dict__")
            permission_fields = object.__getattribute__(permissions, "__dict__")
            log_fields = object.__getattribute__(log, "__dict__")
            if (own.get("registry") is not registry or own.get("log") is not log
                    or own.get("permissions") is not permissions
                    or type(own.get("maximum_sources")) is not int or own["maximum_sources"] != maximum_sources
                    or source_fields.get("scope") is not scope or permission_fields.get("registry") is not registry
                    or source_fields.get("connection") is not connection or permission_fields.get("connection") is not connection
                    or type(source_fields.get("authority_namespace_id")) is not str
                    or source_fields["authority_namespace_id"] != namespace
                    or type(permission_fields.get("authority_namespace_id")) is not str
                    or permission_fields["authority_namespace_id"] != namespace
                    or type(source_fields.get("scope_digest")) is not str or source_fields["scope_digest"] != scope_digest
                    or type(permission_fields.get("scope_digest")) is not str or permission_fields["scope_digest"] != scope_digest
                    or log_fields.get("scope") is not log_scope or permission_fields.get("scope") is not permission_scope
                    or _native_snapshot(scope) != scope_record
                    or _native_snapshot(log_scope) != scope_record
                    or _native_snapshot(permission_scope) != scope_record
                    or log_fields.get("client") is not client
                    or type(log_fields.get("stream")) is not str or log_fields["stream"] != stream):
                raise PermissionError("selected source closure actual owner binding changed")
        require_binding()
        sample = _ClosureMetadataSample(binding_guard=require_binding,
            registry=registry, permissions=permissions, maximum_rows=4 * maximum_sources)
        require_binding()
        commitments, material, actions, action_material = {}, {}, {}, {}
        primitive_commitments, primitive_actions = {}, {}

        def physical(commitment):
            entry = log.lookup_committed(event_id=commitment.source.evidence.ref_id,
                event_sha256=commitment.event_sha256, stream_position=commitment.stream_position,
                expected_recorded_at=commitment.recorded_at)
            require_binding()
            evidence, event = commitment.source.evidence, entry.event
            if (event.scope != scope or evidence.scope != scope
                    or evidence.authority_namespace_id != namespace
                    or event.event_id != evidence.ref_id
                    or event.event_sha256 != commitment.event_sha256
                    or entry.stream_position != commitment.stream_position
                    or event.payload_reference != commitment.source.object_ref
                    or event.content_digest != evidence.content_digest
                    or event.parent_event_ids != evidence.parent_refs
                    or event.occurred_at != evidence.observed_at):
                raise PermissionError("selected source closure event differs from registered evidence")

        # Discover the exact parent set before calling a policy that itself
        # follows parents. No parent is scheduled or read past the source cap.
        scheduled = set(source_event_ids)
        states, positions = {}, {}
        pending = [(event_id, False) for event_id in reversed(source_event_ids)]
        while pending:
            event_id, completed = pending.pop()
            if completed:
                commitment = commitments[event_id]
                for parent_id in commitment.source.evidence.parent_refs:
                    if commitments[parent_id].stream_position >= commitment.stream_position:
                        raise PermissionError("selected source closure parent is not earlier than its child")
                states[event_id] = 2
                continue
            if states.get(event_id) == 2:
                continue
            if states.get(event_id) == 1:
                raise PermissionError("selected source closure contains a parent cycle")
            require_binding()
            commitment = sample.local_registry.lookup_commitment(event_id)
            require_binding()
            if commitment is None:
                raise PermissionError("selected source closure registered source is absent")
            if type(commitment) is not CanonicalSourceCommitment:
                raise TypeError("selected source closure needs a typed registered commitment")
            commitment.validate()
            if commitment.source.evidence.ref_id != event_id:
                raise PermissionError("selected source closure commitment differs from its nomination")
            if commitment.stream_position in positions and positions[commitment.stream_position] != event_id:
                raise PermissionError("selected source closure has ambiguous physical positions")
            parents = commitment.source.evidence.parent_refs
            new_parents = set(parents) - scheduled
            if len(scheduled) + len(new_parents) > maximum_sources:
                raise PermissionError("selected source closure exceeds its source cap")
            if event_id in parents or any(states.get(parent_id) == 1 for parent_id in parents):
                raise PermissionError("selected source closure contains a parent cycle")
            scheduled.update(new_parents)
            commitments[event_id], material[event_id] = commitment, _commitment_bytes(commitment)
            primitive_commitments[event_id] = _native_snapshot(commitment)
            positions[commitment.stream_position] = event_id
            physical(commitment)
            states[event_id] = 1
            pending.append((event_id, True))
            pending.extend((parent_id, False) for parent_id in reversed(parents))

        ordered_ids = tuple(sorted(commitments))
        for event_id in ordered_ids:
            source, action = sample.observe_source(event_id, purpose)
            require_binding()
            if source != commitments[event_id].source:
                raise PermissionError("selected source closure sampled registration changed")
            actions[event_id], action_material[event_id] = action, canonical_json_bytes(action.metadata_record())
            primitive_actions[event_id] = _native_snapshot(action)
            if permissions.permits(commitments[event_id].source, purpose) is not True:
                raise PermissionError("selected source closure current purpose grant refused")
            require_binding()

        # Metadata observed earlier is not a physical lease. Re-read the exact
        # selected locators and targets after the initial policy callbacks.
        for event_id in ordered_ids:
            current = registry.lookup_commitment(event_id)
            require_binding()
            if current is None or _commitment_bytes(current) != material[event_id]:
                raise PermissionError("selected source closure registered locator changed")
            physical(current)
        for event_id in ordered_ids:
            if permissions.permits(commitments[event_id].source, purpose) is not True:
                raise PermissionError("selected source closure final purpose grant refused")
            require_binding()

        def require_observations():
            try:
                unchanged = all(_native_snapshot(commitments[event_id]) == primitive_commitments[event_id]
                    and _native_snapshot(actions[event_id]) == primitive_actions[event_id]
                    for event_id in ordered_ids)
            except (ValueError, TypeError, KeyError) as error:
                raise PermissionError("selected source closure callback observation changed") from error
            if not unchanged:
                raise PermissionError("selected source closure callback observation changed")

        require_binding()
        require_observations()
        # Clone immutable metadata before the terminal boundary. Neither the
        # result nor its source/grant objects are the callback's input aliases.
        proof = SelectedSourceClosureProof(_DOMAIN, purpose, source_event_ids,
            tuple(_commitment_copy(material[event_id]) for event_id in ordered_ids),
            tuple(_action_from_record(json.loads(action_material[event_id])) for event_id in ordered_ids))
        sample.verify_final_current_rows()
        require_binding()
        require_observations()
        return proof


_PURE_FUNCTIONS = tuple((function.__name__, function, function.__code__) for function in (
    _require_native_contracts, _native_snapshot, _descriptor, _raw_code))
_PURE_CLASS_SHAPES = tuple((cls, tuple(vars(cls).items())) for cls in (
    _ReaderBinding, _ClosureMetadataSample))
_PURE_CLASS_CODES = tuple((function, function.__code__) for cls, shape in _PURE_CLASS_SHAPES
    for _, value in shape for function in (value.__func__ if isinstance(value, (classmethod, staticmethod)) else value,)
    if isinstance(function, FunctionType))
