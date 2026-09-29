"""Host-scoped paired-run custody on XTDB, KurrentDB and encrypted objects.

Registration records provenance; it grants no read, review or external-disclosure
permission. Current independently authorized source-purpose actions control reads.
No model, provider client, or inference substitute is implemented here.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from cognitive_kernel.canonical import canonical_sha256, normalize_timestamp, require_identifier
from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent

from ..comparison_run import (
    ArmBinding, HistorySnapshot, MeasuredUsage, PairedRun, PairedRunPlan,
    RunAttempt, SourceMaterial, _context_bytes, validate_run,
)
from ..evaluation_protocol import EvaluationCase, EvaluationProtocol
from .claims import _dml_placeholder, _record_json, _rows, configure_xtdb_connection
from .context import LocalContext
from .decision_outcome import RecordedEvent
from .experience import KurrentExperienceLog
from .formation_context import register_experience_source
from .formation_policy import XTDBFormationPermissionPolicy
from .formation_registry import (
    RegisteredEncryptedFormationCustody, XTDBFormationSourceRegistry,
)
from .object_store import EncryptedObjectPlane


_ARTIFACTS = "flora_comparison_artifacts"


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _identity(value: str, label: str) -> str:
    if require_identifier(value, label) != value:
        raise ValueError(f"{label} must be canonical")
    return value


def evaluation_purpose(run_id: str, case_id: str, phase: str) -> str:
    _identity(run_id, "run_id")
    _identity(case_id, "case_id")
    if phase not in {"before", "after"}:
        raise ValueError("unknown evaluation phase")
    return "comparison_eval:" + canonical_sha256([run_id, case_id, phase])


def _plan_record(plan: PairedRunPlan) -> dict:
    plan.validate()
    return {"protocol": plan.protocol.record(),
            "arm_bindings": {arm: vars(binding) for arm, binding in plan.arm_bindings.items()},
            "context_token_budget": plan.context_token_budget,
            "context_byte_budget": plan.context_byte_budget,
            "feature_call_budget": plan.feature_call_budget,
            "question_sha256_by_case": dict(plan.question_sha256_by_case),
            "evidence_kind": plan.evidence_kind}


def _plan_from_record(record: dict) -> PairedRunPlan:
    protocol_record = dict(record["protocol"])
    if protocol_record.pop("schema") != "flora-evaluation-protocol-v1":
        raise ValueError("stored comparison protocol schema changed")
    protocol_record["cases"] = tuple(EvaluationCase(**case) for case in protocol_record["cases"])
    protocol_record["builder_transfer_host_ids"] = tuple(protocol_record["builder_transfer_host_ids"])
    plan = PairedRunPlan(
        EvaluationProtocol(**protocol_record),
        {arm: ArmBinding(**binding) for arm, binding in record["arm_bindings"].items()},
        record["context_token_budget"], record["context_byte_budget"],
        record["feature_call_budget"], record["question_sha256_by_case"], record["evidence_kind"])
    if _plan_record(plan) != record:
        raise ValueError("stored plan is not canonical")
    return plan


@dataclass(frozen=True)
class ComparisonArtifact:
    record: dict

    @property
    def event_id(self) -> str:
        return self.record["event_id"]


class XTDBComparisonCustody:
    """Immutable artifacts and retryable event-before-registry placement.

    One instance contains one host's run slice. Cross-host aggregation is a
    separately authorized operation, not an implicit capability of this store.
    Host keys remain supplied to the selected local encrypted object plane.
    """

    def __init__(self, *, scope: ProductHostScope, authority_namespace_id: str,
                 connection: Any, registry: XTDBFormationSourceRegistry,
                 objects: EncryptedObjectPlane, log: KurrentExperienceLog):
        scope.validate()
        _identity(authority_namespace_id, "authority_namespace_id")
        if (not scope == registry.scope == objects.scope == log.scope
                or registry.authority_namespace_id != authority_namespace_id):
            raise ValueError("comparison custody crosses host or authority")
        self.scope, self.authority_namespace_id = scope, authority_namespace_id
        self.connection, self.registry = connection, registry
        self.objects, self.log = objects, log
        self.raw_custody = RegisteredEncryptedFormationCustody(registry=registry, objects=objects)
        self.scope_digest = canonical_sha256([scope.metadata_record(), authority_namespace_id])
        configure_xtdb_connection(connection)

    def _key(self, run_id: str, artifact_id: str) -> str:
        return canonical_sha256([self.scope_digest, _identity(run_id, "run_id"),
                                 _identity(artifact_id, "artifact_id")])

    def metadata(self, run_id: str, artifact_id: str) -> ComparisonArtifact | None:
        key = self._key(run_id, artifact_id)
        rows = _rows(self.connection.execute(
            f"SELECT * FROM {_ARTIFACTS} FOR VALID_TIME ALL WHERE _id = %s", (key,)))
        if len(rows) > 1:
            raise ValueError("comparison artifact has ambiguous immutable rows")
        if not rows:
            return None
        row = rows[0]
        record = json.loads(str(row["record_json"]))
        if (row["_id"] != key or row["scope_digest"] != self.scope_digest
                or record.get("schema") != "flora-comparison-artifact-v1"
                or record["scope"] != self.scope.metadata_record()
                or record["authority_namespace_id"] != self.authority_namespace_id
                or record["run_id"] != run_id or record["artifact_id"] != artifact_id
                or record["record_sha256"] != row["record_sha256"]
                or canonical_sha256({k: v for k, v in record.items() if k != "record_sha256"})
                != record["record_sha256"]):
            raise ValueError("comparison immutable metadata changed")
        source = self.registry.lookup(record["event_id"])
        if (source is None or source.object_ref != record["object_id"]
                or source.registration_sha256 != record["registration_sha256"]
                or source.evidence.content_digest != record["content_sha256"]):
            raise ValueError("comparison artifact lacks exact registered raw custody")
        event = next((event for event in self.log.replay() if event.event_id == record["event_id"]), None)
        if (event is None or event.event_sha256 != record["event_sha256"]
                or event.event_type != "comparison_artifact"
                or event.provenance.responsible_component != "comparison_custody"
                or event.provenance.derivation_activity_id != "comparison:" + key
                or event.payload_reference != record["object_id"]
                or event.content_digest != record["content_sha256"]
                or event.parent_event_ids != tuple(record["parent_event_ids"])):
            raise ValueError("comparison artifact differs from exact canonical Experience")
        return ComparisonArtifact(record)

    def register_recorded(self, recorded: RecordedEvent) -> None:
        """Trusted custody binding for an already appended delivery/decision.

        It verifies real replay and raw content through the source registry. It
        neither authenticates the producer nor grants any purpose permission.
        """
        if recorded.event.scope != self.scope or recorded.raw.scope != self.scope:
            raise ValueError("recorded comparison event crosses scope")
        register_experience_source(
            event_id=recorded.event.event_id, raw=recorded.raw,
            registry=self.registry, log=self.log, objects=self.objects,
            role="derived_inference", modality="structured")

    def register_context(self, *, run_id: str, context: LocalContext,
                         delivery: RecordedEvent, occurred_at: str) -> ComparisonArtifact:
        """Retain actual input bytes, not just a declared context hash.

        The supplied delivery must already exist in real registered custody.
        Its canonical receipt must bind this exact LocalContext. Qualification
        of the selector and model attention remains outside this operation.
        """
        if not isinstance(context, LocalContext) or self.load_recorded(delivery.event.event_id) != delivery:
            raise ValueError("context has no exact registered delivery")
        context.plan.validate()
        content = self.raw_custody.read(self.scope, delivery.raw.object_id)
        if (delivery.event.event_type != "context_delivery"
                or content != _json(context.receipt_record())
                or delivery.event.parent_event_ids != context.source_event_ids):
            raise ValueError("actual context differs from canonical delivery")
        material = _context_bytes(context)
        return self._put(run_id=run_id, artifact_id=f"context:{delivery.event.event_id}",
                         kind="context", content=material, parents=(delivery.event.event_id,),
                         metadata={"context_sha256": _digest(material),
                                   "delivery_event_id": delivery.event.event_id,
                                   "source_event_ids": list(context.source_event_ids)},
                         occurred_at=occurred_at)

    def _put(self, *, run_id: str, artifact_id: str, kind: str, content: bytes,
             parents: tuple[str, ...], metadata: dict, occurred_at: str) -> ComparisonArtifact:
        key = self._key(run_id, artifact_id)
        _identity(kind, "artifact_kind")
        if len(set(parents)) != len(parents):
            raise ValueError("artifact parents must be unique")
        raw = self.objects.put(content)
        prior = self.metadata(run_id, artifact_id)
        if prior is not None:
            if (prior.record["kind"] != kind or prior.record["content_sha256"] != raw.plaintext_sha256
                    or prior.record["object_id"] != raw.object_id
                    or prior.record["parent_event_ids"] != list(parents)
                    or prior.record["metadata"] != metadata):
                raise ValueError("comparison artifact identifier is immutable")
            return prior
        activity = "comparison:" + key
        events = self.log.replay()
        matched = [event for event in events if event.event_type == "comparison_artifact"
                   and event.provenance.derivation_activity_id == activity]
        if len(matched) > 1:
            raise ValueError("comparison artifact has duplicate canonical appends")
        if matched:
            event = matched[0]
            if (event.scope != self.scope or event.content_digest != raw.plaintext_sha256
                    or event.provenance.responsible_component != "comparison_custody"
                    or event.payload_reference != raw.object_id or event.parent_event_ids != parents):
                raise ValueError("recovered comparison append differs from retry input")
        else:
            if not set(parents).issubset({event.event_id for event in events}):
                raise ValueError("comparison artifact has absent canonical parents")
            event = ExperienceEvent.create(
                event_type="comparison_artifact", scope=self.scope,
                occurred_at=normalize_timestamp(occurred_at, "occurred_at"),
                content_digest=raw.plaintext_sha256,
                provenance=ProvenanceReference.create(
                    provenance_type="derived_inference", source_reference_ids=parents,
                    derivation_activity_id=activity, responsible_component="comparison_custody"),
                retention_class="ordinary_experience", storage_tier="raw_buffer",
                parent_event_ids=parents, payload_reference=raw.object_id)
            self.log.append(event, expected_revision=len(events) - 1)
        self.register_recorded(RecordedEvent(event, raw))
        source = self.registry.lookup(event.event_id)
        record = {"schema": "flora-comparison-artifact-v1", "scope": self.scope.metadata_record(),
                  "authority_namespace_id": self.authority_namespace_id, "run_id": run_id,
                  "artifact_id": artifact_id, "kind": kind, "object_id": raw.object_id,
                  "content_sha256": raw.plaintext_sha256, "event_id": event.event_id,
                  "event_sha256": event.event_sha256,
                  "registration_sha256": source.registration_sha256,
                  "parent_event_ids": list(parents), "metadata": metadata}
        record["record_sha256"] = canonical_sha256(record)
        values = {"_id": key, "scope_digest": self.scope_digest,
                  "record_sha256": record["record_sha256"], "record_json": _record_json(record)}
        with self.connection.transaction():
            self.connection.execute(
                f"ASSERT NOT EXISTS (SELECT 1 FROM {_ARTIFACTS} FOR VALID_TIME ALL WHERE _id = %s::text)",
                (key,))
            self.connection.execute(
                f"INSERT INTO {_ARTIFACTS} ({', '.join(values)}) VALUES ("
                + ", ".join(_dml_placeholder(value) for value in values.values()) + ")",
                tuple(values.values()))
        return ComparisonArtifact(record)

    def read(self, *, run_id: str, artifact_id: str,
             permissions: XTDBFormationPermissionPolicy, purpose: str) -> bytes:
        artifact = self.metadata(run_id, artifact_id)
        if artifact is not None and artifact.record["kind"] == "blind_key":
            raise PermissionError("blind identity key requires sealed assessment release")
        return self._read_authorized(run_id=run_id, artifact_id=artifact_id,
                                     permissions=permissions, purpose=purpose)

    def _read_authorized(self, *, run_id: str, artifact_id: str,
                         permissions: XTDBFormationPermissionPolicy, purpose: str) -> bytes:
        _identity(purpose, "purpose")
        artifact = self.metadata(run_id, artifact_id)
        if artifact is None:
            raise ValueError("comparison artifact is absent")
        kind = artifact.record["kind"]
        if kind == "blind_key" and purpose != "comparison_unblind":
            raise PermissionError("blind identity key requires the separate unblinding purpose")
        if purpose.startswith("comparison_eval:"):
            if kind in {"plan", "run", "blind_pack", "blind_key"}:
                raise PermissionError("orchestration and review artifacts are not inference inputs")
            if (kind == "history" and purpose != evaluation_purpose(
                    run_id, artifact.record["metadata"]["case_id"], artifact.record["metadata"]["phase"])):
                raise PermissionError("history manifest belongs to a different evaluation phase")
        source = self.registry.lookup(artifact.event_id)
        if not permissions.permits(source, purpose):
            raise PermissionError("comparison artifact is not currently permitted for this purpose")
        content = self.raw_custody.read(self.scope, source.object_ref)
        if (self.metadata(run_id, artifact_id) != artifact
                or _digest(content) != artifact.record["content_sha256"]
                or not permissions.permits(source, purpose)):
            raise PermissionError("comparison artifact changed or permission was withdrawn during read")
        return content

    def register_inputs(self, *, run_id: str, plan: PairedRunPlan,
                        histories: dict[tuple[str, str], HistorySnapshot],
                        questions: dict[str, bytes], occurred_at: str) -> None:
        plan.validate()
        cases = {case.case_id: case for case in plan.protocol.cases}
        if (any(case.host_id != self.scope.host_instance_id for case in cases.values())
                or set(questions) != set(cases)
                or set(histories) != {(case_id, phase) for case_id in cases for phase in ("before", "after")}):
            raise ValueError("comparison inputs must be one complete isolated host slice")
        parents = set()
        for case_id, case in cases.items():
            before = histories[(case_id, "before")]
            after = histories[(case_id, "after")]
            if (before.scope != self.scope or after.scope != self.scope
                    or after.sources[:len(before.sources)] != before.sources
                    or case.intervention_event_id not in after.event_ids
                    or case.intervention_event_id in before.event_ids
                    or _digest(questions[case_id]) != plan.question_sha256_by_case[case_id]):
                raise ValueError("registered input lineage or frozen question changed")
            for phase, history in (("before", before), ("after", after)):
                if history.digest() != getattr(case, f"{phase}_history_sha256"):
                    raise ValueError("registered history differs from frozen protocol")
                entries = {entry.event.event_id: entry.event for entry in self.log.replay_committed()}
                references = []
                for material in history.sources:
                    source = self.registry.lookup(material.event.event_id)
                    if (source is None or entries.get(material.event.event_id) != material.event
                            or self.raw_custody.read(self.scope, source.object_ref) != material.plaintext
                            or not set(source.evidence.parent_refs).issubset(history.event_ids)):
                        raise ValueError("input source lacks exact canonical registration or phase closure")
                    references.append({"event_id": material.event.event_id,
                                       "registration_sha256": source.registration_sha256,
                                       "event_sha256": material.event.event_sha256})
                body = {"schema": "flora-comparison-history-manifest-v1", "case_id": case_id,
                        "phase": phase, "history_sha256": history.digest(), "sources": references}
                self._put(run_id=run_id, artifact_id=f"history:{case_id}:{phase}", kind="history",
                          content=_json(body), parents=history.event_ids,
                          metadata={"case_id": case_id, "phase": phase,
                                    "history_sha256": history.digest(),
                                    "evaluation_purpose": evaluation_purpose(run_id, case_id, phase),
                                    "source_event_ids": list(history.event_ids)}, occurred_at=occurred_at)
                parents.update(history.event_ids)
            # A shared question never acquires after/intervention provenance.
            self._put(run_id=run_id, artifact_id=f"question:{case_id}", kind="question",
                      content=questions[case_id], parents=before.event_ids,
                      metadata={"case_id": case_id, "question_sha256": _digest(questions[case_id])},
                      occurred_at=occurred_at)
        self._put(run_id=run_id, artifact_id="plan", kind="plan", content=_json(_plan_record(plan)),
                  parents=tuple(sorted(parents)), metadata={"plan_sha256": plan.digest()},
                  occurred_at=occurred_at)

    def recover_history(self, *, run_id: str, case_id: str, phase: str,
                        permissions: XTDBFormationPermissionPolicy) -> HistorySnapshot:
        purpose = evaluation_purpose(run_id, case_id, phase)
        body = json.loads(self.read(run_id=run_id, artifact_id=f"history:{case_id}:{phase}",
                                   permissions=permissions, purpose=purpose))
        events = {event.event_id: event for event in self.log.replay()}
        sources = []
        for item in body["sources"]:
            source = self.registry.lookup(item["event_id"])
            event = events.get(item["event_id"])
            if (source is None or event is None or source.registration_sha256 != item["registration_sha256"]
                    or event.event_sha256 != item["event_sha256"]
                    or not permissions.permits(source, purpose)):
                raise PermissionError("history original changed or lost current evaluation permission")
            content = self.raw_custody.read(self.scope, source.object_ref)
            if not permissions.permits(source, purpose):
                raise PermissionError("history source was revoked while recovering content")
            sources.append(SourceMaterial(event, content))
        history = HistorySnapshot(self.scope, tuple(sources))
        if history.digest() != body["history_sha256"]:
            raise ValueError("recovered history differs from immutable input")
        # The manifest's current parent closure rechecks earlier originals too.
        self.read(run_id=run_id, artifact_id=f"history:{case_id}:{phase}",
                  permissions=permissions, purpose=purpose)
        return history

    def save_run(self, *, run_id: str, run: PairedRun, occurred_at: str) -> None:
        validate_run(run)
        plan = self.metadata(run_id, "plan")
        if (plan is None or plan.record["metadata"]["plan_sha256"] != run.plan.digest()
                or any(attempt.host_id != self.scope.host_instance_id for attempt in run.attempts)):
            raise ValueError("run does not bind the registered isolated plan")
        receipts, parents = [], [plan.event_id]
        for attempt in run.attempts:
            input_artifact = self.metadata(run_id, f"history:{attempt.case_id}:{attempt.phase}")
            question = self.metadata(run_id, f"question:{attempt.case_id}")
            if (input_artifact is None or question is None
                    or input_artifact.record["metadata"]["history_sha256"] != attempt.authorized_history_sha256
                    or tuple(input_artifact.record["metadata"]["source_event_ids"]) != attempt.authorized_event_ids
                    or question.record["content_sha256"] != _digest(run.questions[attempt.case_id])):
                raise ValueError("attempt differs from registered input custody")
            output_id = None
            if attempt.output is not None:
                output_parents = attempt.authorized_event_ids
                output_kind = "rejected_output"
                if attempt.status == "success":
                    if attempt.decision_event_id is None:
                        raise ValueError("successful output lacks its recorded decision")
                    recorded = self.load_recorded(attempt.decision_event_id)
                    material = json.loads(self.raw_custody.read(self.scope, recorded.raw.object_id))
                    if (material.get("schema") != "flora-decision-v1"
                            or base64.b64decode(material["verdict_base64"], validate=True) != attempt.output
                            or recorded.event.event_type != "decision"
                            or material.get("model_artifact_sha256") != run.plan.arm_bindings[attempt.arm].model_artifact_sha256
                            or recorded.event.provenance.model_id != run.plan.arm_bindings[attempt.arm].model_artifact_sha256
                            or recorded.event.provenance.responsible_component != run.plan.arm_bindings[attempt.arm].producer_component):
                        raise ValueError("run output differs from canonical recorded verdict")
                    consumed = tuple(material["consumed_event_ids"])
                    if not consumed or consumed != recorded.event.parent_event_ids:
                        raise ValueError("recorded verdict source lineage changed")
                    context_artifact = self.metadata(run_id, f"context:{consumed[0]}")
                    if (context_artifact is None
                            or context_artifact.record["content_sha256"] != attempt.context_sha256
                            or tuple(context_artifact.record["metadata"]["source_event_ids"]) != consumed[1:]
                            or not set(consumed[1:]).issubset(attempt.authorized_event_ids)):
                        raise ValueError("successful run lacks its exact durable input context")
                    context_source = self.registry.lookup(context_artifact.event_id)
                    context_material = self.raw_custody.read(self.scope, context_source.object_ref)
                    if len(context_material) > run.plan.context_byte_budget:
                        raise ValueError("successful context exceeds the frozen actual byte budget")
                    context_body = json.loads(context_material)
                    delivered = self.load_recorded(consumed[0])
                    if (not context_body["receipt"]["sufficient_by_declared_count"]
                            or self.raw_custody.read(self.scope, delivered.raw.object_id) != _json(context_body["receipt"])):
                        raise ValueError("successful context no longer matches canonical delivery")
                    parents.append(context_artifact.event_id)
                    output_parents, output_kind = (attempt.decision_event_id,), "output"
                output_id = f"output:{attempt.case_id}:{attempt.phase}:{attempt.arm}"
                output = self._put(
                    run_id=run_id, artifact_id=output_id, kind=output_kind, content=attempt.output,
                    parents=output_parents, metadata={"output_sha256": attempt.output_sha256,
                                                     "case_id": attempt.case_id, "phase": attempt.phase,
                                                     "attempt_status": attempt.status},
                    occurred_at=occurred_at)
                parents.append(output.event_id)
            receipt = attempt.receipt()
            receipt["output_artifact_id"] = output_id
            receipts.append(receipt)
            parents.extend((input_artifact.event_id, question.event_id))
        body = {"schema": "flora-paired-run-custody-v1", "plan_sha256": run.plan.digest(),
                "attempts": receipts}
        self._put(run_id=run_id, artifact_id="run", kind="run", content=_json(body),
                  parents=tuple(sorted(set(parents))),
                  metadata={"plan_sha256": run.plan.digest(),
                            "matrix": [{"case_id": a.case_id, "phase": a.phase, "arm": a.arm,
                                        "status": a.status} for a in run.attempts]},
                  occurred_at=occurred_at)

    def load_recorded(self, event_id: str) -> RecordedEvent:
        source = self.registry.lookup(event_id)
        event = next((event for event in self.log.replay() if event.event_id == event_id), None)
        if source is None or event is None:
            raise ValueError("recorded comparison event has no durable registration")
        raw = self.registry.raw_reference(source.object_ref)
        content = self.raw_custody.read(self.scope, source.object_ref)
        if (raw is None or event.scope != self.scope or event.payload_reference != raw.object_id
                or event.content_digest != raw.plaintext_sha256 or _digest(content) != event.content_digest
                or event.occurred_at != source.evidence.observed_at
                or event.parent_event_ids != source.evidence.parent_refs):
            raise ValueError("recorded event differs from registered canonical bytes")
        return RecordedEvent(event, raw)

    def recover_run(self, *, run_id: str, permissions: XTDBFormationPermissionPolicy,
                    purpose: str = "comparison_local_recovery") -> PairedRun:
        if not purpose.startswith("comparison_local_"):
            raise ValueError("run recovery requires an explicit local custody purpose")
        plan = _plan_from_record(json.loads(self.read(run_id=run_id, artifact_id="plan",
                                                    permissions=permissions, purpose=purpose)))
        body = json.loads(self.read(run_id=run_id, artifact_id="run", permissions=permissions, purpose=purpose))
        if body["plan_sha256"] != plan.digest():
            raise ValueError("stored run no longer binds its immutable plan")
        questions = {case.case_id: self.read(run_id=run_id, artifact_id=f"question:{case.case_id}",
                                            permissions=permissions, purpose=purpose)
                     for case in plan.protocol.cases}
        attempts = []
        for stored in body["attempts"]:
            values = dict(stored)
            if values.pop("schema") != "flora-run-attempt-v1":
                raise ValueError("stored attempt schema changed")
            output_id = values.pop("output_artifact_id")
            output = None if output_id is None else self.read(
                run_id=run_id, artifact_id=output_id, permissions=permissions, purpose=purpose)
            values["authorized_event_ids"] = tuple(values["authorized_event_ids"])
            values["usage"] = None if values["usage"] is None else MeasuredUsage(**values["usage"])
            attempts.append(RunAttempt(**values, output=output))
        run = PairedRun(plan, tuple(attempts), questions)
        validate_run(run)
        # A revocation during the collection must not be hidden by earlier reads.
        self.read(run_id=run_id, artifact_id="run", permissions=permissions, purpose=purpose)
        return run

    def save_blind_review(self, *, run_id: str, public_pack: dict, private_key: dict,
                         occurred_at: str) -> None:
        plan, run = self.metadata(run_id, "plan"), self.metadata(run_id, "run")
        if (plan is None or run is None or public_pack.get("schema") != "flora-blind-review-v1"
                or set(public_pack) != {"schema", "pairs"}
                or private_key.get("schema") != "flora-blind-review-key-v1"
                or private_key.get("plan_sha256") != plan.record["metadata"]["plan_sha256"]
                or private_key.get("public_pack_sha256") != _digest(_json(public_pack))
                or len(private_key["pairs"]) != len(public_pack["pairs"])
                or set(private_key["pairs"]) != {pair["pair_id"] for pair in public_pack["pairs"]}):
            raise ValueError("blind pack and private key do not bind the registered run")
        parents = set()
        matrix = {(a["case_id"], a["phase"], a["arm"]): a["status"]
                  for a in run.record["metadata"]["matrix"]}
        expected = {(case_id, phase, other) for case_id, phase, arm in matrix if arm == "flora_full"
                    for other in ("general_model_memory", "same_evidence_ablation")
                    if matrix[(case_id, phase, arm)] == matrix[(case_id, phase, other)] == "success"}
        observed = set()
        for pair in public_pack["pairs"]:
            if set(pair) != {"pair_id", "question", "left", "right"}:
                raise ValueError("blind reviewer content must not contain identity metadata")
            identity = private_key["pairs"][pair["pair_id"]]
            pair_arms = {identity["left"], identity["right"]}
            if ("flora_full" not in pair_arms or len(pair_arms) != 2
                    or not pair_arms.issubset({"flora_full", "general_model_memory", "same_evidence_ablation"})):
                raise ValueError("blind pair differs from the frozen comparator arms")
            other = next(arm for arm in pair_arms if arm != "flora_full")
            pair_key = (identity["case_id"], identity["phase"], other)
            if pair_key in observed:
                raise ValueError("blind review contains a duplicate successful comparison")
            observed.add(pair_key)
            question = self.metadata(run_id, f"question:{identity['case_id']}")
            if (identity["host_id"] != self.scope.host_instance_id or question is None
                    or _digest(pair["question"].encode()) != question.record["content_sha256"]):
                raise ValueError("review question differs from registered question")
            parents.add(question.event_id)
            for side in ("left", "right"):
                arm = identity[side]
                output = self.metadata(run_id, f"output:{identity['case_id']}:{identity['phase']}:{arm}")
                if (matrix.get((identity["case_id"], identity["phase"], arm)) != "success"
                        or output is None
                        or _digest(pair[side].encode()) != output.record["content_sha256"]
                        or identity[f"{side}_output_sha256"] != output.record["content_sha256"]):
                    raise ValueError("review output is not an exact successful run output")
                parents.add(output.event_id)
        comparisons = sum(2 for case_id, phase, arm in matrix if arm == "flora_full")
        if observed != expected or private_key.get("excluded_pairs") != comparisons - len(expected):
            raise ValueError("blind review omitted comparisons or changed failure exclusions")
        if not parents:
            parents.add(plan.event_id)
        pack = self._put(run_id=run_id, artifact_id="blind_pack", kind="blind_pack",
                         content=_json(public_pack), parents=tuple(sorted(parents)),
                         metadata={"public_pack_sha256": _digest(_json(public_pack)),
                                   "pair_count": len(public_pack["pairs"])}, occurred_at=occurred_at)
        self._put(run_id=run_id, artifact_id="blind_key", kind="blind_key",
                  content=_json(private_key), parents=(pack.event_id,),
                  metadata={"public_pack_sha256": _digest(_json(public_pack))}, occurred_at=occurred_at)

    def export_review(self, *, run_id: str, permissions: XTDBFormationPermissionPolicy) -> dict:
        # The key is never opened through reviewer permission.
        return json.loads(self.read(run_id=run_id, artifact_id="blind_pack",
                                    permissions=permissions, purpose="comparison_review"))

    def _read_private_key_for_sealed_assessment(
            self, *, run_id: str, permissions: XTDBFormationPermissionPolicy) -> bytes:
        """Internal hook for selected assessment's verified durable seal route.

        The assessment adapter must verify its complete independently signed
        collection and exact run/pack binding before calling this hook. Public
        reads have no permission-only unblinding route. As with the other local
        storage APIs, this is not a sandbox against owner code or raw key access.
        """
        return self._read_authorized(run_id=run_id, artifact_id="blind_key",
                                     permissions=permissions, purpose="comparison_unblind")

    def permits_external_disclosure(self, *, run_id: str, artifact_id: str,
                                    provider_id: str, permissions: XTDBFormationPermissionPolicy) -> bool:
        _identity(provider_id, "provider_id")
        artifact = self.metadata(run_id, artifact_id)
        source = None if artifact is None else self.registry.lookup(artifact.event_id)
        return (source is not None and artifact.record["kind"] != "blind_key"
                and permissions.permits(source, f"comparison_external:{provider_id}"))


class SelectedRunEvidencePolicy:
    """Current phase-purpose original access and verified selected event custody."""

    def __init__(self, *, custody: XTDBComparisonCustody, run_id: str,
                 permissions: XTDBFormationPermissionPolicy):
        _identity(run_id, "run_id")
        if (custody.scope != permissions.scope
                or custody.authority_namespace_id != permissions.authority_namespace_id):
            raise ValueError("comparison evidence policy crosses scope or authority")
        self.custody, self.run_id, self.permissions = custody, run_id, permissions

    def authorize_history(self, *, case_id: str, phase: str, history: HistorySnapshot) -> bool:
        try:
            if history.scope != self.custody.scope:
                return False
            artifact = self.custody.metadata(self.run_id, f"history:{case_id}:{phase}")
            if (artifact is None or artifact.record["metadata"]["history_sha256"] != history.digest()
                    or tuple(artifact.record["metadata"]["source_event_ids"]) != history.event_ids):
                return False
            purpose = evaluation_purpose(self.run_id, case_id, phase)
            entries = {entry.event.event_id: entry.event for entry in self.custody.log.replay_committed()}
            sources = []
            for original in history.sources:
                source = self.custody.registry.lookup(original.event.event_id)
                if (source is None or entries.get(original.event.event_id) != original.event
                        or not set(source.evidence.parent_refs).issubset(history.event_ids)
                        or not self.permissions.permits(source, purpose)
                        or self.custody.raw_custody.read(self.custody.scope, source.object_ref) != original.plaintext
                        or not self.permissions.permits(source, purpose)):
                    return False
                sources.append(source)
            return all(self.permissions.permits(source, purpose) for source in sources)
        except (ValueError, PermissionError, KeyError):
            return False

    def verify_recorded(self, recorded: RecordedEvent) -> bool:
        try:
            return self.custody.load_recorded(recorded.event.event_id) == recorded
        except (ValueError, PermissionError, KeyError):
            return False

    def current_original_permission_marker(self, *, case_id: str, phase: str,
                                           history: HistorySnapshot) -> str | None:
        """Hash a fresh source-registration/permission snapshot, never an allow cache."""
        if not self.authorize_history(case_id=case_id, phase=phase, history=history):
            return None
        purpose = evaluation_purpose(self.run_id, case_id, phase)
        marker = []
        for event_id in history.event_ids:
            source = self.custody.registry.lookup(event_id)
            action = self.permissions.current_action(event_id, purpose)
            if source is None or action is None or action.decision != "allow":
                return None
            marker.append((event_id, source.registration_sha256, action.action_sha256))
        if not self.authorize_history(case_id=case_id, phase=phase, history=history):
            return None
        for event_id, registration_sha, action_sha in marker:
            source = self.custody.registry.lookup(event_id)
            action = self.permissions.current_action(event_id, purpose)
            if (source is None or action is None or source.registration_sha256 != registration_sha
                    or action.action_sha256 != action_sha or action.decision != "allow"):
                return None
        return canonical_sha256({"run_id": self.run_id, "case_id": case_id,
                                 "phase": phase, "purpose": purpose, "sources": marker})

    def allow_question(self, *, host_id: str, case_id: str, question_sha256: str) -> bool:
        artifact = self.custody.metadata(self.run_id, f"question:{case_id}")
        return (host_id == self.custody.scope.host_instance_id and artifact is not None
                and artifact.record["content_sha256"] == question_sha256
                and self.permissions.permits(self.custody.registry.lookup(artifact.event_id), "comparison_review"))

    def allow_review(self, *, host_id: str, case_id: str, output_sha256: str) -> bool:
        if host_id != self.custody.scope.host_instance_id:
            return False
        run = self.custody.metadata(self.run_id, "run")
        if run is None:
            return False
        for attempt in run.record["metadata"]["matrix"]:
            if attempt["case_id"] != case_id or attempt["status"] != "success":
                continue
            artifact = self.custody.metadata(
                self.run_id, f"output:{case_id}:{attempt['phase']}:{attempt['arm']}")
            if (artifact is not None and artifact.record["content_sha256"] == output_sha256
                    and self.permissions.permits(self.custody.registry.lookup(artifact.event_id), "comparison_review")):
                return True
        return False
