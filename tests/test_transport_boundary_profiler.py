"""Timing and privacy boundaries of the opt-in transport diagnostic.

Only ordinary Python functions are observed here. These checks do not replace
selected-engine fixtures or qualify their physical response deadline.
"""
import cProfile
import importlib.util
from pathlib import Path
import subprocess
import sys
import types
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/profile_selected_transport_boundaries.py"
SPEC = importlib.util.spec_from_file_location("flora_transport_boundary_diagnostic", SCRIPT)
diagnostic = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = diagnostic
SPEC.loader.exec_module(diagnostic)


class ManualClocks:
    def __init__(self):
        self.wall = self.cpu = 0

    def set(self, wall, cpu):
        self.wall, self.cpu = int(wall * 1_000_000_000), int(cpu * 1_000_000_000)

    def wall_now(self):
        return self.wall

    def cpu_now(self):
        return self.cpu


class TransportBoundaryProfilerTest(unittest.TestCase):
    def observer(self, targets, clocks, cap_seconds=180):
        return diagnostic.BoundaryObserver(targets, cap_seconds=cap_seconds,
            wall_clock=clocks.wall_now, cpu_clock=clocks.cpu_now)

    def assert_safe_retained_state(self, instance, forbidden):
        """Walk instance containers, without looking inside callable closures."""
        seen = set()
        def check(value):
            if id(value) in seen:
                return
            seen.add(id(value))
            self.assertNotIsInstance(value, (types.FrameType, types.TracebackType, BaseException))
            if isinstance(value, str):
                for secret in forbidden:
                    self.assertNotIn(secret, value)
            elif isinstance(value, dict):
                for key, item in value.items():
                    check(key)
                    check(item)
            elif isinstance(value, (list, tuple, set, frozenset)):
                for item in value:
                    check(item)
            elif not isinstance(value, (types.FunctionType, types.MethodType, types.CodeType,
                    type, types.ModuleType)) and hasattr(value, "__dict__"):
                check(vars(value))
        check(vars(instance))

    def test_nested_calls_have_exact_inclusive_exclusive_and_residual_clocks(self):
        clocks = ManualClocks()
        def inner():
            clocks.set(50, 9)
        def outer():
            clocks.set(30, 5)
            inner()
            clocks.set(80, 20)
        observer = self.observer({outer.__code__: diagnostic.Target("outer", rpc=True),
            inner.__code__: diagnostic.Target("inner")}, clocks)
        with observer:
            clocks.set(10, 1)
            outer()
            clocks.set(100, 25)
        summary = observer.summary()
        rows = {row["tag"]: row for row in summary["functions"]}
        expected = {"outer": (70, 19, 50, 15), "inner": (20, 4, 20, 4)}
        for tag, values in expected.items():
            with self.subTest(tag=tag):
                self.assertEqual(rows[tag]["calls"], 1)
                self.assertEqual(rows[tag]["completed_calls"], 1)
                for name, value in zip(("wall_seconds", "thread_cpu_seconds",
                        "exclusive_wall_seconds", "exclusive_thread_cpu_seconds"), values):
                    self.assertAlmostEqual(rows[tag][name], value)
        self.assertEqual(summary["elapsed_seconds"], 100)
        self.assertEqual(summary["thread_cpu_seconds"], 25)
        self.assertEqual(summary["residual_wall_seconds"], 30)
        self.assertEqual(summary["residual_thread_cpu_seconds"], 6)
        self.assertFalse(summary["stopped_before_rpc"])

    def test_success_and_target_error_restore_the_profile_hook_without_retaining_payloads(self):
        clocks = ManualClocks()
        payload, reply, error = "private-input-token", "private-return-token", "private-error-token"
        def success(argument):
            return reply
        def failure(argument):
            raise RuntimeError(error)
        observer = self.observer({success.__code__: diagnostic.Target("success"),
            failure.__code__: diagnostic.Target("failure")}, clocks)
        original = sys.getprofile()
        with observer:
            self.assertIsNot(sys.getprofile(), original)
            self.assertEqual(success(payload), reply)
        self.assertIs(sys.getprofile(), original)
        self.assert_safe_retained_state(observer, (payload, reply, error))
        observer = self.observer({failure.__code__: diagnostic.Target("failure")}, clocks)
        with self.assertRaisesRegex(RuntimeError, error):
            with observer:
                failure(payload)
        self.assertIs(sys.getprofile(), original)
        self.assert_safe_retained_state(observer, (payload, reply, error))
        self.assertEqual(observer.summary()["functions"][0]["completed_calls"], 1)

    def test_existing_profile_hook_is_refused_and_left_untouched(self):
        clocks = ManualClocks()
        def rpc():
            pass
        def existing(frame, event, argument):
            pass
        observer = self.observer({rpc.__code__: diagnostic.Target("rpc", rpc=True)}, clocks)
        original = sys.getprofile()
        try:
            sys.setprofile(existing)
            with self.assertRaises(RuntimeError):
                with observer:
                    self.fail("observer must refuse an existing profiler")
            self.assertIs(sys.getprofile(), existing)
        finally:
            sys.setprofile(original)

    def test_active_cprofile_hook_is_refused_and_left_untouched(self):
        clocks = ManualClocks()
        def rpc():
            pass
        def monitoring_state():
            monitoring = getattr(sys, "monitoring", None)
            return () if monitoring is None else tuple(
                (tool, monitoring.get_tool(tool), monitoring.get_events(tool))
                for tool in range(6))
        observer = self.observer({rpc.__code__: diagnostic.Target("rpc", rpc=True)}, clocks)
        original = sys.getprofile()
        profiler = cProfile.Profile()
        try:
            profiler.enable()
            rpc()
            prior_hook, prior_monitoring = sys.getprofile(), monitoring_state()
            self.assertTrue(prior_hook is not None or any(tool[1] for tool in prior_monitoring))
            with self.assertRaises(diagnostic.ProfileHookUnavailable):
                with observer:
                    self.fail("observer must refuse an active cProfile observer")
            self.assertIs(sys.getprofile(), prior_hook)
            self.assertEqual(monitoring_state(), prior_monitoring)
            rpc()
        finally:
            profiler.disable()
            if original is not None:
                sys.setprofile(original)
        self.assertEqual(sum(row.callcount for row in profiler.getstats()
            if row.code is rpc.__code__), 2)

    def test_resumable_code_objects_cannot_be_rpc_targets(self):
        clocks = ManualClocks()
        def generator():
            yield None
        async def coroutine():
            return None
        async def async_generator():
            yield None
        original = sys.getprofile()
        for function in (generator, coroutine, async_generator):
            with self.subTest(function=function.__name__):
                with self.assertRaises(ValueError):
                    self.observer({function.__code__: diagnostic.Target("rpc", rpc=True)}, clocks)
                self.assertIs(sys.getprofile(), original)

    def test_structurally_equal_code_copy_is_not_the_selected_original(self):
        clocks = ManualClocks()
        def original():
            return None
        copied_code = original.__code__.replace()
        self.assertIsNot(copied_code, original.__code__)
        self.assertEqual(copied_code, original.__code__)
        copied_function = types.FunctionType(copied_code, globals())
        observer = self.observer({original.__code__: diagnostic.Target("original", rpc=True)}, clocks)
        with observer:
            clocks.set(1, 1)
            copied_function()
            clocks.set(2, 2)
            original()
        row = observer.summary()["functions"][0]
        self.assertEqual(row["calls"], 1)
        self.assertEqual(row["completed_calls"], 1)

    def test_soft_cap_stops_before_the_next_rpc_body_and_restores_hook(self):
        clocks, bodies = ManualClocks(), []
        def rpc():
            bodies.append("ran")
        observer = self.observer({rpc.__code__: diagnostic.Target("rpc", rpc=True)}, clocks, 5)
        original = sys.getprofile()
        self.assertTrue(issubclass(diagnostic.DiagnosticSoftCap, BaseException))
        self.assertFalse(issubclass(diagnostic.DiagnosticSoftCap, Exception))
        with self.assertRaises(diagnostic.DiagnosticSoftCap):
            with observer:
                clocks.set(5, 1)
                rpc()
        self.assertEqual(bodies, [])
        self.assertIs(sys.getprofile(), original)
        summary = observer.summary()
        self.assertTrue(summary["stopped_before_rpc"])
        self.assertEqual(sum(row["calls"] for row in summary["functions"]), 0)
        self.assertEqual(sum(row["completed_calls"] for row in summary["functions"]), 0)
        self.assert_safe_retained_state(observer, ())

    def test_cap_never_interrupts_an_active_rpc_or_a_nonrpc_entry(self):
        clocks, bodies = ManualClocks(), []
        def rpc():
            clocks.set(30, 4)
            bodies.append("completed")
        def codec():
            bodies.append("codec")
        observer = self.observer({rpc.__code__: diagnostic.Target("rpc", rpc=True),
            codec.__code__: diagnostic.Target("codec")}, clocks, 5)
        with observer:
            rpc()
            codec()
            clocks.set(35, 5)
        self.assertEqual(bodies, ["completed", "codec"])
        summary = observer.summary()
        self.assertFalse(summary["stopped_before_rpc"])
        self.assertEqual(summary["overshoot_seconds"], 30)
        self.assertEqual(sum(row["completed_calls"] for row in summary["functions"]), 2)

    def test_cap_during_a_selected_caller_unwinds_without_retaining_its_frame(self):
        clocks, bodies = ManualClocks(), []
        def rpc():
            bodies.append("must not run")
        def caller(payload):
            clocks.set(6, 2)
            rpc()
        observer = self.observer({caller.__code__: diagnostic.Target("caller"),
            rpc.__code__: diagnostic.Target("rpc", rpc=True)}, clocks, 5)
        original = sys.getprofile()
        with self.assertRaises(diagnostic.DiagnosticSoftCap):
            with observer:
                clocks.set(1, 1)
                caller("private-active-frame-token")
        self.assertEqual(bodies, [])
        self.assertIs(sys.getprofile(), original)
        summary = observer.summary()
        self.assertTrue(summary["stopped_before_rpc"])
        rows = {row["tag"]: row for row in summary["functions"]}
        self.assertEqual(rows["caller"]["calls"], 1)
        self.assertEqual(rows["caller"]["completed_calls"], 0)
        self.assert_safe_retained_state(observer, ("private-active-frame-token",))

    def test_active_rpc_allows_nested_and_recursive_rpcs_before_capping_next_outer_call(self):
        clocks, bodies = ManualClocks(), []
        def inner():
            clocks.set(7, 2)
            bodies.append("inner")
        def outer(depth):
            clocks.set(6, 1)
            if depth:
                outer(depth - 1)
            else:
                inner()
            bodies.append("outer" + str(depth))
        observer = self.observer({outer.__code__: diagnostic.Target("outer", rpc=True),
            inner.__code__: diagnostic.Target("inner", rpc=True)}, clocks, 5)
        original = sys.getprofile()
        with self.assertRaises(diagnostic.DiagnosticSoftCap):
            with observer:
                clocks.set(1, .5)
                outer(1)
                self.assertEqual(bodies, ["inner", "outer0", "outer1"])
                outer(0)
        self.assertEqual(bodies, ["inner", "outer0", "outer1"])
        self.assertIs(sys.getprofile(), original)
        summary = observer.summary()
        rows = {row["tag"]: row for row in summary["functions"]}
        self.assertTrue(summary["stopped_before_rpc"])
        self.assertEqual(rows["outer"]["calls"], 2)
        self.assertEqual(rows["outer"]["completed_calls"], 2)
        self.assertEqual(rows["inner"]["calls"], 1)
        self.assertEqual(rows["inner"]["completed_calls"], 1)
        self.assert_safe_retained_state(observer, ())

    def test_result_aggregates_failures_subtests_and_skips_without_fixture_buffers(self):
        sentinel = "private-fixture-token"
        class Cases(unittest.TestCase):
            def test_pass(self):
                pass
            def test_fail(self):
                self.fail(sentinel)
            def test_error(self):
                raise RuntimeError(sentinel)
            def test_subfail(self):
                with self.subTest(payload=sentinel):
                    self.fail(sentinel)
            def test_suberror(self):
                with self.subTest(payload=sentinel):
                    raise RuntimeError(sentinel)
            def test_skip(self):
                self.skipTest(sentinel)
            @unittest.expectedFailure
            def test_expected(self):
                self.fail(sentinel)
            @unittest.expectedFailure
            def test_unexpected(self):
                pass
            def test_cap(self):
                raise diagnostic.DiagnosticSoftCap()
        for name, status in (("pass", "passed"), ("fail", "failed"), ("error", "error"),
                ("subfail", "failed"), ("suberror", "error"), ("skip", "skipped"),
                ("expected", "passed"), ("unexpected", "failed"), ("cap", "capped")):
            with self.subTest(outcome=name):
                result = diagnostic.AggregateTestResult()
                Cases("test_" + name).run(result)
                self.assertEqual(result.testsRun, 1)
                self.assertEqual(result.fixture_status(), status)
                self.assert_safe_retained_state(result, (sentinel,))
                for attribute in ("errors", "failures", "skipped", "expectedFailures",
                        "unexpectedSuccesses"):
                    self.assertEqual(getattr(result, attribute), [])

    def test_fixture_output_suppression_restores_python_streams_and_file_descriptors(self):
        code = f"""
import importlib.util, os, sys
spec = importlib.util.spec_from_file_location('diagnostic_child', {str(SCRIPT)!r})
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
for fail in (False, True):
    try:
        with module.discarded_fixture_output():
            print('private-stdout-token', flush=True)
            print('private-stderr-token', file=sys.stderr, flush=True)
            os.write(1, b'private-fd1-token')
            os.write(2, b'private-fd2-token')
            if fail:
                raise RuntimeError('private-exception-token')
    except RuntimeError:
        pass
print('visible stdout', flush=True)
print('visible stderr', file=sys.stderr, flush=True)
os.write(1, b'visible fd1\\n')
os.write(2, b'visible fd2\\n')
"""
        completed = subprocess.run([sys.executable, "-c", code], capture_output=True,
            text=True, timeout=15, cwd=SCRIPT.parent.parent)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "visible stdout\nvisible fd1\n")
        self.assertEqual(completed.stderr, "visible stderr\nvisible fd2\n")


if __name__ == "__main__":
    unittest.main()
