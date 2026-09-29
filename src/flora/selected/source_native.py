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
    """Read exact evidence without allowing history to override quarantine.

    An explicit valid-time snapshot can retrieve current or historical claims
    at that snapshot. It never grants permission to use a claim whose present
    authority is pending deletion, deleted, conflicted, or unaccepted. Ordinary
    current use additionally requires ``validity_state == "current"``.
    """
    if authority.scope != log.scope or log.scope != objects.scope:
        raise ValueError("source readers must share one host scope")
    if as_of is not None and (
        not isinstance(as_of, datetime)
        or as_of.tzinfo is None or as_of.utcoffset() is None
    ):
        raise ValueError("source valid-time snapshot must be timezone-aware")
    present = authority.load_current(claim_id)
    _require_available(present, claim_id)
    projection = (present if as_of is None else
                  authority.load_current(claim_id, as_of=as_of))
    _require_available(projection, claim_id)
    allowed_validity = {"current"} if as_of is None else {"current", "historical"}
    if projection["validity_state"] not in allowed_validity:
        raise ValueError("claim validity does not permit this source read")
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
    # The source reads are not a cross-plane transaction. Recheck the use
    # barrier after materialization so an intervening quarantine is rejected.
    latest = authority.load_current(claim_id)
    _require_available(latest, claim_id)
    if as_of is None and latest != projection:
        raise ValueError("claim head changed during current source read")
    return CurrentEvidencePacket(claim_id, version["claim_version_id"],
                                 projection["projection_id"], tuple(sources))


def _require_available(projection: dict[str, object], claim_id: str) -> None:
    if (projection["claim_id"] != claim_id
            or projection["deletion_state"] != "active"
            or projection["conflict_state"] != "none"
            or projection["adjudication_state"] not in {"accepted", "revised"}):
        raise ValueError("claim is not an active, resolved current source")
