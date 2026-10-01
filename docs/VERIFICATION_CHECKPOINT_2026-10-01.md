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
