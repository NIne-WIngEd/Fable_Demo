"""Shared namespace sequence/CAS for governed Claim authority mutations.

Authority order is not a Kurrent stream position. Allocation is only committed
inside the caller's one XTDB transaction with the exact authority mutation and
its immutable receipt. It confers no semantic or owner authorization.
"""
from __future__ import annotations

from dataclasses import dataclass
import json

from cognitive_kernel.canonical import canonical_sha256, normalize_timestamp
from .claims import XTDBClaimAuthority, _CURRENT, _HEAD, _VERSIONS, _record_json, _rows, _timestamp

_COUNTER = "flora_claim_admission_namespace_counters"
_CONTROLLER = "flora-governed-claim-admission-v1"
_COUNTER_ID = "admission-namespace-counter"
_INVENTORIES = ((_VERSIONS, "store_sequence"), (_CURRENT, "source_position"), (_HEAD, "source_position"))


@dataclass(frozen=True)
class ClaimSequenceAllocation:
    scope_digest: str
    sequence: int
    expected_counter_sha256: str | None


class XTDBClaimSequenceController:
    def __init__(self, authority: XTDBClaimAuthority):
        self.authority = authority

    def _counter(self):
        authority = self.authority
        row = authority._fetch_record(table=_COUNTER, row_id=authority._row_id(_COUNTER_ID))
        if row is None:
            return None
        record = json.loads(str(row["record_json"]))
        if (row["_id"] != authority._row_id(_COUNTER_ID) or row["scope_digest"] != authority.scope_digest
                or record.get("scope") != authority.scope.metadata_record()
                or record.get("authority_namespace_id") != authority.authority_namespace_id
                or record.get("schema") != "flora-claim-sequence-v1" or record.get("controller_id") != _CONTROLLER
                or record.get("record_sha256") != row["record_sha256"]
                or canonical_sha256({k: v for k, v in record.items() if k != "record_sha256"}) != row["record_sha256"]):
            raise ValueError("Claim namespace has a different sequence controller or changed binding")
        last = record.get("last_store_sequence")
        if isinstance(last, bool) or not isinstance(last, int) or last < 1 or last >= 2**63 - 1:
            raise ValueError("invalid or exhausted Claim namespace sequence counter")
        return record

    def prepare(self, *, require_existing: bool = False) -> ClaimSequenceAllocation:
        authority, counter = self.authority, self._counter()
        if require_existing and counter is None:
            raise ValueError("governed Claim mutation needs an established namespace controller")
        last = 0 if counter is None else counter["last_store_sequence"]
        for table, column in _INVENTORIES:
            rows = _rows(authority.connection.execute(
                f"SELECT MAX(CAST({column} AS BIGINT)) AS maximum FROM {table} FOR VALID_TIME ALL "
                "WHERE scope_digest = %s::text", (authority.scope_digest,)))
            if len(rows) != 1 or "maximum" not in rows[0]:
                raise ValueError("Claim namespace sequence inventory is unavailable")
            maximum = rows[0]["maximum"]
            if maximum is not None and (isinstance(maximum, bool) or not isinstance(maximum, int)
                                        or maximum < 1 or maximum > last):
                raise ValueError("Claim namespace contains an untracked store sequence")
        return ClaimSequenceAllocation(authority.scope_digest, last + 1,
                                       None if counter is None else counter["record_sha256"])

    def assert_allocation(self, allocation: ClaimSequenceAllocation) -> None:
        """Run in the same top-level DML transaction as the authority writes."""
        authority = self.authority
        if (allocation.scope_digest != authority.scope_digest or isinstance(allocation.sequence, bool)
                or not isinstance(allocation.sequence, int) or not 1 <= allocation.sequence < 2**63):
            raise ValueError("Claim sequence allocation crosses namespace or range")
        counter_key = authority._row_id(_COUNTER_ID)
        if allocation.expected_counter_sha256 is None:
            if allocation.sequence != 1:
                raise ValueError("first Claim allocation must be one")
            authority.connection.execute(
                f"ASSERT NOT EXISTS (SELECT 1 FROM {_COUNTER} FOR VALID_TIME ALL WHERE _id = %s::text)",
                (counter_key,))
            for table, _ in _INVENTORIES:
                authority.connection.execute(
                    f"ASSERT NOT EXISTS (SELECT 1 FROM {table} FOR VALID_TIME ALL WHERE scope_digest = %s::text)",
                    (authority.scope_digest,))
        else:
            expected = {"scope": authority.scope.metadata_record(),
                "authority_namespace_id": authority.authority_namespace_id,
                "schema": "flora-claim-sequence-v1", "controller_id": _CONTROLLER,
                "last_store_sequence": allocation.sequence - 1}
            if canonical_sha256(expected) != allocation.expected_counter_sha256:
                raise ValueError("Claim allocation does not follow its exact counter")
            authority.connection.execute(
                f"ASSERT EXISTS (SELECT 1 FROM {_COUNTER} WHERE _id = %s::text AND record_sha256 = %s::text)",
                (counter_key, allocation.expected_counter_sha256))
            for table, column in _INVENTORIES:
                authority.connection.execute(
                    f"ASSERT NOT EXISTS (SELECT 1 FROM {table} FOR VALID_TIME ALL "
                    f"WHERE scope_digest = %s::text AND {column} >= %s::bigint)",
                    (authority.scope_digest, allocation.sequence))

    def write_allocation(self, allocation: ClaimSequenceAllocation, *, at: str) -> None:
        """Write the counter in its caller's existing authority transaction."""
        authority = self.authority
        if allocation.scope_digest != authority.scope_digest:
            raise ValueError("Claim sequence counter crosses namespace")
        at = normalize_timestamp(at)
        record = {"scope": authority.scope.metadata_record(), "authority_namespace_id": authority.authority_namespace_id,
            "schema": "flora-claim-sequence-v1", "controller_id": _CONTROLLER,
            "last_store_sequence": allocation.sequence}
        record["record_sha256"] = canonical_sha256(record)
        authority._insert(table=_COUNTER, columns={"_id": authority._row_id(_COUNTER_ID),
            "scope_digest": authority.scope_digest, "record_sha256": record["record_sha256"],
            "record_json": _record_json(record)}, valid_from=_timestamp(at), valid_to=None)
