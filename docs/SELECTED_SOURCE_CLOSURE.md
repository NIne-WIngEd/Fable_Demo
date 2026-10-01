# Selected source closure

FloRA can nominate the sources needed for one operation and resolve their
registered parents. It does not need to query every memory plane to do that.
This slice follows the [architecture recalibration](LATENCY_ARCHITECTURE_RECALIBRATION_2026-10-01.md).

## What this builds

- `XTDBFormationSourceRegistry.lookup_commitment()` reads the existing source
  and raw-reference rows. It exposes the full event digest, physical stream
  position and original Kurrent commit time already recorded at registration.
- `KurrentExperienceLog.lookup_committed()` requests exactly one physical
  Kurrent record, without link resolution. It checks stream, position, event
  type, scope, full digest, server UUID and original commit time.
- `SelectedSourceClosureResolver` follows the nominated sources' registered
  parent edges within an explicit cap. Every parent must be physically present
  at an earlier position. Missing, cyclic or over-cap closure fails; it is
  never truncated into a successful result.
- Actual current source-use predicates run. A final XTDB statement checks all
  observed source, raw-reference, permission-action and permission-head rows
  together after callbacks. No positive allow answer survives the call.

The new terminal fence compares exact stored metadata text and primitive
columns. It also rejects a formatting-only metadata rewrite. This conservative
rule applies to the new domain; the existing generic fences are unchanged.

The proof domain is explicitly named **`selected-source-closure-v1`**. It covers
the nominated lineage and current scoped purpose authority at the terminal
metadata observation. The resolver opens no private object bytes.

```python
resolver = SelectedSourceClosureResolver(
    registry=registry, log=log, permissions=permissions,
    maximum_sources=source_cap,
)
proof = resolver.resolve(
    source_event_ids=selected_event_ids, purpose="personal_judgment",
)
```

The nomination must be a nonempty tuple of unique IDs. A turn needing no memory
skips the resolver. The cap includes discovered parents, not just nominations.

## How this fits the workflow

1. The context plan chooses the required evidence and optional retrieval planes.
2. The resolver verifies that selected evidence and its original parent closure.
3. A consumer separately checks current Claim/state authority and phase rules.
4. Controlled materialization checks current authority around private I/O and
   validates the bytes it actually opens.

A returned metadata proof is an observation, not permission for a later read.
Another operation must resolve current authority again. Adaptive selection,
learned formation and learned judgment remain separate components.

Kurrent availability and the terminal XTDB rows are separate observations.
This does not create an atomic snapshot across engines or a continuing lease.

## Integrity boundary

One exact event lookup cannot detect corruption or duplicates elsewhere in the
stream. This new domain does not claim whole-stream integrity, global duplicate
absence, model phase exclusion, or correctness of unrelated Claims or missions.
Existing consumers, replay readers and whole-history fences retain their
existing behavior. There is no automatic fallback or default consumer switch.

The original registered commit time helps reject deletion/reappend with new
physical coordinates. The SDK supplies no stream-incarnation token that would
distinguish a hypothetical replacement with identical position, bytes and
physical time. No stream head or inferred generation is treated as proof.

The exact physical API requires the selected SDK record contract and rejects
subclassed or replaced replay receivers. Legacy/custom readers can continue
using their existing replay interface; their events are not converted into
invented physical target proofs.

## Evidence and remaining work

Controlled tests cover exact coordinates, stale locators, current authority,
reader rebinding and bounded closure. Real-engine cases live in
`tests/integration/test_selected_exact_commitments.py`; discovery alone is not
backend execution. The verification checkpoint records completed receipts.

This is infrastructure for a selective path, not a response-latency result.
[Selected context and history consumers](SELECTED_CONTEXT_AND_HISTORY.md) add
explicit opt-in domains, current Claim/state checks, private-read fences and
original before/after exclusion. Their implementation and actual-engine
qualification have separate receipts; the source proof alone does not qualify
consumer behavior or response latency.
Response budgets remain **10,000 ms** standalone and **60,000 ms** native;
ordinary CI jobs retain their **60-minute** caps.

Personality and MFM are not built, trained or substituted here. FBM records
remain procedure seeds in FloRA, not trained builder weights or transfer proof.
