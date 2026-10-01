"""CI discovery mechanics; these tests execute no selected backend cases."""
import importlib.util
from pathlib import Path
import re
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("flora_integration_partition",
    ROOT / "scripts" / "run_selected_integration_shard.py")
partition = importlib.util.module_from_spec(spec)
spec.loader.exec_module(partition)


def identity_case(identity):
    return SimpleNamespace(id=lambda: identity)


class SelectedIntegrationPartitionTest(unittest.TestCase):
    def configured_cases(self):
        return [identity_case(identity) for identity in partition.CASE_SHARDS]

    def test_actual_discovery_assigns_all_43_cases_once_and_six_independent_cases_alone(self):
        discovered = list(partition.cases(unittest.defaultTestLoader.discover(
            str(ROOT / "tests" / "integration"))))
        self.assertFalse([case for case in discovered if isinstance(case, unittest.loader._FailedTest)])
        groups = partition.partition_cases(discovered)
        assigned = [case.id() for group in groups.values() for case in group]
        self.assertEqual(len(discovered), 43)
        self.assertEqual(len(assigned), 43)
        self.assertEqual(len(set(assigned)), 43)
        self.assertEqual(set(assigned), {case.id() for case in discovered})
        self.assertTrue(all(groups.values()))
        self.assertEqual(len(partition.CASE_SHARDS), 6)
        for identity, group in partition.CASE_SHARDS.items():
            self.assertEqual([case.id() for case in groups[group]], [identity])

    def test_new_pilot_or_history_route_case_is_rejected_before_execution(self):
        for module in partition.CASE_SHARDED_MODULES:
            with self.subTest(module=module):
                cases = self.configured_cases() + [identity_case(module + ".NewTest.test_new_case")]
                with self.assertRaisesRegex(RuntimeError, "lacks an explicit shard"):
                    partition.partition_cases(cases)

    def test_missing_configured_case_and_duplicate_identity_are_rejected(self):
        cases = self.configured_cases()
        with self.assertRaisesRegex(RuntimeError, "was not discovered"):
            partition.partition_cases(cases[:-1])
        with self.assertRaisesRegex(RuntimeError, "duplicate test identity"):
            partition.partition_cases(cases + [cases[0]])

    def test_ordinary_new_module_keeps_core_assignment(self):
        case = identity_case("test_new_selected_backend.NewTest.test_new_case")
        groups = partition.partition_cases(self.configured_cases() + [case])
        self.assertEqual(groups["core"], [case])

    def test_workflow_matches_partition_and_preserves_caps_and_transport_observer(self):
        workflow = (ROOT / ".github" / "workflows" / "flora.yml").read_text()
        matrix = re.search(r"^\s+shard: \[([^\]]+)\]$", workflow, re.MULTILINE)
        self.assertIsNotNone(matrix)
        self.assertEqual(tuple(value.strip() for value in matrix.group(1).split(",")), partition.SHARDS)
        self.assertEqual(re.findall(r"^\s+timeout-minutes: (\d+)$", workflow, re.MULTILINE), ["60", "60"])
        self.assertIn("fail-fast: false", workflow)
        self.assertIn("failure() && matrix.shard == 'transport' && steps.selected_backend_gate.outcome == 'failure'", workflow)
        self.assertIn("python scripts/profile_selected_transport_boundaries.py --cap-seconds 180 --output selected-transport-profile.json", workflow)


if __name__ == "__main__":
    unittest.main()
