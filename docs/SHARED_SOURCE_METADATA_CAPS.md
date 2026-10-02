# Shared source metadata caps

Date: 2026-10-02
Status: collector extension; shared serving-frame integration remains pending

This is a small extension to the existing `OneGuardSelectedMetadata` helper,
not a new memory service. It supports the next step in the
[authority-frame protocol](SELECTED_AUTHORITY_FRAME_PROTOCOL.md) within the
[narrow prototype scope](FLORA_CONTEXT.md).

## Existing and bounded nominations

`prime_source_purposes()` continues to accept a tuple of `(source_ids, purpose)`
pairs for existing callers. Those callers retain their merged-by-purpose
inventory and combined metadata-row cap.

New callers can supply `(source_ids, purpose, source_cap)` triples. Each
nomination keeps its own complete registered parent-closure cap, including when
two nominations share a purpose. Overlapping source and raw rows are sampled
once within this guard; purpose heads/actions remain distinct. Parents count
toward the respective cap. Excess closure and cycles reject without truncating
into success. Mixed pair/triple forms and duplicate bounded domains reject.
The existing `maximum_rows` cap bounds the combined sampled dependencies.

```python
inventory = sample.prime_source_purposes((
    (held_original_ids, evaluation_purpose, held_source_dag_cap),
    (context_source_ids, "personal_judgment", context_source_dag_cap),
), raw_object_ids=raw_metadata_extras)
```

The returned inventory merges IDs by purpose for navigation. It is **not**
a per-domain integrity or authorization proof. Keep the declared nominations
and their ownership in the caller; this inventory cannot replace them.

## Boundary retained

- Collection samples source, raw-reference, current permission-head and exact
  action rows. It executes the existing source/action reader callbacks.
- Collection invokes no `permits` predicate and makes no early terminal fence.
  The caller still owes actual current predicates, physical event/phase
  verification and the final current-row observation.
- A later withdrawal, including an unselected held-history evaluation grant,
  must invalidate the final observation. Collection grants no later private read.
- Raw-only object extras consume metadata-row capacity and invent no purpose
  grant. This source-DAG helper does not automatically count a physical history
  manifest against H. The future H contributor must separately account for
  that manifest in H's cap and verify its exact custody. C and each phase
  ancestry keep their own specified limits.
- Every new protected boundary still needs fresh construction. No positive
  allow, current head, qualification or permission lease is cached across calls.
- New triple callers are not activated in the serving path by this change.
  Initial private assembly and the full H/C/Claim/state joint frame remain
  subsequent work, including the privately issued origin/gated-policy contract.

## Custom reader repair

The existing batching classifier compared a reader with the **current** class
attribute. A class-level replacement could therefore be mistaken for a native
reader and have its denial or side effects skipped. Classification now requires
the original reader identity/code, its exact native owner and no instance
override. Class replacements, subclasses and in-place code changes execute
their actual readers through the existing fallback. An inherited registry
subclass consequently performs four additional intentional fallback SQL reads
in the held-history regression; its fresh second pass remains required.

Native tuple/string/integer nomination shapes are checked before effectful
hashing or iteration. These checks preserve metadata collection behavior; they
do not qualify arbitrary application extensions or replace frame-origin checks.

## Verification

Controlled contract tests cover separate and same-purpose caps, overlap,
parents/cycles, changed rows, late H/C withdrawal, row limits, effectful malformed
inputs, and instance/class/subclass/code reader callbacks. The
[October 2 checkpoint](VERIFICATION_CHECKPOINT_2026-10-02.md) records the final
source hashes and exact test selection. Local fixture behavior is not physical
consistency, whole-stream integrity, response latency or learned judgment.
