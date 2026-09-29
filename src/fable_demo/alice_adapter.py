"""Run the demo on A.L.I.C.E.'s real Memory Core, pinned to a reviewed commit.

This module never substitutes a demo-only memory store or retrieval engine.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import uuid

from .events import Event, Question

# Earlier frozen diagnostic packets remain bound to this legacy reference hash.
ALICE_COMMIT = "5f9b9ccb2628eb2a5512d8624b9a78bcc9c7fe38"
_ID_NAMESPACE = uuid.UUID("cdbbe029-40c5-4af9-9cc4-5da43474af99")


def memory_id(event_id: str) -> str:
    return str(uuid.uuid5(_ID_NAMESPACE, event_id))


def _request(event: Event):
    from alice_memory.service import MemoryCreateRequest
    from alice_memory.sources import MemorySourceSpec

    return MemoryCreateRequest(
        memory_id=memory_id(event.id),
        content=event.text,
        memory_key=f"demo.{event.topic}",
        category="profile" if event.kind in {"assertion", "correction"} else "episodic",
        knowledge_status="rayan_statement",
        confidence=1.0,
        data_classification="PRIVATE",
        recorded_at=event.at,
        valid_from=event.at,
        time_precision="day",
        rayan_confirmed=True,
        sources=(MemorySourceSpec(
            source_type="rayan_direct_statement",
            source_ref=event.source,
            support_relation="supports",
            source_text_sha256=hashlib.sha256(event.text.encode()).hexdigest(),
            source_date=event.at,
        ),),
    )


def ingest(connection, events: list[Event]) -> None:
    from alice_memory.service import MemoryWriteAuthorization, create_memory
    from alice_memory.temporal import correct_memory

    authorization = MemoryWriteAuthorization(actor="fable-demo-fixture", allowed=True, reason="synthetic scenario")
    for event in sorted(events, key=lambda e: (e.at, e.id)):
        event.validate()
        if event.kind == "assertion":
            create_memory(connection, request=_request(event), authorization=authorization, created_at=event.at)
        elif event.kind == "correction":
            correct_memory(connection, memory_id=memory_id(event.supersedes), replacement=_request(event), authorization=authorization, corrected_at=event.at)
        elif event.kind in {"decision", "outcome"}:
            create_memory(connection, request=_request(event), authorization=authorization, created_at=event.at)


def retrieve(connection, vault: Path, question: Question, limit: int) -> list[str]:
    from alice_memory.lexical_index import build_memory_lexical_index
    from alice_memory.retrieval import search_memories
    from alice_memory.retrieval_models import MemoryRetrievalAuthorization, MemorySearchRequest

    build_memory_lexical_index(connection, vault, built_at=question.at)
    response = search_memories(
        connection, vault,
        request=MemorySearchRequest(query=question.retrieval_query, limit=limit, at=question.at, memory_key=f"demo.{question.topic}"),
        authorization=MemoryRetrievalAuthorization(actor="fable-demo-eval", allowed=True, purpose="synthetic evaluation"),
    )
    return [result.memory_id for result in response.results]


def resolve_known_key(connection, question: Question, limit: int) -> list[str]:
    """Use A.L.I.C.E.'s authoritative temporal resolver when a key is known."""
    from alice_memory.temporal import resolve_memory_at

    resolution = resolve_memory_at(connection, memory_key=f"demo.{question.topic}", at=question.at)
    return [record.memory_id for record in resolution.memories[-limit:]]
