"""Actual encrypted controls with fictional registry/log/producer ports.

These methods test authority, privacy and dispatch mechanics. They do not
qualify model learning, baseline quality, tokenizer accuracy or real engines.
"""
import asyncio
import base64
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from flora.comparator import GeneralMemoryArmAdapter, ProviderRequest, TokenCount, encoded, provider_payload, sha
from flora.comparison_run import ArmStopped, ExecutionRequest, PreparationRequest
from flora.selected.comparison_custody import SelectedRunEvidencePolicy, evaluation_purpose
from flora.selected.comparator_memory import QdrantOriginalMemory, SelectedComparatorDisclosure, source_windows
from flora.selected.provider_attempt_custody import (
    OriginalMemoryProviderInputVerifier, XTDBProviderAttemptCustody, audit_purpose, capture_purpose,
)
from flora.providers.openai_responses import TransportAttempt
from cognitive_kernel.canonical import canonical_sha256
from comparator_fixtures import FixtureCompiler
import test_experiment_preregistration as controls


class FictionalRegistryEvidence(SelectedRunEvidencePolicy):
    """Only the non-XTDB fixture's current metadata port.

    Production's terminal actual-XTDB metadata proof remains mandatory. The
    inherited initial authorization still authenticates each real ciphertext.
    """
    def authorize_history_metadata(self, *, case_id, phase, history):
        artifact = self.custody.metadata(self.run_id, f"history:{case_id}:{phase}")
        return (artifact is not None
            and artifact.record["metadata"]["history_sha256"] == history.digest()
            and artifact.record["metadata"]["source_event_ids"] == list(history.event_ids)
            and all(self.permissions.permits(self.custody.registry.lookup(event_id),
                evaluation_purpose(self.run_id, case_id, phase)) is True for event_id in history.event_ids))


class ProviderFinalBindingTest(unittest.TestCase):
    def setUp(self):
        self.p = controls.PreregistrationContractsTest("test_anchor_freezes_design_without_unknown_after_hashes")
        self.p.setUp()
        self.addCleanup(self.p.doCleanups)
        self.p.spec = replace(self.p.spec, context_token_budget=20000, context_byte_budget=20000)
        self.comparison, self.permissions = self.p.f.comparison, self.p.local.permissions
        self.compiler = FixtureCompiler()
        self.compiler.artifact_sha256 = self.p.spec.comparator.provider.wire_compiler_artifact_sha256
        config = self.p.spec.comparator.memory
        self.counter = SimpleNamespace(count=lambda content: TokenCount(sha(content),
            config.tokenizer_artifact_sha256, config.tokenizer_configuration_sha256, len(content)))
        self.key = Ed25519PrivateKey.generate()
        selected = patch("flora.selected.provider_attempt_custody.register_experience_source",
            new=self.p.f.f.register_source)
        selected.start()
        self.addCleanup(selected.stop)
        # Explicit fictional immutable external actions. They bind actual
        # fixture registrations; no selected SQL permission claim is made.
        self.external_actions = {}
        def current_action(event_id, purpose):
            source = self.p.local.registry.lookup(event_id)
            if self.permissions.permits(source, purpose) is not True:
                return None
            action_id = "fictional-action:" + canonical_sha256([event_id, purpose])
            action_sha256 = canonical_sha256([action_id, source.registration_sha256])
            self.external_actions[action_id] = {"action": {"action_id": action_id,
                "action_sha256": action_sha256, "source_registration_sha256": source.registration_sha256,
                "source_ref_id": event_id, "purpose": purpose, "decision": "allow"}}
            return SimpleNamespace(action_id=action_id, action_sha256=action_sha256)
        self.permissions.current_action = current_action
        self.permissions._stored_action = self.external_actions.get
        def fictional_rows(*, registry, permissions, source_ids, purpose):
            # Explicit shape-only registry port: production uses the actual
            # single selected SQL fence, tested in test_provider_source_fence.
            pending, sources = list(source_ids), {}
            while pending:
                event_id = pending.pop()
                if event_id in sources:
                    continue
                source = registry.lookup(event_id)
                if source is None or permissions.permits(source, purpose) is not True:
                    raise PermissionError("fictional current source denied")
                sources[event_id] = source
                pending.extend(source.evidence.parent_refs)
            def verify():
                if any(registry.lookup(event_id) != source or (event_id, purpose) not in permissions.allowed
                       for event_id, source in sources.items()):
                    raise PermissionError("fictional terminal grant changed")
            return SimpleNamespace(verify_final_current_rows=verify)
        selected = patch("flora.selected.comparator_memory._current_permission_rows", new=fictional_rows)
        selected.start()
        self.addCleanup(selected.stop)
        connection = self.p.f.f.connection
        execute = connection.execute
        def provider_columns(query, params):
            if query.startswith("INSERT INTO flora_provider_attempt_artifacts"):
                columns = [value.strip() for value in query.split("(", 1)[1].split(")", 1)[0].split(",")]
                connection.records[params[0]] = dict(zip(columns, params))
                return None
            return execute(query, params)
        selected = patch.object(connection, "execute", side_effect=provider_columns)
        selected.start()
        self.addCleanup(selected.stop)

    def sealed(self):
        self.p.complete_captures()
        self.final = self.p.store.finalize()
        self.p.grant("capture")
        self.p.grant("read")
        self.p.store.register_final_inputs(final_authority=self.final, occurred_at=self.p.f.clock())
        self.evidence = FictionalRegistryEvidence(custody=self.comparison, run_id=self.p.run_id,
            permissions=self.permissions, final_authority=self.final)
        self.grant_provider_sources()

    def grant_provider_sources(self):
        from flora.selected.experiment_preregistration import preregistration_purpose
        for event in self.p.local.log.replay():
            for purpose in (capture_purpose(self.p.run_id),
                            audit_purpose(self.p.run_id),
                            "comparison_external:" + self.p.spec.comparator.provider.provider_id,
                            preregistration_purpose(self.p.run_id, "capture"),
                            preregistration_purpose(self.p.run_id, "read"),
                            evaluation_purpose(self.p.run_id, "case", "before"),
                            evaluation_purpose(self.p.run_id, "case", "after")):
                self.permissions.allowed.add((event.event_id, purpose))

    def request(self, *, final=False):
        plan = self.final.plan if final else self.p.f.plan
        history, question = self.p.f.histories[("case", "after")], self.p.f.question
        preparation = PreparationRequest("case", "after", question, history, plan)
        memory = object.__new__(QdrantOriginalMemory)
        memory.configuration, memory.run_id = self.p.spec.comparator, self.p.run_id
        windows = source_windows(history, memory.configuration)
        context = memory._context(preparation, tuple(range(len(windows))), windows)
        execution = ExecutionRequest("case", "after", question, self.p.scope, history.digest(), history.event_ids,
            context, plan.binding_for("case", "after", "general_model_memory"), plan)
        provider = ProviderRequest(memory.configuration.provider, provider_payload(memory.configuration,
            question=question, context=context, response_token_budget=plan.protocol.response_token_budget,
            wire_compiler=self.compiler), plan.protocol.response_token_budget)
        return preparation, execution, provider

    def owner(self):
        key = self.key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        config = self.p.spec.comparator
        return XTDBProviderAttemptCustody(comparison=self.comparison, evidence=self.evidence,
            permissions=self.permissions,
            input_verifier=OriginalMemoryProviderInputVerifier(configuration=config, compiler=self.compiler),
            tokenizer=self.counter, tokenizer_artifact_sha256=config.memory.tokenizer_artifact_sha256,
            tokenizer_configuration_sha256=config.memory.tokenizer_configuration_sha256,
            observer_public_key=key, approved_observer_public_key_sha256=sha(key), clock=self.p.f.clock)

    def test_durable_anchor_without_final_binding_stops_task_before_private_input(self):
        self.p.register()
        self.evidence = SelectedRunEvidencePolicy(custody=self.comparison, run_id=self.p.run_id,
            permissions=self.permissions)
        owner = self.owner()
        _, request, provider = self.request()
        with patch.object(owner, "_live_input", side_effect=AssertionError("private input opened")) as opened:
            with self.assertRaisesRegex(PermissionError, "actual final binding"):
                owner.prepare_task(task_id="provider-task-after", arm="general_model_memory",
                    request=request, provider_request=provider)
            opened.assert_not_called()
        self.assertIsNone(owner._metadata("provider-task-after", "task"))

    def test_durable_anchor_cannot_be_omitted_from_qdrant_or_disclosure_route(self):
        self.p.register()
        self.evidence = SelectedRunEvidencePolicy(custody=self.comparison, run_id=self.p.run_id,
            permissions=self.permissions)
        preparation, request, provider = self.request()
        embeddings, client = SimpleNamespace(embed=AsyncMock()), Mock()
        memory = QdrantOriginalMemory(custody=self.comparison, run_id=self.p.run_id,
            configuration=self.p.spec.comparator, client=client, embeddings=embeddings,
            tokenizer=self.counter, wire_compiler=self.compiler, evidence=self.evidence)
        with self.assertRaisesRegex(PermissionError, "actual final binding"):
            asyncio.run(memory.prepare(preparation))
        embeddings.embed.assert_not_called()
        self.assertEqual(client.mock_calls, [])
        disclosure = SelectedComparatorDisclosure(custody=self.comparison, run_id=self.p.run_id,
            configuration=self.p.spec.comparator, permissions=self.permissions,
            wire_compiler=self.compiler, evidence=self.evidence)
        with patch.object(self.comparison, "recover_history", side_effect=AssertionError("private history opened")) as opened:
            with self.assertRaisesRegex(PermissionError, "actual final binding"):
                disclosure.authorize(request=request, provider_request=provider)
            opened.assert_not_called()

    def test_only_declared_provider_task_can_enter_actual_sealed_run(self):
        self.sealed()
        owner = self.owner()
        _, request, provider = self.request(final=True)
        with self.assertRaisesRegex(PermissionError, "predeclared"):
            owner.prepare_task(task_id="different-task", arm="general_model_memory", request=request,
                provider_request=provider)
        self.assertIsNone(owner._metadata("different-task", "task"))
        sink = owner.prepare_task(task_id="provider-task-after", arm="general_model_memory",
            request=request, provider_request=provider)
        self.assertEqual(sink.body["plan_sha256"], self.final.final_plan_sha256)

    def test_source_withdrawal_in_slow_counter_stops_before_canonical_task_append(self):
        self.sealed()
        owner = self.owner()
        _, request, provider = self.request(final=True)
        count = owner.tokenizer.count
        def withdraw(content):
            result = count(content)
            self.p.revoke_foreign()
            return result
        before = len(self.p.local.log.replay())
        owner.tokenizer.count = withdraw
        with self.assertRaises(PermissionError):
            owner.prepare_task(task_id="provider-task-after", arm="general_model_memory",
                request=request, provider_request=provider)
        self.assertEqual(len(self.p.local.log.replay()), before)
        self.assertIsNone(owner._metadata("provider-task-after", "task"))

    def test_current_update_proof_withdrawal_stops_actual_transfer_callback(self):
        self.sealed()
        owner = self.owner()
        _, request, provider = self.request(final=True)
        sink = owner.prepare_task(task_id="provider-task-after", arm="general_model_memory",
            request=request, provider_request=provider)
        self.grant_provider_sources()
        self.p.update_proof_allowed = False
        with self.assertRaisesRegex(PermissionError, "no longer qualifies"):
            sink.wrap_authorize_transfer(lambda: (_ for _ in ()).throw(AssertionError("transport reached")))()
        self.assertIsNone(owner._metadata("provider-task-after", "authorization"))

    def test_actual_task_cipher_fetch_withdrawal_stops_before_aead(self):
        self.sealed()
        owner = self.owner()
        _, request, provider = self.request(final=True)
        owner.prepare_task(task_id="provider-task-after", arm="general_model_memory",
            request=request, provider_request=provider)
        self.grant_provider_sources()
        task = owner._metadata("provider-task-after", "task")
        backend = self.p.local.objects.backend
        fetch = backend.get_object
        def withdraw(namespace, object_id):
            sealed = fetch(namespace, object_id)
            if object_id == task["object_id"]:
                self.p.revoke_foreign()
            return sealed
        with patch.object(backend, "get_object", side_effect=withdraw), \
             patch.object(AESGCM, "decrypt", side_effect=AssertionError("opened withdrawn task")) as opened:
            with self.assertRaises(PermissionError):
                owner._read_source(task["event_id"], capture_purpose(self.p.run_id))
            opened.assert_not_called()

    def test_signed_failed_attempt_retains_usage_after_evaluation_withdrawal(self):
        self.sealed()
        owner = self.owner()
        _, request, provider = self.request(final=True)
        sink = owner.prepare_task(task_id="provider-task-after", arm="general_model_memory",
            request=request, provider_request=provider)
        self.grant_provider_sources()
        sink.wrap_authorize_transfer(lambda: owner._external_snapshot(sink.body)["source_authorization_marker"])()
        snapshot = owner._metadata(sink.body["task_id"], "authorization")["metadata"]["snapshot"]
        config = self.p.spec.comparator.provider
        raw = encoded({"model": config.requested_model_id, "status": "completed", "output": [],
            "usage": {"input_tokens": 41, "output_tokens": 9}})
        usage = {"feature_engine_id": config.feature_engine_id, "context_tokens": 41,
            "input_tokens": 41, "output_tokens": 9, "feature_calls": 1,
            "cost_microunits": None, "currency": None}
        metadata = {"schema": "flora-openai-transport-attempt-v1",
            "configuration_sha256": sink.body["dispatch"]["configuration_sha256"],
            "request_sha256": sink.body["dispatch"]["payload_sha256"],
            "authorization_marker": snapshot["authorization_marker"], "response_sha256": sha(raw),
            "http_status": 200, "response_complete": True, "request_id": "fictional-refusal",
            "result": "refused", "returned_model_id": config.requested_model_id, "usage": usage,
            "cost_microunits": None, "observer_public_key_sha256": sha(owner._public_bytes)}
        observation = TransportAttempt(metadata, base64.b64decode(sink.body["request_base64"]),
            raw, self.key.sign(encoded(metadata)))
        def withdraw_evaluation_and_external():
            self.permissions.allowed = {pair for pair in self.permissions.allowed
                if not pair[1].startswith(("comparison_eval:", "comparison_external:"))}
        withdraw_evaluation_and_external()
        self.p.update_proof_allowed = False
        sink.record(observation)
        self.assertEqual(sink.verified_usage().input_tokens, 41)
        self.assertEqual(owner._metadata(sink.body["task_id"], "observation")["metadata"]["observed_attempt_count"], 1)
        self.grant_provider_sources()
        # Revoke evaluation again after granting the newly captured audit
        # artifact. Audit retention has its own independent authorization.
        withdraw_evaluation_and_external()
        self.assertEqual(owner.recover(task_id=sink.body["task_id"]).usage.input_tokens, 41)
        with self.assertRaises(PermissionError):
            sink.verify_response(None)
        with self.assertRaises(PermissionError):
            sink.wrap_authorize_transfer(lambda: (_ for _ in ()).throw(AssertionError("transport reached")))()
        self.permissions.allowed.discard((request.authorized_event_ids[0], capture_purpose(self.p.run_id)))
        with patch.object(AESGCM, "decrypt", side_effect=AssertionError("opened revoked capture")) as opened:
            with self.assertRaises(PermissionError):
                sink.verified_usage()
            opened.assert_not_called()

    def test_actual_encrypted_provider_task_external_denial_remains_refused(self):
        self.sealed()
        owner = self.owner()
        _, request, _ = self.request(final=True)
        self.permissions.allowed = {pair for pair in self.permissions.allowed
            if not pair[1].startswith("comparison_external:")}
        configuration = self.p.spec.comparator
        client = SimpleNamespace(configuration=configuration.provider,
            generate=AsyncMock(side_effect=AssertionError("provider dispatched")))
        disclosure = SelectedComparatorDisclosure(custody=self.comparison, run_id=self.p.run_id,
            configuration=configuration, permissions=self.permissions, wire_compiler=self.compiler,
            evidence=self.evidence)
        adapter = GeneralMemoryArmAdapter(configuration=configuration,
            memory=SimpleNamespace(configuration=configuration), tokenizer=self.counter,
            wire_compiler=self.compiler, client=client, exchange_verifier=Mock(), disclosure=disclosure,
            recorder=Mock(), attempt_custody=owner, task_id_for=lambda _: "provider-task-after")
        with self.assertRaises(ArmStopped) as stopped:
            asyncio.run(adapter.execute(request))
        self.assertEqual(stopped.exception.status, "refused")
        client.generate.assert_not_awaited()
        self.assertIsNotNone(owner._metadata("provider-task-after", "task"))
        self.assertIsNone(owner._metadata("provider-task-after", "authorization"))


if __name__ == "__main__":
    unittest.main()
