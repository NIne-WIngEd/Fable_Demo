"""Decision and observed-outcome lineage on selected raw and Experience planes.

These records make later behavioral evaluation auditable. They do not certify
that a model actually attended to a cited source or that an outcome is true.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Callable, Mapping, Sequence

from cognitive_kernel.canonical import require_sha256
from cognitive_kernel.contracts import ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent

from .experience import KurrentExperienceLog
from .object_store import EncryptedObjectPlane, RawObjectReference


@dataclass(frozen=True)
class RecordedEvent:
    event: ExperienceEvent
    raw: RawObjectReference


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _assert_revision(replayed: Sequence[ExperienceEvent],
                     expected_revision: int) -> None:
    if expected_revision != len(replayed) - 1:
        raise ValueError("stale expected Experience revision")


def record_decision(
    *, log: KurrentExperienceLog, objects: EncryptedObjectPlane,
    verdict: bytes, consumed_event_ids: Sequence[str],
    references: Mapping[str, RawObjectReference],
    model_artifact_sha256: str, occurred_at: str,
    expected_revision: int, producer_component: str,
    source_authorizer: Callable[[str], bool] | None = None,
) -> RecordedEvent:
    """Record a supplied judgment and the exact replayed events it cites.

    The producer and artifact are declarations awaiting separate qualification.
    The record is never itself a score or proof of native judgment.
    """
    if log.scope != objects.scope:
        raise ValueError("decision raw and Experience planes cross host scope")
    require_sha256(model_artifact_sha256, "model_artifact_sha256")
    if not isinstance(verdict, bytes) or not verdict:
        raise ValueError("decision verdict must contain bytes")
    if not consumed_event_ids or len(set(consumed_event_ids)) != len(consumed_event_ids):
        raise ValueError("decision must cite unique consumed Experience events")
    replayed = log.replay()
    _assert_revision(replayed, expected_revision)
    by_id = {event.event_id: event for event in replayed}
    if not set(consumed_event_ids).issubset(by_id):
        raise ValueError("decision cites an absent Experience event")
    for event_id in consumed_event_ids:
        if source_authorizer is not None and source_authorizer(event_id) is not True:
            raise PermissionError("decision source is not permitted before raw read")
        source = by_id[event_id]
        reference = references.get(source.payload_reference or "")
        if reference is None or reference.scope != log.scope:
            raise ValueError("decision cites an unavailable raw source")
        plaintext = objects.get(reference)
        if source_authorizer is not None and source_authorizer(event_id) is not True:
            raise PermissionError("decision source permission changed during raw read")
        if (reference.object_id != source.payload_reference
                or hashlib.sha256(plaintext).hexdigest() != source.content_digest):
            raise ValueError("decision source differs from replayed Experience")
    if any(_timestamp(by_id[event_id].occurred_at) > _timestamp(occurred_at)
           for event_id in consumed_event_ids):
        raise ValueError("decision cites a future Experience event")
    material = json.dumps({
        "schema": "flora-decision-v1",
        "verdict_base64": base64.b64encode(verdict).decode("ascii"),
        "consumed_event_ids": list(consumed_event_ids),
        "model_artifact_sha256": model_artifact_sha256,
    }, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    raw = objects.put(material)
    if source_authorizer is not None and any(
            source_authorizer(event_id) is not True for event_id in consumed_event_ids):
        raise PermissionError("decision source permission changed before append")
    event = ExperienceEvent.create(
        event_type="decision", scope=log.scope, occurred_at=occurred_at,
        content_digest=raw.plaintext_sha256,
        provenance=ProvenanceReference.create(
            provenance_type="derived_inference",
            source_reference_ids=tuple(consumed_event_ids),
            derivation_activity_id=f"decision-{hashlib.sha256(material).hexdigest()[:32]}",
            responsible_component=producer_component,
            model_id=model_artifact_sha256,
        ),
        retention_class="ordinary_experience", storage_tier="raw_buffer",
        parent_event_ids=tuple(consumed_event_ids), payload_reference=raw.object_id,
    )
    log.append(event, expected_revision=expected_revision)
    return RecordedEvent(event, raw)


def record_outcome_observation(
    *, log: KurrentExperienceLog, objects: EncryptedObjectPlane,
    decision_event_id: str, observation: bytes,
    observation_provenance: ProvenanceReference,
    occurred_at: str, expected_revision: int,
) -> RecordedEvent:
    """Link an independently sourced observation to an earlier decision.

    The observation is evidence for later governance, not an automatic
    preference update, reward, or verdict that the earlier judgment was good.
    """
    if log.scope != objects.scope:
        raise ValueError("outcome raw and Experience planes cross host scope")
    if not isinstance(observation, bytes) or not observation:
        raise ValueError("outcome observation must contain bytes")
    observation_provenance.validate()
    if not observation_provenance.source_reference_ids:
        raise ValueError("outcome observation needs an external source reference")
    replayed = log.replay()
    _assert_revision(replayed, expected_revision)
    decision = next((event for event in replayed
                     if event.event_id == decision_event_id), None)
    if decision is None or decision.event_type != "decision":
        raise ValueError("outcome lacks a prior decision in this host stream")
    if _timestamp(decision.occurred_at) > _timestamp(occurred_at):
        raise ValueError("outcome predates its decision")
    raw = objects.put(observation)
    event = ExperienceEvent.create(
        event_type="outcome", scope=log.scope, occurred_at=occurred_at,
        content_digest=raw.plaintext_sha256,
        provenance=observation_provenance,
        retention_class="ordinary_experience", storage_tier="raw_buffer",
        parent_event_ids=(decision_event_id,), payload_reference=raw.object_id,
    )
    log.append(event, expected_revision=expected_revision)
    return RecordedEvent(event, raw)
