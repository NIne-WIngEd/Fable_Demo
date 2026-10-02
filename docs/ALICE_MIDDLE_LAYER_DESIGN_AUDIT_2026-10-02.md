# FloRA / Alice middle-layer audit — 2026-10-02

Source-grounded design review for the narrow prototype. This record changes no
serving contract and qualifies no model, response latency or behavioral result.
The source audit and independent proposal review are separate from test execution.

## Refined observation completed

The four-tag diagnostic completed with a failed fixture and qualification
false. [Its source-verified receipt](evidence/2026-10-02_d0f90655_native_profile_validation.json)
matches 116 files. Origin seal traversal recorded 10,063 calls / 21.670 s
exclusive CPU; context binding recorded 245,532 / 13.555 s. The descriptor
contract scan was 2.341 s and frame contract scan 1.507 s exclusive CPU.
This refines the remaining preparation cost; added sampling prevents treating
it as an equal-overhead speedup comparison. Every independent seal remains
required. [The checkpoint](VERIFICATION_CHECKPOINT_2026-10-02.md) records the
conditional shared-dependency representation question and pending ordinary CI;
no further runtime rewrite or memory/mission plane is added.

### Conditional pure-proof follow-up after ordinary CI

Read-only source review identifies two concrete representations to investigate.
Neither is implemented or qualified here:

- `_verify_origin_seal` may materialize typed current origin fields/readers/
  function seals once within one callback-free exact-origin pass. **Every
  descriptor's independently registered expected seal must still be compared.**
  Do not share by history digest or cache a successful seal/permission answer.
- Frame `_verify_binding` traverses nested captures and then calls
  `_FunctionBinding.verify`, which traverses those nested captures again.
  Investigate shallow checks at each node with one explicit nested/closure-reader
  traversal, retaining every owned weak seal, function code, closure/global
  binding, reader seal and opaque callback code pin.

Before either change, discriminate corrupt second/inherited descriptor seals,
replaced nested captures, in-place nested mutation after callbacks, installed
owner changes and later fresh boundaries. Reject replacement objects before
dereferencing or equality effects. Keep physical and terminal mutation cases.
Fresh post-callback/terminal verification must remain; this is bounded pure
dependency processing of the existing slice, not another memory/mission plane.
The reviewed source is `da370ebc` runtime, unchanged at `d0f90655`; the ordinary
source-pinned engine/component gates are still separate from this proposal.

A private issued dependency record is source-level feasible because readers
and function bindings already share exact objects. Bind each registration to
its own descriptor, exact Origin and exact dependency-record identity; reobserve
the actual graph at every fresh pure boundary. Record expected structure only,
with no verified/allow/current-head success bit. Keep owner-held dependencies
and weak/scalar registry relations: a global `_ISSUED` record must not strongly
retain Origin/readers/functions and keep closed sessions alive. Preserve the
existing closed-owner-cycle collection regression. Compare acceptance and
rejection against the current full seal traversal, including independently
issued same-history origin swaps and second/inherited descriptor corruption.

## Current original-code observation

Source `d0f90655` adds only four numeric fixed targets for descriptor tree,
descriptor contracts, origin seals and frame contracts; all prior targets and
budgets remain. Runtime source/tests are identical to `da370ebc`. All 32
observer contracts pass in 3.493 s, separate from the 72 runtime contracts.
The [checkpoint](VERIFICATION_CHECKPOINT_2026-10-02.md) and
[receipt](evidence/2026-10-02_d0f90655_observer_contracts.json) link pending
diagnostic 37073820659 and ordinary PR CI 37073825647. The extra targets add
sampling overhead, so this new scope supports attribution rather than direct
equal-overhead speedup measurement. The previous failed fixture is preserved.

## Completed da370ebc observation

The source-verified fixture failed; collection success does not qualify the
response. Six owned jobs recorded 120.902 s wall / 109.280 s thread CPU and
two preparation calls consumed 119.398 s inclusive wall. More frame/RPC work
was reached within unchanged deadlines, while public descriptor work moved
into private tree traversal under base_bindings. Parent setup is unobserved;
no equal-work speedup or downstream generation attribution follows.

The [latest checkpoint](VERIFICATION_CHECKPOINT_2026-10-02.md) preserves all
116 source hashes, original artifact, numeric comparison, complete 72 targeted
passes and current ordinary CI. The bounded next observation adds only four
original-code tags for descriptor tree/contracts, origin seals and frame
contracts. Added observer overhead changes coverage; it supports diagnosis,
not another runtime rewrite or more memory/mission infrastructure.

## Current bounded implementation

The measured `bf597366` owned profile supersedes the zero-entry diagnostic
described in the earlier audit. It localizes repeated pure origin/binding work
in the reached preparation stage; it cannot attribute unreached lineage or
setup. [The checkpoint](VERIFICATION_CHECKPOINT_2026-10-02.md) binds all loaded
file digests and the failed fixture to exact source.

Candidate `da370ebc9b089aec430859059cc83af52e623089` implements only call-local
exact-origin body de-duplication, with every descriptor/parent seal and fresh
post-callback/next-boundary check retained. The
[component receipt](evidence/2026-10-02_da370ebc_origin_contracts.json) records
72 targeted passes, including the complete original frame suite; ordinary
engine gates remain pending. It changes no ledger or evidence/Claim/state/judgment/outcome role,
adds no mission platform and implements no personality or MFM model.

The source findings below still identify overlapping full-H recovery, H×C
evaluation and context/lineage reconstruction as conditional follow-up work.
Alice's materialized-current serving and separately bounded reconstruction
guide that design; compiled plans are a proposed adaptation, not a qualified
upstream mechanism. Preserve fresh current authority and exact original
evidence while measuring the remaining stage before a further redesign.

## Finding and limits

FloRA already connects exact Experience evidence, governed Claims/current
personal state, selected context, native execution lineage and decision-linked
outcomes. I found no Mission Graph, Result Capsule, Traceback or semantic
mission-routing implementation in src/flora. The current comparison route is
an experimental BEFORE/AFTER route, not a conversational mission runtime.

The remaining hot path does reconstruct overlapping custody/context/lineage
outside the fresh selected frame. That is a concrete alignment question against
Alice's materialized-current/explicit-reconstruction design. It is not evidence
that a full mission platform was built or caused the timeout.

The current 9b57ed3 diagnostic capped at 180.013s with zero owned-reader entries.
No current frame-cost attribution is established. The published workers-only
measurement must reach the owned slice before selecting a latency rewrite;
setup remains unobserved under the separate CI cap. Old measured repeated
proof CPU belongs to its historical source, not this audit's current runtime.

## Source identities and authority

| Role | Exact source |
| --- | --- |
| Current FloRA runtime audited | 9b57ed3ce0d634409c967983bd5878ff74b48d3b; current hot-path sources read locally |
| Alice revised architecture authority | main 8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b; originals read with git show at that ref, rather than the checked-out runtime branch |
| Alice actual imported contract/API pin | research/mfm-foundation-20260923 at 4f287a488bc908bd04f99255ee01b794bacba50b; local checkout remains detached at this pin |
| Revised comic/storyboard | Fable_Sleight 1805a01c73575378246cac8cbbb72cd891e8528e, comic/STORYBOARD.md; fetched directly, Markdown rather than PDF |
| Graphify developer navigation | research/graphify-v1-model-routes-20260930 at 39666dba43aa39d6321933b4952e62f60ed70621, separate research authority |

The October2 owner instruction narrows FloRA to one causal Alice/Fable claim.
Full-product no-capability-reduction and all-plane StageG gates do not become
prototype prerequisites. Architecture8ea804 and API 4f287a are distinct;
the former governs design/physical choices and the latter supplies concrete
interfaces. Phase2 compatibility implementations cannot replace the selected
FloRA engines.

Local orientation was docs/ALICE_INFRASTRUCTURE_MAP.md,
docs/FloRA_ALIGNMENT.md, docs/FLORA_CONTEXT.md and the latest checkpoint.
Consequential findings below follow original sources and code, not summaries.

## What the revised entity actually connects

Canonical originals:

- [Execution plan8ea804](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b/docs/ALICE_PHASE2_REPLACEMENT_AND_FABLE_V1_EXECUTION_PLAN_2026-09-27.md):
  MFM1:262–275 selective Formation Context Planner; MFM3:298–300 semantic
  proposals cannot authorize themselves; MFM5:313–336 fast/slow formation;
  D2:364–384 canonical Experience contracts; D3:388–409 XTDB bitemporal
  Claim authority; D13/D14:578–616 scheduler and selective recollection;
  F1/F2:779–785 persistent mission state/workspace projection.
- [Memory Architecture v4.1](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b/docs/MEMORY_ARCHITECTURE_V4.md):
  §3.1 Experience records observation/action/invocation/outcome/correction/
  processing; §3.2:55–63 adjudicated Claim authority and materialized current
  serving, with historical reconstruction explicit and bounded.
- [Record/provenance standard](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b/docs/MEMORY_RECORD_AND_PROVENANCE_STANDARD.md):
  §§3.4–3.8:69–87 stable Claim identity, immutable versions, rebuildable current
  projection, typed evidence relations and adjudication.
- [Performance standard](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b/docs/MEMORY_PERFORMANCE_AND_RELIABILITY_STANDARD.md):
  §§4–7 materialized state, batch hydration, bounded plans, generation-aware
  indexes, selective context and separately scheduled reconstruction.
- [StageG matrix](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b/docs/STAGE_G_MEMORY_FABRIC_CANDIDATE_QUALIFICATION_MATRIX.md):
  §§6.1–6.5:245–270 consumed evidence, consolidation path dependence, calibrated
  influence, capable route selection and procedural-versus-factual roles.
- [Mission contracts](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b/docs/PHASE_5_MISSION_GRAPH_CONTRACTS.md):
  stable scoped identities; successor state; typed hierarchy/dependency links;
  ResultCapsule evidence/event references; contiguous scoped Traceback.
  The original milestone explicitly does not implement a mission runtime.

The entity is continuous because these representations share scoped identities,
typed evidence/derivation/decision/outcome links and versioned authority.
Experience is the durable record of what was supplied/observed/done; Claims are
adjudicated knowledge; personal state is governed interpretation; mission
structure is persistent goal/dependency state; workspace/retrieval are views.
One representation cannot silently become another's truth authority.

The verified [storyboard](https://github.com/NIne-WIngEd/Fable_Sleight/blob/1805a01c73575378246cac8cbbb72cd891e8528e/comic/STORYBOARD.md)
makes this concrete. Pages33–35 retain a project's technical success and missed
deadline, the original goal/evidence/warning/override and failed assumptions,
then retrieve only relevant workload and project-value lessons. Page37 governs
future influence with the owner. Page42 is context-sensitive long-horizon
recall; page46 is mission continuity beyond a conversation; page47 replans from
new evidence. Pages40/54 preserve continuity through model changes and keep
unresolved improvements as challengers. These are not instructions to scan all
ledgers synchronously for every answer.

## Actual connected FloRA slice

All following source anchors are in runtime 9b57ed3. Repository-relative paths
name the inspected originals, not a proposed implementation.

| Stage | Actual connection and boundary |
| --- | --- |
| Original / Experience | selected/experience.py:195,251,266,395 binds host stream, append expected revision, exact committed lookup with full event digest/physical position/recorded time, and complete replay. selected/formation_registry.py registers source/raw custody, keeping payload out of the metadata ledger. |
| Proposal / Claim authority | selected/experiment_runtime.py:694 form_experience consumes external qualified MFM output; admission is separate. selected/claims.py:240,304,346,410 stores immutable versions, typed evidence relations and CAS-like current heads in XTDB. load_current reads materialized current state; current_history is an explicit historical API. |
| Personal state | selected/personal_state.py:410 follows active head to exact version and approval; governed_development.py:208,293 adds immutable activation/rollback receipts and current source checks. Candidate, formation permission and activation are distinct. Host/relationship/assistant-self identities remain scoped. |
| Judgment input | selected/context.py:153 assembles declared exact Claim/state routes and optional qualified retrieval routes. selected_context.py:235 supplies a finite current C view while retaining original Kurrent owner/positions; exact selected route excludes unsupported episode/vector/graph cases rather than silently falling back. |
| Protected boundary | context_guard.py:841,888 makes fresh initial barriers before nested private bytes; separate baseline and post-assembly capture frames finish before adoption. selected_authority_frame.py:550 orders independent callback → H validation/manifest observation → physical reobservation → joint terminal XTDB rows → pure bindings/discard. |
| Native decision | experiment_runtime.py:862 records exact context delivery, producer input/output and decision source parents; judgment_lineage.py:272 checks source/current-state/artifact/phase lineage. Decision receipts support attribution but do not prove learned behavior or model attention. |
| Outcome / revision | decision_outcome.py:108 records an independent observation linked to an earlier decision. outcome_revision.py:24–91 verifies those raw events and active predecessor, then registers an externally proposed successor candidate. governed_development.py:312 retains a separate activation boundary. |
| Comparison lifecycle | selected/native_arm.py:438–546 applies independent current authorization before preparation, dispatch, recovery, acceptance and selected writes. These are separate protected operations, not a mission command graph. |

The minimum prototype loop therefore exists structurally:
source Experience → qualified proposal → deterministic admission → current
Claim/personal state → relevant exact context → native judgment/decision →
linked observed evidence → proposed governed revision. Models, semantic
quality and causal behavioral evidence remain outside this structural result.

The pilot deliberately separates original evidence from native audit:
pilot_lifecycle.py:383–413 appends an equal-arm original observation/correction,
and for an outcome adds a separate audit linking that observation to the prior
native decision. Its causal_claim is none and its synthetic status is explicit.
Only the original observation enters AFTER history; the native audit/decision
does not become comparator evidence. test_native_pilot_lifecycle.py:100 verifies
that distinction. It preserves linkage without promoting execution records
into shared user history.

## Proven repeated construction versus cost hypotheses

### 1. H current grants are necessary; repeated private H authentication is separate

H is the exact registered original history for scientific/evaluation authority,
including unselected originals and the physical manifest. C is the selected
judgment/source closure. Their purposes/caps are independent; small C cannot
erase H's current evaluation rights.

However, comparison_custody.py:945–967 authorize_history performs complete
replay_committed and raw_custody.read of every original to compare plaintext,
then a terminal metadata fence. Native_reads.py:375 calls this at phase-gate
installation, and judgment_lineage.py:291 calls it again at lineage entry.
This is more than a fresh permission/head observation.

Later guards already use authorize_history_metadata. The existing
authenticated_history.py:157–176 holds actually authenticated bytes and
rechecks current authority without reopening originals. Its owner/controller
binding prevents treating a caller's bytes or positive boolean as proof.
The actual integration fixture history_for is a held histories dictionary
(test_selected_native_comparison.py:176); that fact does not bypass the
unconditional full authorize_history calls described above.

Known: repeated authentication/whole committed replay at these entry points.
Hypothesis: eligible within-owned-operation immutable H custody reuse could
avoid redundant byte work, followed by fresh metadata/physical authority.
A proof cannot simply cross a newly owned SQL/controller session; ownership
and fresh target contracts must be designed and tested first.

### 2. Fresh frame shares rows; canonical work can still multiply

selected_authority_frame.py:411–420 local permits calls
history.validate_permissions for each C predicate. That method,
selected_history_contribution.py:287–300, loops all H evaluation IDs.
Other frame construction/binding checks are deliberately repeated around
callbacks. This can create logical H×C work even when sampled SQL rows are shared.

Known: this code nesting. Hypothesis: cost and the eligible pure-work subset.
Fresh live permission answers cannot be retained across boundaries. Unknown
custom callbacks must continue to run; a supposedly pure segment must first
prove its native code/readers/owners remain fixed. No optimization is approved
by this observation.

### 3. Original assembly and independent lineage remain outside that sharing

- context_guard.py:944 calls assemble_context with original services/view;
  context.py:189–207 reads Claim sources and active state, then:269–291 reads
  active state again for its final authority/content comparison.
- selected_context.py:89–128 replay resolves the finite C closure, hydrates it
  and resolves again. Its allow_event:135 calls that replay. The shared frame
  replaces those local metadata traversals within its own boundary; original
  assembly still performs them.
- judgment_lineage.py:298 prepares current private context again and:305 maps
  runtime.log.replay. Runtime.log remains the original Kurrent log; selected
  preparation only passes a separate finite facade (experiment_runtime.py:840).
- lineage verification resolves both artifact roles at:417, runs independent
  phase qualifier callbacks and revalidates afterward:445–457.
- verify_native_result_details:480,503 constructs context lineage before and
  after recovery. Actual producer/recovery independence is required; repeated
  private context reconstruction is not thereby a necessary implementation.
- experiment_runtime.py:508 computes append revision from replay length, while
  _RuntimePrivateCustody.register:296 and _execute:549 also replay for exact
  canonical membership. These default contracts currently certify more than
  an exact source locator. Sparse list indexes cannot replace physical revision.

Known: these repeated constructions still exist despite a selected C frame.
Hypothesis: how much they contribute to owned-reader latency. The current
zero-entry diagnostic establishes none of their timings.

### 4. Not a demonstrated mission/history/evidence conflation

No Mission/ResultCapsule/Traceback/mission_id/node_id symbols were found in
src/flora. Original versus internal approval/delivery/decision/artifact records
are explicitly separated in judgment_lineage.py:215–221, source closure,
phase membership and pilot shared-history construction.

Episodes, graph/vector projection, Temporal and broader lifecycle modules exist
as inventory. Selected context rejects unsupported routes before private I/O.
Their existence does not show all planes executing on this native response.
The aligned omission is a full mission runtime and unused product planes;
the suspicious expansion is repeated proof construction over the slice already
selected, rather than a proven requirement for more middle-layer services.

## First bounded proposal: native origin verification

Independent inspection found a smaller pure-work hypothesis before broader
history or assembly changes. In selected_authority_frame.py:_base_bindings,
permission and event descriptors each call verify. At
selected_phase_authority.py:252–280, descriptor verification validates its
origin and recursively validates inherited parent descriptors; these may share
the identical origin. There is no authority callback or live read between
those duplicate original-origin traversals. This source structure is known;
its fraction of current latency remains unmeasured.

If the new original-code tags confirm a material cost, add a private native
descriptor-pair/tree validation path with a call-local set of exact verified
origin identities. Check each descriptor's private issuance, class, field,
gate, reader, parent and origin seals independently; verify each unique origin
once during that pure pass and discard the set on return. Keep the public
descriptor/gate behavior, actual callbacks, current H/C rights and terminal
ordering. Never keep an allow, head, qualification or validation success
across callbacks or protected boundaries. Distinct mutable owners are not
interchangeable because their digests happen to match.

Required regressions include same-origin inherited chain counts, different or
mismatched origins, forged issuance/parent/reader/code/held values, and mutation
before or after each real callback and terminal observation. No serving patch
has been made from this proposal. A compiled dependency plan is our possible
implementation of Alice's bounded-plan intent, not a claimed qualified upstream
mechanism. Keep the wider hypotheses below separate and measured.

## Further minimally aligned design proposals for review

1. Preserve current data-role topology, selected engines and exact scoped links.
   Do not add a unified replacement database, autonomous mission scheduler,
   all-plane planner or model implementation.
2. Use current Claim/state heads plus explicit source/control locators as serving
   inputs. Keep full custody authentication/recovery/history reconstruction as
   declared operations rather than incidental work repeated by each predicate.
3. After the owned-reader profile identifies a cost, choose one bounded change:
   a native data-only C/H/lineage contribution inside one fresh boundary; or a
   separately issued actual-byte-authentication handoff for one owned operation.
   Both must still run independent guards and end with current H/C/Claim/state/
   raw/head/activation/manifest/physical observations. Do not reuse a positive allow.
4. Treat original assembly/recovery/phase-qualifier behavior as independent
   contracts. A metadata frame must not remain open across multiple private
   operations. Do not optimize by deleting required byte boundaries.
5. If replay-to-find-current-revision is measured, add only a qualified native
   head/locator contract with exact physical ordering and conflict behavior.
   A finite selected view must never impersonate a canonical append revision.
6. If a future selected experiment requires mission context, retain only its
   stable goal/node identifiers and typed result/outcome linkage needed by the
   case. Full MissionGraph persistence, workspace and scheduling remain omitted.
   If the claim names outcome-to-state causality, test the link without turning
   native audit prose into equal-arm original evidence.
7. Record supported slice and limits: current materialization is governed, not
   an independent truth cache; delivery is not attention; structural lineage
   is not causal learned judgment; correction/withdrawal barriers are not full
   physical deletion or model unlearning.

## Contract evidence to preserve and gaps to close

Existing test definitions were inspected, not run by this audit:

- test_shared_authority_frame.py:108–290 covers one joint terminal/two physical
  observations, final selected C and unselected H withdrawal, separate purposes,
  Claim/state/activation terminal inclusion, pre-private qualification denial,
  and fresh barriers around ciphertext/plaintext.
- Later tests in that module cover origin/held values, effectful helper/class/
  reader replacement and captured physical-object mutation after observation.
- test_selected_context.py:67,98,104,305,324 distinguishes unrelated stream
  integrity from selected proof, live owner approval, disappearing exact target,
  unsupported episode custody and explicit caps/frozen routes.
- test_authenticated_history.py:43,87,110,123 verifies real ciphertext issuance,
  no repeated original opens on legitimate reuse, live withdrawal, controller/
  reader/domain/cap binding, and direct-path full authentication.
- test_governed_development.py:280,306,378 preserves candidate-vs-activation,
  parent/mid-read withdrawal, and inactive decision/outcome-linked successors.
- test_native_pilot_lifecycle.py:88,100,252 distinguishes originals, correction
  lineage, native outcome audit and recoverable partial intake.

A narrow proposed change needs additional falsifiable cases at its actual
consumer, rather than only helper tests:

- Native preparation, authorization and result recovery use the eligible held
  bytes without redundant original decryption; forged/unissued/foreign-session/
  re-bound proof takes full authentication or rejects before private I/O.
- Added unrelated stream events do not expand a declared selected metadata
  proof; all registered H originals and manifest still count and late unselected
  withdrawal still denies. Default whole-stream and explicit recovery retain
  their distinct integrity behavior.
- Same-source two-purpose and same-purpose separate nomination domains retain
  independent grants/caps; ancestor closure, cycles, position/recorded-time
  changes and internal BEFORE contamination reject.
- A final opaque callback revokes selected C, unselected H, Claim/state head,
  activation, source registration/raw reference or producer qualification;
  no cached positive result can survive it.
- Mixed outcome can preserve independent workload/value implications without
  forcing a single good/bad reward, and only independently approved relevant
  successor state becomes current. Qualified semantic proposals and later
  relevant/irrelevant judgment interventions belong to the model-owning lanes.
- If a mission identifier is introduced for a named case, it cannot cross host/
  product scope or become factual evidence; outcome/traceback creates successor
  state and preserves old reasons. No full mission implementation is needed
  for this contract test alone.

## Navigation provenance

Graphify stayed outside runtime authority. The39666dba branch's code-only graph
was built from foundationf357a767ca1542a4043944b380663f27b50c33ec, while recovered
foundation head isa19f8e8893422702c138182f239064385addf91c. Its static catalogs
were routing hints followed by original reads; no live graph query, rebuild
or freshness claim. Research branches and external implementation analogies
are separate from canonical8ea804 architecture and actual4f287a imported APIs.

The direct storyboard fetch used the already-applied Search/Exa capability.
No new external evidence is used as permission to relax Alice/FloRA contracts.


## Observation checkpoint

Source bf59736673d4f054ff85636ca80a1983d14d7cd5 changes only observation code,
its tests and the optional diagnostic workflow after 9b57ed3; the audited middle
layer is unchanged. All31 observer contracts passed on native ARM64 in4.990s,
including the original 21. Worker-only mode excludes parent/setup CPU and starts
each thread's bounded numeric window at its first exact owned-work entry;
it never cancels the fixture and reports long spans as partial. Four fixed
original-code tags expose descriptor/origin/function-binding/frame-binding work.
Native diagnostic 37068588428 and ordinary PR run 37068593649 remain pending.
The latest completed frame CIef9c190e passed 944 component tests but had49/53
physical passes, two failed response budgets and two incomplete cases. The
checkpoint retains those exact-source outcomes and the separate worker repair.
No measured speedup, learned judgment or full experimental acceptance follows.

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

