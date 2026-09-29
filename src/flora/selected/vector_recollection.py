"""Host-scoped Qdrant projection of current, source-verified claim versions.

Vectors are caller-produced derived indexes. Similarity ranks candidates;
XTDB Claim Authority and raw Experience evidence remain the source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from typing import Mapping, Sequence
import uuid

from cognitive_kernel.canonical import require_sha256
from cognitive_kernel.contracts import ProductHostScope
from qdrant_client import QdrantClient, models

from .claims import XTDBClaimAuthority
from .experience import KurrentExperienceLog
from .object_store import EncryptedObjectPlane, RawObjectReference
from .source_native import read_current_sources


@dataclass(frozen=True)
class VectorCandidate:
    claim_id: str
    claim_version_id: str
    projection_id: str
    source_event_ids: tuple[str, ...]
    score: float


class QdrantClaimProjection:
    """A separate host/model-generation collection for one vector space."""

    def __init__(
        self, *, scope: ProductHostScope, client: QdrantClient,
        embedding_artifact_sha256: str, dimension: int,
    ):
        scope.validate()
        require_sha256(embedding_artifact_sha256, "embedding_artifact_sha256")
        if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension <= 0:
            raise ValueError("vector dimension must be positive")
        self.scope = scope
        self.client = client
        self.embedding_artifact_sha256 = embedding_artifact_sha256
        self.dimension = dimension
        host_digest = hashlib.sha256(scope.storage_scope().encode()).hexdigest()
        self.collection = f"flora_{host_digest[:24]}_{embedding_artifact_sha256[:16]}"

    def ensure_collection(self) -> None:
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config={"text": models.VectorParams(
                    size=self.dimension, distance=models.Distance.COSINE)},
            )
        config = self.client.get_collection(self.collection).config.params.vectors
        if not isinstance(config, dict) or "text" not in config or (
            config["text"].size != self.dimension
            or config["text"].distance != models.Distance.COSINE
        ):
            raise ValueError("existing Qdrant collection has a different vector contract")

    def _vector(self, value: Sequence[float]) -> list[float]:
        if len(value) != self.dimension or any(
            isinstance(item, bool) or not isinstance(item, (float, int))
            or not math.isfinite(item) for item in value
        ):
            raise ValueError("vector does not match the finite model dimension")
        return [float(item) for item in value]

    def _point_id(self, version_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_OID,
            f"{self.collection}:{version_id}"))

    def _current_binding(self, authority: XTDBClaimAuthority,
                         claim_id: str) -> tuple[str, str, set[str]] | None:
        try:
            current = authority.load_current(claim_id)
            if (current["deletion_state"] != "active"
                    or current["conflict_state"] != "none"
                    or current["adjudication_state"] not in {"accepted", "revised"}):
                return None
            version_id = current["current_claim_version_id"]
            version = authority.load_version(version_id)
            if version["claim_id"] != claim_id:
                return None
            sources = {
                authority.load_evidence_relation(relation_id)["evidence_record_id"]
                for relation_id in version["evidence_relation_ids"]
            }
            return version_id, current["projection_id"], sources
        except KeyError:
            return None

    def _matches_binding(self, *, payload: dict, point_id: str,
                         binding: tuple[str, str, set[str]] | None,
                         authority: XTDBClaimAuthority) -> bool:
        if binding is None:
            return False
        version_id, projection_id, sources = binding
        source_ids = payload.get("source_event_ids")
        return (
            point_id == self._point_id(version_id)
            and payload.get("claim_version_id") == version_id
            and payload.get("projection_id") == projection_id
            and payload.get("authority_scope_digest") == authority.scope_digest
            and payload.get("embedding_artifact_sha256") == self.embedding_artifact_sha256
            and isinstance(source_ids, list)
            and all(isinstance(item, str) for item in source_ids)
            and len(source_ids) == len(sources)
            and set(source_ids) == sources
        )

    def index_current(
        self, *, claim_id: str, vector: Sequence[float],
        authority: XTDBClaimAuthority, log: KurrentExperienceLog,
        objects: EncryptedObjectPlane,
        references: Mapping[str, RawObjectReference],
    ) -> VectorCandidate:
        if authority.scope != self.scope:
            raise ValueError("claim projection crosses host scope")
        packet = read_current_sources(
            claim_id=claim_id, authority=authority, log=log,
            objects=objects, references=references)
        value = self._vector(vector)
        point_id = self._point_id(packet.claim_version_id)
        source_ids = tuple(item.event_id for item in packet.sources)
        self.client.upsert(collection_name=self.collection, wait=True, points=[
            models.PointStruct(
                id=point_id, vector={"text": value},
                payload={
                    "claim_id": packet.claim_id,
                    "claim_version_id": packet.claim_version_id,
                    "projection_id": packet.projection_id,
                    "source_event_ids": list(source_ids),
                    "embedding_artifact_sha256": self.embedding_artifact_sha256,
                    "authority_scope_digest": authority.scope_digest,
                },
            )
        ])
        return VectorCandidate(packet.claim_id, packet.claim_version_id,
                               packet.projection_id, source_ids, 0.0)

    def query_current(
        self, *, query_vector: Sequence[float],
        authority: XTDBClaimAuthority, limit: int = 10,
    ) -> tuple[VectorCandidate, ...]:
        if authority.scope != self.scope:
            raise ValueError("vector query crosses host scope")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be positive")
        points = self.client.query_points(
            collection_name=self.collection, query=self._vector(query_vector),
            using="text", with_payload=True, limit=limit * 16,
        ).points
        result: list[VectorCandidate] = []
        for point in points:
            payload = point.payload or {}
            claim_id = payload.get("claim_id")
            version_id = payload.get("claim_version_id")
            if not isinstance(claim_id, str) or not isinstance(version_id, str):
                continue
            binding = self._current_binding(authority, claim_id)
            if not self._matches_binding(
                payload=payload, point_id=str(point.id), binding=binding,
                authority=authority,
            ):
                continue
            result.append(VectorCandidate(
                claim_id, version_id, binding[1],
                tuple(payload["source_event_ids"]), float(point.score)))
            if len(result) == limit:
                break
        return tuple(result)

    def prune_noncurrent(self, *, claim_id: str,
                         authority: XTDBClaimAuthority) -> int:
        """Remove obsolete or unbound derived points after an authority change.

        This is safe to retry. Read-time authority filtering remains mandatory:
        XTDB and Qdrant do not update atomically, and a cleanup may lag.
        """
        if authority.scope != self.scope:
            raise ValueError("vector reconciliation crosses host scope")
        binding = self._current_binding(authority, claim_id)
        offset = None
        obsolete: list[str | int] = []
        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection,
                scroll_filter=models.Filter(must=[models.FieldCondition(
                    key="claim_id", match=models.MatchValue(value=claim_id))]),
                limit=128, offset=offset, with_payload=True, with_vectors=False,
            )
            for point in points:
                if not self._matches_binding(
                    payload=point.payload or {}, point_id=str(point.id),
                    binding=binding, authority=authority,
                ):
                    obsolete.append(point.id)
            if offset is None:
                break
        if obsolete:
            self.client.delete(
                collection_name=self.collection,
                points_selector=models.PointIdsList(points=obsolete), wait=True,
            )
        return len(obsolete)
