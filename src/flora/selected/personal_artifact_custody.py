"""Durable encrypted custody for derived personal-state and episode artifacts.

A selected XTDB index binds exact private objects and upstream contracts to a
real canonical Kurrent event. This is custody, not original-source registration,
semantic acceptance, model qualification, key enrollment or permission to use.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Callable

from cognitive_kernel.canonical import canonical_json_bytes, canonical_sha256, normalize_timestamp, require_identifier
from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from cognitive_kernel.projection_contracts import EpisodeRecord, ProjectionVersion

from .claims import _dml_placeholder, _record_json, _rows, configure_xtdb_connection
from .experience import KurrentExperienceLog
from .formation_candidates import _raw_record, _read_raw
from .formation_registry import XTDBFormationSourceRegistry
from .formation_policy import FormationPermissionAction, _action_from_record, formation_permission_payload
from .object_store import EncryptedObjectPlane, RawObjectReference
from .owner_authorization import Ed25519OwnerActionVerifier, OwnerActionProof
from .personal_state import activation_request

_ARTIFACTS = "flora_private_personal_artifacts"
_RAW = "flora_private_personal_raw_references"


@dataclass(frozen=True)
class RecordedPersonalArtifact:
    artifact_id: str
    event: ExperienceEvent
    manifest: RawObjectReference
    record_sha256: str


@dataclass(frozen=True)
class RecoveredPersonalArtifact:
    artifact_id: str
    kind: str
    contract: dict[str, object]
    event: ExperienceEvent
    references: tuple[tuple[str, RawObjectReference], ...]
    content: tuple[tuple[str, bytes], ...] = field(repr=False)


class _SourceAuthorizedObjectReads:
    """Delegate ciphertext metadata; gate every triggered plaintext read."""
    def __init__(self, objects: EncryptedObjectPlane, source_authorizer: Callable[[], bool]):
        self.objects, self.source_authorizer = objects, source_authorizer
    def __getattr__(self, name):
        return getattr(self.objects, name)
    def get(self, reference):
        if self.source_authorizer() is not True:
            raise PermissionError("private artifact source use is not permitted before raw read")
        plaintext = self.objects.get(reference)
        if self.source_authorizer() is not True:
            raise PermissionError("private artifact source permission changed during raw read")
        return plaintext


class XTDBPersonalArtifactCustody:
    """Immutable event/contract/object bindings on the selected XTDB engine."""
    def __init__(self, *, scope: ProductHostScope, authority_namespace_id: str, connection: Any):
        scope.validate()
        namespace = require_identifier(authority_namespace_id, "authority_namespace_id")
        if namespace != authority_namespace_id:
            raise ValueError("private custody namespace must be canonical")
        self.scope, self.authority_namespace_id, self.connection = scope, namespace, connection
        configure_xtdb_connection(connection)
        self.scope_digest = canonical_sha256([scope.storage_scope(), namespace])

    def _key(self, kind: str, identifier: str) -> str:
        if require_identifier(identifier, "identifier") != identifier:
            raise ValueError("private artifact identifier must be canonical")
        return canonical_sha256([self.scope_digest, kind, identifier])

    def _fetch(self, table: str, key: str) -> dict[str, object] | None:
        rows = _rows(self.connection.execute(
            f"SELECT * FROM {table} FOR VALID_TIME ALL WHERE _id = %s", (key,)))
        if len(rows) > 1:
            raise ValueError("private artifact custody has ambiguous immutable rows")
        if not rows:
            return None
        row = rows[0]
        record = json.loads(str(row["record_json"]))
        if (row["_id"] != key or row["scope_digest"] != self.scope_digest
                or record["scope"] != self.scope.metadata_record()
                or record["authority_namespace_id"] != self.authority_namespace_id
                or row["record_sha256"] != record["record_sha256"]
                or canonical_sha256({k: v for k, v in record.items() if k != "record_sha256"})
                != record["record_sha256"]):
            raise ValueError("private artifact custody metadata changed")
        return record

    def _insert(self, table: str, key: str, record: dict[str, object]) -> None:
        values = {"_id": key, "scope_digest": self.scope_digest,
                  "record_sha256": record["record_sha256"], "record_json": _record_json(record)}
        self.connection.execute(
            f"ASSERT NOT EXISTS (SELECT 1 FROM {table} FOR VALID_TIME ALL WHERE _id = %s::text)", (key,))
        self.connection.execute(
            f"INSERT INTO {table} ({', '.join(values)}) VALUES ("
            + ", ".join(_dml_placeholder(v) for v in values.values()) + ")", tuple(values.values()))

    def _scope(self, log: KurrentExperienceLog, objects: EncryptedObjectPlane) -> None:
        if not self.scope == log.scope == objects.scope:
            raise ValueError("private artifact custody crosses host scope")

    def _artifact(self, artifact_id: str) -> dict[str, object] | None:
        row = self._fetch(_ARTIFACTS, self._key("artifact", artifact_id))
        if row is not None and (row.get("schema") != "flora-private-personal-artifact-index-v1"
                                or row["artifact_id"] != artifact_id):
            raise ValueError("private artifact index differs from exact lookup")
        return row

    def _register(self, *, artifact_id: str, kind: str, contract: dict[str, object],
                  event: ExperienceEvent, manifest: RawObjectReference,
                  attachments: tuple[tuple[str, RawObjectReference], ...],
                  log: KurrentExperienceLog, objects: EncryptedObjectPlane,
                  expected_material: bytes) -> RecordedPersonalArtifact:
        self._scope(log, objects)
        event.validate()
        entry = next((entry for entry in log.replay_committed() if entry.event.event_id == event.event_id), None)
        if (entry is None or entry.event != event or entry.recorded_at is None
                or event.payload_reference != manifest.object_id
                or manifest.scope != self.scope or event.content_digest != manifest.plaintext_sha256
                or objects.get(manifest) != expected_material):
            raise ValueError("private artifact lacks its exact committed event and payload")
        committed = log.replay_committed()
        earlier = {item.event.event_id: item.event for item in committed
                   if item.stream_position < entry.stream_position}
        if (not set(event.parent_event_ids).issubset(earlier)
                or any(earlier[parent].occurred_at > event.occurred_at for parent in event.parent_event_ids)):
            raise ValueError("private artifact has missing or later canonical parents")
        if kind in {"projection", "episode", "owner_action_proof"}:
            if event.event_type != "private_personal_artifact":
                raise ValueError("private typed artifact has the wrong event kind")
            if kind in {"projection", "episode"}:
                clock_field = "produced_at" if kind == "projection" else "formed_at"
                source_field = "source_evidence_ids" if kind == "projection" else "member_evidence_ids"
                if (contract[clock_field] > event.occurred_at
                        or not set(contract[source_field]).issubset(event.parent_event_ids)):
                    raise ValueError("private typed artifact has unbound direct lineage or time")
            elif contract["event_id"] not in event.parent_event_ids:
                raise ValueError("private proof artifact lacks its signed event parent")
        if (len({role for role, _ in attachments}) != len(attachments)
                or any(require_identifier(role, "role") != role for role, _ in attachments)):
            raise ValueError("private artifact attachment roles must be unique and canonical")
        record = {"schema": "flora-private-personal-artifact-index-v1",
                  "scope": self.scope.metadata_record(), "authority_namespace_id": self.authority_namespace_id,
                  "artifact_id": artifact_id, "kind": kind, "contract": contract,
                  "contract_sha256": canonical_sha256(contract),
                  "event_id": event.event_id, "event_sha256": event.event_sha256,
                  "event_stream_position": entry.stream_position,
                  "recorded_at": normalize_timestamp(entry.recorded_at.isoformat(), "recorded_at"),
                  "manifest": _raw_record(manifest, objects),
                  "attachments": [[role, _raw_record(raw, objects)] for role, raw in attachments]}
        record["record_sha256"] = canonical_sha256(record)
        prior = self._artifact(artifact_id)
        if prior is not None:
            if prior != record:
                raise ValueError("private artifact identifier was reused")
            return RecordedPersonalArtifact(artifact_id, event, manifest, record["record_sha256"])
        raw_rows = {}
        for raw in (manifest, *(ref for _, ref in attachments)):
            material = {"schema": "flora-private-personal-raw-reference-v1",
                        "scope": self.scope.metadata_record(), "authority_namespace_id": self.authority_namespace_id,
                        "raw": _raw_record(raw, objects)}
            material["record_sha256"] = canonical_sha256(material)
            key = self._key("raw", raw.object_id)
            stored = self._fetch(_RAW, key)
            if stored is not None and stored != material:
                raise ValueError("private object identity has conflicting immutable custody metadata")
            if stored is None:
                raw_rows[key] = material
        with self.connection.transaction():
            for key, material in raw_rows.items():
                self._insert(_RAW, key, material)
            self._insert(_ARTIFACTS, self._key("artifact", artifact_id), record)
        return RecordedPersonalArtifact(artifact_id, event, manifest, record["record_sha256"])

    def record(self, *, artifact_id: str, kind: str, contract: dict[str, object],
               attachments: tuple[tuple[str, RawObjectReference], ...],
               parent_event_ids: tuple[str, ...], log: KurrentExperienceLog,
               objects: EncryptedObjectPlane, occurred_at: str, expected_revision: int) -> RecordedPersonalArtifact:
        """Append a typed manifest and register exact attachments without authority."""
        self._scope(log, objects)
        if kind not in {"projection", "episode", "owner_action_proof"}:
            raise ValueError("private artifact kind requires a typed binding")
        if require_identifier(artifact_id, "artifact_id") != artifact_id:
            raise ValueError("private artifact ID must be canonical")
        self._validate_contract(kind, contract, attachments, objects)
        at = normalize_timestamp(occurred_at, "occurred_at")
        if kind in {"projection", "episode"}:
            observed_field = "produced_at" if kind == "projection" else "formed_at"
            direct_field = "source_evidence_ids" if kind == "projection" else "member_evidence_ids"
            if (contract[observed_field] > at
                    or not set(contract[direct_field]).issubset(parent_event_ids)):
                raise ValueError("private artifact omits direct lineage or predates its contract")
        elif contract["event_id"] not in parent_event_ids:
            raise ValueError("private owner proof omits its signed event parent")
        material = canonical_json_bytes({
            "schema": "flora-private-personal-artifact-v1", "scope": self.scope.metadata_record(),
            "authority_namespace_id": self.authority_namespace_id, "artifact_id": artifact_id,
            "kind": kind, "contract": contract, "contract_sha256": canonical_sha256(contract),
            "attachments": [[role, _raw_record(raw, objects)] for role, raw in attachments]})
        raw = objects.put(material)
        event = ExperienceEvent.create(event_type="private_personal_artifact", scope=self.scope,
            occurred_at=at, content_digest=raw.plaintext_sha256,
            provenance=ProvenanceReference.create(provenance_type="derived_inference",
                source_reference_ids=parent_event_ids,
                derivation_activity_id=artifact_id, responsible_component="personal_artifact_custody"),
            retention_class="ordinary_experience", storage_tier="raw_buffer",
            parent_event_ids=parent_event_ids, payload_reference=raw.object_id)
        prior = self._artifact(artifact_id)
        if prior is not None and prior["event_sha256"] != event.event_sha256:
            raise ValueError("private artifact identifier was reused before append")
        replayed = log.replay()
        positions = {item.event_id: i for i, item in enumerate(replayed)}
        existing = positions.get(event.event_id)
        if existing is None:
            if (isinstance(expected_revision, bool) or not isinstance(expected_revision, int)
                    or expected_revision != len(replayed) - 1):
                raise ValueError("stale expected Experience revision for private artifact")
            if (not parent_event_ids or len(set(parent_event_ids)) != len(parent_event_ids)
                    or not set(parent_event_ids).issubset(positions)
                    or any(replayed[positions[parent]].occurred_at > at for parent in parent_event_ids)):
                raise ValueError("private artifact lacks earlier canonical Experience parents")
            log.append(event, expected_revision=expected_revision)
        elif (existing != expected_revision + 1 or replayed[existing] != event):
            raise ValueError("private artifact retry changed its original Experience position")
        return self._register(artifact_id=artifact_id, kind=kind, contract=contract, event=event,
                              manifest=raw, attachments=attachments, log=log, objects=objects,
                              expected_material=material)

    def _validate_contract(self, kind: str, contract: dict[str, object],
                           attachments: tuple[tuple[str, RawObjectReference], ...],
                           objects: EncryptedObjectPlane) -> None:
        references = dict(attachments)
        if len(references) != len(attachments):
            raise ValueError("private artifact attachment roles are duplicated")
        if kind == "projection":
            from .governed_development import _version_from_record
            version = _version_from_record(contract)
            if (version.scope != self.scope or version.envelope.authority_namespace_id != self.authority_namespace_id
                    or set(references) != {"content"}
                    or references["content"].plaintext_sha256 != version.content_digest
                    or version.envelope.content_digest != version.content_digest):
                raise ValueError("private projection artifact differs from its exact contract")
        elif kind == "episode":
            episode = episode_from_record(contract)
            if (episode.scope != self.scope or episode.envelope.authority_namespace_id != self.authority_namespace_id
                    or set(references) != {"summary", "content"}
                    or references["summary"].plaintext_sha256 != episode.summary_content_digest
                    or references["content"].plaintext_sha256 != episode.full_content_digest
                    or episode.envelope.content_digest != episode.full_content_digest):
                raise ValueError("private episode artifact differs from its exact contract")
        elif kind == "owner_action_proof":
            if (contract.get("schema") != "flora-enrolled-owner-proof-binding-v1"
                    or contract.get("scope") != self.scope.metadata_record()
                    or set(references) != {"proof"}):
                raise ValueError("private owner proof binding differs")
            proof = OwnerActionProof(**json.loads(objects.get(references["proof"])))
            if (proof.action != contract["action"] or proof.event_id != contract["event_id"]
                    or proof.event_sha256 != contract["event_sha256"]):
                raise ValueError("private owner proof differs from its event binding")
        else:
            raise ValueError("private artifact contract kind is unsupported")
        for raw in references.values():
            if raw.scope != self.scope:
                raise ValueError("private artifact content crosses host scope")
            objects.get(raw)

    def register_approval(self, *, approval_event_id: str, candidate: ProjectionVersion,
                          expected_active_version_id: str | None, raw: RawObjectReference,
                          log: KurrentExperienceLog, objects: EncryptedObjectPlane) -> RecordedPersonalArtifact:
        """Persist exact approval custody; signature authorization remains separate."""
        self._scope(log, objects)
        candidate.validate()
        if (candidate.scope != self.scope
                or candidate.envelope.authority_namespace_id != self.authority_namespace_id):
            raise ValueError("private approval candidate crosses host or authority")
        event = next((item for item in log.replay() if item.event_id == approval_event_id), None)
        payload = activation_request(candidate.metadata_record(),
                                     expected_active_version_id=expected_active_version_id)
        if (event is None or event.event_type != "state_activation_approval"
                or event.occurred_at < candidate.produced_at or objects.get(raw) != payload):
            raise ValueError("private approval does not bind the exact candidate")
        contract = {"schema": "flora-personal-state-approval-custody-v1",
                    "candidate": candidate.metadata_record(),
                    "expected_active_version_id": expected_active_version_id}
        return self._register(artifact_id=approval_artifact_id(event.event_id), kind="state_activation_approval",
            contract=contract, event=event, manifest=raw, attachments=(("approval", raw),),
            log=log, objects=objects, expected_material=payload)

    def register_formation_permission(self, *, action: FormationPermissionAction,
                                      request_event_id: str, raw: RawObjectReference,
                                      log: KurrentExperienceLog,
                                      objects: EncryptedObjectPlane) -> RecordedPersonalArtifact:
        """Retain exact permission-request custody, without applying authority."""
        self._scope(log, objects)
        action.validate()
        if action.scope != self.scope or action.authority_namespace_id != self.authority_namespace_id:
            raise ValueError("private permission request crosses host or authority")
        event = next((item for item in log.replay() if item.event_id == request_event_id), None)
        payload = formation_permission_payload(action)
        if (event is None or event.event_type != "formation_permission_action"
                or event.occurred_at != action.authorized_at
                or action.source_ref_id not in event.parent_event_ids
                or objects.get(raw) != payload):
            raise ValueError("private permission request differs from its exact action")
        return self._register(
            artifact_id="formation-permission-" + canonical_sha256([event.event_id])[:48],
            kind="formation_permission_action", contract=action.metadata_record(),
            event=event, manifest=raw, attachments=(("permission", raw),),
            log=log, objects=objects, expected_material=payload)

    def reconcile_event(self, event_id: str, *, log: KurrentExperienceLog,
                        objects: EncryptedObjectPlane, state_registry: Any | None = None) -> RecordedPersonalArtifact:
        """Recover an appended manifest/action after its XTDB registration failed.

        The encrypted object plane authenticates a recovered reference. Exact
        typed/event validation must also pass before any custody row is written.
        No authority is applied.
        """
        self._scope(log, objects)
        event = next((item for item in log.replay() if item.event_id == event_id), None)
        if event is None or event.payload_reference is None:
            raise ValueError("private custody recovery lacks its canonical event")
        raw = objects.recover_reference(object_id=event.payload_reference,
                                        expected_plaintext_sha256=event.content_digest)
        material = objects.get(raw)
        payload = json.loads(material)
        if event.event_type == "private_personal_artifact":
            if (payload.get("schema") != "flora-private-personal-artifact-v1"
                    or payload["scope"] != self.scope.metadata_record()
                    or payload["authority_namespace_id"] != self.authority_namespace_id
                    or canonical_sha256(payload["contract"]) != payload["contract_sha256"]
                    or canonical_json_bytes(payload) != material
                    or event.provenance.provenance_type != "derived_inference"
                    or event.provenance.derivation_activity_id != payload["artifact_id"]
                    or event.provenance.source_reference_ids != event.parent_event_ids):
                raise ValueError("private custody recovery has an unbound typed manifest")
            attachments = tuple((role, _read_raw(record, objects)[0]) for role, record in payload["attachments"])
            self._validate_contract(payload["kind"], payload["contract"], attachments, objects)
            return self._register(artifact_id=payload["artifact_id"], kind=payload["kind"],
                contract=payload["contract"], event=event, manifest=raw, attachments=attachments,
                log=log, objects=objects, expected_material=material)
        if event.event_type == "state_activation_approval":
            if (state_registry is None or state_registry.scope != self.scope
                    or state_registry.authority_namespace_id != self.authority_namespace_id
                    or payload.get("schema") != "flora-state-activation-v1"):
                raise ValueError("private approval recovery lacks its scoped candidate registry")
            from .governed_development import _version_from_record
            from .personal_state import _VERSIONS
            row = state_registry._fetch(_VERSIONS,
                state_registry._version_id(payload["candidate_version_id"]), all_valid=True)
            if row is None:
                raise ValueError("private approval recovery candidate is absent")
            version = _version_from_record(json.loads(str(row["record_json"])))
            if version.projection_sha256 != payload["candidate_sha256"]:
                raise ValueError("private approval recovery candidate digest differs")
            return self.register_approval(approval_event_id=event.event_id, candidate=version,
                expected_active_version_id=payload["expected_active_version_id"], raw=raw,
                log=log, objects=objects)
        if event.event_type == "formation_permission_action":
            return self.register_formation_permission(action=_action_from_record(payload),
                request_event_id=event.event_id, raw=raw, log=log, objects=objects)
        raise ValueError("private custody recovery refuses an unsupported event type")

    def metadata(self, artifact_id: str) -> dict[str, object] | None:
        """Verify immutable metadata without opening private artifact bytes."""
        return self._artifact(artifact_id)

    def raw_reference(self, object_id: str) -> RawObjectReference | None:
        row = self._fetch(_RAW, self._key("raw", object_id))
        if row is None:
            return None
        raw = row["raw"]
        if (row.get("schema") != "flora-private-personal-raw-reference-v1"
                or raw["scope"] != self.scope.metadata_record() or raw["object_id"] != object_id):
            raise ValueError("private raw reference differs from exact lookup")
        return RawObjectReference(self.scope, raw["object_id"], raw["plaintext_sha256"], raw["size"])

    def read(self, artifact_id: str, *, log: KurrentExperienceLog,
             objects: EncryptedObjectPlane,
             source_authorizer: Callable[[], bool] | None = None) -> RecoveredPersonalArtifact:
        """Recover exact bytes; governed consumers provide a current use gate.

        This primitive grants no use by default. Its caller owns that policy.
        An optional gate runs immediately before/after every plaintext read,
        including attachment/contract validation reads inside this method.
        """
        self._scope(log, objects)
        if source_authorizer is not None:
            if not callable(source_authorizer):
                raise TypeError("private artifact source authorizer must be callable")
            objects = _SourceAuthorizedObjectReads(objects, source_authorizer)
        index = self._artifact(artifact_id)
        if index is None:
            raise KeyError(artifact_id)
        entry = next((entry for entry in log.replay_committed() if entry.event.event_id == index["event_id"]), None)
        if (entry is None or entry.recorded_at is None or entry.event.event_sha256 != index["event_sha256"]
                or entry.stream_position != index["event_stream_position"]
                or normalize_timestamp(entry.recorded_at.isoformat()) != index["recorded_at"]
                or entry.event.payload_reference != index["manifest"]["object_id"]):
            raise ValueError("private artifact lost its exact canonical event binding")
        manifest, material = _read_raw(index["manifest"], objects)
        if entry.event.content_digest != manifest.plaintext_sha256:
            raise ValueError("private artifact event digest differs from custody")
        references, content = [], []
        for role, raw_record in index["attachments"]:
            raw, plaintext = _read_raw(raw_record, objects)
            if self.raw_reference(raw.object_id) != raw:
                raise ValueError("private artifact raw reference differs from durable index")
            references.append((role, raw))
            content.append((role, plaintext))
        contract = index["contract"]
        if canonical_sha256(contract) != index["contract_sha256"]:
            raise ValueError("private artifact contract digest differs")
        if index["kind"] == "state_activation_approval":
            from .governed_development import _version_from_record
            candidate = _version_from_record(contract["candidate"])
            expected = activation_request(candidate.metadata_record(),
                                           expected_active_version_id=contract["expected_active_version_id"])
            if (contract.get("schema") != "flora-personal-state-approval-custody-v1"
                    or entry.event.event_type != "state_activation_approval" or material != expected
                    or dict(content).get("approval") != expected):
                raise ValueError("private approval contract binding changed")
        elif index["kind"] == "formation_permission_action":
            action = _action_from_record(contract)
            expected = formation_permission_payload(action)
            if (action.scope != self.scope or action.authority_namespace_id != self.authority_namespace_id
                    or entry.event.event_type != "formation_permission_action"
                    or entry.event.occurred_at != action.authorized_at
                    or action.source_ref_id not in entry.event.parent_event_ids
                    or material != expected or dict(content).get("permission") != expected):
                raise ValueError("private formation permission binding changed")
        else:
            expected = canonical_json_bytes({
                "schema": "flora-private-personal-artifact-v1", "scope": self.scope.metadata_record(),
                "authority_namespace_id": self.authority_namespace_id, "artifact_id": artifact_id,
                "kind": index["kind"], "contract": contract, "contract_sha256": index["contract_sha256"],
                "attachments": index["attachments"]})
            if entry.event.event_type != "private_personal_artifact" or material != expected:
                raise ValueError("private artifact typed manifest changed")
            self._validate_contract(index["kind"], contract, tuple(references), objects)
        return RecoveredPersonalArtifact(artifact_id, index["kind"], contract, entry.event,
                                        tuple(references), tuple(content))

    def record_owner_proof(self, *, proof: OwnerActionProof, owner_public_key: bytes,
                           log: KurrentExperienceLog, objects: EncryptedObjectPlane,
                           occurred_at: str, expected_revision: int) -> RecordedPersonalArtifact:
        """Verify an externally enrolled key and persist its exact signed proof."""
        self._scope(log, objects)
        event = next((item for item in log.replay() if item.event_id == proof.event_id), None)
        verifier = Ed25519OwnerActionVerifier(scope=self.scope, owner_public_key=owner_public_key,
                                              proofs={proof.event_id: proof})
        if event is None or verifier._verify(event, proof.action) is not True:
            raise ValueError("owner proof does not match the independently enrolled key and event")
        raw = objects.put(canonical_json_bytes(proof.__dict__))
        contract = {"schema": "flora-enrolled-owner-proof-binding-v1", "scope": self.scope.metadata_record(),
                    "action": proof.action, "event_id": proof.event_id, "event_sha256": proof.event_sha256,
                    "owner_public_key_sha256": hashlib.sha256(owner_public_key).hexdigest()}
        return self.record(artifact_id=owner_proof_artifact_id(proof.event_id), kind="owner_action_proof",
            contract=contract, attachments=(("proof", raw),), parent_event_ids=(event.event_id,),
            log=log, objects=objects, occurred_at=occurred_at, expected_revision=expected_revision)


def episode_from_record(record: dict[str, object]) -> EpisodeRecord:
    material = {key: value for key, value in record.items() if key != "schema_version"}
    envelope = dict(material["envelope"])
    envelope["scope"] = ProductHostScope.create(**envelope["scope"])
    for name in ("causal_parents", "source_records", "supersedes", "superseded_by"):
        envelope[name] = tuple(envelope[name])
    from cognitive_kernel.memory_contracts import MemoryUnitEnvelope
    material["envelope"] = MemoryUnitEnvelope(**envelope)
    for name in ("member_evidence_ids", "member_claim_version_ids", "member_candidate_ids", "mission_node_ids", "participant_ids"):
        material[name] = tuple(material[name])
    episode = EpisodeRecord(**material)
    episode.validate()
    if episode.metadata_record() != record:
        raise ValueError("private episode contract is not canonical")
    return episode


def approval_artifact_id(event_id: str) -> str:
    return "state-approval-" + canonical_sha256([event_id])[:48]


def owner_proof_artifact_id(event_id: str) -> str:
    return "owner-proof-" + canonical_sha256([event_id])[:48]


class DurablePersonalReferences:
    """Metadata resolver for original plus derived objects, without byte reads."""
    def __init__(self, *, custody: XTDBPersonalArtifactCustody,
                 originals: XTDBFormationSourceRegistry):
        if (custody.scope != originals.scope
                or custody.authority_namespace_id != originals.authority_namespace_id):
            raise ValueError("durable personal references cross source authority")
        self.custody, self.originals = custody, originals

    def get(self, object_id: str, default=None):
        private, original = self.custody.raw_reference(object_id), self.originals.raw_reference(object_id)
        if private is not None and original is not None and private != original:
            raise ValueError("original and derived object custody disagree")
        return private or original or default


class DurableOwnerProofLookup:
    """Fresh verified proof lookup; trust-root key is supplied, never self-enrolled."""
    def __init__(self, *, custody: XTDBPersonalArtifactCustody, log: KurrentExperienceLog,
                 objects: EncryptedObjectPlane, owner_public_key: bytes):
        custody._scope(log, objects)
        # Verify the enrolled key's format before installing this resolver.
        Ed25519OwnerActionVerifier(scope=custody.scope, owner_public_key=owner_public_key, proofs={})
        self.custody, self.log, self.objects, self.owner_public_key = custody, log, objects, owner_public_key

    def get(self, event_id: str, default=None):
        artifact_id = owner_proof_artifact_id(event_id)
        metadata = self.custody.metadata(artifact_id)
        if metadata is None:
            return default
        contract = metadata["contract"]
        if (metadata["kind"] != "owner_action_proof" or contract["event_id"] != event_id
                or contract["owner_public_key_sha256"] != hashlib.sha256(self.owner_public_key).hexdigest()):
            raise ValueError("durable owner proof differs from current enrolled key")
        artifact = self.custody.read(artifact_id, log=self.log, objects=self.objects)
        proof = OwnerActionProof(**json.loads(dict(artifact.content)["proof"]))
        original = next((event for event in self.log.replay() if event.event_id == event_id), None)
        verifier = Ed25519OwnerActionVerifier(scope=self.custody.scope, owner_public_key=self.owner_public_key,
                                              proofs={event_id: proof})
        if original is None or verifier._verify(original, proof.action) is not True:
            raise ValueError("durable owner proof lost its exact event/signature binding")
        return proof
