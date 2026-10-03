"""Real process lifecycle tests with fictional independent worker qualification.

These scripts are transport fixtures, not runtime factories or model exports.
"""
import asyncio
import base64
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cognitive_kernel.canonical import canonical_json_bytes
from cognitive_kernel.contracts import ProductHostScope
from flora.selected.native_worker import (
    NativeProcessLaunch, NativeWorkerDispatchDenied, NativeWorkerFailure, NativeWorkerManifest,
    OwnedPassiveReads,
    QualifiedNativeProcessWorker, VerifiedNativeWorkerQualification,
)


def sha(content):
    return hashlib.sha256(content).hexdigest()


class FictionalWorkerQualifier:
    def __init__(self, key):
        self.key = key
    def verify_worker(self, *, manifest, receipt):
        body = json.loads(receipt)
        self.key.verify(base64.b64decode(body["signature"], validate=True), canonical_json_bytes(body["payload"]))
        if body["payload"] != {"schema": "fictional-worker-qualification-v1", "manifest": manifest.manifest_sha256}:
            raise ValueError("fictional worker proof changed")
        return VerifiedNativeWorkerQualification("fixture-worker-qualifier", "fixture-worker-qualification",
            manifest.manifest_sha256, sha(receipt), True)


def worker_fixture(directory, program, *, arguments=(), maximum_output=4096, wall_ms=2000,
                   scope=None, namespace="fixture-authority"):
    path = Path(directory) / "worker_fixture.py"
    path.write_text(program)
    executable = str(Path("/usr/bin/python3" if Path("/usr/bin/python3").exists() else sys.executable).resolve())
    launch = NativeProcessLaunch(executable, str(path), ("-I", "{factory_artifact}", *arguments))
    scope = scope or ProductHostScope.create(product_id="friday", host_instance_id="fixture-host",
                                            schema_version="1.0.0", encryption_domain="fixture-key")
    manifest = NativeWorkerManifest(scope, namespace, "fixture-worker", sha(Path(executable).read_bytes()),
        sha(path.read_bytes()), launch.configuration_sha256(), "1" * 64, "2" * 64, "3" * 64,
        "4" * 64, "5" * 64, 65536, maximum_output, 4096, wall_ms, 80, 64 * 1024 * 1024)
    key = Ed25519PrivateKey.generate()
    payload = {"schema": "fictional-worker-qualification-v1", "manifest": manifest.manifest_sha256}
    receipt = canonical_json_bytes({"payload": payload,
        "signature": base64.b64encode(key.sign(canonical_json_bytes(payload))).decode()})
    return QualifiedNativeProcessWorker(manifest=manifest, launch=launch, qualification_receipt=receipt,
        qualifier_id="fixture-worker-qualifier", qualification_id="fixture-worker-qualification",
        verifier=FictionalWorkerQualifier(key.public_key()))


async def allow():
    return None


class NativeWorkerProcessTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    async def invoke(self, worker, request=b"private fixture input", **kwargs):
        return await worker.run(request=request, deadline=asyncio.get_running_loop().time() + 3,
                                authorize_dispatch=kwargs.get("authorize", allow))

    async def test_private_pipe_output_is_bound_and_stderr_is_never_retained(self):
        worker = worker_fixture(self.root,
            "import sys\nsys.stderr.write('private fixture log')\nsys.stdout.buffer.write(sys.stdin.buffer.read())\n")
        result = await self.invoke(worker)
        self.assertEqual(result.output, b"private fixture input")
        self.assertEqual(result.output_sha256, sha(result.output))
        self.assertNotIn("private fixture", repr(result))
        self.assertNotIn("private fixture", repr(worker.last_failure))

    async def test_cancelled_passive_callback_retains_physical_slot_and_queues_no_threads(self):
        pool = OwnedPassiveReads(maximum_concurrency=1)
        started, release = threading.Event(), threading.Event()
        entered = []
        def blocked():
            entered.append("first")
            started.set()
            release.wait(2)
            return "first-finished"
        def next_callback():
            entered.append("next")
            return "next-finished"
        first = asyncio.create_task(pool.run(blocked))
        try:
            for _ in range(100):
                if started.is_set():
                    break
                await asyncio.sleep(.003)
            self.assertTrue(started.is_set())
            first.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await first
            self.assertEqual(pool.pending_count, 1)
            # Physical ownership cannot be cancelled like an asyncio wrapper.
            self.assertFalse(next(iter(pool._pending)).cancel())
            for _ in range(3):
                waiting = asyncio.create_task(pool.run(next_callback))
                await asyncio.sleep(.01)
                self.assertEqual(entered, ["first"])
                self.assertEqual(pool.pending_count, 1)
                waiting.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await waiting
            next_task = asyncio.create_task(pool.run(next_callback))
            await asyncio.sleep(.01)
            self.assertEqual(entered, ["first"])
            release.set()
            self.assertEqual(await next_task, "next-finished")
            await asyncio.sleep(0)
            self.assertEqual(pool.pending_count, 0)
            self.assertEqual(entered, ["first", "next"])
        finally:
            release.set()
            if not first.done():
                first.cancel()
                await asyncio.gather(first, return_exceptions=True)

    async def test_missing_or_changed_qualification_never_launches(self):
        marker = self.root / "started"
        worker = worker_fixture(self.root, "from pathlib import Path\nimport sys\nPath(sys.argv[1]).touch()\nprint('done')\n",
                                arguments=(str(marker),))
        worker.qualification_receipt = b"{}"
        with self.assertRaises(NativeWorkerFailure):
            await self.invoke(worker)
        self.assertFalse(marker.exists())

    async def test_factory_change_during_authorization_cannot_run_unqualified_bytes(self):
        marker = self.root / "unqualified"
        worker = worker_fixture(self.root, "import sys\nsys.stdout.buffer.write(sys.stdin.buffer.read())\n")
        async def change():
            Path(worker.launch.factory_artifact).write_text("from pathlib import Path\nPath(" + repr(str(marker)) + ").touch()\nprint('wrong')\n")
        with self.assertRaises(NativeWorkerFailure):
            await self.invoke(worker, authorize=change)
        self.assertFalse(marker.exists())

    async def test_sealed_factory_descriptor_cannot_be_modified_by_running_worker(self):
        worker = worker_fixture(self.root,
            "import sys\nfrom pathlib import Path\ntry:\n Path(__file__).write_bytes(b'changed')\nexcept OSError:\n sys.stdout.buffer.write(sys.stdin.buffer.read())\nelse:\n print('unsealed')\n")
        result = await self.invoke(worker)
        self.assertEqual(result.output, b"private fixture input")

    async def test_dispatch_denial_is_explicit_and_never_sends_input(self):
        marker = self.root / "received"
        worker = worker_fixture(self.root,
            "import sys\nfrom pathlib import Path\nif sys.stdin.buffer.read(): Path(sys.argv[1]).touch()\nprint('done')\n",
            arguments=(str(marker),))
        calls = 0
        async def deny_after_spawn():
            nonlocal calls
            calls += 1
            if calls == 2:
                raise NativeWorkerDispatchDenied("private details are not forwarded")
        with self.assertRaises(NativeWorkerFailure) as failure:
            await self.invoke(worker, authorize=deny_after_spawn)
        self.assertEqual(failure.exception.receipt.reason, "dispatch_refused")
        self.assertFalse(marker.exists())
        self.assertNotIn("private details", str(failure.exception))

    async def test_false_dispatch_result_and_invalid_deadline_never_launch(self):
        marker = self.root / "started"
        worker = worker_fixture(self.root,
            "from pathlib import Path\nimport sys\nPath(sys.argv[1]).touch()\nprint('done')\n",
            arguments=(str(marker),))
        async def false_result():
            return False
        with self.assertRaises(NativeWorkerFailure) as failed:
            await self.invoke(worker, authorize=false_result)
        self.assertEqual(failed.exception.receipt.reason, "dispatch_refused")
        self.assertFalse(marker.exists())
        for deadline in (float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                await worker.run(request=b"private fixture input", deadline=deadline, authorize_dispatch=allow)
        self.assertFalse(marker.exists())

    async def test_stderr_limit_and_no_inherited_environment(self):
        worker = worker_fixture(self.root, "import sys\nsys.stderr.write('private' * 10000)\nprint('done')\n")
        with self.assertRaises(NativeWorkerFailure) as failed:
            await self.invoke(worker)
        self.assertEqual(failed.exception.receipt.reason, "stderr_limit")
        from unittest.mock import patch
        worker = worker_fixture(self.root,
            "import os,sys\nsys.stdout.write('leaked' if 'FLORA_PRIVATE_FIXTURE_SECRET' in os.environ else 'empty')\n")
        with patch.dict(os.environ, {"FLORA_PRIVATE_FIXTURE_SECRET": "private fixture secret"}):
            observed = await self.invoke(worker)
        self.assertEqual(observed.output, b"empty")

    async def test_output_cap_and_exit_failure_have_safe_receipts(self):
        for script, reason in (("import sys\nsys.stdout.write('private' * 10000)\n", "output_limit"),
                               ("import sys\nsys.stderr.write('private')\nsys.exit(7)\n", "exit_failure")):
            worker = worker_fixture(self.root, script, maximum_output=64)
            with self.assertRaises(NativeWorkerFailure) as failure:
                await self.invoke(worker)
            self.assertEqual(failure.exception.receipt.reason, reason)
            self.assertNotIn("private", repr(failure.exception.receipt))

    async def test_exit_before_second_dispatch_preserves_status_and_valid_output(self):
        actual_spawn = asyncio.create_subprocess_exec
        for program, expected_exit, expected_output in (
                ("import sys\nsys.exit(7)\n", 7, None),
                ("print('empty')\n", 0, b"empty\n")):
            with self.subTest(exit_code=expected_exit):
                worker = worker_fixture(self.root, program)
                processes, calls = [], []
                async def spawn(*args, **kwargs):
                    process = await actual_spawn(*args, **kwargs)
                    processes.append(process)
                    return process
                async def authorize():
                    calls.append("authorized")
                    if len(calls) == 2:
                        await asyncio.sleep(.03)
                        # This legal dispatch delay ends only after the real
                        # child has exited, so the closed-input race is exact.
                        await asyncio.wait_for(processes[0].wait(), 1)
                        self.assertEqual(processes[0].returncode, expected_exit)
                with patch("flora.selected.native_worker.asyncio.create_subprocess_exec", new=spawn):
                    if expected_output is None:
                        with self.assertRaises(NativeWorkerFailure) as failed:
                            await self.invoke(worker, authorize=authorize)
                        self.assertEqual(failed.exception.receipt.reason, "exit_failure")
                        self.assertEqual(failed.exception.receipt.exit_code, expected_exit)
                    else:
                        observed = await self.invoke(worker, authorize=authorize)
                        self.assertEqual(observed.exit_code, expected_exit)
                        self.assertEqual(observed.output, expected_output)
                self.assertEqual(calls, ["authorized", "authorized"])

    async def test_cancellation_at_stdin_close_preserves_protocol_future(self):
        worker = worker_fixture(self.root, "import time\ntime.sleep(60)\n")
        loop, errors, processes = asyncio.get_running_loop(), [], []
        actual_handler, actual_spawn = loop.get_exception_handler(), asyncio.create_subprocess_exec
        loop.set_exception_handler(lambda current, context: errors.append(type(context.get("exception"))))
        closed = False
        async def spawn(*args, **kwargs):
            process = await actual_spawn(*args, **kwargs)
            processes.append(process)
            actual_close = process.stdin.close
            def close():
                nonlocal closed
                actual_close()
                if not closed:
                    closed = True
                    task.cancel()
            process.stdin.close = close
            return process
        try:
            with patch("flora.selected.native_worker.asyncio.create_subprocess_exec", new=spawn):
                task = asyncio.create_task(self.invoke(worker))
                with self.assertRaises(asyncio.CancelledError):
                    await task
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            self.assertTrue(closed)
            self.assertEqual(worker.last_failure.reason, "cancelled")
            self.assertEqual(errors, [])
            with self.assertRaises(ProcessLookupError):
                os.kill(processes[0].pid, 0)
        finally:
            loop.set_exception_handler(actual_handler)

    async def test_deadline_does_not_block_event_loop_and_terminates_process_group(self):
        marker = self.root / "pid"
        worker = worker_fixture(self.root, "import os,sys,time\nfrom pathlib import Path\nPath(sys.argv[1]).write_text(str(os.getpid()))\ntime.sleep(60)\n",
                                arguments=(str(marker),), wall_ms=120)
        ticks = 0
        async def ticker():
            nonlocal ticks
            for _ in range(10):
                await asyncio.sleep(.01)
                ticks += 1
        tick = asyncio.create_task(ticker())
        with self.assertRaises(NativeWorkerFailure) as failure:
            await self.invoke(worker)
        await tick
        self.assertEqual(failure.exception.receipt.reason, "timeout")
        self.assertEqual(ticks, 10)
        pid = int(marker.read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    async def test_cancellation_reaps_parent_and_kills_descendant_without_private_echo(self):
        marker = self.root / "pids"
        worker = worker_fixture(self.root,
            "import os,sys,time,subprocess\nfrom pathlib import Path\nchild=subprocess.Popen([sys.argv[2],'-I','-c','import time;time.sleep(60)'])\nPath(sys.argv[1]).write_text(str(os.getpid())+' '+str(child.pid))\ntime.sleep(60)\n",
            arguments=(str(marker), sys.executable))
        task = asyncio.create_task(self.invoke(worker))
        for _ in range(100):
            if marker.exists():
                break
            await asyncio.sleep(.01)
        self.assertTrue(marker.exists())
        parent, child = map(int, marker.read_text().split())
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(worker.last_failure.reason, "cancelled")
        with self.assertRaises(ProcessLookupError):
            os.kill(parent, 0)
        state = Path(f"/proc/{child}/stat")
        self.assertTrue(not state.exists() or state.read_text().split()[2] == "Z")


if __name__ == "__main__":
    unittest.main()
