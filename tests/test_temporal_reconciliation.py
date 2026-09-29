"""Real Temporal local server with injected synthetic selected-plane adapters."""

import asyncio
import unittest
import uuid

from cognitive_kernel.contracts import ProductHostScope
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from flora.selected.derived_reconciliation import (
    DerivedCleanupActivities, ReconcileDerivedClaimWorkflow,
    cleanup_request, cleanup_workflow_id,
)


class _Authority:
    def __init__(self):
        self.scope = ProductHostScope.create(
            product_id="friday", host_instance_id="synthetic-temporal-host",
            schema_version="1.0.0", encryption_domain="synthetic-temporal")
        self.scope_digest = "a" * 64
        self.head = "b" * 64

    def load_current(self, claim_id):
        if claim_id != "synthetic-claim":
            raise KeyError(claim_id)
        return {"projection_sha256": self.head}


class _Index:
    def __init__(self, scope, *, fail_once=False):
        self.scope = scope
        self.calls = 0
        self.fail_once = fail_once

    def prune_noncurrent(self, *, claim_id, authority):
        self.calls += 1
        if self.fail_once and self.calls == 1:
            raise RuntimeError("synthetic transient derived-index failure")
        return 1


class TemporalReconciliationTest(unittest.TestCase):
    def test_durable_activity_retry_and_exact_head(self):
        async def exercise():
            authority = _Authority()
            vector = _Index(authority.scope)
            graph = _Index(authority.scope, fail_once=True)
            activities = DerivedCleanupActivities(
                authority=authority, vector=vector, graph=graph)
            request = cleanup_request(
                authority=authority, claim_id="synthetic-claim")
            self.assertEqual(len(cleanup_workflow_id(request)), len("flora-reconcile-") + 64)
            async with await WorkflowEnvironment.start_local() as env:
                queue = f"flora-reconcile-{uuid.uuid4()}"
                async with Worker(
                    env.client, task_queue=queue,
                    workflows=[ReconcileDerivedClaimWorkflow],
                    activities=[activities.prune_vector, activities.prune_graph],
                ):
                    receipt = await env.client.execute_workflow(
                        ReconcileDerivedClaimWorkflow.run, request,
                        id=cleanup_workflow_id(request), task_queue=queue)
                    self.assertEqual((receipt["vector_removed"],
                                      receipt["graph_removed"]), (1, 1))
                    self.assertEqual((vector.calls, graph.calls), (1, 2))
            authority.head = "c" * 64
            with self.assertRaisesRegex(ValueError, "stale Claim head"):
                activities._check(request)

        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
