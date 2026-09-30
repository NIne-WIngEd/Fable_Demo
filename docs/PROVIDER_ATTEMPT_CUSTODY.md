# Private provider attempt custody

This is infrastructure for the experiment's optional external feature calls. It
does not build or replace the personality model or MFM, make an API call, create a
permission grant, or establish that FloRA improves personal judgment.

`XTDBProviderAttemptCustody` implements the private transport-attempt sink using
the selected stack: encrypted local objects, canonical Kurrent Experience and a
separate immutable XTDB index. No SQLite substitute is involved.

## What one task binds

- The registered run plan, common question, case, phase, arm and host authority.
- The exact independently registered phase history and authorized context.
- The actual compiled request bytes, provider settings and output limit.
- An independent wire-input verification receipt and exact disclosed sources.
- The supplied tokenizer's whole-request count and frozen artifact/configuration.
- An independently enrolled first-party observer public key.

The supplied `ProviderInputVerifier` must verify the actual wire semantics. The
concrete `OriginalMemoryProviderInputVerifier` supports only the existing
`general_model_memory` comparator: it checks extractive original source windows
and rebuilds the exact request with the frozen compiler. It refuses native FloRA
tasks. A native feature packet needs its own qualified verifier; this module does
not invent one or treat encoded memory as automatically safe to disclose.

The plan is an administrative binding, not an inference-history parent. Task
parents contain the question, phase manifest and actual context-source closure.
Provider artifacts have the distinct `provider_attempt_artifact` event type and
XTDB table `flora_provider_attempt_artifacts`; ordinary comparison and reviewer
readers cannot open them. The native-lineage authority excludes this event type
from original experiment history.

## Separate permissions

| Boundary | Required current authority |
| --- | --- |
| Prepare and revalidate input | The exact run/case/phase evaluation purpose and independent context-lineage authority |
| Dispatch to a provider | `comparison_external:<provider_id>` for the exact disclosed question and context-source closure |
| Preserve and validate this bound task's observed attempt | `provider_attempt_capture:<run digest>` for the task's source closure |
| Recover the private task and observation | `provider_attempt_audit:<run digest>` for every artifact and its full parent closure |

The caller supplies these owner-authorized grants through the existing permission
controller. The ledger issues no grant. Local read, external disclosure, capture
and audit are distinct purposes. Withdrawal of external or evaluation permission
blocks further dispatch or answer acceptance; it does not erase an already
observed response if separate local capture permission remains current.

Every private object read has immediate checks before and after decryption,
including nested object `put` and reference-recovery reads. Checks use current
registered metadata and current ancestor permission, never a cached permission
decision. A reviewer grant cannot substitute for private audit permission.

## Distinct dispatch attempts

`prepare_task(...)` returns a `BoundProviderAttemptSink`. One task permits one
dispatch authorization; retries require distinct task IDs. Authorization checks
the actual disclosure callback and then supplies a task-bound marker to the
transport:

1. Verify the current source authorization marker from the caller.
2. Bind that marker to the exact private frozen task digest.
3. Store the authorization and enforce the registered per-arm/phase feature-call
   budget atomically in XTDB.
4. Recheck external authority and return the task-bound marker at dispatch.

The enrolled observer must sign that returned marker with the actual request and
response bytes. Two retries with identical wire bytes and unchanged grants have
different markers. Replaying the first signed observation as the second attempt
is refused. Retrying storage of the same signed observation is idempotent.

A dispatch authorization is permission evidence. It does not prove that a call
was sent, completed, or billed. A failed authorization never becomes an observed
attempt. An interrupted dispatch without a completed observer receipt remains
unresolved; it must not be reported as a zero-cost call.

## Observation and usage

The ledger verifies the enrolled observer signature, exact task marker,
configuration, actual request bytes and response digest. Success, refusal, HTTP
error, incomplete generation, timeout, cancellation and invalid/failed transport
observations remain distinct denominator rows. A bounded response prefix is
stored as incomplete, never as a full response.

Known usage is accepted only when it matches usage parsed from the actual
complete response. Missing usage and cost remain unavailable. A refusal can
retain known consumed tokens even if later evaluation or external authority is
withdrawn. These are first-party observations, not official provider signatures,
proof of provider internal computation, or guarantees about refunds.

Recovery recreates the full task, authorization and signed observation from the
selected stores. It rechecks immutable bindings and current audit permission; no
caller RAM observation or permission map is needed.

The issued sink also exposes `verify_response(response)` and `verified_usage()`.
These validate exactly that handle's captured observation under current capture
permission; they do not provide a general private-artifact reader. A successful
answer must match the durable signed success, actual response bytes, returned
model, request ID, task marker, usage and visible assistant text. A client cannot
skip capture and still pass. A failure's usage comes from this verified durable
capture, not an exception supplied by the client. Missing capture or withdrawn
capture authority leaves usage unverified.

## Verification and remaining wiring

Fourteen local contract tests pass with fictional inputs and signatures. They cover
exact task/wire binding, distinct retry markers, replay refusal, separate
permissions, phase withdrawal during slow verification or storage, known versus
unknown usage, mandatory capture before answer acceptance, immutable observations and nested
decryption gates. The uniquely named selected-backend test covers durable
recovery, per-arm/phase dispatch limits, partial timeout/cancellation, refusal
usage after withdrawal, and rejection before private reads. Its physical-engine
qualification remains pending the repository CI run.

`GeneralMemoryArmAdapter` accepts per-execution attempt custody and a supplied
task-ID function. Without them it is unavailable before dispatch. It prepares a
sink for the exact `ExecutionRequest`, gives that sink to the transport, tracks
the task-bound marker and requires the captured response before accepting an
answer. Preflight and post-response source checks remain separate from the
single-use dispatch authorization. A global first-task sink cannot substitute
for that wiring. The selected comparator test now exercises this flow with
fictional signed Responses bodies; physical CI remains pending. Blocking selected
store calls still need bounded deployment execution before claiming an end-to-end
response deadline.

Actual provider deployment, credentials, observer enrollment, tokenizer
qualification, native wire verification and learned-model artifacts are supplied
separately. This milestone made no live request and exercised no model weights.
