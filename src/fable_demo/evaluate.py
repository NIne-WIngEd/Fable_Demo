"""Chronological, reproducible evidence test with a matched raw-history baseline."""

from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile

from .alice_adapter import ALICE_COMMIT, ingest, memory_id, resolve_known_key, retrieve
from .events import Event, Question, utc
from .ledger_adapter import journal


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def raw_baseline(events: list[Event], question: Question, limit: int) -> list[str]:
    """Raw-history lexical retrieval with the same visible data and evidence count."""
    visible = [event for event in events if utc(event.at) <= utc(question.at)]
    vocabulary = _tokens(question.retrieval_query)
    visible = [event for event in visible if event.topic == question.topic and vocabulary <= _tokens(event.text)]
    scored = sorted(visible, key=lambda event: (len(_tokens(question.text) & _tokens(event.text)), utc(event.at), event.id), reverse=True)
    return [memory_id(event.id) for event in scored[:limit]]


def recent_baseline(events: list[Event], question: Question, limit: int) -> list[str]:
    """Stronger simple competitor: most recent matching topic and search term."""
    vocabulary = _tokens(question.retrieval_query)
    visible = [event for event in events if event.topic == question.topic and utc(event.at) <= utc(question.at) and vocabulary <= _tokens(event.text)]
    return [memory_id(event.id) for event in sorted(visible, key=lambda event: (utc(event.at), event.id), reverse=True)[:limit]]


def evaluate(fixture: Path, limit: int = 1) -> dict:
    from alice_memory.store import open_memory_store

    if limit < 1:
        raise ValueError("limit must be positive")
    data = json.loads(fixture.read_text())
    events = [Event(**item) for item in data["events"]]
    questions = [Question(**{**item, "expected_ids": tuple(item["expected_ids"]), "forbidden_ids": tuple(item.get("forbidden_ids", []))}) for item in data["questions"]]
    if len({event.id for event in events}) != len(events) or len({question.id for question in questions}) != len(questions):
        raise ValueError("fixture ids must be unique")
    known = {event.id for event in events}
    for question in questions:
        if not question.expected_ids or not set(question.expected_ids) <= known or not set(question.forbidden_ids) <= known:
            raise ValueError("expected and forbidden evidence must exist in the fixture")
        if set(question.expected_ids) & set(question.forbidden_ids):
            raise ValueError("evidence cannot be both expected and forbidden")
    if any(utc(question.at) < max(utc(event.at) for event in events if event.id in question.expected_ids) for question in questions):
        raise ValueError("expected evidence is in the future")

    cases = []
    with tempfile.TemporaryDirectory(prefix="fable-demo-") as directory:
        vault = Path(directory)
        ledger = journal(events, vault / "experience-ledger.sqlite3")
        for question in sorted(questions, key=lambda q: (q.at, q.id)):
            question.validate()
            visible = [event for event in events if utc(event.at) <= utc(question.at)]
            # Fresh store per cutoff: later corrections must never leak backward.
            case_vault = vault / question.id
            case_vault.mkdir()
            with open_memory_store(case_vault) as connection:
                ingest(connection, visible)
                actual = retrieve(connection, case_vault, question, limit)
                temporal = resolve_known_key(connection, question, limit)
            baseline = raw_baseline(visible, question, limit)
            recent = recent_baseline(visible, question, limit)
            expected = {memory_id(item) for item in question.expected_ids}
            forbidden = {memory_id(item) for item in question.forbidden_ids}
            def score(ids: list[str]) -> dict:
                return {"expected_recalled": bool(expected & set(ids)), "forbidden_recalled": bool(forbidden & set(ids)), "evidence_ids": ids}
            cases.append({"question": question.id, "alice_search": score(actual), "alice_temporal": score(temporal),
                          "raw_history": score(baseline), "recent_history": score(recent)})
    summary = {arm: {"expected_recalled": sum(case[arm]["expected_recalled"] for case in cases),
                     "forbidden_recalled": sum(case[arm]["forbidden_recalled"] for case in cases)}
               for arm in ("alice_search", "alice_temporal", "raw_history", "recent_history")}
    return {"alice_commit": ALICE_COMMIT, "fixture": fixture.name, "evidence_limit": limit, "case_count": len(cases),
            "summary": summary, "ledger": ledger, "cases": cases,
            "note": "Temporal resolution is given the correct topic key; the test does not measure how Fable would find that key. Search has a separate candidate-budget limit. No personality or judgment is measured."}
