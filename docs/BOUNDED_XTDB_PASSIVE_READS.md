# Bounded local XTDB passive reads

`BoundedXTDBReadOpener` is a concrete connection opener for `InitializedNativeSessionFactory`. It supplies Linux socket deadlines for the local selected XTDB TCP connection. The factory still needs its independently qualified initialized-service binder and exact source/configuration hashes.

## What it binds

- One explicit numeric `hostaddr`, port, database, username and nonempty password value. The opener supplies these directly to psycopg; it reads no environment variables or password file. A local trust-authenticated endpoint may ignore the explicit password.
- The exact psycopg version, disabled prepared plans and autocommit. The configuration's canonical digest and module artifact digest must remain unchanged. Dependency/deployment qualification is separate from these hashes.
- A connect timeout of at least two seconds, one SELECT deadline and a deadline for the entire owned session. Waiting for an opener slot and connection setup consume the session allowance too. A connect attempt requires enough remaining time for libpq's two-second minimum.
- A fixed maximum number of concurrent sessions. A slot retires only after the reader thread closes psycopg and the physical watchdog finishes.

The current opener explicitly uses `sslmode=disable` for the local selected backend. Remote TLS endpoints need a separately supplied and qualified deployment opener; this module does not infer certificate files or connection credentials.

## How physical timeout works

Each owned connection has one watchdog and one retained duplicate of its actual libpq socket. The duplicate names the same open-file description even if the original descriptor is later closed or recycled.

The owning reader thread announces a query deadline before calling psycopg. When a SELECT or the total session expires, the watchdog marks that session poisoned and shuts down the retained socket. That wakes a driver blocked on its response. The watchdog never calls psycopg, closes its connection, retries SQL or writes custody. The owner thread closes the driver.

A completed query clears its own deadline. A timed-out or failed session cannot dispatch another query. Cleanup disarms and joins the watchdog within its frozen cleanup allowance. If cleanup is late, the duplicate and the opener slot stay owned until physical retirement; new opens cannot accumulate watchdogs. A raising driver close cannot prove physical retirement: its socket is shut down and its opener slot remains sealed rather than allowing more unproven sessions. A fresh explicitly qualified opener is needed after that cleanup fault. Error messages contain only public failure categories, never driver errors, SQL parameters or credentials.

The driver facade and the outer `ReadOnlyNativeSQLConnection` both accept the existing single-SELECT templates and reject stacked statements. This is a narrow guard for qualified selected-store code, not a general SQL parser. The actual backend role and transitive opener/binder code still require deployment qualification.

## Validation

- Ten mechanical tests use actual sockets with an explicitly fictional driver. They cover a physically stalled read, successful-query disarming, whole-session expiry, poisoning without retries, owner-thread close, read-only guards, sanitized errors, explicit connection parameters, a late watchdog that keeps its slot and duplicate, a driver-close fault that never releases an unproven physical slot, and failed watchdog setup combined with a raising driver close. The failed-setup path also shuts down retained traffic and preserves its opener slot until driver retirement is proven.
- `test_selected_bounded_xtdb_read_faults.py` is a real psycopg/XTDB gate. A controlled TCP relay completes connection setup, then blackholes a SELECT response. The test cancels the awaiting passive callback, checks that its slot remains owned until the driver physically stops, and verifies connection/watchdog cleanup, later slot reuse and unchanged synthetic XTDB data. It must pass selected-engine CI before this is called a qualified backend fault result.

These tests establish deadline and ownership mechanics. They do not measure model latency, supply a model, authorize a source, or demonstrate the FloRA experiment's behavioral claim.

API references: [psycopg connection and socket API](https://www.psycopg.org/psycopg3/docs/api/connections.html), [libpq numeric hostaddr and connection timeout contract](https://www.postgresql.org/docs/17/libpq-connect.html).

Procedure seed: [bounded XTDB reads](fbm-seeds/2026-09-30_flora_bounded_xtdb_passive_reads.jsonl).
