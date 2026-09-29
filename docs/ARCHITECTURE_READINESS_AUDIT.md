# FloRA architecture and dependency audit

**Reviewed:** 2026-09-29. **Conclusion:** the selected-stack component work is useful, but the model-independent FloRA workflow is not complete. Waiting for personality and MFM weights is not yet the only remaining step.

This audit preserves [FloRA's frozen experiment goal](EXPERIMENT_GOAL.md). It does not create another personality model, MFM, judge, or smaller consumer Fable edition.

## Source versions

These are the fetched upstream revisions reviewed, rather than an assumption that a local checkout is current.

| Repository/lane | Exact revision | Relevant authority or interface |
| --- | --- | --- |
| A.L.I.C.E. main | `8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b` | `docs/ALICE_PHASE2_REPLACEMENT_AND_FABLE_V1_EXECUTION_PLAN_2026-09-27.md`; `docs/STAGE_G_MEMORY_FABRIC_CANDIDATE_QUALIFICATION_MATRIX.md`; `policies/stage_g_memory_fabric_candidate_qualification_policy.json`; identity and personal-development architecture; Friday roadmap |
| A.L.I.C.E. MFM | `4f287a488bc908bd04f99255ee01b794bacba50b` | `docs/MFM_FULL_CAPABILITY_BUILD_PLAN_2026-09-29.md`; `docs/MFM_LEARNING_ADMISSION_2026-09-29.md`; formation contracts, registered sources, context assembly and retrieval interfaces |
| A.L.I.C.E. FBM | `803477ba290030b3ed46459a90eb15529146fff2` | `docs/fable-builder/FBM_DATA_AND_SEED_PROGRAM_2026-09-26.md`; process trace schema and parallel capture contract |
| A.L.I.C.E. personality active repair lane | `5e29f7f69ba4a5d031c7036639b67bebbcdc0bd2` | `docs/eipm/EIPM_ROLE_AND_OBJECTIVE_CONTRACT_v1.0.md`; source-bound N0 work remains separate from FloRA |
| Fable Sleight main | `1805a01c73575378246cac8cbbb72cd891e8528e` | `README.md`; `docs/FIRST_RELEASE.md`; `docs/FABLE_V1_EXECUTION_PROFILE_2026-09-27.md` |
| FloRA audit baseline | `412f7bdff44ef4fc5690f7daab2be8390260885b` | Frozen goal, selected adapters, component/integration checks, source and state receipts |
| FloRA's existing A.L.I.C.E. contract pin | `00583fb25fbe07c1452519992de2bc8055dcebd5` | Reproducible older MFM schema `1.1.0`; not the current MFM integration target |

## What the experiment must establish

- A correction or observed outcome changes a later native personal judgment **when relevant**, with source-linked reasons.
- An irrelevant change leaves unrelated judgment stable.
- A capable general model with memory receives the same authorized history and comparable budget. Held-out comparison cannot depend on a deliberately weak baseline.
- An ablation receives the same selected evidence without the personal judgment update, so evidence selection and judgment updating can be distinguished.
- Only after the claim succeeds does the small FBM attempt to reproduce the qualified slice for another isolated host. Hand-written second-host state is not builder success.

Synthetic histories establish a mechanism result. Consenting real-host assessment is a separate evidence requirement for claims about helping people. Neither is a full Fable release or complete Stage G qualification.

## Cross-repository selection conflict

The live documents disagree on two physical selections.

| Plane | A.L.I.C.E. selected plan and owner-ratified Stage G policy | Fable Sleight execution profile |
| --- | --- | --- |
| Canonical Experience | KurrentDB; NATS JetStream is federation/edge ingress | NATS JetStream; KurrentDB is reference/challenger |
| Scale-out graph | NebulaGraph | JanusGraph |

The disagreement is present at the exact revisions above. It is not resolved by the common claim that adapters are replaceable.

The history also records it:

- A.L.I.C.E. `b78240eb715c6c8c0f4bb5a8ced8b3173916afeb` finalized event and scale-out graph choices on 2026-09-27.
- Fable Sleight `626f156997cc62aedea5a3112b81b957c2cc50e0` restored its full profile later that day while retaining NATS/JanusGraph.
- Fable Sleight `b1894a25e7cd65ddfb7cba58b45f7679b36bd2b7` subsequently bound the release predicate; it did not reconcile the engines.
- A.L.I.C.E. `b3fc5bb879db2305effee1197f405f93640f65aa` later synchronized Stage G's event table with its machine policy. Current policy remains `status=owner_ratified` with KurrentDB/NATS transport and NebulaGraph.

The owner's repeated instruction for this work is to derive FloRA from A.L.I.C.E.'s full successor build plan and to treat old Phase 2 as void for new FloRA implementation. That establishes the **FloRA path**: KurrentDB canonical, NATS ingress, XTDB, LadybugDB, Qdrant and Temporal. It does not silently repair Fable Sleight's public technical authority. Full cross-product alignment remains unconfirmed until the conflicting product document is explicitly reconciled.

No engine substitution or backend tournament is warranted by this documentation conflict. The existing FloRA stack should not be rewritten merely because the downstream table drifted.

## What the implemented components actually establish

FloRA has selected-engine append/replay, bitemporal claim persistence, encrypted raw objects, vector filtering, exact evidence graph projection, episode candidates, versioned personal-state candidates, signed owner actions, source-use quarantine, Temporal activity retry, context delivery receipts, outcome lineage and staged fictional ingestion.

Those are component boundaries. In particular:

- `formation_gate.py` explicitly performs **pre-adjudication only**; it never commits a Claim.
- `formation_input.py` supplies caller-selected replay events and represents every source as `historical_experience`. It does not preserve the newer registered speaker/subject/source/time/duplicate metadata or translate the original evidence roles into a complete MFM context.
- `context.py` executes a caller-authored `ContextPlan`. Exact IDs, a vector and one-hop evidence-graph sources are inputs to the function. There is no implemented adaptive recollection loop or episodic context route. `minimum_claims` is a declared count, not semantic sufficiency.
- `personal_state.py` and `outcome_revision.py` accept supplied candidate content and check lineage. They do not derive a learned revision or provide the complete activation/rollback policy.
- `decision_outcome.py` records supplied verdict bytes and an artifact hash. It does not execute or qualify native personality judgment.
- `evaluation_protocol.py` validates declared paired-run receipts. It does not implement the comparator, execute an experiment, or score a behavioral result.

The current adapter checks should remain labeled as such. A green backend run does not close these workflow gaps.

## Work that can proceed without personality or MFM weights

| Needed for the narrow FloRA claim | Current gap | Next implementation boundary |
| --- | --- | --- |
| Current MFM interface | CI imports older schema `1.1.0` | Bind an exact `1.2.0` source revision and verify compatibility. Preserve the old pin in historical receipts. |
| Registered formation intake | Raw references and modality declarations are supplied by callers; original roles and source metadata are incomplete | Adapt KurrentDB/encrypted objects to the new `FormationEvidenceStore`/registered-source interface. Bind actor, subject, source item, event/import time, duplicate family, parent closure and current permission. |
| Formation retrieval | No selected-stack adapter for the current generic MFM context/retrieval seams | Reuse upstream `formation_sources.py`, `formation_context_planner.py` and `formation_retrieval.py`; provide selected-plane adapters. Derived hits nominate source IDs; the independent source registry opens and authorizes bytes. |
| Proposal-to-authority path | Pre-adjudication assessment is disconnected from Claim acceptance | Persist the exact proposal/context/model lineage, independently adjudicate source, subject, permission, temporal scope, conflict and predecessor, then issue an idempotent XTDB commit and projection work receipt. Models cannot authorize their own writes. |
| Fictional-world authority | Synthetic provenance is retained in Experience, but there is no complete adjudication path for supported fictional-world claims | Define an experiment-scoped policy that keeps every source synthetic. It may admit supported claims inside that isolated fictional world; it must not relabel them as a real owner's history or authenticated testimony. |
| Governed state revision | Candidate registration and explicit approval exist; update orchestration and rollback remain incomplete | Route accepted source-linked proposals into host/relationship/self candidates, activate under an explicit policy, preserve previous versions and implement restore/rollback with current source restrictions reapplied. Meaning is supplied by the qualified models later. |
| Recollection and decision interface | Hand-authored retrieval routes and verdicts | Implement query/context orchestration, cross-plane reconciliation, episodic access where used, budget and sufficiency/defer interfaces, and an ACFP/IDP inference seam with exact model/state versions. Keep any reference policy visibly deterministic. |
| Artifact lineage | A supplied model hash is not a qualification registry | Register artifacts, source/config/evaluator hashes, qualification state and promotion/rollback references. Reject unknown or mismatched artifacts at inference/decision boundaries. |
| Selected-path recovery | Service restart probes and limited activity retry exist | Verify reconstruction of the narrow workflow's references/checkpoints, projection rebuild, stale-source rejection, interrupted operation retry and persisted Temporal recovery. Test the actual included path rather than isolated happy cases. |
| Experiment implementation | Tiny public pilot and manifest validation | Implement a competent baseline, three-arm before/after runner, failure/latency receipts and analysis. Prepare longitudinal distractors and independent source/generator splits; do not tune on final held-outs. |
| Builder capture | Procedure traces are being saved | Continue compact method/failure traces in FloRA only. Create separately linked eligible input-target-outcome cases only when independent authority and observed validation make them valid. |

These entries are a dependency map, not a claim that they have now been implemented. Reusable interfaces on the MFM branch should be integrated rather than rebuilt under different names.

## What legitimately waits for the separate models

- MFM's learned semantic interpretation, formation quality, uncertainty and episode/personal-state proposal content.
- Personality/EIPM's native interpretation, candidate comparison, values, stance, relationship-sensitive behavior and expression obligations.
- The causal assertion that revised personal state caused the later verdict. A supplied verdict or deterministic demonstration cannot substitute for it.
- Behavioral calibration, irrelevant-change stability, provider-swap identity behavior and the scored comparison after real model integration.
- The successful-claim prerequisite for training and qualifying the small builder's cross-host reproduction.

The personality model is the existing native judgment policy. FloRA must not add a disposable small judge or appoint an external feature model as identity authority. ACFP supplies situation, evidence and personal state; the personality model supplies the structured IDP. No single agree/disagree label can replace that policy.

## Narrow experiment versus full product

A.L.I.C.E.'s current Friday roadmap explicitly permits internal builds to exercise the capability under test. FloRA therefore does not need to build the entire Fable v1 installer, every modality, a NebulaGraph cluster, all mission tools or every multi-device feature before this narrow experiment.

The included components must preserve the selected successor semantics. Their scale, recovery and authority claims require matching selected-stack evidence. Missing full-product features must remain visible and cannot be marketed as a complete Fable release.

The stopping condition is concrete: **all infrastructure needed to execute the frozen narrow workflow is integrated and qualified, leaving only learned model outputs and their behavioral evaluation dependent on MFM/personality**. The audit baseline does not yet meet that condition.
