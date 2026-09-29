# Optional comparator provider adapters

This milestone supplies optional implementations for the [general-model-plus-memory
comparator](GENERAL_MODEL_MEMORY_COMPARATOR.md). It builds no personality, MFM,
judgment model or replacement feature model. No live API request, credential
lookup, weight download or real model prediction was performed for this milestone.

## What the adapters do

| Adapter | Actual boundary | Still supplied or qualified separately |
| --- | --- | --- |
| `OpenAIResponsesWireCompiler` | Emits the exact stateless text request body, including the system instruction, common question, extractive source context and output limit | Exact approved deployment, response-model allowlist and generation settings |
| `OpenAIResponsesAsyncClient` | Dispatches that body asynchronously to the fixed official Responses endpoint; parses actual returned model, text and usage; signs their binding to request and raw response | Explicit credential callable, independently enrolled observation key, current disclosure authority and private attempt sink |
| `SuppliedBodyTokenizer` | Loads an explicitly supplied `tokenizer.json`; counts the actual UTF-8 request body without truncation or a characters-per-token estimate | Exact artifact, package version and suitability as a local preflight tokenizer |
| `SuppliedONNXSentenceEmbeddings` | Loads an explicitly supplied inline ONNX export and tokenizer; returns that graph's finite sentence vectors | Existing embedding weights/export, input/output semantics, rights, package versions, retrieval quality and bounded worker deployment |

The OpenAI client implements the existing `ExternallySuppliedFrontierClient`
port. Its successful observations can be verified with the existing
`Ed25519TransportObservationVerifier`. The tokenizer and embedding adapters
implement the existing local comparator ports; they are not additional FloRA
memory models. Their artifact manifest binds file bytes, adapter source,
configuration bytes and the declared runtime package versions. An artifact hash
or package version does not establish the model's quality or training provenance.

## Frozen request and disclosure boundary

The endpoint is exactly `https://api.openai.com/v1/responses`. Redirects,
environment proxy configuration and automatic retries are disabled; TLS
verification remains enabled. Credentials come only from the explicit callable.
They are headers, never part of stored request bodies or signed metadata.

The wire schema is text only: `store=false`, `stream=false`, `background=false`,
`truncation="disabled"`, no tools and no parallel tool calls. It supplies neither
a conversation nor a previous-response reference. Sampling settings are a
conservative allowlist: either temperature or top-p, and an optional supported
reasoning-effort configuration. Whether the chosen deployment supports those
settings must be qualified before a real run. Output limits below the documented
Responses minimum are refused before dispatch.

The transport invokes `authorize_transfer()` immediately before opening the POST.
The signed observation binds that callback's authorization marker. Local evidence
read permission does not imply `comparison_external:openai` disclosure consent.
The comparator rechecks authority after generation and at acceptance/recording.
Revocation can stop further disclosure and acceptance; it cannot recall a request
already processed by the provider. The provider receives the actual authorized
question and source meaning. `store=false` does not make that meaning invisible
to the provider.

The exact returned model must match the frozen allowlist. Only completed assistant
text is accepted as visible output. Refusals, incomplete generation, unexpected
tool content, missing usage and changed-model responses cannot become successful
answers. The response body preserved here is the HTTP entity exposed by HTTPX,
not a TLS packet capture or proof of provider internal computation.

## Metering and failure receipts

- **Local preflight:** the tokenizer counts the whole compiled request body,
  including its system/query/source envelope. It does not claim to reproduce the
  provider's hidden role or message-boundary formatting.
- **Actual acceptance:** the paired runner checks the reported server input
  tokens, output tokens, feature calls and wall time against the frozen limits.
  A request may pass local preflight yet exceed the server input budget. Such a
  result is not a successful comparison answer. No remote token-count call is
  made as an extra disclosure or feature request.
- **Failure-inclusive accounting:** refusals and incomplete responses retain
  actual usage when supplied. After a successful exchange proof, later permission
  refusal or recording/validation failure retains verified usage through the
  runner's metered stop/failure contract. An invalid exchange proof supplies no
  trusted usage. Ordinary missing cost remains unavailable, never zero or an
  estimated bill.
- **Private transport attempts:** the mandatory `PrivateTransportAttemptSink`
  receives signed metadata and actual request/response bytes. It must be supplied
  as a host-authorized encrypted, append-only custody implementation, not public
  telemetry. This milestone defines the port; it does not implement or qualify
  that selected-store sink. Successful exchange custody already exists in the
  comparator recorder.
- **Partial bodies:** timeout, cancellation or the frozen response-byte limit
  can leave only a bounded prefix. Its digest covers that prefix, and
  `response_complete=false` explicitly prevents presenting it as the complete
  response. If no response bytes arrived, they remain unavailable. A sink failure
  blocks response success; cancellation still propagates if recording also fails.

The signature is a first-party observation from an independently enrolled key.
It is not a provider signature, a refund guarantee or proof that a timed-out
request incurred no charge. Fixtures can supply signed fictional bytes without
any API prediction; those fixtures qualify contract mechanics only.

## Local artifact limits

Both local adapters read only explicit supplied files. They make no Hub lookup,
run no custom model code and perform no training. The ONNX adapter refuses
external tensor files, local functions and custom operator domains, including
references inside subgraphs or sparse tensor attributes. It uses the CPU execution
provider and requires an export whose named output already contains sentence
vectors. It adds no invented pooling or normalization. Overlong text or batches
are refused rather than silently truncated.

The ONNX call currently runs in an asyncio thread. Cancelling that await does
not terminate native computation. A terminable worker, memory bounds and actual
latency qualification remain necessary before claiming the shared deadline.
No tokenizer or ONNX model artifact was supplied here, and those runtime
constructors have not been exercised against real weights.

## Verification and remaining work

Eleven local optional-provider tests pass using HTTPX mock transport, fictional
request/response bytes and test keys. They cover fixed dispatch bytes, fresh
transfer refusal, signed response/model/usage binding, redirects, incomplete
responses, refusals, response-byte limits, custody errors, timeout/cancellation
and exact supplied-file checks. Thirteen comparator contract tests also pass,
including actual configured-window membership/bounds, native control-event
exclusion and verified usage after rejection. These tests establish neither a
competent actual baseline nor a FloRA advantage.

Before real execution, independently provide and qualify the deployment/config,
local artifacts and runtime lock, observation-key enrollment, private attempt
custody, explicit disclosure grants and bounded worker. Pilot retrieval and
failure/cost accounting before freezing the held-out protocol. The cohort,
thresholds, real-host judgments and builder reproduction remain governed by the
[frozen experiment goal](EXPERIMENT_GOAL.md).

The optional `providers` install extra pins `httpx==0.28.1`, the runtime used by
the protocol fixtures. This pin is an installation boundary, not qualification
of a real provider deployment or transitive runtime. Local artifacts require separately chosen exact `tokenizers`,
`onnx`, `onnxruntime` and `numpy` versions recorded in their manifest and deployment
lock; no weight package should be automatically downloaded. The repository's
base install does not acquire these optional runtimes by importing `flora`.

Primary API references verified on 2026-09-29:

- [OpenAI Responses create reference](https://developers.openai.com/api/reference/python/resources/responses/methods/create)
- [OpenAI token counting guide](https://developers.openai.com/api/docs/guides/token-counting)
- [OpenAI API authentication and request IDs](https://developers.openai.com/api/reference/overview)
- [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data)
- [Tokenizers API](https://huggingface.co/docs/tokenizers/v0.20.3/en/api/tokenizer)
- [ONNX Runtime Python implementation](https://github.com/microsoft/onnxruntime/blob/main/onnxruntime/python/onnxruntime_inference_collection.py)
- [HTTPX environment controls](https://www.python-httpx.org/environment_variables/)
