"""Versioned, source-linked events for synthetic histories and future authorized data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

EventKind = Literal["assertion", "correction", "decision", "outcome"]


def utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class Event:
    id: str
    at: str
    kind: EventKind
    topic: str
    text: str
    source: str
    supersedes: str | None = None
    decision_id: str | None = None

    def validate(self) -> None:
        utc(self.at)
        if self.kind not in {"assertion", "correction", "decision", "outcome"}:
            raise ValueError(f"unknown event kind: {self.kind}")
        if not all((self.id, self.topic, self.text, self.source)):
            raise ValueError("id, topic, text and source are required")
        if self.kind == "correction" and not self.supersedes:
            raise ValueError("a correction must cite the event it supersedes")
        if self.kind == "outcome" and not self.decision_id:
            raise ValueError("an outcome must cite its decision")


@dataclass(frozen=True)
class Question:
    id: str
    at: str
    text: str
    topic: str
    retrieval_query: str
    expected_ids: tuple[str, ...]
    forbidden_ids: tuple[str, ...] = ()

    def validate(self) -> None:
        utc(self.at)
        if not self.id or not self.text or not self.topic or not self.retrieval_query:
            raise ValueError("question id, text, topic and retrieval query are required")
