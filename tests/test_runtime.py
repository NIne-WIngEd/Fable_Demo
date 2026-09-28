import json
from pathlib import Path
import tempfile
import unittest

from fable_demo.runtime import FableRuntime, Observation


class PersistentRuntimeTest(unittest.TestCase):
    def test_persistent_capture_and_linked_correction(self):
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory) / "host"
            runtime = FableRuntime.initialize(vault)
            original = runtime.record(kind="statement", subject="host", text="I prefer video calls.",
                                      occurred_at="2025-01-01T10:00:00Z")
            corrected = runtime.record(kind="correction", subject="host", text="I prefer written briefs now.",
                                       relates_to=original["logical_id"], occurred_at="2025-02-01T10:00:00Z")
            reopened = FableRuntime(vault)
            self.assertEqual(reopened.inspect()["ledger_events"], 2)
            self.assertEqual([item.kind for item in reopened.history()], ["statement", "correction"])
            self.assertNotIn(b"I prefer video calls", (vault / "experience-ledger.sqlite3").read_bytes())
            self.assertNotIn(b"I prefer video calls", b"".join(path.read_bytes() for path in (vault / "raw" / "objects").rglob("*.payload")))
            from cognitive_kernel.ledger_store import open_experience_ledger
            with open_experience_ledger(vault / "experience-ledger.sqlite3", scope=reopened.scope) as ledger:
                event = ledger.load_event(corrected["event_id"])
                self.assertEqual(event.parent_event_ids, (original["event_id"],))
                self.assertEqual(event.provenance.supersedes_record_ids, (original["event_id"],))

    def test_reconcile_capture_after_interrupted_ledger_append(self):
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory) / "host"
            runtime = FableRuntime.initialize(vault)
            observation = Observation("interrupted-1", "statement", "host", "A sealed observation.", "2025-01-01T10:00:00Z")
            with runtime._stores() as (raw, _ledger):
                raw.capture(runtime._seal(observation), logical_record_id=observation.logical_id,
                            media_type="application/vnd.fable.observation+json", sensitivity_class="private",
                            retention_class="ordinary_experience", captured_at=observation.occurred_at)
            reopened = FableRuntime(vault)
            self.assertEqual(reopened.inspect()["ledger_events"], 1)
            self.assertEqual(reopened.inspect()["ledger_events"], 1)
            self.assertEqual(reopened.history()[0], observation)

    def test_separate_hosts_and_duplicate_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            first = FableRuntime.initialize(Path(directory) / "first")
            second = FableRuntime.initialize(Path(directory) / "second")
            self.assertNotEqual(first.scope.host_instance_id, second.scope.host_instance_id)
            first.record(kind="statement", subject="host", text="private to first", logical_id="same-id")
            self.assertEqual(second.inspect()["ledger_events"], 0)
            with self.assertRaisesRegex(ValueError, "already exists"):
                first.record(kind="statement", subject="host", text="changed", logical_id="same-id")

    def test_invalid_links_do_not_enter_raw_buffer(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = FableRuntime.initialize(Path(directory) / "host")
            original = runtime.record(kind="statement", subject="host", text="A preference.")
            with self.assertRaisesRegex(ValueError, "outcome must refer to a decision"):
                runtime.record(kind="outcome", subject="host", text="A result.",
                               relates_to=original["logical_id"])
            with self.assertRaisesRegex(ValueError, "same subject"):
                runtime.record(kind="correction", subject="assistant_self", text="An unrelated self correction.",
                               relates_to=original["logical_id"])
            self.assertEqual(runtime.inspect()["raw_references"], 1)


if __name__ == "__main__":
    unittest.main()
