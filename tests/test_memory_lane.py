from pathlib import Path
import tempfile
import unittest

from fable_demo.memory_lane import MemoryLane
from fable_demo.runtime import FableRuntime


class MemoryLaneTest(unittest.TestCase):
    def test_linked_correction_requires_transition_and_preserves_history(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = FableRuntime.initialize(Path(directory) / "host")
            old = runtime.record(kind="statement", subject="host", text="I prefer video calls.",
                                 occurred_at="2025-01-01T10:00:00Z")
            lane = MemoryLane(runtime)
            first = lane.stage_host_statement(logical_id=old["logical_id"], key="meetings")
            memory_id = lane.confirm(first["candidate_id"])["memory_id"]
            new = runtime.record(kind="correction", subject="host", text="I prefer written briefs.",
                                 relates_to=old["logical_id"], occurred_at="2025-02-01T10:00:00Z")
            staged = lane.stage_host_correction(logical_id=new["logical_id"], key="meetings")
            self.assertEqual(staged["assessment"], "review_required")
            with self.assertRaisesRegex(ValueError, "requires its target memory"):
                lane.confirm(staged["candidate_id"])
            with self.assertRaisesRegex(ValueError, "only a linked host correction"):
                lane.confirm(first["candidate_id"], target_memory_id=memory_id)
            changed = lane.confirm(staged["candidate_id"], target_memory_id=memory_id)
            self.assertEqual(changed["replaced_memory_id"], memory_id)
            current = lane.current(key="meetings")
            self.assertEqual([item["text"] for item in current], ["I prefer written briefs."])
            self.assertEqual(current[0]["source_event_ids"], [new["event_id"]])
            history = lane.history(key="meetings")
            self.assertEqual([item["validity_state"] for item in history], ["historical", "current"])
            self.assertEqual([item["text"] for item in history], ["I prefer video calls.", "I prefer written briefs."])

    def test_explicit_statement_remains_candidate_until_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = FableRuntime.initialize(Path(directory) / "host")
            source = runtime.record(kind="statement", subject="host", text="I want quiet evenings for deep work.",
                                    occurred_at="2025-01-01T10:00:00Z")
            lane = MemoryLane(runtime)
            staged = lane.stage_host_statement(logical_id=source["logical_id"], key="deep_work", category="goal")
            self.assertEqual(staged["state"], "validated")
            self.assertEqual(staged["assessment"], "promotion_eligible")
            self.assertEqual(lane.current(key="deep_work"), [])
            promoted = lane.confirm(staged["candidate_id"])
            current = MemoryLane(FableRuntime(runtime.vault)).current(key="deep_work")
            self.assertEqual(current[0]["memory_id"], promoted["memory_id"])
            self.assertEqual(current[0]["source_event_ids"], [source["event_id"]])

    def test_self_statement_cannot_enter_host_authority_lane(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = FableRuntime.initialize(Path(directory) / "host")
            source = runtime.record(kind="statement", subject="assistant_self", text="I have learned to ask first.")
            with self.assertRaisesRegex(ValueError, "only explicit host statements"):
                MemoryLane(runtime).stage_host_statement(logical_id=source["logical_id"], key="interaction")


if __name__ == "__main__":
    unittest.main()
