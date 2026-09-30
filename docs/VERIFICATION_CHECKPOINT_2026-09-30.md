# FloRA verification checkpoint — 2026-09-30

**The independent infrastructure work is still active.** Selected-engine checks
have passed for core storage, recovery and guarded readers. The comparison
still exceeds its registered response deadline. Native execution exposed a
pilot guard-contract error, and both history groups reached the one-hour cap.
This is not a model-only stopping point.

## Exact implementation and receipts

Implementation: `5cc36c6754df5e6dcdf99d0581a3f042fcd73077`.
Tree: `3e447fa4b47a5b91e98c084d26277e8d541cb545`.
A.L.I.C.E. contract pin: `4f287a488bc908bd04f99255ee01b794bacba50b`
(formation schema 1.2.0).

[Run 36755050656](https://github.com/NIne-WIngEd/FloRA/actions/runs/36755050656)
uses the selected Stage G–J engines. Results below qualify this implementation
only; they do not qualify a later repair automatically.

| Gate | Observed result | Meaning |
| --- | --- | --- |
| Component contracts | Success: 549 tests in 53 isolated suites | Contract and denial regressions pass. This is not real-model evidence. |
| Core selected engines | Success: 28 tests, 599.024 seconds for the suite | The included storage, authority, formation and governance fixtures pass on the selected engines. |
| Storage restart | Success | KurrentDB, XTDB and NATS were restarted; persisted probes were verified and the pending edge was consumed afterward. |
| Persistent Temporal restart | Success | PostgreSQL and Temporal were restarted; the pending workflow resumed without repeating its completed activity. |
| Guarded readers and physical watchdog | Success: two tests | Fresh sessions, recovery, archive access and live revocation passed. The actual PGconn response-blackhole and owner-retirement test passed. |
| Native lineage | Success: two tests, 2,288.577 seconds for the suite | Episode and approved-state lineage, output recreation and revocation passed on the selected engines. This is not a paired response timing result. |
| Comparator/provider transport | Failure: one failure and one error | The comparator exceeded its deadline. The provider-ledger fault fixture also needs its source-frame anchor updated after the sampled-reader refactor. |
| Native comparison and pilot | Failure: two failures and three errors across five cases | The pilot guard returns `True` where current-context authority guards require `None` on success. The comparison retains two `failed` attempts; its underlying exception still needs a structural diagnostic. |
| Chronological history | Cancelled at the one-hour cap | Coordinator passed. Preregistration completed baseline, cohort, recipe, anchor and original-input registration, then published no first BEFORE capture before cancellation. |
| History routes | Cancelled at the one-hour cap | No route case completed; no internal route stage is inferred. |

The core suite duration is not a response latency. The reader fixture's
111.434 seconds includes setup and multiple operations; its physical watchdog
case took 0.868 seconds. Neither duration qualifies a paired response budget.
Qdrant was exercised by the integration suite but was not restarted by this
workflow; the storage restart receipt is limited to the named services.

## Remaining observed defect

The standalone comparator registers **10,000 milliseconds** per response.
Its expected BEFORE and AFTER successes instead took **41,877** and **69,269**
milliseconds and were retained as `budget_exceeded` attempts. Those failures
stay in the record. The budget is not being raised.

The repair targets repeated authentication of the same held immutable history.
Initial custody authentication remains mandatory; every reuse must still
check current source and permission metadata and the final authority boundary.
Controlled query reductions will not qualify the latency requirement. A new
exact-commit selected-engine run must demonstrate it.

The chronological case's last completed milestone was original-input
registration at 116.859 seconds. It had another 55 minutes before cancellation
without a BEFORE publication receipt. That does not establish any BEFORE
seal, authorized update, AFTER capture or final binding. Both history groups
ended without a segmentation fault or an immediate Python error. Controlled
callback/query profiles are being used to locate the slow path; they are not
physical latency measurements.

## Repair candidate included with this record

- Authenticate the original immutable comparator history once per owned run,
  then verify current source, permission and canonical metadata at each reuse.
  Guarded coordinator copies retain their complete authentication path.
- Preserve installed phase-object guards when copying their facade instead of
  installing the same guards again. Repeated copies now keep the same callback
  count; withdrawal during ciphertext access still prevents decryption.
- Run native phase predicates against this call's sampled metadata. Custom
  delegates keep their live path, and terminal checks still compare current rows.
- Remove the pilot guard's boolean success return to satisfy the existing
  void-return authority contract. Add structural exception diagnostics to the
  native comparison fixture without publishing private exception messages.
- Reuse sampled native decoders for the redundant history-metadata second pass.
  Both real artifact reads and canonical replays remain. Custom readers keep
  their uncached path; every observed row is checked at the terminal SQL fence.

Focused regressions and independent reviews pass. One controlled native history
fixture fell from 24/31 queries to 10/10 for two/three originals. This is a query
count result, not a physical response time or a completed history capture.
The local transport-only chronological profile was interrupted before its first
BEFORE publication; it provides no completed capture receipt. The next full
selected-engine run must qualify the combined repair at its exact commit.

## Stopping boundary

- Finish the observed transport repair and every included engine, fault and
  recovery group at one implementation commit.
- Preserve a named missing-model boundary and the existing evidence and state
  when the separately built personality and MFM exports are absent.
- Integrate only qualified real exports from their workstreams. These tests
  use fictional producer responses and do not demonstrate learned formation,
  native judgment quality or behavioral superiority.
- The model-dependent pilot must establish its operating budget and protocol
  before a held-out cohort and numerical acceptance thresholds are frozen.
- Limited FBM training and transfer remain after a successful Part 1 result.
  Procedure traces saved here are not trained builder cases.

The [frozen experiment goal](EXPERIMENT_GOAL.md) is unchanged. The original
[readiness audit](READINESS_REAUDIT_2026-09-29.md) records why the previous pause
was premature; this checkpoint records the later execution evidence.
