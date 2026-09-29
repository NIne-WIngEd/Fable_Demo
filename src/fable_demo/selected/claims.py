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
from typing import Any

from cognitive_kernel.canonical import require_identifier
from cognitive_kernel.claim_contracts import (
    ClaimIdentity,
    ClaimVersion,
    CurrentClaimProjection,
)
from cognitive_kernel.contracts import ProductHostScope

_IDENTITIES = "fable_claim_identities"
_VERSIONS = "fable_claim_versions"
_CURRENT = "fable_current_claims"


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


def _dml_placeholder(value: object) -> str:
    """Give XTDB pgwire an explicit type for Python strings in DML.

    Psycopg intentionally sends ordinary Python strings with an unknown OID.
    PostgreSQL usually infers that type from a table schema. XTDB's DML
    protocol requires every non-null parameter to arrive typed, so text values
    are explicitly cast while native integer/timestamp parameters keep their
    driver-provided OIDs.
    """
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
    ) -> dict[str, object] | None:
        if valid_time is None:
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
        prior = self._fetch_record(table=_IDENTITIES, row_id=row_id)
        if prior is not None:
            if str(prior["identity_sha256"]) != identity.identity_sha256:
                raise ValueError("claim identity is immutable")
            return
        self._insert(
            table=_IDENTITIES,
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

    def put_version(self, version: ClaimVersion) -> None:
        self._assert_envelope(version)
        row_id = self._row_id(version.claim_version_id)
        prior = self._fetch_record(table=_VERSIONS, row_id=row_id)
        if prior is not None:
            if str(prior["version_sha256"]) != version.version_sha256:
                raise ValueError("claim version identifier was reused")
            return
        self._insert(
            table=_VERSIONS,
            columns={
                "_id": row_id,
                "scope_digest": self.scope_digest,
                "claim_id": version.claim_id,
                "claim_version_id": version.claim_version_id,
                "version_sequence": version.version_sequence,
                "store_sequence": version.store_sequence,
                "request_digest": version.request_digest,
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

    def put_current(self, projection: CurrentClaimProjection) -> None:
        self._assert_envelope(projection)
        valid_from = _timestamp(projection.envelope.valid_from)
        row_id = self._row_id(projection.claim_id)
        prior = self._fetch_record(
            table=_CURRENT,
            row_id=row_id,
            valid_time=valid_from,
        )
        if prior is not None and (
            str(prior["projection_sha256"]) == projection.projection_sha256
        ):
            return
        self._insert(
            table=_CURRENT,
            columns={
                "_id": row_id,
                "scope_digest": self.scope_digest,
                "claim_id": projection.claim_id,
                "current_claim_version_id": projection.current_claim_version_id,
                "projection_generation": projection.projection_generation,
                "source_position": projection.source_position,
                "projection_sha256": projection.projection_sha256,
                "record_json": _record_json(projection.metadata_record()),
            },
            valid_from=valid_from,
            valid_to=(
                None
                if projection.envelope.valid_to is None
                else _timestamp(projection.envelope.valid_to)
            ),
        )

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
