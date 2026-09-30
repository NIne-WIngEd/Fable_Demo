"""Standalone sealed embedding process, not an installed model or training code.

Only inline artifacts received on the private pipe are consumed. Runtime package
paths and OS bounds are frozen public launch configuration, never private input.
The native transport independently qualifies this code and its dependencies.
"""
from __future__ import annotations

import base64
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import resource
import sys


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _inline_graph(model, external):
    if model.functions or any(v.domain not in {"", "ai.onnx"} for v in model.opset_import):
        raise ValueError("unsupported graph")
    def walk(message):
        name = message.DESCRIPTOR.full_name
        if name == "onnx.TensorProto" and (message.data_location == external or message.external_data):
            raise ValueError("external tensor")
        if name == "onnx.NodeProto" and message.domain not in {"", "ai.onnx"}:
            raise ValueError("custom operator")
        for descriptor, value in message.ListFields():
            if descriptor.message_type is not None:
                if descriptor.is_repeated:
                    for child in value:
                        walk(child)
                else:
                    walk(value)
    walk(model)


def _main():
    if len(sys.argv) != 2:
        raise ValueError("launch contract")
    binding = json.loads(base64.b64decode(sys.argv[1], validate=True))
    if (set(binding) != {"schema", "artifact", "artifact_sha256", "limits", "runtime_paths", "runtime_prefix"}
            or binding["schema"] != "flora-embedding-process-binding-v1"):
        raise ValueError("binding contract")
    limits = binding["limits"]
    expected = {"schema", "maximum_artifact_bytes", "maximum_text_bytes", "maximum_batch_bytes",
        "maximum_wall_time_ms", "maximum_output_bytes", "maximum_memory_bytes", "maximum_cpu_seconds",
        "maximum_open_files", "terminate_grace_ms"}
    if (set(limits) != expected or limits["schema"] != "flora-embedding-process-limits-v1"
            or any(isinstance(v, bool) or not isinstance(v, int) or v <= 0
                   for k, v in limits.items() if k != "schema")):
        raise ValueError("resource contract")
    # Limits are installed before private input decoding and native ML imports.
    for kind, maximum in ((resource.RLIMIT_AS, limits["maximum_memory_bytes"]),
                          (resource.RLIMIT_CPU, limits["maximum_cpu_seconds"]),
                          (resource.RLIMIT_NOFILE, limits["maximum_open_files"]),
                          (resource.RLIMIT_FSIZE, 0), (resource.RLIMIT_CORE, 0)):
        current, hard = resource.getrlimit(kind)
        value = maximum if hard == resource.RLIM_INFINITY else min(maximum, hard)
        resource.setrlimit(kind, (value, value))
    sys.dont_write_bytecode = True
    for path in reversed(binding["runtime_paths"]):
        if not isinstance(path, str) or not Path(path).is_absolute():
            raise ValueError("runtime contract")
        sys.path.insert(0, path)
    artifact = binding["artifact"]
    for package, expected_version in artifact["package_versions"]:
        if version(package) != expected_version:
            raise ValueError("runtime package changed")
    cap = (limits["maximum_artifact_bytes"] + limits["maximum_batch_bytes"]) * 2 + 262144
    request = sys.stdin.buffer.read(cap + 1)
    if not request or len(request) > cap:
        raise ValueError("input limit")
    body = json.loads(request)
    if (set(body) != {"schema", "artifact_sha256", "configuration", "files", "texts"}
            or body["schema"] != "flora-embedding-process-request-v1"
            or body["artifact_sha256"] != binding["artifact_sha256"]):
        raise ValueError("request contract")
    configuration = base64.b64decode(body["configuration"], validate=True)
    if _sha(configuration) != artifact["configuration_sha256"]:
        raise ValueError("configuration changed")
    config = json.loads(configuration)
    files = {k: base64.b64decode(v, validate=True) for k, v in body["files"].items()}
    if (set(files) != {k for k, _ in artifact["files"]}
            or sum(len(v) for v in files.values()) > limits["maximum_artifact_bytes"]
            or any(_sha(files[k]) != digest for k, digest in artifact["files"])):
        raise ValueError("artifact changed")
    texts = tuple(base64.b64decode(v, validate=True) for v in body["texts"])
    if (not texts or len(texts) > config["maximum_inputs"]
            or any(len(v) > limits["maximum_text_bytes"] for v in texts)
            or sum(len(v) for v in texts) > limits["maximum_batch_bytes"]):
        raise ValueError("text limit")
    import numpy as np
    import onnx
    import onnxruntime as ort
    from tokenizers import Tokenizer
    graph = onnx.load_model_from_string(files[config["model_file"]])
    _inline_graph(graph, onnx.TensorProto.EXTERNAL)
    tokenizer = Tokenizer.from_str(files[config["tokenizer_file"]].decode("utf-8"))
    tokenizer.no_truncation()
    tokenizer.enable_padding(pad_id=config["pad_id"], pad_token=config["pad_token"])
    if tokenizer.token_to_id(config["pad_token"]) != config["pad_id"]:
        raise ValueError("padding contract")
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.enable_mem_pattern = False
    options.enable_cpu_mem_arena = False
    options.log_severity_level = 4
    session = ort.InferenceSession(files[config["model_file"]], sess_options=options,
                                   providers=["CPUExecutionProvider"])
    if (session.get_providers() != ["CPUExecutionProvider"]
            or {v.name for v in session.get_inputs()} != set(config["input_names"])
            or any(v.type != "tensor(int64)" for v in session.get_inputs())
            or config["output_name"] not in {v.name for v in session.get_outputs()}):
        raise ValueError("graph interface")
    if config["chunk_rule"] != "contiguous_input_order_v1":
        raise ValueError("chunk contract")
    vectors, token_counts = [], []
    # Exactly one session and one parent deadline cover all contiguous chunks.
    # This grouping is part of the qualified artifact configuration; it does
    # not assert an arbitrary graph is invariant to batching or padding.
    for start in range(0, len(texts), config["maximum_batch"]):
        chunk = texts[start:start + config["maximum_batch"]]
        encoded = tokenizer.encode_batch([v.decode("utf-8") for v in chunk],
                                        add_special_tokens=config["add_special_tokens"])
        counts = [len(v.ids) for v in encoded]
        if any(v > config["maximum_tokens"] for v in counts):
            raise ValueError("token limit")
        arrays = {"input_ids": np.asarray([v.ids for v in encoded], dtype=np.int64),
                  "attention_mask": np.asarray([v.attention_mask for v in encoded], dtype=np.int64)}
        if "token_type_ids" in config["input_names"]:
            arrays["token_type_ids"] = np.asarray([v.type_ids for v in encoded], dtype=np.int64)
        output = session.run([config["output_name"]], arrays)[0]
        if (output.shape != (len(chunk), config["dimension"]) or not np.isfinite(output).all()
                or not np.any(output != 0, axis=1).all()):
            raise ValueError("sentence vectors")
        vectors.extend([[float(v) for v in row] for row in output])
        token_counts.extend(counts)
    result = json.dumps({"schema": "flora-embedding-process-output-v1", "request_sha256": _sha(request),
        "artifact_sha256": binding["artifact_sha256"], "configuration_sha256": _sha(configuration),
        "content_sha256": [_sha(v) for v in texts], "token_counts": token_counts,
        "vectors": vectors},
        sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(result) > limits["maximum_output_bytes"]:
        raise ValueError("output limit")
    sys.stdout.buffer.write(result)
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    try:
        _main()
    except Exception:
        # Never copy input, graph messages, filesystem details or tracebacks to
        # the parent. The process transport records a bounded safe exit receipt.
        sys.exit(1)
