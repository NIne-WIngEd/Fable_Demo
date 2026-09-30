"""Physical socket/ownership mechanics with a supplied fictional driver.

These cases neither qualify psycopg nor selected XTDB protocol/deployment.
"""
from dataclasses import replace
import socket
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from flora.selected.bounded_xtdb_reads import (
    BoundedXTDBReadConfiguration, BoundedXTDBReadOpener, ExplicitXTDBReadCredentials,
    _BoundedXTDBReadConnection,
)


def configuration(**changes):
    result = BoundedXTDBReadConfiguration("127.0.0.1", 5432, "fixture_database", "fixture_user",
        "fictional-driver-v1", 2, 50, 3000, watchdog_cleanup_time_ms=100)
    return replace(result, **changes)


class SocketDriver:
    def __init__(self):
        self.socket, self.peer = socket.socketpair()
        self.calls, self.closes = [], []
        self.prepare_threshold = None
        self.adapters = object()
        self.error = None
    def fileno(self):
        return self.socket.fileno()
    def execute(self, sql, parameters):
        self.calls.append((sql, parameters, threading.get_ident()))
        if self.error is not None:
            raise self.error
        data = self.socket.recv(1024)
        if not data:
            raise OSError("fictional private driver/query/password material")
        return data
    def close(self):
        self.closes.append(threading.get_ident())
        self.socket.close()


class BoundedXTDBReadTest(unittest.TestCase):
    def connection(self, *, config=None, started_at=None):
        driver, released = SocketDriver(), []
        connection = _BoundedXTDBReadConnection(driver, configuration=config or configuration(),
            started_at=time.monotonic() if started_at is None else started_at,
            release_slot=lambda: released.append(True), configuration_guard=lambda: None)
        self.addCleanup(driver.peer.close)
        self.addCleanup(connection.close)
        return driver, connection, released

    def test_stalled_socket_physically_wakes_poisoned_reader_and_retires_watchdog(self):
        driver, connection, released = self.connection()
        started = time.monotonic()
        with self.assertRaisesRegex(TimeoutError, "SELECT deadline"):
            connection.execute("SELECT * FROM fixture WHERE _id = %s", ("fixture",))
        self.assertLess(time.monotonic() - started, .8)
        with self.assertRaises(TimeoutError):
            connection.execute("SELECT 2")
        self.assertEqual(len(driver.calls), 1)
        connection.close()
        self.assertFalse(connection.watchdog_alive)
        self.assertEqual(driver.closes, [threading.get_ident()])
        self.assertEqual(released, [True])

    def test_successful_query_disarms_its_deadline_and_owner_can_read_again(self):
        driver, connection, released = self.connection()
        driver.peer.sendall(b"first")
        self.assertEqual(connection.execute("SELECT 1"), b"first")
        time.sleep(.08)  # Longer than the completed query's former allowance.
        driver.peer.sendall(b"second")
        self.assertEqual(connection.execute("SELECT 2"), b"second")
        self.assertTrue(connection.watchdog_alive)
        connection.close()
        self.assertEqual(released, [True])

    def test_whole_session_deadline_poisoning_happens_without_an_active_query(self):
        driver, connection, released = self.connection(started_at=time.monotonic() - 2.95)
        time.sleep(.08)
        with self.assertRaises(TimeoutError):
            connection.execute("SELECT 1")
        self.assertEqual(driver.calls, [])
        connection.close()
        self.assertEqual(released, [True])

    def test_select_guard_prepared_plan_and_cross_thread_operations_fail_before_driver(self):
        driver, connection, released = self.connection()
        for sql in ("INSERT INTO bad VALUES (1)", "SELECT 1; DELETE FROM bad", "SELECT \0"):
            with self.assertRaises(PermissionError):
                connection.execute(sql)
        with self.assertRaises(PermissionError):
            connection.prepare_threshold = 1
        denied = []
        def other_thread():
            for callback in (lambda: connection.execute("SELECT 1"), connection.close):
                try:
                    callback()
                except RuntimeError:
                    denied.append(True)
        thread = threading.Thread(target=other_thread)
        thread.start()
        thread.join(.5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(denied, [True, True])
        self.assertEqual(driver.calls, [])
        self.assertEqual(driver.closes, [])
        connection.close()
        self.assertEqual(released, [True])

    def test_driver_failure_never_exposes_private_error_or_allows_retry(self):
        driver, connection, released = self.connection()
        driver.error = ValueError("private fixture password and original query")
        with self.assertRaisesRegex(RuntimeError, "bounded XTDB SELECT failed") as caught:
            connection.execute("SELECT * FROM fixture", ("private fixture parameter",))
        self.assertNotIn("password", str(caught.exception))
        with self.assertRaises(TimeoutError):
            connection.execute("SELECT 2")
        self.assertEqual(len(driver.calls), 1)
        connection.close()

    def test_late_watchdog_cleanup_keeps_physical_opener_slot_and_retained_socket(self):
        entered, release = threading.Event(), threading.Event()
        original = _BoundedXTDBReadConnection._watch
        def delayed_watch(connection):
            entered.set()
            release.wait(1)
            original(connection)
        slot = threading.BoundedSemaphore(1)
        self.assertTrue(slot.acquire(blocking=False))
        driver = SocketDriver()
        self.addCleanup(driver.peer.close)
        with patch.object(_BoundedXTDBReadConnection, "_watch", delayed_watch):
            connection = _BoundedXTDBReadConnection(driver, configuration=configuration(),
                started_at=time.monotonic(), release_slot=slot.release, configuration_guard=lambda: None)
        self.assertTrue(entered.wait(.5))
        retained_socket = connection._socket.fileno()
        try:
            with self.assertRaisesRegex(TimeoutError, "cleanup deadline"):
                connection.close()
            self.assertTrue(connection.watchdog_alive)
            self.assertGreaterEqual(retained_socket, 0)
            self.assertEqual(connection._socket.fileno(), retained_socket)
            self.assertFalse(slot.acquire(blocking=False))
        finally:
            release.set()
            connection._watchdog.join(.5)
        self.assertFalse(connection.watchdog_alive)
        self.assertEqual(connection._socket.fileno(), -1)
        self.assertTrue(slot.acquire(blocking=False))
        slot.release()
        self.assertEqual(driver.closes, [threading.get_ident()])

    def test_raising_driver_close_shuts_down_socket_and_never_releases_unproven_slot(self):
        driver, connection, released = self.connection()
        self.addCleanup(driver.socket.close)
        def fail_close():
            driver.closes.append(threading.get_ident())
            raise OSError("private driver cleanup and credential fixture")
        driver.close = fail_close
        with self.assertRaisesRegex(RuntimeError, "connection cleanup failed") as caught:
            connection.close()
        self.assertNotIn("credential", str(caught.exception))
        self.assertFalse(connection.watchdog_alive)
        self.assertTrue(connection.closed)
        self.assertEqual(driver.peer.recv(1), b"")
        self.assertEqual(released, [])
        connection.close()
        self.assertEqual(driver.closes, [threading.get_ident()])
        self.assertEqual(released, [])

    def test_explicit_opener_pins_connection_parameters_and_cleans_failed_open(self):
        driver, parameters = SocketDriver(), []
        self.addCleanup(driver.peer.close)
        def connect(**kwargs):
            parameters.append(kwargs)
            return driver
        module = SimpleNamespace(__version__="fictional-driver-v1", connect=connect)
        opener = BoundedXTDBReadOpener(configuration=configuration(),
            credentials=ExplicitXTDBReadCredentials("explicit-fictional-password"))
        with patch.dict(sys.modules, psycopg=module):
            connection = opener(read_timeout_ms=2500)
        self.addCleanup(connection.close)
        self.assertEqual(parameters[0]["hostaddr"], "127.0.0.1")
        self.assertEqual(parameters[0]["password"], "explicit-fictional-password")
        self.assertEqual(parameters[0]["passfile"], "/dev/null")
        self.assertEqual(parameters[0]["connect_timeout"], 2)
        self.assertIsNone(parameters[0]["prepare_threshold"])
        self.assertTrue(parameters[0]["autocommit"])
        connection.close()
        with patch.dict(sys.modules, psycopg=SimpleNamespace(__version__="changed", connect=connect)):
            with self.assertRaisesRegex(ValueError, "driver version"):
                opener(read_timeout_ms=2500)
        self.assertEqual(len(parameters), 1)
        with self.assertRaises(ValueError):
            opener(read_timeout_ms=1000)
        self.assertTrue(opener._slots.acquire(blocking=False))
        opener._slots.release()

    def test_failed_watchdog_setup_and_driver_close_keep_socket_stopped_and_slot_sealed(self):
        driver = SocketDriver()
        self.addCleanup(driver.peer.close)
        self.addCleanup(driver.socket.close)
        def fail_close():
            driver.closes.append(threading.get_ident())
            raise OSError("private driver cleanup and credential fixture")
        driver.close = fail_close
        module = SimpleNamespace(__version__="fictional-driver-v1", connect=lambda **kwargs: driver)
        opener = BoundedXTDBReadOpener(configuration=configuration(),
            credentials=ExplicitXTDBReadCredentials("explicit-fictional-password"))
        with patch.dict(sys.modules, psycopg=module), patch.object(
                threading.Thread, "start", side_effect=RuntimeError("fictional watchdog startup failure")):
            with self.assertRaisesRegex(RuntimeError, "setup cleanup failed") as caught:
                opener(read_timeout_ms=2500)
        self.assertNotIn("credential", str(caught.exception))
        self.assertEqual(driver.peer.recv(1), b"")
        self.assertFalse(opener._slots.acquire(blocking=False))
        self.assertEqual(driver.closes, [threading.get_ident()])
        self.assertEqual(driver.calls, [])

    def test_nonexplicit_or_multihost_configuration_cannot_open(self):
        for host in ("localhost", "127.0.0.1,127.0.0.2", ""):
            with self.assertRaises(ValueError):
                configuration(hostaddr=host).record()
        with self.assertRaises(ValueError):
            configuration(connect_timeout_seconds=1).record()
        with self.assertRaises(ValueError):
            ExplicitXTDBReadCredentials("").validate()


if __name__ == "__main__":
    unittest.main()
