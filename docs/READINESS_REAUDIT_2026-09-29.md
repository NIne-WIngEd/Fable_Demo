# FloRA readiness re-audit — 2026-09-29

**Verdict: FloRA has not exhausted the work that can proceed without the personality model and MFM. The previous model-only stopping conclusion was premature.** The selected-backend foundation is useful, but tested components are not yet a connected experiment.

This audit rechecked FloRA's source, tests and CI, the live A.L.I.C.E. architecture and relevant model/builder branches, Fable Sleight's live product documents, and the five uploaded source-chat PDFs. No personality substitute, MFM substitute, new judgment model, or behavioral win was introduced.

## What FloRA is proving

- Part one: reuse the actual personality model and MFM, alongside selected memory infrastructure, to test whether a correction or outcome changes later native personal judgment for the right reason. Unrelated judgments should remain stable.
- Compare against a competent general model with memory under equal authorized history and comparable budgets. Use a same-evidence ablation to separate retrieval benefits from personal judgment updating.
- Part two starts after the first claim succeeds: a small FBM builds the same qualified slice for other isolated hosts. A hand-configured second host does not prove the builder.
- Synthetic histories establish mechanism evidence. Blind assessment with consenting real hosts establishes a different kind of evidence. Neither is presently demonstrated.
- A narrow internal experiment is permitted. It must preserve the selected roles and engines of the capabilities it exercises; it need not finish every consumer-v1 capability first.

The [frozen goal](EXPERIMENT_GOAL.md) remains correct. See the [experiment audit](EXPERIMENT_READINESS_AUDIT.md) for source-chat context and the missing evaluation work.

## Source and context checks

| Source | Audited ref | Consequence |
| --- | --- | --- |
| FloRA | `main@412f7bdff44ef4fc5690f7daab2be8390260885b` | Starting tree `963768ed5922e1b602fe1d3ecf4c659ffa132e9f`; local pre-audit commit has equivalent content. |
| A.L.I.C.E. selected architecture | `main@8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b` | Stage G/H/I/J successor is the design source; old Phase 2 is not an implementation basis. |
| MFM | `research/mfm-foundation-20260923@4f287a488bc908bd04f99255ee01b794bacba50b` | FloRA still pins older `00583fb2`; schema 1.2 and source/planner seams require deliberate integration. |
| FBM | `fable-builder-model@803477ba290030b3ed46459a90eb15529146fff2` | Procedure traces are seeds, not qualified construction cases or builder weights. |
| Personality work | foundation `a19f8e88`; joint-DDP branch `5e29f7f6` | Read for interface/dependency context only; this audit does not qualify a model. |
| Fable Sleight | `main@1805a01c73575378246cac8cbbb72cd891e8528e` | Product thesis aligns, but execution-profile engine choices drift from A.L.I.C.E.; see architecture audit. |
| Graphify context | `research/graphify-context-substrate@a06f61ea` | Used the repository's catalog query to route to formation, identity and builder sources, then verified current originals. |

Graphify's catalog anchor matches the live historical `alice-eipm-v1-build` ref, but its branch pointers predate newer MFM/FBM work. Its code graph receipt names the older foundation commit `f357a767`, not today's foundation or joint-DDP head. That code graph was not treated as current topology. The missing newer branches and changed source pointers are retrieval freshness gaps, not evidence that the work is absent.

## What was done correctly

- Retired the earlier Phase 2-based demo implementation instead of counting its storage checks as evidence for the successor.
- Implemented actual KurrentDB, XTDB, NATS ingress, Qdrant, LadybugDB and Temporal boundaries for the exercised slice.
- Kept raw evidence, claims, candidates, decisions and approvals distinct; did not label synthetic vectors or supplied verdicts as learned capability.
- Added selected-backend checks, exact-source lineage, host isolation, correction invalidation and basic restart checks.
- Preserved the real-model reuse constraint and recorded process seeds only in FloRA.

## Work still possible before the models arrive

| Order | Required work for the narrow experiment | Present gap | What can proceed now |
| --- | --- | --- | --- |
| 1 | Current source/formation integration | `formation_input.py` reduces every source to `historical_experience`; pinned schema lacks newer provenance fields and parent closure. | Bind the active MFM source, candidate-plane and formation-context interfaces to the selected stores. Preserve roles, speakers, subject, observed/recorded times, duplicates and parents. Never upgrade synthetic provenance into authenticated owner truth. |
| 2 | Proposal-to-authority transaction | `formation_gate.py` returns a pre-adjudication assessment; it does not commit a governed proposal. | Build independent authority/admission, conflict/correction, retry and lineage orchestration around the actual proposal contract. Qualification of learned proposal quality waits for MFM. Fictional-world authority must be explicitly scoped. |
| 3 | Governed personal development | Candidate and activation stores exist; episode lineage is rejected and rollback is absent. | Connect supported episode lineage, approved state revisions, correction/outcome interventions and rollback. A changed state may alter judgment without retraining personality weights after every event. |
| 4 | Recollection and context orchestration | Caller-supplied routes, synthetic vectors, one-hop evidence graph and count-based sufficiency. | Implement/reuse planner interfaces, current-source routing, budget enforcement, provenance closure, abstention and selected-plane adapters. Learned relevance and embedding quality still need qualified components. |
| 5 | Runnable and recoverable slice | Tests compose services manually; raw references/artifact declarations lack a durable application registry and qualified admission. Temporal restart recovery is untested. | Build host configuration, reference/lineage persistence, model-interface admission and an end-to-end runner that explicitly stops at missing models. Exercise rebuild/retry/restore and interrupted workflow recovery on selected services. |
| 6 | Evaluation infrastructure | Manifest validator and tiny public development fixture, but no serious comparator or paired runner, blind pack, scorer/report path or failure receipts. | Implement comparator, cohort generation/sealing, paired execution interfaces, blind assessment and failure-inclusive reports. Actual behavioral runs, numerical threshold calibration and final preregistration depend on pilot results. |
| 7 | Source-use and influence controls | Claim quarantine covers claim-linked readers; direct Experience-derived state/episodes remain outside a global source revocation plane. | Add revocation/influence lineage for the included experiment paths; test historical reads, derivative invalidation and recovery. This is separate from declaring complete consumer-v1 unlearning. |
| 8 | Builder preparation | Procedure seeds exist; builder construction/evaluation is absent. | Validate traces and prepare recipe, permission, artifact and transfer-case registries. Train/test the small FBM only after part one qualifies. |

Detailed sources, cross-repo drift and scope boundaries are in the [architecture audit](ARCHITECTURE_READINESS_AUDIT.md).

## Repairs during this audit

- Repaired the pilot transition so an explicitly bound before-phase decision can precede the correction/outcome. The exact source prefix is retained; undeclared, unrelated and future records are rejected. This remains a fixture-specific pilot path, not the missing general experiment runner.
- Used the actual decision-linked outcome contract for the outcome intervention, preserving synthetic provenance.
- Revised the development commute case to describe a trial after the before decision. The previous story reported an older host outcome and could not honestly be attributed to a newly recorded Fable decision. The revised case still does not establish advice-following or causal quality.
- Rejected future/expired/unknown claims on ordinary current-source/vector use. Historical valid-time reads honor present quarantine and recheck it after materialization. Direct raw-event revocation across all derivatives remains open.
- Repaired and validated required FBM procedure-seed metadata. This does not make them sufficient FBM training/evaluation cases.

These repairs address concrete defects. They do not complete the independent workflow rows above. Verification for the audit commit must be recorded separately from the earlier green build; the earlier selected-backend run [36612784548](https://github.com/NIne-WIngEd/FloRA/actions/runs/36612784548) passed at the starting SHA only.

Local verification passed 21 component test methods, including five source-use regressions, three seed-contract regressions and a Temporal local-server activity retry check. The Temporal server uses in-memory persistence, so this is not durable server-restart evidence. Seed shape validation and `git diff --check` also passed. The updated pilot regression must additionally pass on real KurrentDB in the audit commit's selected-backend CI.

### Follow-up after the audit

- [Selected-backend run 36619700275](https://github.com/NIne-WIngEd/FloRA/actions/runs/36619700275) passed at audit repair commit `96a6302c`. The audit's updated pilot sequencing and selected-backend restart probes are green.
- Work continued instead of declaring a model-only pause. The active pin is moving to MFM `4f287a48`, schema 1.2.0. The [registered formation slice](REGISTERED_FORMATION.md) persists source metadata/raw custody in XTDB, preserves actual Kurrent availability time, and reuses upstream routing, parent closure and input receipts. New backend qualification is pending; this is infrastructure integration, not learned formation.
- Persistent formation-use permissions, recoverable proposal candidates and the paired execution/report harness are being built in parallel. Admission, personal-state governance, qualified runtime artifacts and the other open rows still require follow-through.

## Actual stopping rule

Do not mark this workstream on break merely because the current component checks pass. First finish the included slice's independent wiring and evaluation infrastructure, with selected-stack failure/recovery evidence and explicit admission interfaces. The runner should reach a named missing-model boundary while preserving all earlier state and lineage.

Only then should we pause for qualified MFM formation and personality inference. Their real outputs are required for the behavioral result; successful part-one evidence is required before the learned builder transfer result. No claim of exhaustive completion is supported today.
