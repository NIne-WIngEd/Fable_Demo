"""One terminal basis for selected source, Claim and governed-state metadata.

State heads have primitive columns rather than record_json. They must share
the source/grant terminal statement: a later source callback can otherwise
change an already checked active state. No private bytes or allow results are
stored here, and no JSON/contract helper runs after the terminal statement.
"""
from __future__ import annotations

import json
from types import FunctionType

from cognitive_kernel.canonical import canonical_json_bytes

from . import claims as claim_tables
from .governed_development import XTDBGovernedPersonalDevelopment, _HISTORY
from .personal_state import _ACTIVE, _VERSIONS
from .source_closure import _ClosureMetadataSample, _ReaderBinding, _native_snapshot


_EXTRA = ("subject_type", "subject_id", "projection_id", "version_id", "generation",
          "content_object_id", "activation_generation", "approval_event_id",
          "approval_event_sha256", "expected_active_version_id")
_NUMBERS = {"generation", "activation_generation"}
_HEAD = ("_id", "scope_digest", "subject_type", "subject_id", "projection_id",
         "version_id", "projection_sha256", "activation_generation", "approval_event_id",
         "approval_event_sha256", "expected_active_version_id")
_VERSION = ("_id", "scope_digest", "projection_id", "subject_type", "subject_id",
            "version_id", "generation", "projection_sha256", "content_object_id", "record_json")
_RECEIPT = ("_id", "scope_digest", "record_sha256", "record_json")
_RESULT = ("fence_kind", "_id", "scope_digest", "fence_sha256", "record_json", *_EXTRA)


def _primitive_columns(row, columns):
    if (type(row) is not dict or any(type(name) is not str for name in row)
            or any(name not in row for name in columns)):
        raise PermissionError("selected state fence needs exact primitive row columns")
    values = []
    for name in columns:
        value = row[name]
        if name in _NUMBERS:
            if type(value) is not int:
                raise PermissionError("selected state fence requires integer generations")
        elif name == "expected_active_version_id" and value is None:
            pass
        elif type(value) is not str:
            raise PermissionError("selected state fence requires native metadata text")
        values.append(value)
    return tuple(values)


def _terminal_rows(cursor, binding):
    """Reject effectful result keys/values before hashing or comparison."""
    names = tuple(column.name for column in cursor.description)
    binding()
    if any(type(name) is not str for name in names) or len(set(names)) != len(names):
        raise PermissionError("terminal selected context returned nonnative column names")
    raw = cursor.fetchall()
    binding()
    if type(raw) is not list and type(raw) is not tuple:
        raise PermissionError("terminal selected context returned a nonnative row collection")
    rows = []
    for values in raw:
        if type(values) is not tuple and type(values) is not list:
            raise PermissionError("terminal selected context returned nonnative row values")
        if len(values) != len(names) or any(value is not None and type(value) is not str
                and type(value) is not int for value in values):
            raise PermissionError("terminal selected context returned nonnative metadata")
        rows.append(dict(zip(names, values)))
    return rows


class SelectedContextMetadataSample(_ClosureMetadataSample):
    """Fresh call-local state observations joined with source/Claim rows."""

    def __init__(self, *, state, binding_guard, **kwargs):
        if type(state) is not XTDBGovernedPersonalDevelopment:
            raise TypeError("selected context state fence needs its actual governed owner")
        self.state = state
        self._state_rows = {}
        self._claim_rows = {}
        self._state_readers = tuple(_ReaderBinding.capture(state, name) for name in (
            "_fetch", "_head_id", "_version_id", "_history_key", "_rollback_key", "_rollback_id_key"))
        self._state_scope = state.scope
        self._state_scope_signature = _native_snapshot(state.scope)
        self._state_scope_digest = state.scope_digest
        super().__init__(binding_guard=binding_guard, **kwargs)
        self._claim_readers = (() if self.claims is None else tuple(
            _ReaderBinding.capture(self.claims, name) for name in (
                "_fetch_record", "_row_id", "load_version", "load_evidence_relation")))

    def _bindings(self):
        _require_fence_code()
        super()._bindings()
        for reader in self._state_readers:
            reader.verify()
        for reader in getattr(self, "_claim_readers", ()):
            reader.verify()
        if (self.state.connection is not self.connection or self.state.registry is not self.registry
                or self.state.policy is not self.permissions or self.state.scope is not self._state_scope
                or _native_snapshot(self.state.scope) != self._state_scope_signature
                or type(self.state.scope_digest) is not str or self.state.scope_digest != self._state_scope_digest
                or type(self.state.authority_namespace_id) is not str
                or self.state.authority_namespace_id != self.namespace):
            raise PermissionError("selected context state fence actual owner changed")

    def _observe(self, *, table, key, immutable, expected, columns, record=False):
        self._bindings()
        if type(table) is not str or type(key) is not str or type(immutable) is not bool:
            raise PermissionError("selected state fence nomination is not primitive")
        row = self.state._fetch(table, key, all_valid=immutable)
        self._bindings()
        primitive = _primitive_columns(row, columns)
        if row["_id"] != key or row["scope_digest"] != self._state_scope_digest:
            raise PermissionError("selected state fence row crosses its owner/key")
        if record:
            if canonical_json_bytes(json.loads(row["record_json"])) != expected:
                raise PermissionError("selected state receipt changed before its terminal fence")
        elif primitive != _primitive_columns(expected, columns):
            raise PermissionError("selected state authority changed before its terminal fence")
        identity = table, key, immutable
        value = columns, primitive
        if identity in self._state_rows and self._state_rows[identity] != value:
            raise PermissionError("selected state observation changed during this guard")
        if (len(self._observations) + len(self._state_rows) + len(self._claim_rows)
                + int(identity not in self._state_rows) > self.maximum_rows):
            raise PermissionError("selected state/source fence exceeds its explicit row cap")
        self._state_rows[identity] = value
        self._bindings()

    def _observe_claim(self, *, table, identifier, digest_column, expected):
        self._bindings()
        if self.claims is None:
            raise PermissionError("selected immutable Claim observation lacks its actual owner")
        key = self.claims._row_id(identifier)
        self._bindings()
        row = self.claims._fetch_record(table=table, row_id=key, all_valid=True)
        self._bindings()
        columns = ("_id", "scope_digest", digest_column, "record_json")
        primitive = _primitive_columns(row, columns)
        record = json.loads(row["record_json"])
        if (row["_id"] != key or row["scope_digest"] != self.claims.scope_digest
                or canonical_json_bytes(record) != expected
                or record.get(digest_column) != row[digest_column]):
            raise PermissionError("selected immutable Claim authority changed before its terminal fence")
        identity = table, key, digest_column
        if identity in self._claim_rows and self._claim_rows[identity] != primitive:
            raise PermissionError("selected immutable Claim observation changed during this guard")
        if (len(self._observations) + len(self._state_rows) + len(self._claim_rows)
                + int(identity not in self._claim_rows) > self.maximum_rows):
            raise PermissionError("selected Claim/source/state fence exceeds its explicit row cap")
        self._claim_rows[identity] = primitive
        self._bindings()

    def observe_claim_authorities(self, authorities):
        """Observe immutable exact versions/relations captured with context."""
        for captured in authorities:
            self._observe_claim(table=claim_tables._VERSIONS, identifier=captured.version_id,
                digest_column="version_sha256", expected=captured.version_record)
            for relation_id, material in captured.evidence_records:
                self._observe_claim(table=claim_tables._EVIDENCE, identifier=relation_id,
                    digest_column="relation_sha256", expected=material)
        self._bindings()

    def observe_claim_nominations(self, nominations):
        """Observe initial exact Claim versions/relations before private I/O."""
        for _, material in nominations:
            version = material["version"]
            self._observe_claim(table=claim_tables._VERSIONS, identifier=version["claim_version_id"],
                digest_column="version_sha256", expected=canonical_json_bytes(version))
            for relation_id, record in material["relations"]:
                self._observe_claim(table=claim_tables._EVIDENCE, identifier=relation_id,
                    digest_column="relation_sha256", expected=canonical_json_bytes(record))
        self._bindings()

    def observe_state_authorities(self, state, authorities):
        """Bind the exact state metadata captured with the held private context."""
        if state is not self.state:
            raise PermissionError("selected state observation replaced its actual owner")
        for captured in authorities:
            route = captured.route
            self._observe(table=_ACTIVE, key=state._head_id(route.subject_type, route.subject_id, route.projection_id),
                immutable=False, expected=json.loads(captured.head_record), columns=_HEAD)
            self._observe(table=_VERSIONS, key=state._version_id(captured.version_id),
                immutable=True, expected=json.loads(captured.version_row), columns=_VERSION)
            self._observe(table=_HISTORY, key=state._history_key(route.projection_id, captured.version_id),
                immutable=True, expected=captured.activation_record, columns=_RECEIPT, record=True)
            for table, key, material in captured.rollback_records:
                self._observe(table=table, key=key, immutable=True, expected=material, columns=_RECEIPT, record=True)
            for version_id, material in captured.rollback_version_rows:
                self._observe(table=_VERSIONS, key=state._version_id(version_id), immutable=True,
                    expected=json.loads(material), columns=_VERSION)
            for projection_id, version_id, material in captured.rollback_activation_records:
                self._observe(table=_HISTORY, key=state._history_key(projection_id, version_id),
                    immutable=True, expected=material, columns=_RECEIPT, record=True)
        self._bindings()

    def observe_state_nominations(self, state, nominations):
        """Bind initial exact nominations before any private assembly callbacks."""
        if state is not self.state:
            raise PermissionError("selected state nomination replaced its actual owner")
        for material in nominations:
            route, head = material["route"], material["head"]
            projection, version_id = route["projection_id"], head["version_id"]
            self._observe(table=_ACTIVE, key=state._head_id(route["subject_type"], route["subject_id"], projection),
                immutable=False, expected=head, columns=_HEAD)
            self._observe(table=_VERSIONS, key=state._version_id(version_id),
                immutable=True, expected=material["version"], columns=_VERSION)
            self._observe(table=_HISTORY, key=state._history_key(projection, version_id), immutable=True,
                expected=canonical_json_bytes(material["activation"]), columns=_RECEIPT, record=True)
            if "rollback" in material:
                rollback = material["rollback"]
                binding = rollback["binding"]
                from .governed_development import _ROLLBACKS, _ROLLBACK_IDS
                self._observe(table=_ROLLBACKS, key=state._rollback_key(version_id), immutable=True,
                    expected=canonical_json_bytes(binding), columns=_RECEIPT, record=True)
                self._observe(table=_ROLLBACK_IDS, key=state._rollback_id_key(binding["rollback_id"]), immutable=True,
                    expected=canonical_json_bytes(rollback["action"]), columns=_RECEIPT, record=True)
                target_id = binding["target_version_id"]
                self._observe(table=_VERSIONS, key=state._version_id(target_id), immutable=True,
                    expected=rollback["target"], columns=_VERSION)
                self._observe(table=_HISTORY, key=state._history_key(projection, target_id), immutable=True,
                    expected=canonical_json_bytes(rollback["target_activation"]), columns=_RECEIPT, record=True)
        self._bindings()

    def verify_final_current_rows(self):
        """One source/grant/Claim/state statement followed by primitive checks."""
        self._bindings()
        terms, parameters, expected = [], [], {}
        for item in self._observations.values():
            if (any(type(value) is not str for value in (item.kind, item.table, item.key,
                    item.scope_digest, item.digest_column, item.digest))
                    or type(item.immutable) is not bool):
                raise PermissionError("selected context terminal observation is not primitive")
            row = self._sampled_rows[(item.kind, item.table, item.key, item.immutable)]
            if type(row["record_json"]) is not str:
                raise PermissionError("selected context terminal needs exact record_json text")
            tag = item.kind + ":" + item.table + (":all" if item.immutable else ":current")
            temporal = " FOR VALID_TIME ALL" if item.immutable else ""
            extras = ", ".join(f"CAST(NULL AS {'BIGINT' if name in _NUMBERS else 'TEXT'}) AS {name}" for name in _EXTRA)
            terms.append(f"SELECT '{tag}' AS fence_kind, _id, scope_digest, {item.digest_column} AS fence_sha256, "
                f"record_json, {extras} FROM {item.table}{temporal} WHERE scope_digest = %s AND _id = %s::text")
            parameters.extend((item.scope_digest, item.key))
            expected[tag, item.key] = (tag, item.key, item.scope_digest, item.digest, row["record_json"], *(None for _ in _EXTRA))
        for (table, key, immutable), (columns, primitive) in self._state_rows.items():
            row = dict(zip(columns, primitive))
            tag, temporal = "state:" + table + (":all" if immutable else ":current"), " FOR VALID_TIME ALL" if immutable else ""
            digest = "projection_sha256" if table in (_ACTIVE, _VERSIONS) else "record_sha256"
            json_column = "record_json" if table != _ACTIVE else "CAST(NULL AS TEXT) AS record_json"
            extras = ", ".join(name if name in columns else f"CAST(NULL AS {'BIGINT' if name in _NUMBERS else 'TEXT'}) AS {name}" for name in _EXTRA)
            terms.append(f"SELECT '{tag}' AS fence_kind, _id, scope_digest, {digest} AS fence_sha256, "
                f"{json_column}, {extras} FROM {table}{temporal} WHERE scope_digest = %s AND _id = %s::text")
            parameters.extend((self._state_scope_digest, key))
            expected[tag, key] = (tag, key, row["scope_digest"], row[digest], row.get("record_json"), *(row.get(name) for name in _EXTRA))
        for (table, key, digest), primitive in self._claim_rows.items():
            tag = "claim-immutable:" + table + ":all"
            extras = ", ".join(f"CAST(NULL AS {'BIGINT' if name in _NUMBERS else 'TEXT'}) AS {name}" for name in _EXTRA)
            terms.append(f"SELECT '{tag}' AS fence_kind, _id, scope_digest, {digest} AS fence_sha256, "
                f"record_json, {extras} FROM {table} FOR VALID_TIME ALL WHERE scope_digest = %s AND _id = %s::text")
            parameters.extend((primitive[1], key))
            expected[tag, key] = (tag, *primitive, *(None for _ in _EXTRA))
        if not expected or len(expected) > self.maximum_rows:
            raise PermissionError("selected context terminal has an empty or oversized row domain")
        sql = "SELECT * FROM (" + " UNION ALL ".join(terms) + f") AS flora_selected_context_fence LIMIT {len(expected) + 1}"
        self._bindings()
        cursor = self.connection.execute(sql, tuple(parameters))
        self._bindings()
        rows = _terminal_rows(cursor, self._bindings)
        self._bindings()
        if len(rows) != len(expected):
            raise PermissionError("terminal selected context has missing/ambiguous authority rows")
        seen = set()
        for row in rows:
            if (type(row) is not dict or any(type(name) is not str for name in row)
                    or any(name not in row for name in _RESULT)):
                raise PermissionError("terminal selected context returned nonprimitive authority columns")
            values = tuple(row[name] for name in _RESULT)
            if any(value is not None and type(value) is not str and type(value) is not int for value in values):
                raise PermissionError("terminal selected context returned nonnative metadata")
            key = row["fence_kind"], row["_id"]
            if type(key[0]) is not str or type(key[1]) is not str or key in seen or key not in expected:
                raise PermissionError("terminal selected context has unexpected/duplicate authority rows")
            seen.add(key)
            if values != expected[key]:
                raise PermissionError("terminal selected context authority changed after callbacks")
        self._bindings()


def _require_fence_code():
    for name, value, code in _EXTERNAL:
        if globals().get(name) is not value or (code is not None and value.__code__ is not code):
            raise PermissionError("selected context terminal external helper changed")
    for name, function, code in _PURE:
        if globals().get(name) is not function or function.__code__ is not code:
            raise PermissionError("selected context terminal pure helper changed")
    current = vars(SelectedContextMetadataSample)
    extra = "__slotnames__" not in dict(_SHAPE) and "__slotnames__" in current
    if (len(current) != len(_SHAPE) + int(extra)
            or any(current.get(name) is not value for name, value in _SHAPE)
            or extra and (type(current["__slotnames__"]) is not list or current["__slotnames__"])):
        raise PermissionError("selected context terminal class binding changed")
    if any(function.__code__ is not code for function, code in _CODES):
        raise PermissionError("selected context terminal class code changed")


_PURE = tuple((function.__name__, function, function.__code__) for function in (
    _primitive_columns, _terminal_rows, _require_fence_code))
_SHAPE = tuple(vars(SelectedContextMetadataSample).items())
_CODES = tuple((value, value.__code__) for _, value in _SHAPE if isinstance(value, FunctionType))
_EXTERNAL = tuple((name, value, value.__code__ if isinstance(value, FunctionType) else None)
    for name, value in (("_native_snapshot", _native_snapshot),
                       ("_ReaderBinding", _ReaderBinding), ("_ClosureMetadataSample", _ClosureMetadataSample)))
