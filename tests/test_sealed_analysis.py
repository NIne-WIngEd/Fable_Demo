"""Fictional signed-human fixtures, never a learned or behavioral result."""

from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
import json
import random
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from cognitive_kernel.canonical import canonical_json_bytes
from flora.comparison_run import create_blind_review
from flora.blind_assessment import ApprovedReviewer, Ed25519AssessmentAuthority
from flora.sealed_analysis import (
    MAX_CLUSTER_DRAWS, MAX_RESAMPLES, _ClusterDraws, _bootstrap, _quantile,
    analyze_sealed_assessment, validate_analysis_spec,
)
import test_blind_assessment as fixture_support


def fictional_analysis_spec():
    """All values are explicit fictional inputs, not proposed study choices."""
    return {"schema": "flora-sealed-assessment-analysis-v1", "analysis_id": "fictional-analysis",
        "acceptance_combination": "all_criteria", "metrics": [{
            "metric_id": "fictional-personal-fit", "dimension": "personal_fit",
            "comparator": "general_model_memory", "phase": "after", "split": "heldout",
            "interventions": ["relevant_correction", "irrelevant_correction", "observed_outcome"],
            "denominator": "all_planned_pairs", "reviewer_aggregation": "equal_reviewers_within_pair",
            "point_weighting": "equal_planned_pairs",
            "label_scores": {"prefer_left": {"left": "1/1", "right": "-1/1"},
                "prefer_right": {"left": "-1/1", "right": "1/1"}, "tie": {"left": "0/1", "right": "0/1"}},
            "unassessed_score": "0/1", "excluded_pair_score": "-1/1",
            "uncertainty": {"method": "cluster_percentile_v1", "cluster_unit": "case", "confidence": "9/10",
                "resamples": 20, "seed": 123, "minimum_clusters": 2,
                "sampling_assumptions": "Fictional case-cluster assumption; no actual sampling-design qualification.",
                "quantile": "linear_order_statistics_v1", "resampling": "sha256_counter_rejection_v1"},
            "criteria": [{"quantity": "point", "operator": "ge", "bound": "1/1"}]}]}


def bind_fictional_analysis(fixture, specification):
    """Freeze supplied fixture bytes in the protocol before rating collection."""
    fixture.threshold = canonical_json_bytes(specification)
    protocol = replace(fixture.run.plan.protocol, threshold_spec_sha256=fixture_support.sha(fixture.threshold))
    plan = replace(fixture.run.plan, protocol=protocol)
    fixture.run = replace(fixture.run, plan=plan,
        attempts=tuple(replace(attempt, plan_sha256=plan.digest()) for attempt in fixture.run.attempts))
    fixture.pack, fixture.key = create_blind_review(fixture.run,
        policy=fixture_support.FictionalReviewPermission(), rng=random.Random(13))
    fixture.spec = fixture._spec()


class SealedAnalysisTest(unittest.TestCase):
    def setUp(self):
        self.fx = fixture_support.BlindAssessmentContractTest()
        self.fx.setUp()
        self.analysis = fictional_analysis_spec()

    def _prepare(self, *, analysis=None, failing=False, missing=False, sealed=True):
        self.fx.setUp()
        bind_fictional_analysis(self.fx, analysis or self.analysis)
        if failing:
            self.fx.run = replace(self.fx.run, attempts=tuple(
                replace(a, status="timeout", elapsed_ms=1001, usage=None, output=None,
                    output_sha256=None, decision_event_id=None)
                if a.case_id == self.fx.cases[0].case_id and a.phase == "after" and a.arm == "flora_full"
                else a for a in self.fx.run.attempts))
            self.fx.pack, self.fx.key = create_blind_review(self.fx.run,
                policy=fixture_support.FictionalReviewPermission(), rng=random.Random(13))
            self.fx.spec = self.fx._spec()
        collection = self.fx._collection()
        for pair in self.fx.pack["pairs"]:
            side = "left" if self.fx.key["pairs"][pair["pair_id"]]["left"] == "flora_full" else "right"
            rating = self.fx._rating(pair, labels={"personal_fit": None if missing else "prefer_" + side,
                "reason_fit": "tie", "needed_change": None, "unrelated_stability": None})
            collection.submit(rating, proof=self.fx.reviewer_key.sign(rating.message()))
        if sealed:
            self.fx._seal(collection)
        return collection

    def _analyze(self, collection, **changes):
        inputs = dict(run=self.fx.run, pack=self.fx.pack, private_key=self.fx.key, collection=collection)
        inputs.update(changes)
        return analyze_sealed_assessment(**inputs)

    def test_exact_scores_orientation_denominator_and_conditional_decision(self):
        report = self._analyze(self._prepare())
        metric = report["metrics"][0]
        self.assertEqual(metric["point"], "1/1")
        self.assertEqual(metric["possible_pairs"], 3)
        self.assertEqual(metric["uncertainty"]["clusters"], 3)
        self.assertEqual((metric["uncertainty"]["lower"], metric["uncertainty"]["upper"]), ("1/1", "1/1"))
        self.assertEqual(metric["per_host"]["fictional-assessment-host"]["point"], "1/1")
        self.assertEqual(report["acceptance_decision"], "accepted_under_supplied_criteria")
        self.assertFalse(report["part1_qualified"])
        self.assertEqual(report["evidence_kind"], "contract_fixture")
        self.assertEqual(report["descriptives"]["acceptance_decision"], "not_evaluated")

    def test_rule_preflight_requires_no_model_run_pack_ratings_or_seal(self):
        content = canonical_json_bytes(self.analysis)
        checked = validate_analysis_spec(threshold_spec=content, rubric=self.fx.rubric)
        self.assertEqual(checked, self.analysis)
        self.analysis["metrics"][0]["criteria"][0]["bound"] = "-99/1"
        self.assertEqual(checked["metrics"][0]["criteria"][0]["bound"], "1/1")
        with self.assertRaisesRegex(ValueError, "exact canonical"):
            validate_analysis_spec(threshold_spec=json.dumps(checked).encode(), rubric=self.fx.rubric)

    def test_excluded_failures_and_missing_labels_stay_in_planned_denominator(self):
        report = self._analyze(self._prepare(failing=True))
        metric = report["metrics"][0]
        self.assertEqual((metric["possible_pairs"], metric["excluded_pairs"], metric["point"]), (3, 1, "1/3"))
        self.assertEqual(metric["cases"][0]["score"], "-1/1")
        self.assertEqual(report["descriptives"]["excluded_comparison_pairs"], 2)
        self.assertEqual(report["acceptance_decision"], "rejected_under_supplied_criteria")
        report = self._analyze(self._prepare(missing=True))
        self.assertEqual(report["metrics"][0]["point"], "0/1")
        self.assertEqual(report["metrics"][0]["per_host"]["fictional-assessment-host"]["unassessed_ratings"], 3)

    def test_one_host_cluster_never_fabricates_confidence_interval(self):
        self.analysis["metrics"][0]["uncertainty"]["cluster_unit"] = "host"
        self.analysis["metrics"][0]["criteria"] = [{"quantity": "lower", "operator": "gt", "bound": "0/1"}]
        report = self._analyze(self._prepare())
        uncertainty = report["metrics"][0]["uncertainty"]
        self.assertEqual(uncertainty["status"], "not_estimable_insufficient_clusters")
        self.assertIsNone(uncertainty["lower"])
        self.assertEqual(report["acceptance_decision"], "not_evaluable")

    def test_empty_declared_stratum_is_not_evaluable(self):
        self.analysis["metrics"][0]["split"] = "pilot"
        report = self._analyze(self._prepare())
        self.assertEqual(report["metrics"][0]["possible_pairs"], 0)
        self.assertIsNone(report["metrics"][0]["point"])
        self.assertEqual(report["acceptance_decision"], "not_evaluable")

    def test_unsealed_tampered_and_changed_preregistration_digest_refused(self):
        collection = self._prepare(sealed=False)
        with self.assertRaisesRegex(ValueError, "before.*sealed"):
            self._analyze(collection)
        self.fx._seal(collection)
        key = deepcopy(self.fx.key)
        key["pairs"][next(iter(key["pairs"]))]["left_output_sha256"] = "f" * 64
        with self.assertRaises(ValueError):
            self._analyze(collection, private_key=key)
        altered = replace(collection.spec, threshold_spec=canonical_json_bytes({"changed": True}))
        collection.spec = altered
        with self.assertRaisesRegex(ValueError, "threshold specification"):
            self._analyze(collection)

    def test_no_default_semantics_missing_mapping_method_or_denominator_refused(self):
        for change in (lambda m: m["label_scores"].pop("tie"),
                       lambda m: m.pop("excluded_pair_score"),
                       lambda m: m["uncertainty"].pop("seed"),
                       lambda m: m.update(denominator="reviewed_pairs_only"),
                       lambda m: m.update(unassessed_score=0),
                       lambda m: m["uncertainty"].update(method="invented_method")):
            with self.subTest(change=change):
                modified = deepcopy(self.analysis)
                change(modified["metrics"][0])
                collection = self._prepare(analysis=modified)
                with self.assertRaises(ValueError):
                    self._analyze(collection)

    def test_actual_explicit_criteria_use_exact_rational_equality(self):
        self.analysis["metrics"][0]["criteria"] = [{"quantity": "point", "operator": "gt", "bound": "1/1"}]
        report = self._analyze(self._prepare())
        self.assertEqual(report["acceptance_decision"], "rejected_under_supplied_criteria")
        self.assertFalse(report["metrics"][0]["criteria"][0]["satisfied"])

    def test_known_linear_quantiles_and_deterministic_cluster_resampling(self):
        values = [Fraction(0), Fraction(1, 3), Fraction(2, 3), Fraction(1)]
        self.assertEqual(_quantile(values, Fraction(1, 4)), Fraction(1, 4))
        self.assertEqual(_quantile(values, Fraction(3, 4)), Fraction(3, 4))
        draws = _ClusterDraws(123)
        self.assertEqual([draws.index(2) for _ in range(8)], [1, 0, 0, 0, 1, 1, 1, 1])
        report1 = self._analyze(self._prepare(failing=True))
        report2 = self._analyze(self._prepare(failing=True))
        self.assertEqual(report1["metrics"], report2["metrics"])

    def test_nonconstant_bootstrap_interval_matches_independent_small_case(self):
        # The fixed draw vector above selects cluster pairs (b,a), (a,a),
        # (b,b), (b,b). Their means are 0,-1,1,1. The sorted sample is
        # -1,0,1,1; linear 1/4 and 3/4 quantiles are -1/4 and 1.
        method = fictional_analysis_spec()["metrics"][0]["uncertainty"]
        method.update(resamples=4, confidence="1/2")
        scores = [{"case_id": "a", "host_id": "first", "score": Fraction(-1)},
                  {"case_id": "b", "host_id": "second", "score": Fraction(1)}]
        result, lower, upper = _bootstrap(scores, method)
        self.assertEqual((lower, upper), (Fraction(-1, 4), Fraction(1)))
        self.assertEqual((result["lower"], result["upper"]), ("-1/4", "1/1"))
        self.assertEqual(result["distribution_sha256"],
            fixture_support.sha(canonical_json_bytes(["0/1", "-1/1", "1/1", "1/1"])))

    def test_multiple_human_reviewers_are_collapsed_before_cluster_sampling(self):
        self._prepare(sealed=False)
        second_key = Ed25519PrivateKey.generate()
        second_public = second_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        second = ApprovedReviewer("fictional-second-rater", fixture_support.sha(second_public), "fictional-second-approval")
        first_public = self.fx.reviewer_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        coordinator_public = self.fx.coordinator_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.fx.authority = Ed25519AssessmentAuthority(
            reviewer_public_keys={self.fx.reviewer.reviewer_id: first_public, second.reviewer_id: second_public},
            coordinator_public_key=coordinator_public,
            reviewer_approvals={self.fx.reviewer.reviewer_id: self.fx.reviewer, second.reviewer_id: second},
            coordinator_approval=self.fx.coordinator)
        self.fx.spec = self.fx._spec(reviewers=(self.fx.reviewer, second),
            assignments=tuple((pair["pair_id"], reviewer.reviewer_id)
                for pair in self.fx.pack["pairs"] for reviewer in (self.fx.reviewer, second)))
        collection = self.fx._collection()
        for pair in self.fx.pack["pairs"]:
            side = "left" if self.fx.key["pairs"][pair["pair_id"]]["left"] == "flora_full" else "right"
            for reviewer, key, preference in ((self.fx.reviewer, self.fx.reviewer_key, side),
                    (second, second_key, "right" if side == "left" else "left")):
                rating = replace(self.fx._rating(pair),
                    rating_id="fictional-rating-" + pair["pair_id"] + "-" + reviewer.reviewer_id,
                    reviewer_id=reviewer.reviewer_id,
                    labels={"personal_fit": "prefer_" + preference, "reason_fit": "tie",
                            "needed_change": None, "unrelated_stability": None})
                collection.submit(rating, proof=key.sign(rating.message()))
        self.fx._seal(collection)
        metric = self._analyze(collection)["metrics"][0]
        self.assertEqual(metric["point"], "0/1")
        self.assertEqual(metric["uncertainty"]["clusters"], 3)
        self.assertEqual(metric["per_host"]["fictional-assessment-host"]["ratings"], 6)

    def test_declared_resource_bounds_are_rejected_without_silently_reducing_work(self):
        self.analysis["metrics"][0]["uncertainty"]["resamples"] = MAX_RESAMPLES + 1
        with self.assertRaisesRegex(ValueError, "implementation limit"):
            self._analyze(self._prepare())
        method = fictional_analysis_spec()["metrics"][0]["uncertainty"]
        method["resamples"] = MAX_RESAMPLES
        scores = [{"case_id": str(i), "host_id": "host", "score": Fraction(1)}
                  for i in range(MAX_CLUSTER_DRAWS // MAX_RESAMPLES + 1)]
        with self.assertRaisesRegex(ValueError, "cluster draws"):
            _bootstrap(scores, method)


if __name__ == "__main__":
    unittest.main()
