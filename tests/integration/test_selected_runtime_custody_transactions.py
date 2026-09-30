"""Actual XTDB/Kurrent registration and postcommit owner withdrawal.

No learned model, automatic proposal or producer qualification is supplied.
"""
from contextlib import contextmanager
import importlib.util
from pathlib import Path
import sys
import unittest

from flora.selected.decision_outcome import RecordedEvent
from flora.selected.experiment_runtime import _RuntimePrivateCustody


_path = Path(__file__).with_name("test_selected_runtime_bridge.py")
_spec = importlib.util.spec_from_file_location("flora_runtime_custody_backend_fixture", _path)
_support = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _support
_spec.loader.exec_module(_support)


class _AfterCommitConnection:
    def __init__(self, connection, after_commit=None):
        self.connection, self.after_commit = connection, after_commit
        self.active = False
        self.batches = []

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, sql, parameters):
        if self.active:
            self.batches[-1].append(sql)
        return self.connection.execute(sql, parameters)

    @contextmanager
    def transaction(self):
        self.active = True
        self.batches.append([])
        try:
            with self.connection.transaction():
                yield
        finally:
            self.active = False
        if self.after_commit is not None:
            callback, self.after_commit = self.after_commit, None
            callback()


class SelectedRuntimeCustodyTransactionIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.f = _support.SelectedExperimentRuntimeIntegrationTest(
            "test_actual_runtime_admission_governed_context_recovery_and_denial")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        event = self.f.fabric._source(b"fictional runtime custody transaction source")
        self.source = self.f.registry.lookup(event.event_id)
        self.f._judgment_permission(self.source)
        self.recorded = RecordedEvent(event, self.f.registry.raw_reference(event.payload_reference))

    def guard(self):
        source = self.f.registry.lookup(self.source.evidence.ref_id)
        if self.f.policy.permits(source, "personal_judgment") is not True:
            raise PermissionError("actual owner authority withdrawn after commit")

    def test_actual_xtdb_dml_batch_and_owner_withdrawal_deny_continuation(self):
        writer = _AfterCommitConnection(self.f.connection,
            lambda: self.f._judgment_permission(self.source, "revoke"))
        self.f.runtime.private.connection = writer
        with self.assertRaisesRegex(PermissionError, "owner authority withdrawn"):
            self.f.runtime.private.register(self.recorded, "real-custody-postcommit", "context_delivery",
                                            revalidate=self.guard)
        self.assertEqual(len(writer.batches), 1)
        self.assertEqual([sql.split()[0] for sql in writer.batches[0]], ["ASSERT", "INSERT", "ASSERT", "INSERT"])
        # Canonical/registered partial custody survives. It is not a success or
        # permission lease; a fresh strict continuation remains denied.
        custody = self.f.runtime.private
        self.assertIsNotNone(custody._fetch(_RuntimePrivateCustody.raw_refs,
                                          custody._key("raw", self.recorded.raw.object_id)))
        self.assertIsNotNone(custody._fetch(_RuntimePrivateCustody.records,
                                          custody._key("context_delivery", "real-custody-postcommit")))
        with self.assertRaises(PermissionError):
            custody.register(self.recorded, "real-custody-postcommit", "context_delivery", revalidate=self.guard)
        self.assertEqual(len(writer.batches), 1)


if __name__ == "__main__":
    unittest.main()
