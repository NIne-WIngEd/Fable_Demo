"""Two-stage fictional pilot intake on selected raw/Experience planes.

Before must be materialized and evaluated before an intervention is appended.
All events carry synthetic provenance; none is owner-attested history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import base64
import hashlib
import json
from pathlib import Path
from typing import Sequence

from cognitive_kernel.canonical import canonical_sha256, require_sha256
from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent

from .pilot_fixture import case_history_digest, load_pilot
from .selected.experience import KurrentExperienceLog
from .selected.decision_outcome import RecordedEvent, record_outcome_observation
from .selected.object_store import EncryptedObjectPlane, RawObjectReference


@dataclass(frozen=True)
class PilotCheckpoint:
    case_id: str
    scope: ProductHostScope
    event_by_source_id: dict[str, str]
    references: dict[str, RawObjectReference] = field(repr=False)
    history_sha256: str


def _case(record: dict, case_id: str) -> dict:
    return next(item for item in record["cases"] if item["case_id"] == case_id)


def _scope(record: dict, case_id: str, scope: ProductHostScope,
           log: KurrentExperienceLog, objects: EncryptedObjectPlane) -> None:
    if (scope.product_id != "friday"
            or scope.host_instance_id != f"{record['host_id']}-{case_id}"
            or log.scope != scope or objects.scope != scope):
        raise ValueError("fictional pilot needs an isolated selected host scope")


def _append(event: dict, *, parents: tuple[str, ...],
            scope: ProductHostScope, log: KurrentExperienceLog,
            objects: EncryptedObjectPlane,
            refs: dict[str, RawObjectReference],
            revision: int) -> ExperienceEvent:
    raw = objects.put(event["text"].encode())
    kind = {"owner_report": "observation",
            "owner_correction": "correction",
            "independent_outcome_report": "outcome_observation"}[event["kind"]]
    experience = ExperienceEvent.create(
        event_type=kind, scope=scope, occurred_at=event["at"],
        content_digest=raw.plaintext_sha256,
        provenance=ProvenanceReference.create(
            provenance_type="generated_reconstruction",
            source_reference_ids=(event["id"],),
            derivation_activity_id="flora-fictional-pilot-v1",
            responsible_component="flora-synthetic-pilot"),
        retention_class="ordinary_experience", storage_tier="raw_buffer",
        payload_reference=raw.object_id, parent_event_ids=parents)
    log.append(experience, expected_revision=revision)
    refs[raw.object_id] = raw
    return experience


def _before_phase_records(
    *, checkpoint: PilotCheckpoint, replayed: Sequence[ExperienceEvent],
    records: Sequence[RecordedEvent], objects: EncryptedObjectPlane,
    intervention_at: str, decision_event_id: str | None,
) -> tuple[dict[str, RawObjectReference], str | None]:
    """Verify a closed, source-bound before judgment path after its exact prefix.

    A ledger may also contain the context receipt and decision produced during
    the before phase. Those are outputs, not new authorized host history. They
    must be explicitly supplied, match replay, and all lead to the selected
    final decision. This never qualifies the declared judgment producer.
    """
    prefix_ids = tuple(checkpoint.event_by_source_id.values())
    if (tuple(event.event_id for event in replayed[:len(prefix_ids)]) != prefix_ids
            or tuple(replayed[len(prefix_ids):]) != tuple(item.event for item in records)):
        raise ValueError("pilot intervention does not follow its exact before stream")
    refs = dict(checkpoint.references)
    known = {event.event_id: event for event in replayed[:len(prefix_ids)]}
    phase_ids: set[str] = set()
    cutoff = datetime.fromisoformat(intervention_at.replace("Z", "+00:00"))
    last_source_at = max(datetime.fromisoformat(event.occurred_at.replace("Z", "+00:00"))
                         for event in known.values())
    for item in records:
        event, raw = item.event, item.raw
        event.validate()
        if (event.scope != checkpoint.scope or raw.scope != checkpoint.scope
                or event.event_type not in {"context_delivery", "decision"}
                or event.event_id in known or not event.parent_event_ids
                or not set(event.parent_event_ids).issubset(known)
                or event.payload_reference != raw.object_id):
            raise ValueError("pilot before records must be source-bound context or decisions")
        at = datetime.fromisoformat(event.occurred_at.replace("Z", "+00:00"))
        if (not last_source_at <= at < cutoff or any(
                datetime.fromisoformat(known[parent].occurred_at.replace("Z", "+00:00")) > at
                for parent in event.parent_event_ids)):
            raise ValueError("pilot before record reaches intervention time or has invalid causal order")
        payload = objects.get(raw)
        if hashlib.sha256(payload).hexdigest() != event.content_digest:
            raise ValueError("pilot before record differs from its encrypted payload")
        material = json.loads(payload)
        if event.event_type == "decision":
            if (set(material) != {"schema", "verdict_base64", "consumed_event_ids",
                                  "model_artifact_sha256"}
                    or material["schema"] != "flora-decision-v1"
                    or len(set(material["consumed_event_ids"])) != len(material["consumed_event_ids"])
                    or set(material["consumed_event_ids"]) != set(event.parent_event_ids)
                    or not base64.b64decode(material["verdict_base64"], validate=True)):
                raise ValueError("pilot before decision payload differs from its source lineage")
            require_sha256(material["model_artifact_sha256"], "model_artifact_sha256")
        else:
            if (material.get("schema") != "flora-context-delivery-v1"
                    or material.get("receipt_sha256") != canonical_sha256(
                        {key: value for key, value in material.items() if key != "receipt_sha256"})):
                raise ValueError("pilot before context receipt is unbound")
            delivered_sources = {source for item_record in material["items"]
                                 for source in item_record["source_event_ids"]}
            delivered_sources.update(item_record["approval_event_id"]
                                     for item_record in material["items"]
                                     if item_record.get("approval_event_id") is not None)
            if delivered_sources != set(event.parent_event_ids):
                raise ValueError("pilot before context receipt differs from its source lineage")
        if (event.provenance.provenance_type != "derived_inference"
                or set(event.provenance.source_reference_ids) != set(event.parent_event_ids)):
            raise ValueError("pilot before record provenance differs from its source lineage")
        refs[raw.object_id] = raw
        known[event.event_id] = event
        phase_ids.add(event.event_id)
    if records:
        selected_id = decision_event_id or records[-1].event.event_id
        if (selected_id != records[-1].event.event_id
                or records[-1].event.event_type != "decision"):
            raise ValueError("pilot before phase must end with its selected decision")
        ancestors: set[str] = set()
        pending = [selected_id]
        while pending:
            event_id = pending.pop()
            if event_id in ancestors:
                continue
            ancestors.add(event_id)
            pending.extend(known[event_id].parent_event_ids)
        if not phase_ids.issubset(ancestors):
            raise ValueError("pilot before phase contains an unrelated result")
        return refs, selected_id
    if decision_event_id is not None:
        raise ValueError("pilot before decision is absent from its declared records")
    return refs, None


def materialize_before(*, path: str | Path, case_id: str,
                       scope: ProductHostScope, log: KurrentExperienceLog,
                       objects: EncryptedObjectPlane) -> PilotCheckpoint:
    record = load_pilot(path)
    case = _case(record, case_id)
    _scope(record, case_id, scope, log, objects)
    if log.replay():
        raise ValueError("pilot before history needs an empty case stream")
    sources = {event["id"]: event for event in record["events"]}
    by_id: dict[str, str] = {}
    refs: dict[str, RawObjectReference] = {}
    for revision, source_id in enumerate(case["before_event_ids"], start=-1):
        event = _append(sources[source_id], parents=(), scope=scope, log=log,
                        objects=objects, refs=refs, revision=revision)
        by_id[source_id] = event.event_id
    return PilotCheckpoint(case_id, scope, by_id, refs,
                           case_history_digest(record, case_id, "before"))


def apply_intervention(*, path: str | Path, checkpoint: PilotCheckpoint,
                       log: KurrentExperienceLog,
                       objects: EncryptedObjectPlane,
                       before_records: Sequence[RecordedEvent] = (),
                       decision_event_id: str | None = None) -> PilotCheckpoint:
    record = load_pilot(path)
    case = _case(record, checkpoint.case_id)
    _scope(record, checkpoint.case_id, checkpoint.scope, log, objects)
    if (checkpoint.history_sha256 != case_history_digest(
            record, checkpoint.case_id, "before")
            or tuple(checkpoint.event_by_source_id) != tuple(case["before_event_ids"])):
        raise ValueError("pilot intervention does not follow its exact before stream")
    source = next(event for event in record["events"]
                  if event["id"] == case["intervention_event_id"])
    replayed = log.replay()
    sources = {event["id"]: event for event in record["events"]}
    if len(replayed) < len(case["before_event_ids"]):
        raise ValueError("pilot intervention does not follow its exact before stream")
    for source_id, experience in zip(case["before_event_ids"], replayed):
        original = sources[source_id]
        raw = checkpoint.references.get(experience.payload_reference or "")
        if (raw is None or raw.scope != checkpoint.scope
                or objects.get(raw) != original["text"].encode()
                or raw.plaintext_sha256 != experience.content_digest
                or datetime.fromisoformat(experience.occurred_at.replace("Z", "+00:00"))
                != datetime.fromisoformat(original["at"].replace("Z", "+00:00"))
                or experience.event_type != "observation"
                or experience.parent_event_ids
                or experience.provenance.provenance_type != "generated_reconstruction"
                or experience.provenance.source_reference_ids != (source_id,)
                or experience.provenance.responsible_component != "flora-synthetic-pilot"):
            raise ValueError("pilot intervention does not follow its exact before sources")
    refs, selected_decision_id = _before_phase_records(
        checkpoint=checkpoint, replayed=replayed, records=before_records,
        objects=objects, intervention_at=source["at"],
        decision_event_id=decision_event_id)
    if case["intervention"] == "relevant_correction":
        parents = (checkpoint.event_by_source_id["mira-2022-family"],)
    elif case["intervention"] == "irrelevant_correction":
        parents = (checkpoint.event_by_source_id["mira-2021-coffee"],)
    else:
        if decision_event_id is None or selected_decision_id != decision_event_id:
            raise ValueError("pilot outcome requires its recorded before decision")
        outcome = record_outcome_observation(
            log=log, objects=objects, decision_event_id=decision_event_id,
            observation=source["text"].encode(),
            observation_provenance=ProvenanceReference.create(
                provenance_type="generated_reconstruction",
                source_reference_ids=(source["id"],),
                derivation_activity_id="flora-fictional-pilot-v1",
                responsible_component="flora-synthetic-pilot"),
            occurred_at=source["at"], expected_revision=len(replayed) - 1)
        event = outcome.event
        refs[outcome.raw.object_id] = outcome.raw
    if case["intervention"] != "observed_outcome":
        event = _append(source, parents=parents, scope=checkpoint.scope,
                        log=log, objects=objects, refs=refs,
                        revision=len(replayed) - 1)
    by_id = dict(checkpoint.event_by_source_id)
    by_id[source["id"]] = event.event_id
    return PilotCheckpoint(checkpoint.case_id, checkpoint.scope, by_id, refs,
                           case_history_digest(record, checkpoint.case_id, "after"))
