"""Durable, source-bound MFM proposal outputs on the selected fabric.

Outputs and proposed values are supplied externally. Their immutable lineage
grants no Claim authority, proves no inference, and qualifies no model artifact.
Kurrent append precedes XTDB registration; exact retries recover that boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Protocol

from cognitive_kernel.canonical import canonical_sha256, normalize_timestamp, require_identifier, require_sha256
from cognitive_kernel.claim_contracts import CanonicalTaggedValue
from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from cognitive_kernel.formation_contracts import (
    FormationContextPacket, FormationProposal, MemoryProposalBundle, validate_formation_binding,
)
from cognitive_kernel.formation_sources import RegisteredFormationStore

from .claims import _dml_placeholder, _record_json, _rows, configure_xtdb_connection
from .decision_outcome import RecordedEvent
from .experience import KurrentExperienceLog
from .formation_context import PreparedSelectedFormation
from .formation_registry import _evidence_from_record
from .object_store import EncryptedObjectPlane, RawObjectReference

_TABLE = "flora_formation_proposal_candidates"


class FormationValueResolver(Protocol):
    """Independent proposed-value custody; resolution never accepts a claim."""

    def resolve(self, scope: ProductHostScope, authority_namespace_id: str,
                value_ref: str) -> CanonicalTaggedValue | None: ...


@dataclass(frozen=True)
class RecordedFormationCandidate:
    event: ExperienceEvent
    raw: RawObjectReference
    bundle_sha256: str


@dataclass(frozen=True)
class RecoveredFormationCandidate:
    bundle: MemoryProposalBundle
    packet: FormationContextPacket
    delivery_record: dict[str, object]
    values: tuple[tuple[str, CanonicalTaggedValue], ...] = field(repr=False)
    recorded: RecordedFormationCandidate


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _raw_record(raw: RawObjectReference, objects: EncryptedObjectPlane) -> dict[str, object]:
    if raw.scope != objects.scope:
        raise ValueError("formation candidate raw custody crosses scope")
    objects.get(raw)
    sealed = objects.backend.get_object(objects.namespace, raw.object_id)
    return {"scope": raw.scope.metadata_record(), "object_id": raw.object_id,
            "plaintext_sha256": raw.plaintext_sha256, "size": raw.size,
            "object_namespace": objects.namespace, "cipher_format": "FBO1-AES-256-GCM",
            "ciphertext_sha256": hashlib.sha256(sealed).hexdigest(), "ciphertext_size": len(sealed)}


def _read_raw(record: dict[str, object], objects: EncryptedObjectPlane) -> tuple[RawObjectReference, bytes]:
    if (record["scope"] != objects.scope.metadata_record()
            or record["object_namespace"] != objects.namespace
            or record["cipher_format"] != "FBO1-AES-256-GCM"):
        raise ValueError("formation candidate stored raw custody crosses scope or format")
    require_sha256(record["object_id"], "object_id")
    require_sha256(record["plaintext_sha256"], "plaintext_sha256")
    require_sha256(record["ciphertext_sha256"], "ciphertext_sha256")
    if (isinstance(record["size"], bool) or not isinstance(record["size"], int)
            or record["size"] < 0 or isinstance(record["ciphertext_size"], bool)
            or not isinstance(record["ciphertext_size"], int) or record["ciphertext_size"] < 32):
        raise ValueError("formation candidate raw custody has invalid sizes")
    raw = RawObjectReference(objects.scope, record["object_id"], record["plaintext_sha256"], record["size"])
    sealed = objects.backend.get_object(objects.namespace, raw.object_id)
    if (len(sealed) != record["ciphertext_size"]
            or hashlib.sha256(sealed).hexdigest() != record["ciphertext_sha256"]):
        raise ValueError("formation candidate ciphertext differs from durable custody")
    return raw, objects.get(raw)


def _packet_from_record(record: dict[str, object]) -> FormationContextPacket:
    packet = FormationContextPacket(
        scope=ProductHostScope.create(**record["scope"]),
        authority_namespace_id=record["authority_namespace_id"],
        experience_refs=tuple(record["experience_refs"]),
        evidence=tuple(_evidence_from_record(ref) for ref in record["evidence"]),
        schema_version=record["schema_version"])
    packet.validate()
    if packet.metadata_record() != record:
        raise ValueError("formation candidate packet metadata changed")
    return packet


def _bundle_from_record(record: dict[str, object]) -> MemoryProposalBundle:
    proposals = []
    for proposal_record in record["proposals"]:
        material = dict(proposal_record)
        material["evidence_refs"] = tuple(material["evidence_refs"])
        material["contradicts"] = tuple(material["contradicts"])
        proposals.append(FormationProposal(**material))
    bundle = MemoryProposalBundle(
        scope=ProductHostScope.create(**record["scope"]),
        authority_namespace_id=record["authority_namespace_id"],
        bundle_id=record["bundle_id"], experience_refs=tuple(record["experience_refs"]),
        context_digest=record["context_digest"], model_artifact_digest=record["model_artifact_digest"],
        inference_run_id=record["inference_run_id"], proposals=tuple(proposals),
        schema_version=record["schema_version"])
    bundle.validate()
    if bundle.metadata_record() != record:
        raise ValueError("formation candidate bundle metadata changed")
    return bundle


def _check_sources(packet: FormationContextPacket, delivery_record: dict[str, object],
                   store: RegisteredFormationStore) -> None:
    """Check receipt lineage and open exact sources through current policy."""
    if (store.scope != packet.scope or store.authority_namespace_id != packet.authority_namespace_id
            or delivery_record["schema"] != "flora-registered-formation-delivery-v1"
            or delivery_record["purpose"] != store.purpose
            or delivery_record["packet"] != packet.metadata_record()
            or delivery_record["context_digest"] != packet.content_digest()):
        raise ValueError("formation candidate source store or delivery packet differs")
    as_of = delivery_record["as_of"]
    cutoff = normalize_timestamp(as_of, "as_of") if as_of is not None else None
    if (cutoff != as_of or any(
            ref.recorded_at is None or ref.observed_at is None
            or (cutoff is not None and (ref.recorded_at > cutoff or ref.observed_at > cutoff))
            for ref in packet.evidence)):
        raise ValueError("formation candidate receipt admits evidence beyond its historical cutoff")
    opened = delivery_record["opened"]
    closure = delivery_record["closure_refs"]
    if (len(opened) != len(packet.evidence)
            or not set(closure).issubset({ref.ref_id for ref in packet.evidence})
            or canonical_sha256({"context_digest": packet.content_digest(), "opened": opened,
                                 "closure_refs": closure}) != delivery_record["receipt_sha256"]):
        raise ValueError("formation candidate read receipt differs from source lineage")
    for ref, receipt_item in zip(packet.evidence, opened):
        source = store.registry.lookup(ref.ref_id)
        if (source is None or source.evidence != ref or receipt_item[0] != ref.ref_id
                or receipt_item[1] != ref.content_digest or receipt_item[2] != source.registration_sha256):
            raise ValueError("formation candidate source registration changed")
        if hashlib.sha256(store.read(ref)).hexdigest() != ref.content_digest:
            raise ValueError("formation candidate source bytes changed")
    # Opening a later source can race revocation of an earlier one. Recheck
    # the entire delivered set before exposing the candidate derived from it.
    for ref, receipt_item in zip(packet.evidence, opened):
        current = store.registry.lookup(ref.ref_id)
        if (current is None or current.evidence != ref
                or current.registration_sha256 != receipt_item[2]
                or not store.permits_formation(ref)):
            raise ValueError("formation candidate source changed or permission was revoked during reads")


def _check_delivery(*, event: ExperienceEvent, raw: RawObjectReference,
                    delivery_record: dict[str, object], packet: FormationContextPacket,
                    replayed: list[ExperienceEvent], objects: EncryptedObjectPlane) -> None:
    source_ids = {ref.ref_id for ref in packet.evidence}
    if (event not in replayed or event.scope != packet.scope or raw.scope != packet.scope
            or event.event_type != "formation_context_delivery"
            or event.payload_reference != raw.object_id or event.content_digest != raw.plaintext_sha256
            or set(event.parent_event_ids) != source_ids
            or set(event.provenance.source_reference_ids) != source_ids
            or event.provenance.provenance_type != "derived_inference"
            or objects.get(raw) != _json_bytes(delivery_record)):
        raise ValueError("formation candidate lacks its exact replayed delivery receipt")
    before = {item.event_id: item for item in replayed[:replayed.index(event)]}
    if delivery_record["as_of"] is not None and delivery_record["as_of"] > event.occurred_at:
        raise ValueError("formation candidate delivery predates its declared availability cutoff")
    for ref in packet.evidence:
        source = before.get(ref.ref_id)
        if (source is None or source.scope != packet.scope
                or source.content_digest != ref.content_digest
                or source.parent_event_ids != ref.parent_refs
                or source.occurred_at != ref.observed_at or source.occurred_at > event.occurred_at
                or ref.recorded_at is None or ref.recorded_at > event.occurred_at):
            raise ValueError("formation candidate delivery has missing, changed, or later source lineage")


class XTDBFormationProposalCandidates:
    """Immutable supplied output receipts, with no canonical memory effect."""

    def __init__(self, *, scope: ProductHostScope, authority_namespace_id: str, connection: Any):
        scope.validate()
        self.scope = scope
        self.authority_namespace_id = require_identifier(authority_namespace_id, "authority_namespace_id")
        self.connection = connection
        configure_xtdb_connection(connection)
        self.scope_digest = hashlib.sha256(
            f"{scope.storage_scope()}:{self.authority_namespace_id}".encode()).hexdigest()

    def _key(self, bundle_id: str) -> str:
        return hashlib.sha256(f"{self.scope_digest}:{require_identifier(bundle_id, 'bundle_id')}".encode()).hexdigest()

    def _fetch(self, bundle_id: str) -> dict[str, object] | None:
        rows = _rows(self.connection.execute(
            f"SELECT * FROM {_TABLE} FOR VALID_TIME ALL WHERE _id = %s", (self._key(bundle_id),)))
        if len(rows) > 1:
            raise ValueError("formation candidate registry has ambiguous immutable rows")
        if not rows:
            return None
        row = rows[0]
        record = json.loads(str(row["record_json"]))
        if (row["_id"] != self._key(bundle_id) or row["scope_digest"] != self.scope_digest
                or record["schema"] != "flora-formation-proposal-candidate-index-v1"
                or record["scope"] != self.scope.metadata_record()
                or record["authority_namespace_id"] != self.authority_namespace_id
                or record["bundle_id"] != bundle_id or record["record_sha256"] != row["record_sha256"]
                or canonical_sha256({key: value for key, value in record.items()
                                     if key != "record_sha256"}) != row["record_sha256"]):
            raise ValueError("formation candidate immutable index metadata changed")
        return record

    def record(self, *, prepared: PreparedSelectedFormation, delivery: RecordedEvent,
               bundle: MemoryProposalBundle, log: KurrentExperienceLog,
               objects: EncryptedObjectPlane, expected_model_artifact_sha256: str,
               occurred_at: str, expected_revision: int,
               value_resolver: FormationValueResolver) -> RecordedFormationCandidate:
        """Persist exact supplied outputs; a pinned artifact is only a declaration."""
        if (isinstance(expected_revision, bool) or not isinstance(expected_revision, int)
                or expected_revision < -1):
            raise ValueError("formation candidate expected revision must be an integer at least -1")
        if not callable(getattr(value_resolver, "resolve", None)):
            raise TypeError("formation candidate requires an independent proposed-value resolver")
        packet = prepared.assembled.packet
        if (not self.scope == packet.scope == log.scope == objects.scope
                or packet.authority_namespace_id != self.authority_namespace_id):
            raise ValueError("formation candidate submission crosses scope or authority")
        validate_formation_binding(packet, bundle)
        require_sha256(expected_model_artifact_sha256, "expected_model_artifact_sha256")
        if bundle.model_artifact_digest != expected_model_artifact_sha256:
            raise ValueError("formation candidate model artifact differs from expected declaration")
        at = normalize_timestamp(occurred_at, "occurred_at")
        if at < delivery.event.occurred_at:
            raise ValueError("formation candidate predates its delivered context")
        prepared.revalidate()
        delivery_record = prepared.receipt_record()
        _check_sources(packet, delivery_record, prepared.store)
        replayed = log.replay()
        _check_delivery(event=delivery.event, raw=delivery.raw, delivery_record=delivery_record,
                        packet=packet, replayed=replayed, objects=objects)
        values = []
        for value_ref in sorted({proposal.value_ref for proposal in bundle.proposals}):
            value = value_resolver.resolve(self.scope, self.authority_namespace_id, value_ref)
            if not isinstance(value, CanonicalTaggedValue):
                raise ValueError("formation candidate proposed value lacks independent resolution")
            value.validate()
            values.append([value_ref, value.metadata_record()])
        payload_record = {
            "schema": "flora-formation-proposal-candidate-v1",
            "bundle": bundle.metadata_record(), "formation_delivery": delivery_record,
            "delivery": {"event_id": delivery.event.event_id, "event_sha256": delivery.event.event_sha256,
                         "raw": _raw_record(delivery.raw, objects)},
            "proposed_values": values, "proposed_values_sha256": canonical_sha256(values),
        }
        material = _json_bytes(payload_record)
        prior = self._fetch(bundle.bundle_id)
        if prior is not None and prior["raw"]["plaintext_sha256"] != hashlib.sha256(material).hexdigest():
            raise ValueError("formation candidate bundle ID was reused with different output")
        raw = objects.put(material)
        parent_ids = tuple(sorted({delivery.event.event_id} | {ref.ref_id for ref in packet.evidence}))
        event = ExperienceEvent.create(
            event_type="formation_proposals", scope=self.scope, occurred_at=at,
            content_digest=raw.plaintext_sha256,
            provenance=ProvenanceReference.create(
                provenance_type="derived_inference", source_reference_ids=parent_ids,
                derivation_activity_id=bundle.inference_run_id,
                responsible_component="mfm_candidate_registration", model_id=bundle.model_artifact_digest),
            retention_class="ordinary_experience", storage_tier="raw_buffer",
            parent_event_ids=parent_ids, payload_reference=raw.object_id)
        located = next(((position, item) for position, item in enumerate(replayed)
                        if item.event_id == event.event_id), None)
        if prior is not None and (prior["event_id"] != event.event_id
                                  or prior["event_stream_position"] != expected_revision + 1):
            raise ValueError("formation candidate immutable event binding changed")
        if located is None and any(item.event_type == "formation_proposals"
                                   and item.payload_reference == raw.object_id for item in replayed):
            raise ValueError("formation candidate retry changed its original event envelope")
        prepared.revalidate()
        _check_sources(packet, delivery_record, prepared.store)
        for value_ref, value_record in values:
            current = value_resolver.resolve(self.scope, self.authority_namespace_id, value_ref)
            if not isinstance(current, CanonicalTaggedValue) or current.metadata_record() != value_record:
                raise ValueError("formation candidate proposed value changed before registration")
        if located is None:
            if expected_revision != len(replayed) - 1:
                raise ValueError("stale expected Experience revision for formation candidate")
            log.append(event, expected_revision=expected_revision)
            position = expected_revision + 1
        else:
            position, existing = located
            if existing != event or position != expected_revision + 1:
                raise ValueError("formation candidate retry differs from its original Experience position")
        index = {
            "schema": "flora-formation-proposal-candidate-index-v1", "scope": self.scope.metadata_record(),
            "authority_namespace_id": self.authority_namespace_id, "bundle_id": bundle.bundle_id,
            "bundle_sha256": bundle.content_digest(), "context_digest": bundle.context_digest,
            "model_artifact_sha256": bundle.model_artifact_digest, "event_id": event.event_id,
            "event_sha256": event.event_sha256, "event_stream_position": position,
            "proposed_values_sha256": payload_record["proposed_values_sha256"], "raw": _raw_record(raw, objects),
        }
        index["record_sha256"] = canonical_sha256(index)
        if prior is not None:
            if prior != index:
                raise ValueError("formation candidate immutable event binding changed")
            return RecordedFormationCandidate(event, raw, bundle.content_digest())
        values_row = {"_id": self._key(bundle.bundle_id), "scope_digest": self.scope_digest,
                      "record_sha256": index["record_sha256"], "record_json": _record_json(index)}
        with self.connection.transaction():
            self.connection.execute(
                f"ASSERT NOT EXISTS (SELECT 1 FROM {_TABLE} FOR VALID_TIME ALL WHERE _id = %s::text)",
                (self._key(bundle.bundle_id),))
            self.connection.execute(
                f"INSERT INTO {_TABLE} ({', '.join(values_row)}) VALUES ("
                + ", ".join(_dml_placeholder(value) for value in values_row.values()) + ")",
                tuple(values_row.values()))
        return RecordedFormationCandidate(event, raw, bundle.content_digest())

    def read_candidate(self, bundle_id: str, *, log: KurrentExperienceLog,
                       objects: EncryptedObjectPlane,
                       source_store: RegisteredFormationStore) -> RecoveredFormationCandidate:
        if not self.scope == log.scope == objects.scope == source_store.scope:
            raise ValueError("formation candidate read crosses host scope")
        index = self._fetch(bundle_id)
        if index is None:
            raise KeyError(bundle_id)
        raw, material = _read_raw(index["raw"], objects)
        payload = json.loads(material)
        if payload["schema"] != "flora-formation-proposal-candidate-v1":
            raise ValueError("formation candidate payload schema changed")
        bundle = _bundle_from_record(payload["bundle"])
        delivery_record = payload["formation_delivery"]
        packet = _packet_from_record(delivery_record["packet"])
        validate_formation_binding(packet, bundle)
        if (bundle.bundle_id != bundle_id or bundle.scope != self.scope
                or bundle.authority_namespace_id != self.authority_namespace_id
                or bundle.content_digest() != index["bundle_sha256"]
                or bundle.context_digest != index["context_digest"]
                or bundle.model_artifact_digest != index["model_artifact_sha256"]):
            raise ValueError("formation candidate bundle differs from immutable index")
        proposed_values = payload["proposed_values"]
        if (canonical_sha256(proposed_values) != payload["proposed_values_sha256"]
                or payload["proposed_values_sha256"] != index["proposed_values_sha256"]
                or [ref_id for ref_id, _ in proposed_values]
                != sorted({proposal.value_ref for proposal in bundle.proposals})):
            raise ValueError("formation candidate proposed-value binding changed")
        values = []
        for ref_id, record in proposed_values:
            value = CanonicalTaggedValue.create(type_tag=record["type_tag"], value=record["value"])
            if value.metadata_record() != record:
                raise ValueError("formation candidate canonical value digest changed")
            values.append((ref_id, value))
        replayed = log.replay()
        position = index["event_stream_position"]
        if isinstance(position, bool) or not isinstance(position, int) or not 0 <= position < len(replayed):
            raise ValueError("formation candidate lacks its committed Experience position")
        event = replayed[position]
        parent_ids = {payload["delivery"]["event_id"]} | {ref.ref_id for ref in packet.evidence}
        if (event.event_id != index["event_id"] or event.event_sha256 != index["event_sha256"]
                or event.event_type != "formation_proposals" or event.payload_reference != raw.object_id
                or event.content_digest != raw.plaintext_sha256 or set(event.parent_event_ids) != parent_ids
                or set(event.provenance.source_reference_ids) != parent_ids
                or event.provenance.model_id != bundle.model_artifact_digest
                or event.provenance.derivation_activity_id != bundle.inference_run_id
                or event.provenance.responsible_component != "mfm_candidate_registration"):
            raise ValueError("formation candidate differs from canonical Experience")
        delivery = next((item for item in replayed[:position]
                         if item.event_id == payload["delivery"]["event_id"]), None)
        if delivery is None or delivery.event_sha256 != payload["delivery"]["event_sha256"]:
            raise ValueError("formation candidate delivery is absent or changed")
        delivery_raw, _ = _read_raw(payload["delivery"]["raw"], objects)
        _check_delivery(event=delivery, raw=delivery_raw, delivery_record=delivery_record,
                        packet=packet, replayed=replayed[:position], objects=objects)
        _check_sources(packet, delivery_record, source_store)
        return RecoveredFormationCandidate(bundle, packet, delivery_record, tuple(values),
                                           RecordedFormationCandidate(event, raw, bundle.content_digest()))
