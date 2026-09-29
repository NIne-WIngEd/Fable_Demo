import json
from pathlib import Path
import tempfile
import unittest

from flora.pilot_fixture import case_history_digest, load_pilot


FIXTURE = Path(__file__).resolve().parents[1] / "data/synthetic_pilot/v1.json"


class PilotFixtureTest(unittest.TestCase):
    def test_longitudinal_correction_outcome_and_irrelevant_control(self):
        pilot = load_pilot(FIXTURE)
        self.assertEqual(len(pilot["cases"]), 3)
        for case in pilot["cases"]:
            self.assertNotEqual(
                case_history_digest(pilot, case["case_id"], "before"),
                case_history_digest(pilot, case["case_id"], "after"))
        broken = json.loads(FIXTURE.read_text())
        case = broken["cases"][0]
        case["before_event_ids"].append(case["intervention_event_id"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.json"
            path.write_text(json.dumps(broken))
            with self.assertRaisesRegex(ValueError, "before/after"):
                load_pilot(path)


if __name__ == "__main__":
    unittest.main()
