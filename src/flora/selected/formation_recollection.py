"""Selected memory-plane adapters for the upstream MFM context router.

Routes name independently registered query manifests. They cannot supply
model-written source IDs, vectors, or authority metadata through ``query_ref``.
The three planes return original Experience IDs after current Claim/source
verification; the upstream context assembler still owns source registration,
permission, byte custody, and provenance closure. These adapters neither infer
relevance nor promote a retrieved candidate to an authoritative memory.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Mapping

from cognitive_kernel.canonical import require_identifier
from cognitive_kernel.contracts import ProductHostScope

from .claims import XTDBClaimAuthority
from .experience import KurrentExperienceLog
from .graph_recollection import LadybugEvidenceGraph
from .object_store import EncryptedObjectPlane, RawObjectReference
from .source_native import CurrentEvidencePacket, read_current_sources
from .vector_recollection import QdrantClaimProjection


@dataclass(frozen=True)
class RegisteredFormationQuery:
    """A trusted query-registry record, supplied independently of MFM output.

    Optional routes share one scoped registration. A vector must come from a
    separately supplied embedding pipeline; this record does not manufacture
    embeddings or assert retrieval quality. ``limit`` bounds engine candidates,
    not the number of original sources cited by an accepted candidate.
    """

    scope: ProductHostScope
    authority_namespace_id: str
    query_ref: str
    claim_ids: tuple[str, ...] = ()
    query_vector: tuple[float, ...] | None = None
    graph_source_event_ids: tuple[str, ...] = ()
    limit: int = 10

    def validate(self) -> None:
        self.scope.validate()
        for value, name in (
            (self.authority_namespace_id, "authority_namespace_id"),
            (self.query_ref, "query_ref"),
        ):
            if require_identifier(value, name) != value:
                raise ValueError(f"{name} must be canonical")
        for values, name in (
            (self.claim_ids, "claim_ids"),
            (self.graph_source_event_ids, "graph_source_event_ids"),
        ):
            if not isinstance(values, tuple) or len(set(values)) != len(values):
                raise ValueError(f"{name} must be unique registered IDs")
            for value in values:
                if require_identifier(value, name) != value:
                    raise ValueError(f"{name} must be canonical")
        if self.query_vector is not None and (
            not isinstance(self.query_vector, tuple) or not self.query_vector
            or any(isinstance(value, bool) or not isinstance(value, (int, float))
                   or not math.isfinite(value) for value in self.query_vector)
        ):
            raise ValueError("query vector must be a registered finite tuple")
        if isinstance(self.limit, bool) or not isinstance(self.limit, int) or self.limit <= 0:
            raise ValueError("registered query limit must be positive")


RegisteredQueryResolver = Callable[[str], RegisteredFormationQuery | None]


class _CurrentSourcePlane:
    def __init__(
        self, *, authority: XTDBClaimAuthority, log: KurrentExperienceLog,
        objects: EncryptedObjectPlane,
        references: Mapping[str, RawObjectReference],
        query_resolver: RegisteredQueryResolver,
    ):
        if not (authority.scope == log.scope == objects.scope):
            raise ValueError("formation recollection crosses host scope")
        authority.scope.validate()
        if require_identifier(authority.authority_namespace_id,
                              "authority_namespace_id") != authority.authority_namespace_id:
            raise ValueError("formation authority namespace must be canonical")
        if not callable(query_resolver):
            raise TypeError("formation query resolver must be independently supplied")
        self.scope = authority.scope
        self.authority_namespace_id = authority.authority_namespace_id
        self.authority, self.log, self.objects = authority, log, objects
        self.references = references
        self.query_resolver = query_resolver

    def _query(self, query_ref: str) -> RegisteredFormationQuery:
        if require_identifier(query_ref, "query_ref") != query_ref:
            raise ValueError("formation query reference must be canonical")
        query = self.query_resolver(query_ref)
        if not isinstance(query, RegisteredFormationQuery):
            raise ValueError("formation query is not independently registered")
        query.validate()
        if (query.query_ref != query_ref or query.scope != self.scope
                or query.authority_namespace_id != self.authority_namespace_id):
            raise ValueError("formation query crosses its registered scope or namespace")
        return query

    def _packet(self, claim_id: str) -> CurrentEvidencePacket:
        return read_current_sources(
            claim_id=claim_id, authority=self.authority, log=self.log,
            objects=self.objects, references=self.references)

    @staticmethod
    def _source_ids(packets: list[CurrentEvidencePacket]) -> tuple[str, ...]:
        # Collapse duplicate hits within a plane. The upstream router/assembler
        # preserves every plane that independently finds the same source.
        return tuple(dict.fromkeys(source.event_id for packet in packets
                                   for source in packet.sources))


class ExactClaimFormationPlane(_CurrentSourcePlane):
    """Exact registered Claim queries resolved back to original Experience."""

    def source_ids(self, query_ref: str) -> tuple[str, ...]:
        query = self._query(query_ref)
        if not query.claim_ids:
            raise ValueError("registered query has no exact Claim route")
        return self._source_ids([self._packet(claim_id)
                                 for claim_id in query.claim_ids])


class QdrantFormationPlane(_CurrentSourcePlane):
    """Current Qdrant candidates rechecked against exact Claim/source custody."""

    def __init__(self, *, vector: QdrantClaimProjection, **kwargs):
        super().__init__(**kwargs)
        if vector.scope != self.scope:
            raise ValueError("formation vector projection crosses host scope")
        self.vector = vector

    def source_ids(self, query_ref: str) -> tuple[str, ...]:
        query = self._query(query_ref)
        if query.query_vector is None:
            raise ValueError("registered query has no Qdrant route")
        packets = []
        for candidate in self.vector.query_current(
            query_vector=query.query_vector, authority=self.authority,
            limit=query.limit,
        ):
            try:
                packet = self._packet(candidate.claim_id)
            except (KeyError, ValueError):
                continue  # A stale or unavailable derived hit grants no source use.
            if (candidate.claim_version_id != packet.claim_version_id
                    or candidate.projection_id != packet.projection_id
                    or candidate.source_event_ids != tuple(
                        source.event_id for source in packet.sources)):
                continue
            packets.append(packet)
        return self._source_ids(packets)


class LadybugFormationPlane(_CurrentSourcePlane):
    """Source-connected exact evidence graph candidates, not invented episodes."""

    def __init__(self, *, graph: LadybugEvidenceGraph, **kwargs):
        super().__init__(**kwargs)
        if graph.scope != self.scope:
            raise ValueError("formation graph projection crosses host scope")
        self.graph = graph

    def source_ids(self, query_ref: str) -> tuple[str, ...]:
        query = self._query(query_ref)
        if not query.graph_source_event_ids:
            raise ValueError("registered query has no Ladybug route")
        replayed_ids = {event.event_id for event in self.log.replay()}
        if not set(query.graph_source_event_ids).issubset(replayed_ids):
            raise ValueError("registered graph seed is absent from this host Experience")
        packets = []
        for source_id in query.graph_source_event_ids:
            for candidate in self.graph.related_current(
                source_event_id=source_id, authority=self.authority,
                log=self.log, objects=self.objects, references=self.references,
                limit=query.limit,
            ):
                try:
                    packet = self._packet(candidate.claim_id)
                except (KeyError, ValueError):
                    continue
                if (candidate.claim_version_id != packet.claim_version_id
                        or candidate.projection_id != packet.projection_id
                        or candidate.relation_ids != tuple(
                            source.relation_id for source in packet.sources)
                        or candidate.source_event_ids != tuple(
                            source.event_id for source in packet.sources)):
                    continue
                packets.append(packet)
        return self._source_ids(packets)
