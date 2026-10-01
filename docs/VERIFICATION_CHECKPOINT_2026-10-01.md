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

### Publication and physical gate

- Runtime publication: `479e61d67ec5e610e7ed15401e7b81d517403e4c`, tree
  `e3594bd0f5998d417089bc3c518294c62bb7b063`. All 11 changed paths and local
  blob hashes were verified against the complete GitHub trees before publication.
- [Ordinary selected-engine CI](https://github.com/NIne-WIngEd/FloRA/actions/runs/36815981435)
  is running at that exact commit: contracts and all 12 integration shards.
  No completed result is inferred from a running job.
- The existing [optional chronology diagnostic](https://github.com/NIne-WIngEd/FloRA/actions/runs/36815981471)
  also started automatically. It is not ordinary qualification and supplies no
  model or latency result. No extra diagnostic or microbenchmark was dispatched.

Next: inspect the six actual-engine source/closure receipts, then adapt context
and history boundaries to a deliberately chosen integrity domain. The new
resolver is not silently inserted into the old full-history consumers.

### Completed source-proof receipts and consumer follow-up

These receipts belong to runtime `479e61d67ec5e610e7ed15401e7b81d517403e4c`
in [ordinary run 36815981435](https://github.com/NIne-WIngEd/FloRA/actions/runs/36815981435).

- Core passed **34/34 cases**, suite **933.763 s**. All six new exact-source
  cases passed on actual XTDB/Kurrent: persisted locator and reopen, absent or
  changed coordinates/digest/time, independently false locator, physical
  deletion/reappend, current parent withdrawal, and parent withdrawal during
  the second physical pass. These are infrastructure checks using fictional
  sources and signed fictional-owner actions; case duration is not response
  latency.
- Contracts failed at a stale discovery assertion: it expected **43** cases
  after six were added, while actual discovery and scheduling included **49**.
  The preceding focused selection missed this inventory test. The repair checks
  every discovered identity exactly once, retains all six independently routed
  cases, and explicitly requires the six new physical cases in core. Its five
  contract cases pass locally. This does not retroactively qualify the failed
  contracts job.
- Transport still failed the **10,000 ms** budget: BEFORE **16,531 ms**, AFTER
  **20,932 ms**, both `budget_exceeded`. The other provider case passed; the
  two-case suite took **152.970 s**.
- Native comparison still failed: both responses timed out under the unchanged
  **60,000 ms** budget; suite **215.083 s**. No latency repair is established.
- Remaining completed receipts: readers **2/2**, suite **101.028 s**; lineage
  **2/2**, suite **2,042.644 s**; before/tail **1/1**, **1,685.316 s**;
  outcome/audit **1/1**, **2,199.097 s**; typed phase **1/1**, **3,271.409 s**;
  withdrawal **1/1**, **140.123 s**; retained route **1/1**, **2,285.229 s**;
  native route **1/1**, **2,235.117 s**. These are whole-case infrastructure
  timings, not paired-response or learned-behavior qualification.
- History coordinator passed in **52.064 s**. Preregistration registered its
  original inputs in **45.790 s**, then completed no first BEFORE capture before
  the unchanged one-hour job cap cancelled the job. No chronology, update or
  final seal is qualified.
- All ordinary results are accounted for: **46/49 physical cases passed**,
  **two failed their unchanged response budgets**, and **one did not complete
  before the unchanged job cap**. The separate contracts job failed the stale
  inventory assertion. Green source/lineage/pilot jobs do not erase those gaps.

Consumer integration now targets explicitly selected history and context
domains. Whole-stream readers remain the default. Held-history authentication
also captures domain/cap and exact target-reader bindings, so they cannot be
changed during later reuse. No response budget, job cap or scientific original
input is changed to qualify this work.

### Selected consumer build and final local verification

- Added explicit, capped `selected-history-metadata-v1` and
  `selected-current-context-v1` consumer domains. Defaults retain their
  whole-stream behavior. [Consumer contract](SELECTED_CONTEXT_AND_HISTORY.md).
- Selected history preserves the exact ordered original inputs and their
  parents, physical manifest and live evaluation rights. Joint history and
  external-disclosure checks finish on the same current metadata fence.
  Initial authenticated history still performs its actual custody checks.
- Selected context uses exact current Claims and governed state without
  episodes, retains the actual native phase gate, and protects private reads
  before and after access. Episode-bearing state and custom authority
  overrides reject this explicit domain before private I/O. Vector/graph
  nomination is not yet integrated into this slice.
- Independent review reproduced late-callback and held-content mutation
  windows. The selected terminal path now performs only pure binding and
  native-value comparisons after its final metadata observation; regression
  cases reject stale authority and mutated held content. This review did not
  establish a vulnerability in the previously published standalone closure.
- Final focused verification passed **246 tests across 16 modules**, with no
  failures or errors; summed test-suite duration **127.908 s**. Separate module
  processes avoid integration-discovery import collisions. This duration is
  not response latency, and controlled SDK/SQL fixtures are not actual-engine
  qualification.
- Integration discovery assigns **53 cases** exactly once to the original
  12 shards; core contains **38**. Four new history cases cover authenticated
  initial custody followed by metadata-only verification, terminal withdrawal,
  original-input phase exclusion, and the deliberate difference between
  selected-record and unrelated-tail integrity. Discovery is not execution.
- All **93 builder procedure traces** validate. The two new traces record
  consumer construction and terminal review in FloRA only. They are partial
  infrastructure procedures, not learned models or proven builder transfer.

Personality and MFM were not built, trained, downloaded or substituted. Alice
remains unchanged. Response limits, scientific inputs and original workflow
caps remain unchanged. Ordinary physical receipts for this consumer build are
still pending; **latency improvement remains unverified**.

### Consumer publication and physical gate

- Runtime publication:
  [`029a7655ca4aac16ba5c7644b7ca579a8ac45aac`](https://github.com/NIne-WIngEd/FloRA/commit/029a7655ca4aac16ba5c7644b7ca579a8ac45aac),
  tree `dd9211f8691bf84c28a296a0e07b167890015436`. All **28 changed paths**
  and their local blob hashes were verified against complete GitHub trees;
  other paths were preserved. The published tree equals the tested local tree.
- [Ordinary selected-engine run 36822267124](https://github.com/NIne-WIngEd/FloRA/actions/runs/36822267124)
  has started at that exact runtime commit. Contracts and all original 12
  integration shards retain their original limits. No running or queued job is
  counted as a pass.
- The existing [optional chronology diagnostic](https://github.com/NIne-WIngEd/FloRA/actions/runs/36822267094)
  started automatically. It is not ordinary qualification. No additional
  observer, diagnostic or microbenchmark was dispatched.

Next: read ordinary physical receipts for the selected consumers and their
unchanged response budgets. Selected-record correctness and response latency
remain separate gates; the earlier failed budgets remain part of the record.

### Consumer physical receipts and proof-composition foundation

These receipts belong to runtime `029a7655ca4aac16ba5c7644b7ca579a8ac45aac`
in [ordinary run 36822267124](https://github.com/NIne-WIngEd/FloRA/actions/runs/36822267124).

- Core passed **38/38 cases**, suite **916.972 s**, including all four new
  selected-history cases. Exact manifest reconstruction, original-ID phase
  exclusion, signed terminal withdrawal and the explicit unrelated-tail
  integrity boundary passed on actual XTDB/Kurrent. Restart and persistent
  Temporal probes also passed. These are infrastructure checks, not learned
  behavior or response latency.
- Readers passed **2/2**, suite **102.143 s**; withdrawal **1/1**,
  **139.795 s**; lineage **2/2**, **1,963.973 s**; before/tail **1/1**,
  **2,204.365 s**; outcome/audit **1/1**, **1,844.243 s**; native history
  routes **1/1**, **1,782.996 s**; typed phase **1/1**, **3,035.546 s**.
  Whole-case durations do not qualify a
  paired response budget.
- Standalone comparison still failed **10,000 ms**: BEFORE **12,621 ms**,
  AFTER **19,519 ms**, both `budget_exceeded`. The independent provider case
  passed; the two-case transport suite took **90.959 s**.
- Native comparison still failed **60,000 ms**: BEFORE **60,062 ms**,
  AFTER **60,125 ms**, both `timeout`; suite **198.379 s**. Differences from
  prior runs are not a controlled speedup or a passing budget.
- Contracts stopped at two errors in `test_native_comparison_fixture`.
  The actual integration binder used `self.assertEqual` inside a callback
  extracted without a unittest instance. The preceding focused suite omitted
  that module. Explicit domain/cap checks now preserve its requirements without
  depending on `self`; both actual-binder cases pass locally.
- The complete local contract selection then passed **866 tests in 74
  modules**, with no failures or errors; wall time **494.660 s**. Each module
  ran in its own process. This validates the fixture repair and broad regression
  coverage; the subsequent descriptor foundation needs its separate final
  focused checks and exact published CI receipt.

The existing automatic transport diagnostic was retrieved, not rerun. Artifact
`11143943320` matches archive SHA-256
`cede326213fa6a7cf2816b75abd23cae425ccf58aad647414c323f9c720c1590`.
All seven reported loaded-source hashes match the tested runtime tree.
The [preserved aggregate](evidence/2026-10-01_029a7655_transport_profile.json)
reports `qualification=false`: whole fixture **66.235585484 s**, **189**
combined history checks, **2,215** committed replays, **4,105** Kurrent reads,
**44,403** SQL executions, **12,888** current-action resolutions and **2,748**
permission predicates. These inclusive whole-fixture counts cannot be assigned
to one response or the native case.

The read-only causal audit found repeated proof construction inside nested
phase/source checks. It found no demonstrated new authorization defect in the
selected consumers. The [bounded authority-frame protocol](SELECTED_AUTHORITY_FRAME_PROTOCOL.md)
requires all held-history and selected-context rights to join the same final
fence. Its first implementation step is a privately issued native phase-binding
descriptor. Descriptor recognition skips no existing check; shared collectors
and frame integration remain separate work.

History coordinator passed in **98.935 s**. Preregistration registered its
original inputs in **89.276 s**, then completed no first BEFORE capture before
the unchanged one-hour job cap cancelled the job. Retained history routes also
completed no case receipt before the unchanged one-hour cap. Neither cancellation
qualifies chronology, retained-route recovery, an update or a final seal.

All ordinary results are now accounted for: **49/53 physical cases passed**,
**two failed their unchanged response budgets**, and **two did not complete
before their unchanged job caps**. The separate contracts job failed the two
actual-binder fixture errors described above. **No latency improvement,
complete demo, learned model win or builder transfer is qualified.**

### Selected-phase binding foundation: frozen local receipt

- Added a privately issued identity descriptor for the actual selected native
  phase installer. It binds original held inputs, phase/domain/cap, controller,
  actual readers and callback closures. Exact gate copies and supported
  selected transfers retain the original owner. Generic/custom gates receive
  no descriptor and keep their existing checks.
- Independent review reproduced effectful custom hashing, dictionary access
  and nested iteration during validation of tampered fields. Validation now
  rejects primitive or independently sealed own-field changes before accessing
  nested replacements. All four reproductions reject with **zero effects**;
  an unknown transfer target also rejects before its custom getter runs.
- Private issuance uses weak references and identity keys. Closed owned-session
  cycles are collectible. Descriptor fields, origin fields, reader bindings,
  callback code and held values cannot silently change the recognized phase.
- Final frozen-source verification passed **276 tests in 19 modules**, no
  failures or errors; wall time **51.396 s**. Recorded source hashes stayed
  unchanged during execution. The [controlled receipt](evidence/2026-10-01_selected_phase_foundation_local_contracts.json)
  includes the 18 descriptor cases and current context, history, native read,
  lineage, runtime, private-read, phase, fixture and inventory regressions.
  Independent descriptor review also passed all **18** cases.
- All **94 procedure traces** validate. The new
  [phase-binding procedure seed](fbm-seeds/2026-10-01_flora_selected_phase_authority.jsonl)
  remains a partial infrastructure method in FloRA only. It is not builder
  weights, an eligible supervised case, or demonstrated host transfer.

Every existing phase, ancestry, live grant, qualification and private-read
predicate still runs. This foundation introduces **no proof-sharing frame,
permission cache or check bypass** and makes no performance claim. Its exact
physical CI receipt is pending publication. Next implementation work is the
shared history/source collector and fresh protected-boundary frame described in
the protocol. That work does not require personality or MFM.
