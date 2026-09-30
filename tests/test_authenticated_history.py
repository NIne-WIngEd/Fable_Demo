"""Issued selected byte ownership with actual uncached current authority.

Real custody, registry, grant and crypto algorithms use controlled SQL/log ports;
these tests do not qualify physical engine latency or model behavior.
"""
import asyncio
from copy import copy
from dataclasses import replace
import sys
import unittest
from unittest.mock import patch

from qdrant_client import QdrantClient

from comparator_fixtures import FixtureByteCounter, FixtureCompiler, FixtureEmbeddings, configuration
from flora.comparison_run import PreparationRequest, ExecutionRequest, ArmStopped, run_paired
from flora.selected.authenticated_history import (
    AuthenticatedSelectedHistory, request_authenticated_history,
)
from flora.selected.comparator_memory import QdrantOriginalMemory
from flora.selected.provider_attempt_custody import XTDBProviderAttemptCustody
import test_history_fence as fixtures


class AuthenticatedHistoryTest(unittest.TestCase):
    def setUp(self):
        self.h = fixtures.HistoryFenceTest()
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.plan = replace(self.h.plan, context_token_budget=20000, context_byte_budget=20000)
        self.request = PreparationRequest("case", "before", b"fictional frozen question",
            self.h.before, self.plan)

    def issue(self):
        return AuthenticatedSelectedHistory(policy=self.h.policy, plan=self.plan,
            case_id="case", phase="before", history=self.h.before)

    def current(self, proof, **changes):
        return request_authenticated_history(replace(self.request,
            authenticated_history=proof, **changes), policy=self.h.policy)

    def test_issuance_really_authenticates_original_ciphertext(self):
        ids = {source.event.payload_reference for source in self.h.before.sources}
        opened = []
        actual = self.h.f.objects.backend.get_object
        def get(namespace, object_id):
            opened.append(object_id)
            return actual(namespace, object_id)
        with patch.object(self.h.f.objects.backend, "get_object", side_effect=get):
            proof = self.issue()
        self.assertTrue(ids.issubset(opened))
        self.assertIs(self.current(proof), self.h.before)

    def test_boolean_authorize_override_cannot_issue_unauthenticated_bytes(self):
        with patch.object(self.h.policy, "authorize_history", return_value=True), \
             patch.object(self.h.custody.raw_custody, "read", side_effect=PermissionError("unavailable")):
            with self.assertRaises(PermissionError):
                self.issue()

    def test_prebound_plaintext_reader_cannot_issue_without_actual_ciphertext(self):
        by_id = {source.event.payload_reference: source.plaintext for source in self.h.before.sources}
        with patch.object(self.h.custody.raw_custody, "read", side_effect=lambda scope, object_id: by_id[object_id]), \
             patch.object(self.h.f.objects.backend, "get_object", side_effect=AssertionError("ciphertext unavailable")):
            with self.assertRaises(PermissionError):
                self.issue()

    def test_prebound_metadata_boolean_does_not_hide_actual_withdrawal(self):
        with patch.object(self.h.policy, "authorize_history_metadata", return_value=True):
            proof = self.issue()
            self.h.grant(self.h.before.event_ids[0], "before", "revoke")
            with self.assertRaises(PermissionError):
                self.current(proof)

    def test_prebound_final_authority_callback_cannot_create_missing_anchor(self):
        bindings = {(case.case_id, phase, arm): binding
            for case in self.plan.protocol.cases for phase in ("before", "after")
            for arm, binding in self.plan.arm_bindings.items()}
        anchored = replace(self.plan, phase_bindings=bindings, preregistration_sha256="a" * 64)
        for target in (self.h.policy, self.h.custody):
            with self.subTest(target=type(target).__name__), \
                 patch.object(target, "require_final_authority", return_value=None):
                with self.assertRaises(PermissionError):
                    AuthenticatedSelectedHistory(policy=self.h.policy, plan=anchored,
                        case_id="case", phase="before", history=self.h.before)

    def test_reuse_opens_no_originals_but_observes_current_revocation(self):
        proof = self.issue()
        with patch.object(self.h.f.objects.backend, "get_object", side_effect=AssertionError("original reopened")):
            self.assertIs(self.current(proof), self.h.before)
            self.assertIs(self.current(proof), self.h.before)
        self.h.grant(self.h.before.event_ids[0], "before", "revoke")
        with self.assertRaises(PermissionError):
            self.current(proof)

    def test_unissued_boolean_foreign_policy_and_changed_request_are_denied(self):
        proof = self.issue()
        for forged in (True, object(), object.__new__(AuthenticatedSelectedHistory)):
            with self.subTest(forged=type(forged).__name__), self.assertRaises(PermissionError):
                self.current(forged)
        with self.assertRaises(PermissionError):
            request_authenticated_history(replace(self.request, authenticated_history=proof),
                policy=copy(self.h.policy))
        for changes in ({"question": b"changed"}, {"case_id": "foreign"}, {"phase": "after"},
                {"history": replace(self.h.before)}, {"plan": replace(self.plan)},
                {"plan": replace(self.plan, context_byte_budget=30000)}):
            with self.subTest(changes=tuple(changes)), self.assertRaises(PermissionError):
                self.current(proof, **changes)

    def test_actual_controller_replacement_cannot_reuse_issued_authentication(self):
        proof = self.issue()
        with patch.object(self.h.policy, "authorize_history_metadata", return_value=True):
            with self.assertRaises(PermissionError):
                self.current(proof)
        original_custody = self.h.policy.custody
        self.h.policy.custody = copy(original_custody)
        try:
            with self.assertRaises(PermissionError):
                self.current(proof)
        finally:
            self.h.policy.custody = original_custody

    def test_revoked_authority_cannot_rebind_registered_services_to_stale_connection(self):
        from copy import deepcopy
        from test_governed_development import _SQLCalls
        from metadata_batch_fixture import install_current_metadata_batch
        proof = self.issue()
        shadow = _SQLCalls()
        install_current_metadata_batch(shadow)
        shadow.rows = deepcopy(self.h.f.connection.rows)
        self.h.grant(self.h.before.event_ids[0], "before", "revoke")
        with self.assertRaises(PermissionError):
            self.current(proof)
        actual_registry, actual_permissions = self.h.registry.connection, self.h.permissions.connection
        self.h.registry.connection, self.h.permissions.connection = shadow, shadow
        try:
            with self.assertRaises(PermissionError):
                self.current(proof)
            with self.assertRaises(PermissionError):
                self.issue()
        finally:
            self.h.registry.connection, self.h.permissions.connection = actual_registry, actual_permissions

    def test_last_actual_grant_callback_revocation_denies_held_history(self):
        actual, armed, changed = self.h.permissions.current_action, False, False
        def action(event_id, purpose):
            nonlocal changed, armed
            result = actual(event_id, purpose)
            frame = sys._getframe(1)
            while frame is not None and frame.f_code.co_name != "verify_current_history_metadata":
                frame = frame.f_back
            if (armed and not changed and event_id == self.h.before.event_ids[-1]
                    and frame is not None and "current_entries" in frame.f_locals):
                changed, armed = True, False
                self.h.grant(self.h.before.event_ids[0], "before", "revoke")
            return result
        with patch.object(self.h.permissions, "current_action", side_effect=action):
            proof = self.issue()
            armed = True
            with self.assertRaises(PermissionError):
                self.current(proof)
        self.assertTrue(changed)

    def test_qdrant_reuses_issued_bytes_and_direct_preparation_still_authenticates(self):
        proof = self.issue()
        client = QdrantClient(":memory:")
        self.addCleanup(client.close)
        memory = QdrantOriginalMemory(custody=self.h.custody, run_id="run", configuration=configuration(),
            client=client, embeddings=FixtureEmbeddings(), tokenizer=FixtureByteCounter(),
            wire_compiler=FixtureCompiler(), evidence=self.h.policy)
        with patch.object(self.h.f.objects.backend, "get_object", side_effect=PermissionError("raw unavailable")):
            context = asyncio.run(memory.prepare(replace(self.request, authenticated_history=proof)))
            self.assertTrue(context.source_event_ids)
            from flora.comparison_run import ArmStopped
            with self.assertRaises(ArmStopped):
                asyncio.run(memory.prepare(self.request))

    def test_embedding_owner_rebind_is_denied_before_private_vector_write(self):
        proof = self.issue()
        client = QdrantClient(":memory:")
        self.addCleanup(client.close)
        embeddings = FixtureEmbeddings()
        actual_embed = embeddings.embed
        async def embed(content):
            result = await actual_embed(content)
            self.h.policy.authorize_history_metadata = lambda **_: False
            return result
        memory = QdrantOriginalMemory(custody=self.h.custody, run_id="run", configuration=configuration(),
            client=client, embeddings=embeddings, tokenizer=FixtureByteCounter(),
            wire_compiler=FixtureCompiler(), evidence=self.h.policy)
        with patch.object(embeddings, "embed", side_effect=embed), \
             patch.object(client, "upsert", side_effect=AssertionError("rebound vector write")):
            with self.assertRaises(PermissionError):
                asyncio.run(memory.prepare(replace(self.request, authenticated_history=proof)))

    def test_embedding_cannot_clear_proof_and_hide_actual_source_revocation(self):
        proof = self.issue()
        request = replace(self.request, authenticated_history=proof)
        client = QdrantClient(":memory:")
        self.addCleanup(client.close)
        embeddings = FixtureEmbeddings()
        actual_embed = embeddings.embed
        async def embed(content):
            result = await actual_embed(content)
            self.h.grant(self.h.before.event_ids[0], "before", "revoke")
            object.__setattr__(request, "authenticated_history", None)
            return result
        memory = QdrantOriginalMemory(custody=self.h.custody, run_id="run", configuration=configuration(),
            client=client, embeddings=embeddings, tokenizer=FixtureByteCounter(),
            wire_compiler=FixtureCompiler(), evidence=self.h.policy)
        with patch.object(embeddings, "embed", side_effect=embed), \
             patch.object(client, "upsert", side_effect=AssertionError("withdrawn vector write")):
            with self.assertRaises(PermissionError):
                asyncio.run(memory.prepare(request))

    def test_guarded_coordinator_policy_preserves_full_authentication_without_unwrapping(self):
        checks, prepared = [], []
        def check():
            checks.append(True)
            return True
        guarded = self.h.custody._authority_fenced_copy(check)
        policy = copy(self.h.policy)
        policy.custody = guarded
        class Adapter:
            async def prepare(inner, request):
                prepared.append(request.authenticated_history)
                raise ArmStopped("unavailable")
        opened = []
        actual = self.h.f.objects.backend.get_object
        def get(namespace, object_id):
            opened.append(object_id)
            return actual(namespace, object_id)
        with patch.object(self.h.f.objects.backend, "get_object", side_effect=get):
            run = asyncio.run(run_paired(plan=self.plan,
                histories={("case", "before"): self.h.before, ("case", "after"): self.h.after},
                questions={"case": self.request.question}, adapters={"general_model_memory": Adapter()},
                evidence_policy=policy))
        self.assertEqual(prepared, [None, None])
        self.assertTrue(checks)
        self.assertTrue({source.event.payload_reference for source in self.h.after.sources}.issubset(opened))
        self.assertEqual({attempt.status for attempt in run.attempts}, {"unavailable"})

    def test_provider_held_reuse_preserves_current_manifest_grant(self):
        manifest = self.h.custody.metadata("run", "history:case:before")
        self.h.grant(manifest.event_id, "before")
        proof = self.issue()
        request = ExecutionRequest("case", "before", self.request.question,
            self.h.before.scope, self.h.before.digest(), self.h.before.event_ids, None,
            self.plan.arm_bindings["general_model_memory"], self.plan, proof)
        owner = object.__new__(XTDBProviderAttemptCustody)
        owner.comparison, owner.evidence = self.h.custody, self.h.policy
        owner.permissions, owner.registry = self.h.permissions, self.h.registry
        owner.run_id, owner.scope, owner.log, owner.objects = "run", self.h.f.scope, self.h.f.log, self.h.f.objects
        with patch.object(self.h.f.objects.backend, "get_object", side_effect=AssertionError("held bytes reopened")):
            self.assertIs(owner._phase_history(request)[0], self.h.before)
        self.h.grant(manifest.event_id, "before", "revoke")
        with self.assertRaises(PermissionError):
            owner._phase_history(request)

    def test_execution_hash_ids_and_scope_cannot_substitute_another_history(self):
        proof = self.issue()
        request = ExecutionRequest("case", "before", self.request.question,
            self.h.before.scope, self.h.before.digest(), self.h.before.event_ids, None,
            self.plan.arm_bindings["general_model_memory"], self.plan, proof)
        for changes in ({"authorized_history_sha256": "a" * 64},
                {"authorized_event_ids": self.h.after.event_ids},
                {"scope": replace(self.h.before.scope, host_instance_id="other-host")}):
            with self.subTest(changes=tuple(changes)), self.assertRaises(PermissionError):
                request_authenticated_history(replace(request, **changes), policy=self.h.policy)

    def test_private_proof_has_no_exportable_payload_or_visible_request_representation(self):
        proof = self.issue()
        request = replace(self.request, authenticated_history=proof)
        self.assertNotIn("authenticated_history", repr(request))
        self.assertNotIn(self.h.before.sources[0].plaintext.decode(), repr(proof))
        with self.assertRaises(TypeError):
            vars(proof)
        # There is no successful implicit JSON wire encoding of this local
        # object. Real provider codecs manually encode their declared fields.
        import json
        with self.assertRaises(TypeError):
            json.dumps(proof)


if __name__ == "__main__":
    unittest.main()
