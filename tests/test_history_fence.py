"""Real selected custody/policy contracts with controlled SQL/log ports.

This does not qualify physical engines, model phase exclusion or performance.
"""
import base64
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import inspect
import sys
from types import MethodType
import unittest
from unittest.mock import patch

from cognitive_kernel.contracts import ProductHostScope
from flora.comparison_run import ArmBinding, HistorySnapshot, PairedRunPlan, SourceMaterial
from flora.evaluation_protocol import ARMS, EvaluationCase, EvaluationProtocol
from flora.selected.comparison_custody import ComparisonArtifact, SelectedRunEvidencePolicy, XTDBComparisonCustody, evaluation_purpose
from flora.selected.experience import CommittedExperience
from flora.selected.formation_context import register_experience_source
from flora.selected.formation_policy import FormationPermissionAction, XTDBFormationPermissionPolicy, formation_permission_payload
from flora.selected.formation_registry import XTDBFormationSourceRegistry
from flora.selected.history_fence import (
    authorize_history_metadata, verify_current_history_metadata,
    _verify_current_history_metadata,
)
from flora.selected import formation_registry as source_readers
from flora.selected.owner_authorization import OwnerActionProof, owner_action_message
import test_governed_development as helpers
from metadata_batch_fixture import install_current_metadata_batch


class HistoryFenceTest(unittest.TestCase):
    def setUp(self):
        self.f = helpers.GovernedDevelopmentContractTest()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        f = self.f
        install_current_metadata_batch(f.connection)
        f.log.replay_committed = lambda: tuple(CommittedExperience(event, i,
            datetime(2026, 9, 29, 14, tzinfo=timezone.utc)) for i, event in enumerate(f.log.events))
        def append(event, *, expected_revision):
            if expected_revision != len(f.log.events) - 1:
                raise ValueError("controlled stale canonical append")
            f.log.events.append(event)
        f.log.append = append
        self.registry = XTDBFormationSourceRegistry(scope=f.scope,
            authority_namespace_id=f.namespace, connection=f.connection)
        future = f.event(b"fictional later correction", parents=(f.source_one.event_id,))
        self.materials = tuple(SourceMaterial(event, f.objects.get(f.references[event.payload_reference]))
            for event in (f.source_one, f.source_two, future))
        for material in self.materials:
            register_experience_source(event_id=material.event.event_id, raw=f.references[material.event.payload_reference],
                registry=self.registry, log=f.log, objects=f.objects, role="historical_experience", modality="text")
        self.before = HistorySnapshot(f.scope, self.materials[:2])
        self.after = HistorySnapshot(f.scope, self.materials)
        self.custody = XTDBComparisonCustody(scope=f.scope, authority_namespace_id=f.namespace,
            connection=f.connection, registry=self.registry, objects=f.objects, log=f.log)
        case = EvaluationCase("case", f.scope.host_instance_id, "relevant_correction", "heldout",
            self.before.digest(), self.after.digest(), "a"*64, future.event_id)
        protocol = EvaluationProtocol("history-fence-fixture", "b"*64, "2026-09-29T00:00:00Z",
            "fixture-only-feature", 16, 1000, (case,), "c"*64, "d"*64, "e"*64, "f"*64, ("unused-transfer-host",))
        question = b"fictional frozen question"
        self.plan = PairedRunPlan(protocol, {arm: ArmBinding("fixture-unused", "1"*64, "2"*64,
            "fixture-unused") for arm in ARMS}, 32, 4096, 1, {"case": hashlib.sha256(question).hexdigest()})
        self.custody.register_inputs(run_id="run", plan=self.plan,
            histories={("case", "before"): self.before, ("case", "after"): self.after},
            questions={"case": question}, occurred_at="2026-09-29T15:00:00Z")
        self.permissions = XTDBFormationPermissionPolicy(scope=f.scope, authority_namespace_id=f.namespace,
            connection=f.connection, registry=self.registry)
        self.grant_count = 0
        for phase, history in (("before", self.before), ("after", self.after)):
            for event_id in history.event_ids:
                self.grant(event_id, phase)
        self.policy = SelectedRunEvidencePolicy(custody=self.custody, run_id="run", permissions=self.permissions)
        # The full existing initial path really authenticates ciphertext/plaintext.
        self.assertTrue(self.policy.authorize_history(case_id="case", phase="before", history=self.before))

    def grant(self, event_id, phase, decision="allow"):
        f = self.f
        purpose = evaluation_purpose("run", "case", phase)
        source = self.registry.lookup(event_id)
        previous = self.permissions.current_action(event_id, purpose)
        self.grant_count += 1
        action = FormationPermissionAction.create(scope=f.scope, authority_namespace_id=f.namespace,
            action_id=f"history-grant-{self.grant_count}", source_ref_id=event_id,
            source_registration_sha256=source.registration_sha256, purpose=purpose, decision=decision,
            generation=1 if previous is None else previous.generation + 1,
            previous_action_sha256=None if previous is None else previous.action_sha256,
            authorization_ref="fictional-enrolled-owner", authorized_at="2026-09-29T16:00:00Z")
        parents = (event_id,)
        if previous is not None:
            parents += (self.permissions._stored_action(previous.action_id)["request_event_id"],)
        event = f.event(formation_permission_payload(action), event_type="formation_permission_action",
            timestamp=action.authorized_at, parents=parents)
        f.proofs[event.event_id] = OwnerActionProof("formation_permission", event.event_id,
            event.event_sha256, base64.b64encode(f.key.sign(owner_action_message(event, "formation_permission"))).decode())
        self.permissions.apply(action, request_event_id=event.event_id, log=f.log, objects=f.objects,
            references=f.references, verifier=f.verifier)

    def verify(self, phase="before", history=None):
        return verify_current_history_metadata(policy=self.policy, case_id="case", phase=phase,
            history=self.before if history is None else history)

    def test_current_fence_reconstructs_manifest_and_opens_no_ciphertext_or_plaintext(self):
        with patch.object(self.custody.raw_custody, "read", side_effect=AssertionError("raw custody forbidden")), \
             patch.object(self.f.objects, "get", side_effect=AssertionError("plaintext forbidden")), \
             patch.object(self.f.objects.backend, "get_object", side_effect=AssertionError("ciphertext forbidden")):
            proof = self.verify()
            self.assertEqual(proof.history_sha256, self.before.digest())
            self.assertEqual(len(proof.sources), 2)
            self.verify("after", self.after)

    def test_native_second_pass_has_constant_sql_and_keeps_both_canonical_reads(self):
        for phase, history in (("before", self.before), ("after", self.after)):
            with self.subTest(phase=phase), \
                 patch.object(self.custody, "metadata", wraps=self.custody.metadata) as metadata, \
                 patch.object(self.f.log, "replay_committed", wraps=self.f.log.replay_committed) as replay:
                self.f.connection.calls.clear()
                self.verify(phase, history)
                self.assertEqual(len(self.f.connection.calls), 10)
                self.assertEqual(metadata.call_count, 2)
                self.assertEqual(replay.call_count, 2)
                self.assertIn("AS flora_current_metadata_fence", self.f.connection.calls[-1][0])

    def test_native_terminal_fence_denies_revoke_from_second_canonical_replay(self):
        actual, calls = self.f.log.replay_committed, 0
        def replay():
            nonlocal calls
            entries = actual()
            calls += 1
            if calls == 2:
                self.grant(self.before.event_ids[0], "before", "revoke")
            return entries
        with patch.object(self.f.log, "replay_committed", side_effect=replay):
            with self.assertRaises(PermissionError):
                self.verify()
        self.assertEqual(calls, 2)

    def test_native_terminal_fence_denies_raw_row_change_from_second_replay(self):
        actual, calls = self.f.log.replay_committed, 0
        key = self.registry._key("raw", self.before.sources[0].event.payload_reference)
        def replay():
            nonlocal calls
            entries = actual()
            calls += 1
            if calls == 2:
                self.f.connection.rows[("flora_formation_raw_references", key)]["record_sha256"] = "8" * 64
            return entries
        with patch.object(self.f.log, "replay_committed", side_effect=replay):
            with self.assertRaisesRegex(PermissionError, "terminal current"):
                self.verify()
        self.assertEqual(calls, 2)

    def test_second_canonical_callback_cannot_rebind_a_native_decoder(self):
        actual, calls = self.f.log.replay_committed, 0
        decoder = self.registry._decode
        def replay():
            nonlocal calls
            entries = actual()
            calls += 1
            if calls == 2:
                self.registry._decode = lambda *args, **kwargs: decoder(*args, **kwargs)
            return entries
        with patch.object(self.f.log, "replay_committed", side_effect=replay):
            with self.assertRaisesRegex(PermissionError, "authority crosses scope or changed"):
                self.verify()
        self.assertEqual(calls, 2)

    def test_instance_grant_callback_keeps_live_second_pass_denial(self):
        actual_replay, actual_action = self.f.log.replay_committed, self.permissions.current_action
        replays, late_actions = 0, []
        def replay():
            nonlocal replays
            replays += 1
            return actual_replay()
        def action(event_id, purpose):
            result = actual_action(event_id, purpose)
            if replays == 2:
                late_actions.append(event_id)
                return None
            return result
        with patch.object(self.f.log, "replay_committed", side_effect=replay), \
             patch.object(self.permissions, "current_action", side_effect=action):
            with self.assertRaisesRegex(PermissionError, "grant changed after current metadata"):
                self.verify()
        self.assertTrue(late_actions)

    def test_class_patched_decoder_keeps_live_second_pass_denial(self):
        actual_replay, actual_decoder = self.f.log.replay_committed, XTDBFormationSourceRegistry._decode
        replays, late_decodes = 0, []
        def replay():
            nonlocal replays
            replays += 1
            return actual_replay()
        def decode(service, *args, **kwargs):
            if replays == 2 and service is self.registry:
                late_decodes.append(True)
                raise PermissionError("custom native-class decoder denied the late read")
            return actual_decoder(service, *args, **kwargs)
        with patch.object(self.f.log, "replay_committed", side_effect=replay), \
             patch.object(XTDBFormationSourceRegistry, "_decode", new=decode):
            with self.assertRaisesRegex(PermissionError, "custom native-class decoder"):
                self.verify()
        self.assertTrue(late_decodes)

    def test_module_decoder_callback_keeps_live_second_pass_denial(self):
        actual_replay, actual_decoder = self.f.log.replay_committed, source_readers._evidence_from_record
        replays, late_decodes = 0, []
        def replay():
            nonlocal replays
            replays += 1
            return actual_replay()
        def decode(record):
            if replays == 2:
                late_decodes.append(True)
                raise PermissionError("custom source decoder denied the late read")
            return actual_decoder(record)
        with patch.object(self.f.log, "replay_committed", side_effect=replay), \
             patch.object(source_readers, "_evidence_from_record", new=decode):
            with self.assertRaisesRegex(PermissionError, "custom source decoder"):
                self.verify()
        self.assertTrue(late_decodes)

    def test_same_native_function_instance_override_still_uses_uncached_second_pass(self):
        self.registry.raw_reference = MethodType(XTDBFormationSourceRegistry.raw_reference, self.registry)
        self.f.connection.calls.clear()
        self.verify()
        self.assertGreaterEqual(len(self.f.connection.calls), 24)

    def test_late_same_function_override_still_uses_uncached_second_pass(self):
        actual, calls = self.f.log.replay_committed, 0
        def replay():
            nonlocal calls
            entries = actual()
            calls += 1
            if calls == 2:
                self.registry.raw_reference = self.registry.raw_reference
            return entries
        with patch.object(self.f.log, "replay_committed", side_effect=replay):
            self.f.connection.calls.clear()
            self.verify()
            self.assertEqual(len(self.f.connection.calls), 24)
        self.assertEqual(calls, 2)

    def test_registry_subclass_still_uses_uncached_second_pass(self):
        class CustomRegistry(XTDBFormationSourceRegistry):
            pass
        self.registry.__class__ = CustomRegistry
        self.f.connection.calls.clear()
        self.verify()
        self.assertEqual(len(self.f.connection.calls), 24)

    def test_reordered_history_is_not_the_registered_phase(self):
        history = replace(self.before, sources=tuple(reversed(self.before.sources)))
        with self.assertRaises(PermissionError):
            self.verify(history=history)

    def test_future_after_original_cannot_enter_before_history(self):
        with self.assertRaises(PermissionError):
            self.verify(history=self.after)

    def test_held_plaintext_mutation_refuses_even_with_unmodified_outer_record(self):
        history = replace(self.before, sources=(replace(self.before.sources[0], plaintext=b"unverified change"),
                                              self.before.sources[1]))
        with self.assertRaises(ValueError):
            self.verify(history=history)

    def test_mutable_outer_history_metadata_does_not_replace_manifest_content_proof(self):
        actual = self.custody.metadata("run", "history:case:before")
        forged = deepcopy(actual.record)
        # Controlled metadata port lies while retaining plausible outer fields.
        # The actual canonical manifest and reconstructed body still disagree.
        forged["content_sha256"] = "9"*64
        with patch.object(self.custody, "metadata", return_value=ComparisonArtifact(forged)):
            with self.assertRaisesRegex(PermissionError, "actual manifest content digest"):
                self.verify()

    def test_cross_scope_history_and_policy_fail_closed(self):
        other = ProductHostScope.create(product_id="friday", host_instance_id="other-fictional-host",
            schema_version="1.0.0", encryption_domain="other-fictional-key")
        history = replace(self.before, scope=other)
        with self.assertRaises(ValueError):
            self.verify(history=history)
        self.permissions.scope = other
        self.assertFalse(authorize_history_metadata(policy=self.policy, case_id="case", phase="before", history=self.before))

    def test_current_source_and_parent_revocation_is_not_cached_between_calls(self):
        self.verify("after", self.after)
        self.grant(self.materials[0].event.event_id, "after", "revoke")
        with self.assertRaises(PermissionError):
            self.verify("after", self.after)

    def test_revocation_during_last_original_grant_is_caught_by_fresh_fence(self):
        original = self.permissions.current_action
        changed = False
        def action(event_id, purpose):
            nonlocal changed
            result = original(event_id, purpose)
            if not changed and event_id == self.before.event_ids[-1]:
                changed = True
                self.grant(self.before.event_ids[0], "before", "revoke")
            return result
        with patch.object(self.permissions, "current_action", side_effect=action):
            with self.assertRaises(PermissionError):
                self.verify()
        self.assertTrue(changed)

    def test_last_final_grant_callback_cannot_withdraw_an_earlier_original(self):
        original = self.permissions.current_action
        lines, first_line = inspect.getsourcelines(_verify_current_history_metadata)
        final_line = first_line + next(index for index, line in enumerate(lines)
            if "action = permissions.current_action(snapshot.event_id, purpose)" in line)
        changed = False
        def action(event_id, purpose):
            nonlocal changed
            result = original(event_id, purpose)
            frame = sys._getframe(1)
            at_final = False
            while frame is not None:
                if frame.f_code is _verify_current_history_metadata.__code__ and frame.f_lineno == final_line:
                    at_final = True
                    break
                frame = frame.f_back
            if at_final and event_id == self.before.event_ids[-1] and not changed:
                changed = True
                self.grant(self.before.event_ids[0], "before", "revoke")
            return result
        original_read = self.f.objects.backend.get_object
        original_objects = {material.event.payload_reference for material in self.before.sources}
        def read(namespace, object_id):
            self.assertNotIn(object_id, original_objects, "metadata fence opened original ciphertext")
            return original_read(namespace, object_id)
        with patch.object(self.permissions, "current_action", side_effect=action), \
             patch.object(self.f.objects.backend, "get_object", side_effect=read):
            # The independent enrolled owner persists the actual revoke; its
            # request crypto is separate from original source decryption.
            with self.assertRaises(PermissionError):
                self.verify()
        self.assertTrue(changed)

    def test_initial_private_authentication_ends_with_complete_current_grant_fence(self):
        original = self.permissions.current_action
        lines, first_line = inspect.getsourcelines(_verify_current_history_metadata)
        final_line = first_line + next(index for index, line in enumerate(lines)
            if "action = permissions.current_action(snapshot.event_id, purpose)" in line)
        changed = False
        opened = []
        original_read = self.f.objects.backend.get_object
        original_objects = {material.event.payload_reference for material in self.before.sources}
        def read(namespace, object_id):
            if object_id in original_objects:
                opened.append(object_id)
            return original_read(namespace, object_id)
        def action(event_id, purpose):
            nonlocal changed
            result = original(event_id, purpose)
            frame = sys._getframe(1)
            at_final = False
            while frame is not None:
                if frame.f_code is _verify_current_history_metadata.__code__ and frame.f_lineno == final_line:
                    at_final = True
                    break
                frame = frame.f_back
            if at_final and event_id == self.before.event_ids[-1] and not changed:
                # The initial path must authenticate both real originals first.
                self.assertTrue(original_objects.issubset(opened))
                changed = True
                self.grant(self.before.event_ids[0], "before", "revoke")
            return result
        with patch.object(self.permissions, "current_action", side_effect=action), \
             patch.object(self.f.objects.backend, "get_object", side_effect=read):
            self.assertFalse(self.policy.authorize_history(case_id="case", phase="before", history=self.before))
        self.assertTrue(changed)
        self.assertTrue(original_objects.issubset(opened))

    def test_final_permission_marker_callback_cannot_restore_a_withdrawn_original(self):
        method = SelectedRunEvidencePolicy.current_original_permission_marker
        lines, first_line = inspect.getsourcelines(method)
        final_line = first_line + max(index for index, line in enumerate(lines)
            if "action = self.permissions.current_action(event_id, purpose)" in line)
        original, changed = self.permissions.current_action, False
        def action(event_id, purpose):
            nonlocal changed
            result = original(event_id, purpose)
            frame, at_final = sys._getframe(1), False
            while frame is not None:
                if frame.f_code is method.__code__ and frame.f_lineno == final_line:
                    at_final = True
                    break
                frame = frame.f_back
            if at_final and event_id == self.before.event_ids[-1] and not changed:
                changed = True
                self.grant(self.before.event_ids[0], "before", "revoke")
            return result
        with patch.object(self.permissions, "current_action", side_effect=action):
            self.assertIsNone(self.policy.current_original_permission_marker(
                case_id="case", phase="before", history=self.before))
        self.assertTrue(changed)

    def test_raw_reference_changes_during_grants_cannot_accept_old_held_bytes(self):
        original = self.permissions.current_action
        changed = False
        key = self.registry._key("raw", self.before.sources[0].event.payload_reference)
        def action(event_id, purpose):
            nonlocal changed
            result = original(event_id, purpose)
            if not changed and event_id == self.before.event_ids[-1]:
                changed = True
                self.f.connection.rows[("flora_formation_raw_references", key)]["record_sha256"] = "8"*64
            return result
        with patch.object(self.permissions, "current_action", side_effect=action):
            with self.assertRaises((ValueError, PermissionError)):
                self.verify()
        self.assertTrue(changed)

    def test_wrong_policy_type_is_not_a_self_certified_metadata_receipt(self):
        with self.assertRaises(TypeError):
            verify_current_history_metadata(policy=object(), case_id="case", phase="before", history=self.before)

    def test_final_raw_reference_read_withdrawal_is_followed_by_current_grant_fence(self):
        original = XTDBFormationSourceRegistry.raw_reference
        changed = False
        def reference(service, object_id):
            nonlocal changed
            result = original(service, object_id)
            if (service is self.registry and not changed
                    and object_id == self.before.sources[-1].event.payload_reference):
                changed = True
                self.grant(self.before.event_ids[0], "before", "revoke")
            return result
        with patch.object(XTDBFormationSourceRegistry, "raw_reference", new=reference):
            with self.assertRaises(PermissionError):
                self.verify()
        self.assertTrue(changed)

    def test_final_grant_callback_cannot_replace_the_actual_canonical_reader(self):
        original, changed = self.permissions.current_action, False
        lines, start = inspect.getsourcelines(_verify_current_history_metadata)
        final_line = start + next(i for i, line in enumerate(lines)
            if "action = permissions.current_action(snapshot.event_id, purpose)" in line)
        def action(event_id, purpose):
            nonlocal changed
            result = original(event_id, purpose)
            frame, at_final = sys._getframe(1), False
            while frame is not None:
                if frame.f_code is _verify_current_history_metadata.__code__ and frame.f_lineno == final_line:
                    at_final = True
                    break
                frame = frame.f_back
            if at_final and event_id == self.before.event_ids[-1] and not changed:
                changed = True
                self.f.log.replay_committed = lambda: ()
            return result
        with patch.object(self.permissions, "current_action", side_effect=action):
            with self.assertRaises(PermissionError):
                self.verify()
        self.assertTrue(changed)


if __name__ == "__main__":
    unittest.main()
