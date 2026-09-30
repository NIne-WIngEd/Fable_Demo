# Runtime custody and XTDB transaction mode

Private runtime registration prepares the exact immutable raw-reference and
invocation-stage rows before opening an idle, top-level XTDB transaction. A fresh
source/context guard runs immediately before that transaction. The transaction
contains only absence assertions and inserts; all pending rows commit together.
An existing caller transaction is refused, never committed or reused.

XTDB infers transaction mode from its first statement and prohibits mixing
ordinary queries with DML. A permission callback can query selected authority,
so calling it inside the write transaction either selects a read-only mode or
fails an explicit write mode. This is why a `BEGIN READ WRITE` override would
not repair the original failure.

The guard runs again immediately after commit, including on an idempotent
registration retry. Withdrawal during commit denies continuation, downstream
model invocation and accepted judgment. It does not undo an already canonical
Experience append or registered private receipt. Those partial records remain
available only through explicitly authorized recovery. Registration and
external/source consent are separate boundaries, not one atomic transaction.

The transaction-mode regression uses controlled SQL/producer fixtures and actual
encrypted custody. The real selected runtime and phase suites exercise the same
code against XTDB and Kurrent; only their completed physical CI qualifies that
backend path. Neither suite establishes learned MFM/personality behavior.

Source: [XTDB SQL transactions](https://docs.xtdb.com/reference/main/sql/txs.html).
