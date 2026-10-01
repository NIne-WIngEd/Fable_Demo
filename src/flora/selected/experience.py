"""Metadata-only Experience stream over the selected KurrentDB event fabric.

The upstream ExperienceEvent is the authority for event identity and provenance.
This adapter deliberately has no alternate database implementation.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from types import FunctionType
from typing import Any
from uuid import UUID

from cognitive_kernel.contracts import ProductHostScope
from cognitive_kernel.experience import ExperienceEvent
from cognitive_kernel import canonical as _canonical
from cognitive_kernel import contracts as _contracts
from cognitive_kernel import experience as _experience

try:
    from kurrentdbclient import RecordedEvent as _NATIVE_RECORD
except ImportError:  # Pure envelope helpers do not require the optional backend.
    _NATIVE_RECORD = None


def stream_name(scope: ProductHostScope) -> str:
    """Avoid exposing a host identifier in the server's stream catalog."""
    scope.validate()
    digest = hashlib.sha256(scope.storage_scope().encode()).hexdigest()
    return f"fable-experience-{digest}"


def event_uuid(event: ExperienceEvent) -> UUID:
    event.validate()
    # Stable 128-bit ID for a retry of exactly the same immutable envelope.
    return UUID(hex=event.event_sha256[:32])


def encode_event(event: ExperienceEvent) -> bytes:
    event.validate()
    return json.dumps(event.metadata_record(), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def decode_event(data: bytes, scope: ProductHostScope) -> ExperienceEvent:
    event = ExperienceEvent.from_metadata_record(json.loads(data))
    if event.scope != scope:
        raise ValueError("experience event escaped the host scope")
    return event


# Only exact successfully validated envelope bytes are reusable. None of the
# objects returned by replay, including their nested contracts, enter this cache.
_MAX_ENVELOPES = 256
_MAX_ENVELOPE_BYTES = 2 * 1024 * 1024
_EVENT_FIELDS = tuple(ExperienceEvent.__dataclass_fields__)
_SCOPE_FIELDS = tuple(ProductHostScope.__dataclass_fields__)
_PROVENANCE_FIELDS = tuple(_contracts.ProvenanceReference.__dataclass_fields__)
_NATIVE_EVENT = ExperienceEvent
_NATIVE_SCOPE = ProductHostScope
_NATIVE_PROVENANCE = _contracts.ProvenanceReference
_NATIVE_UUID = UUID


def _primitive(value: object) -> bool:
    return (value is None or type(value) in (str, float)
            or (type(value) is tuple and all(_primitive(item) for item in value)))


def _envelope_snapshot(event: ExperienceEvent) -> tuple | None:
    if (type(event) is not _NATIVE_EVENT or type(event.scope) is not _NATIVE_SCOPE
            or type(event.provenance) is not _NATIVE_PROVENANCE):
        return None
    values = tuple(None if field in ("scope", "provenance") else getattr(event, field)
                   for field in _EVENT_FIELDS)
    scope = tuple(getattr(event.scope, field) for field in _SCOPE_FIELDS)
    provenance = tuple(getattr(event.provenance, field) for field in _PROVENANCE_FIELDS)
    snapshot = values, scope, provenance
    return snapshot if _primitive(snapshot) else None


def _restore_envelope(snapshot: tuple) -> ExperienceEvent:
    values, scope, provenance = snapshot
    arguments = list(values)
    arguments[_EVENT_FIELDS.index("scope")] = _NATIVE_SCOPE(*scope)
    arguments[_EVENT_FIELDS.index("provenance")] = _NATIVE_PROVENANCE(*provenance)
    return _NATIVE_EVENT(*arguments)


def _same_owner(left, right) -> bool:
    return left is not None and left[0] is right[0] and left[1:] == right[1:]


def _capture_native_contracts():
    """Capture the decoder's live Python helper graph, including mutable keys."""
    classes = (_NATIVE_EVENT, _NATIVE_SCOPE, _NATIVE_PROVENANCE, _NATIVE_UUID,
               json.JSONDecoder, json.JSONEncoder, CommittedExperience)
    class_shapes = tuple((cls, tuple(vars(cls).items())) for cls in classes)
    pending = [decode_event, event_uuid]
    for cls in classes:
        for value in vars(cls).values():
            if isinstance(value, (classmethod, staticmethod)):
                value = value.__func__
            if isinstance(value, FunctionType):
                pending.append(value)
    functions, bindings, seen, bound = [], [], set(), set()
    while pending:
        function = pending.pop()
        if id(function) in seen:
            continue
        seen.add(id(function))
        defaults = function.__defaults__
        keywords = tuple((function.__kwdefaults__ or {}).items())
        cells = tuple(cell.cell_contents for cell in (function.__closure__ or ()))
        functions.append((function, function.__code__, defaults, keywords, cells))
        for name in function.__code__.co_names:
            # Remember absence as well: injecting a global can override a
            # formerly builtin lookup without replacing the original function.
            value = function.__globals__.get(name)
            contents = frozenset(value) if type(value) is set else None
            key = id(function.__globals__), name
            if key not in bound:
                bindings.append((function.__globals__, name, value, contents))
                bound.add(key)
            if isinstance(value, FunctionType):
                pending.append(value)
    library = ((json, "loads", json.loads), (json, "dumps", json.dumps),
               (json, "_default_decoder", json._default_decoder),
               (json, "_default_encoder", json._default_encoder),
               (hashlib, "sha256", hashlib.sha256), (math, "isfinite", math.isfinite))
    instances = tuple((instance, tuple(vars(instance).items()))
                      for instance in (json._default_decoder, json._default_encoder))
    return class_shapes, tuple(functions), tuple(bindings), library, instances


_NATIVE_DECODE = decode_event
_NATIVE_EVENT_UUID = event_uuid


def _native_contracts_current() -> bool:
    if decode_event is not _NATIVE_DECODE or event_uuid is not _NATIVE_EVENT_UUID:
        return False
    for namespace, name, function, code in _PRIVATE_CODEC_FUNCTIONS:
        if namespace.get(name) is not function or function.__code__ is not code:
            return False
    for namespace, name, value in _PRIVATE_CODEC_BINDINGS:
        if namespace.get(name) is not value:
            return False
    classes, functions, bindings, library, instances = _NATIVE_CONTRACTS
    for cls, fields in classes:
        current = vars(cls)
        if len(current) != len(fields) or any(current.get(name) is not value
                                              for name, value in fields):
            return False
    for function, code, defaults, keywords, cells in functions:
        if (function.__code__ is not code or function.__defaults__ is not defaults
                or tuple((function.__kwdefaults__ or {}).items()) != keywords
                or any(cell.cell_contents is not value
                       for cell, value in zip(function.__closure__ or (), cells))):
            return False
    for namespace, name, value, contents in bindings:
        if namespace.get(name) is not value:
            return False
        if contents is not None and value != contents:
            return False
    for module, name, value in library:
        if getattr(module, name, None) is not value:
            return False
    for instance, fields in instances:
        current = vars(instance)
        if len(current) != len(fields) or any(current.get(name) is not value
                                              for name, value in fields):
            return False
    return True


@dataclass(frozen=True)
class CommittedExperience:
    """Verified event with physical append position and availability time.

    ``recorded_at`` comes from KurrentDB, not the source's observation clock.
    Older clients may omit it; historical formation must then fail closed.
    """

    event: ExperienceEvent
    stream_position: int
    recorded_at: datetime | None


class KurrentExperienceLog:
    """Expected-revision append and verified replay for one host stream.

    A KurrentDBClient is injected so configuration/credentials live outside the
    repository. This class does not claim cross-plane atomicity or integration
    qualification until run against a real service.
    """

    def __init__(self, *, scope: ProductHostScope, client: Any):
        scope.validate()
        self.scope = scope
        self.client = client
        self.stream = stream_name(scope)
        # One published state keeps owner, map and byte accounting coherent
        # under shallow copies/concurrent inserts. Maps are copy-on-write.
        self._envelope_memo = (None, OrderedDict(), 0)

    def _codec_owner(self, client: Any, stream: str) -> tuple | None:
        """Bind the private memo to this actual current host/transport owner."""
        fields = object.__getattribute__(self, "__dict__")
        if set(fields) != {"scope", "client", "stream", "_envelope_memo"}:
            object.__setattr__(self, "_envelope_memo", (None, OrderedDict(), 0))
            return None
        scope = self.scope
        if (type(scope) is not _NATIVE_SCOPE
                or self.client is not client or type(stream) is not str
                or type(self.stream) is not str or self.stream != stream
                or set(vars(scope)) != set(_SCOPE_FIELDS)):
            self._envelope_memo = (None, OrderedDict(), 0)
            return None
        values = tuple(getattr(scope, field) for field in _SCOPE_FIELDS)
        if not all(type(value) is str for value in values):
            return None
        owner = client, stream, values
        prior = self._envelope_memo[0]
        if prior is None or prior[0] is not client or prior[1:] != owner[1:]:
            self._envelope_memo = (owner, OrderedDict(), 0)
        return owner

    def _remember_envelope(self, owner: tuple, data: bytes, snapshot: tuple) -> None:
        memo_owner, previous, total = self._envelope_memo
        if (not _same_owner(memo_owner, owner) or len(data) > _MAX_ENVELOPE_BYTES
                or data in previous):
            return
        # Default/custom copies retain their original protocol. Copy-on-write
        # keeps a shallow clone's memo and byte accounting independent when
        # either clone inserts, evicts, clears or rebinds its owner.
        envelopes = OrderedDict(previous)
        while envelopes and (len(envelopes) >= _MAX_ENVELOPES
                or total + len(data) > _MAX_ENVELOPE_BYTES):
            old, _ = envelopes.popitem(last=False)
            total -= len(old)
        envelopes[data] = snapshot
        self._envelope_memo = (owner, envelopes, total + len(data))

    def append(self, event: ExperienceEvent, *, expected_revision: int) -> None:
        if event.scope != self.scope:
            raise ValueError("event belongs to a different host")
        if expected_revision < -1:
            raise ValueError("expected revision must be -1 or greater")
        from kurrentdbclient import NewEvent, StreamState

        self.client.append_to_stream(
            stream_name=self.stream,
            current_version=(StreamState.NO_STREAM if expected_revision == -1
                             else expected_revision),
            events=[NewEvent(type="FableExperienceV1", data=encode_event(event),
                             id=event_uuid(event))],
        )

    def lookup_committed(self, *, event_id: str, event_sha256: str,
                         stream_position: int, expected_recorded_at: str) -> CommittedExperience:
        """Freshly resolve one registered canonical commitment.

        The caller supplies an independently verified registration's full
        event digest, physical position, and commit time. A successful lookup
        proves this target remains present. It proves neither the integrity of
        the rest of the stream nor a current permission to use the event.

        Ordinary readers request exactly one physical row. Custom replay
        receivers must use their existing replay protocol; this new interface
        rejects them rather than deriving physical proof from returned events.
        The physical row must use the installed, unchanged SDK RecordedEvent
        contract. No transport error is converted into a replay retry.
        """
        if _canonical.require_identifier(event_id, "event_id") != event_id:
            raise ValueError("exact Experience event identifier is not canonical")
        if _canonical.require_sha256(event_sha256, "event_sha256") != event_sha256:
            raise ValueError("exact Experience event digest is not canonical")
        if type(stream_position) is not int or stream_position < 0:
            raise ValueError("exact Experience position must be a nonnegative integer")
        if (_canonical.normalize_timestamp(expected_recorded_at, "expected_recorded_at")
                != expected_recorded_at):
            raise ValueError("exact Experience commit time is not canonical")
        scope, client = self.scope, self.client
        scope.validate()
        scope_values = tuple(getattr(scope, field) for field in _SCOPE_FIELDS)
        stream = stream_name(scope)

        def verify_receiver():
            replay = self.replay
            committed = self.replay_committed
            if (type(self) is not _NATIVE_LOG_CLASS
                    or getattr(replay, "__self__", None) is not self
                    or getattr(replay, "__func__", None) is not _NATIVE_REPLAY
                    or _NATIVE_REPLAY.__code__ is not _NATIVE_REPLAY_CODE
                    or getattr(committed, "__self__", None) is not self
                    or getattr(committed, "__func__", None) is not _NATIVE_REPLAY_COMMITTED
                    or _NATIVE_REPLAY_COMMITTED.__code__ is not _NATIVE_REPLAY_COMMITTED_CODE):
                raise TypeError("exact Experience lookup does not support a custom replay receiver")

        def verify_owner():
            current_scope = self.scope
            current_stream = stream_name(current_scope)
            current_values = tuple(getattr(current_scope, field) for field in _SCOPE_FIELDS)
            if (self.client is not client or self.stream != stream
                    or current_scope != scope or current_values != scope_values
                    or current_stream != stream):
                raise ValueError("exact Experience reader owner changed during lookup")
            verify_receiver()

        def verify_target(entry):
            entry.event.validate()
            if (entry.stream_position != stream_position
                    or type(entry.stream_position) is not int
                    or entry.event.scope != scope
                    or entry.event.event_id != event_id
                    or entry.event.event_sha256 != event_sha256):
                raise ValueError("exact Experience commitment differs from its lookup")
            recorded_at = entry.recorded_at
            if (not isinstance(recorded_at, datetime) or recorded_at.tzinfo is None
                    or recorded_at.utcoffset() is None):
                raise ValueError("exact Experience requires an aware physical commit time")
            if (_canonical.normalize_timestamp(recorded_at.isoformat(), "recorded_at")
                    != expected_recorded_at):
                raise ValueError("exact Experience physical commit time changed")
            verify_owner()
            return entry

        verify_owner()
        from kurrentdbclient.exceptions import NotFoundError

        try:
            records = client.get_stream(stream_name=stream, stream_position=stream_position,
                                        limit=1, resolve_links=False)
        except NotFoundError as error:
            verify_owner()
            raise ValueError("exact Experience commitment is absent") from error
        verify_owner()
        iterator = iter(records)
        row = next(iterator, None)
        if row is None or next(iterator, None) is not None:
            verify_owner()
            raise ValueError("exact Experience lookup must return one physical record")
        from kurrentdbclient import RecordedEvent

        record_shape = vars(RecordedEvent)
        if (RecordedEvent is not _NATIVE_RECORD or type(row) is not _NATIVE_RECORD
                or len(record_shape) != len(_NATIVE_RECORD_SHAPE)
                or any(record_shape.get(name) is not value
                       for name, value in _NATIVE_RECORD_SHAPE)):
            raise TypeError("exact Experience lookup requires the unchanged SDK RecordedEvent contract")
        position, kind, physical_stream = row.stream_position, row.type, row.stream_name
        if (position != stream_position or type(position) is not int
                or type(kind) is not str or kind != "FableExperienceV1"
                or type(physical_stream) is not str or physical_stream != stream):
            raise ValueError("exact Experience physical record differs from its lookup")
        if (type(row.id) is not _NATIVE_UUID or type(row.id.int) is not int
                or type(row.data) is not bytes):
            raise ValueError("exact Experience physical record has invalid UUID or encoded bytes")
        native = (_NATIVE_GATEWAY(self, records, client, stream)
                  if _NATIVE_GATEWAY.__code__ is _NATIVE_GATEWAY_CODE else None)
        if native is not None:
            owner, rows = native
            position, kind, data, identifier, recorded_at = rows[0]
            memo_owner, envelopes, _ = self._envelope_memo
            snapshot = envelopes.get(data) if _same_owner(memo_owner, owner) else None
            if snapshot is None:
                event = decode_event(data, self.scope)
                expected_id = event_uuid(event).int
            else:
                event = _restore_envelope(snapshot)
                expected_id = _NATIVE_UUID(hex=event.event_sha256[:32]).int
            if identifier != expected_id or identifier != int(event.event_sha256[:32], 16):
                raise ValueError("Kurrent event ID differs from the Experience envelope")
            entry = verify_target(CommittedExperience(event, position, recorded_at))
            if snapshot is None:
                snapshot = _envelope_snapshot(event)
                if snapshot is not None:
                    self._remember_envelope(owner, data, snapshot)
            verify_owner()
            return entry
        # Changed codec helpers and nonmemoizable field values use the current
        # decoder. They do not receive an immutable-byte memo shortcut.
        event = decode_event(row.data, self.scope)
        if row.id != event_uuid(event) or row.id.int != int(event.event_sha256[:32], 16):
            raise ValueError("Kurrent event ID differs from the Experience envelope")
        return verify_target(CommittedExperience(event, position,
                                                 getattr(row, "recorded_at", None)))

    def replay_committed(self) -> tuple[CommittedExperience, ...]:
        from kurrentdbclient.exceptions import NotFoundError

        client, stream = self.client, self.stream
        try:
            records = client.get_stream(stream_name=stream)
        except NotFoundError:
            if _NATIVE_GATEWAY.__code__ is _NATIVE_GATEWAY_CODE:
                _NATIVE_GATEWAY(self, (), client, stream)
            return ()
        native = (_NATIVE_GATEWAY(self, records, client, stream)
                  if _NATIVE_GATEWAY.__code__ is _NATIVE_GATEWAY_CODE else None)
        if native is not None:
            owner, rows = native
            result = []
            for expected_position, (position, kind, data, identifier, recorded_at) in enumerate(rows):
                if position != expected_position or kind != "FableExperienceV1":
                    raise ValueError("unexpected event or gap in Experience stream")
                memo_owner, envelopes, _ = self._envelope_memo
                snapshot = envelopes.get(data) if _same_owner(memo_owner, owner) else None
                if snapshot is None:
                    event = decode_event(data, self.scope)
                    expected_id = event_uuid(event).int
                else:
                    event = _restore_envelope(snapshot)
                    expected_id = _NATIVE_UUID(hex=event.event_sha256[:32]).int
                if event.scope != self.scope:
                    raise ValueError("experience event escaped the host scope")
                if identifier != expected_id:
                    raise ValueError("Kurrent event ID differs from the Experience envelope")
                # Physical availability is freshly sampled, never memoized.
                if recorded_at is not None and (
                    recorded_at.tzinfo is None or recorded_at.utcoffset() is None
                ):
                    raise ValueError("Kurrent record time must be timezone-aware")
                if snapshot is None:
                    snapshot = _envelope_snapshot(event)
                    if snapshot is not None:
                        self._remember_envelope(owner, data, snapshot)
                result.append(CommittedExperience(event, expected_position, recorded_at))
            return tuple(result)
        # Every effectful/custom transport, record, contract, helper or time
        # object keeps the original decoder, receiver and callback order.
        result: list[CommittedExperience] = []
        for expected_position, record in enumerate(records):
            if record.stream_position != expected_position or record.type != "FableExperienceV1":
                raise ValueError("unexpected event or gap in Experience stream")
            event = decode_event(record.data, self.scope)
            if record.id != event_uuid(event):
                raise ValueError("Kurrent event ID differs from the Experience envelope")
            recorded_at = getattr(record, "recorded_at", None)
            if recorded_at is not None and (
                not isinstance(recorded_at, datetime)
                or recorded_at.tzinfo is None or recorded_at.utcoffset() is None
            ):
                raise ValueError("Kurrent record time must be timezone-aware")
            result.append(CommittedExperience(event, expected_position, recorded_at))
        return tuple(result)

    def replay(self) -> list[ExperienceEvent]:
        return [record.event for record in self.replay_committed()]


_NATIVE_LOG_CLASS = KurrentExperienceLog
_NATIVE_LOG_SHAPE = tuple(vars(KurrentExperienceLog).items())
_NATIVE_REPLAY = KurrentExperienceLog.replay
_NATIVE_REPLAY_CODE = _NATIVE_REPLAY.__code__
_NATIVE_REPLAY_COMMITTED = KurrentExperienceLog.replay_committed
_NATIVE_REPLAY_COMMITTED_CODE = _NATIVE_REPLAY_COMMITTED.__code__


def _native_codec_gateway(log, records, client, stream):
    """One current-call classification after all actual transport callbacks."""
    current = vars(_NATIVE_LOG_CLASS)
    # copyreg lazily adds this empty bookkeeping list for ordinary non-slot
    # classes; it is not attribute machinery or an installed delegate.
    copy_slots = current.get("__slotnames__")
    copy_field = ("__slotnames__" not in dict(_NATIVE_LOG_SHAPE)
                  and type(copy_slots) is list and not copy_slots)
    if (type(log) is not _NATIVE_LOG_CLASS or KurrentExperienceLog is not _NATIVE_LOG_CLASS
            or len(current) != len(_NATIVE_LOG_SHAPE) + int(copy_field)
            or any(current.get(name) is not value for name, value in _NATIVE_LOG_SHAPE)
            or _native_contracts_current is not _NATIVE_CHECK
            or _NATIVE_CHECK.__code__ is not _NATIVE_CHECK_CODE
            or not _NATIVE_CHECK()):
        object.__setattr__(log, "_envelope_memo", (None, OrderedDict(), 0))
        return None
    # This private original method is protected above and never dispatches to
    # an instance/class callback pretending to qualify a memo owner.
    owner = _NATIVE_OWNER(log, client, stream)
    if owner is None or type(records) is not tuple or _NATIVE_RECORD is None:
        return None
    shape = vars(_NATIVE_RECORD)
    if (len(shape) != len(_NATIVE_RECORD_SHAPE)
            or any(shape.get(name) is not value for name, value in _NATIVE_RECORD_SHAPE)):
        return None
    rows = []
    for record in records:
        if type(record) is not _NATIVE_RECORD:
            return None
        position, kind, data = record.stream_position, record.type, record.data
        identifier, recorded_at = record.id, record.recorded_at
        if (type(position) is not int or type(kind) is not str or type(data) is not bytes
                or type(identifier) is not _NATIVE_UUID
                or (recorded_at is not None and (
                    type(recorded_at) is not datetime or recorded_at.tzinfo is not timezone.utc))):
            return None
        # Do not retain a returned RecordedEvent or mutable UUID alias.
        identifier_value = identifier.int
        if type(identifier_value) is not int:
            return None
        rows.append((position, kind, data, identifier_value, recorded_at))
    return owner, tuple(rows)


_NATIVE_RECORD_SHAPE = tuple(vars(_NATIVE_RECORD).items()) if _NATIVE_RECORD else ()
_NATIVE_OWNER = KurrentExperienceLog._codec_owner
_NATIVE_CHECK = _native_contracts_current
_NATIVE_CHECK_CODE = _native_contracts_current.__code__
_NATIVE_GATEWAY = _native_codec_gateway
_NATIVE_GATEWAY_CODE = _native_codec_gateway.__code__
_PRIVATE_CODEC_FUNCTIONS = tuple(
    (globals(), function.__name__, function, function.__code__)
    for function in (_primitive, _envelope_snapshot, _restore_envelope, _same_owner,
                     _native_codec_gateway, _native_contracts_current)
) + tuple((vars(KurrentExperienceLog), name, value, value.__code__)
          for name, value in vars(KurrentExperienceLog).items()
          if isinstance(value, FunctionType))
_PRIVATE_CODEC_BINDINGS = tuple((globals(), name, globals()[name]) for name in (
    "_NATIVE_EVENT", "_NATIVE_SCOPE", "_NATIVE_PROVENANCE", "_NATIVE_UUID", "_NATIVE_RECORD",
    "_EVENT_FIELDS", "_SCOPE_FIELDS", "_PROVENANCE_FIELDS", "_NATIVE_OWNER",
    "_NATIVE_CHECK", "_NATIVE_CHECK_CODE", "_NATIVE_GATEWAY", "_NATIVE_GATEWAY_CODE",
    "_NATIVE_REPLAY", "_NATIVE_REPLAY_CODE", "_NATIVE_REPLAY_COMMITTED",
    "_NATIVE_REPLAY_COMMITTED_CODE"))
_PRIVATE_CODEC_BINDINGS += tuple((globals(), name, globals()[name]) for name in (
    "CommittedExperience", "datetime", "timezone", "OrderedDict", "_NATIVE_RECORD_SHAPE"))
_NATIVE_CONTRACTS = _capture_native_contracts()
