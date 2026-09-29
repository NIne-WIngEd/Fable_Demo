"""Validate fictional longitudinal pilot material before model integration."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path

from .evaluation_protocol import INTERVENTIONS


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True,
                                     separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def load_pilot(path: str | Path) -> dict:
    record = json.loads(Path(path).read_text())
    if (record.get("schema") != "flora-synthetic-pilot-v1"
            or record.get("fictional") is not True
            or not record.get("host_id")):
        raise ValueError("pilot must be explicitly fictional and versioned")
    events = record.get("events")
    cases = record.get("cases")
    if not isinstance(events, list) or not isinstance(cases, list) or not events or not cases:
        raise ValueError("pilot needs events and cases")
    by_id = {}
    times = []
    for event in events:
        if (not isinstance(event, dict) or set(event) != {"id", "at", "kind", "text"}
                or not all(isinstance(event[key], str) and event[key]
                           for key in event)):
            raise ValueError("pilot event lacks exact source fields")
        if event["id"] in by_id:
            raise ValueError("pilot event IDs are reused")
        timestamp = datetime.fromisoformat(event["at"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("pilot event time needs a timezone")
        by_id[event["id"]] = event
        times.append(timestamp)
    if times != sorted(times) or len({time.year for time in times}) < 3:
        raise ValueError("pilot history needs chronological multi-year sources")
    case_ids = set()
    for case in cases:
        if (not isinstance(case, dict) or set(case) != {
                "case_id", "intervention", "intervention_event_id",
                "before_event_ids", "after_event_ids", "prompt",
                "expected_relation", "rubric"}):
            raise ValueError("pilot case is incomplete")
        if case["case_id"] in case_ids or not case["case_id"]:
            raise ValueError("pilot case IDs are reused")
        case_ids.add(case["case_id"])
        intervention = case["intervention_event_id"]
        before = case["before_event_ids"]
        after = case["after_event_ids"]
        if (case["intervention"] not in INTERVENTIONS
                or case["expected_relation"] not in {
                    "material_change", "stable_judgment"}
                or intervention not in by_id or not isinstance(before, list)
                or not before or any(item not in by_id for item in before)
                or len(set(before)) != len(before)
                or after != before + [intervention]
                or intervention in before
                or any(by_id[item]["at"] >= by_id[intervention]["at"]
                       for item in before)
                or not case["prompt"] or not case["rubric"]):
            raise ValueError("pilot case has invalid before/after intervention lineage")
        if (case["intervention"] == "irrelevant_correction") != (
                case["expected_relation"] == "stable_judgment"):
            raise ValueError("pilot relevance label contradicts intervention")
    return record


def case_history_digest(record: dict, case_id: str, phase: str) -> str:
    if phase not in {"before", "after"}:
        raise ValueError("unknown pilot phase")
    case = next(item for item in record["cases"]
                if item["case_id"] == case_id)
    events = {item["id"]: item for item in record["events"]}
    ids = case[f"{phase}_event_ids"]
    return _digest({"host_id": record["host_id"],
                    "sources": [events[item] for item in ids]})
