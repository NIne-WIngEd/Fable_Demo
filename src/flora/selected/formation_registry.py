"""Selected XTDB registration and encrypted custody for MFM source evidence.

The trusted ingress service registers metadata; the MFM only resolves sources.
Registration is immutable and binds the actual Kurrent event and commit time.
Read permission remains the independent policy of RegisteredFormationStore.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Any, Protocol

from cognitive_kernel.canonical import canonical_sha256, normalize_timestamp, require_identifier, require_sha256
from cognitive_kernel.contracts import ProductHostScope
from cognitive_kernel.experience import ExperienceEvent
from cognitive_kernel.formation_contracts import FormationEvidenceRef
from cognitive_kernel.formation_sources import RegisteredFormationSource

from .claims import _dml_placeholder, _record_json, _rows, configure_xtdb_connection
from .experience import KurrentExperienceLog
from .object_store import EncryptedObjectPlane, RawObjectReference

_SOURCES = "flora_registered_formation_sources"
_OBJECTS = "flora_formation_raw_references"
_ELEVATED_ROLES = {"authenticated_owner_statement", "owner_attested_source_person"}
_ROLE_ORIGINS = {
    "generated_reconstruction": {"generated_reconstruction", "hypothetical_training"},
    "derived_inference": {"derived_inference", "historical_experience", "outside_source",
                          "tool_or_action_observation", "assistant_self_event"},
    "owner_attested_canonical": _ELEVATED_ROLES | {"historical_experience"},
    "owner_correction": _ELEVATED_ROLES | {"historical_experience"},
    "evolved_identity": {"assistant_self_event", "derived_inference", "historical_experience"},
    "conflict_or_uncertain": {"historical_experience", "derived_inference"},
}


@dataclass(frozen=True)
class CanonicalSourceCommitment:
    """Fresh registered locator, not proof of current Kurrent or permission.

    Position, envelope digest and commit time were bound during trusted source
    registration. A consumer must still obtain an exact physical event proof
    and independently check present-use authority before opening any bytes.
    This record carries no stream head, checkpoint or cached allow result.
    """

    source: RegisteredFormationSource
    event_sha256: str
    stream_position: int
    recorded_at: str

    def validate(self) -> None:
        self.source.validate()
        if require_sha256(self.event_sha256, "event_sha256") != self.event_sha256:
            raise ValueError("registered event digest must be canonical")
        if self.source.evidence.ref_id != f"experience-{self.event_sha256[:32]}":
            raise ValueError("registered event digest does not bind its source ID")
        if (isinstance(self.stream_position, bool)
                or not isinstance(self.stream_position, int)
                or self.stream_position < 0):
            raise ValueError("registered event position must be a nonnegative integer")
        if (normalize_timestamp(self.recorded_at, "recorded_at") != self.recorded_at
                or self.recorded_at != self.source.evidence.recorded_at):
            raise ValueError("registered commit time must bind canonical source metadata")


class OwnerFormationSourceVerifier(Protocol):
    """Independent identity/source authority, never a claim from an inference."""

    def authenticated_owner_source(self, event: ExperienceEvent,
                                   evidence: FormationEvidenceRef) -> bool: ...


def _evidence_from_record(record: dict[str, object]) -> FormationEvidenceRef:
    scope = ProductHostScope.create(**record["scope"])
    material = {key: value for key, value in record.items() if key != "scope"}
    material["parent_refs"] = tuple(material["parent_refs"])
    evidence = FormationEvidenceRef(scope=scope, **material)
    evidence.validate()
    if evidence.metadata_record() != record:
        raise ValueError("formation evidence metadata is not canonical")
    return evidence


class XTDBFormationSourceRegistry:
    """Host/authority-scoped immutable sources and durable raw references.

    This registration interface belongs to trusted ingestion. It is not an
    inference endpoint. Subject, speaker and duplicate metadata must come from
    that ingestion service; an unknown field stays None rather than being
    invented from model output. Elevated owner roles additionally require an
    independent verifier and matching original Experience provenance.
    """

    def __init__(self, *, scope: ProductHostScope,
                 authority_namespace_id: str, connection: Any):
        scope.validate()
        self.scope = scope
        self.authority_namespace_id = require_identifier(
            authority_namespace_id, "authority_namespace_id")
        self.connection = connection
        configure_xtdb_connection(connection)
        self.scope_digest = hashlib.sha256(
            f"{scope.storage_scope()}:{self.authority_namespace_id}".encode()).hexdigest()

    def _key(self, kind: str, identifier: str) -> str:
        return hashlib.sha256(
            f"{self.scope_digest}:{kind}:{require_identifier(identifier, kind)}".encode()
        ).hexdigest()

    def _fetch(self, table: str, key: str) -> dict[str, object] | None:
        rows = _rows(self.connection.execute(
            f"SELECT * FROM {table} FOR VALID_TIME ALL WHERE _id = %s", (key,)))
        if len(rows) > 1:
            raise ValueError("formation registry contains ambiguous immutable rows")
        return rows[0] if rows else None

    def _decode(self, row: dict[str, object], *, expected_key: str) -> dict[str, object]:
        record = json.loads(str(row["record_json"]))
        if (row["_id"] != expected_key or row["scope_digest"] != self.scope_digest
                or record["scope"] != self.scope.metadata_record()
                or record["authority_namespace_id"] != self.authority_namespace_id
                or record["record_sha256"] != row["record_sha256"]
                or canonical_sha256({key: value for key, value in record.items()
                                     if key != "record_sha256"}) != row["record_sha256"]):
            raise ValueError("formation registry immutable metadata changed")
        return record

    def _insert(self, table: str, key: str, record: dict[str, object]) -> None:
        values = {"_id": key, "scope_digest": self.scope_digest,
                  "record_sha256": record["record_sha256"],
                  "record_json": _record_json(record)}
        self.connection.execute(
            f"INSERT INTO {table} ({', '.join(values)}) VALUES ("
            + ", ".join(_dml_placeholder(value) for value in values.values()) + ")",
            tuple(values.values()))

    def register(self, *, evidence: FormationEvidenceRef, raw: RawObjectReference,
                 log: KurrentExperienceLog, objects: EncryptedObjectPlane,
                 owner_verifier: OwnerFormationSourceVerifier | None = None) -> RegisteredFormationSource:
        evidence.validate()
        require_sha256(raw.object_id, "object_id")
        require_sha256(raw.plaintext_sha256, "plaintext_sha256")
        if isinstance(raw.size, bool) or not isinstance(raw.size, int) or raw.size < 0:
            raise ValueError("formation raw reference size must be a nonnegative integer")
        if (not self.scope == evidence.scope == raw.scope == log.scope == objects.scope
                or evidence.authority_namespace_id != self.authority_namespace_id):
            raise ValueError("formation source registration crosses scope or authority")
        committed = log.replay_committed()
        matched = next((entry for entry in committed
                        if entry.event.event_id == evidence.ref_id), None)
        if matched is None:
            raise ValueError("formation source is absent from committed Experience")
        event = matched.event
        event.validate()
        if (matched.recorded_at is None or not isinstance(matched.recorded_at, datetime)
                or matched.recorded_at.tzinfo is None
                or matched.recorded_at.utcoffset() is None):
            raise ValueError("formation source lacks an aware Kurrent commit timestamp")
        recorded_at = normalize_timestamp(matched.recorded_at.isoformat(), "recorded_at")
        if (event.payload_reference != raw.object_id
                or event.content_digest != raw.plaintext_sha256
                or evidence.content_digest != event.content_digest
                or evidence.observed_at != event.occurred_at
                or evidence.recorded_at != recorded_at
                or evidence.parent_refs != event.parent_event_ids):
            raise ValueError("formation evidence differs from committed source metadata")
        earlier_ids = {entry.event.event_id for entry in committed
                       if entry.stream_position < matched.stream_position}
        if not set(evidence.parent_refs).issubset(earlier_ids):
            raise ValueError("formation source has absent or later causal parents")
        if (evidence.source_item_ref is not None
                and evidence.source_item_ref not in set(event.provenance.source_reference_ids)
                | {raw.object_id}):
            raise ValueError("formation source item is absent from original provenance")
        allowed = _ROLE_ORIGINS.get(event.provenance.provenance_type, set())
        if evidence.role not in allowed:
            raise ValueError("formation role differs from original source provenance")
        if evidence.role in _ELEVATED_ROLES:
            if (owner_verifier is None or not owner_verifier.authenticated_owner_source(event, evidence)):
                raise ValueError("formation owner source is not independently authenticated")
            if evidence.role == "authenticated_owner_statement" and (
                    evidence.speaker_ref != self.scope.host_instance_id):
                raise ValueError("authenticated owner statement has a different speaker")
        plaintext = objects.get(raw)
        if hashlib.sha256(plaintext).hexdigest() != event.content_digest:
            raise ValueError("formation raw object differs from committed evidence")
        ciphertext = objects.backend.get_object(objects.namespace, raw.object_id)
        raw_record: dict[str, object] = {
            "schema": "flora-formation-raw-reference-v1",
            "scope": self.scope.metadata_record(),
            "authority_namespace_id": self.authority_namespace_id,
            "object_id": raw.object_id, "plaintext_sha256": raw.plaintext_sha256,
            "size": raw.size, "object_namespace": objects.namespace,
            "cipher_format": "FBO1-AES-256-GCM",
            "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
            "ciphertext_size": len(ciphertext),
        }
        raw_record["record_sha256"] = canonical_sha256(raw_record)
        source = RegisteredFormationSource.create(evidence=evidence, object_ref=raw.object_id)
        source_record: dict[str, object] = {
            "schema": "flora-registered-formation-source-v1",
            "scope": self.scope.metadata_record(),
            "authority_namespace_id": self.authority_namespace_id,
            "evidence": evidence.metadata_record(), "object_ref": source.object_ref,
            "registration_sha256": source.registration_sha256,
            "event_sha256": event.event_sha256,
            "event_stream_position": matched.stream_position,
            "raw_reference_sha256": raw_record["record_sha256"],
        }
        source_record["record_sha256"] = canonical_sha256(source_record)
        source_key = self._key("source", evidence.ref_id)
        raw_key = self._key("raw", raw.object_id)
        prior_source, prior_raw = self._fetch(_SOURCES, source_key), self._fetch(_OBJECTS, raw_key)
        if prior_raw is not None and self._decode(prior_raw, expected_key=raw_key) != raw_record:
            raise ValueError("formation raw reference is immutable")
        if prior_source is not None:
            if (self._decode(prior_source, expected_key=source_key) != source_record
                    or prior_raw is None):
                raise ValueError("formation source registration is immutable or unbound")
            return source
        with self.connection.transaction():
            self.connection.execute(
                f"ASSERT NOT EXISTS (SELECT 1 FROM {_SOURCES} FOR VALID_TIME ALL WHERE _id = %s::text)",
                (source_key,))
            if prior_raw is None:
                self.connection.execute(
                    f"ASSERT NOT EXISTS (SELECT 1 FROM {_OBJECTS} FOR VALID_TIME ALL WHERE _id = %s::text)",
                    (raw_key,))
                self._insert(_OBJECTS, raw_key, raw_record)
            else:
                self.connection.execute(
                    f"ASSERT EXISTS (SELECT 1 FROM {_OBJECTS} FOR VALID_TIME ALL "
                    "WHERE _id = %s::text AND record_sha256 = %s::text)",
                    (raw_key, raw_record["record_sha256"]))
            self._insert(_SOURCES, source_key, source_record)
        return source

    def lookup(self, ref_id: str) -> RegisteredFormationSource | None:
        key = self._key("source", ref_id)
        row = self._fetch(_SOURCES, key)
        if row is None:
            return None
        record = self._decode(row, expected_key=key)
        if record["schema"] != "flora-registered-formation-source-v1":
            raise ValueError("formation source registration schema changed")
        evidence = _evidence_from_record(record["evidence"])
        source = RegisteredFormationSource.create(evidence=evidence, object_ref=record["object_ref"])
        if (evidence.ref_id != ref_id or evidence.scope != self.scope
                or evidence.authority_namespace_id != self.authority_namespace_id
                or source.registration_sha256 != record["registration_sha256"]):
            raise ValueError("formation source registration does not bind its lookup")
        raw_record = self.raw_metadata(source.object_ref)
        if (raw_record is None or raw_record["record_sha256"] != record["raw_reference_sha256"]
                or raw_record["plaintext_sha256"] != evidence.content_digest):
            raise ValueError("formation source has no exact durable raw reference")
        return source

    def lookup_commitment(self, ref_id: str) -> CanonicalSourceCommitment | None:
        """Read the existing canonical source/raw rows and expose their locator.

        This is a separate metadata API. The established ``lookup`` reader and
        its callback order remain unchanged. No Kurrent read or plaintext I/O
        occurs here, and a self-consistent registry row is not by itself proof
        that the corresponding physical event still exists.
        """
        scope, namespace, connection = self.scope, self.authority_namespace_id, self.connection
        scope_digest, scope_record = self.scope_digest, scope.metadata_record()
        readers = tuple((name, getattr(self, name)) for name in (
            "_key", "_fetch", "_decode", "raw_metadata", "lookup_commitment"))
        def require_binding() -> None:
            if (self.scope is not scope or self.authority_namespace_id != namespace
                    or self.connection is not connection or self.scope_digest != scope_digest
                    or scope.metadata_record() != scope_record
                    or any(getattr(self, name) != reader for name, reader in readers)):
                raise ValueError("formation source commitment reader binding changed")
        require_binding()
        key = self._key("source", ref_id)
        require_binding()
        row = self._fetch(_SOURCES, key)
        require_binding()
        if row is None:
            return None
        record = self._decode(row, expected_key=key)
        require_binding()
        if record["schema"] != "flora-registered-formation-source-v1":
            raise ValueError("formation source registration schema changed")
        evidence = _evidence_from_record(record["evidence"])
        source = RegisteredFormationSource.create(evidence=evidence, object_ref=record["object_ref"])
        if (evidence.ref_id != ref_id or evidence.scope != self.scope
                or evidence.authority_namespace_id != self.authority_namespace_id
                or source.registration_sha256 != record["registration_sha256"]):
            raise ValueError("formation source registration does not bind its lookup")
        raw_record = self.raw_metadata(source.object_ref)
        require_binding()
        if (raw_record is None or raw_record["record_sha256"] != record["raw_reference_sha256"]
                or raw_record["plaintext_sha256"] != evidence.content_digest):
            raise ValueError("formation source has no exact durable raw reference")
        commitment = CanonicalSourceCommitment(
            source=source, event_sha256=record["event_sha256"],
            stream_position=record["event_stream_position"],
            recorded_at=evidence.recorded_at)
        commitment.validate()
        require_binding()
        return commitment

    def raw_metadata(self, object_ref: str) -> dict[str, object] | None:
        key = self._key("raw", object_ref)
        row = self._fetch(_OBJECTS, key)
        if row is None:
            return None
        record = self._decode(row, expected_key=key)
        if (record["schema"] != "flora-formation-raw-reference-v1"
                or record["object_id"] != object_ref
                or record["cipher_format"] != "FBO1-AES-256-GCM"):
            raise ValueError("formation raw reference differs from its object lookup")
        require_sha256(record["object_id"], "object_id")
        require_sha256(record["plaintext_sha256"], "plaintext_sha256")
        require_sha256(record["ciphertext_sha256"], "ciphertext_sha256")
        if (isinstance(record["size"], bool) or not isinstance(record["size"], int)
                or record["size"] < 0 or isinstance(record["ciphertext_size"], bool)
                or not isinstance(record["ciphertext_size"], int) or record["ciphertext_size"] < 32):
            raise ValueError("formation raw reference has invalid content sizes")
        return record

    def raw_reference(self, object_ref: str) -> RawObjectReference | None:
        record = self.raw_metadata(object_ref)
        if record is None:
            return None
        return RawObjectReference(self.scope, str(record["object_id"]),
                                  str(record["plaintext_sha256"]), record["size"])

    def get(self, object_ref: str, default=None):
        """Raw-reference resolver for existing selected source readers.

        This reads durable custody metadata, rather than a caller's RAM map.
        It does not resolve source IDs or authorize any use of the bytes.
        """
        reference = self.raw_reference(object_ref)
        return reference if reference is not None else default


class RegisteredEncryptedFormationCustody:
    """Recover raw references from XTDB; keys remain in the local object plane."""

    def __init__(self, *, registry: XTDBFormationSourceRegistry,
                 objects: EncryptedObjectPlane):
        if registry.scope != objects.scope:
            raise ValueError("formation custody crosses host scope")
        self.registry = registry
        self.objects = objects

    def read(self, scope: ProductHostScope, object_ref: str) -> bytes:
        if scope != self.registry.scope:
            raise ValueError("formation custody request crosses host scope")
        record = self.registry.raw_metadata(object_ref)
        raw = self.registry.raw_reference(object_ref)
        if record is None or raw is None:
            raise ValueError("formation custody has no registered raw source")
        if record["object_namespace"] != self.objects.namespace:
            raise ValueError("formation raw reference belongs to a different object namespace")
        ciphertext = self.objects.backend.get_object(self.objects.namespace, object_ref)
        if (len(ciphertext) != record["ciphertext_size"]
                or hashlib.sha256(ciphertext).hexdigest() != record["ciphertext_sha256"]):
            raise ValueError("formation ciphertext differs from durable custody metadata")
        return self.objects.get(raw)
