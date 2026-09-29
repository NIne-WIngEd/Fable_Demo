"""Exact source read for a current Claim, across selected authoritative planes.

This path retrieves registered evidence. It does not interpret that evidence,
adjudicate a conflict, or grant a model permission to use the plaintext.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
from typing import Mapping

from .claims import XTDBClaimAuthority
from .experience import KurrentExperienceLog
from .object_store import EncryptedObjectPlane, RawObjectReference


@dataclass(frozen=True)
class VerifiedSource:
    event_id: str
    relation_id: str
    content_digest: str
    plaintext: bytes = field(repr=False)


@dataclass(frozen=True)
class CurrentEvidencePacket:
    claim_id: str
    claim_version_id: str
    projection_id: str
    sources: tuple[VerifiedSource, ...]


def read_current_sources(
    *, claim_id: str, authority: XTDBClaimAuthority,
    log: KurrentExperienceLog, objects: EncryptedObjectPlane,
    references: Mapping[str, RawObjectReference],
    as_of: datetime | None = None,
) -> CurrentEvidencePacket:
    """Fail closed if a claimed source is absent, changed, or cross-host."""
    if authority.scope != log.scope or log.scope != objects.scope:
        raise ValueError("source readers must share one host scope")
    projection = authority.load_current(claim_id, as_of=as_of)
    if (projection["claim_id"] != claim_id
            or projection["deletion_state"] != "active"
            or projection["conflict_state"] != "none"
            or projection["adjudication_state"] not in {"accepted", "revised"}):
        raise ValueError("claim is not an active, resolved current source")
    version = authority.load_version(projection["current_claim_version_id"])
    if (version["claim_id"] != claim_id
            or version["adjudication_state"] != projection["adjudication_state"]):
        raise ValueError("current projection differs from its committed version")
    replayed = {event.event_id: event for event in log.replay()}
    sources: list[VerifiedSource] = []
    for relation_id in version["evidence_relation_ids"]:
        relation = authority.load_evidence_relation(relation_id)
        event_id = relation["evidence_record_id"]
        if (relation["target_record_id"] != version["claim_version_id"]
                or relation["target_record_type"] != "claim_version"
                or event_id not in version["envelope"]["source_records"]):
            raise ValueError("claim relation does not bind its version")
        event = replayed.get(event_id)
        if event is None or event.scope != authority.scope or event.payload_reference is None:
            raise ValueError("cited Experience source is absent")
        reference = references.get(event.payload_reference)
        if reference is None or reference.scope != authority.scope:
            raise ValueError("cited raw object reference is absent")
        plaintext = objects.get(reference)
        if hashlib.sha256(plaintext).hexdigest() != event.content_digest:
            raise ValueError("raw source does not match Experience digest")
        sources.append(VerifiedSource(event_id, relation_id, event.content_digest,
                                      plaintext))
    if not sources:
        raise ValueError("current claim has no exact source evidence")
    return CurrentEvidencePacket(claim_id, version["claim_version_id"],
                                 projection["projection_id"], tuple(sources))
