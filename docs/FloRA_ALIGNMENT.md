# FloRA: selected architecture and build order

This repo investigates one causal personal-memory claim using a narrow slice of the successor architecture. **A.L.I.C.E. Phase 2 is void as this implementation's basis.** Stage G/H/I/J are replacing it. Older A.L.I.C.E. documentation may still describe it as canonical during migration; that is not authority for new FloRA code. The former Phase 2-based demo files survive in git history only.

**Owner scope correction — 2026-10-02:** alignment means retaining Alice's current contracts and selected physical adapters for capabilities the experiment actually needs. It does not mean implementing the full Alice memory, experience, mission or consumer release infrastructure. The table and lanes below describe the destination and existing work inventory. They are not mandatory completion targets. Full mission execution, federation, scale-out, every memory plane and complete product lifecycle work are deferred unless a named experimental case requires them. Preserve useful completed modules and their evidence; do not broaden serving merely to exercise every service. [Continuation context](FLORA_CONTEXT.md) and [the interconnected Alice map](ALICE_INFRASTRUCTURE_MAP.md) preserve this boundary.

The [frozen FloRA experiment goal](EXPERIMENT_GOAL.md) controls what counts as a behavioral or builder result.

The [2026-09-29 readiness re-audit](READINESS_REAUDIT_2026-09-29.md) supersedes the previous conclusion that only personality and MFM remain. The independent lanes below are not complete. It also records a newer MFM interface and conflicting engine choices in Fable Sleight's execution profile; this map follows the A.L.I.C.E. successor selected by the owner, rather than claiming all product documents already agree.

Sources reviewed: A.L.I.C.E. `main@8ea804aa` `docs/ALICE_PHASE2_REPLACEMENT_AND_FABLE_V1_EXECUTION_PLAN_2026-09-27.md`, `docs/STAGE_G_MEMORY_FABRIC_CANDIDATE_QUALIFICATION_MATRIX.md`, `docs/PHASE2_TO_KERNEL_MEMORY_MIGRATION_PLAN.md`, `docs/FRIDAY_ROADMAP.md`, `docs/FRIDAY_ARCHITECTURE.md`, `docs/FABLE_PERSONAL_DEVELOPMENT_ARCHITECTURE.md`; current MFM branch `research/mfm-foundation-20260923@4f287a48` formation contracts, sources, context planner and retrieval router.

## Alice destination and the prototype boundary

| Role | Selected implementation | Demo boundary |
| --- | --- | --- |
| Original evidence | Encrypted content-addressed object plane, S3-compatible abstraction and local placement | In progress. Original remains separate from model interpretation. |
| Experience | KurrentDB behind A.L.I.C.E./Fable-owned event contracts; NATS JetStream for edge/device ingress | Ordered, replayable observations, corrections, decisions, outcomes, idempotency and checkpoints. |
| Claims | XTDB v2 authority | Evidence-linked versions, valid/system time, conflict and supersession. |
| Formation | Learned MFM -> `MemoryProposalBundle` -> deterministic gate | MFM is built elsewhere; a proposal cannot make itself true. Gate can be built here. |
| Personal development | Governed host, relationship and assistant-self state | Keep origins, uncertainty and revisions separate. No placeholder judgment model. |
| Recollection | Governed episodes; LadybugDB local graph/NebulaGraph scale-out; Qdrant vector; exact/source-native access | Pick the relevant planes adaptively and retain consumed source IDs. |
| Decision | First-party Context Planner -> separately trained EIPM/native personality judgment | The decision must be caused by personal state, not just retrieve a corrected sentence. |
| Learning | Outcome event -> governed candidate -> versioned personal state/model | Measure whether a later judgment changes when it should, and does not change when it should not. |
| Continuity | Temporal workflows, local L1/Valkey, lineage registry, deletion, device reconciliation | Crash, replay, recovery, correction, rollback and influence removal. |

These are the selected full-product components. FloRA exercises only the subset needed by the experiment, preserving the actual roles and chosen engines for any claim about their behavior. Unused destination components need not be built or queried.

## Existing implementation lanes and conditional later work

1. **Raw and Experience:** object plane, project-owned event envelope/stream contract, KurrentDB adapter, edge ingress and recovery.
2. **Authority:** XTDB claim persistence, deterministic formation gate, as-of reading, supersession and deletion lineage.
3. **Recollection:** episodes and graph/vector/source projections, adaptive context selection and evidence packet.
4. **Development:** versioned host/relationship/self state, correction and outcome governance, intervention and rollback.
5. **Integration:** consume real MFM proposals and qualified personality judgment; freeze held-out synthetic experiment and strong comparator.
6. **Builder transfer:** once the claim works, train a small FBM to reproduce that qualified slice for another host.

Relevant parts of the first four lanes do not require personality or MFM weights; completing every lane is not the prototype goal. The current minimum native route is encrypted originals, Kurrent Experience, XTDB accepted/current Claim and governed state, exact selected context and attributed decisions/corrections/outcomes. Optional episodes, graph/vector routes and durable workflows enter only when needed. A learned formation result and native behavioral test **do** depend on the separate workstreams. No deterministic rule is to be relabeled as a learned model.

## Evidence discipline

- Unit checks for contracts and encryption are component checks. They do not validate KurrentDB/XTDB behavior or the personal judgment claim.
- The first real-backend gate is green for KurrentDB expected-revision/retry/replay and restart persistence, plus XTDB valid-time correction reads, host isolation and restart persistence. This is a basic integration gate, not complete backend qualification.
- A claim of full backend qualification would require the remaining conflict, projection-rebuild, deletion/influence-removal, failure-injection, recovery and scale cases defined by the selected architecture. The prototype qualifies only its implemented and exercised slice, retaining current-use, correction, isolation and recovery checks for that slice.
- The behavioral result requires qualified models, held-out longitudinal histories, a comparator with equal evidence and budget, and assessment of reasons and behavior. Synthetic results are labeled synthetic.
- The builder result requires a second isolated host. A single hand-configured personality is not evidence of automatic building.

Development environment status: `compose.integration.yml` and GitHub Actions provide real KurrentDB 26.1.1, XTDB 2.1.0, NATS JetStream 2.12.15, and Qdrant 1.18.3. [Run 36572682119](https://github.com/NIne-WIngEd/FloRA/actions/runs/36572682119) passed the authority restart probes, a pending NATS event across service restart and canonical reconciliation, plus XTDB-guided Qdrant obsolete-point cleanup using synthetic vectors. This does not qualify multi-device conflict policy, embedding quality, scale, or complete deletion/influence removal. LadybugDB and a local Temporal dev server now have narrower integration gates described below. Credentials and user data must stay out of the repository.

[Run 36574357535](https://github.com/NIne-WIngEd/FloRA/actions/runs/36574357535) also passed the three-subject XTDB candidate registry, versioned host revision, negative synthetic approval, exact KurrentDB approval binding, and active-state read after source revalidation. The approval verifier in this integration test is synthetic; production owner authentication and learned state updates remain open. These results do not qualify personal judgment or FloRA's experimental goal.

[Run 36574921127](https://github.com/NIne-WIngEd/FloRA/actions/runs/36574921127) passed the outcome-to-candidate handoff: exact decision/outcome evidence, rejection of an unlinked observation, idempotent candidate registration, and the previously approved state remaining active. The candidate content was supplied by the synthetic test; this is not learned updating or evidence that the prior decision used personal state.

[Run 36576886064](https://github.com/NIne-WIngEd/FloRA/actions/runs/36576886064) passed local context delivery receipts and the claim source-use quarantine across XTDB, Qdrant, state, and later contextual decisions. Context receipt proves delivery, not model attention. Quarantine blocks new use through those paths; it does not erase raw objects, events, all derivatives, or model influence. The [paired evaluation contract](EVALUATION_PROTOCOL.md) is implemented without a model or score.

[Run 36609979659](https://github.com/NIne-WIngEd/FloRA/actions/runs/36609979659) passed host-local LadybugDB exact evidence projection and source-verified graph retrieval before and after a Claim correction. [Run 36610759574](https://github.com/NIne-WIngEd/FloRA/actions/runs/36610759574) passed XTDB episode candidate registration, invalidation after source correction, and a subsequent candidate generation. Neither run demonstrates learned semantic relations or MFM episode formation.

[Run 36611170900](https://github.com/NIne-WIngEd/FloRA/actions/runs/36611170900) passed Temporal activity retry in a local dev server and real XTDB/Qdrant/LadybugDB cleanup after source quarantine. The Temporal test server has in-memory persistence; durable server restart recovery and complete deletion remain open.

[Run 36611584250](https://github.com/NIne-WIngEd/FloRA/actions/runs/36611584250) passed a host-bound Ed25519 owner-action signature over the exact Experience deletion event before the quarantine write. It does not qualify a real person's key enrollment or recovery. The fictional [multi-year pilot fixture](../data/synthetic_pilot/v1.json) prepares three source-lineage cases and has no model score.

[Run 36612501266](https://github.com/NIne-WIngEd/FloRA/actions/runs/36612501266) passed two-stage pilot ingestion in separate fictional KurrentDB host streams. The before phase reaches the evidence-verified MFM input boundary before its intervention is appended. The after phase adds one relevant correction, irrelevant correction, or outcome, then rejects a second application. All three carry generated/synthetic provenance. This is prepared input, not learned formation or a judgment result.

[Run 36619700275](https://github.com/NIne-WIngEd/FloRA/actions/runs/36619700275) passed the audit repair commit `96a6302c`, including an explicit before-phase decision before the intervention, actual decision-linked outcome ingestion, and the corrected fictional trial chronology. It qualifies that repair on selected backends; it does not complete the remaining independent lanes.

The [registered formation slice](REGISTERED_FORMATION.md) integrates current MFM schema 1.2.0 with XTDB durable source/custody references, actual Kurrent record time, parent closure and current permission checks. [Run 36623668349](https://github.com/NIne-WIngEd/FloRA/actions/runs/36623668349) passed the source/context integration at `9b1f024`. [Run 36625507265](https://github.com/NIne-WIngEd/FloRA/actions/runs/36625507265) passed signed durable permissions, proposal/value custody and authority-restart recovery at `0e0a69af`. Recollection adapters preserve original Experience IDs and route provenance; embeddings and learned selection are not qualified.

The [artifact registry](ARTIFACT_ADMISSION.md) now has deterministic qualification/custody/CAS checks and new actual XTDB integration cases. Its production external qualification adapters remain model-owner dependencies. The [persistent Temporal gate](TEMPORAL_PERSISTENCE.md) adds a server/PostgreSQL restart probe; that new gate awaits its own CI result rather than inheriting the earlier in-memory server receipt.
