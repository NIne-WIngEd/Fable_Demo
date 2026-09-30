"""Actual private assembly with controlled metadata engines, not a latency claim."""
from copy import deepcopy
from collections import Counter
import json
import re
import unittest
from unittest.mock import patch

from flora.selected.context import ContextPlan, StateRoute
from flora.selected.context_guard import PreparedCurrentContext, prepare_current_context
from flora.selected.experiment_runtime import _AuthorizedRuntimeReads
from flora.selected.judgment_context import RegisteredJudgmentContextPolicy
from flora.selected.formation_policy import FormationPermissionAction
from flora.selected.governed_development import XTDBGovernedPersonalDevelopment
from flora.selected.personal_state import _ACTIVE, _VERSIONS
import test_governed_development as helpers
import test_governed_episodes as episode_helpers


class CurrentContextGuardTest(unittest.TestCase):
    def setUp(self):
        self.f = helpers.GovernedDevelopmentContractTest()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        f = self.f
        self.version, content = f.version(1)
        f.put(self.version, content)
        _, self.approval = f.activate(self.version)
        f.register_source(self.approval)
        f.policy.allowed.add((self.approval.event_id, "personal_judgment"))
        self.policy = RegisteredJudgmentContextPolicy(claims=f.claims, state=f.state, log=f.log,
            registry=f.registry, permissions=f.policy)
        self.plan = ContextPlan("guarded-exact-context", "personal_judgment",
            state_routes=(StateRoute(**f.identity()),))
        self.phase_allowed = True
        self.factory_calls = 0

    def phase(self):
        if not self.phase_allowed:
            raise PermissionError("phase withdrawn")

    def factory(self, metadata_barrier):
        self.factory_calls += 1
        return self.f.verifier

    def prepare(self, **kwargs):
        f = self.f
        return prepare_current_context(plan=kwargs.pop("plan", self.plan), claims=f.claims, state=f.state,
            log=f.log, objects=f.objects, references=f.references, policy=self.policy,
            approval_verifier_factory=kwargs.pop("factory", self.factory), authority_guard=self.phase, **kwargs)

    def test_actual_assembly_owned_then_repeated_guards_open_no_state_or_original_bytes(self):
        prepared = self.prepare()
        f = self.f
        self.assertEqual(prepared.context.items[0].content, b"fictional supplied state 1")
        with patch.object(f.objects, "get", side_effect=AssertionError("context plaintext re-read forbidden")), \
             patch.object(f.objects.backend, "get_object", side_effect=AssertionError("cipher read forbidden")):
            for _ in range(3):
                prepared.revalidate()
        self.assertGreaterEqual(self.factory_calls, 5)
        self.assertEqual(len(prepared.state_authorities), 1)

    def test_a_supplied_context_cannot_create_a_guard(self):
        with self.assertRaises(TypeError):
            PreparedCurrentContext(None)
        with self.assertRaises(TypeError):
            self.prepare(context=object())

    def test_current_owner_proof_is_rechecked_not_a_cached_allow_bit(self):
        prepared = self.prepare()
        self.f.proofs.clear()
        with self.assertRaises(PermissionError):
            prepared.revalidate()

    def test_current_owner_verifier_factory_can_change_after_preparation(self):
        prepared = self.prepare()
        class Deny:
            def authenticated_approval(self, event, request):
                return False
        self.f.verifier = Deny()
        with self.assertRaises(PermissionError):
            prepared.revalidate()

    def test_source_control_and_phase_revocation_precede_any_owner_proof_io(self):
        for event_id in (self.f.source_one.event_id, self.approval.event_id):
            prepared = self.prepare()
            self.f.policy.allowed.discard((event_id, "personal_judgment"))
            with patch.object(self, "factory", side_effect=AssertionError("proof factory forbidden")):
                with self.assertRaises((PermissionError, ValueError)):
                    prepared.revalidate()
            self.f.policy.allowed.add((event_id, "personal_judgment"))
        prepared = self.prepare()
        self.phase_allowed = False
        with self.assertRaises(PermissionError):
            prepared.revalidate()

    def test_state_head_or_immutable_version_mutation_refuses_held_bytes(self):
        prepared = self.prepare()
        f = self.f
        key = ("flora_personal_state_active_heads", f.state._head_id(**f.identity()))
        head = deepcopy(f.connection.rows[key])
        f.connection.rows[key]["activation_generation"] += 1
        with self.assertRaises(ValueError):
            prepared.revalidate()
        f.connection.rows[key] = head
        key = (_VERSIONS, f.state._version_id(self.version.version_id))
        f.connection.rows[key]["content_object_id"] = "changed-private-content-reference"
        with self.assertRaises(ValueError):
            prepared.revalidate()

    def test_source_registration_and_raw_custody_changes_are_detected(self):
        prepared = self.prepare()
        f = self.f
        f.registry.raw_records[f.source_one.payload_reference]["ciphertext_size"] += 1
        with self.assertRaises(PermissionError):
            prepared.revalidate()

    def test_mutating_the_held_context_is_not_a_new_trusted_snapshot(self):
        prepared = self.prepare()
        object.__setattr__(prepared.context.items[0], "content", b"unverified changed state")
        with self.assertRaises(ValueError):
            prepared.revalidate()

    def test_unsupported_live_accelerator_nominations_fail_explicitly(self):
        plan = ContextPlan("live-retrieval", "personal_judgment", query_vector=(.5,), vector_limit=1)
        with self.assertRaisesRegex(ValueError, "frozen exact nominations"):
            self.prepare(plan=plan)

    def test_preparation_baseline_detects_source_metadata_change_during_initial_read(self):
        f = self.f
        original = f.objects.backend.get_object
        changed = False
        def change(namespace, object_id):
            nonlocal changed
            content = original(namespace, object_id)
            if not changed:
                changed = True
                f.registry.raw_records[f.source_one.payload_reference]["ciphertext_size"] += 1
            return content
        with patch.object(f.objects.backend, "get_object", side_effect=change):
            with self.assertRaisesRegex((PermissionError, ValueError), "nomination.*changed"):
                self.prepare()
        self.assertTrue(changed)

    def test_phase_denial_during_owner_proof_cipher_lookup_prevents_plaintext_return(self):
        f = self.f
        original = f.objects.backend.get_object
        reads = []
        owner_io = False
        class CurrentVerifier:
            def __init__(inner, barrier):
                inner.objects = _AuthorizedRuntimeReads(f.objects, barrier)
            def authenticated_approval(inner, event, request):
                material = inner.objects.get(f.references[event.payload_reference])
                reads.append(material)
                return f.verifier.authenticated_approval(event, request)
        def factory(barrier):
            return CurrentVerifier(barrier)
        prepared = self.prepare(factory=factory)
        reads.clear()
        def revoke_phase(namespace, object_id):
            content = original(namespace, object_id)
            self.phase_allowed = False
            return content
        with patch.object(f.objects.backend, "get_object", side_effect=revoke_phase):
            with self.assertRaises(PermissionError):
                prepared.revalidate()
        self.assertEqual(reads, [])

    def claim(self):
        f = self.f
        version, relation = "fixture-claim-v1", "fixture-relation-v1"
        f.claims.versions[version] = {"claim_id": "fixture-claim", "claim_version_id": version,
            "adjudication_state": "accepted", "evidence_relation_ids": [relation], "value": {"fictional": "fact"},
            "version_sha256": "a"*64, "envelope": {"scope": f.scope.metadata_record(),
                "authority_namespace_id": f.namespace, "source_records": [f.source_one.event_id]}}
        f.claims.relations[relation] = {"evidence_record_id": f.source_one.event_id,
            "target_record_id": version, "target_record_type": "claim_version"}
        f.claims.current["fixture-claim"] = {"claim_id": "fixture-claim", "current_claim_version_id": version,
            "projection_id": "fixture-current-claim", "projection_sha256": "b"*64,
            "validity_state": "current", "deletion_state": "active", "conflict_state": "none",
            "adjudication_state": "accepted"}
        return ContextPlan("claim-context", "personal_judgment", exact_claim_ids=("fixture-claim",), minimum_claims=1)

    def test_current_claim_quarantine_rejects_without_raw_replay(self):
        prepared = self.prepare(plan=self.claim())
        self.f.claims.current["fixture-claim"]["deletion_state"] = "pending_delete"
        with patch.object(self.f.objects.backend, "get_object", side_effect=AssertionError("raw forbidden")):
            with self.assertRaises(ValueError):
                prepared.revalidate()

    def test_claim_value_relation_or_projection_metadata_changes_are_detected(self):
        for family in ("value", "relation", "projection"):
            with self.subTest(family=family):
                plan = self.claim()
                prepared = self.prepare(plan=plan)
                if family == "value":
                    self.f.claims.versions["fixture-claim-v1"]["value"] = {"unverified": "change"}
                elif family == "relation":
                    self.f.claims.relations["fixture-relation-v1"]["evidence_record_id"] = self.f.source_two.event_id
                else:
                    self.f.claims.current["fixture-claim"]["projection_sha256"] = "c"*64
                with self.assertRaises(ValueError):
                    prepared.revalidate()

    def test_valid_claim_head_replacement_during_policy_read_fails_final_fence(self):
        prepared = self.prepare(plan=self.claim())
        original = self.policy.allow_claim
        def change_after_allow(claim_id, purpose):
            allowed = original(claim_id, purpose)
            self.f.claims.current[claim_id]["projection_sha256"] = "c"*64
            return allowed
        with patch.object(self.policy, "allow_claim", side_effect=change_after_allow):
            with self.assertRaisesRegex(ValueError, "during metadata verification"):
                prepared.revalidate()

    def test_metadata_rows_sampled_once_per_guard_then_fenced_and_never_between_guards(self):
        prepared = self.prepare()
        f = self.f
        for _ in range(2):
            before = len(f.connection.calls)
            prepared.metadata_current()
            fetched = Counter((re.search(r"FROM (\w+)", sql).group(1), params)
                for sql, params in f.connection.calls[before:] if sql.startswith("SELECT"))
            # Real governed-state methods use the controlled SQL port. A row is
            # read once by the sampled pass and again by the original final fence.
            self.assertEqual(len(fetched), 3)
            self.assertEqual(set(fetched.values()), {2})

    def test_mutable_registered_policy_configuration_cannot_bypass_exact_bindings(self):
        prepared = self.prepare()
        self.policy.purpose = "formation_only"
        with self.assertRaisesRegex(PermissionError, "authority binding changed"):
            prepared.metadata_current()

    def test_pre_private_gate_is_after_metadata_denial_and_before_plaintext_or_owner_factory(self):
        f = self.f
        f.policy.allowed.discard((f.source_one.event_id, "personal_judgment"))
        with self.assertRaises((PermissionError, ValueError)):
            self.prepare(before_private_assembly=lambda barrier: self.fail("denied source entered private qualification"))
        f.policy.allowed.add((f.source_one.event_id, "personal_judgment"))
        qualified = False
        original = f.objects.backend.get_object
        def before(barrier):
            nonlocal qualified
            self.assertEqual(self.factory_calls, 0)
            barrier()
            qualified = True
        def source_read(namespace, object_id):
            self.assertTrue(qualified)
            return original(namespace, object_id)
        with patch.object(f.objects.backend, "get_object", side_effect=source_read):
            self.prepare(before_private_assembly=before)
        self.assertTrue(qualified)

    def test_withdrawal_during_pre_private_gate_stops_source_and_owner_reads(self):
        f = self.f
        def before(barrier):
            barrier()
            f.policy.allowed.discard((f.source_one.event_id, "personal_judgment"))
        with patch.object(f.objects.backend, "get_object", side_effect=AssertionError("source cipher forbidden")):
            with self.assertRaises((PermissionError, ValueError)):
                self.prepare(before_private_assembly=before)
        self.assertEqual(self.factory_calls, 0)

    def test_final_external_phase_callback_withdrawal_is_followed_by_current_source_fence(self):
        prepared = self.prepare()
        calls = 0
        def phase():
            nonlocal calls
            calls += 1
            if calls == 3:
                self.f.policy.allowed.discard((self.f.source_one.event_id, "personal_judgment"))
        prepared.authority_guard = phase
        with self.assertRaises(PermissionError):
            prepared.metadata_current()
        self.assertEqual(calls, 3)

    def test_initial_final_phase_callback_withdrawal_precedes_private_qualification(self):
        calls = 0
        def phase():
            nonlocal calls
            calls += 1
            if calls == 3:
                self.f.policy.allowed.discard((self.f.source_one.event_id, "personal_judgment"))
        with patch.object(self, "phase", side_effect=phase):
            with self.assertRaises((PermissionError, ValueError)):
                self.prepare(before_private_assembly=lambda barrier: self.fail("withdrawn source entered qualification"))
        self.assertEqual(self.factory_calls, 0)
        self.assertEqual(calls, 3)

    def test_an_allowed_new_grant_generation_is_not_the_captured_grant(self):
        f = self.f
        grants = {}
        for event_id in (f.source_one.event_id, self.approval.event_id):
            source = f.registry.lookup(event_id)
            grants[event_id] = FormationPermissionAction.create(scope=f.scope,
                authority_namespace_id=f.namespace, action_id="guard-grant-" + event_id,
                source_ref_id=event_id, source_registration_sha256=source.registration_sha256,
                purpose="personal_judgment", decision="allow", generation=1,
                previous_action_sha256=None, authorization_ref="fictional-authority",
                authorized_at="2026-09-29T12:00:00Z")
        f.policy.current_action = lambda event_id, purpose: grants.get(event_id)
        prepared = self.prepare()
        original = grants[f.source_one.event_id]
        material = {key: value for key, value in original.__dict__.items() if key != "action_sha256"}
        grants[f.source_one.event_id] = FormationPermissionAction.create(**{**material,
            "action_id": "guard-new-grant", "generation": 2,
            "previous_action_sha256": original.action_sha256})
        self.assertTrue(f.policy.permits(f.registry.lookup(f.source_one.event_id), "personal_judgment"))
        with self.assertRaisesRegex(PermissionError, "grant generation changed"):
            prepared.revalidate()

    def test_ancestor_permission_is_part_of_the_captured_source_closure(self):
        f = self.f
        child = f.event(b"fictional child source", parents=(f.source_one.event_id,))
        f.register_source(child)
        f.policy.allowed.add((child.event_id, "personal_judgment"))
        version, content = f.version(2, source=child, previous=self.version.version_id)
        f.put(version, content, self.version.version_id)
        _, approval = f.activate(version, self.version.version_id)
        f.register_source(approval)
        f.policy.allowed.add((approval.event_id, "personal_judgment"))
        prepared = self.prepare()
        self.assertIn(f.source_one.event_id, {source.event_id for source in prepared.source_authorities})
        f.policy.allowed.discard((f.source_one.event_id, "personal_judgment"))
        with self.assertRaises((PermissionError, ValueError)):
            prepared.revalidate()

    def test_rollback_target_metadata_is_still_current_without_reopening_its_bytes(self):
        f = self.f
        second, content = f.version(2, source=f.source_two, previous=self.version.version_id)
        f.put(second, content, self.version.version_id)
        f.activate(second, self.version.version_id)
        restored = f.rollback(self.version, second)
        _, approval = f.activate(restored.record, second.version_id)
        f.register_source(approval)
        f.policy.allowed.add((approval.event_id, "personal_judgment"))
        prepared = self.prepare()
        self.assertEqual(len(prepared.state_authorities[0].rollback_version_rows), 1)
        key = (_VERSIONS, f.state._version_id(self.version.version_id))
        f.connection.rows[key]["content_object_id"] = "different-rollback-target-reference"
        with patch.object(f.objects.backend, "get_object", side_effect=AssertionError("raw forbidden")):
            with self.assertRaises(ValueError):
                prepared.revalidate()


class CurrentEpisodeContextGuardTest(unittest.TestCase):
    def episode_context(self):
        fixture = episode_helpers.GovernedEpisodeBoundaryTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        f = fixture.f
        episode, artifact, _, _ = fixture.candidate()
        fixture.accept(episode, artifact)
        version, raw = fixture.derived_state(episode.episode_id)
        f.state = XTDBGovernedPersonalDevelopment(scope=f.scope, authority_namespace_id=f.namespace,
            connection=f.connection, registry=f.registry, policy=f.policy, episodes=fixture.episodes)
        f.state.put_candidate(version, content=raw, **fixture.inputs())
        _, approval = f.activate(version)
        f.register_source(approval)
        f.policy.allowed.add((approval.event_id, "personal_judgment"))
        policy = RegisteredJudgmentContextPolicy(claims=f.claims, state=f.state, log=f.log,
            registry=f.registry, permissions=f.policy)
        prepared = prepare_current_context(plan=ContextPlan("exact-episode-context", "personal_judgment",
            state_routes=(StateRoute(**f.identity()),)), claims=f.claims, state=f.state,
            log=f.log, objects=f.objects, references=fixture.references, policy=policy,
            approval_verifier_factory=lambda barrier: f.verifier)
        return fixture, prepared

    def test_current_episode_semantic_and_qualification_authority_is_not_cached(self):
        fixture, prepared = self.episode_context()
        f = fixture.f
        self.assertEqual(len(prepared.episode_authorities), 1)
        with patch.object(f.state, "read_active", side_effect=AssertionError("whole-state re-read forbidden")), \
             patch.object(fixture.episodes, "read_accepted", wraps=fixture.episodes.read_accepted) as accepted:
            prepared.revalidate()
            self.assertEqual(accepted.call_count, 1)
            fixture.admission.adjudicated.clear()
            # Immutable publication metadata still matches. The live external
            # authority must independently deny current semantic admission.
            prepared.metadata_current()
            with self.assertRaises(ValueError):
                prepared.revalidate()

    def test_withdrawal_during_final_episode_lineage_prevents_plaintext_return(self):
        fixture, prepared = self.episode_context()
        f = fixture.f
        original = type(fixture.episodes).current_lineage
        original_cipher_read = f.objects.backend.get_object
        calls = 0
        armed = False
        def withdraw(service, episode_id, **kwargs):
            nonlocal calls
            result = original(service, episode_id, **kwargs)
            # Only the final original-service lineage call is patched. The
            # per-pass copied episode reader continues its ordinary metadata.
            if service is fixture.episodes and armed:
                calls += 1
                f.policy.allowed.discard((f.source_one.event_id, "personal_judgment"))
            return result
        def cipher_read(namespace, object_id):
            nonlocal armed
            content = original_cipher_read(namespace, object_id)
            armed = True
            return content
        raw = f.references[f.source_one.payload_reference]
        guarded = _AuthorizedRuntimeReads(f.objects, prepared.metadata_current)
        with patch.object(type(fixture.episodes), "current_lineage", new=withdraw), \
             patch.object(f.objects.backend, "get_object", side_effect=cipher_read), \
             patch("flora.selected.object_store.AESGCM", side_effect=AssertionError("decryption after withdrawal")):
            with self.assertRaises((ValueError, PermissionError)):
                guarded.get(raw)
        self.assertGreater(calls, 0)
        self.assertTrue(armed)


if __name__ == "__main__":
    unittest.main()
