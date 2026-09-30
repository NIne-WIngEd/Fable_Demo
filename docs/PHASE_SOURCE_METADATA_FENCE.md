# One phase-source guard, one terminal current-row statement

`verify_current_phase_sources` checks the actual selected archive/source policy
without reopening originals. The archive's owner policy remains separate from
the native context's original-only and phase predicates. The helper builds no
model and creates no permission.

The helper accepts an actual `RegisteredJudgmentContextPolicy` backed by actual
XTDB source registry, permission policy and Claim authority on the same selected
connection. IDs are explicit finite tuples. Duplicate, unknown, cross-scope or
oversized nominations fail. `maximum_rows` defaults to 4096 distinct metadata
rows; exceeding it stops instead of splitting into an unlimited number of guards.

## The guard

1. Copy the actual metadata services, keeping their selected connection and
   actual instance-mutated predicates. Sample each source/raw/action/head/Claim
   row only inside this call. Cache no permission answer, owner decision,
   qualification, plaintext or ciphertext.
2. Resolve every nominated source and its actual registered parent closure,
   matching real canonical event scope, payload, digest and parents. Run the
   actual source-use predicates and current Claim availability checks.
3. Run fresh current grant callbacks and the optional current phase/control
   callback. Re-run actual source predicates after that callback.
4. Finish with **one finite XTDB statement** observing every sampled authority
   row together, including current permission heads and current Claim rows.
   Require exact table/key/scope, metadata digest and canonical JSON body, and
   reject missing, duplicate, ambiguous or unexpected rows. No authority callback
   runs after this statement; only pure service-binding comparisons remain.

`OneGuardSelectedMetadata` is also used by the existing history fence. It does
not authorize use by itself: the caller must still authenticate initial private
custody, verify immutable source/event bindings and execute actual authority
predicates. Its sampled readers are discarded after the call.

## Why the terminal statement matters

A sequential grant loop has a real race: the callback reading the final grant
can revoke an earlier original after that original was checked. Repeating the
loop introduces another final callback. The terminal statement compares all
actual current heads together after those callbacks and detects the change.
It also catches Claim quarantine or raw-registration changes during that work.

The query uses bounded `UNION ALL` branches, explicit table names, scoped keys
and a result limit. Source/raw/action rows use the existing `FOR VALID_TIME ALL`
semantics; permission heads and Claim projections use current valid time.
XTDB's [SQL query and basis documentation](https://docs.xtdb.com/reference/main/sql/queries.html)
describes the single query basis. Physical execution of this specific query is
covered by the prepared selected-backend integration test and must pass CI.

## Evidence and limits

Eleven local phase-fence tests plus fourteen history-fence tests pass with actual
selected registry/policy methods, initial encrypted custody and independently
signed owner grants on controlled SQL/log ports. They cover preserved patched
predicates, one immutable lookup per row inside a guard, no original byte I/O,
fresh denial between calls, withdrawal in the **final** grant callback, Claim
quarantine after slow callbacks, raw metadata changes, scope/connection forgery,
strict result completeness, duplicate rows, purpose mutation and explicit caps.
The full initial history path still authenticates both original ciphertexts,
then applies the metadata fence; its final callback and the final permission
marker callback cannot withdraw an earlier original and retain authorization.

The controlled batch recorder is only a SQL-shape fixture. It is not a second
database or evidence of physical consistency or latency. The actual integration
test uses XTDB, Kurrent, encrypted originals and an admitted fictional Claim,
including a real owner withdrawal during the final grant callback. Local XTDB
is unavailable here; that physical test remains pending CI.

This is an observation at the terminal SQL snapshot, not a lease after return,
an atomic transaction across XTDB/Kurrent/object custody, or proof against every
other authority plane changing afterward. Every private backend operation keeps
its own fresh pre/post guard. The unchanged 60-second experimental budget and
actual backend latency remain required gates; no model-quality claim follows.

Files:

- `src/flora/selected/phase_source_fence.py`
- `tests/test_phase_source_fence.py`
- `tests/metadata_batch_fixture.py` (controlled tests only)
- `tests/integration/test_selected_phase_source_fence.py`
