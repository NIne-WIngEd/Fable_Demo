# Fresh Experience replay with bounded envelope reuse

This infrastructure repair reduces repeated decoding of identical Experience
metadata. It builds no model and does not cache permissions, owner proofs,
qualification results, stream existence, committed history or payloads.

## What the measurement showed

The published `8a8f41e26163aeb48f9b871fea6c198204a4d38e` transport run still
exceeded the unchanged **10,000 ms** standalone response limit: BEFORE
**23,041 ms**, AFTER **31,976 ms**. The independent provider callback fixture
passed. Earlier controlled SQL profiles had bypassed the actual Kurrent codec.

The follow-up diagnostic executes the same selected paired fixture through
native `KurrentExperienceLog`, including encoded `NewEvent` metadata and actual
SDK `RecordedEvent` carriers. Only the engine transports and the fixture's
existing fictional producer ports are controlled. It stops immediately after
the same paired timing print, and has a 120-second cap at the controlled
transport boundary. It is not a physical backend qualification.

| Same complete controlled workload | Published source | Frozen candidate |
| --- | ---: | ---: |
| SQL statements | 6,120 | 6,120 |
| Fresh `get_stream` calls | 3,419 | 3,419 |
| Current records / encoded bytes read | 87,350 / 98,302,270 | 87,350 / 98,302,270 |
| Unique appended records | 35 | 35 |
| Actual envelope decodes | 87,350 | 35 |
| Total without cProfile | 19.139 s | 10.873 s |
| BEFORE / AFTER without cProfile | 6,841 / 9,402 ms | 3,534 / 5,795 ms |
| Total with cProfile | 60.039 s | 28.648 s |
| Native replay cumulative profiled time | 33.731 s | 3.059 s |

The final candidate performs 3,419 fresh eligibility checks, costing 0.878 s
cumulatively under cProfile, and creates 87,315 fresh envelope object graphs,
costing 0.549 s. Its profiled AFTER receipt still exceeds the response limit
(14,634 ms). None of these controlled timings proves that the real backend
meets the limit.

## The bounded native path

- Every call reads the actual stream again. Position, event type, envelope ID,
  scope and current commit time are still checked.
- Reuse applies only after a fresh helper/contract classification and an exact
  native SDK tuple of plain records: exact byte/string/integer/UUID fields and
  native UTC timestamps, or an absent timestamp. The current returned records
  are copied into a temporary primitive snapshot; their mutable aliases never
  become cached authority.
- The private per-owner memo contains at most 256 entries and 2 MiB of encoded
  keys. An entry contains only recursively immutable primitives from a
  successfully validated exact envelope. Oversized envelopes remain uncached.
- A hit constructs a fresh `ExperienceEvent`, `ProductHostScope`,
  `ProvenanceReference` and `CommittedExperience`. Mutating a prior returned
  object cannot alter the memo or a later replay.
- Client, stream or host-scope changes clear the memo. Owner, map and byte
  count publish together as one state. Copy-on-write maps preserve ordinary
  and custom Python copy protocols without shared-map accounting drift.
- Native decoder, UUID, contract, constructor, helper, constant and schema-key
  bindings remain live. Custom wrappers, records, generators, tuple subclasses,
  time objects and overrides execute the complete original uncached loop,
  preserving its actual receivers and callback order.

The first prototype performed this eligibility graph after every record getter.
It removed decoding but spent 31.871 s checking eligibility and was slower than
the baseline. The chosen native tuple path checks the graph once per fresh
stream read because its remaining operations have no custom callbacks. All
effectful paths retain the original loop. A harmless empty `copyreg`
`__slotnames__` addition is recognized without relaxing installed delegates.

## Verification and provenance

The focused Experience suites passed **24 tests**. Together with history,
provider custody, issued history and guarded-copy suites, **84 tests passed**
in 4.717 s; independent review reran the same 84 tests in 4.156 s. Cases cover
returned nested-object mutation, changed envelope bytes, physical checks after
warmup, helper and schema changes, private helper/code overrides, custom wrapper
withdrawal, iterator/time callbacks, transport callback withdrawal, cloned
memo eviction/accounting, and actual selected owner permission revocation.
The decode-count regression fails on the published source with `3 != 1`.

Baseline archive: local commit
`04f06b15c76a39cf2bd0e6bac37a7915ad5671fe`, exactly the published tree
`cf2fc78ea271eff42610cb8ec65da9055897c5c1`. The candidate is that immutable
tree plus the reviewed Experience source overlay; all actually loaded source
hashes were recorded and remained unchanged during each diagnostic.

Frozen `src/flora/selected/experience.py` SHA-256:
`6626d6494fd3385be5851a3b3babab9cc3e054b61b3a175b6185d6a2c2707a9b`.
The method trace is saved only in FloRA under `docs/fbm-seeds/`.
Fresh CI against the published candidate is required for physical latency,
restart and recovery qualification.

## Aggregate physical-boundary diagnostic

The published codec repair improved the physical paired receipts to BEFORE
**17,585 ms** and AFTER **22,604 ms**; both still exceed the unchanged 10,000 ms
limit. The provider callback fixture passed. Before another source repair, the
transport shard now reruns only the existing standalone comparator fixture
**after its ordinary gate fails**, as an independent diagnostic. The original
failed gate stays failed; all ordinary tests and response/RPC budgets stay intact.

The diagnostic observes original synchronous code objects with `sys.setprofile`:
actual Kurrent `get_stream`, psycopg `execute`/`fetchall`, and fixed replay,
decoder, policy, metadata and fence boundaries. It changes no callable. Its JSON
contains fixed tags, counts, inclusive/exclusive wall and thread CPU clocks, and
loaded source hashes. Wall minus thread CPU includes waiting, scheduling and
other-thread work; it is not an exact wire-time measurement. Fixture output goes
to `os.devnull`; unittest failures retain counts only, without tracebacks or text.

The **180-second soft cap** stops before the next outer selected RPC body. Nested
RPCs within an active observed RPC complete normally, using the original native
timeout. No signal, stack dump or asynchronous interruption is used. A delayed
return or lack of another RPC can exceed the cap; elapsed time and overshoot are
reported. Existing Python or reserved C profiler hooks cause a safe skip and
remain untouched; every installed diagnostic hook is restored after cleanup.

The same complete controlled workload took **9.930 s** without observation and
**34.297 s** with the frozen observer. Both made 6,120 SQL statements, 3,419 fresh
stream reads and read 87,350 records / 98,302,270 encoded bytes. The observed
native codec still decoded only 35 unique envelopes and materialized 87,315
fresh copies; all loaded production hashes stayed unchanged. Controlled engine
ports do not execute the actual SDK RPC bodies, so their observer counts are
zero in this local check. Physical CI supplies those counts. The substantial
profiler overhead is disclosed; profiled receipts cannot qualify latency.

Twelve observer regressions cover nested clocks, outer-entry cap deferral,
original code identity, hook restoration/refusal (including active Python 3.12
`cProfile`), resumable-code exclusion, payload-free outcome counts and Python/fd
output suppression. Together with codec and trace-contract checks, 36 tests
passed in 0.989 s. The procedure seed lives only in FloRA.
