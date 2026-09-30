"""One fresh selected evaluation/external guard, with real owner actions.

Controlled row/log transports assert infrastructure boundaries and SQL work;
they do not qualify physical engine latency, learning or feature quality.
"""
from copy import deepcopy
from types import MethodType
import unittest
from unittest.mock import patch

from flora.selected.formation_policy import XTDBFormationPermissionPolicy
from flora.selected.formation_registry import XTDBFormationSourceRegistry
from flora.selected.history_fence import (
    supports_combined_history_metadata, verify_history_and_external_metadata,
)
from flora.selected import formation_registry as source_readers
from flora.selected import history_fence as history_readers
import test_provider_source_fence as fixtures


class CombinedHistoryGuardTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ProviderSourceFenceTest()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.h = self.f.h
        self.question = self.h.custody.metadata("run", "question:case").event_id
        self.f.grant(self.question, self.f.external)
        self.source_ids = (self.question, *self.h.before.event_ids)

    def verify(self, *, final_current=lambda: None):
        return verify_history_and_external_metadata(policy=self.h.policy, case_id="case",
            phase="before", history=self.h.before, source_ids=self.source_ids,
            purpose=self.f.external, final_current=final_current)

    def test_one_fresh_sample_keeps_actual_canonical_passes_and_terminal_fence(self):
        actual_replay, replays = self.h.f.log.replay_committed, []
        def replay():
            replays.append(True)
            return actual_replay()
        with patch.object(self.h.f.log, "replay_committed", side_effect=replay), self.f.no_original_cipher():
            for _ in range(2):
                before = len(self.h.f.connection.calls)
                self.verify()
                calls = self.h.f.connection.calls[before:]
                self.assertEqual(len(calls), 9)
                self.assertEqual(sum(sql.startswith("SELECT * FROM flora_comparison_artifacts")
                    for sql, _ in calls), 2)
                self.assertEqual(sum("AS flora_current_metadata_fence" in sql for sql, _ in calls), 1)
                self.assertIn("AS flora_current_metadata_fence", calls[-1][0])
        self.assertEqual(len(replays), 4)
        self.h.grant(self.h.before.event_ids[0], "before", "revoke")
        with self.assertRaises(PermissionError):
            self.verify()

    def test_final_external_authority_callback_cannot_withdraw_earlier_evaluation_grant(self):
        reached = []
        def withdraw():
            reached.append(True)
            self.h.grant(self.h.before.event_ids[0], "before", "revoke")
        with self.f.no_original_cipher(), self.assertRaisesRegex(PermissionError, "terminal current"):
            self.verify(final_current=withdraw)
        self.assertEqual(reached, [True])

    def test_final_callback_cannot_change_raw_metadata(self):
        key = self.h.registry._key("raw", self.h.before.sources[0].event.payload_reference)
        def change():
            self.h.f.connection.rows[("flora_formation_raw_references", key)]["record_sha256"] = "8" * 64
        with self.f.no_original_cipher(), self.assertRaisesRegex(PermissionError, "terminal current"):
            self.verify(final_current=change)

    def test_last_external_callback_cannot_change_or_remove_actual_manifest_row(self):
        key = self.h.custody._key("run", "history:case:before")
        identity = ("flora_comparison_artifacts", key)
        for kind in ("change", "remove"):
            with self.subTest(kind=kind):
                original = deepcopy(self.h.f.connection.rows[identity])
                def change():
                    if kind == "change":
                        self.h.f.connection.rows[identity]["record_sha256"] = "9" * 64
                    else:
                        del self.h.f.connection.rows[identity]
                try:
                    with self.f.no_original_cipher(), self.assertRaisesRegex(PermissionError, "terminal current"):
                        self.verify(final_current=change)
                finally:
                    self.h.f.connection.rows[identity] = original

    def test_final_callback_cannot_rebind_actual_delegates_or_connection(self):
        for kind in ("delegate", "connection"):
            with self.subTest(kind=kind):
                original = self.h.permissions.current_action
                connection = self.h.permissions.connection
                def rebind():
                    if kind == "delegate":
                        self.h.permissions.current_action = original
                    else:
                        shadow = type(connection)()
                        shadow.rows = deepcopy(connection.rows)
                        self.h.permissions.connection = shadow
                try:
                    with self.assertRaises(PermissionError):
                        self.verify(final_current=rebind)
                finally:
                    self.h.permissions.connection = connection
                    if "current_action" in vars(self.h.permissions):
                        del self.h.permissions.current_action

    def test_instance_class_and_module_decoder_overrides_keep_uncached_route(self):
        self.assertTrue(supports_combined_history_metadata(self.h.policy))
        instance = MethodType(XTDBFormationSourceRegistry.lookup, self.h.registry)
        with patch.object(self.h.registry, "lookup", instance):
            self.assertFalse(supports_combined_history_metadata(self.h.policy))
        with patch.object(XTDBFormationPermissionPolicy, "permits", side_effect=PermissionError("custom denial")):
            self.assertFalse(supports_combined_history_metadata(self.h.policy))
        with patch.object(source_readers, "_evidence_from_record", wraps=source_readers._evidence_from_record):
            self.assertFalse(supports_combined_history_metadata(self.h.policy))
        with patch.object(self.h.policy, "authorize_history_metadata", wraps=self.h.policy.authorize_history_metadata):
            self.assertFalse(supports_combined_history_metadata(self.h.policy))
        with patch.object(history_readers, "verify_current_history_metadata",
                side_effect=PermissionError("custom history denial")):
            self.assertFalse(supports_combined_history_metadata(self.h.policy))
            self.assertFalse(self.h.policy.authorize_history_metadata(case_id="case",
                phase="before", history=self.h.before))


if __name__ == "__main__":
    unittest.main()
