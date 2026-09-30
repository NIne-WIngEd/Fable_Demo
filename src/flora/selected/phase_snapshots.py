"""Immutable selected phase custody; a snapshot never freezes source permission.

Capture runs the actual selected context and independent producer phase-proof
route. The private manifest names historical authority records, not a replacement
Claim store, learned model, source interpretation, or qualification producer.
"""
from __future__ import annotations

import base64
from copy import copy, deepcopy
from dataclasses import dataclass, field
import hashlib
import json
from typing import Callable

from cognitive_kernel.canonical import canonical_json_bytes, canonical_sha256, normalize_timestamp, require_identifier, require_sha256
from cognitive_kernel.contracts import ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent

from . import artifact_registry as artifacts_module
from . import governed_episodes as episodes_module
from .claims import _dml_placeholder, _record_json, _rows
from .context import ContextPlan, StateRoute
from .formation_context import register_experience_source
from .formation_registry import RegisteredEncryptedFormationCustody
from .judgment_lineage import NativeJudgmentLineageVerifier
from .personal_artifact_custody import _SourceAuthorizedObjectReads
from .object_store import EncryptedObjectPlane
from .personal_state import _ACTIVE, _VERSIONS
from .source_native import _require_available

_TABLE = "flora_selected_phase_snapshots"
_INTENTS = "flora_selected_phase_capture_intents"
_EVENT_TYPE = "phase_snapshot_artifact"


def _plain(value):
    return json.loads(canonical_json_bytes(value))


def plan_record(plan: ContextPlan):
    plan.validate()
    # Re-running a mutable accelerator is not a historical selector. A learned
    # or derived selector must first nominate and freeze its exact Claim IDs.
    if plan.query_vector is not None or plan.graph_source_event_ids:
        raise ValueError("phase plans require frozen exact Claim/state routes")
    return {**vars(plan), "state_routes": [vars(route) for route in plan.state_routes]}


def plan_from_record(record):
    values = dict(record)
    values["exact_claim_ids"] = tuple(values["exact_claim_ids"])
    values["state_routes"] = tuple(StateRoute(**route) for route in values["state_routes"])
    values["graph_source_event_ids"] = tuple(values["graph_source_event_ids"])
    plan = ContextPlan(**values)
    if _plain(plan_record(plan)) != record:
        raise ValueError("phase context plan is not canonical")
    return plan


class PhaseAuthorizedObjectReads(_SourceAuthorizedObjectReads):
    """Keep the phase barrier around put/recovery's own nested decrypts too."""
    def __copy__(self):
        # Runtime guards wrap a shallow copy's ciphertext backend. Preserve
        # that wrapper inside delegated get() without mutating the live plane.
        return type(self)(copy(self.objects), self.source_authorizer)

    @property
    def backend(self):
        return self.objects.backend

    @backend.setter
    def backend(self, value):
        self.objects.backend = value

    def __getattr__(self, name):
        # copy.copy probes a new object before its state is installed.
        objects = object.__getattribute__(self, "objects")
        return getattr(objects, name)

    def put(self, content):
        if self.source_authorizer() is not True:
            raise PermissionError("phase source is withdrawn before private put")
        return EncryptedObjectPlane.put(self, content)

    def recover_reference(self, **kwargs):
        if self.source_authorizer() is not True:
            raise PermissionError("phase source is withdrawn before private recovery")
        return EncryptedObjectPlane.recover_reference(self, **kwargs)


@dataclass(frozen=True)
class FrozenPhaseUpdatePolicy:
    mode: str = "full_update"
    before_snapshot_id: str | None = None
    before_snapshot_sha256: str | None = None
    excluded_update_event_ids: tuple[str, ...] = ()

    def record(self):
        if self.mode not in {"full_update", "withhold_personal_judgment_update"}:
            raise ValueError("unknown native update policy")
        if self.mode == "full_update":
            if self.before_snapshot_id is not None or self.before_snapshot_sha256 is not None or self.excluded_update_event_ids:
                raise ValueError("full update cannot claim a withheld update")
        else:
            require_identifier(self.before_snapshot_id, "before_snapshot_id")
            require_sha256(self.before_snapshot_sha256, "before_snapshot_sha256")
            if not self.excluded_update_event_ids or tuple(sorted(set(self.excluded_update_event_ids))) != self.excluded_update_event_ids:
                raise ValueError("withheld update needs exact unique actual update event IDs")
            for event_id in self.excluded_update_event_ids:
                require_identifier(event_id, "update_event_id")
        return {"schema": "flora-frozen-phase-update-policy-v1", **vars(self),
            "excluded_update_event_ids": list(self.excluded_update_event_ids)}


def verify_update_policy(*, runtime, snapshot_record, receipt, authority_guard=None):
    policy = snapshot_record["update_policy"]
    typed = FrozenPhaseUpdatePolicy(**{key: (tuple(value) if key == "excluded_update_event_ids" else value)
        for key, value in policy.items() if key != "schema"})
    if typed.record() != policy:
        raise ValueError("phase update policy is not canonical")
    if snapshot_record["phase"] == "before" or snapshot_record["arm"] == "flora_full":
        if typed.mode != "full_update" or receipt is not None:
            raise ValueError("before/full arm cannot substitute a withheld future update")
        return None
    if typed.mode != "withhold_personal_judgment_update" or not isinstance(receipt, bytes) or not receipt:
        raise PermissionError("ablation requires an actual independent producer update-exclusion proof")
    actual_events = {event.event_id for event in runtime.log.replay()}
    if not set(typed.excluded_update_event_ids).issubset(actual_events):
        raise ValueError("ablation exclusions cite absent canonical update events")
    artifact = runtime._resolve("personality_judgment", authority_guard=authority_guard)[1]
    request = {"schema": "flora-phase-update-exclusion-request-v1", "scope": runtime.scope.metadata_record(),
        "authority_namespace_id": runtime.authority_namespace_id,
        **{name: snapshot_record[name] for name in ("run_id", "run_plan_sha256", "case_id", "phase", "arm", "history_sha256", "context_lineage_sha256", "update_policy")},
        "artifact_manifest_sha256": artifact.manifest_sha256}
    verifier = runtime.bindings["personality_judgment"].qualification_verifier
    method = getattr(verifier, "verify_phase_update_policy", None)
    if not callable(method):
        raise PermissionError("actual personality qualifier has no update-exclusion adapter")
    if authority_guard is not None:
        authority_guard()
    verified = method(request=request, receipt=receipt)
    if authority_guard is not None:
        authority_guard()
    expected = {"schema": "flora-qualified-phase-update-exclusion-v1", "request_sha256": canonical_sha256(request),
        "receipt_sha256": hashlib.sha256(receipt).hexdigest(), "artifact_manifest_sha256": artifact.manifest_sha256,
        "qualifier_id": artifact.qualifier_id, "qualification_id": artifact.qualification_id, "allowed": True}
    if verified != expected:
        raise PermissionError("independent producer denied exact phase update exclusion")
    return verified


@dataclass(frozen=True)
class SelectedPhaseSnapshot:
    """A private captured manifest; construction alone grants no authority."""
    record: dict = field(repr=False)

    @property
    def snapshot_id(self):
        return self.record["snapshot_id"]

    @property
    def snapshot_sha256(self):
        return canonical_sha256(self.record)

    @property
    def plan(self):
        return plan_from_record(self.record["context_plan"])

    def validate(self):
        r = self.record
        if r.get("schema") != "flora-selected-phase-snapshot-v1" or r["phase"] not in {"before", "after"}:
            raise ValueError("phase snapshot schema/phase differs")
        for name in ("run_id", "snapshot_id", "case_id", "authority_namespace_id"):
            if require_identifier(r[name], name) != r[name]:
                raise ValueError("phase snapshot identifier differs")
        if r["arm"] not in {"flora_full", "same_evidence_ablation"}:
            raise ValueError("phase snapshot requires an exact native arm")
        for name in ("run_plan_sha256", "history_sha256", "context_lineage_sha256"):
            require_sha256(r[name], name)
        if (isinstance(r["capture_stream_position"], bool) or not isinstance(r["capture_stream_position"], int)
                or r["capture_stream_position"] < 0 or normalize_timestamp(r["captured_at"]) != r["captured_at"]):
            raise ValueError("phase capture lacks exact canonical time/position")
        if (r["original_event_ids"] != sorted(set(r["original_event_ids"]))
                or r["source_event_ids"] != sorted(set(r["source_event_ids"]))
                or not set(r["original_event_ids"]).issubset(r["source_event_ids"])
                or canonical_sha256(r["context_lineage"]) != r["context_lineage_sha256"]):
            raise ValueError("phase capture has inconsistent source/lineage bindings")
        plan_from_record(r["context_plan"])
        if (len(r["producer_receipts"]) != 2 or len(r["context_lineage"]["phase_snapshots"]) != 2
                or {item["request_sha256"] for item in r["producer_receipts"]}
                != {item["request_sha256"] for item in r["context_lineage"]["phase_snapshots"]}):
            raise ValueError("phase capture lacks exact independent producer exclusion receipts")
        receipts = {item["request_sha256"]: base64.b64decode(item["receipt_base64"], validate=True) for item in r["producer_receipts"]}
        if any(hashlib.sha256(receipts[item["request_sha256"]]).hexdigest() != item["receipt_sha256"]
                or item["allowed_for_phase"] is not True for item in r["context_lineage"]["phase_snapshots"]):
            raise ValueError("phase producer receipt bytes differ from verified exclusion")
        roles = {item["role"] for item in r["artifacts"]}
        if roles != {"memory_formation", "personality_judgment"} or len(r["artifacts"]) != 2:
            raise ValueError("phase capture lacks both actual qualified producer roles")


class XTDBPhaseSnapshotCustody:
    """Actual XTDB/Kurrent/encrypted-object placement for frozen selected views.

    Snapshot use requires explicit current personal_judgment permission on the
    artifact and ancestor closure, and independent live phase-history authority.
    Capturing this manifest creates no grants and never declares model quality.
    """
    def __init__(self, *, runtime, run_id: str, run_plan_sha256: str, clock: Callable[[], str], artifact_permissions=None):
        require_identifier(run_id, "run_id")
        require_sha256(run_plan_sha256, "run_plan_sha256")
        if not callable(clock):
            raise TypeError("phase custody requires an explicit clock")
        self.runtime, self.run_id, self.run_plan_sha256, self.clock = runtime, run_id, run_plan_sha256, clock
        self.scope, self.authority_namespace_id = runtime.scope, runtime.authority_namespace_id
        self.connection = runtime.claims.connection
        self.scope_digest = canonical_sha256([self.scope.metadata_record(), self.authority_namespace_id])
        # Archive privacy is separate from model-context original membership.
        # Bind before a native session installs its original-only method guard,
        # or supply an independently bound actual owner policy explicitly.
        permissions = copy(runtime.source_policy if artifact_permissions is None else artifact_permissions)
        if (permissions.scope != self.scope or permissions.authority_namespace_id != self.authority_namespace_id
                or permissions.registry is not runtime.sources
                or getattr(permissions, "connection", self.connection) is not self.connection):
            raise ValueError("phase artifact permission authority crosses actual selected scope/registry/connection")
        from .judgment_context import RegisteredJudgmentContextPolicy
        state = copy(runtime.state)
        state.policy = permissions
        self.artifact_permissions = permissions
        self.artifact_source_policy = RegisteredJudgmentContextPolicy(claims=runtime.claims, state=state,
            log=runtime.log, registry=runtime.sources, permissions=permissions)

    def _key(self, snapshot_id):
        require_identifier(snapshot_id, "snapshot_id")
        return canonical_sha256([self.scope_digest, self.run_id, snapshot_id])

    def _immutable(self, table, snapshot_id):
        rows = _rows(self.connection.execute(f"SELECT * FROM {table} FOR VALID_TIME ALL WHERE _id = %s", (self._key(snapshot_id),)))
        if len(rows) > 1:
            raise ValueError("phase capture has ambiguous immutable metadata")
        if not rows:
            return None
        row = rows[0]
        record = json.loads(str(row["record_json"]))
        if (row["_id"] != self._key(snapshot_id) or row["scope_digest"] != self.scope_digest
                or row["record_sha256"] != record["record_sha256"]
                or canonical_sha256({key: value for key, value in record.items() if key != "record_sha256"}) != record["record_sha256"]
                or record["run_id"] != self.run_id or record["snapshot_id"] != snapshot_id
                or record["scope"] != self.scope.metadata_record() or record["authority_namespace_id"] != self.authority_namespace_id):
            raise ValueError("phase custody immutable metadata changed")
        return record

    def intent(self, snapshot_id):
        """Durable metadata only; this is not a qualified phase context."""
        record = self._immutable(_INTENTS, snapshot_id)
        if record is None:
            return None
        if (record.get("schema") != "flora-selected-phase-capture-intent-v1"
                or record["run_plan_sha256"] != self.run_plan_sha256
                or record["claim_ids"] != sorted(set(record["claim_ids"]))
                or record["source_event_ids"] != sorted(set(record["source_event_ids"]))):
            raise ValueError("phase intent does not bind an exact frozen run")
        for name in ("history_sha256", "snapshot_sha256", "object_id", "context_plan_sha256", "context_lineage_sha256"):
            require_sha256(record[name], name)
        if (record["phase"] not in {"before", "after"} or record["arm"] not in {"flora_full", "same_evidence_ablation"}
                or isinstance(record["object_size"], bool) or not isinstance(record["object_size"], int)
                or record["object_size"] <= 0 or normalize_timestamp(record["captured_at"]) != record["captured_at"]):
            raise ValueError("phase intent metadata is not canonical")
        return record

    def _event_for_intent(self, intent):
        parents = tuple(intent["source_event_ids"])
        return ExperienceEvent.create(event_type=_EVENT_TYPE, scope=self.scope, occurred_at=intent["captured_at"],
            content_digest=intent["snapshot_sha256"], provenance=ProvenanceReference.create(provenance_type="derived_inference",
                source_reference_ids=parents, derivation_activity_id="phase_snapshot:" + self._key(intent["snapshot_id"]), responsible_component="phase_snapshot_custody"),
            retention_class="ordinary_experience", storage_tier="raw_buffer", parent_event_ids=parents,
            payload_reference=intent["object_id"], policy_bindings=("phase_capture_intent:" + intent["record_sha256"],))

    def _insert(self, table, record):
        values = {"_id": self._key(record["snapshot_id"]), "scope_digest": self.scope_digest,
            "record_sha256": record["record_sha256"], "record_json": _record_json(record)}
        with self.connection.transaction():
            self.connection.execute(f"ASSERT NOT EXISTS (SELECT 1 FROM {table} FOR VALID_TIME ALL WHERE _id = %s::text)", (values["_id"],))
            self.connection.execute(f"INSERT INTO {table} ({', '.join(values)}) VALUES (" + ', '.join(_dml_placeholder(value) for value in values.values()) + ')', tuple(values.values()))

    def _custody_record(self, intent, event, source):
        record = {"schema": "flora-selected-phase-custody-v1", "scope": self.scope.metadata_record(),
            "authority_namespace_id": self.authority_namespace_id, "run_id": self.run_id,
            **{name: intent[name] for name in ("snapshot_id", "snapshot_sha256", "object_id", "source_event_ids", "claim_ids", "case_id", "phase", "arm", "history_sha256")},
            "event_id": event.event_id, "event_sha256": event.event_sha256, "registration_sha256": source.registration_sha256,
            "capture_intent_sha256": intent["record_sha256"]}
        record["record_sha256"] = canonical_sha256(record)
        return record

    def _verify_metadata(self, snapshot_id, record):
        intent = self.intent(snapshot_id)
        event = next((entry.event for entry in self.runtime.log.replay_committed() if entry.event.event_id == record["event_id"]), None)
        source = self.runtime.sources.lookup(record["event_id"])
        raw = None if source is None else self.runtime.sources.raw_reference(source.object_ref)
        if (intent is None or event is None or source is None or raw is None
                or event != self._event_for_intent(intent)
                or record != self._custody_record(intent, event, source)
                or event.payload_reference != raw.object_id or event.content_digest != raw.plaintext_sha256
                or source.evidence.scope != self.scope or source.evidence.authority_namespace_id != self.authority_namespace_id
                or source.evidence.parent_refs != event.parent_event_ids or source.evidence.content_digest != event.content_digest
                or raw.object_id != intent["object_id"] or raw.plaintext_sha256 != intent["snapshot_sha256"]
                or raw.size != intent["object_size"]):
            raise ValueError("phase custody lacks exact canonical intent/source/raw binding")
        return record

    def metadata(self, snapshot_id):
        record = self._immutable(_TABLE, snapshot_id)
        return None if record is None else self._verify_metadata(snapshot_id, record)

    def _sources_now(self, source_ids):
        for event_id in source_ids:
            if self.artifact_source_policy.allow_event(event_id, "personal_judgment") is not True:
                raise PermissionError("phase source/control use has been withdrawn")
        return True

    def _checked_history_authority(self, authority, source_gate):
        from .comparison_custody import SelectedRunEvidencePolicy
        if not isinstance(authority, SelectedRunEvidencePolicy):
            return authority
        checked = copy(authority)
        reader = copy(authority.custody)
        reader.objects = PhaseAuthorizedObjectReads(reader.objects, source_gate)
        reader.raw_custody = RegisteredEncryptedFormationCustody(registry=reader.registry, objects=reader.objects)
        checked.custody = reader
        return checked

    def _authorize_history(self, *, authority, case_id, phase, history, metadata_only=False):
        from .comparison_custody import SelectedRunEvidencePolicy
        method = authority.authorize_history
        if metadata_only and isinstance(authority, SelectedRunEvidencePolicy):
            candidate = getattr(authority, "authorize_history_metadata", None)
            if callable(candidate):
                method = candidate
        if method(case_id=case_id, phase=phase, history=history) is not True:
            raise PermissionError("phase capture/recovery lacks current independent history authority")
        return True

    def capture(self, *, snapshot_id: str, case_id: str, phase: str, arm: str,
                plan: ContextPlan, lineage: NativeJudgmentLineageVerifier, history,
                update_policy: FrozenPhaseUpdatePolicy | None = None, update_receipt: bytes | None = None):
        plan_record(plan)
        if phase not in {"before", "after"} or arm not in {"flora_full", "same_evidence_ablation"}:
            raise ValueError("phase capture requires an exact native arm/phase")
        if self.metadata(snapshot_id) is not None:
            raise ValueError("phase snapshot identity is already frozen; recover it instead")
        if self.intent(snapshot_id) is not None:
            raise PermissionError("partial phase capture intent exists; explicit custody reconciliation is required")
        # An interrupted append/index sequence must not create a second event
        # or reinterpret the same snapshot ID after production has advanced.
        if any(entry.event.provenance.responsible_component == "phase_snapshot_custody"
                and entry.event.provenance.derivation_activity_id == "phase_snapshot:" + self._key(snapshot_id)
                for entry in self.runtime.log.replay_committed()):
            raise PermissionError("partial canonical phase capture exists; explicit custody reconciliation is required")
        if (lineage.runtime is not self.runtime or lineage.run_plan_sha256 != self.run_plan_sha256
                or history.scope != self.scope or lineage.history_for(case_id, phase) != history):
            raise ValueError("phase capture crosses actual runtime/registered phase history")
        # Evaluation authority must precede even initial context/owner-proof
        # reads. The history reader's nested decrypts also keep current
        # personal source permission; full guards must never recurse into it.
        def personal_gate():
            self._sources_now(history.event_ids)
            for claim_id in plan.exact_claim_ids:
                if self.runtime.context_policy.allow_claim(claim_id, "personal_judgment") is not True:
                    raise PermissionError("phase capture Claim/source use is withdrawn")
            for route in plan.state_routes:
                if self.runtime.context_policy.allow_state(route.subject_type, route.subject_id,
                        route.projection_id, "personal_judgment") is not True:
                    raise PermissionError("phase capture personal-state/control use is withdrawn")
            self._sources_now(history.event_ids)
            for claim_id in plan.exact_claim_ids:
                _require_available(self.runtime.claims.load_current(claim_id), claim_id)
            return True
        history_authority = self._checked_history_authority(lineage.history_authority, personal_gate)
        personal_gate()
        self._authorize_history(authority=history_authority, case_id=case_id, phase=phase, history=history)
        personal_gate()
        def capture_guard():
            personal_gate()
            self._authorize_history(authority=history_authority, case_id=case_id, phase=phase, history=history,
                metadata_only=True)
            personal_gate()
        capture_guard()
        # The actual shared runtime guards its context, owner proofs and
        # artifact registry. Keep its service identities intact, avoiding
        # nested copies of a runtime-wide private-read wrapper.
        capture_runtime = self.runtime
        update_policy = update_policy or FrozenPhaseUpdatePolicy()
        if arm == "same_evidence_ablation" and phase == "after":
            before = self.metadata(update_policy.before_snapshot_id)
            if (before is None or before["snapshot_sha256"] != update_policy.before_snapshot_sha256
                    or before["phase"] != "before" or before["arm"] != "flora_full" or before["case_id"] != case_id):
                raise PermissionError("ablation must bind the actual frozen before full-update snapshot")
        context = capture_runtime._context(plan, authority_guard=capture_guard)
        receipts = {}
        capturing = copy(lineage)
        capturing.runtime, capturing.history_authority = capture_runtime, history_authority
        def receipt_for(request):
            value = lineage.phase_receipt_for(request)
            if request.request_sha256 in receipts and receipts[request.request_sha256] != value:
                raise ValueError("producer phase receipt changed during capture")
            receipts[request.request_sha256] = value
            return value
        capturing.phase_receipt_for = receipt_for
        actual = capturing.context_lineage(case_id=case_id, phase=phase, history=history, context=context, authority_guard=capture_guard)
        claim_records = []
        for binding in actual.claims:
            current = self.runtime.claims.load_current(binding.claim_id)
            version = self.runtime.claims.load_version(binding.version_id)
            relations = [self.runtime.claims.load_evidence_relation(row[0]) for row in binding.evidence_relations]
            if current["projection_sha256"] != binding.current_projection_sha256 or version["version_sha256"] != binding.version_sha256:
                raise ValueError("Claim changed during phase capture")
            claim_records.append({"claim_id": binding.claim_id, "projection": current, "version": version, "relations": relations})
        states = []
        for binding in actual.personal_state:
            head = self.runtime.state._fetch(_ACTIVE, self.runtime.state._head_id(binding.subject_type, binding.subject_id, binding.projection_id))
            row = self.runtime.state._fetch(_VERSIONS, self.runtime.state._version_id(binding.version_id), all_valid=True)
            receipt = self.runtime.state._history(binding.projection_id, binding.version_id)
            if head is None or row is None or head["version_id"] != binding.version_id or receipt["record_sha256"] != binding.activation_receipt_sha256:
                raise ValueError("personal-state activation changed during phase capture")
            states.append({"route": {"subject_type": binding.subject_type, "subject_id": binding.subject_id, "projection_id": binding.projection_id},
                "head": {key: head[key] for key in ("_id", "scope_digest", "subject_type", "subject_id", "projection_id", "version_id", "projection_sha256", "activation_generation", "approval_event_id", "approval_event_sha256", "expected_active_version_id")},
                "version": json.loads(str(row["record_json"])), "activation": receipt})
        episodes = []
        for binding in actual.episodes:
            accepted, publication, request, _, record = self.runtime.state.episodes.current_lineage(binding.episode_id,
                claims=self.runtime.claims, log=self.runtime.log)
            if record["record_sha256"] != binding.publication_record_sha256:
                raise ValueError("episode publication changed during phase capture")
            episodes.append({"episode_id": binding.episode_id, "thread_id": publication.thread_id,
                "head": self.runtime.state.episodes._head(publication.thread_id), "publication": record})
        artifacts = []
        for manifest in actual.artifacts:
            registry = self.runtime.artifacts
            head = registry._fetch(artifacts_module._CURRENT, registry._key("role", manifest.role))
            admission = registry._fetch(artifacts_module._ADMISSIONS, registry._key("artifact", manifest.artifact_id))
            if head is None or admission is None or admission["record_sha256"] != head["admission_sha256"]:
                raise ValueError("artifact changed during phase capture")
            qualification = registry._fetch(artifacts_module._QUALIFICATIONS, registry._key("qualification", admission["qualification_id"]))
            artifacts.append({"role": manifest.role, "head": head, "admission": admission, "qualification": qualification})
        if capturing.context_lineage(case_id=case_id, phase=phase, history=history, context=context, authority_guard=capture_guard) != actual:
            raise ValueError("phase authority changed during capture")
        parents = tuple(sorted(set(history.event_ids) | set(context.source_event_ids)))
        self._sources_now(parents)
        entries = self.runtime.log.replay_committed()
        body = _plain({"schema": "flora-selected-phase-snapshot-v1", "scope": self.scope.metadata_record(),
            "authority_namespace_id": self.authority_namespace_id, "run_id": self.run_id, "snapshot_id": snapshot_id,
            "case_id": case_id, "phase": phase, "arm": arm, "run_plan_sha256": self.run_plan_sha256,
            "history_sha256": history.digest(), "original_event_ids": sorted(history.event_ids), "source_event_ids": list(parents),
            "context_plan": plan_record(plan), "context_receipt": context.receipt_record(),
            "context_lineage": actual.record(), "context_lineage_sha256": actual.lineage_sha256,
            "claims": claim_records, "states": states, "episodes": episodes, "artifacts": artifacts,
            "update_policy": update_policy.record(), "update_receipt_base64": None if update_receipt is None else base64.b64encode(update_receipt).decode(),
            "producer_receipts": [{"request_sha256": key, "receipt_base64": base64.b64encode(value).decode()} for key, value in sorted(receipts.items())],
            "capture_stream_position": entries[-1].stream_position, "captured_at": normalize_timestamp(self.clock())})
        verified_update = verify_update_policy(runtime=capture_runtime, snapshot_record=body, receipt=update_receipt,
            authority_guard=capture_guard)
        body["verified_update_exclusion"] = verified_update
        if capturing.context_lineage(case_id=case_id, phase=phase, history=history, context=context, authority_guard=capture_guard) != actual:
            raise PermissionError("phase permission changed during update-exclusion verification")
        snapshot = SelectedPhaseSnapshot(body)
        snapshot.validate()
        content = canonical_json_bytes(body)
        def write_gate():
            capture_guard()
            self._sources_now(parents)
            return True
        guarded = PhaseAuthorizedObjectReads(self.runtime.objects, write_gate)
        raw = guarded.put(content)
        intent = {"schema": "flora-selected-phase-capture-intent-v1", "scope": self.scope.metadata_record(),
            "authority_namespace_id": self.authority_namespace_id, "run_id": self.run_id, "snapshot_id": snapshot_id,
            "run_plan_sha256": self.run_plan_sha256, "snapshot_sha256": raw.plaintext_sha256, "object_id": raw.object_id,
            "object_size": raw.size, "claim_ids": sorted(item["claim_id"] for item in claim_records),
            **{name: body[name] for name in ("source_event_ids", "case_id", "phase", "arm", "history_sha256", "captured_at", "capture_stream_position", "context_lineage_sha256")},
            "context_plan_sha256": canonical_sha256(body["context_plan"])}
        intent["record_sha256"] = canonical_sha256(intent)
        self._insert(_INTENTS, intent)
        if capturing.context_lineage(case_id=case_id, phase=phase, history=history, context=context, authority_guard=capture_guard) != actual:
            raise PermissionError("phase authority changed after durable capture intent")
        self._sources_now(parents)
        event = self._event_for_intent(intent)
        expected_revision = len(self.runtime.log.replay()) - 1
        capture_guard()
        self._sources_now(parents)
        self.runtime.log.append(event, expected_revision=expected_revision)
        source = register_experience_source(event_id=event.event_id, raw=raw, registry=self.runtime.sources,
            log=self.runtime.log, objects=guarded, role="derived_inference", modality="structured")
        record = self._custody_record(intent, event, source)
        self._insert(_TABLE, record)
        capture_guard()
        self._sources_now(parents)
        return snapshot

    def _phase_metadata_gate(self, snapshot_id, expected):
        if self.metadata(snapshot_id) != expected:
            raise PermissionError("phase capture metadata changed during source use")
        for claim_id in expected["claim_ids"]:
            _require_available(self.runtime.claims.load_current(claim_id), claim_id)
        self._sources_now((expected["event_id"],))
        # Permission adapters can be slow. A quarantine that arrives in that
        # interval must still win before ciphertext is decrypted.
        for claim_id in expected["claim_ids"]:
            _require_available(self.runtime.claims.load_current(claim_id), claim_id)
        return True

    def authorize(self, *, snapshot_id: str, history, history_authority, expected=None, metadata_only=True):
        """Fresh metadata-only barrier; safe before every nested private read."""
        record = self.metadata(snapshot_id)
        if record is None or (expected is not None and record != expected):
            raise PermissionError("phase capture metadata changed or is absent")
        def metadata_gate():
            return self._phase_metadata_gate(snapshot_id, record)
        metadata_gate()
        # The concrete selected authority reads original history to authenticate
        # it. Its inner reads also retain this phase's live source-use barrier.
        checked_authority = self._checked_history_authority(history_authority, metadata_gate)
        if history.scope != self.scope or history.digest() != record["history_sha256"]:
            raise PermissionError("phase recovery lost exact current history authority")
        self._authorize_history(authority=checked_authority, case_id=record["case_id"], phase=record["phase"],
            history=history, metadata_only=metadata_only)
        metadata_gate()
        return True

    def recover(self, *, snapshot_id: str, history, history_authority):
        record = self.metadata(snapshot_id)
        if record is None:
            raise ValueError("phase snapshot is absent")
        def fresh():
            return self.authorize(snapshot_id=snapshot_id, history=history, history_authority=history_authority, expected=record)
        self.authorize(snapshot_id=snapshot_id, history=history, history_authority=history_authority,
            expected=record, metadata_only=False)
        source = self.runtime.sources.lookup(record["event_id"])
        checked = PhaseAuthorizedObjectReads(self.runtime.objects, fresh)
        body = json.loads(RegisteredEncryptedFormationCustody(registry=self.runtime.sources, objects=checked).read(self.scope, source.object_ref))
        snapshot = SelectedPhaseSnapshot(body)
        snapshot.validate()
        intent = self.intent(snapshot_id)
        if (snapshot.snapshot_sha256 != record["snapshot_sha256"] or body["source_event_ids"] != record["source_event_ids"]
                or any(body[name] != record[name] for name in ("run_id", "snapshot_id", "case_id", "phase", "arm", "history_sha256"))
                or body["run_plan_sha256"] != self.run_plan_sha256 or body["scope"] != self.scope.metadata_record()
                or body["authority_namespace_id"] != self.authority_namespace_id
                or canonical_sha256(body["context_plan"]) != intent["context_plan_sha256"]
                or any(body[name] != intent[name] for name in ("context_lineage_sha256", "captured_at", "capture_stream_position"))
                or sorted(item["claim_id"] for item in body["claims"]) != record["claim_ids"]):
            raise ValueError("phase snapshot changed exact canonical scope/lineage")
        fresh()
        return snapshot

    def _repair_heads_now(self, snapshot):
        """Repair an index, never adopt a new interpretation after head moves."""
        r = snapshot.record
        for value in r["claims"]:
            if self.runtime.claims.load_current(value["claim_id"]) != value["projection"]:
                raise PermissionError("phase index repair stopped: live Claim head moved")
        for value in r["states"]:
            row = self.runtime.state._fetch(_ACTIVE, self.runtime.state._head_id(**value["route"]))
            if row is None or {key: row[key] for key in value["head"]} != value["head"]:
                raise PermissionError("phase index repair stopped: active personal-state head moved")
        for value in r["episodes"]:
            if self.runtime.state.episodes is None or self.runtime.state.episodes._head(value["thread_id"]) != value["head"]:
                raise PermissionError("phase index repair stopped: accepted episode head moved")
        for value in r["artifacts"]:
            if self.runtime.artifacts._fetch(artifacts_module._CURRENT, self.runtime.artifacts._key("role", value["role"])) != value["head"]:
                raise PermissionError("phase index repair stopped: actual producer role moved")

    def reconcile(self, *, snapshot_id: str, history, history_authority,
                  historical_bindings, invocation_id_for):
        """Explicit authenticated missing-index write, separate from recovery.

        The intent and the exact canonical event must already exist. Registered
        source custody and independently granted current permission are also
        required. This method never appends, enrolls, grants, forms or rewinds.
        """
        from .phase_routes import SelectedPhaseRoute
        existing = self.metadata(snapshot_id)
        if existing is not None:
            return SelectedPhaseRoute(custody=self, snapshot_id=snapshot_id, history=history,
                history_authority=history_authority, historical_bindings=historical_bindings,
                invocation_id_for=invocation_id_for).snapshot
        intent = self.intent(snapshot_id)
        if intent is None:
            raise PermissionError("phase index repair lacks the durable exact capture intent")
        expected = self._event_for_intent(intent)
        matching = [entry.event for entry in self.runtime.log.replay_committed()
            if entry.event.provenance.responsible_component == "phase_snapshot_custody"
            and entry.event.provenance.derivation_activity_id == expected.provenance.derivation_activity_id]
        if matching != [expected]:
            raise PermissionError("phase index repair lacks one exact already committed canonical event")
        source = self.runtime.sources.lookup(expected.event_id)
        if source is None:
            raise PermissionError("phase index repair requires independently registered canonical source custody")
        candidate = self._verify_metadata(snapshot_id, self._custody_record(intent, expected, source))
        # This temporary reader is bounded by the actual intent, canonical
        # event and registry, then by actual selected historical qualification.
        # It is never returned or available as a generic artifact reader.
        provisional = object.__new__(_CanonicalOrphanPhaseCustody)
        provisional.__dict__.update(self.__dict__)
        provisional._orphan_record = candidate
        route = SelectedPhaseRoute(custody=provisional, snapshot_id=snapshot_id, history=history,
            history_authority=history_authority, historical_bindings=historical_bindings,
            invocation_id_for=invocation_id_for)
        route.check_live()
        # Current permission evaluation may involve slow owner/backend I/O.
        # Recheck exact production heads after it, immediately before the
        # missing-index write, so that a moved head is never adopted as repair.
        self._repair_heads_now(route.snapshot)
        try:
            self._insert(_TABLE, candidate)
        except Exception:
            if self.metadata(snapshot_id) != candidate:
                raise
        route.check_live()
        self._repair_heads_now(route.snapshot)
        return route.snapshot


class _CanonicalOrphanPhaseCustody(XTDBPhaseSnapshotCustody):
    """Private reconciliation reader over an actual hash-bound physical intent."""
    def metadata(self, snapshot_id):
        record = super().metadata(snapshot_id)
        if record is not None:
            if record != self._orphan_record:
                raise PermissionError("phase index repair encountered conflicting durable custody")
            return record
        if snapshot_id != self._orphan_record["snapshot_id"]:
            raise PermissionError("phase index repair cannot resolve another capture")
        return self._verify_metadata(snapshot_id, self._orphan_record)
