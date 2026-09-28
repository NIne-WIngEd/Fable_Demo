"""A.L.I.C.E. Experience Ledger adapter for source, decision and outcome metadata.

The production ledger owns the append-only chain. Raw text stays in the
synthetic fixture, not in this metadata ledger.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .events import Event


def journal(events: list[Event], path: Path) -> dict:
    from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
    from cognitive_kernel.experience import ExperienceEvent
    from cognitive_kernel.ledger_store import open_experience_ledger

    scope = ProductHostScope.create(product_id="friday", host_instance_id="synthetic-demo", schema_version="1.0.0", encryption_domain="synthetic-demo")
    by_fixture_id: dict[str, str] = {}
    linked_outcomes = 0
    with open_experience_ledger(path, scope=scope, created_at="2025-01-01T00:00:00Z") as ledger:
        for item in sorted(events, key=lambda e: (e.at, e.id)):
            item.validate()
            reference = item.supersedes or item.decision_id
            if reference and reference not in by_fixture_id:
                raise ValueError(f"missing ledger reference: {reference}")
            provenance = ProvenanceReference.create(
                provenance_type="owner_correction" if item.kind == "correction" else "owner_attested_canonical",
                source_reference_ids=(item.source.replace(":", "-"),),
                responsible_component="fable-demo-fixture",
                supersedes_record_ids=(by_fixture_id[item.supersedes],) if item.supersedes else (),
            )
            envelope = ExperienceEvent.create(
                event_type=f"demo-{item.kind}", scope=scope, occurred_at=item.at,
                content_digest=hashlib.sha256(item.text.encode()).hexdigest(),
                provenance=provenance, retention_class="ordinary_experience", storage_tier="ledger",
                parent_event_ids=(by_fixture_id[reference],) if reference else (),
                outcome_reference_ids=(by_fixture_id[item.decision_id],) if item.decision_id else (),
            )
            ledger.append_event(envelope, committed_at=item.at)
            by_fixture_id[item.id] = envelope.event_id
            if item.kind == "outcome":
                stored = ledger.load_event(envelope.event_id)
                if stored.outcome_reference_ids != (by_fixture_id[item.decision_id],):
                    raise ValueError("outcome lost its decision reference")
                linked_outcomes += 1
        report = ledger.verify_integrity()
    payload = path.read_bytes()
    return {"entry_count": report.entry_count, "linked_outcomes": linked_outcomes,
            "integrity_verified": True,
            "plaintext_stored": any(item.text.encode() in payload for item in events)}
