"""Fresh permission authority reads with immutable action codec reuse only.

These use the existing canonical request/encrypted-object contract fixture.
Its SQL recorder is a deterministic boundary, not XTDB qualification or a
replacement model. Genuine decode calls are observed without replacing them.
"""
from contextlib import contextmanager
from copy import copy, deepcopy
import cProfile
import json
import sys
import unittest
from unittest.mock import Mock, patch

from cognitive_kernel import canonical, contracts
from cognitive_kernel.canonical import CognitiveKernelContractError
from cognitive_kernel.contracts import ProductHostScope
from flora.selected import formation_policy as selected
from flora.selected.formation_registry import XTDBFormationSourceRegistry
from flora.selected.phase_source_fence import OneGuardSelectedMetadata
import test_selected_formation_policy as fixture


@contextmanager
def native_action_decode_counts():
    """Count genuine native decoding while its callable identity stays fixed."""
    calls = {"decode": 0}
    code = selected.XTDBFormationPermissionPolicy._decode.__code__
    prior = sys.getprofile()
    def observe(frame, event, argument):
        if event == "call" and frame.f_code is code:
            calls["decode"] += 1
        if prior is not None:
            prior(frame, event, argument)
    sys.setprofile(observe)
    try:
        yield calls
    finally:
        sys.setprofile(prior)


class StoredActionCodecReuseTest(unittest.TestCase):
    # Reuse canonical ingress, encrypted payloads and actual policy application;
    # do not inherit the original test cases and run them twice accidentally.
    setUp = fixture.FormationPolicyContractTest.setUp
    _policy = fixture.FormationPolicyContractTest._policy
    _event = fixture.FormationPolicyContractTest._event
    _source = fixture.FormationPolicyContractTest._source
    _request = fixture.FormationPolicyContractTest._request
    _apply = fixture.FormationPolicyContractTest._apply
    _store = fixture.FormationPolicyContractTest._store

    def _grant(self, *, purpose="memory_formation"):
        request = self._request(self.original, purpose=purpose)
        self._apply(request)
        return request

    def _row(self, action_id, *, policy=None):
        policy = policy or self.policy
        key = policy._key("action", action_id)
        return self.connection.rows[(selected._ACTIONS, key)]

    def _rewrite(self, row, mutate):
        record = json.loads(row["record_json"])
        mutate(record)
        record["record_sha256"] = selected.canonical_sha256(
            {name: value for name, value in record.items() if name != "record_sha256"})
        row["record_json"] = json.dumps(record)
        row["record_sha256"] = record["record_sha256"]

    def test_native_repeated_action_decodes_once_but_fetches_every_time(self):
        grant = self._grant()
        policy = self._policy()
        initial_reads = len(self.connection.calls)
        with native_action_decode_counts() as calls:
            first = policy._stored_action(grant[0].action_id)
            second = policy._stored_action(grant[0].action_id)
            third = policy._stored_action(grant[0].action_id)
        self.assertEqual(calls["decode"], 1)
        self.assertEqual(len(self.connection.calls) - initial_reads, 3)
        self.assertEqual(first, second)
        self.assertEqual(second, third)
        for left, right in ((first, second), (first["scope"], second["scope"]),
                            (first["action"], second["action"]),
                            (first["action"]["scope"], second["action"]["scope"])):
            self.assertIsNot(left, right)

    def test_actual_fenced_fetch_view_can_reuse_codec_without_skipping_fetch(self):
        grant = self._grant()
        registry = XTDBFormationSourceRegistry(scope=self.scope,
            authority_namespace_id=self.namespace, connection=self.connection)
        policy = selected.XTDBFormationPermissionPolicy(scope=self.scope,
            authority_namespace_id=self.namespace, connection=self.connection, registry=registry)
        sample = OneGuardSelectedMetadata(registry=registry, permissions=policy)
        local = sample.local_permissions
        native_fetch = local._fetch
        observed = []
        def observed_fetch(*args, **kwargs):
            observed.append((args, kwargs))
            return native_fetch(*args, **kwargs)
        local._fetch = observed_fetch
        reads = len(self.connection.calls)
        with native_action_decode_counts() as calls:
            first = local._stored_action(grant[0].action_id)
            second = local._stored_action(grant[0].action_id)
        self.assertEqual(first, second)
        self.assertEqual(calls["decode"], 1)
        self.assertEqual(len(observed), 2)
        self.assertEqual(len(self.connection.calls) - reads, 1)
        # This checks the real sampled codec path only, not an authority grant;
        # terminal current-row fencing remains required by the guard's caller.

    def test_present_none_decoder_preserves_original_typeerror_after_warmup(self):
        grant = self._grant()
        policy = self._policy()
        policy._stored_action(grant[0].action_id)
        policy._decode = None
        with self.assertRaises(TypeError):
            policy._stored_action(grant[0].action_id)

    def test_current_integer_limit_changed_by_fetch_rejects_warmed_extra(self):
        previous = sys.get_int_max_str_digits()
        try:
            sys.set_int_max_str_digits(4300)
            grant = self._grant()
            self._rewrite(self._row(grant[0].action_id),
                lambda record: record.update(extra_integer=10 ** 999))
            policy = self._policy()
            policy._stored_action(grant[0].action_id)
            native_fetch = policy._fetch
            observed = []
            def changed_limit_fetch(*args, **kwargs):
                row = native_fetch(*args, **kwargs)
                observed.append("fetch")
                sys.set_int_max_str_digits(640)
                return row
            policy._fetch = changed_limit_fetch
            with native_action_decode_counts() as calls:
                with self.assertRaises(ValueError):
                    policy._stored_action(grant[0].action_id)
            self.assertEqual(observed, ["fetch"])
            self.assertEqual(calls["decode"], 1)
            with self.assertRaises(ValueError):
                self._policy()._stored_action(grant[0].action_id)
        finally:
            sys.set_int_max_str_digits(previous)

    def test_unknown_integer_limit_getter_uses_original_without_extra_callback(self):
        grant = self._grant()
        policy = self._policy()
        expected = policy._stored_action(grant[0].action_id)
        native_fetch = policy._fetch
        unknown_getter = Mock(side_effect=PermissionError("extra getter callback"))
        def changed_getter_fetch(*args, **kwargs):
            row = native_fetch(*args, **kwargs)
            sys.get_int_max_str_digits = unknown_getter
            return row
        policy._fetch = changed_getter_fetch
        with patch.object(sys, "get_int_max_str_digits", sys.get_int_max_str_digits):
            with native_action_decode_counts() as calls:
                actual = policy._stored_action(grant[0].action_id)
        self.assertEqual(actual, expected)
        self.assertEqual(calls["decode"], 1)
        unknown_getter.assert_not_called()

    def test_current_policy_scope_descriptor_runs_once_in_original_fallback(self):
        grant = self._grant()
        policy = self._policy()
        policy._stored_action(grant[0].action_id)
        observed = []
        def scope(current):
            observed.append("scope-descriptor")
            raise PermissionError("current policy scope withdrawn")
        with patch.object(selected.XTDBFormationPermissionPolicy, "scope", property(scope), create=True):
            with self.assertRaisesRegex(PermissionError, "policy scope withdrawn"):
                policy._stored_action(grant[0].action_id)
        self.assertEqual(observed, ["scope-descriptor"])

    def test_new_private_state_descriptor_is_never_an_original_callback(self):
        grant = self._grant()
        policy = self._policy()
        expected = policy._stored_action(grant[0].action_id)
        observed = []
        def get(current):
            observed.append("private-get")
            raise PermissionError("extra private callback")
        def put(current, value):
            observed.append("private-set")
            raise PermissionError("extra private callback")
        descriptor = property(get, put)
        with patch.object(selected.XTDBFormationPermissionPolicy, "_action_codec_memo", descriptor, create=True):
            with native_action_decode_counts() as calls:
                actual = policy._stored_action(grant[0].action_id)
        self.assertEqual(actual, expected)
        self.assertEqual(calls["decode"], 1)
        self.assertEqual(observed, [])

    def test_current_revocation_and_raw_read_barrier_stay_fresh_after_warmup(self):
        grant = self._grant()
        self.assertTrue(self.policy.permits(self.original, "memory_formation"))
        self.policy._stored_action(grant[0].action_id)
        revoked = self._request(self.original, "revoke", grant)
        self._apply(revoked)
        self.assertEqual(self.policy.current_action(self.original.evidence.ref_id,
                                                   "memory_formation"), revoked[0])
        self.assertFalse(self.policy.permits(self.original, "memory_formation"))
        with self.assertRaisesRegex(CognitiveKernelContractError, "permission revoked"):
            self._store().read(self.original.evidence)

    def test_changed_json_digest_scope_and_duplicate_or_missing_rows_stay_live(self):
        grant = self._grant()
        action_id = grant[0].action_id
        policy = self._policy()
        policy._stored_action(action_id)
        row = self._row(action_id)
        original = deepcopy(row)
        for field, value in (("record_json", "{}"), ("record_sha256", "f" * 64),
                             ("scope_digest", "foreign-scope"), ("_id", "wrong-id")):
            with self.subTest(field=field):
                row.update(original)
                row[field] = value
                with self.assertRaises((ValueError, KeyError)):
                    policy._stored_action(action_id)
        row.update(original)
        actual_execute = self.connection.execute
        def duplicate(statement, parameters):
            if statement.startswith("SELECT") and selected._ACTIONS in statement:
                self.connection.calls.append((statement, parameters))
                return fixture._Cursor([row, row])
            return actual_execute(statement, parameters)
        with patch.object(self.connection, "execute", side_effect=duplicate):
            with self.assertRaisesRegex(ValueError, "ambiguous rows"):
                policy._stored_action(action_id)
        key = policy._key("action", action_id)
        del self.connection.rows[(selected._ACTIONS, key)]
        self.assertIsNone(policy._stored_action(action_id))
        with self.assertRaisesRegex(ValueError, "lacks an immutable"):
            policy.current_action(self.original.evidence.ref_id, "memory_formation")

    def test_recomputed_outer_digest_cannot_hide_changed_action_or_request_binding(self):
        grant = self._grant()
        policy = self._policy()
        policy._stored_action(grant[0].action_id)
        row = self._row(grant[0].action_id)
        original = deepcopy(row)
        mutations = (
            lambda record: record["action"].update(decision="revoke"),
            lambda record: record["action"]["scope"].update(host_instance_id="foreign-host"),
            lambda record: record.update(request_payload_sha256="f" * 64),
            lambda record: record.update(event_stream_position=True),
        )
        for mutate in mutations:
            with self.subTest(change=mutate):
                row.update(original)
                self._rewrite(row, mutate)
                with self.assertRaises(ValueError):
                    policy._stored_action(grant[0].action_id)

    def test_returned_action_scope_and_nested_extra_data_cannot_poison_later_read(self):
        grant = self._grant()
        row = self._row(grant[0].action_id)
        self._rewrite(row, lambda record: record.update(
            extra={"notes": [{"meaning": "original"}], "flags": [True, None, 7]}))
        policy = self._policy()
        returned = policy._stored_action(grant[0].action_id)
        expected = deepcopy(returned)
        # Both the initially decoded object and a later hit must be detached.
        for _ in range(2):
            returned["action"]["decision"] = "revoke"
            returned["action"]["scope"]["host_instance_id"] = "foreign-host"
            returned["scope"]["product_id"] = "foreign-product"
            returned["extra"]["notes"][0]["meaning"] = "forged"
            returned["extra"]["flags"].append("forged")
            returned = policy._stored_action(grant[0].action_id)
            self.assertEqual(returned, expected)

    def test_key_and_actual_custom_fetch_are_called_in_order_on_every_read(self):
        grant = self._grant()
        policy = self._policy()
        policy._stored_action(grant[0].action_id)
        actual_key, actual_fetch = policy._key, policy._fetch
        order = []
        def key(*args):
            order.append("key")
            return actual_key(*args)
        def fetch(*args, **kwargs):
            order.append("fetch")
            return actual_fetch(*args, **kwargs)
        policy._key, policy._fetch = key, fetch
        for _ in range(2):
            self.assertIsNotNone(policy._stored_action(grant[0].action_id))
        self.assertEqual(order, ["key", "fetch", "key", "fetch"])

    def test_custom_key_cannot_reuse_one_action_for_another_lookup(self):
        grant = self._grant()
        policy = self._policy()
        policy._stored_action(grant[0].action_id)
        key = policy._key("action", grant[0].action_id)
        policy._key = lambda *args: key
        with self.assertRaisesRegex(ValueError, "differs from its lookup"):
            policy._stored_action("different-action")

    def test_changed_scope_and_namespace_after_fetch_do_not_reuse_old_host_action(self):
        grant = self._grant()
        other = ProductHostScope.create(product_id="friday", host_instance_id="other-host",
            schema_version="1.0.0", encryption_domain="other-key")
        for name, value in (("scope", other), ("authority_namespace_id", "other-authority"),
                            ("scope_digest", "other-digest")):
            with self.subTest(owner_field=name):
                policy = self._policy()
                policy._stored_action(grant[0].action_id)
                actual_fetch = policy._fetch
                def fetch(*args, **kwargs):
                    row = actual_fetch(*args, **kwargs)
                    setattr(policy, name, value)
                    return row
                policy._fetch = fetch
                with self.assertRaisesRegex(ValueError, "metadata changed"):
                    policy._stored_action(grant[0].action_id)

    def test_fetch_callback_current_delegate_withdrawals_execute_original_fallback(self):
        grant = self._grant()
        targets = ((selected.XTDBFormationPermissionPolicy, "_decode"),
                   (selected, "_action_from_record"),
                   (selected, "FormationPermissionAction"),
                   (selected.FormationPermissionAction, "validate"),
                   (selected, "canonical_sha256"),
                   (canonical, "canonical_json_bytes"),
                   (canonical, "require_text"))
        for target, name in targets:
            with self.subTest(delegate=name):
                policy = self._policy()
                policy._stored_action(grant[0].action_id)
                actual_fetch = policy._fetch
                denial = Mock(side_effect=PermissionError("current delegate withdrawn"))
                original = getattr(target, name)
                def fetch(*args, **kwargs):
                    row = actual_fetch(*args, **kwargs)
                    setattr(target, name, denial)
                    return row
                policy._fetch = fetch
                try:
                    with self.assertRaisesRegex(PermissionError, "delegate withdrawn"):
                        policy._stored_action(grant[0].action_id)
                    self.assertGreater(denial.call_count, 0)
                finally:
                    setattr(target, name, original)

    def test_in_place_native_decoder_and_parser_code_withdrawal_stays_live(self):
        grant = self._grant()
        for delegate in (selected.XTDBFormationPermissionPolicy._decode,
                         selected._action_from_record):
            with self.subTest(delegate=delegate.__name__):
                policy = self._policy()
                policy._stored_action(grant[0].action_id)
                original = delegate.__code__
                def deny(*args, **kwargs):
                    raise PermissionError("current delegate code withdrawn")
                try:
                    delegate.__code__ = deny.__code__
                    with self.assertRaisesRegex(PermissionError, "code withdrawn"):
                        policy._stored_action(grant[0].action_id)
                finally:
                    delegate.__code__ = original

    def test_current_scope_product_contract_withdrawal_cannot_use_a_warm_record(self):
        grant = self._grant()
        policy = self._policy()
        policy._stored_action(grant[0].action_id)
        with patch.object(contracts, "PRODUCT_IDS", frozenset({"alice"})):
            with self.assertRaisesRegex(CognitiveKernelContractError, "product_id is not approved"):
                policy._stored_action(grant[0].action_id)

    def test_current_decode_descriptor_runs_once_and_its_parser_withdrawal_stays_live(self):
        grant = self._grant()
        policy = self._policy()
        policy._stored_action(grant[0].action_id)
        policy_class = selected.XTDBFormationPermissionPolicy
        native_decoder = vars(policy_class)["_decode"]
        native_parser = selected._action_from_record
        order = []
        def deny(record):
            order.append("parser-denied")
            raise PermissionError("decode descriptor withdrew the current parser")
        def decoder(current):
            order.append("decode-descriptor")
            selected._action_from_record = deny
            return native_decoder.__get__(current, type(current))
        try:
            policy_class._decode = property(decoder)
            with self.assertRaisesRegex(PermissionError, "descriptor withdrew"):
                policy._stored_action(grant[0].action_id)
        finally:
            policy_class._decode = native_decoder
            selected._action_from_record = native_parser
        self.assertEqual(order, ["decode-descriptor", "parser-denied"])

    def test_rebound_private_codec_helpers_use_original_native_validation(self):
        grant = self._grant()
        for name in ("_action_codec_current", "_action_codec_probe", "_restore_action_record",
                     "_snapshot_action_record", "_same_action_codec_owner", "_remember_action_record"):
            with self.subTest(helper=name):
                policy = self._policy()
                expected = policy._stored_action(grant[0].action_id)
                with patch.object(selected, name,
                        side_effect=AssertionError("custom codec helper must not execute")) as helper:
                    with native_action_decode_counts() as calls:
                        self.assertEqual(policy._stored_action(grant[0].action_id), expected)
                    self.assertEqual(calls["decode"], 1)
                    helper.assert_not_called()

    def test_private_current_and_restore_code_changes_keep_native_validation(self):
        grant = self._grant()
        for name in ("_action_codec_current", "_restore_action_record"):
            with self.subTest(helper=name):
                policy = self._policy()
                expected = policy._stored_action(grant[0].action_id)
                delegate = getattr(selected, name)
                original = delegate.__code__
                def deny(*args, **kwargs):
                    raise AssertionError("changed private helper must not execute")
                try:
                    delegate.__code__ = deny.__code__
                    with native_action_decode_counts() as calls:
                        self.assertEqual(policy._stored_action(grant[0].action_id), expected)
                    self.assertEqual(calls["decode"], 1)
                finally:
                    delegate.__code__ = original

    def test_effectful_row_reads_and_scope_receiver_keep_original_callback_order(self):
        grant = self._grant()
        row = deepcopy(self._row(grant[0].action_id))
        policy = self._policy()
        policy._stored_action(grant[0].action_id)
        accesses = []
        class CurrentRow(dict):
            def __getitem__(self, name):
                accesses.append(name)
                return super().__getitem__(name)
        policy._fetch = lambda *args, **kwargs: CurrentRow(row)
        for _ in range(2):
            accesses.clear()
            self.assertIsNotNone(policy._stored_action(grant[0].action_id))
            self.assertEqual(accesses, ["record_json", "_id", "scope_digest",
                                        "record_sha256", "record_sha256"])
        seen = []
        def metadata():
            seen.append("scope")
            raise PermissionError("current scope receiver withdrawn")
        try:
            object.__setattr__(self.scope, "metadata_record", metadata)
            with self.assertRaisesRegex(PermissionError, "scope receiver withdrawn"):
                policy._stored_action(grant[0].action_id)
        finally:
            self.scope.__dict__.pop("metadata_record", None)
        self.assertEqual(seen, ["scope"])

    def test_row_getter_late_withdrawal_is_observed_before_action_validation(self):
        grant = self._grant()
        policy = self._policy()
        policy._stored_action(grant[0].action_id)
        row = self._row(grant[0].action_id)
        original = selected._action_from_record
        denial = Mock(side_effect=PermissionError("row getter withdrew action parser"))
        class CurrentRow(dict):
            def __getitem__(self, name):
                if name == "record_json":
                    selected._action_from_record = denial
                return super().__getitem__(name)
        policy._fetch = lambda *args, **kwargs: CurrentRow(row)
        try:
            with self.assertRaisesRegex(PermissionError, "getter withdrew"):
                policy._stored_action(grant[0].action_id)
        finally:
            selected._action_from_record = original
        self.assertEqual(denial.call_count, 1)

    def test_effectful_encoded_string_conversion_keeps_current_parser_live(self):
        grant = self._grant()
        policy = self._policy()
        policy._stored_action(grant[0].action_id)
        row = self._row(grant[0].action_id)
        original = selected._action_from_record
        denial = Mock(side_effect=PermissionError("string conversion withdrew parser"))
        conversions = []
        class CurrentString(str):
            def __str__(self):
                conversions.append("convert")
                selected._action_from_record = denial
                return super().__str__()
        row["record_json"] = CurrentString(row["record_json"])
        try:
            with self.assertRaisesRegex(PermissionError, "conversion withdrew"):
                policy._stored_action(grant[0].action_id)
        finally:
            selected._action_from_record = original
        self.assertEqual(conversions, ["convert"])
        self.assertEqual(denial.call_count, 1)

    def test_custom_policy_subclass_revalidates_each_action_read(self):
        grant = self._grant()
        class CurrentPolicy(selected.XTDBFormationPermissionPolicy):
            pass
        policy = CurrentPolicy(scope=self.scope, authority_namespace_id=self.namespace,
            connection=self.connection, registry=self.registry)
        with native_action_decode_counts() as calls:
            policy._stored_action(grant[0].action_id)
            policy._stored_action(grant[0].action_id)
        self.assertEqual(calls["decode"], 2)

    def test_deep_extra_record_accepted_by_native_codec_skips_bookkeeping_safely(self):
        grant = self._grant()
        row = self._row(grant[0].action_id)
        extra = "leaf"
        for _ in range(550):
            extra = [extra]
        self._rewrite(row, lambda record: record.update(extra=extra))
        policy = self._policy()
        # Compare through native encoded bytes; deep Python dict comparison is
        # itself a separate recursion boundary and is not the product behavior.
        for _ in range(2):
            result = policy._stored_action(grant[0].action_id)
            self.assertEqual(selected._record_json(result), selected._record_json(json.loads(row["record_json"])))
            self.assertEqual(result["action"]["decision"], "allow")

    def test_warm_hit_at_lower_recursion_capacity_runs_original_decoder(self):
        grant = self._grant()
        row = self._row(grant[0].action_id)
        extra = "leaf"
        for _ in range(180):
            extra = [extra]
        self._rewrite(row, lambda record: record.update(extra=extra))
        policy = self._policy()
        policy._stored_action(grant[0].action_id)
        initial_limit = sys.getrecursionlimit()
        def call_at_depth(remaining):
            if remaining:
                return call_at_depth(remaining - 1)
            return policy._stored_action(grant[0].action_id)
        try:
            sys.setrecursionlimit(330)
            # A Python profile callback consumes recursion capacity itself and
            # can be disabled by that exception. The native profiler observes
            # the original decoder without adding a Python callback frame.
            profile = cProfile.Profile()
            try:
                profile.enable()
                result = call_at_depth(170)
            finally:
                profile.disable()
            decode = selected.XTDBFormationPermissionPolicy._decode.__code__
            self.assertEqual(sum(entry.callcount for entry in profile.getstats()
                                 if entry.code is decode), 1)
            self.assertEqual(result["action"]["decision"], "allow")
        finally:
            sys.setrecursionlimit(initial_limit)

    def test_oversized_outer_record_is_revalidated_every_time(self):
        grant = self._grant()
        row = self._row(grant[0].action_id)
        self._rewrite(row, lambda record: record.update(extra="x" * (2 * 1024 * 1024)))
        policy = self._policy()
        with native_action_decode_counts() as calls:
            first = policy._stored_action(grant[0].action_id)
            second = policy._stored_action(grant[0].action_id)
        self.assertEqual(first, second)
        self.assertEqual(calls["decode"], 2)

    def test_total_encoded_byte_cap_evicts_instead_of_growing_without_bound(self):
        grants = [self._grant(purpose=f"large-memory-{index}") for index in range(2)]
        for grant in grants:
            self._rewrite(self._row(grant[0].action_id),
                          lambda record: record.update(extra="x" * (1100 * 1024)))
        policy = self._policy()
        with native_action_decode_counts() as calls:
            policy._stored_action(grants[0][0].action_id)
            policy._stored_action(grants[1][0].action_id)
            policy._stored_action(grants[0][0].action_id)
        self.assertEqual(calls["decode"], 3)
        self.assertEqual(len(policy._action_codec_memo[1]), 1)
        self.assertEqual(policy._action_codec_memo[2],
                         len(self._row(grants[0][0].action_id)["record_json"].encode("utf-8")))

    def test_default_copy_insert_eviction_and_owner_clear_are_independent(self):
        grants = [self._grant(purpose=f"memory-formation-{index}") for index in range(257)]
        policy = self._policy()
        for grant in grants[:256]:
            policy._stored_action(grant[0].action_id)
        _, contents, byte_count = policy._action_codec_memo
        encoded_sizes = [len(self._row(grant[0].action_id)["record_json"].encode("utf-8"))
                         for grant in grants]
        self.assertEqual(len(contents), 256)
        self.assertEqual(byte_count, sum(encoded_sizes[:256]))
        before = dict(contents)
        cloned = copy(policy)
        cloned._stored_action(grants[-1][0].action_id)
        self.assertEqual(dict(policy._action_codec_memo[1]), before)
        self.assertEqual(policy._action_codec_memo[2], byte_count)
        self.assertIsNot(policy._action_codec_memo[1], cloned._action_codec_memo[1])
        self.assertLessEqual(len(cloned._action_codec_memo[1]), 256)
        self.assertEqual(cloned._action_codec_memo[2], sum(encoded_sizes[1:]))
        with native_action_decode_counts() as calls:
            policy._stored_action(grants[0][0].action_id)
            self.assertEqual(calls["decode"], 0)
            cloned._stored_action(grants[0][0].action_id)
        self.assertEqual(calls["decode"], 1)
        fresh_connection = fixture._SQLCalls()
        fresh_connection.rows = deepcopy(self.connection.rows)
        cloned.connection = fresh_connection
        with native_action_decode_counts() as calls:
            cloned._stored_action(grants[0][0].action_id)
            policy._stored_action(grants[0][0].action_id)
        self.assertEqual(calls["decode"], 1)
        self.assertEqual(len(cloned._action_codec_memo[1]), 1)
        self.assertEqual(cloned._action_codec_memo[2], encoded_sizes[0])
        self.assertEqual(len(policy._action_codec_memo[1]), 256)
        self.assertGreater(cloned._action_codec_memo[2], 0)
        self.assertLessEqual(cloned._action_codec_memo[2], 2 * 1024 * 1024)
        self.assertEqual(policy._action_codec_memo[2], byte_count)


if __name__ == "__main__":
    unittest.main()
