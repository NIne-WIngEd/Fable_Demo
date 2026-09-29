"""Contract fixtures for execution fairness; no model or selected-backend result."""

import asyncio
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import random
import tempfile
import unittest

from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from flora.comparison_run import (
    ArmBinding, ArmResult, ArmStopped, HistorySnapshot, MeasuredUsage,
    PairedRunPlan, SourceMaterial, create_blind_review, run_paired, run_summary,
    validate_run,
)
from flora.evaluation_protocol import ARMS, EvaluationCase, EvaluationProtocol
from flora.selected.context import ContextPlan, LocalContext, LocalContextItem
from flora.selected.decision_outcome import RecordedEvent, record_decision
from flora.selected.object_store import EncryptedObjectPlane, LocalObjectBackend


def digest(content):
    return hashlib.sha256(content).hexdigest()


class FixtureLog:
    """Only an event-contract fixture, never a replacement backend in FloRA."""

    def __init__(self, scope, events):
        self.scope = scope
        self.events = list(events)

    def replay(self):
        return list(self.events)

    def append(self, event, *, expected_revision):
        if expected_revision != len(self.events) - 1:
            raise ValueError("stale fixture revision")
        self.events.append(event)


class FixtureEvidencePolicy:
    def __init__(self, histories):
        self.histories = histories
        self.recorded = {}
        self.deny_history = False
        self.deny_review = False
        self.deny_question = False

    def authorize_history(self, *, case_id, phase, history):
        return not self.deny_history and history == self.histories[(case_id, phase)]

    def verify_recorded(self, recorded):
        plane, log = self.recorded.get(recorded.event.event_id, (None, None))
        return bool(plane and recorded.event in log.replay()
                    and digest(plane.get(recorded.raw)) == recorded.event.content_digest)

    def allow_review(self, **kwargs):
        return not self.deny_review

    def allow_question(self, **kwargs):
        return not self.deny_question


class FixtureAdapter:
    def __init__(self, policy, root, *, stop=None, delay=0,
                 output_tokens=3, feature_calls=1):
        self.policy, self.root = policy, root
        self.stop, self.delay = stop, delay
        self.output_tokens, self.feature_calls = output_tokens, feature_calls
        self.preparations = []
        self.requests = []

    async def prepare(self, request):
        self.preparations.append(request)
        source = request.history.sources[-1]
        return LocalContext(
            ContextPlan(request_id=f"fixture-{request.phase}", purpose="fixture-review",
                        exact_claim_ids=("fixture-claim",)),
            (LocalContextItem("claim", "fixture-claim", "fixture-version",
                              (source.event.event_id,), source.plaintext),), True)

    async def execute(self, request):
        self.requests.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.stop:
            if self.stop == "private_error":
                raise RuntimeError("private personal content must not enter receipts")
            raise ArmStopped(self.stop)
        scope = request.scope
        plane = EncryptedObjectPlane(scope=scope, key=b"x" * 32,
                                     backend=LocalObjectBackend(self.root))
        history = self.policy.histories[(request.case_id, request.phase)]
        refs = {}
        for source in history.sources:
            raw = plane.put(source.plaintext)
            # Fictional sources already identify these immutable raw objects.
            assert raw.object_id == source.event.payload_reference
            refs[raw.object_id] = raw
        log = FixtureLog(scope, [source.event for source in history.sources])
        material = json.dumps(request.context.receipt_record(), sort_keys=True,
                              separators=(",", ":"), allow_nan=False).encode()
        raw = plane.put(material)
        event = ExperienceEvent.create(
            event_type="context_delivery", scope=scope, occurred_at="2026-09-29T12:00:00Z",
            content_digest=raw.plaintext_sha256,
            provenance=ProvenanceReference.create(
                provenance_type="derived_inference",
                source_reference_ids=request.context.source_event_ids,
                derivation_activity_id="fixture-delivery",
                responsible_component="fixture-context"),
            retention_class="ordinary_experience", storage_tier="raw_buffer",
            parent_event_ids=request.context.source_event_ids,
            payload_reference=raw.object_id)
        log.append(event, expected_revision=len(log.replay()) - 1)
        delivery = RecordedEvent(event, raw)
        refs[raw.object_id] = raw
        # Different real artifacts are recorded without putting identity in prose.
        output = b"A neutral fictional recommendation."
        decision = record_decision(
            log=log, objects=plane, verdict=output,
            consumed_event_ids=(event.event_id,) + request.context.source_event_ids,
            references=refs, model_artifact_sha256=request.binding.model_artifact_sha256,
            occurred_at="2026-09-29T12:00:01Z",
            expected_revision=len(log.replay()) - 1,
            producer_component=request.binding.producer_component)
        for recorded in (delivery, decision):
            self.policy.recorded[recorded.event.event_id] = (plane, log)
        return ArmResult(output, delivery, decision, MeasuredUsage(
            request.plan.protocol.feature_engine_id, 4, 8, self.output_tokens,
            self.feature_calls))


class PairedComparisonContractTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scope = ProductHostScope.create(product_id="friday", host_instance_id="fixture-host",
                                             schema_version="1.0.0", encryption_domain="fixture-key")
        plane = EncryptedObjectPlane(scope=self.scope, key=b"x" * 32,
                                     backend=LocalObjectBackend(self.root))
        sources = []
        for i, plaintext in enumerate((b"A fictional original preference.",
                                       b"A fictional correction.")):
            raw = plane.put(plaintext)
            event = ExperienceEvent.create(
                event_type="observation" if i == 0 else "correction", scope=self.scope,
                occurred_at=f"2026-09-{27+i}T10:00:00Z", content_digest=raw.plaintext_sha256,
                provenance=ProvenanceReference.create(
                    provenance_type="generated_reconstruction",
                    source_reference_ids=(f"fixture-source-{i}",),
                    derivation_activity_id="fixture-history",
                    responsible_component="contract-fixture"),
                retention_class="ordinary_experience", storage_tier="raw_buffer",
                payload_reference=raw.object_id)
            sources.append(SourceMaterial(event, plaintext))
        self.histories = {("fixture-case", "before"): HistorySnapshot(self.scope, tuple(sources[:1])),
                          ("fixture-case", "after"): HistorySnapshot(self.scope, tuple(sources))}
        case = EvaluationCase("fixture-case", "fixture-host", "relevant_correction", "heldout",
                              self.histories[("fixture-case", "before")].digest(),
                              self.histories[("fixture-case", "after")].digest(), "a" * 64,
                              sources[-1].event.event_id)
        protocol = EvaluationProtocol("fixture-protocol", "b" * 64, "2026-09-29T00:00:00Z",
                                      "fixture-feature-engine", 16, 5000, (case,),
                                      "c" * 64, "d" * 64, "e" * 64, "f" * 64,
                                      ("fixture-transfer-host",))
        bindings = {arm: ArmBinding(f"fixture-producer-{i}", str(i+1) * 64,
                                   str(i+4) * 64, f"fixture-mechanism-{i}")
                    for i, arm in enumerate(sorted(ARMS))}
        self.questions = {"fixture-case": b"What should this fictional person do?"}
        self.plan = PairedRunPlan(protocol, bindings, 16, 10000, 2,
                                  {"fixture-case": digest(self.questions["fixture-case"])})
        self.policy = FixtureEvidencePolicy(self.histories)
        self.adapters = {arm: FixtureAdapter(self.policy, self.root) for arm in ARMS}

    async def run_fixture(self, **overrides):
        args = dict(plan=self.plan, histories=self.histories, questions=self.questions,
                    adapters=self.adapters, evidence_policy=self.policy)
        args.update(overrides)
        return await run_paired(**args)

    async def test_actual_input_identity_and_same_evidence_ablation(self):
        run = await self.run_fixture()
        self.assertEqual(len(run.attempts), 6)
        self.assertTrue(all(a.status == "success" for a in run.attempts))
        self.assertEqual(self.adapters["same_evidence_ablation"].preparations, [])
        for phase in ("before", "after"):
            attempts = [a for a in run.attempts if a.phase == phase]
            self.assertEqual(len({a.common_input_sha256 for a in attempts}), 1)
            full = next(a for a in attempts if a.arm == "flora_full")
            ablation = next(a for a in attempts if a.arm == "same_evidence_ablation")
            self.assertEqual(full.context_sha256, ablation.context_sha256)
        self.assertEqual(run_summary(run)["behavioral_assessment"], "not_collected")

    async def test_tampered_or_unauthorized_original_never_reaches_adapter(self):
        self.policy.deny_history = True
        with self.assertRaisesRegex(PermissionError, "unauthorized"):
            await self.run_fixture()
        self.assertTrue(all(not adapter.preparations for adapter in self.adapters.values()))
        self.policy.deny_history = False
        wrong = dict(self.histories)
        snapshot = wrong[("fixture-case", "before")]
        wrong[("fixture-case", "before")] = replace(snapshot, sources=(
            replace(snapshot.sources[0], plaintext=b"changed source"),))
        with self.assertRaises(ValueError):
            await self.run_fixture(histories=wrong)

    async def test_failures_and_observed_budget_excess_remain_in_denominator(self):
        self.adapters["general_model_memory"].stop = "private_error"
        self.adapters["flora_full"].output_tokens = 17
        run = await self.run_fixture()
        self.assertEqual(len(run.attempts), 6)
        self.assertEqual(sum(a.status == "failed" for a in run.attempts), 2)
        self.assertEqual(sum(a.status == "budget_exceeded" for a in run.attempts), 2)
        self.assertNotIn("private personal content", json.dumps([a.receipt() for a in run.attempts]))
        summary = run_summary(run)
        self.assertEqual(sum(g["attempts"] for g in summary["groups"].values()), 6)
        self.assertEqual(sum(g["unavailable_cost_attempts"] for g in summary["groups"].values()), 6)
        self.assertTrue(all(not g["known_costs"] for g in summary["groups"].values()))

    async def test_timeout_refusal_and_missing_adapter_are_explicit(self):
        self.adapters["flora_full"].delay = 0.1
        self.adapters["general_model_memory"].stop = "refused"
        plan = replace(self.plan, protocol=replace(self.plan.protocol, wall_time_budget_ms=20))
        adapters = {key: adapter for key, adapter in self.adapters.items()
                    if key != "same_evidence_ablation"}
        run = await self.run_fixture(plan=plan, adapters=adapters)
        self.assertEqual({a.status for a in run.attempts}, {"timeout", "refused", "unavailable"})
        self.assertEqual(len(run.attempts), 6)

    async def test_blind_pack_separates_identity_and_requires_review_permission(self):
        run = await self.run_fixture()
        pack, key = create_blind_review(run, policy=self.policy, rng=random.Random(3))
        self.assertEqual(len(pack["pairs"]), 4)
        serialized = json.dumps(pack)
        for identity in ARMS | {"fixture-case", "fixture-host", "before", "after"}:
            self.assertNotIn(identity, serialized)
        self.assertNotIn("plan_sha256", serialized)
        self.assertEqual(set(key["pairs"]), {pair["pair_id"] for pair in pack["pairs"]})
        self.policy.deny_review = True
        with self.assertRaises(PermissionError):
            create_blind_review(run, policy=self.policy)

    async def test_unverified_or_wrong_actual_verdict_does_not_count_as_success(self):
        original = self.adapters["general_model_memory"].execute

        async def substituted(request):
            result = await original(request)
            return replace(result, output=b"Different unrecorded output.")

        self.adapters["general_model_memory"].execute = substituted
        run = await self.run_fixture()
        self.assertEqual(sum(a.status == "invalid_result" for a in run.attempts), 2)

    async def test_reports_reject_omitted_failures_and_changed_questions(self):
        self.adapters["general_model_memory"].stop = "unavailable"
        run = await self.run_fixture()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            run_summary(replace(run, attempts=tuple(a for a in run.attempts
                                                    if a.status == "success")))
        with self.assertRaisesRegex(ValueError, "question"):
            validate_run(replace(run, questions={"fixture-case": b"A substituted question?"}))

    async def test_known_cost_is_reported_without_filling_missing_costs(self):
        original = self.adapters["general_model_memory"].execute

        async def measured(request):
            result = await original(request)
            return replace(result, usage=replace(result.usage, cost_microunits=125,
                                                 currency="USD"))

        self.adapters["general_model_memory"].execute = measured
        run = await self.run_fixture()
        group = run_summary(run)["groups"]["fixture-host/general_model_memory"]
        self.assertEqual(group["known_costs"], {"USD": 250})
        self.assertEqual(group["unavailable_cost_attempts"], 0)
        self.assertEqual(group["feature_calls"], 2)
        self.assertEqual(run_summary(run)["groups"]["fixture-host/flora_full"]
                         ["unavailable_cost_attempts"], 2)

    async def test_question_is_frozen_before_execution_and_review_is_authorized(self):
        with self.assertRaisesRegex(ValueError, "frozen question"):
            await self.run_fixture(questions={"fixture-case": b"A substituted task."})
        self.assertTrue(all(not adapter.preparations for adapter in self.adapters.values()))
        run = await self.run_fixture()
        self.policy.deny_question = True
        with self.assertRaisesRegex(PermissionError, "review question"):
            create_blind_review(run, policy=self.policy)

    async def test_revocation_during_inference_prevents_acceptance_and_later_arms(self):
        original = self.adapters["flora_full"].execute

        async def revoked(request):
            result = await original(request)
            self.policy.deny_history = True
            return result

        self.adapters["flora_full"].execute = revoked
        run = await self.run_fixture()
        self.assertEqual(len(run.attempts), 6)
        self.assertTrue(all(a.status == "refused" for a in run.attempts))
        self.assertEqual(self.adapters["general_model_memory"].preparations, [])

    async def test_malformed_context_retains_failures_and_insufficiency_abstains(self):
        async def malformed(request):
            return "not a LocalContext"

        self.adapters["flora_full"].prepare = malformed
        run = await self.run_fixture()
        self.assertEqual(len(run.attempts), 6)
        self.assertEqual(sum(a.status == "invalid_result" for a in run.attempts), 2)
        self.assertTrue(all(a.context_sha256 is None for a in run.attempts
                            if a.arm == "flora_full"))
        self.adapters["flora_full"] = FixtureAdapter(self.policy, self.root)
        original = self.adapters["flora_full"].prepare

        async def insufficient(request):
            return replace(await original(request), sufficient_by_declared_count=False)

        self.adapters["flora_full"].prepare = insufficient
        run = await self.run_fixture()
        self.assertEqual(len(run.attempts), 6)
        self.assertEqual(self.adapters["flora_full"].requests, [])
        self.assertEqual(sum(a.status == "unavailable" for a in run.attempts), 4)


if __name__ == "__main__":
    unittest.main()
