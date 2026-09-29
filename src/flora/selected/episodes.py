"""Evidence-bound EpisodeRecord candidates in XTDB, without episode formation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
from typing import Any, Mapping

from cognitive_kernel.canonical import canonical_sha256, require_identifier
from cognitive_kernel.contracts import ProductHostScope
from cognitive_kernel.projection_contracts import EpisodeRecord

from .claims import (XTDBClaimAuthority, _dml_placeholder, _record_json,
                     _rows, configure_xtdb_connection)
from .experience import KurrentExperienceLog
from .object_store import EncryptedObjectPlane, RawObjectReference
from .source_native import read_current_sources

_VERSIONS = "flora_episode_candidates"
_HEADS = "flora_episode_candidate_heads"


@dataclass(frozen=True)
class VerifiedEpisodeCandidate:
    record: dict[str, object]
    summary: bytes = field(repr=False)
    content: bytes = field(repr=False)


class XTDBEpisodeCandidates:
    """Store externally supplied candidates, preserving raw source authority."""

    def __init__(self, *, scope: ProductHostScope,
                 authority_namespace_id: str, connection: Any):
        scope.validate()
        self.scope = scope
        self.authority_namespace_id = require_identifier(
            authority_namespace_id, "authority_namespace_id")
        self.connection = connection
        configure_xtdb_connection(connection)
        self.scope_digest = hashlib.sha256(
            f"{scope.storage_scope()}:{self.authority_namespace_id}".encode()
        ).hexdigest()

    def _key(self, kind: str, identifier: str) -> str:
        return hashlib.sha256(f"{self.scope_digest}:{kind}:"
                              f"{require_identifier(identifier, kind)}".encode()).hexdigest()

    def _fetch(self, table: str, key: str, *, all_valid: bool = False) -> dict | None:
        suffix = " FOR VALID_TIME ALL" if all_valid else ""
        rows = _rows(self.connection.execute(
            f"SELECT * FROM {table}{suffix} WHERE _id = %s", (key,)))
        if len(rows) > 1:
            raise ValueError("episode registry has an ambiguous row")
        return rows[0] if rows else None

    def _check_sources(self, record: Mapping[str, object], *,
                       claims: XTDBClaimAuthority, log: KurrentExperienceLog,
                       objects: EncryptedObjectPlane,
                       references: Mapping[str, RawObjectReference]) -> None:
        if not (self.scope == claims.scope == log.scope == objects.scope):
            raise ValueError("episode sources cross host scope")
        events = tuple(record["member_evidence_ids"])
        versions = tuple(record["member_claim_version_ids"])
        if (not events and not versions) or record["member_candidate_ids"]:
            raise ValueError("episode needs supported evidence or claim lineage")
        if not set(events + versions).issubset(record["envelope"]["source_records"]):
            raise ValueError("episode envelope omits source lineage")
        replayed = {event.event_id: event for event in log.replay()}
        for event_id in events:
            event = replayed.get(event_id)
            if event is None or event.payload_reference is None:
                raise ValueError("episode cites absent Experience evidence")
            if datetime.fromisoformat(event.occurred_at.replace("Z", "+00:00")) > datetime.fromisoformat(str(record["formed_at"]).replace("Z", "+00:00")):
                raise ValueError("episode cites evidence observed after formation")
            raw = references.get(event.payload_reference)
            if (raw is None or raw.scope != self.scope
                    or hashlib.sha256(objects.get(raw)).hexdigest()
                    != event.content_digest):
                raise ValueError("episode evidence differs from raw Experience")
        for version_id in versions:
            version = claims.load_version(version_id)
            packet = read_current_sources(
                claim_id=version["claim_id"], authority=claims, log=log,
                objects=objects, references=references)
            if packet.claim_version_id != version_id:
                raise ValueError("episode cites a superseded claim")

    def put_candidate(self, episode: EpisodeRecord, *, thread_id: str,
                      summary: RawObjectReference, content: RawObjectReference,
                      claims: XTDBClaimAuthority, log: KurrentExperienceLog,
                      objects: EncryptedObjectPlane,
                      references: Mapping[str, RawObjectReference],
                      expected_previous_episode_id: str | None = None) -> None:
        episode.validate()
        require_identifier(thread_id, "thread_id")
        if (episode.scope != self.scope or episode.envelope.authority_namespace_id
                != self.authority_namespace_id or episode.episode_state != "candidate"):
            raise ValueError("episode candidate crosses scope or asserts acceptance")
        if (summary.scope != self.scope or content.scope != self.scope
                or summary.plaintext_sha256 != episode.summary_content_digest
                or content.plaintext_sha256 != episode.full_content_digest
                or episode.envelope.content_digest != episode.full_content_digest
                or hashlib.sha256(objects.get(summary)).hexdigest()
                != episode.summary_content_digest
                or hashlib.sha256(objects.get(content)).hexdigest()
                != episode.full_content_digest):
            raise ValueError("episode candidate content differs from encrypted objects")
        record = episode.metadata_record()
        self._check_sources(record, claims=claims, log=log,
                            objects=objects, references=references)
        version_key = self._key("episode", episode.episode_id)
        head_key = self._key("thread", thread_id)
        prior = self._fetch(_VERSIONS, version_key, all_valid=True)
        if prior is not None:
            if (prior["episode_sha256"] != episode.episode_sha256
                    or prior["thread_id"] != thread_id
                    or prior["summary_object_id"] != summary.object_id
                    or prior["content_object_id"] != content.object_id):
                raise ValueError("episode ID was reused")
            return
        head = self._fetch(_HEADS, head_key)
        if expected_previous_episode_id is None:
            if (head is not None or episode.generation != 1
                    or episode.supersedes_episode_id is not None):
                raise ValueError("episode first generation conflicts with head")
        elif (head is None or head["episode_id"] != expected_previous_episode_id
              or episode.supersedes_episode_id != expected_previous_episode_id
              or episode.generation != int(head["generation"]) + 1):
            raise ValueError("stale episode predecessor")
        columns = {
            "_id": version_key, "scope_digest": self.scope_digest,
            "thread_id": thread_id,
            "episode_id": episode.episode_id, "generation": episode.generation,
            "episode_sha256": episode.episode_sha256,
            "summary_object_id": summary.object_id,
            "content_object_id": content.object_id,
            "record_json": _record_json(record),
            "_valid_from": datetime.fromisoformat(
                episode.valid_from.replace("Z", "+00:00")),
        }
        if episode.valid_to is not None:
            columns["_valid_to"] = datetime.fromisoformat(
                episode.valid_to.replace("Z", "+00:00"))
        head_columns = {
            "_id": head_key, "scope_digest": self.scope_digest,
            "thread_id": thread_id,
            "episode_id": episode.episode_id, "generation": episode.generation,
            "episode_sha256": episode.episode_sha256,
        }
        def statement(table: str, values: dict[str, object]) -> str:
            return (f"INSERT INTO {table} ({', '.join(values)}) VALUES ("
                    + ", ".join(_dml_placeholder(v) for v in values.values()) + ")")
        with self.connection.transaction():
            if head is None:
                self.connection.execute(
                    f"ASSERT NOT EXISTS (SELECT 1 FROM {_HEADS} WHERE _id = %s::text)",
                    (head_key,))
            else:
                self.connection.execute(
                    f"ASSERT EXISTS (SELECT 1 FROM {_HEADS} WHERE _id = %s::text "
                    "AND episode_id = %s::text)",
                    (head_key, expected_previous_episode_id))
            self.connection.execute(
                f"ASSERT NOT EXISTS (SELECT 1 FROM {_VERSIONS} "
                "FOR VALID_TIME ALL WHERE _id = %s::text)", (version_key,))
            self.connection.execute(statement(_VERSIONS, columns), tuple(columns.values()))
            self.connection.execute(statement(_HEADS, head_columns),
                                    tuple(head_columns.values()))

    def read_latest_candidate(self, *, thread_id: str,
                              claims: XTDBClaimAuthority,
                              log: KurrentExperienceLog,
                              objects: EncryptedObjectPlane,
                              references: Mapping[str, RawObjectReference]) -> VerifiedEpisodeCandidate:
        head = self._fetch(_HEADS, self._key("thread", thread_id))
        if head is None:
            raise KeyError(thread_id)
        row = self._fetch(_VERSIONS, self._key("episode", head["episode_id"]),
                          all_valid=True)
        if row is None or row["episode_sha256"] != head["episode_sha256"]:
            raise ValueError("episode candidate head is unbound")
        record = json.loads(row["record_json"])
        if (record["episode_sha256"] != row["episode_sha256"]
                or canonical_sha256({key: value for key, value in record.items()
                                     if key != "episode_sha256"})
                != row["episode_sha256"]
                or row["thread_id"] != thread_id
                or record["envelope"]["scope"] != self.scope.metadata_record()
                or record["envelope"]["authority_namespace_id"]
                != self.authority_namespace_id):
            raise ValueError("episode candidate metadata differs from head")
        self._check_sources(record, claims=claims, log=log,
                            objects=objects, references=references)
        summary = references.get(row["summary_object_id"])
        content = references.get(row["content_object_id"])
        if (summary is None or content is None or summary.scope != self.scope
                or content.scope != self.scope):
            raise ValueError("episode private content reference is absent")
        summary_bytes, content_bytes = objects.get(summary), objects.get(content)
        if (hashlib.sha256(summary_bytes).hexdigest()
                != record["summary_content_digest"]
                or hashlib.sha256(content_bytes).hexdigest()
                != record["full_content_digest"]):
            raise ValueError("episode candidate content changed")
        return VerifiedEpisodeCandidate(record, summary_bytes, content_bytes)
