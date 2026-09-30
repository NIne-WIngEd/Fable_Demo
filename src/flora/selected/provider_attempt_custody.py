"""Private selected custody for authorized tasks and signed transport attempts.

No provider call, grant, model output or judgment is produced here. Authorization
receipts are permission evidence, not proof that a request reached a provider.
Each actual supplied transport observation remains a separate denominator row.
"""
from __future__ import annotations

import base64
from copy import copy
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Callable, Protocol

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cognitive_kernel.canonical import canonical_sha256, normalize_timestamp, require_sha256
from cognitive_kernel.contracts import ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent

from ..comparator import (BaselineConfiguration, ExactTokenCounter, ProviderRequest, ProviderResponse,
    ProviderWireCompiler, encoded, identifier, provider_payload, sha)
from ..comparison_run import ExecutionRequest, MeasuredUsage, _context_bytes
from ..evaluation_protocol import ARMS
from ..providers.openai_responses import TransportAttempt, _usage
from .claims import _dml_placeholder, _record_json, _rows
from .comparison_custody import (SelectedRunEvidencePolicy, XTDBComparisonCustody,
    _plan_record, evaluation_purpose)
from .comparator_memory import verify_window_context
from .formation_context import register_experience_source
from .formation_policy import XTDBFormationPermissionPolicy
from .formation_registry import RegisteredEncryptedFormationCustody
from .object_store import EncryptedObjectPlane

_TABLE = "flora_provider_attempt_artifacts"
_RESULTS = {"success", "http_error", "incomplete", "refused", "cancelled", "timeout", "invalid_or_failed"}


def capture_purpose(run_id: str) -> str:
    identifier(run_id, "run_id")
    return "provider_attempt_capture:" + canonical_sha256(run_id)


def audit_purpose(run_id: str) -> str:
    identifier(run_id, "run_id")
    return "provider_attempt_audit:" + canonical_sha256(run_id)


@dataclass(frozen=True)
class VerifiedProviderInput:
    verifier_id: str
    verifier_artifact_sha256: str
    request_sha256: str
    context_sha256: str
    disclosed_context_source_ids: tuple[str, ...]
    receipt: bytes = field(repr=False)

    def record(self) -> dict:
        identifier(self.verifier_id, "verifier_id")
        for name in ("verifier_artifact_sha256", "request_sha256", "context_sha256"):
            require_sha256(getattr(self, name), name)
        if (not isinstance(self.receipt, bytes) or not self.receipt
                or tuple(sorted(set(self.disclosed_context_source_ids))) != self.disclosed_context_source_ids):
            raise ValueError("input verifier has no exact receipt or unique source set")
        return {name: getattr(self, name) for name in self.__dataclass_fields__ if name != "receipt"} | {
            "disclosed_context_source_ids": list(self.disclosed_context_source_ids),
            "receipt_sha256": sha(self.receipt)}


class ProviderInputVerifier(Protocol):
    """Independently qualified wire semantics, not a caller declaration.

    Native implementations must prove their own approved feature packet and
    minimum disclosed source closure. No native implementation is supplied here.
    """
    artifact_sha256: str
    def verify(self, *, arm: str, request: ExecutionRequest, provider_request: ProviderRequest,
               history) -> VerifiedProviderInput: ...


class OriginalMemoryProviderInputVerifier:
    """Concrete verifier for the existing original-memory comparator only."""
    def __init__(self, *, configuration: BaselineConfiguration, compiler: ProviderWireCompiler):
        self.configuration, self.compiler = configuration, compiler
        self.artifact_sha256 = canonical_sha256({"source": sha(Path(__file__).read_bytes()),
            "configuration": configuration.digest(), "compiler": compiler.artifact_sha256})

    def verify(self, *, arm, request, provider_request, history):
        config = self.configuration
        if (arm != "general_model_memory" or provider_request.configuration != config.provider
                or request.binding.model_artifact_sha256 != config.provider.digest()
                or request.binding.lineage_sha256 != config.digest()
                or request.binding.producer_component != config.producer_component):
            raise PermissionError("original-memory verifier cannot qualify another producer or native task")
        verify_window_context(request.context, history, config)
        actual = provider_payload(config, question=request.question, context=request.context,
            response_token_budget=request.plan.protocol.response_token_budget, wire_compiler=self.compiler)
        if actual != provider_request.payload:
            raise PermissionError("provider wire differs from exact frozen original-memory input")
        receipt = encoded({"schema": "flora-original-memory-input-verification-v1",
            "configuration_sha256": config.digest(), "wire_sha256": sha(actual),
            "context_sha256": sha(_context_bytes(request.context)), "history_sha256": history.digest()})
        return VerifiedProviderInput("original_memory_wire", self.artifact_sha256, sha(actual),
            sha(_context_bytes(request.context)), request.context.source_event_ids, receipt)


class _CheckedObjects:
    """Gate nested decrypts, including put/recovery's internal get calls."""
    def __init__(self, objects, check: Callable[[], None]):
        self.objects, self.check = objects, check
    def __getattr__(self, name):
        return getattr(self.objects, name)
    def get(self, reference):
        self.check()
        content = self.objects.get(reference)
        self.check()
        return content
    def put(self, content):
        self.check()
        return EncryptedObjectPlane.put(self, content)
    def recover_reference(self, **kwargs):
        self.check()
        return EncryptedObjectPlane.recover_reference(self, **kwargs)


@dataclass(frozen=True)
class RecoveredProviderAttempt:
    task: dict = field(repr=False)
    authorization: dict = field(repr=False)
    observation: TransportAttempt = field(repr=False)
    usage: MeasuredUsage | None
    observed_attempt_count: int = 1


class XTDBProviderAttemptCustody:
    """Separate private ledger; comparison/reviewer read routes cannot open it."""
    def __init__(self, *, comparison: XTDBComparisonCustody, evidence: SelectedRunEvidencePolicy,
                 permissions: XTDBFormationPermissionPolicy, input_verifier: ProviderInputVerifier,
                 tokenizer: ExactTokenCounter, tokenizer_artifact_sha256: str,
                 tokenizer_configuration_sha256: str, observer_public_key: bytes,
                 approved_observer_public_key_sha256: str, clock: Callable[[], str]):
        if (evidence.custody is not comparison or evidence.permissions is not permissions
                or permissions.scope != comparison.scope
                or permissions.authority_namespace_id != comparison.authority_namespace_id):
            raise ValueError("provider custody crosses selected run, host or permission authority")
        for value in (tokenizer_artifact_sha256, tokenizer_configuration_sha256,
                      approved_observer_public_key_sha256, input_verifier.artifact_sha256):
            require_sha256(value, "frozen provider component digest")
        if not isinstance(observer_public_key, bytes) or sha(observer_public_key) != approved_observer_public_key_sha256:
            raise PermissionError("provider observer is not the independently enrolled key")
        self.comparison, self.evidence, self.permissions = comparison, evidence, permissions
        self.registry, self.log, self.objects, self.connection = (comparison.registry,
            comparison.log, comparison.objects, comparison.connection)
        self.run_id, self.scope = evidence.run_id, comparison.scope
        self.input_verifier, self.tokenizer = input_verifier, tokenizer
        self._input_artifact = input_verifier.artifact_sha256
        self._tokenizer_artifact, self._tokenizer_config = tokenizer_artifact_sha256, tokenizer_configuration_sha256
        self._public_bytes, self._public = observer_public_key, Ed25519PublicKey.from_public_bytes(observer_public_key)
        self.clock = clock

    def _key(self, task_id, kind):
        identifier(task_id, "task_id")
        if kind not in {"task", "authorization", "observation"}:
            raise ValueError("unknown private provider artifact")
        return canonical_sha256([self.comparison.scope_digest, self.run_id, task_id, kind])

    def _source(self, event_id):
        source = self.registry.lookup(event_id)
        event = next((event for event in self.log.replay() if event.event_id == event_id), None)
        raw = None if source is None else self.registry.raw_reference(source.object_ref)
        if (source is None or event is None or raw is None or event.scope != self.scope
                or source.evidence.scope != self.scope or raw.scope != self.scope
                or event.payload_reference != raw.object_id or event.content_digest != raw.plaintext_sha256
                or source.evidence.content_digest != event.content_digest
                or tuple(source.evidence.parent_refs) != event.parent_event_ids):
            raise ValueError("provider source lacks exact Kurrent/XTDB/encrypted-object binding")
        return source, event, raw

    def _require(self, source_ids, purpose):
        for event_id in source_ids:
            source, _, _ = self._source(event_id)
            if self.permissions.permits(source, purpose) is not True:
                raise PermissionError("private provider source is not currently permitted")

    def _read_source(self, event_id, purpose):
        source, _, _ = self._source(event_id)
        def check():
            if self.registry.lookup(event_id) != source:
                raise PermissionError("provider source registration changed during private read")
            self._require((event_id,), purpose)
        check()
        checked = _CheckedObjects(self.objects, check)
        return RegisteredEncryptedFormationCustody(registry=self.registry, objects=checked).read(self.scope, source.object_ref)

    def _metadata(self, task_id, kind):
        key = self._key(task_id, kind)
        rows = _rows(self.connection.execute(f"SELECT * FROM {_TABLE} FOR VALID_TIME ALL WHERE _id = %s", (key,)))
        if len(rows) > 1:
            raise ValueError("private provider artifact has ambiguous immutable rows")
        if not rows:
            return None
        row, record = rows[0], json.loads(str(rows[0]["record_json"]))
        if (row["_id"] != key or row["scope_digest"] != self.comparison.scope_digest
                or record.get("schema") != "flora-provider-attempt-artifact-v1"
                or record["run_id"] != self.run_id or record["task_id"] != task_id or record["kind"] != kind
                or record["scope"] != self.scope.metadata_record()
                or record["authority_namespace_id"] != self.comparison.authority_namespace_id
                or row["record_sha256"] != record["record_sha256"]
                or canonical_sha256({k: v for k, v in record.items() if k != "record_sha256"}) != record["record_sha256"]):
            raise ValueError("private provider immutable metadata changed")
        source, event, raw = self._source(record["event_id"])
        if (event.event_type != "provider_attempt_artifact"
                or event.provenance.responsible_component != "provider_attempt_custody"
                or event.provenance.derivation_activity_id != "provider_attempt:" + key
                or event.event_sha256 != record["event_sha256"] or raw.object_id != record["object_id"]
                or raw.plaintext_sha256 != record["content_sha256"]
                or source.registration_sha256 != record["registration_sha256"]
                or list(event.parent_event_ids) != record["parent_event_ids"]):
            raise ValueError("private provider artifact lacks exact selected lineage")
        return record

    def _save(self, task_id, kind, body, *, parents, capture_sources, metadata):
        content, key = encoded(body), self._key(task_id, kind)
        self._require(capture_sources, capture_purpose(self.run_id))
        prior = self._metadata(task_id, kind)
        if prior is not None:
            if (prior["content_sha256"] != sha(content) or prior["parent_event_ids"] != list(parents)
                    or prior["metadata"] != metadata):
                raise ValueError("private provider task/artifact identity is immutable")
            return prior
        checked = _CheckedObjects(self.objects, lambda: self._require(capture_sources, capture_purpose(self.run_id)))
        raw = checked.put(content)
        events = self.log.replay()
        matches = [event for event in events if event.provenance.derivation_activity_id == "provider_attempt:" + key]
        if len(matches) > 1:
            raise ValueError("provider artifact has duplicate canonical appends")
        if matches:
            event = matches[0]
            if (event.scope != self.scope or event.content_digest != raw.plaintext_sha256
                    or event.payload_reference != raw.object_id or event.parent_event_ids != parents
                    or event.event_type != "provider_attempt_artifact"
                    or event.provenance.responsible_component != "provider_attempt_custody"):
                raise ValueError("provider artifact retry differs from actual canonical append")
        else:
            if not set(parents).issubset({event.event_id for event in events}):
                raise ValueError("provider artifact has absent causal parents")
            event = ExperienceEvent.create(event_type="provider_attempt_artifact", scope=self.scope,
                occurred_at=normalize_timestamp(self.clock()), content_digest=raw.plaintext_sha256,
                provenance=ProvenanceReference.create(provenance_type="derived_inference", source_reference_ids=parents,
                    derivation_activity_id="provider_attempt:" + key, responsible_component="provider_attempt_custody"),
                retention_class="ordinary_experience", storage_tier="raw_buffer", parent_event_ids=parents,
                payload_reference=raw.object_id)
            self.log.append(event, expected_revision=len(events) - 1)
        source = register_experience_source(event_id=event.event_id, raw=raw, registry=self.registry,
            log=self.log, objects=checked, role="derived_inference", modality="structured")
        record = {"schema": "flora-provider-attempt-artifact-v1", "scope": self.scope.metadata_record(),
            "authority_namespace_id": self.comparison.authority_namespace_id, "run_id": self.run_id,
            "task_id": task_id, "kind": kind, "event_id": event.event_id, "event_sha256": event.event_sha256,
            "object_id": raw.object_id, "content_sha256": raw.plaintext_sha256,
            "registration_sha256": source.registration_sha256, "parent_event_ids": list(parents), "metadata": metadata}
        record["record_sha256"] = canonical_sha256(record)
        values = {"_id": key, "scope_digest": self.comparison.scope_digest,
            "run_id": self.run_id, "task_id": task_id, "kind": kind,
            "execution_group_sha256": metadata.get("execution_group_sha256", ""),
            "record_sha256": record["record_sha256"], "record_json": _record_json(record)}
        self._require(capture_sources, capture_purpose(self.run_id))
        with self.connection.transaction():
            self.connection.execute(f"ASSERT NOT EXISTS (SELECT 1 FROM {_TABLE} FOR VALID_TIME ALL WHERE _id = %s::text)", (key,))
            if kind == "authorization":
                self.connection.execute(f"ASSERT NOT EXISTS (SELECT 1 FROM {_TABLE} FOR VALID_TIME ALL "
                    "WHERE scope_digest = %s::text AND execution_group_sha256 = %s::text "
                    "AND kind = 'authorization' GROUP BY execution_group_sha256 HAVING COUNT(*) >= %s::bigint)",
                    (self.comparison.scope_digest, metadata["execution_group_sha256"], metadata["maximum_attempts"]))
            self.connection.execute(f"INSERT INTO {_TABLE} ({', '.join(values)}) VALUES ("
                + ", ".join(_dml_placeholder(value) for value in values.values()) + ")", tuple(values.values()))
        self._require(capture_sources, capture_purpose(self.run_id))
        return record

    def _phase_history(self, request):
        history_artifact = self.comparison.metadata(self.run_id, f"history:{request.case_id}:{request.phase}")
        if history_artifact is None:
            raise ValueError("provider task phase history is unregistered")
        gate_ids = request.authorized_event_ids + (history_artifact.event_id,)
        purpose = evaluation_purpose(self.run_id, request.case_id, request.phase)
        reader = copy(self.comparison)
        reader.objects = _CheckedObjects(self.objects, lambda: self._require(gate_ids, purpose))
        reader.raw_custody = RegisteredEncryptedFormationCustody(registry=self.registry, objects=reader.objects)
        history = reader.recover_history(run_id=self.run_id, case_id=request.case_id, phase=request.phase,
                                         permissions=self.permissions)
        checked_evidence = copy(self.evidence)
        checked_evidence.custody = reader
        return history, checked_evidence

    def _authorized_history(self, arm, request):
        history, checked_evidence = self._phase_history(request)
        if (history.digest() != request.authorized_history_sha256 or history.event_ids != request.authorized_event_ids
                or not checked_evidence.authorize_context(case_id=request.case_id, phase=request.phase,
                    history=history, context=request.context, arm=arm)):
            raise PermissionError("provider task lacks current independent phase context lineage")
        return history

    def _live_input(self, arm, request, provider_request):
        history = self._authorized_history(arm, request)
        if self.input_verifier.artifact_sha256 != self._input_artifact:
            raise ValueError("provider input verifier changed its qualified artifact")
        verified = self.input_verifier.verify(arm=arm, request=request, provider_request=provider_request, history=history)
        if (not isinstance(verified, VerifiedProviderInput)
                or verified.record()["verifier_artifact_sha256"] != self._input_artifact
                or verified.request_sha256 != sha(provider_request.payload)
                or verified.context_sha256 != sha(_context_bytes(request.context))
                or not set(verified.disclosed_context_source_ids).issubset(request.context.source_event_ids)):
            raise ValueError("independent wire verification differs from actual source/context input")
        # An independent verifier can take time. Its receipt is not a cached
        # permission grant and cannot survive withdrawal during verification.
        self._authorized_history(arm, request)
        if self.input_verifier.artifact_sha256 != self._input_artifact:
            raise ValueError("provider input verifier changed during verification")
        return verified

    def prepare_task(self, *, task_id: str, arm: str, request: ExecutionRequest,
                     provider_request: ProviderRequest):
        identifier(task_id, "task_id")
        if (arm not in ARMS or request.scope != self.scope
                or request.binding != request.plan.binding_for(request.case_id, request.phase, arm)
                or request.plan.feature_call_budget < 1
                or provider_request.maximum_output_tokens != request.plan.protocol.response_token_budget
                or provider_request.configuration.feature_engine_id != request.plan.protocol.feature_engine_id):
            raise ValueError("provider task differs from frozen host/arm/feature budget")
        provider_request.record()
        plan = self.comparison.metadata(self.run_id, "plan")
        question = self.comparison.metadata(self.run_id, "question:" + request.case_id)
        phase = self.comparison.metadata(self.run_id, f"history:{request.case_id}:{request.phase}")
        if (plan is None or question is None or phase is None
                or plan.record["metadata"]["plan_sha256"] != request.plan.digest()
                or plan.record["content_sha256"] != sha(encoded(_plan_record(request.plan)))
                or question.record["content_sha256"] != sha(request.question)
                or request.plan.question_sha256_by_case[request.case_id] != sha(request.question)):
            raise ValueError("provider task differs from actual registered plan/question")
        verified = self._live_input(arm, request, provider_request)
        count = self.tokenizer.count(provider_request.payload)
        if (count.content_sha256 != sha(provider_request.payload) or count.artifact_sha256 != self._tokenizer_artifact
                or count.configuration_sha256 != self._tokenizer_config
                or isinstance(count.tokens, bool) or not isinstance(count.tokens, int) or count.tokens < 0
                or count.tokens > request.plan.context_token_budget):
            raise ValueError("provider task lacks actual frozen preflight count/budget")
        parents = tuple(sorted(set((question.event_id, phase.event_id) + request.context.source_event_ids)))
        bindings = []
        for event_id in parents:
            source, event, raw = self._source(event_id)
            bindings.append({"event_id": event_id, "event_sha256": event.event_sha256,
                "registration_sha256": source.registration_sha256, "object_id": raw.object_id,
                "content_sha256": raw.plaintext_sha256, "parent_event_ids": list(event.parent_event_ids)})
        body = {"schema": "flora-provider-task-v1", "run_id": self.run_id, "task_id": task_id,
            "case_id": request.case_id, "phase": request.phase, "arm": arm,
            "scope": self.scope.metadata_record(), "authority_namespace_id": self.comparison.authority_namespace_id,
            "plan_sha256": request.plan.digest(), "binding": vars(request.binding),
            "maximum_dispatch_attempts": request.plan.feature_call_budget,
            "history_sha256": request.authorized_history_sha256, "original_event_ids": list(request.authorized_event_ids),
            "question_base64": base64.b64encode(request.question).decode(),
            "context_base64": base64.b64encode(_context_bytes(request.context)).decode(),
            "context_source_ids": list(request.context.source_event_ids),
            "provider_configuration": provider_request.configuration.record(), "dispatch": provider_request.record(),
            "request_base64": base64.b64encode(provider_request.payload).decode(), "preflight_count": vars(count),
            "input_verification": verified.record(), "input_receipt_base64": base64.b64encode(verified.receipt).decode(),
            "observer_public_key_sha256": sha(self._public_bytes), "source_bindings": bindings,
            "disclosure_source_ids": list(dict.fromkeys((question.event_id,) + verified.disclosed_context_source_ids))}
        self._save(task_id, "task", body, parents=parents, capture_sources=parents,
            metadata={"case_id": request.case_id, "phase": request.phase, "arm": arm,
                      "plan_sha256": request.plan.digest(), "request_sha256": sha(provider_request.payload)})
        self._authorized_history(arm, request)
        return BoundProviderAttemptSink(self, body, request, provider_request, verified)

    def _verify_task(self, body, task_id):
        plan = self.comparison.metadata(self.run_id, "plan")
        question = self.comparison.metadata(self.run_id, "question:" + body["case_id"])
        history = self.comparison.metadata(self.run_id, f"history:{body['case_id']}:{body['phase']}")
        request = base64.b64decode(body["request_base64"], validate=True)
        context = base64.b64decode(body["context_base64"], validate=True)
        verification = body["input_verification"]
        count = body["preflight_count"]
        if (body.get("schema") != "flora-provider-task-v1" or body["run_id"] != self.run_id
                or body["task_id"] != task_id or body["scope"] != self.scope.metadata_record()
                or body["authority_namespace_id"] != self.comparison.authority_namespace_id
                or body["arm"] not in ARMS or body["phase"] not in {"before", "after"}
                or plan is None or question is None or history is None
                or plan.record["metadata"]["plan_sha256"] != body["plan_sha256"]
                or question.record["content_sha256"] != sha(base64.b64decode(body["question_base64"], validate=True))
                or history.record["metadata"]["history_sha256"] != body["history_sha256"]
                or history.record["metadata"]["source_event_ids"] != body["original_event_ids"]
                or verification["request_sha256"] != sha(request) or count["content_sha256"] != sha(request)
                or verification["context_sha256"] != sha(context)
                or verification["receipt_sha256"] != sha(base64.b64decode(body["input_receipt_base64"], validate=True))
                or verification["verifier_artifact_sha256"] != self._input_artifact
                or count["artifact_sha256"] != self._tokenizer_artifact or count["configuration_sha256"] != self._tokenizer_config
                or body["dispatch"]["payload_sha256"] != sha(request)
                or body["dispatch"]["configuration_sha256"] != canonical_sha256(body["provider_configuration"])
                or body["observer_public_key_sha256"] != sha(self._public_bytes)
                or not set(verification["disclosed_context_source_ids"]).issubset(body["context_source_ids"])
                or body["disclosure_source_ids"] != list(dict.fromkeys((question.event_id,) + tuple(verification["disclosed_context_source_ids"])))):
            raise ValueError("private provider task no longer binds exact frozen inputs and qualified components")

    def _verify_authorization(self, body, authorization):
        purpose = "comparison_external:" + body["provider_configuration"]["provider_id"]
        source_ids = [value["event_id"] for value in authorization["sources"]]
        source_marker = canonical_sha256({"provider_configuration_sha256": body["dispatch"]["configuration_sha256"],
            "payload_sha256": body["dispatch"]["payload_sha256"], "purpose": purpose,
            "sources": [(value["event_id"], value["registration_sha256"], value["action_sha256"])
                        for value in authorization["sources"]]})
        marker = self._task_marker(body, source_marker)
        if (authorization["purpose"] != purpose or source_ids != body["disclosure_source_ids"]
                or authorization["source_authorization_marker"] != source_marker
                or authorization["authorization_marker"] != marker):
            raise ValueError("dispatch marker changed exact task/provider/wire/source authority")
        for value in authorization["sources"]:
            action = self.permissions._stored_action(value["action_id"])
            if (action is None or action["action"]["action_sha256"] != value["action_sha256"]
                    or action["action"]["source_registration_sha256"] != value["registration_sha256"]
                    or action["action"]["source_ref_id"] != value["event_id"]
                    or action["action"]["purpose"] != purpose or action["action"]["decision"] != "allow"):
                raise ValueError("dispatch authorization lacks its immutable independent permission action")

    def _verify_task_sources(self, body, purpose):
        for binding in body["source_bindings"]:
            source, event, raw = self._source(binding["event_id"])
            if (source.registration_sha256 != binding["registration_sha256"]
                    or event.event_sha256 != binding["event_sha256"] or raw.object_id != binding["object_id"]
                    or raw.plaintext_sha256 != binding["content_sha256"]
                    or list(event.parent_event_ids) != binding["parent_event_ids"]):
                raise ValueError("provider task source registration or exact raw lineage changed")
            self._require((binding["event_id"],), purpose)

    @staticmethod
    def _task_marker(body, source_marker):
        """Bind an observed exchange to one registered task, including retries.

        Equal wire bytes and unchanged source permissions do not identify a
        distinct dispatch. The private task digest additionally binds run,
        case, phase, arm, context, source closure and preflight configuration.
        """
        return canonical_sha256({"schema": "flora-provider-task-transfer-v1",
            "task_sha256": sha(encoded(body)), "source_authorization_marker": source_marker})

    def _external_snapshot(self, body):
        purpose = "comparison_external:" + body["provider_configuration"]["provider_id"]
        sources = []
        for event_id in body["disclosure_source_ids"]:
            source, _, _ = self._source(event_id)
            action = self.permissions.current_action(event_id, purpose)
            if action is None or self.permissions.permits(source, purpose) is not True:
                raise PermissionError("actual wire source lacks separate current external consent")
            sources.append({"event_id": event_id, "registration_sha256": source.registration_sha256,
                            "action_sha256": action.action_sha256, "action_id": action.action_id})
        for saved in sources:
            source, _, _ = self._source(saved["event_id"])
            action = self.permissions.current_action(saved["event_id"], purpose)
            if (action is None or action.action_sha256 != saved["action_sha256"]
                    or source.registration_sha256 != saved["registration_sha256"]
                    or self.permissions.permits(source, purpose) is not True):
                raise PermissionError("external permission changed while checking exact wire")
        source_marker = canonical_sha256({"provider_configuration_sha256": body["dispatch"]["configuration_sha256"],
            "payload_sha256": body["dispatch"]["payload_sha256"], "purpose": purpose,
            "sources": [(value["event_id"], value["registration_sha256"], value["action_sha256"]) for value in sources]})
        return {"purpose": purpose, "source_authorization_marker": source_marker,
            "authorization_marker": self._task_marker(body, source_marker), "sources": sources}

    def _verify_observation(self, body, authorization, observation):
        if not isinstance(observation, TransportAttempt):
            raise ValueError("provider attempt is not an actual transport observation")
        meta = observation.metadata
        self._public.verify(observation.proof, encoded(meta))
        required = {"schema", "configuration_sha256", "request_sha256", "authorization_marker", "response_sha256",
            "http_status", "response_complete", "request_id", "result", "returned_model_id", "usage",
            "cost_microunits", "observer_public_key_sha256"}
        if (set(meta) != required or meta["schema"] != "flora-openai-transport-attempt-v1"
                or meta["configuration_sha256"] != body["dispatch"]["configuration_sha256"]
                or meta["request_sha256"] != body["dispatch"]["payload_sha256"]
                or observation.actual_request != base64.b64decode(body["request_base64"], validate=True)
                or sha(observation.actual_request) != meta["request_sha256"]
                or meta["authorization_marker"] != authorization["authorization_marker"]
                or meta["observer_public_key_sha256"] != body["observer_public_key_sha256"]
                or body["observer_public_key_sha256"] != sha(self._public_bytes)
                or not isinstance(meta["response_complete"], bool) or meta["result"] not in _RESULTS
                or (meta["http_status"] is not None and (isinstance(meta["http_status"], bool)
                    or not isinstance(meta["http_status"], int) or not 100 <= meta["http_status"] <= 599))
                or meta["cost_microunits"] is not None
                or (observation.actual_response is not None and not isinstance(observation.actual_response, bytes))
                or meta["response_sha256"] != (None if observation.actual_response is None else sha(observation.actual_response))):
            raise ValueError("signed attempt differs from frozen task, authority or actual bytes")
        usage = None
        if meta["usage"] is not None:
            usage = MeasuredUsage(**meta["usage"])
            usage.validate()
            if not meta["response_complete"] or observation.actual_response is None:
                raise ValueError("partial/unavailable response cannot supply independently verified server usage")
            response = json.loads(observation.actual_response)
            parsed = _usage(response, body["provider_configuration"]["feature_engine_id"]) if isinstance(response, dict) else None
            if parsed != usage or response.get("model") != meta["returned_model_id"]:
                raise ValueError("signed known usage differs from actual complete response")
        if meta["result"] == "success" and (usage is None or meta["http_status"] != 200
                or not meta["request_id"] or meta["returned_model_id"] not in body["provider_configuration"]["permitted_response_model_ids"]
                or response.get("status") != "completed"):
            raise ValueError("successful observation lacks completed allowlisted model and actual usage")
        return usage

    def recover(self, *, task_id: str) -> RecoveredProviderAttempt:
        records = {kind: self._metadata(task_id, kind) for kind in ("task", "authorization", "observation")}
        if any(record is None for record in records.values()):
            raise ValueError("provider task has no complete durable observed-attempt chain")
        purpose = audit_purpose(self.run_id)
        bodies = {kind: json.loads(self._read_source(record["event_id"], purpose)) for kind, record in records.items()}
        task, authorization, saved = bodies["task"], bodies["authorization"], bodies["observation"]
        self._verify_task(task, task_id)
        if (authorization["task_sha256"] != records["task"]["content_sha256"]
                or saved["task_sha256"] != records["task"]["content_sha256"]
                or saved["authorization_sha256"] != records["authorization"]["content_sha256"]
                or records["authorization"]["parent_event_ids"] != [records["task"]["event_id"]]
                or records["observation"]["parent_event_ids"] != [records["authorization"]["event_id"]]):
            raise ValueError("durable provider task/authorization/observation lineage changed")
        self._verify_task_sources(task, purpose)
        self._verify_authorization(task, authorization)
        observation = TransportAttempt(saved["metadata"], base64.b64decode(saved["actual_request_base64"], validate=True),
            None if saved["actual_response_base64"] is None else base64.b64decode(saved["actual_response_base64"], validate=True),
            base64.b64decode(saved["proof_base64"], validate=True))
        usage = self._verify_observation(task, authorization, observation)
        for record in records.values():
            self._require((record["event_id"],), purpose)
        return RecoveredProviderAttempt(task, authorization, observation, usage)


class BoundProviderAttemptSink:
    """One task is one dispatch attempt; retries require distinct frozen tasks."""
    def __init__(self, owner, body, request, provider_request, verification):
        self.owner, self.body = owner, body
        self.request, self.provider_request, self.verification = request, provider_request, verification

    def wrap_authorize_transfer(self, callback: Callable[[], str]) -> Callable[[], str]:
        def authorize():
            owner, body = self.owner, self.body
            if owner._metadata(body["task_id"], "authorization") is not None:
                raise PermissionError("task already has a dispatch authorization; retry needs a new task ID")
            current = owner._live_input(body["arm"], self.request, self.provider_request)
            if current.record() != self.verification.record() or current.receipt != self.verification.receipt:
                raise PermissionError("task wire/context qualification changed before transfer")
            marker = callback()
            snapshot = owner._external_snapshot(body)
            if marker != snapshot["source_authorization_marker"]:
                raise PermissionError("actual transfer callback differs from independently checked source authority")
            task = owner._metadata(body["task_id"], "task")
            if task is None or task["content_sha256"] != sha(encoded(body)):
                raise ValueError("provider task lost its exact registered immutable binding")
            authorization = {"schema": "flora-provider-dispatch-authorization-v1",
                "task_sha256": task["content_sha256"], **snapshot}
            owner._save(body["task_id"], "authorization", authorization, parents=(task["event_id"],),
                capture_sources=tuple(value["event_id"] for value in body["source_bindings"]),
                metadata={"task_sha256": task["content_sha256"], "snapshot": snapshot,
                    "execution_group_sha256": canonical_sha256([owner.run_id, body["case_id"], body["phase"], body["arm"]]),
                    "maximum_attempts": body["maximum_dispatch_attempts"]})
            owner._authorized_history(body["arm"], self.request)
            if owner._external_snapshot(body) != snapshot:
                raise PermissionError("external permission changed before actual dispatch")
            return snapshot["authorization_marker"]
        return authorize

    def record(self, observation: TransportAttempt) -> None:
        owner, body = self.owner, self.body
        task = owner._metadata(body["task_id"], "task")
        authorization = owner._metadata(body["task_id"], "authorization")
        if task is None or authorization is None or task["content_sha256"] != sha(encoded(body)):
            raise ValueError("transport observation lacks exact durable task and dispatch authorization")
        snapshot = authorization["metadata"]["snapshot"]
        auth_body = {"schema": "flora-provider-dispatch-authorization-v1", "task_sha256": task["content_sha256"], **snapshot}
        if authorization["content_sha256"] != sha(encoded(auth_body)):
            raise ValueError("dispatch snapshot differs from committed authorization bytes")
        usage = owner._verify_observation(body, snapshot, observation)
        owner._verify_task(body, body["task_id"])
        owner._verify_authorization(body, snapshot)
        owner._verify_task_sources(body, capture_purpose(owner.run_id))
        saved = {"schema": "flora-provider-observed-attempt-v1", "task_sha256": task["content_sha256"],
            "authorization_sha256": authorization["content_sha256"], "metadata": observation.metadata,
            "actual_request_base64": base64.b64encode(observation.actual_request).decode(),
            "actual_response_base64": None if observation.actual_response is None else base64.b64encode(observation.actual_response).decode(),
            "proof_base64": base64.b64encode(observation.proof).decode()}
        owner._save(body["task_id"], "observation", saved, parents=(authorization["event_id"],),
            capture_sources=tuple(value["event_id"] for value in body["source_bindings"]),
            metadata={"case_id": body["case_id"], "phase": body["phase"], "arm": body["arm"],
                "result": observation.metadata["result"], "observed_attempt_count": 1,
                "usage": None if usage is None else vars(usage), "task_sha256": task["content_sha256"]})

    def _captured_observation(self):
        """Verify this issued task's capture; this is not a general audit reader.

        Capture authorization covers validation of exactly the observation
        preserved by this handle. It cannot open unrelated artifact IDs or be
        substituted for the independently granted public audit recovery route.
        """
        owner, body = self.owner, self.body
        task = owner._metadata(body["task_id"], "task")
        authorization = owner._metadata(body["task_id"], "authorization")
        observation = owner._metadata(body["task_id"], "observation")
        if (task is None or authorization is None or observation is None
                or task["content_sha256"] != sha(encoded(body))
                or authorization["parent_event_ids"] != [task["event_id"]]
                or observation["parent_event_ids"] != [authorization["event_id"]]):
            raise ValueError("bound task has no exact durable captured observation")
        owner._verify_task(body, body["task_id"])
        snapshot = authorization["metadata"]["snapshot"]
        auth_body = {"schema": "flora-provider-dispatch-authorization-v1", "task_sha256": task["content_sha256"], **snapshot}
        if authorization["content_sha256"] != sha(encoded(auth_body)):
            raise ValueError("bound dispatch differs from canonical authorization")
        owner._verify_authorization(body, snapshot)
        source, _, _ = owner._source(observation["event_id"])
        def check():
            if (owner._metadata(body["task_id"], "observation") != observation
                    or owner.registry.lookup(observation["event_id"]) != source):
                raise PermissionError("captured observation registration changed during bound validation")
            owner._verify_task_sources(body, capture_purpose(owner.run_id))
        check()
        checked = _CheckedObjects(owner.objects, check)
        saved = json.loads(RegisteredEncryptedFormationCustody(registry=owner.registry, objects=checked).read(
            owner.scope, source.object_ref))
        if (saved.get("schema") != "flora-provider-observed-attempt-v1"
                or saved["task_sha256"] != task["content_sha256"]
                or saved["authorization_sha256"] != authorization["content_sha256"]):
            raise ValueError("captured observation differs from exact bound task lineage")
        actual = TransportAttempt(saved["metadata"], base64.b64decode(saved["actual_request_base64"], validate=True),
            None if saved["actual_response_base64"] is None else base64.b64decode(saved["actual_response_base64"], validate=True),
            base64.b64decode(saved["proof_base64"], validate=True))
        usage = owner._verify_observation(body, snapshot, actual)
        check()
        return actual, usage

    def verified_usage(self) -> MeasuredUsage | None:
        """Only durable, signed, currently capture-authorized usage is returned."""
        return self._captured_observation()[1]

    def verify_response(self, response: ProviderResponse) -> None:
        """A successful answer cannot omit or change its captured denominator."""
        actual, usage = self._captured_observation()
        if not isinstance(response, ProviderResponse):
            raise ValueError("answer is not an actual provider response")
        self.owner._public.verify(response.proof, encoded(response.observation()))
        meta = actual.metadata
        if (meta["result"] != "success" or usage is None
                or response.configuration_sha256 != meta["configuration_sha256"]
                or response.request_sha256 != meta["request_sha256"]
                or response.authorization_marker != meta["authorization_marker"]
                or response.request_id != meta["request_id"] or response.returned_model_id != meta["returned_model_id"]
                or response.raw_response != actual.actual_response
                or response.input_tokens != usage.input_tokens or response.output_tokens != usage.output_tokens
                or response.cost_microunits != usage.cost_microunits or response.currency != usage.currency):
            raise ValueError("answer differs from the independently captured successful exchange")
        data, text = json.loads(actual.actual_response), []
        if not isinstance(data.get("output"), list):
            raise ValueError("captured successful exchange has no visible message output")
        for message in data["output"]:
            if not isinstance(message, dict):
                raise ValueError("captured successful exchange has malformed output")
            if message.get("type") == "reasoning":
                continue
            if (message.get("type") != "message" or message.get("role") != "assistant"
                    or message.get("status") != "completed" or not isinstance(message.get("content"), list)):
                raise ValueError("captured successful exchange contains non-message output")
            for fragment in message["content"]:
                if (not isinstance(fragment, dict) or fragment.get("type") != "output_text"
                        or not isinstance(fragment.get("text"), str)):
                    raise ValueError("captured successful exchange contains non-text output")
                text.append(fragment["text"])
        output = "".join(text).encode()
        if not output or response.output != output:
            raise ValueError("answer text differs from actual captured response text")
