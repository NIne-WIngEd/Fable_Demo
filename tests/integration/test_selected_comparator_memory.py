"""Selected Qdrant/custody mechanics with fictional supplied adapter receipts.

No frontier request, real embedding, tokenizer or model prediction occurs.
"""
import asyncio
import base64
from dataclasses import replace
from datetime import datetime, timezone
import json
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
from qdrant_client import QdrantClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from comparator_fixtures import (
    FixtureByteCounter, FixtureCompiler, FixtureEmbeddings, configuration, inputs,
)

from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from flora.comparator import (Ed25519TransportObservationVerifier, GeneralMemoryArmAdapter,
    ProviderResponse, encoded, sha)
from flora.comparison_run import PreparationRequest, SourceMaterial, run_paired
from flora.selected.comparator_memory import (
    QdrantOriginalMemory, SelectedComparatorDisclosure, SelectedComparatorRecorder,
)
from flora.selected.comparison_custody import (
    SelectedRunEvidencePolicy, XTDBComparisonCustody, evaluation_purpose,
)
from flora.selected.experience import KurrentExperienceLog
from flora.selected.formation_context import register_experience_source
from flora.selected.formation_policy import (
    FormationPermissionAction, XTDBFormationPermissionPolicy, formation_permission_payload,
)
from flora.selected.formation_registry import XTDBFormationSourceRegistry
from flora.selected.object_store import EncryptedObjectPlane, LocalObjectBackend
from flora.selected.owner_authorization import (
    Ed25519OwnerActionVerifier, OwnerActionProof, owner_action_message,
)
from flora.providers.openai_responses import TransportAttempt
from flora.selected.provider_attempt_custody import (
    OriginalMemoryProviderInputVerifier, XTDBProviderAttemptCustody, capture_purpose,
)


def now():
    return datetime.now(timezone.utc).isoformat()


class SelectedComparatorIntegrationTest(unittest.TestCase):
    def test_phase_isolated_hybrid_memory_and_separately_authorized_signed_exchange(self):
        host = "comparator-" + uuid.uuid4().hex[:16]
        scope = ProductHostScope.create(product_id="friday", host_instance_id=host,
            schema_version="1.0.0", encryption_domain="key-" + host)
        namespace = "comparator-" + uuid.uuid4().hex[:16]
        client = KurrentDBClient(os.environ.get("KURRENTDB_URI", "kurrentdb://127.0.0.1:2113?tls=false"))
        vectors = QdrantClient(url=os.environ.get("QDRANT_URL", "http://127.0.0.1:6333"))
        try:
            with tempfile.TemporaryDirectory() as directory, psycopg.connect(
                    os.environ.get("XTDB_DSN", "postgresql://xtdb@127.0.0.1:5432/xtdb"), autocommit=True) as connection:
                objects = EncryptedObjectPlane(scope=scope, key=b"c" * 32,
                    backend=LocalObjectBackend(Path(directory) / "objects"))
                log = KurrentExperienceLog(scope=scope, client=client)
                registry = XTDBFormationSourceRegistry(scope=scope, authority_namespace_id=namespace, connection=connection)
                custody = XTDBComparisonCustody(scope=scope, authority_namespace_id=namespace,
                    connection=connection, registry=registry, objects=objects, log=log)
                sources = []
                for index, text in enumerate((b"Fictional host prefers calm project planning.",
                                              b"Correction: this project needs a concise plan.")):
                    raw = objects.put(text)
                    event = ExperienceEvent.create(event_type="observation" if not index else "correction",
                        scope=scope, occurred_at=f"2020-01-0{index+1}T12:00:00Z", content_digest=raw.plaintext_sha256,
                        provenance=ProvenanceReference.create(provenance_type="generated_reconstruction",
                            source_reference_ids=("fictional-source-" + str(index),),
                            derivation_activity_id="comparator-integration-fixture", responsible_component="synthetic-test"),
                        retention_class="ordinary_experience", storage_tier="raw_buffer",
                        parent_event_ids=() if not index else (sources[0].event.event_id,), payload_reference=raw.object_id)
                    log.append(event, expected_revision=len(log.replay()) - 1)
                    register_experience_source(event_id=event.event_id, raw=raw, registry=registry,
                        log=log, objects=objects, role="generated_reconstruction", modality="text")
                    sources.append(SourceMaterial(event, text))
                histories, question, plan = inputs(host, actual_sources=sources)
                custody.register_inputs(run_id="run", plan=plan, histories=histories,
                    questions={"case": question}, occurred_at=now())
                permissions = XTDBFormationPermissionPolicy(scope=scope, authority_namespace_id=namespace,
                    connection=connection, registry=registry)
                owner_key = Ed25519PrivateKey.generate()
                proofs = {}
                owner_verifier = Ed25519OwnerActionVerifier(scope=scope,
                    owner_public_key=owner_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw), proofs=proofs)
                counter = 0
                def grant(event_id, purpose, decision="allow"):
                    nonlocal counter
                    counter += 1
                    source = registry.lookup(event_id)
                    prior = permissions.current_action(event_id, purpose)
                    previous = None if prior is None else next(e for e in log.replay()
                        if e.event_type == "formation_permission_action" and e.provenance.derivation_activity_id == prior.action_id)
                    action = FormationPermissionAction.create(scope=scope, authority_namespace_id=namespace,
                        action_id="fixture-comparator-grant-" + str(counter), source_ref_id=event_id,
                        source_registration_sha256=source.registration_sha256, purpose=purpose, decision=decision,
                        generation=1 if prior is None else prior.generation+1,
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
                    log.append(event, expected_revision=len(log.replay())-1)
                    register_experience_source(event_id=event.event_id, raw=raw, registry=registry,
                        log=log, objects=objects, role="derived_inference", modality="structured")
                    proofs[event.event_id] = OwnerActionProof("formation_permission", event.event_id, event.event_sha256,
                        base64.b64encode(owner_key.sign(owner_action_message(event, "formation_permission"))).decode())
                    permissions.apply(action, request_event_id=event.event_id, log=log, objects=objects,
                        references=registry, verifier=owner_verifier)
                for phase in ("before", "after"):
                    purpose = evaluation_purpose("run", "case", phase)
                    for source in histories[("case", phase)].sources:
                        grant(source.event.event_id, purpose)
                    grant(custody.metadata("run", "history:case:" + phase).event_id, purpose)
                # This ordinary 10-second gate deliberately qualifies selected
                # held-history evidence. Whole-stream consumers remain covered
                # by the other default-domain integration fixtures.
                evidence = SelectedRunEvidencePolicy(custody=custody, run_id="run", permissions=permissions,
                    history_metadata_domain="selected-history-metadata-v1", maximum_history_sources=32)
                self.assertEqual(evidence.history_metadata_domain, "selected-history-metadata-v1")
                self.assertEqual(evidence.maximum_history_sources, 32)
                config, compiler, tokenizer = configuration(), FixtureCompiler(), FixtureByteCounter()
                memory = QdrantOriginalMemory(custody=custody, run_id="run", configuration=config,
                    client=vectors, embeddings=FixtureEmbeddings(), tokenizer=tokenizer,
                    wire_compiler=compiler, evidence=evidence)
                disclosure = SelectedComparatorDisclosure(custody=custody, run_id="run", configuration=config,
                    permissions=permissions, wire_compiler=compiler, evidence=evidence)
                transport_key = Ed25519PrivateKey.generate()
                exchange_verifier = Ed25519TransportObservationVerifier(configuration=config.provider,
                    public_key=transport_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
                for event_id in (sources[0].event.event_id, sources[1].event.event_id,
                                 custody.metadata("run", "question:case").event_id,
                                 custody.metadata("run", "history:case:before").event_id,
                                 custody.metadata("run", "history:case:after").event_id):
                    grant(event_id, capture_purpose("run"))
                observer_public = transport_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
                attempt_custody = XTDBProviderAttemptCustody(comparison=custody, evidence=evidence,
                    permissions=permissions, input_verifier=OriginalMemoryProviderInputVerifier(
                        configuration=config, compiler=compiler), tokenizer=tokenizer,
                    tokenizer_artifact_sha256=config.memory.tokenizer_artifact_sha256,
                    tokenizer_configuration_sha256=config.memory.tokenizer_configuration_sha256,
                    observer_public_key=observer_public,
                    approved_observer_public_key_sha256=sha(observer_public), clock=now)
                class SuppliedContractClient:
                    configuration = config.provider
                    calls = 0
                    async def generate(self, request, *, authorize_transfer, attempt_sink):
                        self.calls += 1
                        marker = authorize_transfer()
                        output = b"Supplied fictional output. No model inference occurred."
                        response_bytes = encoded({"model": "fixture-snapshot", "status": "completed",
                            "output": [{"type": "message", "role": "assistant", "status": "completed", "content": [
                                {"type": "output_text", "text": output.decode()}]}],
                            "usage": {"input_tokens": len(request.payload), "output_tokens": 9}})
                        metadata = {"schema": "flora-openai-transport-attempt-v1",
                            "configuration_sha256": config.provider.digest(), "request_sha256": sha(request.payload),
                            "authorization_marker": marker, "response_sha256": sha(response_bytes), "http_status": 200,
                            "response_complete": True, "request_id": "fixture-request", "result": "success",
                            "returned_model_id": "fixture-snapshot", "usage": {"feature_engine_id": "fixture-feature",
                                "context_tokens": len(request.payload), "input_tokens": len(request.payload),
                                "output_tokens": 9, "feature_calls": 1, "cost_microunits": None, "currency": None},
                            "cost_microunits": None, "observer_public_key_sha256": sha(observer_public)}
                        attempt_sink.record(TransportAttempt(metadata, request.payload, response_bytes,
                            transport_key.sign(encoded(metadata))))
                        response = ProviderResponse(config.provider.digest(), sha(request.payload), "fixture-request",
                            "fixture-snapshot", response_bytes, output, len(request.payload), 9, marker, b"unsigned")
                        return replace(response, proof=transport_key.sign(encoded(response.observation())))
                supplied = SuppliedContractClient()
                recorder = SelectedComparatorRecorder(custody=custody, run_id="run", configuration=config,
                    disclosure=disclosure, exchange_verifier=exchange_verifier, clock=now)
                adapter = GeneralMemoryArmAdapter(configuration=config, memory=memory, tokenizer=tokenizer,
                    wire_compiler=compiler, client=supplied, exchange_verifier=exchange_verifier,
                    disclosure=disclosure, recorder=recorder, attempt_custody=attempt_custody,
                    task_id_for=lambda request: "fixture-task-" + uuid.uuid4().hex)
                async def run():
                    return await run_paired(plan=plan, histories=histories, questions={"case": question},
                        adapters={"general_model_memory": adapter}, evidence_policy=evidence)
                denied = asyncio.run(run())
                self.assertEqual(supplied.calls, 0)
                self.assertEqual([a.status for a in denied.attempts if a.arm == "general_model_memory"], ["refused", "refused"])
                # Local evaluation grants do not imply permission to disclose.
                for event_id in (sources[0].event.event_id, sources[1].event.event_id,
                                 custody.metadata("run", "question:case").event_id):
                    grant(event_id, "comparison_external:fixture-provider")
                completed = asyncio.run(run())
                successes = [a for a in completed.attempts if a.arm == "general_model_memory"]
                timing = [{"phase": a.phase, "status": a.status, "elapsed_ms": a.elapsed_ms}
                    for a in successes]
                print("Selected comparator attempt timing:", json.dumps(timing, sort_keys=True), flush=True)
                self.assertEqual([a.status for a in successes], ["success", "success"], timing)
                self.assertEqual(supplied.calls, 2)
                self.assertTrue(all(a.usage.cost_microunits is None for a in successes))
                custody.save_run(run_id="run", run=completed, occurred_at=now())
                before_request = PreparationRequest("case", "before", question, histories[("case", "before")], plan)
                after_request = PreparationRequest("case", "after", question, histories[("case", "after")], plan)
                self.assertNotEqual(memory.collection(before_request), memory.collection(after_request))
                points, _ = vectors.scroll(collection_name=memory.collection(before_request), with_payload=True, limit=100)
                self.assertEqual({p.payload["source_window"]["event_id"] for p in points}, {sources[0].event.event_id})
                self.assertNotIn(sources[1].event.event_id, {p.payload["source_window"]["event_id"] for p in points})
                for event in list(log.replay()):
                    if event.event_type != "formation_permission_action":
                        grant(event.event_id, "comparison_local_recovery")
                recovered = custody.recover_run(run_id="run", permissions=permissions)
                self.assertEqual(tuple(a.status for a in recovered.attempts), tuple(a.status for a in completed.attempts))
                for attempt in successes:
                    exchange = json.loads(custody.read(run_id="run",
                        artifact_id="provider_exchange:" + attempt.decision_event_id,
                        permissions=permissions, purpose="comparison_local_recovery"))
                    self.assertTrue(exchange["actual_request_base64"])
                    self.assertTrue(exchange["actual_response_base64"])
                    self.assertEqual(exchange["observation"]["configuration_sha256"], config.provider.digest())
                    self.assertIsNone(exchange["observation"]["cost_microunits"])
                grant(sources[0].event.event_id, "comparison_external:fixture-provider", "revoke")
                revoked = asyncio.run(run())
                self.assertEqual(supplied.calls, 2)
                self.assertEqual([a.status for a in revoked.attempts if a.arm == "general_model_memory"], ["refused", "refused"])
                # Revoking disclosure has not revoked separately granted local access.
                self.assertTrue(evidence.authorize_history(case_id="case", phase="after", history=histories[("case", "after")]))
        finally:
            vectors.close()
            client.close()


if __name__ == "__main__":
    unittest.main()
