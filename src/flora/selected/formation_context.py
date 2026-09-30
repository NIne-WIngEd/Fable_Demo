"""Current A.L.I.C.E. MFM assembly over the selected durable memory fabric.

No formation weights, embeddings or learned selector are supplied here. The
exact-read selector is an upstream reference policy. Delivery records certify
opened input bytes and lineage, never model attention or memory authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Callable, Mapping

from cognitive_kernel.canonical import canonical_json_bytes, normalize_timestamp, require_identifier
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


class _CurrentFormationMetadata:
    """Actual upstream-resolved registrations and current use, no raw reread."""
    def __init__(self, *, store, objects, resolved):
        if not resolved:
            raise ValueError("formation has no actual resolved source closure")
        self.store, self.objects, self.registry, self.permits = store, objects, store.registry, store.permits
        self.scope_record = canonical_json_bytes(store.scope.metadata_record())
        self.namespace, self.purpose = store.authority_namespace_id, store.purpose
        self.policy = getattr(self.permits, "__self__", None)
        self.action_reader = getattr(self.policy, "current_action", None)
        self.sources = dict(resolved)
        self.raw_records, self.raw_references, self.grants = {}, {}, {}
        for ref_id, source in self.sources.items():
            if store._lookup(ref_id) != source:
                raise PermissionError("formation source changed after upstream resolution")
            raw, reference = self.registry.raw_metadata(source.object_ref), self.registry.raw_reference(source.object_ref)
            if (raw is None or reference is None or reference.scope != store.scope
                    or reference.object_id != source.object_ref
                    or reference.plaintext_sha256 != source.evidence.content_digest
                    or raw["object_namespace"] != objects.namespace):
                raise PermissionError("formation source has no exact durable raw-reference metadata")
            self.raw_records[ref_id] = canonical_json_bytes(raw)
            self.raw_references[ref_id] = reference
        # Grants follow potentially slow source/raw-reference metadata reads.
        if callable(self.action_reader):
            for ref_id in self.sources:
                action = self.action_reader(ref_id, self.purpose)
                if action is None or action.decision != "allow":
                    raise PermissionError("formation source has no current exact grant")
                self.grants[ref_id] = canonical_json_bytes(action.metadata_record())
        self.metadata_current()

    def _bindings(self):
        if (self.store.registry is not self.registry or self.store.permits is not self.permits
                or self.store.purpose != self.purpose or self.store.authority_namespace_id != self.namespace
                or self.registry.authority_namespace_id != self.namespace
                or canonical_json_bytes(self.store.scope.metadata_record()) != self.scope_record
                or not self.store.scope == self.registry.scope == self.objects.scope):
            raise PermissionError("formation current registered authority binding changed")
        if self.policy is not None and hasattr(self.policy, "registry") and self.policy.registry is not self.registry:
            raise PermissionError("formation current permission registry changed")

    def metadata_current(self) -> None:
        self._bindings()
        for ref_id, source in self.sources.items():
            if (self.store._lookup(ref_id) != source
                    or canonical_json_bytes(self.registry.raw_metadata(source.object_ref)) != self.raw_records[ref_id]
                    or self.registry.raw_reference(source.object_ref) != self.raw_references[ref_id]):
                raise PermissionError("formation current source/raw-reference metadata changed")
        self._bindings()
        for ref_id, source in self.sources.items():
            # This is the actual RegisteredFormationStore predicate and policy,
            # including its current parent closure, not a captured allow bit.
            if self.permits(source, self.purpose) is not True:
                raise PermissionError("formation current source/parent permission was withdrawn")
        # Keep selected current grants after slower metadata/predicate work.
        if callable(self.action_reader):
            for ref_id in self.sources:
                action = self.action_reader(ref_id, self.purpose)
                if (action is None or action.decision != "allow"
                        or canonical_json_bytes(action.metadata_record()) != self.grants[ref_id]):
                    raise PermissionError("formation current source grant changed")
        self._bindings()

    def permits_private_read(self) -> bool:
        self.metadata_current()
        return True


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
    _metadata_guard: Callable[[], None] | None = field(default=None, repr=False, compare=False)

    def metadata_current(self) -> None:
        """Current selected metadata/purpose barrier without original bytes."""
        if self._metadata_guard is None:
            raise PermissionError("formation preparation has no actual metadata barrier")
        self._metadata_guard()

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
        if self._metadata_guard is not None:
            self.metadata_current()
        if record_formation_read(self.assembled, self.store) != self.receipt:
            raise ValueError("formation delivery differs from its current source receipt")
        if self._metadata_guard is not None:
            self.metadata_current()


def prepare_selected_formation(
    *, request: FormationPlanningRequest,
    registry: XTDBFormationSourceRegistry, objects: EncryptedObjectPlane,
    permits: Callable[[RegisteredFormationSource, str], bool],
    routes: tuple[FormationRoute, ...] = (),
    providers: Mapping[str, FormationCandidatePlane] | None = None,
    selector: FormationSelector = select_all_registered,
    purpose: str = "memory_formation",
    before_private_assembly: Callable[[Callable[[], None]], None] | None = None,
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
    if before_private_assembly is not None and not callable(before_private_assembly):
        raise TypeError("formation before-private assembly gate must be callable")
    resolved = {}
    original_resolve, original_read = store.resolve, store.read
    current = None
    def resolve(ref_id):
        ref = original_resolve(ref_id)
        if ref is not None:
            source = store._lookup(ref_id)
            if source is None or source.evidence != ref:
                raise PermissionError("formation upstream source changed during metadata resolution")
            if ref_id in resolved and resolved[ref_id] != source:
                raise PermissionError("formation upstream registration changed")
            resolved[ref_id] = source
        return ref
    def read(ref):
        nonlocal current
        if current is None:
            # The actual upstream assembler reaches its first read only after
            # routing, selector validation and complete selected parent closure.
            # Use that real boundary rather than run a second selector/planner.
            current = _CurrentFormationMetadata(store=store, objects=objects, resolved=resolved)
            from .personal_artifact_custody import _SourceAuthorizedObjectReads
            store.custody = RegisteredEncryptedFormationCustody(registry=registry,
                objects=_SourceAuthorizedObjectReads(objects, current.permits_private_read))
            if before_private_assembly is not None:
                if before_private_assembly(current.metadata_current) is not None:
                    raise PermissionError("formation before-private assembly gate refused")
            current.metadata_current()
        source = current.sources.get(ref.ref_id)
        if source is None or source.evidence != ref:
            raise PermissionError("formation read is outside actual upstream resolved closure")
        current.metadata_current()
        material = original_read(ref)
        current.metadata_current()
        return material
    store.resolve, store.read = resolve, read
    assembled = assemble_formation_context(routed, store, selector)
    if current is None:
        # The upstream contract requires nonempty mandatory experience, hence
        # at least one real read. Do not return an unqualified empty preparation.
        raise PermissionError("formation assembly produced no actual private source read")
    receipt = record_formation_read(assembled, store)
    current.metadata_current()
    return PreparedSelectedFormation(routed, assembled, receipt, store, current.metadata_current)


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
        if ref.recorded_at is None or ref.recorded_at > delivery_time:
            raise ValueError("formation delivery precedes physical source availability")
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
