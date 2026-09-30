"""Real selected custody, two fictional hosts; no learned or builder result."""
import base64
import inspect
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
from cognitive_kernel.canonical import canonical_sha256
from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from flora.comparator import encoded, sha
from flora.selected.comparison_custody import XTDBComparisonCustody
from flora.selected.experience import KurrentExperienceLog
from flora.selected.experiment_manifests import (
    CohortEntry, RegisteredPart1Material, RegisteredPart1MaterialReader, SelectedSourceAuthority,
    SplitIsolationRule, XTDBExperimentManifestCustody,
    cohort_source_purpose, manifest_purpose,
)
from flora.selected.formation_context import register_experience_source
from flora.selected.formation_policy import FormationPermissionAction, XTDBFormationPermissionPolicy, formation_permission_payload
from flora.selected.formation_registry import XTDBFormationSourceRegistry
from flora.selected.object_store import EncryptedObjectPlane, LocalObjectBackend
from flora.selected.owner_authorization import Ed25519OwnerActionVerifier, OwnerActionProof, owner_action_message


def now():
    return datetime.now(timezone.utc).isoformat()


def public(key):
    return key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


class SelectedExperimentManifestIntegrationTest(unittest.TestCase):
    def test_cross_host_metadata_permissions_private_recovery_and_no_auto_builder_case(self):
        client = KurrentDBClient(os.environ.get("KURRENTDB_URI", "kurrentdb://127.0.0.1:2113?tls=false"))
        try:
            with tempfile.TemporaryDirectory() as directory, psycopg.connect(
                    os.environ.get("XTDB_DSN", "postgresql://xtdb@127.0.0.1:5432/xtdb"), autocommit=True) as connection:
                authorities, original_events, owner_controls = [], [], []
                for index in range(2):
                    host = "manifest-" + uuid.uuid4().hex[:12]
                    scope = ProductHostScope.create(product_id="friday", host_instance_id=host,
                        schema_version="1.0.0", encryption_domain="key-" + host)
                    namespace = "manifest-" + uuid.uuid4().hex[:12]
                    objects = EncryptedObjectPlane(scope=scope, key=bytes([71 + index]) * 32,
                        backend=LocalObjectBackend(Path(directory) / str(index)))
                    log = KurrentExperienceLog(scope=scope, client=client)
                    registry = XTDBFormationSourceRegistry(scope=scope, authority_namespace_id=namespace, connection=connection)
                    raw = objects.put(("Independent fictional host source " + str(index)).encode())
                    event = ExperienceEvent.create(event_type="observation", scope=scope, occurred_at="2020-01-01T00:00:00Z",
                        content_digest=raw.plaintext_sha256, provenance=ProvenanceReference.create(provenance_type="generated_reconstruction",
                            source_reference_ids=("fictional-source-" + str(index),), derivation_activity_id="manifest-integration-fixture",
                            responsible_component="synthetic-test"), retention_class="ordinary_experience", storage_tier="raw_buffer",
                        payload_reference=raw.object_id)
                    log.append(event, expected_revision=-1)
                    register_experience_source(event_id=event.event_id, raw=raw, registry=registry, log=log, objects=objects,
                        role="generated_reconstruction", modality="text")
                    permissions = XTDBFormationPermissionPolicy(scope=scope, authority_namespace_id=namespace,
                        connection=connection, registry=registry)
                    key, proofs = Ed25519PrivateKey.generate(), {}
                    verifier = Ed25519OwnerActionVerifier(scope=scope, owner_public_key=public(key), proofs=proofs)
                    authorities.append(SelectedSourceAuthority(registry, log, permissions, objects))
                    original_events.append(event)
                    owner_controls.append((key, proofs, verifier))
                counter = 0
                def grant(index, event_id, purpose, decision="allow"):
                    nonlocal counter
                    counter += 1
                    authority = authorities[index]
                    registry, log, objects, policy = authority.registry, authority.log, authority.objects, authority.permissions
                    source = registry.lookup(event_id)
                    prior = policy.current_action(event_id, purpose)
                    previous = None if prior is None else next(event for event in log.replay()
                        if event.event_type == "formation_permission_action" and event.provenance.derivation_activity_id == prior.action_id)
                    action = FormationPermissionAction.create(scope=registry.scope, authority_namespace_id=registry.authority_namespace_id,
                        action_id="fixture-manifest-grant-" + str(counter), source_ref_id=event_id,
                        source_registration_sha256=source.registration_sha256, purpose=purpose, decision=decision,
                        generation=1 if prior is None else prior.generation + 1,
                        previous_action_sha256=None if prior is None else prior.action_sha256,
                        authorization_ref="fixture-owner-" + str(counter), authorized_at=now())
                    raw = objects.put(formation_permission_payload(action))
                    parents = (event_id,) + (() if previous is None else (previous.event_id,))
                    request = ExperienceEvent.create(event_type="formation_permission_action", scope=registry.scope,
                        occurred_at=action.authorized_at, content_digest=raw.plaintext_sha256,
                        provenance=ProvenanceReference.create(provenance_type="derived_inference", source_reference_ids=parents,
                            derivation_activity_id=action.action_id, responsible_component="synthetic-test"), retention_class="ordinary_experience",
                        storage_tier="raw_buffer", parent_event_ids=parents, payload_reference=raw.object_id)
                    log.append(request, expected_revision=len(log.replay()) - 1)
                    register_experience_source(event_id=request.event_id, raw=raw, registry=registry, log=log, objects=objects,
                        role="derived_inference", modality="structured")
                    key, proofs, verifier = owner_controls[index]
                    proofs[request.event_id] = OwnerActionProof("formation_permission", request.event_id, request.event_sha256,
                        base64.b64encode(key.sign(owner_action_message(request, "formation_permission"))).decode())
                    policy.apply(action, request_event_id=request.event_id, log=log, objects=objects, references=registry, verifier=verifier)
                for index, event in enumerate(original_events):
                    for operation in ("capture", "read"):
                        grant(index, event.event_id, manifest_purpose("exp", operation))
                    grant(index, event.event_id, cohort_source_purpose("exp", "training" if index == 0 else "heldout"))
                lineage_key, result_key = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
                def custody():
                    return XTDBExperimentManifestCustody(experiment_id="exp", local=authorities[0], authorities=tuple(authorities),
                        connection=connection, control_anchor_event_id=original_events[0].event_id,
                        lineage_public_key=public(lineage_key), approved_lineage_key_sha256=sha(public(lineage_key)),
                        qualification_public_key=public(result_key), approved_qualification_key_sha256=sha(public(result_key)),
                        part1_validator=None, clock=now)
                store = custody()
                entries = tuple(CohortEntry("entry-" + str(index), authority.authority_id, original_events[index].event_id,
                    "training" if index == 0 else "heldout", "family-" + str(index), "shared-fixture-generator", "a" * 64,
                    "scenario-" + str(index), (), "person-" + str(index), "host", "authorized_history")
                    for index, authority in enumerate(authorities))
                rule = SplitIsolationRule("heldout", "training",
                    tuple(sorted({"source_family", "scenario_ancestry", "person_family", "source_ancestry"})), ("generator_family",))
                cohort_body = {"entries": [entry.record() for entry in entries], "rules": [rule.record()],
                    "bindings": {entry.entry_id: authorities[index].binding(entry.event_id) for index, entry in enumerate(entries)}}
                claim = {"schema": "flora-cohort-lineage-attestation-v1", "experiment_id": "exp",
                    "enrolled_key_sha256": sha(public(lineage_key)), "actual_family_ancestry_verified": True,
                    "cohort_sha256": canonical_sha256(cohort_body)}
                cohort_record = store.register_cohort(cohort_id="cohort", entries=entries, rules=(rule,), lineage_claim=claim,
                    lineage_proof=lineage_key.sign(encoded(claim)))
                self.assertNotIn(original_events[1].event_id, cohort_record["parent_event_ids"])
                grant(0, cohort_record["event_id"], manifest_purpose("exp", "read"))
                self.assertEqual(custody().recover(kind="cohort", manifest_id="cohort")["status"], "lineage_qualified")
                # The source-lineage fixture key certifies only mechanics here.
                # No signed result validator/native artifact exists in this test.
                recipe = store.register_recipe(recipe_id="recipe", cohort_id="cohort",
                    code_files=(("src/flora/selected/experiment_manifests.py", Path(__file__).resolve().parents[2].joinpath(
                        "src/flora/selected/experiment_manifests.py").read_bytes()),),
                    dependency_lock=b"fictional lock: no qualified model export", role_contracts=(("personality", b"supplied role port only"),),
                    source_choices=(("entry-0", "eligible"), ("entry-1", "stop")), stop_defer_contract=b"supplied fixture stop/defer contract")
                grant(0, recipe["event_id"], manifest_purpose("exp", "read"))
                case = store.register_linked_case(case_id="defer", recipe_id="recipe", split="training", input_entry_ids=("entry-0",),
                    proposal=b"supplied defer proposal", resolution="deferred")
                grant(0, case["event_id"], manifest_purpose("exp", "read"))
                recovered_case = custody().recover(kind="linked_case", manifest_id="defer")
                self.assertFalse(recovered_case["training_eligible"])
                self.assertFalse(recovered_case["evaluation_eligible"])
                comparison = XTDBComparisonCustody(scope=authorities[0].registry.scope,
                    authority_namespace_id=authorities[0].registry.authority_namespace_id, connection=connection,
                    registry=authorities[0].registry, objects=authorities[0].objects, log=authorities[0].log)
                # Exercise only the actual typed storage route. These bytes are
                # explicitly fictional and cannot qualify an empirical result.
                material_bytes = encoded({"schema": "fictional-route-mechanics", "not_an_empirical_result": True})
                material = comparison._put(run_id="fixture-run", artifact_id="run", kind="run", content=material_bytes,
                    parents=(original_events[0].event_id,), metadata={}, occurred_at=now())
                for event_id in (original_events[0].event_id, material.event_id):
                    for purpose in (manifest_purpose("exp", "qualification"), "comparison_local_recovery"):
                        grant(0, event_id, purpose)
                gate = store._gate(authorities[0].authority_id, material.event_id, manifest_purpose("exp", "qualification"), original=False)
                route = RegisteredPart1Material("result", authorities[0].authority_id, material.event_id, "comparison",
                    tuple(sorted({"run_id": "fixture-run", "artifact_id": "run", "artifact_kind": "run",
                        "custody_purpose": "comparison_local_recovery"}.items())), comparison)
                typed_reader = RegisteredPart1MaterialReader(routes=(route,), artifact_sha256=sha(Path(__file__).resolve().parents[2].joinpath(
                    "src/flora/selected/experiment_manifests.py").read_bytes()))
                self.assertEqual(typed_reader.read(name="result", authority=authorities[0], gate=gate), material_bytes)
                with self.assertRaisesRegex(PermissionError, "dedicated typed"):
                    authorities[0].read(gate)
                grant(0, material.event_id, "comparison_local_recovery", "revoke")
                with self.assertRaises(PermissionError):
                    typed_reader.read(name="result", authority=authorities[0], gate=gate)
                original_get, reads = authorities[0].objects.get, []
                def must_not_decrypt(raw):
                    reads.append(raw.object_id)
                    raise AssertionError("private cohort must not enter a generic inference/review route")
                authorities[0].objects.get = must_not_decrypt
                try:
                    with self.assertRaises((ValueError, PermissionError)):
                        comparison.load_recorded(cohort_record["event_id"])
                    self.assertEqual(reads, [])
                finally:
                    authorities[0].objects.get = original_get
                grant(1, original_events[1].event_id, cohort_source_purpose("exp", "heldout"), "revoke")
                grant(0, cohort_record["event_id"], manifest_purpose("exp", "qualification"))
                private_gate = store._gate(authorities[0].authority_id, cohort_record["event_id"],
                    manifest_purpose("exp", "qualification"), original=False)
                with self.assertRaisesRegex(PermissionError, "dedicated typed"):
                    authorities[0].read(private_gate)
                authorities[0].objects.get = must_not_decrypt
                try:
                    with self.assertRaises(PermissionError):
                        custody().recover(kind="cohort", manifest_id="cohort")
                    self.assertEqual(reads, [])
                finally:
                    authorities[0].objects.get = original_get
                grant(1, original_events[1].event_id, cohort_source_purpose("exp", "heldout"))
                backend = authorities[0].objects.backend
                original_cipher_read = backend.get_object
                armed = {"value": True}
                def withdraw_during_read(namespace, object_id):
                    value = original_cipher_read(namespace, object_id)
                    if (armed["value"] and object_id == cohort_record["object_id"]
                            and any(frame.function == "get" and frame.filename.endswith("object_store.py") for frame in inspect.stack())):
                        armed["value"] = False
                        grant(1, original_events[1].event_id, cohort_source_purpose("exp", "heldout"), "revoke")
                    return value
                original_decrypt = AESGCM.decrypt
                cohort_aad = f"{authorities[0].registry.scope.storage_scope()}:{cohort_record['object_id']}".encode()
                cohort_decrypts = []
                def reject_private_decrypt(cipher, nonce, data, aad):
                    if aad == cohort_aad:
                        cohort_decrypts.append(aad)
                        raise AssertionError("withdrawn cohort must remain sealed")
                    return original_decrypt(cipher, nonce, data, aad)
                with patch.object(backend, "get_object", side_effect=withdraw_during_read), \
                        patch.object(AESGCM, "decrypt", reject_private_decrypt):
                    with self.assertRaises(PermissionError):
                        store.recover(kind="cohort", manifest_id="cohort")
                self.assertFalse(armed["value"])
                self.assertEqual(cohort_decrypts, [])
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
