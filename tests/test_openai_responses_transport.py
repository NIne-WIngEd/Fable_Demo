"""Mock HTTP fixtures; no OpenAI call, real API key or model prediction."""
import asyncio
from dataclasses import replace
from importlib.metadata import version
import json
from pathlib import Path
import tempfile
import unittest

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import httpx

from flora.comparator import (
    Ed25519TransportObservationVerifier, ProviderConfiguration, ProviderRequest, encoded, sha,
)
from flora.comparison_run import ArmStopped
from flora.providers.local_artifacts import SuppliedArtifactManifest
from flora.providers.openai_responses import (
    ENDPOINT, OpenAIResponsesAsyncClient, OpenAIResponsesWireCompiler,
    TransportCustodyError, compiler_artifact_sha256, transport_artifact_sha256,
)


class Sink:
    def __init__(self):
        self.attempts = []
    def record(self, attempt):
        self.attempts.append(attempt)


def configuration(timeout=.5, maximum=10000):
    return ProviderConfiguration("openai", "fixture-openai-model", "fixture-approved-snapshot",
        ("fixture-approved-snapshot",), ENDPOINT, b'{"reasoning":{"effort":"low"}}',
        transport_artifact_sha256(timeout_seconds=timeout, maximum_response_bytes=maximum,
                                 httpx_version=version("httpx")), compiler_artifact_sha256())


def request(config):
    semantic = encoded({"schema": "flora-comparator-provider-input-v1", "provider_configuration": config.record(),
        "system": "Fictional frozen system instruction.", "question": "Fictional common question.",
        "maximum_output_tokens": 32, "evidence": [{"kind": "comparator_original_window",
            "source_event_ids": ["fictional-source"], "record_id": "fictional-source",
            "version_id": "f" * 64, "content": "Fictional authorized excerpt."}]})
    body = OpenAIResponsesWireCompiler().compile(configuration=config, semantic_input=semantic, response_token_budget=32)
    return ProviderRequest(config, body, 32)


def response_body(**changes):
    value = {"id": "fixture-response-id", "model": "fixture-approved-snapshot", "status": "completed",
        "output": [{"type": "reasoning", "summary": []}, {"type": "message", "role": "assistant",
            "status": "completed", "content": [{"type": "output_text", "text": "Supplied mock text."}]}],
        "usage": {"input_tokens": 123, "output_tokens": 10}}
    value.update(changes)
    return encoded(value)


class OpenAITransportContractsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.public = self.key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.sink = Sink()

    def client(self, handler, *, config=None, timeout=.5, maximum=10000):
        return OpenAIResponsesAsyncClient(configuration=config or configuration(timeout, maximum),
            credential_provider=lambda: "fictional-placeholder-not-a-real-credential", signing_key=self.key,
            approved_observer_public_key_sha256=sha(self.public), attempt_sink=self.sink,
            timeout_seconds=timeout, maximum_response_bytes=maximum, httpx_version=version("httpx"),
            fixture_transport=httpx.MockTransport(handler))

    def test_wire_compiler_stateless_allowlist_and_actual_budget(self):
        config = configuration()
        body = json.loads(request(config).payload)
        self.assertFalse(body["store"])
        self.assertFalse(body["stream"])
        self.assertFalse(body["background"])
        self.assertEqual(body["tools"], [])
        self.assertEqual(body["truncation"], "disabled")
        self.assertEqual(body["max_output_tokens"], 32)
        self.assertNotIn("previous_response_id", body)
        self.assertNotIn("conversation", body)
        self.assertNotIn("provider_configuration", body["input"])
        for params in (b'{"store":true}', b'{"temperature":true}', b'{"reasoning":{"effort":"unknown"}}'):
            with self.subTest(params=params), self.assertRaises(ValueError):
                request(replace(config, generation_parameters=params))
        with self.assertRaises(ValueError):
            request(replace(config, endpoint="https://fixture.invalid/steal"))

    async def test_real_http_bytes_and_signed_model_output_usage_binding(self):
        seen, checks = [], []
        config = configuration()
        dispatch = request(config)
        async def handler(http_request):
            seen.append(http_request)
            self.assertEqual(len(checks), 1)  # Callback precedes actual dispatch.
            self.assertEqual(str(http_request.url), ENDPOINT)
            self.assertEqual(http_request.content, dispatch.payload)
            return httpx.Response(200, content=response_body(), headers={"x-request-id": "fixture-http-request"})
        client = self.client(handler)
        try:
            result = await client.generate(dispatch, authorize_transfer=lambda: checks.append(True) or "a" * 64)
            Ed25519TransportObservationVerifier(configuration=config, public_key=self.public).verify(request=dispatch, response=result)
            self.assertEqual(result.request_id, "fixture-http-request")
            self.assertEqual(result.raw_response, response_body())
            self.assertEqual(result.output, b"Supplied mock text.")
            self.assertEqual((result.input_tokens, result.output_tokens), (123, 10))
            self.assertIsNone(result.cost_microunits)
            self.assertIsNone(result.currency)
            self.assertEqual(self.sink.attempts[0].metadata["result"], "success")
            self.assertTrue(self.sink.attempts[0].metadata["response_complete"])
            self.assertNotIn(b"fictional-placeholder", encoded(self.sink.attempts[0].metadata))
            self.assertNotIn(b"fictional-placeholder", self.sink.attempts[0].actual_request)
            self.key.public_key().verify(self.sink.attempts[0].proof, encoded(self.sink.attempts[0].metadata))
            with self.assertRaises(InvalidSignature):
                Ed25519TransportObservationVerifier(configuration=config, public_key=self.public).verify(
                    request=dispatch, response=replace(result, raw_response=b"changed"))
        finally:
            await client.aclose()

    async def test_concurrent_calls_capture_only_their_supplied_task_sink(self):
        async def handler(req):
            await asyncio.sleep(0)
            return httpx.Response(200, content=response_body(), headers={"x-request-id": "fixture-concurrent"})
        client = self.client(handler)
        left, right = Sink(), Sink()
        try:
            responses = await asyncio.gather(
                client.generate(request(configuration()), authorize_transfer=lambda: "a" * 64, attempt_sink=left),
                client.generate(request(configuration()), authorize_transfer=lambda: "b" * 64, attempt_sink=right))
            self.assertFalse(self.sink.attempts)  # No global task capture.
            self.assertEqual(len(left.attempts), 1)
            self.assertEqual(len(right.attempts), 1)
            self.assertEqual(left.attempts[0].metadata["authorization_marker"], responses[0].authorization_marker)
            self.assertEqual(right.attempts[0].metadata["authorization_marker"], responses[1].authorization_marker)
            self.assertNotEqual(responses[0].authorization_marker, responses[1].authorization_marker)
        finally:
            await client.aclose()

    async def test_production_transport_cannot_use_constructor_global_sink(self):
        credential_checks, transfer_checks = [], []
        client = OpenAIResponsesAsyncClient(configuration=configuration(),
            credential_provider=lambda: credential_checks.append(True) or "fictional-placeholder",
            signing_key=self.key, approved_observer_public_key_sha256=sha(self.public),
            attempt_sink=self.sink, timeout_seconds=.5, maximum_response_bytes=10000,
            httpx_version=version("httpx"))
        try:
            with self.assertRaises(TransportCustodyError):
                await client.generate(request(configuration()),
                    authorize_transfer=lambda: transfer_checks.append(True) or "a" * 64)
            self.assertFalse(credential_checks)
            self.assertFalse(transfer_checks)
            self.assertFalse(self.sink.attempts)
        finally:
            await client.aclose()

    async def test_denied_transfer_sends_nothing(self):
        calls = []
        client = self.client(lambda req: calls.append(req) or httpx.Response(200, content=response_body()))
        def deny():
            raise PermissionError("fictional denied source")
        try:
            with self.assertRaises(PermissionError):
                await client.generate(request(configuration()), authorize_transfer=deny)
            self.assertFalse(calls)
            self.assertFalse(self.sink.attempts)
        finally:
            await client.aclose()

    async def test_redirect_never_forwards_credential_and_unknown_usage_stays_unknown(self):
        calls = []
        def handler(req):
            calls.append(req)
            return httpx.Response(307, content=b'{"error":"fictional redirect"}',
                headers={"location": "https://fixture.invalid/other", "x-request-id": "fixture-redirect"})
        client = self.client(handler)
        try:
            with self.assertRaises(ArmStopped) as stopped:
                await client.generate(request(configuration()), authorize_transfer=lambda: "a" * 64)
            self.assertIsNone(stopped.exception.usage)
            self.assertEqual(len(calls), 1)
            self.assertIsNone(self.sink.attempts[0].metadata["usage"])
            self.assertEqual(self.sink.attempts[0].metadata["result"], "http_error")
        finally:
            await client.aclose()

    async def test_refusal_preserves_actual_usage_without_success_output(self):
        content = response_body(output=[{"type": "message", "role": "assistant", "status": "completed",
                                       "content": [{"type": "refusal", "refusal": "Supplied mock refusal."}]}])
        client = self.client(lambda req: httpx.Response(200, content=content, headers={"x-request-id": "fixture-refusal"}))
        try:
            with self.assertRaises(ArmStopped) as stopped:
                await client.generate(request(configuration()), authorize_transfer=lambda: "a" * 64)
            self.assertEqual(stopped.exception.status, "refused")
            self.assertEqual(stopped.exception.usage.input_tokens, 123)
            self.assertEqual(self.sink.attempts[0].actual_response, content)
            self.assertEqual(self.sink.attempts[0].metadata["result"], "refused")
        finally:
            await client.aclose()

    async def test_incomplete_response_is_failure_with_actual_usage_not_partial_success(self):
        content = response_body(status="incomplete", incomplete_details={"reason": "max_output_tokens"})
        client = self.client(lambda req: httpx.Response(200, content=content, headers={"x-request-id": "fixture-incomplete"}))
        try:
            with self.assertRaises(ArmStopped) as stopped:
                await client.generate(request(configuration()), authorize_transfer=lambda: "a" * 64)
            self.assertEqual(stopped.exception.status, "unavailable")
            self.assertEqual(stopped.exception.usage.output_tokens, 10)
            self.assertEqual(self.sink.attempts[0].metadata["result"], "incomplete")
            self.assertEqual(self.sink.attempts[0].actual_response, content)
        finally:
            await client.aclose()

    async def test_response_capture_limit_and_custody_failure_never_return_success(self):
        content = response_body()
        client = self.client(lambda req: httpx.Response(200, content=content,
            headers={"x-request-id": "fixture-oversized"}), maximum=17)
        try:
            with self.assertRaises(ValueError):
                await client.generate(request(configuration(maximum=17)), authorize_transfer=lambda: "a" * 64)
            attempt = self.sink.attempts[0]
            self.assertEqual(attempt.actual_response, content[:17])
            self.assertFalse(attempt.metadata["response_complete"])
            self.assertEqual(attempt.metadata["response_sha256"], sha(content[:17]))
            self.assertIsNone(attempt.metadata["usage"])
        finally:
            await client.aclose()
        class BrokenSink:
            def record(self, attempt):
                raise ValueError("fictional sensitive sink detail")
        self.sink = BrokenSink()
        client = self.client(lambda req: httpx.Response(200, content=content,
            headers={"x-request-id": "fixture-custody"}))
        try:
            with self.assertRaises(TransportCustodyError) as error:
                await client.generate(request(configuration()), authorize_transfer=lambda: "a" * 64)
            self.assertNotIn("sensitive", str(error.exception))
        finally:
            await client.aclose()

    async def test_unexpected_model_usage_tools_or_mutable_state_are_rejected(self):
        for content in (response_body(model="different-model"), response_body(usage=None),
                        response_body(output=[{"type": "function_call", "name": "unexpected"}])):
            with self.subTest(content=content):
                client = self.client(lambda req, content=content: httpx.Response(200, content=content,
                                                                              headers={"x-request-id": "fixture-invalid"}))
                try:
                    with self.assertRaises(ValueError):
                        await client.generate(request(configuration()), authorize_transfer=lambda: "a" * 64)
                finally:
                    await client.aclose()
        client = self.client(lambda req: self.fail("invalid body must not dispatch"))
        try:
            dispatch = request(configuration())
            body = json.loads(dispatch.payload)
            body["store"] = True
            with self.assertRaises(ValueError):
                await client.generate(replace(dispatch, payload=encoded(body)), authorize_transfer=lambda: "a" * 64)
        finally:
            await client.aclose()

    async def test_timeout_and_cancellation_are_bounded_signed_failures(self):
        async def slow(req):
            await asyncio.sleep(.05)
            return httpx.Response(200, content=response_body())
        client = self.client(slow, timeout=.01)
        try:
            with self.assertRaises(TimeoutError):
                await client.generate(request(configuration(.01)), authorize_transfer=lambda: "a" * 64)
            self.assertEqual(self.sink.attempts[-1].metadata["result"], "timeout")
            self.assertIsNone(self.sink.attempts[-1].actual_response)
        finally:
            await client.aclose()
        entered, release = asyncio.Event(), asyncio.Event()
        async def waiting(req):
            entered.set()
            await release.wait()
            return httpx.Response(200, content=response_body())
        client = self.client(waiting)
        try:
            task = asyncio.create_task(client.generate(request(configuration()), authorize_transfer=lambda: "a" * 64))
            await asyncio.wait_for(entered.wait(), .5)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertEqual(self.sink.attempts[-1].metadata["result"], "cancelled")
        finally:
            await client.aclose()

    def test_observer_enrollment_and_runtime_binding_required(self):
        with self.assertRaises(PermissionError):
            OpenAIResponsesAsyncClient(configuration=configuration(), credential_provider=lambda: "fixture",
                signing_key=self.key, approved_observer_public_key_sha256="e" * 64, attempt_sink=self.sink,
                timeout_seconds=.5, maximum_response_bytes=10000, httpx_version=version("httpx"))
        with self.assertRaises(ValueError):
            OpenAIResponsesAsyncClient(configuration=configuration(), credential_provider=lambda: "fixture",
                signing_key=self.key, approved_observer_public_key_sha256=sha(self.public), attempt_sink=self.sink,
                timeout_seconds=.5, maximum_response_bytes=10000, httpx_version="0.0.0")

    def test_supplied_file_manifest_checks_actual_bytes_versions_and_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "fixture.json").write_bytes(b"fictional supplied artifact")
            manifest = SuppliedArtifactManifest((("fixture.json", sha(b"fictional supplied artifact")),),
                (("httpx", version("httpx")),), b'{"kind":"fixture-contract"}')
            self.assertEqual(manifest.verify(root)["fixture.json"], b"fictional supplied artifact")
            (root / "fixture.json").write_bytes(b"changed")
            with self.assertRaises(ValueError):
                manifest.verify(root)
            with self.assertRaises(ValueError):
                replace(manifest, files=(("../outside", "f" * 64),)).record()


if __name__ == "__main__":
    unittest.main()
