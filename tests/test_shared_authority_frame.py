"""Issued H/C authority frames on actual contracts with controlled transports.

The encrypted objects, owner signatures and canonical services are real here.
Metadata rows and transport races are controlled fixtures, not physical engine,
response latency or learned-judgment evidence.
"""
from copy import copy, deepcopy
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from flora.selected import claims as claim_tables
from flora.selected import context_guard
from flora.selected import selected_authority_frame as shared_frames
from flora.selected.comparison_custody import SelectedRunEvidencePolicy, evaluation_purpose
from flora.selected.experiment_runtime import _AuthorizedRuntimeReads
from flora.selected.governed_development import _HISTORY
from flora.selected.native_arm import NativeInvocationEntry
from flora.selected.native_reads import SelectedNativeReadServices
from flora.selected.personal_state import _ACTIVE, _VERSIONS
from flora.selected.selected_context import prepare_selected_current_context
from flora.selected.selected_phase_authority import selected_phase_authority
from flora.selected.source_closure import _native_snapshot

import test_selected_context as fixtures


class _Owner:
    def __init__(self, **fields):
        self.__dict__.update(fields)


class SharedAuthorityFrameTest(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.SelectedContextTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.f, self.h = fixture.f, fixture.fixture.h
        self.claims, self.claim_id = fixture.claims, fixture.claim_id
        self.plan, self.log, self.client = fixture.plan, fixture.log, fixture.client
        self.registry = fixture.registry
        self.history = self.h.h.before
        self.h.h.custody.log = self.log
        self.sql_hook, self.physical_hook = None, None
        actual_sql, actual_physical = self.f.connection.execute, self.client.get_stream

        # Install these external transport callbacks before private issuance;
        # later race injection changes their fixture state, not their bindings.
        def execute(statement, parameters):
            if self.sql_hook is not None:
                self.sql_hook(statement, parameters)
            return actual_sql(statement, parameters)

        def get_stream(**kwargs):
            if self.physical_hook is not None:
                self.physical_hook(kwargs)
            return actual_physical(**kwargs)

        self.f.connection.execute, self.client.get_stream = execute, get_stream
        authority = SelectedRunEvidencePolicy(custody=self.h.h.custody, run_id="run",
            permissions=fixture.permissions, history_metadata_domain="selected-history-metadata-v1",
            maximum_history_sources=16)
        self.runtime = _Owner(scope=self.f.scope, authority_namespace_id=self.f.namespace,
            sources=self.registry, log=self.log, source_policy=fixture.permissions,
            context_policy=fixture.policy, state=fixture.state)
        self.lineage = _Owner(history_authority=authority)
        entry = NativeInvocationEntry("case", "before", "shared-frame-fixture", self.plan, "a" * 64)
        SelectedNativeReadServices._install_phase_source_gate(
            SimpleNamespace(runtime=self.runtime, lineage=self.lineage), entry, self.history)
        self.state, self.policy = self.runtime.state, self.runtime.context_policy
        self.permissions = self.runtime.source_policy
        self.assertIsNotNone(selected_phase_authority(self.permissions, "permits"))
        self.assertIsNotNone(selected_phase_authority(self.policy, "allow_event"))

    def prepare(self, **kwargs):
        return prepare_selected_current_context(plan=kwargs.pop("plan", self.plan), claims=self.claims,
            state=self.state, log=self.log, objects=self.f.objects, references=self.f.references,
            policy=kwargs.pop("policy", self.policy), maximum_sources=kwargs.pop("maximum_sources", 8),
            approval_verifier_factory=kwargs.pop("approval_verifier_factory", lambda _: self.f.verifier),
            **kwargs)

    def _head_replacement(self, event_id, *, evaluation=False):
        purpose = evaluation_purpose("run", "case", "before") if evaluation else "personal_judgment"
        table = "flora_formation_permission_current"
        key = self.permissions._key("head", event_id, purpose)
        previous = deepcopy(self.f.connection.rows[(table, key)])
        if evaluation:
            self.h.h.grant(event_id, "before", "revoke")
        else:
            self.h.grant(event_id, "revoke")
        replacement = deepcopy(self.f.connection.rows[(table, key)])
        self.f.connection.rows[(table, key)] = previous
        return lambda: self.f.connection.rows.__setitem__((table, key), deepcopy(replacement))

    def _terminal(self, statement):
        return "AS flora_selected_context_fence LIMIT" in statement

    def _frame(self, prepared):
        frame = shared_frames.create_shared_selected_frame(log=prepared.log, policy=prepared.policy,
            claims=prepared.claims, state=prepared.state, binding_guard=prepared._bindings_current)
        frame.observe_authorities(prepared)
        claims, state, log, policy = frame.metadata_view()
        prepared._verify_authorities(claims=claims, state=state, log=log, policy=policy)
        return frame

    def test_metadata_boundary_has_one_joint_terminal_and_two_physical_observations(self):
        prepared = self.prepare(plan=replace(self.plan, state_routes=()))
        start_sql, start_physical = len(self.f.connection.calls), len(self.client.reads)
        callbacks = []
        prepared.authority_guard = lambda: callbacks.append("independent")
        with patch.object(self.f.objects.backend, "get_object", side_effect=AssertionError("private reopen")):
            prepared.metadata_current()
        calls = self.f.connection.calls[start_sql:]
        terminals = [sql for sql, _ in calls if self._terminal(sql)]
        self.assertEqual(len(terminals), 1)
        self.assertIn("flora_comparison_artifacts", terminals[0])
        self.assertIn("flora_formation_permission_current", terminals[0])
        self.assertIn(claim_tables._CURRENT, terminals[0])
        self.assertFalse(any("AS flora_current_metadata_fence LIMIT" in sql for sql, _ in calls))
        positions = [item["stream_position"] for item in self.client.reads[start_physical:]]
        self.assertEqual(len(positions), 2 * len(set(positions)))
        self.assertTrue(all(positions.count(position) == 2 for position in set(positions)))
        self.assertEqual(callbacks, ["independent", "independent"])
        self.assertIs(prepared.state.policy, prepared.policy.permissions)
        self.assertIs(prepared.state.policy, self.permissions)

    def test_final_callback_withdraws_unselected_history_evaluation_source(self):
        prepared = self.prepare(plan=replace(self.plan, state_routes=()))
        unselected = self.f.source_two.event_id
        self.assertNotIn(unselected, {item.event_id for item in prepared.source_authorities})
        change = self._head_replacement(unselected, evaluation=True)
        calls = 0
        def guard():
            nonlocal calls
            calls += 1
            if calls == 2:
                change()
        prepared.authority_guard = guard
        with patch.object(self.f.objects.backend, "get_object", side_effect=AssertionError("private reopen")):
            with self.assertRaises(PermissionError):
                prepared.metadata_current()
        self.assertEqual(calls, 2)

    def test_final_callback_withdraws_selected_context_source(self):
        prepared = self.prepare()
        change = self._head_replacement(self.f.source_one.event_id)
        calls = 0
        def guard():
            nonlocal calls
            calls += 1
            if calls == 2:
                change()
        prepared.authority_guard = guard
        with self.assertRaises(PermissionError):
            prepared.metadata_current()
        self.assertEqual(calls, 2)

    def test_unselected_history_withdrawal_at_joint_sql_is_in_terminal_domain(self):
        prepared = self.prepare(plan=replace(self.plan, state_routes=()))
        change = self._head_replacement(self.f.source_two.event_id, evaluation=True)
        changed = False
        def hook(statement, parameters):
            nonlocal changed
            if self._terminal(statement) and not changed:
                changed = True
                change()
        self.sql_hook = hook
        with self.assertRaisesRegex(PermissionError, "terminal selected context"):
            prepared.metadata_current()
        self.assertTrue(changed)

    def test_each_purpose_remains_independent_for_one_event(self):
        prepared = self.prepare(plan=replace(self.plan, state_routes=()))
        change = self._head_replacement(self.f.source_one.event_id, evaluation=True)
        self.assertTrue(self.h.permissions.permits(self.registry.lookup(self.f.source_one.event_id),
            "personal_judgment"))
        change()
        with self.assertRaises(PermissionError):
            prepared.metadata_current()
        self.assertTrue(self.h.permissions.permits(self.registry.lookup(self.f.source_one.event_id),
            "personal_judgment"))

    def test_current_claim_state_and_activation_share_terminal_domain(self):
        for kind in ("claim", "claim_version", "relation", "state_head", "state_version", "activation"):
            with self.subTest(kind=kind):
                prepared = self.prepare()
                if kind == "claim":
                    table, key = claim_tables._CURRENT, self.claims._row_id(self.claim_id)
                elif kind == "claim_version":
                    table, key = claim_tables._VERSIONS, self.claims._row_id(prepared.claim_authorities[0].version_id)
                elif kind == "relation":
                    table, key = claim_tables._EVIDENCE, self.claims._row_id(prepared.claim_authorities[0].evidence_records[0][0])
                elif kind == "state_head":
                    table, key = _ACTIVE, self.state._head_id(**self.f.identity())
                elif kind == "state_version":
                    table, key = _VERSIONS, self.state._version_id(prepared.state_authorities[0].version_id)
                else:
                    table, key = _HISTORY, self.state._history_key(
                        prepared.state_authorities[0].route.projection_id, prepared.state_authorities[0].version_id)
                previous = deepcopy(self.f.connection.rows[(table, key)])
                changed = False
                def hook(statement, parameters):
                    nonlocal changed
                    if self._terminal(statement) and not changed:
                        changed = True
                        row = self.f.connection.rows[(table, key)]
                        if kind == "state_head":
                            row["approval_event_sha256"] = "e" * 64
                        else:
                            row["record_json"] = "\n" + row["record_json"]
                self.sql_hook = hook
                try:
                    with self.assertRaisesRegex(PermissionError, "terminal selected context"):
                        prepared.metadata_current()
                    self.assertTrue(changed)
                finally:
                    self.sql_hook = None
                    self.f.connection.rows[(table, key)] = previous

    def test_initial_qualification_withdrawal_prevents_approval_factory_and_private_read(self):
        for evaluation in (False, True):
            with self.subTest(evaluation=evaluation):
                event_id = self.f.source_two.event_id if evaluation else self.f.source_one.event_id
                change = self._head_replacement(event_id, evaluation=evaluation)
                table, purpose = "flora_formation_permission_current", (
                    evaluation_purpose("run", "case", "before") if evaluation else "personal_judgment")
                key = self.permissions._key("head", event_id, purpose)
                previous = deepcopy(self.f.connection.rows[(table, key)])
                qualified = []
                def qualify(barrier):
                    qualified.append(True)
                    change()
                try:
                    with patch.object(self.f.objects.backend, "get_object", side_effect=AssertionError("private I/O")):
                        with self.assertRaises(PermissionError):
                            self.prepare(before_private_assembly=qualify,
                                approval_verifier_factory=lambda _: self.fail("withdrawal reached approval factory"))
                    self.assertEqual(qualified, [True])
                finally:
                    self.f.connection.rows[(table, key)] = previous

    def test_four_fresh_boundaries_surround_one_private_read(self):
        prepared = self.prepare(plan=replace(self.plan, state_routes=()))
        guarded = _AuthorizedRuntimeReads(self.f.objects, prepared.metadata_current)
        start = len(self.f.connection.calls)
        result = guarded.get(self.f.references[self.f.source_one.payload_reference])
        self.assertEqual(result, b"fictional source one")
        self.assertEqual(sum(self._terminal(sql) for sql, _ in self.f.connection.calls[start:]), 4)

    def test_ciphertext_callback_withdrawal_is_fresh_before_decryption(self):
        prepared = self.prepare(plan=replace(self.plan, state_routes=()))
        change = self._head_replacement(self.f.source_two.event_id, evaluation=True)
        actual = self.f.objects.backend.get_object
        reads = []
        def read(namespace, object_id):
            sealed = actual(namespace, object_id)
            reads.append(object_id)
            change()
            return sealed
        with patch.object(self.f.objects.backend, "get_object", new=read), \
             patch("flora.selected.object_store.AESGCM", side_effect=AssertionError("decryption after withdrawal")):
            guarded = _AuthorizedRuntimeReads(self.f.objects, prepared.metadata_current)
            with self.assertRaises(PermissionError):
                guarded.get(self.f.references[self.f.source_one.payload_reference])
        self.assertEqual(reads, [self.f.source_one.payload_reference])

    def test_partial_issued_origin_rejects_before_independent_callback_or_private_io(self):
        detached = copy(self.policy)
        callbacks = []
        with patch.object(self.f.objects.backend, "get_object", side_effect=AssertionError("private I/O")):
            with self.assertRaises(PermissionError):
                self.prepare(policy=detached, authority_guard=lambda: callbacks.append(True))
        self.assertEqual(callbacks, [])

    def test_held_values_and_origin_changes_are_checked_after_terminal_callback(self):
        for kind in ("claim_value", "history", "origin"):
            with self.subTest(kind=kind):
                prepared = self.prepare()
                descriptor = selected_phase_authority(self.permissions, "permits")
                old_phase = descriptor._origin.phase
                old_sources = self.history.sources
                old_value = deepcopy(prepared.context.items[0].claim_value)
                changed = False
                def hook(statement, parameters):
                    nonlocal changed
                    if self._terminal(statement) and not changed:
                        changed = True
                        if kind == "claim_value":
                            prepared.context.items[0].claim_value["fictional"] = "late mutation"
                        elif kind == "history":
                            object.__setattr__(self.history, "sources", tuple(reversed(old_sources)))
                        else:
                            descriptor._origin.phase = "after"
                self.sql_hook = hook
                try:
                    with self.assertRaises(PermissionError):
                        prepared.metadata_current()
                    self.assertTrue(changed)
                finally:
                    self.sql_hook = None
                    prepared.context.items[0].claim_value.clear()
                    prepared.context.items[0].claim_value.update(old_value)
                    object.__setattr__(self.history, "sources", old_sources)
                    descriptor._origin.phase = old_phase

    def test_no_json_callback_runs_after_joint_terminal_observation(self):
        prepared = self.prepare()
        actual = context_guard.canonical_json_bytes
        terminal = False
        after = []
        def hook(statement, parameters):
            nonlocal terminal
            if self._terminal(statement):
                terminal = True
        def serialize(value):
            if terminal:
                after.append(value)
                raise AssertionError("JSON callback after terminal")
            return actual(value)
        self.sql_hook = hook
        with patch.object(context_guard, "canonical_json_bytes", new=serialize):
            prepared.metadata_current()
        self.assertTrue(terminal)
        self.assertEqual(after, [])

    def test_delegated_native_authority_helpers_cannot_be_replaced(self):
        effects = []
        class EffectfulDependency:
            def __getattr__(self, name):
                effects.append(name)
            def __call__(self, *args, **kwargs):
                effects.append("factory")
            def get(self, *args):
                effects.append("registry")
        for name in ("SharedSelectedAuthorityFrame", "SelectedHistoryContribution",
                     "phase_contracts", "context_contracts", "_OWNERS"):
            with self.subTest(dependency=name), patch.object(shared_frames, name, EffectfulDependency()):
                with self.assertRaises(PermissionError):
                    shared_frames.create_shared_selected_frame(log=None, policy=None,
                        claims=None, state=None, binding_guard=None)
                self.assertEqual(effects, [])
        prepared = self.prepare()
        with patch.object(prepared, "_verify_authorities", new=lambda **kwargs: None):
            with self.assertRaises(PermissionError):
                prepared.metadata_current()
        with patch.object(context_guard.PreparedCurrentContext, "_verify_authorities", new=lambda *args, **kwargs: None):
            with self.assertRaises(PermissionError):
                prepared.metadata_current()
        with patch.object(context_guard, "_capture_context_authorities", new=lambda **kwargs: ()):
            with patch.object(self.f.objects.backend, "get_object", side_effect=AssertionError("private I/O")):
                with self.assertRaises(PermissionError):
                    self.prepare()

    def test_replaced_owned_frame_parts_reject_before_their_effects_or_independent_callback(self):
        prepared = self.prepare(plan=replace(self.plan, state_routes=()))
        effects = []
        class Effectful:
            def verify(self):
                effects.append("verify")
            def binding(self):
                effects.append("binding")
            def reobserve(self):
                effects.append("physical")
            def verify_final_current_rows(self):
                effects.append("terminal")
        for field in ("_permission_descriptor", "_event_descriptor", "history", "physical",
                      "sample", "_guard_binding"):
            with self.subTest(field=field):
                frame = self._frame(prepared)
                setattr(frame, field, Effectful())
                with self.assertRaises(PermissionError):
                    frame.finish(authority_guard=lambda: effects.append("independent"))
                self.assertEqual(effects, [])

    def test_nested_owned_guard_parts_reject_before_effectful_verifier(self):
        prepared = self.prepare(plan=replace(self.plan, state_routes=()))
        effects = []
        class Effectful:
            def verify(self):
                effects.append("verify")
            def __call__(self):
                effects.append("binding")
        for kind in ("history_guard", "physical_guard", "frame_guard"):
            with self.subTest(kind=kind):
                frame = self._frame(prepared)
                if kind == "history_guard":
                    frame.history._guard_binding = Effectful()
                elif kind == "physical_guard":
                    frame.physical._binding_guard = Effectful()
                else:
                    frame._binding_guard = Effectful()
                with self.assertRaises(PermissionError):
                    frame.finish(authority_guard=lambda: effects.append("independent"))
                self.assertEqual(effects, [])

    def test_late_original_binding_reader_fields_reject_before_metaclass_effect(self):
        prepared = self.prepare(plan=replace(self.plan, state_routes=()))
        function = prepared._bindings_current
        cells = dict(zip(function.__code__.co_freevars, function.__closure__))
        reader = cells["readers"].cell_contents[0]
        original = reader.owner, reader.owner_class
        effects, changed = [], False
        class EffectfulMeta(type):
            def __getattribute__(cls, name):
                if name == "__mro__":
                    effects.append("metaclass")
                return type.__getattribute__(cls, name)
        class EffectfulOwner(metaclass=EffectfulMeta):
            pass
        def hook(statement, parameters):
            nonlocal changed
            if self._terminal(statement) and not changed:
                changed = True
                reader.__dict__.update(owner=EffectfulOwner(), owner_class=EffectfulOwner)
        self.sql_hook = hook
        try:
            with self.assertRaisesRegex(PermissionError, "captured owner fields changed"):
                prepared.metadata_current()
            self.assertTrue(changed)
            self.assertEqual(effects, [])
        finally:
            self.sql_hook = None
            reader.__dict__.update(owner=original[0], owner_class=original[1])

    def test_opaque_independent_guard_and_port_replacements_never_run_equality(self):
        prepared = self.prepare()
        effects, calls = [], []
        class OpaqueGuard:
            def __call__(self):
                calls.append("independent")
            def __eq__(self, other):
                effects.append("equality")
                raise AssertionError("opaque authority equality callback")
            def __ne__(self, other):
                effects.append("inequality")
                raise AssertionError("opaque authority inequality callback")
        prepared.authority_guard = OpaqueGuard()
        prepared.metadata_current()
        self.assertEqual(calls, ["independent", "independent"])
        self.assertEqual(effects, [])
        original_guard = prepared.authority_guard
        changed = False
        def hook(statement, parameters):
            nonlocal changed
            if self._terminal(statement) and not changed:
                changed = True
                prepared.authority_guard = OpaqueGuard()
        self.sql_hook = hook
        try:
            with self.assertRaises(PermissionError):
                prepared.metadata_current()
            self.assertTrue(changed)
            self.assertEqual(effects, [])
        finally:
            self.sql_hook = None
            prepared.authority_guard = original_guard
        original_port = prepared.policy.allow_event
        changed = False
        def port_hook(statement, parameters):
            nonlocal changed
            if self._terminal(statement) and not changed:
                changed = True
                prepared.policy.allow_event = OpaqueGuard()
        self.sql_hook = port_hook
        try:
            with self.assertRaises(PermissionError):
                prepared.metadata_current()
            self.assertTrue(changed)
            self.assertEqual(effects, [])
        finally:
            self.sql_hook = None
            prepared.policy.allow_event = original_port

    def test_physical_mutation_after_reobservation_rejects_even_with_matching_mutated_signatures(self):
        prepared = self.prepare(plan=replace(self.plan, state_routes=()))
        unselected = self.f.source_two.event_id
        self.assertNotIn(unselected, {item.event_id for item in prepared.source_authorities})
        for kind in ("entry", "commitment", "matching_signatures", "replaced_maps"):
            with self.subTest(kind=kind):
                frame = self._frame(prepared)
                original_entry = frame.physical._entries[unselected]
                original_commitment = frame.physical._commitments[unselected]
                original_digest = original_entry.event.content_digest
                original_event_sha256 = original_commitment.event_sha256
                changed = False
                def hook(statement, parameters):
                    nonlocal changed
                    if self._terminal(statement) and not changed:
                        changed = True
                        physical = frame.physical
                        entry, commitment = physical._entries[unselected], physical._commitments[unselected]
                        if kind == "commitment":
                            object.__setattr__(commitment, "event_sha256", "e" * 64)
                        elif kind == "replaced_maps":
                            physical._entries = dict(physical._entries)
                            physical._commitments = dict(physical._commitments)
                            physical._signatures = dict(physical._signatures)
                        else:
                            object.__setattr__(entry.event, "content_digest", "e" * 64)
                            if kind == "matching_signatures":
                                physical._signatures[unselected] = (
                                    _native_snapshot(commitment), shared_frames._entry_snapshot(entry))
                self.sql_hook = hook
                try:
                    with self.assertRaises(PermissionError):
                        frame.finish()
                    self.assertTrue(changed)
                finally:
                    self.sql_hook = None
                    object.__setattr__(original_entry.event, "content_digest", original_digest)
                    object.__setattr__(original_commitment, "event_sha256", original_event_sha256)

    def test_late_prepared_class_getter_change_rejects_before_effectful_getter(self):
        prepared = self.prepare()
        effects, changed = [], False
        def getter(owner, name):
            effects.append(name)
            return object.__getattribute__(owner, name)
        def hook(statement, parameters):
            nonlocal changed
            if self._terminal(statement) and not changed:
                changed = True
                context_guard.PreparedCurrentContext.__getattribute__ = getter
        self.sql_hook = hook
        try:
            with self.assertRaises(PermissionError):
                prepared.metadata_current()
            self.assertTrue(changed)
            self.assertEqual(effects, [])
        finally:
            self.sql_hook = None
            if "__getattribute__" in vars(context_guard.PreparedCurrentContext):
                del context_guard.PreparedCurrentContext.__getattribute__


if __name__ == "__main__":
    unittest.main()
