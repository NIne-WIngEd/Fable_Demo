"""Deterministic source-use gate checks; these are not backend qualification.

The authority and event replay doubles model already verified records. These
tests cover validity and present quarantine policy independently of services;
they do not establish XTDB, KurrentDB, or Qdrant integration behavior.
"""

from copy import deepcopy
from datetime import datetime, timezone
import tempfile
from types import SimpleNamespace
import unittest

from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from flora.selected.object_store import EncryptedObjectPlane, LocalObjectBackend
from flora.selected.source_native import read_current_source_manifest, read_current_sources
from flora.selected.vector_recollection import QdrantClaimProjection


class _Authority:
    def __init__(self, scope, event_id):
        self.scope = scope
        self.scope_digest = "a" * 64
        self.present = {
            "claim_id": "claim-one", "current_claim_version_id": "version-one",
            "projection_id": "projection-one", "validity_state": "current",
            "deletion_state": "active", "conflict_state": "none",
            "adjudication_state": "accepted",
        }
        self.historical = deepcopy(self.present)
        self.version = {
            "claim_id": "claim-one", "claim_version_id": "version-one",
            "adjudication_state": "accepted", "evidence_relation_ids": ["relation-one"],
            "envelope": {"source_records": [event_id]},
        }
        self.relation = {
            "evidence_record_id": event_id, "target_record_id": "version-one",
            "target_record_type": "claim_version",
        }

    def load_current(self, claim_id, *, as_of=None):
        if claim_id != "claim-one":
            raise KeyError(claim_id)
        return deepcopy(self.present if as_of is None else self.historical)

    def load_version(self, version_id):
        if version_id != "version-one":
            raise KeyError(version_id)
        return deepcopy(self.version)

    def load_evidence_relation(self, relation_id):
        if relation_id != "relation-one":
            raise KeyError(relation_id)
        return deepcopy(self.relation)


class _Log:
    def __init__(self, scope, event):
        self.scope, self.event = scope, event
        self.replays = 0
        self.before_replay = None

    def replay(self):
        self.replays += 1
        if self.before_replay is not None:
            self.before_replay()
        return [self.event]


class _VectorQuery:
    """An injected point response, not a Qdrant service."""

    def __init__(self, point):
        self.point = point

    def query_points(self, **kwargs):
        return SimpleNamespace(points=[self.point])


class SelectedSourceNativeTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.scope = ProductHostScope.create(
            product_id="friday", host_instance_id="synthetic-source-gate",
            schema_version="1.0.0", encryption_domain="synthetic-source-key")
        self.objects = EncryptedObjectPlane(
            scope=self.scope, key=b"a" * 32,
            backend=LocalObjectBackend(self.directory.name))
        self.raw = self.objects.put(b"synthetic source evidence")
        self.event = ExperienceEvent.create(
            event_type="observation", scope=self.scope,
            occurred_at="2026-09-10T00:00:00Z",
            content_digest=self.raw.plaintext_sha256,
            provenance=ProvenanceReference.create(
                provenance_type="derived_inference",
                source_reference_ids=(self.raw.object_id,),
                derivation_activity_id="synthetic-ingest",
                responsible_component="synthetic-source-test"),
            retention_class="ordinary_experience", storage_tier="raw_buffer",
            payload_reference=self.raw.object_id)
        self.authority = _Authority(self.scope, self.event.event_id)
        self.log = _Log(self.scope, self.event)
        self.as_of = datetime(2026, 9, 10, tzinfo=timezone.utc)

    def read(self, **kwargs):
        return read_current_sources(
            claim_id="claim-one", authority=self.authority,
            log=self.log, objects=self.objects,
            references={self.raw.object_id: self.raw}, **kwargs)

    def test_current_use_excludes_every_noncurrent_validity(self):
        for state in ("historical", "future", "expired", "unknown"):
            with self.subTest(validity=state):
                self.authority.present["validity_state"] = state
                with self.assertRaisesRegex(ValueError, "validity"):
                    self.read()
        self.assertEqual(self.log.replays, 0)
        self.authority.present["validity_state"] = "current"
        self.assertEqual(self.read().sources[0].plaintext,
                         b"synthetic source evidence")

    def test_valid_time_history_cannot_bypass_present_quarantine(self):
        for state in ("pending", "deleted", "cryptographically_erased",
                      "technically_limited"):
            with self.subTest(deletion=state):
                self.authority.present["deletion_state"] = state
                with self.assertRaisesRegex(ValueError, "active, resolved"):
                    self.read(as_of=self.as_of)
        self.assertEqual(self.log.replays, 0)

    def test_explicit_history_requires_usable_snapshot_and_present_permission(self):
        self.authority.present["validity_state"] = "expired"
        self.authority.historical["validity_state"] = "historical"
        self.assertEqual(self.read(as_of=self.as_of).claim_version_id, "version-one")
        for state in ("future", "expired", "unknown"):
            with self.subTest(validity=state):
                self.authority.historical["validity_state"] = state
                with self.assertRaisesRegex(ValueError, "validity"):
                    self.read(as_of=self.as_of)
        self.authority.historical["validity_state"] = "current"
        self.authority.present["conflict_state"] = "open"
        with self.assertRaisesRegex(ValueError, "active, resolved"):
            self.read(as_of=self.as_of)
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            self.read(as_of=datetime(2026, 9, 10))

    def test_intervening_quarantine_or_head_change_rejects_materialized_sources(self):
        self.log.before_replay = lambda: self.authority.present.update(
            deletion_state="pending")
        with self.assertRaisesRegex(ValueError, "active, resolved"):
            self.read(as_of=self.as_of)
        self.authority.present["deletion_state"] = "active"
        self.log.before_replay = lambda: self.authority.present.update(
            projection_id="projection-revised")
        with self.assertRaisesRegex(ValueError, "head changed"):
            self.read()

    def test_vector_candidates_require_current_validity(self):
        projection = QdrantClaimProjection(
            scope=self.scope, client=None,
            embedding_artifact_sha256="e" * 64, dimension=2)
        projection.client = _VectorQuery(SimpleNamespace(
            id=projection._point_id("version-one"), score=0.99,
            payload={
                "claim_id": "claim-one", "claim_version_id": "version-one",
                "projection_id": "projection-one",
                "source_event_ids": [self.event.event_id],
                "authority_scope_digest": self.authority.scope_digest,
                "embedding_artifact_sha256": "e" * 64,
            }))
        self.assertEqual(len(projection.query_current(
            query_vector=(1.0, 0.0), authority=self.authority)), 1)
        for state in ("historical", "future", "expired", "unknown"):
            with self.subTest(validity=state):
                self.authority.present["validity_state"] = state
                self.assertEqual(projection.query_current(
                    query_vector=(1.0, 0.0), authority=self.authority), ())

    def test_denial_precedes_raw_io_and_revocation_during_read_fails(self):
        actual_get = self.objects.get
        reads = []
        allowed = [False]

        def get(reference):
            reads.append(reference.object_id)
            content = actual_get(reference)
            allowed[0] = False
            return content

        self.objects.get = get
        with self.assertRaisesRegex(PermissionError, "before raw read"):
            self.read(source_authorizer=lambda event_id: allowed[0])
        self.assertEqual(reads, [])
        allowed[0] = True
        with self.assertRaisesRegex(PermissionError, "during raw read"):
            self.read(source_authorizer=lambda event_id: allowed[0])
        self.assertEqual(reads, [self.raw.object_id])

    def test_metadata_nomination_never_opens_raw_content(self):
        def forbidden_get(reference):
            raise AssertionError("metadata nomination accessed plaintext")
        self.objects.get = forbidden_get
        manifest = read_current_source_manifest(
            claim_id="claim-one", authority=self.authority, log=self.log)
        self.assertEqual(manifest.sources[0].event_id, self.event.event_id)
        self.assertFalse(hasattr(manifest.sources[0], "plaintext"))
        self.authority.present["deletion_state"] = "pending"
        with self.assertRaisesRegex(ValueError, "active, resolved"):
            read_current_source_manifest(
                claim_id="claim-one", authority=self.authority, log=self.log)


if __name__ == "__main__":
    unittest.main()
