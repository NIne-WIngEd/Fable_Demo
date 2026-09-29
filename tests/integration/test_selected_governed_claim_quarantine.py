"""Actual controller quarantine and selected derived cleanup, no model evidence.

Meanings/state are supplied fictional fixtures. The test uses actual Kurrent,
XTDB, Qdrant, Ladybug, durable owner custody and a local Temporal server.
"""
import asyncio
from datetime import datetime
import importlib.util
import os
from pathlib import Path
import sys
import unittest
import uuid

import ladybug
import psycopg
from qdrant_client import QdrantClient
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from flora.selected.context import ContextPlan, StateRoute
from flora.selected.derived_reconciliation import DerivedCleanupActivities, ReconcileDerivedClaimWorkflow, cleanup_workflow_id
from flora.selected.formation_context import register_experience_source
from flora.selected.governed_quarantine import XTDBGovernedClaimQuarantine
from flora.selected.graph_recollection import LadybugEvidenceGraph
from flora.selected.revocation import revocation_request
from flora.selected.source_native import read_current_sources
from flora.selected.vector_recollection import QdrantClaimProjection

spec = importlib.util.spec_from_file_location("flora_quarantine_runtime_backend_fixture",
    Path(__file__).parent / "test_selected_runtime_bridge.py")
_fixture = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = _fixture
spec.loader.exec_module(_fixture)


class _FailReceiptOnce:
    def __init__(self, connection):
        self.connection, self.failed = connection, False

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, sql, parameters):
        if not self.failed and sql.startswith("INSERT INTO flora_governed_claim_quarantine_receipts"):
            self.failed = True
            raise RuntimeError("injected before real quarantine receipt insert")
        return self.connection.execute(sql, parameters)


class GovernedClaimQuarantineIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.f = _fixture.SelectedExperimentRuntimeIntegrationTest()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def test_real_atomic_pending_barrier_recreation_and_temporal_derived_cleanup(self):
        f = self.f
        source = f.fabric._source(b"fictional source used by governed state")
        f._judgment_permission(f.registry.lookup(source.event_id))
        bundle, store = f.fabric._bundle(source, prefix="quarantine-fixture")
        bound, at = f.fabric._prepare(bundle, store)
        adjudication = _fixture._semantic_fixture.fixture_adjudication(bound, at=at)
        f.fabric.semantic_proof.approve_fixture(adjudication, bound)
        accepted = f.fabric._admit(bound, adjudication, store)
        prior = _fixture._semantic_fixture.fixture_projection(f.claims.load_current(accepted.claim_id))
        version = f._state_activation(accepted, source)
        plan = ContextPlan(request_id="quarantine-state-context", purpose="personal_judgment",
            exact_claim_ids=(accepted.claim_id,),
            state_routes=(StateRoute("owner", f.scope.host_instance_id, version.projection_id),))
        self.assertEqual(len(f.runtime._context(plan).items), 2)
        qdrant = QdrantClient(url=os.environ.get("QDRANT_URL", "http://127.0.0.1:6333"))
        self.addCleanup(qdrant.close)
        vectors = QdrantClaimProjection(scope=f.scope, client=qdrant, embedding_artifact_sha256="e" * 64, dimension=2)
        vectors.ensure_collection()
        self.addCleanup(lambda: qdrant.delete_collection(vectors.collection))
        vectors.index_current(claim_id=accepted.claim_id, vector=(1.0, 0.0), authority=f.claims,
            log=f.log, objects=f.objects, references=f.references)
        database = ladybug.Database(str(Path(f.fabric.directory.name) / "quarantine-graph"))
        graph = LadybugEvidenceGraph(scope=f.scope, connection=ladybug.Connection(database))
        graph.ensure_schema()
        graph.project_current(claim_id=accepted.claim_id, authority=f.claims,
            log=f.log, objects=f.objects, references=f.references)
        event, raw = f.fabric._append(revocation_request(prior), event_type="deletion_request",
                                      parents=(source.event_id,))
        register_experience_source(event_id=event.event_id, raw=raw, registry=f.registry,
            log=f.log, objects=f.objects, role="generated_reconstruction", modality="structured")
        f._persist_proof(event, "claim_quarantine")
        f.claims.connection = _FailReceiptOnce(f.connection)
        gateway = XTDBGovernedClaimQuarantine(f.claims)
        args = dict(prior=prior, request_event_id=event.event_id, log=f.log,
            objects=f.objects, references=f.references, verifier=f.owner_verifier)
        with self.assertRaisesRegex(RuntimeError, "real quarantine receipt"):
            gateway.apply(**args)
        self.assertEqual(f.claims.load_current(accepted.claim_id), prior.metadata_record())
        f.claims.connection = f.connection
        receipt = gateway.apply(**args)
        self.assertEqual(receipt.store_sequence, 2)
        self.assertNotEqual(receipt.store_sequence, receipt.event_stream_position)
        self.assertEqual(vectors.query_current(query_vector=(1.0, 0.0), authority=f.claims), ())
        self.assertEqual(graph.related_current_metadata(source_event_id=source.event_id,
                                                        authority=f.claims, log=f.log), ())
        with self.assertRaises(ValueError):
            read_current_sources(claim_id=accepted.claim_id, authority=f.claims, log=f.log,
                objects=f.objects, references=f.references)
        # Historical retrieval cannot bypass today's pending deletion.
        with self.assertRaises(ValueError):
            read_current_sources(claim_id=accepted.claim_id, authority=f.claims, log=f.log,
                objects=f.objects, references=f.references, as_of=datetime.fromisoformat(
                    prior.envelope.valid_from.replace("Z", "+00:00")))
        with self.assertRaises((ValueError, PermissionError)):
            f.runtime._context(plan)
        dsn = f.connection.info.dsn
        f.connection.close()
        reopened = psycopg.connect(dsn, autocommit=True)
        self.addCleanup(reopened.close)
        f._bind_services(reopened)
        gateway = XTDBGovernedClaimQuarantine(f.claims)
        args.update(references=f.references, verifier=f.owner_verifier)
        self.assertEqual(gateway.apply(**args), receipt)

        async def reconcile():
            activities = DerivedCleanupActivities(authority=f.claims, vector=vectors, graph=graph)
            request = gateway.cleanup(receipt)
            async with await WorkflowEnvironment.start_local() as env:
                queue = "flora-governed-quarantine-" + uuid.uuid4().hex
                async with Worker(env.client, task_queue=queue,
                    workflows=[ReconcileDerivedClaimWorkflow],
                    activities=[activities.prune_vector, activities.prune_graph]):
                    return await env.client.execute_workflow(ReconcileDerivedClaimWorkflow.run,
                        request, id=cleanup_workflow_id(request), task_queue=queue)

        cleanup = asyncio.run(reconcile())
        self.assertEqual((cleanup["vector_removed"], cleanup["graph_removed"]), (1, 1))
        self.assertEqual(vectors.prune_noncurrent(claim_id=accepted.claim_id, authority=f.claims), 0)
        self.assertEqual(graph.prune_noncurrent(claim_id=accepted.claim_id, authority=f.claims), 0)


if __name__ == "__main__":
    unittest.main()
