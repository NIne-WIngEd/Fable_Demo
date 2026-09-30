"""Actual upstream closure and selected source/grant custody, no MFM model."""
import base64
from dataclasses import replace
import unittest
from unittest.mock import patch

from cognitive_kernel.formation_context_planner import FormationPlanningRequest
from cognitive_kernel.formation_retrieval import FormationRetrievalHit
from flora.selected.formation_context import prepare_selected_formation
from flora.selected.formation_policy import FormationPermissionAction, formation_permission_payload
from flora.selected.owner_authorization import OwnerActionProof, owner_action_message
from flora.selected.object_store import AESGCM
import test_history_fence as fixtures


class FormationPreflightTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.HistoryFenceTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f = self.fixture.f
        self.registry, self.permissions = self.fixture.registry, self.fixture.permissions
        self.parent, _, self.child = self.fixture.materials
        self.counter = 0
        self.grant(self.parent.event.event_id)
        self.grant(self.child.event.event_id)
        self.request = FormationPlanningRequest(scope=self.f.scope, authority_namespace_id=self.f.namespace,
            experience_refs=(self.child.event.event_id,))

    def grant(self, event_id, decision="allow"):
        f = self.f
        source = self.registry.lookup(event_id)
        prior = self.permissions.current_action(event_id, "memory_formation")
        self.counter += 1
        action = FormationPermissionAction.create(scope=f.scope, authority_namespace_id=f.namespace,
            action_id=f"formation-preflight-grant-{self.counter}", source_ref_id=event_id,
            source_registration_sha256=source.registration_sha256, purpose="memory_formation", decision=decision,
            generation=1 if prior is None else prior.generation + 1,
            previous_action_sha256=None if prior is None else prior.action_sha256,
            authorization_ref="fictional-enrolled-owner", authorized_at="2026-09-29T17:00:00Z")
        parents = (event_id,)
        if prior is not None:
            parents += (self.permissions._stored_action(prior.action_id)["request_event_id"],)
        event = f.event(formation_permission_payload(action), event_type="formation_permission_action",
            timestamp=action.authorized_at, parents=parents)
        f.proofs[event.event_id] = OwnerActionProof("formation_permission", event.event_id,
            event.event_sha256, base64.b64encode(f.key.sign(owner_action_message(event, "formation_permission"))).decode())
        self.permissions.apply(action, request_event_id=event.event_id, log=f.log, objects=f.objects,
            references=f.references, verifier=f.verifier)

    def prepare(self, **kwargs):
        return prepare_selected_formation(request=kwargs.pop("request", self.request), registry=self.registry,
            objects=self.f.objects, permits=self.permissions.permits, **kwargs)

    def test_actual_upstream_parent_closure_and_single_selector_precede_qualification(self):
        selected, qualified = 0, False
        original = self.f.objects.backend.get_object
        def selector(request, evidence, hits):
            nonlocal selected
            selected += 1
            return tuple(ref.ref_id for ref in evidence)
        def qualify(guard):
            nonlocal qualified
            self.assertEqual(selected, 1)
            with patch.object(self.f.objects.backend, "get_object", side_effect=AssertionError("metadata gate opened bytes")):
                guard()
            qualified = True
        def source_read(namespace, object_id):
            self.assertTrue(qualified)
            return original(namespace, object_id)
        with patch.object(self.f.objects.backend, "get_object", side_effect=source_read):
            prepared = self.prepare(selector=selector, before_private_assembly=qualify)
        self.assertEqual(selected, 1)
        self.assertTrue(qualified)
        self.assertEqual(tuple(ref.ref_id for ref in prepared.assembled.packet.evidence),
            (self.parent.event.event_id, self.child.event.event_id))
        self.assertEqual(prepared.assembled.closure_refs, (self.parent.event.event_id,))

    def test_denied_parent_stops_before_private_qualification_and_original_reads(self):
        self.grant(self.parent.event.event_id, "revoke")
        with patch.object(self.f.objects.backend, "get_object", side_effect=AssertionError("original cipher forbidden")):
            with self.assertRaises((ValueError, PermissionError)):
                self.prepare(before_private_assembly=lambda guard: self.fail("denied parent entered qualification"))

    def test_unqualified_role_stops_before_any_original_read(self):
        def refuse(guard):
            guard()
            raise PermissionError("actual producer role not qualified")
        with patch.object(self.f.objects.backend, "get_object", side_effect=AssertionError("original cipher forbidden")):
            with self.assertRaisesRegex(PermissionError, "not qualified"):
                self.prepare(before_private_assembly=refuse)

    def test_source_withdrawal_during_qualification_refuses_before_original_bytes(self):
        source_ids = {self.parent.event.payload_reference, self.child.event.payload_reference}
        original = self.f.objects.backend.get_object
        def read(namespace, object_id):
            if object_id in source_ids:
                self.fail("withdrawn original entered ciphertext read")
            return original(namespace, object_id)
        def qualify(guard):
            guard()
            self.grant(self.parent.event.event_id, "revoke")
        with patch.object(self.f.objects.backend, "get_object", side_effect=read):
            with self.assertRaises(PermissionError):
                self.prepare(before_private_assembly=qualify)

    def test_withdrawal_during_cipher_fetch_precedes_original_AES_decryption(self):
        original_read = self.f.objects.backend.get_object
        source_ids = {self.parent.event.payload_reference, self.child.event.payload_reference}
        source_nonces = {original_read(self.f.objects.namespace, object_id)[4:16] for object_id in source_ids}
        withdrawn = False
        def read(namespace, object_id):
            nonlocal withdrawn
            ciphertext = original_read(namespace, object_id)
            if object_id in source_ids and not withdrawn:
                withdrawn = True
                # Actual authenticated owner action; no helper-created grant.
                self.grant(self.child.event.event_id, "revoke")
            return ciphertext
        outer = self
        class InstrumentedAES:
            def __init__(self, key):
                self.actual = AESGCM(key)
            def encrypt(self, *args):
                return self.actual.encrypt(*args)
            def decrypt(self, nonce, *args):
                if nonce in source_nonces:
                    outer.fail("withdrawn original entered AES decryption")
                return self.actual.decrypt(nonce, *args)
        with patch.object(self.f.objects.backend, "get_object", side_effect=read), \
             patch("flora.selected.object_store.AESGCM", new=InstrumentedAES):
            with self.assertRaises(PermissionError):
                self.prepare()
        self.assertTrue(withdrawn)

    def test_returned_metadata_guard_opens_no_original_bytes_and_is_current(self):
        prepared = self.prepare()
        with patch.object(self.f.objects.backend, "get_object", side_effect=AssertionError("ciphertext forbidden")):
            prepared.metadata_current()
            prepared.revalidate()
        self.grant(self.parent.event.event_id, "revoke")
        with self.assertRaises(PermissionError):
            prepared.metadata_current()

    def test_caller_authored_candidates_and_empty_mandatory_experience_are_rejected(self):
        for request in (replace(self.request, candidates=(FormationRetrievalHit(self.parent.event.event_id, "exact"),)),
                        replace(self.request, experience_refs=())):
            with self.subTest(request=request):
                with self.assertRaises((ValueError, PermissionError)):
                    self.prepare(request=request, before_private_assembly=lambda guard: self.fail("invalid source plan qualified"))

    def test_source_metadata_change_during_gate_is_not_a_new_trusted_snapshot(self):
        key = self.registry._key("raw", self.parent.event.payload_reference)
        def qualify(guard):
            guard()
            self.f.connection.rows[("flora_formation_raw_references", key)]["record_sha256"] = "9"*64
        with patch.object(self.f.objects.backend, "get_object", side_effect=AssertionError("ciphertext forbidden")):
            with self.assertRaises((ValueError, PermissionError)):
                self.prepare(before_private_assembly=qualify)


if __name__ == "__main__":
    unittest.main()
