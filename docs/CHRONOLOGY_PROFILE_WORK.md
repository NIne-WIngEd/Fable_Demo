# Bounded chronological boundary diagnostic

The ordinary history gates remain incomplete. Published run `36778736018`
(head `8a8f41e26163aeb48f9b871fea6c198204a4d38e`) completed original-input
registration at 133.000 seconds and then reached the 60-minute job cap without
a first BEFORE capture-publication label. Run `36784876518` (head
`f3cddfd2b849b00580a95842e349e9f985505db8`) reached that same milestone at
70.981 seconds, again without the first capture-publication label before the
unchanged cap. These receipts justify a separate diagnostic; they do not show
where the remaining work finished or establish any AFTER seal or response.

`scripts/profile_selected_chronology_boundaries.py` runs exactly:

`test_selected_experiment_preregistration.SelectedPreregisteredPhaseRoutesTest.test_anchor_before_seal_actual_head_update_after_capture_final_seal_and_four_routes`

It imports the existing fixture unchanged, including its original real selected
XTDB/KurrentDB services and already supplied fictional producer and independent
qualification ports. It neither trains nor substitutes a model. Input-source
exclusions and the separately bound execution receipt retain their existing
meaning. All permission callbacks, canonical replays and terminal fences run
through their original installed functions.

## Observation and limits

The driver reuses the frozen transport observer, aggregate-only unittest result,
output suppression and cap exception. It adds fixed original synchronous code
objects for phase capture/slot capture, preregistration authorization/current
checks/history metadata, runtime context, context assembly and lineage. Original
direct closure code constants identify `capture_guard`, `personal_gate`, and the
fixture's declared-capture helper without creating or installing any callable.
The generator behind `_current_observations` is deliberately excluded.

The fixture first attempts an expected rejected AFTER capture. A generic
`phase.capture` count therefore cannot identify the first BEFORE attempt. The
first entry of its unchanged declared-capture helper occurs in the BEFORE loop.
The receipt reports this helper entry separately. It never treats return counts
as capture publication: the Python profile hook also reports exception unwinds
as returns. No seal, route, publication or response milestone is inferred from
aggregate counters.

Actual first BEFORE metadata, current guards and context assembly run in the
parent thread. The later owned passive-read workers are outside this observer's
coverage. `sys.setprofile` observes only the original synchronous parent thread;
other threads, child processes and coroutine/generator spans are not targeted.
Native work, scheduling and other-thread work contribute to wall residual or
RPC wait. Inclusive/exclusive wall and thread-CPU values are aggregate counts,
not precise native CPU attribution. Observation overhead itself can be material.

The 180-second diagnostic cap starts before unittest `setUp` and includes setup
and cleanup. Imports and target/source-hash collection precede the measured
span. The observer raises only before the next selected **outer** RPC entry,
when no observed RPC is active. An active or nested native call retains its
original timeout; CPU-only spans and cleanup can also overshoot the soft cap.
The separate workflow still has a 60-minute job cap. Setup may exhaust the soft
cap before the declared-capture helper is entered.

The JSON receipt records `qualification=false`, the unchanged **60000 ms**
protocol response budget, the separate soft cap, numeric outcome counts, helper
entry, aggregate fixed tags and before/after SHA256 hashes of loaded FloRA,
product-neutral contract and selected fixture sources. The driver and reused
observer are hashed too. Changed and newly loaded source modules are listed;
sources first loaded later have only the later file hash. The published Actions
head is recorded when available. An interrupted or failed diagnostic is marked
incomplete. Its measured timings never qualify physical response latency,
custody completion, learned behavior or experiment readiness.

Arguments, query values, locals, frames, tracebacks, payloads and error text are
not retained. Python and native fixture output are discarded through
`os.devnull`; unittest retains outcome counters instead of formatted failures.
The artifact contains only source hashes, fixed metadata/tags, clocks and counts.

## Optional real-engine workflow

`.github/workflows/chronology-profile.yml` supports manual dispatch and pushes
affecting the driver, this workflow or the measured permission/source/comparison
metadata modules through its path filters, including pushes that also change
other files. The measured-module filters were added after the first actual
aggregate identified repeated permission metadata work, so subsequent repairs
receive a new exact-commit diagnostic without changing the original case.
It uses the existing selected-service Compose file, Python 3.12 and the same
A.L.I.C.E. pin `4f287a488bc908bd04f99255ee01b794bacba50b`. Its diagnostic step
has `continue-on-error: true`; a green diagnostic workflow does not replace an
ordinary failed or cancelled gate. Only the aggregate JSON is uploaded. The
ordinary exhaustive workflow and all product budgets remain independent.

Focused component checks instantiate the exact original case and inspect its
code identities without running setup or the fixture body. They check component
reuse, unique direct closure selection, resumable-span rejection, cap validation,
source changes, honest incomplete/publication labels, hook restoration and
payload-free setup/failure/cap orchestration. No new local selected substitute
fixture is used. The first real diagnostic artifact remains pending publication.
