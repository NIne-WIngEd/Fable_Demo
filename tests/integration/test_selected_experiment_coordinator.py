"""Real selected encrypted coordinator custody; no learned/model/API result."""
import asyncio
import base64
from dataclasses import replace
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from kurrentdbclient import KurrentDBClient
import psycopg
from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from flora.comparator import sha
from flora.comparison_run import ArmBinding, HistorySnapshot, PairedRunPlan, SourceMaterial
from flora.evaluation_protocol import ARMS, EvaluationCase, EvaluationProtocol
from flora.selected.assessment_custody import XTDBAssessmentCustody
from flora.selected.comparison_custody import SelectedRunEvidencePolicy, XTDBComparisonCustody, evaluation_purpose
from flora.selected.context import ContextPlan
from flora.selected.experience import KurrentExperienceLog
from flora.selected.experiment_coordinator import RegisteredExperimentCoordinator, coordinator_purpose
from flora.selected.experiment_manifests import CohortEntry, SelectedSourceAuthority, XTDBExperimentManifestCustody, cohort_source_purpose, manifest_purpose
from flora.selected.formation_context import register_experience_source
from flora.selected.formation_policy import FormationPermissionAction, XTDBFormationPermissionPolicy, formation_permission_payload
from flora.selected.formation_registry import XTDBFormationSourceRegistry
from flora.selected.native_arm import FrozenNativeArmPlan, NativeInvocationEntry, NativePhaseSnapshotBinding
from flora.selected.object_store import EncryptedObjectPlane, LocalObjectBackend
from flora.selected.owner_authorization import Ed25519OwnerActionVerifier, OwnerActionProof, owner_action_message


def now():
    return datetime.now(timezone.utc).isoformat()


def public(key):
    return key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


class SelectedExperimentCoordinatorIntegrationTest(unittest.TestCase):
    def test_registered_sources_to_blocked_control_stages_on_actual_selected_engines(self):
        client = KurrentDBClient(os.environ.get("KURRENTDB_URI", "kurrentdb://127.0.0.1:2113?tls=false"))
        try:
            with tempfile.TemporaryDirectory() as directory, psycopg.connect(
                    os.environ.get("XTDB_DSN", "postgresql://xtdb@127.0.0.1:5432/xtdb"), autocommit=True) as connection:
                host = "coordinator-" + uuid.uuid4().hex[:12]
                scope = ProductHostScope.create(product_id="friday", host_instance_id=host,
                    schema_version="1.0.0", encryption_domain="key-" + host)
                namespace = "coordinator-" + uuid.uuid4().hex[:12]
                objects = EncryptedObjectPlane(scope=scope, key=b"W" * 32, backend=LocalObjectBackend(Path(directory)))
                log = KurrentExperienceLog(scope=scope, client=client)
                registry = XTDBFormationSourceRegistry(scope=scope, authority_namespace_id=namespace, connection=connection)
                permissions = XTDBFormationPermissionPolicy(scope=scope, authority_namespace_id=namespace,
                    connection=connection, registry=registry)
                owner_key, proofs = Ed25519PrivateKey.generate(), {}
                verifier = Ed25519OwnerActionVerifier(scope=scope, owner_public_key=public(owner_key), proofs=proofs)
                count = 0
                def grant(event_id, purpose, decision="allow"):
                    nonlocal count
                    count += 1
                    source = registry.lookup(event_id)
                    previous = permissions.current_action(event_id, purpose)
                    prior_event = None if previous is None else next(event for event in log.replay()
                        if event.event_type == "formation_permission_action" and event.provenance.derivation_activity_id == previous.action_id)
                    action = FormationPermissionAction.create(scope=scope, authority_namespace_id=namespace,
                        action_id="coordinator-grant-" + str(count), source_ref_id=event_id,
                        source_registration_sha256=source.registration_sha256, purpose=purpose, decision=decision,
                        generation=1 if previous is None else previous.generation + 1,
                        previous_action_sha256=None if previous is None else previous.action_sha256,
                        authorization_ref="coordinator-owner-" + str(count), authorized_at=now())
                    raw = objects.put(formation_permission_payload(action))
                    parents = (event_id,) + (() if prior_event is None else (prior_event.event_id,))
                    request = ExperienceEvent.create(event_type="formation_permission_action", scope=scope,
                        occurred_at=action.authorized_at, content_digest=raw.plaintext_sha256,
                        provenance=ProvenanceReference.create(provenance_type="derived_inference", source_reference_ids=parents,
                            derivation_activity_id=action.action_id, responsible_component="synthetic-test"),
                        retention_class="ordinary_experience", storage_tier="raw_buffer", parent_event_ids=parents, payload_reference=raw.object_id)
                    log.append(request, expected_revision=len(log.replay()) - 1)
                    register_experience_source(event_id=request.event_id, raw=raw, registry=registry, log=log,
                        objects=objects, role="derived_inference", modality="structured")
                    proofs[request.event_id] = OwnerActionProof("formation_permission", request.event_id, request.event_sha256,
                        base64.b64encode(owner_key.sign(owner_action_message(request, "formation_permission"))).decode())
                    permissions.apply(action, request_event_id=request.event_id, log=log, objects=objects, references=registry, verifier=verifier)
                originals = []
                for index, content in enumerate((b"Fictional prior context", b"Fictional correction", b"Fictional question")):
                    raw = objects.put(content)
                    event = ExperienceEvent.create(event_type="observation", scope=scope, occurred_at="2020-01-01T00:00:00Z",
                        content_digest=raw.plaintext_sha256, provenance=ProvenanceReference.create(provenance_type="generated_reconstruction",
                            source_reference_ids=("fictional-coordinator-source-" + str(index),), derivation_activity_id="coordinator-fixture",
                            responsible_component="synthetic-test"), retention_class="ordinary_experience", storage_tier="raw_buffer", payload_reference=raw.object_id)
                    log.append(event, expected_revision=len(log.replay()) - 1)
                    register_experience_source(event_id=event.event_id, raw=raw, registry=registry, log=log, objects=objects,
                        role="generated_reconstruction", modality="text")
                    originals.append(SourceMaterial(event, content))
                    for purpose in (manifest_purpose("exp", "capture"), manifest_purpose("exp", "read"), cohort_source_purpose("exp", "training")):
                        grant(event.event_id, purpose)
                authority = SelectedSourceAuthority(registry, log, permissions, objects)
                lineage_key, result_key = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
                manifests = XTDBExperimentManifestCustody(experiment_id="exp", local=authority, authorities=(authority,),
                    connection=connection, control_anchor_event_id=originals[0].event.event_id,
                    lineage_public_key=public(lineage_key), approved_lineage_key_sha256=sha(public(lineage_key)),
                    qualification_public_key=public(result_key), approved_qualification_key_sha256=sha(public(result_key)),
                    part1_validator=None, clock=now)
                entries = tuple(CohortEntry("entry-" + str(index), authority.authority_id, source.event.event_id,
                    "training", "family", "generator", "a" * 64, "scenario", (), "person", "host",
                    "question" if index == 2 else "authorized_history") for index, source in enumerate(originals))
                cohort = manifests.register_cohort(cohort_id="cohort", entries=entries, rules=())
                grant(cohort["event_id"], manifest_purpose("exp", "read"))
                recipe = manifests.register_recipe(recipe_id="recipe", cohort_id="cohort",
                    code_files=(("src/flora/selected/supplied_fixture.py", b"# supplied fixture, not a builder\n"),),
                    dependency_lock=b"supplied fixture lock", role_contracts=(("personality", b"supplied interface"),),
                    source_choices=(("entry-0", "eligible"),), stop_defer_contract=b"supplied stop/defer")
                grant(recipe["event_id"], manifest_purpose("exp", "read"))
                comparison = XTDBComparisonCustody(scope=scope, authority_namespace_id=namespace,
                    connection=connection, registry=registry, objects=objects, log=log)
                histories = {("case", "before"): HistorySnapshot(scope, (originals[0],)),
                    ("case", "after"): HistorySnapshot(scope, tuple(originals[:2]))}
                native = {arm: FrozenNativeArmPlan(scope, namespace, arm, "a" * 64,
                    tuple(NativeInvocationEntry("case", phase, "invocation-" + arm + "-" + phase,
                        ContextPlan("context-" + phase, "personal_judgment", exact_claim_ids=("fixture-claim",)), "7" * 64,
                        NativePhaseSnapshotBinding("run", "snapshot-" + arm + "-" + phase, arm)) for phase in ("before", "after")))
                    for arm in ("flora_full", "same_evidence_ablation")}
                case = EvaluationCase("case", host, "relevant_correction", "heldout", histories[("case", "before")].digest(),
                    histories[("case", "after")].digest(), "c" * 64, originals[1].event.event_id)
                protocol = EvaluationProtocol("protocol", "d" * 64, now(), "feature", 16, 1000, (case,),
                    "e" * 64, "f" * 64, "1" * 64, recipe["content_sha256"], ("other-host",))
                bindings = {arm: ArmBinding("fixture-producer", "3" * 64,
                    native[arm].lineage_sha256 if arm in native else "4" * 64, "explicit-update") for arm in ARMS}
                plan = PairedRunPlan(protocol, bindings, 32, 4096, 2, {"case": sha(originals[2].plaintext)},
                    phase_bindings={("case", phase, arm): binding for arm, binding in bindings.items() for phase in ("before", "after")})
                comparison.register_inputs(run_id="run", plan=plan, histories=histories, questions={"case": originals[2].plaintext}, occurred_at=now())
                for (case_id, phase), history in histories.items():
                    for event_id in history.event_ids:
                        grant(event_id, evaluation_purpose("run", case_id, phase))
                control_sources = {source.event.event_id for source in originals} | {
                    cohort["event_id"], recipe["event_id"], comparison.metadata("run", "plan").event_id}
                for event_id in sorted(control_sources):
                    grant(event_id, coordinator_purpose("exp", "run", "capture"))
                evidence = SelectedRunEvidencePolicy(custody=comparison, run_id="run", permissions=permissions)
                coordinator = RegisteredExperimentCoordinator(manifests=manifests, cohort_id="cohort", recipe_id="recipe",
                    comparison=comparison, evidence=evidence,
                    assessment=XTDBAssessmentCustody(comparison_custody=comparison, signature_authority=object()),
                    plan=plan, histories=histories, questions={"case": originals[2].plaintext}, native_plans=native,
                    history_entry_ids={("case", "before"): ("entry-0",), ("case", "after"): ("entry-0", "entry-1")},
                    question_entry_ids={"case": "entry-2"}, provider_task_ids={("case", phase): "provider-" + phase for phase in ("before", "after")}, clock=now)
                binding = coordinator.prepare()
                grant(binding.event_id, coordinator_purpose("exp", "run", "capture"))
                outcome = asyncio.run(coordinator.execute(adapters={}))
                self.assertEqual(outcome.status, "preflight_blocked")
                self.assertIsNone(outcome.run)
                self.assertIsNone(comparison.metadata("run", "run"))
                control_sources.update((binding.event_id, comparison.metadata("run", outcome.artifact_id).event_id))
                for event_id in sorted(control_sources):
                    grant(event_id, coordinator_purpose("exp", "run", "read"))
                recovered = coordinator.recover_stage(artifact_id=outcome.artifact_id)
                self.assertFalse(recovered["part1_accepted"])
                self.assertFalse(recovered["payload"]["attempted"])
                with patch.object(AESGCM, "decrypt", side_effect=AssertionError("generic private control decrypted")):
                    with self.assertRaises(PermissionError):
                        comparison.read(run_id="run", artifact_id="coordinator:binding", permissions=permissions,
                            purpose=coordinator_purpose("exp", "run", "read"))
                grant(originals[0].event.event_id, cohort_source_purpose("exp", "training"), "revoke")
                with patch.object(AESGCM, "decrypt", side_effect=AssertionError("withdrawn control decrypted")):
                    with self.assertRaises(PermissionError):
                        coordinator.recover_stage(artifact_id="coordinator:binding")
        finally:
            client.close()
