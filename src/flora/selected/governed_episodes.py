"""Selected episode publication with external formation and semantic admission.

Episode boundaries/narratives remain supplied by the actual MFM elsewhere.
This module only binds an upstream EpisodeRecord candidate to qualified output,
independent exact adjudication, current originals and serialized publication.
"""
from __future__ import annotations

from dataclasses import dataclass, replace, field
import hashlib
import json
from typing import Any, Mapping, Protocol

from cognitive_kernel.canonical import canonical_json_bytes, canonical_sha256, normalize_timestamp, require_identifier, require_sha256
from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from cognitive_kernel.projection_contracts import EpisodeRecord
from .claims import XTDBClaimAuthority, _dml_placeholder, _record_json
from .development_sources import RegisteredDevelopmentSourceGuard
from .episodes import XTDBEpisodeCandidates, _VERSIONS as _CANDIDATES, _HEADS as _CANDIDATE_HEADS
from .experience import KurrentExperienceLog
from .formation_policy import XTDBFormationPermissionPolicy
from .formation_registry import RegisteredEncryptedFormationCustody, XTDBFormationSourceRegistry
from .object_store import EncryptedObjectPlane, RawObjectReference
from .personal_artifact_custody import RecoveredPersonalArtifact, XTDBPersonalArtifactCustody, episode_from_record, _SourceAuthorizedObjectReads
from .source_native import read_current_source_manifest

_ACCEPTED = "flora_governed_accepted_episodes"
_HEADS = "flora_governed_episode_publication_heads"


@dataclass(frozen=True)
class EpisodeAcceptanceRequest:
    scope: ProductHostScope
    authority_namespace_id: str
    request_id: str
    thread_id: str
    candidate_episode_id: str
    candidate_episode_sha256: str
    candidate_artifact_id: str
    candidate_artifact_sha256: str
    formation_receipt_ref: str
    adjudication_ref: str
    adjudication_policy_sha256: str
    expected_previous_episode_id: str | None
    expected_previous_episode_sha256: str | None
    adjudicated_at: str
    request_sha256: str

    @classmethod
    def create(cls, **values: Any):
        material = dict(values)
        for name in ("authority_namespace_id", "request_id", "thread_id", "candidate_episode_id",
                     "candidate_artifact_id", "formation_receipt_ref", "adjudication_ref"):
            material[name] = require_identifier(material[name], name)
        for name in ("candidate_episode_sha256", "candidate_artifact_sha256", "adjudication_policy_sha256"):
            material[name] = require_sha256(material[name], name)
        if material["expected_previous_episode_id"] is not None:
            material["expected_previous_episode_id"] = require_identifier(material["expected_previous_episode_id"], "expected_previous_episode_id")
        if material["expected_previous_episode_sha256"] is not None:
            material["expected_previous_episode_sha256"] = require_sha256(material["expected_previous_episode_sha256"], "expected_previous_episode_sha256")
        material["adjudicated_at"] = normalize_timestamp(material["adjudicated_at"])
        draft = cls(**material, request_sha256="0" * 64)
        draft._validate()
        result = replace(draft, request_sha256=canonical_sha256(draft.material_record()))
        result.validate()
        return result

    def _validate(self):
        self.scope.validate()
        for name in ("authority_namespace_id", "request_id", "thread_id", "candidate_episode_id",
                     "candidate_artifact_id", "formation_receipt_ref", "adjudication_ref"):
            if require_identifier(getattr(self, name), name) != getattr(self, name):
                raise ValueError("episode acceptance identifier is not canonical")
        for name in ("candidate_episode_sha256", "candidate_artifact_sha256", "adjudication_policy_sha256"):
            if require_sha256(getattr(self, name), name) != getattr(self, name):
                raise ValueError("episode acceptance digest is not canonical")
        if (self.expected_previous_episode_id is None) != (self.expected_previous_episode_sha256 is None):
            raise ValueError("episode acceptance predecessor must bind ID and digest")
        if self.expected_previous_episode_id is not None:
            if (require_identifier(self.expected_previous_episode_id, "expected_previous_episode_id") != self.expected_previous_episode_id
                    or require_sha256(self.expected_previous_episode_sha256, "expected_previous_episode_sha256") != self.expected_previous_episode_sha256):
                raise ValueError("episode acceptance predecessor is not canonical")
        if normalize_timestamp(self.adjudicated_at) != self.adjudicated_at:
            raise ValueError("episode acceptance time is not canonical")

    def material_record(self):
        self._validate()
        return {"schema": "flora-episode-acceptance-request-v1", "scope": self.scope.metadata_record(),
                **{key: value for key, value in self.__dict__.items() if key not in {"scope", "request_sha256"}}}

    def metadata_record(self):
        return {**self.material_record(), "request_sha256": self.request_sha256}

    def validate(self):
        self._validate()
        if canonical_sha256(self.material_record()) != self.request_sha256:
            raise ValueError("episode acceptance request digest changed")


def request_from_record(record):
    if record.get("schema") != "flora-episode-acceptance-request-v1":
        raise ValueError("episode acceptance request schema differs")
    values = {key: value for key, value in record.items() if key != "schema"}
    values["scope"] = ProductHostScope.create(**values["scope"])
    request = EpisodeAcceptanceRequest(**values)
    request.validate()
    if request.metadata_record() != record:
        raise ValueError("episode acceptance request is not canonical")
    return request


class EpisodeAdmissionVerifier(Protocol):
    """External qualified MFM-output lineage and independent semantic authority."""
    def qualified_formation(self, candidate: EpisodeRecord,
                            artifact: RecoveredPersonalArtifact,
                            formation_receipt_ref: str) -> bool: ...
    def authenticated_adjudication(self, request: EpisodeAcceptanceRequest,
                                   candidate: EpisodeRecord,
                                   artifact: RecoveredPersonalArtifact,
                                   event: ExperienceEvent) -> bool: ...


@dataclass(frozen=True)
class EpisodePublicationReceipt:
    episode_id: str
    episode_sha256: str
    candidate_sha256: str
    thread_id: str
    acceptance_request_sha256: str
    acceptance_event_id: str
    receipt_sha256: str


@dataclass(frozen=True)
class VerifiedAcceptedEpisode:
    record: dict[str, object]
    summary: bytes = field(repr=False)
    content: bytes = field(repr=False)
    source_event_ids: tuple[str, ...]
    publication: EpisodePublicationReceipt


def record_episode_acceptance_request(*, request: EpisodeAcceptanceRequest,
                                      parent_event_ids: tuple[str, ...],
                                      log: KurrentExperienceLog, objects: EncryptedObjectPlane,
                                      expected_revision: int):
    """Record an exact external request; writing it does not accept a narrative."""
    request.validate()
    if not request.scope == log.scope == objects.scope:
        raise ValueError("episode acceptance request crosses host scope")
    replayed = log.replay()
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision != len(replayed) - 1:
        raise ValueError("episode acceptance request has stale Experience revision")
    by_id = {event.event_id: event for event in replayed}
    if (not parent_event_ids or len(set(parent_event_ids)) != len(parent_event_ids)
            or not set(parent_event_ids).issubset(by_id)
            or any(by_id[parent].occurred_at > request.adjudicated_at for parent in parent_event_ids)):
        raise ValueError("episode acceptance request lacks earlier canonical parents")
    raw = objects.put(canonical_json_bytes(request.metadata_record()))
    event = ExperienceEvent.create(event_type="episode_acceptance", scope=request.scope,
        occurred_at=request.adjudicated_at, content_digest=raw.plaintext_sha256,
        provenance=ProvenanceReference.create(provenance_type="derived_inference",
            source_reference_ids=parent_event_ids, derivation_activity_id=request.request_id,
            responsible_component="external_episode_adjudication"),
        retention_class="ordinary_experience", storage_tier="raw_buffer",
        parent_event_ids=parent_event_ids, payload_reference=raw.object_id)
    log.append(event, expected_revision=expected_revision)
    from .decision_outcome import RecordedEvent
    return RecordedEvent(event, raw)


class XTDBGovernedEpisodes(XTDBEpisodeCandidates):
    """Selected candidate/accepted episode authority; semantics stay external."""
    def __init__(self, *, scope: ProductHostScope, authority_namespace_id: str, connection: Any,
                 registry: XTDBFormationSourceRegistry, policy: XTDBFormationPermissionPolicy,
                 custody: XTDBPersonalArtifactCustody, verifier: EpisodeAdmissionVerifier):
        super().__init__(scope=scope, authority_namespace_id=authority_namespace_id, connection=connection)
        if (not scope == registry.scope == policy.scope == custody.scope
                or not authority_namespace_id == registry.authority_namespace_id
                == policy.authority_namespace_id == custody.authority_namespace_id
                or policy.registry is not registry):
            raise ValueError("episode authority crosses registered source or private custody scope")
        self.registry, self.policy, self.custody, self.verifier = registry, policy, custody, verifier
        self.guard = RegisteredDevelopmentSourceGuard(scope, authority_namespace_id, registry, policy)

    def _check_sources(self, record: Mapping[str, object], *, claims: XTDBClaimAuthority,
                       log: KurrentExperienceLog, objects: EncryptedObjectPlane,
                       references: Mapping[str, RawObjectReference]) -> None:
        if record["member_candidate_ids"] or (not record["member_evidence_ids"] and not record["member_claim_version_ids"]):
            raise ValueError("episode needs supported original evidence or Claim lineage")
        events = {event.event_id: event for event in log.replay()}
        for event_id in record["member_evidence_ids"]:
            if event_id not in events or events[event_id].occurred_at > record["formed_at"]:
                raise ValueError("episode cites absent or later observed evidence")
        self.guard.check(source_claim_version_ids=tuple(record["member_claim_version_ids"]),
            source_evidence_ids=tuple(record["member_evidence_ids"]),
            source_records=tuple(record["envelope"]["source_records"]),
            source_observed_by=str(record["formed_at"]),
            claims=claims, log=log, objects=objects, references=references)

    def _candidate_read_gate(self, candidate, *, thread_id, claims, log, reading_existing=False):
        source_ids = self._source_lineage(candidate, claims=claims, log=log)
        head = self._fetch(_CANDIDATE_HEADS, self._key("thread", thread_id))
        if reading_existing and (head is None or head["episode_id"] != candidate.episode_id
                or head["episode_sha256"] != candidate.episode_sha256):
            raise ValueError("episode candidate changed before private read")
        def fresh():
            if (self._source_lineage(candidate, claims=claims, log=log) != source_ids
                    or self._fetch(_CANDIDATE_HEADS, self._key("thread", thread_id)) != head):
                raise ValueError("episode candidate authority changed during private read")
            return True
        return fresh

    def put_candidate(self, episode: EpisodeRecord, **kwargs):
        episode.validate()
        inputs = {key: kwargs[key] for key in ("claims", "log", "objects", "references")}
        self._check_sources(episode.metadata_record(), **inputs)
        fresh = self._candidate_read_gate(episode, thread_id=kwargs["thread_id"],
                                         claims=kwargs["claims"], log=kwargs["log"])
        fresh()
        guarded = {**kwargs, "objects": _SourceAuthorizedObjectReads(kwargs["objects"], fresh)}
        super().put_candidate(episode, **guarded)
        # A successful registration intentionally moves the candidate head.
        # Revalidate source authority using the original objects after commit.
        self._check_sources(episode.metadata_record(), **inputs)

    def read_latest_candidate(self, **kwargs):
        head = self._fetch(_CANDIDATE_HEADS, self._key("thread", kwargs["thread_id"]))
        if head is None:
            raise KeyError(kwargs["thread_id"])
        candidate, row = self._candidate_metadata(head["episode_id"])
        fresh = self._candidate_read_gate(candidate, thread_id=kwargs["thread_id"],
                                         claims=kwargs["claims"], log=kwargs["log"], reading_existing=True)
        guarded = {**kwargs, "objects": _SourceAuthorizedObjectReads(kwargs["objects"], fresh)}
        result = super().read_latest_candidate(**guarded)
        fresh()
        self._check_sources(result.record, **{key: kwargs[key]
            for key in ("claims", "log", "objects", "references")})
        if self._fetch(_CANDIDATE_HEADS, self._key("thread", kwargs["thread_id"])) != head:
            raise ValueError("episode candidate head changed during governed read")
        return result

    def _immutable(self, table, key):
        row = self._fetch(table, key, all_valid=True)
        if row is None:
            return None
        record = json.loads(str(row["record_json"]))
        if (row["scope_digest"] != self.scope_digest
                or record["scope"] != self.scope.metadata_record()
                or record["authority_namespace_id"] != self.authority_namespace_id
                or record["record_sha256"] != row["record_sha256"]
                or canonical_sha256({key: value for key, value in record.items() if key != "record_sha256"})
                != record["record_sha256"]):
            raise ValueError("episode publication immutable metadata changed")
        return record

    def _insert(self, table, key, record):
        values = {"_id": key, "scope_digest": self.scope_digest,
                  "record_sha256": record["record_sha256"], "record_json": _record_json(record)}
        self.connection.execute(f"INSERT INTO {table} ({', '.join(values)}) VALUES ("
            + ", ".join(_dml_placeholder(value) for value in values.values()) + ")", tuple(values.values()))

    def _head(self, thread_id):
        row = self._fetch(_HEADS, self._key("publication-thread", thread_id))
        if row is None:
            return None
        record = json.loads(str(row["record_json"]))
        if (record.get("schema") != "flora-current-episode-publication-v1"
                or record["thread_id"] != thread_id or row["scope_digest"] != self.scope_digest
                or record["scope"] != self.scope.metadata_record()
                or record["authority_namespace_id"] != self.authority_namespace_id
                or record["record_sha256"] != row["record_sha256"]
                or canonical_sha256({key: value for key, value in record.items() if key != "record_sha256"})
                != record["record_sha256"]):
            raise ValueError("episode publication head changed")
        return record

    def _receipt(self, record):
        values = record["publication"]
        result = EpisodePublicationReceipt(**values)
        if canonical_sha256({key: value for key, value in values.items() if key != "receipt_sha256"}) != result.receipt_sha256:
            raise ValueError("episode publication receipt changed")
        return result

    def _request_event(self, request, event_id, log):
        replayed = log.replay()
        event = next((event for event in replayed if event.event_id == event_id), None)
        registered = self.registry.lookup(event_id)
        expected_digest = hashlib.sha256(canonical_json_bytes(request.metadata_record())).hexdigest()
        if (event is None or event.event_type != "episode_acceptance" or event.scope != self.scope
                or event.occurred_at != request.adjudicated_at or event.content_digest != expected_digest
                or registered is None or registered.evidence.ref_id != event_id
                or registered.evidence.scope != self.scope
                or registered.evidence.authority_namespace_id != self.authority_namespace_id
                or registered.object_ref != event.payload_reference
                or registered.evidence.content_digest != event.content_digest
                or registered.evidence.parent_refs != event.parent_event_ids
                or self.policy.permits(registered, "personal_judgment") is not True):
            raise ValueError("episode adjudication lacks current exact request authority")
        return event, registered

    def _candidate_metadata(self, episode_id):
        row = self._fetch(_CANDIDATES, self._key("episode", episode_id), all_valid=True)
        if row is None:
            raise ValueError("episode candidate is absent")
        candidate = episode_from_record(json.loads(str(row["record_json"])))
        if (candidate.episode_id != episode_id or candidate.episode_state != "candidate"
                or row["episode_sha256"] != candidate.episode_sha256
                or candidate.scope != self.scope or candidate.envelope.authority_namespace_id != self.authority_namespace_id):
            raise ValueError("episode candidate metadata differs")
        return candidate, row

    def _artifact_metadata(self, request, candidate, event, log, candidate_row):
        metadata = self.custody.metadata(request.candidate_artifact_id)
        events = log.replay()
        position = next(i for i, item in enumerate(events) if item.event_id == event.event_id)
        stored = None if metadata is None else next(((i, item) for i, item in enumerate(events)
            if item.event_id == metadata["event_id"]), None)
        attachments = {} if metadata is None else {role: raw for role, raw in metadata["attachments"]}
        if (metadata is None or metadata["kind"] != "episode" or stored is None
                or stored[0] != metadata["event_stream_position"]
                or stored[1].scope != self.scope
                or stored[1].event_type != "private_personal_artifact"
                or stored[1].event_sha256 != metadata["event_sha256"]
                or stored[1].payload_reference != metadata["manifest"]["object_id"]
                or stored[1].content_digest != metadata["manifest"]["plaintext_sha256"]
                or stored[1].occurred_at > request.adjudicated_at
                or set(attachments) != {"summary", "content"}
                or attachments["summary"]["object_id"] != candidate_row["summary_object_id"]
                or attachments["content"]["object_id"] != candidate_row["content_object_id"]
                or metadata["record_sha256"] != request.candidate_artifact_sha256
                or metadata["event_stream_position"] >= position
                or metadata["contract"] != candidate.metadata_record()):
            raise ValueError("episode request lacks exact earlier private candidate custody")
        return metadata

    def _source_lineage(self, episode, *, control_event_ids=(), claims, log):
        """Resolve current original/control source authority without plaintext."""
        source_ids = (set(episode.member_evidence_ids) | set(control_event_ids)
                      | (set(episode.envelope.source_records) - set(episode.member_claim_version_ids)))
        if claims.scope != self.scope or claims.authority_namespace_id != self.authority_namespace_id:
            raise ValueError("episode source lineage crosses Claim authority")
        for version_id in episode.member_claim_version_ids:
            version = claims.load_version(version_id)
            if (version["envelope"]["scope"] != self.scope.metadata_record()
                    or version["envelope"]["authority_namespace_id"] != self.authority_namespace_id):
                raise ValueError("accepted episode Claim crosses authority")
            manifest = read_current_source_manifest(claim_id=version["claim_id"], authority=claims, log=log)
            if manifest.claim_version_id != version_id:
                raise ValueError("accepted episode cites a superseded Claim")
            source_ids.update(source.event_id for source in manifest.sources)
        replayed = {event.event_id: event for event in log.replay()}
        pending = list(source_ids)
        sources = {}
        while pending:
            source_id = pending.pop()
            source = self.registry.lookup(source_id)
            original = replayed.get(source_id)
            if (source is None or original is None or original.scope != self.scope
                    or source.evidence.ref_id != source_id or source.evidence.scope != self.scope
                    or source.evidence.authority_namespace_id != self.authority_namespace_id
                    or source.object_ref != original.payload_reference
                    or source.evidence.content_digest != original.content_digest
                    or source.evidence.parent_refs != original.parent_event_ids
                    or self.policy.permits(source, "personal_judgment") is not True):
                raise ValueError("accepted episode source use is not currently permitted")
            sources[source_id] = source
            for parent in source.evidence.parent_refs:
                if parent not in source_ids:
                    source_ids.add(parent)
                    pending.append(parent)
        for source_id, source in sources.items():
            if self.registry.lookup(source_id) != source or self.policy.permits(source, "personal_judgment") is not True:
                raise ValueError("accepted episode source authority changed during lineage resolution")
        for version_id in episode.member_claim_version_ids:
            version = claims.load_version(version_id)
            if read_current_source_manifest(claim_id=version["claim_id"], authority=claims,
                                            log=log).claim_version_id != version_id:
                raise ValueError("accepted episode Claim changed during lineage resolution")
        return tuple(sorted(source_ids))

    def _accept_snapshot(self, request, request_event_id, *, claims, log):
        candidate, row = self._candidate_metadata(request.candidate_episode_id)
        if candidate.episode_sha256 != request.candidate_episode_sha256 or row["thread_id"] != request.thread_id:
            raise ValueError("episode admission candidate metadata changed")
        event, registered = self._request_event(request, request_event_id, log)
        artifact = self._artifact_metadata(request, candidate, event, log, row)
        sources = self._source_lineage(candidate, control_event_ids=(event.event_id,), claims=claims, log=log)
        draft = self._fetch(_CANDIDATE_HEADS, self._key("thread", request.thread_id))
        published = self._immutable(_ACCEPTED, self._key("accepted-episode", candidate.episode_id))
        if published is not None and (published["request"] != request.metadata_record()
                or published["request_event_sha256"] != event.event_sha256
                or published["publication"]["candidate_sha256"] != candidate.episode_sha256):
            raise ValueError("episode acceptance identifier was reused")
        if published is None and (draft is None or draft["episode_id"] != candidate.episode_id
                or draft["episode_sha256"] != candidate.episode_sha256):
            raise ValueError("episode admission cites a stale candidate head")
        head = self._head(request.thread_id)
        if published is None and ((head is None and request.expected_previous_episode_id is not None)
                or (head is not None and (head["episode_id"] != request.expected_previous_episode_id
                    or head["episode_sha256"] != request.expected_previous_episode_sha256))):
            raise ValueError("episode acceptance has a stale publication predecessor")
        return candidate, row, event, registered, artifact, sources, draft, head, published

    def _verify_external(self, request, candidate, artifact, event, source_authorizer=None):
        def fresh():
            if source_authorizer is not None and source_authorizer() is not True:
                raise PermissionError("episode source authority changed during external verification")
        fresh()
        if self.verifier is None:
            raise ValueError("episode lacks qualified formation and independent semantic admission")
        qualified = self.verifier.qualified_formation(candidate, artifact, request.formation_receipt_ref)
        fresh()
        if qualified is not True:
            raise ValueError("episode lacks qualified formation and independent semantic admission")
        admitted = self.verifier.authenticated_adjudication(request, candidate, artifact, event)
        fresh()
        if admitted is not True:
            raise ValueError("episode lacks qualified formation and independent semantic admission")

    def accept(self, *, request: EpisodeAcceptanceRequest, request_event_id: str,
               claims: XTDBClaimAuthority, log: KurrentExperienceLog,
               objects: EncryptedObjectPlane, references: Mapping[str, RawObjectReference]):
        request.validate()
        if request.scope != self.scope or request.authority_namespace_id != self.authority_namespace_id:
            raise ValueError("episode acceptance crosses host or authority")
        candidate, row = self._candidate_metadata(request.candidate_episode_id)
        if (row["thread_id"] != request.thread_id or candidate.episode_sha256 != request.candidate_episode_sha256
                or candidate.formed_at > request.adjudicated_at):
            raise ValueError("episode request differs from its exact candidate")
        inputs = dict(claims=claims, log=log, objects=objects, references=references)
        self._check_sources(candidate.metadata_record(), **inputs)
        event, registered = self._request_event(request, request_event_id, log)
        self._artifact_metadata(request, candidate, event, log, row)
        if not set(candidate.member_evidence_ids).issubset(event.parent_event_ids):
            raise ValueError("episode acceptance omits its original Experience parents")
        snapshot = self._accept_snapshot(request, request_event_id, claims=claims, log=log)
        def fresh():
            if self._accept_snapshot(request, request_event_id, claims=claims, log=log) != snapshot:
                raise ValueError("episode admission authority changed during private read")
            return True
        fresh()
        raw_request = RegisteredEncryptedFormationCustody(registry=self.registry,
            objects=_SourceAuthorizedObjectReads(objects, fresh)).read(self.scope, registered.object_ref)
        fresh()
        if raw_request != canonical_json_bytes(request.metadata_record()):
            raise ValueError("episode acceptance request bytes changed")
        fresh()
        artifact = self.custody.read(request.candidate_artifact_id, log=log, objects=objects,
                                     source_authorizer=fresh)
        fresh()
        if artifact.kind != "episode" or artifact.contract != candidate.metadata_record():
            raise ValueError("episode candidate private artifact differs")
        self._verify_external(request, candidate, artifact, event, source_authorizer=fresh)
        fresh()
        material = {key: value for key, value in candidate.__dict__.items() if key != "episode_sha256"}
        accepted = EpisodeRecord.create(**{**material, "episode_state": "accepted"})
        receipt_values = dict(episode_id=accepted.episode_id, episode_sha256=accepted.episode_sha256,
            candidate_sha256=candidate.episode_sha256, thread_id=request.thread_id,
            acceptance_request_sha256=request.request_sha256, acceptance_event_id=event.event_id)
        receipt = EpisodePublicationReceipt(**receipt_values, receipt_sha256=canonical_sha256(receipt_values))
        publication = {"schema": "flora-accepted-episode-publication-v1", "scope": self.scope.metadata_record(),
            "authority_namespace_id": self.authority_namespace_id, "episode": accepted.metadata_record(),
            "request": request.metadata_record(), "request_event_sha256": event.event_sha256,
            "summary_object_id": row["summary_object_id"], "content_object_id": row["content_object_id"],
            "publication": receipt.__dict__}
        publication["record_sha256"] = canonical_sha256(publication)
        publication_key = self._key("accepted-episode", accepted.episode_id)
        prior = self._immutable(_ACCEPTED, publication_key)
        if prior is not None:
            if prior != publication:
                raise ValueError("episode acceptance identifier was reused")
            return receipt
        head = self._head(request.thread_id)
        if head is None:
            if request.expected_previous_episode_id is not None:
                raise ValueError("episode acceptance predecessor is absent")
        elif (head["episode_id"] != request.expected_previous_episode_id
                or head["episode_sha256"] != request.expected_previous_episode_sha256):
            raise ValueError("episode acceptance has a stale publication predecessor")
        # Reapply authority after potentially slow supplied semantic services.
        self._check_sources(candidate.metadata_record(), **inputs)
        if self._request_event(request, event.event_id, log)[0] != event:
            raise ValueError("episode request authority changed before publication")
        current = {"schema": "flora-current-episode-publication-v1", "scope": self.scope.metadata_record(),
            "authority_namespace_id": self.authority_namespace_id, "thread_id": request.thread_id,
            "episode_id": accepted.episode_id, "episode_sha256": accepted.episode_sha256,
            "generation": accepted.generation, "publication_sha256": publication["record_sha256"]}
        current["record_sha256"] = canonical_sha256(current)
        key = self._key("publication-thread", request.thread_id)
        with self.connection.transaction():
            self.connection.execute(f"ASSERT NOT EXISTS (SELECT 1 FROM {_ACCEPTED} FOR VALID_TIME ALL WHERE _id = %s::text)",
                                    (publication_key,))
            if head is None:
                self.connection.execute(f"ASSERT NOT EXISTS (SELECT 1 FROM {_HEADS} WHERE _id = %s::text)", (key,))
            else:
                self.connection.execute(f"ASSERT EXISTS (SELECT 1 FROM {_HEADS} WHERE _id = %s::text AND record_sha256 = %s::text)",
                                        (key, head["record_sha256"]))
            self.connection.execute(f"ASSERT EXISTS (SELECT 1 FROM {_CANDIDATE_HEADS} WHERE _id = %s::text AND episode_id = %s::text)",
                                    (self._key("thread", request.thread_id), candidate.episode_id))
            self._insert(_ACCEPTED, publication_key, publication)
            self._insert(_HEADS, key, current)
        return receipt

    def current_lineage(self, episode_id: str, *, claims: XTDBClaimAuthority, log: KurrentExperienceLog):
        """Current registered lineage/authority metadata; opens no private bytes."""
        record = self._immutable(_ACCEPTED, self._key("accepted-episode", episode_id))
        if record is None or record.get("schema") != "flora-accepted-episode-publication-v1":
            raise ValueError("episode has no governed accepted publication")
        episode = episode_from_record(record["episode"])
        publication = self._receipt(record)
        head = self._head(publication.thread_id)
        request = request_from_record(record["request"])
        if (request.scope != self.scope or request.authority_namespace_id != self.authority_namespace_id
                or request.candidate_episode_id != episode_id
                or request.thread_id != publication.thread_id
                or publication.episode_id != episode_id
                or publication.acceptance_request_sha256 != request.request_sha256
                or episode.episode_id != episode_id or episode.episode_state != "accepted"
                or episode.scope != self.scope or episode.envelope.authority_namespace_id != self.authority_namespace_id
                or publication.episode_sha256 != episode.episode_sha256 or head is None
                or head["episode_id"] != episode_id or head["episode_sha256"] != episode.episode_sha256
                or head["generation"] != episode.generation
                or head["publication_sha256"] != record["record_sha256"]):
            raise ValueError("episode publication is stale, superseded or unbound")
        event, registered = self._request_event(request, publication.acceptance_event_id, log)
        if event.event_sha256 != record["request_event_sha256"]:
            raise ValueError("episode accepted request event changed")
        candidate, row = self._candidate_metadata(episode_id)
        expected_accepted = EpisodeRecord.create(**{**{key: value for key, value in candidate.__dict__.items()
            if key != "episode_sha256"}, "episode_state": "accepted"})
        if (row["thread_id"] != request.thread_id
                or candidate.episode_sha256 != request.candidate_episode_sha256
                or candidate.episode_sha256 != publication.candidate_sha256
                or episode != expected_accepted):
            raise ValueError("episode publication lost its exact candidate lineage")
        self._artifact_metadata(request, candidate, event, log, row)
        if (record["summary_object_id"] != row["summary_object_id"]
                or record["content_object_id"] != row["content_object_id"]):
            raise ValueError("episode publication lost its exact private candidate references")
        source_ids = self._source_lineage(episode, control_event_ids=(event.event_id,), claims=claims, log=log)
        if self._head(publication.thread_id) != head:
            raise ValueError("episode head changed during lineage resolution")
        return episode, publication, request, tuple(sorted(source_ids)), record

    def read_accepted(self, episode_id: str, *, claims: XTDBClaimAuthority, log: KurrentExperienceLog,
                      objects: EncryptedObjectPlane, references: Mapping[str, RawObjectReference]):
        inputs = dict(claims=claims, log=log, objects=objects, references=references)
        lineage = self.current_lineage(episode_id, claims=claims, log=log)
        episode, publication, request, source_ids, record = lineage
        def fresh():
            if self.current_lineage(episode_id, claims=claims, log=log) != lineage:
                raise ValueError("episode authority changed during accepted read")
            return True
        self._check_sources(episode.metadata_record(), **inputs)
        candidate, row = self._candidate_metadata(episode_id)
        event, registered = self._request_event(request, publication.acceptance_event_id, log)
        fresh()
        raw_request = RegisteredEncryptedFormationCustody(registry=self.registry,
            objects=_SourceAuthorizedObjectReads(objects, fresh)).read(self.scope, registered.object_ref)
        fresh()
        if raw_request != canonical_json_bytes(request.metadata_record()):
            raise ValueError("accepted episode adjudication bytes changed")
        self._artifact_metadata(request, candidate, event, log, row)
        fresh()
        artifact = self.custody.read(request.candidate_artifact_id, log=log, objects=objects,
                                     source_authorizer=fresh)
        fresh()
        if (artifact.kind != "episode" or artifact.contract != candidate.metadata_record()
                or dict(artifact.references).get("summary").object_id != record["summary_object_id"]
                or dict(artifact.references).get("content").object_id != record["content_object_id"]):
            raise ValueError("accepted episode private candidate contract changed")
        self._verify_external(request, candidate, artifact, event, source_authorizer=fresh)
        fresh()
        # Custody already authenticated each exact attachment through the live
        # metadata gate. Reuse those bytes instead of reopening private objects.
        summary_bytes, content_bytes = dict(artifact.content)["summary"], dict(artifact.content)["content"]
        if (hashlib.sha256(summary_bytes).hexdigest() != episode.summary_content_digest
                or hashlib.sha256(content_bytes).hexdigest() != episode.full_content_digest):
            raise ValueError("accepted episode private content changed")
        self._check_sources(episode.metadata_record(), **inputs)
        fresh()
        return VerifiedAcceptedEpisode(episode.metadata_record(), summary_bytes, content_bytes, source_ids, publication)
