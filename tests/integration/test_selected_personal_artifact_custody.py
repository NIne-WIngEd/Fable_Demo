"""Actual selected-engine derived custody/reconstruction; supplied fictional state."""
import base64
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
import unittest
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from kurrentdbclient import KurrentDBClient
import psycopg
from cognitive_kernel.canonical import normalize_timestamp
from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from cognitive_kernel.memory_contracts import MemoryUnitEnvelope
from cognitive_kernel.projection_contracts import ProjectionVersion
from flora.selected.claims import XTDBClaimAuthority
from flora.selected.context import ContextPlan, StateRoute, assemble_context
from flora.selected.judgment_context import RegisteredJudgmentContextPolicy
from flora.selected.experience import KurrentExperienceLog
from flora.selected.formation_context import register_experience_source
from flora.selected.formation_policy import FormationPermissionAction, XTDBFormationPermissionPolicy, formation_permission_payload
from flora.selected.formation_registry import XTDBFormationSourceRegistry
from flora.selected.governed_development import XTDBGovernedPersonalDevelopment, _version_from_record
from flora.selected.object_store import EncryptedObjectPlane, LocalObjectBackend
from flora.selected.owner_authorization import Ed25519OwnerActionVerifier, OwnerActionProof, owner_action_message
from flora.selected.personal_artifact_custody import (
    DurableOwnerProofLookup, DurablePersonalReferences, XTDBPersonalArtifactCustody,
)
from flora.selected.personal_state import activation_request


def _now():
    return normalize_timestamp(datetime.now(timezone.utc).isoformat())


class SelectedPersonalArtifactCustodyTest(unittest.TestCase):
    def test_state_approval_permission_and_rollback_recover_without_reference_or_proof_maps(self):
        scope = ProductHostScope.create(product_id="friday",
            host_instance_id=f"flora-private-custody-{uuid.uuid4().hex}", schema_version="1.0.0",
            encryption_domain="fictional-private-custody-key")
        namespace = "fictional-private-custody-authority"
        key = Ed25519PrivateKey.generate()
        public_key = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        dsn = os.environ.get("XTDB_DSN", "postgresql://xtdb@127.0.0.1:5432/xtdb")
        uri = os.environ.get("KURRENTDB_URI", "kurrentdb://127.0.0.1:2113?tls=false")
        connection, client = psycopg.connect(dsn, autocommit=True), KurrentDBClient(uri)
        with tempfile.TemporaryDirectory() as directory:
            objects = EncryptedObjectPlane(scope=scope, key=b"z" * 32,
                                           backend=LocalObjectBackend(Path(directory) / "objects"))
            def attach():
                log = KurrentExperienceLog(scope=scope, client=client)
                registry = XTDBFormationSourceRegistry(scope=scope, authority_namespace_id=namespace, connection=connection)
                custody = XTDBPersonalArtifactCustody(scope=scope, authority_namespace_id=namespace, connection=connection)
                references = DurablePersonalReferences(custody=custody, originals=registry)
                proofs = DurableOwnerProofLookup(custody=custody, log=log, objects=objects, owner_public_key=public_key)
                verifier = Ed25519OwnerActionVerifier(scope=scope, owner_public_key=public_key, proofs=proofs)
                policy = XTDBFormationPermissionPolicy(scope=scope, authority_namespace_id=namespace,
                                                       connection=connection, registry=registry)
                claims = XTDBClaimAuthority(scope=scope, authority_namespace_id=namespace, connection=connection)
                state = XTDBGovernedPersonalDevelopment(scope=scope, authority_namespace_id=namespace,
                    connection=connection, registry=registry, policy=policy)
                return log, registry, custody, references, verifier, policy, claims, state
            log, registry, custody, references, verifier, policy, claims, state = attach()
            identity = dict(subject_type="owner", subject_id=scope.host_instance_id, projection_id="fictional-owner-state")
            def inputs():
                return dict(claims=claims, log=log, objects=objects, references=references)
            def event(content, kind, parents=(), at=None):
                raw = objects.put(content)
                recorded = ExperienceEvent.create(event_type=kind, scope=scope, occurred_at=at or _now(),
                    content_digest=raw.plaintext_sha256,
                    provenance=ProvenanceReference.create(provenance_type="generated_reconstruction",
                        source_reference_ids=(raw.object_id,), derivation_activity_id="fictional-custody-integration",
                        responsible_component="fictional-custody-fixture"),
                    retention_class="ordinary_experience", storage_tier="raw_buffer",
                    payload_reference=raw.object_id, parent_event_ids=parents)
                log.append(recorded, expected_revision=len(log.replay()) - 1)
                return recorded, raw
            def proof(recorded, action):
                signed = OwnerActionProof(action=action, event_id=recorded.event_id,
                    event_sha256=recorded.event_sha256,
                    signature_base64=base64.b64encode(key.sign(owner_action_message(recorded, action))).decode())
                custody.record_owner_proof(proof=signed, owner_public_key=public_key,
                    log=log, objects=objects, occurred_at=_now(), expected_revision=len(log.replay()) - 1)
            def permission(source, decision="allow"):
                previous = policy.current_action(source.evidence.ref_id, "personal_judgment")
                previous_event_id = None if previous is None else policy._stored_action(previous.action_id)["request_event_id"]
                at = _now()
                action = FormationPermissionAction.create(scope=scope, authority_namespace_id=namespace,
                    action_id="permission-" + uuid.uuid4().hex, source_ref_id=source.evidence.ref_id,
                    source_registration_sha256=source.registration_sha256, purpose="personal_judgment",
                    decision=decision, generation=1 if previous is None else previous.generation + 1,
                    previous_action_sha256=None if previous is None else previous.action_sha256,
                    authorization_ref="fictional-enrolled-owner", authorized_at=at)
                parents = (source.evidence.ref_id,) if previous is None else (source.evidence.ref_id, previous_event_id)
                request, raw = event(formation_permission_payload(action), "formation_permission_action", parents, at)
                custody.register_formation_permission(action=action, request_event_id=request.event_id,
                    raw=raw, log=log, objects=objects)
                proof(request, "formation_permission")
                policy.apply(action, request_event_id=request.event_id, log=log, objects=objects,
                             references=references, verifier=verifier)
            def version(number, source, previous=None):
                raw, at = objects.put(f"fictional private state {number}".encode()), _now()
                version_id = f"fictional-state-v{number}"
                envelope = MemoryUnitEnvelope.create(scope=scope, record_id=version_id,
                    record_type="projection_version", authority_namespace_id=namespace,
                    host_or_cluster_id=scope.host_instance_id, authority_role="registered_projection",
                    deployment_profile="single_workstation", created_at=at, valid_from=at, valid_to=None,
                    transaction_time=at, logical_clock=number, source_records=(source.evidence.ref_id,),
                    generation=number, state="committed", data_classification="highly_sensitive",
                    retention_class="authoritative_source", deletion_state="active", provenance_digest="a" * 64,
                    content_digest=raw.plaintext_sha256, writer="fictional-candidate-supplier",
                    workflow_or_request_id="fictional-custody", idempotency_namespace=namespace,
                    idempotency_key=version_id, supersedes=() if previous is None else (previous,))
                result = ProjectionVersion.create(envelope=envelope, projection_id=identity["projection_id"],
                    version_id=version_id, projection_type="owner_model", subject_type="owner",
                    subject_id=scope.host_instance_id, modalities=("symbolic",), generation=number,
                    source_evidence_ids=(source.evidence.ref_id,), valid_from=at, valid_to=None, produced_at=at,
                    projection_state="candidate", responsible_component="fictional-candidate-supplier",
                    model_id=None, model_version=None, content_digest=raw.plaintext_sha256,
                    supersedes_version_id=previous)
                custody.record(artifact_id=version_id, kind="projection", contract=result.metadata_record(),
                    attachments=(("content", raw),), parent_event_ids=(source.evidence.ref_id,),
                    log=log, objects=objects, occurred_at=_now(), expected_revision=len(log.replay()) - 1)
                return result, raw
            def activate(version, previous=None):
                approval, raw = event(activation_request(version.metadata_record(), expected_active_version_id=previous),
                                      "state_activation_approval")
                custody.register_approval(approval_event_id=approval.event_id, candidate=version,
                    expected_active_version_id=previous, raw=raw, log=log, objects=objects)
                proof(approval, "state_activation")
                approval_source = register_experience_source(event_id=approval.event_id, raw=raw,
                    registry=registry, log=log, objects=objects, role="generated_reconstruction", modality="structured")
                permission(approval_source)
                return state.activate(**identity, approval_event_id=approval.event_id,
                    expected_active_version_id=previous, verifier=verifier, **inputs())
            try:
                sources = []
                for number in (1, 2):
                    observation, raw = event(f"fictional source {number}".encode(), "observation")
                    source = register_experience_source(event_id=observation.event_id, raw=raw,
                        registry=registry, log=log, objects=objects, role="generated_reconstruction", modality="text")
                    permission(source)
                    sources.append(source)
                first, raw = version(1, sources[0])
                state.put_candidate(first, content=raw, **inputs())
                activate(first)
                second, raw = version(2, sources[1], first.version_id)
                state.put_candidate(second, content=raw, expected_previous_version_id=first.version_id, **inputs())
                activate(second, first.version_id)
                restored = state.register_rollback(rollback_id="fictional-restoration",
                    version_id="fictional-restored-v3", target_version_id=first.version_id,
                    expected_active_version_id=second.version_id, expected_latest_version_id=second.version_id,
                    produced_at=_now(), verifier=verifier, **inputs())
                restored_version = _version_from_record(restored.record)
                target_artifact = custody.read(first.version_id, log=log, objects=objects)
                target_raw = dict(target_artifact.references)["content"]
                custody.record(artifact_id=restored_version.version_id, kind="projection",
                    contract=restored.record, attachments=(("content", target_raw),),
                    parent_event_ids=(sources[0].evidence.ref_id,), log=log, objects=objects,
                    occurred_at=_now(), expected_revision=len(log.replay()) - 1)
                activate(restored_version, second.version_id)

                connection.close()
                client.close()
                connection, client = psycopg.connect(dsn, autocommit=True), KurrentDBClient(uri)
                objects = EncryptedObjectPlane(scope=scope, key=b"z" * 32,
                    backend=LocalObjectBackend(Path(directory) / "objects"))
                log, registry, custody, references, verifier, policy, claims, state = attach()
                active = state.read_active(**identity, verifier=verifier, **inputs())
                self.assertEqual(active.record["version_id"], "fictional-restored-v3")
                self.assertEqual(active.content, b"fictional private state 1")
                judgment_policy = RegisteredJudgmentContextPolicy(claims=claims, state=state, log=log,
                    registry=registry, permissions=policy)
                plan = ContextPlan(request_id="fictional-registered-state-context", purpose="personal_judgment",
                    state_routes=(StateRoute(**identity),))
                context = assemble_context(plan=plan, state=state, policy=judgment_policy,
                    approval_verifier=verifier, **inputs())
                self.assertEqual(context.items[0].content, b"fictional private state 1")
                self.assertEqual(context.items[0].approval_event_id, active.approval_event_id)
                recovered = custody.read(active.record["version_id"], log=log, objects=objects)
                self.assertEqual(recovered.contract["envelope"]["rollback_reference"], first.version_id)
                permission(registry.lookup(sources[0].evidence.ref_id), "revoke")
                opened, original_get = [], objects.get
                objects.get = lambda ref: (opened.append(ref.object_id), original_get(ref))[1]
                with self.assertRaisesRegex(ValueError, "not currently permitted"):
                    state.read_active(**identity, verifier=verifier, **inputs())
                self.assertEqual(opened, [])
                with self.assertRaisesRegex(PermissionError, "personal state is not permitted"):
                    assemble_context(plan=plan, state=state, policy=judgment_policy,
                        approval_verifier=verifier, **inputs())
                self.assertEqual(opened, [])
            finally:
                connection.close()
                client.close()


if __name__ == "__main__":
    unittest.main()
