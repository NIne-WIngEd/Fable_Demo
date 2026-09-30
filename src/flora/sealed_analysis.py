"""Deterministic analysis of authenticated, sealed human assessments.

The pilot supplies every score, criterion and statistical parameter. This
module applies a supported frozen rule; it does not qualify sampling design,
native producers, a behavioral advantage, or Part1 readiness.
"""

from __future__ import annotations

from fractions import Fraction
import hashlib
import json

from cognitive_kernel.canonical import canonical_json_bytes, require_identifier, require_text
from .blind_assessment import (
    BlindRatingCollection, DIMENSIONS, _validated_private_mapping,
    aggregate_sealed_assessment,
)
from .comparison_run import PairedRun
from .evaluation_protocol import INTERVENTIONS

MAX_METRICS = 64
MAX_RESAMPLES = 100_000
MAX_CLUSTER_DRAWS = 1_000_000
MAX_SEED = (1 << 256) - 1


def _fraction(value: object, label: str) -> Fraction:
    """Canonical rational strings avoid float/rounding-dependent decisions."""
    if not isinstance(value, str) or len(value) > 128:
        raise ValueError(f"{label} must be an explicit canonical rational string")
    try:
        result = Fraction(value)
    except (ValueError, ZeroDivisionError):
        raise ValueError(f"{label} must be an explicit canonical rational string") from None
    if value != _text(result):
        raise ValueError(f"{label} must be an explicit canonical rational string")
    return result


def _text(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def _integer(value: object, label: str, *, minimum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an explicit integer >= {minimum}")


def validate_analysis_spec(*, threshold_spec: bytes, rubric: bytes) -> dict:
    """Validate actual rule/rubric bytes before a held-out run or pack exists.

    The caller freezes these exact bytes' hashes in EvaluationProtocol and its
    durable preregistration. This pure preflight does not create that receipt.
    """
    if not isinstance(threshold_spec, bytes) or not isinstance(rubric, bytes):
        raise ValueError("analysis preflight requires actual supplied specification and rubric bytes")
    content = threshold_spec
    material = json.loads(content)
    if canonical_json_bytes(material) != content:
        raise ValueError("analysis specification must be the exact canonical frozen bytes")
    if (not isinstance(material, dict)
            or set(material) != {"schema", "analysis_id", "metrics", "acceptance_combination"}
            or material["schema"] != "flora-sealed-assessment-analysis-v1"
            or material["acceptance_combination"] != "all_criteria"):
        raise ValueError("unsupported explicit assessment analysis specification")
    require_identifier(material["analysis_id"], "analysis_id")
    if (not isinstance(material["metrics"], list) or not material["metrics"]
            or len(material["metrics"]) > MAX_METRICS):
        raise ValueError("analysis needs explicitly supplied metrics and criteria")
    ids = set()
    rubric_material = json.loads(rubric)
    if (not isinstance(rubric_material, dict) or set(rubric_material) != {"schema", "dimensions"}
            or rubric_material["schema"] != "flora-human-assessment-rubric-v1"
            or not isinstance(rubric_material["dimensions"], dict)
            or set(rubric_material["dimensions"]) != DIMENSIONS):
        raise ValueError("actual rubric must define every separate assessment dimension")
    labels = {}
    for dimension, definition in rubric_material["dimensions"].items():
        if not isinstance(definition, dict) or set(definition) != {"instruction", "labels"}:
            raise ValueError("actual rubric dimension fields changed")
        require_text(definition["instruction"], "rubric instruction", maximum=100_000, allow_newlines=True)
        values = definition["labels"]
        if (not isinstance(values, list) or not values or any(not isinstance(value, str) or not value for value in values)
                or len(set(values)) != len(values)):
            raise ValueError("actual rubric needs explicit distinct human labels")
        labels[dimension] = values
    for metric in material["metrics"]:
        required = {"metric_id", "dimension", "comparator", "phase", "split", "interventions",
                    "label_scores", "unassessed_score", "excluded_pair_score", "uncertainty", "criteria",
                    "denominator", "reviewer_aggregation", "point_weighting"}
        if not isinstance(metric, dict) or set(metric) != required:
            raise ValueError("analysis metric fields are missing or changed")
        require_identifier(metric["metric_id"], "metric_id")
        if metric["metric_id"] in ids:
            raise ValueError("analysis metric ID reused")
        ids.add(metric["metric_id"])
        if (metric["denominator"] != "all_planned_pairs"
                or metric["reviewer_aggregation"] != "equal_reviewers_within_pair"
                or metric["point_weighting"] != "equal_planned_pairs"):
            raise ValueError("unsupported explicit denominator or weighting policy")
        if (metric["dimension"] not in DIMENSIONS
                or metric["comparator"] not in {"general_model_memory", "same_evidence_ablation"}
                or metric["phase"] not in {"before", "after"}
                or metric["split"] not in {"pilot", "heldout"}
                or not isinstance(metric["interventions"], list)
                or not metric["interventions"]
                or len(set(metric["interventions"])) != len(metric["interventions"])
                or not set(metric["interventions"]) <= INTERVENTIONS):
            raise ValueError("analysis metric selector is invalid")
        scores = metric["label_scores"]
        if not isinstance(scores, dict) or set(scores) != set(labels[metric["dimension"]]):
            raise ValueError("every actual rubric label needs its supplied orientation-aware scores")
        for rule in scores.values():
            if not isinstance(rule, dict) or set(rule) != {"left", "right"}:
                raise ValueError("rubric scores need both possible FloRA orientations")
            for score in rule.values():
                _fraction(score, "label score")
        _fraction(metric["unassessed_score"], "unassessed score")
        _fraction(metric["excluded_pair_score"], "excluded pair score")
        method = metric["uncertainty"]
        if (not isinstance(method, dict)
                or set(method) != {"method", "cluster_unit", "confidence", "resamples", "seed",
                                   "minimum_clusters", "sampling_assumptions", "quantile", "resampling"}
                or method["method"] != "cluster_percentile_v1"
                or method["cluster_unit"] not in {"case", "host"}
                or method["quantile"] != "linear_order_statistics_v1"
                or method["resampling"] != "sha256_counter_rejection_v1"):
            raise ValueError("unsupported explicitly supplied uncertainty method")
        confidence = _fraction(method["confidence"], "confidence")
        if not 0 < confidence < 1:
            raise ValueError("confidence must be strictly between zero and one")
        _integer(method["resamples"], "resamples", minimum=2)
        if method["resamples"] > MAX_RESAMPLES:
            raise ValueError("requested resamples exceed the supported implementation limit")
        _integer(method["seed"], "seed", minimum=0)
        if method["seed"] > MAX_SEED:
            raise ValueError("seed exceeds the supported implementation limit")
        _integer(method["minimum_clusters"], "minimum_clusters", minimum=2)
        if method["minimum_clusters"] > MAX_CLUSTER_DRAWS:
            raise ValueError("minimum clusters exceed the supported implementation limit")
        require_text(method["sampling_assumptions"], "sampling assumptions", maximum=100_000,
                     allow_newlines=True)
        if not isinstance(metric["criteria"], list) or not metric["criteria"]:
            raise ValueError("each metric needs explicitly supplied acceptance comparisons")
        for criterion in metric["criteria"]:
            if (not isinstance(criterion, dict) or set(criterion) != {"quantity", "operator", "bound"}
                    or criterion["quantity"] not in {"point", "lower", "upper"}
                    or criterion["operator"] not in {"ge", "le", "gt", "lt"}):
                raise ValueError("unsupported supplied acceptance criterion")
            _fraction(criterion["bound"], "criterion bound")
    return material


class _ClusterDraws:
    """Versioned platform-independent uniform indices, with rejection sampling."""

    def __init__(self, seed: int):
        self.seed, self.counter = seed, 0

    def index(self, bound: int) -> int:
        ceiling = (1 << 256) - ((1 << 256) % bound)
        while True:
            encoded = canonical_json_bytes(["flora-cluster-draw-v1", self.seed, self.counter])
            value = int.from_bytes(hashlib.sha256(encoded).digest(), "big")
            self.counter += 1
            if value < ceiling:
                return value % bound


def _mean(values: list[Fraction]) -> Fraction:
    return sum(values, Fraction()) / len(values)


def _quantile(values: list[Fraction], probability: Fraction) -> Fraction:
    """Linear empirical quantile, exactly specified by method version v1."""
    ordered = sorted(values)
    rank = probability * (len(ordered) - 1)
    left = rank.numerator // rank.denominator
    remainder = rank - left
    right = min(left + 1, len(ordered) - 1)
    return ordered[left] + remainder * (ordered[right] - ordered[left])


def _bootstrap(scores: list[dict], method: dict) -> tuple[dict, Fraction | None, Fraction | None]:
    clusters: dict[str, list[Fraction]] = {}
    for row in scores:
        key = row["case_id"] if method["cluster_unit"] == "case" else row["host_id"]
        clusters.setdefault(key, []).append(row["score"])
    result = {**method, "clusters": len(clusters), "lower": None, "upper": None,
              "sampling_design_qualified": False}
    if len(clusters) < method["minimum_clusters"]:
        return {**result, "status": "not_estimable_insufficient_clusters"}, None, None
    groups = [clusters[key] for key in sorted(clusters)]
    if len(groups) * method["resamples"] > MAX_CLUSTER_DRAWS:
        raise ValueError("requested cluster draws exceed the supported implementation limit")
    rng = _ClusterDraws(method["seed"])
    distribution = []
    for _ in range(method["resamples"]):
        sample = [score for _ in groups for score in groups[rng.index(len(groups))]]
        distribution.append(_mean(sample))
    tail = (1 - _fraction(method["confidence"], "confidence")) / 2
    lower, upper = _quantile(distribution, tail), _quantile(distribution, 1 - tail)
    return {**result, "status": "computed_under_supplied_sampling_assumptions",
            "lower": _text(lower), "upper": _text(upper),
            "distribution_sha256": hashlib.sha256(canonical_json_bytes([_text(x) for x in distribution])).hexdigest()}, lower, upper


def analyze_sealed_assessment(*, run: PairedRun, pack: dict, private_key: dict,
                              collection: BlindRatingCollection) -> dict:
    """Apply explicit protocol-bound criteria after authenticating sealed inputs.

    Every planned case contributes one pair score, including excluded pairs.
    Human reviewers are averaged within a pair, never treated as independent
    experimental units. The declared case/host clustering keeps those paired
    scores together during resampling. No learned or automated judge is used.
    """
    if not collection.sealed:
        raise ValueError("unblinding is forbidden before rating collection is sealed")
    pack = json.loads(canonical_json_bytes(pack))
    private_key = json.loads(canonical_json_bytes(private_key))
    checked = BlindRatingCollection.from_bytes(collection.export_bytes(), spec=collection.spec,
        pack=pack, authority=collection.authority, view_policy=collection.view_policy)
    descriptive = aggregate_sealed_assessment(run=run, pack=pack, private_key=private_key,
                                               collection=checked)
    specification = validate_analysis_spec(threshold_spec=checked.spec.threshold_spec, rubric=checked.spec.rubric)
    identities = _validated_private_mapping(run=run, pack=pack, key=private_key)
    by_pair = {}
    for content in checked._records:
        rating = json.loads(content)["rating"]
        by_pair.setdefault(rating["pair_id"], []).append(rating)
    pair_ids = {}
    for pair_id, identity in identities.items():
        comparator = next(arm for arm in (identity["left"], identity["right"]) if arm != "flora_full")
        pair_ids[(identity["case_id"], identity["phase"], comparator)] = pair_id
    metrics = []
    for metric in specification["metrics"]:
        scores = []
        for case in checked.spec.protocol.cases:
            if case.split != metric["split"] or case.intervention not in metric["interventions"]:
                continue
            pair_id = pair_ids.get((case.case_id, metric["phase"], metric["comparator"]))
            values, unassessed = [], 0
            if pair_id is None:
                score = _fraction(metric["excluded_pair_score"], "excluded pair score")
            else:
                identity = identities[pair_id]
                side = "left" if identity["left"] == "flora_full" else "right"
                for rating in by_pair[pair_id]:
                    label = rating["labels"][metric["dimension"]]
                    if label is None:
                        unassessed += 1
                        values.append(_fraction(metric["unassessed_score"], "unassessed score"))
                    else:
                        values.append(_fraction(metric["label_scores"][label][side], "label score"))
                score = _mean(values)
            scores.append({"case_id": case.case_id, "host_id": case.host_id, "score": score,
                           "excluded": pair_id is None, "ratings": len(values), "unassessed": unassessed})
        point = _mean([row["score"] for row in scores]) if scores else None
        uncertainty, lower, upper = _bootstrap(scores, metric["uncertainty"])
        quantities = {"point": point, "lower": lower, "upper": upper}
        criteria = []
        for rule in metric["criteria"]:
            observed, bound = quantities[rule["quantity"]], _fraction(rule["bound"], "criterion bound")
            comparisons = None if observed is None else {
                "ge": observed >= bound, "le": observed <= bound,
                "gt": observed > bound, "lt": observed < bound}
            criteria.append({**rule, "observed": None if observed is None else _text(observed),
                             "satisfied": None if comparisons is None else comparisons[rule["operator"]]})
        hosts = {}
        for host_id in sorted({row["host_id"] for row in scores}):
            rows = [row for row in scores if row["host_id"] == host_id]
            hosts[host_id] = {"point": _text(_mean([row["score"] for row in rows])),
                "possible_pairs": len(rows), "excluded_pairs": sum(row["excluded"] for row in rows),
                "ratings": sum(row["ratings"] for row in rows),
                "unassessed_ratings": sum(row["unassessed"] for row in rows)}
        metrics.append({"metric_id": metric["metric_id"], "rule": metric,
            "possible_pairs": len(scores), "excluded_pairs": sum(row["excluded"] for row in scores),
            "point": None if point is None else _text(point), "per_host": hosts,
            "cases": [{**row, "score": _text(row["score"])} for row in scores],
            "uncertainty": uncertainty, "criteria": criteria})
    outcomes = [rule["satisfied"] for metric in metrics for rule in metric["criteria"]]
    decision = ("not_evaluable" if None in outcomes else "accepted_under_supplied_criteria"
                if all(outcomes) else "rejected_under_supplied_criteria")
    return {"schema": "flora-sealed-assessment-analysis-report-v1",
        "analysis_id": specification["analysis_id"],
        "analysis_spec_sha256": checked.spec.protocol.threshold_spec_sha256,
        "protocol_sha256": checked.spec.protocol.digest(), "plan_sha256": run.plan.digest(),
        "preregistration_sha256": run.plan.preregistration_sha256,
        "spec_sha256": descriptive["spec_sha256"], "collection_sha256": descriptive["collection_sha256"],
        "evidence_kind": run.plan.evidence_kind, "descriptives": descriptive, "metrics": metrics,
        "acceptance_decision": decision, "part1_qualified": False,
        "interpretation": "arithmetic under supplied frozen human-score rules; sampling design, producer semantics and Part1 remain independently unqualified"}
