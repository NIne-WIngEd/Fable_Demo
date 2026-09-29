"""Current local judgment permissions; no planner, model or semantic judge."""

from __future__ import annotations

import json

from .claims import XTDBClaimAuthority
from .experience import KurrentExperienceLog
from .formation_policy import XTDBFormationPermissionPolicy
from .formation_registry import XTDBFormationSourceRegistry
from .governed_development import XTDBGovernedPersonalDevelopment, _version_from_record
from .personal_state import _ACTIVE, _VERSIONS
from .source_native import read_current_source_manifest


class RegisteredJudgmentContextPolicy:
    """Check current metadata before context opens original or derived bytes.

    Source grants for formation do not grant judgment or provider disclosure.
    Approval events also need explicit registered judgment-use permission;
    their independent owner signature remains required by governed state reads.
    Passing this policy does not establish semantic relevance or sufficiency.
    """

    purpose = "personal_judgment"

    def __init__(self, *, claims: XTDBClaimAuthority,
                 state: XTDBGovernedPersonalDevelopment, log: KurrentExperienceLog,
                 registry: XTDBFormationSourceRegistry,
                 permissions: XTDBFormationPermissionPolicy):
        if not isinstance(state, XTDBGovernedPersonalDevelopment):
            raise TypeError("judgment requires governed personal development")
        if (not claims.scope == state.scope == log.scope == registry.scope == permissions.scope
                or not claims.authority_namespace_id == state.authority_namespace_id
                == registry.authority_namespace_id == permissions.authority_namespace_id
                or permissions.registry is not registry
                or state.registry is not registry or state.policy is not permissions):
            raise ValueError("judgment policy crosses host or authority")
        self.claims, self.state, self.log = claims, state, log
        self.registry, self.permissions = registry, permissions

    def allow_event(self, event_id: str, purpose: str) -> bool:
        if purpose != self.purpose:
            return False
        try:
            source = self.registry.lookup(event_id)
            if source is None or self.permissions.permits(source, purpose) is not True:
                return False
            events = {event.event_id: event for event in self.log.replay()}
            pending, seen = [source], set()
            while pending:
                current = pending.pop()
                evidence = current.evidence
                if evidence.ref_id in seen:
                    continue
                event = events.get(evidence.ref_id)
                if (event is None or event.scope != self.claims.scope
                        or event.payload_reference != current.object_ref
                        or event.content_digest != evidence.content_digest
                        or event.parent_event_ids != evidence.parent_refs
                        or evidence.authority_namespace_id != self.claims.authority_namespace_id
                        or self.permissions.permits(current, purpose) is not True):
                    return False
                seen.add(evidence.ref_id)
                for parent_id in evidence.parent_refs:
                    parent = self.registry.lookup(parent_id)
                    if parent is None:
                        return False
                    pending.append(parent)
            return (self.registry.lookup(event_id) == source
                    and self.permissions.permits(source, purpose) is True)
        except (KeyError, ValueError, TypeError):
            return False

    def allow_claim(self, claim_id: str, purpose: str) -> bool:
        if purpose != self.purpose:
            return False
        try:
            manifest = read_current_source_manifest(
                claim_id=claim_id, authority=self.claims, log=self.log)
            return (all(self.allow_event(source.event_id, purpose) for source in manifest.sources)
                    and read_current_source_manifest(
                        claim_id=claim_id, authority=self.claims, log=self.log) == manifest)
        except (KeyError, ValueError, TypeError):
            return False

    def allow_state(self, subject_type: str, subject_id: str,
                    projection_id: str, purpose: str) -> bool:
        if purpose != self.purpose:
            return False
        try:
            key = self.state._head_id(subject_type, subject_id, projection_id)
            head = self.state._fetch(_ACTIVE, key)
            if head is None:
                return False
            row = self.state._fetch(_VERSIONS, self.state._version_id(head["version_id"]), all_valid=True)
            if row is None:
                return False
            version = _version_from_record(json.loads(str(row["record_json"])))
            if (version.envelope.scope != self.claims.scope
                    or version.envelope.authority_namespace_id != self.claims.authority_namespace_id
                    or (version.subject_type, version.subject_id, version.projection_id)
                    != (subject_type, subject_id, projection_id)
                    or version.version_id != head["version_id"]
                    or version.projection_sha256 != row["projection_sha256"]
                    or version.projection_sha256 != head["projection_sha256"]):
                return False
            history = self.state._history(projection_id, version.version_id)
            if (history["approval_event_id"] != head["approval_event_id"]
                    or history["approval_event_sha256"] != head["approval_event_sha256"]
                    or history["projection_sha256"] != version.projection_sha256):
                return False
            episode_lineages = {}
            for episode_id in version.source_episode_ids:
                if self.state.episodes is None:
                    return False
                lineage = self.state.episodes.current_lineage(episode_id, claims=self.claims, log=self.log)
                if not all(self.allow_event(event_id, purpose) for event_id in lineage[3]):
                    return False
                episode_lineages[episode_id] = lineage
            claims = set(version.source_claim_version_ids)
            for version_id in claims:
                claim = self.claims.load_version(version_id)
                current = self.claims.load_current(claim["claim_id"])
                if (current["current_claim_version_id"] != version_id
                        or not self.allow_claim(claim["claim_id"], purpose)):
                    return False
            originals = set(version.source_evidence_ids) | (set(version.envelope.source_records)
                        - claims - set(version.source_episode_ids))
            return (all(self.allow_event(event_id, purpose) for event_id in originals)
                    and self.allow_event(head["approval_event_id"], purpose)
                    and all(self.state.episodes.current_lineage(episode_id, claims=self.claims, log=self.log) == lineage
                            for episode_id, lineage in episode_lineages.items())
                    and self.state._fetch(_ACTIVE, key) == head)
        except (KeyError, ValueError, TypeError):
            return False
