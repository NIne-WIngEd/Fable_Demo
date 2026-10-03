"""Data-only H contributor with actual contracts and controlled transports.

The physical fixture simulates the root collector's already verified origin
contract. Private descriptor issuance and final frame ownership are separate
integration tests; these tests make no backend latency or learned claim.
"""
from copy import copy
from dataclasses import replace
from datetime import datetime, timezone
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from flora.selected import selected_history_contribution as contributions
from flora.selected.comparison_custody import evaluation_purpose
from flora.selected.formation_context import register_experience_source
from flora.selected.formation_policy import XTDBFormationPermissionPolicy
from flora.selected.governed_development import XTDBGovernedPersonalDevelopment
from flora.selected.native_phase_gate import install_native_phase_gate
from flora.selected.selected_context_fence import SelectedContextMetadataSample
from flora.selected.selected_history_fence import _held_snapshot
from test_experience_envelope_reuse import record
import test_selected_history_fence as fixtures


class CapturedPhysicalFixture:
    """Exact physical collection fixture; captured accessors never read SQL."""

    def __init__(self, origin):
        self.origin, self.sample = origin, None
        self.entries, self.commitments = {}, {}
        self.adoptions, self.captured_reads = [], []
        self.held = _held_snapshot(origin.history)

    def binding(self):
        if _held_snapshot(self.origin.history) != self.held:
            raise PermissionError("controlled origin held material changed")

    def adopt(self, commitment, committed):
        event_id = commitment.source.evidence.ref_id
        if event_id in self.entries:
            if self.entries[event_id] != committed or self.commitments[event_id] != commitment:
                raise PermissionError("controlled collector physical material changed")
        self.entries[event_id], self.commitments[event_id] = committed, commitment
        self.adoptions.append(event_id)

    def entry(self, event_id):
        if event_id not in self.entries:
            current = self.sample.local_registry.lookup_commitment(event_id)
            if current is None:
                raise PermissionError("controlled collector missing physical locator")
            committed = self.origin.log.lookup_committed(event_id=event_id,
                event_sha256=current.event_sha256, stream_position=current.stream_position,
                expected_recorded_at=current.recorded_at)
            evidence, event = current.source.evidence, committed.event
            if (evidence.ref_id != event_id or event.scope != evidence.scope
                    or event.payload_reference != current.source.object_ref
                    or event.content_digest != evidence.content_digest
                    or event.parent_event_ids != evidence.parent_refs or event.occurred_at != evidence.observed_at):
                raise PermissionError("controlled collector registration/physical mismatch")
            self.entries[event_id], self.commitments[event_id] = committed, current
        return self.entries[event_id]

    def commitment(self, event_id):
        self.entry(event_id)
        return self.commitments[event_id]

    def captured_entry(self, event_id):
        self.captured_reads.append(event_id)
        return self.entries.get(event_id)

    def captured_commitment(self, event_id):
        return self.commitments.get(event_id)

    def contains(self, event_id):
        return event_id in self.entries

    def closure(self, ids, *, maximum_sources):
        seen, pending = set(ids), list(ids)
        if len(seen) > maximum_sources:
            raise PermissionError("controlled collector source cap exceeded")
        while pending:
            event_id = pending.pop()
            entry = self.entry(event_id)
            new = set(entry.event.parent_event_ids) - seen
            if len(seen) + len(new) > maximum_sources:
                raise PermissionError("controlled collector parent source cap exceeded")
            seen.update(new)
            pending.extend(new)
        positions = {self.entries[event_id].stream_position for event_id in seen}
        if len(positions) != len(seen) or any(
                self.entries[parent].stream_position >= self.entries[event_id].stream_position
                for event_id in seen for parent in self.entries[event_id].event.parent_event_ids):
            raise PermissionError("controlled collector parent is not earlier")
        return tuple(sorted(seen))


class SelectedHistoryContributionTest(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.SelectedHistoryFenceTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture, self.h, self.f = fixture, fixture.h, fixture.f
        self.gate_calls = []

    def build(self, *, phase="before", cap=16, history=None):
        history = history or (self.h.before if phase == "before" else self.h.after)
        gated = copy(self.h.permissions)
        install_native_phase_gate(gated, "permits", canonical_predicate=XTDBFormationPermissionPolicy.permits,
            phase_now=lambda: self.gate_calls.append("phase") or False,
            phase_member=lambda event_id: self.gate_calls.append(event_id) or False)
        state = XTDBGovernedPersonalDevelopment(scope=self.f.scope,
            authority_namespace_id=self.f.namespace, connection=self.f.connection,
            registry=self.h.registry, policy=gated)
        runtime = SimpleNamespace(source_policy=gated, state=state)
        origin = SimpleNamespace(runtime=runtime, history=history, registry=self.h.registry,
            log=self.fixture.log, custody=self.h.custody, permissions=self.h.permissions,
            cap=cap, event_ids=history.event_ids, history_sha256=history.digest(),
            authority=self.fixture.policy, case_id="case", phase=phase, namespace=self.f.namespace,
            originals={source.event.event_id: source.event for source in history.sources})
        physical = CapturedPhysicalFixture(origin)
        sample = SelectedContextMetadataSample(state=state, binding_guard=physical.binding,
            registry=origin.registry, permissions=gated, comparison=origin.custody, maximum_rows=1024)
        physical.sample = sample
        self.origin, self.physical, self.sample = origin, physical, sample
        self.contribution = contributions.SelectedHistoryContribution(origin, sample, physical)
        return self.contribution

    def register_control(self, event_type="decision", parents=()):
        event = self.f.event(b"fictional supplied control", event_type=event_type, parents=parents)
        register_experience_source(event_id=event.event_id, raw=self.f.references[event.payload_reference],
            registry=self.h.registry, log=self.f.log, objects=self.f.objects,
            role="historical_experience", modality="text")
        self.fixture.client.records = [replace(record(current, index),
            recorded_at=datetime(2026, 9, 29, 14, tzinfo=timezone.utc))
            for index, current in enumerate(self.f.log.events)]
        return event

    def test_collects_history_and_manifest_without_private_reads_proof_or_terminal(self):
        before = len(self.f.connection.calls)
        with patch.object(self.f.objects, "get", side_effect=AssertionError("private read")), \
             patch.object(self.h.custody.raw_custody, "read", side_effect=AssertionError("private read")):
            contribution = self.build()
            self.assertIsNone(contribution.validate_permissions())
        self.assertEqual(contribution.original_ids, self.h.before.event_ids)
        self.assertEqual(contribution.evaluation_purpose, evaluation_purpose("run", "case", "before"))
        self.assertEqual(self.physical.adoptions, [contribution.manifest_id])
        self.assertEqual(len(self.fixture.client.reads), len(contribution.original_ids) + 1)
        self.assertEqual(self.gate_calls, [])
        self.assertIs(self.sample.permissions, self.origin.runtime.source_policy)
        self.assertIsNot(self.sample.permissions, self.origin.permissions)
        self.assertIs(self.sample.comparison, self.origin.custody)
        self.assertFalse(any("metadata_fence LIMIT" in sql or "context_fence LIMIT" in sql
            for sql, _ in self.f.connection.calls[before:]))

    def test_manifest_is_metadata_only_and_needs_no_evaluation_grant(self):
        contribution = self.build()
        contribution.validate_permissions()
        self.assertIsNone(self.h.permissions.current_action(contribution.manifest_id,
            contribution.evaluation_purpose))
        self.assertFalse(any(kind == "permission" and key == self.h.permissions._key(
            "head", contribution.manifest_id, contribution.evaluation_purpose)
            for kind, _, key, _ in self.sample._observations))
        self.sample.verify_final_current_rows()

    def test_evaluation_withdrawal_after_other_purpose_collection_reaches_joint_terminal(self):
        contribution = self.build()
        contribution.validate_permissions()
        other_purpose = evaluation_purpose("run", "case", "after")
        self.sample.prime_source_purposes((((contribution.original_ids[0],), other_purpose, 128),))
        self.h.grant(contribution.original_ids[-1], "before", "revoke")
        with self.assertRaisesRegex(PermissionError, "authority changed after callbacks"):
            self.sample.verify_final_current_rows()

    def test_shared_source_keeps_distinct_evaluation_and_other_purpose_heads(self):
        contribution = self.build()
        other_purpose = evaluation_purpose("run", "case", "after")
        event_id = contribution.original_ids[0]
        self.sample.prime_source_purposes((((event_id,), other_purpose, 128),))
        keys = {key for kind, table, key, _ in self.sample._observations
            if kind == "permission" and table == "flora_formation_permission_current"}
        self.assertIn(self.h.permissions._key("head", event_id, contribution.evaluation_purpose), keys)
        self.assertIn(self.h.permissions._key("head", event_id, other_purpose), keys)
        self.assertEqual(sum(kind == "registry" and table == "flora_registered_formation_sources"
            and key == self.h.registry._key("source", event_id)
            for kind, table, key, _ in self.sample._observations), 1)

    def test_manifest_inclusive_cap_fails_before_effectful_reads(self):
        reads, calls = len(self.fixture.client.reads), len(self.f.connection.calls)
        with self.assertRaisesRegex(PermissionError, "source cap"):
            self.build(cap=2)
        self.assertEqual(len(self.fixture.client.reads), reads)
        self.assertEqual(len(self.f.connection.calls), calls)

    def test_h_cap_is_independent_from_larger_already_collected_domain(self):
        contribution = self.build(cap=3)
        event_id = contribution.original_ids[0]
        for _ in range(3):
            event_id = self.register_control(parents=(event_id,)).event_id
        self.physical.closure((event_id,), maximum_sources=128)
        self.assertFalse(contribution.member(event_id))
        self.assertTrue(contribution.member(contribution.original_ids[0]))

    def test_phase_membership_uses_only_captured_material_and_denies_unknown_future_manifest(self):
        contribution = self.build()
        future = self.h.after.event_ids[-1]
        self.physical.closure((future,), maximum_sources=128)
        before = len(self.f.connection.calls), len(self.fixture.client.reads)
        self.assertTrue(contribution.member(contribution.original_ids[0]))
        for event_id in (future, contribution.manifest_id, "not-captured"):
            self.assertFalse(contribution.member(event_id))
        self.assertEqual(before, (len(self.f.connection.calls), len(self.fixture.client.reads)))

    def test_exact_original_leaf_stops_without_traversing_its_original_parents(self):
        contribution = self.build(phase="after")
        child = self.h.after.event_ids[-1]
        self.physical.captured_reads.clear()
        self.assertTrue(contribution.member(child))
        self.assertEqual(self.physical.captured_reads, [child])

    def test_controls_require_held_leaves_except_zero_parent_signed_approval_shape(self):
        valid = self.register_control(parents=(self.h.before.event_ids[0],))
        invalid = self.register_control(parents=(self.h.after.event_ids[-1],))
        approval = self.register_control("state_activation_approval")
        empty_decision = self.register_control()
        contribution = self.build()
        for event in (valid, invalid, approval, empty_decision):
            self.physical.closure((event.event_id,), maximum_sources=128)
        self.assertTrue(contribution.member(valid.event_id))
        self.assertFalse(contribution.member(invalid.event_id))
        self.assertTrue(contribution.member(approval.event_id))
        self.assertFalse(contribution.member(empty_decision.event_id))

    def test_forbidden_artifacts_deny_even_when_their_parent_is_held(self):
        events = [self.register_control(kind, (self.h.before.event_ids[0],)) for kind in (
            "comparison_artifact", "provider_attempt_artifact", "phase_snapshot_artifact", "experiment_manifest_artifact")]
        contribution = self.build()
        for event in events:
            self.physical.closure((event.event_id,), maximum_sources=128)
            self.assertFalse(contribution.member(event.event_id))

    def test_replaced_phase_classification_constants_cannot_admit_artifacts(self):
        artifact = self.register_control("comparison_artifact", (self.h.before.event_ids[0],))
        contribution = self.build()
        self.physical.closure((artifact.event_id,), maximum_sources=128)
        for name in ("_FORBIDDEN", "_INTERNAL_EVENT_TYPES"):
            with self.subTest(name=name), patch.object(contributions, name, frozenset()):
                self.assertFalse(contribution.member(artifact.event_id))
                with self.assertRaisesRegex(PermissionError, "classification changed"):
                    contribution.binding()

    def test_captured_parent_order_cycle_and_ambiguous_positions_deny(self):
        control = self.register_control(parents=(self.h.before.event_ids[0],))
        contribution = self.build()
        self.physical.closure((control.event_id,), maximum_sources=128)
        entry = self.physical.entries[control.event_id]
        parent = self.physical.entries[control.parent_event_ids[0]]
        self.physical.entries[control.event_id] = replace(entry, stream_position=parent.stream_position)
        self.assertFalse(contribution.member(control.event_id))
        self.physical.entries[control.event_id] = entry
        self.assertTrue(contribution.member(control.event_id))
        changed = replace(entry.event, parent_event_ids=(control.event_id,))
        original = self.physical.commitments[control.event_id]
        evidence = replace(original.source.evidence, parent_refs=(control.event_id,))
        self.physical.entries[control.event_id] = replace(entry, event=changed)
        self.physical.commitments[control.event_id] = replace(original,
            source=replace(original.source, evidence=evidence))
        self.assertFalse(contribution.member(control.event_id))

    def test_held_bytes_mutation_and_pure_helper_replacement_fail_closed(self):
        contribution = self.build()
        original = self.h.before.sources[0]
        saved = original.plaintext
        original.__dict__["plaintext"] = b"changed held bytes"
        try:
            with self.assertRaises(PermissionError):
                contribution.validate_permissions()
            self.assertFalse(contribution.member(contribution.original_ids[0]))
        finally:
            original.__dict__["plaintext"] = saved
        with patch.object(contributions, "_held_snapshot", return_value=contributions._held_snapshot(self.h.before)):
            with self.assertRaises(PermissionError):
                contribution.binding()

    def test_effectful_nonnative_identifier_denies_before_hash_or_comparison(self):
        contribution = self.build()
        calls = []
        class Effectful(str):
            def __hash__(self):
                calls.append("hash")
                return str.__hash__(self)
            def __eq__(self, other):
                calls.append("equal")
                return str.__eq__(self, other)
        self.assertFalse(contribution.member(Effectful(contribution.original_ids[0])))
        self.assertEqual(calls, [])

    def test_changed_pure_guard_closure_is_rejected_without_replacement_effect(self):
        contribution = self.build()
        cells = dict(zip(contribution._guard.__code__.co_freevars, contribution._guard.__closure__))
        original = cells["physical"].cell_contents
        calls = []
        replacement = SimpleNamespace(binding=lambda: calls.append("effect"))
        cells["physical"].cell_contents = replacement
        try:
            with self.assertRaisesRegex(PermissionError, "callback binding changed"):
                contribution.binding()
            self.assertEqual(calls, [])
        finally:
            cells["physical"].cell_contents = original

    def test_captured_reader_fields_are_sealed_before_its_actual_verify(self):
        contribution = self.build()
        cells = dict(zip(contribution._guard.__code__.co_freevars, contribution._guard.__closure__))
        reader = cells["reader_seals"].cell_contents[0][0]
        original = reader.owner, reader.owner_class
        calls = []
        class EffectfulMeta(type):
            def __getattribute__(cls, name):
                if name == "__mro__":
                    calls.append("effect")
                return type.__getattribute__(cls, name)
        class EffectfulOwner(metaclass=EffectfulMeta):
            pass
        reader.__dict__.update(owner=EffectfulOwner(), owner_class=EffectfulOwner)
        try:
            with self.assertRaisesRegex(PermissionError, "descriptor or origin fields changed"):
                contribution.binding()
            self.assertEqual(calls, [])
        finally:
            reader.__dict__.update(owner=original[0], owner_class=original[1])

    def test_manifest_reobservation_preserves_exact_text_and_never_readopts(self):
        contribution = self.build()
        self.assertIsNone(contribution.reobserve_manifest())
        self.assertEqual(self.physical.adoptions, [contribution.manifest_id])
        key = self.h.custody._key("run", "history:case:before")
        row = self.f.connection.rows[("flora_comparison_artifacts", key)]
        original = row["record_json"]
        row["record_json"] = json.dumps(json.loads(original), indent=2)
        with self.assertRaisesRegex(PermissionError, "manifest changed"):
            contribution.reobserve_manifest()
        self.assertEqual(self.physical.adoptions, [contribution.manifest_id])

    def test_manifest_reobservation_detects_changed_physical_recorded_time(self):
        contribution = self.build()
        position = self.physical.entries[contribution.manifest_id].stream_position
        record_value = self.fixture.client.records[position]
        self.fixture.client.records[position] = replace(record_value,
            recorded_at=datetime(2026, 9, 29, 15, tzinfo=timezone.utc))
        with self.assertRaises(ValueError):
            contribution.reobserve_manifest()

    def test_manifest_metadata_callback_revocation_is_left_for_joint_fence(self):
        contribution = self.build()
        contribution.validate_permissions()
        fired = False
        def withdraw():
            nonlocal fired
            if not fired:
                fired = True
                self.h.grant(contribution.original_ids[0], "before", "revoke")
        self.fixture.client.on_read = withdraw
        contribution.reobserve_manifest()
        self.assertTrue(fired)
        with self.assertRaisesRegex(PermissionError, "authority changed after callbacks"):
            self.sample.verify_final_current_rows()


if __name__ == "__main__":
    unittest.main()
