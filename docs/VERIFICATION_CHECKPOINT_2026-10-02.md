# FloRA verification checkpoint — 2026-10-02

## Recovered baseline

Repository baseline: `main@885be57abb582510d27a98177facd2a358c11387`.
Last runtime publication:
`74f42417be37a2fbdc6c603a1ea657b040e0052e`.
The [October 1 checkpoint](VERIFICATION_CHECKPOINT_2026-10-01.md) preserves
earlier evidence. This receipt updates its stale pending status; no earlier
failure is removed.

The owner's October 2 instruction narrows FloRA to the experiment's necessary
Alice-aligned slice. [FLORA_CONTEXT.md](FLORA_CONTEXT.md) records current scope,
the previous continuation and [Alice's connected ledger design](ALICE_INFRASTRUCTURE_MAP.md).
Documentation changes establish no runtime or behavioral qualification.

## Completed ordinary CI at 74f42417

[Run 36828262948](https://github.com/NIne-WIngEd/FloRA/actions/runs/36828262948)
started at 2026-10-01 07:04:41 UTC and has **completed with failure**.
Its 13 jobs were read through current GitHub job records and decoded logs.
Compact safe case summaries and exact job links are preserved in
[the completed receipt](evidence/2026-10-02_74f42417_completed_ci_receipts.json).
No new workflow or diagnostic was dispatched to obtain this receipt.

| Job group | Completed observation |
| --- | --- |
| Contracts | 884 tests in 75 modules passed, including all 18 phase-origin descriptor tests |
| Core | All 38 physical cases passed; the job's existing authority and persistent Temporal restart steps also succeeded |
| Transport | 1/2 cases passed; standalone response BEFORE 17,471 ms and AFTER 28,082 ms exceeded the unchanged 10,000 ms limit |
| Native comparison | 0/1 passed; BEFORE 60,072 ms and AFTER 60,142 ms timed out against 60,000 ms; complete case duration 199.182 s |
| Native pilot before-tail | 1/1 passed, 2,150.790 s fixture duration |
| Native pilot outcome-audit | 1/1 passed, 1,547.685 s fixture duration |
| Native pilot typed-phase | 1/1 passed, 3,261.212 s fixture duration |
| Native pilot withdrawal | 1/1 passed, 139.256 s fixture duration |
| Lineage | 2/2 passed, 1,768.615 s total fixture duration |
| Guarded readers/writer faults | 2/2 passed, 101.812 s total fixture duration |
| History | Coordinator case passed, 106.223 s. Preregistration registered originals in 101.266 s, but its case did not complete before the one-hour job cap |
| Retained history routes | No completed case before the unchanged one-hour job cap |
| Native history routes | 1/1 passed, 2,167.184 s fixture duration |

That is **49/53 physical cases passed**, **two failed response budgets**, and
**two incomplete cases**. Fixture durations include work outside an ordinary
response and are not consumer latency. A green descriptor/correctness case
does not qualify the failed response path.

The descriptor implementation makes no check bypass or proof-sharing change.
The shared serving frame remains pending; the prior CI confirms no latency
improvement. Models, learned behavior, real-host benefit and FBM transfer remain
unqualified.

## This continuation

The context and build map now explicitly separate the narrow prototype from
the complete product. Scope is preserved in a root continuation guide and a
source-pinned ledger/mission map. Existing useful components remain inventory;
completing every full-product lane is not a prerequisite.

The next runtime step extends the existing same-call multi-purpose row
nomination helper with separate source-closure caps. It adds no service, ledger,
storage engine or full memory platform. It cannot authorize a private read or
establish a response-latency pass. Its exact implementation and validation
receipt will be added here once completed.
