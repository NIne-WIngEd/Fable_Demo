"""Source-bound outcome-to-personal-state candidate handoff.

An updater elsewhere may propose new state after observing a decision's
outcome. This gate proves the cited decision/outcome and active predecessor
exist, then registers a candidate. It neither judges the outcome nor learns
the new content, and activation remains a separate approval.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
from typing import Mapping

from cognitive_kernel.projection_contracts import ProjectionVersion

from .claims import XTDBClaimAuthority
from .experience import KurrentExperienceLog
from .object_store import EncryptedObjectPlane, RawObjectReference
from .personal_state import StateApprovalVerifier, XTDBPersonalStateCandidates


def register_outcome_revision(
    *, state: XTDBPersonalStateCandidates, version: ProjectionVersion,
    content: RawObjectReference, decision_event_id: str,
    outcome_event_id: str, claims: XTDBClaimAuthority,
    log: KurrentExperienceLog, objects: EncryptedObjectPlane,
    references: Mapping[str, RawObjectReference],
    verifier: StateApprovalVerifier,
) -> None:
    """Register an externally proposed revision, without making it active."""
    version.validate()
    if not (state.scope == version.scope == claims.scope == log.scope == objects.scope):
        raise ValueError("outcome revision crosses host scope")
    events = {event.event_id: event for event in log.replay()}
    decision = events.get(decision_event_id)
    outcome = events.get(outcome_event_id)
    if decision is None or decision.event_type != "decision":
        raise ValueError("outcome revision lacks a recorded decision")
    if (outcome is None or outcome.event_type != "outcome"
            or decision_event_id not in outcome.parent_event_ids
            or outcome_event_id not in version.source_evidence_ids):
        raise ValueError("outcome revision lacks its linked observation")
    if (datetime.fromisoformat(decision.occurred_at.replace("Z", "+00:00"))
            > datetime.fromisoformat(outcome.occurred_at.replace("Z", "+00:00"))
            or datetime.fromisoformat(outcome.occurred_at.replace("Z", "+00:00"))
            > datetime.fromisoformat(version.produced_at.replace("Z", "+00:00"))):
        raise ValueError("outcome revision has invalid causal time order")
    for event in (decision, outcome):
        if event.payload_reference is None:
            raise ValueError("outcome revision cites an event without raw content")
        raw = references.get(event.payload_reference)
        if (raw is None or raw.scope != state.scope
                or hashlib.sha256(objects.get(raw)).hexdigest() != event.content_digest):
            raise ValueError("outcome revision lacks verified decision or observation")
    active = state.read_active(
        subject_type=version.subject_type, subject_id=version.subject_id,
        projection_id=version.projection_id,
        claims=claims, log=log, objects=objects,
        references=references, verifier=verifier,
    )
    previous_id = active.record["version_id"]
    latest = state.read_latest_candidate(
        subject_type=version.subject_type, subject_id=version.subject_id,
        projection_id=version.projection_id,
        claims=claims, log=log, objects=objects, references=references,
    )
    if (latest.record["version_id"] == version.version_id
            and version.supersedes_version_id == previous_id):
        state.put_candidate(
            version, content=content, claims=claims, log=log,
            objects=objects, references=references,
            expected_previous_version_id=str(previous_id),
        )
        return
    if (latest.record["version_id"] != previous_id
            or version.supersedes_version_id != previous_id
            or version.generation != int(active.record["generation"]) + 1):
        raise ValueError("outcome revision does not follow the active state")
    state.put_candidate(
        version, content=content, claims=claims, log=log, objects=objects,
        references=references,
        expected_previous_version_id=str(previous_id),
    )
