"""Fictional custody/observer contracts; no selected-store or inference claim."""
import base64
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from flora.comparator import ProviderRequest, ProviderResponse, encoded, provider_payload, sha
from flora.comparison_run import ExecutionRequest, PreparationRequest
from flora.providers.openai_responses import TransportAttempt
from flora.selected.comparison_custody import ComparisonArtifact, _plan_record, evaluation_purpose
from flora.selected.comparator_memory import QdrantOriginalMemory, source_windows
from flora.selected.object_store import EncryptedObjectPlane, LocalObjectBackend
from flora.selected.provider_attempt_custody import (
    BoundProviderAttemptSink, OriginalMemoryProviderInputVerifier, XTDBProviderAttemptCustody,
    _CheckedObjects, audit_purpose, capture_purpose,
)
from cognitive_kernel.canonical import canonical_sha256
from comparator_fixtures import configuration, inputs, FixtureByteCounter, FixtureCompiler


class FixturePermission:
    """Fictional independent policy state, not an owner grant implementation."""
    def __init__(self):
        self.denied = set()
        self.actions = {}
    def permits(self, source, purpose):
        return (source.evidence.ref_id, purpose) not in self.denied
    def current_action(self, event_id, purpose):
        if (event_id, purpose) in self.denied:
            return None
        action_id = "fictional-action:" + canonical_sha256([event_id, purpose])
        action = SimpleNamespace(action_id=action_id, action_sha256=canonical_sha256(action_id))
        self.actions[action_id] = {"action": {"action_id": action_id, "action_sha256": action.action_sha256,
            "source_ref_id": event_id, "source_registration_sha256": canonical_sha256(event_id),
            "purpose": purpose, "decision": "allow"}}
        return action
    def _stored_action(self, action_id):
        return self.actions.get(action_id)


def fixture_owner(*, feature_call_budget=1):
    config = configuration()
    histories, question, plan = inputs()
    plan = replace(plan, feature_call_budget=feature_call_budget)
    history = histories[("case", "after")]
    memory = object.__new__(QdrantOriginalMemory)
    memory.configuration, memory.run_id = config, "run"
    prep = PreparationRequest("case", "after", question, history, plan)
    windows = source_windows(history, config)
    context = memory._context(prep, tuple(range(len(windows))), windows)
    execution = ExecutionRequest("case", "after", question, history.scope, history.digest(), history.event_ids,
                                 context, plan.arm_bindings["general_model_memory"], plan)
    provider = ProviderRequest(config.provider, provider_payload(config, question=question, context=context,
                               response_token_budget=32, wire_compiler=FixtureCompiler()), 32)
    owner = object.__new__(XTDBProviderAttemptCustody)
    owner.scope, owner.run_id, owner.permissions = history.scope, "run", FixturePermission()
    owner.input_verifier = OriginalMemoryProviderInputVerifier(configuration=config, compiler=FixtureCompiler())
    owner._input_artifact = owner.input_verifier.artifact_sha256
    owner.tokenizer, owner._tokenizer_artifact, owner._tokenizer_config = FixtureByteCounter(), "5" * 64, "6" * 64
    key = Ed25519PrivateKey.generate()
    owner._public_bytes = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    owner._public = key.public_key()
    records, comparison_records = {}, {}
    event_by_id = {source.event.event_id: source.event for source in history.sources}
    for name, content, metadata in (("plan", encoded(_plan_record(plan)), {"plan_sha256": plan.digest()}),
        ("question:case", question, {}), ("history:case:after", b"fictional-history-manifest",
            {"history_sha256": history.digest(), "source_event_ids": list(history.event_ids)})):
        event_id = "fictional-artifact:" + canonical_sha256(name)
        comparison_records[name] = ComparisonArtifact({"event_id": event_id, "content_sha256": sha(content),
                                                     "metadata": metadata})
        event_by_id[event_id] = SimpleNamespace(event_id=event_id, event_sha256=canonical_sha256(name),
            content_digest=sha(content), parent_event_ids=history.event_ids)
    owner.comparison = SimpleNamespace(authority_namespace_id="fixture-authority", scope_digest="a" * 64,
                                      metadata=lambda run, name: comparison_records.get(name))
    def source(event_id):
        event = event_by_id[event_id]
        raw = SimpleNamespace(object_id="fictional-object:" + canonical_sha256(event_id),
                              plaintext_sha256=event.content_digest)
        registered = SimpleNamespace(registration_sha256=canonical_sha256(event_id),
            evidence=SimpleNamespace(ref_id=event_id), object_ref=raw.object_id)
        return registered, event, raw
    owner._source = source
    owner.registry = SimpleNamespace(lookup=lambda event_id: source(event_id)[0])
    def phase_history(req):
        phase = comparison_records["history:case:after"]
        owner._require(req.authorized_event_ids + (phase.event_id,), evaluation_purpose("run", req.case_id, req.phase))
        return history, SimpleNamespace(authorize_context=lambda **kwargs:
                                        set(req.context.source_event_ids).issubset(history.event_ids))
    owner._phase_history = phase_history
    owner._metadata = lambda task_id, kind: records.get((task_id, kind))
    owner.objects = SimpleNamespace()
    def save(task_id, kind, body, *, parents, capture_sources, metadata):
        owner._require(capture_sources, capture_purpose(owner.run_id))
        saved = {"event_id": "fictional-provider:" + canonical_sha256([task_id, kind]),
                 "content_sha256": sha(encoded(body)), "parent_event_ids": list(parents), "metadata": metadata,
                 "fixture_body": deepcopy(body)}
        prior = records.get((task_id, kind))
        if prior is not None and prior != saved:
            raise ValueError("fixture immutable conflict")
        records[(task_id, kind)] = saved
        event_by_id[saved["event_id"]] = SimpleNamespace(event_id=saved["event_id"],
            event_sha256=canonical_sha256(saved["event_id"]), content_digest=saved["content_sha256"],
            parent_event_ids=parents)
        return saved
    owner._save = save
    return owner, execution, provider, key, records


def observed(sink, key, *, result="refused", known=True, partial=False):
    authorization = sink.owner._metadata(sink.body["task_id"], "authorization")["metadata"]["snapshot"]
    response = encoded({"model": "fixture-snapshot", "status": "completed",
        "output": [{"type": "message", "role": "assistant", "status": "completed", "content": [
            {"type": "output_text", "text": "Fictional supplied response."}]}] if result == "success" else [],
        "usage": {"input_tokens": 41, "output_tokens": 9}}) if known else None
    if partial:
        response = b'{"model":'
    usage = None if not known else {"feature_engine_id": "fixture-feature", "context_tokens": 41,
        "input_tokens": 41, "output_tokens": 9, "feature_calls": 1, "cost_microunits": None, "currency": None}
    metadata = {"schema": "flora-openai-transport-attempt-v1",
        "configuration_sha256": sink.body["dispatch"]["configuration_sha256"],
        "request_sha256": sink.body["dispatch"]["payload_sha256"],
        "authorization_marker": authorization["authorization_marker"],
        "response_sha256": None if response is None else sha(response), "http_status": 200 if known else None,
        "response_complete": bool(known and not partial), "request_id": "fictional-request" if known else None,
        "result": result, "returned_model_id": "fixture-snapshot" if known else None, "usage": usage,
        "cost_microunits": None, "observer_public_key_sha256": sha(sink.owner._public_bytes)}
    return TransportAttempt(metadata, base64.b64decode(sink.body["request_base64"]), response, key.sign(encoded(metadata)))


class ProviderAttemptContractsTest(unittest.TestCase):
    def prepared(self, task_id="task", *, feature_call_budget=1):
        owner, request, provider, key, records = fixture_owner(feature_call_budget=feature_call_budget)
        sink = owner.prepare_task(task_id=task_id, arm="general_model_memory", request=request, provider_request=provider)
        return owner, sink, key, records

    def authorize(self, owner, sink):
        return sink.wrap_authorize_transfer(lambda: owner._external_snapshot(sink.body)["source_authorization_marker"])()

    def test_exact_task_phase_context_wire_and_counts_are_frozen_without_plan_parent(self):
        owner, sink, _, records = self.prepared()
        body = sink.body
        self.assertEqual(body["phase"], "after")
        self.assertEqual(body["context_source_ids"], list(sink.request.context.source_event_ids))
        self.assertEqual(base64.b64decode(body["request_base64"]), sink.provider_request.payload)
        self.assertEqual(body["preflight_count"]["tokens"], len(sink.provider_request.payload))
        self.assertNotIn(owner.comparison.metadata("run", "plan").event_id, records[("task", "task")]["parent_event_ids"])

    def test_original_memory_verifier_cannot_authorize_native_task_or_changed_wire(self):
        owner, request, provider, _, _ = fixture_owner()
        for arm, dispatch in (("flora_full", provider), ("general_model_memory", replace(provider, payload=b"changed"))):
            with self.subTest(arm=arm), self.assertRaises(PermissionError):
                owner.prepare_task(task_id="invalid", arm=arm, request=request, provider_request=dispatch)

    def test_separate_external_consent_and_actual_marker_required_before_dispatch_receipt(self):
        owner, sink, _, records = self.prepared()
        event = sink.body["disclosure_source_ids"][0]
        owner.permissions.denied.add((event, "comparison_external:fixture-provider"))
        with self.assertRaises(PermissionError):
            sink.wrap_authorize_transfer(lambda: "f" * 64)()
        self.assertNotIn(("task", "authorization"), records)
        owner.permissions.denied.clear()
        with self.assertRaisesRegex(PermissionError, "independently checked"):
            sink.wrap_authorize_transfer(lambda: "f" * 64)()
        self.assertNotIn(("task", "authorization"), records)

    def test_phase_withdrawal_during_independent_input_verification_blocks_task(self):
        owner, request, provider, _, records = fixture_owner()
        actual_verify = owner.input_verifier.verify
        def withdraw_in_verifier(**kwargs):
            result = actual_verify(**kwargs)
            owner.permissions.denied.add((request.authorized_event_ids[0], evaluation_purpose("run", "case", "after")))
            return result
        owner.input_verifier.verify = withdraw_in_verifier
        with self.assertRaises(PermissionError):
            owner.prepare_task(task_id="withdrawn", arm="general_model_memory", request=request, provider_request=provider)
        self.assertNotIn(("withdrawn", "task"), records)

    def test_phase_withdrawal_during_authorization_append_cannot_return_dispatch_marker(self):
        owner, sink, _, records = self.prepared()
        actual_save = owner._save
        def withdraw_after_save(task_id, kind, body, **kwargs):
            saved = actual_save(task_id, kind, body, **kwargs)
            if kind == "authorization":
                owner.permissions.denied.add((sink.request.authorized_event_ids[0], evaluation_purpose("run", "case", "after")))
            return saved
        owner._save = withdraw_after_save
        with self.assertRaises(PermissionError):
            self.authorize(owner, sink)
        self.assertIn(("task", "authorization"), records)  # Conservative slot, not an observed call.
        self.assertNotIn(("task", "observation"), records)

    def test_known_usage_survives_external_and_evaluation_revocation_under_separate_capture(self):
        owner, sink, key, records = self.prepared()
        self.authorize(owner, sink)
        observation = observed(sink, key)
        for event_id in sink.body["disclosure_source_ids"]:
            owner.permissions.denied.add((event_id, "comparison_external:fixture-provider"))
        sink.record(observation)
        receipt = records[("task", "observation")]["metadata"]
        self.assertEqual(receipt["observed_attempt_count"], 1)
        self.assertEqual(receipt["usage"]["input_tokens"], 41)
        self.assertIsNone(receipt["usage"]["cost_microunits"])

    def test_cancellation_and_partial_observations_preserve_rows_without_invented_usage(self):
        for result, partial in (("cancelled", False), ("timeout", True)):
            with self.subTest(result=result):
                owner, sink, key, records = self.prepared()
                self.authorize(owner, sink)
                sink.record(observed(sink, key, result=result, known=False, partial=partial))
                receipt = records[("task", "observation")]["metadata"]
                self.assertEqual(receipt["observed_attempt_count"], 1)
                self.assertIsNone(receipt["usage"])
                self.assertEqual(receipt["result"], result)

    def test_changed_request_response_invalid_proof_or_fabricated_usage_never_gets_custody(self):
        owner, sink, key, records = self.prepared()
        self.authorize(owner, sink)
        observation = observed(sink, key)
        for changed in (replace(observation, actual_request=b"changed"), replace(observation, actual_response=b"changed"),
                        replace(observation, proof=b"invalid")):
            with self.subTest(changed=changed), self.assertRaises((ValueError, InvalidSignature)):
                sink.record(changed)
        metadata = deepcopy(observation.metadata)
        metadata["usage"]["input_tokens"] += 1
        with self.assertRaisesRegex(ValueError, "actual complete response"):
            sink.record(replace(observation, metadata=metadata, proof=key.sign(encoded(metadata))))
        self.assertNotIn(("task", "observation"), records)

    def test_partial_response_cannot_carry_known_usage_and_capture_revoke_blocks_storage(self):
        owner, sink, key, records = self.prepared()
        self.authorize(owner, sink)
        with self.assertRaisesRegex(ValueError, "partial/unavailable"):
            sink.record(observed(sink, key, partial=True))
        event_id = sink.body["source_bindings"][0]["event_id"]
        owner.permissions.denied.add((event_id, capture_purpose("run")))
        with self.assertRaises(PermissionError):
            sink.record(observed(sink, key))
        self.assertNotIn(("task", "observation"), records)

    def test_task_dispatch_cannot_be_reused_and_signed_observation_retry_is_idempotent(self):
        owner, sink, key, records = self.prepared()
        self.authorize(owner, sink)
        with self.assertRaisesRegex(PermissionError, "new task ID"):
            self.authorize(owner, sink)
        observation = observed(sink, key)
        sink.record(observation)
        sink.record(observation)
        self.assertEqual(len(records), 3)
        with self.assertRaisesRegex(ValueError, "immutable"):
            sink.record(observed(sink, key, result="incomplete"))

    def test_one_signed_observation_cannot_be_replayed_as_a_second_retry_attempt(self):
        owner, first, key, records = self.prepared("first", feature_call_budget=2)
        first_marker = self.authorize(owner, first)
        second = owner.prepare_task(task_id="second", arm="general_model_memory",
            request=first.request, provider_request=first.provider_request)
        second_marker = self.authorize(owner, second)
        first_snapshot = records[("first", "authorization")]["metadata"]["snapshot"]
        second_snapshot = records[("second", "authorization")]["metadata"]["snapshot"]
        self.assertEqual(first_snapshot["source_authorization_marker"], second_snapshot["source_authorization_marker"])
        self.assertNotEqual(first_marker, second_marker)
        observation = observed(first, key)
        first.record(observation)
        with self.assertRaisesRegex(ValueError, "frozen task"):
            second.record(observation)
        self.assertNotIn(("second", "observation"), records)

    def captured_reader(self, records):
        """Fictional raw reader; selected backend exercises real encrypted reads."""
        def read(scope, object_ref):
            record = next(value for value in records.values()
                if "fictional-object:" + canonical_sha256(value["event_id"]) == object_ref)
            return encoded(record["fixture_body"])
        mocked = patch("flora.selected.provider_attempt_custody.RegisteredEncryptedFormationCustody")
        return mocked, read

    def test_successful_response_needs_exact_durable_capture_and_actual_visible_text(self):
        owner, sink, key, records = self.prepared()
        self.authorize(owner, sink)
        observation = observed(sink, key, result="success")
        response = ProviderResponse(observation.metadata["configuration_sha256"],
            observation.metadata["request_sha256"], "fictional-request", "fixture-snapshot",
            observation.actual_response, b"Fictional supplied response.", 41, 9,
            observation.metadata["authorization_marker"], b"unsigned")
        response = replace(response, proof=key.sign(encoded(response.observation())))
        with self.assertRaisesRegex(ValueError, "durable captured"):
            sink.verify_response(response)
        sink.record(observation)
        mocked, read = self.captured_reader(records)
        with mocked as custody:
            custody.return_value.read.side_effect = read
            sink.verify_response(response)
            self.assertEqual(sink.verified_usage().input_tokens, 41)
            changed = replace(response, output=b"Different signed text.")
            changed = replace(changed, proof=key.sign(encoded(changed.observation())))
            with self.assertRaisesRegex(ValueError, "actual captured response text"):
                sink.verify_response(changed)
            owner.permissions.denied.add((sink.body["source_bindings"][0]["event_id"], capture_purpose("run")))
            custody.return_value.read.reset_mock()
            with self.assertRaises(PermissionError):
                sink.verified_usage()
            custody.return_value.read.assert_not_called()

    def test_unknown_usage_is_verified_without_inventing_consumption(self):
        owner, sink, key, records = self.prepared()
        self.authorize(owner, sink)
        sink.record(observed(sink, key, result="cancelled", known=False))
        mocked, read = self.captured_reader(records)
        with mocked as custody:
            custody.return_value.read.side_effect = read
            self.assertIsNone(sink.verified_usage())

    def test_checked_objects_gate_each_internal_put_get_and_recover_decrypt(self):
        owner, _, _, _, _ = fixture_owner()
        with TemporaryDirectory() as directory:
            objects = EncryptedObjectPlane(scope=owner.scope, key=b"t" * 32, backend=LocalObjectBackend(Path(directory)))
            state = {"allowed": True, "checks": 0}
            def check():
                state["checks"] += 1
                if not state["allowed"]:
                    raise PermissionError("fictional current source revoke")
            guarded = _CheckedObjects(objects, check)
            raw = guarded.put(b"fictional private payload")
            self.assertGreaterEqual(state["checks"], 3)
            old = state["checks"]
            guarded.recover_reference(object_id=raw.object_id, expected_plaintext_sha256=raw.plaintext_sha256)
            self.assertGreaterEqual(state["checks"] - old, 3)
            backend_get = objects.backend.get_object
            def revoke_during_cipher_read(namespace, object_id):
                value = backend_get(namespace, object_id)
                state["allowed"] = False
                return value
            objects.backend.get_object = revoke_during_cipher_read
            with self.assertRaises(PermissionError):
                guarded.get(raw)
            self.assertNotEqual(capture_purpose("run"), audit_purpose("run"))


if __name__ == "__main__":
    unittest.main()
