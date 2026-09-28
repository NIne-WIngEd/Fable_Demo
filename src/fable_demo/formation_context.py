"""Bounded, source-linked input for a future Memory Formation Model.

This planner selects explicit context; it does not infer a topic, form a claim,
or let a learned component promote its own output into memory authority.
Packets describe current state at assembly time, never a historical snapshot.
"""

from __future__ import annotations

import hashlib
import json

from .memory_lane import MemoryLane
from .runtime import FableRuntime


def assemble_formation_context(runtime: FableRuntime, *, logical_id: str,
                               host_keys: tuple[str, ...] = ()) -> dict:
    """Supply one observation, its direct parent, and explicitly selected claims."""
    if len(host_keys) != len(set(host_keys)):
        raise ValueError("duplicate host keys")
    lane = MemoryLane(runtime)
    observation, reference, event = lane._observation(logical_id)
    parent = None
    if observation.relates_to:
        previous, previous_reference, previous_event = lane._observation(observation.relates_to)
        if previous_event.event_id not in event.parent_event_ids:
            raise ValueError("observation parent differs from ledger lineage")
        parent = {"logical_id": previous.logical_id, "event_id": previous_event.event_id,
                  "raw_reference_id": previous_reference.reference_id, "subject": previous.subject,
                  "kind": previous.kind, "text": previous.text, "occurred_at": previous.occurred_at}
    selected = {key: lane.current(key=key) for key in host_keys}
    packet = {
        "host_instance_id": runtime.scope.host_instance_id,
        "ledger_head": runtime.inspect()["ledger_head"],
        "observation": {"logical_id": logical_id, "event_id": event.event_id,
                        "raw_reference_id": reference.reference_id, "subject": observation.subject,
                        "kind": observation.kind, "text": observation.text,
                        "occurred_at": observation.occurred_at},
        "parent_observation": parent,
        "selected_current_host_claims": selected,
        "scope": "current assembly; not an as-of historical replay",
    }
    packet["packet_sha256"] = hashlib.sha256(json.dumps(packet, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return packet
