"""Temporal workflow for retryable cleanup of selected derived indexes.

This does not erase original Experience/raw data or remove model influence.
Each activity compares the exact XTDB head before touching its derived plane.
"""

from __future__ import annotations

from datetime import timedelta
import hashlib
from typing import TYPE_CHECKING

from cognitive_kernel.canonical import require_identifier, require_sha256
from temporalio import activity, workflow
from temporalio.common import RetryPolicy

if TYPE_CHECKING:
    from .claims import XTDBClaimAuthority
    from .graph_recollection import LadybugEvidenceGraph
    from .vector_recollection import QdrantClaimProjection


def cleanup_request(*, authority: XTDBClaimAuthority, claim_id: str) -> dict[str, str]:
    require_identifier(claim_id, "claim_id")
    head = authority.load_current(claim_id)
    require_sha256(head["projection_sha256"], "projection_sha256")
    return {
        "schema": "flora-derived-reconciliation-v1",
        "scope_digest": authority.scope_digest,
        "claim_id": claim_id,
        "projection_sha256": head["projection_sha256"],
    }


def cleanup_workflow_id(request: dict[str, str]) -> str:
    return "flora-reconcile-" + hashlib.sha256(
        (request["scope_digest"] + ":" + request["claim_id"] + ":"
         + request["projection_sha256"]).encode()).hexdigest()


@workflow.defn
class ReconcileDerivedClaimWorkflow:
    @workflow.run
    async def run(self, request: dict[str, str]) -> dict:
        retries = RetryPolicy(initial_interval=timedelta(seconds=1),
                              maximum_attempts=4)
        vector_count = await workflow.execute_activity(
            "flora-prune-qdrant-v1", request,
            start_to_close_timeout=timedelta(seconds=30), retry_policy=retries)
        graph_count = await workflow.execute_activity(
            "flora-prune-ladybug-v1", request,
            start_to_close_timeout=timedelta(seconds=30), retry_policy=retries)
        return {"schema": "flora-derived-reconciliation-result-v1",
                "claim_id": request["claim_id"],
                "projection_sha256": request["projection_sha256"],
                "vector_removed": vector_count, "graph_removed": graph_count}


class DerivedCleanupActivities:
    def __init__(self, *, authority: XTDBClaimAuthority,
                 vector: QdrantClaimProjection,
                 graph: LadybugEvidenceGraph):
        if not (authority.scope == vector.scope == graph.scope):
            raise ValueError("derived cleanup crosses host scope")
        self.authority = authority
        self.vector = vector
        self.graph = graph

    def _check(self, request: dict[str, str]) -> None:
        if (request.get("schema") != "flora-derived-reconciliation-v1"
                or request.get("scope_digest") != self.authority.scope_digest):
            raise ValueError("derived cleanup request crosses scope or schema")
        require_identifier(request["claim_id"], "claim_id")
        require_sha256(request["projection_sha256"], "projection_sha256")
        head = self.authority.load_current(request["claim_id"])
        if head["projection_sha256"] != request["projection_sha256"]:
            raise ValueError("derived cleanup request names a stale Claim head")

    @activity.defn(name="flora-prune-qdrant-v1")
    async def prune_vector(self, request: dict[str, str]) -> int:
        self._check(request)
        return self.vector.prune_noncurrent(
            claim_id=request["claim_id"], authority=self.authority)

    @activity.defn(name="flora-prune-ladybug-v1")
    async def prune_graph(self, request: dict[str, str]) -> int:
        self._check(request)
        return self.graph.prune_noncurrent(
            claim_id=request["claim_id"], authority=self.authority)
