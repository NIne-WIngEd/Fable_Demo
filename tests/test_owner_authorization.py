import base64
from dataclasses import replace
import hashlib
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from cognitive_kernel.formation_contracts import FormationEvidenceRef
from cognitive_kernel.formation_sources import RegisteredFormationSource
from flora.selected.formation_policy import (
    FormationPermissionAction, formation_permission_payload,
)
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

    def test_formation_permission_signature_binds_exact_source_action_and_event(self):
        scope = ProductHostScope.create(
            product_id="friday", host_instance_id="synthetic-permission-owner",
            schema_version="1.0.0", encryption_domain="synthetic-permission-key")
        source = RegisteredFormationSource.create(
            evidence=FormationEvidenceRef(
                ref_id="synthetic-original-source", scope=scope,
                authority_namespace_id="synthetic-formation-authority",
                content_digest=hashlib.sha256(b"synthetic original").hexdigest(),
                role="historical_experience", modality="text"),
            object_ref="synthetic-original-object")
        action = FormationPermissionAction.create(
            scope=scope, authority_namespace_id=source.evidence.authority_namespace_id,
            action_id="synthetic-permission-grant", source_ref_id=source.evidence.ref_id,
            source_registration_sha256=source.registration_sha256,
            purpose="memory_formation", decision="allow", generation=1,
            previous_action_sha256=None, authorization_ref="synthetic-owner-proof",
            authorized_at="2026-09-29T00:00:00Z")
        event = ExperienceEvent.create(
            event_type="formation_permission_action", scope=scope,
            occurred_at=action.authorized_at,
            content_digest=hashlib.sha256(formation_permission_payload(action)).hexdigest(),
            provenance=ProvenanceReference.create(
                provenance_type="owner_attested_canonical",
                source_reference_ids=("synthetic-permission-object",),
                responsible_component="synthetic-signature-test"),
            retention_class="ordinary_experience", storage_tier="raw_buffer",
            payload_reference="synthetic-permission-object",
            parent_event_ids=(source.evidence.ref_id,))
        signer = Ed25519PrivateKey.generate()
        public = signer.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        proof = OwnerActionProof(
            "formation_permission", event.event_id, event.event_sha256,
            base64.b64encode(signer.sign(owner_action_message(
                event, "formation_permission"))).decode())

        def verifier(candidate=proof, *, enrolled_scope=scope, enrolled_key=public):
            return Ed25519OwnerActionVerifier(
                scope=enrolled_scope, owner_public_key=enrolled_key,
                proofs={event.event_id: candidate})

        self.assertTrue(verifier().authorized_action(action, source, event))
        for changed_proof in (
            replace(proof, action="claim_quarantine"),
            replace(proof, event_id="different-event"),
            replace(proof, event_sha256="f" * 64),
            replace(proof, signature_base64="not-valid-base64!"),
            replace(proof, signature_base64=base64.b64encode(b"x" * 64).decode()),
        ):
            with self.subTest(proof=changed_proof):
                self.assertFalse(verifier(changed_proof).authorized_action(action, source, event))
        other = replace(scope, host_instance_id="another-owner")
        self.assertFalse(verifier(enrolled_scope=other).authorized_action(action, source, event))
        other_key = Ed25519PrivateKey.generate().public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.assertFalse(verifier(enrolled_key=other_key).authorized_action(action, source, event))
        # A valid signature for a different domain cannot authorize a grant,
        # even when its proof label is changed to the formation domain.
        wrong_domain = replace(proof, signature_base64=base64.b64encode(signer.sign(
            owner_action_message(event, "claim_quarantine"))).decode())
        self.assertFalse(verifier(wrong_domain).authorized_action(action, source, event))
        self.assertFalse(verifier().authorized_action(
            replace(action, action_sha256="e" * 64), source, event))
        for changes in (
            {"decision": "deny"}, {"source_registration_sha256": "e" * 64},
            {"source_ref_id": "different-source"},
            {"authority_namespace_id": "different-authority"},
        ):
            material = {key: value for key, value in action.__dict__.items()
                        if key != "action_sha256"}
            changed = FormationPermissionAction.create(**(material | changes))
            with self.subTest(action=changes):
                self.assertFalse(verifier().authorized_action(changed, source, event))
        changed_source = RegisteredFormationSource.create(
            evidence=source.evidence, object_ref="different-source-object")
        self.assertFalse(verifier().authorized_action(action, changed_source, event))
        self.assertFalse(verifier().authorized_action(
            action, replace(source, registration_sha256="e" * 64), event))
        self.assertFalse(verifier().authorized_action(
            action, source, replace(event, event_sha256="e" * 64)))
        # A cryptographically valid signature still cannot authorize the
        # wrong event class, host, payload digest, or source-parent binding.
        for changes in (
            {"event_type": "deletion_request"}, {"scope": other},
            {"content_digest": "e" * 64}, {"parent_event_ids": ()},
        ):
            event_material = {
                "event_type": event.event_type, "scope": event.scope,
                "occurred_at": event.occurred_at, "content_digest": event.content_digest,
                "provenance": event.provenance, "retention_class": event.retention_class,
                "storage_tier": event.storage_tier, "payload_reference": event.payload_reference,
                "parent_event_ids": event.parent_event_ids,
            }
            changed_event = ExperienceEvent.create(**(event_material | changes))
            changed_proof = OwnerActionProof(
                "formation_permission", changed_event.event_id, changed_event.event_sha256,
                base64.b64encode(signer.sign(owner_action_message(
                    changed_event, "formation_permission"))).decode())
            signed_wrong_event = Ed25519OwnerActionVerifier(
                scope=scope, owner_public_key=public,
                proofs={changed_event.event_id: changed_proof})
            with self.subTest(event=changes):
                self.assertFalse(signed_wrong_event.authorized_action(action, source, changed_event))


if __name__ == "__main__":
    unittest.main()
