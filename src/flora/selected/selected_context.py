"""Explicit selected-context consumer over original physical source locators.

The replay facade below is a finite source view, never a canonical-log reader.
It cannot append, supply a stream revision, or certify whole-stream integrity.
Default context consumers retain their existing replay behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from types import MethodType

from cognitive_kernel.canonical import canonical_json_bytes, require_identifier

from .claims import XTDBClaimAuthority
from .context import ContextPlan
from .context_guard import prepare_current_context
from .experience import KurrentExperienceLog
from .governed_development import XTDBGovernedPersonalDevelopment, _version_from_record
from .judgment_context import RegisteredJudgmentContextPolicy
from .personal_state import _ACTIVE, _VERSIONS
from .native_phase_gate import transfer_native_phase_gate
from .source_closure import (SelectedSourceClosureResolver, _ReaderBinding,
                             _native_snapshot, _require_native_contracts)
from .source_native import _require_available


_DOMAIN = "selected-current-context-v1"
_ORIGINAL_PREDICATES = tuple((name, getattr(RegisteredJudgmentContextPolicy, name),
                             getattr(RegisteredJudgmentContextPolicy, name).__code__)
    for name in ("allow_claim", "allow_state", "allow_event"))


@dataclass(frozen=True)
class SelectedContextSources:
    """Structural nominations, not a stored positive permission decision."""

    event_ids: tuple[str, ...]
    maximum_sources: int


class SelectedContextLogView:
    """Fresh finite metadata view for one explicitly nominated context.

    Original Kurrent receiver identity is retained inside the resolver. Exact
    reads never run on a copied log or this facade. Each replay resolves fresh
    current grants before and after event hydration. Those observations cannot
    grant a later byte read. Physical positions sort the view but are never
    replaced by list indexes or exposed as an append revision.
    """

    domain = _DOMAIN

    def __init__(self, *, resolver: SelectedSourceClosureResolver,
                 sources: SelectedContextSources, purpose: str,
                 policy_binding_guard=None):
        if type(resolver) is not SelectedSourceClosureResolver:
            raise TypeError("selected context needs the actual source closure resolver")
        if (type(sources) is not SelectedContextSources or type(sources.event_ids) is not tuple
                or not sources.event_ids or len(set(sources.event_ids)) != len(sources.event_ids)
                or type(sources.maximum_sources) is not int or sources.maximum_sources < 1
                or len(sources.event_ids) > sources.maximum_sources
                or resolver.maximum_sources != sources.maximum_sources):
            raise ValueError("selected context needs finite explicit source nominations")
        for event_id in sources.event_ids:
            if require_identifier(event_id, "selected context source") != event_id:
                raise ValueError("selected context source must be canonical")
        if require_identifier(purpose, "selected context purpose") != purpose:
            raise ValueError("selected context purpose must be canonical")
        self.resolver, self.sources, self.purpose = resolver, sources, purpose
        self.scope = resolver.registry.scope
        self._original = (resolver.registry, resolver.log, resolver.permissions)
        self._policy_binding_guard = policy_binding_guard

    def _configuration(self):
        if self._policy_binding_guard is not None:
            self._policy_binding_guard()
        registry, log, permissions = self._original
        if (self.resolver.registry is not registry or self.resolver.log is not log
                or self.resolver.permissions is not permissions
                or self.scope != registry.scope
                or self.resolver.maximum_sources != self.sources.maximum_sources
                or type(log) is not KurrentExperienceLog):
            raise PermissionError("selected context original authority binding changed")

    def replay(self):
        """Return only freshly verified nominated events and their parents."""
        self._configuration()
        resolver, sources, purpose, scope, original, policy_guard = (
            self.resolver, self.sources, self.purpose, self.scope, self._original,
            self._policy_binding_guard)
        _require_native_contracts()
        scope_record = _native_snapshot(scope)
        source_ids, maximum_sources = sources.event_ids, sources.maximum_sources
        readers = tuple(_ReaderBinding.capture(owner, name) for owner, names in (
            (self, ("replay", "_configuration")),
            (resolver, ("resolve", "_require_configuration"))) for name in names)

        def bindings():
            _require_native_contracts()
            for reader in readers:
                reader.verify()
            if (self.resolver is not resolver or self.sources is not sources
                    or self.purpose != purpose or self.scope is not scope
                    or self._original is not original or self._policy_binding_guard is not policy_guard
                    or type(sources.event_ids) is not tuple or sources.event_ids is not source_ids
                    or type(sources.maximum_sources) is not int or sources.maximum_sources != maximum_sources
                    or _native_snapshot(scope) != scope_record):
                raise PermissionError("selected context view binding changed")
            self._configuration()

        bindings()
        proof = resolver.resolve(source_event_ids=sources.event_ids, purpose=purpose)
        bindings()
        events = []
        for commitment in sorted(proof.commitments, key=lambda value: value.stream_position):
            entry = original[1].lookup_committed(
                event_id=commitment.source.evidence.ref_id,
                event_sha256=commitment.event_sha256,
                stream_position=commitment.stream_position,
                expected_recorded_at=commitment.recorded_at)
            bindings()
            events.append(entry.event)
        # Hydration callbacks may withdraw a grant, change a locator or change
        # the actual owner. Resolve again so the returned event list follows a
        # fresh terminal authority observation, never the earlier proof alone.
        current = resolver.resolve(source_event_ids=sources.event_ids, purpose=purpose)
        bindings()
        if current != proof:
            raise PermissionError("selected context source/grant observation changed during hydration")
        return events


class SelectedJudgmentContextPolicy(RegisteredJudgmentContextPolicy):
    """Inherited Claim/state rules with fresh original selected event custody."""

    domain = _DOMAIN

    def allow_event(self, event_id: str, purpose: str) -> bool:
        if purpose != self.purpose:
            return False
        if type(self.log) is not SelectedContextLogView or self.log.purpose != purpose:
            raise PermissionError("selected context policy lost its explicit evidence view")
        # Resolve the whole finite nomination, including original parents. A
        # predicate cannot silently expand the context's selected proof domain.
        return any(event.event_id == event_id for event in self.log.replay())


_SELECTED_EVENT_PREDICATE = SelectedJudgmentContextPolicy.allow_event
_SELECTED_EVENT_CODE = _SELECTED_EVENT_PREDICATE.__code__


def _require_policy_contracts():
    if (any(getattr(RegisteredJudgmentContextPolicy, name) is not function or function.__code__ is not code
            for name, function, code in _ORIGINAL_PREDICATES)
            or SelectedJudgmentContextPolicy.allow_event is not _SELECTED_EVENT_PREDICATE
            or _SELECTED_EVENT_PREDICATE.__code__ is not _SELECTED_EVENT_CODE):
        raise TypeError("selected context canonical policy implementation changed")


def _nominate_sources(*, plan, claims, state, maximum_sources):
    """Read nominated current authority metadata; never open private objects."""
    if type(maximum_sources) is not int or maximum_sources < 1:
        raise ValueError("selected context requires an explicit positive source cap")
    event_ids = set()

    def add(values):
        for event_id in values:
            if require_identifier(event_id, "selected context source") != event_id:
                raise ValueError("selected context source must be canonical")
            event_ids.add(event_id)
        if len(event_ids) > maximum_sources:
            raise PermissionError("selected context nominations exceed their source cap")

    def claim_sources(claim_id, expected_version=None):
        current = claims.load_current(claim_id)
        _require_available(current, claim_id)
        if (current["validity_state"] != "current"
                or expected_version is not None and current["current_claim_version_id"] != expected_version):
            raise ValueError("selected context requires the current exact Claim")
        version = claims.load_version(current["current_claim_version_id"])
        if (version["claim_id"] != claim_id
                or version["adjudication_state"] != current["adjudication_state"]):
            raise ValueError("selected context Claim nomination is unbound")
        relation_sources = []
        for relation_id in version["evidence_relation_ids"]:
            relation = claims.load_evidence_relation(relation_id)
            event_id = relation["evidence_record_id"]
            if (relation["target_record_id"] != version["claim_version_id"]
                    or relation["target_record_type"] != "claim_version"
                    or event_id not in version["envelope"]["source_records"]):
                raise ValueError("selected context Claim relation is unbound")
            relation_sources.append(event_id)
        if not relation_sources or claims.load_current(claim_id) != current:
            raise ValueError("selected context Claim nomination is empty or changed")
        add(relation_sources)

    # Inspect every selected state before source hydration or private I/O.
    # Episode artifact custody currently relies on contiguous replay indexes;
    # a sparse view cannot faithfully supply that contract.
    versions = []
    for route in plan.state_routes:
        head = state._fetch(_ACTIVE, state._head_id(route.subject_type, route.subject_id, route.projection_id))
        if head is None:
            raise ValueError("selected context nominated state has no active head")
        row = state._fetch(_VERSIONS, state._version_id(head["version_id"]), all_valid=True)
        if row is None:
            raise ValueError("selected context nominated state version is absent")
        version = _version_from_record(json.loads(str(row["record_json"])))
        if version.source_episode_ids:
            raise ValueError("selected context episode lineage requires physical-position-aware custody")
        if ((version.subject_type, version.subject_id, version.projection_id)
                != (route.subject_type, route.subject_id, route.projection_id)
                or version.version_id != head["version_id"]
                or version.projection_sha256 != row["projection_sha256"]
                or version.projection_sha256 != head["projection_sha256"]):
            raise ValueError("selected context active state nomination is unbound")
        versions.append((head, version))
    for claim_id in plan.exact_claim_ids:
        claim_sources(claim_id)
    for head, version in versions:
        add(version.source_evidence_ids)
        add(set(version.envelope.source_records) - set(version.source_claim_version_ids))
        add((head["approval_event_id"],))
        for version_id in version.source_claim_version_ids:
            claim_sources(claims.load_version(version_id)["claim_id"], version_id)
    if not event_ids:
        raise ValueError("selected context requires nominated evidence")
    return SelectedContextSources(tuple(sorted(event_ids)), maximum_sources)


def prepare_selected_current_context(*, plan: ContextPlan, claims, state, log,
        objects, references, policy: RegisteredJudgmentContextPolicy,
        maximum_sources: int, approval_verifier_factory, authority_guard=None,
        before_private_assembly=None):
    """Opt in to actual selected private context with existing current barriers.

    Supports frozen exact Claim routes and governed state without episodes.
    Selection does not certify unrelated stream integrity or scientific phase
    exclusion. Supply an independent current phase guard for experiment use.
    Returned PreparedCurrentContext remains responsible for byte/owner/current
    Claim, source, grant and state checks. No model inference occurs here.
    """
    plan.validate()
    _require_policy_contracts()
    if plan.query_vector is not None or plan.graph_source_event_ids:
        raise ValueError("selected context requires explicitly frozen exact routes")
    if (type(claims) is not XTDBClaimAuthority
            or type(state) is not XTDBGovernedPersonalDevelopment
            or type(log) is not KurrentExperienceLog
            or type(policy) is not RegisteredJudgmentContextPolicy
            or policy.claims is not claims or policy.state is not state or policy.log is not log
            or plan.purpose != policy.purpose):
        raise TypeError("selected context needs the original selected governed services")
    for name, function, _ in _ORIGINAL_PREDICATES[:2]:
        predicate = getattr(policy, name)
        if (not isinstance(predicate, MethodType) or predicate.__self__ is not policy
                or predicate.__func__ is not function):
            raise TypeError("selected context cannot replace custom Claim/state predicates")
    registry, permissions = policy.registry, policy.permissions
    readers = tuple(_ReaderBinding.capture(policy, name)
        for name in ("allow_claim", "allow_state", "allow_event"))

    def policy_binding_guard():
        _require_policy_contracts()
        for reader in readers:
            reader.verify()
        if (policy.claims is not claims or policy.state is not state or policy.log is not log
                or policy.registry is not registry or policy.permissions is not permissions
                or policy.purpose != plan.purpose):
            raise PermissionError("selected context original policy owner changed")

    policy_binding_guard()
    # A partially issued or detached phase cannot reach the independent guard
    # or the initial metadata nomination. Fully unissued policies keep their
    # original callback route.
    from .selected_authority_frame import shared_phase_origin
    shared_phase_origin(permissions, policy)
    # Validate/transfer the original source port before nomination or private
    # I/O. The temporary target already owns the real services; its log is
    # replaced by the explicit facade before it can serve context.
    selected_policy = SelectedJudgmentContextPolicy(claims=claims, state=state, log=log,
        registry=registry, permissions=permissions)
    transfer_native_phase_gate(policy, "allow_event", selected_policy,
        expected_original_predicate=_ORIGINAL_PREDICATES[2][1],
        selected_predicate=_SELECTED_EVENT_PREDICATE)
    if authority_guard is not None:
        if not callable(authority_guard) or authority_guard() is not None:
            raise PermissionError("selected context independent authority guard refused")
    sources = _nominate_sources(plan=plan, claims=claims, state=state, maximum_sources=maximum_sources)
    policy_binding_guard()
    resolver = SelectedSourceClosureResolver(registry=registry, log=log,
        permissions=permissions, maximum_sources=maximum_sources)
    view = SelectedContextLogView(resolver=resolver, sources=sources, purpose=plan.purpose,
        policy_binding_guard=policy_binding_guard)
    selected_policy.log = view
    return prepare_current_context(plan=plan, claims=claims, state=state, log=view,
        objects=objects, references=references, policy=selected_policy,
        approval_verifier_factory=approval_verifier_factory, authority_guard=authority_guard,
        before_private_assembly=before_private_assembly)
