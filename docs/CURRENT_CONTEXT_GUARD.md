# Current authority without repeated context decryption

`prepare_current_context` assembles the real selected judgment context once. It
then owns those authenticated bytes and checks current authority whenever the
runtime wants to use them. It does not accept a caller's cached `LocalContext`.
This changes repeated custody work; it adds no model, judgment or permission.

## What is captured and what stays live

| Material | Exact captured binding | Checked again before use |
| --- | --- | --- |
| Claim | Current projection, immutable version and evidence relations | Current availability, version, projection, relations and source permission |
| Personal state | Active head, immutable content reference, projection, activation and rollback lineage | Same exact metadata and current source permission |
| Original and control sources | Registered event, source and parent closure, raw custody metadata and purpose grant | Current registration, raw metadata, parent permission and exact grant generation |
| Owner approval | Exact event and activation request | Actual current independently enrolled owner verifier and signature proof |
| Accepted episode | Exact current publication, candidate, source and admission lineage | Current metadata plus the existing actual `read_accepted` proof, including live formation qualification and semantic admission |
| Experiment phase | No captured allow bit | Supplied independent current authority callback before and after slow work |

Initial assembly samples the actual nomination graph once. A fresh exact
metadata fence checks that baseline before private reads and after every
underlying ciphertext fetch. A change during that work cannot become
a newly trusted captured snapshot. The selected object wrappers prevent a
withdrawn read from reaching decryption. After assembly, the guard also detects
changes to its held context receipt, including private content and Claim values.

## Wiring

```python
prepared = prepare_current_context(
    plan=exact_plan,
    claims=actual_claims,
    state=actual_governed_state,
    log=actual_log,
    objects=actual_objects,
    references=actual_references,
    policy=actual_registered_judgment_policy,
    approval_verifier_factory=current_owner_verifier,
    before_private_assembly=qualify_current_role,
    authority_guard=current_phase_authority,
)
context = prepared.context
prepared.revalidate()
```

`current_owner_verifier(metadata_barrier)` must resolve the actual current owner
verifier with the existing enrolled key and authority. Any private proof lookup
must use the supplied metadata barrier around its inner ciphertext I/O. This
avoids recursively checking a signature while opening that same signature's
proof. The factory cannot replace independent owner authentication with a local
allow decision.

`before_private_assembly(metadata_barrier)` is optional. It runs after current
source/control metadata denial checks and before any source or owner plaintext
assembly. The role qualification hook must use that barrier around private
qualification receipt I/O and return `None`; the fence runs again after it.
This preserves both boundaries: revoked source access precedes qualification
proof reads, and invalid role qualification precedes source/owner plaintext.

`revalidate()` is the complete current-use check. `metadata_current()` checks
selected metadata and phase authority only; it is the inner private-proof I/O
barrier, not a substitute for current owner or semantic authentication.

The plan must have explicitly finite exact Claim and state routes. Live Qdrant
or graph nominations are rejected. Their results must first be explicitly
frozen into exact routes under the appropriate current retrieval authority. The
helper does not certify relevance, hide a mutable accelerator or invent a new
retrieval contract.

## Bounded metadata reuse

Each metadata pass shallow-copies the actual selected service wrappers and
memoizes only their metadata row readers. A key includes that service's reader,
table/record arguments and valid-time options. Connections are retained, not
modified. Derived policy checks still run; owner proof and external semantic
checks are never cached. Raw object plaintext is never memoized here.

The entire view is discarded before a final fence through the original readers.
That fence rechecks the exact heads, versions, evidence, source registrations,
raw metadata and grant generations. A second guard starts fresh. There is no
TTL, global cache, captured positive allow bit or inherited connection patch.
The phase authority callback runs after potentially slow metadata work and
again after the uncached fence. Fresh original/control source and grant
checks then follow the final phase callback; accepted-episode metadata also
precedes these consent checks, so its slow callback cannot withdraw consent
after the last check and still admit decryption. Current scope, purpose and selected service
bindings must also remain exact. Initial private-read barriers use the exact
uncached baseline fence without repeating the full graph nomination traversal.

Metadata remains private local context, including Claim values. Captured records
are not public receipts or training examples. A final fence is not a transaction
across XTDB, the log, owner authority and object custody; current gates remain
required at each subsequent execution, read and acceptance boundary.

## Evidence and remaining boundary

Twenty-five local tests pass with real encrypted custody and Ed25519 owner checks,
using explicitly controlled SQL/source/admission fixtures. They cover withdrawal
before owner I/O, withdrawal during an owner ciphertext fetch, context mutation,
Claim/state/rollback/source changes, parent-source withdrawal, exact grant
generation changes and live accepted-episode admission withdrawal. They do not
train or build personality, MFM or a replacement judge.

In the owner-only SQL fixture, each active head, version and activation row is
fetched exactly twice per metadata check: once for the sampled pass and once for
the fresh fence. Subsequent checks repeat those reads. Ordinary repeated owner
state checks open no original or state bytes. Accepted episodes deliberately
retain their existing full current governed proof read because the current
semantic/qualification port does not promise a cache-safe alternative.

These tests establish the local custody and authority behavior. They do not
establish physical XTDB latency, production throughput, cross-plane atomicity,
checkpoint quality or a behavioral FloRA win. The assembled selected-engine
comparison and its declared time/resource budget remain separate required gates.

Implementation: `src/flora/selected/context_guard.py`.
Tests: `tests/test_current_context_guard.py`.
