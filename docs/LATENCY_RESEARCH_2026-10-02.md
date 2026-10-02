# Latency research — 2026-10-02

The owner clarified that “competitor” means comparable infrastructure and
open implementations, including Graphify. Choosing a benchmark provider is
a separate experimental requirement. This record compares mechanisms with
FloRA's necessary Alice-aligned slice; it proposes no full memory, mission,
experience or model platform.

## Current measurement limit

Runtime/worker/profiler source:
[9b57ed3ce0d634409c967983bd5878ff74b48d3b](https://github.com/NIne-WIngEd/FloRA/commit/9b57ed3ce0d634409c967983bd5878ff74b48d3b).

- Worker **13** and profiler **21** controlled cases pass locally.
- [Native diagnostic 37065691146](https://github.com/NIne-WIngEd/FloRA/actions/runs/37065691146)
  capped at **180.013 s before the first owned reader**, with **zero owned
  entries**. It measured no shared-frame timing.
- [Ordinary CI 37065697026](https://github.com/NIne-WIngEd/FloRA/actions/runs/37065697026)
  remains pending at this research checkpoint.
- A separate all-call cProfile probe stopped incomplete after roughly twelve
  minutes. Its stack location is not a quantitative cause.

No latency improvement or physical/behavioral qualification follows from
these observations. Frame-cost attribution requires a measurement that reaches
the owned-reader slice. The prospective explicit `--workers-only` mode avoids
setup instrumentation so the diagnostic can reach that slice; source and tests
must confirm the mode before its results are used. Setup remains unobserved
and separately bounded by the unchanged 60-minute CI cap. A trace with zero
owned entries cannot establish a shared-frame bottleneck.

The earlier [native profile](NATIVE_BOUNDARY_PROFILE_WORK.md), source
0a690d0a557f5e719426e992c364bb2507c1e203, did observe repeated proof CPU:
898 history-metadata calls, 44.2029 s exclusive CPU, 4,128 Kurrent reads and
17,367 SQL executes. Inclusive spans overlap, qualification was false, and
that historical source does not measure the repaired frame.

## Primary implementation findings

| Comparable system | Pinned mechanism | Applicable hypothesis and limit |
| --- | --- | --- |
| Graphify | [cache.py](https://github.com/Graphify-Labs/graphify/blob/eaaec1abd99d3a7fb30301ccb49f4cc72ae34011/graphify/cache.py): file_hash, check_semantic_cache and save_semantic_cache reuse per-file extraction by source/content identity. AST cache binds extractor version/schema; semantic cache separates mode and supplied prompt. | Reuse exact derived data with its algorithm/configuration identity. Graphify's Markdown hash omits YAML frontmatter; Flora must preserve its own complete-byte/source-envelope hash contract. Cached extraction never grants current authority. |
| Zep / Graphiti | [search.py](https://github.com/getzep/graphiti/blob/4f62cfe7a2d519e55bfdf2dc4a2fd06649dc00b3/graphiti_core/search/search.py): search shares one supplied/computed question vector across enabled retrieval paths; edge_search/node_search deduplicate UUIDs before reranking and bound candidate count/BFS depth. | Share one compatible candidate/dependency representation within a boundary. Preserve separate nomination caps and purposes. Ranking/fusion does not prove H/C/source authority. |
| Mem0 | [memory/main.py](https://github.com/mem0ai/mem0/blob/0fbbb2f525dbaa30bd6ba13b3f7aad5e5b5b846a/mem0/memory/main.py): add/update reconciliation is separate from search of stored vectors/keywords; _create_memory/_update_memory accept precomputed embeddings. | Consider exact-generation derived index maintenance separately from query preparation. text_changed does not itself guarantee that an unchanged-text update avoids embedding. Inferred facts are not Flora's accepted claims or ledger authority. |
| Letta | [SleeptimeMultiAgentV4](https://github.com/letta-ai/letta/blob/67013ef1bb491ec8bdd629bfbeceb70227936afa/letta/groups/sleeptime_multi_agent_v4.py): foreground step completes before frequency/watermark-controlled participant work is scheduled; _issue_background_task registers a run then starts its step with safe_create_task. | Eligible derived maintenance can leave a response's critical path when its contract permits. Task registration is still awaited. Current withdrawal/head checks and the terminal physical fence cannot be deferred. |
| Authzed / SpiceDB | [caching.go](https://github.com/authzed/spicedb/blob/8422483147151728d39c47b439b5ed8090966d48/internal/dispatch/caching/caching.go), v1.56.0: plan-check keys include revision, canonical plan, resource, subject and caveat context; cached checks respect required recursion depth. [singleflight.go](https://github.com/authzed/spicedb/blob/8422483147151728d39c47b439b5ed8090966d48/internal/dispatch/singleflight/singleflight.go) coalesces identical concurrent dispatches with context-aware cancellation. | Separate stable dependency/algorithm work from live evaluation and bind every reuse input. Its cached positive decisions do not satisfy Flora's stricter no-carried-positive-grant contract. Arbitrary effectful callbacks cannot be coalesced. |

Additional primary pointers:

- [Graphify architecture](https://github.com/Graphify-Labs/graphify/blob/eaaec1abd99d3a7fb30301ccb49f4cc72ae34011/ARCHITECTURE.md)
  explains extraction/cache/navigation boundaries.
- [Graphiti semaphore_gather](https://github.com/getzep/graphiti/blob/b59d4ba01118a91708fd6a6892200016168eeb5d/graphiti_core/helpers.py)
  bounds independent coroutines; [search recipes](https://github.com/getzep/graphiti/blob/3c427640abf909f12f71f963fce15eb514a3c493/graphiti_core/search/search_config_recipes.py)
  offer node-only/combined RRF, MMR and cross-encoder paths. These are separate
  source pins, not one tested Flora configuration.
- [SpiceDB v1.56.0 release](https://github.com/authzed/spicedb/releases/tag/v1.56.0)
  distinguishes compiled caveats cached by schema version from live check work.
- [Google Zanzibar](https://www.usenix.org/system/files/atc19-pang.pdf), §2.2,
  supplies a causal snapshot lower bound for ACL/content ordering. Such a token
  does not prove observation of a withdrawal during Flora's final callback.

## Where these hypotheses meet Flora

If an owned-reader profile later shows repeated pure dependency/proof work
inside one issued boundary, investigate sharing that exact native material.
Retain origin/reader/code/cap checks, actual independent guards, H manifest
reobservation, physical-target reobservation and the terminal joint XTDB
sample. The relevant current paths are
[frame.finish](https://github.com/NIne-WIngEd/FloRA/blob/9b57ed3ce0d634409c967983bd5878ff74b48d3b/src/flora/selected/selected_authority_frame.py#L550),
[H evaluation/member checks](https://github.com/NIne-WIngEd/FloRA/blob/9b57ed3ce0d634409c967983bd5878ff74b48d3b/src/flora/selected/selected_history_contribution.py#L287)
and [initial_barrier](https://github.com/NIne-WIngEd/FloRA/blob/9b57ed3ce0d634409c967983bd5878ff74b48d3b/src/flora/selected/context_guard.py#L888).
Actual private assembly and opaque guards retain their original semantics.

A separate comparator hypothesis concerns
[prepare](https://github.com/NIne-WIngEd/FloRA/blob/9b57ed3ce0d634409c967983bd5878ff74b48d3b/src/flora/selected/comparator_memory.py#L256):
it embeds every source window plus the question and upserts all windows
each time. An exact-original/window digest, qualified embedding
artifact/configuration and history-generation binding could support derived
representation reuse. Keep case/phase/arm namespace isolation and fresh
authority checks. Cold construction and warm-query costs must be registered
prospectively under the existing common-budget policy.

Connection reuse is a hypothesis requiring opener/lease/wait/retirement
measurements. [native_reads.py](https://github.com/NIne-WIngEd/FloRA/blob/9b57ed3ce0d634409c967983bd5878ff74b48d3b/src/flora/selected/native_reads.py#L167)
already opens one owned SQL connection for a complete native read action,
rather than each SQL statement. KurrentExperienceLog retains the supplied
client, whose official 1.3.3 implementation retains its gRPC channel.

[Psycopg's pool guide](https://www.psycopg.org/psycopg3/docs/advanced/pool.html)
describes setup reuse and lease/reset behavior. [XTDB's transaction docs](https://docs.xtdb.com/about/txs-in-xtdb.html)
distinguish connection visibility and fixed transaction snapshots. Current
docs include APIs newer than pinned XTDB 2.1.0; they are not a drop-in API
specification. A snapshot begun before a callback cannot replace the fresh
withdrawal fence.

## Alice alignment and Graphify freshness

Alice main
[8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/8ea804aa25c3d1c5f46e9be5810d072ed0fadb4b/docs/MEMORY_PERFORMANCE_AND_RELIABILITY_STANDARD.md),
§§4–6, prefers materialized current claims, batch hydration, bounded plans,
generation-aware indexes and freshness checks. It preserves contradiction,
deletion and authority information. These contracts support the patterns
above without transferring Alice's full product scope into Flora.

The recovered Graphify navigation branch is
research/graphify-v1-model-routes-20260930 at
39666dba43aa39d6321933b4952e62f60ed70621; its substrate branch is
a06f61eafd91d04fb7ec7c1de3ab8a9ed7071b15.

- [SOL_RETRIEVAL_PROTOCOL.md](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/39666dba43aa39d6321933b4952e62f60ed70621/research/graphify-context/SOL_RETRIEVAL_PROTOCOL.md)
  makes graphs/catalogs navigation-only; consequential conclusions require
  fresh, original source pointers.
- [LAST_GRAPH_BUILD.json](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/39666dba43aa39d6321933b4952e62f60ed70621/research/graphify-context/LAST_GRAPH_BUILD.json)
  records code-only Graphify0.9.63 at foundation source
  f357a767ca1542a4043944b380663f27b50c33ec. Recovered foundation head is
  a19f8e8893422702c138182f239064385addf91c, so that graph is stale for its target.
  It does not establish current main semantics.
- Static catalogs reference alice-eipm-v1-build at
  021c5021a98104b35f9c8e94b19e48d21f25f132 and retain explicit experiment-frontier
  continuity staleness. They were used as historical routing hints followed
  by original reads. No Graphify MCP query tool, live graph freshness claim,
  rebuild or workflow dispatch was used.

## Frontier research and method

The recent window was 2025-10-02 through 2026-10-02.
[All-Mem](https://arxiv.org/html/2603.19595v1) bounds the visible retrieval
surface and typed traversal; [MAGMA](https://aclanthology.org/2026.acl-long.1709/)
selects complementary retrieval views; [AgentZeroMemory](https://arxiv.org/abs/2608.29606)
uses intent gating and progressive source expansion.
[Jev-Mem](https://arxiv.org/abs/2609.23986) explores cheaper frequent memory
control, while [MemCalib](https://arxiv.org/abs/2609.24259) separates overuse
and underuse through counterfactual memory-influence evaluation. Alice's
[calibration branch](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/576e9536555f350da83a7a0f8ae52b75a0ba47ac/docs/MEMORY_USE_CALIBRATION_AND_CONTROL_QUALIFICATION.md)
treats these as research challengers, not mandated algorithms. Their QA
results do not establish Flora's personal-judgment, authority or latency claims.

The Search skill/connected Exa discovery reviewed **55 candidate search
hits** across seven topics. Selected primary papers, official implementations
and documentation were fetched; official GitHub API responses resolved the
implementation commit pins. This count describes discovery scope, not
55 complete paper reviews.

This record changes documentation only. It borrows no reported speedup,
changes no runtime/budget, and proposes no model training or additional platform.


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

