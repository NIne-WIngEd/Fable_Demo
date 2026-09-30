"""Actual PGconn blackhole bounds; supplied fictional ownership proof only.

This gate does not qualify an exclusive deployment factory or model behavior.
"""
import hashlib
import os
import time
from types import SimpleNamespace
import unittest
import uuid

import psycopg
from psycopg.conninfo import conninfo_to_dict
from cognitive_kernel.canonical import canonical_sha256
from cognitive_kernel.contracts import ProductHostScope
from flora.selected.claims import configure_xtdb_connection
from flora.selected.native_writer_guard import (
    NativeWriterConfiguration, NativeWriterGuard, VerifiedNativeWriterOwnership,
)
from test_selected_bounded_xtdb_read_faults import _SelectedTCPRelay


class SelectedNativeWriterFaultTest(unittest.TestCase):
    def test_real_blocked_pgconn_exits_on_owner_without_late_sql_continuation(self):
        dsn = os.environ.get("XTDB_DSN", "postgresql://xtdb@127.0.0.1:5432/xtdb")
        parameters = conninfo_to_dict(dsn)
        control = psycopg.connect(dsn, autocommit=True, connect_timeout=2, prepare_threshold=None)
        self.addCleanup(control.close)
        configure_xtdb_connection(control)
        row, late = "native-write-fault-" + uuid.uuid4().hex, "native-late-" + uuid.uuid4().hex
        control.execute("INSERT INTO flora_native_write_fault_fixture (_id, fixture_value) VALUES (%s, %s)",
            (row, "public synthetic fixture"))
        relay = _SelectedTCPRelay(hostaddr=control.info.hostaddr, port=int(control.info.port))
        self.addCleanup(relay.close)
        writer = psycopg.connect(host="127.0.0.1", hostaddr="127.0.0.1", port=relay.port,
            dbname=control.info.dbname, user=control.info.user,
            password=parameters.get("password") or "explicit-selected-trust-fixture", passfile="/dev/null",
            sslmode="disable", connect_timeout=2, autocommit=True, prepare_threshold=None)
        self.addCleanup(writer.close)
        configure_xtdb_connection(writer)
        scope = ProductHostScope.create(product_id="friday", host_instance_id="native-writer-fault-fixture",
            schema_version="1.0.0", encryption_domain="native-writer-fault-key")
        configuration = NativeWriterConfiguration(scope, "native-writer-fault-namespace", "fixture-exclusive-owner",
            psycopg.__version__, "a" * 64, 800, 1000)
        # Explicitly supplied contract proof, not genuine exclusive-factory enrollment.
        verifier = SimpleNamespace(verify_native_writer=lambda *, request, receipt:
            VerifiedNativeWriterOwnership("fixture-qualifier", "fixture-qualification",
                canonical_sha256(request), hashlib.sha256(receipt).hexdigest(), True))
        guard = NativeWriterGuard(connection=writer, configuration=configuration, verifier=verifier,
            qualification_receipt=b"supplied fictional owner qualification", qualifier_id="fixture-qualifier",
            qualification_id="fixture-qualification")
        guard.verify_identity()
        relay.pause_responses.set()
        began = time.monotonic()
        with self.assertRaises(TimeoutError):
            with guard.operation(remaining_seconds=2) as lease:
                lease.require_active(writer)
                writer.execute("SELECT * FROM flora_native_write_fault_fixture WHERE _id = %s", (row,)).fetchall()
                writer.execute("INSERT INTO flora_native_write_fault_fixture (_id, fixture_value) VALUES (%s, %s)",
                    (late, "must never execute"))
        self.assertTrue(relay.response_blocked.is_set())
        self.assertLess(time.monotonic() - began, 2)
        self.assertTrue(writer.closed)
        self.assertIsNone(guard._active)
        with self.assertRaises(PermissionError):
            guard.operation(remaining_seconds=1)
        self.assertEqual(control.execute("SELECT * FROM flora_native_write_fault_fixture WHERE _id = %s", (late,)).fetchall(), [])
        time.sleep(.05)
        self.assertEqual(control.execute("SELECT * FROM flora_native_write_fault_fixture WHERE _id = %s", (late,)).fetchall(), [])


if __name__ == "__main__":
    unittest.main()
