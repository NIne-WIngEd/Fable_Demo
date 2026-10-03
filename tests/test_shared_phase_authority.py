"""Fresh pure origin passes in real frames with controlled transport races."""
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from flora.selected import selected_authority_frame as frames
from flora.selected import selected_phase_authority as phase
from flora.selected.comparison_custody import SelectedRunEvidencePolicy
from flora.selected.native_arm import NativeInvocationEntry
from flora.selected.native_reads import SelectedNativeReadServices

import test_shared_authority_frame as fixtures
from test_selected_phase_authority import _phase_pass_calls


class SharedPhaseAuthorityTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.SharedAuthorityFrameTest()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def prepare(self):
        return self.f.prepare(plan=replace(self.f.plan, state_routes=()))

    def test_one_base_binding_pass_verifies_shared_origin_once_without_io(self):
        prepared = self.prepare()
        frame = self.f._frame(prepared)
        before = len(self.f.f.connection.calls), len(self.f.client.reads)
        calls = _phase_pass_calls(frame._base_bindings)
        self.assertEqual(calls["origins"], [id(frame.origin)])
        self.assertEqual(calls["callbacks"], [])
        self.assertEqual(before, (len(self.f.f.connection.calls), len(self.f.client.reads)))
        calls = _phase_pass_calls(frame._base_bindings)
        self.assertEqual(calls["origins"], [id(frame.origin)])

    def test_in_place_held_mutation_after_independent_callback_runs_fresh_origin_body(self):
        prepared = self.prepare()
        held = self.f.history.sources[0].event
        previous, callbacks = held.event_type, []
        def guard():
            callbacks.append(True)
            if len(callbacks) == 2:
                held.__dict__["event_type"] = "late held mutation"
        prepared.authority_guard = guard
        try:
            with self.assertRaisesRegex(PermissionError, "selected phase held material or scope changed"):
                prepared.metadata_current()
            self.assertEqual(callbacks, [True, True])
        finally:
            held.__dict__["event_type"] = previous

    def test_in_place_scope_mutation_after_independent_callback_runs_fresh_origin_body(self):
        prepared = self.prepare()
        frame = self.f._frame(prepared)
        scope = self.f.history.scope
        previous, callbacks = scope.host_instance_id, []
        def guard():
            callbacks.append(True)
            scope.__dict__["host_instance_id"] = "late-scope-mutation"
        try:
            # The prepared _phase wrapper also checks scope before returning.
            # Invoke the real frame callback directly to discriminate its
            # fresh origin body from that earlier independent rejection.
            with self.assertRaisesRegex(PermissionError, "selected phase held material or scope changed"):
                frame.finish(authority_guard=guard)
            self.assertEqual(callbacks, [True])
        finally:
            scope.__dict__["host_instance_id"] = previous

    def test_in_place_held_mutation_at_terminal_runs_fresh_origin_body(self):
        prepared = self.prepare()
        held = self.f.history.sources[0].event
        previous, changed = held.event_type, []
        def hook(statement, parameters):
            if self.f._terminal(statement) and not changed:
                changed.append(True)
                held.__dict__["event_type"] = "terminal held mutation"
        self.f.sql_hook = hook
        try:
            with self.assertRaisesRegex(PermissionError, "selected phase held material or scope changed"):
                prepared.metadata_current()
            self.assertEqual(changed, [True])
        finally:
            self.f.sql_hook = None
            held.__dict__["event_type"] = previous

    def test_later_metadata_boundary_rechecks_same_origin_held_contents(self):
        prepared = self.prepare()
        prepared.metadata_current()
        held = self.f.history.sources[0].event
        previous = held.event_type
        before = len(self.f.f.connection.calls), len(self.f.client.reads)
        try:
            held.__dict__["event_type"] = "between-boundaries mutation"
            with self.assertRaisesRegex(PermissionError, "selected phase held material or scope changed"):
                prepared.metadata_current()
            self.assertEqual(before, (len(self.f.f.connection.calls), len(self.f.client.reads)))
        finally:
            held.__dict__["event_type"] = previous
        prepared.metadata_current()

    def test_inherited_parent_installed_gate_remains_checked_before_replacement_runs(self):
        prepared = self.prepare()
        frame = self.f._frame(prepared)
        self.assertTrue(frame._event_descriptor._parents)
        parent = frame._event_descriptor._parents[0]
        original = getattr(parent._owner, parent._name)
        effects = []
        def replacement(*args):
            effects.append("changed gate")
            return True
        try:
            setattr(parent._owner, parent._name, replacement)
            with self.assertRaises(PermissionError):
                frame.finish(authority_guard=lambda: effects.append("independent"))
            self.assertEqual(effects, [])
        finally:
            setattr(parent._owner, parent._name, original)

    def test_same_history_digest_cannot_compose_independently_issued_origins(self):
        authority = SelectedRunEvidencePolicy(custody=self.f.h.h.custody, run_id="run",
            permissions=self.f.fixture.permissions,
            history_metadata_domain="selected-history-metadata-v1", maximum_history_sources=16)
        runtime = fixtures._Owner(scope=self.f.f.scope, authority_namespace_id=self.f.f.namespace,
            sources=self.f.registry, log=self.f.log, source_policy=self.f.fixture.permissions,
            context_policy=self.f.fixture.policy, state=self.f.fixture.state)
        lineage = fixtures._Owner(history_authority=authority)
        entry = NativeInvocationEntry("case", "before", "peer-frame-fixture", self.f.plan, "a" * 64)
        SelectedNativeReadServices._install_phase_source_gate(
            SimpleNamespace(runtime=runtime, lineage=lineage), entry, self.f.history)
        peer = phase.selected_phase_authority(runtime.source_policy, "permits")
        original = phase.selected_phase_authority(self.f.policy, "allow_event")
        self.assertEqual(peer.history_sha256, original.history_sha256)
        self.assertIsNot(peer._origin, original._origin)
        before = len(self.f.f.connection.calls), len(self.f.client.reads)
        with self.assertRaisesRegex(PermissionError, "phase origins differ"):
            frames.shared_phase_origin(runtime.source_policy, self.f.policy)
        self.assertEqual(before, (len(self.f.f.connection.calls), len(self.f.client.reads)))

    def test_frame_rejects_pair_helper_replacement_before_its_effects(self):
        prepared = self.prepare()
        frame = self.f._frame(prepared)
        effects = []
        def replacement(*args):
            effects.append("replacement")
        with patch.object(phase, "_verify_selected_phase_pair", new=replacement):
            with self.assertRaisesRegex(PermissionError, "native producer/composition helper changed"):
                frame.finish(authority_guard=lambda: effects.append("independent"))
        self.assertEqual(effects, [])


if __name__ == "__main__":
    unittest.main()
