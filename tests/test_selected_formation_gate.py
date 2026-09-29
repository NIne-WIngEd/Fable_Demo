import hashlib
import unittest

from cognitive_kernel.contracts import ProductHostScope
from cognitive_kernel.formation_contracts import (
    FormationContextPacket, FormationEvidenceRef, FormationProposal, MemoryProposalBundle,
)
from flora.selected.formation_gate import assess_formation


class SyntheticVerifier:
    def authenticated_owner_source(self, evidence):
        return evidence.ref_id == "experience-owner-one"


def bound_input(role="authenticated_owner_statement", status="owner_statement"):
    scope = ProductHostScope.create(product_id="friday", host_instance_id="fictional-owner",
        schema_version="1.0.0", encryption_domain="key-a")
    ref = FormationEvidenceRef(ref_id="experience-owner-one", scope=scope,
        authority_namespace_id="host-claims", content_digest=hashlib.sha256(b"synthetic").hexdigest(),
        role=role, modality="text")
    context = FormationContextPacket(scope=scope, authority_namespace_id="host-claims",
        experience_refs=(ref.ref_id,), evidence=(ref,))
    proposal = FormationProposal(proposal_id="proposal-one", kind="preference", domain="host",
        subject_ref="fictional-owner", value_ref="value-one", evidence_refs=(ref.ref_id,),
        epistemic_status=status)
    bundle = MemoryProposalBundle(scope=scope, authority_namespace_id="host-claims",
        bundle_id="bundle-one", experience_refs=context.experience_refs,
        context_digest=context.content_digest(), model_artifact_digest="a" * 64,
        inference_run_id="synthetic-run", proposals=(proposal,))
    return context, bundle, ref


class FormationGateContractTest(unittest.TestCase):
    def test_model_cannot_authorize_itself(self):
        context, bundle, ref = bound_input()
        without_auth = assess_formation(context=context, bundle=bundle,
            proposal_id="proposal-one", registered={ref.ref_id: ref})
        self.assertEqual(without_auth.disposition, "needs_authentication")
        with_auth = assess_formation(context=context, bundle=bundle,
            proposal_id="proposal-one", registered={ref.ref_id: ref},
            owner_verifier=SyntheticVerifier())
        self.assertEqual(with_auth.disposition, "eligible_for_adjudication")
        self.assertEqual(with_auth.evidence_refs, (ref.ref_id,))
        with self.assertRaisesRegex(ValueError, "registered"):
            assess_formation(context=context, bundle=bundle,
                proposal_id="proposal-one", registered={})

    def test_historical_experience_is_not_owner_speech(self):
        context, bundle, ref = bound_input("historical_experience", "observation")
        assessment = assess_formation(context=context, bundle=bundle,
            proposal_id="proposal-one", registered={ref.ref_id: ref},
            owner_verifier=SyntheticVerifier())
        self.assertEqual(assessment.disposition, "needs_adjudication")

    def test_synthetic_training_source_cannot_become_claim(self):
        context, bundle, ref = bound_input("hypothetical_training", "hypothetical")
        assessment = assess_formation(context=context, bundle=bundle,
            proposal_id="proposal-one", registered={ref.ref_id: ref},
            owner_verifier=SyntheticVerifier())
        self.assertEqual(assessment.disposition, "non_authoritative")


if __name__ == "__main__":
    unittest.main()
