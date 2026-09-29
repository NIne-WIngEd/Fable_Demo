"""XTDB v2 placement for the selected bitemporal Claim Authority.

This module stores A.L.I.C.E./Fable-owned claim contracts in XTDB without
making XTDB itself the semantic contract. XTDB supplies physical bitemporal
persistence; contract validation, product/host scope, and authority namespace
remain project-owned.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any, Sequence

from cognitive_kernel.canonical import require_identifier
from cognitive_kernel.adjudication_contracts import ClaimEvidenceRelation
from cognitive_kernel.claim_contracts import (
    ClaimIdentity,
    ClaimVersion,
    CurrentClaimProjection,
)
from cognitive_kernel.contracts import ProductHostScope
from .authority_binding import bind_claim_source
from .experience import KurrentExperienceLog

_IDENTITIES = "fable_claim_identities"
_VERSIONS = "fable_claim_versions"
_CURRENT = "fable_current_claims"
_EVIDENCE = "fable_claim_evidence_relations"
_HEAD = "fable_claim_heads"


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _record_json(record: dict[str, object]) -> str:
    return json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _rows(cursor: Any) -> list[dict[str, object]]:
    names = [column.name for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def configure_xtdb_connection(connection: Any) -> None:
    """Bind Python strings as PostgreSQL TEXT for XTDB pgwire DML.

    Psycopg normally sends str parameters with OID 0 (unknown), which
    PostgreSQL can infer in most contexts. XTDB v2 requires non-null DML
    parameters to carry explicit type OIDs. A connection-local dumper keeps
    normal parameter binding while sending the PostgreSQL text OID.
    """
    from psycopg.types.string import StrDumper

    text_oid = connection.adapters.types["text"].oid

    class XTDBTextDumper(StrDumper):
        oid = text_oid

    connection.adapters.register_dumper(str, XTDBTextDumper)


def _dml_placeholder(value: object) -> str:
    return "%s::text" if isinstance(value, str) else "%s"


class XTDBClaimAuthority:
    """Bitemporal physical placement for one product/host claim namespace."""

    def __init__(
        self,
        *,
        scope: ProductHostScope,
        authority_namespace_id: str,
        connection: Any,
    ):
        scope.validate()
        self.scope = scope
        self.authority_namespace_id = require_identifier(
            authority_namespace_id, "authority_namespace_id"
        )
        self.connection = connection
        configure_xtdb_connection(self.connection)
        self.scope_digest = hashlib.sha256(
            (
                scope.storage_scope()
                + ":"
                + self.authority_namespace_id
            ).encode("utf-8")
        ).hexdigest()

    def _row_id(self, record_id: str) -> str:
        normalized = require_identifier(record_id, "record_id")
        return hashlib.sha256(
            f"{self.scope_digest}:{normalized}".encode("utf-8")
        ).hexdigest()

    def _assert_envelope(self, value: Any) -> None:
        value.validate()
        if value.envelope.scope != self.scope:
            raise ValueError("claim record belongs to a different host scope")
        if (
            value.envelope.authority_namespace_id
            != self.authority_namespace_id
        ):
            raise ValueError("claim record belongs to a different authority namespace")

    def _fetch_record(
        self,
        *,
        table: str,
        row_id: str,
        valid_time: datetime | None = None,
        all_valid: bool = False,
    ) -> dict[str, object] | None:
        if all_valid:
            sql = f"SELECT * FROM {table} FOR VALID_TIME ALL WHERE _id = %s"
            cursor = self.connection.execute(sql, (row_id,))
        elif valid_time is None:
            sql = f"SELECT * FROM {table} WHERE _id = %s"
            cursor = self.connection.execute(sql, (row_id,))
        else:
            sql = (
                f"SELECT * FROM {table} "
                "FOR VALID_TIME AS OF %s WHERE _id = %s"
            )
            cursor = self.connection.execute(sql, (valid_time, row_id))
        values = _rows(cursor)
        if not values:
            return None
        if len(values) != 1:
            raise ValueError("claim authority returned more than one current row")
        return values[0]

    def _insert_immutable(
        self,
        *,
        table: str,
        row_id: str,
        columns: dict[str, object],
        valid_from: datetime,
        valid_to: datetime | None,
    ) -> None:
        # XTDB INSERT is an upsert. Assert absence inside the same DML
        # transaction so a racing writer cannot replace an immutable record.
        with self.connection.transaction():
            self.connection.execute(
                f"ASSERT NOT EXISTS (SELECT 1 FROM {table} "
                "FOR VALID_TIME ALL WHERE _id = %s::text)",
                (row_id,),
            )
            self._insert(table=table, columns=columns,
                         valid_from=valid_from, valid_to=valid_to)

    def _insert(
        self,
        *,
        table: str,
        columns: dict[str, object],
        valid_from: datetime,
        valid_to: datetime | None,
    ) -> None:
        material = dict(columns)
        material["_valid_from"] = valid_from
        if valid_to is not None:
            material["_valid_to"] = valid_to
        names = tuple(material)
        placeholders = ", ".join(
            _dml_placeholder(material[name]) for name in names
        )
        sql = (
            f"INSERT INTO {table} ("
            + ", ".join(names)
            + f") VALUES ({placeholders})"
        )
        self.connection.execute(sql, tuple(material[name] for name in names))

    def put_identity(self, identity: ClaimIdentity) -> None:
        self._assert_envelope(identity)
        row_id = self._row_id(identity.claim_id)
        prior = self._fetch_record(table=_IDENTITIES, row_id=row_id, all_valid=True)
        if prior is not None:
            if str(prior["identity_sha256"]) != identity.identity_sha256:
                raise ValueError("claim identity is immutable")
            return
        self._insert_immutable(
            table=_IDENTITIES,
            row_id=row_id,
            columns={
                "_id": row_id,
                "scope_digest": self.scope_digest,
                "claim_id": identity.claim_id,
                "semantic_digest": identity.semantic_digest,
                "identity_sha256": identity.identity_sha256,
                "record_json": _record_json(identity.metadata_record()),
            },
            valid_from=_timestamp(identity.envelope.valid_from),
            valid_to=(
                None
                if identity.envelope.valid_to is None
                else _timestamp(identity.envelope.valid_to)
            ),
        )

    def put_version(self, version: ClaimVersion, *,
                    relations: Sequence[ClaimEvidenceRelation],
                    experience_log: KurrentExperienceLog) -> None:
        self._assert_envelope(version)
        if experience_log.scope != self.scope:
            raise ValueError("claim source log belongs to a different host")
        replayed = experience_log.replay()
        receipt = bind_claim_source(version=version, relations=relations,
                                    replayed=replayed)
        identity = self._fetch_record(
            table=_IDENTITIES, row_id=self._row_id(version.claim_id), all_valid=True)
        if identity is None:
            raise ValueError("claim version lacks a committed identity")
        for predecessor_id in version.correction_of:
            predecessor = self._fetch_record(
                table=_VERSIONS, row_id=self._row_id(predecessor_id), all_valid=True)
            if (predecessor is None or predecessor["claim_id"] != version.claim_id
                    or int(predecessor["version_sequence"]) >= version.version_sequence
                    or int(predecessor["event_stream_position"]) >= receipt.stream_position
                    or predecessor["experience_event_id"]
                    not in replayed[receipt.stream_position].parent_event_ids):
                raise ValueError("correction lacks its committed predecessor event")
        if version.adjudication_state in {"accepted", "revised"} and not version.evidence_relation_ids:
            raise ValueError("accepted or revised claim needs exact evidence relations")
        for relation_id in version.evidence_relation_ids:
            relation = self.load_evidence_relation(relation_id)
            submitted = next(r for r in relations if r.relation_id == relation_id)
            if relation["relation_sha256"] != submitted.relation_sha256:
                raise ValueError("persisted evidence relation differs from cited relation")
            if (relation["target_record_id"] != version.claim_version_id
                    or relation["target_record_type"] != "claim_version"
                    or relation["evidence_record_id"] not in version.envelope.source_records):
                raise ValueError("claim version evidence relation does not bind its source")
        row_id = self._row_id(version.claim_version_id)
        prior = self._fetch_record(table=_VERSIONS, row_id=row_id, all_valid=True)
        if prior is not None:
            if str(prior["version_sha256"]) != version.version_sha256:
                raise ValueError("claim version identifier was reused")
            return
        self._insert_immutable(
            table=_VERSIONS,
            row_id=row_id,
            columns={
                "_id": row_id,
                "scope_digest": self.scope_digest,
                "claim_id": version.claim_id,
                "claim_version_id": version.claim_version_id,
                "version_sequence": version.version_sequence,
                "store_sequence": version.store_sequence,
                "request_digest": version.request_digest,
                "experience_event_id": receipt.event_id,
                "event_stream_position": receipt.stream_position,
                "version_sha256": version.version_sha256,
                "record_json": _record_json(version.metadata_record()),
            },
            valid_from=_timestamp(version.envelope.valid_from),
            valid_to=(
                None
                if version.envelope.valid_to is None
                else _timestamp(version.envelope.valid_to)
            ),
        )

    def put_evidence_relation(self, relation: ClaimEvidenceRelation) -> None:
        self._assert_envelope(relation)
        row_id = self._row_id(relation.relation_id)
        prior = self._fetch_record(table=_EVIDENCE, row_id=row_id, all_valid=True)
        if prior is not None:
            if str(prior["relation_sha256"]) != relation.relation_sha256:
                raise ValueError("evidence relation identifier was reused")
            return
        self._insert_immutable(
            table=_EVIDENCE,
            row_id=row_id,
            columns={
                "_id": row_id,
                "scope_digest": self.scope_digest,
                "relation_id": relation.relation_id,
                "evidence_record_id": relation.evidence_record_id,
                "target_record_id": relation.target_record_id,
                "target_record_type": relation.target_record_type,
                "relation_type": relation.relation_type,
                "relation_sha256": relation.relation_sha256,
                "record_json": _record_json(relation.metadata_record()),
            },
            valid_from=_timestamp(relation.envelope.valid_from),
            valid_to=(None if relation.envelope.valid_to is None
                      else _timestamp(relation.envelope.valid_to)),
        )

    def load_evidence_relation(self, relation_id: str) -> dict[str, object]:
        row = self._fetch_record(table=_EVIDENCE, row_id=self._row_id(relation_id),
                                 all_valid=True)
        if row is None:
            raise KeyError(relation_id)
        return json.loads(str(row["record_json"]))

    def load_version(self, claim_version_id: str) -> dict[str, object]:
        row = self._fetch_record(
            table=_VERSIONS, row_id=self._row_id(claim_version_id), all_valid=True)
        if row is None:
            raise KeyError(claim_version_id)
        return json.loads(str(row["record_json"]))

    def put_current(self, projection: CurrentClaimProjection, *,
                    expected_previous: CurrentClaimProjection | None = None) -> None:
        self._assert_envelope(projection)
        valid_from = _timestamp(projection.envelope.valid_from)
        row_id = self._row_id(projection.claim_id)
        identity = self._fetch_record(table=_IDENTITIES,
                                      row_id=self._row_id(projection.claim_id), all_valid=True)
        version = self._fetch_record(table=_VERSIONS,
                                     row_id=self._row_id(projection.current_claim_version_id), all_valid=True)
        if identity is None or version is None or version["claim_id"] != projection.claim_id:
            raise ValueError("projection lacks committed identity and claim version")
        if int(version["store_sequence"]) > projection.source_position:
            raise ValueError("projection precedes the committed claim version")
        stored_version = json.loads(str(version["record_json"]))
        if stored_version["adjudication_state"] != projection.adjudication_state:
            raise ValueError("projection adjudication differs from the committed version")
        if stored_version["envelope"]["scope"] != self.scope.metadata_record():
            raise ValueError("stored version crosses the projection host")
        prior = self._fetch_record(table=_HEAD, row_id=row_id)
        if prior is not None and str(prior["projection_sha256"]) == projection.projection_sha256:
            return
        if expected_previous is None:
            if prior is not None or projection.projection_generation != 1:
                raise ValueError("claim head exists or initial generation is invalid")
        else:
            self._assert_envelope(expected_previous)
            if (prior is None or prior["projection_sha256"] != expected_previous.projection_sha256
                    or expected_previous.claim_id != projection.claim_id
                    or projection.projection_generation != expected_previous.projection_generation + 1
                    or expected_previous.projection_id not in projection.envelope.supersedes
                    or projection.source_position <= expected_previous.source_position):
                raise ValueError("stale or invalid expected claim head")

        columns = {
            "_id": row_id,
            "scope_digest": self.scope_digest,
            "claim_id": projection.claim_id,
            "current_claim_version_id": projection.current_claim_version_id,
            "projection_generation": projection.projection_generation,
            "source_position": projection.source_position,
            "projection_sha256": projection.projection_sha256,
            "record_json": _record_json(projection.metadata_record()),
        }
        valid_to = (None if projection.envelope.valid_to is None
                    else _timestamp(projection.envelope.valid_to))
        with self.connection.transaction():
            if expected_previous is None:
                self.connection.execute(
                    f"ASSERT NOT EXISTS (SELECT 1 FROM {_HEAD} WHERE _id = %s::text)",
                    (row_id,),
                )
            else:
                self.connection.execute(
                    f"ASSERT EXISTS (SELECT 1 FROM {_HEAD} WHERE _id = %s::text "
                    "AND projection_sha256 = %s::text)",
                    (row_id, expected_previous.projection_sha256),
                )
            self._insert(table=_CURRENT, columns=columns,
                         valid_from=valid_from, valid_to=valid_to)
            self._insert(table=_HEAD, columns=columns,
                         valid_from=valid_from, valid_to=None)

    def load_current(
        self,
        claim_id: str,
        *,
        as_of: datetime | None = None,
    ) -> dict[str, object]:
        row = self._fetch_record(
            table=_CURRENT,
            row_id=self._row_id(claim_id),
            valid_time=as_of,
        )
        if row is None:
            raise KeyError(claim_id)
        return json.loads(str(row["record_json"]))

    def current_history(self, claim_id: str) -> tuple[dict[str, object], ...]:
        cursor = self.connection.execute(
            f"SELECT record_json, _valid_from, _valid_to, "
            f"_system_from, _system_to FROM {_CURRENT} "
            "FOR VALID_TIME ALL FOR SYSTEM_TIME ALL "
            "WHERE _id = %s ORDER BY _system_from, _valid_from",
            (self._row_id(claim_id),),
        )
        result: list[dict[str, object]] = []
        for row in _rows(cursor):
            record = json.loads(str(row["record_json"]))
            record["_xtdb_valid_from"] = row["_valid_from"]
            record["_xtdb_valid_to"] = row["_valid_to"]
            record["_xtdb_system_from"] = row["_system_from"]
            record["_xtdb_system_to"] = row["_system_to"]
            result.append(record)
        return tuple(result)
