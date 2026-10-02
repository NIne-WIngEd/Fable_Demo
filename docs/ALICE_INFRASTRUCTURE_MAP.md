# Alice infrastructure map for the FloRA prototype

- Date: 2026-10-02
- Status: source-grounded context preservation; not a new product requirement
- Alice source: `NIne-WIngEd/A.L.I.C.E@8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b`
- Fable source: `NIne-WIngEd/Fable_Sleight@1805a01c73575378246cac8cbbb72cd891e8528e`

## Scope and authority

The owner's 2026-10-02 clarification controls FloRA's scope: **FloRA is a narrow prototype testing a claim about Alice/Fable, not the implementation of Alice's complete memory, experience, mission, or personal-development infrastructure.** Whatever infrastructure the experiment actually needs must remain aligned with Alice. Alignment does not require building every destination plane.

This map preserves how the full architecture works so a small experimental slice can keep the right boundaries. It does not import Fable's full-product release gate into FloRA, require every backend on every turn, activate additional services, or qualify existing implementation. Earlier FloRA documents describing a mandatory full-scale build must be interpreted under the owner's scope correction.

FloRA's experimental question is recorded in [EXPERIMENT_GOAL.md](EXPERIMENT_GOAL.md): a correction or outcome should change relevant later native personal judgment for the right reason, leave unrelated judgments stable, and be compared with a competent general-model-plus-memory baseline. Builder transfer is a separate evidence requirement. Storage, schema tests, fluent answers, and synthetic mechanism results do not establish the whole behavioral claim.

The local Alice checkout inspected during recovery was stale at `285f398c`; current source verification used the pinned GitHub revision above. No `AGENTS.md` was present in the inspected Alice checkout or canonical main tree. Read pinned original sources before treating older context notes as current architecture.

## Pinned source register

| ID | Source and relevant location | Role |
| --- | --- | --- |
| A1 | [ALICE_PHASE2_REPLACEMENT_AND_FABLE_V1_EXECUTION_PLAN_2026-09-27.md](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b/docs/ALICE_PHASE2_REPLACEMENT_AND_FABLE_V1_EXECUTION_PLAN_2026-09-27.md), version 2.0.0; MFM-1 through MFM-6, D1 through D20, F1 through F4, Lane G | Owner-directed full-product execution map; supersedes the same-day lighter Fable/PostgreSQL simplification |
| A2 | [MEMORY_IDENTITY_FORMATION_AND_HOST_LEARNING_ARCHITECTURE.md](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b/docs/MEMORY_IDENTITY_FORMATION_AND_HOST_LEARNING_ARCHITECTURE.md), version 2.3.0; sections 2.1, 4.3, 6-9 | Subject separation, formation, Gate, projections, and current selected engines |
| A3 | [FABLE_PERSONAL_DEVELOPMENT_ARCHITECTURE.md](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b/docs/FABLE_PERSONAL_DEVELOPMENT_ARCHITECTURE.md), required causal loop, native judgment integration, first-release conversation boundary | Personal state must causally affect judgment; downstream generators remain replaceable |
| A4 | [MEMORY_ARCHITECTURE_V4.md](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b/docs/MEMORY_ARCHITECTURE_V4.md), architecture v4.1; sections 3-5 | Evidence/Claim authority, current state, projections and cross-backend consistency |
| A5 | [MEMORY_RECORD_AND_PROVENANCE_STANDARD.md](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b/docs/MEMORY_RECORD_AND_PROVENANCE_STANDARD.md) | Record roles, identities, evidence relations, source lineage, versions, deletion and rollback |
| A6 | [MEMORY_PERFORMANCE_AND_RELIABILITY_STANDARD.md](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b/docs/MEMORY_PERFORMANCE_AND_RELIABILITY_STANDARD.md), sections 4-7 | Materialized current state, batch hydration, bounded plans, generation-aware indexes, asynchronous expensive work |
| A7 | [STORAGE_LIFECYCLE_AND_RETENTION_POLICY.md](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b/docs/STORAGE_LIFECYCLE_AND_RETENTION_POLICY.md), sections 3, 6-8 | Compact ledger, bounded raw capture, selective retention, scoped deduplication, deletion blockers |
| A8 | [STAGE_G_MEMORY_FABRIC_CANDIDATE_QUALIFICATION_MATRIX.md](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b/docs/STAGE_G_MEMORY_FABRIC_CANDIDATE_QUALIFICATION_MATRIX.md), sections 4-6 | Cross-plane loop, evidence-consumption lock, consolidation stability, retrieval influence and identity separation |
| A9 | [PHASE_5_MISSION_GRAPH_CONTRACTS.md](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b/docs/PHASE_5_MISSION_GRAPH_CONTRACTS.md) and [FRIDAY_COGNITIVE_WORKSPACE_AND_PRODUCTION_GOVERNANCE_PLAN.md](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b/docs/FRIDAY_COGNITIVE_WORKSPACE_AND_PRODUCTION_GOVERNANCE_PLAN.md) | Mission identity, routing, Result Capsules, Traceback Chains, workspace as projection |
| A10 | [experience.py](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b/src/cognitive_kernel/experience.py), [mission.py](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b/src/cognitive_kernel/mission.py), [results.py](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b/src/cognitive_kernel/results.py), [memory_contracts.py](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b/src/cognitive_kernel/memory_contracts.py) | Exact neutral contract names and implemented validation rules; contract existence is not full runtime completion |
| F1 | [comic/STORYBOARD.md](https://github.com/NIne-WIngEd/Fable_Sleight/blob/1805a01c73575378246cac8cbbb72cd891e8528e/comic/STORYBOARD.md), The Second Mind, pages 18, 20, 25-26, 31-40, 42, 46-47, 51, 54-55, 60-61 | Behavioral destination and the meaning of one continuing entity |
| F2 | [docs/FIRST_RELEASE.md](https://github.com/NIne-WIngEd/Fable_Sleight/blob/1805a01c73575378246cac8cbbb72cd891e8528e/docs/FIRST_RELEASE.md) and [FABLE_V1_EXECUTION_PROFILE_2026-09-27.md](https://github.com/NIne-WIngEd/Fable_Sleight/blob/1805a01c73575378246cac8cbbb72cd891e8528e/docs/FABLE_V1_EXECUTION_PROFILE_2026-09-27.md) | Full Fable product target and conversation/privacy boundary; physical-stack sync discrepancy described below |
| G1 | [research/graphify-context/SOL_RETRIEVAL_PROTOCOL.md](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/39666dba43aa39d6321933b4952e62f60ed70621/research/graphify-context/SOL_RETRIEVAL_PROTOCOL.md) | Freshness-gated developer navigation; explicitly outside trusted runtime authority |

## One entity through linked evidence and state

The full Alice/Fable loop is:

```text
authorized original evidence / observation
  -> source-bound Experience event
  -> Formation Context Planner + MFM semantic proposal
  -> deterministic Memory Gate / Authority Manager
  -> adjudicated Claim versions and current state
  -> versioned episode / graph / vector / personal / mission projections
  -> selective retrieval and evidence reconciliation
  -> native personal judgment and expression contract
  -> controlled feature generation or authorized action
  -> observed outcome / correction
  -> Experience + governed relevant state revision
  -> changed future judgment where the revision matters
```

Shared scoped identities, evidence relations, generations and outcome links connect the stages. They are not separate assistants, independent truth stores or a requirement to execute every plane synchronously. A projection, workflow or graph link cannot silently promote itself into Claim authority. One canonical component owns each authority type at a declared generation; secondary representations have declared roles and rebuild paths. [A1-A5, A8]

### Original evidence and Experience

Original objects retain exact wording or media, source, custody, permissions and integrity bindings. A learned interpretation is never a replacement for the original. Exact-source reconstruction is different from a generated summary.

The Experience Fabric records observations, supplied material, decisions, model/tool invocations, actions, measurements, outcomes, corrections and processing events. `ExperienceEvent` binds `ProductHostScope`, `content_digest`, provenance, time, `parent_event_ids`, `outcome_reference_ids`, retention, tier, deletion lineage and optional opaque payload reference. Its metadata envelope does not itself contain raw payload bytes.

Event contracts preserve append identity and committed ordering, expected revision/concurrency semantics, idempotency, replay/checkpoint positions, correction/deletion links and integrity. Wall-clock timestamps alone do not define committed ordering. Reusing an idempotency key with different request material is a conflict.

Append-only means ordinary corrections add records and links; it does not prohibit owner-authorized privacy deletion or key destruction. Retained tombstones must not preserve deleted descriptive content against the deletion request. Byte deduplication within an authorized host/key domain must retain distinct logical records, provenance, permissions, retention and influence links. [A4, A5, A7, A10]

### Formation and authority

The `MemoryProposalBundle` is semantic output. It may propose subjects, facts, preferences, relationships, episodes, goals, temporal changes, uncertainty, contradictions, corrections, deletion/revocation and personal-state updates. It cannot authorize itself or choose a physical database as truth authority.

The deterministic Memory Gate applies source/provenance, privacy, temporal, conflict, retention, owner and product/host rules. It records accept, reject, quarantine or review decisions and their lineage.

Accepted knowledge has Claim identity and versions, valid/effective time, transaction/system time, evidence support, source hierarchy, confidence/uncertainty, conflict, supersession, correction, deletion and authority generation. Current adjudicated knowledge is materialized for serving. Historical reconstruction is explicit, rather than ordinary full-history replay on every request. [A1 MFM-3 and D3, A2 sections 6-8, A4, A5]

### Projections and recollection

Episodes are learned, versioned and rebuildable representations of events, participants, uncertain boundaries, narrative, goals, outcomes and context. Dynamic overlapping scenes/domains can include a project, relationship, mission, role, place or period; no fixed authored taxonomy defines a person's life.

Orthogonal graph views share evidence identities but preserve different edge semantics: entity, semantic, temporal, causal, provenance, relationship, mission/dependency, skill, identity, world, model/data and decision/outcome. Graph scores, spreading activation, decay, centrality and similarity describe retrieval accessibility, not factual authority. Vector keys and personal-model state are likewise distinct from source truth.

Recollection selects applicable Claim, exact/source-native, episode, graph, vector/multimodal, procedural, personal, mission or live-source paths. It deduplicates and reconciles against authority/provenance, reranks, records evidence consumed, checks sufficiency and expands, asks or defers when needed. There is no universal vector-first or semantic-fallback hierarchy. Context plan records should distinguish offered, selected, rejected, truncated and deferred material.

The evidence-consumption lock matters even in a small prototype: final factual support must resolve to source/authoritative evidence actually consumed by the producing invocation. An unopened reference, summary, retrieval score or graph-reachable object is insufficient. Procedural lessons guide actions/retrieval; they do not prove current-world facts. Reordering consolidation must not silently create different authoritative truth. [A1 D4-D14, A6, A8 sections 6.1-6.5]

### Judgment, expression and outcomes

Versioned personal state enters native judgment before downstream generation. Its versioned verdict expresses stance, evidence, reasons, uncertainty, perspective, relationship context and expression obligations. A bare agree/disagree label cannot demonstrate the full destination capability.

A replaceable feature model may generate language or other feature output through the authorized egress boundary. Local comparison checks factual bounds, stance, reasoning, disagreement intent, voice and relationship behavior. The intended ordinary conversation path succeeds on the first generation attempt; corrections are targeted and bounded. An API's apparent personal behavior is not proof that native state caused it. Privacy placeholders are local mappings, not a guarantee that an API cannot infer personal meaning.

The decision, selected output/action, relevant evidence, correction and later outcome return to Experience. New authorized evidence can revise relevant host, relationship, self or procedural state. Behavioral interventions should hold the task/evidence constant where appropriate and change only the tested state. Irrelevant changes should not disturb unrelated judgments, and provider replacement should preserve the attributable personal mechanism. [A3, F2]

## Mission, Result Capsule and Traceback connections

Alice's Mission Graph is durable goal/task/decision structure; conversations and frontend views are interfaces to it. It preserves unfinished work and dependencies across separate interactions. FloRA need not implement a complete Mission Graph to test its narrow claim. If an experimental decision needs goal/context identifiers, retain those links without treating the whole destination as a prerequisite. [A1 F1-F2, A9]

Exact neutral contracts in `mission.py` and `results.py` are:

| Contract | Meaning and important boundaries |
| --- | --- |
| `Mission` | Stable scoped mission identity, provenance, lifecycle and deletion links |
| `MissionNode` | Stable node identity with successor state records; status, execution state and visibility are separate; valid successors preserve immutable identity/scope/type/creation fields |
| `MissionEdge` | Typed relationships: `parent_child`, `depends_on`, `blocks`, `related`, `derived_from`, `supersedes`, `result_for`; edge lifecycle remains explicit |
| `MissionGraphSnapshot` | Immutable revision; its parent-child hierarchy is rooted, connected, single-parent and acyclic, while other typed edges retain their own semantics |
| `RoutingDecision` | Exact actions in [routing.py](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b/src/cognitive_kernel/routing.py): `continue_current`, `create_child`, `create_sibling`, `reattach`, `create_mission`, `control_command`; routed turns are not automatically new missions |
| `ResultCapsule` | Binds `mission_id`, `node_id`, result status, output references, evidence references and `source_event_ids`; requires lineage and requires output references for `succeeded` |
| `TracebackTransition` | Exact actions: `propagate_to_parent`, `reopen_node`, `create_followup`, `mark_blocker`, `resolve_conflict`, `stop_at_mission_root` |
| `TracebackChain` | Scope-bound, linked, ordered contiguous transitions with no cycle; stop-at-root must be final |

Result Capsules point to the Experience/evidence that explains a result. Traceback applies the consequence to the mission structure. A reopening or followup creates explicit successor state rather than erasing the earlier completed/failed state. Those decisions, actions and outcomes also enter Experience, where formation can derive claims, lessons and personal updates. Workspace attention/current plans are inspectable projections over this state, not an independent canonical ledger. [A9, A10]

The comic's concrete example is mixed outcome learning: a project succeeds while a deadline is missed. Alice preserves the original goal, evidence, warning, owner override, outcome and failed assumptions. Later recall selects the workload lesson and the project's value, leaving other history in the background. Missions survive conversations; plans change with new evidence; model changes preserve continuity; improvements remain challengers until evaluated. [F1 pages 31-40, 42, 46-47, 54]

## Distinct personal subjects

Alice has three personal subjects plus relationship state:

- **Mehejabin Elaina:** source-person history and identity foundation.
- **Rayan:** owner/host with changing goals, preferences, beliefs and behavior.
- **A.L.I.C.E.:** current assistant-self and post-activation experiences, judgments and continuity.
- **A.L.I.C.E.-Rayan relationship:** shared history, expectations, coordination, trust and interaction norms belonging to neither subject alone.

Ordinary Rayan interaction may revise host/relationship/Alice-self state; it cannot silently rewrite Elaina history or her core source-person anchor. A newly supplied genuine Elaina correction is explicitly a source-person update. Protecting that anchor must not freeze Alice's developing self.

A general Fable uses its own host and `assistant_self`; it does not invent an Elaina axis or receive Alice's private corpus/weights. User statements are evidence, not automatically canonical truth about an ideal self. Synthetic practice can shape behavior while remaining invented training material, never lived history. FloRA's isolated fictional hosts and externally supplied model artifacts must preserve the corresponding subject and truth-role distinctions. [A2, A3, F1 pages 18, 20, 55, 60-61]

## Selective fast/slow processing and latency

Alice already specifies selective work. A Formation Context Planner can choose zero, one or many planes; no backend is mandatory for every event. Simple events should not invoke every memory backend. [A1 MFM-1, A2 section 7]

| Path | Work |
| --- | --- |
| Fast foreground path | Authorized Experience append, source authentication/binding, basic segmentation, safe exact/retrieval keys, temporal backbone, privacy/safety metadata; current selected state and relevant exact evidence for the decision |
| Slow path when needed | Reflection/consolidation, Claim and graph proposals, episode narratives, personal-state/procedural updates, importance/retention and training candidates; asynchronous where appropriate, still behind authority |

Ordinary serving prefers materialized current state, batch hydration, bounded explainable plans, generation-aware indexes and selected parallel retrieval. Expensive replay, full verification, archive restoration, deep consolidation and training may run asynchronously or concurrently. Freshness/current permission checks remain meaningful: deferring consolidation does not permit knowingly obsolete facts to influence the next relevant decision. [A1 MFM-5, A6 sections 4-7]

Read [LATENCY_ARCHITECTURE_RECALIBRATION_2026-10-01.md](LATENCY_ARCHITECTURE_RECALIBRATION_2026-10-01.md) for FloRA's prior repeated-history diagnosis. Its measurements concern experimental custody/recovery machinery and do not establish companion latency or behavioral advantage. The owner's 2026-10-02 clarification adds a scope boundary to that audit: optimize and implement the necessary prototype slice, rather than using a latency audit as a reason to finish the full destination fabric.

## Selected full-product physical engines

These choices describe current Alice upstream architecture. They constrain the corresponding FloRA surface **when that surface is actually required**, but they are not a requirement to instantiate every service. Preserve existing evidence and adapters; do not introduce a random replacement or claim an unsupported cutover. [A1 D1-D20, A2 section 9]

| Logical role | Current Alice choice | FloRA interpretation |
| --- | --- | --- |
| Exact raw originals | Encrypted content-addressed objects behind an S3-compatible abstraction | Keep exact evidence and custody for the slice; no full archive platform prerequisite |
| Canonical Experience | KurrentDB behind project-owned `EvidenceLog`/event contracts | Preserve scoped ordered events, decisions, corrections and outcomes where the prototype uses durable experience |
| Edge/federation transport | NATS JetStream | Needed for an exercised ingress/device route, not every local decision |
| Claim Authority | XTDB v2 | Preserve current accepted state, versions, valid/system time and correction lineage for implemented authority |
| Local cognitive graph | LadybugDB | Use when a graph route contributes to the tested mechanism; not mandatory for every query |
| Scale-out graph | NebulaGraph; Neo4j retained as reference | Full-product placement/reference context; no prototype cluster requirement |
| Vector/multimodal retrieval | Qdrant Edge/server/cluster | Use when semantic/perceptual discovery is needed by the experiment or comparator |
| Durable workflows | Temporal | Use for an exercised durable operation; no complete mission/consolidation workflow program prerequisite |
| Ephemeral workspace/cache | Process-local L1 and Valkey | Caches hold no unique authority; no shared-cache deployment prerequisite |
| Lineage registry | Content-addressed signed/hashed model/data artifacts | Retain exact artifact/version/source evidence needed to reproduce and attribute results |

Logical contracts are owned by Alice/Fable, not by the vendor. An engine's event, graph or vector feature does not determine truth roles. SQLite and old Phase 2/M2 implementations remain compatibility sources/test oracles; their historical physical topology does not override current selections. Conversely, Alice's selected full-product engines do not enlarge FloRA's experiment scope.

### Known downstream documentation discrepancy

At the pinned Fable revision, `FABLE_V1_EXECUTION_PROFILE_2026-09-27.md` still selects NATS as canonical Experience and JanusGraph for scale-out graph. Current Alice execution map and identity architecture select **KurrentDB canonical Experience, NATS ingress/federation, and NebulaGraph scale-out**. Alice's [FULL_PERSONAL_MEMORY_ARCHITECTURE_SYNTHESIS_2026-09-27.md](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b/docs/research/FULL_PERSONAL_MEMORY_ARCHITECTURE_SYNTHESIS_2026-09-27.md) also contains leftover JanusGraph bullets/sources within its NebulaGraph discussion.

Preserve this as a source-sync discrepancy. For upstream physical selection use A1 and A2; do not merge the conflicting lists into a new architecture. The semantic loop and narrow FloRA scope are not changed by the stale physical list.

## Graphify is developer navigation

Alice's Graphify research protocol explicitly declares `authority = navigation-only` and places the research branch outside trusted runtime. Its initial graph describes code topology, not complete architectural rationale or personal history. [G1]

Use a current build receipt tied to the relevant work ref; a stale graph is not a substitute for source verification. Query exact identifiers/typed neighborhoods, follow original source pointers, check branch/date/supersession, and record retrieval misses. Extracted links are navigation hints; inferred links are hypotheses; generated reports provide orientation. Neither is accepted personal knowledge. Graphify can help rebuild development context without becoming FloRA's memory authority or an additional per-turn dependency.

## Minimum FloRA slice versus full Alice/Fable destination

For the tested slice, retain the following semantics where applicable:

1. Isolated host/product subjects and exact evidence/source bindings.
2. Direct, inferred, synthetic, unknown and lived-experience distinctions.
3. Proposal versus deterministic authority separation.
4. Versioned current personal/Claim state, relevant corrections/outcomes and explicit lineage.
5. Selective evidence delivery and consumed-source attribution.
6. Native judgment attributable to the qualified personal mechanism before feature expression.
7. Corrections/deletion/freshness across derivatives actually implemented.
8. Relevant-change and irrelevant-change controls, competent comparator, held-out evaluation and truthful latency/qualification claims.
9. Exact model/data/config/implementation versions and reproducible builder method traces without cross-host private transfer.

A full Mission Graph, all episode/graph/vector/perceptual planes, multi-device federation, broad lifecycle curation, full model-evolution machinery, complete deletion/unlearning coordination and all full-product services are **not prerequisites merely because they appear in Alice's plan**. Add a surface only when the experiment's mechanism, evidence or an exercised reliability requirement needs it. Model work remains with the personality and MFM workstreams; infrastructure receipts cannot substitute for qualified model behavior.

Document the supported slice, omitted capabilities and limits. Full Alice/Fable requires the integrated destination architecture and its release gates; FloRA requires a credible, source-aligned experiment. This map preserves that distinction for later chats and builder learning.
