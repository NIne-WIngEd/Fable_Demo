"""Keep captured construction evidence usable without inventing FBM targets."""

from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest


SEEDS = Path(__file__).resolve().parents[1] / "docs" / "fbm-seeds"
spec = importlib.util.spec_from_file_location("flora_seed_contract",
                                            SEEDS / "validate_traces.py")
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


class FBMSeedContractTest(unittest.TestCase):
    def test_repository_process_traces_have_required_authority(self):
        rows = contract.load_rows(SEEDS)
        self.assertEqual(contract.validate_rows(rows), len(rows))
        self.assertTrue(all(row["authority"].strip() for row in rows))

    def test_missing_authority_and_reused_trace_are_rejected(self):
        row = deepcopy(contract.load_rows(SEEDS)[0])
        missing = deepcopy(row)
        del missing["authority"]
        with self.assertRaisesRegex(ValueError, "authority"):
            contract.validate_rows([missing])
        with self.assertRaisesRegex(ValueError, "duplicate trace_id"):
            contract.validate_rows([row, deepcopy(row)])

    def test_ambiguous_dates_and_unrecognized_training_targets_are_rejected(self):
        row = deepcopy(contract.load_rows(SEEDS)[0])
        row["timestamp_utc"] = "2026-09-29T12:00:00"
        with self.assertRaisesRegex(ValueError, "UTC"):
            contract.validate_rows([row])
        row["timestamp_utc"] = "2026-09-29T12:00:00Z"
        row["training_value"] = ["already_trained_FBM"]
        with self.assertRaisesRegex(ValueError, "unknown training_value"):
            contract.validate_rows([row])


if __name__ == "__main__":
    unittest.main()
