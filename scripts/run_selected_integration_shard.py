"""Run an exhaustive partition of actual selected-engine integration tests."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time
import unittest


SHARDS = ("core", "transport", "native-comparison", "native-pilot-before-tail",
          "native-pilot-outcome-audit", "native-pilot-typed-phase", "native-pilot-withdrawal",
          "lineage", "readers", "history", "history-routes-retained", "history-routes-native")
MODULE_SHARDS = {
    "test_selected_comparator_memory": "transport",
    "test_selected_provider_attempt_ledger": "transport",
    "test_selected_native_comparison": "native-comparison",
    "test_selected_native_lineage_backend": "lineage",
    "test_selected_native_read_sessions": "readers",
    "test_selected_native_writer_faults": "readers",
    "test_selected_experiment_coordinator": "history",
    "test_selected_experiment_preregistration": "history",
}
CASE_SHARDED_MODULES = frozenset({"test_selected_native_pilot_backend", "test_selected_phase_history_routes"})
CASE_SHARDS = {
    "test_selected_native_pilot_backend.SelectedNativePilotBackendTest.test_actual_native_before_tail_then_correction_without_internal_history": "native-pilot-before-tail",
    "test_selected_native_pilot_backend.SelectedNativePilotBackendTest.test_actual_native_outcome_audit_unknown_tail_and_permission_withdrawal": "native-pilot-outcome-audit",
    "test_selected_native_pilot_backend.SelectedNativePilotBackendTest.test_actual_typed_phase_snapshot_and_grant_proof_join_before_tail_only": "native-pilot-typed-phase",
    "test_selected_native_pilot_backend.SelectedNativePilotBackendTest.test_phase_withdrawal_at_native_cipher_read_blocks_later_private_reads": "native-pilot-withdrawal",
    "test_selected_phase_history_routes.SelectedPhaseHistoryRoutesTest.test_actual_claim_state_and_artifact_replacement_keeps_before_route_and_live_withdrawal": "history-routes-retained",
    "test_selected_phase_history_routes.SelectedPhaseHistoryRoutesTest.test_strict_router_recovers_distinct_actual_native_arm_invocations_on_all_phase_routes": "history-routes-native",
}


def shard_for(identity):
    module = identity.split(".")[0]
    if module in CASE_SHARDED_MODULES:
        if identity not in CASE_SHARDS:
            raise RuntimeError("independent integration case lacks an explicit shard: " + identity)
        return CASE_SHARDS[identity]
    return MODULE_SHARDS.get(module, "core")


def partition_cases(discovered):
    groups = {name: [] for name in SHARDS}
    identities = set()
    for test in discovered:
        identity = test.id()
        if identity in identities:
            raise RuntimeError("integration discovery produced a duplicate test identity")
        identities.add(identity)
        groups[shard_for(identity)].append(test)
    if set(CASE_SHARDS) - identities:
        raise RuntimeError("configured independent integration case was not discovered")
    if not discovered or sum(map(len, groups.values())) != len(discovered):
        raise RuntimeError("selected-engine partition must include every discovered test exactly once")
    return groups


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
    groups = partition_cases(discovered)
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
