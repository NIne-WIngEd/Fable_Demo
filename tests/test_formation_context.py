from pathlib import Path
import tempfile
import unittest

from fable_demo.formation_context import assemble_formation_context
from fable_demo.memory_lane import MemoryLane
from fable_demo.runtime import FableRuntime


class FormationContextTest(unittest.TestCase):
    def test_correction_packet_reopens_with_parent_and_confirmed_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = FableRuntime.initialize(Path(directory) / "host")
            first = runtime.record(kind="statement", subject="host", text="I like calls.",
                                   occurred_at="2025-01-01T10:00:00Z")
            candidate = MemoryLane(runtime).stage_host_statement(logical_id=first["logical_id"], key="meetings")
            MemoryLane(runtime).confirm(candidate["candidate_id"])
            correction = runtime.record(kind="correction", subject="host", text="I prefer written briefs.",
                                        relates_to=first["logical_id"], occurred_at="2025-02-01T10:00:00Z")
            packet = assemble_formation_context(FableRuntime(runtime.vault), logical_id=correction["logical_id"],
                                                host_keys=("meetings",))
            self.assertEqual(packet["observation"]["event_id"], correction["event_id"])
            self.assertEqual(packet["parent_observation"]["event_id"], first["event_id"])
            self.assertEqual(packet["selected_current_host_claims"]["meetings"][0]["text"], "I like calls.")
            self.assertEqual(len(packet["packet_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
