"""Bounded source closure with real contracts and controlled selected ports.

Rows use the actual SDK RecordedEvent type and actual selected registry/policy
algorithms. SQL/transport recorders are failure-injection fixtures, not physical
engine consistency, latency, model behavior or scientific phase qualification.
"""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import patch

from cognitive_kernel.canonical import canonical_sha256
from cognitive_kernel.contracts import ProductHostScope
from cognitive_kernel.formation_contracts import FormationEvidenceRef
from flora.selected.experience import KurrentExperienceLog
from flora.selected import source_closure as selected
from flora.selected.source_closure import SelectedSourceClosureResolver

from test_experience_envelope_reuse import record
from test_experience_exact_lookup import BoundedClient
import test_phase_source_fence as fixtures
from metadata_batch_fixture import _Cursor


class SelectedSourceClosureTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PhaseSourceFenceTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f = self.fixture.f
        self.registry, self.permissions = self.fixture.registry, self.fixture.permissions
        self.parent = self.fixture.h.materials[0].event
        self.child = self.fixture.h.materials[-1].event
        self.other = self.fixture.h.materials[1].event
        self.client = BoundedClient([replace(record(event, index),
            recorded_at=datetime(2026, 9, 29, 14, tzinfo=timezone.utc))
            for index, event in enumerate(self.f.log.events)])
        self.log = KurrentExperienceLog(scope=self.f.scope, client=self.client)
        self.resolver = SelectedSourceClosureResolver(registry=self.registry, log=self.log,
            permissions=self.permissions, maximum_sources=2)

    def resolve(self, *, source_ids=None, purpose="personal_judgment"):
        return self.resolver.resolve(source_event_ids=(self.child.event_id,) if source_ids is None else source_ids,
                                     purpose=purpose)

    def write_source(self, event_id, change):
        key = self.registry._key("source", event_id)
        row = self.f.connection.rows[("flora_registered_formation_sources", key)]
        value = json.loads(row["record_json"])
        change(value)
        value["registration_sha256"] = canonical_sha256(
            {"evidence": value["evidence"], "object_ref": value["object_ref"]})
        value["record_sha256"] = canonical_sha256(
            {name: item for name, item in value.items() if name != "record_sha256"})
        row["record_sha256"], row["record_json"] = value["record_sha256"], json.dumps(value)

    def test_returns_only_selected_ordered_parent_metadata_with_no_private_io(self):
        def forbidden(*args, **kwargs):
            raise AssertionError("source closure attempted private I/O")
        before = len(self.f.connection.calls)
        with patch.object(self.f.objects, "get", side_effect=forbidden), \
             patch.object(self.f.objects.backend, "get_object", side_effect=forbidden):
            proof = self.resolve()
        self.assertEqual(proof.domain, "selected-source-closure-v1")
        self.assertEqual(proof.purpose, "personal_judgment")
        self.assertEqual(proof.nominated_event_ids, (self.child.event_id,))
        self.assertEqual({entry.source.evidence.ref_id for entry in proof.commitments},
                         {self.parent.event_id, self.child.event_id})
        self.assertEqual({action.source_ref_id for action in proof.grant_actions},
                         {self.parent.event_id, self.child.event_id})
        self.assertEqual(len(self.client.reads), 4)
        self.assertTrue(all(read["limit"] == 1 and read["stream_position"] is not None
                            and read["resolve_links"] is False for read in self.client.reads))
        terminal = [sql for sql, _ in self.f.connection.calls[before:]
                    if "AS flora_current_metadata_fence LIMIT" in sql]
        self.assertEqual(len(terminal), 1)
        for table in ("flora_registered_formation_sources", "flora_formation_raw_references",
                      "flora_formation_permission_current", "flora_formation_permission_actions"):
            self.assertIn(table, terminal[0])
        self.assertIn("AS flora_current_metadata_fence LIMIT", self.f.connection.calls[-1][0])
        with self.assertRaises(FrozenInstanceError):
            proof.purpose = "provider_disclosure"

    def test_cap_and_input_shape_fail_before_any_read(self):
        before = len(self.f.connection.calls)
        invalid = ((), [self.child.event_id], (self.child.event_id, self.child.event_id),
                   (self.child.event_id, self.parent.event_id, self.other.event_id), (" padded ",))
        for ids in invalid:
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                self.resolve(source_ids=ids)
        for cap in (True, 0, -1, 2.0):
            with self.subTest(cap=cap), self.assertRaises(ValueError):
                SelectedSourceClosureResolver(registry=self.registry, log=self.log,
                    permissions=self.permissions, maximum_sources=cap)
        self.assertEqual(self.client.reads, [])
        self.assertEqual(len(self.f.connection.calls), before)

    def test_discovered_parent_cap_fails_before_parent_or_physical_read(self):
        self.resolver.maximum_sources = 1
        before = len(self.f.connection.calls)
        with self.assertRaisesRegex(PermissionError, "source cap"):
            self.resolve()
        self.assertEqual(self.client.reads, [])
        source_rows = [parameters[0] for sql, parameters in self.f.connection.calls[before:]
                       if "FROM flora_registered_formation_sources" in sql]
        self.assertEqual(source_rows, [self.registry._key("source", self.child.event_id)])

    def test_missing_nominated_or_parent_registration_fails_closed(self):
        for event_id in (self.child.event_id, self.parent.event_id):
            key = ("flora_registered_formation_sources", self.registry._key("source", event_id))
            value = self.f.connection.rows.pop(key)
            try:
                with self.subTest(event_id=event_id), self.assertRaises(PermissionError):
                    self.resolve()
            finally:
                self.f.connection.rows[key] = value

    def test_deleted_parent_position_cannot_be_replaced_by_successor(self):
        position = self.registry.lookup_commitment(self.parent.event_id).stream_position
        self.client.records = [row for row in self.client.records if row.stream_position != position]
        with self.assertRaisesRegex(ValueError, "physical record"):
            self.resolve()

    def test_registered_parent_must_physically_precede_child(self):
        parent_position = self.registry.lookup_commitment(self.parent.event_id).stream_position
        child_position = self.registry.lookup_commitment(self.child.event_id).stream_position
        # Fixture moves real, internally valid envelopes and their registered
        # positions. Exact proofs pass; causal ordering must reject the result.
        self.client.records = [replace(row, stream_position=(
            child_position if row.stream_position == parent_position else
            parent_position if row.stream_position == child_position else row.stream_position))
            for row in self.client.records]
        self.client.records.sort(key=lambda row: row.stream_position)
        self.write_source(self.parent.event_id,
            lambda value: value.update(event_stream_position=child_position))
        self.write_source(self.child.event_id,
            lambda value: value.update(event_stream_position=parent_position))
        with self.assertRaisesRegex(PermissionError, "not earlier"):
            self.resolve()

    def test_self_parent_cycle_rejected_before_physical_read(self):
        self.write_source(self.child.event_id,
            lambda value: value["evidence"].update(parent_refs=[self.child.event_id]))
        with self.assertRaisesRegex(PermissionError, "parent cycle"):
            self.resolve()
        self.assertEqual(self.client.reads, [])

    def test_unrelated_corruption_is_outside_domain_and_old_replay_still_rejects(self):
        position = next(index for index, event in enumerate(self.f.log.events)
                        if event.event_id == self.other.event_id)
        self.client.records[position] = replace(self.client.records[position], data=b"not-json")
        self.assertEqual(len(self.resolve().commitments), 2)
        with self.assertRaises(ValueError):
            self.log.replay_committed()

    def test_wrong_purpose_and_revoked_parent_do_not_reuse_old_proof(self):
        old = self.resolve()
        with self.assertRaises(PermissionError):
            self.resolve(purpose="provider_disclosure")
        self.fixture.grant(self.parent.event_id, "revoke")
        with self.assertRaises(PermissionError):
            self.resolve()
        self.assertEqual(old.domain, "selected-source-closure-v1")

    def test_revocation_during_physical_read_is_seen(self):
        changed = False
        def revoke():
            nonlocal changed
            if not changed:
                changed = True
                self.fixture.grant(self.parent.event_id, "revoke")
        self.client.on_read = revoke
        with self.assertRaises(PermissionError):
            self.resolve()
        self.assertTrue(changed)

    def test_last_permission_callback_withdrawal_of_earlier_source_hits_terminal_fence(self):
        actual = self.permissions.permits
        calls, changed = 0, False
        def permits(source, purpose):
            nonlocal calls, changed
            result = actual(source, purpose)
            calls += 1
            if calls == 4:
                changed = True
                other = self.child if source.evidence.ref_id == self.parent.event_id else self.parent
                self.fixture.grant(other.event_id, "revoke")
            return result
        with patch.object(self.permissions, "permits", new=permits):
            with self.assertRaisesRegex(PermissionError, "terminal current"):
                self.resolve()
        self.assertEqual(calls, 4)
        self.assertTrue(changed)

    def test_last_permission_callback_raw_change_hits_terminal_fence(self):
        actual = self.permissions.permits
        calls = 0
        def permits(source, purpose):
            nonlocal calls
            result = actual(source, purpose)
            calls += 1
            if calls == 4:
                raw_key = self.registry._key("raw", self.parent.payload_reference)
                self.f.connection.rows[("flora_formation_raw_references", raw_key)]["record_sha256"] = "e" * 64
            return result
        with patch.object(self.permissions, "permits", new=permits):
            with self.assertRaisesRegex(PermissionError, "terminal current"):
                self.resolve()

    def test_changed_locator_after_initial_permissions_is_not_hidden_by_samples(self):
        actual = self.permissions.permits
        changed = False
        def permits(source, purpose):
            nonlocal changed
            result = actual(source, purpose)
            if not changed:
                changed = True
                self.write_source(self.child.event_id,
                    lambda value: value.update(event_stream_position=value["event_stream_position"] + 1))
            return result
        with patch.object(self.permissions, "permits", new=permits):
            with self.assertRaisesRegex(PermissionError, "registered locator changed"):
                self.resolve()

    def test_earlier_commit_time_cannot_survive_byte_identical_reappend(self):
        self.resolve()
        position = self.registry.lookup_commitment(self.child.event_id).stream_position
        self.client.records = [replace(row, recorded_at=row.recorded_at + timedelta(seconds=1))
                               if row.stream_position == position else row for row in self.client.records]
        with self.assertRaisesRegex(ValueError, "commit time changed"):
            self.resolve()

    def test_physical_callback_cannot_rebind_resolver_actual_reader(self):
        self.client.on_read = lambda: setattr(self.registry, "lookup_commitment", lambda *_: None)
        with self.assertRaisesRegex(PermissionError, "reader binding changed"):
            self.resolve()

    def test_permission_callback_cannot_rebind_owner_after_true_result(self):
        actual = self.permissions.permits
        def permits(source, purpose):
            result = actual(source, purpose)
            self.permissions.registry = deepcopy(self.registry)
            return result
        with patch.object(self.permissions, "permits", new=permits):
            with self.assertRaisesRegex(PermissionError, "owner binding changed"):
                self.resolve()

    def test_callback_alias_mutation_without_sql_change_is_rejected(self):
        actual = self.permissions.permits
        aliases, count = [], 0
        def permits(source, purpose):
            nonlocal count
            result = actual(source, purpose)
            aliases.append(source)
            count += 1
            if count == 4:
                aliases[0].evidence.__dict__["subject_ref"] = "changed-only-in-memory"
            return result
        with patch.object(self.permissions, "permits", new=permits):
            with self.assertRaisesRegex(PermissionError, "callback observation changed"):
                self.resolve()

    def test_terminal_sql_callback_alias_mutation_is_also_rejected(self):
        actual_permits, actual_execute = self.permissions.permits, self.f.connection.execute
        aliases = []
        def permits(source, purpose):
            aliases.append(source)
            return actual_permits(source, purpose)
        def execute(statement, parameters):
            result = actual_execute(statement, parameters)
            if "AS flora_current_metadata_fence LIMIT" in statement:
                aliases[0].evidence.__dict__["subject_ref"] = "changed-at-terminal-only"
            return result
        with patch.object(self.permissions, "permits", new=permits), \
             patch.object(self.f.connection, "execute", new=execute):
            with self.assertRaisesRegex(PermissionError, "callback observation changed"):
                self.resolve()

    def test_returned_metadata_does_not_alias_predicate_input(self):
        actual = self.permissions.permits
        aliases = []
        def permits(source, purpose):
            aliases.append(source)
            return actual(source, purpose)
        with patch.object(self.permissions, "permits", new=permits):
            proof = self.resolve()
        saved = proof.commitments[0].source.evidence.subject_ref
        for source in aliases:
            source.evidence.__dict__["subject_ref"] = "mutated-after-proof"
        self.assertEqual(proof.commitments[0].source.evidence.subject_ref, saved)

    def test_existing_custom_replay_receiver_is_rejected_without_fallback(self):
        self.log.replay = lambda: []
        with self.assertRaisesRegex(TypeError, "custom replay receiver"):
            self.resolve()

    def test_native_lookup_bound_to_another_owner_is_rejected_before_io(self):
        other = KurrentExperienceLog(scope=self.f.scope, client=BoundedClient(self.client.records))
        self.log.lookup_committed = other.lookup_committed
        before = len(self.f.connection.calls)
        with self.assertRaisesRegex(TypeError, "exact physical lookup protocol"):
            self.resolve()
        self.assertEqual(self.client.reads, [])
        self.assertEqual(other.client.reads, [])
        self.assertEqual(len(self.f.connection.calls), before)

    def test_foreign_bound_lookup_installed_by_physical_callback_is_rejected(self):
        other = KurrentExperienceLog(scope=self.f.scope, client=BoundedClient(self.client.records))
        self.client.on_read = lambda: setattr(self.log, "lookup_committed", other.lookup_committed)
        with self.assertRaisesRegex(PermissionError, "reader binding changed"):
            self.resolve()
        self.assertEqual(other.client.reads, [])

    def test_actual_policy_callback_cannot_install_effectful_contract_helper(self):
        actual_permits = self.permissions.permits
        original = FormationEvidenceRef.metadata_record
        helper_calls = 0
        def effectful(evidence):
            nonlocal helper_calls
            helper_calls += 1
            self.fixture.grant(self.parent.event_id, "revoke")
            return original(evidence)
        def permits(source, purpose):
            result = actual_permits(source, purpose)
            FormationEvidenceRef.metadata_record = effectful
            return result
        try:
            with patch.object(self.permissions, "permits", new=permits):
                with self.assertRaisesRegex(PermissionError, "native contract binding changed"):
                    self.resolve()
        finally:
            FormationEvidenceRef.metadata_record = original
        self.assertEqual(helper_calls, 0)

    def test_terminal_sql_cannot_install_scope_helper_before_old_binding_check(self):
        actual_execute = self.f.connection.execute
        original = ProductHostScope.metadata_record
        helper_calls = 0
        def effectful(scope):
            nonlocal helper_calls
            helper_calls += 1
            self.fixture.grant(self.parent.event_id, "revoke")
            return original(scope)
        def execute(statement, parameters):
            result = actual_execute(statement, parameters)
            if "AS flora_current_metadata_fence LIMIT" in statement:
                ProductHostScope.metadata_record = effectful
            return result
        try:
            with patch.object(self.f.connection, "execute", new=execute):
                with self.assertRaisesRegex(PermissionError, "native contract binding changed"):
                    self.resolve()
        finally:
            ProductHostScope.metadata_record = original
        self.assertEqual(helper_calls, 0)

    def test_terminal_sql_cannot_replace_transport_row_hydration_helper(self):
        actual_execute = self.f.connection.execute
        original = selected._rows
        helper_calls = 0
        def effectful(cursor):
            nonlocal helper_calls
            helper_calls += 1
            self.fixture.grant(self.parent.event_id, "revoke")
            return original(cursor)
        def execute(statement, parameters):
            result = actual_execute(statement, parameters)
            if "AS flora_current_metadata_fence LIMIT" in statement:
                selected._rows = effectful
            return result
        try:
            with patch.object(self.f.connection, "execute", new=execute):
                with self.assertRaisesRegex(PermissionError, "row reader code changed"):
                    self.resolve()
        finally:
            selected._rows = original
        self.assertEqual(helper_calls, 0)

    def test_terminal_row_values_require_exact_primitive_types_before_comparison(self):
        actual_execute = self.f.connection.execute
        comparisons = 0
        class EffectfulString(str):
            def __eq__(self, other):
                nonlocal comparisons
                comparisons += 1
                raise AssertionError("effectful equality was invoked")
            __hash__ = str.__hash__
        def execute(statement, parameters):
            cursor = actual_execute(statement, parameters)
            if "AS flora_current_metadata_fence LIMIT" not in statement:
                return cursor
            names = [item.name for item in cursor.description]
            rows = [dict(zip(names, values)) for values in cursor.fetchall()]
            rows[0]["fence_kind"] = EffectfulString(rows[0]["fence_kind"])
            return _Cursor(rows)
        with patch.object(self.f.connection, "execute", new=execute):
            with self.assertRaisesRegex(PermissionError, "nonprimitive metadata"):
                self.resolve()
        self.assertEqual(comparisons, 0)

    def test_new_domain_rejects_even_formatting_only_terminal_record_rewrite(self):
        actual_execute = self.f.connection.execute
        def execute(statement, parameters):
            cursor = actual_execute(statement, parameters)
            if "AS flora_current_metadata_fence LIMIT" not in statement:
                return cursor
            names = [item.name for item in cursor.description]
            rows = [dict(zip(names, values)) for values in cursor.fetchall()]
            rows[0]["record_json"] = "\n" + rows[0]["record_json"]
            return _Cursor(rows)
        with patch.object(self.f.connection, "execute", new=execute):
            with self.assertRaisesRegex(PermissionError, "terminal current"):
                self.resolve()

    def test_overlapping_nominations_do_not_duplicate_canonical_reads(self):
        proof = self.resolve(source_ids=(self.child.event_id, self.parent.event_id))
        self.assertEqual(proof.nominated_event_ids, (self.child.event_id, self.parent.event_id))
        self.assertEqual(len(proof.commitments), 2)
        self.assertEqual(len(self.client.reads), 4)

    def test_new_call_observes_new_grant_generation(self):
        first = self.resolve()
        self.fixture.grant(self.parent.event_id, "allow")
        second = self.resolve()
        old_action = next(action for action in first.grant_actions if action.source_ref_id == self.parent.event_id)
        new_action = next(action for action in second.grant_actions if action.source_ref_id == self.parent.event_id)
        self.assertEqual(new_action.generation, old_action.generation + 1)
        self.assertNotEqual(new_action.action_sha256, old_action.action_sha256)
        self.assertEqual(len(self.client.reads), 8)

    def test_terminal_alias_custom_dictionary_key_is_rejected_without_hash_callback(self):
        actual_permits, actual_execute = self.permissions.permits, self.f.connection.execute
        aliases, hashes = [], 0
        class EffectfulKey(str):
            def __hash__(self):
                nonlocal hashes
                hashes += 1
                return str.__hash__(self)
        def permits(source, purpose):
            aliases.append(source)
            return actual_permits(source, purpose)
        def execute(statement, parameters):
            result = actual_execute(statement, parameters)
            if "AS flora_current_metadata_fence LIMIT" in statement:
                fields = aliases[0].evidence.__dict__
                value = fields.pop("subject_ref")
                fields[EffectfulKey("subject_ref")] = value
            return result
        with patch.object(self.permissions, "permits", new=permits), \
             patch.object(self.f.connection, "execute", new=execute):
            with self.assertRaisesRegex(PermissionError, "native metadata fields changed"):
                self.resolve()
        # The one insertion hash occurs inside the injected transport callback.
        # The postterminal snapshot must reject the key without hashing it.
        self.assertEqual(hashes, 1)

    def test_terminal_alias_custom_metaclass_is_rejected_without_class_callbacks(self):
        actual_permits, actual_execute = self.permissions.permits, self.f.connection.execute
        aliases, class_callbacks = [], 0
        class EffectfulMeta(type):
            def __hash__(cls):
                nonlocal class_callbacks
                class_callbacks += 1
                return type.__hash__(cls)
            def __eq__(cls, other):
                nonlocal class_callbacks
                class_callbacks += 1
                return type.__eq__(cls, other)
        class EffectfulValue(metaclass=EffectfulMeta):
            pass
        def permits(source, purpose):
            aliases.append(source)
            return actual_permits(source, purpose)
        def execute(statement, parameters):
            result = actual_execute(statement, parameters)
            if "AS flora_current_metadata_fence LIMIT" in statement:
                aliases[0].evidence.__dict__["subject_ref"] = EffectfulValue()
            return result
        with patch.object(self.permissions, "permits", new=permits), \
             patch.object(self.f.connection, "execute", new=execute):
            with self.assertRaisesRegex(PermissionError, "nonnative metadata class"):
                self.resolve()
        self.assertEqual(class_callbacks, 0)


if __name__ == "__main__":
    unittest.main()
