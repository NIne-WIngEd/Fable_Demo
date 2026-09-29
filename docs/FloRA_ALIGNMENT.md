# FloRA: selected architecture and build order

This repo qualifies one causal personal-memory claim within the full-scale successor architecture. **A.L.I.C.E. Phase 2 is void and ancient for this implementation.** Stage G/H/I/J are replacing it. Older A.L.I.C.E. documentation may still describe it as canonical during migration; that is not authority for new FloRA code. The former Phase 2-based demo files survive in git history only.

Sources reviewed: A.L.I.C.E. `main@8ea804aa` `docs/ALICE_PHASE2_REPLACEMENT_AND_FABLE_V1_EXECUTION_PLAN_2026-09-27.md`, `docs/STAGE_G_MEMORY_FABRIC_CANDIDATE_QUALIFICATION_MATRIX.md`, `docs/PHASE2_TO_KERNEL_MEMORY_MIGRATION_PLAN.md`, `docs/FRIDAY_ROADMAP.md`, `docs/FRIDAY_ARCHITECTURE.md`, `docs/FABLE_PERSONAL_DEVELOPMENT_ARCHITECTURE.md`; MFM branch `research/mfm-foundation-20260923@00583fb2` `src/cognitive_kernel/formation_contracts.py`.

## Full-scale path for the claim

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

These are selected full-scale components, not a menu of replacements. An internal demo can exercise one narrow capability, but it must preserve the actual roles and use the chosen engines for any claim about their behavior.

## Independent work in this repository

1. **Raw and Experience:** object plane, project-owned event envelope/stream contract, KurrentDB adapter, edge ingress and recovery.
2. **Authority:** XTDB claim persistence, deterministic formation gate, as-of reading, supersession and deletion lineage.
3. **Recollection:** episodes and graph/vector/source projections, adaptive context selection and evidence packet.
4. **Development:** versioned host/relationship/self state, correction and outcome governance, intervention and rollback.
5. **Integration:** consume real MFM proposals and qualified personality judgment; freeze held-out synthetic experiment and strong comparator.
6. **Builder transfer:** once the claim works, train a small FBM to reproduce that qualified slice for another host.

The first four lanes do not require personality or MFM weights. A learned formation result and native behavioral test **do** depend on those separate workstreams. No deterministic rule is to be relabeled as a learned model.

## Evidence discipline

- Unit checks for contracts and encryption are component checks. They do not validate KurrentDB/XTDB behavior or the personal judgment claim.
- The first real-backend gate is green for KurrentDB expected-revision/retry/replay and restart persistence, plus XTDB valid-time correction reads, host isolation and restart persistence. This is a basic integration gate, not complete backend qualification.
- Full backend qualification still requires the remaining conflict, projection-rebuild, deletion/influence-removal, failure-injection, recovery and scale cases defined by the selected architecture.
- The behavioral result requires qualified models, held-out longitudinal histories, a comparator with equal evidence and budget, and assessment of reasons and behavior. Synthetic results are labeled synthetic.
- The builder result requires a second isolated host. A single hand-configured personality is not evidence of automatic building.

Development environment status: `compose.integration.yml` and GitHub Actions now provide repeatable real KurrentDB 26.1.1 and XTDB 2.1.0 services with restart persistence checks. The next external service work is NATS JetStream, Qdrant, LadybugDB and Temporal as those lanes reach their selected contracts. Credentials and user data must stay out of the repository. Do not broaden the stack merely to make a demo look complete.
