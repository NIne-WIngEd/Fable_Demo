"""Optional stateless OpenAI Responses transport with no automatic live call.

Endpoint/schema verified against official API documentation on 2026-09-29.
Keys, model choice, source disclosure authority and observer enrollment are
explicit supplied inputs. Observations are first-party, not provider signatures.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from importlib.metadata import version
import json
import math
from pathlib import Path
from typing import Callable, Protocol

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import httpx

from cognitive_kernel.canonical import canonical_sha256, require_sha256

from ..comparator import ProviderConfiguration, ProviderRequest, ProviderResponse, encoded, sha
from ..comparison_run import ArmStopped, MeasuredUsage


ENDPOINT = "https://api.openai.com/v1/responses"


def compiler_artifact_sha256() -> str:
    return sha(Path(__file__).read_bytes())


def transport_artifact_sha256(*, timeout_seconds: float, maximum_response_bytes: int,
                             httpx_version: str) -> str:
    if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (float, int))
            or not math.isfinite(timeout_seconds) or timeout_seconds <= 0
            or isinstance(maximum_response_bytes, bool) or not isinstance(maximum_response_bytes, int)
            or maximum_response_bytes <= 0 or not httpx_version):
        raise ValueError("invalid frozen OpenAI transport limits")
    return canonical_sha256({"schema": "flora-openai-transport-v1", "source_sha256": compiler_artifact_sha256(),
        "httpx_version": httpx_version, "timeout_seconds": timeout_seconds,
        "maximum_response_bytes": maximum_response_bytes, "endpoint": ENDPOINT,
        "tls_verification": True, "follow_redirects": False, "trust_environment": False,
        "automatic_retries": 0})


def generation_settings(configuration: ProviderConfiguration) -> dict:
    configuration.record()
    if configuration.provider_id != "openai" or configuration.endpoint != ENDPOINT:
        raise ValueError("OpenAI credentials may only be sent to the pinned official Responses endpoint")
    parameters = json.loads(configuration.generation_parameters)
    if set(parameters) - {"temperature", "top_p", "reasoning"}:
        raise ValueError("unsupported OpenAI generation field")
    if "temperature" in parameters and "top_p" in parameters:
        raise ValueError("freeze either temperature or top_p")
    for name, upper in (("temperature", 2), ("top_p", 1)):
        if name in parameters:
            value = parameters[name]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= upper:
                raise ValueError("invalid OpenAI sampling parameter")
    if "reasoning" in parameters:
        reasoning = parameters["reasoning"]
        if (not isinstance(reasoning, dict) or set(reasoning) != {"effort"}
                or reasoning["effort"] not in {"low", "medium", "high"}):
            raise ValueError("unsupported OpenAI reasoning configuration")
    return parameters


class OpenAIResponsesWireCompiler:
    @property
    def artifact_sha256(self) -> str:
        return compiler_artifact_sha256()

    def compile(self, *, configuration: ProviderConfiguration, semantic_input: bytes,
                response_token_budget: int) -> bytes:
        settings = generation_settings(configuration)
        if (isinstance(response_token_budget, bool) or not isinstance(response_token_budget, int)
                or response_token_budget < 16):
            raise ValueError("Responses max_output_tokens must be at least 16")
        data = json.loads(semantic_input)
        if (set(data) != {"schema", "provider_configuration", "system", "question", "maximum_output_tokens", "evidence"}
                or data["schema"] != "flora-comparator-provider-input-v1"
                or data["provider_configuration"] != configuration.record()
                or data["maximum_output_tokens"] != response_token_budget
                or not isinstance(data["system"], str) or not isinstance(data["question"], str)
                or not isinstance(data["evidence"], list)):
            raise ValueError("OpenAI compiler input differs from frozen semantic contract")
        # No conversation/thread, files, hidden previous response or tools.
        return encoded({"model": configuration.requested_model_id, "instructions": data["system"],
            "input": encoded({"question": data["question"], "evidence": data["evidence"]}).decode(),
            "max_output_tokens": response_token_budget, "store": False, "stream": False,
            "background": False, "truncation": "disabled", "tools": [], "parallel_tool_calls": False,
            **settings})


@dataclass(frozen=True)
class TransportAttempt:
    metadata: dict
    actual_request: bytes = field(repr=False)
    actual_response: bytes | None = field(repr=False)
    proof: bytes = field(repr=False)


class PrivateTransportAttemptSink(Protocol):
    """Host-authorized encrypted append-only sink, not telemetry or public log."""
    def record(self, attempt: TransportAttempt) -> None: ...


class TransportCustodyError(ValueError):
    """Do not accept a provider result when private attempt recording failed."""


def _usage(data: dict, engine: str) -> MeasuredUsage | None:
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None
    try:
        value = MeasuredUsage(engine, usage["input_tokens"], usage["input_tokens"], usage["output_tokens"], 1)
        value.validate()
        return value
    except (KeyError, ValueError, TypeError):
        return None


class OpenAIResponsesAsyncClient:
    def __init__(self, *, configuration: ProviderConfiguration, credential_provider: Callable[[], str],
                 signing_key: Ed25519PrivateKey, approved_observer_public_key_sha256: str,
                 attempt_sink: PrivateTransportAttemptSink, timeout_seconds: float,
                 maximum_response_bytes: int, httpx_version: str,
                 fixture_transport: httpx.AsyncBaseTransport | None = None):
        generation_settings(configuration)
        if version("httpx") != httpx_version:
            raise ValueError("OpenAI HTTP runtime differs from frozen package version")
        if configuration.wire_compiler_artifact_sha256 != compiler_artifact_sha256():
            raise ValueError("OpenAI compiler source differs from frozen artifact")
        if configuration.transport_artifact_sha256 != transport_artifact_sha256(
                timeout_seconds=timeout_seconds, maximum_response_bytes=maximum_response_bytes,
                httpx_version=httpx_version):
            raise ValueError("OpenAI transport differs from frozen code/runtime/limits")
        public = signing_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        require_sha256(approved_observer_public_key_sha256, "approved observer key")
        if sha(public) != approved_observer_public_key_sha256:
            raise PermissionError("transport observer key has not been independently enrolled")
        self.configuration, self._credentials, self._key = configuration, credential_provider, signing_key
        self._sink, self._timeout, self._maximum = attempt_sink, timeout_seconds, maximum_response_bytes
        self._httpx_version = httpx_version
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds), follow_redirects=False,
            trust_env=False, verify=True, transport=fixture_transport)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _validate_dispatch(self, request: ProviderRequest) -> dict:
        if request.configuration != self.configuration:
            raise ValueError("OpenAI request changed its frozen configuration")
        settings = generation_settings(self.configuration)
        if self.configuration.transport_artifact_sha256 != transport_artifact_sha256(
                timeout_seconds=self._timeout, maximum_response_bytes=self._maximum, httpx_version=self._httpx_version):
            raise ValueError("OpenAI transport artifact changed before dispatch")
        body = json.loads(request.payload)
        fixed = {"model", "instructions", "input", "max_output_tokens", "store", "stream", "background",
                 "truncation", "tools", "parallel_tool_calls"}
        if (set(body) != fixed | set(settings) or body["model"] != self.configuration.requested_model_id
                or body["max_output_tokens"] != request.maximum_output_tokens
                or isinstance(request.maximum_output_tokens, bool) or request.maximum_output_tokens < 16
                or body["store"] is not False or body["stream"] is not False or body["background"] is not False
                or body["truncation"] != "disabled" or body["tools"] != [] or body["parallel_tool_calls"] is not False
                or not isinstance(body["instructions"], str) or not isinstance(body["input"], str)
                or any(body[name] != value for name, value in settings.items())):
            raise ValueError("OpenAI request violates the stateless allowlisted wire schema")
        return body

    def _record_attempt(self, *, request, marker, raw, status, request_id, result,
                        response_complete=False, usage=None, model=None):
        metadata = {"schema": "flora-openai-transport-attempt-v1", "configuration_sha256": self.configuration.digest(),
            "request_sha256": sha(request.payload), "authorization_marker": marker,
            "response_sha256": None if raw is None else sha(raw), "http_status": status,
            "response_complete": response_complete,
            "request_id": request_id, "result": result, "returned_model_id": model,
            "usage": None if usage is None else vars(usage), "cost_microunits": None,
            "observer_public_key_sha256": sha(self._key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))}
        try:
            self._sink.record(TransportAttempt(metadata, request.payload, raw, self._key.sign(encoded(metadata))))
        except Exception:
            raise TransportCustodyError("private transport attempt custody is unavailable") from None

    async def generate(self, request: ProviderRequest, *, authorize_transfer: Callable[[], str]) -> ProviderResponse:
        self._validate_dispatch(request)
        credential = self._credentials()
        if not isinstance(credential, str) or not credential or "\n" in credential or "\r" in credential:
            raise ValueError("OpenAI credential is unavailable or malformed")
        headers = {"Authorization": "Bearer " + credential, "Content-Type": "application/json"}
        raw, status, request_id, usage, model = None, None, None, None, None
        response_complete = False
        marker = authorize_transfer()
        require_sha256(marker, "transfer authorization marker")
        try:
            # No intervening await before actual network dispatch.
            async with asyncio.timeout(self._timeout):
                async with self._client.stream("POST", ENDPOINT, content=request.payload, headers=headers) as response:
                    status, request_id = response.status_code, response.headers.get("x-request-id")
                    captured = bytearray()
                    async for chunk in response.aiter_bytes():
                        available = self._maximum - len(captured)
                        captured.extend(chunk[:available])
                        raw = bytes(captured)
                        if len(chunk) > available:
                            raise ValueError("OpenAI response exceeds the frozen byte limit")
                    raw = bytes(captured)
                    response_complete = True
            if status != 200:
                try:
                    data = json.loads(raw)
                except (ValueError, TypeError):
                    data = None
                if isinstance(data, dict):
                    usage, model = _usage(data, self.configuration.feature_engine_id), data.get("model")
                self._record_attempt(request=request, marker=marker, raw=raw, status=status,
                    request_id=request_id, result="http_error", response_complete=response_complete,
                    usage=usage, model=model)
                raise ArmStopped("unavailable", usage)
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("OpenAI response is not a JSON object")
            usage, model = _usage(data, self.configuration.feature_engine_id), data.get("model")
            if (not request_id or usage is None or model not in self.configuration.permitted_response_model_ids
                    or not isinstance(data.get("output"), list)):
                raise ValueError("OpenAI response lacks completed model/usage/request binding")
            if data.get("status") != "completed":
                self._record_attempt(request=request, marker=marker, raw=raw, status=status,
                    request_id=request_id, result="incomplete", response_complete=response_complete,
                    usage=usage, model=model)
                raise ArmStopped("unavailable", usage)
            texts = []
            for item in data["output"]:
                if not isinstance(item, dict):
                    raise ValueError("malformed OpenAI output item")
                if item.get("type") == "reasoning":
                    continue
                if (item.get("type") != "message" or item.get("role") != "assistant"
                        or item.get("status") != "completed" or not isinstance(item.get("content"), list)):
                    raise ValueError("unexpected tool/non-message output from text-only baseline")
                for content in item["content"]:
                    if not isinstance(content, dict):
                        raise ValueError("malformed OpenAI message content")
                    if content.get("type") == "refusal":
                        self._record_attempt(request=request, marker=marker, raw=raw, status=status,
                            request_id=request_id, result="refused", response_complete=response_complete,
                            usage=usage, model=model)
                        raise ArmStopped("refused", usage)
                    if content.get("type") != "output_text" or not isinstance(content.get("text"), str):
                        raise ValueError("unexpected OpenAI output content")
                    texts.append(content["text"])
            output = "".join(texts).encode()
            if not output:
                raise ValueError("OpenAI returned no visible text")
            result = ProviderResponse(self.configuration.digest(), sha(request.payload), request_id, model,
                raw, output, usage.input_tokens, usage.output_tokens, marker, b"unsigned")
            result = replace(result, proof=self._key.sign(encoded(result.observation())))
            self._record_attempt(request=request, marker=marker, raw=raw, status=status,
                request_id=request_id, result="success", response_complete=response_complete,
                usage=usage, model=model)
            return result
        except ArmStopped:
            raise
        except TransportCustodyError:
            raise
        except asyncio.CancelledError as cancelled:
            try:
                self._record_attempt(request=request, marker=marker, raw=raw, status=status,
                    request_id=request_id, result="cancelled", response_complete=response_complete,
                    usage=usage, model=model)
            except TransportCustodyError:
                # Cancellation remains cancellation; failed custody is never a
                # success receipt and must be independently monitored by its sink.
                pass
            raise cancelled
        except (TimeoutError, httpx.TimeoutException):
            self._record_attempt(request=request, marker=marker, raw=raw, status=status,
                request_id=request_id, result="timeout", response_complete=response_complete,
                usage=usage, model=model)
            raise TimeoutError("OpenAI request timed out") from None
        except Exception:
            self._record_attempt(request=request, marker=marker, raw=raw, status=status,
                request_id=request_id, result="invalid_or_failed", response_complete=response_complete,
                usage=usage, model=model)
            raise ValueError("OpenAI exchange failed validation or transport") from None
