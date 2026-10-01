# Original native worker aggregate diagnostic

The completed native comparison still exceeds its unchanged **60,000 ms** phase
budget while preparation awaits owned context authorization. Existing transport
and chronology observations measure the parent thread. They cannot attribute
work inside the actual reader's ThreadPoolExecutor.

This optional diagnostic runs exactly
`test_selected_native_comparison.SelectedNativeComparisonIntegrationTest.test_actual_phase_context_execution_parent_and_private_run_custody`
with the original fixture, selected engines, supplied fictional producer
receipts and timeout/budget settings. No runtime delegate is wrapped or replaced.
No model or substitute is built. Every timing is **nonqualifying** because
observation adds overhead.

## What is measured

The future-thread dispatcher recognizes only the exact original ordinary `work`
code constant inside `SelectedNativeReadServices._read`. It starts a separate
numeric ledger for each classified thread. Fixed tags cover prepare/authorize
context actions, phase setup and consent guards, runtime context, lineage checks,
and existing selected SQL, Kurrent, history, source and permission boundaries.

Each ledger retains bounded numeric counters, clocks and a fixed tag stack.
It never retains call frames, tracebacks, exceptions, arguments, local values,
request/response bytes, SQL, thread names/IDs or Thread objects. `threading.local`
assigns ledgers without confusing reused OS thread IDs. At most 32 worker ledgers
and 256 tagged stack entries per ledger are retained; overflow makes coverage
incomplete rather than changing a read.

Worker thread CPU is sampled by that worker. Its wall/CPU window can include
idle or untagged work between owned jobs and is separate from the fixed-tag
inclusive/exclusive totals. Worker wall spans can overlap; they must not be
added to the parent's elapsed time. Returns can include exception unwinding and
are not authorization, publication or model-quality evidence.

## Hooks, surviving workers and optional cap

The diagnostic refuses occupied parent/future-thread profile hooks and any
reserved monitoring tool. It never installs a hook in preexisting threads and
never uses `setprofile_all_threads`. On exit it closes recording and restores
only its own parent and future-thread hook identities. A later replacement is
left untouched.

A surviving thread can retain the closed, inert dispatcher while idle or blocked
in C. On its next Python profile event it removes only that dispatcher. No read
is cancelled, joined, waited for or stopped by observation. Open spans are
reported incomplete and closed numerically at that thread's last sample; another
thread's CPU clock is never substituted. Queued jobs entering only after the
observer closes are outside coverage.

The workflow and CLI default to a **180-second** parent-only soft cap. The CLI
accepts only a positive finite value at or below that bound. It stops only before the next approved outer parent RPC
when both the observed RPC depth and active classified owned-work count are
zero. It never raises in a worker or during an active observed RPC or owned
CPU-only span. Original fixture cleanup can overshoot; the cap does not shorten
backend, read or response deadlines. If setup consumes the cap before any owned
marker is entered, the aggregate reports zero owned entries; it does not claim
that the native authorization path was measured.

The fresh CLI discards Python/fd fixture output through normal interpreter exit,
including late worker output. It writes only the aggregate artifact and a fixed
status through the saved console fd. The process may remain alive until original
workers finish naturally. It does not force process exit or bypass cleanup.

## Qualification boundary

Focused ordinary-thread checks verify separate stacks/clocks, occupied-hook
refusal, preservation of replacements, deferred survivor removal, no recording
after close, bounded ledgers/stacks, cap deferral, numeric privacy and late-output
suppression. They test observation mechanics only. They do not replace the
original selected-engine fixture or qualify its latency.

The optional workflow must still produce an exact published-head aggregate from
actual selected engines. Receipts include fixed fixture ID, unchanged budget,
source hashes before/after, cap state, outcome counts and incomplete-coverage
counters. They cannot establish learned memory/personality advantage or explain
unobserved native work and scheduling as if those were measured CPU costs.
