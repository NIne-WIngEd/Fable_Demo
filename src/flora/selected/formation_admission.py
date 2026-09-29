"""Governed Claim admission from durable, externally supplied MFM proposals.

The semantic adapter and adjudicator are independent supplied services. Source
authentication, a fluent proposal, and successful schema checks are not semantic
acceptance. This narrow path supports host Claim/preference additions and exact
correction revisions; other conflict operations remain explicit refusals.

One XTDB DML transaction writes authority records, property occupancy, the
namespace sequence and an idempotency receipt. Kurrent source positions remain
separate from Claim store sequences. Derived index work happens after admission.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Protocol

from cognitive_kernel.adjudication_contracts import (
    AdjudicationRecord, ClaimCandidate, ClaimConflictRecord, ClaimEvidenceRelation,
)
from cognitive_kernel.canonical import canonical_sha256, normalize_timestamp, require_identifier
from cognitive_kernel.claim_contracts import ClaimVersion, CurrentClaimProjection
from cognitive_kernel.formation_contracts import FormationProposal, validate_formation_binding
from cognitive_kernel.formation_sources import RegisteredFormationStore
from cognitive_kernel.memory_contracts import MemoryUnitEnvelope

from .authority_binding import bind_claim_source
from .claims import (
    XTDBClaimAuthority, _CURRENT, _EVIDENCE, _HEAD, _IDENTITIES, _VERSIONS,
    _record_json, _rows, _timestamp,
)
from .experience import KurrentExperienceLog
from .formation_candidates import RecoveredFormationCandidate, XTDBFormationProposalCandidates
from .object_store import EncryptedObjectPlane

_COUNTER = "flora_claim_admission_namespace_counters"
_SLOTS = "flora_claim_admission_property_slots"
_CANDIDATES = "flora_admitted_claim_candidates"
_ADJUDICATIONS = "flora_claim_adjudications"
_CONFLICTS = "flora_claim_conflict_records"
_RECEIPTS = "flora_claim_admission_receipts"
_CONTROLLER = "flora-governed-claim-admission-v1"


@dataclass(frozen=True)
class CandidateInterpretation:
    candidate: ClaimCandidate
    relations: tuple[ClaimEvidenceRelation, ...]


class FormationClaimAdapter(Protocol):
    """External semantic interpretation, never replaced by source authentication."""

    def to_candidate(self, *, recovered: RecoveredFormationCandidate,
                     proposal: FormationProposal, value: Any,
                     request_digest: str) -> CandidateInterpretation: ...


class FormationAdmissionVerifier(Protocol):
    """Independent proof for the exact semantic adjudication and experiment scope."""

    def authenticated_adjudication(self, adjudication: AdjudicationRecord,
                                  candidate: ClaimCandidate,
                                  recovered: RecoveredFormationCandidate,
                                  experiment_world_id: str | None) -> bool: ...


@dataclass(frozen=True)
class BoundFormationClaim:
    recovered: RecoveredFormationCandidate
    proposal_id: str
    interpretation: CandidateInterpretation


@dataclass(frozen=True)
class FormationAdmissionReceipt:
    claim_id: str
    claim_version_id: str
    version_sequence: int
    store_sequence: int
    event_stream_position: int
    projection_id: str
    version_sha256: str
    projection_sha256: str
    adjudication_id: str
    request_digest: str
    receipt_sha256: str


def formation_claim_request_digest(recovered: RecoveredFormationCandidate,
                                   proposal_id: str) -> str:
    proposal = next((item for item in recovered.bundle.proposals
                     if item.proposal_id == proposal_id), None)
    if proposal is None:
        raise ValueError("formation proposal is absent from its recorded bundle")
    value = dict(recovered.values).get(proposal.value_ref)
    if value is None:
        raise ValueError("formation proposal lacks its recorded canonical value")
    return canonical_sha256({
        "schema": "flora-formation-claim-request-v1",
        "bundle_sha256": recovered.bundle.content_digest(),
        "proposal": proposal.record(), "value": value.metadata_record(),
        "candidate_event_sha256": recovered.recorded.event.event_sha256,
    })


def _new_envelope(template: MemoryUnitEnvelope, *, record_id: str,
                  record_type: str, authority_role: str,
                  sources: tuple[str, ...], digest: str, content_digest: str,
                  generation: int, supersedes: tuple[str, ...] = (),
                  valid_from: str | None = None, valid_to: str | None = None) -> MemoryUnitEnvelope:
    material = template.material_record()
    material.pop("scope")
    material.update(
        record_id=record_id, record_type=record_type, authority_role=authority_role,
        source_records=tuple(sorted(set(sources))), causal_parents=tuple(sorted(set(sources))),
        generation=generation, logical_clock=generation, state="committed",
        provenance_digest=digest, content_digest=content_digest,
        writer="formation_claim_admission", supersedes=supersedes, superseded_by=(),
        valid_from=valid_from or template.valid_from, valid_to=valid_to,
    )
    return MemoryUnitEnvelope.create(scope=template.scope, **material)


def _receipt(record: dict[str, object]) -> FormationAdmissionReceipt:
    material = record["receipt"]
    result = FormationAdmissionReceipt(**material)
    if canonical_sha256({key: value for key, value in material.items()
                         if key != "receipt_sha256"}) != result.receipt_sha256:
        raise ValueError("formation admission receipt digest changed")
    return result


class XTDBFormationClaimAdmission:
    def __init__(self, *, authority: XTDBClaimAuthority,
                 candidates: XTDBFormationProposalCandidates,
                 experiment_world_id: str | None = None):
        if (authority.scope != candidates.scope
                or authority.authority_namespace_id != candidates.authority_namespace_id):
            raise ValueError("formation admission crosses scope or authority")
        if experiment_world_id is not None and require_identifier(
            experiment_world_id, "experiment_world_id") != experiment_world_id:
            raise ValueError("experiment world ID must be canonical")
        self.authority, self.candidates = authority, candidates
        self.scope = authority.scope
        self.authority_namespace_id = authority.authority_namespace_id
        self.experiment_world_id = experiment_world_id

    def _row(self, table: str, identifier: str) -> dict[str, object] | None:
        return self.authority._fetch_record(
            table=table, row_id=self.authority._row_id(identifier), all_valid=(table != _COUNTER))

    def _read_record(self, row: dict[str, object], *, identifier: str) -> dict[str, object]:
        record = json.loads(str(row["record_json"]))
        if (row["_id"] != self.authority._row_id(identifier)
                or row["scope_digest"] != self.authority.scope_digest
                or record["scope"] != self.scope.metadata_record()
                or record["authority_namespace_id"] != self.authority_namespace_id
                or record["record_sha256"] != row["record_sha256"]
                or canonical_sha256({key: value for key, value in record.items()
                                     if key != "record_sha256"}) != row["record_sha256"]):
            raise ValueError("formation admission metadata changed")
        return record

    def _insert_record(self, table: str, identifier: str, record: dict[str, object],
                       at: str, *, immutable: bool = True) -> None:
        record = {"scope": self.scope.metadata_record(),
                  "authority_namespace_id": self.authority_namespace_id, **record}
        record["record_sha256"] = canonical_sha256(record)
        row_id = self.authority._row_id(identifier)
        if immutable:
            self.authority.connection.execute(
                f"ASSERT NOT EXISTS (SELECT 1 FROM {table} FOR VALID_TIME ALL WHERE _id = %s::text)",
                (row_id,))
        self.authority._insert(
            table=table, columns={"_id": row_id, "scope_digest": self.authority.scope_digest,
                                  "record_sha256": record["record_sha256"],
                                  "record_json": _record_json(record)},
            valid_from=_timestamp(at), valid_to=None)

    def prepare(self, *, bundle_id: str, proposal_id: str, adapter: FormationClaimAdapter,
                log: KurrentExperienceLog, objects: EncryptedObjectPlane,
                source_store: RegisteredFormationStore) -> BoundFormationClaim:
        recovered = self.candidates.read_candidate(
            bundle_id, log=log, objects=objects, source_store=source_store)
        proposal = next((item for item in recovered.bundle.proposals
                         if item.proposal_id == proposal_id), None)
        if proposal is None:
            raise ValueError("formation proposal is absent from its recorded bundle")
        value = dict(recovered.values).get(proposal.value_ref)
        digest = formation_claim_request_digest(recovered, proposal_id)
        interpretation = adapter.to_candidate(
            recovered=recovered, proposal=proposal, value=value, request_digest=digest)
        bound = BoundFormationClaim(recovered, proposal_id, interpretation)
        self._validate_binding(bound)
        return bound

    def _validate_binding(self, bound: BoundFormationClaim) -> FormationProposal:
        recovered = bound.recovered
        validate_formation_binding(recovered.packet, recovered.bundle)
        if (recovered.bundle.scope != self.scope
                or recovered.bundle.authority_namespace_id != self.authority_namespace_id):
            raise ValueError("formation admission bundle crosses scope")
        proposal = next((item for item in recovered.bundle.proposals
                         if item.proposal_id == bound.proposal_id), None)
        if proposal is None or proposal.domain != "host" or proposal.kind not in {
            "claim", "preference", "correction_request"
        }:
            raise ValueError("unsupported formation Claim admission kind or domain")
        candidate, relations = bound.interpretation.candidate, bound.interpretation.relations
        candidate.validate()
        self.authority._assert_envelope(candidate)
        if (candidate.request_digest != formation_claim_request_digest(recovered, bound.proposal_id)
                or candidate.value != dict(recovered.values)[proposal.value_ref]
                or candidate.identity.canonical_subject.type_tag != "identifier"
                or candidate.identity.canonical_subject.value() != proposal.subject_ref
                or "host" not in candidate.identity.semantic_scope
                or candidate.proposed_action not in {"add", "revise"}
                or (proposal.kind == "correction_request") != (candidate.proposed_action == "revise")
                or candidate.candidate_state not in {"submitted", "eligible"}
                or not {recovered.bundle.bundle_id, proposal.proposal_id,
                        recovered.recorded.event.event_id}.issubset(candidate.envelope.source_records)):
            raise ValueError("Claim interpretation differs from its exact formation proposal")
        if (not isinstance(relations, tuple)
                or len(relations) != len(candidate.evidence_relation_ids)
                or {relation.relation_id for relation in relations} != set(candidate.evidence_relation_ids)
                or {relation.evidence_record_id for relation in relations} != set(proposal.evidence_refs)):
            raise ValueError("Claim candidate lacks its exact proposal evidence relations")
        evidence = {ref.ref_id: ref for ref in recovered.packet.evidence}
        for relation in relations:
            relation.validate()
            self.authority._assert_envelope(relation)
            if (relation.target_record_type != "claim_candidate"
                    or relation.target_record_id != candidate.candidate_id
                    or relation.source_class != evidence[relation.evidence_record_id].role):
                raise ValueError("Claim candidate relation changed target or source provenance")
        return proposal

    def admit(self, bound: BoundFormationClaim, *, adjudication: AdjudicationRecord,
              verifier: FormationAdmissionVerifier, log: KurrentExperienceLog,
              objects: EncryptedObjectPlane, source_store: RegisteredFormationStore,
              expected_previous: CurrentClaimProjection | None = None,
              conflict: ClaimConflictRecord | None = None) -> FormationAdmissionReceipt:
        fresh = self.candidates.read_candidate(
            bound.recovered.bundle.bundle_id, log=log, objects=objects, source_store=source_store)
        if fresh != bound.recovered:
            raise ValueError("formation candidate changed before admission")
        proposal = self._validate_binding(bound)
        candidate, candidate_relations = bound.interpretation.candidate, bound.interpretation.relations
        adjudication.assert_adjudicates(candidate)
        self.authority._assert_envelope(adjudication)
        if (adjudication.execution_mode != "production" or adjudication.canonical_effect is not True
                or adjudication.outcome != candidate.proposed_action
                or adjudication.evidence_relation_ids != candidate.evidence_relation_ids):
            raise ValueError("adjudication does not authorize this exact canonical action")
        # Derived evidence retains the authority limits of every registered
        # ancestor. Citing only a derived child cannot turn a reconstruction
        # into an owner statement.
        evidence = {ref.ref_id: ref for ref in fresh.packet.evidence}
        closure, pending = set(), list(proposal.evidence_refs)
        while pending:
            ref_id = pending.pop()
            if ref_id in closure:
                continue
            ref = evidence.get(ref_id)
            if ref is None:
                raise ValueError("Claim evidence lacks its registered parent closure")
            closure.add(ref_id)
            pending.extend(ref.parent_refs)
        synthetic = any(evidence[ref_id].role in {
            "generated_reconstruction", "hypothetical_training"} for ref_id in closure)
        if synthetic and (self.experiment_world_id is None
                          or self.experiment_world_id not in candidate.identity.semantic_scope
                          or adjudication.authority_class != "experimental"
                          or adjudication.policy_profile != "flora-fictional-world-v1"):
            raise ValueError("fictional Claim admission lacks isolated experimental authority")
        if synthetic and any(relation.source_authority_class != "experimental"
                             for relation in candidate_relations):
            raise ValueError("fictional source relations changed experimental provenance")
        if ((proposal.valid_from is not None and normalize_timestamp(proposal.valid_from)
             > adjudication.envelope.transaction_time)
                or (proposal.valid_to is not None and normalize_timestamp(proposal.valid_to)
                    <= adjudication.envelope.transaction_time)):
            raise ValueError("this admission path supports currently effective Claims only")
        if verifier is None or verifier.authenticated_adjudication(
            adjudication, candidate, fresh, self.experiment_world_id) is not True:
            raise ValueError("semantic adjudication is not independently authenticated")
        if expected_previous is not None:
            expected_previous.validate()
            self.authority._assert_envelope(expected_previous)
        if candidate.proposed_action == "add":
            if (expected_previous is not None or conflict is not None
                    or adjudication.conflict_record_id is not None or proposal.contradicts):
                raise ValueError("new Claim has unresolved conflict or predecessor")
            if candidate.identity.canonical_value != candidate.value:
                raise ValueError("new Claim identity differs from its accepted value")
        else:
            if (expected_previous is None or conflict is None
                    or expected_previous.claim_id != candidate.identity.claim_id
                    or proposal.contradicts != (expected_previous.current_claim_version_id,)
                    or expected_previous.deletion_state != "active"
                    or expected_previous.conflict_state != "none"):
                raise ValueError("correction lacks an exact available predecessor")
            conflict.validate()
            self.authority._assert_envelope(conflict)
            if (conflict.conflict_type != "correction" or conflict.resolution_state != "resolved"
                    or conflict.resolution_adjudication_id != adjudication.adjudication_id
                    or conflict.conflict_id != adjudication.conflict_record_id
                    or conflict.claim_id != candidate.identity.claim_id
                    or set(conflict.member_record_ids) != {
                        candidate.candidate_id, expected_previous.current_claim_version_id}
                    or conflict.evidence_relation_ids != candidate.evidence_relation_ids):
                raise ValueError("correction conflict is not resolved by this adjudication")

        request_digest = canonical_sha256({
            "schema": "flora-governed-claim-admission-v1", "bundle_sha256": fresh.bundle.content_digest(),
            "proposal_id": bound.proposal_id, "candidate": candidate.metadata_record(),
            "candidate_relations": [relation.metadata_record() for relation in candidate_relations],
            "adjudication": adjudication.metadata_record(),
            "predecessor": None if expected_previous is None else expected_previous.projection_sha256,
            "conflict": None if conflict is None else conflict.metadata_record(),
            "experiment_world_id": self.experiment_world_id,
        })
        receipt_key = "admission-" + canonical_sha256([
            candidate.envelope.idempotency_namespace, candidate.envelope.idempotency_key])
        prior_receipt = self._row(_RECEIPTS, receipt_key)
        if prior_receipt is not None:
            record = self._read_record(prior_receipt, identifier=receipt_key)
            if record["request_digest"] != request_digest:
                raise ValueError("admission idempotency key was reused with different meaning")
            receipt = _receipt(record)
            version_record = self.authority.load_version(receipt.claim_version_id)
            if (version_record["version_sha256"] != receipt.version_sha256
                    or canonical_sha256({key: value for key, value in version_record.items()
                                         if key != "version_sha256"}) != receipt.version_sha256):
                raise ValueError("admission receipt lacks its exact immutable Claim version")
            return receipt

        authority = self.authority
        counter_row = self._row(_COUNTER, "admission-namespace-counter")
        counter = None if counter_row is None else self._read_record(
            counter_row, identifier="admission-namespace-counter")
        if counter is not None and (counter.get("schema") != "flora-claim-sequence-v1"
                                    or counter.get("controller_id") != _CONTROLLER):
            raise ValueError("Claim namespace has a different sequence controller")
        last = 0 if counter is None else counter["last_store_sequence"]
        if isinstance(last, bool) or not isinstance(last, int) or last < 0:
            raise ValueError("invalid Claim namespace sequence counter")
        sequence = last + 1
        stored = _rows(authority.connection.execute(
            f"SELECT MAX(CAST(store_sequence AS BIGINT)) AS maximum FROM {_VERSIONS} FOR VALID_TIME ALL "
            "WHERE scope_digest = %s::text", (authority.scope_digest,)))
        if len(stored) != 1 or "maximum" not in stored[0]:
            raise ValueError("Claim namespace sequence inventory is unavailable")
        maximum = stored[0]["maximum"]
        if maximum is not None and (isinstance(maximum, bool) or not isinstance(maximum, int)
                                    or maximum < 1 or maximum > last):
            raise ValueError("Claim namespace contains an untracked store sequence")
        claim_id = candidate.identity.claim_id
        current = authority._fetch_record(table=_HEAD, row_id=authority._row_id(claim_id))
        identity = self._row(_IDENTITIES, claim_id)
        previous_version = None
        if candidate.proposed_action == "add":
            if current is not None or identity is not None:
                raise ValueError("new Claim identity or current head already exists")
            version_sequence, projection_generation = 1, 1
        else:
            if (current is None or current["projection_sha256"] != expected_previous.projection_sha256
                    or json.loads(current["record_json"]) != expected_previous.metadata_record()
                    or identity is None
                    or json.loads(identity["record_json"]) != candidate.identity.metadata_record()
                    or expected_previous.source_position >= sequence):
                raise ValueError("stale or invalid correction authority head")
            previous_version = authority.load_version(expected_previous.current_claim_version_id)
            version_sequence = previous_version["version_sequence"] + 1
            projection_generation = expected_previous.projection_generation + 1
        slot_material = candidate.identity.semantic_record()
        slot_material.pop("canonical_value")
        slot_key = "property-" + canonical_sha256(slot_material)
        slot_row = self._row(_SLOTS, slot_key)
        slot = None if slot_row is None else self._read_record(slot_row, identifier=slot_key)
        if candidate.proposed_action == "add" and slot is not None:
            raise ValueError("current semantic property already belongs to another Claim")
        if candidate.proposed_action == "revise" and (slot is None or slot["claim_id"] != claim_id):
            raise ValueError("correction does not own its semantic property slot")

        replayed = log.replay()
        positions = {event.event_id: index for index, event in enumerate(replayed)}
        if not set(proposal.evidence_refs).issubset(positions):
            raise ValueError("admission evidence is absent from canonical Experience")
        event_position = max(positions[ref_id] for ref_id in proposal.evidence_refs)
        source_event = replayed[event_position]
        correction_of = () if expected_previous is None else (expected_previous.current_claim_version_id,)
        if previous_version is not None and (
                source_event.event_type != "correction"
                or previous_version["event_stream_position"] >= event_position
                or replayed[previous_version["event_stream_position"]].event_id
                not in source_event.parent_event_ids):
            raise ValueError("correction lacks its real prior Experience source parent")
        version_id = "flora-claim-version-" + request_digest[:48]
        projection_id = "flora-claim-projection-" + request_digest[:48]
        committed_relations = []
        template = adjudication.envelope
        for relation in candidate_relations:
            relation_id = "flora-claim-relation-" + canonical_sha256(
                [version_id, relation.relation_sha256])[:48]
            envelope = _new_envelope(
                template, record_id=relation_id, record_type="claim_evidence_relation",
                authority_role="claim_authority", sources=(relation.evidence_record_id, version_id),
                digest=request_digest, content_digest=relation.envelope.content_digest, generation=sequence)
            committed_relations.append(ClaimEvidenceRelation.create(
                envelope=envelope, relation_id=relation_id, evidence_record_id=relation.evidence_record_id,
                target_record_id=version_id, target_record_type="claim_version",
                relation_type=relation.relation_type, source_class=relation.source_class,
                source_authority_class=relation.source_authority_class,
                extractor_component_id=relation.extractor_component_id,
                extractor_version=relation.extractor_version, confidence=relation.confidence))
        relation_ids = tuple(sorted(relation.relation_id for relation in committed_relations))
        version_envelope = _new_envelope(
            template, record_id=version_id, record_type="claim_version", authority_role="claim_authority",
            sources=(claim_id, candidate.candidate_id, adjudication.adjudication_id,
                     fresh.bundle.bundle_id, fresh.recorded.event.event_id, *proposal.evidence_refs),
            digest=request_digest, content_digest=candidate.value.value_sha256, generation=sequence,
            supersedes=correction_of, valid_from=proposal.valid_from, valid_to=proposal.valid_to)
        version = ClaimVersion.create(
            envelope=version_envelope, claim_version_id=version_id, claim_id=claim_id,
            version_sequence=version_sequence, store_sequence=sequence, event_stream_position=event_position,
            value=candidate.value, qualifiers=candidate.qualifiers, authority_class=adjudication.authority_class,
            confidence=adjudication.confidence, adjudication_state=("accepted" if not correction_of else "revised"),
            evidence_relation_ids=relation_ids, conflict_set_id=None if conflict is None else conflict.conflict_id,
            correction_of=correction_of, request_digest=request_digest)
        source_binding = bind_claim_source(version=version, relations=committed_relations, replayed=replayed)
        projection_envelope = _new_envelope(
            template, record_id=projection_id, record_type="current_claim_projection",
            authority_role="registered_projection", sources=(claim_id, version_id),
            digest=request_digest, content_digest=candidate.value.value_sha256,
            generation=projection_generation, supersedes=(() if expected_previous is None else
                                                         (expected_previous.projection_id,)),
            valid_from=proposal.valid_from, valid_to=proposal.valid_to)
        projection = CurrentClaimProjection.create(
            envelope=projection_envelope, projection_id=projection_id, claim_id=claim_id,
            current_claim_version_id=version_id, authority_generation=sequence,
            projection_generation=projection_generation, adjudication_state=version.adjudication_state,
            validity_state="current", conflict_state="none", deletion_state="active", source_position=sequence)
        projection.assert_projects(candidate.identity, version)
        receipt_material = {
            "claim_id": claim_id, "claim_version_id": version_id, "version_sequence": version_sequence,
            "store_sequence": sequence, "event_stream_position": event_position,
            "projection_id": projection_id, "version_sha256": version.version_sha256,
            "projection_sha256": projection.projection_sha256,
            "adjudication_id": adjudication.adjudication_id, "request_digest": request_digest,
        }
        receipt = FormationAdmissionReceipt(**receipt_material,
            receipt_sha256=canonical_sha256(receipt_material))
        # Re-read all source permissions/bytes after potentially slow external
        # adjudication. The separate source-use barrier remains mandatory.
        if self.candidates.read_candidate(fresh.bundle.bundle_id, log=log, objects=objects,
                                          source_store=source_store) != fresh:
            raise ValueError("formation sources changed before authority transaction")
        connection = authority.connection
        if hasattr(connection, "info") and connection.info.transaction_status != 0:
            raise ValueError("admission requires its own top-level XTDB transaction")
        at = template.transaction_time
        with connection.transaction():
            # No nested put_* transactions/SAVEPOINTs: all writes roll back as
            # one native XTDB DML transaction if any assertion or insert fails.
            counter_key = authority._row_id("admission-namespace-counter")
            if counter is None:
                connection.execute(
                    f"ASSERT NOT EXISTS (SELECT 1 FROM {_COUNTER} FOR VALID_TIME ALL WHERE _id = %s::text)",
                    (counter_key,))
                connection.execute(
                    f"ASSERT NOT EXISTS (SELECT 1 FROM {_VERSIONS} FOR VALID_TIME ALL "
                    "WHERE scope_digest = %s::text)", (authority.scope_digest,))
            else:
                connection.execute(
                    f"ASSERT EXISTS (SELECT 1 FROM {_COUNTER} WHERE _id = %s::text AND record_sha256 = %s::text)",
                    (counter_key, counter["record_sha256"]))
                connection.execute(
                    f"ASSERT NOT EXISTS (SELECT 1 FROM {_VERSIONS} FOR VALID_TIME ALL "
                    "WHERE scope_digest = %s::text AND store_sequence >= %s::bigint)",
                    (authority.scope_digest, sequence))
            if expected_previous is None:
                connection.execute(f"ASSERT NOT EXISTS (SELECT 1 FROM {_HEAD} WHERE _id = %s::text)",
                                   (authority._row_id(claim_id),))
                connection.execute(f"ASSERT NOT EXISTS (SELECT 1 FROM {_SLOTS} WHERE _id = %s::text)",
                                   (authority._row_id(slot_key),))
            else:
                connection.execute(
                    f"ASSERT EXISTS (SELECT 1 FROM {_HEAD} WHERE _id = %s::text AND projection_sha256 = %s::text)",
                    (authority._row_id(claim_id), expected_previous.projection_sha256))
                connection.execute(
                    f"ASSERT EXISTS (SELECT 1 FROM {_SLOTS} WHERE _id = %s::text AND record_sha256 = %s::text)",
                    (authority._row_id(slot_key), slot["record_sha256"]))
            for table, identifier, record in (
                (_CANDIDATES, candidate.candidate_id, candidate.metadata_record()),
                (_ADJUDICATIONS, adjudication.adjudication_id, adjudication.metadata_record()),
                *(((_CONFLICTS, conflict.conflict_id, conflict.metadata_record()),) if conflict else ()),
            ):
                self._insert_record(table, identifier, {"schema": "flora-authority-artifact-v1", "artifact": record}, at)
            if identity is None:
                connection.execute(
                    f"ASSERT NOT EXISTS (SELECT 1 FROM {_IDENTITIES} FOR VALID_TIME ALL WHERE _id = %s::text)",
                    (authority._row_id(claim_id),))
                authority._insert(table=_IDENTITIES, columns={
                    "_id": authority._row_id(claim_id), "scope_digest": authority.scope_digest,
                    "claim_id": claim_id, "semantic_digest": candidate.identity.semantic_digest,
                    "identity_sha256": candidate.identity.identity_sha256,
                    "record_json": _record_json(candidate.identity.metadata_record())},
                    valid_from=_timestamp(candidate.identity.envelope.valid_from),
                    valid_to=None)
            for relation in (*candidate_relations, *committed_relations):
                connection.execute(
                    f"ASSERT NOT EXISTS (SELECT 1 FROM {_EVIDENCE} FOR VALID_TIME ALL WHERE _id = %s::text)",
                    (authority._row_id(relation.relation_id),))
                authority._insert(table=_EVIDENCE, columns={
                    "_id": authority._row_id(relation.relation_id), "scope_digest": authority.scope_digest,
                    "relation_id": relation.relation_id, "evidence_record_id": relation.evidence_record_id,
                    "target_record_id": relation.target_record_id, "target_record_type": relation.target_record_type,
                    "relation_type": relation.relation_type, "relation_sha256": relation.relation_sha256,
                    "record_json": _record_json(relation.metadata_record())},
                    valid_from=_timestamp(relation.envelope.valid_from), valid_to=None)
            connection.execute(
                f"ASSERT NOT EXISTS (SELECT 1 FROM {_VERSIONS} FOR VALID_TIME ALL WHERE _id = %s::text)",
                (authority._row_id(version_id),))
            authority._insert(table=_VERSIONS, columns={
                "_id": authority._row_id(version_id), "scope_digest": authority.scope_digest,
                "claim_id": claim_id, "claim_version_id": version_id, "version_sequence": version_sequence,
                "store_sequence": sequence, "request_digest": request_digest,
                "experience_event_id": source_binding.event_id, "event_stream_position": event_position,
                "version_sha256": version.version_sha256, "record_json": _record_json(version.metadata_record())},
                valid_from=_timestamp(version.envelope.valid_from),
                valid_to=None if version.envelope.valid_to is None else _timestamp(version.envelope.valid_to))
            columns = {
                "_id": authority._row_id(claim_id), "scope_digest": authority.scope_digest,
                "claim_id": claim_id, "current_claim_version_id": version_id,
                "projection_generation": projection_generation, "source_position": sequence,
                "projection_sha256": projection.projection_sha256,
                "record_json": _record_json(projection.metadata_record()),
            }
            authority._insert(table=_CURRENT, columns=columns,
                              valid_from=_timestamp(projection.envelope.valid_from),
                              valid_to=None if projection.envelope.valid_to is None else _timestamp(projection.envelope.valid_to))
            authority._insert(table=_HEAD, columns=columns,
                              valid_from=_timestamp(projection.envelope.valid_from), valid_to=None)
            self._insert_record(_COUNTER, "admission-namespace-counter",
                                {"schema": "flora-claim-sequence-v1", "controller_id": _CONTROLLER,
                                 "last_store_sequence": sequence},
                                at, immutable=False)
            if slot is None:
                self._insert_record(_SLOTS, slot_key, {"schema": "flora-claim-property-v1", "claim_id": claim_id}, at)
            self._insert_record(_RECEIPTS, receipt_key, {
                "schema": "flora-claim-admission-receipt-v1", "request_digest": request_digest,
                "receipt": receipt.__dict__, "proposal": proposal.record(),
                "bundle_sha256": fresh.bundle.content_digest(),
                "candidate_event_sha256": fresh.recorded.event.event_sha256,
            }, at)
        return receipt
