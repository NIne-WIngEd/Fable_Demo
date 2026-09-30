"""Real selected-store assessment custody, with fictional human submissions.

No MFM, personality, model inference, live human study or qualified acceptance result.
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
from unittest.mock import patch

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from kurrentdbclient import KurrentDBClient
import psycopg

from cognitive_kernel.canonical import canonical_json_bytes, normalize_timestamp
from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from flora.blind_assessment import ApprovedReviewer, DIMENSIONS, Ed25519AssessmentAuthority, HumanRating, freeze_assessment_spec, pair_binding_sha256
from flora.comparison_run import ArmBinding, HistorySnapshot, MeasuredUsage, PairedRun, PairedRunPlan, RunAttempt, SourceMaterial, create_blind_review, _context_bytes
from flora.evaluation_protocol import ARMS, EvaluationCase, EvaluationProtocol
from flora.selected.assessment_custody import XTDBAssessmentCustody, assessment_purpose, assessment_rating_id
from flora.selected.comparison_custody import SelectedRunEvidencePolicy, XTDBComparisonCustody
from flora.selected.context import ContextPlan, LocalContext, LocalContextItem
from flora.selected.decision_outcome import RecordedEvent, record_decision
from flora.selected.experience import KurrentExperienceLog
from flora.selected.formation_context import register_experience_source
from flora.selected.formation_policy import FormationPermissionAction, XTDBFormationPermissionPolicy, formation_permission_payload
from flora.selected.formation_registry import XTDBFormationSourceRegistry
from flora.selected.object_store import EncryptedObjectPlane, LocalObjectBackend
from flora.selected.owner_authorization import Ed25519OwnerActionVerifier, OwnerActionProof, owner_action_message
from test_sealed_analysis import fictional_analysis_spec


def sha(content):
    return hashlib.sha256(content).hexdigest()


def now():
    return normalize_timestamp(datetime.now(timezone.utc).isoformat(), "fixture_time")


def run_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


class SelectedAssessmentCustodyIntegrationTest(unittest.TestCase):
    def test_real_custody_recovery_signed_seal_and_current_key_release(self):
        host = "assessment-" + uuid.uuid4().hex[:16]
        scope = ProductHostScope.create(product_id="friday", host_instance_id=host,
            schema_version="1.0.0", encryption_domain="key-" + host)
        namespace = "assessment-" + uuid.uuid4().hex[:16]
        dsn = os.environ.get("XTDB_DSN", "postgresql://xtdb@127.0.0.1:5432/xtdb")
        client = KurrentDBClient(os.environ.get("KURRENTDB_URI", "kurrentdb://127.0.0.1:2113?tls=false"))
        self.addCleanup(client.close)
        with tempfile.TemporaryDirectory() as directory:
            objects = EncryptedObjectPlane(scope=scope, key=b"s" * 32,
                backend=LocalObjectBackend(Path(directory) / "private-objects"))
            log = KurrentExperienceLog(scope=scope, client=client)
            with psycopg.connect(dsn, autocommit=True) as connection:
                registry = XTDBFormationSourceRegistry(scope=scope, authority_namespace_id=namespace, connection=connection)
                custody = XTDBComparisonCustody(scope=scope, authority_namespace_id=namespace,
                    connection=connection, registry=registry, objects=objects, log=log)
                materials = []
                for index, content in enumerate((b"Fictional original preference.", b"Fictional correction.")):
                    raw = objects.put(content)
                    parents = () if not index else (materials[0].event.event_id,)
                    event = ExperienceEvent.create(event_type="observation" if not index else "correction",
                        scope=scope, occurred_at=f"2020-01-0{index+1}T12:00:00Z", content_digest=raw.plaintext_sha256,
                        provenance=ProvenanceReference.create(provenance_type="generated_reconstruction",
                            source_reference_ids=(f"fictional-source-{index}",), derivation_activity_id="assessment-fixture",
                            responsible_component="synthetic-test"), retention_class="ordinary_experience",
                        storage_tier="raw_buffer", parent_event_ids=parents, payload_reference=raw.object_id)
                    log.append(event, expected_revision=len(log.replay()) - 1)
                    register_experience_source(event_id=event.event_id, raw=raw, registry=registry,
                        log=log, objects=objects, role="generated_reconstruction", modality="text")
                    materials.append(SourceMaterial(event, content))
                histories = {("case", "before"): HistorySnapshot(scope, tuple(materials[:1])),
                             ("case", "after"): HistorySnapshot(scope, tuple(materials))}
                rubric = canonical_json_bytes({"schema": "flora-human-assessment-rubric-v1",
                    "dimensions": {dimension: {"instruction": "Fictional rubric instruction; no actual study.",
                        "labels": ["left", "right", "tie"]} for dimension in sorted(DIMENSIONS)}})
                analysis_spec = fictional_analysis_spec()
                metric = analysis_spec["metrics"][0]
                metric["interventions"] = ["relevant_correction"]
                metric["label_scores"] = {"left": {"left": "1/1", "right": "-1/1"},
                    "right": {"left": "-1/1", "right": "1/1"}, "tie": {"left": "0/1", "right": "0/1"}}
                metric["uncertainty"].update(cluster_unit="host", resamples=4)
                metric["criteria"] = [{"quantity": "lower", "operator": "gt", "bound": "0/1"}]
                thresholds = canonical_json_bytes(analysis_spec)
                case_rubric = b"Fictional sealed expected case behavior; no actual personal judgment."
                question = b"What should this fictional person do?"
                case = EvaluationCase("case", host, "relevant_correction", "heldout", histories[("case", "before")].digest(),
                    histories[("case", "after")].digest(), sha(case_rubric), materials[-1].event.event_id)
                protocol = EvaluationProtocol("assessment-fixture", "a" * 64, now(), "fictional-feature",
                    32, 1000, (case,), "b" * 64, sha(rubric), sha(thresholds), "c" * 64, ("isolated-transfer-host",))
                bindings = {arm: ArmBinding(f"fictional-producer-{index}", str(index+1) * 64,
                    str(index+4) * 64, "supplied-contract-output") for index, arm in enumerate(sorted(ARMS))}
                plan = PairedRunPlan(protocol, bindings, 32, 10000, 2, {"case": sha(question)})
                custody.register_inputs(run_id="run", plan=plan, histories=histories, questions={"case": question}, occurred_at=now())
                attempts = []
                for phase in ("before", "after"):
                    history = histories[("case", phase)]
                    source = history.sources[-1]
                    context = LocalContext(ContextPlan(request_id=f"fictional-{phase}", purpose="fixture-assessment",
                        exact_claim_ids=("supplied-claim",)), (LocalContextItem("claim", "supplied-claim", "supplied-version",
                        (source.event.event_id,), source.plaintext),), True)
                    for index, arm in enumerate(("flora_full", "general_model_memory", "same_evidence_ablation")):
                        status = "unavailable" if phase == "before" and arm == "general_model_memory" else "success"
                        output = decision = None
                        if status == "success":
                            raw = objects.put(run_bytes(context.receipt_record()))
                            event = ExperienceEvent.create(event_type="context_delivery", scope=scope, occurred_at=now(),
                                content_digest=raw.plaintext_sha256, provenance=ProvenanceReference.create(
                                    provenance_type="derived_inference", source_reference_ids=context.source_event_ids,
                                    derivation_activity_id=f"fictional-context-{phase}-{index}", responsible_component="synthetic-test"),
                                retention_class="ordinary_experience", storage_tier="raw_buffer",
                                parent_event_ids=context.source_event_ids, payload_reference=raw.object_id)
                            log.append(event, expected_revision=len(log.replay()) - 1)
                            delivery = RecordedEvent(event, raw)
                            custody.register_recorded(delivery)
                            custody.register_context(run_id="run", context=context, delivery=delivery, occurred_at=now())
                            output = f"Supplied fictional recommendation {phase}-{index}; no inference.".encode()
                            decision = record_decision(log=log, objects=objects, verdict=output,
                                consumed_event_ids=(event.event_id,) + context.source_event_ids, references=registry,
                                model_artifact_sha256=bindings[arm].model_artifact_sha256, producer_component=bindings[arm].producer_component,
                                occurred_at=now(), expected_revision=len(log.replay()) - 1)
                            custody.register_recorded(decision)
                        common = sha(run_bytes({"history_sha256": history.digest(), "question_sha256": sha(question)}))
                        attempts.append(RunAttempt("case", host, arm, phase, plan.digest(), history.digest(), history.event_ids,
                            common, sha(_context_bytes(context)), status, 2,
                            MeasuredUsage("fictional-feature", 3, 5, 4, 1) if status == "success" else None,
                            None if output is None else sha(output), None if decision is None else decision.event.event_id,
                            bindings[arm].lineage_sha256, output))
                run = PairedRun(plan, tuple(attempts), {"case": question})
                custody.save_run(run_id="run", run=run, occurred_at=now())
                permissions = XTDBFormationPermissionPolicy(scope=scope, authority_namespace_id=namespace,
                    connection=connection, registry=registry)
                owner_key = Ed25519PrivateKey.generate()
                proofs, counter = {}, 0
                owner = Ed25519OwnerActionVerifier(scope=scope,
                    owner_public_key=owner_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw), proofs=proofs)

                def grant(event_id, purpose, decision="allow"):
                    nonlocal counter
                    previous = permissions.current_action(event_id, purpose)
                    if previous is not None and previous.decision == decision:
                        return
                    counter += 1
                    source = registry.lookup(event_id)
                    prior = None if previous is None else next(e for e in log.replay()
                        if e.event_type == "formation_permission_action" and e.provenance.derivation_activity_id == previous.action_id)
                    action = FormationPermissionAction.create(scope=scope, authority_namespace_id=namespace,
                        action_id=f"assessment-grant-{counter}", source_ref_id=event_id,
                        source_registration_sha256=source.registration_sha256, purpose=purpose, decision=decision,
                        generation=1 if previous is None else previous.generation+1,
                        previous_action_sha256=None if previous is None else previous.action_sha256,
                        authorization_ref=f"fictional-owner-proof-{counter}", authorized_at=now())
                    raw = objects.put(formation_permission_payload(action))
                    parents = (event_id,) + (() if prior is None else (prior.event_id,))
                    event = ExperienceEvent.create(event_type="formation_permission_action", scope=scope, occurred_at=action.authorized_at,
                        content_digest=raw.plaintext_sha256, provenance=ProvenanceReference.create(provenance_type="derived_inference",
                            source_reference_ids=parents, derivation_activity_id=action.action_id, responsible_component="synthetic-test"),
                        retention_class="ordinary_experience", storage_tier="raw_buffer", parent_event_ids=parents,
                        payload_reference=raw.object_id)
                    log.append(event, expected_revision=len(log.replay()) - 1)
                    register_experience_source(event_id=event.event_id, raw=raw, registry=registry, log=log,
                        objects=objects, role="derived_inference", modality="structured")
                    proofs[event.event_id] = OwnerActionProof("formation_permission", event.event_id, event.event_sha256,
                        base64.b64encode(owner_key.sign(owner_action_message(event, "formation_permission"))).decode())
                    permissions.apply(action, request_event_id=event.event_id, log=log, objects=objects, references=registry, verifier=owner)

                def grant_all(purpose):
                    for event_id in [e.event_id for e in log.replay() if e.event_type != "formation_permission_action"]:
                        grant(event_id, purpose)

                for purpose in ("comparison_local_recovery", "comparison_review"):
                    grant_all(purpose)
                review_policy = SelectedRunEvidencePolicy(custody=custody, run_id="run", permissions=permissions)
                pack, private = create_blind_review(run, policy=review_policy, rng=random.Random(7))
                custody.save_blind_review(run_id="run", public_pack=pack, private_key=private, occurred_at=now())
                for purpose in ("comparison_review", "comparison_unblind", "comparison_local_recovery"):
                    grant_all(purpose)
                with self.assertRaises(PermissionError):
                    custody.read(run_id="run", artifact_id="blind_key", permissions=permissions, purpose="comparison_unblind")
                reviewer_key, coordinator_key = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
                rpub = reviewer_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
                cpub = coordinator_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
                reviewer = ApprovedReviewer("fictional-reviewer", sha(rpub), "fictional-review-approval")
                coordinator = ApprovedReviewer("fictional-coordinator", sha(cpub), "fictional-seal-approval")
                signature_authority = Ed25519AssessmentAuthority(reviewer_public_keys={reviewer.reviewer_id: rpub},
                    coordinator_public_key=cpub, reviewer_approvals={reviewer.reviewer_id: reviewer}, coordinator_approval=coordinator)
                spec = freeze_assessment_spec(run=run, pack=pack, collection_id="collection", frozen_at=now(),
                    rubric=rubric, threshold_spec=thresholds, case_rubrics={"case": case_rubric}, reviewers=(reviewer,),
                    coordinator=coordinator, assignments=tuple((p["pair_id"], reviewer.reviewer_id) for p in pack["pairs"]))
                adapter = XTDBAssessmentCustody(comparison_custody=custody, signature_authority=signature_authority)
                adapter.register_spec(run_id="run", spec=spec, permissions=permissions, occurred_at=now())
                purpose = assessment_purpose("run", "collection")
                grant_all(purpose)
                with self.assertRaises(PermissionError):
                    custody.read(run_id="run", artifact_id="run", permissions=permissions, purpose=purpose)
                with self.assertRaises(PermissionError):
                    adapter.release_private_key(run_id="run", collection_id="collection", permissions=permissions)
                for pair in pack["pairs"]:
                    rating = HumanRating(assessment_rating_id("run", "collection", pair["pair_id"], reviewer.reviewer_id),
                        "collection", spec.digest(), reviewer.reviewer_id, pair["pair_id"], pair_binding_sha256(pair), now(),
                        {"personal_fit": "left", "reason_fit": "tie", "needed_change": None, "unrelated_stability": None})
                    arguments = dict(run_id="run", collection_id="collection", rating=rating,
                        proof=reviewer_key.sign(rating.message()), permissions=permissions, occurred_at=now())
                    artifact = adapter.submit_rating(**arguments)
                    grant_all(purpose)
                    self.assertEqual(adapter.submit_rating(**arguments), artifact)
                sealed_at = now()
                message = adapter.prepare_seal_message(run_id="run", collection_id="collection", sealed_at=sealed_at, permissions=permissions)
                with self.assertRaises(InvalidSignature):
                    adapter.seal_collection(run_id="run", collection_id="collection", sealed_at=sealed_at,
                        proof=b"x"*64, permissions=permissions, occurred_at=now())
                seal = adapter.seal_collection(run_id="run", collection_id="collection", sealed_at=sealed_at,
                    proof=coordinator_key.sign(message), permissions=permissions, occurred_at=now())
                with self.assertRaises(PermissionError):
                    adapter.release_private_key(run_id="run", collection_id="collection", permissions=permissions)
                grant_all(purpose)
                self.assertEqual(adapter.release_private_key(run_id="run", collection_id="collection", permissions=permissions), private)
                summary = adapter.aggregate_after_seal(run_id="run", collection_id="collection", permissions=permissions)
                self.assertEqual((summary["possible_comparison_pairs"], summary["reviewed_comparison_pairs"], summary["excluded_comparison_pairs"]), (4, 3, 1))
                self.assertEqual(summary["acceptance_decision"], "not_evaluated")
                key_event_id = custody.metadata("run", "blind_key").event_id
                report = adapter.analyze_after_seal(run_id="run", collection_id="collection", permissions=permissions)
                self.assertEqual(report["metrics"][0]["possible_pairs"], 1)
                self.assertEqual(report["acceptance_decision"], "not_evaluable")
                self.assertFalse(report["part1_qualified"])
                from flora.selected import assessment_custody as assessment_module
                actual_analysis = assessment_module.analyze_sealed_assessment
                completed_analyses = []
                armed, withdrawn = [False], []
                def withdraw_after_actual_analysis(**fields):
                    result = actual_analysis(**fields)
                    completed_analyses.append(result["schema"])
                    armed[0] = True
                    return result
                native_permits = permissions.permits
                def last_unblind_callback(source, current_purpose):
                    allowed = native_permits(source, current_purpose)
                    if (armed[0] and not withdrawn and source.evidence.ref_id == key_event_id
                            and current_purpose == "comparison_unblind"):
                        withdrawn.append(True)
                        grant(seal.event_id, purpose, "revoke")
                    return allowed
                with patch.object(assessment_module, "analyze_sealed_assessment", withdraw_after_actual_analysis), \
                        patch.object(permissions, "permits", last_unblind_callback):
                    with self.assertRaises(PermissionError):
                        adapter.analyze_after_seal(run_id="run", collection_id="collection", permissions=permissions)
                self.assertEqual(completed_analyses, ["flora-sealed-assessment-analysis-report-v1"])
                self.assertEqual(withdrawn, [True])
                grant(seal.event_id, purpose, "allow")
            # Recreate the connection/registry/policy/adapter from actual custody.
            with psycopg.connect(dsn, autocommit=True) as connection:
                registry = XTDBFormationSourceRegistry(scope=scope, authority_namespace_id=namespace, connection=connection)
                custody = XTDBComparisonCustody(scope=scope, authority_namespace_id=namespace, connection=connection,
                    registry=registry, objects=objects, log=log)
                permissions = XTDBFormationPermissionPolicy(scope=scope, authority_namespace_id=namespace, connection=connection, registry=registry)
                adapter = XTDBAssessmentCustody(comparison_custody=custody, signature_authority=signature_authority)
                self.assertTrue(adapter.recover_collection(run_id="run", collection_id="collection", permissions=permissions).sealed)
                self.assertEqual(adapter.release_private_key(run_id="run", collection_id="collection", permissions=permissions), private)
                grant(key_event_id, "comparison_unblind", "revoke")
                with self.assertRaises(PermissionError):
                    adapter.release_private_key(run_id="run", collection_id="collection", permissions=permissions)
