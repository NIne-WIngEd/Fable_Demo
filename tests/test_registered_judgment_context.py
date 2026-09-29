"""Permission-order regressions; fixture state is not learned judgment."""

from dataclasses import replace
from types import SimpleNamespace
import unittest

import test_governed_development as development_fixtures
import test_selected_source_native as source_fixtures

from flora.selected.context import ContextPlan, assemble_context
from flora.selected.judgment_context import RegisteredJudgmentContextPolicy


class RegisteredJudgmentContextTest(unittest.TestCase):
    def setUp(self):
        self.fixture = development_fixtures.GovernedDevelopmentContractTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        self.policy = RegisteredJudgmentContextPolicy(
            claims=f.claims, state=f.state, log=f.log,
            registry=f.registry, permissions=f.policy)

    def test_judgment_grant_is_distinct_and_parent_denial_blocks_child(self):
        f = self.fixture
        child = f.event(b"fictional derived source", parents=(f.source_one.event_id,))
        f.register_source(child)
        f.policy.allowed.add((child.event_id, "personal_judgment"))
        self.assertTrue(self.policy.allow_event(child.event_id, "personal_judgment"))
        f.policy.allowed.remove((f.source_one.event_id, "personal_judgment"))
        f.policy.allowed.add((f.source_one.event_id, "memory_formation"))
        self.assertFalse(self.policy.allow_event(child.event_id, "personal_judgment"))
        self.assertFalse(self.policy.allow_event(child.event_id, "provider_disclosure"))

    def test_active_state_requires_registered_permitted_approval(self):
        f = self.fixture
        version, content = f.version(1)
        f.put(version, content)
        self.assertFalse(self.policy.allow_state(**f.identity(), purpose="personal_judgment"))
        _, approval = f.activate(version)
        self.assertFalse(self.policy.allow_state(**f.identity(), purpose="personal_judgment"))
        f.register_source(approval)
        f.policy.allowed.add((approval.event_id, "personal_judgment"))
        self.assertTrue(self.policy.allow_state(**f.identity(), purpose="personal_judgment"))
        f.policy.allowed.remove((approval.event_id, "personal_judgment"))
        self.assertFalse(self.policy.allow_state(**f.identity(), purpose="personal_judgment"))

    def test_changed_registration_cannot_relabel_original_event(self):
        f = self.fixture
        original = f.registry.sources[f.source_one.event_id]
        f.registry.sources[f.source_one.event_id] = replace(original, object_ref="different-object")
        self.assertFalse(self.policy.allow_event(f.source_one.event_id, "personal_judgment"))

    def test_context_denied_source_is_never_opened(self):
        f = self.fixture
        authority = source_fixtures._Authority(f.scope, f.source_one.event_id)
        authority.present["projection_sha256"] = "a" * 64
        authority.version["value"] = {"fixture": "supplied meaning"}
        policy = SimpleNamespace(allow_claim=lambda *args: True,
                                 allow_event=lambda *args: False,
                                 allow_state=lambda *args: False)
        def forbidden_get(reference):
            raise AssertionError("denied original was opened")
        f.objects.get = forbidden_get
        with self.assertRaisesRegex(PermissionError, "before raw read"):
            assemble_context(plan=ContextPlan(request_id="fictional-context",
                purpose="personal_judgment", exact_claim_ids=("claim-one",), minimum_claims=1),
                claims=authority, state=f.state, log=f.log, objects=f.objects,
                references=f.references, policy=policy, approval_verifier=f.verifier)


if __name__ == "__main__":
    unittest.main()
