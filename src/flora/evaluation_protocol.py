"""Pre-model fairness contract for FloRA's frozen experimental goal.

This module validates a preregistered case/arm matrix and immutable run
receipts. It does not create synthetic life histories, execute models, infer
personal fit, or score a behavioral advantage.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Sequence


ARMS = frozenset({"flora_full", "general_model_memory", "same_evidence_ablation"})
PHASES = frozenset({"before", "after"})
INTERVENTIONS = frozenset({"relevant_correction", "irrelevant_correction",
                           "observed_outcome"})


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True,
                                     separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def _sha(value: str, label: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(
        char not in "0123456789abcdef" for char in value
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    host_id: str
    intervention: str
    split: str
    before_history_sha256: str
    after_history_sha256: str
    sealed_rubric_sha256: str
    intervention_event_id: str

    def validate(self) -> None:
        if not self.case_id or not self.host_id or not self.intervention_event_id:
            raise ValueError("case needs IDs for host, decision and intervention")
        if self.intervention not in INTERVENTIONS:
            raise ValueError("unknown intervention class")
        if self.split not in {"pilot", "heldout"}:
            raise ValueError("case split must be pilot or heldout")
        for label in ("before_history_sha256", "after_history_sha256",
                      "sealed_rubric_sha256"):
            _sha(getattr(self, label), label)
        if self.before_history_sha256 == self.after_history_sha256:
            raise ValueError("before and after histories must differ")


@dataclass(frozen=True)
class EvaluationProtocol:
    protocol_id: str
    goal_sha256: str
    frozen_at: str
    feature_engine_id: str
    response_token_budget: int
    wall_time_budget_ms: int
    cases: tuple[EvaluationCase, ...]
    baseline_design_sha256: str
    scoring_rubric_sha256: str
    threshold_spec_sha256: str
    builder_recipe_sha256: str
    builder_transfer_host_ids: tuple[str, ...]

    def validate(self) -> None:
        if not self.protocol_id or not self.frozen_at or not self.feature_engine_id:
            raise ValueError("protocol needs identity, date, and feature engine")
        for label in ("goal_sha256", "baseline_design_sha256",
                      "scoring_rubric_sha256", "threshold_spec_sha256",
                      "builder_recipe_sha256"):
            _sha(getattr(self, label), label)
        if (isinstance(self.response_token_budget, bool)
                or self.response_token_budget <= 0
                or isinstance(self.wall_time_budget_ms, bool)
                or self.wall_time_budget_ms <= 0):
            raise ValueError("response and time budgets must be positive")
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("case IDs are reused")
        if not self.cases or not any(case.split == "heldout" for case in self.cases):
            raise ValueError("protocol needs held-out cases")
        for case in self.cases:
            case.validate()
        hosts = {case.host_id for case in self.cases}
        if (not self.builder_transfer_host_ids
                or len(set(self.builder_transfer_host_ids))
                != len(self.builder_transfer_host_ids)
                or hosts.intersection(self.builder_transfer_host_ids)):
            raise ValueError("builder transfer hosts must be distinct and isolated")

    def record(self) -> dict[str, object]:
        self.validate()
        return {
            "schema": "flora-evaluation-protocol-v1",
            "protocol_id": self.protocol_id,
            "goal_sha256": self.goal_sha256,
            "frozen_at": self.frozen_at,
            "feature_engine_id": self.feature_engine_id,
            "response_token_budget": self.response_token_budget,
            "wall_time_budget_ms": self.wall_time_budget_ms,
            "cases": [vars(case) for case in self.cases],
            "baseline_design_sha256": self.baseline_design_sha256,
            "scoring_rubric_sha256": self.scoring_rubric_sha256,
            "threshold_spec_sha256": self.threshold_spec_sha256,
            "builder_recipe_sha256": self.builder_recipe_sha256,
            "builder_transfer_host_ids": list(self.builder_transfer_host_ids),
        }

    def digest(self) -> str:
        return _digest(self.record())


@dataclass(frozen=True)
class AttemptReceipt:
    protocol_sha256: str
    case_id: str
    host_id: str
    arm: str
    phase: str
    authorized_history_sha256: str
    selected_evidence_sha256: str
    delivered_context_sha256: str
    output_sha256: str
    feature_engine_id: str
    response_token_budget: int
    elapsed_ms: int
    artifact_lineage_sha256: str

    def validate(self) -> None:
        if self.arm not in ARMS or self.phase not in PHASES:
            raise ValueError("unknown arm or phase")
        for label in ("protocol_sha256", "authorized_history_sha256",
                      "selected_evidence_sha256", "delivered_context_sha256",
                      "output_sha256", "artifact_lineage_sha256"):
            _sha(getattr(self, label), label)
        if (not self.case_id or not self.host_id or not self.feature_engine_id
                or isinstance(self.response_token_budget, bool)
                or self.response_token_budget <= 0
                or isinstance(self.elapsed_ms, bool) or self.elapsed_ms < 0):
            raise ValueError("attempt receipt has invalid identity or budget")


def validate_paired_run(protocol: EvaluationProtocol,
                        attempts: Sequence[AttemptReceipt]) -> None:
    """Check comparability and completeness; never turn receipts into scores."""
    protocol.validate()
    by_case = {case.case_id: case for case in protocol.cases}
    expected = {(case.case_id, arm, phase)
                for case in protocol.cases for arm in ARMS for phase in PHASES}
    observed: dict[tuple[str, str, str], AttemptReceipt] = {}
    for attempt in attempts:
        attempt.validate()
        key = (attempt.case_id, attempt.arm, attempt.phase)
        if key in observed or key not in expected:
            raise ValueError("unexpected or duplicate evaluation attempt")
        case = by_case[attempt.case_id]
        history = (case.before_history_sha256 if attempt.phase == "before"
                   else case.after_history_sha256)
        if (attempt.protocol_sha256 != protocol.digest()
                or attempt.host_id != case.host_id
                or attempt.authorized_history_sha256 != history
                or attempt.feature_engine_id != protocol.feature_engine_id
                or attempt.response_token_budget != protocol.response_token_budget
                or attempt.elapsed_ms > protocol.wall_time_budget_ms):
            raise ValueError("evaluation attempt violates frozen evidence or budget")
        observed[key] = attempt
    if set(observed) != expected:
        raise ValueError("evaluation run is incomplete")
    for case in protocol.cases:
        for phase in PHASES:
            full = observed[(case.case_id, "flora_full", phase)]
            ablation = observed[(case.case_id, "same_evidence_ablation", phase)]
            if full.selected_evidence_sha256 != ablation.selected_evidence_sha256:
                raise ValueError("judgment ablation received different selected evidence")
