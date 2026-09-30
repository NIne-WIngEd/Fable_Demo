"""Optional offline tokenizer and exported sentence-embedding adapters.

Only explicitly supplied files are read. No Hub lookup, weight download,
training, invented pooling or custom model code is performed. Exact file and
package bindings do not qualify an artifact's semantic quality or data rights.
"""
from __future__ import annotations

import asyncio
import base64
import math
import os
import stat
import sys
from dataclasses import dataclass
from importlib.metadata import version
import json
from pathlib import Path
from typing import Awaitable, Callable
from types import MappingProxyType

from cognitive_kernel.canonical import canonical_sha256, require_sha256

from ..comparator import EmbeddingBatch, TokenCount, sha


@dataclass(frozen=True)
class SuppliedArtifactManifest:
    files: tuple[tuple[str, str], ...]
    package_versions: tuple[tuple[str, str], ...]
    configuration: bytes

    def record(self) -> dict:
        if (not self.files or len(dict(self.files)) != len(self.files)
                or not self.package_versions or len(dict(self.package_versions)) != len(self.package_versions)):
            raise ValueError("supplied artifact needs unique file and package bindings")
        for name, digest in self.files:
            path = Path(name)
            if not name or path.is_absolute() or ".." in path.parts or str(path) != name:
                raise ValueError("artifact file must have a canonical relative path")
            require_sha256(digest, "artifact file digest")
        if any(not name or not expected for name, expected in self.package_versions):
            raise ValueError("artifact runtime versions must be exact")
        if not isinstance(self.configuration, bytes) or not isinstance(json.loads(self.configuration), dict):
            raise ValueError("supplied artifact needs actual configuration bytes")
        record = {"schema": "flora-supplied-local-artifact-v1", "files": [list(v) for v in self.files],
            "package_versions": [list(v) for v in self.package_versions],
            "adapter_source_sha256": sha(Path(__file__).read_bytes()),
            "configuration_sha256": sha(self.configuration)}
        if json.loads(self.configuration).get("kind") == "inline_onnx_sentence_vectors":
            record["embedding_worker_source_sha256"] = sha(Path(__file__).with_name("embedding_worker.py").read_bytes())
        return record

    def digest(self) -> str:
        return canonical_sha256(self.record())

    def verify(self, root: Path, *, maximum_total_bytes: int | None = None) -> dict[str, bytes]:
        self.record()
        if (maximum_total_bytes is not None and (isinstance(maximum_total_bytes, bool)
                or not isinstance(maximum_total_bytes, int) or maximum_total_bytes <= 0)):
            raise ValueError("artifact total byte bound must be a positive integer")
        base = root.resolve(strict=True)
        content = {}
        total = 0
        base_fd = os.open(base, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            for name, digest in self.files:
                parts = Path(name).parts
                parent_fd = os.dup(base_fd)
                try:
                    for part in parts[:-1]:
                        next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                                          dir_fd=parent_fd)
                        os.close(parent_fd)
                        parent_fd = next_fd
                    fd = os.open(parts[-1], os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
                                 dir_fd=parent_fd)
                    with os.fdopen(fd, "rb") as stream:
                        meta = os.fstat(stream.fileno())
                        if (not stat.S_ISREG(meta.st_mode)
                                or (maximum_total_bytes is not None and total + meta.st_size > maximum_total_bytes)):
                            raise ValueError("supplied artifact exceeds its actual regular-file bound")
                        remaining = None if maximum_total_bytes is None else maximum_total_bytes - total + 1
                        value = stream.read() if remaining is None else stream.read(remaining)
                    total += len(value)
                    if maximum_total_bytes is not None and total > maximum_total_bytes:
                        raise ValueError("supplied artifact grew beyond its byte bound")
                    if sha(value) != digest:
                        raise ValueError("supplied artifact file bytes changed")
                    content[name] = value
                finally:
                    os.close(parent_fd)
        finally:
            os.close(base_fd)
        for package, expected in self.package_versions:
            if version(package) != expected:
                raise ValueError("local artifact runtime differs from its frozen package version")
        return content


class SuppliedBodyTokenizer:
    """Exact tokenization of supplied UTF-8 body, not server-processed input.

    OpenAI message boundary/role formatting can add tokens not represented in
    these bytes. Server usage remains authoritative at acceptance. Qualification
    must decide whether this tokenizer is suitable for comparator preflight.
    """
    def __init__(self, *, root: Path, manifest: SuppliedArtifactManifest):
        content = manifest.verify(root)
        config = json.loads(manifest.configuration)
        if (set(config) != {"kind", "tokenizer_file", "add_special_tokens", "count_domain"}
                or config["kind"] != "serialized_body_tokenizer"
                or config["add_special_tokens"] is not False
                or config["count_domain"] != "compiled_request_body_utf8"
                or set(content) != {config["tokenizer_file"]}
                or set(dict(manifest.package_versions)) != {"tokenizers"}):
            raise ValueError("unsupported local body-tokenizer contract")
        from tokenizers import Tokenizer
        self._tokenizer = Tokenizer.from_str(content[config["tokenizer_file"]].decode())
        self._tokenizer.no_truncation()
        self._tokenizer.no_padding()
        self.artifact_sha256, self.configuration_sha256 = manifest.digest(), sha(manifest.configuration)

    def count(self, content: bytes) -> TokenCount:
        if not isinstance(content, bytes):
            raise ValueError("body tokenizer requires actual bytes")
        result = self._tokenizer.encode(content.decode("utf-8"), add_special_tokens=False)
        return TokenCount(sha(content), self.artifact_sha256, self.configuration_sha256, len(result.ids))


@dataclass(frozen=True)
class EmbeddingProcessLimits:
    """Frozen limits apply to the complete fresh child lifetime, including imports."""
    maximum_artifact_bytes: int
    maximum_text_bytes: int
    maximum_batch_bytes: int
    maximum_wall_time_ms: int
    maximum_output_bytes: int
    maximum_memory_bytes: int
    maximum_cpu_seconds: int
    maximum_open_files: int
    terminate_grace_ms: int

    def record(self) -> dict:
        for name, value in vars(self).items():
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError("embedding process limits must be positive integers")
        if self.maximum_open_files < 16 or self.maximum_batch_bytes < self.maximum_text_bytes:
            raise ValueError("embedding descriptor or aggregate byte bound is invalid")
        return {"schema": "flora-embedding-process-limits-v1", **vars(self)}


def _embedding_config(manifest: SuppliedArtifactManifest) -> dict:
    manifest.record()
    if len(manifest.configuration) > 65536:
        raise ValueError("embedding configuration exceeds its bound")
    config = json.loads(manifest.configuration)
    fields = {"kind", "model_file", "tokenizer_file", "dimension", "maximum_tokens",
              "maximum_batch", "maximum_inputs", "chunk_rule", "pad_token", "pad_id", "add_special_tokens", "input_names", "output_name"}
    if (set(config) != fields or config["kind"] != "inline_onnx_sentence_vectors"
            or set(dict(manifest.files)) != {config["model_file"], config["tokenizer_file"]}
            or set(dict(manifest.package_versions)) != {"tokenizers", "onnxruntime", "onnx", "numpy"}
            or config["chunk_rule"] != "contiguous_input_order_v1"
            or config["input_names"] not in [["input_ids", "attention_mask"],
                ["input_ids", "attention_mask", "token_type_ids"]]
            or not isinstance(config["add_special_tokens"], bool)
            or not isinstance(config["pad_token"], str) or not config["pad_token"]
            or not isinstance(config["output_name"], str) or not config["output_name"]):
        raise ValueError("unsupported supplied ONNX sentence-vector contract")
    for name in ("dimension", "maximum_tokens", "maximum_batch", "maximum_inputs"):
        if isinstance(config[name], bool) or not isinstance(config[name], int) or config[name] <= 0:
            raise ValueError("invalid frozen ONNX bound")
    if config["maximum_inputs"] < config["maximum_batch"]:
        raise ValueError("total embedding input cap must cover its frozen batch cap")
    if isinstance(config["pad_id"], bool) or not isinstance(config["pad_id"], int) or config["pad_id"] < 0:
        raise ValueError("invalid padding token ID")
    return config


def _embedding_binding(manifest: SuppliedArtifactManifest, limits: EmbeddingProcessLimits,
                       runtime_paths: tuple[str, ...], runtime_prefix: str) -> dict:
    _embedding_config(manifest)
    limits.record()
    if (not isinstance(runtime_paths, tuple) or len(set(runtime_paths)) != len(runtime_paths)
            or any(not isinstance(v, str) or not Path(v).is_absolute()
                   or str(Path(v).resolve(strict=True)) != v or not Path(v).is_dir() for v in runtime_paths)):
        raise ValueError("embedding runtime paths must be exact explicit local directories")
    if (not isinstance(runtime_prefix, str) or not Path(runtime_prefix).is_absolute()
            or str(Path(runtime_prefix).resolve(strict=True)) != runtime_prefix or not Path(runtime_prefix).is_dir()):
        raise ValueError("embedding Python runtime prefix must be an exact local directory")
    return {"schema": "flora-embedding-process-binding-v1", "artifact": manifest.record(),
            "artifact_sha256": manifest.digest(), "limits": limits.record(),
            "runtime_paths": list(runtime_paths), "runtime_prefix": runtime_prefix}


def embedding_process_configuration(*, manifest: SuppliedArtifactManifest,
        limits: EmbeddingProcessLimits, scope, authority_namespace_id: str, worker_id: str,
        executable: str = sys.executable, runtime_paths: tuple[str, ...] = (),
        runtime_prefix: str = sys.base_prefix):
    """Build the actual sealed worker launch/manifest; qualification remains external.

    Runtime directories are explicit code dependencies, never taken from private
    input. An independent qualifier must cover their transitive files and rights.
    """
    from ..selected.native_worker import NativeProcessLaunch, NativeWorkerManifest
    from cognitive_kernel.canonical import canonical_json_bytes
    binding = _embedding_binding(manifest, limits, runtime_paths, runtime_prefix)
    executable = str(Path(executable).resolve(strict=True))
    factory = str(Path(__file__).with_name("embedding_worker.py").resolve(strict=True))
    public_binding = base64.b64encode(canonical_json_bytes(binding)).decode("ascii")
    environment = tuple(sorted({"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1", "TOKENIZERS_PARALLELISM": "false",
        "PYTHONHOME": runtime_prefix}.items()))
    launch = NativeProcessLaunch(executable, factory, ("-S", "-s", "-P", "{factory_artifact}", public_binding), environment)
    worker_source = sha(Path(factory).read_bytes())
    source = sha(Path(__file__).read_bytes())
    # Native transport fields bind the real embedding codec, parent read gate and
    # graph/token/batch limits. They do not pretend an embedding is a judgment.
    native_manifest = NativeWorkerManifest(scope, authority_namespace_id, worker_id,
        sha(Path(executable).read_bytes()), worker_source, launch.configuration_sha256(),
        worker_source, source, canonical_sha256(binding), worker_source,
        canonical_sha256({"configuration": sha(manifest.configuration), "limits": limits.record()}),
        (limits.maximum_artifact_bytes + limits.maximum_batch_bytes) * 2 + 262144,
        limits.maximum_output_bytes, 4096, limits.maximum_wall_time_ms, limits.terminate_grace_ms,
        max(Path(executable).stat().st_size, Path(factory).stat().st_size))
    native_manifest.record()
    return launch, native_manifest


class SuppliedONNXSentenceEmbeddings:
    """A fresh, terminable CPU process runs an existing sentence-vector export.

    No ONNX or tokenizer inference occurs in the parent. The concrete sealed
    worker is shipped here; actual existing artifacts and independent transitive
    worker qualification are still supplied by the deployment, not fabricated.
    """
    def __init__(self, *, root: Path, manifest: SuppliedArtifactManifest,
                 limits: EmbeddingProcessLimits, worker,
                 authorize_read: Callable[[], Awaitable[None]], runtime_paths: tuple[str, ...] = (),
                 runtime_prefix: str = sys.base_prefix):
        from ..selected.native_worker import OwnedPassiveReads, QualifiedNativeProcessWorker
        if not isinstance(worker, QualifiedNativeProcessWorker) or not callable(authorize_read):
            raise TypeError("embedding requires the actual qualified process and current read gate")
        config = _embedding_config(manifest)
        config["input_names"] = tuple(config["input_names"])
        self.configuration = MappingProxyType(config)
        self.root, self.manifest, self.limits = root, manifest, limits
        self.worker, self.authorize_read, self.runtime_paths = worker, authorize_read, runtime_paths
        self.runtime_prefix = runtime_prefix
        self._invocation_lock = asyncio.Lock()
        self._passive_reads = OwnedPassiveReads(maximum_concurrency=1)
        self.artifact_sha256, self.configuration_sha256 = manifest.digest(), sha(manifest.configuration)
        self._check_worker_binding()

    def _check_worker_binding(self) -> None:
        launch, expected = embedding_process_configuration(manifest=self.manifest, limits=self.limits,
            scope=self.worker.manifest.scope, authority_namespace_id=self.worker.manifest.authority_namespace_id,
            worker_id=self.worker.manifest.worker_id, executable=self.worker.launch.executable,
            runtime_paths=self.runtime_paths, runtime_prefix=self.runtime_prefix)
        if self.worker.launch != launch or self.worker.manifest != expected:
            raise ValueError("embedding process differs from the exact supplied-artifact binding")

    async def _authorize(self) -> None:
        if await self.authorize_read() is not None:
            raise PermissionError("embedding read refused")

    async def embed(self, content: tuple[bytes, ...], *, deadline: float | None = None) -> EmbeddingBatch:
        from cognitive_kernel.canonical import canonical_json_bytes
        from ..selected.native_worker import NativeWorkerDispatchDenied
        config = self.configuration
        if (not isinstance(content, tuple) or not content or len(content) > config["maximum_inputs"]
                or any(not isinstance(v, bytes) or len(v) > self.limits.maximum_text_bytes for v in content)
                or sum(len(v) for v in content) > self.limits.maximum_batch_bytes):
            raise ValueError("embedding batch exceeds its frozen byte/batch contract")
        if deadline is None:
            deadline = asyncio.get_running_loop().time() + self.limits.maximum_wall_time_ms / 1000
        if isinstance(deadline, bool) or not isinstance(deadline, (int, float)) or not math.isfinite(deadline):
            raise ValueError("embedding deadline must be a finite event-loop timestamp")
        deadline = min(deadline, asyncio.get_running_loop().time() + self.limits.maximum_wall_time_ms / 1000)
        async with asyncio.timeout_at(deadline):
            async with self._invocation_lock:
                await self._passive_reads.run(self._check_worker_binding)
                await self._authorize()
                # Passive bounded regular-file reads only; cancellation leaves no
                # inference or publication continuation in this owned reader.
                files = await self._passive_reads.run(self.manifest.verify, self.root,
                    maximum_total_bytes=self.limits.maximum_artifact_bytes)
                await self._authorize()
                def serialize():
                    return canonical_json_bytes({"schema": "flora-embedding-process-request-v1",
                    "artifact_sha256": self.artifact_sha256,
                    "configuration": base64.b64encode(self.manifest.configuration).decode("ascii"),
                    "files": {k: base64.b64encode(v).decode("ascii") for k, v in files.items()},
                    "texts": [base64.b64encode(v).decode("ascii") for v in content]})
                request = await self._passive_reads.run(serialize)
                async def authorize_dispatch():
                    try:
                        await self._authorize()
                        await self._passive_reads.run(self._check_worker_binding)
                    except PermissionError:
                        raise NativeWorkerDispatchDenied("refused") from None
                observation = await self.worker.run(request=request, deadline=deadline,
                    authorize_dispatch=authorize_dispatch)
                await self._authorize()
                def decode_output():
                    body = json.loads(observation.output)
                    if (set(body) != {"schema", "request_sha256", "artifact_sha256", "configuration_sha256", "content_sha256", "token_counts", "vectors"}
                            or body["schema"] != "flora-embedding-process-output-v1"
                            or body["request_sha256"] != sha(request) or body["artifact_sha256"] != self.artifact_sha256
                            or body["configuration_sha256"] != self.configuration_sha256
                            or body["content_sha256"] != [sha(v) for v in content]
                            or not isinstance(body["token_counts"], list) or len(body["token_counts"]) != len(content)
                            or any(isinstance(v, bool) or not isinstance(v, int) or v < 0
                                   or v > config["maximum_tokens"] for v in body["token_counts"])
                            or not isinstance(body["vectors"], list) or len(body["vectors"]) != len(content)):
                        raise ValueError("embedding worker returned unbound output")
                    for row in body["vectors"]:
                        if (not isinstance(row, list) or len(row) != config["dimension"]
                                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in row)
                                or not any(v != 0 for v in row)):
                            raise ValueError("embedding worker returned invalid sentence vectors")
                    return tuple(tuple(float(v) for v in row) for row in body["vectors"])
                vectors = await self._passive_reads.run(decode_output)
                await self._authorize()
                return EmbeddingBatch(tuple(sha(v) for v in content), self.artifact_sha256,
                    self.configuration_sha256, vectors)
