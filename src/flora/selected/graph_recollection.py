"""LadybugDB evidence graph; a derived candidate index, never Claim authority."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Mapping

from cognitive_kernel.contracts import ProductHostScope
import ladybug

from .claims import XTDBClaimAuthority
from .experience import KurrentExperienceLog
from .object_store import EncryptedObjectPlane, RawObjectReference
from .source_native import read_current_sources


@dataclass(frozen=True)
class GraphCandidate:
    claim_id: str
    claim_version_id: str
    projection_id: str
    relation_ids: tuple[str, ...]
    source_event_ids: tuple[str, ...]


class LadybugEvidenceGraph:
    """One host-local database; all graph hits are verified against selected authority."""

    def __init__(self, *, scope: ProductHostScope, connection: ladybug.Connection):
        scope.validate()
        self.scope = scope
        self.connection = connection
        self.scope_digest = hashlib.sha256(scope.storage_scope().encode()).hexdigest()

    def ensure_schema(self) -> None:
        for statement in (
            "CREATE NODE TABLE IF NOT EXISTS FloRAClaimVersion(id STRING PRIMARY KEY, claim_id STRING, projection_id STRING)",
            "CREATE NODE TABLE IF NOT EXISTS FloRAEvidence(id STRING PRIMARY KEY)",
            "CREATE REL TABLE IF NOT EXISTS FloRACites(FROM FloRAClaimVersion TO FloRAEvidence, relation_id STRING, relation_type STRING)",
        ):
            self.connection.execute(statement)

    def _key(self, identifier: str) -> str:
        return hashlib.sha256(f"{self.scope_digest}:{identifier}".encode()).hexdigest()

    def _check_scope(self, authority: XTDBClaimAuthority,
                     log: KurrentExperienceLog, objects: EncryptedObjectPlane) -> None:
        if not (self.scope == authority.scope == log.scope == objects.scope):
            raise ValueError("graph projection crosses host scope")

    def _edges(self, claim_version_id: str) -> list[list[str]]:
        return self.connection.execute(
            "MATCH (c:FloRAClaimVersion {id:$id})-[r:FloRACites]->(e:FloRAEvidence) "
            "RETURN e.id, r.relation_id, r.relation_type",
            {"id": self._key(claim_version_id)},
        ).get_all()

    def _exact_edges(self, candidate: GraphCandidate,
                     authority: XTDBClaimAuthority) -> bool:
        version = authority.load_version(candidate.claim_version_id)
        if set(version["evidence_relation_ids"]) != set(candidate.relation_ids):
            return False
        expected = sorted((self._key(event_id), relation_id,
                           authority.load_evidence_relation(relation_id)["relation_type"])
                          for event_id, relation_id in zip(
                              candidate.source_event_ids, candidate.relation_ids))
        return sorted(tuple(row) for row in self._edges(candidate.claim_version_id)) == expected

    def project_current(self, *, claim_id: str,
                        authority: XTDBClaimAuthority, log: KurrentExperienceLog,
                        objects: EncryptedObjectPlane,
                        references: Mapping[str, RawObjectReference]) -> GraphCandidate:
        self._check_scope(authority, log, objects)
        packet = read_current_sources(
            claim_id=claim_id, authority=authority, log=log,
            objects=objects, references=references)
        candidate = GraphCandidate(
            claim_id, packet.claim_version_id, packet.projection_id,
            tuple(s.relation_id for s in packet.sources),
            tuple(s.event_id for s in packet.sources))
        if set(authority.load_version(packet.claim_version_id)["evidence_relation_ids"]) != set(candidate.relation_ids):
            raise ValueError("graph projection differs from Claim evidence")
        claim_key = self._key(packet.claim_version_id)
        rows = self.connection.execute(
            "MATCH (c:FloRAClaimVersion {id:$id}) RETURN c.claim_id, c.projection_id",
            {"id": claim_key}).get_all()
        if rows:
            if rows != [[claim_id, packet.projection_id]] or not self._exact_edges(candidate, authority):
                raise ValueError("graph version differs from selected authority")
            return candidate
        self.connection.execute("BEGIN TRANSACTION")
        try:
            self.connection.execute(
                "CREATE (:FloRAClaimVersion {id:$id, claim_id:$claim, projection_id:$projection})",
                {"id": claim_key, "claim": claim_id, "projection": packet.projection_id})
            for source in packet.sources:
                event_key = self._key(source.event_id)
                if not self.connection.execute(
                    "MATCH (e:FloRAEvidence {id:$id}) RETURN e.id",
                    {"id": event_key}).get_all():
                    self.connection.execute(
                        "CREATE (:FloRAEvidence {id:$id})", {"id": event_key})
                relation = authority.load_evidence_relation(source.relation_id)
                self.connection.execute(
                    "MATCH (c:FloRAClaimVersion {id:$claim}), (e:FloRAEvidence {id:$event}) "
                    "CREATE (c)-[:FloRACites {relation_id:$relation, relation_type:$type}]->(e)",
                    {"claim": claim_key, "event": event_key,
                     "relation": source.relation_id, "type": relation["relation_type"]})
            self.connection.execute("COMMIT")
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        return candidate

    def related_current(self, *, source_event_id: str,
                        authority: XTDBClaimAuthority, log: KurrentExperienceLog,
                        objects: EncryptedObjectPlane,
                        references: Mapping[str, RawObjectReference],
                        limit: int = 10) -> tuple[GraphCandidate, ...]:
        """Return source-connected claims only if still current and source verified."""
        self._check_scope(authority, log, objects)
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("graph candidate limit must be positive")
        rows = self.connection.execute(
            "MATCH (c:FloRAClaimVersion)-[r:FloRACites]->(e:FloRAEvidence {id:$event}) "
            "RETURN c.id, c.claim_id, c.projection_id, r.relation_id",
            {"event": self._key(source_event_id)}).get_all()
        result = []
        for key, claim_id, projection_id, relation_id in rows:
            try:
                packet = read_current_sources(
                    claim_id=claim_id, authority=authority, log=log,
                    objects=objects, references=references)
                candidate = GraphCandidate(
                    claim_id, packet.claim_version_id, packet.projection_id,
                    tuple(s.relation_id for s in packet.sources),
                    tuple(s.event_id for s in packet.sources))
                if (key != self._key(packet.claim_version_id)
                        or projection_id != packet.projection_id
                        or (source_event_id, relation_id) not in {
                            (s.event_id, s.relation_id) for s in packet.sources}
                        or not self._exact_edges(candidate, authority)):
                    continue
            except (KeyError, ValueError):
                continue
            result.append(candidate)
            if len(result) == limit:
                break
        return tuple(result)

    def prune_noncurrent(self, *, claim_id: str,
                         authority: XTDBClaimAuthority) -> int:
        if authority.scope != self.scope:
            raise ValueError("graph cleanup crosses host scope")
        try:
            head = authority.load_current(claim_id)
            keep = self._key(head["current_claim_version_id"]) if head["deletion_state"] == "active" else None
            projection = head["projection_id"]
        except KeyError:
            keep, projection = None, None
        rows = self.connection.execute(
            "MATCH (c:FloRAClaimVersion {claim_id:$claim}) RETURN c.id, c.projection_id",
            {"claim": claim_id}).get_all()
        stale = [key for key, projected in rows if key != keep or projected != projection]
        for key in stale:
            self.connection.execute(
                "MATCH (c:FloRAClaimVersion {id:$id}) DETACH DELETE c", {"id": key})
        return len(stale)
