# Native judgment lineage in the paired experiment

A shared history contains original user evidence. A native FloRA context can also
contain an owner-approved private state projection. Its approval event must stay
auditable without becoming original user history or entering the baseline.

`selected/judgment_lineage.py` supplies an independent bridge for this distinction.
It creates no model, selector, semantic judge, ACFP shape, or IDP shape.

| Binding | Required check |
| --- | --- |
| Original evidence | Actual Kurrent event, exact registered raw digest and role, parent closure, current permission, membership in the frozen phase history |
| Claim | Exact current accepted version, evidence relations, current projection and value/content hashes |
| Personal state | Exact active subject-bound version, governed activation receipt, independent owner approval, registered permitted approval, and current Claim/source closure |
| Internal approval | Typed separately; never accepted as shared original evidence |
| Model roles | Current registered MFM and personality artifacts, host/interface/generation and exact checkpoint bytes |
| Phase snapshot | Each actual artifact qualifier independently verifies the exact phase, frozen history, run plan, current state lineage and private training/updater exclusions |
| Native result | Actual runtime recovery verifies exact invocation, task, context, output, delivery, decision and qualified execution proof |

The source check alone cannot prove that a model or state learned nothing from
future data. That requires the actual producer's independent phase qualification.
Missing proof fails closed. Signed fictional receipts in tests exercise wiring;
they establish no learned behavior or real training exclusion.

## Hooks

Construct `NativeJudgmentLineageVerifier` with the selected runtime, an independent
`history_authority`, the frozen `run_plan_sha256`, and independent
`history_for(case_id, phase)`, `invocation_id_for(request, result)` and
`phase_receipt_for(snapshot_request)` lookups. None comes from a model response.

- `context_lineage(case_id=..., phase=..., history=..., context=...)` returns the
  exact current `JudgmentContextLineage`, including original and internal IDs.
- `authorize_context(case_id=..., phase=..., history=..., context=..., arm=...)`
  permits only `flora_full` or `same_evidence_ablation`. The baseline retains its
  independent original-only path and cannot use this exception.
- `verify_native_result(request, result)` returns precisely the additional
  qualified output `RecordedEvent` verified by the runtime. It does not remove
  the original output/delivery/context execution lineage to fit a generic arm.
- `verify_native_result_details` also returns the current context proof.

The comparison evidence policy forwards these optional hooks. Other arms keep
the strict original-only context and generic result rules. Failures remain
attempts in the comparison denominator.

## Producer phase adapter

Each actual `RuntimeRoleBinding.qualification_verifier` implements:

```python
verify_phase_snapshot(
    *, request: PhaseArtifactSnapshotRequest, receipt: bytes
) -> VerifiedPhaseArtifactSnapshot
```

The request binds scope, authority namespace, case, phase, run-plan digest,
authorized original history digest/IDs, exact context lineage digest, and the
current `RuntimeWiringManifest`. The producer's receipt remains opaque. Its
verified result binds qualifier and qualification IDs, artifact manifest digest,
request digest, receipt digest, private training/source snapshot digest, and an
explicit `allowed_for_phase=True`. This bridge defines the verification boundary,
not a universal receipt format or a new producer training schema.

Current supported contexts contain Claims and approved personal state. An
accepted episode route must use the separate governed episode publication and
original closure; an unregistered episode candidate cannot satisfy this bridge.

## Validation boundary

Seven deterministic test methods cover parent closure, before/after exclusion,
current content and value mutations, denied/missing/wrong/signed phase receipts,
internal approvals, concurrent phase-history permission/checkpoint changes, and exact native
result recovery. The SQL recorder is mechanics evidence only. The selected
integration case separately exercises real Kurrent/XTDB custody and recreation
with fictional producer outputs/receipts. Passing it qualifies the bridge's
backend wiring, not MFM, personality, or the FloRA behavioral claim.
