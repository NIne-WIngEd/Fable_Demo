"""Hybrid source-memory comparator on selected Qdrant and canonical custody.

Original windows are source excerpts, never accepted native claims. Embeddings,
tokenization and frontier inference are externally supplied qualified components.
"""
from __future__ import annotations

import base64
from copy import copy
from dataclasses import dataclass
import math
import re
import uuid

from qdrant_client import QdrantClient, models

from cognitive_kernel.canonical import canonical_sha256, normalize_timestamp
from cognitive_kernel.contracts import ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent

from ..comparator import (
    BaselineConfiguration, EmbeddingBatch, ExactTokenCounter, LocalEmbeddingProvider,
    ProviderExchangeVerifier, ProviderRequest, ProviderResponse, ProviderWireCompiler, TokenCount,
    encoded, provider_payload, sha,
)
from ..comparison_run import (
    ArmResult, ArmStopped, ExecutionRequest, HistorySnapshot, MeasuredUsage,
    PreparationRequest, SourceMaterial, _context_bytes,
)
from .comparison_custody import SelectedRunEvidencePolicy, XTDBComparisonCustody, evaluation_purpose
from .context import ContextPlan, LocalContext, LocalContextItem
from .decision_outcome import RecordedEvent, record_decision
from .formation_policy import XTDBFormationPermissionPolicy


def _current_permission_rows(*, registry, permissions, source_ids, purpose):
    """Sample one exact purpose's real source/ancestor authority, not allows.

    Callers retain their actual canonical-source and permission predicates.
    They finish with this fence after every slow control callback, so a last
    callback cannot withdraw an earlier grant unnoticed.
    """
    from .phase_source_fence import OneGuardSelectedMetadata
    sample = OneGuardSelectedMetadata(registry=registry, permissions=permissions)
    pending, seen = list(source_ids), set()
    while pending:
        event_id = pending.pop()
        if event_id in seen:
            continue
        source, _ = sample.observe_source(event_id, purpose)
        seen.add(event_id)
        pending.extend(source.evidence.parent_refs)
    if not seen:
        raise PermissionError("provider permission fence has no source closure")
    return sample


def _require_final(custody, run_id, evidence, configuration, request, *, qualified=False):
    """Use actual durable run mode, including a committed orphan anchor."""
    if not isinstance(custody, XTDBComparisonCustody):
        raise TypeError("comparator requires actual selected final authority")
    authority = custody.require_final_authority(run_id=run_id, plan=request.plan,
        final_authority=getattr(evidence, "final_authority", None))
    if authority is None:
        return None
    if (authority.store.spec.comparator.digest() != configuration.digest()
            or sha(request.question) != authority.plan.question_sha256_by_case.get(request.case_id)):
        raise PermissionError("comparator changed its preregistered provider/question contract")
    task_id = authority.store.spec.provider_task_ids.get((request.case_id, request.phase))
    method = authority.authorize_evaluation if qualified else authority.require_evaluation
    method(plan=request.plan, case_id=request.case_id, phase=request.phase,
        arm="general_model_memory", invocation_id=task_id)
    return authority


@dataclass(frozen=True)
class SourceWindow:
    event_id: str
    event_sha256: str
    start_byte: int
    end_byte: int
    content_sha256: str

    def record(self) -> dict:
        if (isinstance(self.start_byte, bool) or not isinstance(self.start_byte, int) or self.start_byte < 0
                or isinstance(self.end_byte, bool) or not isinstance(self.end_byte, int)
                or self.end_byte <= self.start_byte):
            raise ValueError("invalid exact source-window bounds")
        return vars(self).copy()


@dataclass(frozen=True)
class OriginalWindowPlan(ContextPlan):
    windows: tuple[SourceWindow, ...] = ()
    history_sha256: str = ""
    comparator_configuration_sha256: str = ""

    def validate(self) -> None:
        from ..comparator import identifier
        from cognitive_kernel.canonical import require_sha256
        identifier(self.request_id, "request_id")
        identifier(self.purpose, "purpose")
        if (self.exact_claim_ids or self.state_routes or self.query_vector is not None
                or self.vector_limit or self.graph_source_event_ids or self.graph_limit or self.minimum_claims):
            raise ValueError("original source windows cannot masquerade as native claims or state")
        if not self.windows or len({canonical_sha256(w.record()) for w in self.windows}) != len(self.windows):
            raise ValueError("original window plan is empty or duplicated")
        require_sha256(self.history_sha256, "history_sha256")
        require_sha256(self.comparator_configuration_sha256, "comparator_configuration_sha256")


@dataclass(frozen=True)
class OriginalWindowContext(LocalContext):
    def receipt_record(self) -> dict:
        material = super().receipt_record()
        material.pop("receipt_sha256")
        if not isinstance(self.plan, OriginalWindowPlan):
            raise ValueError("comparator source context lacks its exact window plan")
        material["routes"]["original_source_windows"] = [w.record() for w in self.plan.windows]
        material["routes"]["history_sha256"] = self.plan.history_sha256
        material["routes"]["comparator_configuration_sha256"] = self.plan.comparator_configuration_sha256
        material["receipt_sha256"] = canonical_sha256(material)
        return material


def source_windows(history: HistorySnapshot, configuration: BaselineConfiguration) -> tuple[tuple[SourceWindow, bytes], ...]:
    history.digest()
    result = []
    config = configuration.memory
    for source in history.sources:
        text = source.plaintext.decode("utf-8")
        step = config.window_characters - config.window_overlap_characters
        for start in range(0, len(text), step):
            fragment = text[start:start + config.window_characters].encode()
            if not fragment:
                continue
            offset = len(text[:start].encode())
            result.append((SourceWindow(source.event.event_id, source.event.event_sha256,
                                       offset, offset + len(fragment), sha(fragment)), fragment))
            if len(result) > config.maximum_windows:
                raise ArmStopped("unavailable")
            if start + config.window_characters >= len(text):
                break
    if not result or len(result) > config.maximum_windows:
        raise ArmStopped("unavailable")
    return tuple(result)


def ancestors(history: HistorySnapshot, event_id: str) -> tuple[str, ...]:
    by_id = {source.event.event_id: source.event for source in history.sources}
    found, pending = set(), [event_id]
    while pending:
        current = pending.pop()
        if current not in by_id:
            raise ValueError("original source ancestor lies outside authorized phase history")
        if current in found:
            continue
        found.add(current)
        pending.extend(by_id[current].parent_event_ids)
    return tuple(source.event.event_id for source in history.sources if source.event.event_id in found)


def lexical_ranking(query: bytes, windows: tuple[tuple[SourceWindow, bytes], ...]) -> tuple[int, ...]:
    """BM25 over real local window terms; scores are accessibility, not truth."""
    tokens = lambda value: re.findall(r"\w+", value.decode("utf-8").casefold())
    documents = [tokens(value) for _, value in windows]
    terms = set(tokens(query))
    average = sum(map(len, documents)) / len(documents) or 1
    frequencies = {term: sum(term in document for document in documents) for term in terms}
    scores = []
    for index, document in enumerate(documents):
        score = 0.0
        for term in terms:
            frequency = document.count(term)
            if frequency:
                inverse = math.log(1 + (len(documents) - frequencies[term] + .5) / (frequencies[term] + .5))
                score += inverse * frequency * 2.2 / (frequency + 1.2 * (.25 + .75 * len(document) / average))
        scores.append((index, score))
    return tuple(index for index, _ in sorted(scores, key=lambda item: (-item[1], item[0])))


class QdrantOriginalMemory:
    def __init__(self, *, custody: XTDBComparisonCustody, run_id: str,
                 configuration: BaselineConfiguration, client: QdrantClient,
                 embeddings: LocalEmbeddingProvider, tokenizer: ExactTokenCounter,
                 wire_compiler: ProviderWireCompiler,
                 evidence: SelectedRunEvidencePolicy):
        if evidence.custody is not custody or evidence.run_id != run_id:
            raise ValueError("comparator retrieval has a different registered evidence policy")
        self.custody, self.run_id, self.configuration = custody, run_id, configuration
        self.client, self.embeddings, self.tokenizer, self.evidence = client, embeddings, tokenizer, evidence
        self.wire_compiler = wire_compiler
        configuration.record()

    def collection(self, request: PreparationRequest) -> str:
        # Include authority, frozen config, case/phase and actual history generation.
        return "floracmp_" + canonical_sha256([self.custody.scope_digest, self.run_id,
            request.case_id, request.phase, request.history.digest(), self.configuration.digest()])[:48]

    def _verify_embeddings(self, content: tuple[bytes, ...], batch: EmbeddingBatch) -> None:
        config = self.configuration.memory
        if (batch.input_sha256 != tuple(sha(value) for value in content)
                or batch.artifact_sha256 != config.embedding_artifact_sha256
                or batch.configuration_sha256 != config.embedding_configuration_sha256
                or len(batch.vectors) != len(content)
                or any(len(vector) != config.dimension or any(isinstance(value, bool)
                    or not isinstance(value, (int, float)) or not math.isfinite(value) for value in vector)
                    or not any(value != 0 for value in vector) for vector in batch.vectors)):
            raise ValueError("embeddings differ from actual input or frozen model/configuration")

    def _context(self, request: PreparationRequest, selected: tuple[int, ...], windows) -> OriginalWindowContext:
        route = tuple(windows[index][0] for index in selected)
        by_id = {source.event.event_id: source.event for source in request.history.sources}
        items = tuple(LocalContextItem("comparator_original_window", window.event_id,
            window.event_sha256, (window.event_id,), encoded({
                "source_event_id": window.event_id, "event_type": by_id[window.event_id].event_type,
                "occurred_at": by_id[window.event_id].occurred_at,
                "provenance_type": by_id[window.event_id].provenance.provenance_type,
                "parent_event_ids": list(by_id[window.event_id].parent_event_ids),
                "start_byte": window.start_byte, "end_byte": window.end_byte,
                "source_excerpt": windows[index][1].decode("utf-8")}))
            for index, window in zip(selected, route))
        plan = OriginalWindowPlan(request_id="comparator:" + canonical_sha256([
            request.case_id, request.phase, request.history.digest(), [w.record() for w in route]]),
            purpose=evaluation_purpose(self.run_id, request.case_id, request.phase), windows=route,
            history_sha256=request.history.digest(), comparator_configuration_sha256=self.configuration.digest())
        return OriginalWindowContext(plan, items,
            len({window.event_id for window in route}) >= self.configuration.memory.minimum_sources)

    async def prepare(self, request: PreparationRequest) -> OriginalWindowContext:
        config = self.configuration.memory
        def final_current():
            _require_final(self.custody, self.run_id, self.evidence, self.configuration, request)
            return True
        _require_final(self.custody, self.run_id, self.evidence, self.configuration, request, qualified=True)
        evidence = copy(self.evidence)
        evidence.custody = self.custody._authority_fenced_copy(final_current)
        def current():
            final_current()
            if not evidence.authorize_history(case_id=request.case_id, phase=request.phase, history=request.history):
                raise ArmStopped("refused")
            final_current()
        current()
        windows = source_windows(request.history, self.configuration)
        content = tuple(value for _, value in windows)
        batch = await self.embeddings.embed(content + (request.question,))
        self._verify_embeddings(content + (request.question,), batch)
        current()
        collection = self.collection(request)
        if not self.client.collection_exists(collection):
            current()
            self.client.create_collection(collection_name=collection, vectors_config={"text": models.VectorParams(
                size=config.dimension, distance=models.Distance.COSINE)})
        current()
        actual = self.client.get_collection(collection).config.params.vectors
        if not isinstance(actual, dict) or actual["text"].size != config.dimension or actual["text"].distance != models.Distance.COSINE:
            raise ValueError("comparator Qdrant collection has a different vector contract")
        point_ids = [str(uuid.uuid5(uuid.NAMESPACE_OID, collection + canonical_sha256(w.record()))) for w, _ in windows]
        current()
        self.client.upsert(collection_name=collection, wait=True, points=[models.PointStruct(
            id=point_ids[index], vector={"text": list(batch.vectors[index])}, payload={
                "source_window": window.record(), "history_sha256": request.history.digest(),
                "comparator_configuration_sha256": self.configuration.digest()})
            for index, (window, _) in enumerate(windows)])
        current()
        found = self.client.query_points(collection_name=collection, query=list(batch.vectors[-1]),
            using="text", with_payload=True, limit=min(len(windows), config.dense_candidates)).points
        by_point = {point: index for index, point in enumerate(point_ids)}
        dense = []
        for point in found:
            index = by_point.get(str(point.id))
            payload = point.payload or {}
            if (index is None or payload.get("source_window") != windows[index][0].record()
                    or payload.get("history_sha256") != request.history.digest()
                    or payload.get("comparator_configuration_sha256") != self.configuration.digest()):
                raise ValueError("Qdrant result differs from the exact authorized projection")
            dense.append(index)
        lexical = lexical_ranking(request.question, windows)
        # Independent exact/semantic/temporal routes are fused; no score grants truth.
        events = {source.event.event_id: source.event for source in request.history.sources}
        temporal = sorted(range(len(windows)), key=lambda i: (
            events[windows[i][0].event_id].occurred_at, i), reverse=True)
        corrections = [i for i in temporal if events[windows[i][0].event_id].event_type in {"correction", "outcome"}]
        score = {index: 0.0 for index in range(len(windows))}
        for ranking in (lexical, dense, corrections):
            for rank, index in enumerate(ranking, 1):
                score[index] += 1 / (config.rank_fusion_constant + rank)
        ordered = sorted(score, key=lambda index: (-score[index], index))
        best_for_source = {}
        for index in ordered:
            best_for_source.setdefault(windows[index][0].event_id, index)
        selected = ()
        for index in ordered:
            bundle = tuple(best_for_source[event_id] for event_id in ancestors(request.history, windows[index][0].event_id))
            proposed = tuple(dict.fromkeys(selected + bundle + (index,)))
            context = self._context(request, proposed, windows)
            payload = provider_payload(self.configuration, question=request.question, context=context,
                                       response_token_budget=request.plan.protocol.response_token_budget,
                                       wire_compiler=self.wire_compiler)
            count = self.tokenizer.count(payload)
            count.verify(payload, config)
            if (count.tokens <= request.plan.context_token_budget
                    and len(_context_bytes(context)) <= request.plan.context_byte_budget):
                selected = proposed
        if not selected:
            raise ArmStopped("unavailable")
        context = self._context(request, selected, windows)
        current()
        return context


class SelectedComparatorDisclosure:
    def __init__(self, *, custody: XTDBComparisonCustody, run_id: str,
                 configuration: BaselineConfiguration, permissions: XTDBFormationPermissionPolicy,
                 wire_compiler: ProviderWireCompiler,
                 evidence: SelectedRunEvidencePolicy):
        if (evidence.custody is not custody or evidence.run_id != run_id
                or permissions.scope != custody.scope or permissions.authority_namespace_id != custody.authority_namespace_id):
            raise ValueError("comparator disclosure crosses registered host/authority")
        self.custody, self.run_id, self.configuration = custody, run_id, configuration
        self.permissions, self.evidence = permissions, evidence
        self.wire_compiler = wire_compiler

    def authorize(self, *, request: ExecutionRequest, provider_request: ProviderRequest) -> str:
        _require_final(self.custody, self.run_id, self.evidence, self.configuration, request, qualified=True)
        def final_current():
            _require_final(self.custody, self.run_id, self.evidence, self.configuration, request)
            return True
        if (provider_request.configuration != self.configuration.provider
                or provider_request.payload != provider_payload(self.configuration, question=request.question,
                    context=request.context, response_token_budget=request.plan.protocol.response_token_budget,
                    wire_compiler=self.wire_compiler)):
            raise PermissionError("provider request differs from the exact authorized input")
        reader = self.custody._authority_fenced_copy(final_current)
        history = reader.recover_history(run_id=self.run_id, case_id=request.case_id,
                                               phase=request.phase, permissions=self.permissions)
        if (history.digest() != request.authorized_history_sha256 or history.event_ids != request.authorized_event_ids
                or not self.evidence.authorize_history(case_id=request.case_id, phase=request.phase, history=history)):
            raise PermissionError("comparator source history changed or lost local permission")
        verify_window_context(request.context, history, self.configuration)
        purpose = "comparison_external:" + self.configuration.provider.provider_id
        question = self.custody.metadata(self.run_id, "question:" + request.case_id)
        if question is None or question.record["content_sha256"] != sha(request.question):
            raise PermissionError("provider question differs from frozen custody")
        source_ids = tuple(dict.fromkeys((question.event_id,) + request.context.source_event_ids))
        permission_rows = _current_permission_rows(registry=self.custody.registry,
            permissions=self.permissions, source_ids=source_ids, purpose=purpose)
        markers = []
        for event_id in source_ids:
            source = self.custody.registry.lookup(event_id)
            action = self.permissions.current_action(event_id, purpose)
            if source is None or action is None or not self.permissions.permits(source, purpose):
                raise PermissionError("external disclosure lacks its own current host authorization")
            markers.append((event_id, source.registration_sha256, action.action_sha256))
        for event_id, registration, action_hash in markers:
            source = self.custody.registry.lookup(event_id)
            action = self.permissions.current_action(event_id, purpose)
            if (source is None or action is None or source.registration_sha256 != registration
                    or action.action_sha256 != action_hash or not self.permissions.permits(source, purpose)):
                raise PermissionError("external disclosure authority changed during verification")
        _require_final(self.custody, self.run_id, self.evidence, self.configuration, request, qualified=True)
        permission_rows.verify_final_current_rows()
        return canonical_sha256({"provider_configuration_sha256": provider_request.configuration.digest(),
            "payload_sha256": sha(provider_request.payload), "purpose": purpose, "sources": markers})


def verify_window_context(context: LocalContext, history: HistorySnapshot,
                          configuration: BaselineConfiguration) -> None:
    if not isinstance(context, OriginalWindowContext) or not isinstance(context.plan, OriginalWindowPlan):
        raise ValueError("comparator does not have a raw-source-window context")
    context.plan.validate()
    if (context.plan.history_sha256 != history.digest()
            or context.plan.comparator_configuration_sha256 != configuration.digest()
            or len(context.items) != len(context.plan.windows)):
        raise ValueError("comparator context changed its frozen original history or configuration")
    by_id = {source.event.event_id: source for source in history.sources}
    allowed_windows = {window for window, _ in source_windows(history, configuration)}
    for window, item in zip(context.plan.windows, context.items):
        window.record()
        source = by_id.get(window.event_id)
        if source is None or source.event.event_sha256 != window.event_sha256:
            raise ValueError("comparator window does not have exact original provenance")
        if window.end_byte > len(source.plaintext):
            raise ValueError("comparator window exceeds actual original byte bounds")
        if window not in allowed_windows:
            raise ValueError("comparator window is outside the frozen configured source windows")
        fragment = source.plaintext[window.start_byte:window.end_byte]
        expected = encoded({"source_event_id": window.event_id, "event_type": source.event.event_type,
            "occurred_at": source.event.occurred_at, "provenance_type": source.event.provenance.provenance_type,
            "parent_event_ids": list(source.event.parent_event_ids), "start_byte": window.start_byte,
            "end_byte": window.end_byte, "source_excerpt": fragment.decode("utf-8")})
        if (sha(fragment) != window.content_sha256 or item.kind != "comparator_original_window"
                or item.record_id != window.event_id or item.version_id != window.event_sha256
                or item.source_event_ids != (window.event_id,) or item.content != expected
                or item.claim_value is not None or item.approval_event_id is not None
                or item.control_event_ids):
            raise ValueError("comparator excerpt changed the actual original bytes")
    if not all(set(ancestors(history, source)).issubset(context.source_event_ids) for source in context.source_event_ids):
        raise ValueError("comparator selected evidence lacks correction/outcome ancestor closure")


class SelectedComparatorRecorder:
    def __init__(self, *, custody: XTDBComparisonCustody, run_id: str,
                 configuration: BaselineConfiguration, disclosure: SelectedComparatorDisclosure,
                 exchange_verifier: ProviderExchangeVerifier, clock):
        self.custody, self.run_id, self.configuration, self.disclosure, self.clock = custody, run_id, configuration, disclosure, clock
        self.exchange_verifier = exchange_verifier

    def record(self, *, request: ExecutionRequest, provider_request: ProviderRequest,
               response: ProviderResponse, token_count: TokenCount,
               authorization_marker: str) -> ArmResult:
        if (request.binding.model_artifact_sha256 != self.configuration.provider.digest()
                or request.binding.lineage_sha256 != self.configuration.digest()
                or request.binding.producer_component != self.configuration.producer_component
                or authorization_marker != response.authorization_marker):
            raise ValueError("comparator recorder lacks its frozen producer/exchange binding")
        token_count.verify(provider_request.payload, self.configuration.memory)
        evidence = self.disclosure.evidence
        _require_final(self.custody, self.run_id, evidence, self.configuration, request, qualified=True)
        self.exchange_verifier.verify(request=provider_request, response=response)
        self.disclosure.authorize(request=request, provider_request=provider_request)
        def final_current():
            _require_final(self.custody, self.run_id, evidence, self.configuration, request)
            return True
        reader = self.custody._authority_fenced_copy(final_current)
        history = reader.recover_history(run_id=self.run_id, case_id=request.case_id,
            phase=request.phase, permissions=self.disclosure.permissions)
        question = self.custody.metadata(self.run_id, "question:" + request.case_id)
        if question is None or question.record["content_sha256"] != sha(request.question):
            raise ValueError("comparator exchange lost its exact frozen question custody")
        def current():
            final_current()
            purpose = "comparison_external:" + self.configuration.provider.provider_id
            source_ids = (question.event_id, *request.context.source_event_ids)
            permission_rows = _current_permission_rows(registry=self.custody.registry,
                permissions=self.disclosure.permissions, source_ids=source_ids, purpose=purpose)
            if not evidence.authorize_history_metadata(case_id=request.case_id, phase=request.phase, history=history):
                raise PermissionError("comparator result lost current original source authority")
            for event_id in source_ids:
                if not self.disclosure.permissions.permits(self.custody.registry.lookup(event_id), purpose):
                    raise PermissionError("comparator result lost current external source authority")
            final_current()
            permission_rows.verify_final_current_rows()
            return True
        selected = self.custody._authority_fenced_copy(current)
        _require_final(self.custody, self.run_id, evidence, self.configuration, request, qualified=True)
        material = encoded(request.context.receipt_record())
        raw = selected.objects.put(material)
        event = ExperienceEvent.create(event_type="context_delivery", scope=request.scope,
            occurred_at=normalize_timestamp(self.clock(), "occurred_at"), content_digest=raw.plaintext_sha256,
            provenance=ProvenanceReference.create(provenance_type="derived_inference",
                source_reference_ids=request.context.source_event_ids,
                derivation_activity_id="comparator-context:" + sha(material),
                responsible_component=self.configuration.producer_component),
            retention_class="ordinary_experience", storage_tier="raw_buffer",
            parent_event_ids=request.context.source_event_ids, payload_reference=raw.object_id)
        selected.log.append(event, expected_revision=len(selected.log.replay()) - 1)
        delivery = RecordedEvent(event, raw)
        selected.register_recorded(delivery)
        selected.register_context(run_id=self.run_id, context=request.context, delivery=delivery, occurred_at=self.clock())
        decision = record_decision(log=selected.log, objects=selected.objects, verdict=response.output,
            consumed_event_ids=(event.event_id,) + request.context.source_event_ids,
            references=selected.registry, model_artifact_sha256=request.binding.model_artifact_sha256,
            occurred_at=self.clock(), expected_revision=len(selected.log.replay()) - 1,
            producer_component=self.configuration.producer_component, source_authorizer=lambda _: current())
        selected.register_recorded(decision)
        exchange = {"schema": "flora-comparator-provider-exchange-v1", "dispatch": provider_request.record(),
            "observation": response.observation(), "proof_base64": base64.b64encode(response.proof).decode(),
            "actual_request_base64": base64.b64encode(provider_request.payload).decode(),
            "actual_response_base64": base64.b64encode(response.raw_response).decode(),
            "token_count": vars(token_count), "authorization_marker": authorization_marker,
            "decision_event_id": decision.event.event_id}
        selected._put(run_id=self.run_id, artifact_id="provider_exchange:" + decision.event.event_id,
            kind="comparator_provider_exchange", content=encoded(exchange),
            parents=(decision.event.event_id, question.event_id),
            metadata={"decision_event_id": decision.event.event_id,
                "provider_configuration_sha256": self.configuration.provider.digest(),
                "request_sha256": sha(provider_request.payload), "response_sha256": sha(response.raw_response)},
            occurred_at=self.clock())
        self.disclosure.authorize(request=request, provider_request=provider_request)
        _require_final(self.custody, self.run_id, evidence, self.configuration, request, qualified=True)
        current()
        return ArmResult(response.output, delivery, decision,
            MeasuredUsage(self.configuration.provider.feature_engine_id, response.input_tokens,
                response.input_tokens, response.output_tokens, 1, response.cost_microunits, response.currency))
