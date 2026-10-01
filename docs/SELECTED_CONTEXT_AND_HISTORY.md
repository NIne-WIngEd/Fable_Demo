# Selected context and history consumers

This is the consumer step after [selected source closure](SELECTED_SOURCE_CLOSURE.md).
It follows the [source-grounded architecture direction](LATENCY_ARCHITECTURE_RECALIBRATION_2026-10-01.md):
retrieve the evidence a situation needs, while keeping its current authority.
It does not activate every memory plane on every turn.

## Explicit domains

| Consumer | Default | Opt-in | What the opt-in checks |
| --- | --- | --- | --- |
| Current held-history metadata | `whole-stream-history-metadata-v1` | `selected-history-metadata-v1` | Every held original, its registered parents, the exact physical manifest, and current evaluation grants |
| Current private context | `whole-stream-current-context-v1` | `selected-current-context-v1` | Nominated exact Claims, governed state without episodes, original/control source closure, live grants, current authority and private-read barriers |

Opt-in requires an explicit positive source cap. Parents count toward the cap;
history also counts its manifest. Missing or excessive closure fails. It is
never truncated into success and never falls back to a broader reader.
Defaults retain their existing behavior.

The selected domains check the relevant physical records. They do not establish
the integrity or duplicate absence of unrelated records elsewhere in a stream.
Initial history authentication, recovery and archive operations retain their
separate custody checks. Exact Kurrent reads and terminal XTDB observations
are not an atomic transaction across engines or a permission lease.

## History

- Read the actual immutable artifact row and its persisted source locator.
- Check the manifest and held originals against fresh physical Kurrent records.
  Full digest, scope, position and original recorded time must match.
- Preserve the exact ordered original IDs. Parents must belong to those
  originals and precede their children; all originals precede the manifest.
- Reconstruct the writer's exact manifest and bind its digest, raw reference
  and size. Metadata verification opens no encrypted object bytes.
- Check evaluation rights for **all held originals**, including ones that a
  context does not select. Manifest custody does not invent an extra manifest
  evaluation grant.
- Re-read after callbacks and finish with one shared XTDB observation of the
  artifact, source, raw-reference, permission-head and action rows. Combined
  external-disclosure checks share this fence rather than accepting an earlier
  proof and running more callbacks after it.

```python
evidence = SelectedRunEvidencePolicy(
    custody=custody, run_id=run_id, permissions=permissions,
    history_metadata_domain="selected-history-metadata-v1",
    maximum_history_sources=source_cap,
)
```

Issued held-history authentication captures the domain, cap and target readers.
Changing them invalidates reuse. Native phase membership uses the original
physical log and held **original input IDs**. Internal receipts cannot become
extra BEFORE evidence.

## Context

- Nominate evidence from exact current Claim relations and governed state.
  Retain their current heads, approval, activation and rollback authority.
- Resolve the finite nomination and its parents on the original Kurrent owner.
  The finite view supplies metadata to existing context checks; it cannot
  append, provide a canonical stream revision or represent a full log.
- Re-resolve current source authority at protected boundaries. Keep independent
  owner authentication and checks around both ciphertext and plaintext reads.
- Preserve the actual native phase gate. Unknown custom authority overrides
  reject explicit selection before private I/O; they are never discarded.
- Finish current checks after callbacks, including Claims, governed state,
  original/control sources and grants. A late correction or withdrawal must
  prevent stale private material from returning.
- Keep held context content and route bindings pinned. After the terminal
  observation, only pure binding and native-value comparisons run; mutable
  JSON helpers and authority callbacks cannot reopen a stale-proof window.

```python
runtime = FloRAExperimentRuntime(
    # Existing selected services, producer bindings and independent verifiers.
    ...,
    context_integrity_domain="selected-current-context-v1",
    maximum_context_sources=source_cap,
)
```

The current selected context slice accepts frozen exact Claim/state routes.
Episode-bearing state fails before private I/O: episode custody still needs a
physical-position-aware sparse contract. Optional vector/graph nomination is
not yet integrated into this domain. Those existing paths remain available in
the default consumer. This is infrastructure selection, not a learned planner.

## Qualification

The standalone comparator and passive native comparison explicitly opt in to
exercise the consumer path. Other pilot and phase-route fixtures retain the
default as regression coverage. Source inputs, question/context budgets, clocks,
scientific phase boundaries and workflow limits stay unchanged.

Controlled SDK/SQL fixtures establish contract behavior, not physical latency.
Actual selected-engine receipts and failures belong to their exact published
commit and are recorded in the [verification checkpoint](VERIFICATION_CHECKPOINT_2026-10-01.md).
The response limits remain **10,000 ms** standalone and **60,000 ms** native;
ordinary CI jobs retain their **60-minute** caps.

Personality and MFM remain in their separate workstreams. No model training,
substitute judgment, learned behavior win or builder transfer is produced here.
Construction procedure seeds stay in FloRA only.
