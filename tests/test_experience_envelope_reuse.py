"""Native Experience codec with fresh encoded transport; no backend qualification."""
from contextlib import contextmanager
from copy import copy
from datetime import datetime, timezone, tzinfo
import json
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4
from kurrentdbclient import RecordedEvent

from cognitive_kernel import canonical, experience as contracts
from cognitive_kernel.contracts import ProductHostScope
from cognitive_kernel.experience import ExperienceEvent
from flora.selected import experience as selected
from test_selected_experience import event_for


def record(event, position=0):
    return RecordedEvent(stream_position=position, type="FableExperienceV1",
        data=selected.encode_event(event), id=selected.event_uuid(event), metadata=b"",
        content_type="application/json", stream_name=selected.stream_name(event.scope),
        commit_position=position, prepare_position=position,
        recorded_at=datetime(2026, 9, 30, tzinfo=timezone.utc))


class EncodedClient:
    def __init__(self, records):
        self.records, self.reads = list(records), 0

    def get_stream(self, *, stream_name):
        self.reads += 1
        return tuple(self.records)


@contextmanager
def native_decode_counts():
    """Observe genuine code execution without replacing an eligible delegate."""
    counts = {"decode": 0}
    code = selected.decode_event.__code__
    prior = sys.getprofile()
    def observe(frame, event, argument):
        if event == "call" and frame.f_code is code:
            counts["decode"] += 1
        if prior is not None:
            prior(frame, event, argument)
    sys.setprofile(observe)
    try:
        yield counts
    finally:
        sys.setprofile(prior)


class ExperienceEnvelopeReuseTest(unittest.TestCase):
    def setUp(self):
        self.event = event_for("host-one")
        self.row = record(self.event)
        self.client = EncodedClient([self.row])
        self.log = selected.KurrentExperienceLog(scope=self.event.scope, client=self.client)

    def test_repeated_native_envelope_decodes_once_and_returns_fresh_nested_contracts(self):
        with native_decode_counts() as calls:
            first = self.log.replay_committed()[0]
            second = self.log.replay_committed()[0]
            third = self.log.replay()[0]
        self.assertEqual(calls["decode"], 1)
        self.assertEqual(self.client.reads, 3)
        self.assertEqual(first, second)
        self.assertEqual(third, first.event)
        self.assertIsNot(first, second)
        for left, right in ((first.event, second.event),
                            (first.event.scope, second.event.scope),
                            (first.event.provenance, second.event.provenance)):
            self.assertIsNot(left, right)

    def test_mutating_returned_event_and_nested_contracts_cannot_poison_later_replay(self):
        returned = self.log.replay_committed()[0]
        returned.event.__dict__["event_type"] = "forged"
        returned.event.scope.__dict__["host_instance_id"] = "wrong-host"
        object.__setattr__(returned.event.provenance, "responsible_component", "forged")
        object.__setattr__(returned, "recorded_at", None)
        fresh = self.log.replay_committed()[0]
        self.assertEqual(fresh.event, self.event)
        self.assertEqual(fresh.recorded_at, self.row.recorded_at)

    def test_every_current_position_type_id_time_and_absence_is_checked_after_warmup(self):
        self.log.replay_committed()
        for field, value, error in (("stream_position", 1, "unexpected event"),
                                   ("type", "WrongType", "unexpected event"),
                                   ("id", uuid4(), "event ID differs"),
                                   ("recorded_at", datetime(2026, 9, 30), "timezone-aware")):
            original = getattr(self.row, field)
            object.__setattr__(self.row, field, value)
            try:
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, error):
                    self.log.replay_committed()
            finally:
                object.__setattr__(self.row, field, original)
        original = self.row.recorded_at
        object.__setattr__(self.row, "recorded_at", None)
        self.assertIsNone(self.log.replay_committed()[0].recorded_at)
        object.__setattr__(self.row, "recorded_at", original)
        self.client.records.clear()
        self.assertEqual(self.log.replay_committed(), ())
        self.assertEqual(self.client.reads, 7)

    def test_changed_bytes_are_decoded_and_invalid_envelope_is_not_reused_by_id(self):
        self.log.replay_committed()
        changed = json.loads(self.row.data)
        changed["content_digest"] = "0" * 64
        object.__setattr__(self.row, "data", json.dumps(changed).encode())
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            self.log.replay_committed()

    def test_current_decoder_and_contract_and_helper_denials_keep_original_path(self):
        self.log.replay_committed()
        for target, name in ((selected, "decode_event"),
                             (ExperienceEvent, "from_metadata_record"),
                             (ExperienceEvent, "validate"),
                             (canonical, "require_text")):
            with self.subTest(delegate=name), patch.object(target, name,
                    side_effect=PermissionError("current native delegate withdrawn")) as callback:
                with self.assertRaisesRegex(PermissionError, "delegate withdrawn"):
                    self.log.replay_committed()
                self.assertGreater(callback.call_count, 0)

    def test_private_restore_snapshot_and_owner_overrides_cannot_qualify_a_hit(self):
        self.log.replay_committed()
        for name in ("_restore_envelope", "_envelope_snapshot", "_primitive", "_same_owner"):
            with self.subTest(helper=name), patch.object(selected, name,
                    side_effect=AssertionError("custom private helper must not run")):
                with native_decode_counts() as calls:
                    self.assertEqual(self.log.replay_committed()[0].event, self.event)
                self.assertEqual(calls["decode"], 1)
        with patch.object(self.log, "_codec_owner", return_value=(self.client, self.log.stream, ())) as helper:
            with native_decode_counts() as calls:
                self.log.replay_committed()
            self.assertEqual(calls["decode"], 1)
            helper.assert_not_called()

    def test_private_restore_code_mutation_cannot_skip_native_validation(self):
        self.log.replay_committed()
        restore = selected._restore_envelope
        original = restore.__code__
        def changed(snapshot):
            raise AssertionError("changed restore must not run")
        try:
            restore.__code__ = changed.__code__
            with native_decode_counts() as calls:
                self.assertEqual(self.log.replay_committed()[0].event, self.event)
            self.assertEqual(calls["decode"], 1)
        finally:
            restore.__code__ = original

    def test_custom_committed_wrapper_keeps_later_decoder_withdrawal_live(self):
        from dataclasses import replace
        self.client.records.append(replace(self.row, stream_position=1,
            commit_position=1, prepare_position=1))
        self.log.replay_committed()
        wrapper = selected.CommittedExperience
        original = selected.decode_event
        calls = []
        def deny(*args):
            raise PermissionError("wrapper withdrew the next decoder")
        def custom(*args):
            calls.append(args)
            selected.decode_event = deny
            return wrapper(*args)
        try:
            with patch.object(selected, "CommittedExperience", side_effect=custom):
                with self.assertRaisesRegex(PermissionError, "wrapper withdrew"):
                    self.log.replay_committed()
        finally:
            selected.decode_event = original
        self.assertEqual(len(calls), 1)

    def test_generator_and_tuple_subclass_callbacks_keep_live_original_decoder(self):
        self.log.replay_committed()
        original = selected.decode_event
        row = self.row
        def deny(*args):
            raise PermissionError("iterator withdrew decoder")
        def generate():
            selected.decode_event = deny
            yield row
        class EffectfulTuple(tuple):
            def __iter__(self):
                selected.decode_event = deny
                return super().__iter__()
        for rows in (generate(), EffectfulTuple((row,))):
            with self.subTest(iterator=type(rows).__name__):
                try:
                    with patch.object(self.client, "get_stream", return_value=rows):
                        with self.assertRaisesRegex(PermissionError, "iterator withdrew"):
                            self.log.replay_committed()
                finally:
                    selected.decode_event = original

    def test_custom_timezone_callback_stays_uncached_and_runs_on_every_read(self):
        self.log.replay_committed()
        calls = []
        class CurrentTime(tzinfo):
            def utcoffset(self, value):
                calls.append(value)
                return None
        object.__setattr__(self.row, "recorded_at", datetime(2026, 9, 30, tzinfo=CurrentTime()))
        with native_decode_counts() as decodes:
            for _ in range(2):
                with self.assertRaisesRegex(ValueError, "timezone-aware"):
                    self.log.replay_committed()
        self.assertEqual(decodes["decode"], 2)
        self.assertEqual(len(calls), 2)

    def test_in_place_schema_key_set_change_uses_current_contract(self):
        self.log.replay_committed()
        keys = contracts._EXPERIENCE_EVENT_KEYS
        original = set(keys)
        try:
            keys.remove("event_type")
            with self.assertRaisesRegex(ValueError, "keys are invalid"):
                self.log.replay_committed()
        finally:
            keys.clear()
            keys.update(original)

    def test_contract_changed_by_data_getter_is_called_once_with_current_scope(self):
        self.log.replay_committed()
        row = self.row
        original = ExperienceEvent.__dict__["from_metadata_record"]
        seen = []
        def deny(data):
            seen.append(data)
            raise PermissionError("data callback decoder withdrawal")
        class CallbackRecord:
            stream_position, type = 0, "FableExperienceV1"
            @property
            def data(self):
                ExperienceEvent.from_metadata_record = staticmethod(deny)
                return row.data
        self.client.records = [CallbackRecord()]
        try:
            with self.assertRaisesRegex(PermissionError, "data callback"):
                self.log.replay_committed()
        finally:
            ExperienceEvent.from_metadata_record = original
        self.assertEqual(seen, [json.loads(row.data)])

    def test_id_getter_rebinds_uuid_delegate_before_its_actual_rhs_call(self):
        self.log.replay_committed()
        row = self.row
        original = selected.event_uuid
        seen = []
        def deny(event):
            seen.append(event)
            raise PermissionError("ID callback UUID withdrawal")
        class CallbackRecord:
            stream_position, type, data = 0, "FableExperienceV1", row.data
            @property
            def id(self):
                selected.event_uuid = deny
                return row.id
        self.client.records = [CallbackRecord()]
        try:
            with self.assertRaisesRegex(PermissionError, "ID callback"):
                self.log.replay_committed()
        finally:
            selected.event_uuid = original
        self.assertEqual(seen, [self.event])

    def test_each_record_attribute_is_read_once_in_original_order(self):
        self.log.replay_committed()
        row, accesses = self.row, []
        class CallbackRecord:
            def __getattr__(self, name):
                accesses.append(name)
                return getattr(row, name)
        self.client.records = [CallbackRecord()]
        self.assertEqual(self.log.replay_committed()[0].event, self.event)
        self.assertEqual(accesses, ["stream_position", "type", "data", "id", "recorded_at"])

    def test_scope_rebind_during_data_read_denies_old_host_envelope(self):
        self.log.replay_committed()
        row, log = self.row, self.log
        other = event_for("host-two").scope
        class CallbackRecord:
            stream_position, type = 0, "FableExperienceV1"
            @property
            def data(self):
                log.scope = other
                return row.data
        self.client.records = [CallbackRecord()]
        with self.assertRaisesRegex(ValueError, "host scope"):
            self.log.replay_committed()

    def test_client_and_stream_rebind_revalidate_exact_envelope_on_new_owner(self):
        with native_decode_counts() as calls:
            self.log.replay_committed()
            other = EncodedClient([self.row])
            self.log.client = other
            self.log.replay_committed()
            self.log.stream = self.log.stream + "-new"
            self.log.replay_committed()
        self.assertEqual(calls["decode"], 3)
        self.assertEqual(self.client.reads, 1)
        self.assertEqual(other.reads, 2)

    def test_actual_get_stream_callback_withdrawal_precedes_fresh_codec_eligibility(self):
        self.log.replay_committed()
        original = selected.decode_event
        def deny(*args):
            raise PermissionError("transport callback withdrew decoder")
        def current(**kwargs):
            self.client.reads += 1
            selected.decode_event = deny
            return (self.row,)
        try:
            with patch.object(self.client, "get_stream", side_effect=current):
                with self.assertRaisesRegex(PermissionError, "transport callback"):
                    self.log.replay_committed()
        finally:
            selected.decode_event = original
        self.assertEqual(self.client.reads, 2)

    def test_subclass_and_instance_scope_override_keep_uncached_original_decoder(self):
        class CustomLog(selected.KurrentExperienceLog):
            pass
        custom = CustomLog(scope=self.event.scope, client=self.client)
        with native_decode_counts() as calls:
            custom.replay_committed()
            custom.replay_committed()
        self.assertEqual(calls["decode"], 2)
        object.__setattr__(self.log.scope, "validate", lambda: None)
        with native_decode_counts() as calls:
            self.log.replay_committed()
            self.log.replay_committed()
        self.assertEqual(calls["decode"], 2)

    def test_bounded_eviction_and_oversized_entries_keep_fresh_decoding(self):
        events = [event_for("host-one")]
        for index in range(2):
            base = events[0]
            events.append(ExperienceEvent.create(event_type="observation", scope=base.scope,
                occurred_at=f"2026-09-{27 + index}T00:00:00Z", content_digest=base.content_digest,
                provenance=base.provenance, retention_class=base.retention_class,
                storage_tier=base.storage_tier, payload_reference=base.payload_reference))
        self.client.records = [record(event, index) for index, event in enumerate(events)]
        with patch.object(selected, "_MAX_ENVELOPES", 2), native_decode_counts() as calls:
            self.assertEqual(len(self.log.replay_committed()), 3)
            self.assertEqual(len(self.log.replay_committed()), 3)
        self.assertEqual(calls["decode"], 6)
        with patch.object(selected, "_MAX_ENVELOPE_BYTES", 1):
            fresh = selected.KurrentExperienceLog(scope=self.event.scope, client=self.client)
            with native_decode_counts() as calls:
                fresh.replay_committed()
                fresh.replay_committed()
            self.assertEqual(calls["decode"], 6)

    def test_default_copy_cache_accounting_remains_independent_after_mutation(self):
        self.log.replay_committed()
        cloned = copy(self.log)
        cloned.client = EncodedClient([])
        cloned.replay_committed()
        # Rebinding/clearing a clone cannot remove the original's validated
        # envelope or leave its byte counter referring to an emptied map.
        with native_decode_counts() as calls:
            self.log.replay_committed()
        self.assertEqual(calls["decode"], 0)
        self.assertEqual(self.log._envelope_memo[2], sum(map(len, self.log._envelope_memo[1])))
        self.assertEqual(cloned._envelope_memo[2], sum(map(len, cloned._envelope_memo[1])))
        self.assertIsNot(cloned._envelope_memo[1], self.log._envelope_memo[1])
        from dataclasses import replace
        clone = copy(self.log)
        self.client.records = [self.row,
            replace(self.row, stream_position=1, data=self.row.data + b" ",
                    commit_position=1, prepare_position=1),
            replace(self.row, stream_position=2, data=self.row.data + b"  ",
                    commit_position=2, prepare_position=2)]
        with patch.object(selected, "_MAX_ENVELOPES", 2):
            clone.replay_committed()
        self.client.records = [self.row]
        with native_decode_counts() as calls:
            self.log.replay_committed()
        self.assertEqual(calls["decode"], 0)
        for log in (self.log, clone):
            self.assertEqual(log._envelope_memo[2], sum(map(len, log._envelope_memo[1])))
        self.assertIsNot(clone._envelope_memo[1], self.log._envelope_memo[1])

    def test_cached_native_envelopes_do_not_cache_actual_selected_owner_permission(self):
        from test_history_fence import HistoryFenceTest
        fixture = HistoryFenceTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        old_log = fixture.f.log
        from dataclasses import replace
        committed_at = datetime(2026, 9, 29, 14, tzinfo=timezone.utc)
        client = EncodedClient([replace(record(event, index), recorded_at=committed_at)
                               for index, event in enumerate(old_log.events)])
        native = selected.KurrentExperienceLog(scope=fixture.f.scope, client=client)
        fixture.custody.log = native
        fixture.verify()
        fixture.verify()
        warmed_reads = client.reads
        fixture.grant(fixture.materials[0].event.event_id, "before", "deny")
        client.records = [replace(record(event, index), recorded_at=committed_at)
                          for index, event in enumerate(old_log.events)]
        with self.assertRaises(PermissionError):
            fixture.verify()
        self.assertGreater(client.reads, warmed_reads)


if __name__ == "__main__":
    unittest.main()
