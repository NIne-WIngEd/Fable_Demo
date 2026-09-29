"""Evidence-bound personal-state candidates on the selected XTDB plane.

The product-neutral ProjectionVersion contract describes host, relationship,
and assistant-self derivatives. This registry stores their immutable lineage
and a serialized latest-candidate head. It does not promote a candidate into
judgment authority or claim that a learned updater produced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
from typing import Any, Mapping, Protocol

from cognitive_kernel.canonical import canonical_sha256, require_identifier
from cognitive_kernel.contracts import ProductHostScope
from cognitive_kernel.experience import ExperienceEvent
from cognitive_kernel.projection_contracts import ProjectionVersion

from .claims import (
    XTDBClaimAuthority, _dml_placeholder, _record_json, _rows,
    configure_xtdb_connection,
)
from .experience import KurrentExperienceLog
from .object_store import EncryptedObjectPlane, RawObjectReference
from .source_native import read_current_sources

_VERSIONS = "flora_personal_state_versions"
_HEADS = "flora_personal_state_candidate_heads"
_ACTIVE = "flora_personal_state_active_heads"
_TYPE_PAIRS = {
    "owner": "owner_model",
    "relationship": "relationship_model",
    "assistant_self": "self_model",
}


@dataclass(frozen=True)
class VerifiedStateCandidate:
    record: dict[str, object]
    content: bytes = field(repr=False)


class StateApprovalVerifier(Protocol):
    """Trusted local policy/authentication adapter, supplied by the product."""

    def authenticated_approval(self, event: ExperienceEvent,
                               request: dict[str, object]) -> bool: ...


def activation_request(record: Mapping[str, object], *,
                       expected_active_version_id: str | None) -> bytes:
    """Exact private approval payload; IDs and a digest, never state content."""
    if expected_active_version_id is not None:
        require_identifier(expected_active_version_id, "expected_active_version_id")
    material = {
        "schema": "flora-state-activation-v1",
        "subject_type": record["subject_type"],
        "subject_id": record["subject_id"],
        "projection_id": record["projection_id"],
        "candidate_version_id": record["version_id"],
        "candidate_sha256": record["projection_sha256"],
        "expected_active_version_id": expected_active_version_id,
    }
    return json.dumps(material, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


class XTDBPersonalStateCandidates:
    """Host-scoped candidate lineage, without a pretend judgment model."""

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

    def _version_id(self, version_id: str) -> str:
        return hashlib.sha256(
            f"{self.scope_digest}:version:{require_identifier(version_id, 'version_id')}".encode()
        ).hexdigest()

    def _head_id(self, subject_type: str, subject_id: str,
                 projection_id: str) -> str:
        for field_name, value in (("subject_type", subject_type),
                                  ("subject_id", subject_id),
                                  ("projection_id", projection_id)):
            require_identifier(value, field_name)
        return hashlib.sha256(
            f"{self.scope_digest}:{subject_type}:{subject_id}:{projection_id}".encode()
        ).hexdigest()

    def _fetch(self, table: str, row_id: str, *, all_valid: bool = False) -> dict | None:
        suffix = " FOR VALID_TIME ALL" if all_valid else ""
        rows = _rows(self.connection.execute(
            f"SELECT * FROM {table}{suffix} WHERE _id = %s", (row_id,)))
        if len(rows) > 1:
            raise ValueError("personal-state registry returned ambiguous row")
        return rows[0] if rows else None

    def _check_sources(
        self, *, source_claim_version_ids: tuple[str, ...],
        source_evidence_ids: tuple[str, ...], source_records: tuple[str, ...],
        claims: XTDBClaimAuthority, log: KurrentExperienceLog,
        objects: EncryptedObjectPlane,
        references: Mapping[str, RawObjectReference],
    ) -> None:
        if not (self.scope == claims.scope == log.scope == objects.scope):
            raise ValueError("personal-state sources cross host scope")
        if not set(source_claim_version_ids + source_evidence_ids).issubset(source_records):
            raise ValueError("personal-state envelope omits source lineage")
        replayed = {event.event_id: event for event in log.replay()}
        for version_id in source_claim_version_ids:
            version = claims.load_version(version_id)
            packet = read_current_sources(
                claim_id=version["claim_id"], authority=claims, log=log,
                objects=objects, references=references,
            )
            if packet.claim_version_id != version_id:
                raise ValueError("personal state cites a superseded claim")
        for event_id in source_evidence_ids:
            event = replayed.get(event_id)
            if event is None or event.payload_reference is None:
                raise ValueError("personal state cites absent Experience evidence")
            raw = references.get(event.payload_reference)
            if raw is None or raw.scope != self.scope:
                raise ValueError("personal state lacks its raw source")
            if hashlib.sha256(objects.get(raw)).hexdigest() != event.content_digest:
                raise ValueError("personal-state evidence differs from Experience")

    def put_candidate(
        self, version: ProjectionVersion, *, content: RawObjectReference,
        claims: XTDBClaimAuthority, log: KurrentExperienceLog,
        objects: EncryptedObjectPlane,
        references: Mapping[str, RawObjectReference],
        expected_previous_version_id: str | None = None,
    ) -> None:
        version.validate()
        if (version.scope != self.scope
                or version.envelope.authority_namespace_id != self.authority_namespace_id):
            raise ValueError("personal-state version crosses scope or namespace")
        if _TYPE_PAIRS.get(version.subject_type) != version.projection_type:
            raise ValueError("personal-state subject and projection type differ")
        if version.subject_type == "owner" and version.subject_id != self.scope.host_instance_id:
            raise ValueError("owner state belongs to a different host")
        if version.projection_state not in {"candidate", "shadow"}:
            raise ValueError("candidate registry cannot activate personal state")
        if version.source_episode_ids:
            raise ValueError("episode lineage awaits the selected episode plane")
        if (not version.source_claim_version_ids and not version.source_evidence_ids):
            raise ValueError("personal state needs implemented source lineage")
        if (content.scope != self.scope
                or version.content_digest != content.plaintext_sha256
                or version.envelope.content_digest != content.plaintext_sha256
                or hashlib.sha256(objects.get(content)).hexdigest() != version.content_digest):
            raise ValueError("personal-state content differs from encrypted raw object")
        self._check_sources(
            source_claim_version_ids=version.source_claim_version_ids,
            source_evidence_ids=version.source_evidence_ids,
            source_records=version.envelope.source_records,
            claims=claims, log=log, objects=objects, references=references,
        )
        row_id = self._version_id(version.version_id)
        prior = self._fetch(_VERSIONS, row_id, all_valid=True)
        if prior is not None:
            if (prior["projection_sha256"] != version.projection_sha256
                    or prior["content_object_id"] != content.object_id):
                raise ValueError("personal-state version ID was reused")
            return

        head_id = self._head_id(version.subject_type, version.subject_id,
                                version.projection_id)
        head = self._fetch(_HEADS, head_id)
        if expected_previous_version_id is None:
            if (head is not None or version.generation != 1
                    or version.supersedes_version_id is not None):
                raise ValueError("personal-state first generation conflicts with head")
        else:
            if (head is None or head["version_id"] != expected_previous_version_id
                    or version.supersedes_version_id != expected_previous_version_id
                    or version.generation != int(head["generation"]) + 1):
                raise ValueError("stale or invalid personal-state predecessor")

        valid_from = datetime.fromisoformat(version.valid_from.replace("Z", "+00:00"))
        material = {
            "_id": row_id, "scope_digest": self.scope_digest,
            "projection_id": version.projection_id,
            "subject_type": version.subject_type, "subject_id": version.subject_id,
            "version_id": version.version_id, "generation": version.generation,
            "projection_sha256": version.projection_sha256,
            "content_object_id": content.object_id,
            "record_json": _record_json(version.metadata_record()),
            "_valid_from": valid_from,
        }
        if version.valid_to is not None:
            material["_valid_to"] = datetime.fromisoformat(
                version.valid_to.replace("Z", "+00:00"))
        names = tuple(material)
        version_sql = (f"INSERT INTO {_VERSIONS} ({', '.join(names)}) VALUES ("
                       + ", ".join(_dml_placeholder(material[name]) for name in names)
                       + ")")
        head_material = {
            "_id": head_id, "scope_digest": self.scope_digest,
            "projection_id": version.projection_id,
            "subject_type": version.subject_type, "subject_id": version.subject_id,
            "version_id": version.version_id, "generation": version.generation,
            "projection_sha256": version.projection_sha256,
        }
        head_names = tuple(head_material)
        head_sql = (f"INSERT INTO {_HEADS} ({', '.join(head_names)}) VALUES ("
                    + ", ".join(_dml_placeholder(head_material[name])
                                  for name in head_names) + ")")
        with self.connection.transaction():
            if head is None:
                self.connection.execute(
                    f"ASSERT NOT EXISTS (SELECT 1 FROM {_HEADS} WHERE _id = %s::text)",
                    (head_id,),
                )
            else:
                self.connection.execute(
                    f"ASSERT EXISTS (SELECT 1 FROM {_HEADS} WHERE _id = %s::text "
                    "AND version_id = %s::text)",
                    (head_id, expected_previous_version_id),
                )
            self.connection.execute(
                f"ASSERT NOT EXISTS (SELECT 1 FROM {_VERSIONS} "
                "FOR VALID_TIME ALL WHERE _id = %s::text)", (row_id,),
            )
            self.connection.execute(version_sql, tuple(material.values()))
            self.connection.execute(head_sql, tuple(head_material.values()))

    def read_latest_candidate(
        self, *, subject_type: str, subject_id: str, projection_id: str,
        claims: XTDBClaimAuthority, log: KurrentExperienceLog,
        objects: EncryptedObjectPlane,
        references: Mapping[str, RawObjectReference],
    ) -> VerifiedStateCandidate:
        head = self._fetch(_HEADS, self._head_id(subject_type, subject_id,
                                                 projection_id))
        if head is None:
            raise KeyError(projection_id)
        return self._read_version(
            version_id=str(head["version_id"]),
            projection_sha256=str(head["projection_sha256"]),
            subject_type=subject_type, subject_id=subject_id,
            projection_id=projection_id, claims=claims, log=log,
            objects=objects, references=references,
        )

    def _read_version(
        self, *, version_id: str, projection_sha256: str,
        subject_type: str, subject_id: str, projection_id: str,
        claims: XTDBClaimAuthority, log: KurrentExperienceLog,
        objects: EncryptedObjectPlane,
        references: Mapping[str, RawObjectReference],
    ) -> VerifiedStateCandidate:
        row = self._fetch(_VERSIONS, self._version_id(version_id), all_valid=True)
        if row is None or row["projection_sha256"] != projection_sha256:
            raise ValueError("personal-state version is unbound")
        record = json.loads(str(row["record_json"]))
        if (record.get("projection_sha256") != row["projection_sha256"]
                or canonical_sha256({key: value for key, value in record.items()
                                     if key != "projection_sha256"})
                != row["projection_sha256"]
                or record["subject_type"] != subject_type
                or record["subject_id"] != subject_id
                or record["projection_id"] != projection_id
                or record["envelope"]["scope"] != self.scope.metadata_record()
                or record["envelope"]["authority_namespace_id"]
                != self.authority_namespace_id):
            raise ValueError("personal-state candidate record differs from its head")
        if record["source_episode_ids"]:
            raise ValueError("episode lineage awaits the selected episode plane")
        self._check_sources(
            source_claim_version_ids=tuple(record["source_claim_version_ids"]),
            source_evidence_ids=tuple(record["source_evidence_ids"]),
            source_records=tuple(record["envelope"]["source_records"]),
            claims=claims, log=log, objects=objects, references=references,
        )
        content = references.get(str(row["content_object_id"]))
        if content is None or content.scope != self.scope:
            raise ValueError("personal-state private content reference is absent")
        plaintext = objects.get(content)
        if hashlib.sha256(plaintext).hexdigest() != record["content_digest"]:
            raise ValueError("personal-state content digest differs")
        return VerifiedStateCandidate(record, plaintext)

    def _check_approval(
        self, *, approval_event_id: str, candidate: VerifiedStateCandidate,
        expected_active_version_id: str | None,
        log: KurrentExperienceLog, objects: EncryptedObjectPlane,
        references: Mapping[str, RawObjectReference],
        verifier: StateApprovalVerifier,
    ) -> ExperienceEvent:
        if log.scope != self.scope or objects.scope != self.scope:
            raise ValueError("state approval crosses host scope")
        event = next((item for item in log.replay()
                      if item.event_id == approval_event_id), None)
        if (event is None or event.event_type != "state_activation_approval"
                or event.payload_reference is None):
            raise ValueError("state activation lacks an approval event")
        reference = references.get(event.payload_reference)
        if reference is None or reference.scope != self.scope:
            raise ValueError("state activation lacks private approval content")
        material = activation_request(
            candidate.record,
            expected_active_version_id=expected_active_version_id,
        )
        if (objects.get(reference) != material
                or event.content_digest != hashlib.sha256(material).hexdigest()):
            raise ValueError("state approval does not bind the exact candidate")
        if (datetime.fromisoformat(event.occurred_at.replace("Z", "+00:00"))
                < datetime.fromisoformat(candidate.record["produced_at"].replace(
                    "Z", "+00:00"))):
            raise ValueError("state approval predates its candidate")
        if not verifier.authenticated_approval(event, json.loads(material)):
            raise ValueError("state activation was not independently authorized")
        return event

    def activate(
        self, *, subject_type: str, subject_id: str, projection_id: str,
        approval_event_id: str, expected_active_version_id: str | None,
        claims: XTDBClaimAuthority, log: KurrentExperienceLog,
        objects: EncryptedObjectPlane,
        references: Mapping[str, RawObjectReference],
        verifier: StateApprovalVerifier,
    ) -> VerifiedStateCandidate:
        """Activate a latest candidate after an exact independently verified approval."""
        candidate = self.read_latest_candidate(
            subject_type=subject_type, subject_id=subject_id,
            projection_id=projection_id, claims=claims, log=log,
            objects=objects, references=references,
        )
        event = self._check_approval(
            approval_event_id=approval_event_id, candidate=candidate,
            expected_active_version_id=expected_active_version_id,
            log=log, objects=objects, references=references, verifier=verifier,
        )
        head_id = self._head_id(subject_type, subject_id, projection_id)
        prior = self._fetch(_ACTIVE, head_id)
        version_id = str(candidate.record["version_id"])
        if (prior is not None and prior["version_id"] == version_id
                and prior["approval_event_id"] == event.event_id):
            return candidate
        if expected_active_version_id is None:
            if prior is not None:
                raise ValueError("active personal state already exists")
            generation = 1
        else:
            if (prior is None or prior["version_id"] != expected_active_version_id
                    or prior["version_id"] == version_id):
                raise ValueError("stale active personal-state predecessor")
            generation = int(prior["activation_generation"]) + 1
        columns = {
            "_id": head_id, "scope_digest": self.scope_digest,
            "subject_type": subject_type, "subject_id": subject_id,
            "projection_id": projection_id, "version_id": version_id,
            "projection_sha256": candidate.record["projection_sha256"],
            "activation_generation": generation,
            "approval_event_id": event.event_id,
            "approval_event_sha256": event.event_sha256,
            "expected_active_version_id": expected_active_version_id,
        }
        names = tuple(columns)
        sql = (f"INSERT INTO {_ACTIVE} ({', '.join(names)}) VALUES ("
               + ", ".join(_dml_placeholder(columns[name]) for name in names)
               + ")")
        with self.connection.transaction():
            if prior is None:
                self.connection.execute(
                    f"ASSERT NOT EXISTS (SELECT 1 FROM {_ACTIVE} WHERE _id = %s::text)",
                    (head_id,),
                )
            else:
                self.connection.execute(
                    f"ASSERT EXISTS (SELECT 1 FROM {_ACTIVE} WHERE _id = %s::text "
                    "AND version_id = %s::text AND approval_event_id = %s::text)",
                    (head_id, expected_active_version_id,
                     prior["approval_event_id"]),
                )
            self.connection.execute(sql, tuple(columns.values()))
        return candidate

    def read_active(
        self, *, subject_type: str, subject_id: str, projection_id: str,
        claims: XTDBClaimAuthority, log: KurrentExperienceLog,
        objects: EncryptedObjectPlane,
        references: Mapping[str, RawObjectReference],
        verifier: StateApprovalVerifier,
    ) -> VerifiedStateCandidate:
        """Revalidate both evidence and approval before a judgment can consume state."""
        head = self._fetch(_ACTIVE, self._head_id(subject_type, subject_id,
                                                  projection_id))
        if head is None:
            raise KeyError(projection_id)
        candidate = self._read_version(
            version_id=str(head["version_id"]),
            projection_sha256=str(head["projection_sha256"]),
            subject_type=subject_type, subject_id=subject_id,
            projection_id=projection_id, claims=claims, log=log,
            objects=objects, references=references,
        )
        event = self._check_approval(
            approval_event_id=str(head["approval_event_id"]),
            candidate=candidate,
            expected_active_version_id=head["expected_active_version_id"],
            log=log, objects=objects, references=references, verifier=verifier,
        )
        if event.event_sha256 != head["approval_event_sha256"]:
            raise ValueError("active personal-state approval event changed")
        return candidate
