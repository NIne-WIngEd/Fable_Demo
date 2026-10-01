"""Current metadata guard for an actually assembled private judgment context.

A supplied LocalContext never creates this guard. Initial selected assembly
opens and authenticates the actual bytes. Repeated checks retain those exact
bytes while resolving present authority metadata and independent approvals.
No permission, semantic judgment, model or cross-plane transaction is invented.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from copy import copy, deepcopy
import hashlib
import json
from types import FunctionType
from typing import Any, Callable

from cognitive_kernel.canonical import canonical_json_bytes, canonical_sha256
from .context import ContextPlan, LocalContext, LocalContextItem, StateRoute, assemble_context
from .governed_development import (_version_from_record, _ROLLBACKS, _ROLLBACK_IDS,
                                  XTDBGovernedPersonalDevelopment)
from .judgment_context import RegisteredJudgmentContextPolicy
from .personal_state import _ACTIVE, _VERSIONS, activation_request
from .source_native import _require_available, read_current_source_manifest


_CONTEXT_LAYOUTS = {cls: tuple(cls.__dataclass_fields__) for cls in (
    ContextPlan, LocalContext, LocalContextItem, StateRoute)}
_CONTEXT_SHAPES = tuple((cls, tuple(vars(cls).items())) for cls in _CONTEXT_LAYOUTS)
_CONTEXT_CODES = tuple((value, value.__code__) for _, shape in _CONTEXT_SHAPES
                       for _, value in shape if type(value) is FunctionType)
_CONTEXT_ID = id


def _require_context_snapshot_contracts():
    for name, function, code in _CONTEXT_FUNCTIONS:
        if globals().get(name) is not function or function.__code__ is not code:
            raise PermissionError("selected held-context snapshot helper changed")
    if globals().get("_CONTEXT_ID") is not _CONTEXT_IDENTITY:
        raise PermissionError("selected held-context identity helper changed")
    for cls, shape in _CONTEXT_SHAPES:
        current = vars(cls)
        extra = "__slotnames__" not in dict(shape) and "__slotnames__" in current
        if (len(current) != len(shape) + int(extra)
                or any(current.get(name) is not value for name, value in shape)
                or extra and (type(current["__slotnames__"]) is not list or current["__slotnames__"])):
            raise PermissionError("selected held-context native contract changed")
    if any(function.__code__ is not code for function, code in _CONTEXT_CODES):
        raise PermissionError("selected held-context native contract code changed")


def _context_snapshot_value(value, active):
    cls = type(value)
    if value is None:
        return cls, value
    if type(cls) is not type:
        raise PermissionError("selected held context contains a custom metadata class")
    if cls is str or cls is int or cls is bool or cls is float or cls is bytes:
        return cls, value
    if cls not in (dict, list, tuple) and cls not in _CONTEXT_LAYOUTS:
        raise PermissionError("selected held context contains unsupported native metadata")
    identity = _CONTEXT_ID(value)
    if identity in active:
        raise PermissionError("selected held context contains a metadata cycle")
    active.add(identity)
    try:
        if cls is tuple or cls is list:
            return cls, tuple(_context_snapshot_value(item, active) for item in value)
        if cls is dict:
            if any(type(key) is not str for key in value):
                raise PermissionError("selected held context contains nonnative dictionary keys")
            return cls, tuple((key, _context_snapshot_value(value[key], active)) for key in sorted(value))
        fields = _CONTEXT_LAYOUTS[cls]
        material = object.__getattribute__(value, "__dict__")
        if (type(material) is not dict or any(type(key) is not str for key in material)
                or set(material) != set(fields)):
            raise PermissionError("selected held-context native fields changed")
        return cls, tuple((name, _context_snapshot_value(material[name], active)) for name in fields)
    finally:
        active.remove(identity)


def _native_context_snapshot(context):
    """Immutable content observation, never a stored authorization decision."""
    _require_context_snapshot_contracts()
    if type(context) is not LocalContext:
        raise PermissionError("selected held context lost its native material owner")
    try:
        return _context_snapshot_value(context, set())
    except (RuntimeError, RecursionError) as error:
        raise PermissionError("selected held-context metadata changed during its snapshot") from error


_CONTEXT_IDENTITY = _CONTEXT_ID
_CONTEXT_FUNCTIONS = tuple((function.__name__, function, function.__code__) for function in (
    _require_context_snapshot_contracts, _context_snapshot_value, _native_context_snapshot))


@dataclass(frozen=True)
class CapturedClaimAuthority:
    claim_id: str
    version_id: str
    projection_sha256: str
    current_record: bytes = field(repr=False)
    version_record: bytes = field(repr=False)
    evidence_records: tuple[tuple[str, bytes], ...] = field(repr=False)


@dataclass(frozen=True)
class CapturedStateAuthority:
    route: StateRoute
    version_id: str
    projection_sha256: str
    head_record: bytes = field(repr=False)
    version_row: bytes = field(repr=False)
    activation_record: bytes = field(repr=False)
    rollback_records: tuple[tuple[str, str, bytes], ...] = field(repr=False)
    rollback_version_rows: tuple[tuple[str, bytes], ...] = field(repr=False)
    rollback_activation_records: tuple[tuple[str, str, bytes], ...] = field(repr=False)
    approval_event_id: str
    approval_request: bytes = field(repr=False)

    def version_record(self) -> dict:
        return json.loads(json.loads(self.version_row)["record_json"])


@dataclass(frozen=True)
class CapturedSourceAuthority:
    event_id: str
    event_sha256: str
    source_record: bytes = field(repr=False)
    raw_record: bytes = field(repr=False)
    grant_record: bytes | None = field(repr=False)


@dataclass(frozen=True)
class CapturedEpisodeAuthority:
    episode_id: str
    lineage_sha256: str


def _source_record(source) -> bytes:
    return canonical_json_bytes({"evidence": source.evidence.metadata_record(),
        "object_ref": source.object_ref, "registration_sha256": source.registration_sha256})


def _state_row(row):
    # Temporal SQL columns may be datetime objects. Exact version identity and
    # canonical upstream metadata are the immutable contract, not a driver repr.
    if row is None:
        return None
    return {key: row[key] for key in ("_id", "scope_digest", "projection_id", "subject_type", "subject_id",
        "version_id", "generation", "projection_sha256", "content_object_id", "record_json")}


def _episode_record(lineage):
    episode, publication, request, sources, record = lineage
    return {"episode": episode.metadata_record(), "publication": vars(publication),
            "request": request.metadata_record(), "sources": list(sources), "record": record}


def _invoke_guard(guard):
    if guard is not None and guard() is not None:
        raise PermissionError("independent context authority guard refused")


def _binding_guard(*, claims, state, log, objects, policy, purpose):
    """Keep exact registered services/configuration live, never an allow result."""
    from .selected_context import SelectedContextLogView
    if type(log) is SelectedContextLogView:
        return _selected_binding_guard(claims=claims, state=state, log=log,
            objects=objects, policy=policy, purpose=purpose)
    registry, permissions, episodes = policy.registry, policy.permissions, state.episodes
    scope, namespace = claims.scope, claims.authority_namespace_id
    scope_record = canonical_json_bytes(scope.metadata_record())
    def current():
        if (policy.purpose != purpose or policy.claims is not claims
                or policy.state is not state or policy.log is not log
                or policy.registry is not registry or policy.permissions is not permissions
                or state.registry is not registry or state.policy is not permissions
                or permissions.registry is not registry or state.episodes is not episodes
                or canonical_json_bytes(scope.metadata_record()) != scope_record
                or not scope == claims.scope == state.scope == log.scope == objects.scope
                    == registry.scope == permissions.scope
                or not namespace == claims.authority_namespace_id == state.authority_namespace_id
                    == registry.authority_namespace_id == permissions.authority_namespace_id):
            raise PermissionError("current registered context authority binding changed")
        if episodes is not None and (episodes.registry is not registry or episodes.policy is not permissions
                or episodes.scope != scope or episodes.authority_namespace_id != namespace):
            raise PermissionError("current registered episode authority binding changed")
    current()
    return current


def _selected_binding_guard(*, claims, state, log, objects, policy, purpose):
    """Pure selected-domain owner checks after terminal metadata observation.

    Native contract snapshots bypass metadata_record and JSON helpers. Reader
    bindings reject getter/field replacement before direct dictionary reads.
    Neither an external phase callback nor an authority predicate runs here.
    """
    from .source_closure import _ReaderBinding, _native_snapshot, _require_native_contracts
    native_guard, snapshot = _require_native_contracts, _native_snapshot
    guard_code, snapshot_code = native_guard.__code__, snapshot.__code__
    registry, permissions, episodes = policy.registry, policy.permissions, state.episodes
    scope, namespace = claims.scope, claims.authority_namespace_id
    native_guard()
    scope_record = snapshot(scope)
    if type(namespace) is not str or type(purpose) is not str:
        raise TypeError("selected current context needs native authority identifiers")
    if type(policy.purpose) is not str or policy.purpose != purpose:
        raise PermissionError("selected current-context purpose binding changed")
    owner_fields = (
        (claims, ("scope", "authority_namespace_id", "connection")),
        (state, ("scope", "authority_namespace_id", "connection", "registry", "policy", "episodes")),
        (log, ("scope", "resolver", "sources", "purpose", "_original", "_policy_binding_guard")),
        (objects, ("scope",)),
        (policy, ("claims", "state", "log", "registry", "permissions", "purpose")),
        (registry, ("scope", "authority_namespace_id", "connection")),
        (permissions, ("scope", "authority_namespace_id", "connection", "registry")))
    if episodes is not None:
        owner_fields += ((episodes, ("scope", "authority_namespace_id", "registry", "policy")),)
    readers = tuple(_ReaderBinding.capture(owner, name) for owner, names in owner_fields for name in names)

    def current():
        if native_guard.__code__ is not guard_code or snapshot.__code__ is not snapshot_code:
            raise PermissionError("selected current-context native snapshot helper changed")
        native_guard()
        for reader in readers:
            reader.verify()
        fields = {id(owner): object.__getattribute__(owner, "__dict__") for owner, _ in owner_fields}
        policy_fields, state_fields = fields[id(policy)], fields[id(state)]
        registry_fields, permission_fields = fields[id(registry)], fields[id(permissions)]
        if (policy_fields.get("claims") is not claims or policy_fields.get("state") is not state
                or policy_fields.get("log") is not log or policy_fields.get("registry") is not registry
                or policy_fields.get("permissions") is not permissions
                or state_fields.get("registry") is not registry or state_fields.get("policy") is not permissions
                or state_fields.get("episodes") is not episodes or permission_fields.get("registry") is not registry):
            raise PermissionError("selected current-context actual owner changed")
        for owner in (claims, state, log, objects, registry, permissions):
            if snapshot(fields[id(owner)]["scope"]) != scope_record:
                raise PermissionError("selected current-context native scope changed")
        for owner in (claims, state, registry, permissions):
            value = fields[id(owner)]["authority_namespace_id"]
            if type(value) is not str or value != namespace:
                raise PermissionError("selected current-context native authority changed")
        if episodes is not None:
            episode_fields = fields[id(episodes)]
            if (episode_fields.get("registry") is not registry or episode_fields.get("policy") is not permissions
                    or snapshot(episode_fields["scope"]) != scope_record
                    or type(episode_fields.get("authority_namespace_id")) is not str
                    or episode_fields["authority_namespace_id"] != namespace):
                raise PermissionError("selected current-context actual episode owner changed")
    current()
    return current


def _metadata_view(*, claims, state, log, policy, source_sample=None):
    """One guard's sampled actual rows; every view is discarded before a fence.

    Only metadata readers are memoized. No connection, plaintext reader, owner
    verifier, external semantic verifier or allow decision is copied/cached.
    """
    from .native_phase_gate import copy_native_phase_view
    def sampled(service, names):
        result = copy_native_phase_view(service)
        for name in names:
            method = getattr(result, name, None)
            if not callable(method):
                continue
            cache = {}
            def read(*args, _method=method, _cache=cache, **kwargs):
                key = (args, tuple(sorted(kwargs.items())))
                if key not in _cache:
                    _cache[key] = deepcopy(_method(*args, **kwargs))
                return deepcopy(_cache[key])
            setattr(result, name, read)
        return result
    captured_events = log.replay()
    local_log = copy(log)
    local_log.replay = lambda: list(captured_events)
    if callable(getattr(claims, "_fetch_record", None)):
        local_claims = sampled(claims, ("_fetch_record",))
    else:  # Explicit contract fixtures still resolve actual supplied reader ports.
        local_claims = sampled(claims, ("load_current", "load_version", "load_evidence_relation"))
    if source_sample is not None:
        registry = source_sample.local_registry
    else:
        registry = (sampled(policy.registry, ("_fetch",))
            if callable(getattr(policy.registry, "_fetch", None))
            else sampled(policy.registry, ("lookup", "raw_metadata", "raw_reference")))
    permissions = (source_sample.local_permissions if source_sample is not None
        else sampled(policy.permissions, ("_fetch",)))
    permissions.registry = registry
    local_state = sampled(state, ("_fetch",))
    local_state.registry, local_state.policy = registry, permissions
    if state.episodes is not None:
        local_state.episodes = sampled(state.episodes, ("_fetch",))
        local_state.episodes.registry, local_state.episodes.policy = registry, permissions
        local_state.episodes.custody = sampled(state.episodes.custody, ("_fetch",))
    local_policy = copy_native_phase_view(policy)
    local_policy.claims, local_policy.state, local_policy.log = local_claims, local_state, local_log
    local_policy.registry, local_policy.permissions = registry, permissions
    return local_claims, local_state, local_log, local_policy


def _nomination_record(*, plan, claims, state, log, policy):
    """Metadata nomination only, before any source/state/private proof opens."""
    claim_records, state_records, episode_records = {}, [], {}
    source_ids = set()
    events = {event.event_id: event for event in log.replay()}
    def claim_record(claim_id, expected_version=None):
        manifest = read_current_source_manifest(claim_id=claim_id, authority=claims, log=log)
        current = claims.load_current(claim_id)
        version = claims.load_version(manifest.claim_version_id)
        if (expected_version is not None and manifest.claim_version_id != expected_version
                or policy.allow_claim(claim_id, plan.purpose) is not True):
            raise PermissionError("context nomination lost current Claim authority")
        material = {"current": current, "version": version,
            "relations": [(key, claims.load_evidence_relation(key)) for key in version["evidence_relation_ids"]]}
        if claim_id in claim_records and claim_records[claim_id] != material:
            raise ValueError("context nomination contains incompatible Claim generations")
        claim_records[claim_id] = material
        source_ids.update(source.event_id for source in manifest.sources)
    for claim_id in plan.exact_claim_ids:
        claim_record(claim_id)
    for route in plan.state_routes:
        head = state._fetch(_ACTIVE, state._head_id(route.subject_type, route.subject_id, route.projection_id))
        if head is None:
            raise ValueError("context nomination lacks an active state")
        row = state._fetch(_VERSIONS, state._version_id(head["version_id"]), all_valid=True)
        if row is None:
            raise ValueError("context nomination lacks its state version")
        version = _version_from_record(json.loads(str(row["record_json"])))
        if policy.allow_state(route.subject_type, route.subject_id, route.projection_id, plan.purpose) is not True:
            raise PermissionError("context nomination state use is not current")
        material = {"route": vars(route), "head": head, "version": _state_row(row),
            "activation": state._history(route.projection_id, head["version_id"])}
        if version.envelope.rollback_reference is not None:
            binding = state._immutable(_ROLLBACKS, state._rollback_key(version.version_id))
            if binding is None:
                raise ValueError("context nomination lost rollback binding")
            target = state._fetch(_VERSIONS, state._version_id(binding["target_version_id"]), all_valid=True)
            if target is None:
                raise ValueError("context nomination lost rollback target")
            material["rollback"] = {"binding": binding,
                "action": state._immutable(_ROLLBACK_IDS, state._rollback_id_key(binding["rollback_id"])),
                "target": _state_row(target),
                "target_activation": state._history(route.projection_id, binding["target_version_id"])}
        state_records.append(material)
        source_ids.update(version.source_evidence_ids)
        source_ids.add(head["approval_event_id"])
        source_ids.update(set(version.envelope.source_records) - set(version.source_claim_version_ids)
                          - set(version.source_episode_ids))
        for version_id in version.source_claim_version_ids:
            claim_record(claims.load_version(version_id)["claim_id"], version_id)
        for episode_id in version.source_episode_ids:
            if state.episodes is None:
                raise ValueError("context nomination lacks accepted episode authority")
            lineage = state.episodes.current_lineage(episode_id, claims=claims, log=log)
            episode_records[episode_id] = _episode_record(lineage)
            source_ids.update(lineage[3])
            for version_id in lineage[0].member_claim_version_ids:
                claim_record(claims.load_version(version_id)["claim_id"], version_id)
    sources, pending = {}, list(source_ids)
    while pending:
        event_id = pending.pop()
        if event_id in sources:
            continue
        source, event = policy.registry.lookup(event_id), events.get(event_id)
        if (source is None or event is None or source.object_ref != event.payload_reference
                or source.evidence.content_digest != event.content_digest
                or source.evidence.parent_refs != event.parent_event_ids
                or policy.allow_event(event_id, plan.purpose) is not True):
            raise PermissionError("context nomination source closure is not permitted")
        action_reader = getattr(policy.permissions, "current_action", None)
        grant = action_reader(event_id, plan.purpose) if callable(action_reader) else None
        if callable(action_reader) and grant is None:
            raise PermissionError("context nomination lost its source grant")
        sources[event_id] = {"event": event.metadata_record(), "source": json.loads(_source_record(source)),
            "raw": policy.registry.raw_metadata(source.object_ref),
            "grant": None if grant is None else grant.metadata_record()}
        pending.extend(source.evidence.parent_refs)
    return {"claims": [(key, claim_records[key]) for key in sorted(claim_records)],
            "states": state_records, "episodes": [(key, episode_records[key]) for key in sorted(episode_records)],
            "sources": [(key, sources[key]) for key in sorted(sources)]}


def _nomination_fence(*, material, plan, claims, state, log, policy):
    """Fresh exact rows after one sampled metadata pass, before private I/O.

    The pass may reuse a row within its own closure traversal. This fence uses
    the original services and never those sampled readers or a cached allow.
    """
    for claim_id, expected in material["claims"]:
        actual = {"current": claims.load_current(claim_id),
            "version": claims.load_version(expected["version"]["claim_version_id"]),
            "relations": [(key, claims.load_evidence_relation(key)) for key, _ in expected["relations"]]}
        if canonical_json_bytes(actual) != canonical_json_bytes(expected):
            raise ValueError("context nomination changed during initial metadata verification")
    for expected in material["states"]:
        route = StateRoute(**expected["route"])
        head = state._fetch(_ACTIVE, state._head_id(route.subject_type, route.subject_id, route.projection_id))
        version_id = expected["head"]["version_id"]
        actual = {"route": vars(route), "head": head,
            "version": _state_row(state._fetch(_VERSIONS, state._version_id(version_id), all_valid=True)),
            "activation": state._history(route.projection_id, version_id)}
        if "rollback" in expected:
            rollback = expected["rollback"]
            binding = state._immutable(_ROLLBACKS, state._rollback_key(version_id))
            actual["rollback"] = {"binding": binding,
                "action": state._immutable(_ROLLBACK_IDS, state._rollback_id_key(rollback["binding"]["rollback_id"])),
                "target": _state_row(state._fetch(_VERSIONS,
                    state._version_id(rollback["binding"]["target_version_id"]), all_valid=True)),
                "target_activation": state._history(route.projection_id, rollback["binding"]["target_version_id"])}
        if canonical_json_bytes(actual) != canonical_json_bytes(expected):
            raise ValueError("context nomination changed during initial metadata verification")
    for episode_id, expected in material["episodes"]:
        if state.episodes is None or canonical_json_bytes(_episode_record(
                state.episodes.current_lineage(episode_id, claims=claims, log=log))) != canonical_json_bytes(expected):
            raise ValueError("context nomination changed during initial metadata verification")
    _nomination_source_fence(material=material, plan=plan, log=log, policy=policy)


def _nomination_source_fence(*, material, plan, log, policy):
    """Initial originals/controls follow all slow metadata/phase callbacks."""
    events = {event.event_id: event for event in log.replay()}
    current_sources = {}
    for event_id, expected in material["sources"]:
        source, event = policy.registry.lookup(event_id), events.get(event_id)
        if source is None or event is None:
            raise PermissionError("context nomination source disappeared during initial metadata verification")
        actual = {"event": event.metadata_record(), "source": json.loads(_source_record(source)),
            "raw": policy.registry.raw_metadata(source.object_ref)}
        if canonical_json_bytes(actual) != canonical_json_bytes({key: value for key, value in expected.items() if key != "grant"}):
            raise PermissionError("context nomination source changed during initial metadata verification")
        current_sources[event_id] = source
    for event_id, expected in material["sources"]:
        action_reader = getattr(policy.permissions, "current_action", None)
        grant = action_reader(event_id, plan.purpose) if callable(action_reader) else None
        if (canonical_json_bytes(None if grant is None else grant.metadata_record()) != canonical_json_bytes(expected["grant"])
                or not callable(action_reader) and policy.permissions.permits(current_sources[event_id], plan.purpose) is not True):
            raise PermissionError("context nomination source grant changed after initial metadata verification")


_CONSTRUCTION = object()


class PreparedCurrentContext:
    """Owned actual material and present-use checks; no TTL or cached allow bit."""
    def __init__(self, token, *, context, claims, state, log, objects, references, policy,
                 approval_verifier_factory, authority_guard, claim_snapshots, state_snapshots,
                 source_snapshots, episode_snapshots):
        if token is not _CONSTRUCTION:
            raise TypeError("prepare_current_context must assemble the actual context")
        self.context = context
        self.claims, self.state, self.log = claims, state, log
        self.objects, self.references, self.policy = objects, references, policy
        self.approval_verifier_factory, self.authority_guard = approval_verifier_factory, authority_guard
        self.claim_authorities = claim_snapshots
        self.state_authorities = state_snapshots
        self.source_authorities = source_snapshots
        self.episode_authorities = episode_snapshots
        self._context_record = canonical_json_bytes(context.receipt_record())
        from .selected_context import SelectedContextLogView
        self._selected_context_snapshot = (_native_context_snapshot(context)
            if type(log) is SelectedContextLogView else None)
        self._bindings_current = _binding_guard(claims=claims, state=state, log=log,
            objects=objects, policy=policy, purpose=context.plan.purpose)

    def _phase(self):
        _invoke_guard(self.authority_guard)
        self._bindings_current()

    def metadata_current(self) -> None:
        """No raw read, owner proof or external semantic call occurs here."""
        from .claims import XTDBClaimAuthority
        from .formation_policy import XTDBFormationPermissionPolicy
        from .formation_registry import XTDBFormationSourceRegistry
        from .phase_source_fence import OneGuardSelectedMetadata
        controllers = tuple(getattr(self, name) for name in
            ("claims", "state", "log", "objects", "references", "policy"))
        phase_guard, actual_bindings = self.authority_guard, self._bindings_current
        selected_context_snapshot = self._selected_context_snapshot
        context_snapshot_reader, context_snapshot_code = _native_context_snapshot, _native_context_snapshot.__code__
        methods = [(self.policy, name, getattr(self.policy, name))
            for name in ("allow_event", "allow_claim", "allow_state")]
        methods += [(self.log, name, getattr(self.log, name, None))
            for name in ("replay", "replay_committed")]
        def bindings():
            if (any(getattr(self, name) is not value for name, value in zip(
                    ("claims", "state", "log", "objects", "references", "policy"), controllers))
                    or self.authority_guard != phase_guard or self._bindings_current != actual_bindings
                    or selected_context_snapshot is not None and self._selected_context_snapshot is not selected_context_snapshot
                    or any(getattr(service, name, None) != method for service, name, method in methods)):
                raise PermissionError("prepared current-context controller/callback binding changed")
            actual_bindings()
            if selected_context_snapshot is not None:
                if (_native_context_snapshot is not context_snapshot_reader
                        or context_snapshot_reader.__code__ is not context_snapshot_code
                        or context_snapshot_reader(self.context) != selected_context_snapshot):
                    raise PermissionError("selected held private context changed during authority verification")
        bindings()
        self._phase()
        bindings()
        if canonical_json_bytes(self.context.receipt_record()) != self._context_record:
            raise ValueError("prepared private context was changed")
        source_sample = None
        if (isinstance(self.policy.registry, XTDBFormationSourceRegistry)
                and isinstance(self.policy.permissions, XTDBFormationPermissionPolicy)
                and (self.source_authorities or self.claim_authorities)):
            if self.claim_authorities and not isinstance(self.claims, XTDBClaimAuthority):
                raise TypeError("selected current-context Claim fence needs actual selected Claim authority")
            from .selected_context import SelectedContextLogView
            if type(self.log) is SelectedContextLogView:
                from .selected_context_fence import SelectedContextMetadataSample
                source_sample = SelectedContextMetadataSample(state=self.state,
                    binding_guard=bindings, registry=self.policy.registry,
                    permissions=self.policy.permissions,
                    claims=self.claims if isinstance(self.claims, XTDBClaimAuthority) else None)
                source_sample.observe_state_authorities(self.state, self.state_authorities)
                source_sample.observe_claim_authorities(self.claim_authorities)
            else:
                source_sample = OneGuardSelectedMetadata(registry=self.policy.registry,
                    permissions=self.policy.permissions,
                    claims=self.claims if isinstance(self.claims, XTDBClaimAuthority) else None)
            if self.source_authorities:
                source_sample.prime_sources(tuple(captured.event_id for captured in self.source_authorities),
                    self.context.plan.purpose)
            for captured in self.claim_authorities:
                current = source_sample.local_claims.load_current(captured.claim_id)
                _require_available(current, captured.claim_id)
                if canonical_json_bytes(current) != captured.current_record:
                    raise ValueError("prepared Claim changed before terminal metadata observation")
        claims, state, log, policy = _metadata_view(claims=self.claims, state=self.state,
            log=self.log, policy=self.policy, source_sample=source_sample)
        events = {event.event_id: event for event in log.replay()}
        for captured in self.claim_authorities:
            current = claims.load_current(captured.claim_id)
            _require_available(current, captured.claim_id)
            if (current["validity_state"] != "current" or current["current_claim_version_id"] != captured.version_id
                    or canonical_json_bytes(current) != captured.current_record
                    or canonical_json_bytes(claims.load_version(captured.version_id)) != captured.version_record
                    or any(canonical_json_bytes(claims.load_evidence_relation(key)) != record
                           for key, record in captured.evidence_records)):
                raise ValueError("prepared Claim authority changed")
        for captured in self.state_authorities:
            route = captured.route
            head = state._fetch(_ACTIVE, state._head_id(route.subject_type, route.subject_id, route.projection_id))
            row = state._fetch(_VERSIONS, state._version_id(captured.version_id), all_valid=True)
            if (head is None or row is None or canonical_json_bytes(head) != captured.head_record
                    or canonical_json_bytes(_state_row(row)) != captured.version_row
                    or canonical_json_bytes(state._history(route.projection_id, captured.version_id)) != captured.activation_record
                    or any(canonical_json_bytes(state._immutable(table, key)) != record
                           for table, key, record in captured.rollback_records)
                    or any(canonical_json_bytes(_state_row(state._fetch(_VERSIONS,
                        state._version_id(key), all_valid=True))) != record
                           for key, record in captured.rollback_version_rows)
                    or any(canonical_json_bytes(state._history(projection, version)) != record
                           for projection, version, record in captured.rollback_activation_records)):
                raise ValueError("prepared active state authority changed")
            if policy.allow_state(route.subject_type, route.subject_id, route.projection_id,
                                       self.context.plan.purpose) is not True:
                raise PermissionError("prepared personal state use was withdrawn")
        for captured in self.episode_authorities:
            if (state.episodes is None
                    or canonical_sha256(_episode_record(state.episodes.current_lineage(captured.episode_id,
                        claims=claims, log=log))) != captured.lineage_sha256):
                raise ValueError("prepared accepted episode authority changed")
        for captured in self.source_authorities:
            source = policy.registry.lookup(captured.event_id)
            event = events.get(captured.event_id)
            if (source is None or event is None or event.event_sha256 != captured.event_sha256
                    or _source_record(source) != captured.source_record
                    or canonical_json_bytes(policy.registry.raw_metadata(source.object_ref)) != captured.raw_record
                    or policy.allow_event(captured.event_id, self.context.plan.purpose) is not True):
                raise PermissionError("prepared original/control source authority changed")
            current_action = getattr(policy.permissions, "current_action", None)
            grant = current_action(captured.event_id, self.context.plan.purpose) if callable(current_action) else None
            if captured.grant_record is not None and (grant is None
                    or canonical_json_bytes(grant.metadata_record()) != captured.grant_record):
                raise PermissionError("prepared source grant generation changed")
        # Exact Claim policy is also current, rather than a captured allow bit.
        for captured in self.claim_authorities:
            if policy.allow_claim(captured.claim_id, self.context.plan.purpose) is not True:
                raise PermissionError("prepared Claim use was withdrawn")
        self._phase()
        self._metadata_fence(source_sample=source_sample)
        self._phase()
        # A final external phase callback may perform slow metadata work.
        # Current original/control consent must still follow that work, before
        # the caller's inner ciphertext result can reach decryption.
        self._source_fence(source_sample=source_sample)
        bindings()
        if source_sample is not None:
            # Last grant/phase callbacks can withdraw an earlier source or
            # quarantine an already checked Claim. One actual selected basis
            # observes every sampled source/raw/action/head/current-Claim row
            # together after those callbacks, before private bytes can return.
            source_sample.verify_final_current_rows()
        bindings()

    def _metadata_fence(self, *, source_sample=None) -> None:
        """Final narrow exact fence after potentially slow policy lookups."""
        # Episode metadata can involve multiple dependent service calls. Do not
        # leave it after the current original/control permission fence.
        for captured in self.episode_authorities:
            if (self.state.episodes is None or canonical_sha256(_episode_record(
                    self.state.episodes.current_lineage(captured.episode_id, claims=self.claims, log=self.log))) != captured.lineage_sha256):
                raise ValueError("prepared episode changed during metadata verification")
        for captured in self.claim_authorities:
            if (canonical_json_bytes(self.claims.load_current(captured.claim_id)) != captured.current_record
                    or canonical_json_bytes(self.claims.load_version(captured.version_id)) != captured.version_record
                    or any(canonical_json_bytes(self.claims.load_evidence_relation(key)) != record
                           for key, record in captured.evidence_records)):
                raise ValueError("prepared Claim changed during metadata verification")
        for captured in self.state_authorities:
            route = captured.route
            if (canonical_json_bytes(self.state._fetch(_ACTIVE, self.state._head_id(
                    route.subject_type, route.subject_id, route.projection_id))) != captured.head_record
                    or canonical_json_bytes(_state_row(self.state._fetch(_VERSIONS,
                        self.state._version_id(captured.version_id), all_valid=True))) != captured.version_row
                    or canonical_json_bytes(self.state._history(route.projection_id, captured.version_id)) != captured.activation_record
                    or any(canonical_json_bytes(self.state._immutable(table, key)) != record
                           for table, key, record in captured.rollback_records)
                    or any(canonical_json_bytes(_state_row(self.state._fetch(_VERSIONS,
                        self.state._version_id(key), all_valid=True))) != record
                           for key, record in captured.rollback_version_rows)
                    or any(canonical_json_bytes(self.state._history(projection, version)) != record
                           for projection, version, record in captured.rollback_activation_records)):
                raise ValueError("prepared state changed during metadata verification")
        self._source_fence(source_sample=source_sample)

    def _source_fence(self, *, source_sample=None) -> None:
        """Exact source/control checks before the terminal current-row fence."""
        events = {event.event_id: event for event in self.log.replay()}
        registry = self.policy.registry if source_sample is None else source_sample.local_registry
        permissions = self.policy.permissions if source_sample is None else source_sample.local_permissions
        current_sources = {}
        for captured in self.source_authorities:
            source = registry.lookup(captured.event_id)
            event = events.get(captured.event_id)
            if (source is None or event is None or event.event_sha256 != captured.event_sha256
                    or _source_record(source) != captured.source_record
                    or canonical_json_bytes(registry.raw_metadata(source.object_ref)) != captured.raw_record):
                raise PermissionError("prepared source changed during metadata verification")
            current_sources[captured.event_id] = source
        for captured in self.source_authorities:
            current_action = getattr(permissions, "current_action", None)
            if captured.grant_record is not None:
                grant = current_action(captured.event_id, self.context.plan.purpose)
                if grant is None or canonical_json_bytes(grant.metadata_record()) != captured.grant_record:
                    raise PermissionError("prepared grant changed during metadata verification")
            elif permissions.permits(current_sources[captured.event_id], self.context.plan.purpose) is not True:
                raise PermissionError("prepared source permission changed during metadata verification")

    def revalidate(self) -> None:
        """Recheck live owner/episode proof authority without reopening state bytes."""
        self.metadata_current()
        # Resolve the actual current owner verifier each time. Its private proof
        # I/O must use the supplied metadata-only barrier to avoid recursion.
        verifier = self.approval_verifier_factory(self.metadata_current)
        if not callable(getattr(verifier, "authenticated_approval", None)):
            raise TypeError("prepared state needs the current independent owner verifier")
        events = {event.event_id: event for event in self.log.replay()}
        for captured in self.state_authorities:
            event = events.get(captured.approval_event_id)
            self.metadata_current()
            if event is None or verifier.authenticated_approval(event, json.loads(captured.approval_request)) is not True:
                raise PermissionError("prepared owner approval is no longer authenticated")
            self.metadata_current()
        # Existing episode ports can inspect private candidate content and have
        # mutable qualification/adjudication authority. Retain their full current
        # governed proof read; a new cache-safe semantic API is not invented.
        if self.episode_authorities:
            from .experiment_runtime import _AuthorizedRuntimeReads
            guarded_objects = _AuthorizedRuntimeReads(self.objects, self.metadata_current)
            for captured in self.episode_authorities:
                self.metadata_current()
                self.state.episodes.read_accepted(captured.episode_id, claims=self.claims, log=self.log,
                    objects=guarded_objects, references=self.references)
                self.metadata_current()
        self.metadata_current()


def prepare_current_context(*, plan: ContextPlan, claims, state, log, objects, references,
        policy: RegisteredJudgmentContextPolicy,
        approval_verifier_factory: Callable[[Callable[[], None]], Any],
        authority_guard: Callable[[], None] | None = None,
        before_private_assembly: Callable[[Callable[[], None]], None] | None = None,
        vector=None, graph=None) -> PreparedCurrentContext:
    """Assemble selected plaintext once and capture exact current finite authority.

    This first implementation accepts exact Claim and state routes only. A live
    accelerator nomination can change independently; it must be explicitly
    frozen into exact routes before preparing this invocation. No caller context,
    cached approval, fixture source or self-certified snapshot is accepted.
    """
    plan.validate()
    if plan.query_vector is not None or plan.graph_source_event_ids or vector is not None or graph is not None:
        raise ValueError("current-context guard requires explicitly frozen exact nominations")
    if (not isinstance(policy, RegisteredJudgmentContextPolicy)
            or not isinstance(state, XTDBGovernedPersonalDevelopment)
            or policy.claims is not claims or policy.state is not state or policy.log is not log
            or not callable(approval_verifier_factory)):
        raise TypeError("current-context guard needs the actual registered governed authority services")
    from .experiment_runtime import _AuthorizedRuntimeReads
    bindings_current = _binding_guard(claims=claims, state=state, log=log,
        objects=objects, policy=policy, purpose=plan.purpose)
    def phase():
        _invoke_guard(authority_guard)
        bindings_current()
    phase()
    sampled_claims, sampled_state, sampled_log, sampled_policy = _metadata_view(
        claims=claims, state=state, log=log, policy=policy)
    baseline_material = _nomination_record(plan=plan, claims=sampled_claims, state=sampled_state,
        log=sampled_log, policy=sampled_policy)
    assembled_context, assembled_snapshot = None, None
    def initial_barrier():
        phase()
        source_sample = None
        from .selected_context import SelectedContextLogView
        if type(log) is SelectedContextLogView:
            from .selected_context_fence import SelectedContextMetadataSample
            source_sample = SelectedContextMetadataSample(state=state,
                binding_guard=bindings_current, registry=policy.registry,
                permissions=policy.permissions, claims=claims)
            source_sample.prime_sources(tuple(key for key, _ in baseline_material["sources"]), plan.purpose)
            for claim_id, expected in baseline_material["claims"]:
                current = source_sample.local_claims.load_current(claim_id)
                _require_available(current, claim_id)
                if canonical_json_bytes(current) != canonical_json_bytes(expected["current"]):
                    raise ValueError("selected initial Claim changed before terminal observation")
            source_sample.observe_state_nominations(state, baseline_material["states"])
            source_sample.observe_claim_nominations(baseline_material["claims"])
        # The one actual nomination pass already validated the complete graph.
        # Exact original readers keep every captured dependency current without
        # re-running that whole traversal on each nested private proof fetch.
        _nomination_fence(material=baseline_material, plan=plan, claims=claims,
            state=state, log=log, policy=policy)
        phase()
        _nomination_source_fence(material=baseline_material, plan=plan, log=log, policy=policy)
        bindings_current()
        if source_sample is not None:
            source_sample.verify_final_current_rows()
            bindings_current()
            if (assembled_context is not None
                    and _native_context_snapshot(assembled_context) != assembled_snapshot):
                raise PermissionError("selected assembled private context changed after its terminal fence")
    initial_barrier()
    if before_private_assembly is not None:
        if not callable(before_private_assembly):
            raise TypeError("before-private assembly gate must be callable")
        # Source/control denial is checked before any private qualification
        # proof. Role qualification must also precede source/owner plaintext.
        if before_private_assembly(initial_barrier) is not None:
            raise PermissionError("before-private assembly gate refused")
        initial_barrier()
    guarded = _AuthorizedRuntimeReads(objects, initial_barrier)
    verifier = approval_verifier_factory(initial_barrier)
    context = assemble_context(plan=plan, claims=claims, state=state, log=log, objects=guarded,
        references=references, policy=policy, approval_verifier=verifier)
    from .selected_context import SelectedContextLogView
    if type(log) is SelectedContextLogView:
        assembled_context, assembled_snapshot = context, _native_context_snapshot(context)
    initial_barrier()
    claims_by_id, states, episodes_by_id = {}, [], {}
    source_ids = set(context.source_event_ids)
    events = {event.event_id: event for event in log.replay()}

    def capture_claim(claim_id, expected_version):
        manifest = read_current_source_manifest(claim_id=claim_id, authority=claims, log=log)
        current, version = claims.load_current(claim_id), claims.load_version(expected_version)
        _require_available(current, claim_id)
        if (manifest.claim_version_id != expected_version or current["validity_state"] != "current"
                or current["current_claim_version_id"] != expected_version):
            raise ValueError("assembled Claim changed before guard capture")
        evidence = tuple((key, canonical_json_bytes(claims.load_evidence_relation(key)))
                         for key in version["evidence_relation_ids"])
        if claim_id in claims_by_id and claims_by_id[claim_id].version_id != expected_version:
            raise ValueError("assembled context contains incompatible Claim generations")
        claims_by_id[claim_id] = CapturedClaimAuthority(claim_id, expected_version, current["projection_sha256"],
            canonical_json_bytes(current), canonical_json_bytes(version), evidence)
        source_ids.update(source.event_id for source in manifest.sources)

    for item in context.items:
        if item.kind == "claim":
            capture_claim(item.record_id, item.version_id)
            captured = claims_by_id[item.record_id]
            version = json.loads(captured.version_record)
            manifest = read_current_source_manifest(claim_id=item.record_id, authority=claims, log=log)
            if (item.projection_sha256 != captured.projection_sha256
                    or item.claim_value != version["value"]
                    or item.source_event_ids != tuple(source.event_id for source in manifest.sources)):
                raise ValueError("assembled Claim content does not match exact captured authority")
            continue
        if not item.kind.startswith("state:"):
            raise ValueError("unsupported assembled context authority")
        routes = [route for route in plan.state_routes if route.subject_type == item.kind.removeprefix("state:")
                  and route.projection_id == item.record_id]
        if len(routes) != 1:
            raise ValueError("assembled state lacks an exact subject nomination")
        route = routes[0]
        head = state._fetch(_ACTIVE, state._head_id(route.subject_type, route.subject_id, route.projection_id))
        row = state._fetch(_VERSIONS, state._version_id(item.version_id), all_valid=True)
        if head is None or row is None:
            raise ValueError("assembled active state disappeared")
        version = _version_from_record(json.loads(str(row["record_json"])))
        activation = state._history(route.projection_id, item.version_id)
        approval = events.get(item.approval_event_id)
        request = activation_request(version.metadata_record(), expected_active_version_id=head["expected_active_version_id"])
        if (version.version_id != head["version_id"] or version.projection_sha256 != item.projection_sha256
                or head["projection_sha256"] != version.projection_sha256
                or version.content_digest != hashlib.sha256(item.content).hexdigest()
                or activation["approval_event_id"] != item.approval_event_id
                or approval is None or approval.event_sha256 != head["approval_event_sha256"]
                or activation["approval_event_sha256"] != approval.event_sha256
                or approval.content_digest != hashlib.sha256(request).hexdigest()):
            raise ValueError("assembled private state lacks exact active/approval authority")
        rollback_records, rollback_rows, rollback_activations = [], [], []
        if version.envelope.rollback_reference is not None:
            key = state._rollback_key(item.version_id)
            binding = state._immutable(_ROLLBACKS, key)
            if binding is None:
                raise ValueError("assembled rollback lost its immutable target binding")
            target = state._fetch(_VERSIONS, state._version_id(binding["target_version_id"]), all_valid=True)
            if target is None:
                raise ValueError("assembled rollback target disappeared")
            rollback_rows.append((binding["target_version_id"], canonical_json_bytes(_state_row(target))))
            rollback_activations.append((version.projection_id, binding["target_version_id"],
                canonical_json_bytes(state._history(version.projection_id, binding["target_version_id"]))))
            rollback_records.extend(((_ROLLBACKS, key, canonical_json_bytes(binding)),
                (_ROLLBACK_IDS, state._rollback_id_key(binding["rollback_id"]),
                 canonical_json_bytes(state._immutable(_ROLLBACK_IDS, state._rollback_id_key(binding["rollback_id"]))))))
        states.append(CapturedStateAuthority(route, item.version_id, item.projection_sha256,
            canonical_json_bytes(head), canonical_json_bytes(_state_row(row)), canonical_json_bytes(activation),
            tuple(rollback_records), tuple(rollback_rows), tuple(rollback_activations), item.approval_event_id, request))
        for version_id in version.source_claim_version_ids:
            capture_claim(claims.load_version(version_id)["claim_id"], version_id)
        for episode_id in version.source_episode_ids:
            lineage = state.episodes.current_lineage(episode_id, claims=claims, log=log)
            episode = lineage[0]
            episodes_by_id[episode_id] = CapturedEpisodeAuthority(episode_id, canonical_sha256(_episode_record(lineage)))
            source_ids.update(lineage[3])
            for version_id in episode.member_claim_version_ids:
                capture_claim(claims.load_version(version_id)["claim_id"], version_id)
        source_ids.update(version.source_evidence_ids)
        source_ids.update(set(version.envelope.source_records) - set(version.source_claim_version_ids)
                          - set(version.source_episode_ids))
    sources = {}
    pending = list(source_ids)
    while pending:
        event_id = pending.pop()
        if event_id in sources:
            continue
        source, event = policy.registry.lookup(event_id), events.get(event_id)
        if (source is None or event is None or source.object_ref != event.payload_reference
                or source.evidence.content_digest != event.content_digest
                or source.evidence.parent_refs != event.parent_event_ids
                or policy.allow_event(event_id, plan.purpose) is not True):
            raise PermissionError("assembled source closure changed before guard capture")
        current_action = getattr(policy.permissions, "current_action", None)
        grant = current_action(event_id, plan.purpose) if callable(current_action) else None
        if callable(current_action) and grant is None:
            raise PermissionError("assembled current source lost its exact grant")
        sources[event_id] = CapturedSourceAuthority(event_id, event.event_sha256, _source_record(source),
            canonical_json_bytes(policy.registry.raw_metadata(source.object_ref)),
            None if grant is None else canonical_json_bytes(grant.metadata_record()))
        pending.extend(source.evidence.parent_refs)
    prepared = PreparedCurrentContext(_CONSTRUCTION, context=context, claims=claims, state=state, log=log,
        objects=objects, references=references, policy=policy, approval_verifier_factory=approval_verifier_factory,
        authority_guard=authority_guard, claim_snapshots=tuple(claims_by_id[key] for key in sorted(claims_by_id)),
        state_snapshots=tuple(states), source_snapshots=tuple(sources[key] for key in sorted(sources)),
        episode_snapshots=tuple(episodes_by_id[key] for key in sorted(episodes_by_id)))
    initial_barrier()
    prepared.revalidate()
    initial_barrier()
    return prepared
