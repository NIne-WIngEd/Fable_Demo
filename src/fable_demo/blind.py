"""Build a blind paired review from independently submitted candidate outputs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def pair(frozen_path: Path, first_path: Path, second_path: Path, *, seed: str) -> tuple[dict, dict]:
    if not seed:
        raise ValueError("a review seed is required")
    frozen = json.loads(frozen_path.read_text())
    expected = {item["trial_id"]: item["packet_sha256"] for item in frozen["trials"]}
    if len(expected) != len(frozen["trials"]):
        raise ValueError("duplicate frozen trial id")

    def submission(path: Path) -> dict:
        data = json.loads(path.read_text())
        if not isinstance(data, list):
            raise ValueError("submission must be a JSON array")
        result = {}
        for item in data:
            trial_id = item["trial_id"]
            if trial_id in result or trial_id not in expected:
                raise ValueError("duplicate or unknown submitted trial")
            if item["packet_sha256"] != expected[trial_id] or not isinstance(item["response"], str) or not item["response"].strip():
                raise ValueError("packet hash mismatch or empty response")
            result[trial_id] = item["response"]
        if set(result) != set(expected):
            raise ValueError("both arms must answer every trial")
        return result

    first = submission(first_path)
    second = submission(second_path)
    review = []
    key = {}
    for trial_id in expected:
        flip = int(hashlib.sha256(f"{seed}:{trial_id}".encode()).hexdigest(), 16) % 2 == 1
        responses = [second[trial_id], first[trial_id]] if flip else [first[trial_id], second[trial_id]]
        review.append({"trial_id": trial_id, "packet_sha256": expected[trial_id], "A": responses[0], "B": responses[1]})
        key[trial_id] = {"A": "second" if flip else "first", "B": "first" if flip else "second"}
    return {"pairs": review, "review_instruction": "Assess response behavior and use of evidence; keep the key separate until ratings are complete."}, key
