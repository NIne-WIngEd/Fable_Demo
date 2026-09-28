import json
from pathlib import Path
import tempfile
import unittest

from fable_demo.evaluate import evaluate

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "correction_v1.json"


class DemoIntegrationTest(unittest.TestCase):
    def test_real_memory_core_correction_and_chronology(self):
        result = evaluate(FIXTURE)
        self.assertEqual(result["ledger"]["entry_count"], 5)
        self.assertTrue(result["ledger"]["integrity_verified"])
        cases = {case["question"]: case for case in result["cases"]}
        for case in cases.values():
            self.assertTrue(case["alice_memory"]["expected_recalled"])
            self.assertFalse(case["alice_memory"]["forbidden_recalled"])
        self.assertFalse(cases["q_after"]["raw_history"]["expected_recalled"])
        self.assertTrue(cases["q_after"]["recent_history"]["expected_recalled"])

    def test_future_answer_cannot_enter_a_past_question(self):
        data = json.loads(FIXTURE.read_text())
        data["questions"][0]["expected_ids"] = ["e3"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "future"):
                evaluate(path)


if __name__ == "__main__":
    unittest.main()
