"""Governed personal-state updates and rollback on the selected XTDB plane.

Supplied ProjectionVersion candidates remain candidates until an independently
verified exact approval. Registered source-use permission is checked separately
for ``personal_judgment``; formation permission alone grants no use here.
Rollback restores bytes, not meaning: it creates a new immutable candidate from
an actually activated older version and requires another explicit activation.

No model is trained, inferred, or replaced by this module. Episode acceptance
and episode-derived personal state remain unsupported. Source-use denial is a
read/use barrier, not erasure or model unlearning.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any, Mapping

from cognitive_kernel.canonical import canonical_sha256, normalize_timestamp, require_identifier
from cognitive_kernel.contracts import ProductHostScope
from cognitive_kernel.memory_contracts import MemoryUnitEnvelope
from cognitive_kernel.projection_contracts import ProjectionVersion

from .claims import XTDBClaimAuthority, _dml_placeholder, _record_json
from .experience import KurrentExperienceLog
from .formation_policy import XTDBFormationPermissionPolicy
from .formation_registry import RegisteredEncryptedFormationCustody, XTDBFormationSourceRegistry
from .object_store import EncryptedObjectPlane, RawObjectReference
from .outcome_revision import register_outcome_revision
from .personal_state import (
    StateApprovalVerifier, VerifiedStateCandidate, XTDBPersonalStateCandidates,
    _ACTIVE, _HEADS, _VERSIONS,
)
from .source_native import _require_available, read_current_sources

_HISTORY = "flora_personal_state_activation_receipts"
_ROLLBACKS = "flora_personal_state_rollback_candidates"
_ROLLBACK_IDS = "flora_personal_state_rollback_ids"
_PURPOSE = "personal_judgment"


def _version_from_record(record: Mapping[str, object]) -> ProjectionVersion:
    material = {key: value for key, value in record.items() if key != "schema_version"}
    envelope = dict(material["envelope"])
    envelope.pop("schema_version", None)
    envelope["scope"] = ProductHostScope.create(**envelope["scope"])
    for name in ("causal_parents", "source_records", "supersedes", "superseded_by"):
        envelope[name] = tuple(envelope[name])
    material["envelope"] = MemoryUnitEnvelope(**envelope)
    for name in ("modalities", "source_episode_ids", "source_claim_version_ids", "source_evidence_ids"):
        material[name] = tuple(material[name])
    version = ProjectionVersion(**material)
    version.validate()
    if version.metadata_record() != dict(record):
        raise ValueError("personal-state record is not canonical")
    return version


class XTDBGovernedPersonalDevelopment(XTDBPersonalStateCandidates):
    """Current-authority wrapper for the included personal-development slice.

    The selected XTDB connection holds candidate lineage, active heads and
    immutable activation/rollback receipts. Kurrent and encrypted raw custody
    remain the independent evidence authority. A permission change racing an
    external read can cause the operation to fail after a durable write; every
    subsequent consumer must use this wrapper and revalidate current authority.
    It never repairs permission or resurrects a historical claim implicitly.
    """
    def __init__(self, *, scope: ProductHostScope, authority_namespace_id: str,
                 connection: Any, registry: XTDBFormationSourceRegistry,
                 policy: XTDBFormationPermissionPolicy):
        super().__init__(scope=scope, authority_namespace_id=authority_namespace_id,
                         connection=connection)
        if (registry.scope != scope or policy.scope != scope
                or registry.authority_namespace_id != self.authority_namespace_id
                or policy.authority_namespace_id != self.authority_namespace_id
                or policy.registry is not registry):
            raise ValueError("personal development crosses source-use authority")
        self.registry, self.policy = registry, policy

    def _check_sources(self, *, source_claim_version_ids: tuple[str, ...],
                       source_evidence_ids: tuple[str, ...], source_records: tuple[str, ...],
                       claims: XTDBClaimAuthority, log: KurrentExperienceLog,
                       objects: EncryptedObjectPlane,
                       references: Mapping[str, RawObjectReference]) -> None:
        if (not self.scope == claims.scope == log.scope == objects.scope
                or claims.authority_namespace_id != self.authority_namespace_id):
            raise ValueError("personal development sources cross host or authority")
        declared = set(source_claim_version_ids + source_evidence_ids)
        if not declared.issubset(source_records):
            raise ValueError("personal development omits source lineage")
        # Every additional source record must also be an authorized original.
        # Candidate/episode identifiers cannot silently become source authority.
        original_ids = set(source_evidence_ids) | (set(source_records) - set(source_claim_version_ids))
        claim_versions = {}
        for version_id in source_claim_version_ids:
            version = claims.load_version(version_id)
            if (version["envelope"]["scope"] != self.scope.metadata_record()
                    or version["envelope"]["authority_namespace_id"] != self.authority_namespace_id):
                raise ValueError("personal development claim crosses source authority")
            present = claims.load_current(version["claim_id"])
            _require_available(present, version["claim_id"])
            if present["validity_state"] != "current":
                raise ValueError("personal development claim is not currently valid")
            if present["current_claim_version_id"] != version_id:
                raise ValueError("personal development cites a superseded claim")
            claim_versions[version_id] = version
            for relation_id in version["evidence_relation_ids"]:
                relation = claims.load_evidence_relation(relation_id)
                if (relation["target_record_type"] != "claim_version"
                        or relation["target_record_id"] != version_id
                        or relation["evidence_record_id"] not in version["envelope"]["source_records"]):
                    raise ValueError("personal development claim lacks exact evidence binding")
                original_ids.add(str(relation["evidence_record_id"]))
        replayed = {event.event_id: event for event in log.replay()}
        closure = {}
        pending = list(original_ids)
        while pending:
            event_id = pending.pop()
            if event_id in closure:
                continue
            source = self.registry.lookup(event_id)
            event = replayed.get(event_id)
            if (source is None or event is None or event.payload_reference is None
                    or source.evidence.scope != self.scope
                    or source.evidence.authority_namespace_id != self.authority_namespace_id
                    or source.object_ref != event.payload_reference
                    or source.evidence.content_digest != event.content_digest
                    or source.evidence.parent_refs != event.parent_event_ids):
                raise ValueError("personal development lacks registered original evidence")
            if self.policy.permits(source, _PURPOSE) is not True:
                raise ValueError("personal judgment source use is not currently permitted")
            closure[event_id] = source
            pending.extend(source.evidence.parent_refs)
        # Recover original references from durable XTDB custody rather than a
        # caller-authored map. Permission precedes all original plaintext I/O.
        custody = RegisteredEncryptedFormationCustody(registry=self.registry, objects=objects)
        authorized_references = {}
        for event_id, source in closure.items():
            raw = self.registry.raw_reference(source.object_ref)
            if (raw is None or raw.scope != self.scope or raw.object_id != source.object_ref
                    or hashlib.sha256(custody.read(self.scope, source.object_ref)).hexdigest()
                    != source.evidence.content_digest):
                raise ValueError("personal development original content differs from registered evidence")
            authorized_references[source.object_ref] = raw
        for version_id, version in claim_versions.items():
            packet = read_current_sources(
                claim_id=version["claim_id"], authority=claims, log=log,
                objects=objects, references=authorized_references)
            if packet.claim_version_id != version_id:
                raise ValueError("personal development cites a superseded claim")
        # No successful materialization is allowed to outrun a current denial.
        for event_id, source in closure.items():
            if (self.registry.lookup(event_id) != source
                    or self.policy.permits(source, _PURPOSE) is not True):
                raise ValueError("personal judgment source authority changed during read")

    def _immutable(self, table: str, key: str) -> dict[str, object] | None:
        row = self._fetch(table, key, all_valid=True)
        if row is None:
            return None
        record = json.loads(str(row["record_json"]))
        if (row["scope_digest"] != self.scope_digest
                or row["record_sha256"] != record["record_sha256"]
                or record["scope"] != self.scope.metadata_record()
                or record["authority_namespace_id"] != self.authority_namespace_id
                or canonical_sha256({k: v for k, v in record.items() if k != "record_sha256"})
                != record["record_sha256"]):
            raise ValueError("personal development immutable receipt changed")
        return record

    def _history_key(self, projection_id: str, version_id: str) -> str:
        return canonical_sha256([self.scope_digest, "activation", projection_id, version_id])

    def _rollback_key(self, version_id: str) -> str:
        return canonical_sha256([self.scope_digest, "rollback", version_id])

    def _rollback_id_key(self, rollback_id: str) -> str:
        return canonical_sha256([self.scope_digest, "rollback-action", rollback_id])

    def _insert_receipt(self, table: str, key: str, record: dict[str, object]) -> None:
        columns = {"_id": key, "scope_digest": self.scope_digest,
                   "record_sha256": record["record_sha256"], "record_json": _record_json(record)}
        self.connection.execute(
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ("
            + ", ".join(_dml_placeholder(value) for value in columns.values()) + ")",
            tuple(columns.values()))

    def _history(self, projection_id: str, version_id: str) -> dict[str, object]:
        record = self._immutable(_HISTORY, self._history_key(projection_id, version_id))
        if (record is None or record.get("schema") != "flora-personal-state-activation-receipt-v1"
                or record["projection_id"] != projection_id or record["version_id"] != version_id):
            raise ValueError("personal state lacks an actual governed activation receipt")
        return record

    def _read_version(self, **kwargs: Any) -> VerifiedStateCandidate:
        candidate = super()._read_version(**kwargs)
        version = _version_from_record(candidate.record)
        if version.envelope.rollback_reference is not None:
            binding = self._immutable(_ROLLBACKS, self._rollback_key(version.version_id))
            if (binding is None or binding.get("schema") != "flora-personal-state-rollback-candidate-v1"
                    or binding["restored_version_id"] != version.version_id
                    or binding["target_version_id"] != version.envelope.rollback_reference
                    or binding["expected_latest_version_id"] != version.supersedes_version_id
                    or binding["produced_at"] != version.produced_at
                    or binding["content_digest"] != version.content_digest
                    or binding["record_sha256"] != version.envelope.provenance_digest):
                raise ValueError("rollback candidate lacks its immutable target binding")
            if self._immutable(_ROLLBACK_IDS, self._rollback_id_key(binding["rollback_id"])) != binding:
                raise ValueError("rollback action identifier lacks its exact target binding")
            target_row = self._fetch(_VERSIONS, self._version_id(binding["target_version_id"]), all_valid=True)
            if target_row is None:
                raise ValueError("rollback target is absent")
            target = _version_from_record(json.loads(str(target_row["record_json"])))
            if (target.projection_sha256 != binding["target_projection_sha256"]
                    or target.projection_id != version.projection_id
                    or target.subject_type != version.subject_type or target.subject_id != version.subject_id
                    or target.projection_type != version.projection_type
                    or target.source_episode_ids != version.source_episode_ids
                    or target.source_claim_version_ids != version.source_claim_version_ids
                    or target.source_evidence_ids != version.source_evidence_ids
                    or target.envelope.source_records != version.envelope.source_records
                    or target.content_digest != version.content_digest):
                raise ValueError("rollback candidate differs from its target state")
            history = self._history(target.projection_id, target.version_id)
            if history["projection_sha256"] != target.projection_sha256:
                raise ValueError("rollback target differs from its activation receipt")
        self._check_sources(
            source_claim_version_ids=version.source_claim_version_ids,
            source_evidence_ids=version.source_evidence_ids,
            source_records=version.envelope.source_records,
            claims=kwargs["claims"], log=kwargs["log"], objects=kwargs["objects"],
            references=kwargs["references"])
        return candidate

    def activate(self, *, subject_type: str, subject_id: str, projection_id: str,
                 approval_event_id: str, expected_active_version_id: str | None,
                 claims: XTDBClaimAuthority, log: KurrentExperienceLog,
                 objects: EncryptedObjectPlane, references: Mapping[str, RawObjectReference],
                 verifier: StateApprovalVerifier) -> VerifiedStateCandidate:
        """Atomically select an approved candidate and record actual activation."""
        inputs = dict(claims=claims, log=log, objects=objects, references=references)
        candidate = self.read_latest_candidate(subject_type=subject_type, subject_id=subject_id,
                                                projection_id=projection_id, **inputs)
        event = self._check_approval(approval_event_id=approval_event_id, candidate=candidate,
                                    expected_active_version_id=expected_active_version_id,
                                    log=log, objects=objects, references=references, verifier=verifier)
        version = _version_from_record(candidate.record)
        if version.envelope.rollback_reference is not None:
            binding = self._immutable(_ROLLBACKS, self._rollback_key(version.version_id))
            if binding is None or binding["expected_active_version_id"] != expected_active_version_id:
                raise ValueError("rollback activation changes its bound active predecessor")
        self._check_sources(source_claim_version_ids=version.source_claim_version_ids,
                            source_evidence_ids=version.source_evidence_ids,
                            source_records=version.envelope.source_records, **inputs)
        head_id = self._head_id(subject_type, subject_id, projection_id)
        prior = self._fetch(_ACTIVE, head_id)
        retry = (prior is not None and prior["version_id"] == version.version_id
                 and prior["approval_event_id"] == event.event_id)
        if retry:
            generation = int(prior["activation_generation"])
        elif expected_active_version_id is None:
            if prior is not None:
                raise ValueError("active personal state already exists")
            generation = 1
        else:
            if (prior is None or prior["version_id"] != expected_active_version_id
                    or prior["version_id"] == version.version_id):
                raise ValueError("stale active personal-state predecessor")
            generation = int(prior["activation_generation"]) + 1
        columns = {
            "_id": head_id, "scope_digest": self.scope_digest,
            "subject_type": subject_type, "subject_id": subject_id, "projection_id": projection_id,
            "version_id": version.version_id, "projection_sha256": version.projection_sha256,
            "activation_generation": generation, "approval_event_id": event.event_id,
            "approval_event_sha256": event.event_sha256,
            "expected_active_version_id": expected_active_version_id,
        }
        receipt = {
            "schema": "flora-personal-state-activation-receipt-v1",
            "scope": self.scope.metadata_record(), "authority_namespace_id": self.authority_namespace_id,
            **{k: v for k, v in columns.items() if k not in {"_id", "scope_digest"}},
        }
        receipt["record_sha256"] = canonical_sha256(receipt)
        history_key = self._history_key(projection_id, version.version_id)
        history = self._immutable(_HISTORY, history_key)
        if retry:
            if history != receipt:
                raise ValueError("active personal state lacks its exact atomic activation receipt")
            return VerifiedStateCandidate(candidate.record, candidate.content, event.event_id)
        if history is not None:
            raise ValueError("personal state version was already activated")
        with self.connection.transaction():
            if prior is None:
                self.connection.execute(f"ASSERT NOT EXISTS (SELECT 1 FROM {_ACTIVE} WHERE _id = %s::text)",
                                        (head_id,))
            else:
                self.connection.execute(
                    f"ASSERT EXISTS (SELECT 1 FROM {_ACTIVE} WHERE _id = %s::text "
                    "AND version_id = %s::text AND approval_event_id = %s::text)",
                    (head_id, expected_active_version_id, prior["approval_event_id"]))
            # The candidate cannot change while activation commits.
            self.connection.execute(
                f"ASSERT EXISTS (SELECT 1 FROM {_HEADS} WHERE _id = %s::text AND version_id = %s::text)",
                (head_id, version.version_id))
            self.connection.execute(
                f"ASSERT NOT EXISTS (SELECT 1 FROM {_HISTORY} FOR VALID_TIME ALL WHERE _id = %s::text)",
                (history_key,))
            self.connection.execute(
                f"INSERT INTO {_ACTIVE} ({', '.join(columns)}) VALUES ("
                + ", ".join(_dml_placeholder(value) for value in columns.values()) + ")",
                tuple(columns.values()))
            self._insert_receipt(_HISTORY, history_key, receipt)
        self._check_sources(source_claim_version_ids=version.source_claim_version_ids,
                            source_evidence_ids=version.source_evidence_ids,
                            source_records=version.envelope.source_records, **inputs)
        return VerifiedStateCandidate(candidate.record, candidate.content, event.event_id)

    def read_active(self, **kwargs: Any) -> VerifiedStateCandidate:
        head_id = self._head_id(kwargs["subject_type"], kwargs["subject_id"], kwargs["projection_id"])
        original_head = self._fetch(_ACTIVE, head_id)
        result = super().read_active(**kwargs)
        version = _version_from_record(result.record)
        receipt = self._history(version.projection_id, version.version_id)
        if (receipt["projection_sha256"] != version.projection_sha256
                or receipt["approval_event_id"] != result.approval_event_id):
            raise ValueError("active personal state differs from its governed activation receipt")
        self._check_sources(source_claim_version_ids=version.source_claim_version_ids,
                            source_evidence_ids=version.source_evidence_ids,
                            source_records=version.envelope.source_records,
                            claims=kwargs["claims"], log=kwargs["log"], objects=kwargs["objects"],
                            references=kwargs["references"])
        if self._fetch(_ACTIVE, head_id) != original_head:
            raise ValueError("active personal state changed during governed read")
        return result

    def register_outcome_revision(self, **kwargs: Any) -> None:
        """Gate a supplied outcome-linked proposal without deriving new state."""
        version = kwargs["version"]
        version.validate()
        self._check_sources(source_claim_version_ids=version.source_claim_version_ids,
                            source_evidence_ids=version.source_evidence_ids,
                            source_records=version.envelope.source_records,
                            claims=kwargs["claims"], log=kwargs["log"], objects=kwargs["objects"],
                            references=kwargs["references"])
        register_outcome_revision(state=self, **kwargs)

    def register_rollback(self, *, rollback_id: str, version_id: str,
                          target_version_id: str, expected_active_version_id: str,
                          expected_latest_version_id: str, produced_at: str,
                          claims: XTDBClaimAuthority, log: KurrentExperienceLog,
                          objects: EncryptedObjectPlane, references: Mapping[str, RawObjectReference],
                          verifier: StateApprovalVerifier) -> VerifiedStateCandidate:
        """Register an exact old-state restore; a new approval must activate it.

        Candidate storage and the rollback binding are separate commits. An
        interrupted binding write leaves an unusable candidate; an exact retry
        can finish it. It never activates or guesses a target after failure.
        """
        for value, name in ((rollback_id, "rollback_id"), (version_id, "version_id"),
                            (target_version_id, "target_version_id"),
                            (expected_active_version_id, "expected_active_version_id"),
                            (expected_latest_version_id, "expected_latest_version_id")):
            if require_identifier(value, name) != value:
                raise ValueError(f"{name} must be canonical")
        produced_at = normalize_timestamp(produced_at, "produced_at")
        inputs = dict(claims=claims, log=log, objects=objects, references=references)
        target_row = self._fetch(_VERSIONS, self._version_id(target_version_id), all_valid=True)
        if target_row is None:
            raise ValueError("rollback target is absent")
        target = _version_from_record(json.loads(str(target_row["record_json"])))
        identity = dict(subject_type=target.subject_type, subject_id=target.subject_id,
                        projection_id=target.projection_id)
        target_read = self._read_version(version_id=target.version_id,
                                         projection_sha256=target.projection_sha256,
                                         **identity, **inputs)
        history = self._history(target.projection_id, target.version_id)
        if history["projection_sha256"] != target.projection_sha256:
            raise ValueError("rollback target lacks exact activation lineage")
        self._check_approval(approval_event_id=history["approval_event_id"], candidate=target_read,
                             expected_active_version_id=history["expected_active_version_id"],
                             log=log, objects=objects, references=references, verifier=verifier)
        active = self._fetch(_ACTIVE, self._head_id(**identity))
        latest = self._fetch(_HEADS, self._head_id(**identity))
        if (active is None or active["version_id"] != expected_active_version_id
                or expected_active_version_id == target_version_id or latest is None):
            raise ValueError("rollback has a stale or unchanged active predecessor")
        if latest["version_id"] not in {expected_latest_version_id, version_id}:
            raise ValueError("rollback has a stale latest-candidate predecessor")
        active_row = self._fetch(_VERSIONS, self._version_id(expected_active_version_id), all_valid=True)
        latest_row = self._fetch(_VERSIONS, self._version_id(expected_latest_version_id), all_valid=True)
        if active_row is None or latest_row is None:
            raise ValueError("rollback predecessor is absent")
        active_version = _version_from_record(json.loads(str(active_row["record_json"])))
        predecessor = _version_from_record(json.loads(str(latest_row["record_json"])))
        if any((item.subject_type, item.subject_id, item.projection_id)
               != (target.subject_type, target.subject_id, target.projection_id)
               for item in (active_version, predecessor)):
            raise ValueError("rollback predecessor crosses personal subject")
        active_history = self._history(active_version.projection_id, active_version.version_id)
        if (active_history["projection_sha256"] != active_version.projection_sha256
                or active_history["approval_event_id"] != active["approval_event_id"]
                or active_history["approval_event_sha256"] != active["approval_event_sha256"]):
            raise ValueError("rollback active predecessor has unbound activation lineage")
        # Revoked active evidence need not be reopened to replace unsafe state.
        active_approval = self._check_approval(
            approval_event_id=active_history["approval_event_id"],
            candidate=VerifiedStateCandidate(active_version.metadata_record(), b""),
            expected_active_version_id=active_history["expected_active_version_id"],
            log=log, objects=objects, references=references, verifier=verifier)
        if any(datetime.fromisoformat(produced_at.replace("Z", "+00:00")) <
               datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
               for timestamp in (predecessor.produced_at, active_approval.occurred_at)):
            raise ValueError("rollback predates its predecessor or authorization")
        binding = {
            "schema": "flora-personal-state-rollback-candidate-v1", "scope": self.scope.metadata_record(),
            "authority_namespace_id": self.authority_namespace_id, "rollback_id": rollback_id,
            "restored_version_id": version_id, "target_version_id": target.version_id,
            "target_projection_sha256": target.projection_sha256,
            "expected_active_version_id": expected_active_version_id,
            "expected_latest_version_id": expected_latest_version_id,
            "content_digest": target.content_digest, "produced_at": produced_at,
        }
        binding["record_sha256"] = canonical_sha256(binding)
        envelope_values = {k: v for k, v in target.envelope.__dict__.items() if k != "envelope_sha256"}
        envelope_values.update(record_id=version_id, created_at=produced_at,
                               valid_from=produced_at, valid_to=None, transaction_time=produced_at,
                               logical_clock=predecessor.envelope.logical_clock + 1,
                               generation=predecessor.envelope.generation + 1,
                               provenance_digest=binding["record_sha256"],
                               workflow_or_request_id=rollback_id, idempotency_key=version_id,
                               supersedes=(expected_latest_version_id,), superseded_by=(),
                               rollback_reference=target_version_id)
        envelope = MemoryUnitEnvelope.create(**envelope_values)
        material = {k: v for k, v in target.__dict__.items() if k != "projection_sha256"}
        material.update(envelope=envelope, version_id=version_id, generation=predecessor.generation + 1,
                        valid_from=produced_at, valid_to=None, produced_at=produced_at,
                        projection_state="candidate", responsible_component="flora-governed-rollback",
                        supersedes_version_id=expected_latest_version_id)
        restored = ProjectionVersion.create(**material)
        content = references.get(str(target_row["content_object_id"]))
        if content is None:
            raise ValueError("rollback target content is unavailable")
        key, action_key = self._rollback_key(version_id), self._rollback_id_key(rollback_id)
        prior = self._immutable(_ROLLBACKS, key)
        prior_action = self._immutable(_ROLLBACK_IDS, action_key)
        if ((prior is not None and prior != binding)
                or (prior_action is not None and prior_action != binding)):
            raise ValueError("rollback identifier was reused for a different target")
        if (prior is None) != (prior_action is None):
            raise ValueError("rollback action and target binding disagree")
        self.put_candidate(restored, content=content,
                           expected_previous_version_id=expected_latest_version_id, **inputs)
        if prior is None:
            with self.connection.transaction():
                self.connection.execute(
                    f"ASSERT NOT EXISTS (SELECT 1 FROM {_ROLLBACKS} FOR VALID_TIME ALL WHERE _id = %s::text)",
                    (key,))
                self.connection.execute(
                    f"ASSERT NOT EXISTS (SELECT 1 FROM {_ROLLBACK_IDS} FOR VALID_TIME ALL WHERE _id = %s::text)",
                    (action_key,))
                self._insert_receipt(_ROLLBACKS, key, binding)
                self._insert_receipt(_ROLLBACK_IDS, action_key, binding)
        return self._read_version(version_id=restored.version_id,
                                  projection_sha256=restored.projection_sha256,
                                  **identity, **inputs)
