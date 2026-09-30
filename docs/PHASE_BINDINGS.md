# Phase bindings and passive recovery

A before judgment must identify the actual checkpoint and producer that made it. An after judgment may use a different qualified checkpoint. `PairedRunPlan.phase_bindings` freezes a complete `(case, phase, arm)` matrix; it changes the plan digest and is preserved by selected encrypted custody. `binding_for` is the only attempt-level binding lookup. Constant-binding historical plans retain their original digest.

This binding matrix works with the [selected phase snapshots](SELECTED_PHASE_SNAPSHOTS.md). Their historical Claim, state, episode and qualified artifact views preserve the actual captured authority without rewinding live heads. Current source consent and present quarantine still apply. The strict native router also binds each actual frozen arm header and its distinct invocation; the after ablation requires independently qualified producer exclusion. Missing snapshots, ports or proofs stop the route.

`recover_judgment(..., reconcile=False)` and `recover_formation(..., reconcile=False)` validate the actual qualified execution and existing private registry metadata without repairing rows. Missing custody stops the passive read. Explicit default recovery can reconcile an append-before-index interruption; it belongs outside a cancelled reader.

On failure, the paired runner may recover exact cached usage from an adapter's `measured_stop_usage` hook. That hook binds the frozen plan, case, phase and context; it opens no private data and performs no inference. Unknown counters remain unknown. Failed and timed-out attempts remain in the denominator.

Provider attempt records have their own capture/audit route. Generic comparison recovery rejects their canonical event type before decrypting bytes.

Local tests cover changed phase checkpoints, incomplete matrices, durable plan round-trip, timeout metering, strict recovery with missing indexes, no-write spies and provider audit isolation. Real backend qualification is recorded separately from these mechanical tests. No test here proves learned judgment or a behavioral advantage.
