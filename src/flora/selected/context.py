"""Local context assembly and auditable delivery, without a judgment model.

An explicit plan chooses registered retrieval routes. The plan is a caller's
request, not learned relevance or sufficient semantic understanding. Returned
content stays local; the Experience receipt records exact delivered versions,
sources, and hashes rather than duplicating private context plaintext.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
from typing import Callable, Mapping, Protocol, Sequence

from cognitive_kernel.canonical import canonical_sha256, require_identifier
from cognitive_kernel.contracts import ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent

from .claims import XTDBClaimAuthority
from .decision_outcome import RecordedEvent, record_decision
from .experience import KurrentExperienceLog
from .graph_recollection import LadybugEvidenceGraph
from .object_store import EncryptedObjectPlane, RawObjectReference
from .personal_state import StateApprovalVerifier, XTDBPersonalStateCandidates
from .source_native import read_current_sources
from .vector_recollection import QdrantClaimProjection


class ContextUsePolicy(Protocol):
    """Trusted local permission check, not a decision made by a retriever."""

    def allow_claim(self, claim_id: str, purpose: str) -> bool: ...
    def allow_state(self, subject_type: str, subject_id: str,
                    projection_id: str, purpose: str) -> bool: ...
    def allow_event(self, event_id: str, purpose: str) -> bool: ...


@dataclass(frozen=True)
class StateRoute:
    subject_type: str
    subject_id: str
    projection_id: str


@dataclass(frozen=True)
class ContextPlan:
    request_id: str
    purpose: str
    exact_claim_ids: tuple[str, ...] = ()
    state_routes: tuple[StateRoute, ...] = ()
    query_vector: tuple[float, ...] | None = None
    vector_limit: int = 0
    minimum_claims: int = 0
    graph_source_event_ids: tuple[str, ...] = ()
    graph_limit: int = 0

    def validate(self) -> None:
        require_identifier(self.request_id, "request_id")
        require_identifier(self.purpose, "purpose")
        if (len(set(self.exact_claim_ids)) != len(self.exact_claim_ids)
                or len(set(self.state_routes)) != len(self.state_routes)):
            raise ValueError("context plan contains duplicate routes")
        for claim_id in self.exact_claim_ids:
            require_identifier(claim_id, "claim_id")
        if len(set(self.graph_source_event_ids)) != len(self.graph_source_event_ids):
            raise ValueError("context plan has duplicate graph sources")
        for event_id in self.graph_source_event_ids:
            require_identifier(event_id, "source_event_id")
        for route in self.state_routes:
            for label, value in (("subject_type", route.subject_type),
                                 ("subject_id", route.subject_id),
                                 ("projection_id", route.projection_id)):
                require_identifier(value, label)
        if (self.query_vector is None) != (self.vector_limit == 0):
            raise ValueError("vector route needs a vector and positive limit")
        if (isinstance(self.vector_limit, bool) or not isinstance(self.vector_limit, int)
                or self.vector_limit < 0 or isinstance(self.minimum_claims, bool)
                or not isinstance(self.minimum_claims, int) or self.minimum_claims < 0):
            raise ValueError("context route limits must be nonnegative integers")
        if (isinstance(self.graph_limit, bool) or not isinstance(self.graph_limit, int)
                or self.graph_limit < 0
                or bool(self.graph_source_event_ids) != (self.graph_limit > 0)):
            raise ValueError("graph route needs sources and a positive limit")
        if (not self.exact_claim_ids and not self.state_routes
                and self.query_vector is None and not self.graph_source_event_ids):
            raise ValueError("context plan has no retrieval route")


@dataclass(frozen=True)
class LocalContextItem:
    kind: str
    record_id: str
    version_id: str
    source_event_ids: tuple[str, ...]
    content: bytes = field(repr=False)
    claim_value: dict[str, object] | None = field(default=None, repr=False)
    approval_event_id: str | None = None
    projection_sha256: str | None = None
    control_event_ids: tuple[str, ...] = ()

    def receipt_record(self) -> dict[str, object]:
        return {
            "kind": self.kind, "record_id": self.record_id,
            "version_id": self.version_id,
            "source_event_ids": list(self.source_event_ids),
            "control_event_ids": list(self.control_event_ids),
            "content_sha256": hashlib.sha256(self.content).hexdigest(),
            "claim_value_sha256": (
                canonical_sha256(self.claim_value)
                if self.claim_value is not None else None),
            "approval_event_id": self.approval_event_id,
            "projection_sha256": self.projection_sha256,
        }


@dataclass(frozen=True)
class LocalContext:
    plan: ContextPlan
    items: tuple[LocalContextItem, ...] = field(repr=False)
    sufficient_by_declared_count: bool

    def receipt_record(self) -> dict[str, object]:
        material = {
            "schema": "flora-context-delivery-v2",
            "request_id": self.plan.request_id,
            "purpose": self.plan.purpose,
            "routes": {
                "exact_claim_ids": list(self.plan.exact_claim_ids),
                "state_routes": [vars(route) for route in self.plan.state_routes],
                "vector_used": self.plan.query_vector is not None,
                "vector_limit": self.plan.vector_limit,
                "graph_source_event_ids": list(self.plan.graph_source_event_ids),
                "graph_limit": self.plan.graph_limit,
                "minimum_claims": self.plan.minimum_claims,
            },
            "items": [item.receipt_record() for item in self.items],
            "sufficient_by_declared_count": self.sufficient_by_declared_count,
        }
        material["receipt_sha256"] = canonical_sha256(material)
        return material

    @property
    def source_event_ids(self) -> tuple[str, ...]:
        return tuple(sorted({source for item in self.items
                             for source in item.source_event_ids} |
                            {control for item in self.items for control in item.control_event_ids} |
                            {item.approval_event_id for item in self.items
                             if item.approval_event_id is not None}))


def assemble_context(
    *, plan: ContextPlan, claims: XTDBClaimAuthority,
    state: XTDBPersonalStateCandidates, log: KurrentExperienceLog,
    objects: EncryptedObjectPlane,
    references: Mapping[str, RawObjectReference],
    policy: ContextUsePolicy, approval_verifier: StateApprovalVerifier,
    vector: QdrantClaimProjection | None = None,
    graph: LadybugEvidenceGraph | None = None,
) -> LocalContext:
    """Assemble only permitted exact, active, source-verified material."""
    plan.validate()
    if not (claims.scope == state.scope == log.scope == objects.scope):
        raise ValueError("context planes cross host scope")
    if plan.query_vector is not None and (vector is None or vector.scope != claims.scope):
        raise ValueError("selected vector route is unavailable or cross host")
    if plan.graph_source_event_ids and (graph is None or graph.scope != claims.scope):
        raise ValueError("selected graph route is unavailable or cross host")
    items: list[LocalContextItem] = []
    claim_ids = list(plan.exact_claim_ids)
    if plan.query_vector is not None:
        for candidate in vector.query_current(
            query_vector=plan.query_vector, authority=claims,
            limit=plan.vector_limit,
        ):
            if candidate.claim_id not in claim_ids:
                claim_ids.append(candidate.claim_id)
    for event_id in plan.graph_source_event_ids:
        if not policy.allow_event(event_id, plan.purpose):
            raise PermissionError("graph source event is not permitted")
        for candidate in graph.related_current_metadata(
            source_event_id=event_id, authority=claims, log=log,
            limit=plan.graph_limit):
            if candidate.claim_id not in claim_ids:
                claim_ids.append(candidate.claim_id)
    for claim_id in claim_ids:
        if not policy.allow_claim(claim_id, plan.purpose):
            raise PermissionError("context claim is not permitted for this purpose")
        packet = read_current_sources(
            claim_id=claim_id, authority=claims, log=log,
            objects=objects, references=references,
            source_authorizer=lambda event_id: policy.allow_event(event_id, plan.purpose),
        )
        source_ids = tuple(source.event_id for source in packet.sources)
        if not all(policy.allow_event(event_id, plan.purpose)
                   for event_id in source_ids):
            raise PermissionError("context claim source is not permitted")
        items.append(LocalContextItem(
            kind="claim", record_id=claim_id,
            version_id=packet.claim_version_id, source_event_ids=source_ids,
            content=b"\n".join(source.plaintext for source in packet.sources),
            claim_value=claims.load_version(packet.claim_version_id)["value"],
            projection_sha256=claims.load_current(claim_id)["projection_sha256"],
        ))
    for route in plan.state_routes:
        if not policy.allow_state(route.subject_type, route.subject_id,
                                  route.projection_id, plan.purpose):
            raise PermissionError("personal state is not permitted for this purpose")
        active = state.read_active(
            subject_type=route.subject_type, subject_id=route.subject_id,
            projection_id=route.projection_id,
            claims=claims, log=log, objects=objects, references=references,
            verifier=approval_verifier,
        )
        sources = set(active.record["source_evidence_ids"])
        controls = set()
        episode_snapshots = {}
        episode_ids = set(active.record["source_episode_ids"])
        if episode_ids:
            episodes = getattr(state, "episodes", None)
            if episodes is None:
                raise ValueError("context requires governed accepted episode authority")
            for episode_id in episode_ids:
                lineage = episodes.current_lineage(episode_id, claims=claims, log=log)
                episode_snapshots[episode_id] = lineage
                controls.add(lineage[1].acceptance_event_id)
                sources.update(lineage[3])
            sources.difference_update(controls)
        sources.update(set(active.record["envelope"]["source_records"])
                       - set(active.record["source_claim_version_ids"]) - episode_ids)
        for version_id in active.record["source_claim_version_ids"]:
            version = claims.load_version(version_id)
            packet = read_current_sources(
                claim_id=version["claim_id"], authority=claims,
                log=log, objects=objects, references=references,
                source_authorizer=lambda event_id: policy.allow_event(event_id, plan.purpose),
            )
            if packet.claim_version_id != version_id:
                raise ValueError("active state cites a superseded claim")
            sources.update(source.event_id for source in packet.sources)
        if active.approval_event_id is None or not all(
            policy.allow_event(event_id, plan.purpose)
            for event_id in sources | controls | {active.approval_event_id}
        ):
            raise PermissionError("personal state source or approval is not permitted")
        if any(state.episodes.current_lineage(episode_id, claims=claims, log=log) != lineage
               for episode_id, lineage in episode_snapshots.items()):
            raise ValueError("accepted episode lineage changed during context assembly")
        items.append(LocalContextItem(
            kind=f"state:{route.subject_type}", record_id=route.projection_id,
            version_id=active.record["version_id"],
            source_event_ids=tuple(sorted(sources)), content=active.content,
            approval_event_id=active.approval_event_id,
            projection_sha256=active.record["projection_sha256"],
            control_event_ids=tuple(sorted(controls)),
        ))
    # Separate stores do not give a cross-plane transaction. Recheck each
    # materialized item's present authority and permission before returning.
    for item in items:
        if not all(policy.allow_event(event_id, plan.purpose) is True
                   for event_id in item.source_event_ids + item.control_event_ids):
            raise PermissionError("context source permission changed during assembly")
        if item.kind == "claim":
            current = claims.load_current(item.record_id)
            if (policy.allow_claim(item.record_id, plan.purpose) is not True
                    or current["current_claim_version_id"] != item.version_id
                    or current["projection_sha256"] != item.projection_sha256):
                raise ValueError("context claim changed during assembly")
        else:
            subject_type = item.kind.split(":", 1)[1]
            route = next(route for route in plan.state_routes
                         if route.subject_type == subject_type
                         and route.projection_id == item.record_id)
            if (policy.allow_state(route.subject_type, route.subject_id,
                                   route.projection_id, plan.purpose) is not True
                    or policy.allow_event(item.approval_event_id, plan.purpose) is not True):
                raise PermissionError("context state permission changed during assembly")
            active = state.read_active(
                subject_type=route.subject_type, subject_id=route.subject_id,
                projection_id=route.projection_id, claims=claims, log=log,
                objects=objects, references=references, verifier=approval_verifier)
            if (active.record["version_id"] != item.version_id
                    or active.record["projection_sha256"] != item.projection_sha256
                    or active.approval_event_id != item.approval_event_id
                    or active.content != item.content):
                raise ValueError("context state changed during assembly")
    claim_count = sum(item.kind == "claim" for item in items)
    return LocalContext(plan, tuple(items),
                        claim_count >= plan.minimum_claims)


def record_context_delivery(
    *, context: LocalContext, log: KurrentExperienceLog,
    objects: EncryptedObjectPlane,
    references: Mapping[str, RawObjectReference],
    claims: XTDBClaimAuthority, state: XTDBPersonalStateCandidates,
    policy: ContextUsePolicy, approval_verifier: StateApprovalVerifier,
    vector: QdrantClaimProjection | None = None,
    graph: LadybugEvidenceGraph | None = None,
    occurred_at: str, expected_revision: int,
    authority_guard: Callable[[], None] | None = None,
) -> RecordedEvent:
    """Append a receipt for material delivered to a judgment interface.

    The receipt does not prove the model attended to that material.
    """
    if log.scope != objects.scope:
        raise ValueError("context delivery crosses host scope")
    if authority_guard is not None:
        authority_guard()
    fresh = assemble_context(
        plan=context.plan, claims=claims, state=state, log=log,
        objects=objects, references=references, policy=policy,
        approval_verifier=approval_verifier, vector=vector, graph=graph,
    )
    if fresh.receipt_record() != context.receipt_record():
        raise ValueError("context changed before delivery")
    replayed = log.replay()
    if len(replayed) - 1 != expected_revision:
        raise ValueError("stale expected Experience revision")
    by_id = {event.event_id: event for event in replayed}
    for event_id in context.source_event_ids:
        if policy.allow_event(event_id, context.plan.purpose) is not True:
            raise PermissionError("context source permission changed before delivery")
        event = by_id.get(event_id)
        if event is None or event.payload_reference is None:
            raise ValueError("context receipt cites an absent Experience source")
        raw = references.get(event.payload_reference)
        if (raw is None or raw.scope != log.scope
                or hashlib.sha256(objects.get(raw)).hexdigest() != event.content_digest):
            raise ValueError("context receipt source differs from Experience")
        if policy.allow_event(event_id, context.plan.purpose) is not True:
            raise PermissionError("context source permission changed during delivery")
        if datetime.fromisoformat(event.occurred_at.replace("Z", "+00:00")) > datetime.fromisoformat(occurred_at.replace("Z", "+00:00")):
            raise ValueError("context receipt cites a future source")
    material = json.dumps(context.receipt_record(), sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode()
    raw = objects.put(material)
    if any(policy.allow_event(event_id, context.plan.purpose) is not True
           for event_id in context.source_event_ids):
        raise PermissionError("context source permission changed before delivery append")
    event = ExperienceEvent.create(
        event_type="context_delivery", scope=log.scope, occurred_at=occurred_at,
        content_digest=raw.plaintext_sha256,
        provenance=ProvenanceReference.create(
            provenance_type="derived_inference",
            source_reference_ids=context.source_event_ids,
            derivation_activity_id=f"context-{hashlib.sha256(material).hexdigest()[:32]}",
            responsible_component="flora-context-assembly",
        ),
        retention_class="ordinary_experience", storage_tier="raw_buffer",
        parent_event_ids=context.source_event_ids,
        payload_reference=raw.object_id,
    )
    if authority_guard is not None:
        authority_guard()
    log.append(event, expected_revision=expected_revision)
    return RecordedEvent(event, raw)


def record_contextual_decision(
    *, context: LocalContext, delivery: RecordedEvent,
    log: KurrentExperienceLog, objects: EncryptedObjectPlane,
    references: Mapping[str, RawObjectReference],
    claims: XTDBClaimAuthority, state: XTDBPersonalStateCandidates,
    policy: ContextUsePolicy, approval_verifier: StateApprovalVerifier,
    vector: QdrantClaimProjection | None = None,
    graph: LadybugEvidenceGraph | None = None,
    verdict: bytes, model_artifact_sha256: str, occurred_at: str,
    expected_revision: int, producer_component: str,
) -> RecordedEvent:
    """Bind a supplied verdict to the exact delivered-context receipt."""
    if delivery.event.event_type != "context_delivery":
        raise ValueError("decision lacks a context delivery receipt")
    if not context.sufficient_by_declared_count:
        raise ValueError("declared context minimum is not met; expand or defer")
    fresh = assemble_context(
        plan=context.plan, claims=claims, state=state, log=log,
        objects=objects, references=references, policy=policy,
        approval_verifier=approval_verifier, vector=vector, graph=graph,
    )
    if fresh.receipt_record() != context.receipt_record():
        raise ValueError("context changed before decision")
    if (objects.get(delivery.raw) != json.dumps(
            context.receipt_record(), sort_keys=True, separators=(",", ":"),
            allow_nan=False).encode()
            or delivery.event.content_digest != delivery.raw.plaintext_sha256):
        raise ValueError("decision context receipt differs from delivery")
    linked = dict(references)
    linked[delivery.raw.object_id] = delivery.raw
    return record_decision(
        log=log, objects=objects, verdict=verdict,
        consumed_event_ids=(delivery.event.event_id,) + context.source_event_ids,
        references=linked, model_artifact_sha256=model_artifact_sha256,
        occurred_at=occurred_at, expected_revision=expected_revision,
        producer_component=producer_component,
        source_authorizer=lambda event_id: (
            event_id == delivery.event.event_id
            or policy.allow_event(event_id, context.plan.purpose)),
    )
