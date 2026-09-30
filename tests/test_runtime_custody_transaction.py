"""XTDB transaction-mode regressions; fictional producer outputs only.

The controlled connection rejects the exact SELECT/DML mixing rejected by real
XTDB. Actual selected-backend coverage lives in test_selected_runtime_bridge.
"""
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from flora.selected.context import ContextPlan
from flora.selected.experiment_runtime import _RuntimePrivateCustody
import test_selected_experiment_runtime as support


class _XTDBTransactionMode:
    """Mode-sensitive wrapper around the existing rollback/immutable SQL fixture."""
    def __init__(self, connection):
        self.connection = connection
        self.execute_original = connection.execute
        self.transaction_original = connection.transaction
        self.mode = None
        self.in_transaction = False
        self.transactions = []
        self.after_commit = None
        self.info = SimpleNamespace(transaction_status=0)

    def execute(self, sql, parameters):
        if self.in_transaction:
            mode = "read" if sql.lstrip().upper().startswith("SELECT ") else "write"
            if self.mode is not None and self.mode != mode:
                raise RuntimeError("XTDB transaction cannot mix SELECT and DML")
            self.mode = mode
            self.transactions[-1].append(sql)
        return self.execute_original(sql, parameters)

    @contextmanager
    def transaction(self):
        if self.in_transaction or self.info.transaction_status != 0:
            raise AssertionError("runtime attempted nested or caller-owned transaction")
        self.mode, self.in_transaction, self.info.transaction_status = None, True, 2
        self.transactions.append([])
        committed = False
        try:
            with self.transaction_original():
                yield
            committed = True
        finally:
            self.in_transaction, self.info.transaction_status = False, 0
        if committed and self.after_commit is not None:
            callback, self.after_commit = self.after_commit, None
            callback()


class RuntimeCustodyTransactionTest(unittest.TestCase):
    def setUp(self):
        self.f = support.SelectedExperimentRuntimeTest(
            "test_registered_current_context_reaches_native_adapter_and_exact_decision_lineage")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def install_mode(self):
        mode = _XTDBTransactionMode(self.f.connection)
        for name, value in (("execute", mode.execute), ("transaction", mode.transaction), ("info", mode.info)):
            selected = patch.object(self.f.connection, name, value, create=True)
            selected.start()
            self.addCleanup(selected.stop)
        return mode

    def guard(self):
        # This is an actual SELECT template, as the runtime source/context
        # callback uses. It must never execute in the DML transaction.
        self.f.connection.execute(
            "SELECT * FROM flora_qualified_runtime_steps FOR VALID_TIME ALL WHERE _id = %s", ("guard",))
        if not self.f.permitted[0]:
            raise PermissionError("fictional current authority withdrawn")

    def custody_rows(self):
        return {key: deepcopy(row) for key, row in self.f.connection.rows.items()
                if key[0] in {_RuntimePrivateCustody.records, _RuntimePrivateCustody.raw_refs}}

    def test_live_select_guard_surrounds_one_atomic_dml_only_batch_and_retry(self):
        mode = self.install_mode()
        self.f.runtime.private.register(self.f.delivery, "mode-invocation", "context_delivery", revalidate=self.guard)
        self.assertEqual(len(mode.transactions), 1)
        self.assertEqual([sql.split()[0] for sql in mode.transactions[0]], ["ASSERT", "INSERT", "ASSERT", "INSERT"])
        self.assertEqual(len(self.custody_rows()), 2)
        prior = self.custody_rows()
        self.f.runtime.private.register(self.f.delivery, "mode-invocation", "context_delivery", revalidate=self.guard)
        self.assertEqual(len(mode.transactions), 1)
        self.assertEqual(self.custody_rows(), prior)

    def test_active_caller_transaction_is_never_committed_or_reused(self):
        mode = self.install_mode()
        mode.info.transaction_status = 2
        with self.assertRaisesRegex(ValueError, "idle top-level"):
            self.f.runtime.private.register(self.f.delivery, "caller-transaction", "context_delivery", revalidate=self.guard)
        self.assertEqual(mode.transactions, [])
        self.assertEqual(self.custody_rows(), {})
        self.assertEqual(mode.info.transaction_status, 2)

    def test_active_caller_idempotent_retry_refuses_before_guard_or_private_reads(self):
        mode = self.install_mode()
        self.f.runtime.private.register(self.f.delivery, "active-retry", "context_delivery", revalidate=self.guard)
        before_rows, before_calls = self.custody_rows(), list(self.f.connection.calls)
        mode.info.transaction_status = 2
        with patch.object(self.f.runtime.private, "_fetch", side_effect=AssertionError("opened private row")), \
             patch.object(self.f.objects.backend, "get_object", side_effect=AssertionError("opened ciphertext")), \
             patch.object(self, "guard", side_effect=AssertionError("reused caller authority snapshot")) as guarded:
            with self.assertRaisesRegex(ValueError, "idle top-level"):
                self.f.runtime.private.register(self.f.delivery, "active-retry", "context_delivery", revalidate=self.guard)
            guarded.assert_not_called()
        self.assertEqual(self.custody_rows(), before_rows)
        self.assertEqual(self.f.connection.calls, before_calls)
        self.assertEqual(len(mode.transactions), 1)
        self.assertEqual(mode.info.transaction_status, 2)

    def test_guard_leaving_implicit_transaction_blocks_write(self):
        mode = self.install_mode()
        def guard():
            self.guard()
            mode.info.transaction_status = 2
        with self.assertRaisesRegex(ValueError, "idle top-level|guard left"):
            self.f.runtime.private.register(self.f.delivery, "implicit-read", "context_delivery", revalidate=guard)
        self.assertEqual(mode.transactions, [])
        self.assertEqual(self.custody_rows(), {})

    def test_second_insert_failure_rolls_back_both_pending_rows(self):
        mode = self.install_mode()
        self.f.connection.failure_table = _RuntimePrivateCustody.records
        events = self.f.log.replay()
        with self.assertRaisesRegex(RuntimeError, "insert failure"):
            self.f.runtime.private.register(self.f.delivery, "atomic-failure", "context_delivery", revalidate=self.guard)
        self.assertEqual(self.custody_rows(), {})
        self.assertEqual(self.f.log.replay(), events)
        self.assertEqual(len(mode.transactions), 1)

    def test_postcommit_withdrawal_denies_return_but_retains_recoverable_rows(self):
        mode = self.install_mode()
        mode.after_commit = lambda: self.f.permitted.__setitem__(0, False)
        with self.assertRaisesRegex(PermissionError, "withdrawn"):
            self.f.runtime.private.register(self.f.delivery, "withdraw-on-commit", "context_delivery", revalidate=self.guard)
        self.assertEqual(len(self.custody_rows()), 2)
        prior = self.custody_rows()
        with self.assertRaises(PermissionError):
            self.f.runtime.private.register(self.f.delivery, "withdraw-on-commit", "context_delivery", revalidate=self.guard)
        self.assertEqual(self.custody_rows(), prior)
        self.assertEqual(len(mode.transactions), 1)

    def test_withdrawal_on_delivery_commit_prevents_downstream_model_invocation(self):
        self.f._admit_artifact("memory_formation")
        personality = self.f._admit_artifact("personality_judgment")
        accepted = self.f._accept(self.f._form())
        mode = self.install_mode()
        mode.after_commit = lambda: self.f.permitted.__setitem__(0, False)
        invocation_id = "postcommit-native-denial"
        with self.assertRaises(PermissionError):
            self.f.runtime.judge(plan=ContextPlan(request_id="postcommit-plan", purpose="personal_judgment",
                exact_claim_ids=(accepted.claim_id,)), task=b"fictional task", invocation_id=invocation_id)
        self.assertEqual(personality.invocations, [])
        self.assertEqual(len(mode.transactions), 1)
        self.assertTrue(any(row["record_json"].find(invocation_id) >= 0 for row in self.custody_rows().values()))
        self.assertFalse(any(event.provenance.derivation_activity_id == invocation_id
            and event.event_type in {"qualified_model_input", "qualified_model_output", "decision"}
            for event in self.f.log.replay()))


if __name__ == "__main__":
    unittest.main()
