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

## Combined repair run — completed receipts

Implementation: `c6150be27d2623eae12061ccab4924c669234ef3`.
Tree: `885a33e8337ba42d0ad74ec1e02f0a71219437e8`.
[Run 36767672665](https://github.com/NIne-WIngEd/FloRA/actions/runs/36767672665).

| Completed gate | Observed result |
| --- | --- |
| Component contracts | Success: 584 tests in 55 isolated suites. |
| Core selected engines | Success: all 28 cases; 841.021 seconds for the suite. Storage and persistent Temporal restart probes also passed. |
| Guarded readers | Success: both cases; fresh-session/recovery/revocation fixture 79.666 seconds, physical PGconn watchdog 0.866 seconds. |
| Native lineage | Success: both cases; episode/control/state recreation 1,502.736 seconds, approved-state/history/output recreation and revocation 137.461 seconds. Whole fixtures are not paired response timings. |
| Native comparison and pilot | Failure: one withdrawal case passed, one comparison failed and three positive pilot cases errored. Suite 3,247.935 seconds. |
| Comparator/provider transport | Failure: BEFORE 23,210 milliseconds and AFTER 31,362 milliseconds, both `budget_exceeded` against the unchanged 10,000-millisecond budget. |
| Chronological history | Cancelled at the unchanged one-hour cap. Coordinator passed in 86.345 seconds; preregistration reached original-input registration at 88.070 seconds, then published no first BEFORE capture in the remaining 56 minutes. |
| History routes | Cancelled at the unchanged one-hour cap; no completed route case or internal stage receipt. |

The provider fixture also failed before its intended final external callback:
an AFTER evaluation grant withdrawn by an earlier retention scenario had not
been restored. That earlier denial was genuine. The fixture repair restores
only that scenario precondition, retaining the original terminal-denial,
callback-executed and private-ciphertext assertions.

The native comparison failed on an owner-proof fixture binding: a byte-read
facade was supplied where the actual metadata/read custody was required. The
pilot's three positive cases reached a second guard seam: the void authority
callback was passed to a source-read guard requiring `True`. A dedicated adapter
must call the void guard freshly and return `True` only after it completes;
neither existing strict contract is relaxed.

Both history groups ended without an immediate assertion or segmentation fault.
No BEFORE seal, probe, update, AFTER capture or final binding is inferred. The next repair
also addresses confirmed guard-copy amplification in the general manifest and
provider object facades. The standalone fixture never calls those copy methods;
that repair is not evidence that its response deadline has been met.

The next CI partition separates the one native comparison case from the four
pilot cases. Discovery still includes every one of the 43 physical integration
cases exactly once across eight shards. Component contracts remain a separate
job; all nine jobs must qualify the same implementation. Job caps and response
budgets are unchanged. Discovery is not a physical execution receipt.

The shared-purpose candidate's identical controlled workload uses 6,120 SQL
calls instead of 7,254; recorder calls fall from 3,472 to 2,338. Without cProfile,
BEFORE and AFTER completed in 3,097 and 4,579 milliseconds with unchanged
recorded source hashes. These controlled transports do not qualify actual
engine latency. Profiling overhead is reported separately rather than used as
a response measurement.

The metadata-only chronological slot candidate retains both original current
checks, both predicate bodies and all 70 authority callbacks. Its typed controlled
fixture uses 25 SQL reads instead of 52 and two actual canonical replays instead
of 11. The frame ends before private reads or producer/update qualification;
final canonical and metadata fences still reject withdrawal, new stage or
evaluation evidence, previously absent keys and changed frozen inputs. These
counts do not establish physical latency or a completed BEFORE capture.

## Second combined repair — completed receipts

Implementation: `8a8f41e26163aeb48f9b871fea6c198204a4d38e`.
Tree: `cf2fc78ea271eff42610cb8ec65da9055897c5c1`.
[Run 36778736018](https://github.com/NIne-WIngEd/FloRA/actions/runs/36778736018).
All jobs have completed. The timing failures and unfinished cases prevent an
all-job qualification at this implementation.

| Completed gate | Observed result |
| --- | --- |
| Component contracts | Success: 622 tests in 61 isolated suites; no failures, errors or skips. |
| Core selected engines | Success: all 28 cases, 551.158 seconds for the suite. Storage restart and persistent Temporal resume probes passed. |
| Guarded readers | Success: both cases, 81.357 seconds for the suite. Fresh-session/recovery/revocation took 80.476 seconds; actual blocked PGconn retirement took 0.881 seconds. |
| Native lineage | Success: both cases, 2,402.533 seconds for the suite. Episode/control/state recreation took 2,196.069 seconds; approved-state/history/output recreation and revocation took 206.464 seconds. These are whole-fixture durations, not response timings. |
| Provider fault fixture | Success: 147.974 seconds. Restoring the independent race precondition lets the actual final callback run and deny the private read. |
| Standalone comparator | Failure: BEFORE 23,041 milliseconds and AFTER 31,976 milliseconds, both `budget_exceeded` against the unchanged 10,000-millisecond budget. |
| Native comparison | Failure: both attempts timed out during context preparation/authorization, BEFORE 60,116 milliseconds and AFTER 60,226 milliseconds against the unchanged 60,000-millisecond budget. The earlier owner-custody binding error is cleared. |
| Native pilot | Cancelled at the unchanged one-hour cap. One positive case passed in 2,667.285 seconds; the remaining three have no completed receipt. This clears the earlier source-port error for that case, not a response deadline. |
| Chronological history | Cancelled at the unchanged one-hour cap. Coordinator passed in 131.935 seconds; preregistration reached original-input registration at 133.000 seconds, then published no first BEFORE capture in the remaining 54 minutes 42 seconds. |
| History routes | Cancelled at the unchanged one-hour cap; no completed route or internal stage receipt. |

The core assessment case completed its arithmetic, then its last unblind callback
persisted an actual typed owner withdrawal. `analyze_after_seal` denied release.
This checks the final authority boundary; it is not a behavioral assessment.

An immutable, controlled-transport 90-second chronological diagnostic reached
original-input registration and entered the first BEFORE capture. It stopped
safely at a controlled SQL boundary without completing or publishing that
capture. Its partial capture traversed 47,690 encoded records across 502 actual
canonical replays. Source hashes stayed unchanged. It does not establish any
later chronological stage or physical timing.

The identical paired workload using the actual Kurrent envelope codec over a
controlled encoded client makes 3,419 fresh stream reads and decodes 87,350
records although only 35 unique records were appended. Replay used 32.465 of
57.280 profiled seconds. Without profiling, the controlled BEFORE and AFTER
attempts took 6,736 and 9,671 milliseconds. The physical comparator still fails;
these controlled measurements identify repeated immutable decoding for the next
narrow repair, not a satisfied physical response budget.

The frozen codec candidate uses exact SDK record carriers, private bounded
immutable field snapshots and fresh returned event/scope/provenance objects.
It still performs all 3,419 stream reads, all 6,120 SQL calls and every physical
record check. Independent focused verification passed 84 tests. In the identical
unprofiled controlled workload, total time fell from 19.139 to 10.873 seconds;
BEFORE/AFTER fell from 6,841/9,402 to 3,534/5,795 milliseconds. Native decodes fell
from 87,350 to 35. Custom records, generators, delegates and callback machinery
retain the original uncached path. These receipts identify a useful controlled
repair; a new exact-commit engine run must establish physical response timing.

## Immutable envelope repair — completed physical receipts

Implementation: `f3cddfd2b849b00580a95842e349e9f985505db8`.
Tree: `7425ee3cf6b991ea9af07b11cb1e958e047fe0e3`.
[Run 36784876518](https://github.com/NIne-WIngEd/FloRA/actions/runs/36784876518).
All jobs have completed. Timing failures and unfinished cases prevent a full
qualification of this implementation.

| Completed gate | Observed result |
| --- | --- |
| Component contracts | Success: 643 tests in 62 isolated suites; no failures, errors or skips. |
| Core selected engines | Success: all 28 cases, 951.157 seconds for the suite. Storage restart, persistent Temporal resume and the actual final assessment callback withdrawal denial passed. |
| Guarded readers | Success: both cases, 99.487 seconds for the suite. Session/recovery/revocation took 98.618 seconds; actual blocked PGconn retirement took 0.869 seconds. |
| Native lineage | Success: both cases, 1,887.451 seconds for the suite. Episode/control/state recreation took 1,730.209 seconds; approved-state/history/output recreation and revocation took 157.242 seconds. Whole-fixture durations are not response timings. |
| Provider fault fixture | Success: 109.136 seconds. |
| Standalone comparator | Failure: BEFORE 17,585 milliseconds and AFTER 22,604 milliseconds, both `budget_exceeded` against the unchanged 10,000-millisecond budget. They improve by 5,456 and 9,372 milliseconds over the prior run but do not pass. |
| Native comparison | Failure: BEFORE 60,102 milliseconds and AFTER 60,184 milliseconds, both `timeout` against the unchanged 60,000-millisecond budget. Both now reach context authorization; neither response qualifies. |
| Native pilot | Cancelled at the unchanged one-hour cap. One of four cases passed in 1,947.869 seconds; the other three have no completed receipt. |
| Chronological history | Cancelled at the unchanged one-hour cap. Coordinator passed in 74.940 seconds; preregistration reached original-input registration in 70.981 seconds, then published no first BEFORE capture in the remaining 56 minutes 33 seconds. |
| History routes | Cancelled at the unchanged one-hour cap. The retained-route and live-withdrawal case passed in 3,518.312 seconds. The strict-router case had only 31.366 seconds left and did not complete. |

The remaining same-workload query profile still has 6,120 SQL calls and 3,419
fresh stream reads. Actual transport/CPU attribution is the next diagnostic;
query counts alone do not prove which remaining transport dominates latency.
The recorded failures remain part of the evidence. No budget is raised.

## Aggregate transport diagnostic — partial physical receipts

Implementation: `6a1afd975093e7684f9ca8c0d960e04ce892547a`.
Tree: `397415236c1c5eae1e1d42251aeb8976e028dbaf`.
[Run 36789254686](https://github.com/NIne-WIngEd/FloRA/actions/runs/36789254686).
The publication adds a failure-only observer and verification records; the
production runtime is unchanged. Other jobs remain pending.

| Completed gate | Observed result |
| --- | --- |
| Component contracts | Success: 655 tests in 63 isolated suites; no failures, errors or skips. |
| Core selected engines | Success: all 28 cases, 959.783 seconds for the suite. Restart/persistence/Temporal resume and actual last-unblind withdrawal denial passed. |
| Guarded readers | Success: both cases, 70.960 seconds for the suite. Recovery/current withdrawal took 70.093 seconds; blocked physical PGconn retirement took 0.867 seconds. |
| Native lineage | Success: both cases, 2,012.108 seconds for the suite. Episode/native state recreation took 1,841.844 seconds; approved-state/history/output recreation and current revocation took 170.263 seconds. Whole-fixture times do not qualify response latency. |
| Provider fault fixture | Success: 109.085 seconds. |
| Standalone comparator | Failure: BEFORE 16,540 milliseconds and AFTER 21,989 milliseconds, both `budget_exceeded` against the unchanged 10,000-millisecond budget. |
| Native comparison | Failure: BEFORE 60,071 milliseconds and AFTER 60,145 milliseconds, both `timeout` against the unchanged 60,000-millisecond budget. Both remain in owned context authorization. |

The subsequent aggregate diagnostic completed and uploaded its JSON with
artifact `11131985172`. It leaves the ordinary gate failed. Its profiled timing
cannot qualify response latency; see the
[observer method and overhead](EXPERIENCE_ENVELOPE_DECODE_WORK.md#aggregate-physical-boundary-diagnostic).

The verified aggregate completed in 90.319 seconds (76.352 thread CPU), with
no cap or overshoot. Its one failure is the ordinary comparator assertion;
`qualification` remains false. All six loaded runtime source hashes and the
observer hash match the published source.

| Original physical boundary | Calls | Profiled wall / thread CPU | Wall minus thread CPU |
| --- | ---: | ---: | ---: |
| Kurrent `get_stream` | 3,419 | 21.069 / 13.901 seconds | 7.168 seconds |
| psycopg `execute` | 6,120 | 7.813 / 1.511 seconds | 6.302 seconds |
| psycopg `fetchall` | 5,894 | 0.072 / 0.070 seconds | 0.001 seconds |

Wall minus CPU includes waiting, scheduling and other-thread work. It is not
exact network time. The largest exclusive profiled CPU costs were immutable
stored-action validation (25,590 calls; 19.624 seconds) and history metadata
(301 calls; 12.760 seconds). Profiling overhead is substantial, so these values
are diagnostic attribution rather than unprofiled costs or satisfied deadlines.
The next narrow candidate reuses validated immutable action-row decoding while
preserving actual key/fetch/head reads, all callbacks and terminal fences.
Current permission and qualification results must never be cached.

The next exhaustive runner assigns all 43 physical cases exactly once across
12 shards, plus contracts: the four pilot cases and two history-route cases
each receive an independent job. Discovery/partition checks and the chronology
driver/seed checks passed 14 tests in 1.206 seconds. This verifies configuration,
not physical execution. All 13 ordinary jobs still require completed receipts
at the same implementation; see the
[case partition](SELECTED_INTEGRATION_PARTITION.md).

The separate optional [chronology diagnostic](CHRONOLOGY_PROFILE_WORK.md) runs
the unchanged preregistration fixture with a 180-second outer-RPC soft cap.
It observes original synchronous parent-thread code objects and excludes later
owned child work. Its 60,000-millisecond protocol budget remains independent.
Its aggregate reports incomplete outcomes and cannot infer capture publication
from return counts. A green diagnostic job never replaces an ordinary gate.

## Stored-action decode repair — frozen candidate

The candidate keeps every actual key/fetch/head read, permission callback and
terminal current-row fence. It reuses only decoded fields of freshly read,
previously validated exact immutable action records, including their recorded
authorization metadata. Returned nested objects are fresh. A current allow
verdict, proof verification or permission result is never cached.

Final source SHA-256:
`c3050590d7ccc0926989fd1118636d93750f5f99a0fb4cadeaa02d2108ae19d7`.
Final test SHA-256:
`4e313c23594ec899dc65545928f0984ad553e7e843ad2c37e2cce2a0751e1121`.
After the native decoder-setting compatibility correction, 54 focused checks
passed in 45.647 seconds; independent review passed 29 codec cases in 1.002
seconds with stable hashes. Accepted deep records, custom receiver callbacks,
explicit null overrides, live revocation and changed native integer decoding
settings retain the original validation behavior.

The final immutable controlled candidate took 9.514 seconds, with BEFORE/AFTER
3,440/4,609 milliseconds. It retains all 6,120 SQL calls, 3,419 fresh stream
reads, 87,350 records and 98,302,270 encoded bytes, plus identical named boundary
and SQL leaf/shape counters. This is not an actual-engine latency receipt.
The earlier quiet pair and profiler measurements are explicitly tied to their
pre-correction source in the [method record](STORED_ACTION_CODEC_WORK.md).
All 85 FloRA procedure traces validate; no builder training is inferred.

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
- Post-seal analysis must consume the actual frozen rubric, label semantics and
  acceptance/uncertainty specification. A full independent Part1 semantic
  validator still requires the real producer and material contracts; a signed
  Boolean or an analysis result alone does not qualify Part1.
- Limited FBM training and transfer remain after a successful Part 1 result.
  Procedure traces saved here are not trained builder cases.

The [frozen experiment goal](EXPERIMENT_GOAL.md) is unchanged. The original
[readiness audit](READINESS_REAUDIT_2026-09-29.md) records why the previous pause
was premature; this checkpoint records the later execution evidence.
