import json
from pathlib import Path
import tempfile
import unittest

from fable_demo.evaluate import evaluate
from fable_demo.events import Event
from fable_demo.ledger_adapter import journal

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "correction_v1.json"


class DemoIntegrationTest(unittest.TestCase):
    def test_production_ledger_links_outcome_to_prior_decision(self):
        fixture = FIXTURE.with_name("outcome_chain_v1.json")
        data = json.loads(fixture.read_text())
        events = [Event(**item) for item in data["events"]]
        with tempfile.TemporaryDirectory() as directory:
            report = journal(events, Path(directory) / "ledger.sqlite3")
        self.assertEqual(report["entry_count"], 3)
        self.assertEqual(report["linked_outcomes"], 1)
        self.assertTrue(report["integrity_verified"])
        self.assertFalse(report["plaintext_stored"])

    def test_unlinked_outcome_is_rejected(self):
        fixture = FIXTURE.with_name("outcome_chain_v1.json")
        events = [Event(**item) for item in json.loads(fixture.read_text())["events"]]
        broken = [events[0], events[2]]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "missing ledger reference"):
                journal(broken, Path(directory) / "ledger.sqlite3")

    def test_real_memory_core_correction_and_chronology(self):
        result = evaluate(FIXTURE)
        self.assertEqual(result["ledger"]["entry_count"], 5)
        self.assertTrue(result["ledger"]["integrity_verified"])
        cases = {case["question"]: case for case in result["cases"]}
        for case in cases.values():
            self.assertTrue(case["alice_temporal"]["expected_recalled"])
            self.assertFalse(case["alice_temporal"]["forbidden_recalled"])
        self.assertFalse(cases["q_after"]["raw_history"]["expected_recalled"])
        self.assertTrue(cases["q_after"]["recent_history"]["expected_recalled"])

    def test_frozen_longitudinal_history_uses_real_memory_core(self):
        fixture = FIXTURE.with_name("longitudinal_v1.json")
        result = evaluate(fixture)
        self.assertEqual(result["case_count"], 20)
        self.assertEqual(result["ledger"]["entry_count"], 20)
        self.assertEqual(result["summary"]["alice_temporal"]["expected_recalled"], 20)
        self.assertEqual(result["summary"]["alice_temporal"]["forbidden_recalled"], 0)
        self.assertLess(result["summary"]["alice_search"]["expected_recalled"], 20)

    def test_future_answer_cannot_enter_a_past_question(self):
        data = json.loads(FIXTURE.read_text())
        data["questions"][0]["expected_ids"] = ["e3"]
        data["questions"][0]["forbidden_ids"] = []
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "future"):
                evaluate(path)


if __name__ == "__main__":
    unittest.main()
