# Selected authority frame protocol

Date: 2026-10-01 UTC
Status: bounded design and descriptor foundation; shared collectors and frame integration pending

Continuation scope, 2026-10-02: this composes checks already needed by FloRA's
narrow prototype. It is not a mandate to implement Alice's full memory/mission
platform. The [context record](FLORA_CONTEXT.md) and
[completed physical receipt](VERIFICATION_CHECKPOINT_2026-10-02.md) supersede
the older pending CI status. The full serving frame remains unimplemented.

This protocol follows [the latency architecture review](LATENCY_ARCHITECTURE_RECALIBRATION_2026-10-01.md)
and [explicit selected context/history consumers](SELECTED_CONTEXT_AND_HISTORY.md).
The next change should compose their checks within each protected boundary.
It must not reuse a successful authorization from an earlier boundary.

The privately issued selected-phase descriptor is a foundation for identifying
which native checks can be composed. Its addition alone changes no serving
algorithm and skips no existing history, permission, ancestry or private-read
check. The shared frame described below is not yet implemented or qualified.
No latency improvement is claimed.

## What the existing implementation repeats

The audit concerns runtime
[`029a7655ca4aac16ba5c7644b7ca579a8ac45aac`](https://github.com/NIne-WIngEd/FloRA/commit/029a7655ca4aac16ba5c7644b7ca579a8ac45aac).
Let **C** be the selected context source closure and **H** the held original
history. Both include their required parents. Selecting a small C does not
currently prevent repeated verification of H.

| Call path | Repeated work | Pinned implementation |
| --- | --- | --- |
| Selected context replay | Two complete source resolutions plus separate hydration: five exact Kurrent reads per selected event | [selected_context.py, lines 114-128](https://github.com/NIne-WIngEd/FloRA/blob/029a7655ca4aac16ba5c7644b7ca579a8ac45aac/src/flora/selected/selected_context.py#L114-L128); [source_closure.py, lines 331-335](https://github.com/NIne-WIngEd/FloRA/blob/029a7655ca4aac16ba5c7644b7ca579a8ac45aac/src/flora/selected/source_closure.py#L331-L335) |
| Each source resolution | Actual permission predicates run twice per closure event | [source_closure.py, lines 462-484](https://github.com/NIne-WIngEd/FloRA/blob/029a7655ca4aac16ba5c7644b7ca579a8ac45aac/src/flora/selected/source_closure.py#L462-L484) |
| Each native permission or event gate | Reconstruct held-history authority, then independently resolve that event's phase ancestry | [native_phase_gate.py, lines 28-43 and 109-118](https://github.com/NIne-WIngEd/FloRA/blob/029a7655ca4aac16ba5c7644b7ca579a8ac45aac/src/flora/selected/native_phase_gate.py#L28-L43); [native_reads.py, lines 401-420](https://github.com/NIne-WIngEd/FloRA/blob/029a7655ca4aac16ba5c7644b7ca579a8ac45aac/src/flora/selected/native_reads.py#L401-L420) |
| One successful `metadata_current()` | Three actual selected replays: initial metadata view, metadata/source fence, final source fence. Claim/state predicates add further checks | [context_guard.py, lines 278, 534, 587-592, 631-635](https://github.com/NIne-WIngEd/FloRA/blob/029a7655ca4aac16ba5c7644b7ca579a8ac45aac/src/flora/selected/context_guard.py#L534-L635) |
| One private object `get()` | Fresh checks before and after ciphertext access, and before and after the outer plaintext operation | [experiment_runtime.py, lines 65-97](https://github.com/NIne-WIngEd/FloRA/blob/029a7655ca4aac16ba5c7644b7ca579a8ac45aac/src/flora/selected/experiment_runtime.py#L65-L97) |
| Native context authorization | Authenticate originals, assemble context again, then check current owner, state and producer lineage | [judgment_lineage.py, lines 272-301 and 441-457](https://github.com/NIne-WIngEd/FloRA/blob/029a7655ca4aac16ba5c7644b7ca579a8ac45aac/src/flora/selected/judgment_lineage.py#L272-L301) |
| Native arm lifecycle | Repeat that context authorization during preparation, dispatch, result acceptance and each selected write | [native_arm.py, lines 438-455 and 470-546](https://github.com/NIne-WIngEd/FloRA/blob/029a7655ca4aac16ba5c7644b7ca579a8ac45aac/src/flora/selected/native_arm.py#L438-L455) |
| Independent native result verification | Reconstruct context lineage before recovery and again after it | [judgment_lineage.py, lines 480-505](https://github.com/NIne-WIngEd/FloRA/blob/029a7655ca4aac16ba5c7644b7ca579a8ac45aac/src/flora/selected/judgment_lineage.py#L480-L505) |

These paths explain amplification. They do not establish which change will
pass the response budgets. The private boundaries and independent recovery
checks protect different operations; their existence is not itself a defect.
The problem is repeatedly constructing overlapping proof material inside them.

## Actual receipts and the diagnostic's limits

[Ordinary run 36822267124](https://github.com/NIne-WIngEd/FloRA/actions/runs/36822267124)
ran at that exact runtime commit. Core passed **38/38**, including the four
selected-history physical cases. Standalone comparison failed its unchanged
10,000 ms budget: BEFORE **12,621 ms**, AFTER **19,519 ms**. Native comparison
timed out under its unchanged 60,000 ms budget: BEFORE **60,062 ms**, AFTER
**60,125 ms**; its complete suite took **198.379 s**. Successful infrastructure
cases do not qualify those failed responses.

The completed ordinary run passed **49/53 physical cases**, with two failed
response budgets and two incomplete cases at the original one-hour job caps.
Its separate contracts job stopped at the extracted native comparison binder's
undefined `self`; that fixture repair has broad local regression coverage.
[Complete physical receipts](evidence/2026-10-01_029a7655_physical_ci_receipts.json)
and the [verification checkpoint](VERIFICATION_CHECKPOINT_2026-10-01.md) retain
those failures.

The existing ordinary transport diagnostic artifact `11143943320` has archive
SHA-256 `cede326213fa6a7cf2816b75abd23cae425ccf58aad647414c323f9c720c1590`.
It reports `qualification=false` and **66.235585484 s** over the whole fixture:

- 189 combined history/external metadata checks.
- 2,215 canonical committed replays and 4,105 Kurrent reads.
- 44,403 SQL executions.
- 12,888 current-action resolutions and 2,748 permission predicates.

These counts include fixture work outside a single response. The observer has
no selected-consumer-specific tags. They cannot be assigned wholesale to the
native case, treated as response timings or added across nested inclusive
timings. They support the source finding that proof construction still repeats.
No new profiler, microbenchmark or relaxed-budget experiment is required to
establish that call graph.

## Authority that must be joined

One frame owns one synchronous protected-boundary verification on one actual
owned metadata connection. It contains structural nominations and exact row
observations. It contains no reusable permission lease.

| Domain | Required material and live authority |
| --- | --- |
| Held history H | Exact ordered original IDs, held-byte bindings, original parents, registered source/raw metadata, physical manifest and evaluation grants for every held original |
| Selected context C | Exact nominated originals/control events, bounded parent closure, physical positions and current `personal_judgment` grants |
| Claims | Immutable selected versions and evidence relations, current head/projection, validity, adjudication and quarantine/deletion authority |
| Governed state | Exact version and current active head, activation and approval, rollback bindings and their target versions/activations |
| Independent controllers | Original reader ownership, approved key/enrollment authority, actual model artifact/qualification, native phase and final-seal authority where applicable |

H and C can overlap but their purposes remain separate. All H evaluation
rights must enter the final fence even if C does not select those originals.
Checking phase history early and fencing only C afterward would leave part of
the declared authority outside the terminal observation.

The manifest remains custody material. Its inclusion does not invent an extra
manifest evaluation grant. Context controls cannot become original BEFORE or
AFTER inputs. A valid signed approval cannot stand in for its live activation,
source consent or current owner authority.

## Native descriptor foundation

The descriptor must be privately issued by the actual selected native phase
installation path. A caller-created object or a separately mutable function
attribute cannot identify a trusted native authority.

It must bind the actual phase, held originals and their pure native snapshot;
the selected history controller, domain and source cap; original registry,
permissions and Kurrent owners; the actual native gate and its closure/code
bindings; and the independent current authority callbacks it preserves.
Copying a known gate onto a same-call view must retain those original bindings.
Changed owners, callbacks, code, cap, domain or held originals invalidate it.

The current gate registry identifies wrapper code but accepts supplied
`phase_now` and `phase_member` callbacks. Recognizing that wrapper is therefore
insufficient permission to omit the callbacks. A frame may compose only an
issued and still-bound selected native descriptor with the exact supported
contracts. Unknown/custom gates remain on their existing path or reject the
explicit frame domain before private I/O. A custom denial or side effect may
never disappear behind batching.

Descriptor issuance alone keeps every existing check running. It proves
neither current consent, private custody, a model capability nor lower latency.
Independent issuance records must seal descriptor and origin fields without
keeping closed owners alive. Validate each object's own native field identities
before traversing nested records. A tampered name, record or collection must
reject before any custom hash, equality, property or iteration callback runs.
The lookup and validation helpers must retain their pinned native code.

## Proposed protected-boundary order

1. **Bind and nominate.** Capture exact native owners, readers, code and held
   values. Validate the descriptor and selected domains. Nominate H, its
   manifest, C, Claim/state rows and all required parents within explicit caps.
   Reject unsupported episodes, undeclared tables and excessive closure before
   private I/O. Do not truncate a nomination into success.
2. **Collect actual rows and physical material.** Batch bounded XTDB row keys
   and discover parents in bounded rounds. Verify exact original Kurrent
   commitments, full digest, position, scope, recorded time and parent order.
   Keep immutable captured material local to this frame. No positive predicate
   answer is stored for a later call.
3. **Run the supported predicates.** Re-evaluate native source-purpose,
   Claim/state and phase-membership semantics using the actual sampled rows and
   immutable material. Membership must resolve to this phase's original IDs;
   receipts and future originals remain excluded. A shared collector must not
   return an independently successful nested proof before the outer frame ends.
4. **Run independent callbacks.** Preserve actual owner/proof, producer,
   qualification and final-authority callbacks. Custom supported row readers
   still execute. Callback denial, rebinding or unexpected expansion fails the
   frame. Separate qualification mechanisms are not replaced by a metadata
   sample.
5. **Reobserve after callbacks.** Re-read registered locators and exact physical
   targets. Compare them with the frame's captured immutable material. Include
   all current head/action rows for both H evaluation and C personal judgment.
6. **Finish one joint terminal fence.** Observe source/raw, manifest, grants,
   Claims and state dependencies in one capped statement on the owned XTDB
   connection. Missing, duplicate, ambiguous or changed rows fail. Only pinned
   pure binding and native-value checks may run afterward. No authority callback
   or mutable JSON helper may reopen a stale-proof window.
7. **Close and discard.** Return only this boundary's result. Ciphertext and
   plaintext boundaries each require a new frame. A new source, head, grant,
   correction or qualification generation requires fresh evaluation; a previous
   successful frame cannot authorize it.

The initial AEAD authentication and separate archive/recovery contracts remain
in force. Request-local authenticated bytes or immutable lineage may eventually
avoid duplicate reconstruction only through a separately specified ownership
contract. They never carry a current allow answer. This frame work does not
authorize pooling live connections or skipping independent execution recovery.

## Boundedness and backend limits

- Source caps cover required parents and manifest inclusion. The implementation
  must derive a finite row cap that also includes distinct purposes, Claim/state
  dependencies and rollback targets. Every discovered dependency counts.
- Keep H (including its custody manifest) and C under separate source-closure
  caps. Each phase-membership ancestry traversal also keeps its H cap. The
  existing history helper's additional `source_purposes` puts the combined
  set under H's cap and cannot substitute for these separate domains. The
  native fixture has H=32 and C=128; a broad C must not enlarge one ancestry's
  permitted width or shrink into H's aggregate cap.
- A future frame must cover initial private context assembly through
  `prepare_current_context`'s `initial_barrier`, as well as later current checks
  and ciphertext/plaintext boundaries. Composing only `metadata_current`
  would leave the first private read on the old path.
- Sampled rows and immutable event material live within one frame. Mutable
  heads, positive permissions and current qualification are not persistent
  caches. Native predicates execute again at every protected boundary.
- Existing metadata batching distinguishes exact native readers from custom
  readers and executes the latter rather than hiding their behavior; preserve
  [that contract](https://github.com/NIne-WIngEd/FloRA/blob/029a7655ca4aac16ba5c7644b7ca579a8ac45aac/src/flora/selected/phase_source_fence.py#L197-L219).
- Kurrent currently exposes exact point reads through this adapter. It has no
  qualified multipoint primitive. Reading an arbitrarily wide min-to-max
  position window would violate bounded selection. Any future grouped physical
  reads need an explicit maximum scan domain and exact coordinate validation.
- A terminal XTDB statement and Kurrent observations are not a cross-engine
  atomic transaction. They are not a permission lease or a whole-stream
  integrity certificate. Default whole-stream consumers retain their contract.
- Engine choices, source inputs, scientific phases, clocks and concurrency limits
  stay unchanged. Response budgets remain **10,000 ms** standalone and
  **60,000 ms** native. Ordinary CI jobs retain their **60-minute** caps.

## Implementation and verification gates

**Foundation:** independently verify private descriptor issuance, exact
original/callback bindings, copy behavior and invalidation. Existing native
predicate, revocation and private-read tests must remain green. Verify that
descriptor/origin field swaps and effectful nested values reject without
executing their callbacks, and that the issuance registry releases closed owner
cycles. This stage alone has no performance claim.

**Shared collectors:** add a distinct supported frame contract. Prove that the
actual all-H history collector, selected-source collector and Claim/state
collector contribute their complete dependencies without accepting earlier
terminal successes. Unknown/custom authority must fail or retain its original
explicit path. No optimized frame is active until these contracts exist.

**Race and custody checks:** withdraw an unselected H evaluation grant from the
last callback; withdraw a selected C grant; replace a Claim head or state
activation; change a parent locator, physical event or recorded time; mutate held
context/descriptor/reader bindings; change owner or qualification authority.
Each must prevent stale private material or a result from returning. Preserve
signed owner proof, exact BEFORE/AFTER originals, ciphertext/plaintext checks,
restart behavior and independently recovered output attribution.

**Physical and latency gates:** run the same original engine cases against the
exact published runtime. Report construction, response, update and recovery as
separate observations. Pass all correctness gates before attributing a response
change to the new serving path. A failed response budget remains a failure;
fixture timings and diagnostic counts cannot replace it.

No personality model or MFM is constructed, trained, downloaded or substituted
by this protocol. Shared frame implementation, learned behavior, builder
transfer and consumer performance qualification remain pending.
