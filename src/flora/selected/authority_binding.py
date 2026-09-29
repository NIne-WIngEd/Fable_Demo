"""Cross-check Claim Authority sources against replayed Experience positions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from cognitive_kernel.adjudication_contracts import ClaimEvidenceRelation
from cognitive_kernel.claim_contracts import ClaimVersion
from cognitive_kernel.experience import ExperienceEvent


@dataclass(frozen=True)
class ClaimSourceReceipt:
    claim_version_id: str
    event_id: str
    stream_position: int
    relation_ids: tuple[str, ...]


def bind_claim_source(*, version: ClaimVersion,
                      relations: Sequence[ClaimEvidenceRelation],
                      replayed: Sequence[ExperienceEvent]) -> ClaimSourceReceipt:
    """Reject a claim version whose cited source is missing or in the future.

    The caller must obtain `replayed` from KurrentExperienceLog.replay(). This
    is evidence binding, not proof that the content is true or owner-authored.
    """
    version.validate()
    position = version.event_stream_position
    if position is None or position >= len(replayed):
        raise ValueError("claim version has no replayed Experience position")
    by_id = {event.event_id: index for index, event in enumerate(replayed)}
    if len(by_id) != len(replayed):
        raise ValueError("Experience replay contains duplicate event IDs")
    for event in replayed:
        event.validate()
        if event.scope != version.envelope.scope:
            raise ValueError("Experience replay crosses host scope")
    if len(relations) != len(version.evidence_relation_ids) or {
        relation.relation_id for relation in relations
    } != set(version.evidence_relation_ids):
        raise ValueError("claim version lacks an exact evidence relation set")
    for relation in relations:
        relation.validate()
        if (relation.envelope.scope != version.envelope.scope
                or relation.envelope.authority_namespace_id
                != version.envelope.authority_namespace_id
                or relation.target_record_type != "claim_version"
                or relation.target_record_id != version.claim_version_id
                or relation.evidence_record_id not in version.envelope.source_records):
            raise ValueError("claim evidence relation crosses its target or scope")
        source_position = by_id.get(relation.evidence_record_id)
        if source_position is None or source_position > position:
            raise ValueError("claim cites missing or later Experience evidence")
    event = replayed[position]
    if event.event_id not in {r.evidence_record_id for r in relations}:
        raise ValueError("claim position is not one of its cited evidence sources")
    if version.correction_of and (
        event.event_type != "correction" or not event.parent_event_ids
    ):
        raise ValueError("correction lacks a linked Experience correction event")
    return ClaimSourceReceipt(version.claim_version_id, event.event_id,
                              position, tuple(sorted(version.evidence_relation_ids)))
