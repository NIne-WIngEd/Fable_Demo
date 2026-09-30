"""One selected metadata guard and a finite terminal XTDB current-row fence.

Sampled rows exist only inside one call. Actual policy callbacks still run;
their answers are never cached. The last SQL statement observes all sampled
authority rows together after those callbacks, including mutable permission
heads and Claim quarantine. It grants no lease after that query's snapshot.
"""
from __future__ import annotations

from copy import copy, deepcopy
from dataclasses import dataclass
import json

from cognitive_kernel.canonical import canonical_json_bytes, require_identifier

from . import claims as claim_tables
from . import formation_policy as permission_tables
from . import formation_registry as source_tables
from .claims import XTDBClaimAuthority, _rows
from .formation_policy import XTDBFormationPermissionPolicy
from .formation_registry import XTDBFormationSourceRegistry
from .judgment_context import RegisteredJudgmentContextPolicy
from .source_native import _require_available


@dataclass(frozen=True)
class _Row:
    kind: str
    table: str
    key: str
    immutable: bool
    scope_digest: str
    digest_column: str
    record: bytes
    digest: str


class OneGuardSelectedMetadata:
    """Actual same-connection row observations; never a positive authority cache.

    Callers must run their actual authority predicates and immutable/source
    checks before ``verify_final_current_rows``. This helper only checks that
    their sampled rows remain exact in one terminal selected-engine statement.
    It neither authenticates private objects nor authorizes a source by itself.
    """
    def __init__(self, *, registry, permissions, claims=None, maximum_rows=4096):
        if (not isinstance(registry, XTDBFormationSourceRegistry)
                or not isinstance(permissions, XTDBFormationPermissionPolicy)
                or (claims is not None and not isinstance(claims, XTDBClaimAuthority))):
            raise TypeError("metadata fence needs actual selected services")
        if (isinstance(maximum_rows, bool) or not isinstance(maximum_rows, int)
                or maximum_rows < 1):
            raise ValueError("metadata fence needs an explicit positive row cap")
        self.registry, self.permissions, self.claims = registry, permissions, claims
        self.connection, self.maximum_rows = registry.connection, maximum_rows
        self.scope_record = canonical_json_bytes(registry.scope.metadata_record())
        self.namespace = registry.authority_namespace_id
        self._observations = {}
        self._methods = [(registry, name, getattr(registry, name))
            for name in ("_fetch", "lookup", "raw_metadata", "raw_reference")]
        self._methods += [(permissions, name, getattr(permissions, name))
            for name in ("_fetch", "permits", "current_action", "_head", "_stored_action")]
        if claims is not None:
            self._methods += [(claims, name, getattr(claims, name))
                for name in ("_fetch_record", "load_current")]
        self._bindings()
        self.local_registry = self._sample(registry, "registry")
        self.local_permissions = self._sample(permissions, "permission")
        self.local_permissions.registry = self.local_registry
        self.local_claims = None if claims is None else self._sample(claims, "claim")

    def _bindings(self):
        if any(getattr(service, name) != method for service, name, method in self._methods):
            raise PermissionError("metadata fence actual reader/predicate binding changed")
        if (self.registry.connection is not self.connection
                or self.permissions.connection is not self.connection
                or self.permissions.registry is not self.registry
                or canonical_json_bytes(self.registry.scope.metadata_record()) != self.scope_record
                or self.permissions.scope != self.registry.scope
                or self.registry.authority_namespace_id != self.namespace
                or self.permissions.authority_namespace_id != self.namespace):
            raise PermissionError("metadata fence actual scoped services changed")
        if self.claims is not None and (
                self.claims.connection is not self.connection
                or self.claims.scope != self.registry.scope
                or self.claims.authority_namespace_id != self.namespace):
            raise PermissionError("metadata fence Claim authority crosses actual selected connection/scope")

    def _sample(self, service, kind):
        local = copy(service)
        name = "_fetch_record" if kind == "claim" else "_fetch"
        actual = getattr(local, name)
        sampled = {}
        def fetch(*args, **kwargs):
            cache_key = (args, tuple(sorted(kwargs.items())))
            if cache_key not in sampled:
                self._bindings()
                row = actual(*args, **kwargs)
                sampled[cache_key] = deepcopy(row)
                if kind == "claim":
                    table, key = kwargs["table"], kwargs["row_id"]
                    if kwargs.get("valid_time") is not None:
                        raise PermissionError("terminal metadata fence cannot substitute a historical current Claim")
                    immutable = kwargs.get("all_valid", False)
                    allowed = {claim_tables._CURRENT, claim_tables._HEAD}
                    digest_column = "projection_sha256"
                else:
                    table, key = args[:2]
                    immutable = True if kind == "registry" else kwargs["immutable"]
                    allowed = ({source_tables._SOURCES, source_tables._OBJECTS} if kind == "registry"
                               else {permission_tables._ACTIONS, permission_tables._CURRENT})
                    digest_column = "record_sha256"
                if table not in allowed:
                    raise PermissionError("metadata fence cannot sample an undeclared table")
                identity = (kind, table, key, immutable)
                if row is None:
                    raise PermissionError("metadata fence source/authority row is absent")
                record = json.loads(str(row["record_json"]))
                envelope = record.get("envelope", {})
                if (row["_id"] != key or row["scope_digest"] != service.scope_digest
                        or canonical_json_bytes(record.get("scope", envelope.get("scope"))) != self.scope_record
                        or record.get("authority_namespace_id", envelope.get("authority_namespace_id")) != self.namespace):
                    raise PermissionError("metadata fence row crosses exact key/scope")
                observation = _Row(kind, table, key, immutable, service.scope_digest,
                    digest_column, canonical_json_bytes(record), row[digest_column])
                if identity in self._observations and self._observations[identity] != observation:
                    raise PermissionError("metadata fence sampled row changed during this guard")
                self._observations[identity] = observation
                if len(self._observations) > self.maximum_rows:
                    raise PermissionError("metadata fence exceeds its explicit finite row cap")
            return deepcopy(sampled[cache_key])
        setattr(local, name, fetch)
        return local

    def observe_source(self, event_id, purpose):
        """Bind all real source/raw/action/head rows even with patched predicates."""
        source = self.local_registry.lookup(event_id)
        if source is None:
            raise PermissionError("metadata fence source is absent")
        action = self.local_permissions.current_action(event_id, purpose)
        # An instance callback may use the original service rather than this
        # copy. Preserve it, then independently sample the actual scoped rows.
        head = self.local_permissions._head(event_id, purpose)
        if (action is None or action.decision != "allow" or head is None
                or action.source_registration_sha256 != source.registration_sha256
                or action.action_sha256 != head["action_sha256"]):
            raise PermissionError("metadata fence current source grant was withdrawn or changed")
        stored = self.local_permissions._stored_action(head["action_id"])
        if stored is None or stored["action"] != action.metadata_record():
            raise PermissionError("metadata fence callback differs from its actual immutable authorized action")
        return source, action

    def verify_final_current_rows(self):
        """One actual statement after callbacks; no subsequent authority callback."""
        self._bindings()
        if not self._observations:
            raise PermissionError("terminal metadata fence has no actual observed rows")
        grouped = {}
        for observation in self._observations.values():
            group = (observation.kind, observation.table, observation.immutable,
                     observation.scope_digest, observation.digest_column)
            grouped.setdefault(group, []).append(observation)
        terms, parameters, expected = [], [], {}
        for (kind, table, immutable, scope_digest, column), observations in sorted(grouped.items()):
            tag = kind + ":" + table + (":all" if immutable else ":current")
            keys = sorted(item.key for item in observations)
            temporal = " FOR VALID_TIME ALL" if immutable else ""
            terms.append(f"SELECT '{tag}' AS fence_kind, _id, scope_digest, "
                f"{column} AS fence_sha256, record_json FROM {table}{temporal} "
                "WHERE scope_digest = %s AND _id IN (" + ", ".join("%s::text" for _ in keys) + ")")
            parameters.extend((scope_digest, *keys))
            for item in observations:
                expected[(tag, item.key)] = item
        # A bounded count also detects ambiguous valid-time versions. The
        # statement's single XTDB basis covers all terms, including heads.
        sql = "SELECT * FROM (" + " UNION ALL ".join(terms) + ") AS flora_current_metadata_fence LIMIT %s::bigint"
        parameters.append(self.maximum_rows + 1)
        values = _rows(self.connection.execute(sql, tuple(parameters)))
        if len(values) != len(expected):
            raise PermissionError("terminal current metadata fence has missing/ambiguous rows")
        seen = set()
        for row in values:
            key = (row.get("fence_kind"), row.get("_id"))
            item = expected.get(key)
            if item is None or key in seen:
                raise PermissionError("terminal current metadata fence has unexpected/duplicate rows")
            seen.add(key)
            if (row.get("scope_digest") != item.scope_digest
                    or row.get("fence_sha256") != item.digest
                    or canonical_json_bytes(json.loads(str(row.get("record_json")))) != item.record):
                raise PermissionError("terminal current source/grant/Claim metadata changed")
        self._bindings()  # Pure service identity/scope comparison, no I/O.


def verify_current_phase_sources(*, policy, source_event_ids, claim_ids=(),
                                 authority_guard=None, maximum_rows=4096):
    """Current archive/original closure with one finite terminal authority fence."""
    if not isinstance(policy, RegisteredJudgmentContextPolicy):
        raise TypeError("phase source fence needs actual registered judgment policy")
    if policy.purpose != "personal_judgment":
        raise PermissionError("phase source fence cannot replace its personal-judgment purpose")
    if not isinstance(source_event_ids, tuple) or not isinstance(claim_ids, tuple):
        raise TypeError("phase source fence needs explicit finite tuples")
    if (not source_event_ids or len(set(source_event_ids)) != len(source_event_ids)
            or len(set(claim_ids)) != len(claim_ids)
            or len(source_event_ids) + len(claim_ids) > maximum_rows):
        raise PermissionError("phase source fence has empty/duplicate/oversized nominations")
    for identifier in (*source_event_ids, *claim_ids):
        if require_identifier(identifier, "phase metadata ID") != identifier:
            raise PermissionError("phase source fence ID is noncanonical")
    if authority_guard is not None and not callable(authority_guard):
        raise TypeError("phase authority guard must be callable")
    registry, permissions, claims, state, log = policy.registry, policy.permissions, policy.claims, policy.state, policy.log
    source_predicate, permission_predicate, purpose = policy.allow_event, permissions.permits, policy.purpose
    sample = OneGuardSelectedMetadata(registry=registry, permissions=permissions,
        claims=claims, maximum_rows=maximum_rows)
    def bindings():
        sample._bindings()
        if (policy.registry is not registry or policy.permissions is not permissions
                or policy.claims is not claims or policy.state is not state or policy.log is not log
                or policy.allow_event != source_predicate or permissions.permits != permission_predicate
                or policy.purpose != purpose
                or state.registry is not registry or state.policy is not permissions
                or log.scope != registry.scope):
            raise PermissionError("phase actual policy/control service binding changed")
    bindings()
    if authority_guard is not None:
        authority_guard()
    events = tuple(log.replay())
    by_id = {event.event_id: event for event in events}
    if len(by_id) != len(events):
        raise PermissionError("phase canonical events are ambiguous")
    local_log, local_state, local_policy = copy(log), copy(state), copy(policy)
    local_log.replay = lambda: list(events)
    local_state.registry, local_state.policy = sample.local_registry, sample.local_permissions
    local_policy.registry, local_policy.permissions = sample.local_registry, sample.local_permissions
    local_policy.claims, local_policy.state, local_policy.log = sample.local_claims, local_state, local_log
    captured, pending = {}, list(source_event_ids)
    while pending:
        event_id = pending.pop()
        if event_id in captured:
            continue
        source, _ = sample.observe_source(event_id, policy.purpose)
        event = by_id.get(event_id)
        if (event is None or event.scope != registry.scope
                or event.payload_reference != source.object_ref
                or event.content_digest != source.evidence.content_digest
                or event.parent_event_ids != source.evidence.parent_refs):
            raise PermissionError("phase source lacks exact current canonical ancestor closure")
        captured[event_id] = source
        pending.extend(source.evidence.parent_refs)
    # Copy preserves actual instance-mutated predicates. Their closure may
    # retain an original service and run more reads; correctness precedes speed.
    for event_id in source_event_ids:
        if local_policy.allow_event(event_id, policy.purpose) is not True:
            raise PermissionError("phase actual source/control predicate denied use")
    for claim_id in claim_ids:
        _require_available(sample.local_claims.load_current(claim_id), claim_id)
    # Execute fresh real grant callbacks after traversal; a LAST callback can
    # withdraw an earlier grant or quarantine a Claim. Terminal SQL catches both.
    for event_id, source in captured.items():
        action = permissions.current_action(event_id, policy.purpose)
        head = sample.local_permissions._head(event_id, policy.purpose)
        if (action is None or action.decision != "allow"
                or action.source_registration_sha256 != source.registration_sha256
                or action.action_sha256 != head["action_sha256"]):
            raise PermissionError("phase current source/parent grant was withdrawn")
    if authority_guard is not None:
        authority_guard()
    bindings()
    # A current phase/control callback may change an actual custom predicate.
    # Re-run those real predicates before the terminal selected-row statement.
    for event_id in source_event_ids:
        if local_policy.allow_event(event_id, policy.purpose) is not True:
            raise PermissionError("phase actual source/control predicate changed")
    bindings()
    sample.verify_final_current_rows()
    bindings()
    return True
