"""Adapter contract checks using explicit doubles, not engine qualification.

The source gate and encrypted raw objects are real components. Authority/replay
and retrieved hit doubles isolate the routing boundary; real selected-backend
coverage belongs in the integration suite.
"""

from dataclasses import replace
import tempfile
from types import SimpleNamespace
import unittest

from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from cognitive_kernel.formation_contracts import FormationEvidenceRef
from cognitive_kernel.formation_context_planner import (
    FormationPlanningRequest, assemble_formation_context,
)
from cognitive_kernel.formation_retrieval import FormationRoute, gather_formation_candidates
from flora.selected.formation_recollection import (
    ExactClaimFormationPlane, LadybugFormationPlane, QdrantFormationPlane,
    RegisteredFormationQuery,
)
from flora.selected.graph_recollection import GraphCandidate
from flora.selected.object_store import EncryptedObjectPlane, LocalObjectBackend
from flora.selected.vector_recollection import VectorCandidate


class _Authority:
    def __init__(self, scope, event_ids):
        self.scope = scope
        self.authority_namespace_id = "synthetic-claims"
        self.event_ids = event_ids
        self.deletion = "active"
        self.validity = "current"

    def load_current(self, claim_id, **kwargs):
        if claim_id not in {"claim-one", "claim-two"}:
            raise KeyError(claim_id)
        suffix = claim_id.split("-")[-1]
        return {
            "claim_id": claim_id, "current_claim_version_id": f"version-{suffix}",
            "projection_id": f"projection-{suffix}", "validity_state": self.validity,
            "deletion_state": self.deletion, "conflict_state": "none",
            "adjudication_state": "accepted",
        }

    def load_version(self, version_id):
        suffix = version_id.split("-")[-1]
        if suffix not in self.event_ids:
            raise KeyError(version_id)
        return {
            "claim_id": f"claim-{suffix}", "claim_version_id": version_id,
            "adjudication_state": "accepted",
            "evidence_relation_ids": [f"relation-{suffix}"],
            "envelope": {"source_records": [self.event_ids[suffix]]},
        }

    def load_evidence_relation(self, relation_id):
        suffix = relation_id.split("-")[-1]
        return {
            "evidence_record_id": self.event_ids[suffix],
            "target_record_id": f"version-{suffix}",
            "target_record_type": "claim_version",
        }


class _Log:
    def __init__(self, scope, events):
        self.scope, self.events = scope, events

    def replay(self):
        return self.events


class _Vector:
    def __init__(self, scope, candidates):
        self.scope, self.candidates = scope, candidates
        self.queries = []

    def query_current(self, **kwargs):
        self.queries.append(kwargs)
        return self.candidates


class _Graph:
    def __init__(self, scope, candidates):
        self.scope, self.candidates = scope, candidates
        self.queries = []

    def related_current_metadata(self, **kwargs):
        self.queries.append(kwargs)
        return self.candidates


class _SourceStore:
    def __init__(self, scope, namespace, sources):
        self.sources = sources
        self.refs = {
            ref_id: FormationEvidenceRef(
                ref_id=ref_id, scope=scope, authority_namespace_id=namespace,
                content_digest=raw.plaintext_sha256,
                role="historical_experience", modality="text")
            for ref_id, (raw, _) in sources.items()
        }

    def resolve(self, ref_id):
        return self.refs.get(ref_id)

    def read(self, ref):
        return self.sources[ref.ref_id][1]

    def permits_formation(self, ref):
        return ref.ref_id in self.refs


class SelectedFormationRecollectionTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.scope = ProductHostScope.create(
            product_id="friday", host_instance_id="synthetic-formation-retrieval",
            schema_version="1.0.0", encryption_domain="synthetic-formation-key")
        self.objects = EncryptedObjectPlane(
            scope=self.scope, key=b"a" * 32,
            backend=LocalObjectBackend(self.directory.name))
        self.events, self.references, self.sources, event_ids = [], {}, {}, {}
        for suffix in ("one", "two"):
            content = f"synthetic registered source {suffix}".encode()
            raw = self.objects.put(content)
            event = ExperienceEvent.create(
                event_type="observation", scope=self.scope,
                occurred_at="2026-09-10T00:00:00Z", content_digest=raw.plaintext_sha256,
                provenance=ProvenanceReference.create(
                    provenance_type="derived_inference", source_reference_ids=(raw.object_id,),
                    derivation_activity_id=f"synthetic-{suffix}",
                    responsible_component="synthetic-retrieval-test"),
                retention_class="ordinary_experience", storage_tier="raw_buffer",
                payload_reference=raw.object_id)
            self.events.append(event)
            self.references[raw.object_id] = raw
            self.sources[event.event_id] = (raw, content)
            event_ids[suffix] = event.event_id
        self.authority = _Authority(self.scope, event_ids)
        self.log = _Log(self.scope, self.events)
        self.query = RegisteredFormationQuery(
            scope=self.scope, authority_namespace_id=self.authority.authority_namespace_id,
            query_ref="registered-query", claim_ids=("claim-one", "claim-two"),
            query_vector=(1.0, 0.0), graph_source_event_ids=(event_ids["one"],), limit=3)
        self.resolver = lambda query_ref: self.query if query_ref == "registered-query" else None
        self.vector = _Vector(self.scope, (VectorCandidate(
            "claim-two", "version-two", "projection-two", (event_ids["two"],), 0.5),))
        self.graph = _Graph(self.scope, tuple(GraphCandidate(
            f"claim-{suffix}", f"version-{suffix}", f"projection-{suffix}",
            (f"relation-{suffix}",), (event_ids[suffix],)) for suffix in ("one", "two")))
        self.kwargs = {
            "authority": self.authority, "log": self.log, "objects": self.objects,
            "references": self.references, "query_resolver": self.resolver,
        }

    def planes(self):
        return {
            "exact_claim": ExactClaimFormationPlane(**self.kwargs),
            "qdrant": QdrantFormationPlane(vector=self.vector, **self.kwargs),
            "ladybug": LadybugFormationPlane(graph=self.graph, **self.kwargs),
        }

    def test_every_formation_route_nominates_without_opening_originals(self):
        def forbidden_get(reference):
            raise AssertionError("retrieval opened originals before registered custody")
        self.objects.get = forbidden_get
        for name, plane in self.planes().items():
            with self.subTest(plane=name):
                self.assertTrue(plane.source_ids(self.query.query_ref))

    def test_upstream_routes_keep_original_source_ids_and_plane_provenance(self):
        planes = self.planes()
        request = FormationPlanningRequest(
            scope=self.scope, authority_namespace_id=self.authority.authority_namespace_id,
            experience_refs=(self.events[0].event_id,))
        gathered = gather_formation_candidates(
            request=request, routes=tuple(FormationRoute(plane, "registered-query")
                                          for plane in planes), providers=planes)
        self.assertEqual(
            tuple(hit.ref_id for hit in gathered.candidates),
            (self.events[0].event_id, self.events[1].event_id, self.events[1].event_id,
             self.events[0].event_id, self.events[1].event_id))
        assembled = assemble_formation_context(
            gathered, _SourceStore(self.scope, self.authority.authority_namespace_id,
                                   self.sources))
        self.assertEqual(assembled.selected_planes, (
            (self.events[0].event_id, ("exact_claim", "ladybug")),
            (self.events[1].event_id, ("exact_claim", "qdrant", "ladybug")),
        ))
        self.assertEqual(tuple(ref.ref_id for ref in assembled.packet.evidence),
                         tuple(event.event_id for event in self.events))
        self.assertEqual(self.vector.queries[0]["query_vector"], (1.0, 0.0))
        self.assertEqual(self.vector.queries[0]["limit"], 3)
        self.assertEqual(self.graph.queries[0]["source_event_id"], self.events[0].event_id)

    def test_unregistered_or_foreign_query_cannot_select_sources_or_vectors(self):
        for plane in self.planes().values():
            with self.subTest(plane=type(plane).__name__):
                with self.assertRaisesRegex(ValueError, "independently registered"):
                    plane.source_ids(self.events[0].event_id)
        for changes in (
            {"authority_namespace_id": "foreign-claims"},
            {"query_ref": "different-query"},
            {"scope": replace(self.scope, host_instance_id="foreign-host")},
        ):
            with self.subTest(changes=changes):
                original = self.query
                self.query = replace(original, **changes)
                with self.assertRaisesRegex(ValueError, "registered scope or namespace"):
                    ExactClaimFormationPlane(**self.kwargs).source_ids("registered-query")
                self.query = original
        self.assertEqual(self.vector.queries, [])

    def test_stale_or_forged_derived_hits_grant_no_original_sources(self):
        self.vector.candidates = (replace(self.vector.candidates[0],
                                          source_event_ids=("fabricated-event",)),)
        self.assertEqual(self.planes()["qdrant"].source_ids("registered-query"), ())
        self.graph.candidates = (replace(self.graph.candidates[0],
                                         claim_version_id="obsolete-version"),)
        self.assertEqual(self.planes()["ladybug"].source_ids("registered-query"), ())
        self.authority.deletion = "pending"
        with self.assertRaisesRegex(ValueError, "active, resolved"):
            self.planes()["exact_claim"].source_ids("registered-query")
        self.vector.candidates = (VectorCandidate(
            "claim-two", "version-two", "projection-two",
            (self.events[1].event_id,), 0.5),)
        self.assertEqual(self.planes()["qdrant"].source_ids("registered-query"), ())

    def test_query_contract_and_graph_seed_are_independently_checked(self):
        for vector in ((True, 0.0), (float("nan"), 0.0), (float("inf"), 0.0), ()):
            with self.subTest(vector=vector):
                self.query = replace(self.query, query_vector=vector)
                with self.assertRaisesRegex(ValueError, "finite tuple"):
                    self.planes()["qdrant"].source_ids("registered-query")
        self.query = replace(self.query, query_vector=(1.0, 0.0),
                             graph_source_event_ids=("not-replayed",))
        with self.assertRaisesRegex(ValueError, "absent from this host Experience"):
            self.planes()["ladybug"].source_ids("registered-query")
        self.assertEqual(self.graph.queries, [])
        foreign = SimpleNamespace(scope=replace(self.scope, host_instance_id="foreign-host"))
        with self.assertRaisesRegex(ValueError, "vector projection crosses host"):
            QdrantFormationPlane(vector=foreign, **self.kwargs)


if __name__ == "__main__":
    unittest.main()
