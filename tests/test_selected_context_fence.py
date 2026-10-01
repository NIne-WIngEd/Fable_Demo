"""Compound current-row races with supplied state, not a latency/model claim."""
from copy import copy, deepcopy
import json
import re
import unittest
from unittest.mock import patch

from cognitive_kernel.canonical import canonical_json_bytes
from flora.selected import claims as claim_tables
from flora.selected.context_guard import CapturedClaimAuthority
from flora.selected import selected_context_fence as fence
from flora.selected.personal_state import _ACTIVE, _VERSIONS
from flora.selected.governed_development import _HISTORY
from metadata_batch_fixture import _Cursor
import test_current_context_guard as fixtures


class SelectedContextStateFenceTest(unittest.TestCase):
    def setUp(self):
        self.h = fixtures.SelectedCurrentContextTerminalFenceTest()
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.prepared = self.h.prepare()
        self.f, self.state = self.h.f, self.h.state
        self.registry, self.permissions = self.h.h.registry, self.h.h.permissions
        self.connection = self.f.connection
        self.original_execute = self.connection.execute
        self.connection.execute = self.execute
        self.addCleanup(setattr, self.connection, "execute", self.original_execute)

    def execute(self, sql, parameters):
        if ") AS flora_selected_context_fence LIMIT" not in sql:
            return self.original_execute(sql, parameters)
        self.connection.calls.append((sql, parameters))
        clauses = re.findall(r"SELECT '([^']+)' AS fence_kind, _id, scope_digest, "
            r"(\w+) AS fence_sha256, (.*?) FROM (\w+)( FOR VALID_TIME ALL)? "
            r"WHERE scope_digest = %s AND _id = %s::text", sql)
        if not clauses or len(parameters) != 2 * len(clauses):
            raise AssertionError("unexpected compound selected-context SQL shape")
        rows = []
        for index, (tag, digest, projection, table, _) in enumerate(clauses):
            scope_digest, key = parameters[2 * index:2 * index + 2]
            row = self.connection.rows.get((table, key))
            if row is None or row["scope_digest"] != scope_digest:
                continue
            row = deepcopy(row)
            rows.append({"fence_kind": tag, "_id": row["_id"], "scope_digest": row["scope_digest"],
                "fence_sha256": row[digest], "record_json": row.get("record_json"),
                **{name: row.get(name) for name in fence._EXTRA}})
        return _Cursor(rows)

    def sample(self):
        sample = fence.SelectedContextMetadataSample(state=self.state, binding_guard=lambda: None,
            registry=self.registry, permissions=self.permissions, claims=self.h.h.claims, maximum_rows=64)
        sample.observe_state_authorities(self.state, self.prepared.state_authorities)
        sample.prime_sources(tuple(source.event_id for source in self.prepared.source_authorities),
            "personal_judgment")
        return sample

    def head_key(self):
        captured = self.prepared.state_authorities[0]
        route = captured.route
        return _ACTIVE, self.state._head_id(route.subject_type, route.subject_id, route.projection_id)

    def test_state_and_original_grants_share_one_terminal_statement_without_private_io(self):
        sample = self.sample()
        before = len(self.connection.calls)
        with patch.object(self.f.objects, "get", side_effect=AssertionError("private I/O forbidden")):
            sample.verify_final_current_rows()
        calls = self.connection.calls[before:]
        self.assertEqual(len(calls), 1)
        for table in (_ACTIVE, _VERSIONS, _HISTORY, "flora_formation_permission_current",
                "flora_registered_formation_sources"):
            self.assertIn(table, calls[0][0])

    def test_active_head_change_after_last_source_callback_cannot_return_held_state(self):
        for column, value in (("activation_generation", 2), ("approval_event_sha256", "f" * 64),
                ("expected_active_version_id", "different-predecessor")):
            with self.subTest(column=column):
                sample = self.sample()
                row = self.connection.rows[self.head_key()]
                original = row[column]
                row[column] = value
                try:
                    with self.assertRaisesRegex(PermissionError, "authority changed after callbacks"):
                        sample.verify_final_current_rows()
                finally:
                    row[column] = original

    def test_immutable_version_content_reference_change_is_in_same_terminal_domain(self):
        sample = self.sample()
        version = self.prepared.state_authorities[0].version_id
        self.connection.rows[(_VERSIONS, self.state._version_id(version))]["content_object_id"] = "different-content"
        with self.assertRaises(PermissionError):
            sample.verify_final_current_rows()

    def test_immutable_receipt_format_rewrite_is_rejected_after_observation(self):
        sample = self.sample()
        captured = self.prepared.state_authorities[0]
        key = _HISTORY, self.state._history_key(captured.route.projection_id, captured.version_id)
        row = self.connection.rows[key]
        row["record_json"] = json.dumps(json.loads(row["record_json"]), indent=2)
        with self.assertRaises(PermissionError):
            sample.verify_final_current_rows()

    def test_original_grant_withdrawal_still_rejects_when_state_rows_are_unchanged(self):
        sample = self.sample()
        self.h.h.grant(self.prepared.source_authorities[0].event_id, "revoke")
        with self.assertRaises(PermissionError):
            sample.verify_final_current_rows()

    def test_initial_observation_compares_the_captured_current_head(self):
        self.connection.rows[self.head_key()]["activation_generation"] += 1
        with self.assertRaisesRegex(PermissionError, "changed before"):
            self.sample()

    def test_state_owner_replacement_and_reader_rebinding_fail_closed(self):
        sample = self.sample()
        self.state.registry = copy(self.registry)
        with self.assertRaises(PermissionError):
            sample.verify_final_current_rows()
        self.state.registry = self.registry
        self.state._fetch = lambda *_args, **_kwargs: None
        with self.assertRaises(PermissionError):
            sample.verify_final_current_rows()

    def test_custom_result_keys_do_not_hash_or_compare_after_terminal(self):
        effects = []
        class EffectfulKey(str):
            def __hash__(self):
                effects.append("hash")
                return super().__hash__()
        actual = self.execute
        def execute(sql, parameters):
            cursor = actual(sql, parameters)
            if ") AS flora_selected_context_fence LIMIT" not in sql:
                return cursor
            names = [column.name for column in cursor.description]
            rows = [dict(zip(names, values)) for values in cursor.fetchall()]
            value = rows[0].pop("fence_kind")
            rows[0][EffectfulKey("fence_kind")] = value
            effects.clear()
            cursor = _Cursor(rows)
            effects.clear()
            return cursor
        self.connection.execute = execute
        sample = self.sample()
        with self.assertRaises(PermissionError):
            sample.verify_final_current_rows()
        self.assertEqual(effects, [])

    def test_changed_local_row_helper_cannot_run_after_terminal_query(self):
        actual = self.execute
        effects = []
        def execute(sql, parameters):
            cursor = actual(sql, parameters)
            if ") AS flora_selected_context_fence LIMIT" in sql:
                fence._terminal_rows = lambda _cursor, _binding: effects.append("helper") or []
            return cursor
        self.connection.execute = execute
        sample = self.sample()
        original = fence._terminal_rows
        try:
            with self.assertRaisesRegex(PermissionError, "pure helper changed"):
                sample.verify_final_current_rows()
            self.assertEqual(effects, [])
        finally:
            fence._terminal_rows = original

    def claim_authority(self):
        claims, claim_id, current = self.h.claim_fixture()
        version_id = current["current_claim_version_id"]
        version = claims.load_version(version_id)
        relations = tuple((key, canonical_json_bytes(claims.load_evidence_relation(key)))
            for key in version["evidence_relation_ids"])
        return CapturedClaimAuthority(claim_id, version_id, current["projection_sha256"],
            canonical_json_bytes(current), canonical_json_bytes(version), relations)

    def test_immutable_claim_version_and_relation_share_state_source_terminal_basis(self):
        authority = self.claim_authority()
        sample = self.sample()
        sample.observe_claim_authorities((authority,))
        sample.verify_final_current_rows()
        terminal = self.connection.calls[-1][0]
        self.assertIn(claim_tables._VERSIONS, terminal)
        self.assertIn(claim_tables._EVIDENCE, terminal)
        self.assertIn(_ACTIVE, terminal)

    def test_late_immutable_claim_and_relation_mutations_cannot_use_current_head_alone(self):
        authority = self.claim_authority()
        for table, identifier in ((claim_tables._VERSIONS, authority.version_id),
                (claim_tables._EVIDENCE, authority.evidence_records[0][0])):
            with self.subTest(table=table):
                sample = self.sample()
                sample.observe_claim_authorities((authority,))
                row = self.connection.rows[(table, self.h.h.claims._row_id(identifier))]
                original = row["record_json"]
                record = json.loads(original)
                if table == claim_tables._VERSIONS:
                    record["value"] = {"fictional": "changed supplied fact"}
                else:
                    record["target_record_id"] = "different-target"
                row["record_json"] = json.dumps(record)
                try:
                    with self.assertRaisesRegex(PermissionError, "authority changed after callbacks"):
                        sample.verify_final_current_rows()
                finally:
                    row["record_json"] = original


if __name__ == "__main__":
    unittest.main()
