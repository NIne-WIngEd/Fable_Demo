"""Actual XTDB finite terminal metadata SQL and real owner grant races.

No MFM/personality execution, learned outcome, or consumer latency is claimed.
"""
import importlib.util
import inspect
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from flora.selected.personal_artifact_custody import _SourceAuthorizedObjectReads
from flora.selected.phase_source_fence import verify_current_phase_sources

_path = Path(__file__).parent / "test_selected_runtime_bridge.py"
_spec = importlib.util.spec_from_file_location("flora_phase_fence_backend_runtime", _path)
_fixture = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _fixture
_spec.loader.exec_module(_fixture)


class SelectedPhaseSourceFenceIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.f = _fixture.SelectedExperimentRuntimeIntegrationTest()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def test_actual_finite_source_action_head_claim_query_and_final_callback_withdrawal(self):
        f = self.f
        first = f.fabric._source(b"fictional finite metadata original")
        second = f.fabric._source(b"fictional finite metadata other original")
        for event in (first, second):
            f._judgment_permission(f.registry.lookup(event.event_id))
        bundle, store = f.fabric._bundle(first, prefix="finite-metadata")
        bound, at = f.fabric._prepare(bundle, store)
        decision = _fixture._semantic_fixture.fixture_adjudication(bound, at=at)
        f.fabric.semantic_proof.approve_fixture(decision, bound)
        admitted = f.fabric._admit(bound, decision, store)
        ids = (first.event_id, second.event_id)
        def guard():
            return verify_current_phase_sources(policy=f.runtime.context_policy,
                source_event_ids=ids, claim_ids=(admitted.claim_id,))
        original_read = f.objects.backend.get_object
        def read(namespace, object_id):
            self.assertNotIn(object_id, {first.payload_reference, second.payload_reference},
                "metadata guard opened original ciphertext")
            return original_read(namespace, object_id)
        actual_execute, guard_statements = f.connection.execute, []
        def execute(sql, parameters=()):
            guard_statements.append(sql)
            return actual_execute(sql, parameters)
        with patch.object(f.objects.backend, "get_object", side_effect=read), \
             patch.object(f.connection, "execute", side_effect=execute):
            self.assertTrue(guard())  # Executes real UNION ALL against XTDB.
        self.assertEqual(len(guard_statements), 4)  # Two batches, current Claim, final fence.
        self.assertEqual(sum("AS flora_current_metadata_sample LIMIT" in sql
            for sql in guard_statements), 2)
        self.assertEqual(sum("AS flora_current_metadata_fence LIMIT" in sql
            for sql in guard_statements), 1)
        original_action, changed = f.policy.current_action, False
        lines, first_line = inspect.getsourcelines(verify_current_phase_sources)
        final_line = first_line + next(index for index, line in enumerate(lines)
            if "action = sample.local_permissions.current_action(event_id, policy.purpose)" in line)
        def action(event_id, purpose):
            nonlocal changed
            result = original_action(event_id, purpose)
            frame, final = sys._getframe(1), False
            while frame is not None:
                if frame.f_code is verify_current_phase_sources.__code__ and frame.f_lineno == final_line:
                    final = True
                    break
                frame = frame.f_back
            if final and event_id == first.event_id and not changed:
                changed = True
                f._judgment_permission(f.registry.lookup(second.event_id), "revoke")
            return result
        raw = f.references.get(first.payload_reference)
        checked = _SourceAuthorizedObjectReads(f.objects, guard)
        with patch.object(f.policy, "current_action", side_effect=action), \
             patch.object(f.objects.backend, "get_object", side_effect=read):
            with self.assertRaises(PermissionError):
                checked.get(raw)
        self.assertTrue(changed)
        self.assertEqual(original_action(second.event_id, "personal_judgment").decision, "revoke")


if __name__ == "__main__":
    unittest.main()
