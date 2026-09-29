import base64
import hashlib
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from flora.selected.owner_authorization import (
    Ed25519OwnerActionVerifier, OwnerActionProof, owner_action_message,
)


class OwnerAuthorizationTest(unittest.TestCase):
    def test_signature_binds_enrolled_key_action_event_and_host(self):
        scope = ProductHostScope.create(
            product_id="friday", host_instance_id="synthetic-owner",
            schema_version="1.0.0", encryption_domain="synthetic-key")
        event = ExperienceEvent.create(
            event_type="deletion_request", scope=scope,
            occurred_at="2026-09-29T00:00:00Z",
            content_digest=hashlib.sha256(b"synthetic request").hexdigest(),
            provenance=ProvenanceReference.create(
                provenance_type="derived_inference",
                source_reference_ids=("synthetic-owner-action",),
                derivation_activity_id="synthetic-owner-signing",
                responsible_component="synthetic-test"),
            retention_class="ordinary_experience", storage_tier="raw_buffer",
            payload_reference="synthetic-object")
        signer = Ed25519PrivateKey.generate()
        public = signer.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        signature = signer.sign(owner_action_message(event, "claim_quarantine"))
        proof = OwnerActionProof(
            "claim_quarantine", event.event_id, event.event_sha256,
            base64.b64encode(signature).decode())
        verifier = Ed25519OwnerActionVerifier(
            scope=scope, owner_public_key=public,
            proofs={event.event_id: proof})
        request = {"schema": "flora-claim-quarantine-v1"}
        self.assertTrue(verifier.authenticated_request(event, request))
        self.assertFalse(verifier.authenticated_request(
            event, {"schema": "flora-state-activation-v1"}))
        self.assertFalse(verifier.authenticated_approval(
            event, {"schema": "flora-state-activation-v1"}))
        wrong_key = Ed25519PrivateKey.generate().public_key().public_bytes(
            Encoding.Raw, PublicFormat.Raw)
        self.assertFalse(Ed25519OwnerActionVerifier(
            scope=scope, owner_public_key=wrong_key,
            proofs={event.event_id: proof}).authenticated_request(event, request))
        other = ProductHostScope.create(
            product_id="friday", host_instance_id="another-host",
            schema_version="1.0.0", encryption_domain="another-key")
        self.assertFalse(Ed25519OwnerActionVerifier(
            scope=other, owner_public_key=public,
            proofs={event.event_id: proof}).authenticated_request(event, request))
        approval = ExperienceEvent.create(
            event_type="state_activation_approval", scope=scope,
            occurred_at="2026-09-29T00:01:00Z",
            content_digest=hashlib.sha256(b"synthetic approval").hexdigest(),
            provenance=event.provenance,
            retention_class="ordinary_experience", storage_tier="raw_buffer",
            payload_reference="synthetic-approval-object")
        approval_proof = OwnerActionProof(
            "state_activation", approval.event_id, approval.event_sha256,
            base64.b64encode(signer.sign(owner_action_message(
                approval, "state_activation"))).decode())
        approval_verifier = Ed25519OwnerActionVerifier(
            scope=scope, owner_public_key=public,
            proofs={approval.event_id: approval_proof})
        self.assertTrue(approval_verifier.authenticated_approval(
            approval, {"schema": "flora-state-activation-v1"}))


if __name__ == "__main__":
    unittest.main()
