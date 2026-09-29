"""Primitive replay manifest retained for historical component regressions.

This helper lacks registered identity, physical availability time and lineage
closure. It is not the current MFM inference entry point. Use formation_context
with registered custody and independent permissions for the actual model seam.
This helper neither infers memory nor grants Claim authority.
"""

from __future__ import annotations

from collections.abc import Sequence

from cognitive_kernel.experience import ExperienceEvent
from cognitive_kernel.formation_contracts import FormationContextPacket, FormationEvidenceRef

from .object_store import EncryptedObjectPlane, RawObjectReference
from .experience import KurrentExperienceLog


def formation_input(*, events: Sequence[ExperienceEvent],
                    references: dict[str, RawObjectReference],
                    modalities: dict[str, str], objects: EncryptedObjectPlane,
                    authority_namespace_id: str) -> FormationContextPacket:
    if not events:
        raise ValueError("formation needs at least one Experience event")
    refs: list[FormationEvidenceRef] = []
    for event in events:
        event.validate()
        if event.scope != objects.scope or event.payload_reference is None:
            raise ValueError("event lacks an authorized raw object for this host")
        raw = references.get(event.payload_reference)
        if raw is None or raw.object_id != event.payload_reference or raw.scope != event.scope:
            raise ValueError("event raw object reference is missing or cross-host")
        content = objects.get(raw)  # AEAD and keyed content identity are verified here.
        if raw.plaintext_sha256 != event.content_digest or len(content) != raw.size:
            raise ValueError("event content digest differs from the raw source")
        if event.event_id not in modalities:
            raise ValueError("evidence modality must be declared from source metadata")
        refs.append(FormationEvidenceRef(ref_id=event.event_id, scope=event.scope,
            authority_namespace_id=authority_namespace_id, content_digest=event.content_digest,
            role="historical_experience", modality=modalities[event.event_id]))
    packet = FormationContextPacket(scope=objects.scope,
        authority_namespace_id=authority_namespace_id,
        experience_refs=tuple(event.event_id for event in events), evidence=tuple(refs))
    packet.validate()
    return packet


def formation_input_from_replay(*, log: KurrentExperienceLog,
                                event_ids: Sequence[str],
                                references: dict[str, RawObjectReference],
                                modalities: dict[str, str],
                                objects: EncryptedObjectPlane,
                                authority_namespace_id: str) -> FormationContextPacket:
    """Bind formation to the real Experience stream, not caller-made events."""
    if log.scope != objects.scope or not event_ids or len(set(event_ids)) != len(event_ids):
        raise ValueError("formation replay must select unique events within one host")
    replayed = {event.event_id: event for event in log.replay()}
    if not set(event_ids).issubset(replayed):
        raise ValueError("formation evidence is absent from Experience replay")
    return formation_input(events=[replayed[event_id] for event_id in event_ids],
        references=references, modalities=modalities, objects=objects,
        authority_namespace_id=authority_namespace_id)
