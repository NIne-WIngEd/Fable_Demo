"""Optional offline tokenizer and exported sentence-embedding adapters.

Only explicitly supplied files are read. No Hub lookup, weight download,
training, invented pooling or custom model code is performed. Exact file and
package bindings do not qualify an artifact's semantic quality or data rights.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from importlib.metadata import version
import json
from pathlib import Path

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
        return {"schema": "flora-supplied-local-artifact-v1", "files": [list(v) for v in self.files],
            "package_versions": [list(v) for v in self.package_versions],
            "adapter_source_sha256": sha(Path(__file__).read_bytes()),
            "configuration_sha256": sha(self.configuration)}

    def digest(self) -> str:
        return canonical_sha256(self.record())

    def verify(self, root: Path) -> dict[str, bytes]:
        self.record()
        base = root.resolve(strict=True)
        content = {}
        for name, digest in self.files:
            path = base / name
            if path.is_symlink() or not path.is_file() or not path.resolve(strict=True).is_relative_to(base):
                raise ValueError("artifact file is missing or leaves supplied custody")
            value = path.read_bytes()
            if sha(value) != digest:
                raise ValueError("supplied artifact file bytes changed")
            content[name] = value
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


class SuppliedONNXSentenceEmbeddings:
    """Runs an existing inline ONNX export that already outputs sentence vectors.

    This adapter performs no mean/CLS pooling, normalization, truncation or
    training. The supplied graph owns those semantics and must be qualified.
    Run bounded native work in a terminable worker for production deadlines;
    asyncio thread cancellation alone cannot terminate an ONNX computation.
    """
    def __init__(self, *, root: Path, manifest: SuppliedArtifactManifest):
        content = manifest.verify(root)
        config = json.loads(manifest.configuration)
        fields = {"kind", "model_file", "tokenizer_file", "dimension", "maximum_tokens",
                  "maximum_batch", "pad_token", "pad_id", "add_special_tokens", "input_names", "output_name"}
        if (set(config) != fields or config["kind"] != "inline_onnx_sentence_vectors"
                or set(content) != {config["model_file"], config["tokenizer_file"]}
                or set(dict(manifest.package_versions)) != {"tokenizers", "onnxruntime", "onnx", "numpy"}
                or config["input_names"] not in [["input_ids", "attention_mask"],
                    ["input_ids", "attention_mask", "token_type_ids"]]
                or not isinstance(config["add_special_tokens"], bool)
                or not isinstance(config["pad_token"], str) or not config["pad_token"]
                or not isinstance(config["output_name"], str) or not config["output_name"]):
            raise ValueError("unsupported supplied ONNX sentence-vector contract")
        for name in ("dimension", "maximum_tokens", "maximum_batch"):
            if isinstance(config[name], bool) or not isinstance(config[name], int) or config[name] <= 0:
                raise ValueError("invalid frozen ONNX bound")
        if isinstance(config["pad_id"], bool) or not isinstance(config["pad_id"], int) or config["pad_id"] < 0:
            raise ValueError("invalid padding token ID")
        import onnx
        import onnxruntime as ort
        from tokenizers import Tokenizer
        graph = onnx.load_model_from_string(content[config["model_file"]])
        # Memory-loaded inline export has no external-file or custom-op route.
        _require_inline_standard_onnx(graph, onnx.TensorProto.EXTERNAL)
        self._tokenizer = Tokenizer.from_str(content[config["tokenizer_file"]].decode())
        self._tokenizer.no_truncation()
        self._tokenizer.enable_padding(pad_id=config["pad_id"], pad_token=config["pad_token"])
        if self._tokenizer.token_to_id(config["pad_token"]) != config["pad_id"]:
            raise ValueError("supplied tokenizer pad contract differs")
        self._session = ort.InferenceSession(content[config["model_file"]], providers=["CPUExecutionProvider"])
        if (self._session.get_providers() != ["CPUExecutionProvider"]
                or {value.name for value in self._session.get_inputs()} != set(config["input_names"])
                or any(value.type != "tensor(int64)" for value in self._session.get_inputs())
                or config["output_name"] not in {value.name for value in self._session.get_outputs()}):
            raise ValueError("supplied ONNX runtime input/output contract differs")
        self.configuration = config
        self.artifact_sha256, self.configuration_sha256 = manifest.digest(), sha(manifest.configuration)

    def _embed(self, content: tuple[bytes, ...]) -> EmbeddingBatch:
        import numpy as np
        config = self.configuration
        if (not content or len(content) > config["maximum_batch"]
                or any(not isinstance(value, bytes) for value in content)):
            raise ValueError("embedding batch exceeds the frozen local contract")
        encoded_text = self._tokenizer.encode_batch([value.decode("utf-8") for value in content],
                                                   add_special_tokens=config["add_special_tokens"])
        if any(len(value.ids) > config["maximum_tokens"] for value in encoded_text):
            raise ValueError("embedding input exceeds limit; no silent truncation")
        arrays = {"input_ids": np.asarray([value.ids for value in encoded_text], dtype=np.int64),
                  "attention_mask": np.asarray([value.attention_mask for value in encoded_text], dtype=np.int64)}
        if "token_type_ids" in config["input_names"]:
            arrays["token_type_ids"] = np.asarray([value.type_ids for value in encoded_text], dtype=np.int64)
        output = self._session.run([config["output_name"]], arrays)[0]
        if (output.shape != (len(content), config["dimension"]) or not np.isfinite(output).all()
                or not np.any(output != 0, axis=1).all()):
            raise ValueError("ONNX export did not return finite nonzero sentence vectors")
        return EmbeddingBatch(tuple(sha(value) for value in content), self.artifact_sha256,
            self.configuration_sha256, tuple(tuple(float(value) for value in row) for row in output))

    async def embed(self, content: tuple[bytes, ...]) -> EmbeddingBatch:
        return await asyncio.to_thread(self._embed, content)


def _require_inline_standard_onnx(model, external_location: int) -> None:
    """Refuse external tensor references even inside sparse/subgraph attributes."""
    if (model.functions or any(value.domain not in {"", "ai.onnx"} for value in model.opset_import)):
        raise ValueError("ONNX adapter requires an inline standard-op graph without local functions")

    def inspect(message) -> None:
        name = message.DESCRIPTOR.full_name
        if name == "onnx.TensorProto" and (message.data_location == external_location or message.external_data):
            raise ValueError("ONNX adapter refuses external tensor files")
        if name == "onnx.NodeProto" and message.domain not in {"", "ai.onnx"}:
            raise ValueError("ONNX adapter refuses custom operator domains")
        for descriptor, value in message.ListFields():
            if descriptor.message_type is not None:
                if descriptor.is_repeated:
                    for child in value:
                        inspect(child)
                else:
                    inspect(value)

    inspect(model)
