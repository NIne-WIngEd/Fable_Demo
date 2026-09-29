"""Selected-engine state activation/rollback qualification with fictional data.

Uses real XTDB, KurrentDB, encrypted local objects, durable registered sources
and current purpose-specific permissions. Supplied state bytes are fixtures,
not MFM or EIPM output and not evidence of learned personal development.
"""
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
from flora.selected.experience import KurrentExperienceLog
from flora.selected.formation_context import register_experience_source
from flora.selected.formation_policy import (
    FormationPermissionAction, XTDBFormationPermissionPolicy, formation_permission_payload,
)
from flora.selected.formation_registry import XTDBFormationSourceRegistry
from flora.selected.governed_development import XTDBGovernedPersonalDevelopment
from flora.selected.object_store import EncryptedObjectPlane, LocalObjectBackend
from flora.selected.owner_authorization import (
    Ed25519OwnerActionVerifier, OwnerActionProof, owner_action_message,
)
from flora.selected.personal_state import activation_request


def _now():
    return normalize_timestamp(datetime.now(timezone.utc).isoformat())


class GovernedDevelopmentSelectedBackendTest(unittest.TestCase):
    def test_registered_permissions_govern_activation_restore_and_restart(self):
        scope = ProductHostScope.create(product_id="friday",
            host_instance_id=f"flora-development-{uuid.uuid4().hex}", schema_version="1.0.0",
            encryption_domain="fictional-development-integration")
        namespace = "fictional-development-authority"
        dsn = os.environ.get("XTDB_DSN", "postgresql://xtdb@127.0.0.1:5432/xtdb")
        client = KurrentDBClient(os.environ.get("KURRENTDB_URI", "kurrentdb://127.0.0.1:2113?tls=false"))
        connection = psycopg.connect(dsn, autocommit=True)
        key, proofs, references = Ed25519PrivateKey.generate(), {}, {}
        verifier = Ed25519OwnerActionVerifier(scope=scope,
            owner_public_key=key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw), proofs=proofs)
        with tempfile.TemporaryDirectory() as directory:
            objects = EncryptedObjectPlane(scope=scope, key=b"g" * 32,
                                           backend=LocalObjectBackend(Path(directory) / "objects"))
            log = KurrentExperienceLog(scope=scope, client=client)
            registry = XTDBFormationSourceRegistry(scope=scope, authority_namespace_id=namespace,
                                                   connection=connection)
            policy = XTDBFormationPermissionPolicy(scope=scope, authority_namespace_id=namespace,
                                                   connection=connection, registry=registry)
            claims = XTDBClaimAuthority(scope=scope, authority_namespace_id=namespace, connection=connection)
            state = XTDBGovernedPersonalDevelopment(scope=scope, authority_namespace_id=namespace,
                connection=connection, registry=registry, policy=policy)
            identity = dict(subject_type="owner", subject_id=scope.host_instance_id,
                            projection_id="fictional-owner-state")
            inputs = dict(claims=claims, log=log, objects=objects, references=references)

            def event(content, event_type="observation", parents=(), occurred_at=None):
                raw = objects.put(content)
                references[raw.object_id] = raw
                recorded = ExperienceEvent.create(event_type=event_type, scope=scope,
                    occurred_at=occurred_at or _now(), content_digest=raw.plaintext_sha256,
                    provenance=ProvenanceReference.create(provenance_type="generated_reconstruction",
                        source_reference_ids=(raw.object_id,), derivation_activity_id="fictional-integration",
                        responsible_component="fictional-development-integration"),
                    retention_class="ordinary_experience", storage_tier="raw_buffer",
                    payload_reference=raw.object_id, parent_event_ids=parents)
                log.append(recorded, expected_revision=len(log.replay()) - 1)
                return recorded, raw

            def sign(recorded, action):
                proofs[recorded.event_id] = OwnerActionProof(action=action, event_id=recorded.event_id,
                    event_sha256=recorded.event_sha256,
                    signature_base64=base64.b64encode(key.sign(owner_action_message(recorded, action))).decode())

            permission_counter = 0
            def permission(source, decision="allow", previous=None):
                nonlocal permission_counter
                permission_counter += 1
                action = FormationPermissionAction.create(scope=scope, authority_namespace_id=namespace,
                    action_id=f"fictional-permission-{permission_counter}", source_ref_id=source.evidence.ref_id,
                    source_registration_sha256=source.registration_sha256, purpose="personal_judgment",
                    decision=decision, generation=1 if previous is None else previous[0].generation + 1,
                    previous_action_sha256=None if previous is None else previous[0].action_sha256,
                    authorization_ref=f"fixture-enrolled-owner-proof-{permission_counter}", authorized_at=_now())
                parents = (source.evidence.ref_id,) if previous is None else (source.evidence.ref_id, previous[1].event_id)
                recorded, _ = event(formation_permission_payload(action), "formation_permission_action",
                                    parents, action.authorized_at)
                sign(recorded, "formation_permission")
                policy.apply(action, request_event_id=recorded.event_id, log=log, objects=objects,
                             references=references, verifier=verifier)
                return action, recorded

            def version(generation, source, previous=None):
                raw = objects.put(f"fictional supplied personal state {generation}".encode())
                references[raw.object_id] = raw
                timestamp, version_id = _now(), f"fictional-state-v{generation}"
                envelope = MemoryUnitEnvelope.create(scope=scope, record_id=version_id,
                    record_type="projection_version", authority_namespace_id=namespace,
                    host_or_cluster_id=scope.host_instance_id, authority_role="registered_projection",
                    deployment_profile="single_workstation", created_at=timestamp, valid_from=timestamp,
                    valid_to=None, transaction_time=timestamp, logical_clock=generation,
                    source_records=(source.evidence.ref_id,), generation=generation, state="committed",
                    data_classification="highly_sensitive", retention_class="authoritative_source",
                    deletion_state="active", provenance_digest="a" * 64, content_digest=raw.plaintext_sha256,
                    writer="fixture-candidate-provider", workflow_or_request_id="fictional-development-run",
                    idempotency_namespace=namespace, idempotency_key=version_id,
                    supersedes=() if previous is None else (previous,))
                result = ProjectionVersion.create(envelope=envelope, projection_id=identity["projection_id"],
                    version_id=version_id, projection_type="owner_model", subject_type="owner",
                    subject_id=scope.host_instance_id, modalities=("symbolic",), generation=generation,
                    source_evidence_ids=(source.evidence.ref_id,), valid_from=timestamp, valid_to=None,
                    produced_at=timestamp, projection_state="candidate", responsible_component="fixture-candidate-provider",
                    model_id=None, model_version=None, content_digest=raw.plaintext_sha256,
                    supersedes_version_id=previous)
                return result, raw

            def activate(record, previous=None):
                approval, _ = event(activation_request(record, expected_active_version_id=previous),
                                    "state_activation_approval")
                sign(approval, "state_activation")
                result = state.activate(**identity, approval_event_id=approval.event_id,
                    expected_active_version_id=previous, verifier=verifier, **inputs)
                self.assertEqual(state.activate(**identity, approval_event_id=approval.event_id,
                    expected_active_version_id=previous, verifier=verifier, **inputs), result)
                return result

            try:
                source_event_one, raw = event(b"fictional evidence for first state")
                source_one = register_experience_source(event_id=source_event_one.event_id, raw=raw,
                    registry=registry, log=log, objects=objects, role="generated_reconstruction", modality="text")
                source_event_two, raw = event(b"fictional evidence for second state")
                source_two = register_experience_source(event_id=source_event_two.event_id, raw=raw,
                    registry=registry, log=log, objects=objects, role="generated_reconstruction", modality="text")
                first, first_content = version(1, source_one)
                with self.assertRaisesRegex(ValueError, "not currently permitted"):
                    state.put_candidate(first, content=first_content, **inputs)
                permission_one = permission(source_one)
                permission_two = permission(source_two)
                state.put_candidate(first, content=first_content, **inputs)
                activate(first.metadata_record())
                second, second_content = version(2, source_two, first.version_id)
                state.put_candidate(second, content=second_content,
                                    expected_previous_version_id=first.version_id, **inputs)
                activate(second.metadata_record(), first.version_id)
                permission(source_two, "revoke", permission_two)
                with self.assertRaisesRegex(ValueError, "not currently permitted"):
                    state.read_active(**identity, verifier=verifier, **inputs)
                restored = state.register_rollback(rollback_id="fictional-restore-one",
                    version_id="fictional-restored-v3", target_version_id=first.version_id,
                    expected_active_version_id=second.version_id, expected_latest_version_id=second.version_id,
                    produced_at=_now(), verifier=verifier, **inputs)
                self.assertEqual(restored.content, objects.get(first_content))
                self.assertEqual(restored.record["supersedes_version_id"], second.version_id)
                self.assertEqual(restored.record["envelope"]["rollback_reference"], first.version_id)
                activate(restored.record, second.version_id)

                # Fresh pgwire connection and registry/policy/state objects read
                # durable lineage. Private references/proofs remain explicitly
                # supplied test custody, not a production enrollment mechanism.
                connection.close()
                connection = psycopg.connect(dsn, autocommit=True)
                registry = XTDBFormationSourceRegistry(scope=scope, authority_namespace_id=namespace,
                                                       connection=connection)
                policy = XTDBFormationPermissionPolicy(scope=scope, authority_namespace_id=namespace,
                                                       connection=connection, registry=registry)
                claims = XTDBClaimAuthority(scope=scope, authority_namespace_id=namespace, connection=connection)
                state = XTDBGovernedPersonalDevelopment(scope=scope, authority_namespace_id=namespace,
                    connection=connection, registry=registry, policy=policy)
                inputs["claims"] = claims
                active = state.read_active(**identity, verifier=verifier, **inputs)
                self.assertEqual(active.record["version_id"], "fictional-restored-v3")
                self.assertEqual(active.content, objects.get(first_content))
                permission(source_one, "revoke", permission_one)
                with self.assertRaisesRegex(ValueError, "not currently permitted"):
                    state.read_active(**identity, verifier=verifier, **inputs)
                with self.assertRaisesRegex(ValueError, "not currently permitted"):
                    state.register_rollback(rollback_id="fictional-unsafe-restore",
                        version_id="fictional-restored-v4", target_version_id=first.version_id,
                        expected_active_version_id="fictional-restored-v3",
                        expected_latest_version_id="fictional-restored-v3", produced_at=_now(),
                        verifier=verifier, **inputs)
            finally:
                connection.close()
                client.close()


if __name__ == "__main__":
    unittest.main()
