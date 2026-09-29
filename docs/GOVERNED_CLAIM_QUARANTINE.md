# Governed Claim quarantine

`XTDBGovernedClaimQuarantine` closes the legacy writer gap for the admission-owned
Claim namespace. It uses the same controller as governed semantic admission.
A Kurrent deletion request position never becomes Claim authority ordering.

```python
receipt = XTDBGovernedClaimQuarantine(authority).apply(
    prior=exact_current_projection,
    request_event_id=committed_signed_deletion_request_id,
    log=log, objects=objects, references=durable_references,
    verifier=enrolled_owner_action_verifier,
)
temporal_request = XTDBGovernedClaimQuarantine(authority).cleanup(receipt)
```

The request bytes are exactly `revocation_request(prior)`. The enrolled owner
signs the existing `claim_quarantine` action domain. The actual Kurrent request
must parent the Claim's actual earlier source event, bind the exact predecessor,
and have a physically committed timestamp. Authorization is checked before
opening its encrypted request and again afterward. Model outputs confer no
quarantine authority.

One native XTDB transaction atomically checks the controller and predecessor,
advances the namespace counter, selects a `pending` deletion projection/head,
preserves the prior valid-time interval, and records an immutable idempotency
receipt. A failed receipt insert rolls back the mutation and counter. An exact
retry after process recreation returns the same receipt; a changed control
request or current head fails closed. The receipt retains the Kurrent
`event_stream_position` separately from `store_sequence`/`source_position`.

`claim_controller.py` is shared by semantic admission and quarantine. It verifies
its exact controller and counter, inventories historical version sequences and
current/head source positions, and repeats absence/CAS assertions inside the
mutation transaction. This catches untracked sequence advances both before and
between inventory and commit. Authorized legacy writers are fenced separately.
It is not a provenance scan for direct out-of-band database alterations that reuse
an older sequence. Quarantines consume an authority sequence without
inventing another factual Claim version.

The pending head immediately blocks current source reads and filtered vector or
graph hits. Dependent governed state/episode readers recheck the Claim and also
refuse it. Existing `ReconcileDerivedClaimWorkflow` receives an exact-head cleanup
request and retries Qdrant/Ladybug cleanup. Cleanup success is separate from the
atomic authority barrier; no derived engine participates in the XTDB transaction.

This is an influence-use barrier for the selected Claim and dependent governed
routes. It does not erase original Experience/raw objects, revoke every source
permission, delete every derivative, or unlearn model weights. Original-source
permission revocation remains a separate governed action. A namespace's semantic
property occupancy stays reserved; an ordinary add/revise cannot silently reopen
a quarantined identity.

Six deterministic quarantine methods and seven semantic admission methods pass.
SQL call recording demonstrates transaction mechanics only. The actual selected
integration case covers rollback, durable signed request/receipt recreation,
historical-read denial, dependent state denial, stale Qdrant/Ladybug filtering,
and Temporal cleanup using fictional semantic/state fixtures. Its CI outcome is
tracked separately; no learned behavior is qualified.
