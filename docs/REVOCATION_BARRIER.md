# Claim source quarantine

A verified deletion request first needs an **immediate use barrier**. `quarantine_claim` checks the exact KurrentDB request and encrypted payload against the current XTDB claim projection. A trusted product-supplied verifier must authenticate and authorize it. The function then writes a new bitemporal current projection with `deletion_state=pending` and prunes that claim's Qdrant points.

All current claim reads already reject non-active projections. Active personal state rechecks its source claim. Context delivery and contextual decisions reassemble against current authority and permissions. Thus a source quarantined after context delivery cannot be used for a new decision through this path. The Qdrant read filter remains in place even if cleanup is delayed. An identical request may retry cleanup.

`pending` is deliberate. The raw object and immutable Experience event still exist. Other derivatives, cached or running-model context, backups, exports, training data, and weights are not erased by this function. Complete deletion and influence removal need a durable coordinator, lineage traversal, restore checks, and model-specific rebuild or unlearning. This slice must never be reported as completed erasure.

The integration verifier is synthetic. Production owner authentication and policy remain open.

The legacy path above is refused for namespaces owned by the new [governed admission controller](FORMATION_ADMISSION.md). Its Kurrent request position cannot serve as a Claim store sequence. Registered formation permission revocation provides a separate current source-use barrier; governed Claim quarantine and cross-layer invalidation still require controller-aware implementation.
