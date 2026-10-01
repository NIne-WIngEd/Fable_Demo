"""Fresh registry locators; no backend, Kurrent integrity or use qualification.

The SQL recorder is inherited from registration contract fixtures. Re-signed
fixture rows test fresh decoding and malformed metadata, not an authorized
registry rewrite or a substitute for an exact physical event proof.
"""

from dataclasses import FrozenInstanceError
import json
import unittest

from cognitive_kernel.canonical import canonical_sha256
from cognitive_kernel.contracts import ProductHostScope
from flora.selected.formation_registry import CanonicalSourceCommitment

import test_selected_formation_registry as fixtures


class SelectedSourceCommitmentTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.FormationRegistryContractTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.source = self.fixture._register()

    def source_row(self):
        f = self.fixture
        return f.connection.rows[("flora_registered_formation_sources",
                                  f.registry._key("source", f.event.event_id))]

    def raw_row(self):
        f = self.fixture
        return f.connection.rows[("flora_formation_raw_references",
                                  f.registry._key("raw", f.raw.object_id))]

    def write_record(self, row, record):
        record["record_sha256"] = canonical_sha256(
            {key: value for key, value in record.items() if key != "record_sha256"})
        row["record_sha256"] = record["record_sha256"]
        row["record_json"] = json.dumps(record)

    def write_source(self, record, *, rebind_registration=False):
        if rebind_registration:
            record["registration_sha256"] = canonical_sha256(
                {"evidence": record["evidence"], "object_ref": record["object_ref"]})
        self.write_record(self.source_row(), record)

    def lookup(self):
        f = self.fixture
        return f.registry.lookup_commitment(f.event.event_id)

    def test_exposes_exact_frozen_registration_locator_without_private_io(self):
        f = self.fixture
        def forbidden(*args, **kwargs):
            raise AssertionError("commitment lookup performed private or Kurrent I/O")
        f.objects.get = forbidden
        f.backend.get_object = forbidden
        f.log.replay_committed = forbidden
        before = len(f.connection.calls)
        commitment = self.lookup()
        self.assertIsInstance(commitment, CanonicalSourceCommitment)
        self.assertEqual(commitment.source, self.source)
        self.assertEqual(commitment.event_sha256, f.event.event_sha256)
        self.assertEqual(commitment.stream_position, 0)
        self.assertEqual(commitment.recorded_at, f.evidence.recorded_at)
        commitment.validate()
        self.assertEqual(len(f.connection.calls) - before, 2)
        with self.assertRaises(FrozenInstanceError):
            commitment.stream_position = 2

    def test_absent_source_does_not_probe_raw_metadata(self):
        f = self.fixture
        before = len(f.connection.calls)
        self.assertIsNone(f.registry.lookup_commitment("missing-source"))
        self.assertEqual(len(f.connection.calls) - before, 1)
        self.assertIn("flora_registered_formation_sources", f.connection.calls[-1][0])

    def test_each_call_reads_current_rows_instead_of_caching_locator(self):
        f = self.fixture
        first = self.lookup()
        record = json.loads(self.source_row()["record_json"])
        record["event_stream_position"] = 7
        changed_digest = f.event.event_sha256[:32] + "b" * 32
        record["event_sha256"] = changed_digest
        record["evidence"]["recorded_at"] = "2026-09-30T12:00:00.000000Z"
        self.write_source(record, rebind_registration=True)
        before = len(f.connection.calls)
        second = self.lookup()
        self.assertEqual(len(f.connection.calls) - before, 2)
        self.assertNotEqual(second, first)
        self.assertEqual(second.stream_position, 7)
        self.assertEqual(second.event_sha256, changed_digest)
        self.assertEqual(second.recorded_at, "2026-09-30T12:00:00.000000Z")
        self.assertEqual(first.stream_position, 0)
        # This API surfaces a self-consistent fresh row. An exact Kurrent
        # proof must reject these invented physical locator values later.

    def test_position_must_be_nonboolean_nonnegative_integer(self):
        original = json.loads(self.source_row()["record_json"])
        for value in (True, False, -1, "0", 0.0, None):
            with self.subTest(position=value):
                record = dict(original, event_stream_position=value)
                self.write_source(record)
                with self.assertRaisesRegex(ValueError, "nonnegative integer"):
                    self.lookup()

    def test_digest_must_be_full_canonical_sha256(self):
        original = json.loads(self.source_row()["record_json"])
        for value in ("a" * 63, "a" * 65, "A" * 64, " a" + "a" * 63, None, 123):
            with self.subTest(digest=value):
                record = dict(original, event_sha256=value)
                self.write_source(record)
                with self.assertRaises(ValueError):
                    self.lookup()

    def test_canonical_digest_must_still_bind_registered_source_id(self):
        record = json.loads(self.source_row()["record_json"])
        record["event_sha256"] = "e" * 64
        self.write_source(record)
        with self.assertRaisesRegex(ValueError, "does not bind its source ID"):
            self.lookup()

    def test_commit_time_is_required_canonical_and_source_bound(self):
        original = json.loads(self.source_row()["record_json"])
        for value in (None, "2026-09-29T12:00:00", "2026-09-29T12:00:00Z",
                      "2026-09-29T12:00:00.000000+00:00", "not-a-date"):
            with self.subTest(recorded_at=value):
                record = json.loads(json.dumps(original))
                record["evidence"]["recorded_at"] = value
                self.write_source(record, rebind_registration=True)
                with self.assertRaises(ValueError):
                    self.lookup()
        record = json.loads(json.dumps(original))
        record["evidence"]["recorded_at"] = "2026-09-30T12:00:00.000000Z"
        self.write_source(record)
        with self.assertRaisesRegex(ValueError, "does not bind its lookup"):
            self.lookup()

    def test_self_consistent_cross_ref_or_scope_row_is_rejected(self):
        original = json.loads(self.source_row()["record_json"])
        for field, value in (("ref_id", "different-source"),
                             ("authority_namespace_id", "different-namespace")):
            with self.subTest(field=field):
                record = json.loads(json.dumps(original))
                record["evidence"][field] = value
                self.write_source(record, rebind_registration=True)
                with self.assertRaisesRegex(ValueError, "does not bind its lookup"):
                    self.lookup()
        record = json.loads(json.dumps(original))
        record["evidence"]["scope"]["host_instance_id"] = "different-host"
        self.write_source(record, rebind_registration=True)
        with self.assertRaisesRegex(ValueError, "does not bind its lookup"):
            self.lookup()
        record = json.loads(json.dumps(original))
        record["scope"]["host_instance_id"] = "different-host"
        self.write_source(record)
        with self.assertRaisesRegex(ValueError, "immutable metadata changed"):
            self.lookup()

    def test_source_record_hash_registration_and_raw_stamp_are_enforced(self):
        row = self.source_row()
        original_json, original_digest = row["record_json"], row["record_sha256"]
        record = json.loads(original_json)
        record["event_stream_position"] += 1
        row["record_json"] = json.dumps(record)
        with self.assertRaisesRegex(ValueError, "immutable metadata changed"):
            self.lookup()
        row["record_json"], row["record_sha256"] = original_json, original_digest
        for field in ("registration_sha256", "raw_reference_sha256"):
            with self.subTest(field=field):
                record = json.loads(original_json)
                record[field] = "c" * 64
                self.write_source(record)
                with self.assertRaises(ValueError):
                    self.lookup()

    def test_raw_row_is_fresh_and_still_binds_source_digest(self):
        f = self.fixture
        self.lookup()
        raw_key = ("flora_formation_raw_references", f.registry._key("raw", f.raw.object_id))
        original = f.connection.rows.pop(raw_key)
        with self.assertRaisesRegex(ValueError, "no exact durable raw reference"):
            self.lookup()
        f.connection.rows[raw_key] = original
        record = json.loads(original["record_json"])
        record["plaintext_sha256"] = "d" * 64
        self.write_record(original, record)
        source_record = json.loads(self.source_row()["record_json"])
        source_record["raw_reference_sha256"] = record["record_sha256"]
        self.write_source(source_record)
        with self.assertRaisesRegex(ValueError, "no exact durable raw reference"):
            self.lookup()

    def test_new_api_does_not_replace_established_lookup(self):
        f = self.fixture
        original = f.registry.lookup
        calls = []
        def observed(ref_id):
            calls.append(ref_id)
            return original(ref_id)
        f.registry.lookup = observed
        self.assertEqual(f.registry.lookup(f.event.event_id), self.source)
        self.assertEqual(self.lookup().source, self.source)
        self.assertEqual(calls, [f.event.event_id])

    def test_sql_callback_cannot_rebind_registry_owner_or_namespace(self):
        f = self.fixture
        original_scope, original_namespace = f.registry.scope, f.registry.authority_namespace_id
        original_connection, original_digest = f.registry.connection, f.registry.scope_digest
        actual = original_connection.execute
        equal_scope = ProductHostScope.create(**original_scope.metadata_record())
        for field, value in (("scope", equal_scope),
                             ("authority_namespace_id", "rebound-namespace"),
                             ("connection", fixtures._SQLCalls()),
                             ("scope_digest", "f" * 64)):
            with self.subTest(field=field):
                f.registry.scope, f.registry.authority_namespace_id = original_scope, original_namespace
                f.registry.connection, f.registry.scope_digest = original_connection, original_digest
                def execute(statement, parameters):
                    result = actual(statement, parameters)
                    setattr(f.registry, field, value)
                    return result
                original_connection.execute = execute
                before = len(original_connection.calls)
                with self.assertRaisesRegex(ValueError, "reader binding changed"):
                    self.lookup()
                # Rebinding during source SQL is detected before raw metadata.
                self.assertEqual(len(original_connection.calls) - before, 1)
        original_connection.execute = actual
        f.registry.scope, f.registry.authority_namespace_id = original_scope, original_namespace
        f.registry.connection, f.registry.scope_digest = original_connection, original_digest

    def test_rebinding_during_raw_metadata_callback_is_also_rejected(self):
        f = self.fixture
        actual = f.connection.execute
        def execute(statement, parameters):
            result = actual(statement, parameters)
            if "flora_formation_raw_references" in statement:
                f.registry.connection = fixtures._SQLCalls()
            return result
        f.connection.execute = execute
        with self.assertRaisesRegex(ValueError, "reader binding changed"):
            self.lookup()

    def test_sql_callback_cannot_replace_later_registry_reader(self):
        f = self.fixture
        actual = f.connection.execute
        for name in ("_key", "_fetch", "_decode", "raw_metadata", "lookup_commitment"):
            with self.subTest(reader=name):
                expected = getattr(f.registry, name)
                def execute(statement, parameters):
                    result = actual(statement, parameters)
                    setattr(f.registry, name, lambda *args, **kwargs: None)
                    return result
                f.connection.execute = execute
                try:
                    with self.assertRaisesRegex(ValueError, "reader binding changed"):
                        expected_lookup = (expected if name == "lookup_commitment"
                                           else f.registry.lookup_commitment)
                        expected_lookup(f.event.event_id)
                finally:
                    setattr(f.registry, name, expected)
        f.connection.execute = actual

    def test_raw_metadata_callback_cannot_replace_reader_before_return(self):
        f = self.fixture
        actual_raw = f.registry.raw_metadata
        def raw_metadata(object_ref):
            result = actual_raw(object_ref)
            f.registry._decode = lambda *args, **kwargs: None
            return result
        f.registry.raw_metadata = raw_metadata
        with self.assertRaisesRegex(ValueError, "reader binding changed"):
            self.lookup()


if __name__ == "__main__":
    unittest.main()
