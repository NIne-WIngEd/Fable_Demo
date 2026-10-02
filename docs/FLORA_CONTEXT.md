# FloRA continuation context

Updated: 2026-10-02, America/Chicago. Recovery baseline:
`main@885be57abb582510d27a98177facd2a358c11387`; recovery starting runtime
`74f42417be37a2fbdc6c603a1ea657b040e0052e`.

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
Current ordinary CI remains pending; the candidate's source and controlled
results must be recorded separately before publishing a runtime claim.

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
Frame identity above remains `ef9c190e`; worker repair is at `9b57ed3`; current observation source is
`bf59736673d4f054ff85636ca80a1983d14d7cd5`. The context branch records that work;
code remains on the development branch
until reviewed. Do not infer its implementation from the context branch's
runtime files. Final frame SHA-256 is
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

Next collect the exact bf597366 native aggregate, verify source hashes and owned
coverage, and compare pure binding, H/C evaluation, context preparation, lineage
and RPC cost. Use the middle-layer audit's smallest falsifiable proposal if the
observations support it. Keep independent callback, withdrawal, physical and
terminal ordering cases; do not move old work out of frozen clocks. Then compare
the original exact-engine responses under unchanged caps. Report construction,
response, correction propagation and recovery separately. Stop while only runs
are pending, then resume when the owner returns.

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

These are builder construction-method seeds, not Flora's runtime personal
memory. They are not weights or automatically eligible training/evaluation
cases. Supervised cases additionally need permitted concrete inputs, independent
targets, authority/outcome records and source/generator split lineage. Capture
new material steps here without delaying construction or changing Alice's repo.
