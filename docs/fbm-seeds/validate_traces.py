"""Validate FloRA procedure traces against A.L.I.C.E. trace schema v0.1.

This checks audit-record shape only. It cannot certify trace claims, privacy,
authority, or suitability as a supervised FBM case.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
from typing import Iterable


TEXT_FIELDS = frozenset({
    "trace_id", "timestamp_utc", "actor", "project_stage", "operation_type",
    "goal", "procedure", "authority", "validation", "result",
    "failure_or_lesson", "privacy",
})
LIST_FIELDS = frozenset({
    "input_classes", "input_refs", "constraints", "decision_criteria",
    "output_classes", "output_refs", "fbm_capabilities", "training_value",
})
RESULTS = frozenset({"success", "partial", "failed", "superseded", "historical"})
TRAINING_VALUES = frozenset({
    "positive_example", "negative_example", "contrastive_pair", "procedure_only",
    "evaluation_case",
})


def validate_rows(rows: Iterable[dict]) -> int:
    """Reject incomplete/ambiguous records; return the checked row count."""
    seen = set()
    count = 0
    for row in rows:
        count += 1
        if not isinstance(row, dict):
            raise ValueError(f"trace {count}: expected an object")
        missing = (TEXT_FIELDS | LIST_FIELDS) - row.keys()
        if missing:
            raise ValueError(f"trace {count}: missing fields {sorted(missing)}")
        for field in TEXT_FIELDS:
            if not isinstance(row[field], str) or not row[field].strip():
                raise ValueError(f"trace {count}: {field} must be nonempty text")
        for field in LIST_FIELDS:
            values = row[field]
            if (not isinstance(values, list)
                    or any(not isinstance(value, str) or not value.strip()
                           for value in values)
                    or (field not in {"input_refs", "output_refs"} and not values)):
                raise ValueError(f"trace {count}: {field} must contain text values")
        if row["trace_id"] in seen:
            raise ValueError(f"duplicate trace_id: {row['trace_id']}")
        seen.add(row["trace_id"])
        try:
            timestamp = datetime.fromisoformat(
                row["timestamp_utc"].replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"trace {count}: timestamp_utc is not ISO-8601") from exc
        if timestamp.tzinfo is None or timestamp.utcoffset() != timedelta(0):
            raise ValueError(f"trace {count}: timestamp_utc must be UTC")
        if row["result"] not in RESULTS:
            raise ValueError(f"trace {count}: unknown result")
        if not set(row["training_value"]).issubset(TRAINING_VALUES):
            raise ValueError(f"trace {count}: unknown training_value")
    if not count:
        raise ValueError("no process traces found")
    return count


def load_rows(directory: Path) -> list[dict]:
    rows = []
    for path in sorted(directory.glob("*.jsonl")):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if not line.strip():
                raise ValueError(f"{path.name}:{number}: empty trace row")
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path.name}:{number}: invalid JSON") from exc
    return rows


if __name__ == "__main__":
    directory = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
    count = validate_rows(load_rows(directory))
    print(f"Validated {count} procedure traces; linked-case readiness is not certified.")
