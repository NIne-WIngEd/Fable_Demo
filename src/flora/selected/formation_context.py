"""Current A.L.I.C.E. MFM assembly over the selected durable memory fabric.

No formation weights, embeddings or learned selector are supplied here. The
exact-read selector is an upstream reference policy. Delivery records certify
opened input bytes and lineage, never model attention or memory authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Callable, Mapping

from cognitive_kernel.canonical import normalize_timestamp, require_identifier
from cognitive_kernel.contracts import ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from cognitive_kernel.formation_context_planner import (
    AssembledFormationContext, FormationPlanningRequest, FormationSelector,
    assemble_formation_context, select_all_registered,
)
from cognitive_kernel.formation_contracts import FormationEvidenceRef
from cognitive_kernel.formation_retrieval import (
    FormationCandidatePlane, FormationRoute, gather_formation_candidates,
)
from cognitive_kernel.formation_sources import (
    FormationReadReceipt, RegisteredFormationSource, RegisteredFormationStore,
    record_formation_read,
)

from .decision_outcome import RecordedEvent
from .experience import KurrentExperienceLog
from .formation_registry import (
    OwnerFormationSourceVerifier, RegisteredEncryptedFormationCustody,
    XTDBFormationSourceRegistry,
)
from .object_store import EncryptedObjectPlane, RawObjectReference


def register_experience_source(
    *, event_id: str, raw: RawObjectReference,
    registry: XTDBFormationSourceRegistry, log: KurrentExperienceLog,
    objects: EncryptedObjectPlane, role: str, modality: str,
    subject_ref: str | None = None, speaker_ref: str | None = None,
    source_item_ref: str | None = None, duplicate_group_ref: str | None = None,
    owner_verifier: OwnerFormationSourceVerifier | None = None,
) -> RegisteredFormationSource:
    """Trusted ingress supplies source meaning; Kurrent supplies availability.

    Unknown identity fields stay unknown. Observation time is never substituted
    for the physical commit time, including for an imported synthetic history.
    """
    entry = next((entry for entry in log.replay_committed()
                  if entry.event.event_id == event_id), None)
    if entry is None or entry.recorded_at is None:
        raise ValueError("formation registration lacks a committed timestamped source")
    event = entry.event
    evidence = FormationEvidenceRef(
        ref_id=event.event_id, scope=event.scope,
        authority_namespace_id=registry.authority_namespace_id,
        content_digest=event.content_digest, role=role, modality=modality,
        subject_ref=subject_ref, speaker_ref=speaker_ref,
        source_item_ref=source_item_ref, duplicate_group_ref=duplicate_group_ref,
        observed_at=event.occurred_at,
        recorded_at=normalize_timestamp(entry.recorded_at.isoformat(), "recorded_at"),
        parent_refs=event.parent_event_ids,
    )
    return registry.register(evidence=evidence, raw=raw, log=log,
                             objects=objects, owner_verifier=owner_verifier)


@dataclass(frozen=True)
class PreparedSelectedFormation:
    request: FormationPlanningRequest
    assembled: AssembledFormationContext = field(repr=False)
    receipt: FormationReadReceipt
    store: RegisteredFormationStore = field(repr=False, compare=False)

    def receipt_record(self) -> dict[str, object]:
        return {
            "schema": "flora-registered-formation-delivery-v1",
            "packet": self.assembled.packet.metadata_record(),
            "as_of": self.request.as_of,
            "purpose": self.store.purpose,
            "context_digest": self.receipt.context_digest,
            "opened": self.receipt.opened,
            "closure_refs": self.receipt.closure_refs,
            "receipt_sha256": self.receipt.receipt_sha256,
        }

    def revalidate(self) -> None:
        if record_formation_read(self.assembled, self.store) != self.receipt:
            raise ValueError("formation delivery differs from its current source receipt")


def prepare_selected_formation(
    *, request: FormationPlanningRequest,
    registry: XTDBFormationSourceRegistry, objects: EncryptedObjectPlane,
    permits: Callable[[RegisteredFormationSource, str], bool],
    routes: tuple[FormationRoute, ...] = (),
    providers: Mapping[str, FormationCandidatePlane] | None = None,
    selector: FormationSelector = select_all_registered,
    purpose: str = "memory_formation",
) -> PreparedSelectedFormation:
    """Route candidates, open authorized originals, and seal a read receipt."""
    if (request.scope != registry.scope or registry.scope != objects.scope
            or request.authority_namespace_id != registry.authority_namespace_id):
        raise ValueError("formation context crosses selected scope or authority")
    if not callable(permits):
        raise TypeError("formation requires an independent current permission policy")
    # Candidate IDs must enter through registered query/plane routing. A caller
    # cannot smuggle self-authored search hits into this selected entry point.
    if request.candidates:
        raise ValueError("selected formation needs independently routed candidates")
    routed = gather_formation_candidates(
        request=request, routes=routes, providers=providers or {})
    store = RegisteredFormationStore(
        scope=registry.scope, authority_namespace_id=registry.authority_namespace_id,
        registry=registry,
        custody=RegisteredEncryptedFormationCustody(registry=registry, objects=objects),
        permits=permits, purpose=purpose,
    )
    assembled = assemble_formation_context(routed, store, selector)
    receipt = record_formation_read(assembled, store)
    return PreparedSelectedFormation(routed, assembled, receipt, store)


def record_selected_formation_delivery(
    *, prepared: PreparedSelectedFormation, log: KurrentExperienceLog,
    objects: EncryptedObjectPlane, occurred_at: str,
    expected_revision: int, request_id: str,
) -> RecordedEvent:
    """Persist a metadata receipt in private custody and canonical Experience.

    Permission is rechecked at delivery. This function does not invoke a model
    or turn an input receipt into an accepted memory or judgment.
    """
    require_identifier(request_id, "request_id")
    packet = prepared.assembled.packet
    if not (packet.scope == log.scope == objects.scope == prepared.store.scope):
        raise ValueError("formation delivery crosses host scope")
    replayed = log.replay()
    if expected_revision != len(replayed) - 1:
        raise ValueError("stale expected Experience revision")
    by_id = {event.event_id: event for event in replayed}
    source_ids = tuple(ref.ref_id for ref in packet.evidence)
    if not set(source_ids).issubset(by_id):
        raise ValueError("formation delivery names an absent Experience source")
    delivery_time = normalize_timestamp(occurred_at, "occurred_at")
    for ref in packet.evidence:
        event = by_id[ref.ref_id]
        if (event.content_digest != ref.content_digest
                or event.parent_event_ids != ref.parent_refs
                or event.occurred_at != ref.observed_at):
            raise ValueError("formation delivery source differs from canonical Experience")
        if event.occurred_at > delivery_time:
            raise ValueError("formation delivery precedes a source observation")
    prepared.revalidate()
    material = json.dumps(prepared.receipt_record(), sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode()
    raw = objects.put(material)
    prepared.revalidate()
    event = ExperienceEvent.create(
        event_type="formation_context_delivery", scope=log.scope,
        occurred_at=delivery_time, content_digest=raw.plaintext_sha256,
        provenance=ProvenanceReference.create(
            provenance_type="derived_inference", source_reference_ids=source_ids,
            derivation_activity_id=request_id,
            responsible_component="registered_formation_context"),
        retention_class="ordinary_experience", storage_tier="raw_buffer",
        parent_event_ids=source_ids, payload_reference=raw.object_id,
    )
    log.append(event, expected_revision=expected_revision)
    return RecordedEvent(event, raw)
