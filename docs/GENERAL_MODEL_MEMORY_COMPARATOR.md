# General-model-plus-memory comparator

The [FloRA goal](EXPERIMENT_GOAL.md) requires a serious memory-assisted general
model comparison. A weak prompt baseline would not answer it. This milestone
builds the comparison path and evidence boundaries; **it does not demonstrate a
competent real baseline or a FloRA win yet**.

The baseline consumes the same registered original history, common question and
frozen resource limits as the paired runner. It uses local source memory and an
externally supplied frontier client. It receives no native personality judgment,
MFM-produced personal state, assistant-self update or generated approval as extra
shared history. Original evidence and native internal state remain separate.

## Memory behavior

[comparator_memory.py](../src/flora/selected/comparator_memory.py) uses real
Qdrant behind the selected original-event/custody contracts. Its collection
namespace binds host authority, run, case, phase, history generation and the exact
comparator configuration. Before history is never indexed into an after namespace
or supplemented with after evidence.

- **Exact source windows:** overlapping UTF-8 text windows retain original event
  IDs, event hashes, byte offsets and content hashes. Full originals remain in
  encrypted custody. Returned excerpts are rechecked against their real bytes.
- **Hybrid retrieval:** local BM25 and dense Qdrant candidates are fused with a
  correction/outcome route. Semantic vectors must come from the separately
  supplied local embedding model with exact artifact/configuration/input bindings.
- **Correction and outcome context:** choosing an event also selects a window
  from every original ancestor, including linked prior observations or decisions.
  If that complete bundle cannot fit, it is not silently split. Chronology,
  provenance type and parent relationships accompany the excerpt. A correction
  is evidence for the general model to assess, not automatically authoritative
  truth.
- **Extractive memory:** the source windows provide a bounded extractive view;
  this slice does not invent an abstractive summary or a fake learned claim.
  `OriginalWindowContext` extends the existing `LocalContext` delivery shape with
  explicit raw-source routes. Its items are `comparator_original_window`, never
  accepted native claims or personal-state projections.
- **Bounded selection:** the frozen window count, window size/overlap, dense
  candidate count, fusion rule and minimum source count are part of comparator
  lineage. Exceeding the registered ingestion bound makes the attempt unavailable
  rather than discarding unknown history. Sufficiency by source count is a
  mechanical limit, not proof that the evidence answers the question.

This is a configurable retrieval implementation to qualify, not an automatic
claim that BM25 plus dense search is enough for every personal decision. Actual
embedding relevance, corpus coverage, conflict handling and held-out retrieval
quality remain measured pilot requirements.

Each preparation authenticates its held original bytes against encrypted
registered custody on entry. Subsequent guards around embedding and Qdrant
operations reconstruct that exact history manifest and resolve fresh source,
ancestor and evaluation grants through the terminal selected-row fence. They do
not reopen the same original ciphertext after every operation. A later
preparation authenticates again; an earlier grant is never a permission lease.

The physical run at `950fe8321902b681ae798f455779e281985d04a0` reached the
comparator but both supplied success attempts exceeded that fixture's frozen 10-second
response limit. In the same controlled two-original fixture, removing repeated
private authentication initially reduced preparation from 722 to 326 SQL calls and 28 to
4 original object opens. Those counts identify redundant work; they do not
qualify physical latency. The actual engine retry retains the same budget and
prints each comparator attempt's phase, status and elapsed milliseconds.
The call-local metadata sampler also batches the finite registered source DAG,
current purpose heads and immutable actions; its final current-row query and
actual control callbacks still run at each guard. Physical qualification remains
pending after those repairs.

## Configured frontier execution

[comparator.py](../src/flora/comparator.py) defines `GeneralMemoryArmAdapter` and
the externally supplied component ports.

| Required component | Binding/evidence |
| --- | --- |
| Provider deployment | Exact provider/endpoint, requested snapshot, returned-model allowlist and generation parameter bytes |
| Provider wire compiler | Frozen local serializer artifact; produces the actual outbound body from only the supplied input/configuration |
| Token counter | Independently qualified local tokenizer artifact/configuration; count binds actual complete request bytes |
| Embedding model | Independently qualified local model/configuration; vectors bind each real source window and query |
| Frontier client | Frozen transport artifact; honors cancellation and calls the live disclosure check immediately before dispatch |
| Exchange verifier | Independently enrolled first-party transport-observation key; signature binds request body, response bytes, output, actual usage, model and transfer permission marker |

There is no official GPT/Claude HTTP client, tokenizer, embedding model or model
training in these modules. Implementing an official client later requires current
primary-source API verification. Actual provider credentials and credential
headers are not part of the recorded body. The configured client must use
stateless requests and cannot add undisclosed history, files, memory or session
state. Its serializer, dispatch, response parsing, usage extraction and remote
identity checks need independent qualification.

`ArmBinding.model_artifact_sha256` for this remote baseline is the hash of the
external deployment descriptor; it is **not a hash of provider-owned weights**.
`lineage_sha256` binds the complete baseline configuration, including the system
instruction, memory settings and embedding/tokenizer/transport/compiler artifacts.
Requested and returned model identities are checked; a provider configuration
change invalidates the attempt.

The input budget covers the **actual full compiled body**, including the system
instruction, common question, source excerpts and provider envelope. Selection
counts that body while packing evidence; execution counts it again. The provider's
observed total input/output token values are retained and the actual total input
is also checked through the runner's context limit. Output tokens, feature-call
count and end-to-end time remain under the existing common limits. Cost stays
unavailable unless actually supplied by the trusted metering boundary.

The Ed25519 proof authenticates a first-party observation boundary. It is not an
official provider signature or independent proof of a provider's internal
computation. Hashes alone also do not prove that a real API call occurred.

## Local access does not authorize disclosure

`SelectedComparatorDisclosure` first reconstructs and verifies the registered
phase history and exact context windows. It then checks current
`comparison_external:<provider_id>` authority for the frozen question and every
selected source, including full parent closure. Local evaluation permission does
not imply that external grant.

The terminal metadata statement covers both independently required purposes.
A late external-permission callback cannot withdraw local evaluation permission
and still return a dispatch marker or authorize sealing the response context.
Provider capture and audit keep their separate purposes, so an already observed
failed call can remain recoverable after evaluation or external use is withdrawn.

The check runs before generation, in the supplied client's actual dispatch
callback, after generation and at recording. The signed response must bind the
marker produced by the dispatch callback. Revocation blocks new disclosure and
result acceptance; it cannot undo bytes a provider already processed. The provider
receives the authorized source meaning. This path claims no encryption scheme
that hides that meaning from the inference service.

The selected recorder rechecks producer/configuration, token count and exchange
proof, then registers the existing canonical context-delivery and decision
contracts. It stores the actual compiled request body, raw response, signature,
usage and authorization marker as a separate encrypted
`comparator_provider_exchange` artifact. Its parents include the exact decision
and frozen question. The generic baseline's API-written answer is labeled as that
baseline; it is not evidence of native personal judgment.

## Current evidence and next boundary

- Ten local regressions pass with fictional source histories, byte-count and
  embedding fixtures, supplied output bytes and a fictional transport signing
  key. They cover exact UTF-8 excerpts, ancestor closure, changed-source rejection,
  before/after namespace separation, whole-body accounting, signed exchange
  binding, transfer callback enforcement, revocation and frozen-arm checks.
- [The selected integration test](../tests/integration/test_selected_comparator_memory.py)
  is prepared for real KurrentDB, XTDB, Qdrant and encrypted objects. It exercises
  denied disclosure despite local grants, phase-isolated projection, canonical
  exchange/output custody, failure-inclusive run recovery and disclosure
  revocation. **Its CI result is pending.** Its supplied fixtures qualify mechanics
  only; there is no actual frontier call, real tokenizer/embedding quality or
  prediction in that test.
- Required production components remain externally supplied and unqualified
  here. Blocking backend/model work needs a cancellable worker deployment;
  synchronous Qdrant calls are not certified against the wall-time deadline by
  these local checks. No latency or scale result is claimed.
- Before final comparison: choose and qualify a serious provider/model and
  memory configuration, pilot source relevance and correction/outcome handling,
  freeze the actual cohort/rubrics/budgets/thresholds, verify comparable feature
  and disclosure access across arms, then run held-out evidence. No tuning on the
  final held-out decisions and no numerical threshold is invented here.
- Stage G's source-consumption and privacy requirements continue to apply.
  Stage H/I/J authority/cutover status and Phase 2 retirement are not implied by
  a comparator or storage test. This implementation follows FloRA's owner-selected
  successor path, not the obsolete Phase 2 runtime.

Primary project references reviewed: A.L.I.C.E.'s first-release
`FRIDAY_PRIVACY_AND_TRUST_MODEL.md`, `FABLE_PERSONAL_DEVELOPMENT_ARCHITECTURE.md`,
Stage G qualification matrix and Stage H/I/J execution plan. The API boundary
preserves their explicit authorized disclosure, native judgment and source
authority separation; the general-memory arm intentionally tests what a generic
model can do with competent source access without FloRA's learned personal update.
