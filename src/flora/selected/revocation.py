"""Immediate source-use quarantine across selected Claim and vector planes.

This is a first influence barrier, not deletion completion. Original objects,
append-only events, derivatives outside this slice, and model weights require
separate coordinated removal or quarantine work.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Mapping, Protocol

from cognitive_kernel.claim_contracts import CurrentClaimProjection
from cognitive_kernel.experience import ExperienceEvent
from cognitive_kernel.memory_contracts import MemoryUnitEnvelope

from .claims import XTDBClaimAuthority
from .experience import KurrentExperienceLog
from .object_store import EncryptedObjectPlane, RawObjectReference
from .vector_recollection import QdrantClaimProjection


class RevocationVerifier(Protocol):
    """Product-supplied authentication and policy authority."""

    def authenticated_request(self, event: ExperienceEvent,
                              request: dict[str, str]) -> bool: ...


def revocation_request(prior: CurrentClaimProjection) -> bytes:
    prior.validate()
    material = {
        "schema": "flora-claim-quarantine-v1",
        "claim_id": prior.claim_id,
        "current_claim_version_id": prior.current_claim_version_id,
        "expected_projection_sha256": prior.projection_sha256,
    }
    return json.dumps(material, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


@dataclass(frozen=True)
class QuarantineResult:
    projection: CurrentClaimProjection
    removed_vector_points: int


def quarantine_claim(
    *, prior: CurrentClaimProjection, request_event_id: str,
    authority: XTDBClaimAuthority, log: KurrentExperienceLog,
    objects: EncryptedObjectPlane,
    references: Mapping[str, RawObjectReference],
    vector: QdrantClaimProjection, verifier: RevocationVerifier,
) -> QuarantineResult:
    """Fail closed on use immediately; retry vector cleanup if it lagged."""
    prior.validate()
    if not (prior.envelope.scope == authority.scope == log.scope
            == objects.scope == vector.scope):
        raise ValueError("claim quarantine crosses host scope")
    current = authority.load_current(prior.claim_id)
    retry_head = False
    if current["projection_sha256"] != prior.projection_sha256:
        # An earlier successful retry can find the same quarantine head.
        if (current["deletion_state"] == "pending"
                and request_event_id in current["envelope"]["source_records"]
                and prior.projection_id in current["envelope"]["supersedes"]):
            retry_head = True
        else:
            raise ValueError("stale claim quarantine predecessor")
    if not retry_head and current["deletion_state"] != "active":
        raise ValueError("claim is already unavailable for use")
    replayed = log.replay()
    located = next(((index, event) for index, event in enumerate(replayed)
                    if event.event_id == request_event_id), None)
    if located is None:
        raise ValueError("claim quarantine lacks a replayed request")
    position, event = located
    if event.event_type != "deletion_request" or event.payload_reference is None:
        raise ValueError("claim quarantine requires a deletion request event")
    raw = references.get(event.payload_reference)
    material = revocation_request(prior)
    if (raw is None or raw.scope != log.scope or objects.get(raw) != material
            or event.content_digest != hashlib.sha256(material).hexdigest()):
        raise ValueError("claim quarantine request differs from raw Experience")
    if not verifier.authenticated_request(event, json.loads(material)):
        raise ValueError("claim quarantine request is not independently authorized")
    if retry_head:
        removed = vector.prune_noncurrent(
            claim_id=prior.claim_id, authority=authority)
        return QuarantineResult(_projection_from_prior_and_record(
            prior, current), removed)
    prior_envelope = prior.envelope
    if datetime.fromisoformat(event.occurred_at.replace("Z", "+00:00")) <= datetime.fromisoformat(prior_envelope.valid_from.replace("Z", "+00:00")):
        raise ValueError("claim quarantine predates the active projection")
    if position <= prior.source_position:
        raise ValueError("claim quarantine does not advance source position")
    projection_id = f"{prior.projection_id}-quarantine-{event.event_sha256[:12]}"
    envelope = MemoryUnitEnvelope.create(
        scope=authority.scope,
        record_id=projection_id, record_type="current_claim_projection",
        authority_namespace_id=prior_envelope.authority_namespace_id,
        host_or_cluster_id=prior_envelope.host_or_cluster_id,
        authority_role="registered_projection",
        deployment_profile=prior_envelope.deployment_profile,
        created_at=event.occurred_at, valid_from=event.occurred_at,
        valid_to=None, transaction_time=event.occurred_at,
        logical_clock=prior_envelope.logical_clock + 1,
        causal_parents=(prior.projection_id, request_event_id),
        source_records=tuple(sorted({prior.claim_id,
                                     prior.current_claim_version_id,
                                     request_event_id})),
        generation=prior_envelope.generation + 1,
        state="committed", data_classification=prior_envelope.data_classification,
        retention_class=prior_envelope.retention_class,
        deletion_state="pending",
        provenance_digest=hashlib.sha256(material).hexdigest(),
        content_digest=prior_envelope.content_digest,
        writer="claim_authority", workflow_or_request_id=request_event_id,
        idempotency_namespace="claim_quarantine",
        idempotency_key=projection_id,
        supersedes=(prior.projection_id,),
    )
    projection = CurrentClaimProjection.create(
        envelope=envelope, projection_id=projection_id,
        claim_id=prior.claim_id,
        current_claim_version_id=prior.current_claim_version_id,
        authority_generation=prior.authority_generation + 1,
        projection_generation=prior.projection_generation + 1,
        adjudication_state=prior.adjudication_state,
        validity_state=prior.validity_state,
        conflict_state=prior.conflict_state,
        deletion_state="pending", source_position=position,
    )
    authority.put_current(projection, expected_previous=prior)
    removed = vector.prune_noncurrent(
        claim_id=prior.claim_id, authority=authority)
    return QuarantineResult(projection, removed)


def _projection_from_prior_and_record(
    prior: CurrentClaimProjection, record: dict[str, object],
) -> CurrentClaimProjection:
    """Reconstruct the deterministic retry result without granting new authority."""
    # Only used after the head was checked against this request and predecessor.
    from cognitive_kernel.claim_contracts import CurrentClaimProjection as Projection

    envelope_record = record["envelope"]
    envelope = MemoryUnitEnvelope.create(
        scope=prior.envelope.scope,
        record_id=envelope_record["record_id"],
        record_type=envelope_record["record_type"],
        authority_namespace_id=envelope_record["authority_namespace_id"],
        host_or_cluster_id=envelope_record["host_or_cluster_id"],
        authority_role=envelope_record["authority_role"],
        deployment_profile=envelope_record["deployment_profile"],
        created_at=envelope_record["created_at"],
        valid_from=envelope_record["valid_from"],
        valid_to=envelope_record["valid_to"],
        transaction_time=envelope_record["transaction_time"],
        logical_clock=envelope_record["logical_clock"],
        causal_parents=envelope_record["causal_parents"],
        source_records=envelope_record["source_records"],
        generation=envelope_record["generation"],
        state=envelope_record["state"],
        data_classification=envelope_record["data_classification"],
        retention_class=envelope_record["retention_class"],
        deletion_state=envelope_record["deletion_state"],
        provenance_digest=envelope_record["provenance_digest"],
        content_digest=envelope_record["content_digest"],
        writer=envelope_record["writer"],
        workflow_or_request_id=envelope_record["workflow_or_request_id"],
        idempotency_namespace=envelope_record["idempotency_namespace"],
        idempotency_key=envelope_record["idempotency_key"],
        supersedes=envelope_record["supersedes"],
        superseded_by=envelope_record["superseded_by"],
        rollback_reference=envelope_record["rollback_reference"],
    )
    if envelope.envelope_sha256 != envelope_record["envelope_sha256"]:
        raise ValueError("stored quarantine envelope changed")
    projection = Projection.create(
        envelope=envelope, projection_id=record["projection_id"],
        claim_id=record["claim_id"],
        current_claim_version_id=record["current_claim_version_id"],
        authority_generation=record["authority_generation"],
        projection_generation=record["projection_generation"],
        adjudication_state=record["adjudication_state"],
        validity_state=record["validity_state"],
        conflict_state=record["conflict_state"],
        deletion_state=record["deletion_state"],
        source_position=record["source_position"],
    )
    if projection.projection_sha256 != record["projection_sha256"]:
        raise ValueError("stored quarantine projection changed")
    return projection
