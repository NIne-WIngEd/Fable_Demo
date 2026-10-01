"""Selected private context with controlled SDK/SQL, never a model/latency win."""

from copy import copy, deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
import unittest
from unittest.mock import patch

from cognitive_kernel.canonical import canonical_sha256
from flora.selected import claims as claim_tables
from flora.selected import context_guard as context_guards
from flora.selected import phase_source_fence as phase_fences
from flora.selected.context import ContextPlan, StateRoute
from flora.selected.experience import KurrentExperienceLog
from flora.selected.judgment_context import RegisteredJudgmentContextPolicy
from flora.selected.native_phase_gate import install_native_phase_gate, transfer_native_phase_gate
from flora.selected.personal_state import _ACTIVE, _VERSIONS
from flora.selected.selected_context import (SelectedContextLogView, SelectedJudgmentContextPolicy,
                                            prepare_selected_current_context)

import test_current_context_guard as fixtures
from test_experience_envelope_reuse import record
from test_experience_exact_lookup import BoundedClient


class SelectedContextTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.SelectedCurrentContextTerminalFenceTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f, self.state = self.fixture.f, self.fixture.state
        self.claims, self.claim_id, self.claim_current = self.fixture.claim_fixture()
        self.registry, self.permissions = self.fixture.h.registry, self.fixture.h.permissions
        self.client = BoundedClient([replace(record(event, index),
            recorded_at=datetime(2026, 9, 29, 14, tzinfo=timezone.utc))
            for index, event in enumerate(self.f.log.events)])
        self.log = KurrentExperienceLog(scope=self.f.scope, client=self.client)
        self.policy = RegisteredJudgmentContextPolicy(claims=self.claims, state=self.state,
            log=self.log, registry=self.registry, permissions=self.permissions)
        self.plan = ContextPlan("selected-context-fixture", "personal_judgment",
            exact_claim_ids=(self.claim_id,), state_routes=(StateRoute(**self.f.identity()),),
            minimum_claims=1)

    def prepare(self, **kwargs):
        return prepare_selected_current_context(plan=kwargs.pop("plan", self.plan),
            claims=self.claims, state=self.state, log=self.log, objects=self.f.objects,
            references=self.f.references, policy=self.policy, maximum_sources=kwargs.pop("maximum_sources", 8),
            approval_verifier_factory=kwargs.pop("approval_verifier_factory", lambda _: self.f.verifier), **kwargs)

    def test_actual_selected_claim_and_governed_state_have_explicit_finite_domain(self):
        prepared = self.prepare()
        self.assertIs(type(prepared.log), SelectedContextLogView)
        self.assertIs(type(prepared.policy), SelectedJudgmentContextPolicy)
        self.assertEqual(prepared.log.domain, "selected-current-context-v1")
        self.assertEqual(prepared.log.resolver.log, self.log)
        self.assertEqual([item.kind for item in prepared.context.items], ["claim", "state:owner"])
        self.assertEqual(prepared.context.items[0].content, b"fictional source one")
        self.assertEqual(prepared.context.items[1].content, b"fictional supplied state 1")
        selected_positions = {self.registry.lookup_commitment(source.event_id).stream_position
            for source in prepared.source_authorities}
        self.assertEqual({read["stream_position"] for read in self.client.reads}, selected_positions)
        self.assertTrue(all(read["limit"] == 1 and read["resolve_links"] is False for read in self.client.reads))
        self.assertFalse(hasattr(prepared.log, "append"))
        self.assertFalse(hasattr(prepared.log, "replay_committed"))

    def test_unrelated_corruption_is_not_a_selected_context_proof_and_default_replay_rejects_it(self):
        position = next(index for index, event in enumerate(self.f.log.events)
                        if event.event_id == self.f.source_two.event_id)
        self.client.records[position] = replace(self.client.records[position], data=b"not-json")
        claim_only = replace(self.plan, state_routes=())
        prepared = self.prepare(plan=claim_only)
        self.assertEqual(prepared.context.items[0].content, b"fictional source one")
        self.assertNotIn(position, {read["stream_position"] for read in self.client.reads})
        with self.assertRaises(ValueError):
            self.log.replay()

    def test_revalidation_retains_content_but_rechecks_actual_purpose_authority(self):
        prepared = self.prepare()
        start = len(self.client.reads)
        with patch.object(self.f.objects.backend, "get_object", side_effect=AssertionError("private reopen forbidden")):
            prepared.revalidate()
            self.assertGreater(len(self.client.reads), start)
        self.fixture.h.grant(self.f.source_one.event_id, "revoke")
        with patch.object(self.f.objects.backend, "get_object", side_effect=AssertionError("private reopen forbidden")):
            with self.assertRaises(PermissionError):
                prepared.metadata_current()

    def test_current_claim_quarantine_refuses_held_selected_content(self):
        prepared = self.prepare()
        changed = deepcopy(self.claim_current)
        changed["deletion_state"] = "pending_delete"
        self.f.connection.rows[(claim_tables._CURRENT, self.claims._row_id(self.claim_id))]["record_json"] = json.dumps(changed)
        with patch.object(self.f.objects.backend, "get_object", side_effect=AssertionError("private reopen forbidden")):
            with self.assertRaises((ValueError, PermissionError)):
                prepared.revalidate()

    def test_owner_approval_remains_live_in_selected_route(self):
        prepared = self.prepare()
        self.f.proofs.clear()
        with self.assertRaises(PermissionError):
            prepared.revalidate()

    def test_exact_registered_physical_target_disappearing_refuses_held_content(self):
        prepared = self.prepare()
        position = self.registry.lookup_commitment(self.f.source_one.event_id).stream_position
        self.client.records = [row for row in self.client.records if row.stream_position != position]
        with self.assertRaises((ValueError, PermissionError)):
            prepared.metadata_current()

    def test_unknown_original_policy_callbacks_reject_before_private_or_physical_io(self):
        for name in ("allow_event", "allow_claim", "allow_state"):
            with self.subTest(port=name), patch.object(self.policy, name, return_value=False), \
                 patch.object(self.f.objects.backend, "get_object", side_effect=AssertionError("private I/O forbidden")):
                with self.assertRaises(TypeError):
                    self.prepare()
        self.assertEqual(self.client.reads, [])

    def test_original_policy_class_changes_cannot_qualify_as_the_canonical_route(self):
        for name in ("allow_event", "allow_claim", "allow_state"):
            with self.subTest(port=name), patch.object(RegisteredJudgmentContextPolicy, name,
                                                       new=lambda *args: False):
                with self.assertRaisesRegex(TypeError, "canonical policy implementation"):
                    self.prepare()
        self.assertEqual(self.client.reads, [])

    def test_known_source_phase_gate_is_transferred_and_remains_current(self):
        active, calls = True, []
        def phase_now():
            calls.append("phase")
            return active
        def member(event_id):
            calls.append(event_id)
            return True
        install_native_phase_gate(self.policy, "allow_event",
            canonical_predicate=RegisteredJudgmentContextPolicy.allow_event,
            phase_now=phase_now, phase_member=member)
        prepared = self.prepare()
        self.assertTrue(calls)
        active = False
        with self.assertRaises(PermissionError):
            prepared.metadata_current()

    def test_original_policy_reader_rebinding_after_prepare_refuses_selected_context(self):
        prepared = self.prepare()
        self.policy.allow_claim = lambda *_: True
        with self.assertRaises(PermissionError):
            prepared.metadata_current()

    def test_initial_terminal_head_change_is_rejected_before_private_assembly(self):
        actual = self.f.connection.execute
        changed = False
        head_key = (_ACTIVE, self.state._head_id(**self.f.identity()))
        def execute(statement, parameters):
            nonlocal changed
            if ") AS flora_selected_context_fence LIMIT" in statement and not changed:
                changed = True
                self.f.connection.rows[head_key]["version_id"] = "late-selected-state-head"
            return actual(statement, parameters)
        with patch.object(self.f.connection, "execute", new=execute), \
             patch.object(self.f.objects.backend, "get_object", side_effect=AssertionError("private I/O forbidden")):
            with self.assertRaisesRegex(PermissionError, "terminal selected context"):
                self.prepare()
        self.assertTrue(changed)

    def test_repeated_terminal_state_change_is_jointly_rejected_with_source_authority(self):
        prepared = self.prepare()
        actual = self.f.connection.execute
        changed = False
        head_key = (_ACTIVE, self.state._head_id(**self.f.identity()))
        def execute(statement, parameters):
            nonlocal changed
            if ") AS flora_selected_context_fence LIMIT" in statement and not changed:
                changed = True
                self.f.connection.rows[head_key]["approval_event_sha256"] = "e" * 64
            return actual(statement, parameters)
        with patch.object(self.f.connection, "execute", new=execute), \
             patch.object(self.f.objects.backend, "get_object", side_effect=AssertionError("private reopen forbidden")):
            with self.assertRaisesRegex(PermissionError, "terminal selected context"):
                prepared.metadata_current()
        self.assertTrue(changed)

    def test_late_immutable_claim_and_relation_changes_are_part_of_the_same_terminal_basis(self):
        for table in (claim_tables._VERSIONS, claim_tables._EVIDENCE):
            with self.subTest(table=table):
                prepared = self.prepare(plan=replace(self.plan, state_routes=()))
                captured = prepared.claim_authorities[0]
                record_id = captured.version_id if table == claim_tables._VERSIONS else captured.evidence_records[0][0]
                key = table, self.claims._row_id(record_id)
                prior = deepcopy(self.f.connection.rows[key])
                actual = self.f.connection.execute
                changed = False
                def execute(statement, parameters):
                    nonlocal changed
                    if ") AS flora_selected_context_fence LIMIT" in statement and not changed:
                        changed = True
                        self.f.connection.rows[key]["record_json"] = "\n" + self.f.connection.rows[key]["record_json"]
                    return actual(statement, parameters)
                try:
                    with patch.object(self.f.connection, "execute", new=execute), \
                         patch.object(self.f.objects.backend, "get_object", side_effect=AssertionError("private reopen forbidden")):
                        with self.assertRaisesRegex(PermissionError, "terminal selected context"):
                            prepared.metadata_current()
                    self.assertTrue(changed)
                finally:
                    self.f.connection.rows[key] = prior

    def test_no_json_helper_can_revoke_a_source_after_the_terminal_context_observation(self):
        prepared = self.prepare()
        for module in (context_guards, phase_fences):
            with self.subTest(helper_module=module.__name__):
                actual_execute, actual_json = self.f.connection.execute, module.canonical_json_bytes
                armed, revoked, before_calls, after_calls = False, False, 0, 0
                def execute(statement, parameters):
                    nonlocal armed
                    cursor = actual_execute(statement, parameters)
                    if ") AS flora_selected_context_fence LIMIT" in statement:
                        armed = True
                    return cursor
                def effectful_json(value):
                    nonlocal revoked, before_calls, after_calls
                    if armed:
                        after_calls += 1
                        if not revoked:
                            revoked = True
                            self.fixture.h.grant(self.f.source_one.event_id, "revoke")
                    else:
                        before_calls += 1
                    return actual_json(value)
                with patch.object(self.f.connection, "execute", new=execute), \
                     patch.object(module, "canonical_json_bytes", new=effectful_json):
                    prepared.metadata_current()
                self.assertTrue(armed)
                self.assertGreater(before_calls, 0, "the repro must exercise the helper before the terminal fence")
                self.assertEqual(after_calls, 0)
                self.assertFalse(revoked)
                self.assertEqual(self.permissions.current_action(self.f.source_one.event_id,
                    "personal_judgment").decision, "allow")

    def test_terminal_held_content_items_and_claim_value_mutations_are_rejected(self):
        for kind in ("content", "items", "claim_value"):
            with self.subTest(material=kind):
                prepared = self.prepare(plan=replace(self.plan, state_routes=()))
                actual = self.f.connection.execute
                changed = False
                def execute(statement, parameters):
                    nonlocal changed
                    cursor = actual(statement, parameters)
                    if ") AS flora_selected_context_fence LIMIT" in statement and not changed:
                        changed = True
                        if kind == "content":
                            object.__setattr__(prepared.context.items[0], "content", b"unverified terminal context mutation")
                        elif kind == "items":
                            object.__setattr__(prepared.context, "items", ())
                        else:
                            prepared.context.items[0].claim_value["fictional"] = "unverified terminal value"
                    return cursor
                with patch.object(self.f.connection, "execute", new=execute):
                    with self.assertRaisesRegex(PermissionError, "held private context changed"):
                        prepared.metadata_current()
                self.assertTrue(changed)

    def test_terminal_custom_claim_keys_reject_without_effectful_hash_or_equality(self):
        prepared = self.prepare(plan=replace(self.plan, state_routes=()))
        actual = self.f.connection.execute
        hashes, equalities = 0, 0
        class EffectfulKey(str):
            def __hash__(self):
                nonlocal hashes
                hashes += 1
                return str.__hash__(self)
            def __eq__(self, other):
                nonlocal equalities
                equalities += 1
                return str.__eq__(self, other)
        changed = False
        def execute(statement, parameters):
            nonlocal changed
            cursor = actual(statement, parameters)
            if ") AS flora_selected_context_fence LIMIT" in statement and not changed:
                changed = True
                prepared.context.items[0].claim_value[EffectfulKey("new-terminal-key")] = "unverified"
            return cursor
        with patch.object(self.f.connection, "execute", new=execute):
            with self.assertRaisesRegex(PermissionError, "nonnative dictionary keys"):
                prepared.metadata_current()
        self.assertTrue(changed)
        self.assertEqual(hashes, 1, "only the injected dictionary insertion may hash the custom key")
        self.assertEqual(equalities, 0)

    def test_selected_claim_subclass_rejects_before_source_and_private_io(self):
        class CustomClaimAuthority(claim_tables.XTDBClaimAuthority):
            pass
        custom = CustomClaimAuthority(scope=self.f.scope, authority_namespace_id=self.f.namespace,
                                      connection=self.f.connection)
        policy = RegisteredJudgmentContextPolicy(claims=custom, state=self.state, log=self.log,
            registry=self.registry, permissions=self.permissions)
        with patch.object(self.f.objects.backend, "get_object", side_effect=AssertionError("private I/O forbidden")):
            with self.assertRaises(TypeError):
                prepare_selected_current_context(plan=self.plan, claims=custom, state=self.state, log=self.log,
                    objects=self.f.objects, references=self.f.references, policy=policy, maximum_sources=8,
                    approval_verifier_factory=lambda _: self.f.verifier)
        self.assertEqual(self.client.reads, [])

    def test_episode_state_is_explicitly_unsupported_before_private_or_physical_io(self):
        key = self.state._head_id(**self.f.identity())
        head = self.state._fetch(_ACTIVE, key)
        row = self.f.connection.rows[(_VERSIONS, self.state._version_id(head["version_id"]))]
        value = json.loads(row["record_json"])
        value["source_episode_ids"] = ["unresolved-episode"]
        value["envelope"]["source_records"] = sorted(value["envelope"]["source_records"] + ["unresolved-episode"])
        value["envelope"]["envelope_sha256"] = canonical_sha256({name: item for name, item in value["envelope"].items()
                                                                if name != "envelope_sha256"})
        value["projection_sha256"] = canonical_sha256({name: item for name, item in value.items()
                                                     if name != "projection_sha256"})
        row["record_json"] = json.dumps(value)
        row["projection_sha256"] = value["projection_sha256"]
        self.f.connection.rows[(_ACTIVE, key)]["projection_sha256"] = value["projection_sha256"]
        with patch.object(self.f.objects.backend, "get_object", side_effect=AssertionError("private I/O forbidden")):
            with self.assertRaisesRegex(ValueError, "episode lineage"):
                self.prepare()
        self.assertEqual(self.client.reads, [])

    def test_finite_cap_and_unfrozen_routes_reject_before_private_io(self):
        for cap in (True, 0, -1):
            with self.subTest(cap=cap), self.assertRaises(ValueError):
                self.prepare(maximum_sources=cap)
        with self.assertRaises(PermissionError):
            self.prepare(maximum_sources=1)
        with self.assertRaisesRegex(ValueError, "frozen exact routes"):
            self.prepare(plan=replace(self.plan, query_vector=(1.0,), vector_limit=1))
        self.assertEqual(self.client.reads, [])


class NativePhaseTransferTest(unittest.TestCase):
    def fixture(self, phase_now=lambda: True, phase_member=lambda _: True):
        class Original:
            def allow_event(self, event_id, purpose):
                return True
        class Selected:
            def allow_event(self, event_id, purpose):
                return True
        source, target = Original(), Selected()
        install_native_phase_gate(source, "allow_event", canonical_predicate=Original.allow_event,
                                  phase_now=phase_now, phase_member=phase_member)
        return source, target, Original, Selected

    def transfer(self, source, target, Original, Selected):
        return transfer_native_phase_gate(source, "allow_event", target,
            expected_original_predicate=Original.allow_event, selected_predicate=Selected.allow_event)

    def test_mutable_configuration_attribute_cannot_override_actual_denying_phase(self):
        source, target, Original, Selected = self.fixture(phase_now=lambda: False)
        source.allow_event.__func__._native_phase_configuration = (
            source, "allow_event", Original.allow_event.__get__(source), Original.allow_event,
            lambda: True, lambda _: True, source.allow_event)
        self.transfer(source, target, Original, Selected)
        self.assertIs(target.allow_event("source", "personal_judgment"), False)

    def test_actual_phase_cell_mutation_during_callback_is_rejected(self):
        source = None
        def phase_now():
            cells = dict(zip(source.allow_event.__func__.__code__.co_freevars,
                             source.allow_event.__func__.__closure__))
            cells["phase_member"].cell_contents = lambda _: True
            return True
        source, target, Original, Selected = self.fixture(phase_now=phase_now)
        self.transfer(source, target, Original, Selected)
        with self.assertRaises(PermissionError):
            target.allow_event("source", "personal_judgment")

    def test_selected_algorithm_code_change_during_phase_is_rejected(self):
        Selected = None
        def phase_now():
            Selected.allow_event.__code__ = (lambda self, event_id, purpose: True).__code__
            return True
        source, target, Original, Selected = self.fixture(phase_now=phase_now)
        self.transfer(source, target, Original, Selected)
        with self.assertRaises(PermissionError):
            target.allow_event("source", "personal_judgment")

    def test_original_installed_gate_replacement_is_rejected(self):
        source = None
        def phase_now():
            source.allow_event = lambda *_: True
            return True
        source, target, Original, Selected = self.fixture(phase_now=phase_now)
        self.transfer(source, target, Original, Selected)
        with self.assertRaises(PermissionError):
            target.allow_event("source", "personal_judgment")


if __name__ == "__main__":
    unittest.main()
