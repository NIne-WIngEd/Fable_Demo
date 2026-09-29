"""Real selected-fabric admission, correction and rollback boundaries.

All proposed meanings and semantic adjudications are supplied fictional fixtures.
This qualifies no MFM/personality model and reports no behavioral improvement.
XTDB/Kurrent, source permission/custody, Qdrant and Ladybug paths are actual.
"""

from datetime import datetime, timedelta, timezone
import base64
import os
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from kurrentdbclient import KurrentDBClient
import ladybug
import psycopg
from qdrant_client import QdrantClient

from cognitive_kernel.canonical import normalize_timestamp
from cognitive_kernel.claim_contracts import CanonicalTaggedValue
from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from cognitive_kernel.formation_context_planner import FormationPlanningRequest
from cognitive_kernel.formation_contracts import FormationProposal, MemoryProposalBundle
from flora.selected.claims import XTDBClaimAuthority
from flora.selected.experience import KurrentExperienceLog
from flora.selected.formation_admission import XTDBFormationClaimAdmission
from flora.selected.formation_candidates import XTDBFormationProposalCandidates
from flora.selected.formation_context import (
    prepare_selected_formation, record_selected_formation_delivery, register_experience_source,
)
from flora.selected.formation_policy import (
    FormationPermissionAction, XTDBFormationPermissionPolicy, formation_permission_payload,
)
from flora.selected.formation_registry import XTDBFormationSourceRegistry
from flora.selected.graph_recollection import LadybugEvidenceGraph
from flora.selected.object_store import EncryptedObjectPlane, LocalObjectBackend
from flora.selected.owner_authorization import (
    Ed25519OwnerActionVerifier, OwnerActionProof, owner_action_message,
)
from flora.selected.source_native import read_current_sources
from flora.selected.revocation import quarantine_claim
from flora.selected.vector_recollection import QdrantClaimProjection

_TESTS = str(Path(__file__).resolve().parents[1])
if _TESTS not in sys.path:
    sys.path.insert(0, _TESTS)
from test_selected_formation_admission import (
    FixtureSemanticAdapter, FixtureSemanticVerifier, fixture_adjudication,
    fixture_conflict, fixture_projection,
)


class _Values:
    def __init__(self, scope, namespace, values):
        self.scope, self.namespace, self.values = scope, namespace, values

    def resolve(self, scope, authority_namespace_id, value_ref):
        return self.values.get(value_ref) if (scope, authority_namespace_id) == (
            self.scope, self.namespace) else None


class _FailVersionInsertOnce:
    """Inject an application failure inside an actual XTDB transaction."""

    def __init__(self, connection):
        self.connection, self.failed = connection, False

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, sql, parameters):
        if not self.failed and sql.startswith("INSERT INTO fable_claim_versions"):
            self.failed = True
            raise RuntimeError("injected before version insert in real XTDB transaction")
        return self.connection.execute(sql, parameters)


class FormationAdmissionIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        suffix = uuid.uuid4().hex[:14]
        self.scope = ProductHostScope.create(
            product_id="friday", host_instance_id=f"fictional-admission-{suffix}",
            schema_version="1.0.0", encryption_domain=f"integration-admission-{suffix}")
        self.namespace = f"flora-experiment-admission-{suffix}"
        self.connection = psycopg.connect(os.environ.get(
            "XTDB_DSN", "postgresql://xtdb@127.0.0.1:5432/xtdb"), autocommit=True)
        self.addCleanup(self.connection.close)
        self.client = KurrentDBClient(os.environ.get(
            "KURRENTDB_URI", "kurrentdb://127.0.0.1:2113?tls=false"))
        self.addCleanup(self.client.close)
        self.log = KurrentExperienceLog(scope=self.scope, client=self.client)
        self.objects = EncryptedObjectPlane(scope=self.scope, key=b"f" * 32,
            backend=LocalObjectBackend(Path(self.directory.name) / "objects"))
        self.registry = XTDBFormationSourceRegistry(scope=self.scope,
            authority_namespace_id=self.namespace, connection=self.connection)
        self.policy = XTDBFormationPermissionPolicy(scope=self.scope,
            authority_namespace_id=self.namespace, connection=self.connection, registry=self.registry)
        self.candidates = XTDBFormationProposalCandidates(scope=self.scope,
            authority_namespace_id=self.namespace, connection=self.connection)
        self.authority = XTDBClaimAuthority(scope=self.scope,
            authority_namespace_id=self.namespace, connection=self.connection)
        self.gateway = XTDBFormationClaimAdmission(authority=self.authority,
            candidates=self.candidates, experiment_world_id="fictional-world")
        self.semantic_proof = FixtureSemanticVerifier(self.scope, self.namespace)
        self.signer = Ed25519PrivateKey.generate()
        self.owner_proofs = {}
        self.owner_verifier = Ed25519OwnerActionVerifier(scope=self.scope,
            owner_public_key=self.signer.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw),
            proofs=self.owner_proofs)
        self.raw_refs, self.grants = {}, {}
        self.clock = 0
        self.artifact = "a" * 64  # Declared fixture artifact, not model qualification.

    def _time(self):
        self.clock += 1
        return normalize_timestamp((datetime(2026, 9, 29, 12, tzinfo=timezone.utc)
                                    + timedelta(minutes=self.clock)).isoformat())

    def _append(self, payload, *, event_type, parents=(), at=None, provenance="generated_reconstruction"):
        raw = self.objects.put(payload)
        self.raw_refs[raw.object_id] = raw
        event = ExperienceEvent.create(event_type=event_type, scope=self.scope,
            occurred_at=at or self._time(), content_digest=raw.plaintext_sha256,
            provenance=ProvenanceReference.create(provenance_type=provenance,
                source_reference_ids=(raw.object_id,), derivation_activity_id="fictional-admission-fixture",
                responsible_component="fictional-ingress"),
            retention_class="ordinary_experience", storage_tier="raw_buffer",
            payload_reference=raw.object_id, parent_event_ids=parents)
        self.log.append(event, expected_revision=len(self.log.replay()) - 1)
        return event, raw

    def _source(self, payload, *, correction_parent=None):
        event, raw = self._append(payload, event_type="observation" if correction_parent is None else "correction",
            parents=() if correction_parent is None else (correction_parent,))
        source = register_experience_source(event_id=event.event_id, raw=raw, registry=self.registry,
            log=self.log, objects=self.objects, role="generated_reconstruction", modality="text",
            subject_ref=self.scope.host_instance_id, source_item_ref=raw.object_id)
        self._permission(source, "allow")
        return event

    def _permission(self, source, decision):
        prior = self.grants.get(source.evidence.ref_id)
        action = FormationPermissionAction.create(scope=self.scope, authority_namespace_id=self.namespace,
            action_id=f"permission-{self.clock}-{decision}", source_ref_id=source.evidence.ref_id,
            source_registration_sha256=source.registration_sha256, purpose="memory_formation",
            decision=decision, generation=1 if prior is None else prior[0].generation + 1,
            previous_action_sha256=None if prior is None else prior[0].action_sha256,
            authorization_ref=f"owner-proof-{self.clock}-{decision}", authorized_at=self._time())
        parents = (source.evidence.ref_id,) + (() if prior is None else (prior[1].event_id,))
        event, _ = self._append(formation_permission_payload(action),
            event_type="formation_permission_action", parents=parents, at=action.authorized_at,
            provenance="owner_attested_canonical")
        self.owner_proofs[event.event_id] = OwnerActionProof("formation_permission", event.event_id,
            event.event_sha256, base64.b64encode(self.signer.sign(owner_action_message(
                event, "formation_permission"))).decode())
        self.policy.apply(action, request_event_id=event.event_id, log=self.log, objects=self.objects,
                          references=self.raw_refs, verifier=self.owner_verifier)
        self.grants[source.evidence.ref_id] = (action, event)

    def _bundle(self, source, *, prefix, correction_of=None):
        prepared = prepare_selected_formation(request=FormationPlanningRequest(scope=self.scope,
            authority_namespace_id=self.namespace, experience_refs=(source.event_id,)),
            registry=self.registry, objects=self.objects, permits=self.policy.permits)
        delivery = record_selected_formation_delivery(prepared=prepared, log=self.log, objects=self.objects,
            occurred_at=self._time(), expected_revision=len(self.log.replay()) - 1,
            request_id=f"{prefix}-formation")
        packet = prepared.assembled.packet
        values = {"value-one": CanonicalTaggedValue.create(type_tag="text", value="fictional value one"),
                  "value-two": CanonicalTaggedValue.create(type_tag="text", value="fictional value two")}
        proposal_ids = (f"{prefix}-one",) if correction_of is not None else (f"{prefix}-one", f"{prefix}-two")
        bundle = MemoryProposalBundle(scope=self.scope, authority_namespace_id=self.namespace,
            bundle_id=f"{prefix}-bundle", experience_refs=packet.experience_refs,
            context_digest=packet.content_digest(), model_artifact_digest=self.artifact,
            inference_run_id=f"{prefix}-inference", proposals=tuple(FormationProposal(
                proposal_id=proposal_id, kind="correction_request" if correction_of else "preference",
                domain="host", subject_ref=self.scope.host_instance_id,
                value_ref="value-two" if correction_of or proposal_id.endswith("two") else "value-one",
                evidence_refs=(source.event_id,), epistemic_status="reconstruction",
                valid_from=source.occurred_at if correction_of else None,
                contradicts=() if correction_of is None else (correction_of,),
            ) for proposal_id in proposal_ids))
        self.candidates.record(prepared=prepared, delivery=delivery, bundle=bundle, log=self.log,
            objects=self.objects, expected_model_artifact_sha256=self.artifact, occurred_at=self._time(),
            expected_revision=len(self.log.replay()) - 1,
            value_resolver=_Values(self.scope, self.namespace, values))
        return bundle, prepared.store

    def _prepare(self, bundle, store, *, proposal_number="one", identity=None, claim_id="fictional-claim-one"):
        at = self._time()
        bound = self.gateway.prepare(bundle_id=bundle.bundle_id,
            proposal_id=bundle.proposals[0].proposal_id if proposal_number == "one" else bundle.proposals[1].proposal_id,
            adapter=FixtureSemanticAdapter(identity=identity, claim_id=claim_id, at=at),
            log=self.log, objects=self.objects, source_store=store)
        return bound, at

    def _admit(self, bound, adjudication, store, **kwargs):
        return self.gateway.admit(bound, adjudication=adjudication, verifier=self.semantic_proof,
            log=self.log, objects=self.objects, source_store=store, **kwargs)

    def test_real_atomic_authority_correction_idempotency_and_source_revocation(self):
        original = self._source(b"fictional original preference evidence")
        bundle, store = self._bundle(original, prefix="original")
        first, at = self._prepare(bundle, store)
        adjudication = fixture_adjudication(first, at=at)
        with self.assertRaisesRegex(ValueError, "independently authenticated"):
            self._admit(first, adjudication, store)
        self.semantic_proof.approve_fixture(adjudication, first)
        # Rollback covers earlier candidate/decision/identity/relation inserts
        # and leaves the counter, head, property slot and receipt uncommitted.
        self.authority.connection = _FailVersionInsertOnce(self.connection)
        with self.assertRaisesRegex(RuntimeError, "real XTDB transaction"):
            self._admit(first, adjudication, store)
        self.authority.connection = self.connection
        with self.assertRaises(KeyError):
            self.authority.load_current("fictional-claim-one")
        self.assertIsNone(self.gateway._row("fable_claim_identities", "fictional-claim-one"))
        self.assertIsNone(self.gateway._row("flora_admitted_claim_candidates", first.interpretation.candidate.candidate_id))
        self.assertIsNone(self.gateway._row("flora_claim_admission_namespace_counters", "admission-namespace-counter"))
        receipt = self._admit(first, adjudication, store)
        self.assertEqual((receipt.store_sequence, receipt.version_sequence, receipt.event_stream_position), (1, 1, 0))
        self.assertEqual(self._admit(first, adjudication, store), receipt)
        current = self.authority.load_current(receipt.claim_id)
        self.assertEqual(current["source_position"], 1)
        self.assertEqual(read_current_sources(claim_id=receipt.claim_id, authority=self.authority,
            log=self.log, objects=self.objects, references=self.raw_refs).sources[0].event_id, original.event_id)
        competing, competing_at = self._prepare(bundle, store, proposal_number="two", claim_id="competing-claim")
        competing_decision = fixture_adjudication(competing, at=competing_at)
        self.semantic_proof.approve_fixture(competing_decision, competing)
        with self.assertRaisesRegex(ValueError, "semantic property already"):
            self._admit(competing, competing_decision, store)

        qdrant = QdrantClient(url=os.environ.get("QDRANT_URL", "http://127.0.0.1:6333"))
        self.addCleanup(qdrant.close)
        vectors = QdrantClaimProjection(scope=self.scope, client=qdrant,
                                       embedding_artifact_sha256="e" * 64, dimension=2)
        vectors.ensure_collection()
        self.addCleanup(lambda: qdrant.delete_collection(vectors.collection))
        vectors.index_current(claim_id=receipt.claim_id, vector=(1.0, 0.0), authority=self.authority,
            log=self.log, objects=self.objects, references=self.raw_refs)
        graph_database = ladybug.Database(str(Path(self.directory.name) / "graph"))
        graph_connection = ladybug.Connection(graph_database)
        graph = LadybugEvidenceGraph(scope=self.scope, connection=graph_connection)
        graph.ensure_schema()
        graph.project_current(claim_id=receipt.claim_id, authority=self.authority,
                              log=self.log, objects=self.objects, references=self.raw_refs)
        with self.assertRaisesRegex(ValueError, "governed namespace"):
            self.authority.put_identity(first.interpretation.candidate.identity)
        with self.assertRaisesRegex(ValueError, "governed namespace"):
            quarantine_claim(prior=fixture_projection(current), request_event_id="unused-legacy-request",
                authority=self.authority, log=self.log, objects=self.objects, references=self.raw_refs,
                vector=vectors, verifier=self.owner_verifier)

        correction = self._source(b"fictional explicit correction evidence", correction_parent=original.event_id)
        corrected_bundle, corrected_store = self._bundle(correction, prefix="corrected",
                                                         correction_of=receipt.claim_version_id)
        corrected, corrected_at = self._prepare(corrected_bundle, corrected_store,
                                               identity=first.interpretation.candidate.identity)
        previous = fixture_projection(current)
        corrected_decision = fixture_adjudication(corrected, at=corrected_at,
                                                   conflict_id="fictional-correction-conflict")
        conflict = fixture_conflict(corrected, corrected_decision, previous)
        self.semantic_proof.approve_fixture(corrected_decision, corrected)
        with self.assertRaisesRegex(ValueError, "exact available predecessor"):
            self._admit(corrected, corrected_decision, corrected_store)
        updated = self._admit(corrected, corrected_decision, corrected_store,
                              expected_previous=previous, conflict=conflict)
        self.assertEqual((updated.store_sequence, updated.version_sequence), (2, 2))
        self.assertNotEqual(updated.event_stream_position, updated.store_sequence)
        present = self.authority.load_current(receipt.claim_id)
        self.assertEqual(present["current_claim_version_id"], updated.claim_version_id)
        self.assertEqual(self.authority.load_version(updated.claim_version_id)["correction_of"],
                         [receipt.claim_version_id])
        self.assertEqual(self.authority.load_current(receipt.claim_id,
            as_of=datetime.fromisoformat(at.replace("Z", "+00:00")))["current_claim_version_id"],
            receipt.claim_version_id)
        self.assertEqual(self._admit(first, adjudication, store), receipt)
        self.assertEqual(self.authority.load_current(receipt.claim_id), present)
        self.assertEqual(vectors.query_current(query_vector=(1.0, 0.0), authority=self.authority), ())
        self.assertEqual(graph.related_current(source_event_id=original.event_id, authority=self.authority,
            log=self.log, objects=self.objects, references=self.raw_refs), ())
        vectors.index_current(claim_id=receipt.claim_id, vector=(0.0, 1.0), authority=self.authority,
            log=self.log, objects=self.objects, references=self.raw_refs)
        graph.project_current(claim_id=receipt.claim_id, authority=self.authority,
                              log=self.log, objects=self.objects, references=self.raw_refs)
        self.assertEqual(vectors.query_current(query_vector=(0.0, 1.0),
            authority=self.authority)[0].claim_version_id, updated.claim_version_id)

        self._permission(self.registry.lookup(original.event_id), "revoke")
        recreated_registry = XTDBFormationSourceRegistry(scope=self.scope,
            authority_namespace_id=self.namespace, connection=self.connection)
        recreated_policy = XTDBFormationPermissionPolicy(scope=self.scope,
            authority_namespace_id=self.namespace, connection=self.connection, registry=recreated_registry)
        self.assertFalse(recreated_policy.permits(recreated_registry.lookup(correction.event_id), "memory_formation"))
        with self.assertRaisesRegex(ValueError, "revoked"):
            self._admit(corrected, corrected_decision, corrected_store,
                        expected_previous=previous, conflict=conflict)


if __name__ == "__main__":
    unittest.main()
