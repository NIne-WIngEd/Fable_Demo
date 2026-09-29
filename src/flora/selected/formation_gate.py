"""Deterministic pre-adjudication gate for learned MFM proposals.

The gate compares model output with independently registered evidence. An
eligible proposal is still a candidate, never a committed Claim. Authentication,
conflict policy and XTDB commit remain separate authority steps.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from cognitive_kernel.formation_contracts import (
    FormationContextPacket, FormationEvidenceRef, MemoryProposalBundle,
    validate_formation_binding,
)


class OwnerSourceVerifier(Protocol):
    """An independent source service, not a claim made by the MFM."""

    def authenticated_owner_source(self, evidence: FormationEvidenceRef) -> bool: ...


@dataclass(frozen=True)
class GateAssessment:
    proposal_id: str
    disposition: str
    reasons: tuple[str, ...]
    context_digest: str
    bundle_digest: str
    evidence_refs: tuple[str, ...]


def assess_formation(
    *, context: FormationContextPacket, bundle: MemoryProposalBundle,
    proposal_id: str, registered: Mapping[str, FormationEvidenceRef],
    owner_verifier: OwnerSourceVerifier | None = None,
) -> GateAssessment:
    """Fail closed on invented, changed, unregistered, or unauthenticated sources.

    Only direct owner statements can advance to an adjudication candidate here.
    Other kinds stay as evidence or await a later, explicit authority policy.
    This function never writes to a store or promotes an MFM interpretation.
    """
    validate_formation_binding(context, bundle)
    proposal = next((p for p in bundle.proposals if p.proposal_id == proposal_id), None)
    if proposal is None:
        raise ValueError("proposal is absent from the bound MFM bundle")

    context_refs = {ref.ref_id: ref for ref in context.evidence}
    for ref_id in proposal.evidence_refs:
        if registered.get(ref_id) != context_refs[ref_id]:
            raise ValueError("proposal source differs from the registered evidence")

    sources = tuple(context_refs[ref_id] for ref_id in proposal.evidence_refs)
    if any(ref.role == "hypothetical_training" for ref in sources):
        disposition, reasons = "non_authoritative", ("synthetic_training_source",)
    elif proposal.kind not in {"claim", "preference", "goal", "correction_request"}:
        disposition, reasons = "non_authoritative", ("unsupported_canonical_kind",)
    elif proposal.epistemic_status != "owner_statement" or any(
        ref.role != "authenticated_owner_statement" for ref in sources
    ):
        disposition, reasons = "needs_adjudication", ("not_direct_owner_statement",)
    elif owner_verifier is None or not all(
        owner_verifier.authenticated_owner_source(ref) for ref in sources
    ):
        disposition, reasons = "needs_authentication", ("independent_owner_verification_missing",)
    else:
        disposition, reasons = "eligible_for_adjudication", ("bound_owner_evidence",)

    return GateAssessment(
        proposal_id=proposal.proposal_id, disposition=disposition,
        reasons=reasons, context_digest=context.content_digest(),
        bundle_digest=bundle.content_digest(), evidence_refs=proposal.evidence_refs,
    )
