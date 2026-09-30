"""Explicit Linux psycopg reads with retained-socket physical deadlines.

This opener supplies bounded connection/query/session mechanics, not deployment
qualification. Addresses and credentials are explicit; no connection is inferred
from environment variables. Only the owning reader thread touches/closes psycopg.
One bounded watchdog owns a duplicate socket until physical cleanup finishes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import ipaddress
import os
from pathlib import Path
import socket
import sys
import threading
import time

from cognitive_kernel.canonical import canonical_sha256


def _positive(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(name + " must be a positive integer")


@dataclass(frozen=True)
class BoundedXTDBReadConfiguration:
    hostaddr: str
    port: int
    database: str
    username: str
    driver_version: str
    connect_timeout_seconds: int
    maximum_query_time_ms: int
    maximum_session_time_ms: int
    maximum_concurrent_sessions: int = 1
    watchdog_cleanup_time_ms: int = 1000

    def record(self):
        if not isinstance(self.hostaddr, str) or str(ipaddress.ip_address(self.hostaddr)) != self.hostaddr:
            raise ValueError("bounded XTDB opener requires one canonical numeric hostaddr")
        _positive(self.port, "port")
        if self.port > 65535:
            raise ValueError("bounded XTDB port is outside the TCP range")
        for name in ("database", "username", "driver_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or value != value.strip() or "\0" in value:
                raise ValueError("bounded XTDB connection identity must be explicit")
        for name in ("connect_timeout_seconds", "maximum_query_time_ms", "maximum_session_time_ms",
                     "maximum_concurrent_sessions", "watchdog_cleanup_time_ms"):
            _positive(getattr(self, name), name)
        # libpq treats connect_timeout=1 as two seconds, per its own contract.
        if self.connect_timeout_seconds < 2:
            raise ValueError("libpq connect timeout must be at least two seconds")
        if (self.maximum_query_time_ms > self.maximum_session_time_ms
                or self.connect_timeout_seconds * 1000 > self.maximum_session_time_ms):
            raise ValueError("query/connect deadline exceeds the frozen whole-session deadline")
        return {"schema": "flora-bounded-xtdb-read-configuration-v1", **vars(self),
                "platform": "linux", "sslmode": "disable", "prepared_plans": "disabled"}

    @property
    def configuration_sha256(self):
        return canonical_sha256(self.record())


@dataclass(frozen=True)
class ExplicitXTDBReadCredentials:
    password: str = field(repr=False)

    def validate(self):
        # A nonempty explicit value prevents libpq falling back to PGPASSWORD or
        # a password file. A trust-authenticated local XTDB endpoint may ignore it.
        if not isinstance(self.password, str) or not self.password or "\0" in self.password:
            raise ValueError("bounded XTDB opener requires an explicit nonempty password value")


def _shutdown_unwrapped_driver(connection):
    """Stop failed-setup traffic without closing the owner's descriptor."""
    descriptor, retained = None, None
    try:
        descriptor = os.dup(connection.fileno())
        retained = socket.socket(fileno=descriptor)
        descriptor = None
        retained.shutdown(socket.SHUT_RDWR)
    except Exception:
        pass  # An unavailable descriptor is not proof of driver retirement.
    finally:
        if retained is not None:
            retained.close()
        elif descriptor is not None:
            os.close(descriptor)


class _BoundedXTDBReadConnection:
    """Owner-thread driver facade; the watchdog never calls driver methods."""
    def __init__(self, connection, *, configuration, started_at, release_slot, configuration_guard):
        self.__connection, self.configuration = connection, configuration
        self.owner_thread_id = threading.get_ident()
        self._condition = threading.Condition()
        self._deadline = started_at + configuration.maximum_session_time_ms / 1000
        self._query_deadline = None
        self._poisoned, self._closing, self._driver_closed = False, False, False
        self._watchdog_finished, self._slot_released = False, False
        self._release_slot, self._configuration_guard = release_slot, configuration_guard
        self.closed = False
        # Retaining the duplicated open-file description prevents descriptor
        # reuse from redirecting a later timeout to a different connection.
        descriptor = os.dup(connection.fileno())
        try:
            self._socket = socket.socket(fileno=descriptor)
        except BaseException:
            os.close(descriptor)
            raise
        self._watchdog = threading.Thread(target=self._watch, name="flora-xtdb-read-watchdog", daemon=True)
        try:
            self._watchdog.start()
        except BaseException:
            self._socket.close()
            raise

    def _release_if_finished(self):
        release = False
        with self._condition:
            if self._driver_closed and self._watchdog_finished and not self._slot_released:
                self._slot_released = True
                release = True
        if release:
            self._release_slot()

    def _watch(self):
        shutdown = False
        try:
            with self._condition:
                while not self._closing:
                    deadline = self._deadline
                    if self._query_deadline is not None:
                        deadline = min(deadline, self._query_deadline)
                    remaining = deadline - time.monotonic()
                    if self._poisoned or remaining <= 0:
                        self._poisoned = True
                        shutdown = True
                        break
                    self._condition.wait(remaining)
            if shutdown:
                try:
                    self._socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass  # An already closed/reset socket is equally unusable.
        finally:
            self._socket.close()
            with self._condition:
                self._watchdog_finished = True
                self._condition.notify_all()
            self._release_if_finished()

    def _owner(self):
        if threading.get_ident() != self.owner_thread_id:
            raise RuntimeError("bounded XTDB connection belongs to another reader thread")
        if self.closed:
            raise RuntimeError("bounded XTDB connection is closed")
        self._configuration_guard()
        with self._condition:
            if self._poisoned or time.monotonic() >= self._deadline:
                self._poisoned = True
                self._condition.notify_all()
                raise TimeoutError("bounded XTDB read session is expired or poisoned")

    def execute(self, sql, parameters=()):
        self._owner()
        if (not isinstance(sql, str) or not sql.lstrip().upper().startswith("SELECT ")
                or ";" in sql or "\0" in sql):
            raise PermissionError("bounded XTDB passive connection accepts single SELECT templates only")
        with self._condition:
            if self._query_deadline is not None:
                raise RuntimeError("bounded XTDB reader cannot overlap queries")
            self._query_deadline = min(self._deadline,
                time.monotonic() + self.configuration.maximum_query_time_ms / 1000)
            self._condition.notify_all()
        failed = False
        try:
            result = self.__connection.execute(sql, parameters)
        except BaseException as exc:
            failed = True
            if not isinstance(exc, Exception):
                raise
        finally:
            with self._condition:
                expired = self._poisoned or time.monotonic() >= self._query_deadline
                if failed or expired:
                    self._poisoned = True
                self._query_deadline = None
                self._condition.notify_all()
        if expired:
            raise TimeoutError("bounded XTDB SELECT deadline expired") from None
        if failed:
            raise RuntimeError("bounded XTDB SELECT failed") from None
        try:
            self._configuration_guard()
        except Exception:
            with self._condition:
                self._poisoned = True
                self._condition.notify_all()
            raise
        return result

    @property
    def adapters(self):
        self._owner()
        return self.__connection.adapters

    @property
    def prepare_threshold(self):
        self._owner()
        return self.__connection.prepare_threshold

    @prepare_threshold.setter
    def prepare_threshold(self, value):
        self._owner()
        if value is not None:
            raise PermissionError("bounded XTDB reads must disable prepared plans")
        self.__connection.prepare_threshold = None

    @property
    def watchdog_alive(self):
        return self._watchdog.is_alive()

    def close(self):
        if threading.get_ident() != self.owner_thread_id:
            raise RuntimeError("bounded XTDB connection must close in its owning reader thread")
        if self.closed:
            return
        self.closed = True
        with self._condition:
            self._closing = True
            # Stop traffic before disarming the watchdog. Even a driver-close
            # fault cannot leave this retained socket serving later work.
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self._condition.notify_all()
        failed = False
        try:
            self.__connection.close()
        except Exception:
            failed = True
        finally:
            with self._condition:
                # A raising close does not prove its descriptor retired. Keep
                # the physical opener slot sealed rather than accumulate more
                # unproven driver cleanup behind a successful await.
                self._driver_closed = not failed
            self._watchdog.join(self.configuration.watchdog_cleanup_time_ms / 1000)
            self._release_if_finished()
        # A late watchdog still owns its duplicate and the opener slot. Further
        # opens cannot accumulate watchdogs while that physical cleanup runs.
        if self._watchdog.is_alive():
            raise TimeoutError("bounded XTDB watchdog cleanup deadline expired")
        if failed:
            raise RuntimeError("bounded XTDB connection cleanup failed") from None


class BoundedXTDBReadOpener:
    """Concrete callable for InitializedNativeSessionFactory.connection_opener.

    This deliberately supports the local selected XTDB TCP endpoint (sslmode
    disable), not remote TLS deployment. It pins one numeric endpoint and exact
    driver version. Runtime/factory dependency qualification remains independent.
    """
    def __init__(self, *, configuration: BoundedXTDBReadConfiguration,
                 credentials: ExplicitXTDBReadCredentials):
        if sys.platform != "linux":
            raise RuntimeError("bounded XTDB socket deadlines require Linux")
        configuration.record()
        credentials.validate()
        self.configuration, self.credentials = configuration, credentials
        self.artifact_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.configuration_sha256 = configuration.configuration_sha256
        self._slots = threading.BoundedSemaphore(configuration.maximum_concurrent_sessions)

    def _check_configuration(self):
        if (self.configuration_sha256 != self.configuration.configuration_sha256
                or self.artifact_sha256 != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()):
            raise ValueError("bounded XTDB opener differs from frozen source/configuration")
        self.credentials.validate()

    def __call__(self, *, read_timeout_ms):
        _positive(read_timeout_ms, "read_timeout_ms")
        self._check_configuration()
        c = self.configuration
        if c.maximum_query_time_ms > read_timeout_ms or c.connect_timeout_seconds * 1000 > read_timeout_ms:
            raise ValueError("bounded XTDB query/connect deadline exceeds the factory allowance")
        started = time.monotonic()
        if not self._slots.acquire(timeout=min(read_timeout_ms, c.maximum_session_time_ms) / 1000):
            raise TimeoutError("bounded XTDB opener has no physically retired session slot")
        connection = None
        try:
            import psycopg
            if psycopg.__version__ != c.driver_version:
                raise ValueError("bounded XTDB driver version differs from frozen configuration")
            remaining_seconds = int(started + c.maximum_session_time_ms / 1000 - time.monotonic())
            if remaining_seconds < 2:
                raise TimeoutError("bounded XTDB session has no remaining bounded connection allowance")
            try:
                connection = psycopg.connect(host=c.hostaddr, hostaddr=c.hostaddr, port=c.port,
                    dbname=c.database, user=c.username, password=self.credentials.password,
                    passfile="/dev/null", sslmode="disable", gssencmode="disable", channel_binding="disable",
                    connect_timeout=min(c.connect_timeout_seconds, remaining_seconds),
                    autocommit=True, prepare_threshold=None)
            except Exception as exc:
                timeout_type = getattr(getattr(psycopg, "errors", None), "ConnectionTimeout", None)
                if (isinstance(exc, TimeoutError)
                        or (isinstance(timeout_type, type) and isinstance(exc, timeout_type))):
                    raise TimeoutError("bounded XTDB connection deadline expired") from None
                raise RuntimeError("bounded XTDB connection attempt failed") from None
            if time.monotonic() >= started + c.maximum_session_time_ms / 1000:
                raise TimeoutError("bounded XTDB session expired during connection setup")
            return _BoundedXTDBReadConnection(connection, configuration=c, started_at=started,
                release_slot=self._slots.release, configuration_guard=self._check_configuration)
        except BaseException:
            retired = connection is None
            if connection is not None:
                _shutdown_unwrapped_driver(connection)
                try:
                    connection.close()
                except Exception:
                    pass
                else:
                    retired = True
            if retired:
                self._slots.release()
            else:
                # The wrapper never acquired cleanup ownership, so retain the
                # opener's slot when physical driver retirement is unproven.
                raise RuntimeError("bounded XTDB setup cleanup failed") from None
            raise
