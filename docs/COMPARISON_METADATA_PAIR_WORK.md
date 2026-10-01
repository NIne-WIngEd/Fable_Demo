# Held comparison source/raw metadata pair

**Decision: HOLD.** No comparison metadata runtime change is included. The
original sequential registered-source and raw-reference reads remain in place.
The standalone comparator's **10,000 ms** response budget is unchanged.

## The bounded idea

A freshly validated comparison artifact independently nominates its event and
raw object IDs. A prototype used those exact keys in one tagged `UNION ALL`
metadata statement, with `LIMIT 3` to detect ambiguity across either nomination.
It rejected mismatching source `object_ref` before using the nominated raw row
and replayed the existing schema, scope, digest and reference-binding decoders.
It retained the initial fresh artifact read and canonical Experience validation.

The prior **controlled** attribution counted 694 comparison metadata calls and
1,388 source/raw statements. That motivated the candidate; it was not evidence
of actual eligibility or a physical saving. The completed physical aggregate
contains 1,807 metadata calls and has no pair-eligibility counter. No actual
query saving or latency improvement is claimed.

## Why the prototype was held

Combining these reads moves raw metadata retrieval ahead of source decoding and
reconstruction. It also changes the number and order of driver callbacks.
Native method and receiver identities alone do not establish that those paths
are free of effects:

- The reviewer reproduced native eligibility while `Cursor.execute`,
  `Cursor.fetchall` or `Cursor.__init__` had custom implementations.
- Native psycopg connections can carry custom adapter loaders and dumpers.
  A row loader can run before reconstruction, where the sequential path would
  run it later. The selected connection also registers a generated XTDB string
  dumper, so a blanket adapter identity check would not qualify its configuration.
- Static fingerprints for constructors, canonical helpers, JSON configuration,
  access machinery and copy protocols addressed local reconstruction changes;
  they did not establish the remaining per-connection driver qualification.

Expanding into a driver qualification audit exceeded the approved bounded seam.
The runtime prototype and its new tests were removed. The unpublished patch is
retained only at `/tmp/flora-metadata-pair-held-20261001.patch`; it is not shipped
or a reusable authority boundary.

## Evidence and builder lesson

The pre-hold prototype passed 18 focused component checks using actual registry
decoders over explicitly controlled rows and unconnected typed eligibility
handles. A final cursor-exclusion regression raised that local count to 19.
Those checks covered row mechanics and local rejection behavior; they did not
qualify physical selected-engine behavior, complete callback equivalence or the
response budget.

Batching immutable metadata can still change meaningful effects. A smaller
statement count is insufficient evidence for adoption. Preserve the original
custom, guarded, copied and effectful paths until an explicitly owned native
configuration can be qualified. No authority answer or grant may be cached, and
no model, substitute, GPU, paid API, synthetic workload or calibration belongs
in this infrastructure check.
