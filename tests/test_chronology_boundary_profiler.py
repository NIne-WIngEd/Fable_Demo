"""Check the separate diagnostic without executing a selected-engine fixture."""
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/profile_selected_chronology_boundaries.py"
SPEC = importlib.util.spec_from_file_location("flora_chronology_boundary_diagnostic", SCRIPT)
diagnostic = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = diagnostic
SPEC.loader.exec_module(diagnostic)


class ChronologyBoundaryProfilerTest(unittest.TestCase):
    def test_components_are_reused_and_exact_original_case_is_selected_without_running_it(self):
        for name in ("BoundaryObserver", "AggregateTestResult", "DiagnosticSoftCap",
                "ProfileHookUnavailable", "Target", "discarded_fixture_output"):
            self.assertIs(getattr(diagnostic, name), getattr(diagnostic.transport, name))
        with patch.object(sys, "path", [str(ROOT / "tests/integration"), *sys.path]):
            module, case = diagnostic.original_case()
        self.assertEqual(case.id(), diagnostic.FIXTURE_ID)
        self.assertEqual(case._testMethodName, diagnostic.FIXTURE_METHOD)
        self.assertIs(type(case), module.SelectedPreregisteredPhaseRoutesTest)
        self.assertFalse(hasattr(case, "f"))  # setUp and the body were not entered.
        targets = diagnostic.chronology_targets(module)
        method = getattr(type(case), diagnostic.FIXTURE_METHOD)
        helper = diagnostic._nested_code(method, "capture")
        self.assertEqual(targets[helper].tag, diagnostic.CAPTURE_HELPER_TAG)
        self.assertEqual(targets[method.__code__].tag, "fixture.chronological_body")
        from flora.selected.phase_snapshots import XTDBPhaseSnapshotCustody
        for name in ("capture_guard", "personal_gate"):
            code = diagnostic._nested_code(XTDBPhaseSnapshotCustody.capture, name)
            self.assertIn(code, targets)
        inherited = diagnostic.transport.selected_targets()
        for code, target in inherited.items():
            self.assertEqual(targets[code], target)
        observer = diagnostic.BoundaryObserver(targets)
        self.assertEqual(len(observer._target_codes), len(targets))

    def test_nested_target_requires_unique_original_direct_code_and_rejects_resumable_span(self):
        def parent():
            def capture():
                return None
        original = diagnostic._nested_code(parent, "capture")
        self.assertIs(original, next(value for value in parent.__code__.co_consts
            if isinstance(value, types.CodeType) and value.co_name == "capture"))
        with self.assertRaises(ValueError):
            diagnostic._nested_code(parent, "missing")
        duplicated = types.FunctionType(parent.__code__.replace(
            co_consts=parent.__code__.co_consts + (original,)), globals())
        with self.assertRaises(ValueError):
            diagnostic._nested_code(duplicated, "capture")
        def resumable_parent():
            def capture():
                yield None
        generator = diagnostic._nested_code(resumable_parent, "capture")
        with self.assertRaises(ValueError):
            diagnostic.BoundaryObserver({generator: diagnostic.Target("fixed")})

    def test_capture_entry_and_return_counts_are_not_publication_or_latency_receipts(self):
        def observed():
            return None
        observer = diagnostic.BoundaryObserver({observed.__code__:
            diagnostic.Target(diagnostic.CAPTURE_HELPER_TAG)})
        with observer:
            observed()
        receipt = diagnostic.build_receipt(status="capped", result=diagnostic.AggregateTestResult(),
            observer=observer, cap_seconds=180, before={"fixed": "a" * 64}, after={"fixed": "a" * 64})
        self.assertTrue(receipt["declared_capture_helper_entry_observed"])
        self.assertEqual(receipt["capture_publication_evidence"], "not_collected_by_aggregate_hook")
        self.assertEqual(receipt["completion"], "incomplete")
        self.assertFalse(receipt["qualification"])
        self.assertEqual(receipt["response_budget_ms"], 60000)
        self.assertEqual(receipt["soft_cap_seconds"], 180)
        self.assertIn("parent_thread_only", receipt["coverage"])
        self.assertEqual(receipt["aggregate"]["functions"][0]["completed_calls"], 1)

    def test_missing_summary_and_changed_or_newly_loaded_sources_are_explicit(self):
        receipt = diagnostic.build_receipt(status="diagnostic_error", result=diagnostic.AggregateTestResult(),
            observer=None, cap_seconds=180, before={"fixed": "a" * 64},
            after={"fixed": "b" * 64, "new_fixed": "c" * 64})
        self.assertEqual(receipt["cap_outcome"], "not_observed")
        self.assertFalse(receipt["declared_capture_helper_entry_observed"])
        self.assertFalse(receipt["source_hashes_unchanged"])
        self.assertEqual(receipt["changed_source_modules"], ["fixed"])
        self.assertEqual(receipt["newly_loaded_source_modules"], ["new_fixed"])
        empty = diagnostic.build_receipt(status="diagnostic_error", result=diagnostic.AggregateTestResult(),
            observer=None, cap_seconds=180, before={}, after={})
        self.assertIsNone(empty["source_hashes_unchanged"])

    def test_cap_validation_precedes_any_fixture_import(self):
        with patch.object(diagnostic, "original_case") as original:
            for value in ("0", "-1", "181", "nan", "inf"):
                with self.subTest(value=value), redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        diagnostic.main(["--cap-seconds", value])
            original.assert_not_called()

    def test_import_failure_and_capped_or_failed_orchestration_discard_payload_output(self):
        secret = "private-chronology-sentinel"
        for outcome in ("import_error", "capped", "failed"):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "aggregate.json"
                retained = diagnostic.AggregateTestResult()
                def setup():
                    print(secret, flush=True)
                    os.write(2, secret.encode())
                    if outcome == "import_error":
                        raise RuntimeError(secret)
                    return None, None
                def suite_run(result):
                    print(secret, flush=True)
                    os.write(1, secret.encode())
                    if outcome == "capped":
                        raise diagnostic.DiagnosticSoftCap(secret)
                    result.startTest(None)
                    result.addFailure(None, (AssertionError, AssertionError(secret), None))
                    result.stopTest(None)
                visible = io.StringIO()
                previous = sys.getprofile()
                with patch.object(diagnostic, "original_case", side_effect=setup), \
                        patch.object(diagnostic, "chronology_targets", return_value={}), \
                        patch.object(diagnostic, "source_hashes", return_value={"fixed": "a" * 64}), \
                        patch.object(diagnostic, "AggregateTestResult", return_value=retained), \
                        patch.object(diagnostic.unittest, "TestSuite") as suite, \
                        redirect_stdout(visible), redirect_stderr(visible):
                    suite.return_value.run.side_effect = suite_run
                    exit_code = diagnostic.main(["--output", str(output)])
                self.assertEqual(exit_code, 1)
                self.assertIs(sys.getprofile(), previous)
                receipt_text = output.read_text()
                self.assertNotIn(secret, receipt_text)
                self.assertNotIn(secret, visible.getvalue())
                self.assertEqual(retained.failures, [])
                self.assertEqual(retained.errors, [])
                self.assertNotIn(secret, repr(vars(retained)))
                receipt = json.loads(receipt_text)
                expected = "diagnostic_error" if outcome == "import_error" else outcome
                self.assertEqual(receipt["diagnostic_status"], expected)
                self.assertEqual(receipt["completion"], "incomplete")


if __name__ == "__main__":
    unittest.main()
