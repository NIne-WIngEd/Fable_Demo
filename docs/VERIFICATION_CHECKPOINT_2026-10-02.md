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

The [shared source metadata collector](SHARED_SOURCE_METADATA_CAPS.md) now
extends the existing same-call nomination helper with separate source-DAG caps,
including overlapping domains with the same purpose. Existing pair callers
keep their behavior; no triple caller or shared serving frame is activated.
Raw-only dependencies invent no grants. The future H contributor must still
account for its physical manifest independently.

Testing exposed an existing classifier defect: replacing a reader on its class
could cause batching to skip that callback. Original reader identity/code and
the exact native owner are now required for batching. Custom readers run the
fallback, including fresh second-pass source/raw callbacks.

**90 controlled contract tests in five modules passed** on Windows/Python
3.12.14 with Alice API pin `4f287a48`: 21 shared-source metadata, 14 phase-source
fence, 25 history fence, 24 selected-history fence and 6 combined-purpose tests.
An independent reviewer reran all 21 new tests and verified the frozen source
hashes. Summed suite duration 28.614 s is test execution time, not response
latency. The [exact local receipt](evidence/2026-10-02_shared_source_caps_local_contracts.json)
preserves the test selection, source identity and failures/repairs.

The tested source was published at
`3a6e03cfeb2207a88f555c1fa88d10aad5bd987b` on
`codex/flora-shared-source-caps`, in
[draft PR #1](https://github.com/NIne-WIngEd/FloRA/pull/1).
Ordinary [run 37041602495](https://github.com/NIne-WIngEd/FloRA/actions/runs/37041602495)
checks merge commit `1573eeb47bf804ae7b06b98ffbe0472f04b57d5a`, whose complete
tree exactly matches that development commit. At 2026-10-02 17:40:19 UTC the
run remained in progress: guarded readers/writer faults passed 2/2 physical
cases and native pilot withdrawal passed its one case. Contracts and other
physical jobs were still pending completion. This partial observation is not
a completed same-commit gate, latency pass or behavioral result. Inspect the
run before replacing pending status with a completed receipt.

A [later partial observation](evidence/2026-10-02_3a6e03cf_partial_ci_receipts.json)
at 17:44:50 UTC records the completed response failures: standalone BEFORE
24,377 ms and AFTER 39,477 ms exceed 10,000 ms; native BEFORE 60,074 ms and
AFTER 60,141 ms time out against 60,000 ms. Reader and withdrawal cases remain
passed. Contracts and eight other physical jobs were still running. This helper
does not activate the serving optimization; response latency remains unresolved.

| Source | LF SHA-256 |
| --- | --- |
| `src/flora/selected/phase_source_fence.py` | `b0829cf3995179b37a0beaf7bf4d42f0f06833b636d52b3231a13962bbb50015` |
| `tests/test_shared_source_metadata.py` | `8af6bd2399666c7f8f6c13b23cb1b0b23fb0cc32e3941a6cef28907dd2102bfc` |
| `tests/test_history_fence.py` | `9b4f48dcba18cc69606a05040d2914a064eb629ffc9018ef23442e7267064989` |

The two preregistration modules import Unix-only `fcntl` through the existing
native worker and could not execute locally; no compatibility shim was used.
The ordinary Linux gate remains required. No local physical engines were run.
Shared initial-assembly and H/C/Claim/state frame integration, actual-engine
response qualification, learned judgment and builder transfer remain pending.

The public procedure ledger now has 97 schema-valid seeds. They describe
construction methods, not qualified FBM training cases or runtime personal
memory. Documentation and the helper establish no broader experimental pass.
