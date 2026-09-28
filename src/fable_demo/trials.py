"""Freeze identical A.L.I.C.E. evidence packets for paired model evaluation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .context import prepare


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def freeze(spec_path: Path) -> dict:
    spec = json.loads(spec_path.read_text())
    fixture = spec_path.parent / spec["fixture"]
    ids = [item["id"] for item in spec["trials"]]
    if len(set(ids)) != len(ids):
        raise ValueError("trial ids must be unique")
    cases = []
    for item in spec["trials"]:
        packet = prepare(fixture, at=item["at"], topic=item["topic"], question=item["question"])
        cases.append({"trial_id": item["id"], "packet_sha256": hashlib.sha256(canonical(packet)).hexdigest(), "packet": packet})
    return {"source_fixture": spec["fixture"], "trials": cases,
            "note": "Every candidate receives exactly the same packet. No model output or behavioral score is included."}
