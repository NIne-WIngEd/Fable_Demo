"""Selected history with actual contracts and controlled physical transports.

These are custody/permission tests, not backend latency or learned behavior.
"""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import patch

from cognitive_kernel.canonical import canonical_sha256
from flora.selected.comparison_custody import SelectedRunEvidencePolicy, evaluation_purpose
from flora.selected.experience import KurrentExperienceLog
from flora.selected.history_fence import verify_history_and_external_metadata
from flora.selected.selected_history_fence import verify_selected_history_metadata, selected_phase_member
from test_experience_envelope_reuse import record
from test_experience_exact_lookup import BoundedClient
import test_history_fence as fixtures


class SelectedHistoryFenceTest(unittest.TestCase):
    def setUp(self):
        self.h = fixtures.HistoryFenceTest()
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.f = self.h.f
        self.client = BoundedClient([replace(record(event, index),
            recorded_at=datetime(2026, 9, 29, 14, tzinfo=timezone.utc))
            for index, event in enumerate(self.f.log.events)])
        self.log = KurrentExperienceLog(scope=self.f.scope, client=self.client)
        self.h.custody.log = self.log
        self.policy = SelectedRunEvidencePolicy(custody=self.h.custody, run_id="run",
            permissions=self.h.permissions, history_metadata_domain="selected-history-metadata-v1",
            maximum_history_sources=16)

    def verify(self, phase="before", history=None, **kwargs):
        return verify_selected_history_metadata(policy=self.policy, case_id="case", phase=phase,
            history=self.h.before if history is None else history, **kwargs)

    def row(self, table, key):
        return self.f.connection.rows[(table, key)]

    def write_source(self, event_id, change):
        row = self.row("flora_registered_formation_sources", self.h.registry._key("source", event_id))
        value = json.loads(row["record_json"])
        change(value)
        value["registration_sha256"] = canonical_sha256(
            {"evidence": value["evidence"], "object_ref": value["object_ref"]})
        value["record_sha256"] = canonical_sha256({key: item for key, item in value.items()
            if key != "record_sha256"})
        row["record_sha256"], row["record_json"] = value["record_sha256"], json.dumps(value)

    def test_selected_metadata_reconstructs_both_phases_without_private_reads_or_full_replay(self):
        actual = self.client.get_stream
        def bounded(**kwargs):
            self.assertEqual(kwargs.get("limit"), 1)
            self.assertIsNotNone(kwargs.get("stream_position"))
            self.assertIs(kwargs.get("resolve_links"), False)
            return actual(**kwargs)
        with patch.object(self.client, "get_stream", side_effect=bounded), \
             patch.object(self.h.custody.raw_custody, "read", side_effect=AssertionError("private read")), \
             patch.object(self.f.objects, "get", side_effect=AssertionError("plaintext read")):
            for phase, history in (("before", self.h.before), ("after", self.h.after)):
                start = len(self.f.connection.calls)
                proof = self.verify(phase, history)
                self.assertEqual(proof.domain, "selected-history-metadata-v1")
                self.assertEqual(proof.history_sha256, history.digest())
                self.assertEqual(tuple(source.event_id for source in proof.sources), history.event_ids)
                self.assertIn("AS flora_current_metadata_fence", self.f.connection.calls[-1][0])
                terminal = [sql for sql, _ in self.f.connection.calls[start:]
                    if "AS flora_current_metadata_fence" in sql]
                self.assertEqual(len(terminal), 1)
                self.assertIn("flora_comparison_artifacts", terminal[0])

    def test_replaced_physical_reader_cannot_invent_a_selected_target_proof(self):
        actual = self.log.lookup_committed
        with patch.object(self.log, "lookup_committed", side_effect=actual):
            with self.assertRaises(TypeError):
                self.verify()
            with self.assertRaises(TypeError):
                self.h.custody.metadata_selected("run", "history:case:before")
            with self.assertRaises(TypeError):
                selected_phase_member(registry=self.h.registry, log=self.log,
                    permissions=self.h.permissions, originals={source.event.event_id: source.event
                        for source in self.h.before.sources}, maximum_sources=16,
                    event_id=self.h.before.event_ids[0])

    def test_policy_dispatch_is_explicit_and_default_route_still_scans(self):
        self.assertTrue(self.policy.authorize_history_metadata(case_id="case", phase="before", history=self.h.before))
        self.assertTrue(all(item["limit"] == 1 for item in self.client.reads))
        self.client.reads.clear()
        self.assertTrue(self.h.policy.authorize_history_metadata(case_id="case", phase="before", history=self.h.before))
        self.assertTrue(any(item["stream_position"] is None for item in self.client.reads))

    def test_selected_domain_preserves_full_initial_private_authentication(self):
        with patch.object(self.h.custody.raw_custody, "read", wraps=self.h.custody.raw_custody.read) as reads:
            self.assertTrue(self.policy.authorize_history(case_id="case", phase="before", history=self.h.before))
        self.assertEqual(reads.call_count, len(self.h.before.sources))

    def test_manifest_does_not_need_an_invented_evaluation_grant(self):
        manifest = self.h.custody.metadata_selected("run", "history:case:before")
        purpose = evaluation_purpose("run", "case", "before")
        self.assertIsNone(self.h.permissions.current_action(manifest.artifact.event_id, purpose))
        self.assertEqual(self.verify().manifest_sha256, manifest.artifact.record["content_sha256"])

    def test_cap_and_invalid_domain_fail_before_selected_reads(self):
        self.policy.maximum_history_sources = 2
        before = len(self.f.connection.calls)
        with self.assertRaisesRegex(PermissionError, "source cap"):
            self.verify()
        self.assertEqual(len(self.f.connection.calls), before)
        self.assertEqual(self.client.reads, [])
        for values in ({"history_metadata_domain": "unknown"},
                       {"maximum_history_sources": 10},
                       {"history_metadata_domain": "selected-history-metadata-v1", "maximum_history_sources": True},
                       {"history_metadata_domain": "selected-history-metadata-v1", "maximum_history_sources": None}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                SelectedRunEvidencePolicy(custody=self.h.custody, run_id="run", permissions=self.h.permissions, **values)

    def test_unrelated_corruption_is_explicitly_outside_selected_domain(self):
        selected_ids = set(self.h.before.event_ids)
        manifest = self.h.custody.metadata_selected("run", "history:case:before").artifact.event_id
        index = next(index for index, event in enumerate(self.f.log.events)
            if event.event_id not in selected_ids | {manifest})
        self.client.records[index] = replace(self.client.records[index], data=b"invalid unrelated envelope")
        self.verify()
        self.assertFalse(self.h.policy.authorize_history_metadata(case_id="case", phase="before", history=self.h.before))

    def test_missing_original_or_manifest_position_fails_closed(self):
        manifest = self.h.custody.metadata_selected("run", "history:case:before").artifact.event_id
        for event_id in (self.h.before.event_ids[0], manifest):
            original = list(self.client.records)
            position = self.h.registry.lookup_commitment(event_id).stream_position
            self.client.records = [row for row in original if row.stream_position != position]
            try:
                with self.subTest(event_id=event_id), self.assertRaises(ValueError):
                    self.verify()
            finally:
                self.client.records = original

    def test_recreated_original_with_different_commit_time_fails_closed(self):
        position = self.h.registry.lookup_commitment(self.h.before.event_ids[0]).stream_position
        self.client.records[position] = replace(self.client.records[position],
            recorded_at=self.client.records[position].recorded_at + timedelta(seconds=1))
        with self.assertRaises(ValueError):
            self.verify()

    def test_original_after_manifest_position_is_rejected(self):
        original_id = self.h.before.event_ids[0]
        manifest_id = self.h.custody.metadata_selected("run", "history:case:before").artifact.event_id
        a, b = (self.h.registry.lookup_commitment(event_id).stream_position for event_id in (original_id, manifest_id))
        self.client.records = [replace(row, stream_position=b if row.stream_position == a else
            a if row.stream_position == b else row.stream_position) for row in self.client.records]
        self.client.records.sort(key=lambda row: row.stream_position)
        self.write_source(original_id, lambda value: value.update(event_stream_position=b))
        self.write_source(manifest_id, lambda value: value.update(event_stream_position=a))
        with self.assertRaisesRegex(PermissionError, "parent is not earlier|original-before-manifest"):
            self.verify()

    def test_reordered_or_future_history_cannot_enter_before_phase(self):
        for history in (replace(self.h.before, sources=tuple(reversed(self.h.before.sources))), self.h.after):
            with self.subTest(history=history.event_ids), self.assertRaises(PermissionError):
                self.verify(history=history)

    def test_parent_outside_held_phase_fails_before_its_physical_read(self):
        self.write_source(self.h.before.event_ids[0],
            lambda value: value["evidence"].update(parent_refs=[self.h.after.event_ids[-1]]))
        with self.assertRaisesRegex(PermissionError, "parent is outside"):
            self.verify()

    def test_physical_callback_revocation_is_seen(self):
        fired = False
        def revoke():
            nonlocal fired
            if not fired:
                fired = True
                self.h.grant(self.h.before.event_ids[0], "before", "revoke")
        self.client.on_read = revoke
        with self.assertRaises(PermissionError):
            self.verify()
        self.assertTrue(fired)

    def test_last_callback_withdrawal_is_caught_by_shared_terminal_fence(self):
        with self.assertRaisesRegex(PermissionError, "terminal current"):
            self.verify(final_current=lambda: self.h.grant(self.h.before.event_ids[0], "before", "revoke"))

    def test_last_callback_artifact_or_raw_mutation_is_caught(self):
        artifact_key = self.h.custody._key("run", "history:case:before")
        raw_key = self.h.registry._key("raw", self.h.before.sources[0].event.payload_reference)
        for table, key in (("flora_comparison_artifacts", artifact_key), ("flora_formation_raw_references", raw_key)):
            row = self.row(table, key)
            original = deepcopy(row)
            try:
                with self.subTest(table=table), self.assertRaisesRegex(PermissionError, "terminal current"):
                    self.verify(final_current=lambda: row.update(record_sha256="9" * 64))
            finally:
                row.clear()
                row.update(original)

    def test_actual_artifact_text_is_fenced_even_for_format_only_rewrite(self):
        row = self.row("flora_comparison_artifacts", self.h.custody._key("run", "history:case:before"))
        row["record_json"] = json.dumps(json.loads(row["record_json"]), indent=2)
        self.verify()
        with self.assertRaisesRegex(PermissionError, "terminal current"):
            self.verify(final_current=lambda: row.update(record_json=json.dumps(json.loads(row["record_json"]))))

    def test_last_callback_config_or_connection_or_held_event_mutation_is_rejected(self):
        original_connection = self.h.permissions.connection
        original_cap = self.policy.maximum_history_sources
        original_type = self.h.before.sources[0].event.event_type
        actions = (lambda: setattr(self.policy, "maximum_history_sources", 20),
                   lambda: setattr(self.h.permissions, "connection", object()),
                   lambda: self.h.before.sources[0].event.__dict__.update(event_type="forged"))
        for action in actions:
            try:
                with self.subTest(action=action), self.assertRaises(PermissionError):
                    self.verify(final_current=action)
            finally:
                self.policy.maximum_history_sources = original_cap
                self.h.permissions.connection = original_connection
                self.h.before.sources[0].event.__dict__["event_type"] = original_type

    def test_second_physical_pass_catches_late_locator_change(self):
        calls = 0
        def change():
            nonlocal calls
            calls += 1
            if calls == 4:
                self.write_source(self.h.before.event_ids[0], lambda value: value.update(event_stream_position=999))
        self.client.on_read = change
        with self.assertRaises(PermissionError):
            self.verify()

    def test_selected_phase_membership_uses_original_ids_and_no_full_replay(self):
        originals = {source.event.event_id: source.event for source in self.h.before.sources}
        actual = self.client.get_stream
        def bounded(**kwargs):
            self.assertEqual(kwargs.get("limit"), 1)
            return actual(**kwargs)
        with patch.object(self.client, "get_stream", side_effect=bounded):
            self.assertTrue(selected_phase_member(registry=self.h.registry, log=self.log,
                permissions=self.h.permissions, originals=originals, maximum_sources=16,
                event_id=self.h.before.event_ids[0]))
            self.assertFalse(selected_phase_member(registry=self.h.registry, log=self.log,
                permissions=self.h.permissions, originals=originals, maximum_sources=16,
                event_id=self.h.after.event_ids[-1]))
            manifest = self.h.custody.metadata_selected("run", "history:case:before").artifact.event_id
            self.assertFalse(selected_phase_member(registry=self.h.registry, log=self.log,
                permissions=self.h.permissions, originals=originals, maximum_sources=16, event_id=manifest))

    def test_selected_phase_original_key_hygiene_is_pure(self):
        calls, armed = [], False
        class EffectfulKey(str):
            def __hash__(self):
                if armed:
                    calls.append("hash")
                return str.__hash__(self)
            def __eq__(self, other):
                if armed:
                    calls.append("equal")
                return str.__eq__(self, other)
            def __lt__(self, other):
                if armed:
                    calls.append("less")
                return str.__lt__(self, other)
        original = self.h.before.sources[0].event
        originals = {EffectfulKey(original.event_id): original}
        armed = True
        with self.assertRaises(TypeError):
            selected_phase_member(registry=self.h.registry, log=self.log,
                permissions=self.h.permissions, originals=originals, maximum_sources=16,
                event_id=original.event_id)
        self.assertEqual(calls, [])

    def test_selected_compound_route_keeps_terminal_all_original_rights(self):
        # Reusing the evaluation purpose still exercises the actual combined
        # consumer dispatch without requiring external-provider fixture state.
        purpose = evaluation_purpose("run", "case", "before")
        actual = self.client.get_stream
        def bounded(**kwargs):
            self.assertEqual(kwargs.get("limit"), 1)
            return actual(**kwargs)
        with patch.object(self.client, "get_stream", side_effect=bounded):
            proof = verify_history_and_external_metadata(policy=self.policy, case_id="case", phase="before",
                history=self.h.before, source_ids=self.h.before.event_ids, purpose=purpose, final_current=lambda: None)
        self.assertEqual(proof.domain, "selected-history-metadata-v1")
        with self.assertRaisesRegex(PermissionError, "terminal current"):
            verify_history_and_external_metadata(policy=self.policy, case_id="case", phase="before",
                history=self.h.before, source_ids=self.h.before.event_ids, purpose=purpose,
                final_current=lambda: self.h.grant(self.h.before.event_ids[0], "before", "revoke"))

    def test_near_cap_compound_history_counts_distinct_purpose_rows(self):
        # Three physical sources: two originals and the manifest. Two purpose
        # heads/actions per original exceed the old single-purpose row bound.
        self.policy.maximum_history_sources = 3
        proof = self.verify(source_purposes=((self.h.before.event_ids,
            evaluation_purpose("run", "case", "after")),))
        self.assertEqual(proof.domain, "selected-history-metadata-v1")

    def test_terminal_sql_cannot_introduce_an_effectful_held_dictionary_key(self):
        calls, armed = [], False
        class EffectfulKey(str):
            def __hash__(self):
                if armed:
                    calls.append("hash")
                return str.__hash__(self)
            def __eq__(self, other):
                if armed:
                    calls.append("equal")
                return str.__eq__(self, other)
        event = self.h.before.sources[0].event
        actual = self.f.connection.execute
        def execute(sql, parameters=()):
            nonlocal armed
            cursor = actual(sql, parameters)
            if "AS flora_current_metadata_fence" in sql:
                value = event.__dict__.pop("event_type")
                event.__dict__[EffectfulKey("event_type")] = value
                armed = True
            return cursor
        with patch.object(self.f.connection, "execute", side_effect=execute), \
             self.assertRaises(PermissionError):
            self.verify()
        self.assertEqual(calls, [])

    def test_terminal_sql_cannot_introduce_a_custom_metaclass_in_held_fields(self):
        calls = []
        class EffectfulMeta(type):
            def __hash__(self):
                calls.append("hash")
                return type.__hash__(self)
            def __eq__(self, other):
                calls.append("equal")
                return type.__eq__(self, other)
        class Field(metaclass=EffectfulMeta):
            pass
        actual = self.f.connection.execute
        def execute(sql, parameters=()):
            cursor = actual(sql, parameters)
            if "AS flora_current_metadata_fence" in sql:
                self.h.before.sources[0].event.__dict__["event_type"] = Field()
            return cursor
        with patch.object(self.f.connection, "execute", side_effect=execute), \
             self.assertRaises(PermissionError):
            self.verify()
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
