# Comparator attempt wiring

The general-model-plus-memory comparator now connects each execution to the
selected private provider-attempt ledger. This is experiment infrastructure;
it does not establish baseline quality or a FloRA behavioral result.

`GeneralMemoryArmAdapter` requires `attempt_custody` and an explicit
`task_id_for(ExecutionRequest)`. Missing either stops as unavailable before a
provider call. The selected implementation is `XTDBProviderAttemptCustody`:
it checks the registered run plan, phase history, common question, original
memory context, actual compiled request, source permissions and token receipt.
Retries need distinct authorized task IDs and remain subject to the frozen
per-case, per-phase arm call budget. No automatic retry is added.

For one dispatch:

1. Prepare its immutable private task under the host's separate capture consent.
2. Check ordinary source disclosure during preflight.
3. Pass that task's bound sink to `client.generate(..., attempt_sink=sink)`.
4. At the actual transfer boundary, the sink wraps the source disclosure callback
   and records a single-use, task-bound authorization marker. The transport signs
   that marker with its observed request, response and metering.
5. Verify the signed exchange and its exact durable captured response. Then
   check current source disclosure again before accepting the result.

Preflight and post-response checks use the ordinary source marker. They do not
consume or replay the single-use dispatch marker. A source-only marker, a marker
from another task or an uncaptured signed response cannot become an accepted
comparison result. The ledger also checks the visible assistant text against
the actual captured HTTP body; a signature alone cannot turn different text
into that response.

The optional OpenAI transport accepts the sink per call. Concurrent calls never
swap a shared sink. A constructor-level sink is retained only for explicitly
supplied mock HTTP fixtures. Without a per-call sink, production transport
stops before credential lookup or dispatch.

Known usage belongs to the denominator even when acceptance fails. On ordinary
failure, refusal, timeout or cancellation, the adapter recovers usage only from
the exact task's durable, signed observation under current capture permission.
An exception's token count is not trusted. Signed response counters alone cannot
replace metering independently checked against the exact captured body. Once
that metering is verified, later acceptance failures retain it. Unknown usage stays
unknown; it is never changed to zero or an estimate. Timeout and cancellation
keep their control behavior.

The runner's optional `measured_stop_usage` hook reads cached, already verified
metadata only. It performs no private reads or decryption. Its key binds the
plan digest, case, phase and context digest; a new execution clears its prior
stop cache and the adapter refuses concurrent execution of that identical key.
It is a failure-only bridge, not a replacement for successful result validation.

Local validation covers 19 comparator contracts and 13 optional-transport
contracts, using fictional supplied bytes and mock HTTP. Selected integration
fixtures additionally wire the actual ledger; their physical backend gate must
pass before this wiring is described as qualified on the selected stack. There
has been no live provider request, credential lookup, model training or claimed
comparative win in this milestone. Actual provider, tokenizer, embedding and
transport qualifications and experiment participants remain external inputs.

Related: [provider-attempt custody](PROVIDER_ATTEMPT_CUSTODY.md),
[optional provider adapters](OPTIONAL_PROVIDER_ADAPTERS.md), and the
[frozen experiment goal](EXPERIMENT_GOAL.md).
