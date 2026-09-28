"""Prepare a bounded, source-linked packet; no personality inference happens here."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile

from .alice_adapter import ALICE_COMMIT, ingest
from .events import Event, utc
from .ledger_adapter import journal


def prepare(fixture: Path, *, at: str, topic: str, question: str, max_evidence: int = 8) -> dict:
    from alice_memory.provenance import list_memory_sources
    from alice_memory.service import MemoryContentAccessAuthorization, load_memory_content
    from alice_memory.store import open_memory_store
    from alice_memory.temporal import resolve_memory_at

    utc(at)
    if not topic or not question or max_evidence < 1:
        raise ValueError("topic, question and positive max_evidence are required")
    data = json.loads(fixture.read_text())
    visible = [event for event in (Event(**item) for item in data["events"]) if utc(event.at) <= utc(at)]
    with tempfile.TemporaryDirectory(prefix="fable-demo-packet-") as directory:
        vault = Path(directory)
        ledger = journal(visible, vault / "experience-ledger.sqlite3")
        with open_memory_store(vault) as connection:
            ingest(connection, visible)
            resolution = resolve_memory_at(connection, memory_key=f"demo.{topic}", at=at)
            if len(resolution.memories) > max_evidence:
                raise ValueError("current evidence exceeds the packet budget; select explicitly")
            auth = MemoryContentAccessAuthorization(actor="fable-demo-packet", allowed=True, reason="synthetic evaluation")
            evidence = [{
                "memory_id": item.memory_id, "text": load_memory_content(connection, memory_id=item.memory_id, authorization=auth),
                "recorded_at": item.recorded_at, "category": item.category,
                "knowledge_status": item.knowledge_status,
                "sources": [source.source_ref for source in list_memory_sources(connection, memory_id=item.memory_id)],
            } for item in resolution.memories]
    return {"alice_commit": ALICE_COMMIT, "question": question, "at": at, "topic": topic,
            "evidence": evidence, "conflicts": [list(pair) for pair in resolution.conflict_pairs],
            "ledger": ledger, "status": "evidence only; no personality judgment or response"}
