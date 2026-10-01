"""Exact Experience target proofs; controlled transport, not backend qualification."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import inspect
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from kurrentdbclient import KurrentDBClient
from kurrentdbclient.exceptions import NotFoundError

from cognitive_kernel.canonical import normalize_timestamp
from cognitive_kernel.experience import ExperienceEvent
from flora.selected import experience as selected
from test_experience_envelope_reuse import native_decode_counts, record
from test_selected_experience import event_for


class BoundedClient:
    """Controlled encoded rows with the selected SDK's explicit read bounds."""

    def __init__(self, records):
        self.records = list(records)
        self.reads = []
        self.on_read = None

    def get_stream(self, *, stream_name, stream_position=None, limit=None,
                   resolve_links=False):
        self.reads.append({"stream_name": stream_name, "stream_position": stream_position,
                           "limit": limit, "resolve_links": resolve_links})
        if self.on_read is not None:
            self.on_read()
        rows = self.records if stream_position is None else [
            row for row in self.records if row.stream_position >= stream_position]
        return tuple(rows if limit is None else rows[:limit])


class ExperienceExactLookupTest(unittest.TestCase):
    def setUp(self):
        base = event_for("host-one")
        self.events = [ExperienceEvent.create(event_type="observation", scope=base.scope,
            occurred_at=f"2026-09-29T00:00:{index:02d}Z",
            content_digest=hashlib.sha256(f"controlled-{index}".encode()).hexdigest(),
            provenance=base.provenance, retention_class=base.retention_class,
            storage_tier=base.storage_tier, payload_reference=base.payload_reference)
            for index in range(10)]
        self.rows = [record(event, index) for index, event in enumerate(self.events)]
        self.event, self.row = self.events[7], self.rows[7]
        self.client = BoundedClient(self.rows)
        self.log = selected.KurrentExperienceLog(scope=self.event.scope, client=self.client)
        self.lookup_args = {"event_id": self.event.event_id,
                            "event_sha256": self.event.event_sha256,
                            "stream_position": self.row.stream_position,
                            "expected_recorded_at": normalize_timestamp(self.row.recorded_at.isoformat())}

    def lookup(self, **changes):
        return self.log.lookup_committed(**(self.lookup_args | changes))

    def test_sdk_exposes_the_required_explicit_read_bounds(self):
        parameters = inspect.signature(KurrentDBClient.get_stream).parameters
        self.assertTrue({"stream_name", "stream_position", "limit", "resolve_links"}
                        .issubset(parameters))

    def test_exact_read_requests_one_named_position_without_link_resolution(self):
        entry = self.lookup()
        self.assertEqual(entry.event, self.event)
        self.assertEqual(entry.stream_position, 7)
        self.assertEqual(entry.recorded_at, self.row.recorded_at)
        self.assertEqual(self.client.reads, [{"stream_name": self.log.stream,
            "stream_position": 7, "limit": 1, "resolve_links": False}])

    def test_repeated_calls_sample_transport_and_return_unshared_contracts(self):
        with native_decode_counts() as decodes:
            first, second = self.lookup(), self.lookup()
        self.assertEqual(len(self.client.reads), 2)
        self.assertEqual(decodes["decode"], 1)
        self.assertEqual(first, second)
        self.assertIsNot(first.event, second.event)
        self.assertIsNot(first.event.scope, second.event.scope)
        self.assertIsNot(first.event.provenance, second.event.provenance)
        first.event.__dict__["event_type"] = "forged"
        first.event.scope.__dict__["host_instance_id"] = "forged"
        self.assertEqual(self.lookup().event, self.event)

    def test_unrelated_corrupted_envelope_is_never_decoded_by_target_lookup(self):
        self.client.records[0] = replace(self.rows[0], data=b"not-json")
        self.client.records[9] = replace(self.rows[9], data=b"not-json")
        with native_decode_counts() as decodes:
            self.assertEqual(self.lookup().event, self.event)
        self.assertEqual(decodes["decode"], 1)
        with self.assertRaises(ValueError):
            self.log.replay_committed()

    def test_target_proof_does_not_claim_unrelated_prefix_or_tail_integrity(self):
        self.client.records = [self.row]
        self.assertEqual(self.lookup().event, self.event)
        with self.assertRaisesRegex(ValueError, "gap"):
            self.log.replay_committed()

    def test_missing_or_truncated_target_fails_after_successful_read(self):
        self.lookup()
        for rows in ([], self.rows[:7], self.rows[8:]):
            self.client.records = rows
            with self.subTest(rows=len(rows)), self.assertRaises(ValueError):
                self.lookup()
        self.assertEqual(len(self.client.reads), 4)

    def test_not_found_is_absence_and_does_not_return_a_warm_envelope(self):
        self.lookup()
        with patch.object(self.client, "get_stream", side_effect=NotFoundError()) as read:
            with self.assertRaisesRegex(ValueError, "absent"):
                self.lookup()
        read.assert_called_once()

    def test_transport_type_error_is_not_caught_or_retried_as_replay(self):
        with patch.object(self.client, "get_stream", side_effect=TypeError("transport failure")) as read:
            with self.assertRaisesRegex(TypeError, "transport failure"):
                self.lookup()
        read.assert_called_once()

    def test_successor_returned_for_a_deleted_position_is_rejected(self):
        self.client.records = self.rows[8:]
        with self.assertRaisesRegex(ValueError, "physical record"):
            self.lookup()

    def test_more_than_one_returned_record_is_rejected_before_decode(self):
        with patch.object(self.client, "get_stream", return_value=(self.row, self.rows[8])), \
                native_decode_counts() as decodes:
            with self.assertRaisesRegex(ValueError, "one physical record"):
                self.lookup()
        self.assertEqual(decodes["decode"], 0)

    def test_custom_record_and_sdk_class_override_cannot_claim_a_physical_proof(self):
        row = SimpleNamespace(**vars(self.row))
        with patch.object(self.client, "get_stream", return_value=(row,)):
            with self.assertRaisesRegex(TypeError, "SDK RecordedEvent"):
                self.lookup()
        with patch("kurrentdbclient.RecordedEvent", object):
            with self.assertRaisesRegex(TypeError, "SDK RecordedEvent"):
                self.lookup()

    def test_modified_sdk_record_class_contract_is_rejected(self):
        with patch.object(type(self.row), "is_checkpoint", True):
            with self.assertRaisesRegex(TypeError, "SDK RecordedEvent"):
                self.lookup()

    def test_returned_physical_position_kind_and_stream_are_verified(self):
        for change in ({"stream_position": 8}, {"stream_position": True},
                       {"type": "WrongType"}, {"stream_name": "wrong-stream"}):
            with self.subTest(change=change), patch.object(self.client, "get_stream",
                    return_value=(replace(self.row, **change),)):
                with self.assertRaisesRegex(ValueError, "physical record"):
                    self.lookup()

    def test_server_uuid_is_checked_again_on_every_read(self):
        self.lookup()
        for identifier in (uuid4(),):
            with self.subTest(identifier=identifier), patch.object(self.client, "get_stream",
                    return_value=(replace(self.row, id=identifier),)):
                with self.assertRaisesRegex(ValueError, "event ID differs"):
                    self.lookup()

    def test_effectful_id_equality_and_text_envelope_cannot_claim_a_physical_record(self):
        class EqualToAnyUuid:
            def __eq__(self, other):
                return True
        for change in ({"id": EqualToAnyUuid()}, {"id": str(self.row.id)},
                       {"data": self.row.data.decode()}):
            with self.subTest(change=tuple(change)), patch.object(self.client, "get_stream",
                    return_value=(replace(self.row, **change),)):
                with self.assertRaisesRegex(ValueError, "invalid UUID or encoded bytes"):
                    self.lookup()

    def test_other_valid_same_host_envelope_cannot_replace_the_registered_target(self):
        other = replace(self.rows[8], stream_position=7)
        with patch.object(self.client, "get_stream", return_value=(other,)):
            with self.assertRaisesRegex(ValueError, "commitment differs"):
                self.lookup()

    def test_wrong_host_envelope_is_rejected_even_in_the_requested_stream(self):
        other = replace(record(event_for("host-two"), 7), stream_name=self.log.stream)
        with patch.object(self.client, "get_stream", return_value=(other,)):
            with self.assertRaisesRegex(ValueError, "host scope"):
                self.lookup()

    def test_corrupted_envelope_cannot_use_a_warm_identity_or_bytes_memo(self):
        self.lookup()
        changed = json.loads(self.row.data)
        changed["content_digest"] = "0" * 64
        replacement = replace(self.row, data=json.dumps(changed).encode())
        with patch.object(self.client, "get_stream", return_value=(replacement,)):
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                self.lookup()

    def test_full_registered_digest_is_checked_not_only_its_uuid_prefix(self):
        changed_digest = self.event.event_sha256[:32] + "0" * 32
        with self.assertRaisesRegex(ValueError, "commitment differs"):
            self.lookup(event_sha256=changed_digest)

    def test_commit_time_is_required_and_must_be_physically_aware(self):
        for recorded_at in (None, datetime(2026, 9, 30)):
            with self.subTest(recorded_at=recorded_at), patch.object(self.client, "get_stream",
                    return_value=(replace(self.row, recorded_at=recorded_at),)):
                with self.assertRaisesRegex(ValueError, "aware physical commit"):
                    self.lookup()

    def test_byte_identical_reappend_with_a_new_physical_time_is_rejected(self):
        self.lookup()
        replacement = replace(self.row, recorded_at=self.row.recorded_at + timedelta(seconds=1))
        with patch.object(self.client, "get_stream", return_value=(replacement,)):
            with self.assertRaisesRegex(ValueError, "commit time changed"):
                self.lookup()

    def test_aware_server_time_with_a_different_offset_compares_the_same_instant(self):
        same_instant = self.row.recorded_at.astimezone(timezone(timedelta(hours=-5)))
        with patch.object(self.client, "get_stream", return_value=(
                replace(self.row, recorded_at=same_instant),)):
            self.assertEqual(self.lookup().recorded_at, same_instant)

    def test_noncanonical_inputs_fail_before_a_physical_read(self):
        for change in ({"event_id": self.event.event_id.upper()},
                       {"event_sha256": self.event.event_sha256.upper()},
                       {"event_sha256": "invalid"}, {"stream_position": True},
                       {"stream_position": -1}, {"stream_position": 7.0},
                       {"expected_recorded_at": "2026-09-30T00:00:00Z"},
                       {"expected_recorded_at": "2026-09-30T00:00:00"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.lookup(**change)
        self.assertEqual(self.client.reads, [])

    def test_mismatched_preexisting_stream_owner_fails_before_transport(self):
        self.log.stream += "-wrong"
        with self.assertRaisesRegex(ValueError, "owner changed"):
            self.lookup()
        self.assertEqual(self.client.reads, [])

    def test_owner_rebinding_during_transport_fails_closed(self):
        for field, value in (("client", BoundedClient(self.rows)),
                             ("stream", self.log.stream + "-wrong"),
                             ("scope", event_for("host-two").scope)):
            original = getattr(self.log, field)
            self.client.on_read = lambda field=field, value=value: setattr(self.log, field, value)
            try:
                with self.subTest(field=field), self.assertRaises(ValueError):
                    self.lookup()
            finally:
                setattr(self.log, field, original)
                self.client.on_read = None

    def test_in_place_scope_change_during_transport_is_detected(self):
        original = self.log.scope.host_instance_id
        self.client.on_read = lambda: object.__setattr__(self.log.scope, "host_instance_id", "changed-host")
        try:
            with self.assertRaises(ValueError):
                self.lookup()
        finally:
            object.__setattr__(self.log.scope, "host_instance_id", original)

    def test_current_transport_decoder_withdrawal_is_honored_after_memo_warmup(self):
        self.lookup()
        original = selected.decode_event
        def deny(*arguments):
            raise PermissionError("decoder withdrawn by transport")
        self.client.on_read = lambda: setattr(selected, "decode_event", deny)
        try:
            with self.assertRaisesRegex(PermissionError, "decoder withdrawn"):
                self.lookup()
        finally:
            selected.decode_event = original
            self.client.on_read = None

    def test_changed_current_contract_cannot_use_a_warm_codec_shortcut(self):
        self.lookup()
        with patch.object(ExperienceEvent, "validate", side_effect=PermissionError("current contract withdrawn")):
            with self.assertRaisesRegex(PermissionError, "contract withdrawn"):
                self.lookup()

    def test_custom_codec_helper_is_not_invoked_to_qualify_a_warm_hit(self):
        self.lookup()
        with patch.object(selected, "_restore_envelope", side_effect=AssertionError("custom restore")), \
                native_decode_counts() as decodes:
            self.assertEqual(self.lookup().event, self.event)
        self.assertEqual(decodes["decode"], 1)

    def test_subclass_receiver_rejected_but_existing_replay_remains_available(self):
        class CustomLog(selected.KurrentExperienceLog):
            pass
        custom = CustomLog(scope=self.event.scope, client=self.client)
        with self.assertRaisesRegex(TypeError, "custom replay receiver"):
            custom.lookup_committed(**self.lookup_args)
        self.assertEqual(self.client.reads, [])
        self.assertEqual(custom.replay()[7], self.event)

    def test_instance_replay_overrides_are_rejected_without_bypassing_the_callback(self):
        for method in ("replay", "replay_committed"):
            with self.subTest(method=method), patch.object(self.log, method,
                    side_effect=PermissionError("custom replay boundary")) as custom:
                with self.assertRaisesRegex(TypeError, "custom replay receiver"):
                    self.lookup()
                custom.assert_not_called()
                with self.assertRaisesRegex(PermissionError, "custom replay boundary"):
                    getattr(self.log, method)()
        self.assertEqual(self.client.reads, [])

    def test_class_replay_override_rejected_before_transport(self):
        with patch.object(selected.KurrentExperienceLog, "replay_committed",
                          side_effect=PermissionError("custom class boundary")) as custom:
            with self.assertRaisesRegex(TypeError, "custom replay receiver"):
                self.lookup()
            custom.assert_not_called()
        self.assertEqual(self.client.reads, [])

    def test_original_native_methods_bound_to_another_log_do_not_qualify(self):
        other = selected.KurrentExperienceLog(scope=self.event.scope, client=BoundedClient(self.rows))
        for method in ("replay", "replay_committed"):
            with self.subTest(method=method), patch.object(self.log, method, getattr(other, method)):
                with self.assertRaisesRegex(TypeError, "custom replay receiver"):
                    self.lookup()
        self.assertEqual(self.client.reads, [])

    def test_transport_cannot_install_a_native_method_bound_to_another_log(self):
        other = selected.KurrentExperienceLog(scope=self.event.scope, client=BoundedClient(self.rows))
        self.client.on_read = lambda: setattr(self.log, "replay_committed", other.replay_committed)
        try:
            with self.assertRaisesRegex(TypeError, "custom replay receiver"):
                self.lookup()
        finally:
            del self.log.replay_committed
            self.client.on_read = None

    def test_replay_receiver_withdrawal_during_transport_is_rejected(self):
        self.client.on_read = lambda: setattr(self.log, "replay", lambda: [])
        try:
            with self.assertRaisesRegex(TypeError, "custom replay receiver"):
                self.lookup()
        finally:
            del self.log.replay
            self.client.on_read = None

    def test_decoder_cannot_install_a_replay_override_and_still_return_a_proof(self):
        original = selected.decode_event
        def change_receiver(data, scope):
            event = original(data, scope)
            self.log.replay_committed = lambda: ()
            return event
        try:
            with patch.object(selected, "decode_event", side_effect=change_receiver):
                with self.assertRaisesRegex(TypeError, "custom replay receiver"):
                    self.lookup()
        finally:
            del self.log.replay_committed

    def test_return_wrapper_cannot_rebind_the_owner_after_decoding(self):
        original = selected.CommittedExperience
        def rebind(*arguments):
            self.log.client = BoundedClient(self.rows)
            return original(*arguments)
        try:
            with patch.object(selected, "CommittedExperience", side_effect=rebind):
                with self.assertRaisesRegex(ValueError, "owner changed"):
                    self.lookup()
        finally:
            self.log.client = self.client

    def test_existing_native_replay_memo_is_shared_only_for_exact_validated_bytes(self):
        with native_decode_counts() as decodes:
            self.log.replay_committed()
            self.lookup()
        self.assertEqual(decodes["decode"], 10)
        self.assertEqual(len(self.client.reads), 2)


if __name__ == "__main__":
    unittest.main()
