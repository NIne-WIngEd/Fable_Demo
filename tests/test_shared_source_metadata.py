"""Shared metadata nominations, using controlled SQL and real scoped contracts.

This collector opens no private bytes, proves no physical event or phase, and
returns no authority. These checks are not real-engine or latency evidence.
"""
from copy import deepcopy
from dataclasses import replace
import json
from types import FunctionType
import unittest
from unittest.mock import patch

from cognitive_kernel.canonical import canonical_sha256
from flora.selected.comparison_custody import evaluation_purpose
from flora.selected import formation_policy as permissions
from flora.selected import formation_registry as sources
from flora.selected.phase_source_fence import OneGuardSelectedMetadata
import test_phase_source_fence as fixtures


class SharedSourceMetadataTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PhaseSourceFenceTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.history = self.fixture.h
        self.f = self.fixture.f
        self.registry, self.permissions = self.fixture.registry, self.fixture.permissions
        self.parent = self.history.materials[0].event.event_id
        self.other = self.history.materials[1].event.event_id
        self.child = self.history.materials[-1].event.event_id
        self.evaluation = evaluation_purpose("run", "case", "before")
        self.judgment = "personal_judgment"

    def sample(self, maximum_rows=4096):
        return OneGuardSelectedMetadata(registry=self.registry, permissions=self.permissions,
                                        maximum_rows=maximum_rows)

    def nominations(self):
        return ((self.history.before.event_ids, self.evaluation, 2),
                ((self.parent,), self.judgment, 1))

    def source_row(self, event_id):
        return self.f.connection.rows[(sources._SOURCES, self.registry._key("source", event_id))]

    def change_parents(self, event_id, parents):
        # A self-consistent corrupted metadata fixture, not a valid new physical
        # event or a trusted registration. The collector must reject its cycle.
        row = self.source_row(event_id)
        record = json.loads(row["record_json"])
        record["evidence"]["parent_refs"] = list(parents)
        record["registration_sha256"] = canonical_sha256(
            {"evidence": record["evidence"], "object_ref": record["object_ref"]})
        record["record_sha256"] = canonical_sha256(
            {name: value for name, value in record.items() if name != "record_sha256"})
        row["record_json"], row["record_sha256"] = json.dumps(record), record["record_sha256"]

    def test_overlapping_sources_sample_once_but_keep_distinct_purpose_heads(self):
        sample = self.sample()
        before = len(self.f.connection.calls)
        with patch.object(self.f.objects, "get", side_effect=AssertionError("private read")), \
             patch.object(self.f.objects.backend, "get_object", side_effect=AssertionError("ciphertext read")):
            inventory = sample.prime_source_purposes(self.nominations())
        self.assertEqual(dict(inventory), {self.evaluation: tuple(sorted((self.parent, self.other))),
                                          self.judgment: (self.parent,)})
        self.assertEqual(sum(kind == "registry" and table == sources._SOURCES
                             for kind, table, _, _ in sample._observations), 2)
        self.assertEqual(sum(kind == "registry" and table == sources._OBJECTS
                             for kind, table, _, _ in sample._observations), 2)
        self.assertEqual(sum(kind == "permission" and table == permissions._CURRENT
                             for kind, table, _, _ in sample._observations), 3)
        self.assertEqual(sum(kind == "permission" and table == permissions._ACTIONS
                             for kind, table, _, _ in sample._observations), 3)
        calls = self.f.connection.calls[before:]
        self.assertEqual(len(calls), 2)
        self.assertTrue(all("AS flora_current_metadata_sample LIMIT" in sql for sql, _ in calls))
        source_key = self.registry._key("source", self.parent)
        raw_key = self.registry._key("raw", self.registry.lookup(self.parent).object_ref)
        self.assertEqual(sum(parameters.count(source_key) for _, parameters in calls), 1)
        self.assertEqual(sum(parameters.count(raw_key) for _, parameters in calls), 1)
        sample.verify_final_current_rows()

    def test_collector_runs_no_permit_predicate_or_early_terminal_fence(self):
        with patch.object(self.permissions, "permits", return_value=False) as predicate:
            sample = self.sample()
            before = len(self.f.connection.calls)
            inventory = sample.prime_source_purposes(self.nominations())
            predicate.assert_not_called()
            self.assertIs(type(inventory), tuple)
            self.assertFalse(any("AS flora_current_metadata_fence LIMIT" in sql
                                 for sql, _ in self.f.connection.calls[before:]))
            # The caller still must run this actual denial; a collected inventory
            # cannot replace it with an earlier successful allow answer.
            source = sample.local_registry.lookup(self.parent)
            self.assertFalse(sample.local_permissions.permits(source, self.judgment))
            self.assertEqual(predicate.call_count, 1)

    def test_unselected_history_grant_withdrawal_after_context_collection_hits_terminal_fence(self):
        sample = self.sample()
        sample.prime_source_purposes(self.nominations())
        self.history.grant(self.other, "before", "revoke")
        with self.assertRaisesRegex(PermissionError, "terminal current"):
            sample.verify_final_current_rows()

    def test_last_context_callback_cannot_withdraw_unselected_history_grant(self):
        actual, changed = self.permissions.current_action, False
        def current_action(event_id, purpose):
            nonlocal changed
            result = actual(event_id, purpose)
            if purpose == self.judgment and not changed:
                changed = True
                self.history.grant(self.other, "before", "revoke")
            return result
        with patch.object(self.permissions, "current_action", side_effect=current_action):
            sample = self.sample()
            sample.prime_source_purposes(self.nominations())
            with self.assertRaisesRegex(PermissionError, "terminal current"):
                sample.verify_final_current_rows()
        self.assertTrue(changed)

    def test_context_grant_withdrawal_is_independent_of_history_grant(self):
        sample = self.sample()
        sample.prime_source_purposes(self.nominations())
        self.fixture.grant(self.parent, "revoke")
        with self.assertRaisesRegex(PermissionError, "terminal current"):
            sample.verify_final_current_rows()
        with self.assertRaisesRegex(PermissionError, "withdrawn or changed"):
            self.sample().prime_source_purposes(self.nominations())

    def test_each_domain_cap_counts_parents_without_borrowing_other_cap(self):
        after = evaluation_purpose("run", "case", "after")
        for nominations in (
                (((self.child,), after, 1), ((self.child,), self.judgment, 8)),
                (((self.child,), self.judgment, 8), ((self.child,), self.judgment, 1))):
            with self.subTest(nominations=nominations), \
                 self.assertRaisesRegex(PermissionError, "parent closure exceeds"):
                self.sample().prime_source_purposes(nominations)
        inventory = self.sample().prime_source_purposes(
            (((self.child,), after, 2), ((self.parent,), self.judgment, 1)))
        self.assertEqual(dict(inventory)[after], tuple(sorted((self.parent, self.child))))

    def test_independent_caps_can_share_purpose_without_becoming_one_union_cap(self):
        sample = self.sample()
        inventory = sample.prime_source_purposes(
            (((self.parent,), self.evaluation, 1), ((self.other,), self.evaluation, 1)))
        self.assertEqual(inventory, ((self.evaluation, tuple(sorted((self.parent, self.other)))),))
        sample.verify_final_current_rows()

    def test_parent_closure_reads_each_shared_source_row_once_across_rounds(self):
        sample = self.sample()
        before = len(self.f.connection.calls)
        sample.prime_source_purposes(
            (((self.parent,), self.judgment, 1), ((self.child,), self.judgment, 2)))
        calls = self.f.connection.calls[before:]
        for event_id in (self.parent, self.child):
            key = self.registry._key("source", event_id)
            self.assertEqual(sum(parameters.count(key) for _, parameters in calls), 1)
        sample.verify_final_current_rows()

    def test_cycle_is_rejected_even_when_closure_fits_cap(self):
        for parents in ((self.child,), (self.parent,)):
            with self.subTest(parents=parents):
                saved = deepcopy(self.source_row(self.child))
                self.change_parents(self.child, parents)
                if parents == (self.parent,):
                    saved_parent = deepcopy(self.source_row(self.parent))
                    self.change_parents(self.parent, (self.child,))
                try:
                    purpose = "metadata-cycle-self" if parents == (self.child,) else "metadata-cycle-pair"
                    # Reuse signed grant construction for a separate fictional
                    # purpose, not a fabricated BEFORE/AFTER experiment phase.
                    with patch("test_history_fence.evaluation_purpose", return_value=purpose):
                        self.history.grant(self.child, "before")
                        if parents == (self.parent,):
                            self.history.grant(self.parent, "before")
                    with self.assertRaisesRegex(PermissionError, "contains a cycle"):
                        self.sample().prime_source_purposes((((self.child,), purpose, 2),))
                finally:
                    self.source_row(self.child).update(saved)
                    if parents == (self.parent,):
                        self.source_row(self.parent).update(saved_parent)

    def test_raw_manifest_metadata_invents_no_source_grant(self):
        artifact = self.history.custody.metadata("run", "history:case:before")
        source = self.registry.lookup(artifact.event_id)
        self.assertIsNone(self.permissions.current_action(artifact.event_id, self.evaluation))
        sample = self.sample()
        sample.prime_source_purposes(self.nominations(), raw_object_ids=(source.object_ref,))
        manifest_head = self.permissions._key("head", artifact.event_id, self.evaluation)
        self.assertFalse(any(key == manifest_head for _, _, key, _ in sample._observations))
        self.assertIn(("registry", sources._OBJECTS, self.registry._key("raw", source.object_ref), True),
                      sample._observations)
        sample.verify_final_current_rows()

    def test_combined_row_cap_and_missing_dependency_fail_closed(self):
        with self.assertRaisesRegex(PermissionError, "row cap"):
            self.sample(maximum_rows=9).prime_source_purposes(self.nominations())
        source = self.registry.lookup(self.parent)
        action = self.permissions.current_action(self.parent, self.judgment)
        for table, key in (
                (sources._SOURCES, self.registry._key("source", self.parent)),
                (sources._OBJECTS, self.registry._key("raw", source.object_ref)),
                (permissions._CURRENT, self.permissions._key("head", self.parent, self.judgment)),
                (permissions._ACTIONS, self.permissions._key("action", action.action_id))):
            saved = self.f.connection.rows.pop((table, key))
            try:
                with self.subTest(table=table), self.assertRaises(PermissionError):
                    self.sample().prime_source_purposes(self.nominations())
            finally:
                self.f.connection.rows[(table, key)] = saved

    def test_source_and_raw_changes_after_collection_are_terminal_dependencies(self):
        for table, kind, identifier in ((sources._SOURCES, "source", self.parent),
                (sources._OBJECTS, "raw", self.registry.lookup(self.parent).object_ref)):
            row = self.f.connection.rows[(table, self.registry._key(kind, identifier))]
            saved = deepcopy(row)
            try:
                sample = self.sample()
                sample.prime_source_purposes(self.nominations())
                row["record_sha256"] = "9" * 64
                with self.subTest(table=table), self.assertRaisesRegex(PermissionError, "terminal current"):
                    sample.verify_final_current_rows()
            finally:
                row.update(saved)

    def test_custom_actual_readers_execute_and_their_denials_are_not_batched_away(self):
        for service in (self.registry, self.permissions):
            actual = service._fetch
            with self.subTest(service=type(service).__name__), \
                 patch.object(service, "_fetch", wraps=actual) as reader:
                sample = self.sample()
                sample.prime_source_purposes(self.nominations())
                self.assertGreater(reader.call_count, 0)
                identities = [(args[0], args[1], kwargs.get("immutable", True))
                              for args, kwargs in reader.call_args_list]
                self.assertEqual(len(identities), len(set(identities)))
                sample.verify_final_current_rows()
            with patch.object(service, "_fetch", return_value=None) as denial:
                with self.assertRaises(PermissionError):
                    self.sample().prime_source_purposes(self.nominations())
                self.assertGreater(denial.call_count, 0)

    def test_custom_source_callback_and_binding_replacement_stay_visible(self):
        actual, calls = self.registry.lookup, []
        def lookup(event_id):
            calls.append(event_id)
            return actual(event_id)
        with patch.object(self.registry, "lookup", side_effect=lookup):
            sample = self.sample()
            sample.prime_source_purposes(self.nominations())
            self.assertEqual(calls.count(self.parent), 2)  # One per purpose.
            sample.verify_final_current_rows()
            self.registry.lookup = actual
            with self.assertRaisesRegex(PermissionError, "binding changed"):
                sample.verify_final_current_rows()

    def test_custom_class_readers_and_subclasses_retain_actual_callbacks(self):
        for service in (self.registry, self.permissions):
            cls, calls = type(service), []
            actual = cls._fetch
            def fetch(owner, *args, **kwargs):
                calls.append((args, kwargs))
                return actual(owner, *args, **kwargs)
            with self.subTest(service=cls.__name__), patch.object(cls, "_fetch", new=fetch):
                sample = self.sample()
                sample.prime_source_purposes(self.nominations())
                self.assertGreater(len(calls), 0)
                sample.verify_final_current_rows()
            class CustomReader(cls):
                def _fetch(owner, *args, **kwargs):
                    calls.append((args, kwargs))
                    return actual(owner, *args, **kwargs)
            service.__class__ = CustomReader
            calls.clear()
            try:
                sample = self.sample()
                sample.prime_source_purposes(self.nominations())
                self.assertGreater(len(calls), 0)
                sample.verify_final_current_rows()
            finally:
                service.__class__ = cls

    def test_in_place_reader_code_change_keeps_its_actual_callback(self):
        for service in (self.registry, self.permissions):
            native = type(service)._fetch
            code, calls = native.__code__, []
            original = FunctionType(code, native.__globals__, native.__name__, native.__defaults__)
            def replacement(owner, *args, **kwargs):
                _shared_metadata_reader_calls.append((args, kwargs))
                return _shared_metadata_original_reader(owner, *args, **kwargs)
            with patch.dict(native.__globals__, {"_shared_metadata_reader_calls": calls,
                                                "_shared_metadata_original_reader": original}):
                native.__code__ = replacement.__code__
                try:
                    sample = self.sample()
                    sample.prime_source_purposes(self.nominations())
                    self.assertGreater(len(calls), 0)
                    sample.verify_final_current_rows()
                finally:
                    native.__code__ = code

    def test_custom_class_reader_denial_is_not_batched_away(self):
        for service in (self.registry, self.permissions):
            calls = []
            def denied(owner, *args, **kwargs):
                calls.append((args, kwargs))
                return None
            with patch.object(type(service), "_fetch", new=denied):
                with self.assertRaises(PermissionError):
                    self.sample().prime_source_purposes(self.nominations())
                self.assertGreater(len(calls), 0)

    def test_domain_count_is_bounded_before_metadata_io(self):
        sample = self.sample(maximum_rows=1)
        before = len(self.f.connection.calls)
        with self.assertRaisesRegex(PermissionError, "domain count"):
            sample.prime_source_purposes(
                (((self.parent,), self.judgment, 1), ((self.parent,), self.judgment, 2)))
        self.assertEqual(len(self.f.connection.calls), before)

    def test_invalid_native_nominations_fail_before_io_or_effectful_values(self):
        effects = []
        class EffectfulString(str):
            def __hash__(self):
                effects.append("hash")
                return super().__hash__()
            def __eq__(self, other):
                effects.append("equality")
                return super().__eq__(other)
        class EffectfulTuple(tuple):
            def __iter__(self):
                effects.append("iteration")
                return super().__iter__()
        valid = ((self.parent,), self.judgment, 1)
        invalid = ((), [valid], EffectfulTuple((valid,)), (EffectfulTuple(valid),),
            ((EffectfulTuple((self.parent,)), self.judgment, 1),),
            (((EffectfulString(self.parent),), self.judgment, 1),),
            (((self.parent,), EffectfulString(self.judgment), 1),),
            (((self.parent,), self.judgment, True),),
            (((self.parent,), self.judgment, None),),
            (((self.parent,), self.judgment, 0),),
            (((self.parent,), self.judgment, 1.0),),
            (((self.parent, self.parent), self.judgment, 2),),
            (((" padded ",), self.judgment, 1),),
            (((self.parent,), self.judgment, 1), ((self.parent,), self.judgment, 1)),
            (((self.parent,), self.judgment), valid),
            ((self.history.before.event_ids, self.evaluation, 1),))
        sample, before = self.sample(), len(self.f.connection.calls)
        for nominations in invalid:
            with self.subTest(shape=type(nominations).__name__), self.assertRaises((PermissionError, ValueError)):
                sample.prime_source_purposes(nominations)
        for raw_ids in (EffectfulTuple(()), (EffectfulString("raw-object"),), ("x", "x")):
            with self.assertRaises((PermissionError, ValueError)):
                sample.prime_source_purposes((valid,), raw_object_ids=raw_ids)
        self.assertEqual(effects, [])
        self.assertEqual(len(self.f.connection.calls), before)

    def test_tampered_parent_ids_reject_before_effectful_hash_or_iteration(self):
        effects = []
        class ParentString(str):
            def __hash__(self):
                effects.append("hash")
                return super().__hash__()
        class ParentTuple(tuple):
            def __iter__(self):
                effects.append("iteration")
                return super().__iter__()
        actual = self.registry.lookup
        for parents in ((ParentString(self.parent),), ParentTuple((self.parent,))):
            def lookup(event_id):
                source = actual(event_id)
                return replace(source, evidence=replace(source.evidence, parent_refs=parents))
            with patch.object(self.registry, "lookup", side_effect=lookup):
                with self.assertRaisesRegex(PermissionError, "parent ID"):
                    self.sample().prime_source_purposes((((self.child,), self.judgment, 2),))
        self.assertEqual(effects, [])

    def test_legacy_pair_and_single_purpose_api_keep_their_inventory(self):
        legacy = self.sample()
        inventory = legacy.prime_source_purposes(
            (((self.parent,), self.evaluation), ((self.other,), self.evaluation),
             ((self.parent,), self.judgment)))
        self.assertEqual(dict(inventory), {self.evaluation: tuple(sorted((self.parent, self.other))),
                                          self.judgment: (self.parent,)})
        legacy.verify_final_current_rows()
        single = self.sample()
        self.assertEqual(single.prime_sources((self.child,), self.judgment),
                         tuple(sorted((self.parent, self.child))))
        single.verify_final_current_rows()


if __name__ == "__main__":
    unittest.main()
