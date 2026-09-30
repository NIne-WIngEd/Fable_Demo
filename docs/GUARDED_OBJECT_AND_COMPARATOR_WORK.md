# Guarded copies and comparator metadata work

The c615 implementation's actual standalone comparator exceeded its unchanged
10,000 ms response budget: BEFORE 23,210 ms and AFTER 31,362 ms in
[run 36767672665](https://github.com/NIne-WIngEd/FloRA/actions/runs/36767672665).
These repairs remain candidates until a new implementation commit passes the
actual engine gates.

## Keep copies from adding the same guard again

`_GuardedObjects` and `_CheckedObjects` previously reran their guard-installing
constructors during shallow copy. A get invoked the same current check
4, 6, 8, 10, then 12 times across guarded copies; checked copies started at 6
and grew in the same way.

- Copy the facade, its owned object plane, and its top backend wrapper without
  installing the same guard again. Retain every distinct nested guard.
- Keep the installed `check` immutable. Its callback still reads current
  authority on every invocation.
- Keep actual owner withdrawal before target AEAD for get, put, and reference
  recovery, including after repeated copies.
- A new actual typed regression fails with the old constructor: 6 checks
  instead of 4, and 8 instead of 6. The repair retains 4/6 checks and 12/18
  controlled SQL reads per copied get.

The standalone paired fixture does **not** call either copy method. Its SQL
count therefore does not improve from this repair. The copy correction protects
guarded chronological/coordinator paths from accumulating work.

## Combine observations inside one fresh recorder guard

The recorder sampled evaluation and external permissions separately even
within the same `current()` call. The combined path now:

- Creates its own fresh sample for that call and binds the actual custody,
  registry, permission owner, connection, scope, and namespace.
- Discovers and checks each purpose's source and ancestor closure separately.
  An evaluation grant never becomes an external disclosure grant.
- Keeps both actual history manifest metadata reads and both canonical
  replays, source/raw checks, predicates, and final authority callbacks.
- Checks all observed source, raw, action, head, and actual history manifest
  rows together after the last callback. A later callback cannot revoke an
  earlier evaluation grant or change/remove the manifest unnoticed.
- Uses shared observations only for genuine native delegates. Instance, class,
  and module decoder overrides, a custom public history verifier, or a distinct
  disclosure permission owner retain the complete original path.

No caller supplies a sample, permission answers are not retained, and no route
can skip the terminal fence. The existing single-purpose history API remains
fresh and always fenced.

## Measured scope

An immutable local source snapshot of `fe5f9ff` has the same tree as remote
`c6150be`. The existing selected integration setup and paired attempts were
profiled through their timing label, before later recovery assertions. Actual
selected algorithms, grants, crypto, and existing fictional supplied ports ran;
row/log transports and local Qdrant were controlled.

| Controlled work | c615 source | Five-file repair candidate |
|---|---:|---:|
| SQL for setup and paired attempts | 7,254 | 6,120 |
| SQL within recorder | 3,472 | 2,338 |
| SQL for one combined history/external check | Separate guards | 9 |

The candidate's profiled controlled attempts took 8,331/13,403 ms. AFTER still
exceeded the frozen budget. These counts and cProfile times are diagnostic
evidence; they do not qualify physical XTDB latency or learned behavior.

Tests use actual typed selected services and enrolled-owner actions to exercise
withdrawal, raw and manifest row mutation/removal, delegate/connection changes,
custom public denial, and distinct permission owners. The focused combined
suites passed 68 tests; independent review reproduced those passes. Copy and
provider custody review passed 18 tests. The saved
[FloRA procedure trace](fbm-seeds/2026-09-30_flora_guarded_copy_and_purpose_union.jsonl)
records source hashes and qualification limits.
