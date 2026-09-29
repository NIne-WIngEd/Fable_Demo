# Failure-inclusive paired comparison interface

`src/flora/comparison_run.py` builds one independent step of the [frozen experiment](EXPERIMENT_GOAL.md): execute supplied arm adapters under a common plan, retain every attempt, and prepare separate blinded review content. It contains **no personality model, MFM, substitute judge, trained baseline, provider client, or behavioral score**.

## Input and execution boundary

- `HistorySnapshot` contains exact original `ExperienceEvent` envelopes and their actual plaintext bytes. It verifies each content digest and host scope and constructs a canonical history hash. The after history must preserve the entire before prefix and append the declared intervention.
- `PairedRunPlan` wraps the existing `EvaluationProtocol`, names each arm's artifact and update mechanism, and freezes each case's question hash plus common context-byte, context-token and feature-call limits. Actual question and history bytes must match those hashes before any adapter receives them.
- A separately trusted `RunEvidencePolicy` authorizes the exact originals. The runner rechecks it immediately before every arm, after preparation, and after inference before accepting an output. A source-use withdrawal produces a retained refusal; initial unapproved inputs are rejected before execution.
- `ArmAdapter.prepare` supplies the actual selected `LocalContext`. Full FloRA and the same-evidence ablation receive the **same exact context content and receipt**, rather than independently selected contexts with matching labels. The general-model memory baseline prepares its own context from the same authorized originals. Insufficient declared context stops before inference.
- `ArmAdapter.execute` returns actual output bytes, observed cumulative usage, and the existing selected `RecordedEvent` delivery/decision pair. The runner checks the exact delivered-context digest, consumed event IDs, artifact, producer, and recorded verdict bytes. The independent evidence policy must also verify both persisted events through the selected stores.

Use the real selected context/decision paths when implementing an adapter: `assemble_context`, `record_context_delivery`, and `record_contextual_decision`. The runner does not promote a caller's bytes into a qualified native judgment or silently replace those paths with another datastore.

## Budgets and failure reporting

- Preparation and execution share one measured asynchronous deadline. Actual context bytes are checked before inference. Async adapters must cooperate with cancellation; blocking or detached inference needs separately terminable workers. This is not yet a worker lifecycle implementation.
- `MeasuredUsage` carries observed context/input/output token counts and feature-call counts for preparation **and** execution. Adapters must obtain these from actual tokenization and engine receipts and enforce limits before issuing additional calls. The runner checks reported observed totals and marks an over-budget result `budget_exceeded`; it does not estimate unknown usage or independently intercept provider calls.
- Cost is optional, represented as integer micro-units plus a three-letter currency code. Missing cost remains unavailable. There is no price-table estimate or invented zero cost. Usage missing after a timeout remains unavailable unless the adapter supplies an explicit measured stop receipt.
- Every case has before/after attempts for full FloRA, the general-model baseline and the same-evidence ablation. `success`, `unavailable`, `refused`, `timeout`, `failed`, `invalid_result`, and `budget_exceeded` all remain in the matrix. Exception text is omitted because it can contain personal inputs or provider payloads.
- `validate_run` rejects omitted failures, changed questions/history/lineage, unequal original event sets, and an altered same-evidence context. `run_summary` reports operational statuses, per-host/arm elapsed times, known usage and known costs. It does not score judgment or declare an advantage.

The new failure-inclusive receipts are separate from the earlier success-only `AttemptReceipt` validator. Overtime failures must not be passed through that validator and dropped from the report.

## Blinded review boundary

`create_blind_review` returns two separate objects. The review pack contains randomized opaque pair IDs, the authorized question, and left/right output text. It includes no arm, host, case, phase, artifact, cost, diagnostics or attempt receipt. The private key maps those opaque pairs back to their identities and records the pack hash. Keep it unavailable to reviewers until assessment is closed.

Both questions and outputs need independent review permission. The pack contains personal material and is not public by default. Hiding provenance metadata does not prove that a reviewer cannot infer identity from the response's own wording; that limitation needs assessment. Only successful pairs enter the review pack; excluded pairs remain counted in the private key and the failure-inclusive run report.

This milestone prepares review content. Rating intake, reason/evidence scoring, per-host behavioral uncertainty, final preregistration and numerical acceptance criteria remain separate work. No rating or result is generated here.

## Plug-in shape

Call `await run_paired(plan=..., histories=..., questions=..., adapters=..., evidence_policy=...)` with registered histories, frozen questions, and externally qualified arm adapters. Missing adapters generate explicit unavailable attempts. Then use `run_summary(run)` and, only with review permission, `create_blind_review(run, policy=...)`.

The numerical plan and cohort must be calibrated and preregistered before final evaluation. `evidence_kind` must accurately label `contract_fixture`, `synthetic`, or `consenting_real_host`; it is a declaration requiring independent qualification, not something the runner infers.

## Verification and actual remaining boundary

Eleven local contract regressions exercise input tampering, independent authorization, revocation during inference, malformed/insufficient context, same actual ablation evidence, recorded-verdict substitution, deadline/refusal/unavailability, failure denominator preservation, explicit unknown costs, frozen questions, and review authorization/blinding. Their fictional adapter and in-memory event log exercise contracts only. They are not selected-backend qualification, a model run, a strong comparator implementation, or a benchmark win.

The next independent integration is a selected-store evidence-policy adapter and selected-context arm plumbing with durable run custody. Actual formation/native inference still comes from the separately built MFM and personality workstreams. A serious general-model comparator and its authorized feature-engine client remain to be integrated; this module performs no live external API call.

## Native phase and execution lineage

A native context can include exact approved-state controls. They stay separate
from shared original user history; the baseline cannot receive them through a
source-membership exception. Configure the selected evidence policy with the
[qualified native lineage bridge](JUDGMENT_COMPARISON_LINEAGE.md). It checks the
current original closure, Claim/state authority and independently qualified
phase training/state exclusions before and after execution.

A native decision retains its qualified execution output parent. A configured
native arm cannot replace it with an otherwise valid generic recorded verdict.
Run custody requires the exact execution request/result and current selected
policy for native decisions and internal controls; it does not flatten those
records into original user history. Verified usage stays in failures; actual
processed input tokens also have to fit the frozen request budget.

Production adapters must cooperate with cancellation or invoke inference through
a separately terminable worker. The synchronous supplied-output integration
fixture tests actual selected custody; it is not a production model worker.
A shared evaluable decision/output contract must come from the actual qualified
producer before behavioral scoring. Native IDP bytes and a free-form API answer
do not by themselves constitute a comparable blinded judgment task.
