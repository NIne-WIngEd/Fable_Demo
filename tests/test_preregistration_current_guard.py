"""Actual selected source/grant methods; fictional manifest rows and SQL ports.

These check one-call observations and withdrawal, not physical performance,
producer qualification or learning.
"""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cognitive_kernel.canonical import canonical_sha256
from flora.selected.experiment_manifests import SelectedSourceAuthority, XTDBExperimentManifestCustody, manifest_purpose
from flora.selected.experiment_preregistration import XTDBExperimentPreregistrationCustody
from flora.selected.formation_policy import FormationPermissionAction, formation_permission_payload
from flora.selected.owner_authorization import OwnerActionProof, owner_action_message
import base64
import test_phase_source_fence as support


class PreregistrationCurrentGuardTest(unittest.TestCase):
    def setUp(self):
        self.base = support.PhaseSourceFenceTest()
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.f, self.registry, self.permissions = self.base.f, self.base.registry, self.base.permissions
        self.authority = SelectedSourceAuthority(self.registry, self.f.log, self.permissions, self.f.objects)
        purpose = manifest_purpose("guard-fixture", "read")
        for index, event_id in enumerate(self.base.h.before.event_ids):
            source = self.registry.lookup(event_id)
            action = FormationPermissionAction.create(scope=self.f.scope, authority_namespace_id=self.f.namespace,
                action_id="prereg-current-manifest-" + str(index), source_ref_id=event_id,
                source_registration_sha256=source.registration_sha256, purpose=purpose, decision="allow",
                generation=1, previous_action_sha256=None, authorization_ref="fictional-enrolled-owner",
                authorized_at="2026-09-30T16:00:00Z")
            event = self.f.event(formation_permission_payload(action), event_type="formation_permission_action",
                timestamp=action.authorized_at, parents=(event_id,))
            self.f.proofs[event.event_id] = OwnerActionProof("formation_permission", event.event_id, event.event_sha256,
                base64.b64encode(self.f.key.sign(owner_action_message(event, "formation_permission"))).decode())
            self.permissions.apply(action, request_event_id=event.event_id, log=self.f.log,
                objects=self.f.objects, references=self.f.references, verifier=self.f.verifier)
        gates = tuple({"authority_id": self.authority.authority_id, "event_id": event_id,
            "purpose": "personal_judgment", "original": True,
            "binding_sha256": canonical_sha256(self.authority.binding(event_id))}
            for event_id in self.base.h.before.event_ids)
        cohort = {"manifest_id": "cohort", "event_id": gates[0]["event_id"], "source_gates": gates,
            "dependencies": (), "record_sha256": "a" * 64}
        recipe = {"manifest_id": "recipe", "event_id": gates[1]["event_id"], "source_gates": gates,
            "dependencies": ({"kind": "cohort", "manifest_id": "cohort", "record_sha256": "a" * 64},),
            "record_sha256": "b" * 64}
        manifests = object.__new__(XTDBExperimentManifestCustody)
        manifests.local = self.authority
        manifests.authorities = {self.authority.authority_id: self.authority}
        manifests.experiment_id = "guard-fixture"
        manifests.metadata = lambda kind, manifest_id: deepcopy({"cohort": cohort, "recipe": recipe}[kind])
        store = object.__new__(XTDBExperimentPreregistrationCustody)
        store.manifests, store.permissions = manifests, self.permissions
        store.comparison = SimpleNamespace(registry=self.registry, log=self.f.log,
            objects=self.f.objects, connection=self.f.connection)
        store._controllers = (self.registry, self.f.log, self.f.objects, self.permissions, self.f.connection)
        store.dependencies = {"cohort": cohort, "recipe": recipe}
        store._source_gates, store.spec, store.anchor = gates[:1], None, None
        self.store = store

    def test_same_call_batches_metadata_without_omitting_any_actual_gate(self):
        actual, gate_calls = SelectedSourceAuthority.gate, []
        def gate(authority, frozen):
            gate_calls.append((frozen["event_id"], frozen["purpose"]))
            return actual(authority, frozen)
        with patch.object(SelectedSourceAuthority, "gate", gate):
            start = len(self.f.connection.calls)
            self.store._check_current(manifests=self.store.manifests, permissions=self.permissions,
                operation=None, parents=(), include_evaluation=True)
            original_reads = len(self.f.connection.calls) - start
            expected_calls = tuple(gate_calls)
            gate_calls.clear()
            start = len(self.f.connection.calls)
            self.store._current()
            observed_reads = len(self.f.connection.calls) - start
        self.assertEqual(tuple(gate_calls), expected_calls)
        self.assertGreater(len(expected_calls), 10)
        self.assertLess(observed_reads * 4, original_reads)
        self.assertEqual(observed_reads, 5)

    def test_last_actual_gate_withdrawal_is_seen_by_terminal_fence_and_next_call(self):
        actual, count = SelectedSourceAuthority.gate, 0
        def gate(authority, frozen):
            nonlocal count
            result = actual(authority, frozen)
            count += 1
            if count == 12:
                self.base.grant(self.base.h.before.event_ids[1], "revoke")
            return result
        with patch.object(SelectedSourceAuthority, "gate", gate):
            with self.assertRaises(PermissionError):
                self.store._current()
        self.assertEqual(count, 12)
        with self.assertRaises(PermissionError):
            self.store._current()

    def test_fresh_canonical_replay_rejects_changed_commits_after_last_gate(self):
        actual, original_replay = SelectedSourceAuthority.gate, self.f.log.replay_committed
        changed, count = False, 0
        def replay():
            entries = tuple(original_replay())
            return (replace(entries[0], stream_position=99), *entries[1:]) if changed else entries
        def gate(authority, frozen):
            nonlocal changed, count
            result = actual(authority, frozen)
            count += 1
            if count == 12:
                changed = True
            return result
        with patch.object(self.f.log, "replay_committed", replay), patch.object(SelectedSourceAuthority, "gate", gate):
            with self.assertRaisesRegex(PermissionError, "canonical observations changed"):
                self.store._current()
        self.assertTrue(changed)

    def test_final_canonical_callback_cannot_replace_an_actual_reader(self):
        original_replay, original_plain = self.f.log.replay_committed, self.f.log.replay
        calls = 0
        def replay():
            nonlocal calls
            entries = original_replay()
            calls += 1
            if calls == 2:
                self.f.log.replay = lambda: []
            return entries
        try:
            with patch.object(self.f.log, "replay_committed", replay):
                with self.assertRaisesRegex(PermissionError, "reader changed"):
                    self.store._current()
        finally:
            self.f.log.replay = original_plain
        self.assertEqual(calls, 2)

    def test_terminal_sql_callback_cannot_replace_an_actual_reader(self):
        actual_execute, original_plain = self.f.connection.execute, self.f.log.replay
        changed = False
        def execute(sql, parameters):
            nonlocal changed
            result = actual_execute(sql, parameters)
            if "AS flora_current_metadata_fence LIMIT" in sql:
                self.f.log.replay = lambda: []
                changed = True
            return result
        try:
            with patch.object(self.f.connection, "execute", execute):
                with self.assertRaisesRegex(PermissionError, "reader changed"):
                    self.store._current()
        finally:
            self.f.log.replay = original_plain
        self.assertTrue(changed)

    def test_final_canonical_callback_cannot_replace_source_binding(self):
        original_replay = self.f.log.replay_committed
        calls = 0
        def replay():
            nonlocal calls
            entries = original_replay()
            calls += 1
            if calls == 2:
                object.__setattr__(self.authority, "binding", lambda event_id: {})
            return entries
        try:
            with patch.object(self.f.log, "replay_committed", replay):
                with self.assertRaisesRegex(PermissionError, "reader changed"):
                    self.store._current()
        finally:
            object.__delattr__(self.authority, "binding")
        self.assertEqual(calls, 2)

    def test_final_canonical_callback_cannot_replace_source_class_gate(self):
        original_replay, original_gate = self.f.log.replay_committed, SelectedSourceAuthority.gate
        # Hold the instance binding unchanged so the class comparison has its
        # own regression rather than merely repeating the bound-method check.
        object.__setattr__(self.authority, "gate", original_gate.__get__(self.authority))
        calls = 0
        def replay():
            nonlocal calls
            entries = original_replay()
            calls += 1
            if calls == 2:
                SelectedSourceAuthority.gate = lambda authority, frozen: None
            return entries
        try:
            with patch.object(self.f.log, "replay_committed", replay):
                with self.assertRaisesRegex(PermissionError, "reader changed"):
                    with self.store._current_observations(operation=None, parents=(), include_evaluation=True):
                        pass
        finally:
            SelectedSourceAuthority.gate = original_gate
            object.__delattr__(self.authority, "gate")
        self.assertEqual(calls, 2)


if __name__ == "__main__":
    unittest.main()
