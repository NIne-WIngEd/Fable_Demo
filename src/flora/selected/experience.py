"""Metadata-only Experience stream over the selected KurrentDB event fabric.

The upstream ExperienceEvent is the authority for event identity and provenance.
This adapter deliberately has no alternate database implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Any
from uuid import UUID

from cognitive_kernel.contracts import ProductHostScope
from cognitive_kernel.experience import ExperienceEvent


def stream_name(scope: ProductHostScope) -> str:
    """Avoid exposing a host identifier in the server's stream catalog."""
    scope.validate()
    digest = hashlib.sha256(scope.storage_scope().encode()).hexdigest()
    return f"fable-experience-{digest}"


def event_uuid(event: ExperienceEvent) -> UUID:
    event.validate()
    # Stable 128-bit ID for a retry of exactly the same immutable envelope.
    return UUID(hex=event.event_sha256[:32])


def encode_event(event: ExperienceEvent) -> bytes:
    event.validate()
    return json.dumps(event.metadata_record(), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def decode_event(data: bytes, scope: ProductHostScope) -> ExperienceEvent:
    event = ExperienceEvent.from_metadata_record(json.loads(data))
    if event.scope != scope:
        raise ValueError("experience event escaped the host scope")
    return event


@dataclass(frozen=True)
class CommittedExperience:
    """Verified event with physical append position and availability time.

    ``recorded_at`` comes from KurrentDB, not the source's observation clock.
    Older clients may omit it; historical formation must then fail closed.
    """

    event: ExperienceEvent
    stream_position: int
    recorded_at: datetime | None


class KurrentExperienceLog:
    """Expected-revision append and verified replay for one host stream.

    A KurrentDBClient is injected so configuration/credentials live outside the
    repository. This class does not claim cross-plane atomicity or integration
    qualification until run against a real service.
    """

    def __init__(self, *, scope: ProductHostScope, client: Any):
        scope.validate()
        self.scope = scope
        self.client = client
        self.stream = stream_name(scope)

    def append(self, event: ExperienceEvent, *, expected_revision: int) -> None:
        if event.scope != self.scope:
            raise ValueError("event belongs to a different host")
        if expected_revision < -1:
            raise ValueError("expected revision must be -1 or greater")
        from kurrentdbclient import NewEvent, StreamState

        self.client.append_to_stream(
            stream_name=self.stream,
            current_version=(StreamState.NO_STREAM if expected_revision == -1
                             else expected_revision),
            events=[NewEvent(type="FableExperienceV1", data=encode_event(event),
                             id=event_uuid(event))],
        )

    def replay_committed(self) -> tuple[CommittedExperience, ...]:
        from kurrentdbclient.exceptions import NotFoundError

        try:
            records = self.client.get_stream(stream_name=self.stream)
        except NotFoundError:
            return ()
        result: list[CommittedExperience] = []
        for expected_position, record in enumerate(records):
            if record.stream_position != expected_position or record.type != "FableExperienceV1":
                raise ValueError("unexpected event or gap in Experience stream")
            event = decode_event(record.data, self.scope)
            if record.id != event_uuid(event):
                raise ValueError("Kurrent event ID differs from the Experience envelope")
            recorded_at = getattr(record, "recorded_at", None)
            if recorded_at is not None and (
                not isinstance(recorded_at, datetime)
                or recorded_at.tzinfo is None or recorded_at.utcoffset() is None
            ):
                raise ValueError("Kurrent record time must be timezone-aware")
            result.append(CommittedExperience(event, expected_position, recorded_at))
        return tuple(result)

    def replay(self) -> list[ExperienceEvent]:
        return [record.event for record in self.replay_committed()]
