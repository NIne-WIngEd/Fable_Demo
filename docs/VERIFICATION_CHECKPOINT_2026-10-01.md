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
- Lineage: both cases passed, suite **1,961.855 s**. Accepted episode/state
  recreation **1,798.857 s**; approved native state/history/output recreation and
  current revocation **162.998 s**. These qualify infrastructure, not learned
  episode or judgment quality.
- Native outcome/audit pilot: one case passed in **1,965.103 s**. Outcome audit,
  unknown tail and current permission withdrawal were exercised.
- Native typed-phase pilot: one case passed in **3,263.089 s** (suite
  **3,263.090 s**). Typed phase snapshot and grant-proof join preserve the
  BEFORE/tail boundary. All four isolated pilot cases passed at this head.
- Retained route: one case passed in **2,287.871 s** (suite **2,287.872 s**).
  Original claim/state/artifact replacement preserves the BEFORE route and live
  withdrawal. This is the first completed receipt for the isolated case.
- Native route: one case passed in **2,577.512 s**. Four distinct actual native
  invocations were recovered on their declared phase routes; supplied signed
  outputs qualify wiring, not learned behavior or response latency.
- History: coordinator passed in **100.530 s**. Preregistration registered
  original inputs in **96.752 s**, then published no first BEFORE capture in the
  remaining **55 min 52 s**. The job was cancelled at its unchanged one-hour cap.
  No chronological BEFORE/AFTER, update, final seal or response is qualified.
- Transport: BEFORE **15,262 ms**, AFTER **19,598 ms**, both `budget_exceeded`
  under **10,000 ms**. Provider authority case passed in **96.816 s**. Two tests,
  one failure, zero errors; suite **143.592 s**.
- Native comparison: BEFORE **60,073 ms**, AFTER **60,133 ms**, both timeout
  during owned context authorization under **60,000 ms**. Suite **249.750 s**;
  one test, zero passes. Other jobs retain their own receipt boundaries.

This ordinary run is fully accounted for: **40/43 physical cases passed**,
**two failed their unchanged response budgets**, and **one chronology case did
not complete before the unchanged job cap**. Its 695 contracts passed. Whole-case
pilot/route times and fictional producer receipts establish no learned behavior
or consumer-response latency.

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
- [First worker diagnostic](https://github.com/NIne-WIngEd/FloRA/actions/runs/36801543475):
  commit `58d6966c494d7bff10badc68e24e83c084846bfc`, tree
  `3e3a57299070f230647dbb86639ce04af9254c97`. Artifact `11136306383` has JSON
  SHA256 `e6c2ee6d532253db4e7310806f04377ac0b5ce1ebc4fdb99d494ac1c91b81f39`;
  its ZIP digest matches GitHub.
- Capped during setup: **180.009 s wall / 133.144 s parent thread CPU**, with
  **zero owned entries and zero worker ledgers**. Parent setup included 36,199
  SQL executes, 2,790 fresh streams and five context assemblies. These do not
  measure the later owned authorization path. All 108 after-source digests match
  the published tree/reference pin; all 107 before-source hashes remain unchanged.
- The wrapper workflow is green because it permits diagnostic failure. The
  fixture was capped with no pass, failure or ordinary error recorded; it remains
  unqualified. The follow-up omits non-RPC parent setup tags while keeping the
  same 180-second clock and RPC/owned-work cap fences. Optional diagnostics never
  qualify the ordinary latency gates.
- The narrower observer passed **41 local observer/seed-contract checks**,
  including four new setup-scope, nested-RPC and original-clock checks. All
  **89** FloRA procedure traces validate. The first published observer trace
  remains intact.


### First measured owned-reader work

- [Follow-up worker diagnostic](https://github.com/NIne-WIngEd/FloRA/actions/runs/36802794585):
  commit `0a690d0a557f5e719426e992c364bb2507c1e203`, tree
  `a44a2d787f048acfb343525bef59bc20d965ec54`, artifact `11136143617`.
  JSON SHA256 `82a85fb463fa2c1641ee99817d2fecab1761d84e406bc4102992f55317fee4e3`;
  ZIP SHA256 `b50e9656b0f59fae90552399664ebb969cef393f838ec10b02a90d987df67788`
  matches GitHub. All 109 after-source digests match the published tree and
  pinned A.L.I.C.E. reference; all 107 before-source hashes remain unchanged.
- First owned entry **147.530 s** after observer entry. Eight jobs ran on one
  worker ledger. Worker window **147.968 s wall / 111.495 s thread CPU**.
- Owned context authorization: **60.027 s wall / 44.391 s CPU**. The measured
  path includes **898 history metadata checks**, with **44.203 s exclusive CPU**
  (about 39.6% of worker CPU), plus **4,128 fresh streams** and **17,367 SQL
  executes**. Inclusive context/lineage/history spans overlap; they cannot be
  summed as independent costs.
- Original 180-second cap deferred 135 times during active work/RPCs. Observation
  ended at **295.511 s**, after **115.511 s** safe overshoot. No observer errors,
  ledger/stack overflow, open spans, active work or hook changes remained at close.
- The fixture **failed**, with no pass or ordinary error; `qualification=false`.
  The earlier zero-worker aggregate provides no worker performance comparison.

### Completed contract receipt and next repair

- The first observer publication's ordinary contracts passed: **711 tests across
  67 modules** on `58d6966c494d7bff10badc68e24e83c084846bfc`, run
  `36801543459`, job `110176760559`. Per-module durations total **1,141.307 s**.
  This is contract execution time and establishes no response latency.
- The current candidate concerns discarded immutable metadata reconstruction in
  `history_fence._committed`. Existing event validation, canonical replays,
  current grants and terminal withdrawal fences must remain.
- Per-entry native graph qualification costs more than the metadata work it
  would omit in a mechanical check. A finite call-local native batch might
  amortize that cost, but its cost, semantic pin and fallback checks remain
  unverified. **No candidate runtime change is published.**
- Workspace execution became unavailable before the batch measurement could run.
  The verified receipts and append-only FloRA measurement trace are preserved
  through GitHub. The existing 89-trace registry passed before this evidence-only
  update; full Python registry revalidation remains pending workspace recovery.

## Selective source proof build

The [architecture recalibration](LATENCY_ARCHITECTURE_RECALIBRATION_2026-10-01.md)
replaced the proposed micro-cost experiment with an explicit selective read
direction. The earlier measured failures remain evidence; no new observer or
codec microbenchmark is used to claim a repair.

- Added fresh registered locators and exact one-record Kurrent proofs. Scope,
  full digest, UUID, physical position and original commit time are checked.
- Added the explicitly named `selected-source-closure-v1` resolver. It follows
  nominated sources and their registered parents within a strict cap, invokes
  actual current purpose predicates, re-reads selected physical commitments,
  and finishes with one XTDB source/raw/action/head row observation.
- The new terminal fence performs guarded primitive comparisons after SQL,
  rather than invoking mutable contract helpers. Formatting-only metadata
  rewrites also fail closed in this new domain. Old generic fences are unchanged.
- Existing consumers, replay readers, context/history fences and scientific
  phase rules retain their behavior. This is not a whole-stream integrity
  certificate, a cross-engine atomic snapshot, a private-read lease, or a
  completed consumer switch. [Build details](SELECTED_SOURCE_CLOSURE.md).
- Verified all **95 restored dependency blobs** against the frozen Alice
  contract pin `4f287a488bc908bd04f99255ee01b794bacba50b`. No Alice repository
  changes were made. Local SDK checks use `kurrentdbclient 1.3.3`.
- Final local verification passed **173 tests across 10 focused modules** in
  **35.228 s**, with no failures or errors. This includes 38 new exact-target,
  15 new locator and 31 new closure cases plus existing event, codec, registry,
  phase-fence, context and lineage regressions. Test duration is not response
  latency; transport/SQL recorders do not establish physical-engine results.
- All **90 prior procedure traces** now pass the Python registry validator;
  the workspace-recovery validation noted above is complete. Shape validation
  still does not certify linked builder cases or transfer readiness.
- The new [selected-source procedure seed](fbm-seeds/2026-10-01_flora_selected_source_closure.jsonl)
  brings the validated registry to **91 traces**. It records this build and its
  limits in FloRA only; no seed is written to Alice.
- Integration discovery assigns **49 real-engine cases** exactly once across
  the original 12 shards; core contains **34**. The six new cases exercise
  persisted locators, wrong/missing coordinates, false locators, physical
  reappend, parent withdrawal and withdrawal during the second physical pass.
  Discovery is not physical execution; completed CI receipts are required.

Personality and MFM remain independent workstreams. No substitute, training,
download, semantic score or builder transfer is produced here. Original
**10,000/60,000 ms** response budgets and **60-minute** ordinary job caps remain
unchanged. This additive build does not yet qualify a latency improvement.
