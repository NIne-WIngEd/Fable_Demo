"""Lifecycle/privacy checks for aggregate observation, not a native workload.

Ordinary controlled threads exercise hooks only. They do not replace the
original integration case, supply a model or qualify a response deadline.
"""
from contextlib import contextmanager
import cProfile
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/profile_selected_native_boundaries.py"
SPEC = importlib.util.spec_from_file_location("flora_native_boundary_diagnostic", SCRIPT)
diagnostic = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = diagnostic
SPEC.loader.exec_module(diagnostic)


class NativeBoundaryProfilerTest(unittest.TestCase):
    def test_shared_frame_targets_bind_original_code_without_wrapping(self):
        from flora.selected import (selected_authority_frame, selected_history_contribution,
            selected_phase_authority)
        def fixture(self):
            pass
        fixture_class = type('Fixture', (), {diagnostic.FIXTURE_METHOD: fixture})
        module = types.SimpleNamespace(**{diagnostic.FIXTURE_CLASS: fixture_class})
        frame = selected_authority_frame.SharedSelectedAuthorityFrame
        history = selected_history_contribution.SelectedHistoryContribution
        before = frame.binding, frame.binding.__code__, history.member, history.member.__code__
        pure_proofs = (("phase.descriptor_verify", selected_phase_authority.SelectedPhaseAuthorityDescriptor.verify),
            ("phase.origin_verify", selected_phase_authority._Origin.verify),
            ("phase.function_binding_verify", selected_phase_authority._FunctionBinding.verify),
            ("shared.frame.context_binding_verify", selected_authority_frame._verify_binding))
        proof_codes = tuple(function.__code__ for _, function in pure_proofs)
        contract_targets = (
            (selected_phase_authority, "_verify_selected_phase_tree", "phase.descriptor_tree_verify"),
            (selected_phase_authority, "_require_descriptor_contracts", "phase.descriptor_contracts"),
            (selected_phase_authority, "_verify_origin_seal", "phase.origin_seal_verify"),
            (selected_authority_frame, "_require_frame_contracts", "shared.frame.contracts"))
        contract_before = tuple((owner, name, tag, getattr(owner, name), getattr(owner, name).__code__)
            for owner, name, tag in contract_targets)
        targets, marker = diagnostic.native_targets(module)
        self.assertEqual(targets[before[1]].tag, 'shared.frame.binding')
        self.assertEqual(targets[before[3]].tag, 'shared.history.member')
        self.assertEqual(targets[frame.finish.__code__].tag, 'shared.frame.finish')
        self.assertEqual(targets[frame._base_bindings.__code__].tag, 'shared.frame.base_bindings')
        self.assertEqual(targets[marker].tag, 'native.owned_work')
        self.assertIs(frame.binding, before[0])
        self.assertIs(frame.binding.__code__, before[1])
        self.assertIs(history.member, before[2])
        self.assertIs(history.member.__code__, before[3])
        for (tag, function), code in zip(pure_proofs, proof_codes):
            self.assertIs(function.__code__, code)
            self.assertEqual(targets[code].tag, tag)
            self.assertFalse(targets[code].rpc)
        for owner, name, tag, function, code in contract_before:
            self.assertIs(getattr(owner, name), function)
            self.assertIs(function.__code__, code)
            self.assertTrue(any(targeted is code for targeted in targets))
            self.assertEqual(targets[code].tag, tag)
            self.assertFalse(targets[code].rpc)

    def test_contract_target_does_not_classify_an_equal_copied_code_object(self):
        from flora.selected import selected_phase_authority
        original = selected_phase_authority._require_descriptor_contracts
        code = original.__code__
        copied_code = code.replace()
        self.assertEqual(copied_code, code)
        self.assertIsNot(copied_code, code)
        copied = types.FunctionType(copied_code, original.__globals__, original.__name__)
        def owned():
            copied()
            original()
        observer = self.observer(owned, ("phase.descriptor_contracts", original, False),
            workers_only=True)
        self.assertNotIn(id(copied_code), observer.targets)
        with observer:
            with self.worker(owned):
                pass
        summary = observer.summary()
        row = self.rows(summary["workers"][0])["phase.descriptor_contracts"]
        self.assertEqual((row["calls"], row["return_events"]), (1, 1))
        self.assertEqual(summary["classified_owned_work_entries"], 1)
        self.assertIs(selected_phase_authority._require_descriptor_contracts, original)
        self.assertIs(original.__code__, code)

    def observer(self, marker, *fixed, **kwargs):
        targets = {marker.__code__: diagnostic.Target("owned")}
        targets.update({function.__code__: diagnostic.Target(tag, rpc)
            for tag, function, rpc in fixed})
        return diagnostic.OwnedThreadObserver(targets, owned_work_code=marker.__code__, **kwargs)

    def rows(self, ledger):
        return {row["tag"]: row for row in ledger["functions"]}

    @contextmanager
    def worker(self, function, release=None):
        failures = []
        def target():
            try:
                function()
            except BaseException as error:
                failures.append(type(error).__name__)
        thread = threading.Thread(target=target)
        thread.start()
        try:
            yield thread
        finally:
            if release is not None:
                release.set()
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive(), "controlled lifecycle thread did not retire")
            self.assertEqual(failures, [])

    def assert_safe_state(self, observer, forbidden):
        seen = set()
        def check(value):
            if id(value) in seen:
                return
            seen.add(id(value))
            self.assertNotIsInstance(value, (types.FrameType, types.TracebackType, BaseException))
            if type(value) is str:
                self.assertTrue(all(secret not in value for secret in forbidden))
            elif type(value) is dict:
                for key, item in value.items():
                    check(key)
                    check(item)
            elif type(value) in (tuple, list, set, frozenset):
                for item in value:
                    check(item)
            elif not isinstance(value, (types.FunctionType, types.MethodType, types.CodeType,
                    type, types.ModuleType)) and hasattr(value, "__dict__"):
                check(vars(value))
        check(vars(observer))

    def test_parent_and_two_worker_stacks_are_independent(self):
        ready = [threading.Event(), threading.Event()]
        release = threading.Event()
        def inner():
            return None
        def owned(index):
            ready[index].set()
            release.wait(timeout=5)
            inner()
        observer = self.observer(owned, ("inner", inner, False), cap_seconds=None)
        original_parent, original_future = sys.getprofile(), threading.getprofile()
        with observer:
            with self.worker(lambda: owned(0), release), self.worker(lambda: owned(1), release):
                self.assertTrue(all(event.wait(timeout=5) for event in ready))
                inner()
                release.set()
        summary = observer.summary()
        self.assertEqual(summary["classified_owned_work_entries"], 2)
        self.assertEqual(summary["retained_worker_ledgers"], 2)
        self.assertEqual(self.rows(summary["parent"])["inner"]["calls"], 1)
        self.assertEqual([self.rows(worker)["inner"]["calls"] for worker in summary["workers"]], [1, 1])
        self.assertEqual([self.rows(worker)["owned"]["return_events"] for worker in summary["workers"]], [1, 1])
        self.assertIs(sys.getprofile(), original_parent)
        self.assertIs(threading.getprofile(), original_future)

    def test_idle_survivor_self_removes_only_on_next_python_event(self):
        idle, release = threading.Event(), threading.Event()
        observed_after = []
        def owned():
            return None
        def target():
            owned()
            idle.set()
            release.wait(timeout=5)
            owned()  # Closed observer must not record this later call.
            observed_after.append(sys.getprofile())
        observer = self.observer(owned, cap_seconds=None)
        with self.worker_when_observed(observer, target, release):
            self.assertTrue(idle.wait(timeout=5))
        self.assertEqual(observed_after, [None])
        self.assertEqual(observer.summary()["classified_owned_work_entries"], 1)

    @contextmanager
    def worker_when_observed(self, observer, target, release):
        observer.__enter__()
        with self.worker(target, release):
            try:
                yield
            finally:
                observer.__exit__(None, None, None)
                frozen = json.dumps(observer.summary(), sort_keys=True)
                release.set()
        self.assertEqual(json.dumps(observer.summary(), sort_keys=True), frozen)

    def test_active_survivor_is_incomplete_not_cancelled_or_reclocked(self):
        ready, release = threading.Event(), threading.Event()
        completed = []
        def rpc():
            ready.set()
            release.wait(timeout=5)
            completed.append(True)
        def owned():
            rpc()
        observer = self.observer(owned, ("rpc", rpc, True), cap_seconds=None)
        with self.worker_when_observed(observer, owned, release):
            self.assertTrue(ready.wait(timeout=5))
        summary = observer.summary()
        self.assertEqual(completed, [True])
        self.assertEqual(summary["active_owned_work_at_close"], 1)
        self.assertEqual(summary["active_observed_rpcs_at_close"], 1)
        self.assertEqual(summary["open_tagged_spans_at_close"], 2)
        self.assertEqual(self.rows(summary["workers"][0])["rpc"]["return_events"], 0)

    def test_worker_installed_replacement_is_never_overwritten(self):
        ready, release = threading.Event(), threading.Event()
        profiles = []
        def replacement(frame, event, argument):
            return None
        def owned():
            sys.setprofile(replacement)
            ready.set()
            release.wait(timeout=5)
            profiles.append(sys.getprofile())
        observer = self.observer(owned, cap_seconds=None)
        with self.worker_when_observed(observer, owned, release):
            self.assertTrue(ready.wait(timeout=5))
        self.assertEqual(profiles, [replacement])

    def test_later_parent_and_future_hooks_are_preserved_on_close(self):
        def owned():
            pass
        def replacement(frame, event, argument):
            pass
        observer = self.observer(owned, cap_seconds=None)
        original_parent, original_future = sys.getprofile(), threading.getprofile()
        try:
            with observer:
                sys.setprofile(replacement)
                threading.setprofile(replacement)
            self.assertIs(sys.getprofile(), replacement)
            self.assertIs(threading.getprofile(), replacement)
            self.assertTrue(observer.summary()["parent_hook_changed"])
            self.assertTrue(observer.summary()["future_hook_changed"])
        finally:
            sys.setprofile(original_parent)
            threading.setprofile(original_future)

    def test_existing_current_or_future_hooks_are_refused_untouched(self):
        def owned():
            pass
        def existing(frame, event, argument):
            pass
        original_parent, original_future = sys.getprofile(), threading.getprofile()
        for setter, getter in ((sys.setprofile, sys.getprofile), (threading.setprofile, threading.getprofile)):
            with self.subTest(setter=setter.__name__):
                try:
                    setter(existing)
                    observer = self.observer(owned)
                    with self.assertRaises(diagnostic.ProfileHookUnavailable):
                        observer.__enter__()
                    self.assertIs(getter(), existing)
                finally:
                    sys.setprofile(original_parent)
                    threading.setprofile(original_future)

    def test_monitoring_tools_and_active_cprofile_are_refused_untouched(self):
        def owned():
            pass
        monitoring = getattr(sys, "monitoring", None)
        if monitoring is not None:
            unused = next((tool for tool in range(6) if monitoring.get_tool(tool) is None), None)
            if unused is not None:
                try:
                    monitoring.use_tool_id(unused, "native-observer-test-reserved")
                    with self.assertRaises(diagnostic.ProfileHookUnavailable):
                        self.observer(owned).__enter__()
                    self.assertEqual(monitoring.get_tool(unused), "native-observer-test-reserved")
                finally:
                    monitoring.free_tool_id(unused)
        profiler = cProfile.Profile()
        original_parent = sys.getprofile()
        try:
            profiler.enable()
            before = sys.getprofile()
            with self.assertRaises(diagnostic.ProfileHookUnavailable):
                self.observer(owned).__enter__()
            self.assertIs(sys.getprofile(), before)
            owned()
        finally:
            profiler.disable()
            if original_parent is not None:
                sys.setprofile(original_parent)
        self.assertTrue(any(row.code is owned.__code__ for row in profiler.getstats()))

    def test_failed_parent_install_restores_future_inheritance(self):
        def owned():
            pass
        original_future = threading.getprofile()
        with patch.object(sys, "setprofile", side_effect=RuntimeError("controlled install failure")):
            with self.assertRaises(RuntimeError):
                self.observer(owned).__enter__()
        self.assertIs(threading.getprofile(), original_future)

    def test_ledger_limit_accounts_overflow_and_thread_local_separation(self):
        def owned():
            pass
        observer = self.observer(owned, maximum_worker_ledgers=1, cap_seconds=None)
        with observer:
            with self.worker(owned):
                pass
            with self.worker(owned):
                pass
        summary = observer.summary()
        self.assertEqual(summary["retained_worker_ledgers"], 1)
        self.assertEqual(summary["worker_ledger_overflow"], 1)
        self.assertEqual(summary["classified_owned_work_entries"], 2)
        self.assertEqual(summary["active_owned_work_at_close"], 0)

    def test_parent_cap_waits_for_cpu_only_owned_work_to_return(self):
        ready, release = threading.Event(), threading.Event()
        calls, clock = [], [0]
        def rpc():
            calls.append(True)
        def owned():
            ready.set()
            release.wait(timeout=5)
        observer = self.observer(owned, ("rpc", rpc, True), cap_seconds=1,
            wall_clock=lambda: clock[0], cpu_clock=lambda: clock[0])
        with self.assertRaises(diagnostic.DiagnosticSoftCap):
            with observer:
                with self.worker(owned, release):
                    self.assertTrue(ready.wait(timeout=5))
                    clock[0] = 2_000_000_000
                    rpc()
                    release.set()
                rpc()
        self.assertEqual(calls, [True])
        self.assertEqual(observer.summary()["cap_deferred_parent_entries"], 1)
        self.assertTrue(observer.summary()["stopped_before_parent_rpc"])

    def test_cap_never_raises_in_worker_rpc(self):
        clock, calls = [0], []
        def rpc():
            calls.append(True)
        def owned():
            rpc()
        observer = self.observer(owned, ("rpc", rpc, True), cap_seconds=1,
            wall_clock=lambda: clock[0], cpu_clock=lambda: clock[0])
        with observer:
            clock[0] = 2_000_000_000
            with self.worker(owned):
                pass
        self.assertEqual(calls, [True])
        self.assertFalse(observer.summary()["stopped_before_parent_rpc"])

    def test_native_mode_skips_non_rpc_setup_and_activates_after_exact_marker(self):
        def non_rpc():
            return None
        def rpc():
            non_rpc()
        def owned():
            non_rpc()
        observer = self.observer(owned, ("non_rpc", non_rpc, False), ("rpc", rpc, True),
            cap_seconds=None, parent_rpc_only_before_owned=True)
        with observer:
            non_rpc()
            rpc()
            with self.worker(owned):
                pass
            non_rpc()
        summary = observer.summary()
        self.assertEqual(self.rows(summary["parent"])["non_rpc"]["calls"], 1)
        self.assertEqual(self.rows(summary["parent"])["rpc"]["calls"], 1)
        self.assertEqual(self.rows(summary["workers"][0])["non_rpc"]["calls"], 1)
        self.assertIsNotNone(summary["first_owned_entry_offset_seconds"])
        receipt = diagnostic.build_receipt(status="passed", result=diagnostic.AggregateTestResult(),
            observer=observer, cap_seconds=None, before={}, after={})
        self.assertFalse(receipt["parent_non_rpc_setup_observed"])
        self.assertIn("parent_rpc_only_before_first_owned_entry", receipt["coverage"])

    def test_native_mode_keeps_original_cap_when_setup_never_reaches_marker(self):
        calls, clock = [], [0]
        def non_rpc():
            calls.append("unobserved setup")
        def rpc():
            calls.append("RPC body")
        def owned():
            pass
        observer = self.observer(owned, ("non_rpc", non_rpc, False), ("rpc", rpc, True),
            cap_seconds=1, parent_rpc_only_before_owned=True,
            wall_clock=lambda: clock[0], cpu_clock=lambda: clock[0])
        with self.assertRaises(diagnostic.DiagnosticSoftCap):
            with observer:
                clock[0] = 2_000_000_000
                non_rpc()
                rpc()
        summary = observer.summary()
        self.assertEqual(calls, ["unobserved setup"])
        self.assertEqual(self.rows(summary["parent"])["non_rpc"]["calls"], 0)
        self.assertTrue(summary["stopped_before_parent_rpc"])
        self.assertEqual(summary["classified_owned_work_entries"], 0)
        self.assertIsNone(summary["first_owned_entry_offset_seconds"])

    def test_native_mode_keeps_pre_marker_rpc_nesting_safe_at_expired_cap(self):
        calls, clock = [], [0]
        def inner_rpc():
            calls.append(True)
        def outer_rpc():
            clock[0] = 2_000_000_000
            inner_rpc()
        def owned():
            pass
        observer = self.observer(owned, ("inner", inner_rpc, True), ("outer", outer_rpc, True),
            cap_seconds=1, parent_rpc_only_before_owned=True,
            wall_clock=lambda: clock[0], cpu_clock=lambda: clock[0])
        with self.assertRaises(diagnostic.DiagnosticSoftCap):
            with observer:
                outer_rpc()
                outer_rpc()
        self.assertEqual(calls, [True])
        self.assertEqual(observer.summary()["cap_deferred_parent_entries"], 1)
        self.assertEqual(self.rows(observer.summary()["parent"])["inner"]["calls"], 1)

    def test_native_mode_defers_for_owned_work_without_resetting_cap_at_first_marker(self):
        ready, release = threading.Event(), threading.Event()
        calls, clock = [], [0]
        def rpc():
            calls.append(True)
        def owned():
            ready.set()
            release.wait(timeout=5)
        observer = self.observer(owned, ("rpc", rpc, True), cap_seconds=1,
            parent_rpc_only_before_owned=True,
            wall_clock=lambda: clock[0], cpu_clock=lambda: clock[0])
        with self.assertRaises(diagnostic.DiagnosticSoftCap):
            with observer:
                clock[0] = 900_000_000
                with self.worker(owned, release):
                    self.assertTrue(ready.wait(timeout=5))
                    clock[0] = 1_100_000_000
                    rpc()
                    release.set()
                rpc()
        summary = observer.summary()
        self.assertEqual(calls, [True])
        self.assertEqual(summary["first_owned_entry_offset_seconds"], .9)
        self.assertEqual(summary["cap_deferred_parent_entries"], 1)
        self.assertTrue(summary["stopped_before_parent_rpc"])

    def test_numeric_windows_and_fixed_tag_totals_are_separate(self):
        ledger = diagnostic.NumericLedger(("outer", "inner"), 0, 0)
        ledger.observe("call", 0, False, 10, 1)
        ledger.observe("call", 1, True, 30, 5)
        ledger.observe("return", 1, True, 50, 9)
        ledger.observe("return", 0, False, 80, 20)
        ledger.observe("call", 0, False, 100, 25)
        ledger.observe("return", 0, False, 120, 30)
        summary = ledger.summary(("outer", "inner"))
        rows = self.rows(summary)
        self.assertAlmostEqual(summary["window_wall_seconds"], 120 / 1e9)
        self.assertAlmostEqual(rows["outer"]["wall_seconds"], 90 / 1e9)
        self.assertAlmostEqual(rows["outer"]["exclusive_thread_cpu_seconds"], 20 / 1e9)
        self.assertAlmostEqual(rows["inner"]["thread_cpu_seconds"], 4 / 1e9)

    def test_workers_only_never_installs_parent_hook_or_samples_pre_owned_cpu(self):
        parent_ident = threading.get_ident()
        original_setprofile = sys.setprofile
        cpu_samples, phases = [], []
        def cpu_clock():
            self.assertNotEqual(threading.get_ident(), parent_ident)
            cpu_samples.append(True)
            return 0
        def setprofile(hook):
            self.assertNotEqual(threading.get_ident(), parent_ident)
            original_setprofile(hook)
        def rpc():
            phases.append(len(cpu_samples))
        def owned():
            rpc()
        def impostor():
            rpc()
        impostor.__name__ = owned.__name__
        def worker():
            rpc()
            impostor()
            self.assertEqual(cpu_samples, [])
            owned()
        observer = self.observer(owned, ("rpc", rpc, True), workers_only=True,
            cpu_clock=cpu_clock)
        original_future = threading.getprofile()
        with patch.object(sys, "setprofile", side_effect=setprofile):
            with observer:
                self.assertIsNone(sys.getprofile())
                rpc()
                owned()  # A matching code in the parent is outside this scope.
                with self.worker(worker):
                    pass
            self.assertIsNone(sys.getprofile())
        summary = observer.summary()
        self.assertIsNone(summary["parent"])
        self.assertEqual(summary["classified_owned_work_entries"], 1)
        self.assertEqual(self.rows(summary["workers"][0])["rpc"]["calls"], 1)
        self.assertTrue(cpu_samples)
        self.assertFalse(summary["parent_hook_changed"])
        self.assertIs(threading.getprofile(), original_future)

    def test_workers_only_long_parent_setup_does_not_consume_worker_window(self):
        clock, completed = [0], []
        def rpc():
            completed.append(True)
        def owned():
            rpc()
            clock[0] += 900_000_000
        observer = self.observer(owned, ("rpc", rpc, True), workers_only=True,
            cap_seconds=1, wall_clock=lambda: clock[0], cpu_clock=lambda: 0)
        with observer:
            clock[0] = 200_000_000_000
            rpc()
            with self.worker(owned):
                pass
            rpc()
        summary = observer.summary()
        self.assertEqual(completed, [True, True, True])
        self.assertEqual(summary["elapsed_seconds"], 200.9)
        self.assertEqual(summary["first_owned_entry_offset_seconds"], 200)
        self.assertEqual(summary["workers"][0]["window_wall_seconds"], .9)
        self.assertFalse(summary["workers"][0]["observation_cap_reached"])
        self.assertIsNone(summary["overshoot_seconds"])
        self.assertFalse(summary["stopped_before_parent_rpc"])

    def test_workers_only_reused_worker_window_is_not_reset_and_stops_numeric_sampling(self):
        clock, cpu, cpu_samples, completed = [0], [0], [], []
        def cpu_clock():
            cpu_samples.append(clock[0])
            return cpu[0]
        def rpc():
            completed.append(True)
            clock[0] += 400_000_000
            cpu[0] += 40_000_000
        def owned():
            rpc()
        def worker():
            owned()
            clock[0] = 900_000_000
            owned()
            clock[0] = 2_000_000_000
            owned()
        observer = self.observer(owned, ("rpc", rpc, True), workers_only=True,
            cap_seconds=1, wall_clock=lambda: clock[0], cpu_clock=cpu_clock)
        with observer:
            with self.worker(worker):
                pass
        summary = observer.summary()
        ledger = summary["workers"][0]
        self.assertEqual(completed, [True, True, True])
        self.assertEqual(summary["classified_owned_work_entries"], 3)
        self.assertEqual(summary["active_owned_work_at_close"], 0)
        self.assertEqual(ledger["first_owned_entry_offset_seconds"], 0)
        self.assertEqual(ledger["cap_crossing_elapsed_seconds"], 1.3)
        self.assertEqual(ledger["window_wall_seconds"], .9)
        self.assertEqual(ledger["window_thread_cpu_seconds"], .04)
        self.assertTrue(all(value <= 900_000_000 for value in cpu_samples))
        self.assertEqual(self.rows(ledger)["owned"]["calls"], 2)
        self.assertEqual(self.rows(ledger)["owned"]["return_events"], 1)
        self.assertEqual(self.rows(ledger)["rpc"]["calls"], 2)
        self.assertEqual(self.rows(ledger)["rpc"]["return_events"], 1)

    def test_workers_only_long_rpc_remains_partial_without_deadline_cpu_fabrication(self):
        clock, cpu, cpu_samples, completed = [0], [0], [], []
        def cpu_clock():
            cpu_samples.append(clock[0])
            return cpu[0]
        def rpc():
            clock[0] = 2_000_000_000
            cpu[0] = 900_000_000
            completed.append(True)
        def owned():
            clock[0] = 100_000_000
            cpu[0] = 10_000_000
            rpc()
        observer = self.observer(owned, ("rpc", rpc, True), workers_only=True,
            cap_seconds=1, wall_clock=lambda: clock[0], cpu_clock=cpu_clock)
        with observer:
            with self.worker(owned):
                pass
        summary = observer.summary()
        ledger = summary["workers"][0]
        self.assertEqual(completed, [True])
        self.assertEqual(ledger["cap_crossing_elapsed_seconds"], 2)
        self.assertEqual(ledger["window_wall_seconds"], .1)
        self.assertEqual(ledger["window_thread_cpu_seconds"], .01)
        self.assertNotIn(2_000_000_000, cpu_samples)
        self.assertEqual(ledger["open_tagged_spans_at_cap"], 2)
        self.assertEqual(ledger["active_observed_rpcs_at_cap"], 1)
        self.assertEqual(ledger["active_owned_work_at_cap"], 1)
        self.assertEqual(summary["active_owned_work_at_close"], 0)
        self.assertEqual(summary["open_tagged_spans_at_close"], 0)
        self.assertEqual(self.rows(ledger)["owned"]["return_events"], 0)
        self.assertEqual(self.rows(ledger)["rpc"]["return_events"], 0)
        receipt = diagnostic.build_receipt(status="passed", result=diagnostic.AggregateTestResult(),
            observer=observer, cap_seconds=1, before={}, after={})
        self.assertEqual(receipt["cap_outcome"], "worker_observation_window_capped")
        self.assertFalse(receipt["qualification"])
        self.assertEqual(receipt["response_budget_ms"], 60000)

    def test_workers_only_each_new_worker_gets_its_own_first_entry_window(self):
        clock, duration, completed = [0], [2_000_000_000], []
        def rpc():
            clock[0] += duration[0]
            completed.append(True)
        def owned():
            rpc()
        observer = self.observer(owned, ("rpc", rpc, True), workers_only=True,
            cap_seconds=1, wall_clock=lambda: clock[0], cpu_clock=lambda: 0)
        with observer:
            with self.worker(owned):
                pass
            clock[0], duration[0] = 10_000_000_000, 500_000_000
            with self.worker(owned):
                pass
        workers = observer.summary()["workers"]
        self.assertEqual(completed, [True, True])
        self.assertEqual([worker["first_owned_entry_offset_seconds"] for worker in workers], [0, 10])
        self.assertEqual([worker["observation_cap_reached"] for worker in workers], [True, False])
        self.assertEqual([worker["window_wall_seconds"] for worker in workers], [0, .5])
        self.assertEqual(self.rows(workers[1])["rpc"]["return_events"], 1)

    def test_workers_only_no_owned_entry_reports_unobserved_parent_and_setup(self):
        clock, completed = [0], []
        def owned():
            pass
        def rpc():
            completed.append(True)
        def no_cpu_sample():
            self.fail("unowned setup must not sample thread CPU")
        observer = self.observer(owned, ("rpc", rpc, True), workers_only=True,
            wall_clock=lambda: clock[0], cpu_clock=no_cpu_sample)
        with observer:
            clock[0] = 1_000_000_000_000
            rpc()
            with self.worker(rpc):
                pass
        receipt = diagnostic.build_receipt(status="passed", result=diagnostic.AggregateTestResult(),
            observer=observer, cap_seconds=180, before={}, after={})
        self.assertEqual(completed, [True, True])
        self.assertEqual(receipt["cap_outcome"], "owned_work_not_observed")
        self.assertIsNone(receipt["soft_cap_seconds"])
        self.assertEqual(receipt["worker_observation_cap_seconds"], 180)
        self.assertIsNone(receipt["aggregate"]["parent"])
        self.assertIsNone(receipt["aggregate"]["overshoot_seconds"])
        self.assertEqual(receipt["aggregate"]["elapsed_seconds"], 1000)
        self.assertEqual(receipt["aggregate"]["workers"], [])
        for key in ("parent_non_rpc_setup_observed", "parent_rpc_setup_observed",
                "parent_profile_hook_installed", "parent_thread_cpu_observed", "qualification"):
            self.assertFalse(receipt[key])
        self.assertIn("workers_only", receipt["coverage"])
        self.assertIn("observation_only", receipt["cap_policy"])
        self.assertIn("all_parent_and_setup_rpc_non_rpc_cpu_timings_are_unobserved", receipt["coverage_limits"])
        failed_setup = diagnostic.build_receipt(status="setup_error", result=diagnostic.AggregateTestResult(),
            observer=None, cap_seconds=180, before={}, after={}, workers_only=True)
        self.assertEqual(failed_setup["cap_outcome"], "not_observed")
        self.assertIn("workers_only", failed_setup["coverage"])

    def test_workers_only_context_close_does_not_cancel_surviving_rpc(self):
        ready, release, completed = threading.Event(), threading.Event(), []
        def rpc():
            ready.set()
            release.wait(timeout=5)
            completed.append(True)
        def owned():
            rpc()
        observer = self.observer(owned, ("rpc", rpc, True), workers_only=True)
        with self.worker_when_observed(observer, owned, release):
            self.assertTrue(ready.wait(timeout=5))
        summary = observer.summary()
        self.assertEqual(completed, [True])
        self.assertIsNone(summary["parent"])
        self.assertEqual(summary["active_owned_work_at_close"], 1)
        self.assertEqual(summary["active_observed_rpcs_at_close"], 1)
        self.assertEqual(summary["open_tagged_spans_at_close"], 2)
        self.assertFalse(summary["workers"][0]["observation_cap_reached"])
        self.assertEqual(self.rows(summary["workers"][0])["rpc"]["return_events"], 0)

    def test_workers_only_preserves_later_parent_and_future_hooks(self):
        def owned():
            pass
        def replacement(frame, event, argument):
            pass
        observer = self.observer(owned, workers_only=True)
        original_parent, original_future = sys.getprofile(), threading.getprofile()
        try:
            with observer:
                sys.setprofile(replacement)
                threading.setprofile(replacement)
            self.assertIs(sys.getprofile(), replacement)
            self.assertIs(threading.getprofile(), replacement)
            self.assertTrue(observer.summary()["parent_hook_changed"])
            self.assertTrue(observer.summary()["future_hook_changed"])
        finally:
            sys.setprofile(original_parent)
            threading.setprofile(original_future)

    def test_workers_only_cli_is_explicit_and_does_not_change_default_scope(self):
        def owned():
            pass
        targets = {owned.__code__: diagnostic.Target("owned")}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "receipt.json"
            for scope in ([], ["--workers-only"]):
                with self.subTest(scope=scope), patch.object(diagnostic, "original_case",
                        return_value=(None, unittest.FunctionTestCase(lambda: None))), \
                        patch.object(diagnostic, "native_targets", return_value=(targets, owned.__code__)), \
                        patch.object(diagnostic, "source_hashes", return_value={}), \
                        patch.object(diagnostic, "_discard_cli_output", return_value=diagnostic.os.dup(1)), \
                        patch.object(diagnostic.os, "write"):
                    self.assertEqual(diagnostic.main(["--output", str(output), *scope]), 0)
                    receipt = json.loads(output.read_text())
                    if scope:
                        self.assertIsNone(receipt["aggregate"]["parent"])
                        self.assertEqual(receipt["cap_outcome"], "owned_work_not_observed")
                        self.assertEqual(receipt["worker_observation_cap_seconds"], 180)
                    else:
                        self.assertIsNotNone(receipt["aggregate"]["parent"])
                        self.assertEqual(receipt["soft_cap_seconds"], 180)
                        self.assertIn("parent_rpc_only_before_first_owned_entry", receipt["coverage"])

    def test_workers_only_scope_rejects_ambiguous_or_unbounded_configuration(self):
        def owned():
            pass
        for kwargs in ({"workers_only": 1}, {"workers_only": True, "cap_seconds": None},
                {"workers_only": True, "parent_rpc_only_before_owned": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.observer(owned, **kwargs)

    def test_stack_overflow_is_bounded_and_incomplete(self):
        ledger = diagnostic.NumericLedger(("recursive",), 0, 0)
        for index in range(diagnostic.MAX_STACK_DEPTH + 1):
            ledger.observe("call", 0, True, index, index)
        self.assertEqual(len(ledger.stack), diagnostic.MAX_STACK_DEPTH)
        self.assertEqual(ledger.stack_overflow, 1)
        self.assertTrue(ledger.observation_disabled)
        self.assertEqual(ledger.close_numeric_window()[0], diagnostic.MAX_STACK_DEPTH)

    def test_frames_args_returns_errors_and_thread_names_are_not_retained(self):
        payload, reply, error, name = "private-input", "private-reply", "private-error", "private-thread-name"
        def owned(argument):
            if argument:
                raise RuntimeError(error)
            return reply
        observer = self.observer(owned, cap_seconds=None)
        def work():
            self.assertEqual(owned(None), reply)
            with self.assertRaises(RuntimeError):
                owned(payload)
        with observer:
            with self.worker(work) as thread:
                thread.name = name
        self.assert_safe_state(observer, (payload, reply, error, name))
        receipt = diagnostic.build_receipt(status="passed", result=diagnostic.AggregateTestResult(),
            observer=observer, cap_seconds=None, before={}, after={})
        serialized = json.dumps(receipt)
        self.assertTrue(all(secret not in serialized for secret in (payload, reply, error, name)))
        self.assertFalse(receipt["qualification"])
        self.assertEqual(receipt["response_budget_ms"], 60000)

    def test_cli_suppression_covers_late_thread_output_through_normal_exit(self):
        script = f"""import importlib.util,sys,threading,time,os
+spec=importlib.util.spec_from_file_location('native_output_test',{str(SCRIPT)!r})
+module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
+console=module._discard_cli_output()
+def worker():
+    time.sleep(.01)
+    print('private-late-worker-output',flush=True)
+    os.write(2,b'private-late-native-output\\n')
+threading.Thread(target=worker).start()
+os.write(console,b'fixed safe status\\n');os.close(console)
+""".replace("\n+", "\n")
        completed = subprocess.run([sys.executable, "-c", script], capture_output=True, check=True)
        self.assertEqual(completed.stdout, b"fixed safe status\n")
        self.assertEqual(completed.stderr, b"")

    def test_resumable_marker_and_unbounded_configuration_are_rejected(self):
        async def coroutine():
            return None
        with self.assertRaises(ValueError):
            self.observer(coroutine)
        def owned():
            pass
        for kwargs in ({"cap_seconds": 181}, {"maximum_worker_ledgers": 33},
                {"cap_seconds": float("inf")}, {"parent_rpc_only_before_owned": 1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.observer(owned, **kwargs)


if __name__ == "__main__":
    unittest.main()
