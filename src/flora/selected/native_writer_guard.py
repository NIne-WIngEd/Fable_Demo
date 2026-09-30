"""Physically bound one qualified, exclusive native writer PGconn operation.

The retained socket watchdog touches no driver methods. SQL remains on the
binding owner thread and the actual connection/controller identities are kept.
This does not bound Kurrent, object-store or producer callbacks: their concrete
code and deadlines remain independently qualified deployment inputs.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import socket
import sys
import threading
import time
import weakref

from cognitive_kernel.canonical import canonical_sha256, require_identifier, require_sha256
from cognitive_kernel.contracts import ProductHostScope
from .bounded_xtdb_reads import _shutdown_unwrapped_driver


_owners = weakref.WeakKeyDictionary()
_owner_lock = threading.Lock()


@dataclass(frozen=True)
class NativeWriterConfiguration:
    scope: ProductHostScope
    authority_namespace_id: str
    owner_id: str
    driver_version: str
    exclusive_owner_contract_sha256: str
    maximum_operation_time_ms: int
    watchdog_cleanup_time_ms: int = 1000

    def record(self):
        self.scope.validate()
        for name in ("authority_namespace_id", "owner_id"):
            if require_identifier(getattr(self, name), name) != getattr(self, name):
                raise ValueError("native writer identity must be canonical")
        require_sha256(self.exclusive_owner_contract_sha256, "exclusive_owner_contract_sha256")
        if not isinstance(self.driver_version, str) or not self.driver_version or self.driver_version != self.driver_version.strip():
            raise ValueError("native writer driver version must be explicit")
        for name in ("maximum_operation_time_ms", "watchdog_cleanup_time_ms"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError("native writer allowance must be a positive integer")
        return {"schema": "flora-native-writer-configuration-v1", **vars(self),
                "scope": self.scope.metadata_record(), "platform": "linux"}

    @property
    def configuration_sha256(self):
        return canonical_sha256(self.record())


@dataclass(frozen=True)
class VerifiedNativeWriterOwnership:
    qualifier_id: str
    qualification_id: str
    request_sha256: str
    receipt_sha256: str
    allowed: bool


class NativeWriterGuard:
    """An explicitly enrolled ownership contract bound to one actual PGconn.

    verify_identity is passive, has no permission to touch the writer driver,
    and runs in the adapter's bounded callback pool. Its supplied verifier must
    prove exclusive factory/driver use, rather than merely sign plausible JSON.
    The qualified worker manifest pins this guard's source and configuration.
    """
    def __init__(self, *, connection, configuration: NativeWriterConfiguration,
                 verifier, qualification_receipt: bytes, qualifier_id: str, qualification_id: str):
        import psycopg
        if sys.platform != "linux" or not isinstance(connection, psycopg.Connection):
            raise TypeError("native writer guard requires an actual Linux psycopg connection")
        configuration.record()
        if psycopg.__version__ != configuration.driver_version:
            raise ValueError("native writer driver differs from its frozen configuration")
        for name, value in (("qualifier_id", qualifier_id), ("qualification_id", qualification_id)):
            if require_identifier(value, name) != value:
                raise ValueError("native writer qualifier identity must be canonical")
        if not isinstance(qualification_receipt, bytes) or not qualification_receipt:
            raise ValueError("native writer requires an independently verified ownership receipt")
        self.connection, self.configuration = connection, configuration
        self.verifier, self.qualification_receipt = verifier, qualification_receipt
        self.qualifier_id, self.qualification_id = qualifier_id, qualification_id
        self.owner_thread_id = threading.get_ident()
        self.artifact_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.configuration_sha256 = configuration.configuration_sha256
        self._socket_binding = self._connection_binding()
        self._request = {"schema": "flora-native-writer-ownership-request-v1",
            "configuration": configuration.record(), "artifact_sha256": self.artifact_sha256,
            "connection_binding": self._socket_binding, "owner_thread_id": self.owner_thread_id,
            "qualifier_id": qualifier_id, "qualification_id": qualification_id}
        self._verified = None
        self._active = None
        self._lock = threading.Lock()
        with _owner_lock:
            prior = _owners.get(connection)
            if prior is not None and (prior["poisoned"] or prior["guard"]() is not None):
                raise PermissionError("native writer PGconn already belongs to another guard or is poisoned")
            self._ownership = {"guard": weakref.ref(self), "poisoned": False}
            _owners[connection] = self._ownership

    def _connection_binding(self):
        if getattr(self.connection, "closed", False):
            raise RuntimeError("native writer PGconn is closed")
        descriptor = self.connection.fileno()
        stat = os.fstat(descriptor)
        return {"descriptor": descriptor, "device": stat.st_dev, "inode": stat.st_ino,
                "backend_pid": self.connection.pgconn.backend_pid}

    def verify_identity(self):
        # Frozen dynamic binding metadata was collected by the actual owner.
        # The verifier may not access the PGconn from this passive thread.
        proof = self.verifier.verify_native_writer(request=self._request, receipt=self.qualification_receipt)
        if (not isinstance(proof, VerifiedNativeWriterOwnership) or proof.allowed is not True
                or proof.qualifier_id != self.qualifier_id or proof.qualification_id != self.qualification_id
                or proof.request_sha256 != canonical_sha256(self._request)
                or proof.receipt_sha256 != hashlib.sha256(self.qualification_receipt).hexdigest()):
            raise PermissionError("native writer lacks actual exclusive-owner qualification")
        self._verified = proof

    def require_identity(self):
        if threading.get_ident() != self.owner_thread_id:
            raise RuntimeError("native writer PGconn belongs to another owner thread")
        if (self._ownership["poisoned"] or self._verified is None
                or self._verified.allowed is not True
                or self._verified.qualifier_id != self.qualifier_id
                or self._verified.qualification_id != self.qualification_id
                or self._socket_binding != self._connection_binding()
                or self.configuration_sha256 != self.configuration.configuration_sha256
                or self.artifact_sha256 != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
                or self._verified.request_sha256 != canonical_sha256(self._request)
                or self._verified.receipt_sha256 != hashlib.sha256(self.qualification_receipt).hexdigest()):
            raise PermissionError("native writer ownership changed, is unqualified, or is poisoned")

    def operation(self, *, remaining_seconds):
        self.require_identity()
        if (isinstance(remaining_seconds, bool) or not isinstance(remaining_seconds, (int, float))
                or not math.isfinite(remaining_seconds) or remaining_seconds <= 0):
            raise TimeoutError("native writer task deadline expired")
        return _NativeWriterLease(self, min(remaining_seconds,
            self.configuration.maximum_operation_time_ms / 1000))

    def poison(self):
        if threading.get_ident() != self.owner_thread_id:
            raise RuntimeError("native writer must retire on its owner thread")
        self._ownership["poisoned"] = True
        _shutdown_unwrapped_driver(self.connection)
        try:
            self.connection.close()
        except Exception:
            # The ownership entry remains sealed; successful retirement cannot
            # be inferred from a raising SDK close, nor permit a replacement.
            raise RuntimeError("native writer retirement failed") from None


class _NativeWriterLease:
    def __init__(self, guard, allowance):
        self.guard, self.deadline = guard, time.monotonic() + allowance
        self._condition = threading.Condition()
        self._closing, self._expired = False, False
        self._thread, self._socket = None, None

    def __enter__(self):
        self.guard.require_identity()
        if not self.guard._lock.acquire(blocking=False):
            raise PermissionError("native writer cannot overlap synchronous operations")
        try:
            self.guard._active = self
            descriptor = os.dup(self.guard.connection.fileno())
            try:
                self._socket = socket.socket(fileno=descriptor)
            except BaseException:
                os.close(descriptor)
                raise
            self._thread = threading.Thread(target=self._watch, name="flora-native-writer-watchdog", daemon=True)
            self._thread.start()
            return self
        except BaseException:
            if self._socket is not None:
                self._socket.close()
            try:
                self.guard.poison()
            finally:
                # A setup failure never exposes an active write continuation.
                # The poisoned PGconn reservation remains sealed independently.
                self.guard._active = None
                self.guard._lock.release()
            raise

    def _watch(self):
        try:
            with self._condition:
                while not self._closing:
                    remaining = self.deadline - time.monotonic()
                    if remaining <= 0:
                        self._expired = True
                        self.guard._ownership["poisoned"] = True
                        break
                    self._condition.wait(remaining)
            if self._expired:
                try:
                    self._socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        finally:
            self._socket.close()

    def require_active(self, connection):
        self.guard.require_identity()
        if self.guard._active is not self or connection is not self.guard.connection:
            raise PermissionError("native write escaped its exact bounded PGconn operation")
        if self._expired or time.monotonic() >= self.deadline:
            raise TimeoutError("native writer operation deadline expired")

    def __exit__(self, kind, value, traceback):
        expired = self._expired or time.monotonic() >= self.deadline
        with self._condition:
            self._closing = True
            self._condition.notify_all()
        self._thread.join(self.guard.configuration.watchdog_cleanup_time_ms / 1000)
        if self._thread.is_alive():
            # Still-live watchdog owns its duplicate; retain the operation lock.
            self.guard.poison()
            raise TimeoutError("native writer watchdog cleanup deadline expired")
        try:
            if kind is not None or expired:
                self.guard.poison()
        finally:
            self.guard._active = None
            self.guard._lock.release()
        if expired:
            raise TimeoutError("native writer operation deadline expired") from None
        return False
