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

    def test_actual_discovery_assigns_every_case_once_and_six_independent_cases_alone(self):
        discovered = list(partition.cases(unittest.defaultTestLoader.discover(
            str(ROOT / "tests" / "integration"))))
        self.assertFalse([case for case in discovered if isinstance(case, unittest.loader._FailedTest)])
        groups = partition.partition_cases(discovered)
        assigned = [case.id() for group in groups.values() for case in group]
        self.assertEqual(len(assigned), len(discovered))
        self.assertEqual(len(set(assigned)), len(discovered))
        self.assertEqual(set(assigned), {case.id() for case in discovered})
        self.assertTrue(all(groups.values()))
        self.assertEqual(len(partition.CASE_SHARDS), 6)
        for identity, group in partition.CASE_SHARDS.items():
            self.assertEqual([case.id() for case in groups[group]], [identity])

        # These six new physical proofs must actually be discovered and run in
        # core. A fixed total made additive ordinary cases fail this inventory
        # test, although the partition correctly scheduled every one of them.
        prefix = "test_selected_exact_commitments.SelectedExactCommitmentIntegrationTest."
        required_exact_cases = {
            prefix + name for name in (
                "test_persisted_locator_resolves_exact_source_after_unrelated_tail",
                "test_missing_wrong_position_digest_and_time_fail_against_actual_records",
                "test_well_formed_false_locator_still_needs_independent_physical_proof",
                "test_soft_delete_and_reappend_reject_stale_position_and_commit_time",
                "test_selected_parent_closure_checks_actual_grants_and_later_withdrawal",
                "test_selected_closure_rejects_actual_parent_revocation_during_physical_read",
            )
        }
        self.assertTrue(required_exact_cases <= {case.id() for case in groups["core"]})
        history_prefix = "test_selected_history_consumer.SelectedHistoryConsumerIntegrationTest."
        required_history_cases = {history_prefix + name for name in (
            "test_actual_manifest_reconstruction_uses_only_bounded_metadata_reads",
            "test_actual_signed_late_revocation_is_rejected_by_shared_terminal_fence",
            "test_actual_phase_membership_uses_original_ids_and_excludes_receipts",
            "test_explicit_selected_domain_does_not_claim_unrelated_stream_integrity",
        )}
        self.assertTrue(required_history_cases <= {case.id() for case in groups["core"]})

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
