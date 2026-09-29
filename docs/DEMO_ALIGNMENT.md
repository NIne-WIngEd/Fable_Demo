# Fable demo architecture alignment

This is an internal experiment for **one causal personal-memory claim**, not a smaller Fable v1 release. Its current compatibility runtime is not yet the selected successor fabric.

Source decisions reviewed:

- A.L.I.C.E. `main@8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b`: `docs/ALICE_PHASE2_REPLACEMENT_AND_FABLE_V1_EXECUTION_PLAN_2026-09-27.md`, `docs/STAGE_G_MEMORY_FABRIC_CANDIDATE_QUALIFICATION_MATRIX.md`, `docs/PHASE2_TO_KERNEL_MEMORY_MIGRATION_PLAN.md`, `docs/FRIDAY_ROADMAP.md`, `docs/FRIDAY_ARCHITECTURE.md`, `docs/FABLE_PERSONAL_DEVELOPMENT_ARCHITECTURE.md`, and `docs/MEMORY_IDENTITY_FORMATION_AND_HOST_LEARNING_ARCHITECTURE.md`.
- A.L.I.C.E. `research/mfm-foundation-20260923@00583fb25fbe07c1452519992de2bc8055dcebd5`: `docs/MEMORY_FORMATION_MODEL_FOUNDATION.md` and `src/cognitive_kernel/formation_contracts.py`.
- Fable Sleight README: first release requires the connected personal foundation; feature language/coding/simulation may use replaceable external services under local control.

## Destination loop and selected implementation

| Role | Selected Fable/A.L.I.C.E. implementation | Why the demo needs it for the first claim |
| --- | --- | --- |
| Raw evidence | Encrypted content-addressed object store behind an S3-compatible abstraction | Reconstruct exactly what was observed. |
| Experience | KurrentDB behind project-owned event contracts; NATS JetStream for device/edge ingress | Preserve ordered observations, decisions, corrections, and outcomes. |
| Claim authority | XTDB v2 | Distinguish current claims from what was known and valid at an earlier time. |
| Formation | Learned MFM -> `MemoryProposalBundle` -> deterministic Memory Gate | Interpret experience without letting model output become truth. |
| Personal state | Governed host, relationship, and Fable-self projections | Keep their histories and influence distinct. |
| Episodes and graph | Governed episodes; LadybugDB local graph, NebulaGraph at scale; associative graph compute | Link events, goals, people, decisions, and outcomes when relevant. |
| Semantic retrieval | Qdrant Edge/server/cluster; exact/source-native access in parallel | Retrieve meaning and inspect original evidence. Do not replace the selected vector plane with SQLite search. |
| Context and judgment | First-party Context Planner -> EIPM/native judgment -> identity decision packet | Let learned personal state influence the decision before feature wording. |
| Outcome learning | Outcome event -> governed candidate revision -> versioned personal state/model | Establish a causal change in later relevant judgment. |
| Workflow and continuity | Temporal, model/data lineage registry, local L1/Valkey, deletion influence, device reconciliation | Retry, rebuild, correct, delete, and preserve state across model/device changes. |

The full Fable v1 requires all logical planes. An internal demo can focus on a bounded claim, but it must use the same semantics and selected engines for the planes it exercises. It cannot substitute another physical backend and call the resulting benchmark evidence for the selected stack.

## First demo claim and dependency order

The intended claim is: **after a host corrects a relevant preference and a later decision has an outcome, Fable's subsequent personal judgment changes for the right reason and preserves the evidence trail**. The experiment must distinguish a retrieved fact from a changed native judgment. A strong general-model-plus-memory comparator receives the same allowed evidence and response budget.

1. **Formation contract — active here.** A recorded event becomes a scoped `FormationContextPacket`. A learned model may return a `MemoryProposalBundle`. The upstream binding validator rejects absent evidence, wrong host, and changed context. This is backend-neutral and independent of EIPM. No proposal gains authority here.
2. **Selected fabric — not built here yet.** Wire the encrypted object plane, KurrentDB experience, XTDB claim authority, and deterministic gate. Preserve exact event/claim IDs and bitemporal semantics. Port the existing compatibility runtime only through explicit adapters and compare its output; never treat its SQLite stores as the experiment's chosen backend.
3. **Selected recollection — not built yet.** Materialize source-linked episode/graph and Qdrant projections when the chosen claim needs them. Implement source-native access and an adaptive planner that can select zero or several planes. Record consumed evidence and sufficiency. Do not use a manually supplied memory key in the eventual behavioral test.
4. **Learned formation and personal development — independent of personality training, not built here.** MFM work on its own branch must emit actual learned proposals. Host, relationship, and self state need governed versioned updates and isolated interventions. Outcome feedback remains evidence until the gate and updater decide its influence.
5. **Native judgment — dependent on EIPM, not built here.** Connect the separately qualified personality model through its versioned personal-state/ACFP/IDP interface. A stored packet or a generic model's response cannot stand in for this stage.
6. **Behavioral experiment — dependent on steps 2–5.** Freeze a substantial synthetic history and held-out questions; measure relevant and irrelevant judgment changes, evidence lineage, provider swap, latency, and a strong comparator. The older fixtures only check legacy plumbing.
7. **Builder transfer — independent FBM lane but dependent on a proven target capability.** Make a small FBM reproduce that qualified capability for another isolated fictional/consenting host. The full builder remains a broader product goal.

## Current code boundary

`runtime.py`, `memory_lane.py`, the old fixtures, and their passing checks run on A.L.I.C.E.'s released Phase 2/reference stores. They are useful for interface and compatibility work. They are **not** selected-stack qualification, a trained MFM, a learned host/relationship/self model, or evidence of the first claim. Their manually supplied keys and confirmations cannot be treated as autonomous formation.

`formation_context.py` now uses the MFM branch's shared `FormationContextPacket` and `MemoryProposalBundle` binding contract. It treats unverified CLI input as historical experience, not authenticated owner speech. The packet can reference a current Phase 2 claim for development, but this must be replaced by registered XTDB authority before the behavioral experiment. This code is a reusable interface slice and cannot by itself validate either backend or learned behavior.
