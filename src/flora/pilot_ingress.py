"""Two-stage fictional pilot intake on selected raw/Experience planes.

Before must be materialized and evaluated before an intervention is appended.
All events carry synthetic provenance; none is owner-attested history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent

from .pilot_fixture import case_history_digest, load_pilot
from .selected.experience import KurrentExperienceLog
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
                       objects: EncryptedObjectPlane) -> PilotCheckpoint:
    record = load_pilot(path)
    case = _case(record, checkpoint.case_id)
    _scope(record, checkpoint.case_id, checkpoint.scope, log, objects)
    if (checkpoint.history_sha256 != case_history_digest(
            record, checkpoint.case_id, "before")
            or tuple(checkpoint.event_by_source_id) != tuple(case["before_event_ids"])
            or [event.event_id for event in log.replay()]
            != list(checkpoint.event_by_source_id.values())):
        raise ValueError("pilot intervention does not follow its exact before stream")
    source = next(event for event in record["events"]
                  if event["id"] == case["intervention_event_id"])
    if case["intervention"] == "relevant_correction":
        parents = (checkpoint.event_by_source_id["mira-2022-family"],)
    elif case["intervention"] == "irrelevant_correction":
        parents = (checkpoint.event_by_source_id["mira-2021-coffee"],)
    else:
        parents = (checkpoint.event_by_source_id["mira-2025-commute"],
                   checkpoint.event_by_source_id["mira-2025-sleep"])
    refs = dict(checkpoint.references)
    event = _append(source, parents=parents, scope=checkpoint.scope,
                    log=log, objects=objects, refs=refs,
                    revision=len(checkpoint.event_by_source_id) - 1)
    by_id = dict(checkpoint.event_by_source_id)
    by_id[source["id"]] = event.event_id
    return PilotCheckpoint(checkpoint.case_id, checkpoint.scope, by_id, refs,
                           case_history_digest(record, checkpoint.case_id, "after"))
