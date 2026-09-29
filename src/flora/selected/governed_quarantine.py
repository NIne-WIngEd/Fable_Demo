"""Controller-governed immediate Claim use quarantine, not completed erasure.

Exact enrolled-owner control authority is independent of model semantics. The
namespace sequence, pending projection/head and immutable receipt commit in one
XTDB transaction. Kurrent request positions stay separate. Existing current-use
filters reject stale graph/vector records even while Temporal cleanup is pending.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Mapping

from cognitive_kernel.canonical import canonical_sha256
from cognitive_kernel.claim_contracts import CurrentClaimProjection
from cognitive_kernel.memory_contracts import MemoryUnitEnvelope
from .claim_controller import XTDBClaimSequenceController
from .claims import XTDBClaimAuthority, _CURRENT, _HEAD, _VERSIONS, _record_json, _timestamp
from .derived_reconciliation import cleanup_request
from .experience import KurrentExperienceLog
from .object_store import EncryptedObjectPlane, RawObjectReference
from .revocation import RevocationVerifier, _projection_from_prior_and_record, revocation_request

_RECEIPTS = "flora_governed_claim_quarantine_receipts"


@dataclass(frozen=True)
class GovernedQuarantineReceipt:
    projection: CurrentClaimProjection
    request_event_id: str
    request_event_sha256: str
    event_stream_position: int
    store_sequence: int
    prior_projection_sha256: str
    receipt_sha256: str

    def material_record(self):
        return {"projection": self.projection.metadata_record(),
            **{k: v for k, v in vars(self).items() if k not in {"projection", "receipt_sha256"}}}


class XTDBGovernedClaimQuarantine:
    def __init__(self, authority: XTDBClaimAuthority):
        self.authority = authority
        self.controller = XTDBClaimSequenceController(authority)

    def _request(self, *, prior, request_event_id, log, objects, references, verifier):
        prior.validate()
        authority = self.authority
        if not (prior.envelope.scope == authority.scope == log.scope == objects.scope
                and prior.envelope.authority_namespace_id == authority.authority_namespace_id):
            raise ValueError("governed Claim quarantine crosses scope or namespace")
        entries = log.replay_committed()
        matched = next((entry for entry in entries if entry.event.event_id == request_event_id), None)
        if matched is None:
            raise ValueError("governed Claim quarantine lacks a committed request")
        event, position = matched.event, matched.stream_position
        event.validate()
        material = revocation_request(prior)
        if (event.scope != authority.scope or event.event_type != "deletion_request" or event.payload_reference is None
                or event.content_digest != hashlib.sha256(material).hexdigest()
                or matched.recorded_at is None or not isinstance(matched.recorded_at, datetime)
                or matched.recorded_at.tzinfo is None or matched.recorded_at.utcoffset() is None
                or _timestamp(event.occurred_at) > matched.recorded_at):
            raise ValueError("governed Claim quarantine request scope/type/digest/time differs")
        if verifier.authenticated_request(event, json.loads(material)) is not True:
            raise PermissionError("governed Claim quarantine is not independently authorized")
        row = authority._fetch_record(table=_VERSIONS,
            row_id=authority._row_id(prior.current_claim_version_id), all_valid=True)
        version = authority.load_version(prior.current_claim_version_id)
        source = next((entry for entry in entries if entry.event.event_id == row["experience_event_id"]), None)
        if (row["version_sha256"] != version["version_sha256"] or row["claim_id"] != prior.claim_id
                or source is None or source.event.scope != authority.scope
                or source.stream_position != row["event_stream_position"]
                or source.stream_position != version["event_stream_position"]
                or source.stream_position >= position or source.event.event_id not in event.parent_event_ids
                or source.event.event_id not in version["envelope"]["source_records"]):
            raise ValueError("governed Claim quarantine lacks its actual prior source parent")
        raw = references.get(event.payload_reference)
        if (raw is None or raw.scope != authority.scope or raw.object_id != event.payload_reference
                or raw.plaintext_sha256 != event.content_digest or objects.get(raw) != material):
            raise ValueError("governed Claim quarantine differs from exact encrypted request")
        # Authorization may depend on an independent mutable product policy.
        if verifier.authenticated_request(event, json.loads(material)) is not True:
            raise PermissionError("Claim quarantine authorization changed during request read")
        return event, position

    def _stored(self, prior, request_event_id):
        authority = self.authority
        row = authority._fetch_record(table=_RECEIPTS, row_id=authority._row_id(request_event_id), all_valid=True)
        if row is None:
            return None
        record = json.loads(str(row["record_json"]))
        if (row["_id"] != authority._row_id(request_event_id) or row["scope_digest"] != authority.scope_digest
                or record["schema"] != "flora-governed-claim-quarantine-receipt-v1"
                or record["scope"] != authority.scope.metadata_record()
                or record["authority_namespace_id"] != authority.authority_namespace_id
                or record["record_sha256"] != row["record_sha256"]
                or canonical_sha256({k: v for k, v in record.items() if k != "record_sha256"}) != row["record_sha256"]):
            raise ValueError("governed quarantine receipt changed or crosses authority")
        receipt = dict(record["receipt"])
        projection = _projection_from_prior_and_record(prior, receipt.pop("projection"))
        result = GovernedQuarantineReceipt(projection=projection, **receipt)
        if (canonical_sha256(result.material_record()) != result.receipt_sha256
                or result.request_event_id != request_event_id
                or result.prior_projection_sha256 != prior.projection_sha256
                or result.projection.source_position != result.store_sequence):
            raise ValueError("governed quarantine receipt lacks exact request/predecessor")
        return result

    def apply(self, *, prior: CurrentClaimProjection, request_event_id: str,
              log: KurrentExperienceLog, objects: EncryptedObjectPlane,
              references: Mapping[str, RawObjectReference], verifier: RevocationVerifier) -> GovernedQuarantineReceipt:
        event, event_position = self._request(prior=prior, request_event_id=request_event_id,
            log=log, objects=objects, references=references, verifier=verifier)
        authority = self.authority
        current = authority.load_current(prior.claim_id)
        existing = self._stored(prior, request_event_id)
        if existing is not None:
            allocation = self.controller.prepare(require_existing=True)
            if (existing.request_event_sha256 != event.event_sha256 or existing.event_stream_position != event_position
                    or current != existing.projection.metadata_record()
                    or existing.store_sequence >= allocation.sequence):
                raise ValueError("governed quarantine retry has a changed request or current head")
            return existing
        if (current != prior.metadata_record() or prior.deletion_state != "active"
                or prior.conflict_state != "none" or prior.adjudication_state not in {"accepted", "revised"}
                or _timestamp(event.occurred_at) <= _timestamp(prior.envelope.valid_from)):
            raise ValueError("governed quarantine has a stale/unavailable/time-invalid predecessor")
        allocation = self.controller.prepare(require_existing=True)
        if allocation.sequence <= prior.source_position:
            raise ValueError("governed quarantine does not advance authority order")
        projection_id = "flora-quarantined-claim-" + canonical_sha256(
            [prior.projection_sha256, event.event_sha256])[:48]
        old = prior.envelope
        envelope = MemoryUnitEnvelope.create(scope=authority.scope, record_id=projection_id,
            record_type="current_claim_projection", authority_namespace_id=authority.authority_namespace_id,
            host_or_cluster_id=old.host_or_cluster_id, authority_role="registered_projection",
            deployment_profile=old.deployment_profile, created_at=event.occurred_at,
            valid_from=event.occurred_at, valid_to=None, transaction_time=event.occurred_at,
            logical_clock=old.logical_clock + 1, causal_parents=(prior.projection_id, event.event_id),
            source_records=tuple(sorted({prior.claim_id, prior.current_claim_version_id, event.event_id})),
            generation=old.generation + 1, state="committed", data_classification=old.data_classification,
            retention_class=old.retention_class, deletion_state="pending", provenance_digest=event.content_digest,
            content_digest=old.content_digest, writer="governed_claim_quarantine",
            workflow_or_request_id=event.event_id, idempotency_namespace="governed_claim_quarantine",
            idempotency_key=event.event_id, supersedes=(prior.projection_id,))
        projection = CurrentClaimProjection.create(envelope=envelope, projection_id=projection_id,
            claim_id=prior.claim_id, current_claim_version_id=prior.current_claim_version_id,
            authority_generation=prior.authority_generation + 1, projection_generation=prior.projection_generation + 1,
            adjudication_state=prior.adjudication_state, validity_state=prior.validity_state,
            conflict_state=prior.conflict_state, deletion_state="pending", source_position=allocation.sequence)
        values = dict(projection=projection, request_event_id=event.event_id, request_event_sha256=event.event_sha256,
            event_stream_position=event_position, store_sequence=allocation.sequence,
            prior_projection_sha256=prior.projection_sha256)
        draft = GovernedQuarantineReceipt(**values, receipt_sha256="0" * 64)
        receipt = GovernedQuarantineReceipt(**values, receipt_sha256=canonical_sha256(draft.material_record()))
        record = {"schema": "flora-governed-claim-quarantine-receipt-v1", "scope": authority.scope.metadata_record(),
            "authority_namespace_id": authority.authority_namespace_id,
            "receipt": {**receipt.material_record(), "receipt_sha256": receipt.receipt_sha256}}
        record["record_sha256"] = canonical_sha256(record)
        columns = {"_id": authority._row_id(prior.claim_id), "scope_digest": authority.scope_digest,
            "claim_id": prior.claim_id, "current_claim_version_id": prior.current_claim_version_id,
            "projection_generation": projection.projection_generation, "source_position": allocation.sequence,
            "projection_sha256": projection.projection_sha256, "record_json": _record_json(projection.metadata_record())}
        # No nested low-level Claim writer/SAVEPOINT and no derived engine call
        # inside this one exact authority transaction.
        if hasattr(authority.connection, "info") and authority.connection.info.transaction_status != 0:
            raise ValueError("governed quarantine requires its own top-level XTDB transaction")
        with authority.connection.transaction():
            self.controller.assert_allocation(allocation)
            authority.connection.execute(
                f"ASSERT EXISTS (SELECT 1 FROM {_HEAD} WHERE _id = %s::text AND projection_sha256 = %s::text)",
                (authority._row_id(prior.claim_id), prior.projection_sha256))
            authority.connection.execute(
                f"ASSERT NOT EXISTS (SELECT 1 FROM {_RECEIPTS} FOR VALID_TIME ALL WHERE _id = %s::text)",
                (authority._row_id(event.event_id),))
            # Native valid-time replacement preserves prior historical interval
            # while selecting this pending projection from the request time.
            authority._insert(table=_CURRENT, columns=columns, valid_from=_timestamp(event.occurred_at), valid_to=None)
            authority._insert(table=_HEAD, columns=columns, valid_from=_timestamp(event.occurred_at), valid_to=None)
            self.controller.write_allocation(allocation, at=event.occurred_at)
            authority._insert(table=_RECEIPTS, columns={"_id": authority._row_id(event.event_id),
                "scope_digest": authority.scope_digest, "record_sha256": record["record_sha256"],
                "record_json": _record_json(record)}, valid_from=_timestamp(event.occurred_at), valid_to=None)
        return receipt

    def cleanup(self, receipt: GovernedQuarantineReceipt) -> dict[str, str]:
        """Exact-head request for the existing retryable Temporal cleanup."""
        if self.authority.load_current(receipt.projection.claim_id) != receipt.projection.metadata_record():
            raise ValueError("quarantine cleanup names a changed current head")
        return cleanup_request(authority=self.authority, claim_id=receipt.projection.claim_id)
