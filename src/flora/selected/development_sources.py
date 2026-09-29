"""Shared current source authority for derived episode and personal-state reads.

No semantics, model or permission grant is produced here. The selected registry
and current policy precede all original plaintext; consumers separately govern
any explicitly omitted derived-record IDs.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import hashlib
from typing import Mapping
from cognitive_kernel.contracts import ProductHostScope
from .claims import XTDBClaimAuthority
from .experience import KurrentExperienceLog
from .formation_policy import XTDBFormationPermissionPolicy
from .formation_registry import RegisteredEncryptedFormationCustody, XTDBFormationSourceRegistry
from .object_store import EncryptedObjectPlane, RawObjectReference
from .personal_artifact_custody import _SourceAuthorizedObjectReads
from .source_native import _require_available, read_current_sources

_PURPOSE = "personal_judgment"

@dataclass(frozen=True)
class RegisteredDevelopmentSourceGuard:
    scope: ProductHostScope
    authority_namespace_id: str
    registry: XTDBFormationSourceRegistry
    policy: XTDBFormationPermissionPolicy

    def check(self, *, source_claim_version_ids: tuple[str, ...],
                       source_evidence_ids: tuple[str, ...], source_records: tuple[str, ...],
                       derived_record_ids: tuple[str, ...] = (),
                       source_observed_by: str | None = None,
                       claims: XTDBClaimAuthority, log: KurrentExperienceLog,
                       objects: EncryptedObjectPlane,
                       references: Mapping[str, RawObjectReference]) -> None:
        if (not self.scope == claims.scope == log.scope == objects.scope
                or claims.authority_namespace_id != self.authority_namespace_id):
            raise ValueError("personal development sources cross host or authority")
        declared = set(source_claim_version_ids + source_evidence_ids + derived_record_ids)
        if not declared.issubset(source_records):
            raise ValueError("personal development omits source lineage")
        # Every additional source record must also be an authorized original.
        # Candidate/episode identifiers cannot silently become source authority.
        original_ids = set(source_evidence_ids) | (set(source_records) - set(source_claim_version_ids) - set(derived_record_ids))
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
                    or source.evidence.ref_id != event_id
                    or source.evidence.scope != self.scope
                    or source.evidence.authority_namespace_id != self.authority_namespace_id
                    or source.object_ref != event.payload_reference
                    or source.evidence.content_digest != event.content_digest
                    or source.evidence.parent_refs != event.parent_event_ids):
                raise ValueError("personal development lacks registered original evidence")
            if (source_observed_by is not None
                    and datetime.fromisoformat(event.occurred_at.replace("Z", "+00:00"))
                    > datetime.fromisoformat(source_observed_by.replace("Z", "+00:00"))):
                raise ValueError("personal development cites evidence observed after formation")
            if self.policy.permits(source, _PURPOSE) is not True:
                raise ValueError("personal judgment source use is not currently permitted")
            closure[event_id] = source
            pending.extend(source.evidence.parent_refs)
        # Recover original references from durable XTDB custody rather than a
        # caller-authored map. Permission precedes all original plaintext I/O.
        def permitted_now(event_id: str) -> bool:
            captured = closure.get(event_id)
            return (captured is not None and self.registry.lookup(event_id) == captured
                    and self.policy.permits(captured, _PURPOSE) is True)

        authorized_references = {}
        for event_id, source in closure.items():
            if permitted_now(event_id) is not True:
                raise ValueError("personal judgment source authority changed before raw read")
            def fresh_original():
                if permitted_now(event_id) is not True:
                    raise ValueError("personal judgment source authority changed during read")
                return True
            custody = RegisteredEncryptedFormationCustody(registry=self.registry,
                objects=_SourceAuthorizedObjectReads(objects, fresh_original))
            raw = self.registry.raw_reference(source.object_ref)
            if (raw is None or raw.scope != self.scope or raw.object_id != source.object_ref
                    or hashlib.sha256(custody.read(self.scope, source.object_ref)).hexdigest()
                    != source.evidence.content_digest):
                raise ValueError("personal development original content differs from registered evidence")
            if permitted_now(event_id) is not True:
                raise ValueError("personal judgment source authority changed during read")
            authorized_references[source.object_ref] = raw
        for version_id, version in claim_versions.items():
            packet = read_current_sources(
                claim_id=version["claim_id"], authority=claims, log=log,
                objects=_SourceAuthorizedObjectReads(objects,
                    lambda: all(permitted_now(event_id) for event_id in closure)),
                references=authorized_references, source_authorizer=permitted_now)
            if packet.claim_version_id != version_id:
                raise ValueError("personal development cites a superseded claim")
        # No successful materialization is allowed to outrun a current denial.
        for event_id, source in closure.items():
            if (self.registry.lookup(event_id) != source
                    or self.policy.permits(source, _PURPOSE) is not True):
                raise ValueError("personal judgment source authority changed during read")

        for version_id, version in claim_versions.items():
            present = claims.load_current(version["claim_id"])
            _require_available(present, version["claim_id"])
            if present["validity_state"] != "current" or present["current_claim_version_id"] != version_id:
                raise ValueError("personal development Claim changed during source resolution")
