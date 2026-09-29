import dataclasses
import unittest

from flora.evaluation_protocol import (
    ARMS, PHASES, AttemptReceipt, EvaluationCase,
    EvaluationProtocol, validate_paired_run,
)


class EvaluationProtocolTest(unittest.TestCase):
    def setUp(self):
        self.protocol = EvaluationProtocol(
            protocol_id="synthetic-contract-check", goal_sha256="a" * 64,
            frozen_at="2026-09-29T14:00:00Z",
            feature_engine_id="same-feature-service",
            response_token_budget=500, wall_time_budget_ms=30000,
            cases=(EvaluationCase(
                case_id="heldout-one", host_id="host-one",
                intervention="relevant_correction", split="heldout",
                before_history_sha256="b" * 64,
                after_history_sha256="c" * 64,
                sealed_rubric_sha256="d" * 64,
                intervention_event_id="source-correction-one"),),
            baseline_design_sha256="e" * 64,
            scoring_rubric_sha256="f" * 64,
            threshold_spec_sha256="1" * 64,
            builder_recipe_sha256="2" * 64,
            builder_transfer_host_ids=("host-two",),
        )
        self.attempts = [AttemptReceipt(
            protocol_sha256=self.protocol.digest(), case_id="heldout-one",
            host_id="host-one", arm=arm, phase=phase,
            authorized_history_sha256=("b" if phase == "before" else "c") * 64,
            selected_evidence_sha256=("9" if arm == "general_model_memory"
                                      else "8") * 64,
            delivered_context_sha256="3" * 64,
            output_sha256="4" * 64,
            feature_engine_id="same-feature-service",
            response_token_budget=500, elapsed_ms=100,
            artifact_lineage_sha256="5" * 64,
        ) for phase in sorted(PHASES) for arm in sorted(ARMS)]

    def test_complete_equal_budget_and_attribution_control(self):
        validate_paired_run(self.protocol, self.attempts)
        wrong = list(self.attempts)
        wrong[0] = dataclasses.replace(wrong[0], response_token_budget=501)
        with self.assertRaisesRegex(ValueError, "evidence or budget"):
            validate_paired_run(self.protocol, wrong)
        wrong = list(self.attempts)
        index = next(i for i, item in enumerate(wrong)
                     if item.arm == "same_evidence_ablation")
        wrong[index] = dataclasses.replace(wrong[index],
                                           selected_evidence_sha256="7" * 64)
        with self.assertRaisesRegex(ValueError, "different selected evidence"):
            validate_paired_run(self.protocol, wrong)

    def test_host_transfer_and_complete_matrix(self):
        with self.assertRaisesRegex(ValueError, "isolated"):
            dataclasses.replace(self.protocol,
                                builder_transfer_host_ids=("host-one",)).validate()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            validate_paired_run(self.protocol, self.attempts[:-1])


if __name__ == "__main__":
    unittest.main()
