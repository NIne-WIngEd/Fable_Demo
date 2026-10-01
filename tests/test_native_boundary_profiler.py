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
        for kwargs in ({"cap_seconds": 181}, {"maximum_worker_ledgers": 33}, {"cap_seconds": float("inf")}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.observer(owned, **kwargs)


if __name__ == "__main__":
    unittest.main()
