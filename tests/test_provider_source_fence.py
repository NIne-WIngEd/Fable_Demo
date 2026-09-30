"""Actual selected grant services with controlled SQL/log ports; no models.

The terminal query runs against a row recorder here. Physical-engine coverage
is included in test_selected_provider_attempt_ledger; it remains separate.
"""
import base64
import inspect
import sys
import unittest
from unittest.mock import patch

from flora.selected.formation_policy import FormationPermissionAction, formation_permission_payload
from flora.selected.owner_authorization import OwnerActionProof, owner_action_message
from flora.selected.personal_artifact_custody import _SourceAuthorizedObjectReads
from flora.selected.provider_attempt_custody import XTDBProviderAttemptCustody, capture_purpose
import test_history_fence as fixtures


def _inside(function, line=None):
    frame = sys._getframe(1)
    while frame is not None:
        if frame.f_code is function.__code__ and (line is None or frame.f_lineno == line):
            return True
        frame = frame.f_back
    return False


class ProviderSourceFenceTest(unittest.TestCase):
    def setUp(self):
        self.h = fixtures.HistoryFenceTest()
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.f, self.registry, self.permissions = self.h.f, self.h.registry, self.h.permissions
        self.ids = self.h.before.event_ids
        self.count = 0
        self.owner = object.__new__(XTDBProviderAttemptCustody)
        self.owner.comparison, self.owner.evidence = self.h.custody, self.h.policy
        self.owner.permissions, self.owner.registry = self.permissions, self.registry
        self.owner.run_id, self.owner.scope, self.owner.log = "run", self.f.scope, self.f.log
        self.capture, self.external = capture_purpose("run"), "comparison_external:fixture"
        for purpose in (self.capture, self.external):
            for event_id in self.ids:
                self.grant(event_id, purpose)

    def grant(self, event_id, purpose, decision="allow"):
        source = self.registry.lookup(event_id)
        prior = self.permissions.current_action(event_id, purpose)
        self.count += 1
        action = FormationPermissionAction.create(scope=self.f.scope, authority_namespace_id=self.f.namespace,
            action_id=f"provider-fence-grant-{self.count}", source_ref_id=event_id,
            source_registration_sha256=source.registration_sha256, purpose=purpose, decision=decision,
            generation=1 if prior is None else prior.generation + 1,
            previous_action_sha256=None if prior is None else prior.action_sha256,
            authorization_ref="fictional-enrolled-owner", authorized_at="2026-09-29T18:00:00Z")
        parents = (event_id,) + (() if prior is None else
            (self.permissions._stored_action(prior.action_id)["request_event_id"],))
        event = self.f.event(formation_permission_payload(action), event_type="formation_permission_action",
            timestamp=action.authorized_at, parents=parents)
        self.f.proofs[event.event_id] = OwnerActionProof("formation_permission", event.event_id, event.event_sha256,
            base64.b64encode(self.f.key.sign(owner_action_message(event, "formation_permission"))).decode())
        self.permissions.apply(action, request_event_id=event.event_id, log=self.f.log,
            objects=self.f.objects, references=self.f.references, verifier=self.f.verifier)

    def no_original_cipher(self):
        actual = self.f.objects.backend.get_object
        ids = {source.event.payload_reference for source in self.h.before.sources}
        def get(namespace, object_id):
            self.assertNotIn(object_id, ids, "withdrawn original ciphertext was opened")
            return actual(namespace, object_id)
        return patch.object(self.f.objects.backend, "get_object", side_effect=get)

    def test_capture_last_permits_callback_cannot_revoke_first_before_private_read(self):
        permits, changed = self.permissions.permits, False
        def current(source, purpose):
            nonlocal changed
            result = permits(source, purpose)
            if (_inside(XTDBProviderAttemptCustody._require)
                    and source.evidence.ref_id == self.ids[-1] and purpose == self.capture and not changed):
                changed = True
                self.grant(self.ids[0], self.capture, "revoke")
            return result
        raw = self.registry.raw_reference(self.registry.lookup(self.ids[0]).object_ref)
        def guard():
            self.owner._require(self.ids, self.capture)
            return True
        guarded = _SourceAuthorizedObjectReads(self.f.objects, guard)
        with patch.object(self.permissions, "permits", side_effect=current), self.no_original_cipher():
            with self.assertRaises(PermissionError):
                guarded.get(raw)
        self.assertTrue(changed)
        self.assertEqual(self.permissions.current_action(self.ids[0], self.capture).decision, "revoke")

    def test_external_last_current_action_cannot_revoke_first_before_marker_returns(self):
        body = {"provider_configuration": {"provider_id": "fixture"}, "disclosure_source_ids": list(self.ids),
            "dispatch": {"configuration_sha256": "a" * 64, "payload_sha256": "b" * 64}}
        self.owner._external_snapshot(body)
        action, changed = self.permissions.current_action, False
        lines, start = inspect.getsourcelines(XTDBProviderAttemptCustody._external_snapshot)
        final_line = start + next(i for i, line in enumerate(lines)
            if 'action = self.permissions.current_action(saved["event_id"], purpose)' in line)
        def current(event_id, purpose):
            nonlocal changed
            result = action(event_id, purpose)
            if (_inside(XTDBProviderAttemptCustody._external_snapshot, final_line)
                    and event_id == self.ids[-1] and not changed):
                changed = True
                self.grant(self.ids[0], purpose, "revoke")
            return result
        with patch.object(self.permissions, "current_action", side_effect=current), self.no_original_cipher():
            with self.assertRaisesRegex(PermissionError, "terminal"):
                self.owner._external_snapshot(body)
        self.assertTrue(changed)
        self.assertEqual(action(self.ids[0], self.external).decision, "revoke")

    def test_parent_grant_is_sampled_even_with_original_bound_allow_predicate(self):
        # Only nominate the later original. Its actual parent is still fenced.
        later = self.h.after.sources[-1].event.event_id
        self.grant(later, self.capture)
        self.owner._require((later,), self.capture)
        permits, changed = self.permissions.permits, False
        def current(source, purpose):
            nonlocal changed
            result = permits(source, purpose)
            if (_inside(XTDBProviderAttemptCustody._require)
                    and source.evidence.ref_id == later and not changed):
                changed = True
                self.grant(self.ids[0], purpose, "revoke")
            return result
        with patch.object(self.permissions, "permits", side_effect=current), self.no_original_cipher():
            with self.assertRaisesRegex(PermissionError, "terminal"):
                self.owner._require((later,), self.capture)
        self.assertTrue(changed)

    def test_individual_task_binding_checks_end_with_complete_capture_closure(self):
        bindings = []
        for event_id in self.ids:
            source, event, raw = self.owner._source(event_id)
            bindings.append({"event_id": event_id, "registration_sha256": source.registration_sha256,
                "event_sha256": event.event_sha256, "object_id": raw.object_id,
                "content_sha256": raw.plaintext_sha256, "parent_event_ids": list(event.parent_event_ids)})
        permits, changed = self.permissions.permits, False
        def current(source, purpose):
            nonlocal changed
            result = permits(source, purpose)
            if (_inside(XTDBProviderAttemptCustody._verify_task_sources)
                    and source.evidence.ref_id == self.ids[-1] and not changed):
                changed = True
                self.grant(self.ids[0], purpose, "revoke")
            return result
        with patch.object(self.permissions, "permits", side_effect=current), self.no_original_cipher():
            with self.assertRaises(PermissionError):
                self.owner._verify_task_sources({"source_bindings": bindings}, self.capture)
        self.assertTrue(changed)


if __name__ == "__main__":
    unittest.main()
