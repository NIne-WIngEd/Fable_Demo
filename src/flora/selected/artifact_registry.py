"""Scoped artifact admission with independently verified external qualification.

This is a registry and wiring boundary, not a model, loader or inference adapter.
Checkpoint bytes are hashed without deserialization. External qualification has
no universal settled MFM/EIPM export schema yet; the trusted verifier must inspect
the actual producer's receipt and determine runtime/interface eligibility.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Protocol

from cognitive_kernel.canonical import canonical_sha256, require_identifier, require_sha256, require_text
from cognitive_kernel.contracts import ProductHostScope

from .claims import _dml_placeholder, _record_json, _rows, configure_xtdb_connection
from .object_store import EncryptedObjectPlane, RawObjectReference

ARTIFACT_ROLES = frozenset({"memory_formation", "personality_judgment"})
_ADMISSIONS = "flora_model_artifact_admissions"
_QUALIFICATIONS = "flora_model_artifact_qualifications"
_CURRENT = "flora_model_artifact_current_roles"


def _identifier(value: str, name: str) -> None:
    if require_identifier(value, name) != value:
        raise ValueError(f"{name} must be canonical")


def _digest(value: str, name: str) -> None:
    if require_sha256(value, name) != value:
        raise ValueError(f"{name} must be canonical")


@dataclass(frozen=True)
class ArtifactManifest:
    scope: ProductHostScope
    artifact_id: str
    role: str
    source_repository: str
    source_branch: str
    source_commit: str
    checkpoint_sha256: str
    checkpoint_size: int
    input_contract_id: str
    input_contract_sha256: str
    output_contract_id: str
    output_contract_sha256: str

    def validate(self) -> None:
        self.scope.validate()
        if self.role not in ARTIFACT_ROLES:
            raise ValueError("artifact role is not a supported FloRA runtime role")
        for name in ("artifact_id", "input_contract_id", "output_contract_id"):
            _identifier(getattr(self, name), name)
        for name in ("checkpoint_sha256", "input_contract_sha256", "output_contract_sha256"):
            _digest(getattr(self, name), name)
        for name in ("source_repository", "source_branch"):
            value = getattr(self, name)
            if require_text(value, name, maximum=512) != value:
                raise ValueError(f"{name} must be exact nonempty source text")
        if not re.fullmatch(r"[0-9a-f]{40}", self.source_commit):
            raise ValueError("artifact source must bind an exact Git commit")
        if (isinstance(self.checkpoint_size, bool)
                or not isinstance(self.checkpoint_size, int) or self.checkpoint_size <= 0):
            raise ValueError("checkpoint size must be a positive byte count")

    def metadata_record(self) -> dict[str, object]:
        self.validate()
        return {"schema": "flora-model-artifact-manifest-v1",
                "scope": self.scope.metadata_record(),
                **{name: getattr(self, name) for name in self.__dataclass_fields__
                   if name != "scope"}}

    @classmethod
    def from_record(cls, record: dict[str, object]) -> "ArtifactManifest":
        if set(record) != {"schema", *cls.__dataclass_fields__} or record["schema"] != "flora-model-artifact-manifest-v1":
            raise ValueError("artifact manifest schema or fields changed")
        manifest = cls(scope=ProductHostScope.create(**record["scope"]),
                       **{name: record[name] for name in cls.__dataclass_fields__ if name != "scope"})
        if manifest.metadata_record() != record:
            raise ValueError("artifact manifest is not canonical")
        return manifest

    @property
    def manifest_sha256(self) -> str:
        return canonical_sha256(self.metadata_record())


@dataclass(frozen=True)
class VerifiedArtifactQualification:
    """Returned by a trusted external-receipt adapter, never self-declared.

    ``runtime_allowed`` includes the producer's actual capability qualification
    and compatibility with both contract references in the exact manifest. A
    checkpoint receipt or a schema test alone must not produce this result.
    """

    qualification_id: str
    qualifier_id: str
    receipt_schema: str
    manifest_sha256: str
    receipt_sha256: str
    runtime_allowed: bool

    def validate_binding(self, manifest: ArtifactManifest, receipt: bytes) -> None:
        for name in ("qualification_id", "qualifier_id", "receipt_schema"):
            _identifier(getattr(self, name), name)
        for name in ("manifest_sha256", "receipt_sha256"):
            _digest(getattr(self, name), name)
        if (self.manifest_sha256 != manifest.manifest_sha256
                or not isinstance(receipt, bytes) or not receipt
                or self.receipt_sha256 != hashlib.sha256(receipt).hexdigest()):
            raise ValueError("external qualification does not bind the exact scoped manifest and receipt")
        if self.runtime_allowed is not True:
            raise ValueError("external qualification does not authorize this artifact/interface for runtime")

    def metadata_record(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


class ArtifactQualificationVerifier(Protocol):
    def verify(self, *, manifest: ArtifactManifest,
               receipt: bytes) -> VerifiedArtifactQualification: ...


def verify_local_artifact(*, manifest: ArtifactManifest, checkpoint_path: str | Path,
                          receipt: bytes, verifier: ArtifactQualificationVerifier) -> VerifiedArtifactQualification:
    """Hash local bytes and recheck them after independent qualification I/O."""
    manifest.validate()

    def check() -> None:
        path = Path(checkpoint_path)
        if not path.is_file():
            raise ValueError("artifact checkpoint is absent or not a regular file")
        digest, size = hashlib.sha256(), 0
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
                size += len(block)
        if size != manifest.checkpoint_size or digest.hexdigest() != manifest.checkpoint_sha256:
            raise ValueError("local checkpoint bytes differ from the registered artifact")

    check()
    qualification = verifier.verify(manifest=manifest, receipt=receipt)
    if not isinstance(qualification, VerifiedArtifactQualification):
        raise TypeError("qualification adapter returned no independently bound result")
    qualification.validate_binding(manifest, receipt)
    check()
    return qualification


@dataclass(frozen=True)
class ArtifactAdmissionReceipt:
    artifact_id: str
    manifest_sha256: str
    qualification_id: str
    generation: int
    admission_sha256: str
    idempotent_replay: bool = False


@dataclass(frozen=True)
class RuntimeWiringManifest:
    """Validated references only. This does not load or invoke either model."""

    scope: ProductHostScope
    role: str
    artifact_id: str
    manifest_sha256: str
    generation: int
    checkpoint_sha256: str
    input_contract_id: str
    input_contract_sha256: str
    output_contract_id: str
    output_contract_sha256: str
    qualification_id: str
    qualifier_id: str


class XTDBModelArtifactRegistry:
    def __init__(self, *, scope: ProductHostScope, authority_namespace_id: str,
                 connection: Any, objects: EncryptedObjectPlane):
        scope.validate()
        if objects.scope != scope:
            raise ValueError("artifact registry custody crosses host scope")
        _identifier(authority_namespace_id, "authority_namespace_id")
        self.scope, self.authority_namespace_id = scope, authority_namespace_id
        self.connection, self.objects = connection, objects
        configure_xtdb_connection(connection)
        self.scope_digest = canonical_sha256({"scope": scope.metadata_record(),
                                             "authority_namespace_id": authority_namespace_id})

    def _key(self, kind: str, identifier: str) -> str:
        _identifier(identifier, kind)
        return canonical_sha256({"scope_digest": self.scope_digest, "kind": kind, "id": identifier})

    def _fetch(self, table: str, key: str) -> dict[str, object] | None:
        # A role head is deliberately replaced by each admitted generation.
        # Reading ALL valid time would also return its historical heads.
        temporal = "" if table == _CURRENT else " FOR VALID_TIME ALL"
        rows = _rows(self.connection.execute(
            f"SELECT * FROM {table}{temporal} WHERE _id = %s", (key,)))
        if len(rows) > 1:
            raise ValueError("artifact registry returned ambiguous immutable records")
        if not rows:
            return None
        row = rows[0]
        record = json.loads(str(row["record_json"]))
        if (row["_id"] != key or row["scope_digest"] != self.scope_digest
                or record["scope"] != self.scope.metadata_record()
                or record["authority_namespace_id"] != self.authority_namespace_id
                or record["record_sha256"] != row["record_sha256"]
                or canonical_sha256({name: value for name, value in record.items()
                                     if name != "record_sha256"}) != record["record_sha256"]):
            raise ValueError("artifact registry metadata changed or crossed host scope")
        return record

    def _insert(self, table: str, key: str, record: dict[str, object]) -> None:
        values = {"_id": key, "scope_digest": self.scope_digest,
                  "record_sha256": record["record_sha256"], "record_json": _record_json(record)}
        self.connection.execute(
            f"INSERT INTO {table} ({', '.join(values)}) VALUES ("
            + ", ".join(_dml_placeholder(value) for value in values.values()) + ")",
            tuple(values.values()))

    def _seal(self, material: dict[str, object]) -> dict[str, object]:
        record = {"scope": self.scope.metadata_record(),
                  "authority_namespace_id": self.authority_namespace_id, **material}
        return {**record, "record_sha256": canonical_sha256(record)}

    def admit(self, *, manifest: ArtifactManifest, checkpoint_path: str | Path,
              external_receipt: bytes, verifier: ArtifactQualificationVerifier,
              expected_previous_artifact_id: str | None = None,
              expected_previous_generation: int = 0) -> ArtifactAdmissionReceipt:
        if manifest.scope != self.scope:
            raise ValueError("artifact admission crosses host scope")
        if (isinstance(expected_previous_generation, bool)
                or not isinstance(expected_previous_generation, int)
                or expected_previous_generation < 0
                or (expected_previous_artifact_id is None) != (expected_previous_generation == 0)):
            raise ValueError("artifact admission needs an exact predecessor and role generation")
        if expected_previous_artifact_id is not None:
            _identifier(expected_previous_artifact_id, "expected_previous_artifact_id")
        verified = verify_local_artifact(manifest=manifest, checkpoint_path=checkpoint_path,
                                         receipt=external_receipt, verifier=verifier)
        raw = self.objects.put(external_receipt)
        qualification = self._seal({"schema": "flora-artifact-qualification-custody-v1",
            "qualification": verified.metadata_record(), "object_id": raw.object_id,
            "content_sha256": raw.plaintext_sha256, "size": raw.size})
        qualification_key = self._key("qualification", verified.qualification_id)
        prior_qualification = self._fetch(_QUALIFICATIONS, qualification_key)
        if prior_qualification is not None and prior_qualification != qualification:
            raise ValueError("qualification ID is immutable and cannot bind another receipt or artifact")
        generation = expected_previous_generation + 1
        record = self._seal({"schema": "flora-model-artifact-admission-v1",
            "manifest": manifest.metadata_record(), "manifest_sha256": manifest.manifest_sha256,
            "qualification_id": verified.qualification_id,
            "qualification_sha256": qualification["record_sha256"], "generation": generation,
            "previous_artifact_id": expected_previous_artifact_id,
            "previous_generation": expected_previous_generation})
        artifact_key, current_key = self._key("artifact", manifest.artifact_id), self._key("role", manifest.role)
        prior = self._fetch(_ADMISSIONS, artifact_key)
        if prior is not None:
            if prior != record or prior_qualification is None:
                raise ValueError("artifact admission ID was reused or lost qualification custody")
            return ArtifactAdmissionReceipt(manifest.artifact_id, manifest.manifest_sha256,
                verified.qualification_id, generation, record["record_sha256"], True)
        current = self._fetch(_CURRENT, current_key)
        if ((current is None) != (expected_previous_artifact_id is None)
                or current is not None and (current["artifact_id"] != expected_previous_artifact_id
                    or current["generation"] != expected_previous_generation)):
            raise ValueError("stale artifact role predecessor")
        head = self._seal({"schema": "flora-model-artifact-current-role-v1", "role": manifest.role,
            "artifact_id": manifest.artifact_id, "manifest_sha256": manifest.manifest_sha256,
            "generation": generation, "admission_sha256": record["record_sha256"]})
        if verify_local_artifact(manifest=manifest, checkpoint_path=checkpoint_path,
                                 receipt=external_receipt, verifier=verifier) != verified:
            raise ValueError("artifact qualification changed before admission")
        with self.connection.transaction():
            for table, key in ((_ADMISSIONS, artifact_key),):
                self.connection.execute(f"ASSERT NOT EXISTS (SELECT 1 FROM {table} "
                    "FOR VALID_TIME ALL WHERE _id = %s::text)", (key,))
            if prior_qualification is None:
                self.connection.execute(f"ASSERT NOT EXISTS (SELECT 1 FROM {_QUALIFICATIONS} "
                    "FOR VALID_TIME ALL WHERE _id = %s::text)", (qualification_key,))
                self._insert(_QUALIFICATIONS, qualification_key, qualification)
            else:
                self.connection.execute(f"ASSERT EXISTS (SELECT 1 FROM {_QUALIFICATIONS} "
                    "FOR VALID_TIME ALL WHERE _id = %s::text AND record_sha256 = %s::text)",
                    (qualification_key, qualification["record_sha256"]))
            if current is None:
                self.connection.execute(f"ASSERT NOT EXISTS (SELECT 1 FROM {_CURRENT} WHERE _id = %s::text)", (current_key,))
            else:
                self.connection.execute(f"ASSERT EXISTS (SELECT 1 FROM {_CURRENT} WHERE _id = %s::text "
                    "AND record_sha256 = %s::text)", (current_key, current["record_sha256"]))
            self._insert(_ADMISSIONS, artifact_key, record)
            self._insert(_CURRENT, current_key, head)
        return ArtifactAdmissionReceipt(manifest.artifact_id, manifest.manifest_sha256,
            verified.qualification_id, generation, record["record_sha256"])

    def resolve_current_for_runtime(self, *, role: str, checkpoint_path: str | Path,
            expected_input_contract_id: str, expected_input_contract_sha256: str,
            expected_output_contract_id: str, expected_output_contract_sha256: str,
            verifier: ArtifactQualificationVerifier) -> RuntimeWiringManifest:
        if role not in ARTIFACT_ROLES:
            raise ValueError("unsupported artifact runtime role")
        for name, value in (("expected_input_contract_id", expected_input_contract_id),
                            ("expected_output_contract_id", expected_output_contract_id)):
            _identifier(value, name)
        for name, value in (("expected_input_contract_sha256", expected_input_contract_sha256),
                            ("expected_output_contract_sha256", expected_output_contract_sha256)):
            _digest(value, name)
        head_key = self._key("role", role)
        head = self._fetch(_CURRENT, head_key)
        if head is None or head.get("schema") != "flora-model-artifact-current-role-v1" or head["role"] != role:
            raise ValueError("no admitted current artifact for this runtime role")
        record = self._fetch(_ADMISSIONS, self._key("artifact", head["artifact_id"]))
        if (record is None or record.get("schema") != "flora-model-artifact-admission-v1"
                or record["record_sha256"] != head["admission_sha256"]
                or record["generation"] != head["generation"]):
            raise ValueError("current artifact is not bound to its admission generation")
        manifest = ArtifactManifest.from_record(record["manifest"])
        if (manifest.scope != self.scope or manifest.role != role
                or manifest.artifact_id != head["artifact_id"]
                or manifest.manifest_sha256 != record["manifest_sha256"]
                or manifest.manifest_sha256 != head["manifest_sha256"]
                or (manifest.input_contract_id, manifest.input_contract_sha256,
                    manifest.output_contract_id, manifest.output_contract_sha256) !=
                   (expected_input_contract_id, expected_input_contract_sha256,
                    expected_output_contract_id, expected_output_contract_sha256)):
            raise ValueError("artifact does not match the exact scoped runtime interface")
        qualification = self._fetch(_QUALIFICATIONS, self._key("qualification", record["qualification_id"]))
        if (qualification is None or qualification.get("schema") != "flora-artifact-qualification-custody-v1"
                or qualification["record_sha256"] != record["qualification_sha256"]):
            raise ValueError("artifact external qualification custody is unavailable or changed")
        receipt = self.objects.get(RawObjectReference(self.scope, qualification["object_id"],
                                  qualification["content_sha256"], qualification["size"]))
        verified = verify_local_artifact(manifest=manifest, checkpoint_path=checkpoint_path,
                                         receipt=receipt, verifier=verifier)
        if (verified.metadata_record() != qualification["qualification"]
                or self._fetch(_CURRENT, head_key) != head):
            raise ValueError("artifact qualification or role head changed during runtime binding")
        return RuntimeWiringManifest(self.scope, role, manifest.artifact_id,
            manifest.manifest_sha256, head["generation"], manifest.checkpoint_sha256,
            manifest.input_contract_id, manifest.input_contract_sha256,
            manifest.output_contract_id, manifest.output_contract_sha256,
            verified.qualification_id, verified.qualifier_id)
