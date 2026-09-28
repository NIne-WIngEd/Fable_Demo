from pathlib import Path
import tempfile
import unittest

from fable_demo.memory_lane import MemoryLane
from fable_demo.runtime import FableRuntime
from fable_demo.state import assemble_current


class CurrentStateTest(unittest.TestCase):
    def test_host_claim_and_experience_remain_distinct_from_self_and_relationship(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = FableRuntime.initialize(Path(directory) / "host")
            goal = runtime.record(kind="statement", subject="host",
                                  text="I want one free evening for deep work.")
            lane = MemoryLane(runtime)
            candidate = lane.stage_host_statement(logical_id=goal["logical_id"], key="deep_work", category="goal")
            lane.confirm(candidate["candidate_id"])
            choice = runtime.record(kind="decision", subject="host", text="I accepted another evening meeting.")
            runtime.record(kind="outcome", subject="host", text="I lost the deep work evening.",
                           relates_to=choice["logical_id"])
            runtime.record(kind="observation", subject="assistant_self", text="I noticed I had been too agreeable.")
            runtime.record(kind="observation", subject="relationship", text="We agreed to check the weekly goal.")
            packet = assemble_current(FableRuntime(runtime.vault), host_keys=("deep_work",))
            self.assertEqual(len(packet["host_confirmed_claims"]["deep_work"]), 1)
            self.assertEqual(len(packet["observed_outcomes"]), 1)
            self.assertEqual(packet["observed_outcomes"][0]["decision_id"], choice["logical_id"])
            self.assertEqual(len(packet["assistant_self_observations"]), 1)
            self.assertEqual(len(packet["relationship_observations"]), 1)
            self.assertIn("no native judgment", packet["state"])
            self.assertEqual(packet["packet_sha256"], assemble_current(runtime, host_keys=("deep_work",))["packet_sha256"])


if __name__ == "__main__":
    unittest.main()
