"""Run an exhaustive partition of actual selected-engine integration tests."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import unittest


NATIVE = frozenset({
    "test_selected_native_comparison", "test_selected_native_lineage_backend",
    "test_selected_native_pilot_backend", "test_selected_native_read_sessions",
    "test_selected_native_writer_faults",
})
HISTORY = frozenset({
    "test_selected_phase_history_routes", "test_selected_experiment_coordinator",
    "test_selected_experiment_preregistration",
})


def cases(suite):
    for entry in suite:
        if isinstance(entry, unittest.TestSuite):
            yield from cases(entry)
        else:
            yield entry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", choices=("core", "native", "history"), required=True)
    parser.add_argument("--list", action="store_true", help="Discover only; do not claim backend execution")
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    discovered = list(cases(unittest.defaultTestLoader.discover(str(root / "tests" / "integration"))))
    failed_imports = [test for test in discovered if isinstance(test, unittest.loader._FailedTest)]
    if failed_imports:
        unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(failed_imports))
        return 1
    groups = {name: [] for name in ("core", "native", "history")}
    identities = set()
    for test in discovered:
        identity = test.id()
        if identity in identities:
            raise RuntimeError("integration discovery produced a duplicate test identity")
        identities.add(identity)
        module = identity.split(".")[0]
        group = "native" if module in NATIVE else "history" if module in HISTORY else "core"
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
    return 0 if unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(selected)).wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
