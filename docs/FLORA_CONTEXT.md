# FloRA continuation context
## Latest completed gates and next diagnostic — October 3

Both `4b88946f` ordinary workflows have completed with failure. The
[full 26-job receipt](evidence/2026-10-03_4b88946f_completed_ci_receipts.json)
verifies all logged checkout trees and the Alice runtime pin. Each workflow's
component job passes **978 cases / 80 modules**. PR physical cases are **50 passed /
2 failed / 1 incomplete**; push is **49 / 2 / 2**, plus the separate restart-probe
exit 139. Completed cases in cancelled jobs count; unfinished cases do not.
Original response timings and failed/incomplete results remain unchanged.

The passed PR and failed push core jobs install the same package versions.
Temporal `1.33.0` upstream shutdown notes do not establish the segfault cause.
The crash remains unresolved; a later exact process probe needs a crash trace,
not a guessed SDK upgrade or blind rerun.

The [controlled unobserved cost check](evidence/2026-10-03_4b88946f_unobserved_proof_cost.json)
measures original-code operations without profile/trace hooks: median seal
0.214 ms, origin body 0.392 ms, plain pair 0.960 ms, inherited pair 1.184 ms.
Call counts are gathered separately, and no IO counters change. This local
fixture does not establish cloud cost or an end-to-end saving.

**Next: one optional original-code stack-sample diagnostic, with runtime unchanged.**
Sample fixed-tag owned-reader stacks every 50 ms, retaining numeric counts and
source hashes. There are no call hooks, delegate replacements, raw stack/locals
records or worker interruption. Thread windows remain bounded at 180 s; response
60,000 ms and CI 60 minutes stay unchanged. Short jobs may be missed; thread IDs
can be reused; GIL/native-call bias and stale snapshots remain. These are wall
residency samples, not CPU or call counts, and inclusive tag counts overlap.

The existing aggregate mode stays the default. Twelve new sampler checks and all
32 existing observer checks pass (44 total). Review caught and independently
reproduced false diagnostic success when a sampler failed; separate fixture and
observation statuses now preserve that boundary. Correction review is clear.
The [construction receipt](evidence/2026-10-03_native_stack_sampler_contracts.json)
binds the exact tested diagnostic files and unchanged runtime blobs. This diagnostic resolves whether further pure
proof representation work is justified or the next design should target physical
reads/reconstruction and H×C preparation. Origin-seal materialization remains
deferred; no new memory/mission platform or personality/MFM implementation is added.

The [FBM index](fbm-seeds/README.md) now links **118 validated procedure traces**.
The sampler's source-pinned publication/dispatch is the next step; its physical
result is unobserved. Older partial/pending snapshots below are superseded here.

Updated: 2026-10-03, America/Chicago. Recovery baseline:
`main@885be57abb582510d27a98177facd2a358c11387`; recovery starting runtime
`74f42417be37a2fbdc6c603a1ea657b040e0052e`.

## Latest continuation: published dependency repair and failed diagnostic

Runtime `4b88946f` is published. Its full local native receipt verifies 978 final
cases/80 modules, retaining the initial unchanged worker failure and warning-bearing
repeat. Eight tested/published source blobs match. Current push CI independently
reports 978 component cases/80 modules, all final statuses OK.

Once-dispatched native diagnostic 37109188927 is complete: **collection succeeds,
fixture fails, qualification false**. All 116 after/115 before source hashes match
exact FloRA/Alice pins. Its 121.672 s owned worker wall window remains concentrated
in preparation; origin seals cost 26.225 s exclusive CPU. The new shallow method
changes tag attribution, so fewer tagged calls do not prove a speedup.

Read [the October 3 checkpoint](VERIFICATION_CHECKPOINT_2026-10-03.md) first for
numeric artifacts, exact source validation and current partial CI. Ordinary PR
37109136216 and push 37109132198 still have running jobs in the saved snapshot.
Both retain standalone budget failures and native timeouts. Push core reports
38 tests OK, then its Temporal restart verification process segfaults with exit
139; do not replace this failed process gate with the preceding success summary.
Recover complete ordinary results before another measured runtime candidate.

The dependency repair preserves fresh code/closure/global and owned reader checks,
recursive phase verification, origin/descriptor seals, callbacks and all fences.
Origin-seal representation remains deferred. FloRA remains the narrow causal
prototype aligned with Alice's needed logical contracts. Personality/MFM are
external integrations; no full memory or mission platform is being added here.

[FBM's visible update index](fbm-seeds/README.md) now links 116 validated public
procedure traces, including this failed result. Trace shape is separate from
training eligibility; no FBM training, response or learned result is claimed.
The context branch is documentation authority, not current runtime source.
Older pending and candidate notices below are historical snapshots superseded here.

## Completed refined observation: independent seal traversal is costly

[Four-tag diagnostic 37073820659](https://github.com/NIne-WIngEd/FloRA/actions/runs/37073820659)
finished collection at 22:45:56 UTC. The fixture **failed**, qualification is
false, and the original 60,000 ms response budget remains. The
[original numeric artifact](evidence/2026-10-02_d0f90655_native_profile.json)
is byte-identical; [validation](evidence/2026-10-02_d0f90655_native_profile_validation.json)
matches all 116 after-source files (60 FloRA `d0f90655`, 56 Alice `4f287a`)
and all 115 before files. Job logs confirm both checkouts and workers-only mode.

Six owned jobs used one ledger, 121.014 s wall / 106.410 s thread CPU. Two
preparation calls total 119.080 s inclusive wall / 105.249 s CPU. No worker
window capped, no observer error/overflow/hook change occurred, and no active
or open span remained at close. Parent setup remains unobserved. Added tags
change sampling overhead; this is attribution within the new observation,
not a speedup comparison to earlier scopes.

| Original-code tag | Calls | Exclusive CPU seconds | Inclusive CPU seconds |
| --- | ---: | ---: | ---: |
| phase.descriptor_tree_verify | 3,469 | 2.424 | 35.861 |
| phase.descriptor_contracts | 20,451 | 2.341 | 2.341 |
| phase.origin_seal_verify | 10,063 | 21.670 | 21.670 |
| shared.frame.contracts | 9,908 | 1.507 | 2.649 |
| shared.frame.context_binding_verify | 245,532 | 13.555 | 30.056 |

The new tags distinguish **origin seal traversal** from the cheaper module
contract scans. `_verify_origin_seal` independently checks each registered
origin's identity, reader identities and recursively captured function-binding
seals for every descriptor/parent. The earlier origin-body de-duplication
deliberately retained all those seals. This evidence does not justify skipping
them or caching a successful authority answer. Context binding verification
also remains material. Inclusive tree/binding totals contain nested work and
must not be added to their child totals.

The next design question is how to represent exact immutable origin dependency
bindings once while still checking every descriptor's private issuance and
independent seal relation, then rechecking after callbacks and at each new
protected boundary. Establish that representation and mutation/replacement
tests before changing runtime. Keep current physical reobservation, independent
controllers and terminal fences. Ordinary CI for `da370ebc`/`d0f90655` is still
the separate gate; no further runtime change is made at this checkpoint.

## Current continuation: bounded contract-cost observation

Observation source `d0f906550ca36a35903702a205d263a8b1b21061`, tree
`a24132ef82b59f972ca5398e4ab0928079d147a6`, adds exactly four fixed original
code tags: `phase.descriptor_tree_verify`, `phase.descriptor_contracts`,
`phase.origin_seal_verify`, and `shared.frame.contracts`. Runtime and its four
candidate source/test hashes stay identical to `da370ebc`. Every old tag,
worker/default-mode semantic, numeric-only privacy rule and budget remains.
No native function is wrapped or replaced.

All **32 observer contracts passed in 3.493 s** on native Linux/ARM64, including
the existing 31 and a controlled-thread regression that excludes an equal
copied code object while counting the original target once. The
[source-pinned receipt](evidence/2026-10-02_d0f90655_observer_contracts.json)
separates these observer tests from the 72 passed runtime contracts and the
failed `da370ebc` engine fixture. Added sampling changes observation overhead;
compare reached stages and attribution, not equal-overhead speedups.

The existing push filter launched
[diagnostic 37073820659](https://github.com/NIne-WIngEd/FloRA/actions/runs/37073820659)
once. [PR CI 37073825647](https://github.com/NIne-WIngEd/FloRA/actions/runs/37073825647)
and push CI 37073820636 are also pending. Recover their exact checkouts and
artifacts next; no current response pass is claimed. When only runs remain,
stop the turn and resume when the owner returns.

## Completed candidate observation — no response qualification

[Native diagnostic 37072026458](https://github.com/NIne-WIngEd/FloRA/actions/runs/37072026458)
completed collection at 22:25:33 UTC, but the exact fixture **failed** and
qualification remains false. The [original artifact](evidence/2026-10-02_da370ebc_native_profile.json)
is retained byte-for-byte. [Validation](evidence/2026-10-02_da370ebc_native_profile_validation.json)
matches all 116 after-source hashes (60 FloRA `da370ebc`, 56 Alice `4f287a`),
all 115 before hashes, and the sole newly loaded authenticated-history module.
Job logs confirm both checkouts and `--workers-only --cap-seconds 180`.
File hashes and separately bound original code identities remain distinct.

Both observations have six owned jobs on one ledger. Neither reached the
180 s worker cutoff, changed hooks, overflowed, recorded observer errors or
left active/open spans at close. Parent setup and CPU remain unobserved.

| Observed quantity | bf597366 | da370ebc |
| --- | ---: | ---: |
| Worker wall seconds | 121.382 | 120.902 |
| Worker thread CPU seconds | 110.109 | 109.280 |
| Two preparation calls, inclusive wall seconds | 118.229 | 119.398 |
| Two preparation calls, inclusive CPU seconds | 108.083 | 108.309 |
| Frames created | 8 | 17 |
| Kurrent reads / SQL executes | 870 / 9,180 | 2,261 / 23,836 |
| Origin-body calls / exclusive CPU seconds | 5,436 / 21.012 | 4,201 / 8.045 |

More frame/RPC progress occurred before unchanged deadlines, so these are
different work mixes, not equal-work speedup measurements. Whole elapsed fell
from 247.910 s to 182.645 s while first owned entry moved from 126.165 s to
61.569 s; unobserved setup prevents attributing that difference to the candidate.
Public descriptor calls fell from 5,434 to 292, but private pair/tree traversal
moved their remaining cost into `base_bindings`, whose exclusive CPU was
29.698 s. Context binding checks ran 297,586 times at 14.207 s exclusive CPU.
These are overlapping stages' exclusive measurements, not connection counts.

The [read-only review](evidence/2026-10-02_da370ebc_native_profile_review.json)
localizes the remaining reached stage to context preparation/assembly and
current-authority frame work. Native authorization and lineage tags remain
zero; downstream generation was not measured. Four additional fixed original
code tags are the bounded next observation: descriptor tree, descriptor
contract scan, origin seal and frame contract scan. They add observation
overhead and must not be treated as identical old measurement coverage. No
further runtime rewrite is supported yet. Ordinary CI for `da370ebc` remains
the independent response/correctness gate under unchanged clocks.

## Published measured-origin candidate

Runtime `da370ebc9b089aec430859059cc83af52e623089`, tree
`5a904dbd310814bf5dbeeaac8832dc4fc53d573c`, applies the smallest measured
dependency change in [draft PR #1](https://github.com/NIne-WIngEd/FloRA/pull/1).
Runtime code lives on `codex/flora-shared-source-caps`; `codex/flora-context`
is the documentation handoff and retains older runtime files.
One fresh descriptor-tree pass verifies each exact native origin body once.
Every root and inherited parent still checks its own private issuance, class,
token, descriptor/gate/reader/origin seals and installed gate owner. The local
identity map holds exact objects and ends before returning to frame callbacks;
later checks start fresh. This is pure dependency work, with no saved permission
answer, source-head result or cross-boundary proof.

The [source-pinned component receipt](evidence/2026-10-02_da370ebc_origin_contracts.json)
records **52 focused passes** on native Linux/ARM64: phase 25 in 3.573 s, H 19
in 2.656 s and consumer/frame 8 in 64.170 s. The first consumer run had seven
passes and one test-placement failure: the prepared wrapper rejected changed
scope before the intended origin assertion. The corrected test mutates scope
inside the real frame callback and requires origin-specific rejection. Runtime
bytes stayed unchanged. The separate original frame suite then passed **20/20
in 823.111 s** (827.967 s process) at 22:32:20 UTC, with runtime/test hashes
unchanged. Total current targeted coverage is **72 passes**. These component
timings do not establish response latency or a controlled speedup over old runs.

[Ordinary PR CI 37072008699](https://github.com/NIne-WIngEd/FloRA/actions/runs/37072008699),
push CI 37072002344 and the once-dispatched
[engine diagnostic 37072026458](https://github.com/NIne-WIngEd/FloRA/actions/runs/37072026458)
were pending at publication. The completed diagnostic is recorded above;
ordinary CI remains pending. Component passes do not inherit older physical
results or establish response improvement. The original 10,000 ms standalone,
60,000 ms native and 60-minute CI limits remain. No learned model is run.

The observer is unchanged: private pair traversal now appears within
`shared.frame.base_bindings` instead of calling the public
`phase.descriptor_verify` entry. A drop in that entry's count or CPU alone cannot
show removed cost. Compare whole observed worker/preparation CPU and wall,
original origin-body counts, reached stages and overlapping fixed-tag spans.
Retain setup coverage limits and observation overhead.

The necessary Alice-aligned loop remains source Experience → external proposal
→ deterministic Claim admission → governed current state → exact context →
native judgment/decision → linked outcome → externally proposed successor →
separate activation. [The middle-layer audit](ALICE_MIDDLE_LAYER_DESIGN_AUDIT_2026-10-02.md)
binds that loop to Alice's architecture and revised comic. The remaining full-H
reconstruction, H×C evaluation and lineage/context reconstruction are measured
follow-up candidates, not permission to add a full mission platform or skip
authority. Personality and MFM remain external integration inputs.

## Completed worker-repair CI at 9b57ed3

Both earlier ordinary runs completed with failure at 22:15 UTC:
[PR 37065697026](https://github.com/NIne-WIngEd/FloRA/actions/runs/37065697026)
and push 37065691025. Each passed **947 component tests in 78 modules**.
Physical results are **49 passed, two failed and two incomplete of 53**,
including one explicit history coordinator pass before cancellation. History
preregistration and retained history remain incomplete. PR merge `6eb543a6`
has the exact published `9b57ed3` tree `9541734d`; Alice is pinned at `4f287a`.

Standalone BEFORE/AFTER were **14,707 / 21,102 ms** in PR CI and
**23,956 / 38,911 ms** in push CI, all above 10,000 ms. Native attempts were
**60,071 / 60,132 ms** and **60,108 / 60,134 ms** respectively, all timeout
under 60,000 ms. The [completed exact-source receipts](evidence/2026-10-02_9b57ed3_completed_ci_receipts.json)
retain per-job summaries and cancellation progress. Component correctness
does not qualify those responses; these outcomes apply to 9b57ed3, not the
current candidate. Pending references to these runs below are historical.

## Measured owned work at bf597366

[Native diagnostic 37068588428](https://github.com/NIne-WIngEd/FloRA/actions/runs/37068588428)
completed at 21:49:45UTC. Its [artifact](evidence/2026-10-02_bf597366_native_profile.json)
records a failed fixture and qualification=false. The corrected scope reached
six original owned jobs on one worker ledger:121.382s wall/110.109s thread CPU,
with first entry126.165s after observation started and 247.910s total elapsed.
Parent/setup timing is unobserved; no worker window capped and no hook change,
overflow, observer error or open span remained at close. Return events include
exception unwind and never certify authority success.

The [source validation](evidence/2026-10-02_bf597366_native_profile_validation.json)
matches all 116 loaded after-source file hashes to pinned Git blobs:60 FloRA
atbf597366 and 56 Alice at 4f287a. All115 before-source hashes are unchanged;
newly loaded authenticated_history also matches. These are file hashes, not
compiled-code attestation; fixed targets separately bind original code identities.
The job logs confirm both exact checkouts and the explicit workers-only command.

| Original-code tag | Calls | Exclusive thread CPU | Inclusive thread CPU |
| --- | ---: | ---: | ---: |
| phase.descriptor_verify |5,434|23.257s|64.947s|
| phase.origin_verify |5,436|21.012s|22.940s|
| phase.function_binding_verify |93,790|5.359s|12.149s|
| shared.frame.context_binding_verify |132,111|12.831s|27.865s|
| shared.frame.base_bindings |2,948|4.962s|64.809s|
| context.prepare_current |2|0.268s|108.083s|

The first four exclusive tagged totals sum62.459s, about56.7% of this observed
worker CPU window. They include untargeted work within those spans and observer
overhead. Inclusive spans overlap and must not be added. This localizes pure
verification work; it does not predict an equivalent response speedup.
Kurrent recorded 870reads, SQL 9,180executes; these are not connection-open counts.
Preparation alone accounts for118.229s inclusive wall across two calls. Later
authorization/lineage stages were not reached in this fixture, which uses
controlled recovered producer receipts rather than learned inference.

This supports testing the audit's narrow exact-origin de-duplication within
one pure descriptor traversal. Every descriptor seal remains independent;
tracking ends before callbacks and later checks start fresh. Removing repeated
origin bodies cannot remove all descriptor, seal, binding, H/C or context work.
No serving improvement,60-second pass or learned result is claimed. The original
standalone10,000ms/native60,000ms response and 60-minute CI limits still govern.
The measured candidate is now published and source-pinned in the latest section
above. Its engine and ordinary CI results remain pending.

## Preserved recovery and observation checkpoint

The repaired frame's ordinary [run 37054784829](https://github.com/NIne-WIngEd/FloRA/actions/runs/37054784829)
completed with failure at 20:32:57 UTC. Runtime `ef9c190e` and merge checkout
`2f166a9d` share exact tree `1f9b9558`; all 944 component tests in 78 modules
passed, including H 19, frame 20 and the original worker 11. Physical results
are **49 passed, two failed and two incomplete out of 53**. Standalone
BEFORE/AFTER attempts were 25,743 / 40,144 ms against 10,000 ms; native attempts
were 60,061 / 60,108 ms against 60,000 ms. History preregistration and retained
history did not finish. The [completed receipt](evidence/2026-10-02_ef9c190e_completed_ci_receipts.json)
supersedes pending observations below; earlier failures remain historical evidence.

The separate local worker failures were reproduced. A child exiting before
input dispatch could raise `ConnectionResetError` while awaiting stdin closure,
hiding its exit status; cancellation could cancel the protocol-owned close
future. Runtime `9b57ed3ce0d634409c967983bd5878ff74b48d3b`, tree
`9541734db403ed1931c974a7e2a1bdab0e2b9c1e`, applies Python's subprocess
stdin handling and adds process regressions. Its unchanged-source local rerun
passed 13/13 worker tests in 1.972 s; fixed-tag profiler contracts passed 21/21
in 6.388 s on native ARM64. The first worker run's deadline-fixture error and
remaining transport warnings are preserved in the [component receipt](evidence/2026-10-02_9b57ed3_worker_profile_contracts.json).
This resolves the confirmed input race; it does not establish cleanup or latency
qualification. The new [ordinary PR run](https://github.com/NIne-WIngEd/FloRA/actions/runs/37065697026)
remains pending at this checkpoint and inherits none of the older CI results.

The [actual-engine diagnostic 37065691146](https://github.com/NIne-WIngEd/FloRA/actions/runs/37065691146)
completed its workflow, but its [artifact](evidence/2026-10-02_9b57ed3_native_profile_setup_cap.json)
is **capped, qualification false**: 180.013 s, zero owned-work entries and zero
worker ledgers. Parent setup recorded 2,673 Kurrent reads and 35,577 SQL executes;
those are statements/RPCs, not connection-open counts. Non-RPC setup was
unobserved. It never reached the fresh-frame native path, so no frame-cost or
response attribution is justified. An all-call local diagnostic was also
stopped incomplete without usable stage timings; its interruption stack is
not quantitative evidence.

The owner's clarification means comparable systems and their open implementations,
not a request to name a benchmark provider. [Pinned primary research](LATENCY_RESEARCH_2026-10-02.md)
covers Graphify, Graphiti, Mem0, Letta, SpiceDB and Alice's research branches.
The useful hypothesis is reuse of exact immutable dependency work inside one
fresh boundary. First measure the remaining duplicated work; keep independent
authority callbacks, physical reobservation and the terminal joint row fence.
No cached positive authority or full memory/mission platform is proposed.

The observation update is published at `bf59736673d4f054ff85636ca80a1983d14d7cd5`,
tree `58510702886b9915c84305e070fec9fe24a5b8fd`. All 31 controlled profiler
contracts passed in 4.990 s on native ARM64; the original 21 and default cap
semantics remain. The [source-pinned receipt](evidence/2026-10-02_bf597366_owned_observer_contracts.json)
records the separate worker windows and review. The workflow explicitly uses
`--workers-only`: parent setup stays unprofiled, each worker gets one bounded
180-second observation window from its first original owned entry, and cutoff
never cancels the worker or fabricates a CPU sample. Response and CI clocks
are unchanged. Four original-code tags expose descriptor/origin/function-binding
work. [Actual-engine diagnostic 37068588428](https://github.com/NIne-WIngEd/FloRA/actions/runs/37068588428)
and [ordinary PR CI 37068593649](https://github.com/NIne-WIngEd/FloRA/actions/runs/37068593649)
are pending; no observed speedup or new full gate is claimed.

The owner's latest reminder also makes middle-layer design alignment explicit.
The [source audit](ALICE_MIDDLE_LAYER_DESIGN_AUDIT_2026-10-02.md) compares the
implemented experience/Claim/state/judgment/outcome links with Alice's original
docs and revised comic. Current roles are connected and aligned; a full mission
subsystem is absent and not required by this case. Concrete repeated history
authentication, H-per-C evaluation and native-origin verifier traversal remain.
Their response cost still needs measurement. The smallest proposed next change
is call-local de-duplication of the same native origin during one pure descriptor
validation pass, retaining every descriptor seal and fresh live boundary. This
is a conditional implementation proposal, not an implemented Alice mechanism
or cached authorization. Personality and MFM remain external.

Kaggle and Magnolia remain preferred for eligible compute; Hugging Face and
local PC Docker are also available. Paid GPU hours remain the last fallback.
Docker has been used for native CPU contracts; no GPU or model work was launched.
Personality and MFM are built in the other chats and will be plugged in here.
When only a run is pending and no independent work remains, end the turn and
resume when the owner returns; do not spend tokens polling unchanged jobs.

## Preserved frame publication and earlier observations

The context recovery began on `codex/flora-context` at
`d584f29e622b875220d408240a21a7d8bf661ebd`. The fresh shared authority frame
is now published on `codex/flora-shared-source-caps` at
`ef9c190e0688c2bb06dce5b12bbef06e6bd4f13f`, tree
`1f9b955849cbc69ed1f0244366876bbe672fd0c6`, in
[draft PR #1](https://github.com/NIne-WIngEd/FloRA/pull/1).
Historical frame identity above is `ef9c190e`; worker repair is at `9b57ed3`;
the four-tag observer extension is published at `d0f90655`. Current runtime
code is `da370ebc`
as recorded in the latest section. The context branch records that work;
code remains on the development branch
until reviewed. Do not infer its implementation from the context branch's
runtime files. Frame SHA-256 at the historical ef9c190e checkpoint is
`73302f5edb934dc536c16ac7554a084ff85f604d8e6ad2f4eae3e0def7c2a197`;
frame-test SHA-256 is
`6adaae62780b1fabda5e9e39c041d8849797206f4433822c807de57683300552`.
The other four source/test hashes are unchanged from the checkpoint's preserved
failed revision. All six were independently checked at this publication.

The final-source withdrawal pair passed **2/2 in 73.007 s** on native
Linux/ARM64. The new opaque-guard code-swap test passed **1/1 in 10.439 s**.
The repair binds independent function identity and code while allowing
legitimate closure-counter state; actual guard calls remain required. These
targeted results are partial. The complete 20-case frame suite and 76 existing
module suites began on native ARM64 at **19:32:58 UTC**, using the same image
and pinned dependencies. Its completed frame result is linked above. The existing runner
halted at **19:37:32 UTC** after **35/76 modules**, with **476 passes, one
failure and one error across 478 cases**; 41 modules were not run. The
unchanged worker module's two `worker_rejected` issues and asyncio/transport
warnings need investigation. Their cause is unresolved; neither an
environment-only cause nor a frame regression is established.

Ordinary [run 37054784829](https://github.com/NIne-WIngEd/FloRA/actions/runs/37054784829)
uses merge `2f166a9d745667b200302a404bd04f8def7a83d9`, whose tree exactly
matches `ef9c190e`. At 19:38:11 UTC, readers 2/2 and withdrawal 1/1 passed,
but native responses 60,061 / 60,108 ms failed the unchanged 60,000 ms budget.
Transport, contracts and other jobs remained pending. The
[current checkpoint](VERIFICATION_CHECKPOINT_2026-10-02.md) and
[partial CI receipt](evidence/2026-10-02_ef9c190e_partial_ci_receipts.json)
preserve these incomplete outcomes without a full qualification claim.

Earlier ordinary
[run 37049792243](https://github.com/NIne-WIngEd/FloRA/actions/runs/37049792243)
belongs to `36f39b36`. Its [verified partial receipt](evidence/2026-10-02_36f39b36_partial_ci_receipts.json)
binds merge `268091dade9856c95f37d0ecdf416f6c4fe690bb` to the same runtime tree.
At 19:26:37 UTC, 48 completed physical cases passed, two response cases failed
and three cases remained pending. Native responses were 60,087 / 60,155 ms
against 60,000 ms. This earlier source does not verify `ef9c190e` or establish
complete physical or response qualification.

At `36f39b36`, the exact-source native frame suite failed two of 19 cases in
930.594 s. Binding capture froze legitimate mutable counter state inside an
opaque independent phase guard, preventing its required second call in the
selected C and unselected H withdrawal cases. Retain the
[failed receipt](evidence/2026-10-02_36f39b36_frame_contract_failure.json) and
unchanged assertions. The earlier local capture repair passed the pair in
68.205 s at source fingerprint `82c784b`, before the final independent
function-code pins. That progress belongs to the earlier source; the final
73.007 s pair result and separate code-swap test above are still subsets.

The prior collector-only runtime `3a6e03cf` completed ordinary
[Linux/physical run 37041602495](https://github.com/NIne-WIngEd/FloRA/actions/runs/37041602495)
with failure: 905 component cases passed; 50/53 physical cases passed, two
response budgets failed and one history-preregistration case was incomplete.
The [completed receipt](evidence/2026-10-02_3a6e03cf_completed_ci_receipts.json)
preserves exact source identity and clocks. It does not verify the later frame.

## Owner's current scope

The owner's latest latency instruction is to make further changes from a
measured explanation. Repeated authority construction is documented, but its
share of the remaining timeout still needs measurement. Use existing profiles,
the Flora/Alice research branches, relevant plugins and Graphify navigation
where useful. Consult relevant frontier research, the actual competing model
or system, and their primary papers or open-source implementations. Record
source identity, applicable mechanism and a falsifiable expected effect before
changing the serving path. Do not adopt an unrelated stack or relax authority
and experimental gates on the strength of an analogy. Graphify remains a
development aid; original source pointers govern. The primary research is now recorded in LATENCY_RESEARCH_2026-10-02.md;
no competitor speedup is attributed to FloRA.

The October 2 continuation instruction is authoritative: FloRA is a prototype
to test one Alice/Fable claim. It does **not** need the complete Alice memory,
experience or mission infrastructure. Whatever it needs must remain aligned
with Alice; that does not authorize building everything in Alice. A convenient
replacement database is not evidence for the selected physical engine.

This supersedes interpreting the older four infrastructure lanes as mandatory
completion targets. Keep completed useful components and their regression
coverage; add a new surface only when a selected experiment case requires it.
Full mission execution, federation, scale-out graph, background lifecycle
daemons, all memory planes, complete product key management and full-system
unlearning are not prototype prerequisites. Neither the full Fable release
gate nor its all-at-once product scope transfers to FloRA.

The owner's latest October 2 compute preference is to use available Kaggle
and Magnolia for later eligible external-artifact or integration workloads.
Paid GPU hours are the last fallback if those options fail. Current CPU
contract validation needs no GPU, and no GPU work is being launched now.
Personality and MFM stay in their other chats. Do not infer provider details,
quotas or new infrastructure from these names.

## What the experiment asks

The [frozen goal](EXPERIMENT_GOAL.md) asks whether a relevant correction or
observed outcome changes later **native personal judgment for the right reason**,
while irrelevant changes leave it stable, and whether it beats a competent
general model with memory. A same-selected-evidence ablation separates evidence
selection gains from learned judgment gains. Builder transfer follows a
qualified first slice; it is not a reason to construct the full product now.

Freeze final histories, held-out decisions, equal-evidence comparator, clocks,
thresholds and scoring before evaluation. Synthetic wiring and fictional
producer receipts are not learned results or real-host benefit. Numerical
thresholds and the final cohort are still pending. Personality and MFM remain
external workstreams with qualified artifact/invocation receipts required.
The owner's follow-up explicitly confirms they are built in other chats:
FloRA builds their integration interfaces and plugs them in when ready; it
does not implement, train or fine-tune personality or MFM here.

The smallest current native case uses exact Claim evidence and one governed
owner-state route, with before/after originals. Its essential path is encrypted
originals -> scoped Kurrent Experience -> XTDB accepted/current Claim and state
-> bounded delivered context -> external native judgment -> attributed response
and decision -> correction/outcome -> governed relevant revision. Preserve
proposal/adjudication separation, exact provenance, current authority, phase
exclusion and causal output lineage. Use extra retrieval planes only when the
chosen cases need them. A strong comparator may need its existing hybrid memory;
do not weaken it to manufacture an advantage.

## How Alice connects the whole entity

The detailed source map is [ALICE_INFRASTRUCTURE_MAP.md](ALICE_INFRASTRUCTURE_MAP.md).
Current architectural authority is Alice
`main@8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b`, especially the September 27
replacement execution map, identity/formation and personal-development docs,
record/provenance and performance standards, and Stage G qualification matrix.
Fable's storyboard is pinned at
`1805a01c73575378246cac8cbbb72cd891e8528e`.

Experience preserves observations, decisions, reasons, actions, corrections
and outcomes; encrypted originals preserve exact source content. MFM proposes
meaning with evidence references. The deterministic Gate adjudicates. Claim
Authority preserves accepted versions and materialized current state. Episodes,
graphs, vectors, host/relationship/assistant-self and procedural/mission views
share those identities and provenance. They do not become separate truth stores.
Selected recollection delivers usable, sufficient evidence to native judgment.
The controlled response/action and its actual outcome return to Experience and
governed development. Distinguish source-person identity from host, relationship
and assistant-self; a host correction cannot rewrite source-person history.

Missions persist independently of chats. Their stable nodes, typed dependencies,
Result Capsules and ordered Traceback Chains bind results/evidence to continuing
work; outcomes also feed Experience. This explains the full entity, and does not
require a mission subsystem for FloRA's current correction/outcome experiment.

Alice permits zero, one or many retrieval planes, materialized current reads,
fast capture and slower asynchronous formation/consolidation. A connected entity
does not synchronously run every subsystem on each turn. Current FloRA's
`ContextPlan.validate()` still requires a nonempty route; zero-memory serving is
an architecture capability, not an already implemented FloRA capability.

Selected full-product engines are Kurrent Experience, XTDB v2 Claims, NATS
JetStream transport, Qdrant, local LadybugDB/scale-out NebulaGraph, encrypted
content-addressed objects, Temporal and process-local/Valkey caches. Selectively
using these does not create a mandatory per-turn sequence. PostgreSQL in the
compose file stores Temporal service history; XTDB uses a PostgreSQL wire
protocol. Neither makes PostgreSQL FloRA's Claim Authority.

Known source conflicts: Fable's execution profile retains NATS-as-canonical-log
and JanusGraph scale-out; older FBM program text retains PostgreSQL/Neo4j.
Alice's later selected execution map governs Kurrent/NATS/NebulaGraph roles.
Record those sync gaps rather than blend old and new stacks. The runtime's
product-neutral interface pin is separately
`research/mfm-foundation-20260923@4f287a488bc908bd04f99255ee01b794bacba50b`
(formation schema 1.2.0); architectural main is not an automatic API upgrade.
Graphify is optional development navigation with source pointers, outside
runtime authority. Its inferred links are not accepted personal facts.

## What happened before this chat

The old Phase 2 implementation was removed from main; historical tests do not
qualify the current experiment. The repo then built a broad inventory of
selected-stack source, permission, state, episode, retrieval, recovery, model
custody, comparison, assessment and preregistration modules. That inventory is
broader than the minimum prototype, but there is no implemented full mission,
Valkey or NebulaGraph subsystem in Flora's source tree.

The [October 1 recalibration](LATENCY_ARCHITECTURE_RECALIBRATION_2026-10-01.md)
changed direction from codec/loop tuning to bounded selected evidence and
authority composition. The failing native case was one Claim plus one state,
not a full companion conversation or an all-engine query. Nested `permits` and
`allow_event` checks repeatedly invoke `phase_now`, which reconstructs held
history H. Whole-stream fences replay twice; internal custody events enlarge
the stream. Selected paths still repeat source closure, hydration and overlapping
metadata proofs. The direct measured cause is repeated proof construction;
full mission infrastructure was not measured as its cause.

Published progression:

1. `479e61d`: persisted exact source locator lookup and bounded parent closure.
2. `029a765`: explicit selected history/context consumers; whole-stream defaults
   remain and domains never silently fall back.
3. `74f4241`: native phase-origin descriptor foundation and actual-binder fixture
   repair. The descriptor recognizes issued bindings; all predicates still run.
4. `885be57`: publication documentation only. Shared authority frame pending.

Kurrent exact lookup already reads one physical record (`limit=1`, links off),
checking scope, stream, position, full digest, server UUID and original commit
time. XTDB source registration already holds those coordinates. No new storage
is needed. There is no qualified multipoint lookup or stream-incarnation token;
exact reads do not certify unrelated whole-stream integrity.

## Recovered continuation and its limits

The previous Flora chat is the durable task
`01a0d562-f68f-75d0-ac23-425b684ba036`. Its final message describes
`FloRA_Complete_Continuation_Handoff_2026-10-02.md` and states no new code
publication. The complete Library artifact is not readable through the current
available tools; do not claim it was fully read. Its smaller design-review chat
`01a0f98c-9e6d-7071-9cff-d2d7cbd790ff` was recovered, and repo code/history plus
completed CI were independently inspected. Unknown scratch work is not adopted.

Recovered review constraints governing the shared frame:

- H means **all held original history**, including its physical manifest for
  custody, with evaluation rights for every original. C means nominated context
  evidence and parents, with personal-judgment rights. Purposes remain distinct.
- H and C keep separate closure caps; parents count. The existing helper
  `verify_selected_history_metadata(source_purposes=C)` places their union under
  H's cap and cannot be reused wholesale (the native fixture uses H=32, C=128).
  Per-event phase ancestry also retains its specified cap.
- Extract data contributors that provide sampled rows, exact physical material
  and dependencies, **not** authorization success or an early terminal proof.
- The first frame must protect initial private assembly via `initial_barrier()`
  as well as later `metadata_current()`/ciphertext/plaintext boundaries.
- Compose only privately issued runtime `permits` and selected `allow_event`
  descriptors with identical current origin. Keep sample permissions attached
  to the actual gated runtime policy; do not silently replace it with origin
  permissions or discard independent guards.
- Preserve actual source predicates, owner proofs, qualification, final-seal
  authority and custom-reader semantics. Reobserve exact physical commitments
  after callbacks, then finish one joint XTDB observation for H+C+Claim/state
  dependencies. Only pinned pure comparisons may follow. Discard each frame.

See [SELECTED_AUTHORITY_FRAME_PROTOCOL.md](SELECTED_AUTHORITY_FRAME_PROTOCOL.md).
This optimization is confined to existing prototype checks, not a new full
Alice memory platform or a reusable permission lease.

## Preserved collector and baseline physical status

The completed collector-only ordinary
[run 37041602495](https://github.com/NIne-WIngEd/FloRA/actions/runs/37041602495)
belongs to collector-only runtime `3a6e03cf` and completed with failure.
Its 905 component tests passed in 76 modules. Physical results were 50 passed,
two failed response cases and one incomplete history-preregistration case.
Standalone BEFORE/AFTER took 24,377 / 39,477 ms against 10,000 ms; native
BEFORE/AFTER timed out at 60,074 / 60,141 ms against 60,000 ms. Retained
history completed, but preregistration hit the unchanged one-hour cap.
The completed receipt supersedes its partial CI observations.

The earlier baseline
[run 36828262948](https://github.com/NIne-WIngEd/FloRA/actions/runs/36828262948)
at runtime `74f42417` has **completed with failure**; the earlier checkpoint's
pending status was stale when this chat started. It passed 884 component cases
in 75 modules and 49/53 physical cases. Standalone BEFORE/AFTER took 17,471 /
28,082 ms against 10,000 ms. Native BEFORE/AFTER timed out at 60,072 / 60,142 ms
against 60,000 ms. History preregistration and retained history routes hit the
unchanged one-hour caps; completion is unqualified. Successful physical cases
and fixture timings do not erase failed budgets. Compact exact job receipts are
in [the October 2 checkpoint](VERIFICATION_CHECKPOINT_2026-10-02.md).

No response-latency pass, native learned advantage, complete demo, real-host
benefit, trained FBM or automatic host transfer is established.

## Work next and scope check

The finite shared source-row collector accepts independently
capped domains, sharing sampled rows while retaining each complete parent-DAG
limit. [SHARED_SOURCE_METADATA_CAPS.md](SHARED_SOURCE_METADATA_CAPS.md) records
the API and custom-reader repair. Its earlier 90 targeted contracts passed
locally; the collector-only ordinary run later passed 905 component cases.
The collector returns metadata inventory, not authority or a terminal proof.
The new runtime connects it to a fresh H/C/Claim/state frame. No new engine,
ledger or product plane was introduced.

This helper's source cap counts nominated source DAGs. Raw-only object extras
consume the combined row budget without inventing grants. The new data-only H
contributor separately includes the physical manifest in H's own cap and
verifies custody; the helper alone does not establish that history contract.

The [frame protocol](SELECTED_AUTHORITY_FRAME_PROTOCOL.md) now has a serving
implementation: separate frames protect initial nomination, every initial
assembly barrier, prepared metadata checks and post-assembly capture. Actual
gated policy ownership, independent authority callbacks, source predicates,
signed owner proofs and four fresh private byte boundaries remain governing.
Callbacks precede manifest/physical rereads and one joint H/C/Claim/state XTDB
terminal observation; only sealed native comparisons follow.

Original `assemble_context` services, opaque independent guards and some
immutable-row sampling still repeat work. These are explicit remaining costs.
The failed 36f39b36 frame selection and repaired ef9c190e result are
preserved in the checkpoint. Its completed ordinary CI covers all 78 component
modules but fails response budgets and leaves two physical cases incomplete.
The two local worker failures were separately reproduced and repaired; residual
warnings remain. Current observation mechanics pass 31 cases, while their actual
engine result and current ordinary gate remain pending.

The d0f90655 four-tag aggregate is recovered and source-verified above.
Next recover completed ordinary CI for the exact candidate and observer sources.
Then review typed current origin-seal materialization with every descriptor's
independent expected seal still compared, and shallow binding-node checks with
one explicit nested/closure-reader traversal. The middle-layer audit records
both conditional proposals and their mutation tests. Every private issuance,
owned seal, code/closure/global binding and fresh post-callback check remains.
The measured origin-seal cost, rather than cheaper module scans, is material;
context binding also contains concrete duplicate traversal.
Require mutation/replacement and physical fence coverage before a further
runtime change. Older and extended tags have different sampling overhead. The
pure-origin candidate addresses one repetition; H/C evaluation, context and
lineage work remain. Preserve independent callbacks, withdrawal, physical and
terminal ordering and keep all work inside frozen response clocks. Report
construction, response, correction propagation and recovery separately. Stop
while only runs remain and resume when the owner returns; do not burn tokens
waiting. Expand infrastructure only for a named experimental need.

Use a frozen explicit context route first. An adaptive learned planner, complete
episode subsystem or mission platform is not required to fix this proof
amplification. Expand only for a named experimental case. After the existing
slice is usable and model exports are qualified, run relevant/irrelevant/outcome
pilots, finalize preregistration, compare with the serious baseline and ablation,
then attempt builder transfer. Do not wait on models to repair independent
infrastructure, and do not invent a learned result while models are absent.

## FBM continuity

[docs/fbm-seeds](fbm-seeds/README.md) holds append-only public procedure JSONL
rows under Alice trace schema v0.1. Record observable inputs, choices,
constraints, method, authority, actual validation, outcome and failure lesson.
Link a repair to earlier trace IDs; preserve failures. Validate schema and
unique IDs with `docs/fbm-seeds/validate_traces.py`.
The latest inventory has **111 schema-valid procedure records**. All three FBM
contract tests passed at the 110-record checkpoint; the appended refined-cost
record was separately validated with the complete inventory. These tests
validate record shape and rejection rules, not learning or linked-case readiness.

These are builder construction-method seeds, not Flora's runtime personal
memory. They are not weights or automatically eligible training/evaluation
cases. Supervised cases additionally need permitted concrete inputs, independent
targets, authority/outcome records and source/generator split lineage. Capture
new material steps here without delaying construction or changing Alice's repo.
