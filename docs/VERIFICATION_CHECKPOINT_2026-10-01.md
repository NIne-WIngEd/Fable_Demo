# FloRA verification checkpoint — October 1, 2026

**Infrastructure work continues. This is not a model-only waiting point.**
Personality and MFM remain separate workstreams. No replacement model, learned
behavior result or builder transfer result is produced here.

## Published implementation

- Commit: `cebca97b7a67f8ef7b5607a702d6d5b6d389fef0`.
- Tree: `8177fe4af9cd1008da371991153c9499a7da8230`.
- [Ordinary selected-engine run](https://github.com/NIne-WIngEd/FloRA/actions/runs/36794412418):
  43 physical cases assigned exactly once across 12 integration jobs, plus contracts.
- [Optional chronology diagnostic](https://github.com/NIne-WIngEd/FloRA/actions/runs/36794412409):
  aggregate observation only. Its green workflow does not qualify the test.
- Standalone/native response budgets remain **10,000/60,000 ms**. Job caps remain
  **60 minutes**. Whole-case suite times are not response timings.

The repair reuses decoded immutable permission-action records after fresh
key/fetch operations. It does not cache current permission or qualification.
Separate pilot and routing jobs give each independent case its full existing cap.
The [September 30 checkpoint](VERIFICATION_CHECKPOINT_2026-09-30.md) preserves the
earlier source reviews, physical failures and method receipts.

## Completed ordinary receipts

Other jobs remain unqualified until their completed receipts are recorded.

| Job | Exact-commit result | Limit of the evidence |
| --- | --- | --- |
| Contracts | All 695 tests across 66 modules passed; no failures, errors or skips. | Contract mechanics, including codec, source fences and observers. |
| Core | All 28 cases passed; suite 907.487 s. Actual selected-service restart/persistence and Temporal resume passed without repeating completed activity. | Includes signed assessment/release withdrawal, physical SELECT cancellation and DML-owner withdrawal; no learned-model result. |
| Readers | Both cases passed; suite 88.805 s. Recovery/current withdrawal 87.936 s; blocked physical pgconn retirement/no late SQL 0.869 s. | Fresh-read and recovery infrastructure. |
| Lineage | Both cases passed; suite 1,437.941 s. Episode/state recreation 1,319.197 s; approved state/history/output recreation and revocation 118.743 s. | Native lineage infrastructure; not learned episode or judgment quality. |
| Native pilot: withdrawal | One case passed in 140.917 s. Withdrawal during cipher read blocks later private reads. | No paired-response latency qualification. |
| Native pilot: before/tail | One case passed in 2,120.850 s. Actual BEFORE, accepted tail and unrelated correction are retained. | Whole-case time, not a paired-response deadline. |
| Native pilot: outcome/audit | One case passed in 2,265.598 s. Outcome audit, unknown tail and current permission withdrawal exercised. | First completed physical receipt after grouped-job caps; no learned outcome quality. |
| Native pilot: typed phase | One case passed in 3,293.899 s. Typed phase snapshot and grant-proof join preserve the BEFORE/tail boundary. | All four isolated pilot cases passed at this implementation; whole-case time is not response latency. |
| Native routes | One case passed in 2,320.896 s. Four distinct actual native invocations were recovered on their declared phase routes. | Signed supplied outputs/usage counters qualify wiring; not model latency, chronological preregistration or learning. |
| History | Coordinator passed in 90.657 s. Preregistration registered original inputs in 85.739 s, then published no first BEFORE capture in the remaining 56 min 18 s; job cancelled at the unchanged one-hour cap. | No AFTER, update, final seal, response or chronological qualification. |
| Retained route | No case completed before the unchanged one-hour cap. | Separating the job did not qualify this path. |
| Transport | Comparator failed: BEFORE 15,479 ms / AFTER 20,136 ms, both `budget_exceeded`. Provider authority/failure case passed in 99.450 s. Two tests, one failure, zero errors; suite 147.040 s. | Both ordinary responses still exceed 10,000 ms. |
| Native comparison | Failed: BEFORE 60,068 ms / AFTER 60,128 ms, both timeout during owned context authorization. One test, zero passes; suite 237.878 s. | Both responses still exceed 60,000 ms. |

Completed logs are evidence for the named commit only. Fictional producer ports
in infrastructure fixtures do not establish real MFM formation or personality
judgment quality.

## Actual transport aggregate

Artifact `11133446168` is tied to the ordinary transport job `110154425161`.
Its ZIP digest matches GitHub. Loaded permission source is
`c3050590d7ccc0926989fd1118636d93750f5f99a0fb4cadeaa02d2108ae19d7`.
Aggregate JSON SHA256:
`0615c56f2cf64e234952fa25bb3517d4f3f0d570596b3a44ecb7abb2a9fccb27`.

- Observed wall/thread CPU: **86.998/74.305 s**, down from **90.319/76.352 s**
  in the preceding observer run. The observer itself adds overhead.
- All 17 observed function counts match: **6,120 SQL executes**, **3,419 fresh
  Kurrent streams**, **25,590 stored-action reads**, **9,668 current-action
  resolutions**, **1,817 permission checks** and **301 history verifications**.
- Largest exclusive observed CPU: stored actions **18.315 s**, Kurrent stream
  reads **13.353 s**, history verification **12.774 s**, current actions
  **8.193 s**, permission checks **6.202 s**.
- Combined observed RPC wall/thread CPU: **26.993/14.787 s**. Their difference
  includes waiting, scheduling and other-thread work; it is not wire latency.
- One ordinary assertion failure; no diagnostic cap, overshoot or errors.
  `qualification=false`. These measured costs do not replace ordinary timings.

## Actual chronology aggregate

Artifact `11133313585` runs the unchanged original preregistration case, using
the selected real engines. The optional driver stopped before the next outer
RPC at its **180-second soft cap**; driver exit 1 is permitted by that diagnostic
workflow. It reports **incomplete**, `qualification=false` and the unchanged
**60,000 ms** protocol response budget.
Aggregate JSON SHA256:
`5a53d540fd789f7b0155388562514902c5b423c36b5fdf4ebf7c9277022b5e5e`.

- Observed wall/thread CPU: **180.032/141.522 s**; overshoot **0.032 s**.
- All 115 before/after loaded-source hashes match. No changed or newly loaded
  source module was reported.
- The declared-capture helper entered once. The original first BEFORE guard
  entered once. Context assembly and lineage target counts remain zero.
- At the cap, a personal source fence was open inside the capture guard.
  No capture publication, response, update, seal or successful route is inferred
  from entry/return counts; exception unwinds also generate profile returns.
- Across setup and observed fixture work: **36,410 SQL executes**, **2,353 fresh
  stream reads/replays**, **85,487 stored-action reads**, **38,346 current-action
  resolutions**, **10,917 permission checks** and **246 current-history checks**.
- Exclusive observed CPU in stored-action/current-action/permission work totals
  roughly **62.7%** of thread CPU. The aggregate includes about **163.719 s before
  declared helper entry**; it cannot assign all of that work to the first BEFORE.

## Next repair boundary

- Review repeated immutable action reconstruction and fresh source/raw metadata
  reads using these actual costs. Preserve current reads, effectful/custom paths,
  exact source joins and terminal fences; cache no positive authority result.
- Finish ordinary pilot, chronology, routing, core, lineage and contract receipts.
- Integrate only independently qualified real personality/MFM exports later.
  Behavioral comparison and successful Part 1 evidence still precede the small
  learned builder transfer experiment.

No response budget increase, incomplete-case omission or optional diagnostic
success can establish readiness.

## Local follow-up candidate

- Typed-action material handoff remains **held**. Its fresh qualification and
  private ownership interface could cost more than the validation it removes.
- Existing codec eligibility loops are simplified with the same checks and
  ordering. All 66 codec/source-fence/preregistration checks pass; independent
  review and 43 independent checks pass. The
  [predicate method record](ACTION_CODEC_ELIGIBILITY_LOOP_WORK.md) separates
  its internal timing improvement from missing physical qualification.
- Native nominated source/raw query batching is **held**. The prototype's local
  reconstruction checks do not qualify native Cursor and adapter loader/dumper
  callbacks; batching could reorder those effects. The existing sequential
  runtime is retained. The [method record](COMPARISON_METADATA_PAIR_WORK.md) and
  FloRA procedure seed preserve the failed boundary without a performance claim.

## Late receipts from the preceding observer-only run

These belong to `6a1afd975093e7684f9ca8c0d960e04ce892547a`, not the current
implementation:

- Native pilot: first case passed in 2,202.084 s; the other three did not complete
  before the existing one-hour cap.
- History: coordinator passed in 108.014 s; preregistration registered original
  inputs, then published no first BEFORE capture in the remaining 55 min 28 s.
- Combined routes: no case completed before the existing one-hour cap.

The new separate jobs preserve all original cases and caps; old outcomes do not
qualify the newly isolated jobs.

## Guard-loop follow-up: published, verification ongoing

- Commit `027b363b9625daa90cbedab6e10667c11091eb0d`, tree
  `926fe58c1ba6fdebea3486bec6c44051d587f806`.
- [Ordinary run](https://github.com/NIne-WIngEd/FloRA/actions/runs/36797599008),
  [optional chronology run](https://github.com/NIne-WIngEd/FloRA/actions/runs/36797599015).
- Permission source SHA256:
  `b8b088256d5ef3f55f310181fd207559c0dd978ec90ceb4ee129e527a2214278`.
- Comparison source remains exactly the pre-prototype implementation:
  `5cf6300f389feb6636caa80c81d7391a000ccadb3ba3a1979aec35651d49a010`.
- Readers: both cases passed, suite **94.769 s**; guarded recovery/revocation
  **93.901 s**, physical blocked-pgconn retirement/no late SQL **0.868 s**.
- Contracts: **695 tests across 66 modules**, all passed; no failures, errors
  or skips.
- Core: **28/28** passed, suite **944.353 s**. All actual restart/persistence and
  Temporal no-repeat checks passed. Assessment release withdrawal **639.959 s**;
  SELECT cancellation **0.834 s**, final callback withdrawal **2.848 s**,
  DML-owner withdrawal **0.388 s**.
- Native withdrawal: one case passed in **96.513 s**.
- Native before/tail pilot: one case passed in **1,430.465 s**. Its actual BEFORE,
  accepted tail and unrelated correction are retained; this whole-case time
  does not qualify the paired-response deadline.
- Transport: BEFORE **15,262 ms**, AFTER **19,598 ms**, both `budget_exceeded`
  under **10,000 ms**. Provider authority case passed in **96.816 s**. Two tests,
  one failure, zero errors; suite **143.592 s**.
- Native comparison: BEFORE **60,073 ms**, AFTER **60,133 ms**, both timeout
  during owned context authorization under **60,000 ms**. Suite **249.750 s**;
  one test, zero passes. Other jobs retain their own receipt boundaries.

Only the eligibility checking loops changed in the runtime. Neither query
batching nor typed-action material handoff was shipped. All **87** FloRA
procedure traces validate; they are not trained or qualified builder cases.

### Follow-up measured costs

Actual transport artifact `11134436917` matches the published source and GitHub
ZIP digest. JSON SHA256:
`12b46e512b8984cc50123711db5a4190c7651ae78e451a7dfdd58424c8939df1`.

- All 17 observed counts match the preceding aggregate, including **6,120 SQL
  executes**, **3,419 fresh streams** and **25,590 stored-action reads**.
- Observed wall/thread CPU decreased **86.998/74.305 s → 81.668/68.803 s**;
  stored-action exclusive observed CPU **18.315 s → 12.983 s**.
- Combined RPC wall/thread CPU: **27.194/14.846 s**. No cap/overshoot; ordinary
  assertion failure retained, `qualification=false`. Observer costs are not
  ordinary latency receipts.

Actual chronology artifact `11134301927` also loads the published source, with
115 unchanged before/after module hashes and the same driver/observer/fixture.
JSON SHA256:
`91c3f10f917151467982fe60dc302e4a6a8cc5e9de0721356f9dc5229e4b893a`.

- Capped/incomplete: **180.042 s wall / 134.441 s thread CPU**.
- This run stopped during original body setup, before the declared BEFORE
  helper; capture/context/lineage counts are zero. Its prefix differs from the
  preceding capped run, so smaller counts do **not** establish higher throughput.
- Parent-only coverage still cannot attribute the native comparison's owned
  context-worker timeout. No worker, model, timeout or authority behavior has
  been changed.

### Original owned-worker diagnostic

- The [native worker method](NATIVE_BOUNDARY_PROFILE_WORK.md) observes the unchanged
  original selected-engine comparison case, including its owned reader threads.
- Each classified thread has bounded numeric counters and its own CPU clock.
  Observation retains no frames, payloads, SQL or thread identifiers. It leaves
  reads and later-installed hooks untouched and suppresses late fixture output.
- The optional cap remains **180 seconds**, applied only before a new parent RPC
  while no observed RPC or owned work is active. Cleanup can overshoot; response
  and backend deadlines remain unchanged.
- **37 local observer and seed-contract checks passed**, including the 16 native
  lifecycle/privacy checks. All **88** FloRA procedure traces validate. These are
  mechanics and method evidence, not qualified builder or learned-model cases.
- The first exact published-head selected-engine worker aggregate is still
  pending. Optional diagnostics never qualify the ordinary latency gates.
