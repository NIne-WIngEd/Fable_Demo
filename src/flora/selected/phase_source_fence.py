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
from types import MethodType

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
        self._sampled_rows = {}
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
                row = self._sampled_rows.get(identity)
                if row is None:
                    row = actual(*args, **kwargs)
                self._remember(kind, table, key, immutable, service, digest_column, row)
                sampled[cache_key] = deepcopy(row)
            return deepcopy(sampled[cache_key])
        setattr(local, name, fetch)
        return local

    def _remember(self, kind, table, key, immutable, service, digest_column, row):
        if row is None:
            raise PermissionError("metadata fence source/authority row is absent")
        record = json.loads(str(row["record_json"]))
        envelope = record.get("envelope", {})
        if (row["_id"] != key or row["scope_digest"] != service.scope_digest
                or canonical_json_bytes(record.get("scope", envelope.get("scope"))) != self.scope_record
                or record.get("authority_namespace_id", envelope.get("authority_namespace_id")) != self.namespace):
            raise PermissionError("metadata fence row crosses exact key/scope")
        identity = (kind, table, key, immutable)
        observation = _Row(kind, table, key, immutable, service.scope_digest,
            digest_column, canonical_json_bytes(record), row[digest_column])
        if identity in self._observations and self._observations[identity] != observation:
            raise PermissionError("metadata fence sampled row changed during this guard")
        self._observations[identity] = observation
        if len(self._observations) > self.maximum_rows:
            raise PermissionError("metadata fence exceeds its explicit finite row cap")
        self._sampled_rows[identity] = deepcopy(row)

    def _prime_rows(self, requests):
        """Read a finite nominated row set once; no authority answer is cached."""
        self._bindings()
        pending = {request for request in requests if request not in self._sampled_rows}
        if not pending:
            return
        if len(self._observations) + len(pending) > self.maximum_rows:
            raise PermissionError("metadata fence exceeds its explicit finite row cap")
        services = {"registry": self.registry, "permission": self.permissions, "claim": self.claims}
        allowed = {("registry", source_tables._SOURCES, True),
            ("registry", source_tables._OBJECTS, True),
            ("permission", permission_tables._CURRENT, False),
            ("permission", permission_tables._ACTIONS, True),
            ("claim", claim_tables._CURRENT, False), ("claim", claim_tables._HEAD, True)}
        grouped, expected = {}, {}
        for kind, table, key, immutable in pending:
            if (kind, table, immutable) not in allowed or services[kind] is None:
                raise PermissionError("metadata batch cannot nominate an undeclared table")
            if require_identifier(key, "metadata row key") != key:
                raise PermissionError("metadata batch key is noncanonical")
            grouped.setdefault((kind, table, immutable), []).append(key)
        # Custom instance readers are actual callbacks too. Invoke them rather
        # than hiding their denial or side effects behind a direct batch query.
        # Native selected class readers are exactly the algorithms whose row
        # requests this finite batch replaces.
        native_classes = {"registry": XTDBFormationSourceRegistry,
            "permission": XTDBFormationPermissionPolicy, "claim": XTDBClaimAuthority}
        for group in tuple(grouped):
            kind, table, immutable = group
            service = services[kind]
            name = "_fetch_record" if kind == "claim" else "_fetch"
            reader = getattr(service, name)
            if (isinstance(reader, MethodType) and reader.__self__ is service
                    and reader.__func__ is getattr(native_classes[kind], name)):
                continue
            local = {"registry": self.local_registry, "permission": self.local_permissions,
                "claim": self.local_claims}[kind]
            for key in grouped.pop(group):
                if kind == "registry":
                    local._fetch(table, key)
                elif kind == "permission":
                    local._fetch(table, key, immutable=immutable)
                else:
                    local._fetch_record(table=table, row_id=key, all_valid=immutable)
        if not grouped:
            self._bindings()
            return
        terms, parameters = [], []
        for (kind, table, immutable), keys in sorted(grouped.items()):
            keys.sort()
            service = services[kind]
            column = "projection_sha256" if kind == "claim" else "record_sha256"
            tag = kind + ":" + table + (":all" if immutable else ":current")
            temporal = " FOR VALID_TIME ALL" if immutable else ""
            terms.append(f"SELECT '{tag}' AS fence_kind, _id, scope_digest, "
                f"{column} AS fence_sha256, record_json FROM {table}{temporal} "
                "WHERE scope_digest = %s AND _id IN (" + ", ".join("%s::text" for _ in keys) + ")")
            parameters.extend((service.scope_digest, *keys))
            for key in keys:
                expected[(tag, key)] = (kind, table, key, immutable, service, column)
        sql = "SELECT * FROM (" + " UNION ALL ".join(terms) + f") AS flora_current_metadata_sample LIMIT {len(expected) + 1}"
        rows = _rows(self.connection.execute(sql, tuple(parameters)))
        if len(rows) != len(expected):
            raise PermissionError("metadata batch has missing/ambiguous rows")
        seen = set()
        for row in rows:
            identity = (row.get("fence_kind"), row.get("_id"))
            request = expected.get(identity)
            if request is None or identity in seen:
                raise PermissionError("metadata batch has unexpected/duplicate rows")
            seen.add(identity)
            kind, table, key, immutable, service, column = request
            actual = {"_id": row["_id"], "scope_digest": row["scope_digest"],
                column: row["fence_sha256"], "record_json": row["record_json"]}
            self._remember(kind, table, key, immutable, service, column, actual)
        self._bindings()

    def prime_sources(self, source_event_ids, purpose):
        """Batch actual source/ancestor/raw/action/head rows within this guard.

        Every copied selected decoder and purpose predicate still runs. Source
        parents are discovered from digest-checked immutable registration;
        callers must separately check the actual canonical event closure. The
        terminal current-row fence remains mandatory after all callbacks.
        """
        if (not isinstance(source_event_ids, tuple) or not source_event_ids
                or len(set(source_event_ids)) != len(source_event_ids)):
            raise PermissionError("metadata source batch needs unique finite source IDs")
        if require_identifier(purpose, "metadata purpose") != purpose:
            raise PermissionError("metadata source batch purpose is noncanonical")
        pending, seen = source_event_ids, set()
        while pending:
            requests = []
            for event_id in pending:
                if require_identifier(event_id, "metadata source ID") != event_id:
                    raise PermissionError("metadata source batch ID is noncanonical")
                requests.extend((("registry", source_tables._SOURCES, self.registry._key("source", event_id), True),
                    ("permission", permission_tables._CURRENT, self.permissions._key("head", event_id, purpose), False)))
            self._prime_rows(requests)
            dependencies = []
            for event_id in pending:
                source_key = self.registry._key("source", event_id)
                source = self.registry._decode(self._sampled_rows[("registry", source_tables._SOURCES, source_key, True)],
                    expected_key=source_key)
                if source.get("schema") != "flora-registered-formation-source-v1":
                    raise PermissionError("metadata source batch registration schema changed")
                head_key = self.permissions._key("head", event_id, purpose)
                head = self.permissions._decode(self._sampled_rows[("permission", permission_tables._CURRENT, head_key, False)], key=head_key)
                if (head.get("schema") != "flora-current-formation-permission-v1"
                        or head["source_ref_id"] != event_id or head["purpose"] != purpose):
                    raise PermissionError("metadata source batch head differs from its exact lookup")
                dependencies.extend((("registry", source_tables._OBJECTS, self.registry._key("raw", source["object_ref"]), True),
                    ("permission", permission_tables._ACTIONS, self.permissions._key("action", head["action_id"]), True)))
            self._prime_rows(dependencies)
            ancestors = []
            for event_id in pending:
                source, _ = self.observe_source(event_id, purpose)
                seen.add(event_id)
                ancestors.extend(parent for parent in source.evidence.parent_refs if parent not in seen)
            pending = tuple(dict.fromkeys(parent for parent in ancestors if parent not in seen))
        return tuple(sorted(seen))

    def prime_raw_references(self, object_ids):
        """Nominate only raw-reference metadata, granting no source use/read."""
        if (not isinstance(object_ids, tuple) or not object_ids
                or len(set(object_ids)) != len(object_ids)):
            raise PermissionError("metadata raw batch needs unique finite object IDs")
        self._prime_rows(tuple(("registry", source_tables._OBJECTS,
            self.registry._key("raw", object_id), True) for object_id in object_ids))

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
        # XTDB's LIMIT grammar rejects a cast parameter. Only this validated
        # finite cardinality is rendered as a literal; every data value stays
        # bound. One extra row detects an ambiguous sampled immutable record.
        row_limit = len(expected) + 1
        sql = "SELECT * FROM (" + " UNION ALL ".join(terms) + f") AS flora_current_metadata_fence LIMIT {row_limit}"
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
    canonical_ids, pending = set(), list(source_event_ids)
    while pending:
        event_id = pending.pop()
        if event_id in canonical_ids:
            continue
        event = by_id.get(event_id)
        if event is None or event.scope != registry.scope:
            raise PermissionError("phase source has no actual scoped canonical ancestor")
        canonical_ids.add(event_id)
        if len(canonical_ids) > maximum_rows:
            raise PermissionError("phase canonical source closure exceeds its finite row cap")
        pending.extend(event.parent_event_ids)
    sample.prime_sources(tuple(sorted(canonical_ids)), policy.purpose)
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
        action = sample.local_permissions.current_action(event_id, policy.purpose)
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
