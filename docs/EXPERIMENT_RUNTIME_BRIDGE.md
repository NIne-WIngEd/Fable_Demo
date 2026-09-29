# FloRA experiment runtime bridge

This is runnable orchestration for the selected fabric. It waits for externally
qualified MFM and personality artifacts; it does not build either model or turn
the infrastructure fixtures into learned behavior.

## What runs

`FloRAExperimentRuntime.run_cycle(...)` connects these existing stages:

1. Open registered, currently permitted originals and their parent closure.
2. Record the formation delivery; invoke the externally qualified local MFM
   adapter through its exact producer codec and independently verified execution
   receipt. Persist the returned proposal bundle as a candidate.
3. Apply a supplied semantic interpretation and independently authenticated
   adjudication through atomic governed Claim admission.
4. Register and activate any separately supplied, independently approved personal
   state through `XTDBGovernedPersonalDevelopment`.
5. Assemble current permitted Claim and active personal-state context. The actual
   personality producer codec serializes its native cognitive frame; its qualified
   local adapter returns the actual identity decision packet. Record exact input,
   output, execution proof and decision lineage.

The separate methods `form_experience`, `admit_proposal`,
`activate_personal_state`, and `judge` let callers inspect those boundaries.
`recover_formation` and `recover_judgment` recover exact private receipts from
XTDB/Kurrent and recheck current source/state permissions, context bytes, artifact
generation and producer proof. They can reconcile an appended execution receipt
whose XTDB custody index is missing. They never restore permission or replay an
old judgment against changed context.

## Required services

| Service | Required boundary |
|---|---|
| MFM and personality `RuntimeRoleBinding` | Exact registered artifact, checkpoint path, interface IDs/digests and independent qualification verifier |
| `ExternalRuntimeAdapter` | Host-local execution of that qualified artifact; no generic model fallback |
| `QualifiedProducerCodec` | Actual producer input/output format; personality ACFP serialization and IDP validation come from the producer |
| `RuntimeExecutionVerifier` | Independent producer proof binding the loaded artifact, generation, host, interface, invocation and exact input/output |
| Semantic admission service | Exact upstream candidate/adjudication contracts and independent authority; authenticated sources alone cannot accept meaning |
| Governed state and owner verifier | Approved current subject-separated state, not a bare candidate registry |
| `RegisteredJudgmentContextPolicy` | Current original/parent permissions before and after private reads |
| `DurablePersonalReferences` | Selected durable original/private object custody; no caller raw-reference dictionary |
| Explicit experiment plan | Frozen nonlearned routes; declared item counts do not establish semantic sufficiency |

Call `runtime.readiness()` first. It reports `memory_formation` and
`personality_judgment` separately and identifies absent role bindings, producer
codecs, inference adapters, qualification/execution verifiers or usable current
artifacts. A complete cycle refuses missing roles before opening user evidence.

```python
roles = runtime.readiness()
if all(role.ready for role in roles):
    formation, admitted, active, judgment = runtime.run_cycle(
        request=registered_request,
        formation_invocation_id=formation_run_id,
        value_resolver=independent_value_custody,
        supplied_admissions=external_admission_service,
        supplied_states=external_approved_state_service,
        plan=frozen_experiment_plan,
        task=local_task_bytes,
        judgment_invocation_id=judgment_run_id,
    )
```

Those services must be real qualified producer implementations. The repository
does not supply production MFM/EIPM exports or settle their ACFP/IDP codecs by
inventing a new JSON shape. A source checkpoint hash or N0 training receipt does
not establish host-qualified personality judgment.

## Evidence and failure boundaries

- Input and output bytes stay in encrypted private custody. Canonical Experience
  links each invocation to its delivery and exact scoped artifact/interface.
- Failed proof, inference, revoked context and changed artifact attempts receive
  failure metadata when the backend is available. A delivered input remains an
  attempt even if recording the failure also fails. Comparison runs must retain
  their frozen planned denominator and must not discard those failures.
- Kurrent append, XTDB custody, candidate recording, Claim admission, state
  activation and judgment recording are separate durable boundaries. The cycle
  is not a global transaction, and a later failure does not undo accepted Claims.
- Frozen exact routes are mechanics. No learned selector, sufficient-context
  judgment, state updater or personality model is implemented here.
- Permission denial blocks current use. It does not complete derivative erasure,
  execution-state deletion or parameter unlearning.
- Deterministic tests use signed fictional producer fixtures and SQL call
  recording. The selected-backend fixture exercises real Kurrent/XTDB/private
  custody/admission/state/context/recovery, with fictional producer outputs. It
  qualifies wiring only and reports no memory or personality improvement.

## Architecture sources

- A.L.I.C.E. `main@5f9b9ccb2628eb2a5512d8624b9a78bcc9c7fe38`:
  `docs/FABLE_PERSONAL_DEVELOPMENT_ARCHITECTURE.md` and
  `docs/ALICE_PHASE2_REPLACEMENT_AND_FABLE_V1_EXECUTION_PLAN_2026-09-27.md`.
- Personality branch
  `alice-eipm-v1-n0-semantic-operator-foundation-v1@cef6e5ed48bb69e064596b30a87a73c3e79a0763`:
  `docs/eipm/EIPM_ROLE_AND_OBJECTIVE_CONTRACT_v1.0.md`.
- Current MFM reference at `4f287a48`: registered evidence/context/retrieval
  contracts and formation schema `1.2.0`.

These sources require versioned personal state to enter native judgment before
downstream generation, preserve user/self/source-person separation, and qualify
the integrated successor before Stage H/I/J migration. This bridge does not
revive the obsolete Phase 2 serving implementation or close those release gates.
