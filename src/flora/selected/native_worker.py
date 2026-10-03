"""Qualified, bounded local process transport; no runtime factory is installed.

The producer supplies the executable/factory, codec and independent qualifier.
Hashes pin bytes; they do not establish that a worker or its dependencies are
qualified. Private data travels through pipes, never command-line arguments.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import hashlib
import math
import fcntl
import os
from pathlib import Path
import signal
import stat
import sys
from typing import Awaitable, Callable, Protocol

from cognitive_kernel.canonical import canonical_sha256, require_identifier, require_sha256
from cognitive_kernel.contracts import ProductHostScope

# Linux UAPI values (linux/fcntl.h); some embedded Python builds omit names.
_ADD_SEALS = getattr(fcntl, "F_ADD_SEALS", 1033)
_GET_SEALS = getattr(fcntl, "F_GET_SEALS", 1034)
_IMMUTABLE_SEALS = (getattr(fcntl, "F_SEAL_SEAL", 1) | getattr(fcntl, "F_SEAL_SHRINK", 2)
                    | getattr(fcntl, "F_SEAL_GROW", 4) | getattr(fcntl, "F_SEAL_WRITE", 8))


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _positive(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(name + " must be a positive integer")


def _regular_file(path: str):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise ValueError("worker code must be an exact regular local file")
    return os.fdopen(fd, "rb")


def _owned_read_future(function, *args, **kwargs):
    """Low-level executor ownership; repeated callers use OwnedPassiveReads."""
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="flora-native-read")
    # Retain the actual physical future: cancelling an asyncio wrapper can mark
    # it done even when its driver thread is still running.
    future = executor.submit(partial(function, *args, **kwargs))
    def finish(completed):
        executor.shutdown(wait=False, cancel_futures=True)
        if not completed.cancelled():
            completed.exception()  # No unhandled private exception log after cancellation.
    future.add_done_callback(finish)
    return future


async def _await_owned_read(future):
    # A bounded timer also services embedded runtimes whose cross-thread loop
    # wakeup is delayed. It never blocks the event loop or calls inference.
    while not future.done():
        await asyncio.sleep(.005)
    return future.result()


class OwnedPassiveReads:
    """Bound physical passive callbacks even after an awaiting task is cancelled.

    A slot is acquired before submission and remains owned by the actual future
    until its callback returns. There is no executor queue or shared global loop.
    Callback qualification must still enforce real backend/codec deadlines and
    forbid inference or mutation; this pool cannot kill a Python driver thread.
    """
    def __init__(self, *, maximum_concurrency: int = 1):
        _positive(maximum_concurrency, "maximum_concurrency")
        self.maximum_concurrency = maximum_concurrency
        self._slots = asyncio.Semaphore(maximum_concurrency)
        self._loop = None
        self._pending = set()

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    async def submit(self, function, *args, **kwargs):
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            raise RuntimeError("passive callback pool belongs to a different event loop")
        if not callable(function):
            raise TypeError("passive callback must be an explicitly supplied callable")
        await self._slots.acquire()
        try:
            future = _owned_read_future(function, *args, **kwargs)
        except BaseException:
            self._slots.release()
            raise
        self._pending.add(future)
        def finished(done):
            def retire():
                self._pending.discard(done)
                self._slots.release()
                if not done.cancelled():
                    done.exception()  # No private error log after a cancelled await.
            # A concurrent Future's callbacks run in its owning worker thread.
            # Closed loops cannot reuse this pool and own no write continuation.
            try:
                loop.call_soon_threadsafe(retire)
            except RuntimeError:
                if not loop.is_closed():
                    raise
        future.add_done_callback(finished)
        return future

    async def run(self, function, *args, **kwargs):
        return await _await_owned_read(await self.submit(function, *args, **kwargs))


@dataclass(frozen=True)
class NativeProcessLaunch:
    executable: str = field(repr=False)
    factory_artifact: str = field(repr=False)
    arguments: tuple[str, ...] = field(default=(), repr=False)
    environment: tuple[tuple[str, str], ...] = field(default=(), repr=False)
    working_directory: str | None = field(default=None, repr=False)

    def configuration_sha256(self) -> str:
        if (not Path(self.executable).is_absolute() or not Path(self.factory_artifact).is_absolute()
                or any(not isinstance(v, str) or "\0" in v for v in self.arguments)
                or len(dict(self.environment)) != len(self.environment)
                or any(not k or "=" in k or "\0" in k or "\0" in v for k, v in self.environment)
                or (self.working_directory is not None and not Path(self.working_directory).is_absolute())):
            raise ValueError("worker launch must have exact local paths and a unique explicit environment")
        if self.arguments.count("{factory_artifact}") != 1:
            raise ValueError("worker launch must consume its exact sealed factory descriptor once")
        return canonical_sha256(vars(self))


@dataclass(frozen=True)
class NativeWorkerManifest:
    scope: ProductHostScope
    authority_namespace_id: str
    worker_id: str
    executable_sha256: str
    factory_artifact_sha256: str
    launch_configuration_sha256: str
    codec_artifact_sha256: str
    read_service_artifact_sha256: str
    read_service_configuration_sha256: str
    meter_artifact_sha256: str
    meter_configuration_sha256: str
    maximum_input_bytes: int
    maximum_output_bytes: int
    maximum_stderr_bytes: int
    maximum_wall_time_ms: int
    terminate_grace_ms: int
    maximum_artifact_bytes: int
    writer_guard_artifact_sha256: str | None = None
    writer_guard_configuration_sha256: str | None = None

    def record(self) -> dict:
        self.scope.validate()
        for name in ("authority_namespace_id", "worker_id"):
            value = getattr(self, name)
            if require_identifier(value, name) != value:
                raise ValueError("worker identifiers must be canonical")
        for name in self.__dataclass_fields__:
            if name.endswith("_sha256"):
                value = getattr(self, name)
                if name.startswith("writer_guard_") and value is None:
                    continue
                if require_sha256(value, name) != value:
                    raise ValueError("worker digests must be canonical")
            elif name.startswith("maximum_") or name == "terminate_grace_ms":
                _positive(getattr(self, name), name)
        writer = (self.writer_guard_artifact_sha256, self.writer_guard_configuration_sha256)
        if any(value is not None for value in writer) and any(value is None for value in writer):
            raise ValueError("native writer guard artifact/configuration hashes must be supplied together")
        values = {name: value for name, value in vars(self).items()
                  if not (name.startswith("writer_guard_") and value is None)}
        return {"schema": "flora-native-worker-manifest-v2" if writer[0] is not None else "flora-native-worker-manifest-v1",
                **values, "scope": self.scope.metadata_record()}

    @property
    def manifest_sha256(self) -> str:
        return canonical_sha256(self.record())


@dataclass(frozen=True)
class VerifiedNativeWorkerQualification:
    qualifier_id: str
    qualification_id: str
    manifest_sha256: str
    receipt_sha256: str
    allowed: bool

    def validate(self, manifest: NativeWorkerManifest, receipt: bytes,
                 qualifier_id: str, qualification_id: str) -> None:
        if (not isinstance(receipt, bytes) or not receipt or self.allowed is not True
                or self.qualifier_id != qualifier_id or self.qualification_id != qualification_id
                or self.manifest_sha256 != manifest.manifest_sha256 or self.receipt_sha256 != _sha(receipt)):
            raise ValueError("worker lacks exact independently verified qualification")


class NativeWorkerQualificationVerifier(Protocol):
    """Qualification covers actual factory, transitive code and async ports.

    It includes pipe isolation, stateless task handling, backend read deadlines,
    owned/serialized connections, exclusive qualified bounded native writer
    guard/factory ownership when its hashes are declared, no inference in parent read callbacks and the
    actual codec/meter adapters. An arbitrary signature is not qualification.
    """
    def verify_worker(self, *, manifest: NativeWorkerManifest,
                      receipt: bytes) -> VerifiedNativeWorkerQualification: ...


@dataclass(frozen=True)
class NativeWorkerObservation:
    worker_manifest_sha256: str
    request_sha256: str
    output_sha256: str
    exit_code: int
    output: bytes = field(repr=False)

    @property
    def observation_sha256(self) -> str:
        return canonical_sha256({k: v for k, v in vars(self).items() if k != "output"})


@dataclass(frozen=True)
class NativeWorkerFailureReceipt:
    worker_manifest_sha256: str
    request_sha256: str
    reason: str
    exit_code: int | None


class NativeWorkerFailure(RuntimeError):
    def __init__(self, receipt: NativeWorkerFailureReceipt):
        self.receipt = receipt
        super().__init__(receipt.reason)


class NativeWorkerDispatchDenied(PermissionError):
    """Sanitized denial from the separately authorized private input gate."""


class QualifiedNativeProcessWorker:
    """POSIX subprocess port with bounded pipes and terminated descendants.

    No shell, inherited environment, pickle, dynamic import, stdout forwarding or
    default runtime factory. The supplied independently qualified executable may
    load only the factory/dependencies covered by its actual qualification.
    """
    def __init__(self, *, manifest: NativeWorkerManifest, launch: NativeProcessLaunch,
                 qualification_receipt: bytes, qualifier_id: str, qualification_id: str,
                 verifier: NativeWorkerQualificationVerifier):
        manifest.record()
        for name, value in (("qualifier_id", qualifier_id), ("qualification_id", qualification_id)):
            if require_identifier(value, name) != value:
                raise ValueError("worker qualifier identifiers must be canonical")
        self.manifest, self.launch = manifest, launch
        self.qualification_receipt = qualification_receipt
        self.qualifier_id, self.qualification_id, self.verifier = qualifier_id, qualification_id, verifier
        self.last_failure: NativeWorkerFailureReceipt | None = None
        self._passive_reads = OwnedPassiveReads()

    def verify_identity(self) -> None:
        if sys.platform != "linux" or not hasattr(os, "memfd_create"):
            raise ValueError("sealed terminable process port is unavailable on this platform")
        if self.launch.configuration_sha256() != self.manifest.launch_configuration_sha256:
            raise ValueError("worker launch configuration changed")
        def check_bytes():
            for path, expected in ((self.launch.executable, self.manifest.executable_sha256),
                                   (self.launch.factory_artifact, self.manifest.factory_artifact_sha256)):
                actual = hashlib.sha256()
                total = 0
                with _regular_file(path) as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        total += len(chunk)
                        if total > self.manifest.maximum_artifact_bytes:
                            raise ValueError("worker code exceeds its artifact size bound")
                        actual.update(chunk)
                if actual.hexdigest() != expected:
                    raise ValueError("worker executable/factory bytes changed")
        check_bytes()
        verified = self.verifier.verify_worker(manifest=self.manifest, receipt=self.qualification_receipt)
        if not isinstance(verified, VerifiedNativeWorkerQualification):
            raise TypeError("worker qualifier returned no bound verified receipt")
        verified.validate(self.manifest, self.qualification_receipt, self.qualifier_id, self.qualification_id)
        check_bytes()

    def _sealed_launch(self) -> tuple[int, int]:
        """Pin actual opened executable/factory bytes; path rehashing is not pinning."""
        descriptors = []
        try:
            for path, digest in ((self.launch.executable, self.manifest.executable_sha256),
                                 (self.launch.factory_artifact, self.manifest.factory_artifact_sha256)):
                fd = os.memfd_create("flora-native-code", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
                descriptors.append(fd)
                total, actual = 0, hashlib.sha256()
                with _regular_file(path) as source:
                    while chunk := source.read(1024 * 1024):
                        total += len(chunk)
                        if total > self.manifest.maximum_artifact_bytes:
                            raise ValueError("worker code exceeds its qualified artifact size bound")
                        actual.update(chunk)
                        view = memoryview(chunk)
                        while view:
                            view = view[os.write(fd, view):]
                if actual.hexdigest() != digest:
                    raise ValueError("actual launch bytes differ from qualified code")
                os.fchmod(fd, 0o500)
                fcntl.fcntl(fd, _ADD_SEALS, _IMMUTABLE_SEALS)
                if fcntl.fcntl(fd, _GET_SEALS) & _IMMUTABLE_SEALS != _IMMUTABLE_SEALS:
                    raise ValueError("worker code descriptor is not immutable")
            return tuple(descriptors)
        except BaseException:
            for fd in descriptors:
                os.close(fd)
            raise
    async def run(self, *, request: bytes, deadline: float,
                  authorize_dispatch: Callable[[], Awaitable[None]]) -> NativeWorkerObservation:
        if not isinstance(request, bytes) or not request or len(request) > self.manifest.maximum_input_bytes:
            raise ValueError("private worker request exceeds its frozen input bounds")
        if not callable(authorize_dispatch):
            raise TypeError("worker requires a current independent dispatch authorization")
        if isinstance(deadline, bool) or not isinstance(deadline, (int, float)) or not math.isfinite(deadline):
            raise ValueError("worker deadline must be a finite event-loop timestamp")
        loop = asyncio.get_running_loop()
        end = min(deadline, loop.time() + self.manifest.maximum_wall_time_ms / 1000)
        request_sha = _sha(request)
        proc = None
        spawn_task = None
        code_fds = ()
        tasks = []
        self.last_failure = None

        def failure(reason, exit_code=None):
            receipt = NativeWorkerFailureReceipt(self.manifest.manifest_sha256, request_sha, reason, exit_code)
            self.last_failure = receipt
            return NativeWorkerFailure(receipt)

        async def stop():
            if proc is None:
                return
            # Even an exited parent may have left descendants holding the pipes.
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(proc.wait(), self.manifest.terminate_grace_ms / 1000)
            except TimeoutError:
                pass
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(proc.wait(), self.manifest.terminate_grace_ms / 1000)
            except TimeoutError:
                # asyncio's subprocess wait can await pipe disconnection even
                # after exit. Close paused pipe transports as a bounded fallback.
                proc._transport.close()
                try:
                    await asyncio.wait_for(proc.wait(), self.manifest.terminate_grace_ms / 1000)
                except TimeoutError:
                    raise failure("cleanup_failed", proc.returncode) from None

        async def drain(stream, cap, retain):
            parts, total = [], 0
            while True:
                chunk = await stream.read(min(65536, cap + 1))
                if not chunk:
                    return b"".join(parts)
                total += len(chunk)
                if total > cap:
                    raise failure("output_limit" if retain else "stderr_limit")
                if retain:
                    parts.append(chunk)

        try:
            async with asyncio.timeout_at(end):
                await self._passive_reads.run(self.verify_identity)
                if await authorize_dispatch() is not None:
                    raise NativeWorkerDispatchDenied("refused")
                if loop.time() >= end:
                    raise TimeoutError
                snapshot_task = await self._passive_reads.submit(self._sealed_launch)
                try:
                    code_fds = await _await_owned_read(snapshot_task)
                except BaseException:
                    # A cancelled passive copy owns no launch/write continuation.
                    # If it finishes later, dispose of its descriptors immediately.
                    def close_late(task):
                        try:
                            for fd in task.result():
                                os.close(fd)
                        except BaseException:
                            pass
                    snapshot_task.add_done_callback(close_late)
                    raise
                if loop.time() >= end:
                    raise TimeoutError
                arguments = tuple("/proc/self/fd/" + str(code_fds[1]) if value == "{factory_artifact}" else value
                                  for value in self.launch.arguments)
                spawn_task = asyncio.create_task(asyncio.create_subprocess_exec("/proc/self/fd/" + str(code_fds[0]), *arguments,
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    cwd=self.launch.working_directory, env=dict(self.launch.environment), start_new_session=True,
                    pass_fds=code_fds, limit=min(65536, self.manifest.maximum_output_bytes + 1)))
                proc = await asyncio.shield(spawn_task)
                # Process startup cannot authorize private input disclosure.
                if await authorize_dispatch() is not None:
                    raise NativeWorkerDispatchDenied("refused")
                async def send():
                    try:
                        proc.stdin.write(request)
                        await proc.stdin.drain()
                    except (BrokenPipeError, ConnectionResetError):
                        # Match asyncio.communicate when the child exits before
                        # consuming stdin; bounded readers and exit status decide.
                        pass
                    finally:
                        # Like communicate, do not await the protocol-owned close
                        # future: sender cancellation must not cancel that future.
                        proc.stdin.close()
                tasks = [asyncio.create_task(drain(proc.stdout, self.manifest.maximum_output_bytes, True)),
                         asyncio.create_task(drain(proc.stderr, self.manifest.maximum_stderr_bytes, False)),
                         asyncio.create_task(send()), asyncio.create_task(proc.wait())]
                output, _, _, exit_code = await asyncio.gather(*tasks)
                if exit_code != 0:
                    raise failure("exit_failure", exit_code)
                if not output:
                    raise failure("empty_output", exit_code)
                await self._passive_reads.run(self.verify_identity)
                return NativeWorkerObservation(self.manifest.manifest_sha256, request_sha, _sha(output), exit_code, output)
        except asyncio.CancelledError:
            failure("cancelled", None if proc is None else proc.returncode)
            raise
        except TimeoutError:
            raise failure("timeout", None if proc is None else proc.returncode) from None
        except NativeWorkerFailure:
            raise
        except NativeWorkerDispatchDenied:
            raise failure("dispatch_refused", None if proc is None else proc.returncode) from None
        except Exception:
            raise failure("worker_rejected", None if proc is None else proc.returncode) from None
        finally:
            async def cleanup():
                nonlocal proc
                drainers = []
                try:
                    if proc is None and spawn_task is not None:
                        # Startup cancellation cannot hide a spawned process.
                        proc = await asyncio.shield(spawn_task)
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    if tasks:
                        await asyncio.gather(*tasks, return_exceptions=True)
                    if proc is not None:
                        async def discard(stream):
                            while await stream.read(65536):
                                pass
                        # Resume pipes whose original bounded reader stopped.
                        drainers = [asyncio.create_task(discard(proc.stdout)),
                                    asyncio.create_task(discard(proc.stderr))]
                    await stop()
                finally:
                    for task in drainers:
                        task.cancel()
                    if drainers:
                        await asyncio.gather(*drainers, return_exceptions=True)
                    for fd in code_fds:
                        os.close(fd)
            cleanup_task = asyncio.create_task(cleanup())
            interrupted = None
            while not cleanup_task.done():
                try:
                    await asyncio.shield(cleanup_task)
                except asyncio.CancelledError as exc:
                    interrupted = exc
            cleanup_task.result()
            if interrupted is not None:
                raise interrupted
