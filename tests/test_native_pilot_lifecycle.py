"""Intake/causal boundary mechanics, not model qualification or a behavioral run."""
import asyncio
import ast
from dataclasses import replace
import inspect
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from flora.comparison_run import HistorySnapshot, SourceMaterial
from flora.pilot_ingress import materialize_before
from flora.selected.context import ContextPlan
from flora.selected.object_store import EncryptedObjectPlane, LocalObjectBackend
from flora.selected.pilot_lifecycle import (
    NativeBeforeReference, VerifiedNativePilotBefore, apply_native_intervention,
    run_native_pilot_transition, verify_native_before,
)
from flora.selected import pilot_lifecycle
from flora.selected.context_guard import _invoke_guard

FIXTURE = Path(__file__).resolve().parents[1] / "data/synthetic_pilot/v1.json"


class LogRecorder:
    def __init__(self, scope):
        self.scope, self.events = scope, []
    def replay(self):
        return list(self.events)
    def append(self, event, *, expected_revision):
        if expected_revision != len(self.events) - 1 or event.scope != self.scope:
            raise ValueError("mechanical fixture rejected stale revision/scope")
        self.events.append(event)


class NativePilotLifecycleMechanicsTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.reference = NativeBeforeReference((), ContextPlan("native-pilot-context", "personal_judgment",
            exact_claim_ids=("fixture-claim",)), b"same fictional task", "fixture-judgment")

    def fixture(self, case_id):
        scope = ProductHostScope.create(product_id="friday", host_instance_id="fictional-host-mira-" + case_id,
            schema_version="1.0.0", encryption_domain="fictional-native-pilot")
        log = LogRecorder(scope)
        objects = EncryptedObjectPlane(scope=scope, key=b"p" * 32,
            backend=LocalObjectBackend(Path(self.directory.name) / case_id))
        checkpoint = materialize_before(path=FIXTURE, case_id=case_id, scope=scope, log=log, objects=objects)
        originals = tuple(SourceMaterial(event, objects.get(checkpoint.references[event.payload_reference]))
                          for event in log.replay())
        history = HistorySnapshot(scope, originals)
        raw = objects.put(b"fictional supplied decision; not a learned result")
        decision = ExperienceEvent.create(event_type="decision", scope=scope, occurred_at="2026-09-29T14:00:00Z",
            content_digest=raw.plaintext_sha256, parent_event_ids=(originals[-1].event.event_id,),
            payload_reference=raw.object_id, retention_class="ordinary_experience", storage_tier="raw_buffer",
            provenance=ProvenanceReference.create(provenance_type="derived_inference",
                source_reference_ids=(originals[-1].event.event_id,), derivation_activity_id="fixture-only",
                responsible_component="fixture-only"))
        log.append(decision, expected_revision=len(log.replay()) - 1)
        verified = VerifiedNativePilotBefore(case_id, history.digest(),
            tuple((event.event_id, event.event_sha256) for event in log.replay()), history.event_ids,
            decision.event_id, "a" * 64)
        sources = {item.event.event_id: SimpleNamespace(object_ref=item.event.payload_reference,
            evidence=SimpleNamespace(role="generated_reconstruction", content_digest=item.event.content_digest,
                                     parent_refs=item.event.parent_event_ids)) for item in originals}
        runtime = SimpleNamespace(scope=scope, log=log, objects=objects,
            sources=SimpleNamespace(lookup=sources.get), source_policy=SimpleNamespace(permits=lambda *_: True))
        lineage = SimpleNamespace(history_for=lambda *_: history,
            history_authority=SimpleNamespace(authorize_history=lambda **_: True))
        return checkpoint, runtime, lineage, verified

    def transition(self, case_id, at="2026-09-29T14:01:00Z"):
        checkpoint, runtime, lineage, verified = self.fixture(case_id)
        # Only the append mechanics are tested under this patch. Actual selected
        # native recovery is exercised by the separate backend gate.
        with patch("flora.selected.pilot_lifecycle.verify_native_before", return_value=verified):
            result = apply_native_intervention(path=FIXTURE, checkpoint=checkpoint, reference=self.reference,
                runtime=runtime, lineage=lineage, occurred_at=at)
        return result, runtime

    def test_correction_preserves_historical_observation_and_original_only_parent(self):
        result, runtime = self.transition("pilot-caregiving-correction")
        event = result.intervention.event
        payload = json.loads(runtime.objects.get(result.intervention.raw))
        self.assertEqual(payload["observed_at"], "2026-09-01T10:00:00.000000Z")
        self.assertEqual(event.occurred_at, "2026-09-29T14:01:00.000000Z")
        self.assertEqual(event.provenance.provenance_type, "generated_reconstruction")
        self.assertTrue(set(event.parent_event_ids).issubset(result.before.original_event_ids))
        self.assertNotIn(result.before.native_decision_event_id, result.after_history.event_ids)
        self.assertEqual(result.after_history.event_ids, (*result.before.original_event_ids, event.event_id))
        self.assertIsNone(result.outcome_audit)

    def test_outcome_audit_is_linked_but_excluded_from_shared_original_history(self):
        result, runtime = self.transition("pilot-commute-outcome")
        self.assertFalse(result.intervention.event.parent_event_ids)
        audit = result.outcome_audit
        self.assertEqual(audit.event.parent_event_ids,
                         (result.before.native_decision_event_id, result.intervention.event.event_id))
        self.assertEqual(json.loads(runtime.objects.get(audit.raw))["causal_claim"], "none")
        self.assertNotIn(audit.event.event_id, result.after_history.event_ids)
        self.assertNotIn(result.before.native_decision_event_id, result.after_history.event_ids)
        self.assertEqual(len(runtime.log.replay()), len(result.before.canonical_prefix) + 2)

    def test_past_intervention_and_changed_canonical_prefix_stop_before_append(self):
        checkpoint, runtime, lineage, verified = self.fixture("pilot-coffee-correction")
        count = len(runtime.log.replay())
        with patch("flora.selected.pilot_lifecycle.verify_native_before", return_value=verified):
            with self.assertRaisesRegex(ValueError, "cannot precede"):
                apply_native_intervention(path=FIXTURE, checkpoint=checkpoint, reference=self.reference,
                    runtime=runtime, lineage=lineage, occurred_at="2026-09-01T11:00:00Z")
        self.assertEqual(len(runtime.log.replay()), count)
        changed = replace(verified, canonical_prefix=verified.canonical_prefix[:-1])
        with patch("flora.selected.pilot_lifecycle.verify_native_before", return_value=changed):
            with self.assertRaisesRegex(ValueError, "cannot precede"):
                apply_native_intervention(path=FIXTURE, checkpoint=checkpoint, reference=self.reference,
                    runtime=runtime, lineage=lineage, occurred_at="2026-09-29T14:01:00Z")
        self.assertEqual(len(runtime.log.replay()), count)

    def test_convincing_text_or_generic_services_cannot_qualify_before_run(self):
        checkpoint, runtime, lineage, _ = self.fixture("pilot-coffee-correction")
        with self.assertRaisesRegex(TypeError, "actual selected"):
            verify_native_before(path=FIXTURE, checkpoint=checkpoint, reference=self.reference,
                                 runtime=runtime, lineage=lineage)
        async def text_only(_):
            return b"a convincing answer is not a recovered native receipt"
        with self.assertRaisesRegex(TypeError, "persisted stage references"):
            asyncio.run(run_native_pilot_transition(path=FIXTURE, checkpoint=checkpoint, runtime=runtime,
                lineage=lineage, before_executor=text_only, occurred_at=lambda: "2026-09-29T14:01:00Z"))

    def test_actual_before_guard_obeys_void_context_contract_and_rechecks_withdrawal(self):
        """Exercise the real nested guard and context contract, with fixture ports."""
        checkpoint, runtime, lineage, _ = self.fixture("pilot-coffee-correction")
        history = lineage.history_for(checkpoint.case_id, "before")
        phase_allowed, source_allowed, calls = [True], [True], []
        def authorize_history(**kwargs):
            calls.append(kwargs["phase"])
            return phase_allowed[0]
        lineage.history_authority.authorize_history = authorize_history
        runtime.source_policy.permits = lambda *_: source_allowed[0]
        # Select the actual callback body rather than copy its implementation
        # or mock away the current-context authority_guard return contract.
        parsed = ast.parse(inspect.getsource(verify_native_before))
        guard_node = next(node for node in parsed.body[0].body
                          if isinstance(node, ast.FunctionDef) and node.name == "guard")
        module = ast.Module(body=[guard_node], type_ignores=[])
        namespace = dict(vars(pilot_lifecycle), checkpoint=checkpoint, runtime=runtime,
            lineage=lineage, history=history, phase=None, permission_snapshots=[])
        exec(compile(ast.fix_missing_locations(module), inspect.getsourcefile(verify_native_before), "exec"), namespace)
        guard = namespace["guard"]
        self.assertIsNone(_invoke_guard(guard))
        self.assertEqual(calls, ["before"])
        phase_allowed[0] = False
        with self.assertRaisesRegex(PermissionError, "phase permission was withdrawn"):
            _invoke_guard(guard)
        phase_allowed[0], source_allowed[0] = True, False
        with self.assertRaisesRegex(PermissionError, "original source is no longer permitted"):
            _invoke_guard(guard)
        source_allowed[0] = True
        self.assertIsNone(_invoke_guard(guard))
        self.assertEqual(calls, ["before"] * 4)

    def test_phase_withdrawal_during_payload_write_stops_intervention_append(self):
        checkpoint, runtime, lineage, verified = self.fixture("pilot-coffee-correction")
        count, allowed, put = len(runtime.log.replay()), [True], runtime.objects.put
        lineage.history_authority.authorize_history = lambda **_: allowed[0]
        def withdraw_during_write(payload):
            raw = put(payload)
            allowed[0] = False
            return raw
        runtime.objects.put = withdraw_during_write
        with patch("flora.selected.pilot_lifecycle.verify_native_before", return_value=verified):
            with self.assertRaisesRegex(PermissionError, "changed before intervention"):
                apply_native_intervention(path=FIXTURE, checkpoint=checkpoint, reference=self.reference,
                    runtime=runtime, lineage=lineage, occurred_at="2026-09-29T14:01:00Z")
        self.assertEqual(len(runtime.log.replay()), count)

    def test_phase_withdrawal_during_source_metadata_stops_intervention_append(self):
        checkpoint, runtime, lineage, verified = self.fixture("pilot-coffee-correction")
        count, allowed, lookup = len(runtime.log.replay()), [True], runtime.sources.lookup
        lineage.history_authority.authorize_history = lambda **_: allowed[0]
        def withdraw_during_lookup(event_id):
            result = lookup(event_id)
            allowed[0] = False
            return result
        runtime.sources.lookup = withdraw_during_lookup
        with patch("flora.selected.pilot_lifecycle.verify_native_before", return_value=verified):
            with self.assertRaisesRegex(PermissionError, "changed before intervention"):
                apply_native_intervention(path=FIXTURE, checkpoint=checkpoint, reference=self.reference,
                    runtime=runtime, lineage=lineage, occurred_at="2026-09-29T14:01:00Z")
        self.assertEqual(len(runtime.log.replay()), count)

    def test_audit_write_withdrawal_retains_original_partial_intake_without_audit(self):
        checkpoint, runtime, lineage, verified = self.fixture("pilot-commute-outcome")
        count, allowed, calls, put = len(runtime.log.replay()), [True], [0], runtime.objects.put
        lineage.history_authority.authorize_history = lambda **_: allowed[0]
        def withdraw_during_audit_write(payload):
            raw = put(payload)
            calls[0] += 1
            if calls[0] == 2:
                allowed[0] = False
            return raw
        runtime.objects.put = withdraw_during_audit_write
        with patch("flora.selected.pilot_lifecycle.verify_native_before", return_value=verified):
            with self.assertRaisesRegex(PermissionError, "changed before outcome audit"):
                apply_native_intervention(path=FIXTURE, checkpoint=checkpoint, reference=self.reference,
                    runtime=runtime, lineage=lineage, occurred_at="2026-09-29T14:01:00Z")
        replay = runtime.log.replay()
        self.assertEqual(len(replay), count + 1)
        self.assertEqual(replay[-1].event_type, "observation")
        self.assertFalse(replay[-1].parent_event_ids)
        self.assertFalse(any(event.event_type == "outcome" for event in replay))

    def test_withdrawal_during_canonical_commit_blocks_complete_transition(self):
        checkpoint, runtime, lineage, verified = self.fixture("pilot-commute-outcome")
        count, allowed, append = len(runtime.log.replay()), [True], runtime.log.append
        lineage.history_authority.authorize_history = lambda **_: allowed[0]
        def withdraw_during_commit(event, **kwargs):
            append(event, **kwargs)
            allowed[0] = False
        runtime.log.append = withdraw_during_commit
        with patch("flora.selected.pilot_lifecycle.verify_native_before", return_value=verified):
            with self.assertRaisesRegex(PermissionError, "changed before intervention"):
                apply_native_intervention(path=FIXTURE, checkpoint=checkpoint, reference=self.reference,
                    runtime=runtime, lineage=lineage, occurred_at="2026-09-29T14:01:00Z")
        self.assertEqual(len(runtime.log.replay()), count + 1)
        self.assertEqual(runtime.log.replay()[-1].event_type, "observation")


if __name__ == "__main__":
    unittest.main()
