"""Explicit runtime routing and callback integrity; no physical latency claim."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from flora.selected.context import ContextPlan
from flora.selected.selected_context import SelectedContextLogView, SelectedJudgmentContextPolicy
import test_selected_experiment_runtime as fixture


WHOLE = "whole-stream-current-context-v1"
SELECTED = "selected-current-context-v1"


class RuntimeContextDomainTest(unittest.TestCase):
    def setUp(self):
        self.f = fixture.SelectedExperimentRuntimeTest()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.plan = ContextPlan("runtime-domain-contract", "personal_judgment", exact_claim_ids=("claim",))

    def selected(self):
        return self.f._runtime(context_integrity_domain=SELECTED, maximum_context_sources=16)

    def prepared(self, *, domain=SELECTED):
        log = object.__new__(SelectedContextLogView)
        policy = object.__new__(SelectedJudgmentContextPolicy)
        log.domain = policy.domain = domain
        return SimpleNamespace(context=object(), log=log, policy=policy)

    def test_constructor_requires_explicit_domain_and_matching_finite_cap(self):
        for domain, cap in (("unknown", None), (WHOLE, 16), (SELECTED, None),
                            (SELECTED, 0), (SELECTED, True), (SELECTED, 1.5)):
            with self.subTest(domain=domain, cap=cap), self.assertRaises(ValueError):
                self.f._runtime(context_integrity_domain=domain, maximum_context_sources=cap)
        runtime = self.selected()
        self.assertEqual((runtime.context_integrity_domain, runtime.maximum_context_sources), (SELECTED, 16))

    def test_default_preparation_retains_whole_stream_consumer(self):
        runtime, expected = self.f._runtime(), object()
        self.assertEqual((runtime.context_integrity_domain, runtime.maximum_context_sources), (WHOLE, None))
        with patch("flora.selected.context_guard.prepare_current_context", return_value=expected) as old, \
                patch("flora.selected.selected_context.prepare_selected_current_context",
                    side_effect=AssertionError("default route entered selected domain")):
            self.assertIs(runtime._prepare_current_context(self.plan), expected)
        self.assertIs(old.call_args.kwargs["log"], runtime.log)
        self.assertIs(old.call_args.kwargs["policy"], runtime.context_policy)

    def test_selected_dispatch_keeps_original_services_and_qualification_hook(self):
        runtime, expected, guards = self.selected(), self.prepared(), []
        qualify = lambda barrier: None
        def selected(**arguments):
            guards.append(arguments["authority_guard"])
            arguments["authority_guard"]()
            self.assertIs(arguments["log"], runtime.log)
            self.assertIs(arguments["policy"], runtime.context_policy)
            self.assertEqual(arguments["maximum_sources"], 16)
            self.assertIs(arguments["before_private_assembly"], qualify)
            return expected
        with patch("flora.selected.selected_context.prepare_selected_current_context", side_effect=selected), \
                patch("flora.selected.context_guard.prepare_current_context",
                    side_effect=AssertionError("selected route fell back to whole stream")):
            self.assertIs(runtime._prepare_current_context(self.plan, before_private_assembly=qualify), expected)
        runtime.maximum_context_sources = 17
        with self.assertRaisesRegex(PermissionError, "domain changed"):
            guards[0]()

    def test_authority_callback_cannot_change_selected_domain_before_private_read(self):
        runtime, reached = self.selected(), []
        def authority():
            runtime.context_integrity_domain, runtime.maximum_context_sources = WHOLE, None
        def selected(**arguments):
            arguments["authority_guard"]()
            reached.append("private bytes")
            return self.prepared()
        with patch("flora.selected.selected_context.prepare_selected_current_context", side_effect=selected), \
                self.assertRaisesRegex(PermissionError, "domain changed"):
            runtime._prepare_current_context(self.plan, authority_guard=authority)
        self.assertEqual(reached, [])

    def test_external_authority_callback_cannot_run_after_selected_terminal_return(self):
        runtime, returned, late_revocations, checked = self.selected(), [False], [], []
        def authority():
            checked.append("authority")
            if returned[0]:
                # Such a callback would revoke an already observed original
                # after the selected consumer's shared terminal fence.
                late_revocations.append("original source withdrawn")
        expected = self.prepared()
        def selected(**arguments):
            arguments["authority_guard"]()
            returned[0] = True
            return expected
        with patch("flora.selected.selected_context.prepare_selected_current_context", side_effect=selected):
            self.assertIs(runtime._prepare_current_context(self.plan, authority_guard=authority), expected)
        self.assertEqual(checked, ["authority"])
        self.assertEqual(late_revocations, [])

    def test_selected_result_must_prove_effective_log_and_policy_domain(self):
        for wrong in (self.prepared(domain=WHOLE),
                      SimpleNamespace(log=SimpleNamespace(domain=SELECTED), policy=SimpleNamespace(domain=SELECTED))):
            with self.subTest(result=wrong), \
                    patch("flora.selected.selected_context.prepare_selected_current_context", return_value=wrong), \
                    self.assertRaisesRegex(PermissionError, "declared evidence domain"):
                self.selected()._prepare_current_context(self.plan)

    def test_selected_context_assembly_uses_prepared_route_without_model_resolution(self):
        runtime, expected = self.selected(), self.prepared()
        with patch("flora.selected.selected_context.prepare_selected_current_context", return_value=expected), \
                patch.object(runtime, "_resolve", side_effect=AssertionError("context assembly invoked a model")), \
                patch("flora.selected.experiment_runtime.assemble_context",
                    side_effect=AssertionError("selected context entered legacy producer")):
            self.assertIs(runtime._context(self.plan), expected.context)

    def test_mutated_invalid_cap_is_rejected_before_consumer_dispatch(self):
        runtime = self.selected()
        runtime.maximum_context_sources = True
        with patch("flora.selected.selected_context.prepare_selected_current_context",
                    side_effect=AssertionError("invalid cap reached selected consumer")), \
                self.assertRaisesRegex(ValueError, "positive source cap"):
            runtime._prepare_current_context(self.plan)


if __name__ == "__main__":
    unittest.main()
