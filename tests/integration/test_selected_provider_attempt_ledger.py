"""Real selected stores with signed fictional observations, not a provider call."""
import base64
from dataclasses import replace
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from kurrentdbclient import KurrentDBClient
import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from comparator_fixtures import configuration, inputs, FixtureByteCounter, FixtureCompiler
from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from flora.comparator import ProviderRequest, encoded, provider_payload, sha
from flora.comparison_run import ExecutionRequest, PreparationRequest, SourceMaterial
from flora.providers.openai_responses import TransportAttempt
from flora.selected.comparator_memory import QdrantOriginalMemory, source_windows
from flora.selected.comparison_custody import XTDBComparisonCustody, SelectedRunEvidencePolicy, evaluation_purpose
from flora.selected.experience import KurrentExperienceLog
from flora.selected.formation_context import register_experience_source
from flora.selected.formation_policy import FormationPermissionAction, XTDBFormationPermissionPolicy, formation_permission_payload
from flora.selected.formation_registry import XTDBFormationSourceRegistry
from flora.selected.object_store import EncryptedObjectPlane, LocalObjectBackend
from flora.selected.owner_authorization import Ed25519OwnerActionVerifier, OwnerActionProof, owner_action_message
from flora.selected.provider_attempt_custody import (
    XTDBProviderAttemptCustody, OriginalMemoryProviderInputVerifier, capture_purpose, audit_purpose,
)


def now():
    return datetime.now(timezone.utc).isoformat()


class SelectedProviderAttemptLedgerIntegrationTest(unittest.TestCase):
    def test_frozen_phase_custody_signed_failures_and_fresh_per_decrypt_authority(self):
        host = "provider-ledger-" + uuid.uuid4().hex[:12]
        scope = ProductHostScope.create(product_id="friday", host_instance_id=host,
            schema_version="1.0.0", encryption_domain="key-" + host)
        namespace = "provider-ledger-" + uuid.uuid4().hex[:12]
        client = KurrentDBClient(os.environ.get("KURRENTDB_URI", "kurrentdb://127.0.0.1:2113?tls=false"))
        try:
            with tempfile.TemporaryDirectory() as directory, psycopg.connect(
                    os.environ.get("XTDB_DSN", "postgresql://xtdb@127.0.0.1:5432/xtdb"), autocommit=True) as connection:
                objects = EncryptedObjectPlane(scope=scope, key=b"p" * 32,
                    backend=LocalObjectBackend(Path(directory) / "objects"))
                log = KurrentExperienceLog(scope=scope, client=client)
                registry = XTDBFormationSourceRegistry(scope=scope, authority_namespace_id=namespace, connection=connection)
                comparison = XTDBComparisonCustody(scope=scope, authority_namespace_id=namespace,
                    connection=connection, registry=registry, objects=objects, log=log)
                sources = []
                for index, text in enumerate((b"Fictional host prefers calm project planning.",
                                              b"Correction: the fictional host wants a concise plan.")):
                    raw = objects.put(text)
                    event = ExperienceEvent.create(event_type="observation" if index == 0 else "correction", scope=scope,
                        occurred_at=f"2020-01-0{index+1}T12:00:00Z", content_digest=raw.plaintext_sha256,
                        provenance=ProvenanceReference.create(provenance_type="generated_reconstruction",
                            source_reference_ids=("fictional-source-" + str(index),),
                            derivation_activity_id="provider-ledger-fixture", responsible_component="synthetic-test"),
                        retention_class="ordinary_experience", storage_tier="raw_buffer",
                        parent_event_ids=() if index == 0 else (sources[0].event.event_id,), payload_reference=raw.object_id)
                    log.append(event, expected_revision=len(log.replay()) - 1)
                    register_experience_source(event_id=event.event_id, raw=raw, registry=registry,
                        log=log, objects=objects, role="generated_reconstruction", modality="text")
                    sources.append(SourceMaterial(event, text))
                histories, question, plan = inputs(host, actual_sources=sources)
                plan = replace(plan, feature_call_budget=2)
                comparison.register_inputs(run_id="run", plan=plan, histories=histories,
                    questions={"case": question}, occurred_at=now())
                policy = XTDBFormationPermissionPolicy(scope=scope, authority_namespace_id=namespace,
                    connection=connection, registry=registry)
                owner_key, proofs, counter = Ed25519PrivateKey.generate(), {}, 0
                owner = Ed25519OwnerActionVerifier(scope=scope,
                    owner_public_key=owner_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw), proofs=proofs)
                def grant(event_id, purpose, decision="allow"):
                    nonlocal counter
                    counter += 1
                    source = registry.lookup(event_id)
                    prior = policy.current_action(event_id, purpose)
                    previous = None if prior is None else next(event for event in log.replay()
                        if event.event_type == "formation_permission_action" and event.provenance.derivation_activity_id == prior.action_id)
                    action = FormationPermissionAction.create(scope=scope, authority_namespace_id=namespace,
                        action_id="fixture-provider-grant-" + str(counter), source_ref_id=event_id,
                        source_registration_sha256=source.registration_sha256, purpose=purpose, decision=decision,
                        generation=1 if prior is None else prior.generation + 1,
                        previous_action_sha256=None if prior is None else prior.action_sha256,
                        authorization_ref="fixture-owner-" + str(counter), authorized_at=now())
                    raw = objects.put(formation_permission_payload(action))
                    parents = (event_id,) + (() if previous is None else (previous.event_id,))
                    event = ExperienceEvent.create(event_type="formation_permission_action", scope=scope,
                        occurred_at=action.authorized_at, content_digest=raw.plaintext_sha256,
                        provenance=ProvenanceReference.create(provenance_type="derived_inference", source_reference_ids=parents,
                            derivation_activity_id=action.action_id, responsible_component="synthetic-test"),
                        retention_class="ordinary_experience", storage_tier="raw_buffer",
                        parent_event_ids=parents, payload_reference=raw.object_id)
                    log.append(event, expected_revision=len(log.replay()) - 1)
                    register_experience_source(event_id=event.event_id, raw=raw, registry=registry,
                        log=log, objects=objects, role="derived_inference", modality="structured")
                    proofs[event.event_id] = OwnerActionProof("formation_permission", event.event_id, event.event_sha256,
                        base64.b64encode(owner_key.sign(owner_action_message(event, "formation_permission"))).decode())
                    policy.apply(action, request_event_id=event.event_id, log=log, objects=objects, references=registry, verifier=owner)
                for phase in ("before", "after"):
                    for source in histories[("case", phase)].sources:
                        grant(source.event.event_id, evaluation_purpose("run", "case", phase))
                    grant(comparison.metadata("run", "history:case:" + phase).event_id, evaluation_purpose("run", "case", phase))
                for event in list(log.replay()):
                    if event.event_type != "formation_permission_action":
                        grant(event.event_id, capture_purpose("run"))
                config, compiler = configuration(), FixtureCompiler()
                evidence = SelectedRunEvidencePolicy(custody=comparison, run_id="run", permissions=policy)
                verifier = OriginalMemoryProviderInputVerifier(configuration=config, compiler=compiler)
                transport_key = Ed25519PrivateKey.generate()
                public = transport_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
                def ledger():
                    return XTDBProviderAttemptCustody(comparison=comparison, evidence=evidence, permissions=policy,
                        input_verifier=verifier, tokenizer=FixtureByteCounter(), tokenizer_artifact_sha256="5" * 64,
                        tokenizer_configuration_sha256="6" * 64, observer_public_key=public,
                        approved_observer_public_key_sha256=sha(public), clock=now)
                store = ledger()
                memory = object.__new__(QdrantOriginalMemory)
                memory.configuration, memory.run_id = config, "run"
                def prepare(task_id, phase):
                    history = histories[("case", phase)]
                    preparation = PreparationRequest("case", phase, question, history, plan)
                    windows = source_windows(history, config)
                    context = memory._context(preparation, tuple(range(len(windows))), windows)
                    request = ExecutionRequest("case", phase, question, scope, history.digest(), history.event_ids,
                        context, plan.arm_bindings["general_model_memory"], plan)
                    provider = ProviderRequest(config.provider, provider_payload(config, question=question, context=context,
                        response_token_budget=32, wire_compiler=compiler), 32)
                    return store.prepare_task(task_id=task_id, arm="general_model_memory", request=request, provider_request=provider)
                after = prepare("after-refusal", "after")
                with self.assertRaises(PermissionError):
                    after.wrap_authorize_transfer(lambda: "f" * 64)()
                self.assertIsNone(store._metadata("after-refusal", "authorization"))
                for event_id in after.body["disclosure_source_ids"]:
                    grant(event_id, "comparison_external:fixture-provider")
                def authorize(sink):
                    return sink.wrap_authorize_transfer(lambda: store._external_snapshot(sink.body)["source_authorization_marker"])()
                marker = authorize(after)
                retry = prepare("after-timeout", "after")
                retry_marker = authorize(retry)
                self.assertNotEqual(marker, retry_marker)  # Equal wire/grants still identify two distinct attempts.
                overflow = prepare("after-over-budget", "after")
                with self.assertRaises(psycopg.Error):
                    authorize(overflow)
                self.assertIsNone(store._metadata("after-over-budget", "authorization"))
                response = encoded({"model": "fixture-snapshot", "status": "completed",
                    "output": [{"type": "message", "role": "assistant", "status": "completed",
                                "content": [{"type": "refusal", "refusal": "Fictional supplied refusal."}]}],
                    "usage": {"input_tokens": 41, "output_tokens": 9}})
                metadata = {"schema": "flora-openai-transport-attempt-v1", "configuration_sha256": config.provider.digest(),
                    "request_sha256": sha(after.provider_request.payload), "authorization_marker": marker,
                    "response_sha256": sha(response), "http_status": 200, "response_complete": True,
                    "request_id": "fixture-request", "result": "refused", "returned_model_id": "fixture-snapshot",
                    "usage": {"feature_engine_id": "fixture-feature", "context_tokens": 41, "input_tokens": 41,
                              "output_tokens": 9, "feature_calls": 1, "cost_microunits": None, "currency": None},
                    "cost_microunits": None, "observer_public_key_sha256": sha(public)}
                observation = TransportAttempt(metadata, after.provider_request.payload, response,
                                               transport_key.sign(encoded(metadata)))
                with self.assertRaisesRegex(ValueError, "frozen task"):
                    retry.record(observation)
                partial_response = b'{"partial":'
                retry_metadata = {**metadata, "authorization_marker": retry_marker,
                    "response_sha256": sha(partial_response), "response_complete": False,
                    "request_id": None, "result": "timeout", "returned_model_id": None, "usage": None}
                retry.record(TransportAttempt(retry_metadata, retry.provider_request.payload, partial_response,
                    transport_key.sign(encoded(retry_metadata))))
                grant(sources[0].event.event_id, "comparison_external:fixture-provider", "revoke")
                grant(sources[0].event.event_id, evaluation_purpose("run", "case", "after"), "revoke")
                after.record(observation)  # Capture survives a distinct authority's withdrawal.
                after.record(observation)
                self.assertEqual(after.verified_usage().input_tokens, 41)
                self.assertIsNone(retry.verified_usage())
                grant(sources[0].event.event_id, capture_purpose("run"), "revoke")
                with self.assertRaises(PermissionError):
                    after.verified_usage()
                grant(sources[0].event.event_id, capture_purpose("run"))
                before = prepare("before-cancelled", "before")
                grant(sources[0].event.event_id, "comparison_external:fixture-provider")
                before_marker = authorize(before)
                cancelled_meta = {**metadata, "request_sha256": sha(before.provider_request.payload),
                    "authorization_marker": before_marker, "response_sha256": None, "http_status": None,
                    "response_complete": False, "request_id": None, "result": "cancelled", "returned_model_id": None, "usage": None}
                before.record(TransportAttempt(cancelled_meta, before.provider_request.payload, None,
                                               transport_key.sign(encoded(cancelled_meta))))
                for event in list(log.replay()):
                    if event.event_type != "formation_permission_action":
                        grant(event.event_id, audit_purpose("run"))
                restarted = ledger()  # No caller RAM observation or authorization map.
                recovered = restarted.recover(task_id="after-refusal")
                self.assertEqual(recovered.usage.input_tokens, 41)
                self.assertIsNone(recovered.usage.cost_microunits)
                self.assertEqual(recovered.observed_attempt_count, 1)
                recovered_retry = restarted.recover(task_id="after-timeout")
                self.assertIsNone(recovered_retry.usage)
                self.assertEqual(recovered_retry.observation.actual_response, partial_response)
                self.assertFalse(recovered_retry.observation.metadata["response_complete"])
                before_recovered = restarted.recover(task_id="before-cancelled")
                self.assertIsNone(before_recovered.usage)
                self.assertNotIn(sources[1].event.event_id, before_recovered.task["original_event_ids"])
                self.assertNotIn(comparison.metadata("run", "plan").event_id,
                               restarted._metadata("before-cancelled", "task")["parent_event_ids"])
                self.assertIsNone(comparison.metadata("run", "before-cancelled"))
                # A reviewer grant cannot substitute for this private audit route.
                grant(sources[0].event.event_id, audit_purpose("run"), "revoke")
                grant(sources[0].event.event_id, "comparison_review")
                original_get, private_reads = objects.get, []
                def no_private_read(reference):
                    private_reads.append(reference.object_id)
                    raise AssertionError("withdrawn source must be checked before private decrypt")
                objects.get = no_private_read
                try:
                    with self.assertRaises(PermissionError):
                        restarted.recover(task_id="after-refusal")
                    self.assertEqual(private_reads, [])
                finally:
                    objects.get = original_get
                grant(sources[0].event.event_id, audit_purpose("run"))
                target = restarted._metadata("after-refusal", "observation")["object_id"]
                original_get = objects.get
                def withdraw_inside_decrypt(reference):
                    content = original_get(reference)
                    if reference.object_id == target:
                        grant(sources[0].event.event_id, audit_purpose("run"), "revoke")
                    return content
                objects.get = withdraw_inside_decrypt
                try:
                    with self.assertRaises(PermissionError):
                        restarted.recover(task_id="after-refusal")
                finally:
                    objects.get = original_get
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
