"""Freeze a synthetic 24-month correction history, independent of retrieval code."""

from __future__ import annotations

import json
from pathlib import Path


TOPICS = {
    "meeting_style": ("video calls", "written briefs", "short calls", "written briefs", "async notes"),
    "working_hours": ("early mornings", "late evenings", "afternoons", "early mornings", "late evenings"),
    "travel_style": ("quiet hotels", "short trips", "overnight trains", "quiet hotels", "short trips"),
    "learning_style": ("long lectures", "small examples", "written exercises", "small examples", "hands-on projects"),
}


def build() -> dict:
    events = []
    questions = []
    for topic, values in TOPICS.items():
        previous = None
        for revision, value in enumerate(values):
            month_index = 5 * revision
            year = 2024 + month_index // 12
            month = 1 + month_index % 12
            event_id = f"{topic}-{revision}"
            event = {
                "id": event_id, "at": f"{year}-{month:02d}-01T09:00:00Z",
                "kind": "assertion" if previous is None else "correction",
                "topic": topic,
                "text": f"I prefer {value}." if previous is None else f"Correction: I now prefer {value}.",
                "source": f"synthetic:{topic}:{year}-{month:02d}",
            }
            if previous is not None:
                event["supersedes"] = previous
            events.append(event)
            questions.append({
                "id": f"ask-{topic}-{revision}", "at": f"{year}-{month:02d}-15T09:00:00Z",
                "text": f"For {topic.replace('_', ' ')}, do I still prefer {values[0]}?",
                "topic": topic, "retrieval_query": "prefer", "expected_ids": [event_id],
                "forbidden_ids": [previous] if previous is not None else [],
            })
            previous = event_id
    return {"description": "Synthetic 20-month, four-topic correction diagnostic. Generated labels come from the scenario plan, not from A.L.I.C.E. retrieval.",
            "events": events, "questions": questions}


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "fixtures" / "longitudinal_v1.json"
    target.write_text(json.dumps(build(), indent=2) + "\n")
