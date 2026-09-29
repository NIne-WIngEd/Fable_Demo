"""Source-bound input using A.L.I.C.E.'s actual MFM formation contract.

This planner selects explicit context; it does not infer a topic, form a claim,
or let a learned component promote its own output into memory authority.
Packets describe current state at assembly time, never a historical snapshot.
"""

from __future__ import annotations

import hashlib
import json

from .memory_lane import MemoryLane
from .runtime import FableRuntime


def _subject_ref(runtime: FableRuntime, subject: str) -> str:
    if subject == "host":
        return runtime.scope.host_instance_id
    if subject in {"assistant_self", "relationship"}:
        return f"{subject}-{runtime.scope.host_instance_id}"
    raise ValueError("unsupported observation subject")


def build_formation_manifest(runtime: FableRuntime, *, logical_id: str,
                             host_keys: tuple[str, ...] = ()):
    """Bind input references to checked vault records; expose no plaintext."""
    from cognitive_kernel.formation_contracts import FormationContextPacket, FormationEvidenceRef

    if len(host_keys) != len(set(host_keys)):
        raise ValueError("duplicate host keys")
    lane = MemoryLane(runtime)
    observation, _reference, event = lane._observation(logical_id)
    namespace = runtime.scope.host_instance_id

    def experience_ref(item, ledger_event):
        return FormationEvidenceRef(ref_id=ledger_event.event_id, scope=runtime.scope,
            authority_namespace_id=namespace, content_digest=hashlib.sha256(item.text.encode()).hexdigest(),
            role="historical_experience", modality="text",
            subject_ref=_subject_ref(runtime, item.subject))

    evidence = [experience_ref(observation, event)]
    if observation.relates_to:
        previous, _previous_reference, previous_event = lane._observation(observation.relates_to)
        if previous_event.event_id not in event.parent_event_ids:
            raise ValueError("observation parent differs from ledger lineage")
        evidence.append(experience_ref(previous, previous_event))
    for key in host_keys:
        for claim in lane.current(key=key):
            evidence.append(FormationEvidenceRef(ref_id=claim["memory_id"], scope=runtime.scope,
                authority_namespace_id=namespace,
                content_digest=hashlib.sha256(claim["text"].encode()).hexdigest(),
                role="authoritative_claim", modality="text", subject_ref=runtime.scope.host_instance_id))
    manifest = FormationContextPacket(scope=runtime.scope, authority_namespace_id=namespace,
        experience_refs=(event.event_id,), evidence=tuple(evidence))
    manifest.validate()
    return manifest


def bind_model_proposals(runtime: FableRuntime, *, logical_id: str, host_keys: tuple[str, ...], bundle) -> dict:
    """Validate an MFM output against fresh registered input. Grant no authority."""
    from cognitive_kernel.formation_contracts import MemoryProposalBundle, validate_formation_binding

    if not isinstance(bundle, MemoryProposalBundle):
        raise TypeError("expected A.L.I.C.E. MemoryProposalBundle")
    manifest = build_formation_manifest(runtime, logical_id=logical_id, host_keys=host_keys)
    validate_formation_binding(manifest, bundle)
    return {"bundle_id": bundle.bundle_id, "context_digest": manifest.content_digest(),
            "proposal_count": len(bundle.proposals), "authority": "none; proposals need a separate deterministic gate"}


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
    manifest = build_formation_manifest(runtime, logical_id=logical_id, host_keys=host_keys)
    packet["formation_manifest"] = manifest.metadata_record()
    packet["formation_digest"] = manifest.content_digest()
    packet["packet_sha256"] = hashlib.sha256(json.dumps(packet, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return packet
