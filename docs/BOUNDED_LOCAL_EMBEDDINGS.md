# Bounded local comparator embeddings

`SuppliedONNXSentenceEmbeddings` now runs its existing, explicitly supplied ONNX
sentence-vector export in a fresh, terminable CPU process. ONNX session creation,
tokenizer encoding and inference happen there. Cancelling the await can terminate
that computation; it does not leave an ONNX inference thread running in FloRA.
This is comparator infrastructure, not another FloRA memory or judgment model.

## What is implemented

- **Exact artifacts:** the existing graph and tokenizer files, configuration,
  adapter/worker source and declared package versions are frozen in
  `SuppliedArtifactManifest`. Descriptor-relative regular-file reads refuse
  symlinked intermediate directories and enforce the aggregate artifact byte
  limit. Actual bytes are hashed before use.
- **Concrete shipped worker:** `embedding_process_configuration` builds the
  exact launch and manifest for `providers/embedding_worker.py`. It needs no
  missing model factory. `QualifiedNativeProcessWorker` seals the executable and
  worker source before execution; the independently supplied qualifier must
  cover their actual transitive runtime dependencies and the embedding artifact
  contract. Hashes alone are not qualification.
- **Private transfer:** graph, tokenizer, configuration and authorized text bytes
  go through bounded private pipes. They are not command-line arguments. Public
  launch configuration contains only artifact metadata, resource limits and
  explicit runtime paths. No Hub lookup, model download, custom model code,
  training or network request is used by the worker.
- **Current read authority:** the mandatory deployment `authorize_read` callback
  runs around actual artifact reads, before dispatch, after process startup
  before input transfer, and around output acceptance. It creates no permission.
  The selected original-memory retriever also checks its current phase history
  before and after embeddings. A callback must implement actual host-scoped
  current authority; a fixture `allow()` is not a production consent system.
- **Bounded lifetime:** caller deadline and frozen wall-time limit include fresh
  process startup and inference. Timeout, cancellation, bad exit and pipe limits
  produce sanitized transport failures, and the transport reaps the child and
  terminates its process group. One adapter admits one child at a time; waiting
  for that slot also consumes the caller deadline.
- **Resource controls:** before private decoding and ML imports, the child sets
  hard Linux address-space, CPU-time, open-file, file-size and core-file limits.
  ONNX Runtime uses only `CPUExecutionProvider`, sequential graph execution and
  one intra/inter-op thread. BLAS thread settings are frozen at one and tokenizer
  parallelism is disabled. These are explicit runtime/library settings, not a
  claim that an arbitrary native dependency is an adversarial sandbox.
- **Input and output checks:** text, aggregate bytes, artifact bytes and batch
  count are bounded. `maximum_inputs` limits the whole call; `maximum_batch`
  limits each contiguous chunk. `chunk_rule="contiguous_input_order_v1"` is
  frozen in the artifact configuration/digest. One child/session processes those
  chunks in input order under one deadline, never resetting time per chunk.
  Total output and per-input token-count records are bounded. Overlong tokens are rejected without truncation. Only inline
  standard-op graphs without external tensors, local functions or custom
  operator domains are accepted. The graph must already output finite, nonzero
  sentence vectors of the declared shape. The adapter adds no pooling or
  normalization. Output binds the exact request, artifact, configuration and
  every input digest.

Passive descriptor hashing and private-request serialization use owned bounded
reader tasks with a per-adapter retained concurrency slot. No replacement
callback starts while a cancelled callback is still physically running. A cancelled reader may finish its bounded passive read or encoding;
it has no inference, publication or process-launch continuation. Native inference
is confined to the terminable child.

## Runtime configuration

The deployment explicitly supplies `EmbeddingProcessLimits`, the existing graph
and tokenizer, exact package versions, a Python executable/runtime prefix,
optional explicit dependency directories, current read authority and an
independently verified worker qualification receipt. The constructor refuses a
worker whose launch or manifest differs from the exact artifact/resource binding.

The sealed executable has no reliable original pathname for virtual-environment
discovery. The fixed Python launch therefore uses `-S -s -P`, a frozen explicit
`PYTHONHOME`, and explicit ML package directories. It inherits no environment,
`PYTHONPATH`, site initialization or user site. The independent qualification must
cover the Python standard library and those directories, including native shared
libraries; matching package-version strings alone cannot establish those bytes.
A deployment must keep its qualified runtime immutable for the invocation. This
process boundary is not a filesystem or network security sandbox.

`RLIMIT_AS` bounds virtual address space, not resident RAM. CPU time is measured
in whole seconds; wall-time enforcement remains the process transport's job.
Resource settings that cannot support imports or the qualified graph fail closed.
The process is Linux-specific because its transport requires immutable memfd
code descriptors. No weaker thread fallback is installed.

## Verification and remaining evidence

Fifteen local tests run with `onnx==1.17.0`, `onnxruntime==1.20.1`,
`tokenizers==0.20.3` and `numpy==2.2.6`. The test generates a tiny inline ONNX
arithmetic graph and a tiny serialized word tokenizer; it downloads no model and
trains nothing. Actual child execution succeeds while parent ONNX session
creation is forbidden. Tests cover changed artifact and missing qualification,
current permission refusal before input/after inference, real memory refusal,
byte/batch/output/token bounds, symlink confinement, serialized child admission,
a call above the per-chunk cap but within the frozen total cap, and actual child reaping after timeout/cancellation.

The test's independent qualification is explicitly fictional. Its arithmetic
vectors establish process and contract mechanics, not embedding quality, a strong
comparator, latency at experiment scale, customer benefit or a FloRA win. A real
existing embedding artifact, its data rights and suitability, transitive worker
qualification, actual hardware settings and retrieval/latency pilot still need to
be frozen and qualified. The exact frozen chunking/padding method must be qualified with the actual
graph; an arbitrary graph need not be invariant to batch membership. Source
histories beyond the declared total count or byte cap are refused rather than
silently dropped, truncated or split into an unlimited sequence.

Primary runtime references:
[ONNX Runtime thread controls](https://onnxruntime.ai/docs/performance/tune-performance/threading.html),
[Python resource limits](https://docs.python.org/3/library/resource.html), and
[Python command-line isolation controls](https://docs.python.org/3/using/cmdline.html).
