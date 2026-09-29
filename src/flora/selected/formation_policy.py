"""Durable XTDB source-use authority for registered formation evidence.

An immutable action binds a real Kurrent event, its encrypted request, the exact
source registration and an independently verified authorization. The latest
scoped decision controls use; valid-time history never restores permission.
RegisteredFormationStore calls this policy before and after custody reads.

This is a formation-use barrier for sources and their registered parent closure.
It is not raw erasure, derivative invalidation, execution-state rewind, or model
unlearning. Those cross-layer influence operations remain separate work.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from typing import Any, Mapping, Protocol

from cognitive_kernel.canonical import (
    canonical_json_bytes, canonical_sha256, normalize_timestamp,
    require_identifier, require_sha256,
)
from cognitive_kernel.contracts import ProductHostScope
from cognitive_kernel.experience import ExperienceEvent
from cognitive_kernel.formation_sources import RegisteredFormationSource

from .claims import _dml_placeholder, _record_json, _rows, configure_xtdb_connection
from .experience import KurrentExperienceLog
from .formation_registry import XTDBFormationSourceRegistry
from .object_store import EncryptedObjectPlane, RawObjectReference

_ACTIONS = "flora_formation_permission_actions"
_CURRENT = "flora_formation_permission_current"


@dataclass(frozen=True)
class FormationPermissionAction:
    scope: ProductHostScope
    authority_namespace_id: str
    action_id: str
    source_ref_id: str
    source_registration_sha256: str
    purpose: str
    decision: str
    generation: int
    previous_action_sha256: str | None
    authorization_ref: str
    authorized_at: str
    action_sha256: str

    @classmethod
    def create(cls, **values: Any) -> "FormationPermissionAction":
        material = dict(values)
        for name in ("authority_namespace_id", "action_id", "source_ref_id",
                     "purpose", "authorization_ref"):
            material[name] = require_identifier(material[name], name)
        material["source_registration_sha256"] = require_sha256(
            material["source_registration_sha256"], "source_registration_sha256")
        if material["previous_action_sha256"] is not None:
            material["previous_action_sha256"] = require_sha256(
                material["previous_action_sha256"], "previous_action_sha256")
        material["authorized_at"] = normalize_timestamp(material["authorized_at"], "authorized_at")
        draft = cls(**material, action_sha256="0" * 64)
        draft._validate_material()
        result = replace(draft, action_sha256=canonical_sha256(draft.material_record()))
        result.validate()
        return result

    def _validate_material(self) -> None:
        self.scope.validate()
        for value, name in (
            (self.authority_namespace_id, "authority_namespace_id"),
            (self.action_id, "action_id"), (self.source_ref_id, "source_ref_id"),
            (self.purpose, "purpose"), (self.authorization_ref, "authorization_ref"),
        ):
            if require_identifier(value, name) != value:
                raise ValueError(f"{name} must be canonical")
        if require_sha256(self.source_registration_sha256,
                          "source_registration_sha256") != self.source_registration_sha256:
            raise ValueError("source registration digest must be canonical")
        if self.decision not in {"allow", "deny", "revoke"}:
            raise ValueError("unknown formation permission decision")
        if (isinstance(self.generation, bool) or not isinstance(self.generation, int)
                or self.generation < 1):
            raise ValueError("permission generation must be positive")
        if self.previous_action_sha256 is not None and require_sha256(
            self.previous_action_sha256, "previous_action_sha256"
        ) != self.previous_action_sha256:
            raise ValueError("previous action digest must be canonical")
        if ((self.generation == 1) != (self.previous_action_sha256 is None)):
            raise ValueError("permission generation does not bind its predecessor")
        if normalize_timestamp(self.authorized_at, "authorized_at") != self.authorized_at:
            raise ValueError("permission authorization time must be canonical")

    def material_record(self) -> dict[str, object]:
        self._validate_material()
        return {
            "schema": "flora-formation-permission-action-v1",
            "scope": self.scope.metadata_record(),
            "authority_namespace_id": self.authority_namespace_id,
            "action_id": self.action_id, "source_ref_id": self.source_ref_id,
            "source_registration_sha256": self.source_registration_sha256,
            "purpose": self.purpose, "decision": self.decision,
            "generation": self.generation,
            "previous_action_sha256": self.previous_action_sha256,
            "authorization_ref": self.authorization_ref,
            "authorized_at": self.authorized_at,
        }

    def metadata_record(self) -> dict[str, object]:
        return {**self.material_record(), "action_sha256": self.action_sha256}

    def validate(self) -> None:
        self._validate_material()
        if (require_sha256(self.action_sha256, "action_sha256") != self.action_sha256
                or canonical_sha256(self.material_record()) != self.action_sha256):
            raise ValueError("formation permission action digest changed")


def formation_permission_payload(action: FormationPermissionAction) -> bytes:
    """Exact encrypted request material to append before applying authority."""
    action.validate()
    return canonical_json_bytes(action.metadata_record())


class FormationPermissionVerifier(Protocol):
    """Trusted authorization service; a recorded event alone cannot authorize."""

    def authorized_action(self, action: FormationPermissionAction,
                          source: RegisteredFormationSource,
                          event: ExperienceEvent) -> bool: ...


def _action_from_record(record: dict[str, object]) -> FormationPermissionAction:
    if record.get("schema") != "flora-formation-permission-action-v1":
        raise ValueError("formation permission action schema changed")
    values = {key: value for key, value in record.items() if key != "schema"}
    values["scope"] = ProductHostScope.create(**values["scope"])
    action = FormationPermissionAction(**values)
    action.validate()
    if action.metadata_record() != record:
        raise ValueError("formation permission action metadata is not canonical")
    return action


class XTDBFormationPermissionPolicy:
    """Scoped immutable permission actions and an immediately current use head.

    Missing or malformed authority denies use. The policy holds no positive
    permission cache. An initial grant and every change require independent
    authorization; the model can only propose a change elsewhere.
    """

    def __init__(self, *, scope: ProductHostScope, authority_namespace_id: str,
                 connection: Any, registry: XTDBFormationSourceRegistry):
        scope.validate()
        namespace = require_identifier(authority_namespace_id, "authority_namespace_id")
        if namespace != authority_namespace_id:
            raise ValueError("permission authority namespace must be canonical")
        if (registry.scope != scope or registry.authority_namespace_id != namespace):
            raise ValueError("permission registry crosses scope or authority")
        self.scope, self.authority_namespace_id = scope, namespace
        self.connection, self.registry = connection, registry
        configure_xtdb_connection(connection)
        self.scope_digest = hashlib.sha256(
            f"{scope.storage_scope()}:{namespace}".encode()).hexdigest()

    def _key(self, kind: str, *identifiers: str) -> str:
        for identifier in identifiers:
            if require_identifier(identifier, kind) != identifier:
                raise ValueError(f"{kind} identifier must be canonical")
        return canonical_sha256([self.scope_digest, kind, *identifiers])

    def _fetch(self, table: str, key: str, *, immutable: bool) -> dict[str, object] | None:
        valid = " FOR VALID_TIME ALL" if immutable else ""
        rows = _rows(self.connection.execute(
            f"SELECT * FROM {table}{valid} WHERE _id = %s", (key,)))
        if len(rows) > 1:
            raise ValueError("formation permission authority returned ambiguous rows")
        return rows[0] if rows else None

    def _decode(self, row: dict[str, object], *, key: str) -> dict[str, object]:
        record = json.loads(str(row["record_json"]))
        if (row["_id"] != key or row["scope_digest"] != self.scope_digest
                or record["scope"] != self.scope.metadata_record()
                or record["authority_namespace_id"] != self.authority_namespace_id
                or record["record_sha256"] != row["record_sha256"]
                or canonical_sha256({name: value for name, value in record.items()
                                     if name != "record_sha256"}) != row["record_sha256"]):
            raise ValueError("formation permission authority metadata changed")
        return record

    def _insert(self, table: str, key: str, record: dict[str, object]) -> None:
        values = {"_id": key, "scope_digest": self.scope_digest,
                  "record_sha256": record["record_sha256"],
                  "record_json": _record_json(record)}
        self.connection.execute(
            f"INSERT INTO {table} ({', '.join(values)}) VALUES ("
            + ", ".join(_dml_placeholder(value) for value in values.values()) + ")",
            tuple(values.values()))

    def _stored_action(self, action_id: str) -> dict[str, object] | None:
        key = self._key("action", action_id)
        row = self._fetch(_ACTIONS, key, immutable=True)
        if row is None:
            return None
        record = self._decode(row, key=key)
        if record.get("schema") != "flora-recorded-formation-permission-v1":
            raise ValueError("recorded permission action schema changed")
        action = _action_from_record(record["action"])
        if (action.action_id != action_id or action.scope != self.scope
                or action.authority_namespace_id != self.authority_namespace_id):
            raise ValueError("recorded permission action differs from its lookup")
        require_identifier(record["request_event_id"], "request_event_id")
        require_sha256(record["request_event_sha256"], "request_event_sha256")
        require_sha256(record["request_payload_sha256"], "request_payload_sha256")
        if (isinstance(record["event_stream_position"], bool)
                or not isinstance(record["event_stream_position"], int)
                or record["event_stream_position"] < 0):
            raise ValueError("recorded permission has invalid stream position")
        if record["request_payload_sha256"] != hashlib.sha256(
                formation_permission_payload(action)).hexdigest():
            raise ValueError("recorded permission no longer binds its exact request")
        return record

    def _head(self, source_ref_id: str, purpose: str) -> dict[str, object] | None:
        key = self._key("head", source_ref_id, purpose)
        row = self._fetch(_CURRENT, key, immutable=False)
        if row is None:
            return None
        record = self._decode(row, key=key)
        if (record.get("schema") != "flora-current-formation-permission-v1"
                or record["source_ref_id"] != source_ref_id or record["purpose"] != purpose):
            raise ValueError("permission head differs from its exact lookup")
        action_record = self._stored_action(record["action_id"])
        if action_record is None:
            raise ValueError("permission head lacks an immutable authorized action")
        action = _action_from_record(action_record["action"])
        if (action.source_ref_id != source_ref_id or action.purpose != purpose
                or action.action_sha256 != record["action_sha256"]
                or action.generation != record["generation"]):
            raise ValueError("permission head differs from its immutable action")
        return record

    def current_action(self, source_ref_id: str, purpose: str) -> FormationPermissionAction | None:
        head = self._head(source_ref_id, purpose)
        if head is None:
            return None
        return _action_from_record(self._stored_action(head["action_id"])["action"])

    def apply(self, action: FormationPermissionAction, *, request_event_id: str,
              log: KurrentExperienceLog, objects: EncryptedObjectPlane,
              references: Mapping[str, RawObjectReference],
              verifier: FormationPermissionVerifier) -> FormationPermissionAction:
        """Apply verified authority after event append, with exact retry safety.

        Kurrent append and XTDB update are separate commits. A recorded request
        grants nothing until this verified CAS succeeds. After failure, retry
        the same action/event; reusing a recorded old grant cannot restore it
        over a newer denial. Head-loss repair is not inferred from an old grant.
        """
        action.validate()
        if (not self.scope == action.scope == log.scope == objects.scope
                or action.authority_namespace_id != self.authority_namespace_id):
            raise ValueError("permission action crosses scope or authority")
        source = self.registry.lookup(action.source_ref_id)
        if source is None:
            raise ValueError("permission action has no registered original source")
        source.validate()
        if (source.evidence.scope != self.scope
                or source.evidence.authority_namespace_id != self.authority_namespace_id
                or source.evidence.ref_id != action.source_ref_id
                or source.registration_sha256 != action.source_registration_sha256):
            raise ValueError("permission action does not bind its registered source")
        events = log.replay()
        located = {event.event_id: (position, event) for position, event in enumerate(events)}
        request = located.get(request_event_id)
        original = located.get(action.source_ref_id)
        if request is None or original is None:
            raise ValueError("permission action lacks replayed request or source")
        position, event = request
        event.validate()
        if (event.scope != self.scope or event.event_type != "formation_permission_action"
                or event.payload_reference is None
                or event.occurred_at != action.authorized_at
                or action.source_ref_id not in event.parent_event_ids
                or original[0] >= position
                or original[1].scope != self.scope
                or original[1].content_digest != source.evidence.content_digest):
            raise ValueError("permission action is not bound to its original Experience")
        payload = formation_permission_payload(action)
        raw = references.get(event.payload_reference)
        if (raw is None or raw.scope != self.scope or raw.object_id != event.payload_reference
                or objects.get(raw) != payload
                or event.content_digest != hashlib.sha256(payload).hexdigest()):
            raise ValueError("permission action differs from its encrypted raw request")
        if verifier is None or verifier.authorized_action(action, source, event) is not True:
            raise ValueError("permission action is not independently authorized")

        action_key = self._key("action", action.action_id)
        recorded: dict[str, object] = {
            "schema": "flora-recorded-formation-permission-v1",
            "scope": self.scope.metadata_record(),
            "authority_namespace_id": self.authority_namespace_id,
            "action": action.metadata_record(), "request_event_id": event.event_id,
            "request_event_sha256": event.event_sha256,
            "request_payload_sha256": event.content_digest,
            "event_stream_position": position,
        }
        recorded["record_sha256"] = canonical_sha256(recorded)
        prior_recorded = self._stored_action(action.action_id)
        head = self._head(action.source_ref_id, action.purpose)
        if prior_recorded is not None:
            if prior_recorded != recorded:
                raise ValueError("formation permission action identifier is immutable")
            if head is None:
                raise ValueError("recorded permission head is absent; explicit recovery required")
            # An exact old-action retry is a no-op even when a later denial won.
            return action

        if head is None:
            if action.generation != 1 or action.previous_action_sha256 is not None:
                raise ValueError("permission predecessor is absent")
        else:
            prior = self._stored_action(head["action_id"])
            previous = _action_from_record(prior["action"])
            if (action.previous_action_sha256 != previous.action_sha256
                    or action.generation != previous.generation + 1
                    or action.source_registration_sha256 != previous.source_registration_sha256
                    or action.authorized_at < previous.authorized_at
                    or prior["event_stream_position"] >= position
                    or prior["request_event_id"] not in event.parent_event_ids):
                raise ValueError("stale or unbound permission predecessor")
        current: dict[str, object] = {
            "schema": "flora-current-formation-permission-v1",
            "scope": self.scope.metadata_record(),
            "authority_namespace_id": self.authority_namespace_id,
            "source_ref_id": action.source_ref_id, "purpose": action.purpose,
            "action_id": action.action_id, "action_sha256": action.action_sha256,
            "generation": action.generation,
        }
        current["record_sha256"] = canonical_sha256(current)
        head_key = self._key("head", action.source_ref_id, action.purpose)
        with self.connection.transaction():
            self.connection.execute(
                f"ASSERT NOT EXISTS (SELECT 1 FROM {_ACTIONS} FOR VALID_TIME ALL WHERE _id = %s::text)",
                (action_key,))
            if head is None:
                self.connection.execute(
                    f"ASSERT NOT EXISTS (SELECT 1 FROM {_CURRENT} WHERE _id = %s::text)",
                    (head_key,))
            else:
                self.connection.execute(
                    f"ASSERT EXISTS (SELECT 1 FROM {_CURRENT} WHERE _id = %s::text "
                    "AND record_sha256 = %s::text)",
                    (head_key, head["record_sha256"]))
            self._insert(_ACTIONS, action_key, recorded)
            self._insert(_CURRENT, head_key, current)
        return action

    def permits(self, source: RegisteredFormationSource, purpose: str) -> bool:
        """Freshly resolve current permission for the source and all parents."""
        source.validate()
        if (source.evidence.scope != self.scope
                or source.evidence.authority_namespace_id != self.authority_namespace_id):
            return False
        if require_identifier(purpose, "purpose") != purpose:
            return False
        if self.registry.lookup(source.evidence.ref_id) != source:
            return False
        state: dict[str, int] = {}
        resolved: dict[str, tuple[RegisteredFormationSource, str]] = {}
        # Iterative closure avoids a Python recursion limit on long histories.
        pending: list[tuple[str, bool]] = [(source.evidence.ref_id, False)]
        while pending:
            ref_id, completed = pending.pop()
            if completed:
                state[ref_id] = 2
                continue
            if state.get(ref_id) == 2:
                continue
            if state.get(ref_id) == 1:
                return False
            registered = self.registry.lookup(ref_id)
            if registered is None:
                return False
            registered.validate()
            evidence = registered.evidence
            if (evidence.ref_id != ref_id or evidence.scope != self.scope
                    or evidence.authority_namespace_id != self.authority_namespace_id):
                return False
            action = self.current_action(ref_id, purpose)
            if (action is None or action.decision != "allow"
                    or action.source_registration_sha256 != registered.registration_sha256):
                return False
            state[ref_id] = 1
            resolved[ref_id] = (registered, action.action_sha256)
            pending.append((ref_id, True))
            for parent in reversed(evidence.parent_refs):
                if state.get(parent) == 1:
                    return False
                if state.get(parent) != 2:
                    pending.append((parent, False))
        # Detect a registration/permission change during closure traversal.
        # RegisteredFormationStore additionally repeats this check after I/O.
        for ref_id, (registered, action_digest) in resolved.items():
            current = self.current_action(ref_id, purpose)
            if (self.registry.lookup(ref_id) != registered or current is None
                    or current.decision != "allow" or current.action_sha256 != action_digest):
                return False
        return True
