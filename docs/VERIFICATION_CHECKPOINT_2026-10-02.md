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

The owner's latest October 2 compute instruction prefers available Kaggle and
Magnolia for later eligible external-artifact or integration workloads, with
paid GPU hours only as the last fallback if those options fail. Current CPU
contract validation requires no GPU, and no GPU work is being launched now.
Personality and MFM remain in other chats. Provider details, quotas and new
infrastructure are not inferred.

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
At that source the shared serving frame remained pending; the prior CI confirms no latency
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
keep their behavior; at collector publication no triple caller or shared
serving frame was activated.
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
At collector publication, shared initial-assembly and H/C/Claim/state frame
integration, actual-engine response qualification, learned judgment and builder
transfer remained pending.

The public procedure ledger now has 97 schema-valid seeds. They describe
construction methods, not qualified FBM training cases or runtime personal
memory. Documentation and the helper establish no broader experimental pass.

## Completed collector CI at 3a6e03cf

The ordinary collector-only
[run 37041602495](https://github.com/NIne-WIngEd/FloRA/actions/runs/37041602495)
completed at 18:34:41 UTC with failure. Its
[completed receipt](evidence/2026-10-02_3a6e03cf_completed_ci_receipts.json)
supersedes the earlier partial observations above, while retaining them as
historical records. All 905 component cases in 76 modules passed; 50 of 53
physical cases passed, two response cases failed, and one history
preregistration case remained incomplete at the unchanged 60-minute cap.
The retained-history route completed this time.

These results belong to runtime
`3a6e03cfeb2207a88f555c1fa88d10aad5bd987b` and checkout
`1573eeb47bf804ae7b06b98ffbe0472f04b57d5a`, whose identical complete tree is
`a2ad365699f9c328635bf39acbcbf8019ac6152a`. They precede fresh-frame activation.
Standalone BEFORE/AFTER responses were 24,377 / 39,477 ms against 10,000 ms;
native responses timed out at 60,074 / 60,141 ms against 60,000 ms. Passing
contracts and more completed fixtures do not qualify these failed budgets.

## Fresh shared authority frame at 36f39b36 — failed candidate

The owner authorized integration of the fresh frame within FloRA's existing
narrow experimental slice. The development change now joins held-history H,
selected context C, current/immutable Claims and governed-state metadata in one
protected-boundary terminal observation. The
[updated protocol](SELECTED_AUTHORITY_FRAME_PROTOCOL.md) records the precise
ownership, separate caps and final ordering.

The runtime is published at
`36f39b36d3101a6af4e785fb60d382234db6409f`, tree
`3ef7a298432d81a08923e264ae36e95a0df9fb72`, on
`codex/flora-shared-source-caps` in
[draft PR #1](https://github.com/NIne-WIngEd/FloRA/pull/1).
Ordinary [run 37049792243](https://github.com/NIne-WIngEd/FloRA/actions/runs/37049792243)
is now in progress. The guarded reader job has passed. Native comparison
failed its one case: BEFORE 60,087 ms and AFTER 60,155 ms exceeded the unchanged
60,000 ms budget; the complete case duration was 212.594 s. This partial
observation preserves the response failure and is not a completed full gate.
Its actual checkout tree and remaining completed test results
must be verified before assigning exact-source correctness or physical
qualification. There is no completed full-runtime receipt yet.

New source files are `src/flora/selected/selected_authority_frame.py` and
`src/flora/selected/selected_history_contribution.py`. The context consumer
integrates them in `context_guard.py` and preflights dual issuance in
`selected_context.py`. Test additions are `test_shared_authority_frame.py` and
`test_selected_history_contribution.py`. All six published source/test hashes
were independently read before the pending opaque-guard repair:

| Source | LF SHA-256 |
| --- | --- |
| `src/flora/selected/selected_authority_frame.py` | `790091cc1589910d5a85b7650e63ab1f2c9046202b353d413b20ea369305a3c4` |
| `src/flora/selected/selected_history_contribution.py` | `12aa389e4b33bd0aa98b5c3d2b7c6435d225386020de38c45ac6b1182894be9b` |
| `src/flora/selected/context_guard.py` | `84877fc0101521f79dabfa9b0f4f787235e980b742d512228cf55ad54e4fa778` |
| `src/flora/selected/selected_context.py` | `c11d75502049966ae1949c2c7f696141b493fd4e7714e799a7ceee1c5d78b243` |
| `tests/test_selected_history_contribution.py` | `5e55d15f68af571ed6e0b50a8034c6606cab59d4ae1ddb49c6adf092eae9e803` |
| `tests/test_shared_authority_frame.py` | `3ede52a8972ab03c52ae14f6b02d9f43038ad2bfead82239ae85f12ffb9ed7e5` |

A native Linux/ARM64 final-source runner began at **18:54:22 UTC** against
`36f39b36`, checking all six hashes above at startup. It runs all **78 contract
modules in separate processes**, matching ordinary CI's isolation, and
prioritizes the two new modules. The runner uses image
`bbb524290db6a69edc7479eec6ee6a2d2b9946d5c0be0af86eb948575b5379e2`,
Python 3.12.15 and GLIBC 2.41 with the exact pinned dependencies. Imports,
including native `fcntl`, succeeded without a shim. The H contributor module
passed **19 controlled tests in 4.535 s**. The frame module then finished in
**930.594 s with 17/19 cases passing and two failures** at this exact source.
`test_final_callback_withdraws_selected_context_source` and
`test_final_callback_withdraws_unselected_history_evaluation_source` both
expected two independent guard calls but observed one. This is a failed
controlled frame gate, not a completed final-runtime pass.
The [source-pinned failure receipt](evidence/2026-10-02_36f39b36_frame_contract_failure.json)
preserves native environment, six hashes, exact assertion values and timings.
This runner completed only two of its 78 planned modules before the failure:
36/38 cases passed overall, including 19 H and 17 frame cases. Its complete
runner duration was 943.478 s; module/process/runner timings are distinct.

The failure is premature binding refusal: recursive `_FunctionBinding`
capture descended into the opaque external phase guard and froze its
closed-over counter. Its first legitimate call changed that state while the
guard's identity and code stayed fixed. The frame then rejected before the
required second callback. The pending repair limits recursive closure capture
to known pure context binding helpers, while separately retaining external
function identity/code and actual independent calls. Tests and response
budgets remain unchanged. The repaired source identity and its verification
are pending; this failed source and receipt must remain visible.

A local `_capture_context_binding` repair now limits that recursive capture
to known pure context helper closures. The two formerly failing selected C
and unselected H final-callback tests passed **2/2 in 68.205 s** on native
Linux/ARM64 with unchanged assertions. This is progress on an unpublished
local repair, whose final source receipt remains pending. The complete
19-case frame suite and new ordinary CI remain required; this subset does not
qualify the frame, physical correctness or response latency.

The earlier Linux/amd64 QEMU contributor selection passed 19 tests in 26.478 s.
Its frame and selected-context selections against candidate
`876e4177c8b67edea525b138620fbe0907c2cd72` were stopped incomplete after being
superseded by the final-source native runner. Candidate ordinary runs
[37049045405](https://github.com/NIne-WIngEd/FloRA/actions/runs/37049045405) and
[37049038903](https://github.com/NIne-WIngEd/FloRA/actions/runs/37049038903)
were intentionally canceled to free current CI slots. They are not new
qualification. The published follow-up changes only the frame's module/class
alias identity pins. An earlier exploratory full metadata case passed in
253.115 s before the final seals; it is not a final-source receipt. These are
controlled fixture durations, not response latency. The ordinary
published-source CI remains required.

The frame keeps `sample.permissions` and `state.policy` attached to the actual
gated runtime owner. Local copied predicates share native sampled material;
independent external callbacks and signed owner/qualification mechanisms must
remain live, including legitimate opaque guard state. H includes its custody
manifest under its own cap and every evaluation
grant, even for originals absent from C. C and each phase ancestry keep their
separate limits. Private reads keep four fresh checks; initial qualification
and assembly byte boundaries also construct new frames. A final physical pass
and joint XTDB observation follow the actual callbacks; only pure sealed
identity/native-value checks run afterward.

Original-service `assemble_context` traversal and opaque independent guards
remain intact and can still repeat history work. Immutable Claim/state row
sampling can also repeat within a frame. No connection pool, new memory ledger,
request-wide positive authority cache, full Alice infrastructure, personality
model or MFM is introduced. These are explicit remaining costs, not evidence
that response budgets have passed.

The new public method seed is
[the fresh-frame construction record](fbm-seeds/2026-10-02_fresh_shared_authority_frame.jsonl).
The [linked opaque-guard failure/repair record](fbm-seeds/2026-10-02_fresh_frame_opaque_guard_repair.jsonl)
preserves this failed 17/19 selection. The
[two-case repair progress seed](fbm-seeds/2026-10-02_opaque_guard_repair_subset.jsonl)
records the narrow passing subset without full qualification. All 101 procedure records pass the
existing shape validator, and the three
FBM-seed contract tests pass. The full implementation receipt remains pending.
The record is a procedure seed, not runtime personal memory,
a linked eligible FBM training case, a learned result or a transfer result.
The prior completed physical failures above remain authoritative
for their exact earlier sources. No complete physical gate, response-latency
or learned pass is claimed here.

## Current repair at ef9c190e — partial checkpoint before ending this turn

Published runtime `ef9c190e0688c2bb06dce5b12bbef06e6bd4f13f` has tree
`1f9b955849cbc69ed1f0244366876bbe672fd0c6`. Pure context closures remain
recursively sealed; native immutable guard-code pairs separately bind opaque
function identity/code while permitting legitimate internal state changes.
The two final withdrawal tests passed 2/2 in 73.007 s on native Linux/ARM64;
the new opaque guard code-swap test passed 1/1 in 10.439 s. Earlier 68.205 s
progress belongs to source fingerprint `82c784b`, before final code pins.
The failed `36f39b36` frame receipt remains preserved above.

| Final source | LF SHA-256 |
| --- | --- |
| `src/flora/selected/selected_authority_frame.py` | `73302f5edb934dc536c16ac7554a084ff85f604d8e6ad2f4eae3e0def7c2a197` |
| `src/flora/selected/selected_history_contribution.py` | `12aa389e4b33bd0aa98b5c3d2b7c6435d225386020de38c45ac6b1182894be9b` |
| `src/flora/selected/context_guard.py` | `84877fc0101521f79dabfa9b0f4f787235e980b742d512228cf55ad54e4fa778` |
| `src/flora/selected/selected_context.py` | `c11d75502049966ae1949c2c7f696141b493fd4e7714e799a7ceee1c5d78b243` |
| `tests/test_selected_history_contribution.py` | `5e55d15f68af571ed6e0b50a8034c6606cab59d4ae1ddb49c6adf092eae9e803` |
| `tests/test_shared_authority_frame.py` | `6adaae62780b1fabda5e9e39c041d8849797206f4433822c807de57683300552` |

The 20-case frame suite and separate 76-existing-module selection began at
19:32:58 UTC on native Linux/ARM64, using the same pinned image/dependencies
recorded above. The frame suite is still pending. The existing-module runner
halted at **19:37:32 UTC** after **35/76 modules** and **478 cases: 476 passed,
one failed, one errored**. Forty-one modules were not run. Its
[safe source-pinned receipt](evidence/2026-10-02_ef9c190e_existing_contract_failure.json)
preserves all module counts and fixed diagnostics without fixture content.

`test_native_worker.py` ran 11 cases in 1.765 s: nine passed, one failed and
one errored. `test_output_cap_and_exit_failure_have_safe_receipts` expected
`exit_failure` but received `worker_rejected`;
`test_stderr_limit_and_no_inherited_environment` raised
`NativeWorkerFailure: worker_rejected`. `asyncio.InvalidStateError` and
transport resource warnings also appeared. Worker code/tests are unchanged,
but the cause is **unresolved**; neither an environment-only cause nor a frame
regression is established. The broad local gate failed and requires
investigation, not a full-pass claim.

Ordinary [run 37054784829](https://github.com/NIne-WIngEd/FloRA/actions/runs/37054784829)
checks merge `2f166a9d745667b200302a404bd04f8def7a83d9`, whose complete tree
exactly matches the published runtime. At **19:38:11 UTC**, its
[partial receipt](evidence/2026-10-02_ef9c190e_partial_ci_receipts.json) records
readers 2/2 and withdrawal 1/1 passing; native comparison failed at
60,061 / 60,108 ms against the unchanged 60,000 ms budget. Three of 53
physical cases passed, one failed, and 49 remained pending. Component
contracts, transport and other jobs had no completed full receipt. No
standalone response measurement is inferred while transport remains pending.

Resume by collecting both local JSON receipts in this continuation workspace:
`work/frame-contracts-repaired-frame/receipt.json` and
`work/frame-contracts-repaired-existing/receipt.json`. Original tool sessions
were 25400 (frame) and 67177 (existing), if still available; receipts are the
durable source. Collect ordinary CI's completed exact-source jobs, investigate
the two worker issues, then address the 41 unrun modules. A fresh H contributor
19-case run at the repaired source is optional when needed to complete the
selection; its files are unchanged. Do not infer completion from a still
running frame suite or dispatch extra runners merely to keep this turn open.

The linked [final code-pin progress seed](fbm-seeds/2026-10-02_opaque_guard_code_pin_progress.jsonl)
records these source distinctions and partial outcomes. All 101 method seeds
are schema-valid, and the three FBM contract tests pass. Method seeds remain
procedure-only records, not qualified training cases. Physical correctness,
response latency, learned judgment and FBM transfer remain unqualified.

The owner's latest direction is to measure the remaining latency cause before
another serving change, use the existing research branches/plugins and
Graphify where useful, and consult relevant frontier/competing-system primary
research and open-source implementations. Record the applicable mechanism and
predicted effect, then test it against the same physical clocks and authority
contracts. This is a next-step requirement, not a completed research receipt.
