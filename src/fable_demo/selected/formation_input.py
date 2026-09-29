"""Evidence-verified MFM input manifest from the selected raw and event planes.

This does not infer a memory or grant Claim authority. The model may consume
authorized bytes separately after this manifest is bound to exact evidence.
"""

from __future__ import annotations

from collections.abc import Sequence

from cognitive_kernel.experience import ExperienceEvent
from cognitive_kernel.formation_contracts import FormationContextPacket, FormationEvidenceRef

from .object_store import EncryptedObjectPlane, RawObjectReference


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
