"""Run an exhaustive partition of actual selected-engine integration tests."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time
import unittest


SHARDS = ("core", "transport", "native-comparison", "native-pilot", "lineage", "readers", "history", "history-routes")
MODULE_SHARDS = {
    "test_selected_comparator_memory": "transport",
    "test_selected_provider_attempt_ledger": "transport",
    "test_selected_native_comparison": "native-comparison",
    "test_selected_native_pilot_backend": "native-pilot",
    "test_selected_native_lineage_backend": "lineage",
    "test_selected_native_read_sessions": "readers",
    "test_selected_native_writer_faults": "readers",
    "test_selected_experiment_coordinator": "history",
    "test_selected_experiment_preregistration": "history",
    "test_selected_phase_history_routes": "history-routes",
}


class LiveIntegrationResult(unittest.TextTestResult):
    """Retain failed-case diagnostics even if a later case hits the job cap.

    Only fixed test identities and timings are added. Native runtimes must not
    be interrupted by asynchronous stack dumping while their tests execute.
    """

    def startTest(self, test):
        self._started_at = time.monotonic()
        super().startTest(test)

    def stopTest(self, test):
        elapsed = time.monotonic() - self._started_at
        self.stream.writeln(f"[completed {test.id()} in {elapsed:.3f}s]")
        self.stream.flush()
        super().stopTest(test)

    def addError(self, test, err):
        super().addError(test, err)
        self._print_immediate(self.errors[-1])

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._print_immediate(self.failures[-1])

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            entries = self.failures if issubclass(err[0], test.failureException) else self.errors
            self._print_immediate(entries[-1])

    def _print_immediate(self, entry):
        test, formatted_error = entry
        self.stream.writeln(f"\n[immediate failure {test.id()}]")
        self.stream.writeln(formatted_error)
        self.stream.flush()


def cases(suite):
    for entry in suite:
        if isinstance(entry, unittest.TestSuite):
            yield from cases(entry)
        else:
            yield entry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", choices=SHARDS, required=True)
    parser.add_argument("--list", action="store_true", help="Discover only; do not claim backend execution")
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    discovered = list(cases(unittest.defaultTestLoader.discover(str(root / "tests" / "integration"))))
    failed_imports = [test for test in discovered if isinstance(test, unittest.loader._FailedTest)]
    if failed_imports:
        unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(failed_imports))
        return 1
    groups = {name: [] for name in SHARDS}
    identities = set()
    for test in discovered:
        identity = test.id()
        if identity in identities:
            raise RuntimeError("integration discovery produced a duplicate test identity")
        identities.add(identity)
        module = identity.split(".")[0]
        group = MODULE_SHARDS.get(module, "core")
        groups[group].append(test)
    if not discovered or sum(map(len, groups.values())) != len(discovered):
        raise RuntimeError("selected-engine partition must include every discovered test exactly once")
    selected = groups[arguments.shard]
    if not selected:
        raise RuntimeError("selected-engine shard is unexpectedly empty")
    print(f"Discovered {len(discovered)} tests; {arguments.shard} includes {len(selected)}.", flush=True)
    if arguments.list:
        print("Discovery only; no physical backend result.")
        for test in selected:
            print(test.id())
        return 0
    return 0 if unittest.TextTestRunner(verbosity=2, resultclass=LiveIntegrationResult).run(
        unittest.TestSuite(selected)).wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
