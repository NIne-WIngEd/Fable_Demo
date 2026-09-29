"""General-model-plus-memory comparator ports and frozen execution contracts.

No provider transport, tokenizer or embedding model is installed here. Actual
adapters are supplied and independently qualified. Signed exchange evidence
attests a trusted transport's observations, not a provider's signature.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import json
from typing import Callable, Protocol

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from cognitive_kernel.canonical import canonical_sha256, require_identifier, require_sha256

from .comparison_run import (
    ArmExecutionFailure, ArmResult, ArmStopped, ExecutionRequest, MeasuredUsage, PreparationRequest,
)
from .selected.context import LocalContext


def encoded(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def identifier(value: str, name: str) -> None:
    if require_identifier(value, name) != value:
        raise ValueError(f"{name} must be canonical")


def positive(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True)
class ProviderConfiguration:
    provider_id: str
    feature_engine_id: str
    requested_model_id: str
    permitted_response_model_ids: tuple[str, ...]
    endpoint: str
    generation_parameters: bytes = field(repr=False)
    transport_artifact_sha256: str
    wire_compiler_artifact_sha256: str

    def record(self) -> dict:
        for name in ("provider_id", "feature_engine_id"):
            identifier(getattr(self, name), name)
        if (not self.requested_model_id or not self.endpoint.startswith("https://")
                or not self.permitted_response_model_ids
                or len(set(self.permitted_response_model_ids)) != len(self.permitted_response_model_ids)
                or any(not isinstance(value, str) or not value for value in self.permitted_response_model_ids)):
            raise ValueError("provider requires an exact deployment and response-model allowlist")
        require_sha256(self.transport_artifact_sha256, "transport_artifact_sha256")
        require_sha256(self.wire_compiler_artifact_sha256, "wire_compiler_artifact_sha256")
        if not isinstance(self.generation_parameters, bytes) or not isinstance(json.loads(self.generation_parameters), dict):
            raise ValueError("actual generation parameters must be JSON object bytes")
        return {"provider_id": self.provider_id, "feature_engine_id": self.feature_engine_id,
                "requested_model_id": self.requested_model_id,
                "permitted_response_model_ids": list(self.permitted_response_model_ids),
                "endpoint": self.endpoint,
                "generation_parameters_base64": base64.b64encode(self.generation_parameters).decode(),
                "transport_artifact_sha256": self.transport_artifact_sha256,
                "wire_compiler_artifact_sha256": self.wire_compiler_artifact_sha256}

    def digest(self) -> str:
        return canonical_sha256(self.record())


@dataclass(frozen=True)
class MemoryConfiguration:
    embedding_artifact_sha256: str
    embedding_configuration_sha256: str
    tokenizer_artifact_sha256: str
    tokenizer_configuration_sha256: str
    dimension: int
    window_characters: int
    window_overlap_characters: int
    dense_candidates: int
    rank_fusion_constant: int
    maximum_windows: int
    minimum_sources: int

    def record(self) -> dict:
        for name in ("embedding_artifact_sha256", "embedding_configuration_sha256",
                     "tokenizer_artifact_sha256", "tokenizer_configuration_sha256"):
            require_sha256(getattr(self, name), name)
        for name in ("dimension", "window_characters", "dense_candidates", "rank_fusion_constant",
                     "maximum_windows", "minimum_sources"):
            positive(getattr(self, name), name)
        overlap = self.window_overlap_characters
        if isinstance(overlap, bool) or not isinstance(overlap, int) or not 0 <= overlap < self.window_characters:
            raise ValueError("invalid source-window overlap")
        return vars(self).copy()


@dataclass(frozen=True)
class BaselineConfiguration:
    provider: ProviderConfiguration
    memory: MemoryConfiguration
    system_instruction: bytes = field(repr=False)
    producer_component: str = "flora-comparator-general-memory-v1"

    def record(self) -> dict:
        identifier(self.producer_component, "producer_component")
        if not isinstance(self.system_instruction, bytes) or not self.system_instruction:
            raise ValueError("baseline needs actual frozen system instructions")
        self.system_instruction.decode("utf-8")
        return {"schema": "flora-general-memory-configuration-v1", "provider": self.provider.record(),
                "memory": self.memory.record(),
                "system_instruction_base64": base64.b64encode(self.system_instruction).decode(),
                "producer_component": self.producer_component}

    def digest(self) -> str:
        return canonical_sha256(self.record())


@dataclass(frozen=True)
class TokenCount:
    content_sha256: str
    artifact_sha256: str
    configuration_sha256: str
    tokens: int

    def verify(self, content: bytes, memory: MemoryConfiguration) -> None:
        if (self.content_sha256 != sha(content)
                or self.artifact_sha256 != memory.tokenizer_artifact_sha256
                or self.configuration_sha256 != memory.tokenizer_configuration_sha256
                or isinstance(self.tokens, bool) or not isinstance(self.tokens, int) or self.tokens < 0):
            raise ValueError("token count does not bind the actual input and frozen tokenizer")


class ExactTokenCounter(Protocol):
    """Local, independently qualified tokenizer, not a characters/4 estimate."""
    def count(self, content: bytes) -> TokenCount: ...


@dataclass(frozen=True)
class EmbeddingBatch:
    input_sha256: tuple[str, ...]
    artifact_sha256: str
    configuration_sha256: str
    vectors: tuple[tuple[float, ...], ...]


class LocalEmbeddingProvider(Protocol):
    """Local existing model; no network disclosure or training is authorized."""
    async def embed(self, content: tuple[bytes, ...]) -> EmbeddingBatch: ...


class ProviderWireCompiler(Protocol):
    """Qualified local provider serializer; returns the actual request body.

    Credential headers are outside this content object and never stored here.
    It may only serialize the supplied input/configuration, not append memory.
    """
    artifact_sha256: str
    def compile(self, *, configuration: ProviderConfiguration,
                semantic_input: bytes, response_token_budget: int) -> bytes: ...


def provider_payload(configuration: BaselineConfiguration, *, question: bytes,
                     context: LocalContext, response_token_budget: int,
                     wire_compiler: ProviderWireCompiler) -> bytes:
    positive(response_token_budget, "response_token_budget")
    semantic = encoded({"schema": "flora-comparator-provider-input-v1",
        "provider_configuration": configuration.provider.record(),
        "system": configuration.system_instruction.decode("utf-8"),
        "question": question.decode("utf-8"), "maximum_output_tokens": response_token_budget,
        "evidence": [{"kind": item.kind, "source_event_ids": list(item.source_event_ids),
                      "record_id": item.record_id, "version_id": item.version_id,
                      "content": item.content.decode("utf-8")} for item in context.items]})
    if wire_compiler.artifact_sha256 != configuration.provider.wire_compiler_artifact_sha256:
        raise ValueError("provider wire compiler differs from frozen artifact")
    actual = wire_compiler.compile(configuration=configuration.provider, semantic_input=semantic,
                                   response_token_budget=response_token_budget)
    if not isinstance(actual, bytes) or not actual:
        raise ValueError("provider compiler did not produce an actual request body")
    return actual


@dataclass(frozen=True)
class ProviderRequest:
    configuration: ProviderConfiguration
    payload: bytes = field(repr=False)
    maximum_output_tokens: int

    def record(self) -> dict:
        positive(self.maximum_output_tokens, "maximum_output_tokens")
        return {"schema": "flora-provider-dispatch-v1", "configuration_sha256": self.configuration.digest(),
                "payload_sha256": sha(self.payload), "maximum_output_tokens": self.maximum_output_tokens}


@dataclass(frozen=True)
class ProviderResponse:
    configuration_sha256: str
    request_sha256: str
    request_id: str
    returned_model_id: str
    raw_response: bytes = field(repr=False)
    output: bytes = field(repr=False)
    input_tokens: int
    output_tokens: int
    authorization_marker: str
    proof: bytes = field(repr=False)
    cost_microunits: int | None = None
    currency: str | None = None

    def observation(self) -> dict:
        if not self.request_id or not self.returned_model_id:
            raise ValueError("provider observation needs an actual request ID and returned model")
        for name in ("configuration_sha256", "request_sha256", "authorization_marker"):
            require_sha256(getattr(self, name), name)
        for name in ("raw_response", "output", "proof"):
            if not isinstance(getattr(self, name), bytes) or not getattr(self, name):
                raise ValueError("provider observation is missing actual bytes or its proof")
        MeasuredUsage("validation", 0, self.input_tokens, self.output_tokens, 1,
                      self.cost_microunits, self.currency).validate()
        return {"schema": "flora-provider-observation-v1", "configuration_sha256": self.configuration_sha256,
                "request_sha256": self.request_sha256, "request_id": self.request_id,
                "returned_model_id": self.returned_model_id, "raw_response_sha256": sha(self.raw_response),
                "output_sha256": sha(self.output), "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens, "cost_microunits": self.cost_microunits,
                "currency": self.currency, "authorization_marker": self.authorization_marker}


class ProviderExchangeVerifier(Protocol):
    def verify(self, *, request: ProviderRequest, response: ProviderResponse) -> None: ...


class Ed25519TransportObservationVerifier:
    """Verifies an enrolled first-party dispatch/parse/metering boundary key.

    This is not an official provider signature. The supplied transport must
    observe authenticated network dispatch/response, parse output and actual
    usage, and sign these bindings. Qualification of that transport is separate.
    """
    def __init__(self, *, configuration: ProviderConfiguration, public_key: bytes):
        self.configuration = configuration
        self.public_key = Ed25519PublicKey.from_public_bytes(public_key)

    def verify(self, *, request: ProviderRequest, response: ProviderResponse) -> None:
        if (request.configuration != self.configuration
                or response.configuration_sha256 != self.configuration.digest()
                or response.request_sha256 != sha(request.payload)
                or response.returned_model_id not in self.configuration.permitted_response_model_ids):
            raise ValueError("provider observation differs from the frozen dispatch")
        self.public_key.verify(response.proof, encoded(response.observation()))


class ExternallySuppliedFrontierClient(Protocol):
    configuration: ProviderConfiguration
    async def generate(self, request: ProviderRequest, *, authorize_transfer: Callable[[], str]) -> ProviderResponse:
        """Recheck callback immediately before dispatch; honor async cancellation."""
        ...


class GeneralMemoryRetriever(Protocol):
    configuration: BaselineConfiguration
    async def prepare(self, request: PreparationRequest) -> LocalContext: ...


class ComparatorDisclosurePolicy(Protocol):
    def authorize(self, *, request: ExecutionRequest, provider_request: ProviderRequest) -> str: ...


class ComparatorRecorder(Protocol):
    def record(self, *, request: ExecutionRequest, provider_request: ProviderRequest,
               response: ProviderResponse, token_count: TokenCount,
               authorization_marker: str) -> ArmResult: ...


class GeneralMemoryArmAdapter:
    def __init__(self, *, configuration: BaselineConfiguration, memory: GeneralMemoryRetriever,
                 tokenizer: ExactTokenCounter, wire_compiler: ProviderWireCompiler,
                 client: ExternallySuppliedFrontierClient,
                 exchange_verifier: ProviderExchangeVerifier,
                 disclosure: ComparatorDisclosurePolicy, recorder: ComparatorRecorder):
        configuration.record()
        if memory.configuration != configuration or client.configuration != configuration.provider:
            raise ValueError("comparator components have different frozen configuration")
        if wire_compiler.artifact_sha256 != configuration.provider.wire_compiler_artifact_sha256:
            raise ValueError("comparator wire compiler differs from frozen configuration")
        self.configuration, self.memory, self.tokenizer, self.client = configuration, memory, tokenizer, client
        self.wire_compiler = wire_compiler
        self.exchange_verifier, self.disclosure, self.recorder = exchange_verifier, disclosure, recorder

    async def prepare(self, request: PreparationRequest) -> LocalContext:
        return await self.memory.prepare(request)

    async def execute(self, request: ExecutionRequest) -> ArmResult:
        configuration = self.configuration
        if (request.binding.model_artifact_sha256 != configuration.provider.digest()
                or request.binding.lineage_sha256 != configuration.digest()
                or request.binding.producer_component != configuration.producer_component
                or request.plan.protocol.feature_engine_id != configuration.provider.feature_engine_id):
            raise ValueError("comparator does not match the frozen arm/provider binding")
        if request.plan.feature_call_budget < 1:
            raise ArmStopped("unavailable")
        payload = provider_payload(configuration, question=request.question, context=request.context,
                                   response_token_budget=request.plan.protocol.response_token_budget,
                                   wire_compiler=self.wire_compiler)
        count = self.tokenizer.count(payload)
        count.verify(payload, configuration.memory)
        # Count the actual whole request, including system/query/source envelope.
        if count.tokens > request.plan.context_token_budget:
            raise ArmStopped("unavailable")
        dispatch = ProviderRequest(configuration.provider, payload, request.plan.protocol.response_token_budget)
        transfer_markers = []
        def authorize():
            try:
                marker = self.disclosure.authorize(request=request, provider_request=dispatch)
            except PermissionError as exc:
                raise ArmStopped("refused") from exc
            require_sha256(marker, "authorization_marker")
            transfer_markers.append(marker)
            return marker
        authorize()
        preflight_checks = len(transfer_markers)
        if self.client.configuration != configuration.provider:
            raise ValueError("provider configuration changed before dispatch")
        response = await self.client.generate(dispatch, authorize_transfer=authorize)
        if (len(transfer_markers) <= preflight_checks
                or response.authorization_marker != transfer_markers[-1]):
            raise ValueError("transport lacks its actual transfer-boundary authorization binding")
        self.exchange_verifier.verify(request=dispatch, response=response)
        # Only an authenticated observation can supply metering for a rejected
        # result. Subsequent permission or recording failures cannot undo a call.
        observed_usage = MeasuredUsage(configuration.provider.feature_engine_id, count.tokens,
            response.input_tokens, response.output_tokens, 1, response.cost_microunits, response.currency)
        observed_usage.validate()
        try:
            authorize()  # Refuse acceptance if authority changed during generation.
            if self.client.configuration != configuration.provider:
                raise ValueError("provider configuration changed during dispatch")
            return self.recorder.record(request=request, provider_request=dispatch, response=response,
                                        token_count=count, authorization_marker=response.authorization_marker)
        except ArmExecutionFailure as failure:
            raise ArmExecutionFailure(failure.status, observed_usage) from None
        except ArmStopped as stop:
            raise ArmStopped(stop.status, observed_usage) from None
        except ValueError:
            raise ArmExecutionFailure("invalid_result", observed_usage) from None
        except Exception:
            # Retain metering without returning private exception text or output.
            raise ArmExecutionFailure("failed", observed_usage) from None
