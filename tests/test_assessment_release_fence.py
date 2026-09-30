"""Actual selected services/owner actions on controlled SQL/log ports.

No physical-engine or signed-human-study qualification. This isolates the
post-analysis release fence; existing tests separately authenticate seals.
"""

import base64
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from flora.selected.assessment_custody import XTDBAssessmentCustody, assessment_artifact_id, assessment_purpose
from flora.selected.formation_policy import FormationPermissionAction, formation_permission_payload
from flora.selected.owner_authorization import OwnerActionProof, owner_action_message
import test_history_fence as fixture_support


class AssessmentReleaseFenceTest(unittest.TestCase):
    def setUp(self):
        self.h = fixture_support.HistoryFenceTest()
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.f, self.custody = self.h.f, self.h.custody
        self.permissions, self.registry = self.h.permissions, self.h.registry
        self.count = 0
        first, second = self.h.before.event_ids
        spec = self.custody._put(run_id="run", artifact_id="fictional-assessment-spec", kind="assessment_spec",
            content=b"fictional spec; this test is only the actual authority fence", parents=(first,),
            metadata={}, occurred_at="2026-09-30T18:00:00Z")
        rating = self.custody._put(run_id="run", artifact_id="fictional-assessment-rating", kind="assessment_rating",
            content=b"fictional rating; not a human study", parents=(spec.event_id,), metadata={},
            occurred_at="2026-09-30T18:00:01Z")
        self.seal = self.custody._put(run_id="run", artifact_id=assessment_artifact_id("collection", "seal"),
            kind="assessment_seal", content=b"fictional seal bytes; not accepted by signed-seal recovery",
            parents=(spec.event_id, rating.event_id), metadata={}, occurred_at="2026-09-30T18:00:02Z")
        pack = self.custody._put(run_id="run", artifact_id="blind_pack", kind="blind_pack",
            content=b"fictional pack", parents=(second,), metadata={}, occurred_at="2026-09-30T18:00:03Z")
        self.key = self.custody._put(run_id="run", artifact_id="blind_key", kind="blind_key",
            content=b"fictional key", parents=(pack.event_id,), metadata={}, occurred_at="2026-09-30T18:00:04Z")
        self.purposes = (assessment_purpose("run", "collection"), "comparison_review", "comparison_unblind")
        for event in tuple(self.f.log.replay()):
            if event.event_type != "formation_permission_action":
                for purpose in self.purposes:
                    self.grant(event.event_id, purpose)
        self.adapter = XTDBAssessmentCustody(comparison_custody=self.custody,
            signature_authority=SimpleNamespace())

    def grant(self, event_id, purpose, decision="allow"):
        source = self.registry.lookup(event_id)
        prior = self.permissions.current_action(event_id, purpose)
        self.count += 1
        action = FormationPermissionAction.create(scope=self.f.scope, authority_namespace_id=self.f.namespace,
            action_id=f"assessment-terminal-grant-{self.count}", source_ref_id=event_id,
            source_registration_sha256=source.registration_sha256, purpose=purpose, decision=decision,
            generation=1 if prior is None else prior.generation + 1,
            previous_action_sha256=None if prior is None else prior.action_sha256,
            authorization_ref="fictional-enrolled-owner", authorized_at="2026-09-30T19:00:00Z")
        parents = (event_id,)
        if prior is not None:
            parents += (self.permissions._stored_action(prior.action_id)["request_event_id"],)
        event = self.f.event(formation_permission_payload(action), event_type="formation_permission_action",
            timestamp=action.authorized_at, parents=parents)
        self.f.proofs[event.event_id] = OwnerActionProof("formation_permission", event.event_id, event.event_sha256,
            base64.b64encode(self.f.key.sign(owner_action_message(event, "formation_permission"))).decode())
        self.permissions.apply(action, request_event_id=event.event_id, log=self.f.log,
            objects=self.f.objects, references=self.f.references, verifier=self.f.verifier)

    def verify(self):
        self.adapter._assert_analysis_release_permissions(run_id="run", collection_id="collection",
            permissions=self.permissions)

    def test_actual_selected_closure_uses_one_terminal_statement_and_no_plaintext(self):
        before = len(self.f.connection.calls)
        with patch.object(self.f.objects, "get", side_effect=AssertionError("terminal authority opened plaintext")):
            self.verify()
        statements = self.f.connection.calls[before:]
        self.assertEqual(sum("AS flora_current_metadata_fence LIMIT" in sql for sql, _ in statements), 1)
        self.assertIn("AS flora_current_metadata_fence LIMIT", statements[-1][0])
        self.grant(self.h.before.event_ids[0], self.purposes[0], "revoke")
        with self.assertRaises(PermissionError):
            self.verify()

    def test_last_unblind_callback_withdraws_prior_root_or_deep_parent_and_is_denied(self):
        native = self.permissions.permits
        for target in (self.seal.event_id, self.h.before.event_ids[0]):
            with self.subTest(target=target):
                for restore in (self.seal.event_id, self.h.before.event_ids[0]):
                    self.grant(restore, self.purposes[0])
                fired = []
                def withdraw_after_allow(source, purpose):
                    allowed = native(source, purpose)
                    if source.evidence.ref_id == self.key.event_id and purpose == "comparison_unblind" and not fired:
                        fired.append(True)
                        self.grant(target, self.purposes[0], "revoke")
                    return allowed
                with patch.object(self.permissions, "permits", withdraw_after_allow):
                    with self.assertRaisesRegex(PermissionError, "terminal current source/grant"):
                        self.verify()
                self.assertEqual(fired, [True])
                self.assertEqual(self.permissions.current_action(target, self.purposes[0]).decision, "revoke")

    def test_actual_custom_predicate_denial_is_preserved(self):
        with patch.object(self.permissions, "permits", return_value=False) as denial:
            with self.assertRaisesRegex(PermissionError, "actual source-purpose predicate"):
                self.verify()
        self.assertGreater(denial.call_count, 0)


if __name__ == "__main__":
    unittest.main()
