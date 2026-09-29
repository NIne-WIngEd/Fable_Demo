"""Actual selected episode/state persistence with fictional externally supplied outputs.

The local admission allow-list exercises infrastructure gates only. It is neither
qualified MFM formation nor a semantic judge and is never a behavioral result.
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
from cognitive_kernel.projection_contracts import ProjectionVersion, EpisodeRecord
from flora.selected.claims import XTDBClaimAuthority
from flora.selected.context import ContextPlan, StateRoute, assemble_context, record_context_delivery
from flora.selected.judgment_context import RegisteredJudgmentContextPolicy
from flora.selected.experience import KurrentExperienceLog
from flora.selected.formation_context import register_experience_source
from flora.selected.formation_policy import FormationPermissionAction, XTDBFormationPermissionPolicy, formation_permission_payload
from flora.selected.formation_registry import XTDBFormationSourceRegistry
from flora.selected.governed_development import XTDBGovernedPersonalDevelopment
from flora.selected.governed_episodes import (
    EpisodeAcceptanceRequest, XTDBGovernedEpisodes, record_episode_acceptance_request,
)
from flora.selected.object_store import EncryptedObjectPlane, LocalObjectBackend
from flora.selected.owner_authorization import Ed25519OwnerActionVerifier, OwnerActionProof, owner_action_message
from flora.selected.personal_artifact_custody import (
    DurableOwnerProofLookup, DurablePersonalReferences, XTDBPersonalArtifactCustody,
)
from flora.selected.personal_state import activation_request


def _now():
    return normalize_timestamp(datetime.now(timezone.utc).isoformat())


class _SuppliedAdmissionFixture:
    """Externally controlled test receipt allow-list; no learned inference."""
    def __init__(self):
        self.qualified, self.accepted = set(), set()
    def qualified_formation(self, candidate, artifact, reference):
        return (candidate.episode_sha256, artifact.artifact_id, reference) in self.qualified
    def authenticated_adjudication(self, request, candidate, artifact, event):
        return (request.request_sha256, event.event_sha256) in self.accepted


class SelectedGovernedEpisodesTest(unittest.TestCase):
    def test_accepted_episode_and_state_recover_then_current_denial_blocks_private_reads(self):
        scope = ProductHostScope.create(product_id="friday",
            host_instance_id=f"flora-governed-episodes-{uuid.uuid4().hex}", schema_version="1.0.0",
            encryption_domain="fictional-private-custody-key")
        namespace = "fictional-governed-episodes-authority"
        key = Ed25519PrivateKey.generate()
        public_key = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        dsn = os.environ.get("XTDB_DSN", "postgresql://xtdb@127.0.0.1:5432/xtdb")
        uri = os.environ.get("KURRENTDB_URI", "kurrentdb://127.0.0.1:2113?tls=false")
        connection, client = psycopg.connect(dsn, autocommit=True), KurrentDBClient(uri)
        with tempfile.TemporaryDirectory() as directory:
            objects = EncryptedObjectPlane(scope=scope, key=b"z" * 32,
                                           backend=LocalObjectBackend(Path(directory) / "objects"))
            admission = _SuppliedAdmissionFixture()
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
                episodes = XTDBGovernedEpisodes(scope=scope, authority_namespace_id=namespace,
                    connection=connection, registry=registry, policy=policy, custody=custody, verifier=admission)
                state = XTDBGovernedPersonalDevelopment(scope=scope, authority_namespace_id=namespace,
                    connection=connection, registry=registry, policy=policy, episodes=episodes)
                return log, registry, custody, references, verifier, policy, claims, state, episodes
            log, registry, custody, references, verifier, policy, claims, state, episodes = attach()
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
            def version(number, episode, original, previous=None):
                raw, at = objects.put(f"fictional private state {number}".encode()), _now()
                version_id = f"fictional-state-v{number}"
                envelope = MemoryUnitEnvelope.create(scope=scope, record_id=version_id,
                    record_type="projection_version", authority_namespace_id=namespace,
                    host_or_cluster_id=scope.host_instance_id, authority_role="registered_projection",
                    deployment_profile="single_workstation", created_at=at, valid_from=at, valid_to=None,
                    transaction_time=at, logical_clock=number, source_records=(episode.episode_id,),
                    generation=number, state="committed", data_classification="highly_sensitive",
                    retention_class="authoritative_source", deletion_state="active", provenance_digest="a" * 64,
                    content_digest=raw.plaintext_sha256, writer="fictional-candidate-supplier",
                    workflow_or_request_id="fictional-custody", idempotency_namespace=namespace,
                    idempotency_key=version_id, supersedes=() if previous is None else (previous,))
                result = ProjectionVersion.create(envelope=envelope, projection_id=identity["projection_id"],
                    version_id=version_id, projection_type="owner_model", subject_type="owner",
                    subject_id=scope.host_instance_id, modalities=("symbolic",), generation=number,
                    source_episode_ids=(episode.episode_id,), valid_from=at, valid_to=None, produced_at=at,
                    projection_state="candidate", responsible_component="fictional-candidate-supplier",
                    model_id=None, model_version=None, content_digest=raw.plaintext_sha256,
                    supersedes_version_id=previous)
                custody.record(artifact_id=version_id, kind="projection", contract=result.metadata_record(),
                    attachments=(("content", raw),), parent_event_ids=(original.evidence.ref_id,),
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
                observation, raw = event(b"fictional episode original", "observation")
                source = register_experience_source(event_id=observation.event_id, raw=raw,
                    registry=registry, log=log, objects=objects, role="generated_reconstruction", modality="text")
                permission(source)
                summary, content = objects.put(b"fictional supplied episode summary"), objects.put(b"fictional supplied episode narrative")
                at = _now()
                envelope = MemoryUnitEnvelope.create(scope=scope, record_id="fictional-episode-v1",
                    record_type="episode", authority_namespace_id=namespace,
                    host_or_cluster_id=scope.host_instance_id, authority_role="registered_projection",
                    deployment_profile="single_workstation", created_at=at, valid_from=at, valid_to=None,
                    transaction_time=at, logical_clock=1, source_records=(source.evidence.ref_id,),
                    generation=1, state="committed", data_classification="highly_sensitive",
                    retention_class="authoritative_source", deletion_state="active", provenance_digest="a"*64,
                    content_digest=content.plaintext_sha256, writer="fictional-external-mfm-output",
                    workflow_or_request_id="fictional-episode-fixture", idempotency_namespace=namespace,
                    idempotency_key="fictional-episode-v1")
                candidate = EpisodeRecord.create(envelope=envelope, episode_id="fictional-episode-v1",
                    episode_kind="life_event", episode_state="candidate", member_evidence_ids=(source.evidence.ref_id,),
                    participant_ids=(scope.host_instance_id,), mission_node_ids=("fictional-mission",),
                    valid_from=at, valid_to=None, formed_at=at, formation_component_id="external-mfm-fixture",
                    formation_version="fixture-only", summary_content_digest=summary.plaintext_sha256,
                    full_content_digest=content.plaintext_sha256, confidence=None)
                artifact = custody.record(artifact_id="fictional-episode-artifact", kind="episode",
                    contract=candidate.metadata_record(), attachments=(("summary",summary),("content",content)),
                    parent_event_ids=(source.evidence.ref_id,),log=log,objects=objects,
                    occurred_at=_now(),expected_revision=len(log.replay())-1)
                episodes.put_candidate(candidate, thread_id="fictional-life-thread",summary=summary,content=content,**inputs())
                request = EpisodeAcceptanceRequest.create(scope=scope,authority_namespace_id=namespace,
                    request_id="fictional-external-adjudication",thread_id="fictional-life-thread",
                    candidate_episode_id=candidate.episode_id,candidate_episode_sha256=candidate.episode_sha256,
                    candidate_artifact_id=artifact.artifact_id,candidate_artifact_sha256=artifact.record_sha256,
                    formation_receipt_ref="fictional-qualified-formation",adjudication_ref="fictional-independent-semantic-admission",
                    adjudication_policy_sha256="b"*64,expected_previous_episode_id=None,
                    expected_previous_episode_sha256=None,adjudicated_at=_now())
                recorded = record_episode_acceptance_request(request=request,parent_event_ids=candidate.member_evidence_ids,
                    log=log,objects=objects,expected_revision=len(log.replay())-1)
                action_source = register_experience_source(event_id=recorded.event.event_id,raw=recorded.raw,
                    registry=registry,log=log,objects=objects,role="derived_inference",modality="structured")
                permission(action_source)
                admission.qualified.add((candidate.episode_sha256,artifact.artifact_id,request.formation_receipt_ref))
                with self.assertRaisesRegex(ValueError,"independent semantic admission"):
                    episodes.accept(request=request,request_event_id=recorded.event.event_id,**inputs())
                self.assertIsNone(episodes._head("fictional-life-thread"))
                admission.accepted.add((request.request_sha256,recorded.event.event_sha256))
                published = episodes.accept(request=request,request_event_id=recorded.event.event_id,**inputs())
                accepted = episodes.read_accepted(candidate.episode_id,**inputs())
                self.assertEqual(accepted.record["episode_state"],"accepted")
                self.assertEqual(accepted.record["mission_node_ids"],["fictional-mission"])
                first,state_raw = version(1,candidate,source)
                state.put_candidate(first,content=state_raw,**inputs())
                activate(first)
                connection.close()
                client.close()
                connection,client = psycopg.connect(dsn,autocommit=True),KurrentDBClient(uri)
                objects = EncryptedObjectPlane(scope=scope,key=b"z"*32,
                    backend=LocalObjectBackend(Path(directory)/"objects"))
                log,registry,custody,references,verifier,policy,claims,state,episodes = attach()
                recovered = episodes.read_accepted(candidate.episode_id,**inputs())
                self.assertEqual(recovered.publication,published)
                self.assertEqual(recovered.content,b"fictional supplied episode narrative")
                active = state.read_active(**identity,verifier=verifier,**inputs())
                self.assertEqual(active.record["source_episode_ids"],[candidate.episode_id])
                self.assertEqual(active.content,b"fictional private state 1")
                judgment_policy=RegisteredJudgmentContextPolicy(claims=claims,state=state,log=log,
                    registry=registry,permissions=policy)
                plan=ContextPlan(request_id="fictional-accepted-episode-context",purpose="personal_judgment",
                    state_routes=(StateRoute(**identity),),minimum_claims=0)
                context=assemble_context(plan=plan,state=state,policy=judgment_policy,
                    approval_verifier=verifier,**inputs())
                item=context.items[0]
                self.assertIn(recorded.event.event_id,item.control_event_ids)
                self.assertNotIn(recorded.event.event_id,item.source_event_ids)
                self.assertIn(source.evidence.ref_id,item.source_event_ids)
                self.assertTrue({source.evidence.ref_id,recorded.event.event_id,active.approval_event_id}.issubset(
                    context.source_event_ids))
                delivery=record_context_delivery(context=context,state=state,policy=judgment_policy,
                    approval_verifier=verifier,occurred_at=_now(),expected_revision=len(log.replay())-1,**inputs())
                self.assertIn(recorded.event.event_id,delivery.event.parent_event_ids)
                self.assertEqual(context.receipt_record()["schema"],"flora-context-delivery-v2")
                permission(registry.lookup(source.evidence.ref_id),"revoke")
                opened,original_get = [],objects.get
                objects.get = lambda ref:(opened.append(ref.object_id),original_get(ref))[1]
                with self.assertRaisesRegex(ValueError,"request authority|source use"):
                    episodes.read_accepted(candidate.episode_id,**inputs())
                self.assertEqual(opened,[])
                with self.assertRaisesRegex(ValueError,"request authority|source use"):
                    state.read_active(**identity,verifier=verifier,**inputs())
                self.assertEqual(opened,[])
                with self.assertRaisesRegex(PermissionError,"personal state is not permitted"):
                    assemble_context(plan=plan,state=state,policy=judgment_policy,
                        approval_verifier=verifier,**inputs())
                self.assertEqual(opened,[])
            finally:
                connection.close()
                client.close()


if __name__ == "__main__":
    unittest.main()
