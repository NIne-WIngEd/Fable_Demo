"""Runnable selected-fabric bridge for externally qualified personal models.

No model, selector, judgment, ACFP schema or IDP schema is invented here. The
producer supplies the exact contract codec, inference adapter, independent
qualification verifier and execution verifier. Missing roles fail closed.
Explicit experiment routes are frozen nonlearned inputs, not relevance proof.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from copy import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol
from cryptography.exceptions import InvalidSignature, InvalidTag

from cognitive_kernel.adjudication_contracts import AdjudicationRecord, ClaimConflictRecord
from cognitive_kernel.canonical import canonical_json_bytes, canonical_sha256, normalize_timestamp, require_identifier
from cognitive_kernel.claim_contracts import CurrentClaimProjection
from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from cognitive_kernel.formation_context_planner import FormationPlanningRequest, select_all_registered
from cognitive_kernel.formation_contracts import MemoryProposalBundle, validate_formation_binding
from cognitive_kernel.formation_retrieval import FormationCandidatePlane, FormationRoute
from cognitive_kernel.projection_contracts import ProjectionVersion

from .artifact_registry import ArtifactQualificationVerifier, RuntimeWiringManifest, XTDBModelArtifactRegistry
from .claims import XTDBClaimAuthority, _dml_placeholder, _record_json, _rows
from .context import ContextPlan, ContextUsePolicy, LocalContext, assemble_context, record_context_delivery
from .decision_outcome import RecordedEvent, record_decision
from .experience import KurrentExperienceLog
from .formation_admission import (
    FormationAdmissionReceipt, FormationAdmissionVerifier, FormationClaimAdapter, XTDBFormationClaimAdmission,
)
from .formation_candidates import (
    FormationValueResolver, RecordedFormationCandidate, XTDBFormationProposalCandidates, _raw_record, _read_raw,
)
from .formation_context import PreparedSelectedFormation, prepare_selected_formation, record_selected_formation_delivery
from .formation_policy import XTDBFormationPermissionPolicy
from .formation_registry import XTDBFormationSourceRegistry
from .governed_development import XTDBGovernedPersonalDevelopment
from .object_store import EncryptedObjectPlane, RawObjectReference
from .personal_state import StateApprovalVerifier, VerifiedStateCandidate
from .personal_artifact_custody import DurablePersonalReferences


def _hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class _AuthorizedRuntimeBackend:
    def __init__(self, backend, revalidate):
        self.backend, self.revalidate = backend, revalidate

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "backend"), name)

    def get_object(self, namespace, object_id):
        self.revalidate()
        sealed = self.backend.get_object(namespace, object_id)
        self.revalidate()
        return sealed


class _AuthorizedRuntimeReads:
    """Check live authority around every private ciphertext/plaintext read."""
    def __init__(self, objects, revalidate):
        self.objects, self.revalidate = copy(objects), revalidate
        self.objects.backend = _AuthorizedRuntimeBackend(objects.backend, revalidate)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "objects"), name)

    def get(self, raw):
        self.revalidate()
        material = EncryptedObjectPlane.get(self.objects, raw)
        self.revalidate()
        return material

    def recover_reference(self, **kwargs):
        self.revalidate()
        reference = EncryptedObjectPlane.recover_reference(self.objects, **kwargs)
        self.revalidate()
        return reference


def _binding_record(binding: RuntimeWiringManifest) -> dict[str, object]:
    return {**vars(binding), "scope": binding.scope.metadata_record()}


@dataclass(frozen=True)
class RuntimeInvocation:
    scope: ProductHostScope
    authority_namespace_id: str
    invocation_id: str
    operation: str
    artifact: RuntimeWiringManifest
    delivery_event_id: str
    input_event_id: str
    input_sha256: str
    payload: bytes = field(repr=False)

    def binding_record(self) -> dict[str, object]:
        return {"schema": "flora-qualified-runtime-invocation-v1",
                "scope": self.scope.metadata_record(), "authority_namespace_id": self.authority_namespace_id,
                "invocation_id": self.invocation_id, "operation": self.operation,
                "artifact": _binding_record(self.artifact), "delivery_event_id": self.delivery_event_id,
                "input_event_id": self.input_event_id, "input_sha256": self.input_sha256}


@dataclass(frozen=True)
class RuntimeResult:
    invocation_id: str
    artifact: RuntimeWiringManifest
    input_sha256: str
    output: bytes = field(repr=False)
    execution_proof: bytes = field(repr=False)


class ExternalRuntimeAdapter(Protocol):
    adapter_id: str
    execution_location: str

    def invoke(self, invocation: RuntimeInvocation) -> RuntimeResult: ...


class RuntimeExecutionVerifier(Protocol):
    """Actual producer proof, including loaded artifact and local execution.

    A signature from an arbitrary adapter is insufficient. The trusted verifier
    must inspect the producer's execution receipt against this exact invocation,
    result, artifact qualification and local execution policy.
    """
    def verified_execution(self, *, adapter: ExternalRuntimeAdapter,
                           invocation: RuntimeInvocation, result: RuntimeResult) -> bool: ...


class QualifiedProducerCodec(Protocol):
    input_contract_id: str
    input_contract_sha256: str
    output_contract_id: str
    output_contract_sha256: str

    def formation_input(self, prepared: PreparedSelectedFormation) -> bytes: ...
    def decode_formation(self, output: bytes) -> MemoryProposalBundle: ...
    def encode_formation_output(self, bundle: MemoryProposalBundle) -> bytes: ...
    def judgment_frame(self, *, context: LocalContext, task: bytes) -> bytes: ...
    def validate_identity_decision(self, *, output: bytes, context: LocalContext) -> None: ...


@dataclass(frozen=True)
class RuntimeRoleBinding:
    checkpoint_path: str | Path
    codec: QualifiedProducerCodec
    qualification_verifier: ArtifactQualificationVerifier
    adapter: ExternalRuntimeAdapter
    execution_verifier: RuntimeExecutionVerifier


@dataclass(frozen=True)
class RoleReadiness:
    role: str
    ready: bool
    missing: tuple[str, ...]


class RuntimeBlocked(RuntimeError):
    def __init__(self, missing_roles: tuple[RoleReadiness, ...]):
        self.missing_roles = missing_roles
        super().__init__("runtime blocked: " + "; ".join(
            item.role + "=" + ",".join(item.missing) for item in missing_roles))


@dataclass(frozen=True)
class ExecutedModelOutput:
    invocation: RuntimeInvocation
    result: RuntimeResult = field(repr=False)
    input_record: RecordedEvent
    output_record: RecordedEvent


@dataclass(frozen=True)
class FormationRun:
    prepared: PreparedSelectedFormation = field(repr=False)
    delivery: RecordedEvent
    execution: ExecutedModelOutput = field(repr=False)
    candidate: RecordedFormationCandidate
    bundle: MemoryProposalBundle


@dataclass(frozen=True)
class JudgmentRun:
    context: LocalContext = field(repr=False)
    delivery: RecordedEvent
    execution: ExecutedModelOutput = field(repr=False)
    decision: RecordedEvent


@dataclass(frozen=True)
class SuppliedClaimAdmission:
    proposal_id: str
    adapter: FormationClaimAdapter = field(repr=False)
    adjudication: AdjudicationRecord
    verifier: FormationAdmissionVerifier = field(repr=False)
    previous: CurrentClaimProjection | None = None
    conflict: ClaimConflictRecord | None = None


@dataclass(frozen=True)
class SuppliedStateActivation:
    """Already externally produced state, never inferred by this driver."""
    version: ProjectionVersion
    content: RawObjectReference
    approval_event_id: str
    expected_previous_version_id: str | None
    expected_active_version_id: str | None


class _LinkedReferences:
    def __init__(self, durable: Any, extra: Mapping[str, RawObjectReference]):
        self.durable, self.extra = durable, extra

    def get(self, key: str, default: Any = None) -> Any:
        return self.extra.get(key) or self.durable.get(key, default)


class _RuntimePrivateCustody:
    """Selected XTDB metadata for private execution receipts, not authority.

    Kurrent append and this registration are separate durable boundaries.
    Recovery never replaces a missing canonical event or repairs permissions.
    """
    records = "flora_qualified_runtime_steps"
    raw_refs = "flora_qualified_runtime_raw_references"

    def __init__(self, runtime: "FloRAExperimentRuntime"):
        self.runtime = runtime
        self.connection = runtime.claims.connection
        self.scope_digest = canonical_sha256([runtime.scope.storage_scope(), runtime.authority_namespace_id])

    def _key(self, kind: str, identifier: str) -> str:
        return canonical_sha256([self.scope_digest, kind, identifier])

    def _seal(self, material: dict[str, object]) -> dict[str, object]:
        record = {"scope": self.runtime.scope.metadata_record(),
                  "authority_namespace_id": self.runtime.authority_namespace_id, **material}
        return {**record, "record_sha256": canonical_sha256(record)}

    def _fetch(self, table: str, key: str) -> dict[str, object] | None:
        rows = _rows(self.connection.execute(
            f"SELECT * FROM {table} FOR VALID_TIME ALL WHERE _id = %s", (key,)))
        if len(rows) > 1:
            raise ValueError("runtime private custody returned ambiguous immutable records")
        if not rows:
            return None
        row, record = rows[0], json.loads(str(rows[0]["record_json"]))
        if (row["_id"] != key or row["scope_digest"] != self.scope_digest
                or record["scope"] != self.runtime.scope.metadata_record()
                or record["authority_namespace_id"] != self.runtime.authority_namespace_id
                or row["record_sha256"] != record["record_sha256"]
                or canonical_sha256({name: value for name, value in record.items()
                                     if name != "record_sha256"}) != record["record_sha256"]):
            raise ValueError("runtime private custody crossed scope or changed metadata")
        return record

    def _insert(self, table: str, key: str, record: dict[str, object]) -> None:
        values = {"_id": key, "scope_digest": self.scope_digest,
                  "record_sha256": record["record_sha256"], "record_json": _record_json(record)}
        self.connection.execute(f"ASSERT NOT EXISTS (SELECT 1 FROM {table} FOR VALID_TIME ALL WHERE _id = %s::text)",
                                (key,))
        self.connection.execute(f"INSERT INTO {table} ({', '.join(values)}) VALUES ("
            + ", ".join(_dml_placeholder(value) for value in values.values()) + ")", tuple(values.values()))

    def register(self, recorded: RecordedEvent, invocation_id: str, stage: str, *,
                 revalidate: Callable[[], None] | None = None) -> None:
        if revalidate is not None:
            revalidate()
        event = recorded.event
        if (event.scope != self.runtime.scope or recorded.raw.scope != self.runtime.scope
                or event not in self.runtime.log.replay() or event.payload_reference != recorded.raw.object_id
                or event.content_digest != recorded.raw.plaintext_sha256):
            raise ValueError("runtime custody lacks its exact canonical event/raw binding")
        objects = self.runtime.objects if revalidate is None else _AuthorizedRuntimeReads(self.runtime.objects, revalidate)
        raw = _raw_record(recorded.raw, objects)
        raw_record = self._seal({"schema": "flora-runtime-private-reference-v1", "raw": raw})
        step_record = self._seal({"schema": "flora-runtime-private-step-v1", "invocation_id": invocation_id,
            "stage": stage, "event_id": event.event_id, "event_sha256": event.event_sha256,
            "raw": raw})
        pairs = ((self.raw_refs, self._key("raw", recorded.raw.object_id), raw_record),
                 (self.records, self._key(stage, invocation_id), step_record))
        pending = []
        for table, key, record in pairs:
            prior = self._fetch(table, key)
            if prior is not None and prior != record:
                raise ValueError("runtime invocation/stage custody is immutable")
            if prior is None:
                pending.append((table, key, record))
        if pending:
            with self.connection.transaction():
                for table, key, record in pending:
                    if revalidate is not None:
                        revalidate()
                    self._insert(table, key, record)

    def raw_reference(self, object_id: str) -> RawObjectReference | None:
        record = self._fetch(self.raw_refs, self._key("raw", object_id))
        if record is None:
            return None
        raw = record["raw"]
        if record["schema"] != "flora-runtime-private-reference-v1" or raw["object_id"] != object_id:
            raise ValueError("runtime private reference differs from lookup")
        return RawObjectReference(self.runtime.scope, object_id, raw["plaintext_sha256"], raw["size"])

    def read(self, invocation_id: str, stage: str, *, event_id: str | None = None,
             parent_event_id: str | None = None, allow_replay: bool = True,
             revalidate: Callable[[], None] | None = None) -> tuple[RecordedEvent, bytes]:
        objects = self.runtime.objects if revalidate is None else _AuthorizedRuntimeReads(self.runtime.objects, revalidate)
        record = self._fetch(self.records, self._key(stage, invocation_id))
        if record is None:
            if not allow_replay:
                raise ValueError("read-only runtime recovery requires registered private custody")
            # Replay recovery after append succeeded but the XTDB index failed.
            # The caller must check live authority BEFORE calling this method
            # and authenticate the complete typed step before registering it.
            events = [event for event in self.runtime.log.replay()
                      if event.event_type == stage and (event.event_id == event_id if event_id is not None
                      else parent_event_id in event.parent_event_ids if parent_event_id is not None
                      else event.provenance.derivation_activity_id == invocation_id)]
            if len(events) != 1 or events[0].scope != self.runtime.scope or events[0].payload_reference is None:
                raise ValueError("runtime private step is absent or ambiguous in canonical replay")
            event = events[0]
            raw = objects.recover_reference(
                object_id=event.payload_reference, expected_plaintext_sha256=event.content_digest)
            return RecordedEvent(event, raw), objects.get(raw)
        if (record["schema"] != "flora-runtime-private-step-v1"
                or record["invocation_id"] != invocation_id or record["stage"] != stage):
            raise ValueError("runtime private step is absent or changed")
        event = next((event for event in self.runtime.log.replay() if event.event_id == record["event_id"]), None)
        if (event is None or event.scope != self.runtime.scope or event.event_sha256 != record["event_sha256"]
                or event.payload_reference != record["raw"]["object_id"]
                or event.content_digest != record["raw"]["plaintext_sha256"]):
            raise ValueError("runtime private step lacks its canonical event")
        if not allow_replay:
            reference = self._fetch(self.raw_refs, self._key("raw", record["raw"]["object_id"]))
            expected = self._seal({"schema": "flora-runtime-private-reference-v1", "raw": record["raw"]})
            if reference != expected:
                raise ValueError("read-only runtime recovery requires exact registered raw reference")
        raw, material = _read_raw(record["raw"], objects)
        return RecordedEvent(event, raw), material


class _RuntimeReferences:
    def __init__(self, durable: DurablePersonalReferences, runtime_custody: _RuntimePrivateCustody):
        self.durable, self.runtime_custody = durable, runtime_custody

    def get(self, key: str, default: Any = None) -> Any:
        original, runtime = self.durable.get(key), self.runtime_custody.raw_reference(key)
        if original is not None and runtime is not None and original != runtime:
            raise ValueError("runtime and personal private custody disagree")
        return original or runtime or default


class FloRAExperimentRuntime:
    """Run real provided adapters through existing selected authority services.

    ``references`` should be DurablePersonalReferences; ``context_policy`` must
    resolve current original/parent permissions. Neither is an in-memory source
    authority. The same live governed state instance is used for every stage.
    """
    def __init__(self, *, artifacts: XTDBModelArtifactRegistry,
                 bindings: Mapping[str, RuntimeRoleBinding], claims: XTDBClaimAuthority,
                 sources: XTDBFormationSourceRegistry, source_policy: XTDBFormationPermissionPolicy,
                 candidates: XTDBFormationProposalCandidates, admission: XTDBFormationClaimAdmission,
                 state: XTDBGovernedPersonalDevelopment, log: KurrentExperienceLog,
                 objects: EncryptedObjectPlane, references: Any,
                 context_policy: ContextUsePolicy, state_approval_verifier: StateApprovalVerifier,
                 clock: Callable[[], str], vector: Any = None, graph: Any = None):
        if not isinstance(state, XTDBGovernedPersonalDevelopment):
            raise TypeError("live runtime requires XTDBGovernedPersonalDevelopment")
        from .judgment_context import RegisteredJudgmentContextPolicy
        if not isinstance(context_policy, RegisteredJudgmentContextPolicy):
            raise TypeError("live runtime requires registered current judgment permissions")
        if not isinstance(references, DurablePersonalReferences):
            raise TypeError("live runtime requires durable original/private reference custody")
        planes = (artifacts, claims, sources, source_policy, candidates, admission, state)
        if (any(plane.scope != claims.scope or plane.authority_namespace_id != claims.authority_namespace_id
                for plane in planes) or not claims.scope == log.scope == objects.scope
                or state.registry is not sources or state.policy is not source_policy
                or admission.authority is not claims or admission.candidates is not candidates):
            raise ValueError("runtime crosses selected scope or authority services")
        if (references.originals is not sources or references.custody.scope != claims.scope
                or references.custody.authority_namespace_id != claims.authority_namespace_id
                or context_policy.claims is not claims or context_policy.state is not state
                or context_policy.registry is not sources or context_policy.permissions is not source_policy
                or context_policy.log is not log):
            raise ValueError("runtime context/custody is bound to different authority services")
        if not callable(clock) or not callable(getattr(references, "get", None)):
            raise TypeError("runtime needs an explicit clock and durable reference resolver")
        self.scope, self.authority_namespace_id = claims.scope, claims.authority_namespace_id
        self.artifacts, self.bindings = artifacts, dict(bindings)
        self.claims, self.sources, self.source_policy = claims, sources, source_policy
        self.candidates, self.admission, self.state = candidates, admission, state
        self.log, self.objects, self.original_references = log, objects, references
        self.private = _RuntimePrivateCustody(self)
        self.references = _RuntimeReferences(references, self.private)
        self.context_policy, self.state_approval_verifier = context_policy, state_approval_verifier
        self.clock, self.vector, self.graph = clock, vector, graph

    def _resolve(self, role: str, *, authority_guard: Callable[[], None] | None = None
                 ) -> tuple[RuntimeRoleBinding, RuntimeWiringManifest]:
        if authority_guard is not None:
            authority_guard()
        binding = self.bindings.get(role)
        missing = []
        if binding is None:
            raise RuntimeBlocked((RoleReadiness(role, False, ("role_binding",)),))
        for label, service, method in (
            ("producer_codec", binding.codec, "formation_input" if role == "memory_formation" else "judgment_frame"),
            ("qualified_inference_adapter", binding.adapter, "invoke"),
            ("independent_qualification_verifier", binding.qualification_verifier, "verify"),
            ("independent_execution_verifier", binding.execution_verifier, "verified_execution"),
        ):
            if not callable(getattr(service, method, None)):
                missing.append(label)
        extra_codec_methods = (("decode_formation", "encode_formation_output") if role == "memory_formation"
                               else ("validate_identity_decision",))
        if any(not callable(getattr(binding.codec, name, None)) for name in extra_codec_methods):
            missing.append("producer_output_codec")
        if missing:
            raise RuntimeBlocked((RoleReadiness(role, False, tuple(missing)),))
        codec = binding.codec
        artifacts = self.artifacts
        if authority_guard is not None:
            artifacts = copy(artifacts)
            artifacts.objects = _AuthorizedRuntimeReads(artifacts.objects, authority_guard)
        resolved = artifacts.resolve_current_for_runtime(role=role,
            checkpoint_path=binding.checkpoint_path,
            expected_input_contract_id=codec.input_contract_id,
            expected_input_contract_sha256=codec.input_contract_sha256,
            expected_output_contract_id=codec.output_contract_id,
            expected_output_contract_sha256=codec.output_contract_sha256,
            verifier=binding.qualification_verifier)
        if resolved.scope != self.scope or resolved.role != role:
            raise ValueError("qualified runtime artifact crosses host or role")
        if binding.adapter.execution_location != "host_local":
            raise ValueError("personal model execution must be host local")
        require_identifier(binding.adapter.adapter_id, "adapter_id")
        if authority_guard is not None:
            authority_guard()
        return binding, resolved

    def readiness(self) -> tuple[RoleReadiness, ...]:
        result = []
        for role in ("memory_formation", "personality_judgment"):
            try:
                self._resolve(role)
            except RuntimeBlocked as blocked:
                result.extend(blocked.missing_roles)
            except (ValueError, TypeError, AttributeError, OSError, InvalidSignature, InvalidTag) as blocked:
                result.append(RoleReadiness(role, False, ("qualified_current_artifact: "
                    + (str(blocked) or type(blocked).__name__),)))
            else:
                result.append(RoleReadiness(role, True, ()))
        return tuple(result)

    def _require_all(self) -> None:
        missing = tuple(role for role in self.readiness() if not role.ready)
        if missing:
            raise RuntimeBlocked(missing)

    def _revision(self) -> int:
        return len(self.log.replay()) - 1

    def _append(self, *, payload: bytes, event_type: str, parents: tuple[str, ...],
                invocation_id: str, model_digest: str,
                revalidate: Callable[[], None] | None = None) -> RecordedEvent:
        if revalidate is not None:
            revalidate()
        raw = self.objects.put(payload)
        event = ExperienceEvent.create(event_type=event_type, scope=self.scope,
            occurred_at=normalize_timestamp(self.clock(), "occurred_at"), content_digest=raw.plaintext_sha256,
            provenance=ProvenanceReference.create(provenance_type="derived_inference",
                source_reference_ids=parents, derivation_activity_id=invocation_id,
                responsible_component="flora-qualified-runtime", model_id=model_digest),
            retention_class="ordinary_experience", storage_tier="raw_buffer",
            parent_event_ids=parents, payload_reference=raw.object_id)
        revision = self._revision()
        if revalidate is not None:
            revalidate()
        self.log.append(event, expected_revision=revision)
        recorded = RecordedEvent(event, raw)
        if revalidate is not None:
            revalidate()
        self.private.register(recorded, invocation_id, event_type, revalidate=revalidate)
        return recorded

    def _execute(self, *, role: str, invocation_id: str, operation: str,
                 delivery: RecordedEvent, payload: bytes, revalidate: Callable[[], None],
                 private_guard: Callable[[], None] | None = None) -> ExecutedModelOutput:
        require_identifier(invocation_id, "invocation_id")
        if not isinstance(payload, bytes) or not payload:
            raise ValueError("qualified producer codec returned no exact input bytes")
        guard = private_guard or revalidate
        objects = _AuthorizedRuntimeReads(self.objects, guard)
        binding, artifact = self._resolve(role, authority_guard=guard)
        revalidate()
        replayed = self.log.replay()
        if (delivery.event not in replayed or delivery.event.scope != self.scope
                or delivery.raw.scope != self.scope or delivery.event.payload_reference != delivery.raw.object_id
                or objects.get(delivery.raw) == b"" or delivery.event.content_digest != delivery.raw.plaintext_sha256):
            raise ValueError("runtime input lacks its actual scoped delivery")
        input_material = {"schema": "flora-qualified-model-input-v1", "scope": self.scope.metadata_record(),
            "authority_namespace_id": self.authority_namespace_id, "invocation_id": invocation_id,
            "operation": operation, "artifact": _binding_record(artifact),
            "delivery_event_id": delivery.event.event_id, "input_sha256": _hash(payload),
            "input_base64": base64.b64encode(payload).decode()}
        input_record = self._append(payload=canonical_json_bytes(input_material),
            event_type="qualified_model_input", parents=(delivery.event.event_id,),
            invocation_id=invocation_id, model_digest=artifact.checkpoint_sha256, revalidate=guard)
        try:
            revalidate()
            if self._resolve(role, authority_guard=guard)[1] != artifact:
                raise ValueError("current model artifact changed before inference")
            invocation = RuntimeInvocation(self.scope, self.authority_namespace_id, invocation_id,
                operation, artifact, delivery.event.event_id, input_record.event.event_id, _hash(payload), payload)
            result = binding.adapter.invoke(invocation)
            revalidate()
            if (not isinstance(result, RuntimeResult) or result.invocation_id != invocation_id
                    or result.artifact != artifact or result.input_sha256 != invocation.input_sha256
                    or not isinstance(result.output, bytes) or not result.output
                    or not isinstance(result.execution_proof, bytes) or not result.execution_proof):
                raise ValueError("runtime output differs from exact artifact/input invocation")
            if binding.execution_verifier.verified_execution(
                    adapter=binding.adapter, invocation=invocation, result=result) is not True:
                raise ValueError("runtime execution is not independently verified")
            revalidate()
            if self._resolve(role, authority_guard=guard)[1] != artifact:
                raise ValueError("current model artifact changed during inference")
            output_material = {"schema": "flora-qualified-model-output-v1", "invocation": invocation.binding_record(),
                "adapter_id": binding.adapter.adapter_id, "execution_location": binding.adapter.execution_location,
                "output_sha256": _hash(result.output), "output_base64": base64.b64encode(result.output).decode(),
                "execution_proof_base64": base64.b64encode(result.execution_proof).decode()}
            output_record = self._append(payload=canonical_json_bytes(output_material),
                event_type="qualified_model_output", parents=(input_record.event.event_id,),
                invocation_id=invocation_id, model_digest=artifact.checkpoint_sha256, revalidate=guard)
            revalidate()
            return ExecutedModelOutput(invocation, result, input_record, output_record)
        except Exception as failure:
            # Every delivered invocation remains an attempt, including bad
            # proof, timeout, revoked context and changed artifact failures.
            # This metadata receipt does not reopen denied personal content.
            try:
                self._append(payload=canonical_json_bytes({
                    "schema": "flora-qualified-model-attempt-failure-v1",
                    "scope": self.scope.metadata_record(),
                    "authority_namespace_id": self.authority_namespace_id,
                    "invocation_id": invocation_id, "operation": operation,
                    "artifact": _binding_record(artifact),
                    "input_event_id": input_record.event.event_id,
                    "failure_class": type(failure).__name__,
                }), event_type="qualified_model_attempt_failure",
                    parents=(input_record.event.event_id,), invocation_id=invocation_id,
                    model_digest=artifact.checkpoint_sha256)
            except Exception as recording_failure:
                failure.add_note("Runtime failure receipt unavailable: " + type(recording_failure).__name__)
            raise

    def _recover_execution(self, *, role: str, invocation_id: str, current_payload: bytes,
                           revalidate: Callable[[], None], reconcile: bool = True,
                           private_guard: Callable[[], None] | None = None) -> ExecutedModelOutput:
        # Live source/state checks and artifact qualification precede opening
        # the private input/output. A stored receipt is not current permission.
        revalidate()
        guard = private_guard or revalidate
        binding, artifact = self._resolve(role, authority_guard=guard)
        input_record, input_bytes = self.private.read(invocation_id, "qualified_model_input",
            allow_replay=reconcile, revalidate=guard)
        revalidate()
        output_record, output_bytes = self.private.read(invocation_id, "qualified_model_output",
            allow_replay=reconcile, revalidate=guard)
        revalidate()
        input_material, output_material = json.loads(input_bytes), json.loads(output_bytes)
        if (input_material["artifact"] != _binding_record(artifact)
                or input_material["input_base64"] != base64.b64encode(current_payload).decode()
                or input_material["input_sha256"] != _hash(current_payload)):
            raise ValueError("recovered execution differs from current artifact/context")
        invocation = RuntimeInvocation(self.scope, self.authority_namespace_id, invocation_id,
            input_material["operation"], artifact, input_material["delivery_event_id"], input_record.event.event_id,
            input_material["input_sha256"], current_payload)
        result = RuntimeResult(invocation_id, artifact, invocation.input_sha256,
            base64.b64decode(output_material["output_base64"], validate=True),
            base64.b64decode(output_material["execution_proof_base64"], validate=True))
        execution = ExecutedModelOutput(invocation, result, input_record, output_record)
        self._assert_execution(execution, role, revalidate=guard)
        revalidate()
        if reconcile:
            self.private.register(input_record, invocation_id, "qualified_model_input", revalidate=guard)
            revalidate()
            self.private.register(output_record, invocation_id, "qualified_model_output", revalidate=guard)
        revalidate()
        return execution

    def _assert_execution(self, execution: ExecutedModelOutput, role: str, *,
                          revalidate: Callable[[], None] | None = None) -> None:
        objects = self.objects if revalidate is None else _AuthorizedRuntimeReads(self.objects, revalidate)
        binding, artifact = self._resolve(role, authority_guard=revalidate)
        invocation, result = execution.invocation, execution.result
        replayed = self.log.replay()
        if (invocation.scope != self.scope or invocation.authority_namespace_id != self.authority_namespace_id
                or invocation.artifact != artifact or result.artifact != artifact
                or invocation.invocation_id != result.invocation_id
                or _hash(invocation.payload) != invocation.input_sha256
                or result.input_sha256 != invocation.input_sha256
                or invocation.input_event_id != execution.input_record.event.event_id):
            raise ValueError("execution no longer binds current artifact and input")
        expected_input = {"schema": "flora-qualified-model-input-v1", "scope": self.scope.metadata_record(),
            "authority_namespace_id": self.authority_namespace_id, "invocation_id": invocation.invocation_id,
            "operation": invocation.operation, "artifact": _binding_record(artifact),
            "delivery_event_id": invocation.delivery_event_id, "input_sha256": invocation.input_sha256,
            "input_base64": base64.b64encode(invocation.payload).decode()}
        expected_output = {"schema": "flora-qualified-model-output-v1", "invocation": invocation.binding_record(),
            "adapter_id": binding.adapter.adapter_id, "execution_location": binding.adapter.execution_location,
            "output_sha256": _hash(result.output), "output_base64": base64.b64encode(result.output).decode(),
            "execution_proof_base64": base64.b64encode(result.execution_proof).decode()}
        for recorded, event_type, parent, expected in (
            (execution.input_record, "qualified_model_input", invocation.delivery_event_id, expected_input),
            (execution.output_record, "qualified_model_output", invocation.input_event_id, expected_output),
        ):
            if (recorded.event not in replayed or recorded.event.scope != self.scope
                    or recorded.raw.scope != self.scope or recorded.event.event_type != event_type
                    or recorded.event.parent_event_ids != (parent,)
                    or recorded.event.payload_reference != recorded.raw.object_id
                    or recorded.event.content_digest != recorded.raw.plaintext_sha256
                    or recorded.event.provenance.provenance_type != "derived_inference"
                    or recorded.event.provenance.responsible_component != "flora-qualified-runtime"
                    or recorded.event.provenance.model_id != artifact.checkpoint_sha256
                    or recorded.event.provenance.derivation_activity_id != invocation.invocation_id
                    or objects.get(recorded.raw) != canonical_json_bytes(expected)):
                raise ValueError("execution lacks its exact durable input/output receipts")
        ids = [event.event_id for event in replayed]
        if (invocation.delivery_event_id not in ids
                or not ids.index(invocation.delivery_event_id) < ids.index(invocation.input_event_id)
                < ids.index(execution.output_record.event.event_id)):
            raise ValueError("execution delivery/input/output order changed")
        if binding.execution_verifier.verified_execution(adapter=binding.adapter,
                invocation=invocation, result=result) is not True or self._resolve(role, authority_guard=revalidate)[1] != artifact:
            raise ValueError("runtime execution is not independently verified")

    def form_experience(self, *, request: FormationPlanningRequest, invocation_id: str,
                        value_resolver: FormationValueResolver, routes: tuple[FormationRoute, ...] = (),
                        providers: Mapping[str, FormationCandidatePlane] | None = None) -> FormationRun:
        role = {}
        def qualify(metadata_guard):
            role["resolved"] = self._resolve("memory_formation", authority_guard=metadata_guard)
        prepared = prepare_selected_formation(request=request, registry=self.sources, objects=self.objects,
            permits=self.source_policy.permits, routes=routes, providers=providers,
            selector=select_all_registered,
            before_private_assembly=qualify)  # Exact experiment policy, never learned selection.
        binding, _ = role["resolved"]
        objects = _AuthorizedRuntimeReads(self.objects, prepared.metadata_current)
        delivery = record_selected_formation_delivery(prepared=prepared, log=self.log, objects=objects,
            occurred_at=self.clock(), expected_revision=self._revision(), request_id=invocation_id)
        self.private.register(delivery, invocation_id, "formation_context_delivery",
                              revalidate=prepared.metadata_current)
        execution = self._execute(role="memory_formation", invocation_id=invocation_id, operation="memory_formation",
            delivery=delivery, payload=binding.codec.formation_input(prepared), revalidate=prepared.revalidate,
            private_guard=prepared.metadata_current)
        bundle = binding.codec.decode_formation(execution.result.output)
        validate_formation_binding(prepared.assembled.packet, bundle)
        if (binding.codec.encode_formation_output(bundle) != execution.result.output
                or bundle.model_artifact_digest != execution.invocation.artifact.checkpoint_sha256
                or bundle.inference_run_id != invocation_id):
            raise ValueError("decoded formation output differs from qualified execution")
        candidate = self.candidates.record(prepared=prepared, delivery=delivery, bundle=bundle,
            log=self.log, objects=objects,
            expected_model_artifact_sha256=execution.invocation.artifact.checkpoint_sha256,
            occurred_at=self.clock(), expected_revision=self._revision(), value_resolver=value_resolver)
        prepared.revalidate()
        return FormationRun(prepared, delivery, execution, candidate, bundle)

    def recover_formation(self, *, request: FormationPlanningRequest, bundle_id: str,
                          invocation_id: str, routes: tuple[FormationRoute, ...] = (),
                          providers: Mapping[str, FormationCandidatePlane] | None = None,
                          reconcile: bool = True,
                          authority_guard: Callable[[], None] | None = None) -> FormationRun:
        if not isinstance(reconcile, bool):
            raise TypeError("reconcile must be an explicit boolean")
        objects = self.objects if authority_guard is None else _AuthorizedRuntimeReads(self.objects, authority_guard)
        role = {}
        def qualify(metadata_guard):
            role["resolved"] = self._resolve("memory_formation", authority_guard=metadata_guard)
        def permits(source, purpose):
            if authority_guard is not None:
                authority_guard()
            return self.source_policy.permits(source, purpose)
        prepared = prepare_selected_formation(request=request, registry=self.sources, objects=objects,
            permits=permits, routes=routes, providers=providers, selector=select_all_registered,
            before_private_assembly=qualify)
        binding, _ = role["resolved"]
        def metadata_current():
            if authority_guard is not None:
                authority_guard()
            prepared.metadata_current()
        objects = _AuthorizedRuntimeReads(objects, metadata_current)
        def revalidate():
            if authority_guard is not None:
                authority_guard()
            prepared.revalidate()
        recovered = self.candidates.read_candidate(bundle_id, log=self.log, objects=objects,
                                                   source_store=prepared.store)
        if recovered.packet != prepared.assembled.packet:
            raise ValueError("recovered formation differs from current registered context")
        execution = self._recover_execution(role="memory_formation", invocation_id=invocation_id,
            current_payload=binding.codec.formation_input(prepared), revalidate=revalidate,
            reconcile=reconcile, private_guard=metadata_current)
        delivery, delivery_bytes = self.private.read(invocation_id, "formation_context_delivery",
                                                    event_id=execution.invocation.delivery_event_id,
                                                    allow_replay=reconcile, revalidate=revalidate)
        if (execution.invocation.delivery_event_id != delivery.event.event_id
                or delivery_bytes != json.dumps(prepared.receipt_record(), sort_keys=True,
                    separators=(",", ":"), allow_nan=False).encode()
                or binding.codec.encode_formation_output(recovered.bundle) != execution.result.output
                or recovered.bundle.inference_run_id != invocation_id):
            raise ValueError("recovered formation lacks exact qualified output/delivery")
        revalidate()
        if reconcile:
            self.private.register(delivery, invocation_id, "formation_context_delivery", revalidate=revalidate)
        return FormationRun(prepared, delivery, execution, recovered.recorded, recovered.bundle)

    def admit_proposal(self, formation: FormationRun, supplied: SuppliedClaimAdmission) -> FormationAdmissionReceipt:
        # Exact semantic acceptance remains independent of model execution.
        formation.prepared.revalidate()
        self._assert_execution(formation.execution, "memory_formation", revalidate=formation.prepared.revalidate)
        if (formation.execution.invocation.operation != "memory_formation"
                or formation.execution.invocation.delivery_event_id != formation.delivery.event.event_id
                or self.bindings["memory_formation"].codec.encode_formation_output(formation.bundle)
                != formation.execution.result.output):
            raise ValueError("admission formation differs from qualified output")
        bound = self.admission.prepare(bundle_id=formation.bundle.bundle_id, proposal_id=supplied.proposal_id,
            adapter=supplied.adapter, log=self.log, objects=self.objects, source_store=formation.prepared.store)
        return self.admission.admit(bound, adjudication=supplied.adjudication, verifier=supplied.verifier,
            log=self.log, objects=self.objects, source_store=formation.prepared.store,
            expected_previous=supplied.previous, conflict=supplied.conflict)

    def activate_personal_state(self, supplied: SuppliedStateActivation) -> VerifiedStateCandidate:
        inputs = dict(claims=self.claims, log=self.log, objects=self.objects, references=self.references)
        self.state.put_candidate(supplied.version, content=supplied.content,
            expected_previous_version_id=supplied.expected_previous_version_id, **inputs)
        return self.state.activate(subject_type=supplied.version.subject_type, subject_id=supplied.version.subject_id,
            projection_id=supplied.version.projection_id, approval_event_id=supplied.approval_event_id,
            expected_active_version_id=supplied.expected_active_version_id,
            verifier=self.state_approval_verifier, **inputs)

    def _guarded_state_verifier(self, objects):
        from .owner_authorization import Ed25519OwnerActionVerifier
        from .personal_artifact_custody import DurableOwnerProofLookup
        verifier = self.state_approval_verifier
        if isinstance(verifier, Ed25519OwnerActionVerifier) and isinstance(verifier.proofs, DurableOwnerProofLookup):
            verifier = copy(verifier)
            verifier.proofs = copy(verifier.proofs)
            verifier.proofs.objects = objects
        return verifier

    def _context(self, plan: ContextPlan, *, authority_guard: Callable[[], None] | None = None) -> LocalContext:
        objects = self.objects if authority_guard is None else _AuthorizedRuntimeReads(self.objects, authority_guard)
        if authority_guard is not None:
            authority_guard()
        return assemble_context(plan=plan, claims=self.claims, state=self.state, log=self.log,
            objects=objects, references=self.references, policy=self.context_policy,
            approval_verifier=self._guarded_state_verifier(objects), vector=self.vector, graph=self.graph)

    def _prepare_current_context(self, plan: ContextPlan, *,
                                 authority_guard: Callable[[], None] | None = None,
                                 before_private_assembly: Callable | None = None):
        from .context_guard import prepare_current_context
        def approval_verifier_factory(metadata_guard):
            return self._guarded_state_verifier(_AuthorizedRuntimeReads(self.objects, metadata_guard))
        return prepare_current_context(plan=plan, claims=self.claims, state=self.state, log=self.log,
            objects=self.objects, references=self.references, policy=self.context_policy,
            approval_verifier_factory=approval_verifier_factory, authority_guard=authority_guard,
            before_private_assembly=before_private_assembly)

    def judge(self, *, plan: ContextPlan, task: bytes, invocation_id: str) -> JudgmentRun:
        if not isinstance(task, bytes) or not task:
            raise ValueError("native judgment requires an exact task input")
        role = {}
        def qualify(metadata_guard):
            role["resolved"] = self._resolve("personality_judgment", authority_guard=metadata_guard)
        prepared = self._prepare_current_context(plan, before_private_assembly=qualify)
        binding, _ = role["resolved"]
        context = prepared.context
        if not context.sufficient_by_declared_count:
            raise ValueError("explicit experiment context minimum is not met")
        revalidate = prepared.revalidate
        objects = _AuthorizedRuntimeReads(self.objects, prepared.metadata_current)
        delivery = record_context_delivery(context=context, claims=self.claims, state=self.state,
            log=self.log, objects=objects, references=self.references, policy=self.context_policy,
            approval_verifier=self._guarded_state_verifier(objects), vector=self.vector, graph=self.graph,
            occurred_at=self.clock(), expected_revision=self._revision(), authority_guard=prepared.metadata_current)
        prepared.metadata_current()
        self.private.register(delivery, invocation_id, "context_delivery", revalidate=prepared.metadata_current)
        execution = self._execute(role="personality_judgment", invocation_id=invocation_id, operation="native_judgment",
            delivery=delivery, payload=binding.codec.judgment_frame(context=context, task=task), revalidate=revalidate,
            private_guard=prepared.metadata_current)
        binding.codec.validate_identity_decision(output=execution.result.output, context=context)
        revalidate()
        linked = _LinkedReferences(self.references, {
            delivery.raw.object_id: delivery.raw, execution.input_record.raw.object_id: execution.input_record.raw,
            execution.output_record.raw.object_id: execution.output_record.raw})
        consumed = tuple(dict.fromkeys((execution.output_record.event.event_id, delivery.event.event_id,
                                       *context.source_event_ids)))
        def authorize_consumed(_event_id):
            prepared.metadata_current()
            return True
        decision = record_decision(log=self.log, objects=objects, verdict=execution.result.output,
            consumed_event_ids=consumed, references=linked,
            model_artifact_sha256=execution.invocation.artifact.checkpoint_sha256,
            occurred_at=self.clock(), expected_revision=self._revision(), producer_component=binding.adapter.adapter_id,
            source_authorizer=authorize_consumed)
        prepared.metadata_current()
        self.private.register(decision, invocation_id, "decision", revalidate=prepared.metadata_current)
        revalidate()
        return JudgmentRun(context, delivery, execution, decision)

    def recover_judgment(self, *, plan: ContextPlan, task: bytes, invocation_id: str,
                         reconcile: bool = True,
                         authority_guard: Callable[[], None] | None = None) -> JudgmentRun:
        if not isinstance(reconcile, bool):
            raise TypeError("reconcile must be an explicit boolean")
        role = {}
        def qualify(metadata_guard):
            role["resolved"] = self._resolve("personality_judgment", authority_guard=metadata_guard)
        prepared = self._prepare_current_context(plan, authority_guard=authority_guard,
                                                 before_private_assembly=qualify)
        binding, _ = role["resolved"]
        context = prepared.context
        if not context.sufficient_by_declared_count:
            raise ValueError("current context minimum is not met for judgment recovery")
        revalidate = prepared.revalidate
        execution = self._recover_execution(role="personality_judgment", invocation_id=invocation_id,
            current_payload=binding.codec.judgment_frame(context=context, task=task), revalidate=revalidate,
            reconcile=reconcile, private_guard=prepared.metadata_current)
        binding.codec.validate_identity_decision(output=execution.result.output, context=context)
        delivery, delivery_bytes = self.private.read(invocation_id, "context_delivery",
                                                    event_id=execution.invocation.delivery_event_id,
                                                    allow_replay=reconcile, revalidate=prepared.metadata_current)
        revalidate()
        decision, material = self.private.read(invocation_id, "decision",
                                             parent_event_id=execution.output_record.event.event_id,
                                             allow_replay=reconcile, revalidate=prepared.metadata_current)
        record = json.loads(material)
        expected_consumed = list(dict.fromkeys((execution.output_record.event.event_id, delivery.event.event_id,
                                               *context.source_event_ids)))
        if (execution.invocation.delivery_event_id != delivery.event.event_id
                or delivery_bytes != json.dumps(context.receipt_record(), sort_keys=True,
                    separators=(",", ":"), allow_nan=False).encode()
                or execution.invocation.operation != "native_judgment"
                or execution.output_record.event.event_id not in decision.event.parent_event_ids
                or set(record) != {"schema", "verdict_base64", "consumed_event_ids", "model_artifact_sha256"}
                or record["schema"] != "flora-decision-v1" or record["consumed_event_ids"] != expected_consumed
                or set(decision.event.parent_event_ids) != set(expected_consumed)
                or record["verdict_base64"] != base64.b64encode(execution.result.output).decode()
                or record["model_artifact_sha256"] != execution.invocation.artifact.checkpoint_sha256):
            raise ValueError("recovered decision lacks its exact native execution lineage")
        revalidate()
        if reconcile:
            self.private.register(delivery, invocation_id, "context_delivery", revalidate=prepared.metadata_current)
            revalidate()
            self.private.register(decision, invocation_id, "decision", revalidate=prepared.metadata_current)
        revalidate()
        return JudgmentRun(context, delivery, execution, decision)

    def run_cycle(self, *, request: FormationPlanningRequest, formation_invocation_id: str,
                  value_resolver: FormationValueResolver,
                  supplied_admissions: Callable[[FormationRun], tuple[SuppliedClaimAdmission, ...]],
                  supplied_states: Callable[[tuple[FormationAdmissionReceipt, ...]], tuple[SuppliedStateActivation, ...]],
                  plan: ContextPlan, task: bytes, judgment_invocation_id: str,
                  routes: tuple[FormationRoute, ...] = (), providers: Mapping[str, FormationCandidatePlane] | None = None
                  ) -> tuple[FormationRun, tuple[FormationAdmissionReceipt, ...], tuple[VerifiedStateCandidate, ...], JudgmentRun]:
        """Execute stages; supplied governance services confer no learned ability.

        No stage manufactures an approval, state proposal, ranking or verdict.
        Appends/transactions are separate durable boundaries, not one global
        atomic transaction. A failure does not undo already accepted authority.
        """
        self._require_all()
        formation = self.form_experience(request=request, invocation_id=formation_invocation_id,
            value_resolver=value_resolver, routes=routes, providers=providers)
        admitted = tuple(self.admit_proposal(formation, item) for item in supplied_admissions(formation))
        activated = tuple(self.activate_personal_state(item) for item in supplied_states(admitted))
        judgment = self.judge(plan=plan, task=task, invocation_id=judgment_invocation_id)
        return formation, admitted, activated, judgment
