"""Actual selected history consumers over XTDB/Kurrent and held AEAD originals.

Generated fictional data and signed fictional-owner actions exercise current
custody and phase boundaries. They do not measure learned behavior or qualify
the ordinary comparator/native response budgets.
"""
import base64
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import uuid

from kurrentdbclient import NewEvent

from cognitive_kernel.contracts import ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from flora.comparison_run import SourceMaterial
from flora.selected.comparison_custody import SelectedRunEvidencePolicy, XTDBComparisonCustody, evaluation_purpose
from flora.selected.formation_context import register_experience_source
from flora.selected.formation_policy import FormationPermissionAction, formation_permission_payload
from flora.selected.owner_authorization import OwnerActionProof, owner_action_message
from flora.selected.selected_history_fence import verify_selected_history_metadata, selected_phase_member


_TESTS = Path(__file__).resolve().parents[1]
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))
from comparator_fixtures import inputs


def fixture_module():
    name = "flora_selected_history_consumer_source_fixture"
    spec = importlib.util.spec_from_file_location(name,
        Path(__file__).parent / "test_selected_exact_commitments.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Keep the upstream TestCase inside a module object. Importing its class into
# this module or inheriting from it would accidentally discover its six cases.
_source_fixture = fixture_module()


class SelectedHistoryConsumerIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.f = _source_fixture.SelectedExactCommitmentIntegrationTest()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        f = self.f
        original, raw = f._append("original history")
        f._register(original, raw)
        first = SourceMaterial(original, f.objects.get(raw))
        later, raw = f._append("later intervention", parents=(original.event_id,))
        f._register(later, raw)
        second = SourceMaterial(later, f.objects.get(raw))
        self.histories, self.question, self.plan = inputs(f.scope.host_instance_id, actual_sources=(first, second))
        self.custody = XTDBComparisonCustody(scope=f.scope, authority_namespace_id=f.namespace,
            connection=f.connection, registry=f.registry, objects=f.objects, log=f.log)
        self.custody.register_inputs(run_id="history-consumer", plan=self.plan,
            histories=self.histories, questions={"case": self.question}, occurred_at=self.now())
        self.control_events = []
        for (_, phase), history in self.histories.items():
            purpose = evaluation_purpose("history-consumer", "case", phase)
            for event_id in history.event_ids:
                self.permission(event_id, purpose)
            self.permission(self.custody.metadata("history-consumer", f"history:case:{phase}").event_id, purpose)
        self.policy = SelectedRunEvidencePolicy(custody=self.custody, run_id="history-consumer",
            permissions=f.permissions, history_metadata_domain="selected-history-metadata-v1",
            maximum_history_sources=16)
        # Authenticating actual encrypted original bytes precedes the narrowed
        # metadata route. The proof below never treats registration as consent.
        for (_, phase), history in self.histories.items():
            self.assertTrue(self.policy.authorize_history(case_id="case", phase=phase, history=history))

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat()

    def permission(self, event_id, purpose, decision="allow"):
        f = self.f
        source = f.registry.lookup(event_id)
        previous = f.permissions.current_action(event_id, purpose)
        previous_event_id = None if previous is None else f.permissions._stored_action(
            previous.action_id)["request_event_id"]
        action = FormationPermissionAction.create(scope=f.scope, authority_namespace_id=f.namespace,
            action_id="history-consumer-action-" + uuid.uuid4().hex, source_ref_id=event_id,
            source_registration_sha256=source.registration_sha256, purpose=purpose, decision=decision,
            generation=1 if previous is None else previous.generation + 1,
            previous_action_sha256=None if previous is None else previous.action_sha256,
            authorization_ref="fictional-history-owner-" + uuid.uuid4().hex, authorized_at=self.now())
        raw = f.objects.put(formation_permission_payload(action))
        parents = (event_id,) + (() if previous is None else (previous_event_id,))
        event = ExperienceEvent.create(event_type="formation_permission_action", scope=f.scope,
            occurred_at=action.authorized_at, content_digest=raw.plaintext_sha256,
            provenance=ProvenanceReference.create(provenance_type="derived_inference", source_reference_ids=parents,
                derivation_activity_id=action.action_id, responsible_component="synthetic-test"),
            retention_class="ordinary_experience", storage_tier="raw_buffer", parent_event_ids=parents,
            payload_reference=raw.object_id)
        f.log.append(event, expected_revision=f.client.get_current_version(f.log.stream))
        register_experience_source(event_id=event.event_id, raw=raw, registry=f.registry,
            log=f.log, objects=f.objects, role="derived_inference", modality="structured")
        f.proofs[event.event_id] = OwnerActionProof("formation_permission", event.event_id, event.event_sha256,
            base64.b64encode(f.signer.sign(owner_action_message(event, "formation_permission"))).decode())
        f.permissions.apply(action, request_event_id=event.event_id, log=f.log, objects=f.objects,
            references=f.registry, verifier=f.verifier)
        self.control_events.append(event)
        return event, raw

    def bounded_reads(self, *, writer_active=lambda: False):
        actual, calls = self.f.client.get_stream, []
        def read(*args, **kwargs):
            if not writer_active():
                self.assertEqual(kwargs.get("limit"), 1, "selected consumer attempted whole-stream replay")
                self.assertIs(kwargs.get("resolve_links"), False)
                self.assertIs(type(kwargs.get("stream_position")), int)
                calls.append(kwargs["stream_position"])
            return actual(*args, **kwargs)
        return read, calls

    def test_actual_manifest_reconstruction_uses_only_bounded_metadata_reads(self):
        read, calls = self.bounded_reads()
        with patch.object(self.f.client, "get_stream", side_effect=read), \
                patch.object(self.f.objects, "get", side_effect=AssertionError("metadata reopened private plaintext")), \
                patch.object(self.f.objects.backend, "get_object", side_effect=AssertionError("metadata reopened ciphertext")):
            for (_, phase), history in self.histories.items():
                proof = verify_selected_history_metadata(policy=self.policy, case_id="case", phase=phase, history=history)
                self.assertEqual(proof.domain, "selected-history-metadata-v1")
                self.assertEqual(proof.history_sha256, history.digest())
                self.assertEqual(tuple(source.event_id for source in proof.sources), history.event_ids)
                self.assertTrue(self.policy.authorize_history_metadata(case_id="case", phase=phase, history=history))
        self.assertTrue(calls)

    def test_actual_signed_late_revocation_is_rejected_by_shared_terminal_fence(self):
        history = self.histories[("case", "after")]
        purpose = evaluation_purpose("history-consumer", "case", "after")
        active, completed = [False], []
        def late():
            active[0] = True
            try:
                event, _ = self.permission(history.event_ids[0], purpose, "revoke")
                completed.append(event.event_id)
            finally:
                active[0] = False
        read, calls = self.bounded_reads(writer_active=lambda: active[0])
        with patch.object(self.f.client, "get_stream", side_effect=read), \
                self.assertRaisesRegex(PermissionError, "terminal current source/grant selected metadata changed"):
            verify_selected_history_metadata(policy=self.policy, case_id="case", phase="after",
                history=history, final_current=late)
        self.assertEqual(len(completed), 1)
        self.assertTrue(calls)
        self.assertEqual(self.f.permissions.current_action(history.event_ids[0], purpose).decision, "revoke")
        self.assertFalse(self.policy.authorize_history_metadata(case_id="case", phase="after", history=history))

    def test_actual_phase_membership_uses_original_ids_and_excludes_receipts(self):
        before, after = (self.histories[("case", phase)] for phase in ("before", "after"))
        receipt = self.custody.metadata("history-consumer", "history:case:before").event_id
        original_control = self.control_events[0].event_id
        read, calls = self.bounded_reads()
        def member(history, event_id):
            return selected_phase_member(registry=self.f.registry, log=self.f.log,
                permissions=self.f.permissions, originals={source.event.event_id: source.event for source in history.sources},
                maximum_sources=16, event_id=event_id)
        with patch.object(self.f.client, "get_stream", side_effect=read):
            self.assertFalse(member(before, after.event_ids[-1]))
            self.assertTrue(member(after, after.event_ids[-1]))
            self.assertFalse(member(before, receipt))
            self.assertFalse(member(after, receipt))
            # A permitted internal control may lead to the before originals;
            # that structural lineage never makes the control an original.
            self.assertTrue(member(before, original_control))
        self.assertNotIn(receipt, before.event_ids)
        self.assertNotIn(original_control, before.event_ids)
        self.assertNotIn(original_control, after.event_ids)
        self.assertTrue(calls)

    def test_explicit_selected_domain_does_not_claim_unrelated_stream_integrity(self):
        self.f.client.append_to_stream(self.f.log.stream,
            current_version=self.f.client.get_current_version(self.f.log.stream),
            events=[NewEvent(type="UnrelatedMalformedFixture", data=b"not an Experience envelope")])
        history = self.histories[("case", "after")]
        read, calls = self.bounded_reads()
        with patch.object(self.f.client, "get_stream", side_effect=read):
            self.assertTrue(self.policy.authorize_history_metadata(case_id="case", phase="after", history=history))
        legacy = SelectedRunEvidencePolicy(custody=self.custody, run_id="history-consumer", permissions=self.f.permissions)
        self.assertEqual(legacy.history_metadata_domain, "whole-stream-history-metadata-v1")
        self.assertFalse(legacy.authorize_history_metadata(case_id="case", phase="after", history=history))
        self.assertTrue(calls)


if __name__ == "__main__":
    unittest.main()
