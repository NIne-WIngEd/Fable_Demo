"""Owner-key verifier for exact Experience actions, without key enrollment.

The product supplies a previously enrolled host-bound public key and durable
proof lookup. A proof's signing key is never accepted from the proof itself.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from typing import Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cognitive_kernel.contracts import ProductHostScope
from cognitive_kernel.experience import ExperienceEvent


@dataclass(frozen=True)
class OwnerActionProof:
    action: str
    event_id: str
    event_sha256: str
    signature_base64: str


def owner_action_message(event: ExperienceEvent, action: str) -> bytes:
    event.validate()
    if action not in {"state_activation", "claim_quarantine"}:
        raise ValueError("unknown owner action")
    return (f"FloRA-owner-action-v1\n{action}\n{event.scope.storage_scope()}\n"
            f"{event.event_sha256}\n").encode()


class Ed25519OwnerActionVerifier:
    """Cryptographic verifier; enrollment, custody and policy stay outside."""

    def __init__(self, *, scope: ProductHostScope, owner_public_key: bytes,
                 proofs: Mapping[str, OwnerActionProof]):
        scope.validate()
        self.scope = scope
        self.key = Ed25519PublicKey.from_public_bytes(owner_public_key)
        self.proofs = proofs

    def _verify(self, event: ExperienceEvent, action: str) -> bool:
        if event.scope != self.scope:
            return False
        proof = self.proofs.get(event.event_id)
        if (proof is None or proof.action != action
                or proof.event_id != event.event_id
                or proof.event_sha256 != event.event_sha256):
            return False
        try:
            signature = base64.b64decode(proof.signature_base64, validate=True)
            self.key.verify(signature, owner_action_message(event, action))
        except (InvalidSignature, ValueError, binascii.Error):
            return False
        return True

    def authenticated_approval(self, event: ExperienceEvent,
                               request: dict[str, object]) -> bool:
        return (event.event_type == "state_activation_approval"
                and request.get("schema") == "flora-state-activation-v1"
                and self._verify(event, "state_activation"))

    def authenticated_request(self, event: ExperienceEvent,
                              request: dict[str, str]) -> bool:
        return (event.event_type == "deletion_request"
                and request.get("schema") == "flora-claim-quarantine-v1"
                and self._verify(event, "claim_quarantine"))
