from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
import tempfile
from threading import Barrier
import unittest

import psycopg
from kurrentdbclient import KurrentDBClient
from kurrentdbclient.exceptions import WrongCurrentVersionError

from cognitive_kernel.adjudication_contracts import ClaimEvidenceRelation
from cognitive_kernel.claim_contracts import (
    CanonicalTaggedValue,
    ClaimIdentity,
    ClaimVersion,
    CurrentClaimProjection,
)
from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from cognitive_kernel.memory_contracts import MemoryUnitEnvelope
from flora.selected.claims import XTDBClaimAuthority
from flora.selected.authority_binding import bind_claim_source
from flora.selected.experience import KurrentExperienceLog
from flora.selected.formation_input import formation_input_from_replay
from flora.selected.object_store import EncryptedObjectPlane, LocalObjectBackend


PROVENANCE_DIGEST = "a" * 64
CONTENT_DIGEST = "b" * 64


def _event(scope: ProductHostScope, *, suffix: str, occurred_at: str,
           event_type: str = "observation", parent_event_ids: tuple[str, ...] = ()) -> ExperienceEvent:
    payload = f"synthetic-{suffix}".encode()
    return ExperienceEvent.create(
        event_type=event_type,
        scope=scope,
        occurred_at=occurred_at,
        content_digest=hashlib.sha256(payload).hexdigest(),
        provenance=ProvenanceReference.create(
            provenance_type="derived_inference",
            source_reference_ids=(f"raw-{suffix}",),
            derivation_activity_id="backend-integration",
            responsible_component="synthetic-test",
        ),
        retention_class="ordinary_experience",
        storage_tier="raw_buffer",
        payload_reference=f"raw-{suffix}",
        parent_event_ids=parent_event_ids,
    )


def _scope(host: str) -> ProductHostScope:
    return ProductHostScope.create(
        product_id="friday",
        host_instance_id=host,
        schema_version="1.0.0",
        encryption_domain=f"integration-{host}",
    )


def _envelope(
    *,
    scope: ProductHostScope,
    authority_namespace_id: str,
    record_id: str,
    record_type: str,
    authority_role: str,
    created_at: str,
    source_records: tuple[str, ...] = (),
    supersedes: tuple[str, ...] = (),
    logical_clock: int = 1,
) -> MemoryUnitEnvelope:
    return MemoryUnitEnvelope.create(
        scope=scope,
        record_id=record_id,
        record_type=record_type,
        authority_namespace_id=authority_namespace_id,
        host_or_cluster_id=scope.host_instance_id,
        authority_role=authority_role,
        deployment_profile="single_workstation",
        created_at=created_at,
        valid_from=created_at,
        valid_to=None,
        transaction_time=created_at,
        logical_clock=logical_clock,
        causal_parents=(),
        source_records=source_records,
        generation=0,
        state="committed",
        data_classification="highly_sensitive",
        retention_class="authoritative_source",
        deletion_state="active",
        provenance_digest=PROVENANCE_DIGEST,
        content_digest=CONTENT_DIGEST,
        writer="claim_authority",
        workflow_or_request_id="integration-request",
        idempotency_namespace="claim_authority",
        idempotency_key=record_id,
        supersedes=supersedes,
    )


def _text(value: str) -> CanonicalTaggedValue:
    return CanonicalTaggedValue.create(type_tag="text", value=value)


class SelectedBackendIntegrationTest(unittest.TestCase):
    def test_xtdb_immutable_relation_race_has_one_winner(self):
        scope = _scope("flora-relation-race")
        namespace = "race-claims"
        relation_id = "relation-race-one"
        dsn = os.environ.get("XTDB_DSN", "postgresql://xtdb@127.0.0.1:5432/xtdb")
        barrier = Barrier(2)

        def contender(source: str) -> str:
            relation = ClaimEvidenceRelation.create(
                envelope=_envelope(
                    scope=scope, authority_namespace_id=namespace,
                    record_id=relation_id, record_type="claim_evidence_relation",
                    authority_role="claim_authority",
                    created_at="2026-09-01T00:00:00Z",
                    source_records=(source, "claim-race-v1"),
                ),
                relation_id=relation_id, evidence_record_id=source,
                target_record_id="claim-race-v1", target_record_type="claim_version",
                relation_type="support", source_class="experience",
                source_authority_class="historical_experience",
                extractor_component_id="flora-integration", extractor_version="v1",
                confidence=0.5,
            )
            try:
                with psycopg.connect(dsn, autocommit=True) as connection:
                    authority = XTDBClaimAuthority(scope=scope,
                        authority_namespace_id=namespace, connection=connection)
                    barrier.wait(timeout=20)
                    authority.put_evidence_relation(relation)
                return "accepted"
            except (ValueError, psycopg.Error):
                return "rejected"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(contender, ("evidence-left", "evidence-right")))
        self.assertEqual(sorted(results), ["accepted", "rejected"])
        with psycopg.connect(dsn, autocommit=True) as connection:
            authority = XTDBClaimAuthority(scope=scope,
                authority_namespace_id=namespace, connection=connection)
            stored = authority.load_evidence_relation(relation_id)
            self.assertIn(stored["evidence_record_id"], ("evidence-left", "evidence-right"))

    def test_raw_experience_replay_binds_mfm_input_without_granting_authority(self):
        scope = _scope("flora-formation")
        with tempfile.TemporaryDirectory() as directory:
            objects = EncryptedObjectPlane(scope=scope, key=b"f" * 32,
                backend=LocalObjectBackend(Path(directory) / "objects"))
            raw = objects.put(b"synthetic, unverified experience")
            event = ExperienceEvent.create(
                event_type="observation", scope=scope,
                occurred_at="2026-09-28T21:00:00Z", content_digest=raw.plaintext_sha256,
                provenance=ProvenanceReference.create(
                    provenance_type="derived_inference",
                    source_reference_ids=(raw.object_id,),
                    derivation_activity_id="flora-formation-test",
                    responsible_component="synthetic-test"),
                retention_class="ordinary_experience", storage_tier="raw_buffer",
                payload_reference=raw.object_id,
            )
            client = KurrentDBClient(os.environ.get(
                "KURRENTDB_URI", "kurrentdb://127.0.0.1:2113?tls=false"))
            try:
                log = KurrentExperienceLog(scope=scope, client=client)
                log.append(event, expected_revision=-1)
                packet = formation_input_from_replay(
                    log=log, event_ids=(event.event_id,),
                    references={raw.object_id: raw},
                    modalities={event.event_id: "text"}, objects=objects,
                    authority_namespace_id="host-claims")
                self.assertEqual(packet.experience_refs, (event.event_id,))
                self.assertEqual(packet.evidence[0].role, "historical_experience")
                with self.assertRaisesRegex(ValueError, "absent"):
                    formation_input_from_replay(
                        log=log, event_ids=("experience-fabricated",),
                        references={raw.object_id: raw},
                        modalities={event.event_id: "text"}, objects=objects,
                        authority_namespace_id="host-claims")
            finally:
                client.close()

    def test_kurrent_expected_revision_idempotency_and_replay(self):
        scope = _scope("integration-kurrent")
        client = KurrentDBClient(
            os.environ.get(
                "KURRENTDB_URI",
                "kurrentdb://127.0.0.1:2113?tls=false",
            )
        )
        try:
            log = KurrentExperienceLog(scope=scope, client=client)
            first = _event(
                scope,
                suffix="event-one",
                occurred_at="2026-09-28T20:00:00Z",
            )
            log.append(first, expected_revision=-1)
            log.append(first, expected_revision=-1)
            self.assertEqual(log.replay(), [first])

            second = _event(
                scope,
                suffix="event-two",
                occurred_at="2026-09-28T20:01:00Z",
            )
            log.append(second, expected_revision=0)
            self.assertEqual(log.replay(), [first, second])

            conflicting = _event(
                scope,
                suffix="event-three",
                occurred_at="2026-09-28T20:02:00Z",
            )
            with self.assertRaises(WrongCurrentVersionError):
                log.append(conflicting, expected_revision=0)
        finally:
            client.close()

    def test_xtdb_bitemporal_current_claim_and_host_isolation(self):
        dsn = os.environ.get(
            "XTDB_DSN",
            "postgresql://xtdb@127.0.0.1:5432/xtdb",
        )
        with psycopg.connect(dsn, autocommit=True) as connection:
            scope = _scope("integration-xtdb")
            namespace = "integration-claims"
            authority = XTDBClaimAuthority(
                scope=scope,
                authority_namespace_id=namespace,
                connection=connection,
            )
            first_event = _event(scope, suffix="claim-source-one",
                occurred_at="2026-09-01T00:00:00Z")
            second_event = _event(scope, suffix="claim-source-two",
                occurred_at="2026-09-15T00:00:00Z", event_type="correction",
                parent_event_ids=(first_event.event_id,))
            event_client = KurrentDBClient(os.environ.get(
                "KURRENTDB_URI", "kurrentdb://127.0.0.1:2113?tls=false"))
            try:
                experience_log = KurrentExperienceLog(scope=scope, client=event_client)
                experience_log.append(first_event, expected_revision=-1)
                experience_log.append(second_event, expected_revision=0)
                replayed = experience_log.replay()
            finally:
                event_client.close()

            identity = ClaimIdentity.create(
                envelope=_envelope(
                    scope=scope,
                    authority_namespace_id=namespace,
                    record_id="claim-integration",
                    record_type="claim_identity",
                    authority_role="claim_authority",
                    created_at="2026-09-01T00:00:00Z",
                ),
                claim_id="claim-integration",
                canonical_subject=CanonicalTaggedValue.create(
                    type_tag="identifier",
                    value="integration-subject",
                ),
                canonical_predicate="prefers_interface",
                canonical_value=_text("dark mode"),
                semantic_scope=("owner_preference", "user_interface"),
            )
            authority.put_identity(identity)

            first_relation = ClaimEvidenceRelation.create(
                envelope=_envelope(
                    scope=scope, authority_namespace_id=namespace,
                    record_id="relation-integration-v1",
                    record_type="claim_evidence_relation",
                    authority_role="claim_authority",
                    created_at="2026-09-01T00:00:00Z",
                    source_records=(first_event.event_id, "claim-integration-v1"),
                ),
                relation_id="relation-integration-v1",
                evidence_record_id=first_event.event_id,
                target_record_id="claim-integration-v1",
                target_record_type="claim_version",
                relation_type="support", source_class="experience",
                source_authority_class="owner_attested",
                extractor_component_id="flora-integration",
                extractor_version="v1", confidence=0.99,
            )
            authority.put_evidence_relation(first_relation)
            authority.put_evidence_relation(first_relation)
            self.assertEqual(authority.load_evidence_relation(first_relation.relation_id),
                             first_relation.metadata_record())

            first_version = ClaimVersion.create(
                envelope=_envelope(
                    scope=scope,
                    authority_namespace_id=namespace,
                    record_id="claim-integration-v1",
                    record_type="claim_version",
                    authority_role="claim_authority",
                    created_at="2026-09-01T00:00:00Z",
                    source_records=("claim-integration", first_event.event_id, first_relation.relation_id),
                ),
                claim_version_id="claim-integration-v1",
                claim_id="claim-integration",
                version_sequence=1,
                store_sequence=1,
                event_stream_position=0,
                value=_text("dark mode"),
                authority_class="owner_attested",
                confidence=0.99,
                adjudication_state="accepted",
                evidence_relation_ids=(first_relation.relation_id,),
                request_digest="c" * 64,
            )
            first_projection = CurrentClaimProjection.create(
                envelope=_envelope(
                    scope=scope,
                    authority_namespace_id=namespace,
                    record_id="claim-integration-projection-v1",
                    record_type="current_claim_projection",
                    authority_role="registered_projection",
                    created_at="2026-09-01T00:00:00Z",
                    source_records=("claim-integration", "claim-integration-v1"),
                ),
                projection_id="claim-integration-projection-v1",
                claim_id="claim-integration",
                current_claim_version_id="claim-integration-v1",
                authority_generation=1,
                projection_generation=1,
                adjudication_state="accepted",
                validity_state="current",
                conflict_state="none",
                deletion_state="active",
                source_position=1,
            )
            first_projection.assert_projects(identity, first_version)
            self.assertEqual(bind_claim_source(version=first_version,
                relations=(first_relation,), replayed=replayed).stream_position, 0)
            authority.put_version(first_version)
            authority.put_current(first_projection)
            authority.put_current(first_projection)  # Same immutable request is idempotent.

            before_change = authority.load_current(
                "claim-integration",
                as_of=datetime(2026, 9, 10, tzinfo=timezone.utc),
            )
            self.assertEqual(
                before_change["current_claim_version_id"],
                "claim-integration-v1",
            )

            second_relation = ClaimEvidenceRelation.create(
                envelope=_envelope(
                    scope=scope, authority_namespace_id=namespace,
                    record_id="relation-integration-v2",
                    record_type="claim_evidence_relation",
                    authority_role="claim_authority",
                    created_at="2026-09-15T00:00:00Z",
                    source_records=(second_event.event_id, "claim-integration-v2"),
                ),
                relation_id="relation-integration-v2",
                evidence_record_id=second_event.event_id,
                target_record_id="claim-integration-v2",
                target_record_type="claim_version",
                relation_type="correction", source_class="experience",
                source_authority_class="owner_correction",
                extractor_component_id="flora-integration",
                extractor_version="v1", confidence=1.0,
            )
            authority.put_evidence_relation(second_relation)

            second_version = ClaimVersion.create(
                envelope=_envelope(
                    scope=scope,
                    authority_namespace_id=namespace,
                    record_id="claim-integration-v2",
                    record_type="claim_version",
                    authority_role="claim_authority",
                    created_at="2026-09-15T00:00:00Z",
                    source_records=("claim-integration", second_event.event_id, second_relation.relation_id),
                    supersedes=("claim-integration-v1",),
                    logical_clock=2,
                ),
                claim_version_id="claim-integration-v2",
                claim_id="claim-integration",
                version_sequence=2,
                store_sequence=2,
                event_stream_position=1,
                value=_text("light mode"),
                authority_class="owner_correction",
                confidence=1.0,
                adjudication_state="revised",
                evidence_relation_ids=(second_relation.relation_id,),
                correction_of=("claim-integration-v1",),
                request_digest="d" * 64,
            )
            second_projection = CurrentClaimProjection.create(
                envelope=_envelope(
                    scope=scope,
                    authority_namespace_id=namespace,
                    record_id="claim-integration-projection-v2",
                    record_type="current_claim_projection",
                    authority_role="registered_projection",
                    created_at="2026-09-15T00:00:00Z",
                    source_records=("claim-integration", "claim-integration-v2"),
                    supersedes=("claim-integration-projection-v1",),
                    logical_clock=2,
                ),
                projection_id="claim-integration-projection-v2",
                claim_id="claim-integration",
                current_claim_version_id="claim-integration-v2",
                authority_generation=1,
                projection_generation=2,
                adjudication_state="revised",
                validity_state="current",
                conflict_state="none",
                deletion_state="active",
                source_position=2,
            )
            second_projection.assert_projects(identity, second_version)
            self.assertEqual(bind_claim_source(version=second_version,
                relations=(second_relation,), replayed=replayed).stream_position, 1)
            with self.assertRaisesRegex(ValueError, "no replayed"):
                bind_claim_source(version=second_version, relations=(second_relation,),
                                  replayed=replayed[:1])
            authority.put_version(second_version)
            with self.assertRaisesRegex(ValueError, "head exists"):
                authority.put_current(second_projection)
            authority.put_current(second_projection, expected_previous=first_projection)
            authority.put_current(second_projection, expected_previous=first_projection)
            with self.assertRaisesRegex(ValueError, "stale"):
                authority.put_current(first_projection, expected_previous=first_projection)

            still_before = authority.load_current(
                "claim-integration",
                as_of=datetime(2026, 9, 10, tzinfo=timezone.utc),
            )
            after_change = authority.load_current(
                "claim-integration",
                as_of=datetime(2026, 9, 20, tzinfo=timezone.utc),
            )
            self.assertEqual(
                still_before["current_claim_version_id"],
                "claim-integration-v1",
            )
            self.assertEqual(
                after_change["current_claim_version_id"],
                "claim-integration-v2",
            )
            projection_ids = {
                row["projection_id"]
                for row in authority.current_history("claim-integration")
            }
            self.assertIn("claim-integration-projection-v1", projection_ids)
            self.assertIn("claim-integration-projection-v2", projection_ids)

            other_scope = _scope("integration-xtdb-other")
            other = XTDBClaimAuthority(
                scope=other_scope,
                authority_namespace_id=namespace,
                connection=connection,
            )
            with self.assertRaises(KeyError):
                other.load_current(
                    "claim-integration",
                    as_of=datetime(2026, 9, 20, tzinfo=timezone.utc),
                )
            with self.assertRaises(KeyError):
                other.load_evidence_relation(first_relation.relation_id)


if __name__ == "__main__":
    unittest.main()
