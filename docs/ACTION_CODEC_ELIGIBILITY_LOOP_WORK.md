# Native action-codec eligibility loops

The real October 1 transport and chronology aggregates still report permission
metadata work as a major cost. The current-action material handoff proposal was
held: qualifying each typed reconstruction could erase its benefit and would
introduce another private ownership interface.

This smaller change keeps the existing native eligibility predicate and all its
checks. Generator-based `any` expressions become explicit early-return loops.
The predicate still checks class members, keyword defaults, closure cells and
JSON-instance fields in the same order. Native policy key/fetch overrides remain
the same deliberate exceptions. Constructors, JSON settings, helper code,
library bindings, owner checks, fresh reads and authorization are unchanged.

## Evidence and limits

- Published baseline source SHA256:
  `c3050590d7ccc0926989fd1118636d93750f5f99a0fb4cadeaa02d2108ae19d7`.
- Candidate source SHA256:
  `b8b088256d5ef3f55f310181fd207559c0dd978ec90ceb4ee129e527a2214278`.
- A pure-predicate measurement loaded the immutable published source and current
  source in one process. Eight alternating blocks per version made 3,000 native
  eligibility calls each. Every call returned true in the unchanged environment.
- Median block: baseline **0.115782 s**, candidate **0.071576 s**. This measures
  only the predicate, with no models, storage fixture or physical endpoint.
  It cannot establish whole-response latency or experiment qualification.
- All 29 existing action-codec regressions passed in **0.705 s** after the change.
- The combined 66 codec/source-fence/preregistration checks passed in **18.104 s**.
  Independent review approved the same ordering and fallback semantics;
  43 independent codec/source-fence checks passed in **1.461 s**. Source and
  unchanged codec-test hashes remained stable.

The same actual-engine budgets remain 10,000/60,000 ms. The next published
implementation still needs real-engine timing and ordinary gate receipts.
The optional chronology workflow also triggers on changes to the measured
permission/source/comparison metadata modules. Its driver and reused observer
remain unchanged; diagnostic success never replaces an ordinary gate.
