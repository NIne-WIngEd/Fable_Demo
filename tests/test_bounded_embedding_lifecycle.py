"""Actual process and tiny generated ONNX mechanics, never learned quality proof."""
import asyncio
import base64
from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from cognitive_kernel.canonical import canonical_json_bytes
from cognitive_kernel.contracts import ProductHostScope
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from flora.comparator import sha
from flora.providers.local_artifacts import (EmbeddingProcessLimits, SuppliedArtifactManifest,
    SuppliedONNXSentenceEmbeddings, embedding_process_configuration)
from flora.selected.native_worker import (NativeWorkerFailure, QualifiedNativeProcessWorker,
    VerifiedNativeWorkerQualification)


AVAILABLE = all(importlib.util.find_spec(v) is not None for v in ("onnx", "onnxruntime", "tokenizers", "numpy"))


class FictionalEmbeddingQualifier:
    """Fixture-only independent authority; no real artifact suitability claim."""
    def __init__(self, key):
        self.key = key
    def verify_worker(self, *, manifest, receipt):
        body = json.loads(receipt)
        self.key.verify(base64.b64decode(body["signature"], validate=True), canonical_json_bytes(body["payload"]))
        if body["payload"] != {"schema": "fictional-embedding-qualification-v1", "manifest": manifest.manifest_sha256}:
            raise ValueError("fixture qualification changed")
        return VerifiedNativeWorkerQualification("fixture-embedding-qualifier", "fixture-embedding-qualification",
            manifest.manifest_sha256, sha(receipt), True)


def make_worker(manifest, limits, runtime_paths):
    scope = ProductHostScope.create(product_id="friday", host_instance_id="fixture-host",
        schema_version="1.0.0", encryption_domain="fixture-key")
    launch, process_manifest = embedding_process_configuration(manifest=manifest, limits=limits,
        scope=scope, authority_namespace_id="fixture-authority", worker_id="fixture-embedding-worker",
        runtime_paths=runtime_paths)
    key = Ed25519PrivateKey.generate()
    payload = {"schema": "fictional-embedding-qualification-v1", "manifest": process_manifest.manifest_sha256}
    receipt = canonical_json_bytes({"payload": payload,
        "signature": base64.b64encode(key.sign(canonical_json_bytes(payload))).decode("ascii")})
    return QualifiedNativeProcessWorker(manifest=process_manifest, launch=launch, qualification_receipt=receipt,
        qualifier_id="fixture-embedding-qualifier", qualification_id="fixture-embedding-qualification",
        verifier=FictionalEmbeddingQualifier(key.public_key()))


def artifact_fixture(root):
    import onnx
    from onnx import helper, TensorProto
    from tokenizers import Tokenizer
    from tokenizers.models import WordLevel
    from tokenizers.pre_tokenizers import Whitespace
    from importlib.metadata import version
    tokenizer = Tokenizer(WordLevel({"[PAD]": 0, "[UNK]": 1, "hello": 2, "world": 3}, unk_token="[UNK]"))
    tokenizer.pre_tokenizer = Whitespace()
    tokenizer_bytes = tokenizer.to_str().encode("utf-8")
    graph = helper.make_graph([
        helper.make_node("Cast", ["input_ids"], ["float_ids"], to=TensorProto.FLOAT),
        helper.make_node("ReduceSum", ["float_ids", "axis"], ["vectors"], keepdims=1)],
        "mechanical-fixture-only", [
            helper.make_tensor_value_info("input_ids", TensorProto.INT64, [None, None]),
            helper.make_tensor_value_info("attention_mask", TensorProto.INT64, [None, None])],
        [helper.make_tensor_value_info("vectors", TensorProto.FLOAT, [None, 1])],
        [helper.make_tensor("axis", TensorProto.INT64, [1], [1])])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)], ir_version=10)
    model_bytes = model.SerializeToString()
    (root / "fixture.onnx").write_bytes(model_bytes)
    (root / "tokenizer.json").write_bytes(tokenizer_bytes)
    configuration = canonical_json_bytes({"kind": "inline_onnx_sentence_vectors", "model_file": "fixture.onnx",
        "tokenizer_file": "tokenizer.json", "dimension": 1, "maximum_tokens": 8, "maximum_batch": 2,
        "maximum_inputs": 4, "chunk_rule": "contiguous_input_order_v1",
        "pad_token": "[PAD]", "pad_id": 0, "add_special_tokens": False,
        "input_names": ["input_ids", "attention_mask"], "output_name": "vectors"})
    manifest = SuppliedArtifactManifest((("fixture.onnx", sha(model_bytes)), ("tokenizer.json", sha(tokenizer_bytes))),
        tuple((name, version(name)) for name in ("onnx", "onnxruntime", "tokenizers", "numpy")), configuration)
    # Explicit dependency directories, not model directories. The fixed launch
    # receives no inherited PYTHONPATH and disables site/user lookup. Qualification of these fixture paths is fictional and stated.
    runtime_paths = tuple(dict.fromkeys(str(Path(importlib.util.find_spec(name).origin).parent.parent.resolve())
                                       for name in ("onnx", "onnxruntime", "tokenizers", "numpy")))
    return manifest, runtime_paths


@unittest.skipUnless(AVAILABLE, "optional pinned embedding verification dependencies not installed")
class BoundedEmbeddingLifecycleTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manifest, self.paths = artifact_fixture(self.root)
        self.limits = EmbeddingProcessLimits(1024 * 1024, 1024, 2048, 6000, 65536,
                                            4 * 1024**3, 10, 64, 100)
        self.calls = 0
        async def allow():
            self.calls += 1
        self.allow = allow

    def adapter(self, *, limits=None, authorize=None):
        limits = limits or self.limits
        worker = make_worker(self.manifest, limits, self.paths)
        return SuppliedONNXSentenceEmbeddings(root=self.root, manifest=self.manifest,
            limits=limits, worker=worker, authorize_read=authorize or self.allow, runtime_paths=self.paths)

    async def test_actual_inline_onnx_runs_only_in_fresh_child_and_binds_every_input(self):
        adapter = self.adapter()
        with patch("onnxruntime.InferenceSession", side_effect=AssertionError("parent inference forbidden")):
            result = await adapter.embed((b"hello", b"hello world"))
        self.assertEqual(result.vectors, ((2.0,), (5.0,)))
        self.assertEqual(result.input_sha256, (sha(b"hello"), sha(b"hello world")))
        self.assertEqual(result.artifact_sha256, adapter.artifact_sha256)
        self.assertGreaterEqual(self.calls, 6)

    async def test_frozen_chunks_share_one_child_preserve_input_order_and_total_cap(self):
        adapter = self.adapter()
        original_spawn = asyncio.create_subprocess_exec
        spawned = []
        async def observe_spawn(*args, **kwargs):
            proc = await original_spawn(*args, **kwargs)
            spawned.append(proc)
            return proc
        with patch("asyncio.create_subprocess_exec", side_effect=observe_spawn):
            result = await adapter.embed((b"hello", b"hello world", b"world", b"world world"))
        self.assertEqual(result.vectors, ((2.0,), (5.0,), (3.0,), (6.0,)))
        self.assertEqual(len(spawned), 1)
        self.assertEqual(adapter.configuration["maximum_batch"], 2)
        self.assertEqual(adapter.configuration["maximum_inputs"], 4)
        with self.assertRaises(TypeError):
            adapter.configuration["maximum_inputs"] = 999
        with self.assertRaises(ValueError):
            await adapter.embed((b"hello",) * 5)

    async def test_changed_artifact_refused_before_any_dispatch(self):
        adapter = self.adapter()
        (self.root / "fixture.onnx").write_bytes(b"changed fixture")
        with patch.object(adapter.worker, "run", side_effect=AssertionError("dispatch forbidden")):
            with self.assertRaises(ValueError):
                await adapter.embed((b"hello",))

    async def test_missing_qualification_refuses_before_private_input(self):
        adapter = self.adapter()
        adapter.worker.qualification_receipt = b"{}"
        with self.assertRaises(NativeWorkerFailure) as error:
            await adapter.embed((b"hello",))
        self.assertEqual(error.exception.receipt.reason, "worker_rejected")

    async def test_current_gate_revoked_after_spawn_refuses_input(self):
        async def revoke():
            self.calls += 1
            if self.calls == 4:
                raise PermissionError("private reason")
        adapter = self.adapter(authorize=revoke)
        with self.assertRaises(NativeWorkerFailure) as error:
            await adapter.embed((b"hello",))
        self.assertEqual(error.exception.receipt.reason, "dispatch_refused")
        self.assertNotIn("private reason", repr(error.exception.receipt))

    async def test_current_gate_revoked_after_inference_refuses_acceptance(self):
        async def revoke():
            self.calls += 1
            if self.calls == 5:
                raise PermissionError("revoked")
        adapter = self.adapter(authorize=revoke)
        with self.assertRaises(PermissionError):
            await adapter.embed((b"hello",))

    async def test_input_batch_artifact_and_output_bounds_are_actual(self):
        for content in ((b"x" * 1025,), (b"hello",) * 5):
            adapter = self.adapter()
            with patch.object(adapter.worker, "run", side_effect=AssertionError("dispatch forbidden")):
                with self.assertRaises(ValueError):
                    await adapter.embed(content)
        tiny_files = self.adapter(limits=replace(self.limits, maximum_artifact_bytes=10))
        with self.assertRaises(ValueError):
            await tiny_files.embed((b"hello",))
        tiny_output = self.adapter(limits=replace(self.limits, maximum_output_bytes=10))
        with self.assertRaises(NativeWorkerFailure):
            await tiny_output.embed((b"hello",))

    async def test_token_bound_refuses_without_silent_truncation(self):
        adapter = self.adapter()
        with self.assertRaises(NativeWorkerFailure):
            await adapter.embed((b"hello " * 9,))

    async def test_deadline_and_cancellation_terminate_owned_process(self):
        original_spawn = asyncio.create_subprocess_exec
        spawned = []
        async def observe_spawn(*args, **kwargs):
            proc = await original_spawn(*args, **kwargs)
            spawned.append(proc)
            return proc
        # Force expiry after actual child startup, including a blocked current
        # authorization callback. The process cannot survive the expired await.
        async def delayed_gate():
            self.calls += 1
            if self.calls == 4:
                await asyncio.sleep(2)
        adapter = self.adapter(limits=replace(self.limits, maximum_wall_time_ms=1500), authorize=delayed_gate)
        with patch("asyncio.create_subprocess_exec", side_effect=observe_spawn):
            with self.assertRaises((NativeWorkerFailure, TimeoutError)):
                await adapter.embed((b"hello",))
        self.assertEqual(len(spawned), 1)
        self.assertIsNotNone(spawned[0].returncode)
        with self.assertRaises(ProcessLookupError):
            os.kill(spawned[0].pid, 0)
        self.calls = 0
        spawned.clear()
        adapter = self.adapter()
        dispatched = asyncio.Event()
        async def allow_spawn():
            self.calls += 1
            if self.calls == 4:
                dispatched.set()
                await asyncio.sleep(2)
        adapter.authorize_read = allow_spawn
        with patch("asyncio.create_subprocess_exec", side_effect=observe_spawn):
            task = asyncio.create_task(adapter.embed((b"hello",)))
            await asyncio.wait_for(dispatched.wait(), 3)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(adapter.worker.last_failure.reason, "cancelled")
        self.assertEqual(len(spawned), 1)
        self.assertIsNotNone(spawned[0].returncode)
        with self.assertRaises(ProcessLookupError):
            os.kill(spawned[0].pid, 0)

    async def test_one_adapter_serializes_actual_children_and_queue_deadline(self):
        adapter = self.adapter()
        first_spawned = asyncio.Event()
        release = asyncio.Event()
        original_authorize = adapter.authorize_read
        async def hold_gate():
            await original_authorize()
            if self.calls == 4:
                first_spawned.set()
                await release.wait()
        adapter.authorize_read = hold_gate
        first = asyncio.create_task(adapter.embed((b"hello",)))
        try:
            await asyncio.wait_for(first_spawned.wait(), 3)
            with self.assertRaises(TimeoutError):
                await adapter.embed((b"world",), deadline=asyncio.get_running_loop().time() + .02)
            self.assertEqual(self.calls, 4)
            release.set()
            result = await first
            self.assertEqual(result.vectors, ((2.0,),))
        finally:
            release.set()
            if not first.done():
                first.cancel()
            await asyncio.gather(first, return_exceptions=True)

    async def test_long_caller_deadline_cannot_extend_whole_call_wall_cap(self):
        adapter = self.adapter(limits=replace(self.limits, maximum_wall_time_ms=30))
        entered = 0
        async def slow_authority():
            nonlocal entered
            entered += 1
            await asyncio.sleep(1)
        adapter.authorize_read = slow_authority
        started = asyncio.get_running_loop().time()
        # Constructor already verified the exact worker; isolate this test to
        # the whole-call timer around a cooperative current-authority await.
        with patch.object(adapter, "_check_worker_binding", return_value=None):
            with self.assertRaises(TimeoutError):
                await adapter.embed((b"hello",), deadline=started + 10)
        self.assertLess(asyncio.get_running_loop().time() - started, .5)
        self.assertEqual(entered, 1)
        self.assertIsNone(adapter.worker.last_failure)

    async def test_cancelled_passive_callback_retains_its_only_slot_until_done(self):
        adapter = self.adapter()
        entered, release = threading.Event(), threading.Event()
        original = adapter._check_worker_binding
        physical_calls = 0
        def paused_check():
            nonlocal physical_calls
            physical_calls += 1
            if physical_calls == 1:
                entered.set()
                if not release.wait(3):
                    raise ValueError("fixture callback timeout")
            original()
        with patch.object(adapter, "_check_worker_binding", side_effect=paused_check):
            first = asyncio.create_task(adapter.embed((b"hello",)))
            try:
                for _ in range(100):
                    if entered.is_set():
                        break
                    await asyncio.sleep(.005)
                self.assertTrue(entered.is_set())
                first.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await first
                for _ in range(3):
                    with self.assertRaises(TimeoutError):
                        await adapter.embed((b"world",), deadline=asyncio.get_running_loop().time() + .02)
                self.assertEqual(physical_calls, 1)
                self.assertIsNone(adapter.worker.last_failure)
                release.set()
                result = await adapter.embed((b"hello",))
                self.assertEqual(result.vectors, ((2.0,),))
            finally:
                release.set()
                if not first.done():
                    first.cancel()
                await asyncio.gather(first, return_exceptions=True)

    async def test_symlinked_artifact_directory_cannot_leave_supplied_root(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "fixture.onnx").write_bytes((self.root / "fixture.onnx").read_bytes())
        (self.root / "alias").symlink_to(outside, target_is_directory=True)
        altered = replace(self.manifest, files=(("alias/fixture.onnx", dict(self.manifest.files)["fixture.onnx"]),
            self.manifest.files[1]))
        with self.assertRaises(OSError):
            altered.verify(self.root, maximum_total_bytes=self.limits.maximum_artifact_bytes)

    async def test_memory_resource_bound_is_installed_before_native_imports(self):
        adapter = self.adapter(limits=replace(self.limits, maximum_memory_bytes=32 * 1024**2))
        with self.assertRaises(NativeWorkerFailure):
            await adapter.embed((b"hello",))


class EmbeddingConfigurationTest(unittest.TestCase):
    def test_no_default_worker_read_authority_or_unbounded_resource_limit(self):
        with self.assertRaises(ValueError):
            EmbeddingProcessLimits(1, 1, 1, 1, 1, 1, 16, 16, 0).record()


if __name__ == "__main__":
    unittest.main()
