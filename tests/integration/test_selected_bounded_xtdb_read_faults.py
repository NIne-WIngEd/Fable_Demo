"""Real XTDB/psycopg SELECT blackhole; no model or behavioral result.

The explicit selected-test DSN is used only to derive this local relay fixture.
No production opener reads an environment variable or logs a credential/query.
"""
import asyncio
import os
import socket
import sys
import threading
import time
import unittest
import uuid

import psycopg
from psycopg.conninfo import conninfo_to_dict

from flora.selected.bounded_xtdb_reads import (
    BoundedXTDBReadConfiguration, BoundedXTDBReadOpener, ExplicitXTDBReadCredentials,
)
from flora.selected.native_reads import ReadOnlyNativeSQLConnection
from flora.selected.native_worker import OwnedPassiveReads
from flora.selected.claims import configure_xtdb_connection


class _SelectedTCPRelay:
    """One bounded fixture connection; blackholed bytes are never retained."""
    def __init__(self, *, hostaddr, port):
        self.endpoint = (hostaddr, port)
        self.stop, self.pause_responses, self.response_blocked = (threading.Event() for _ in range(3))
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.listener.settimeout(.1)
        self.port = self.listener.getsockname()[1]
        self.connections, self.pipes = [], []
        self.thread = threading.Thread(target=self._serve, name="flora-selected-fault-relay", daemon=True)
        self.thread.start()

    def _copy(self, source, destination, *, responses):
        while not self.stop.is_set():
            try:
                data = source.recv(65536)
                if not data:
                    break
                if responses and self.pause_responses.is_set():
                    self.response_blocked.set()
                else:
                    destination.sendall(data)
            except socket.timeout:
                continue
            except OSError:
                break

    def _serve(self):
        client = None
        while not self.stop.is_set() and client is None:
            try:
                client, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
        if client is None:
            return
        try:
            backend = socket.create_connection(self.endpoint, timeout=2)
        except OSError:
            client.close()
            return
        self.connections.extend((client, backend))
        for connection in (client, backend):
            connection.settimeout(.1)
        for source, destination, responses in ((client, backend, False), (backend, client, True)):
            pipe = threading.Thread(target=self._copy, args=(source, destination),
                kwargs={"responses": responses}, name="flora-selected-fault-pipe", daemon=True)
            self.pipes.append(pipe)
            pipe.start()

    def close(self):
        self.stop.set()
        self.listener.close()
        for connection in self.connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()
        self.thread.join(2.5)
        # An accept/connect completing during close cannot leave an unowned fd.
        for connection in self.connections:
            connection.close()
        for pipe in self.pipes:
            pipe.join(.5)
        if self.thread.is_alive() or any(pipe.is_alive() for pipe in self.pipes):
            raise AssertionError("selected fault relay did not physically retire")


@unittest.skipUnless(sys.platform == "linux", "retained-socket watchdog requires Linux")
class SelectedBoundedXTDBFaultTest(unittest.TestCase):
    def test_real_select_blackhole_releases_cancelled_physical_reader_without_late_mutation(self):
        # This is the existing explicit selected-test endpoint, not discovery.
        dsn = os.environ.get("XTDB_DSN", "postgresql://xtdb@127.0.0.1:5432/xtdb")
        parameters = conninfo_to_dict(dsn)
        control = psycopg.connect(dsn, autocommit=True, connect_timeout=2, prepare_threshold=None)
        self.addCleanup(control.close)
        configure_xtdb_connection(control)
        row_id = "flora-read-fault-" + uuid.uuid4().hex
        control.execute("INSERT INTO flora_selected_read_fault_fixture (_id, fixture_value) VALUES (%s, %s)",
                        (row_id, "public-synthetic-fixture"))
        relay = _SelectedTCPRelay(hostaddr=control.info.hostaddr, port=int(control.info.port))
        self.addCleanup(relay.close)
        config = BoundedXTDBReadConfiguration("127.0.0.1", relay.port, control.info.dbname,
            control.info.user, psycopg.__version__, 2, 800, 5000)
        opener = BoundedXTDBReadOpener(configuration=config,
            credentials=ExplicitXTDBReadCredentials(parameters.get("password") or "explicit-selected-trust-fixture"))
        ready, release_query, physically_closed = (threading.Event() for _ in range(3))
        observed, connections = [], []
        query_started = []
        def read():
            raw = opener(read_timeout_ms=2500)
            connection = ReadOnlyNativeSQLConnection(raw, read_timeout_ms=2500)
            connections.append(raw)
            try:
                configure_xtdb_connection(connection)
                connection.execute("SELECT 1").fetchone()
                with self.assertRaises(PermissionError):
                    connection.execute("DELETE FROM flora_selected_read_fault_fixture")
                ready.set()
                if not release_query.wait(2):
                    raise AssertionError("selected fault query was not released")
                query_started.append(time.monotonic())
                try:
                    connection.execute("SELECT fixture_value FROM flora_selected_read_fault_fixture WHERE _id = %s",
                                       (row_id,)).fetchone()
                except TimeoutError:
                    observed.append("timeout")
                else:
                    raise AssertionError("blackholed selected result was accepted")
            finally:
                connection.close()
                physically_closed.set()

        async def wait_event(event, seconds):
            deadline = asyncio.get_running_loop().time() + seconds
            while not event.is_set() and asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(.005)
            self.assertTrue(event.is_set(), "selected physical fault checkpoint did not complete")

        async def exercise():
            pool = OwnedPassiveReads()
            first = asyncio.create_task(pool.run(read))
            second = None
            try:
                await wait_event(ready, 3)
                relay.pause_responses.set()
                release_query.set()
                await wait_event(relay.response_blocked, .7)
                first.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await first
                self.assertEqual(pool.pending_count, 1)
                second_started = threading.Event()
                second = asyncio.create_task(pool.run(second_started.set))
                await asyncio.sleep(.025)
                self.assertFalse(second_started.is_set())
                await wait_event(physically_closed, 2)
                await second
                self.assertTrue(second_started.is_set())
                self.assertEqual(pool.pending_count, 0)
            finally:
                release_query.set()
                relay.pause_responses.clear()
                if not first.done():
                    first.cancel()
                await asyncio.gather(first, return_exceptions=True)
                if second is not None:
                    if not second.done():
                        second.cancel()
                    await asyncio.gather(second, return_exceptions=True)
        asyncio.run(exercise())
        self.assertEqual(observed, ["timeout"])
        self.assertEqual(len(connections), 1)
        self.assertTrue(connections[0].closed)
        self.assertFalse(connections[0].watchdog_alive)
        self.assertLess(time.monotonic() - query_started[0], 3)
        self.assertTrue(opener._slots.acquire(blocking=False))
        opener._slots.release()
        self.assertEqual(control.execute(
            "SELECT fixture_value FROM flora_selected_read_fault_fixture WHERE _id = %s", (row_id,)).fetchone()[0],
            "public-synthetic-fixture")


if __name__ == "__main__":
    unittest.main()
