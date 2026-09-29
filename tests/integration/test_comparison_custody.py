"""Real selected-store custody qualification with supplied fictional outputs.

No personality, MFM, provider call or learned comparator is invoked. These tests
qualify placement/recovery/authority boundaries only.
"""

import base64
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import tempfile
import unittest
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from kurrentdbclient import KurrentDBClient
import psycopg

from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from flora.comparison_run import (
    ArmBinding, HistorySnapshot, MeasuredUsage, PairedRun, PairedRunPlan,
    RunAttempt, SourceMaterial, create_blind_review,
)
from flora.evaluation_protocol import ARMS, EvaluationCase, EvaluationProtocol
from flora.selected.comparison_custody import (
    SelectedRunEvidencePolicy, XTDBComparisonCustody, evaluation_purpose,
)
from flora.selected.context import ContextPlan, LocalContext, LocalContextItem
from flora.selected.decision_outcome import RecordedEvent, record_decision
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


def sha(content):
    return hashlib.sha256(content).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


class FailOneArtifactInsert:
    """Injected after real Kurrent/source registration, before artifact commit."""
    def __init__(self, connection):
        self.connection = connection
        self.pending = True
    def __getattr__(self, name):
        return getattr(self.connection, name)
    def execute(self, sql, params=None):
        if self.pending and sql.startswith("INSERT INTO flora_comparison_artifacts"):
            self.pending = False
            raise RuntimeError("synthetic interruption after canonical append")
        return self.connection.execute(sql, params)


class SelectedComparisonCustodyIntegrationTest(unittest.TestCase):
    def test_recovery_failure_matrix_exact_sources_and_separate_review_authority(self):
        host = "comparison-" + uuid.uuid4().hex[:16]
        scope = ProductHostScope.create(product_id="friday", host_instance_id=host,
                                        schema_version="1.0.0", encryption_domain="key-" + host)
        namespace = "comparison-" + uuid.uuid4().hex[:16]
        dsn = os.environ.get("XTDB_DSN", "postgresql://xtdb:xtdb@127.0.0.1:5432/xtdb")
        client = KurrentDBClient(os.environ.get("KURRENTDB_URI", "kurrentdb://127.0.0.1:2113?tls=false"))
        try:
            with tempfile.TemporaryDirectory() as directory:
                objects = EncryptedObjectPlane(scope=scope, key=b"k" * 32,
                    backend=LocalObjectBackend(Path(directory) / "objects"))
                log = KurrentExperienceLog(scope=scope, client=client)
                with psycopg.connect(dsn, autocommit=True) as connection:
                    registry = XTDBFormationSourceRegistry(scope=scope,
                        authority_namespace_id=namespace, connection=connection)
                    custody = XTDBComparisonCustody(scope=scope, authority_namespace_id=namespace,
                        connection=connection, registry=registry, objects=objects, log=log)
                    materials = []
                    for index, text in enumerate((b"Fictional original preference.", b"Fictional correction.")):
                        raw = objects.put(text)
                        event = ExperienceEvent.create(event_type="observation" if not index else "correction",
                            scope=scope, occurred_at=f"2020-01-0{index+1}T12:00:00Z",
                            content_digest=raw.plaintext_sha256,
                            provenance=ProvenanceReference.create(provenance_type="generated_reconstruction",
                                source_reference_ids=(f"synthetic-item-{index}",),
                                derivation_activity_id="comparison-custody-fixture", responsible_component="synthetic-test"),
                            retention_class="ordinary_experience", storage_tier="raw_buffer",
                            parent_event_ids=() if not index else (materials[0].event.event_id,),
                            payload_reference=raw.object_id)
                        log.append(event, expected_revision=len(log.replay()) - 1)
                        register_experience_source(event_id=event.event_id, raw=raw, registry=registry,
                            log=log, objects=objects, role="generated_reconstruction", modality="text")
                        materials.append(SourceMaterial(event, text))
                    histories = {("case", "before"): HistorySnapshot(scope, tuple(materials[:1])),
                                 ("case", "after"): HistorySnapshot(scope, tuple(materials))}
                    question = b"What should this fictional person do?"
                    case = EvaluationCase("case", host, "relevant_correction", "heldout",
                        histories[("case", "before")].digest(), histories[("case", "after")].digest(),
                        "a" * 64, materials[-1].event.event_id)
                    protocol = EvaluationProtocol("fixture-protocol", "b" * 64, now(), "synthetic-feature",
                        16, 1000, (case,), "c" * 64, "d" * 64, "e" * 64, "f" * 64, ("isolated-transfer-host",))
                    bindings = {arm: ArmBinding(f"synthetic-{index}", str(index + 1) * 64,
                        str(index + 4) * 64, "supplied-contract-output") for index, arm in enumerate(sorted(ARMS))}
                    plan = PairedRunPlan(protocol, bindings, 32, 10000, 2, {"case": sha(question)})
                    arguments = dict(run_id="run", plan=plan, histories=histories,
                                     questions={"case": question}, occurred_at=now())
                    custody.connection = FailOneArtifactInsert(connection)
                    with self.assertRaisesRegex(RuntimeError, "interruption"):
                        custody.register_inputs(**arguments)
                    custody.connection = connection
                    count_after_interruption = len(log.replay())
                    custody.register_inputs(**arguments)
                    count_after_recovery = len(log.replay())
                    custody.register_inputs(**arguments)
                    self.assertEqual(len(log.replay()), count_after_recovery)
                    self.assertGreater(count_after_recovery, count_after_interruption)
                    question_artifact = custody.metadata("run", "question:case")
                    self.assertEqual(question_artifact.record["parent_event_ids"], list(histories[("case", "before")].event_ids))
                    self.assertNotIn(materials[-1].event.event_id, question_artifact.record["parent_event_ids"])

                    permissions = XTDBFormationPermissionPolicy(scope=scope, authority_namespace_id=namespace,
                        connection=connection, registry=registry)
                    key = Ed25519PrivateKey.generate()
                    proofs = {}
                    verifier = Ed25519OwnerActionVerifier(scope=scope,
                        owner_public_key=key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw), proofs=proofs)
                    counter = 0
                    def grant(event_id, purpose, decision="allow"):
                        nonlocal counter
                        counter += 1
                        source = registry.lookup(event_id)
                        previous = permissions.current_action(event_id, purpose)
                        prior_event = None if previous is None else next(e for e in log.replay()
                            if e.provenance.derivation_activity_id == previous.action_id
                            and e.event_type == "formation_permission_action")
                        action = FormationPermissionAction.create(scope=scope,
                            authority_namespace_id=namespace, action_id=f"custody-permission-{counter}",
                            source_ref_id=event_id, source_registration_sha256=source.registration_sha256,
                            purpose=purpose, decision=decision,
                            generation=1 if previous is None else previous.generation + 1,
                            previous_action_sha256=None if previous is None else previous.action_sha256,
                            authorization_ref=f"synthetic-owner-{counter}", authorized_at=now())
                        raw = objects.put(formation_permission_payload(action))
                        parents = (event_id,) + (() if prior_event is None else (prior_event.event_id,))
                        event = ExperienceEvent.create(event_type="formation_permission_action", scope=scope,
                            occurred_at=action.authorized_at, content_digest=raw.plaintext_sha256,
                            provenance=ProvenanceReference.create(provenance_type="derived_inference",
                                source_reference_ids=parents, derivation_activity_id=action.action_id,
                                responsible_component="synthetic-test"),
                            retention_class="ordinary_experience", storage_tier="raw_buffer",
                            parent_event_ids=parents, payload_reference=raw.object_id)
                        log.append(event, expected_revision=len(log.replay()) - 1)
                        register_experience_source(event_id=event.event_id, raw=raw, registry=registry,
                            log=log, objects=objects, role="derived_inference", modality="structured")
                        proofs[event.event_id] = OwnerActionProof("formation_permission", event.event_id,
                            event.event_sha256, base64.b64encode(key.sign(owner_action_message(event, "formation_permission"))).decode())
                        permissions.apply(action, request_event_id=event.event_id, log=log,
                            objects=objects, references=registry, verifier=verifier)
                    policy = SelectedRunEvidencePolicy(custody=custody, run_id="run", permissions=permissions)
                    self.assertFalse(policy.authorize_history(case_id="case", phase="before", history=histories[("case", "before")]))
                    self.assertIsNone(policy.current_original_permission_marker(
                        case_id="case", phase="before", history=histories[("case", "before")]))
                    for phase in ("before", "after"):
                        for material in histories[("case", phase)].sources:
                            grant(material.event.event_id, evaluation_purpose("run", "case", phase))
                        self.assertTrue(policy.authorize_history(case_id="case", phase=phase, history=histories[("case", phase)]))
                        grant(custody.metadata("run", f"history:case:{phase}").event_id,
                              evaluation_purpose("run", "case", phase))
                        self.assertEqual(custody.recover_history(run_id="run", case_id="case", phase=phase,
                            permissions=permissions), histories[("case", phase)])
                    self.assertEqual(len(policy.current_original_permission_marker(
                        case_id="case", phase="before", history=histories[("case", "before")])), 64)
                    with self.assertRaisesRegex(PermissionError, "different evaluation phase"):
                        custody.read(run_id="run", artifact_id="history:case:after", permissions=permissions,
                                     purpose=evaluation_purpose("run", "case", "before"))
                    tampered = replace(histories[("case", "before")], sources=(replace(materials[0], plaintext=b"changed"),))
                    self.assertFalse(policy.authorize_history(case_id="case", phase="before", history=tampered))

                    attempts = []
                    for phase in ("before", "after"):
                        history = histories[("case", phase)]
                        source = history.sources[-1]
                        context = LocalContext(ContextPlan(request_id="supplied-" + phase,
                            purpose="synthetic-custody", exact_claim_ids=("supplied-fixture-claim",)),
                            (LocalContextItem("claim", "supplied-fixture-claim", "supplied-fixture-version",
                                              (source.event.event_id,), source.plaintext),), True)
                        context_sha = sha(json.dumps({"receipt": context.receipt_record(), "content": [
                            base64.b64encode(source.plaintext).decode()]}, sort_keys=True,
                            separators=(",", ":"), allow_nan=False).encode())
                        for arm in ("flora_full", "general_model_memory", "same_evidence_ablation"):
                            status = "success"
                            if arm == "general_model_memory":
                                status = "failed" if phase == "before" else "invalid_result"
                            if arm == "same_evidence_ablation" and phase == "after":
                                status = "timeout"
                            output, decision = None, None
                            if status == "success":
                                material = json.dumps(context.receipt_record(), sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()
                                raw = objects.put(material)
                                delivery = ExperienceEvent.create(event_type="context_delivery", scope=scope,
                                    occurred_at=now(), content_digest=raw.plaintext_sha256,
                                    provenance=ProvenanceReference.create(provenance_type="derived_inference",
                                        source_reference_ids=context.source_event_ids,
                                        derivation_activity_id=f"supplied-{phase}-{arm}", responsible_component="synthetic-test"),
                                    retention_class="ordinary_experience", storage_tier="raw_buffer",
                                    parent_event_ids=context.source_event_ids, payload_reference=raw.object_id)
                                log.append(delivery, expected_revision=len(log.replay()) - 1)
                                custody.register_recorded(RecordedEvent(delivery, raw))
                                custody.register_context(run_id="run", context=context,
                                    delivery=RecordedEvent(delivery, raw), occurred_at=now())
                                output = b"Supplied fictional contract output; no model inference."
                                decision = record_decision(log=log, objects=objects, verdict=output,
                                    consumed_event_ids=(delivery.event_id,) + context.source_event_ids,
                                    references=registry, model_artifact_sha256=bindings[arm].model_artifact_sha256,
                                    occurred_at=now(), expected_revision=len(log.replay()) - 1,
                                    producer_component=bindings[arm].producer_component)
                                self.assertFalse(policy.verify_recorded(decision))
                                custody.register_recorded(decision)
                                self.assertTrue(policy.verify_recorded(decision))
                            elif status == "invalid_result":
                                output = b"Rejected supplied candidate bytes; never a valid verdict."
                            common = sha(json.dumps({"history_sha256": history.digest(),
                                "question_sha256": sha(question)}, sort_keys=True, separators=(",", ":")).encode())
                            attempts.append(RunAttempt("case", host, arm, phase, plan.digest(), history.digest(),
                                history.event_ids, common, context_sha, status, 2,
                                MeasuredUsage("synthetic-feature", 3, 5, 4, 1) if status == "success" else None,
                                None if output is None else sha(output),
                                None if decision is None else decision.event.event_id,
                                bindings[arm].lineage_sha256, output))
                    run = PairedRun(plan, tuple(attempts), {"case": question})
                    custody.save_run(run_id="run", run=run, occurred_at=now())
                    custody.save_run(run_id="run", run=run, occurred_at=now())
                    self.assertEqual(len(custody.metadata("run", "run").record["metadata"]["matrix"]), 6)
                    self.assertEqual(custody.metadata("run", "output:case:after:general_model_memory").record["kind"], "rejected_output")
                    registered_events = [e.event_id for e in log.replay() if e.event_type != "formation_permission_action"]
                    for event_id in registered_events:
                        grant(event_id, "comparison_local_recovery")
                        grant(event_id, "comparison_review")
                    recovered = custody.recover_run(run_id="run", permissions=permissions)
                    self.assertEqual(tuple(a.status for a in recovered.attempts), tuple(a.status for a in attempts))
                    self.assertEqual(recovered.questions, run.questions)
                    pack, private = create_blind_review(recovered, policy=policy, rng=random.Random(3))
                    self.assertEqual(len(pack["pairs"]), 1)
                    custody.save_blind_review(run_id="run", public_pack=pack, private_key=private, occurred_at=now())
                    self.assertNotEqual(custody.metadata("run", "blind_pack").record["object_id"],
                                        custody.metadata("run", "blind_key").record["object_id"])
                    with self.assertRaises(PermissionError):
                        custody.export_review(run_id="run", permissions=permissions)
                    grant(custody.metadata("run", "blind_pack").event_id, "comparison_review")
                    self.assertEqual(custody.export_review(run_id="run", permissions=permissions), pack)
                    with self.assertRaisesRegex(PermissionError, "sealed assessment"):
                        custody.read(run_id="run", artifact_id="blind_key", permissions=permissions,
                                     purpose="comparison_review")
                    with self.assertRaisesRegex(PermissionError, "sealed assessment"):
                        custody.read(run_id="run", artifact_id="blind_key", permissions=permissions,
                                     purpose="comparison_unblind")
                    self.assertFalse(custody.permits_external_disclosure(run_id="run",
                        artifact_id="question:case", provider_id="fixture-provider", permissions=permissions))
                    for event_id in (materials[0].event.event_id, question_artifact.event_id):
                        grant(event_id, "comparison_external:fixture-provider")
                    self.assertTrue(custody.permits_external_disclosure(run_id="run",
                        artifact_id="question:case", provider_id="fixture-provider", permissions=permissions))
                    grant(materials[0].event.event_id, "comparison_review", "revoke")
                    with self.assertRaises(PermissionError):
                        custody.export_review(run_id="run", permissions=permissions)
                    # Local recovery did not inherit the separately revoked review purpose.
                    self.assertEqual(len(custody.recover_run(run_id="run", permissions=permissions).attempts), 6)
                # Recreate every registry/custody connection without caller RAM maps.
                with psycopg.connect(dsn, autocommit=True) as connection:
                    registry = XTDBFormationSourceRegistry(scope=scope, authority_namespace_id=namespace, connection=connection)
                    custody = XTDBComparisonCustody(scope=scope, authority_namespace_id=namespace,
                        connection=connection, registry=registry, objects=objects, log=log)
                    permissions = XTDBFormationPermissionPolicy(scope=scope,
                        authority_namespace_id=namespace, connection=connection, registry=registry)
                    recovered = custody.recover_run(run_id="run", permissions=permissions)
                    self.assertEqual(tuple(a.status for a in recovered.attempts), tuple(a.status for a in attempts))
                    self.assertIsNone(recovered.attempts[1].usage)
                    self.assertEqual(recovered.plan.digest(), plan.digest())
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
