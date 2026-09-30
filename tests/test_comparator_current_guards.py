"""Selected comparator guard mechanics with controlled SQL and local Qdrant.

Actual scoped registry/policy, encrypted objects and current-row checks run.
The SQL/log and embedding outputs are fixtures; this is no physical latency,
semantic retrieval or model-quality qualification.
"""
import asyncio
from copy import copy
from dataclasses import replace
import sys
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from qdrant_client import QdrantClient

from comparator_fixtures import (
    FixtureByteCounter, FixtureCompiler, FixtureEmbeddings, configuration, signed_response,
)
from flora.comparator import Ed25519TransportObservationVerifier, ProviderRequest, encoded, provider_payload
from flora.comparison_run import ArmBinding, ArmStopped, ExecutionRequest, PreparationRequest
from flora.selected.comparator_memory import (
    QdrantOriginalMemory, SelectedComparatorDisclosure, SelectedComparatorRecorder, source_windows,
)
import test_history_fence as fixtures
import test_provider_source_fence as provider_fixtures


class ComparatorCurrentGuardsTest(unittest.TestCase):
    def setUp(self):
        self.h = fixtures.HistoryFenceTest()
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.client = QdrantClient(":memory:")
        self.addCleanup(self.client.close)
        self.embeddings = FixtureEmbeddings()
        self.memory = QdrantOriginalMemory(custody=self.h.custody, run_id="run",
            configuration=configuration(), client=self.client,
            embeddings=self.embeddings, tokenizer=FixtureByteCounter(),
            wire_compiler=FixtureCompiler(), evidence=self.h.policy)
        self.request = PreparationRequest("case", "before", b"fictional frozen question",
            self.h.before, replace(self.h.plan, context_token_budget=20000,
                context_byte_budget=20000))

    def test_initial_authentication_then_current_guards_do_not_reopen_originals(self):
        actual_embed = self.embeddings.embed
        original_ids = {s.event.payload_reference for s in self.h.before.sources}
        original_get = self.h.f.objects.backend.get_object
        opened, after_authentication = [], False
        async def embed(content):
            nonlocal after_authentication
            self.assertTrue(original_ids.issubset(opened))
            after_authentication = True
            return await actual_embed(content)
        def get(namespace, object_id):
            if object_id in original_ids:
                self.assertFalse(after_authentication,
                    "a later operation guard reopened an already authenticated original")
                opened.append(object_id)
            return original_get(namespace, object_id)
        with patch.object(self.embeddings, "embed", side_effect=embed), \
             patch.object(self.h.f.objects.backend, "get_object", side_effect=get):
            context = asyncio.run(self.memory.prepare(self.request))
        self.assertEqual(set(context.source_event_ids), set(self.h.before.event_ids))
        # A subsequent preparation must perform its own actual authentication.
        with patch.object(self.h.f.objects.backend, "get_object", side_effect=PermissionError("source unavailable")):
            with self.assertRaises(ArmStopped):
                asyncio.run(self.memory.prepare(self.request))

    def test_revocation_during_embedding_denies_before_qdrant_creation(self):
        actual_embed = self.embeddings.embed
        async def embed(content):
            result = await actual_embed(content)
            self.h.grant(self.h.before.event_ids[0], "before", "revoke")
            return result
        with patch.object(self.embeddings, "embed", side_effect=embed), \
             patch.object(self.client, "create_collection", side_effect=AssertionError("withdrawn vector write")):
            with self.assertRaises(ArmStopped):
                asyncio.run(self.memory.prepare(self.request))

    def test_last_current_callback_withdrawal_denies_before_vector_write(self):
        actual_get = self.client.get_collection
        def collection(name):
            result = actual_get(name)
            # The source was initially authenticated and projection metadata
            # was read. The next write still needs fresh actual grant authority.
            self.h.grant(self.h.before.event_ids[0], "before", "revoke")
            return result
        with patch.object(self.client, "get_collection", side_effect=collection), \
             patch.object(self.client, "upsert", side_effect=AssertionError("withdrawn vector write")):
            with self.assertRaises(ArmStopped):
                asyncio.run(self.memory.prepare(self.request))

    def test_changed_held_original_is_denied_before_embedding(self):
        changed = replace(self.h.before, sources=(replace(self.h.before.sources[0], plaintext=b"changed"),)
            + self.h.before.sources[1:])
        with patch.object(self.embeddings, "embed", side_effect=AssertionError("unverified original reached embedding")):
            with self.assertRaises(ArmStopped):
                asyncio.run(self.memory.prepare(replace(self.request, history=changed)))

    def test_external_callback_cannot_withdraw_evaluation_before_response_seal(self):
        self._assert_external_callback_withdrawal()

    def test_distinct_disclosure_permission_owner_keeps_its_actual_denial(self):
        self._assert_external_callback_withdrawal(distinct_owner=True)

    def _assert_external_callback_withdrawal(self, *, distinct_owner=False):
        h, config = self.h, self.memory.configuration
        self.f, self.registry, self.permissions, self.count = h.f, h.registry, h.permissions, 0
        def grant(event_id, purpose):
            return provider_fixtures.ProviderSourceFenceTest.grant(self, event_id, purpose)
        h.grant(h.custody.metadata("run", "history:case:before").event_id, "before")
        external = "comparison_external:" + config.provider.provider_id
        question_id = h.custody.metadata("run", "question:case").event_id
        for event_id in (question_id, *h.before.event_ids):
            grant(event_id, external)
        binding = ArmBinding(config.producer_component, config.provider.digest(), config.digest(),
            "source-memory-without-native-update")
        plan = replace(self.request.plan, arm_bindings={arm: binding for arm in self.request.plan.arm_bindings})
        prep = replace(self.request, plan=plan)
        context = self.memory._context(prep, tuple(range(len(source_windows(h.before, config)))),
            source_windows(h.before, config))
        request = ExecutionRequest("case", "before", prep.question, h.before.scope, h.before.digest(),
            h.before.event_ids, context, binding, plan)
        provider = ProviderRequest(config.provider, provider_payload(config, question=prep.question,
            context=context, response_token_budget=plan.protocol.response_token_budget,
            wire_compiler=FixtureCompiler()), plan.protocol.response_token_budget)
        key = Ed25519PrivateKey.generate()
        verifier = Ed25519TransportObservationVerifier(configuration=config.provider,
            public_key=key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
        disclosure_permissions = copy(h.permissions) if distinct_owner else h.permissions
        disclosure = SelectedComparatorDisclosure(custody=h.custody, run_id="run", configuration=config,
            permissions=disclosure_permissions, wire_compiler=FixtureCompiler(), evidence=h.policy)
        recorder = SelectedComparatorRecorder(custody=h.custody, run_id="run", configuration=config,
            disclosure=disclosure, exchange_verifier=verifier, clock=lambda: "2026-09-30T17:00:00Z")
        response = signed_response(provider, "d" * 64, key)
        actual_permits, changed = disclosure_permissions.permits, False
        target = h.f.objects._identity(encoded(context.receipt_record()))
        sealed = []
        actual_encrypt = AESGCM.encrypt
        def encrypt(cipher, nonce, content, aad):
            if aad.decode().rsplit(":", 1)[-1] == target:
                sealed.append(target)
            return actual_encrypt(cipher, nonce, content, aad)
        def permits(source, purpose):
            nonlocal changed
            result = actual_permits(source, purpose)
            frame = sys._getframe(1)
            inside_current = False
            while frame is not None:
                if (frame.f_code.co_name == "current" and
                        frame.f_code.co_filename.endswith("comparator_memory.py") and
                        "permission_rows" in frame.f_locals):
                    inside_current = True
                    break
                frame = frame.f_back
            if (inside_current and purpose == external and
                    source.evidence.ref_id == h.before.event_ids[-1] and not changed):
                changed = True
                h.grant(h.before.event_ids[0], "before", "revoke")
            return result
        with patch.object(disclosure_permissions, "permits", side_effect=permits), \
             patch.object(AESGCM, "encrypt", new=encrypt):
            with self.assertRaises(PermissionError):
                recorder.record(request=request, provider_request=provider, response=response,
                    token_count=FixtureByteCounter().count(provider.payload), authorization_marker="d" * 64)
        self.assertTrue(changed)
        self.assertFalse(sealed, "response was sealed after its evaluation source grant was withdrawn")


if __name__ == "__main__":
    unittest.main()
