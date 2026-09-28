"""Current evidence/state assembly for the separately built personality model.

This is a rebuildable projection, not another authority store. It does not
infer a host trait, learn an assistant identity, or decide how to respond.
"""

from __future__ import annotations

import hashlib
import json

from .memory_lane import MemoryLane
from .runtime import FableRuntime


def assemble_current(runtime: FableRuntime, *, host_keys: tuple[str, ...]) -> dict:
    """Assemble the current state; historical snapshots need bitemporal authority."""
    if len(host_keys) != len(set(host_keys)):
        raise ValueError("duplicate host keys")
    audit = runtime.inspect()
    lane = MemoryLane(runtime)
    host = {key: lane.current(key=key) for key in host_keys}
    events = runtime.history()
    decisions = {event.logical_id: event for event in events if event.kind == "decision"}
    outcomes = [{"logical_id": event.logical_id, "decision_id": event.relates_to,
                 "text": event.text, "occurred_at": event.occurred_at}
                for event in events if event.kind == "outcome" and event.relates_to in decisions]
    observed = {
        subject: [{"logical_id": event.logical_id, "kind": event.kind, "text": event.text,
                   "occurred_at": event.occurred_at, "relates_to": event.relates_to}
                  for event in events if event.subject == subject]
        for subject in ("assistant_self", "relationship")
    }
    packet = {
        "host_instance_id": runtime.scope.host_instance_id,
        "ledger_head": audit["ledger_head"],
        "host_confirmed_claims": host,
        "assistant_self_observations": observed["assistant_self"],
        "relationship_observations": observed["relationship"],
        "decisions": [{"logical_id": item.logical_id, "text": item.text, "occurred_at": item.occurred_at}
                      for item in decisions.values()],
        "observed_outcomes": outcomes,
        "state": "evidence and confirmed claims; no native judgment yet",
    }
    packet["packet_sha256"] = hashlib.sha256(json.dumps(packet, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return packet
