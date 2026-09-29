"""Signed human rating collection and post-seal descriptive assessment.

No inference, automated judge, manufactured rating or automatic win decision.
Actual rubric/threshold/case-rubric bytes must match the frozen protocol. The
producer may prepare authorized longitudinal views with the private identity
key; the rating collector receives no key until collection has been sealed.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import json
from threading import RLock
from typing import Mapping, Protocol

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from cognitive_kernel.canonical import (
    canonical_json_bytes, canonical_sha256, normalize_timestamp,
    require_identifier, require_sha256, require_text,
)
from .comparison_run import PairedRun, validate_run
from .evaluation_protocol import EvaluationProtocol

DIMENSIONS = frozenset({"personal_fit", "reason_fit", "needed_change", "unrelated_stability"})
LONGITUDINAL = frozenset({"needed_change", "unrelated_stability"})


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _exact_identifier(value: str, name: str) -> None:
    if require_identifier(value, name) != value:
        raise ValueError(f"{name} must be canonical")


def _timestamp(value: str, name: str) -> None:
    if normalize_timestamp(value, name) != value:
        raise ValueError(f"{name} must be canonical UTC time")


def _pack_bytes(pack: dict) -> bytes:
    # Match comparison_run.create_blind_review's existing serialization,
    # including escaped non-ASCII text. Other records use kernel canonical JSON.
    return json.dumps(pack, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _pairs(pack: dict) -> dict[str, dict]:
    if set(pack) != {"schema", "pairs"} or pack["schema"] != "flora-blind-review-v1":
        raise ValueError("unknown or unblinded review pack")
    if not isinstance(pack["pairs"], list):
        raise ValueError("review pairs must be a list")
    result = {}
    for pair in pack["pairs"]:
        if set(pair) != {"pair_id", "question", "left", "right"}:
            raise ValueError("review pair contains unblinded metadata or changed fields")
        _exact_identifier(pair["pair_id"], "pair_id")
        if pair["pair_id"] in result:
            raise ValueError("review pair ID reused")
        for name in ("question", "left", "right"):
            if not isinstance(pair[name], str) or not pair[name]:
                raise ValueError("review pair lacks actual question/output text")
            pair[name].encode("utf-8")
        result[pair["pair_id"]] = pair
    return result


def pair_binding_sha256(pair: dict) -> str:
    return canonical_sha256({"pair_id": pair["pair_id"],
        "question_sha256": _sha(pair["question"].encode()),
        "left_output_sha256": _sha(pair["left"].encode()),
        "right_output_sha256": _sha(pair["right"].encode())})


@dataclass(frozen=True)
class ApprovedReviewer:
    reviewer_id: str
    credential_sha256: str
    authorization_ref: str

    def record(self) -> dict:
        _exact_identifier(self.reviewer_id, "reviewer_id")
        _exact_identifier(self.authorization_ref, "authorization_ref")
        if require_sha256(self.credential_sha256, "credential_sha256") != self.credential_sha256:
            raise ValueError("reviewer credential digest is not canonical")
        return vars(self).copy()


@dataclass(frozen=True)
class LongitudinalReviewView:
    """Anonymous A/B stay fixed across actual before and after outputs.

    A is the after pair's left side, B its right side. The producer orders the
    before outputs using the private key. Constant identity and intervention
    binding are checked after collection sealing, before any report is made.
    """

    view_id: str
    dimension: str
    before_pair_id: str
    after_pair_id: str
    question: str = field(repr=False)
    intervention_context: str = field(repr=False)
    anonymous_a_before: str = field(repr=False)
    anonymous_a_after: str = field(repr=False)
    anonymous_b_before: str = field(repr=False)
    anonymous_b_after: str = field(repr=False)
    intervention_event_id: str

    def record(self) -> dict:
        for name in ("view_id", "before_pair_id", "after_pair_id", "intervention_event_id"):
            _exact_identifier(getattr(self, name), name)
        if self.dimension not in LONGITUDINAL or self.before_pair_id == self.after_pair_id:
            raise ValueError("invalid longitudinal view dimension or phase pair")
        for name in ("question", "intervention_context", "anonymous_a_before", "anonymous_a_after",
                     "anonymous_b_before", "anonymous_b_after"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError("longitudinal view lacks actual authorized content")
        return {"schema": "flora-longitudinal-review-view-v1", **vars(self)}

    def digest(self) -> str:
        return canonical_sha256(self.record())

    def review_record(self) -> dict:
        """Authorized reviewer content; original event lineage stays private."""
        record = self.record()
        return {name: value for name, value in record.items() if name != "intervention_event_id"} | {
            "schema": "flora-anonymous-longitudinal-review-v1"}


@dataclass(frozen=True)
class VerifiedViewAuthorization:
    view_sha256: str
    review_pack_sha256: str
    plan_sha256: str
    authorization_ref: str
    proof_sha256: str

    def record(self) -> dict:
        for name in ("view_sha256", "review_pack_sha256", "plan_sha256", "proof_sha256"):
            if require_sha256(getattr(self, name), name) != getattr(self, name):
                raise ValueError("view authorization digest is not canonical")
        _exact_identifier(self.authorization_ref, "authorization_ref")
        return vars(self).copy()


class LongitudinalViewAuthorization(Protocol):
    """Trusted source/view permission authority, independent of submitted ratings."""

    def verify_view(self, *, view: LongitudinalReviewView, review_pack_sha256: str,
                    plan_sha256: str) -> VerifiedViewAuthorization: ...


@dataclass(frozen=True)
class FrozenAssessmentSpec:
    collection_id: str
    protocol: EvaluationProtocol
    plan_sha256: str
    review_pack_sha256: str
    frozen_at: str
    rubric: bytes = field(repr=False)
    threshold_spec: bytes = field(repr=False)
    case_rubrics: tuple[tuple[str, bytes], ...] = field(repr=False)
    reviewers: tuple[ApprovedReviewer, ...]
    coordinator: ApprovedReviewer
    assignments: tuple[tuple[str, str], ...]
    views: tuple[tuple[LongitudinalReviewView, VerifiedViewAuthorization], ...] = field(default=(), repr=False)

    def _labels(self) -> dict[str, tuple[str, ...]]:
        rubric = json.loads(self.rubric)
        if (set(rubric) != {"schema", "dimensions"}
                or rubric["schema"] != "flora-human-assessment-rubric-v1"
                or set(rubric["dimensions"]) != DIMENSIONS):
            raise ValueError("actual rubric must define each separate assessment dimension")
        labels = {}
        for dimension, rule in rubric["dimensions"].items():
            if set(rule) != {"instruction", "labels"}:
                raise ValueError("rubric dimension fields changed")
            require_text(rule["instruction"], "rubric instruction", maximum=100_000, allow_newlines=True)
            values = rule["labels"]
            if (not isinstance(values, list) or not values or len(set(values)) != len(values)
                    or any(not isinstance(label, str) or not label for label in values)):
                raise ValueError("rubric must supply actual distinct human labels")
            labels[dimension] = tuple(values)
        return labels

    def validate(self, pack: dict, *, view_policy: LongitudinalViewAuthorization | None = None) -> None:
        self.protocol.validate()
        for name in ("response_token_budget", "wall_time_budget_ms"):
            value = getattr(self.protocol, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError("assessment protocol budget must be an actual positive integer")
        normalize_timestamp(self.protocol.frozen_at, "protocol frozen_at")
        _exact_identifier(self.collection_id, "collection_id")
        _timestamp(self.frozen_at, "frozen_at")
        require_sha256(self.plan_sha256, "plan_sha256")
        if _sha(_pack_bytes(pack)) != self.review_pack_sha256:
            raise ValueError("actual review pack differs from frozen assessment")
        pairs = _pairs(pack)
        if (not isinstance(self.rubric, bytes) or not isinstance(self.threshold_spec, bytes)
                or _sha(self.rubric) != self.protocol.scoring_rubric_sha256
                or _sha(self.threshold_spec) != self.protocol.threshold_spec_sha256):
            raise ValueError("actual scoring rubric or threshold specification differs from protocol")
        self._labels()
        if not isinstance(json.loads(self.threshold_spec), dict) or not json.loads(self.threshold_spec):
            raise ValueError("actual threshold specification is missing")
        actual_cases = dict(self.case_rubrics)
        if len(actual_cases) != len(self.case_rubrics) or set(actual_cases) != {c.case_id for c in self.protocol.cases}:
            raise ValueError("sealed case rubric matrix is incomplete or duplicated")
        for case in self.protocol.cases:
            material = actual_cases[case.case_id]
            if not isinstance(material, bytes) or not material or _sha(material) != case.sealed_rubric_sha256:
                raise ValueError("actual sealed case rubric differs from frozen protocol")
        reviewers = {reviewer.reviewer_id: reviewer for reviewer in self.reviewers}
        if (not reviewers or len(reviewers) != len(self.reviewers)
                or len({r.credential_sha256 for r in self.reviewers}) != len(self.reviewers)):
            raise ValueError("assessment needs distinct approved reviewers")
        for reviewer in (*self.reviewers, self.coordinator):
            reviewer.record()
        if (self.coordinator.reviewer_id in reviewers
                or self.coordinator.credential_sha256 in {r.credential_sha256 for r in self.reviewers}):
            raise ValueError("collection coordinator must use a separate approved identity and credential")
        if (len(set(self.assignments)) != len(self.assignments)
                or {pair_id for pair_id, _ in self.assignments} != set(pairs)
                or any(pair_id not in pairs or reviewer not in reviewers for pair_id, reviewer in self.assignments)):
            raise ValueError("frozen reviewer assignment matrix is incomplete or unknown")
        seen = set()
        for view, authorization in self.views:
            view.record()
            binding = (view.after_pair_id, view.dimension)
            if binding in seen or view.before_pair_id not in pairs or view.after_pair_id not in pairs:
                raise ValueError("longitudinal view pair or dimension is reused or unknown")
            seen.add(binding)
            before, after = pairs[view.before_pair_id], pairs[view.after_pair_id]
            if (before["question"] != view.question or after["question"] != view.question
                    or after["left"] != view.anonymous_a_after or after["right"] != view.anonymous_b_after
                    or sorted((before["left"], before["right"])) !=
                       sorted((view.anonymous_a_before, view.anonymous_b_before))):
                raise ValueError("longitudinal view differs from actual pair output bytes")
            authorization.record()
            if (authorization.view_sha256 != view.digest()
                    or authorization.review_pack_sha256 != self.review_pack_sha256
                    or authorization.plan_sha256 != self.plan_sha256 or view_policy is None
                    or view_policy.verify_view(view=view, review_pack_sha256=self.review_pack_sha256,
                        plan_sha256=self.plan_sha256) != authorization):
                raise PermissionError("longitudinal review view lacks independent current authorization")

    def record(self) -> dict:
        return {"schema": "flora-frozen-human-assessment-v1", "collection_id": self.collection_id,
            "protocol_sha256": self.protocol.digest(), "plan_sha256": self.plan_sha256,
            "review_pack_sha256": self.review_pack_sha256, "frozen_at": self.frozen_at,
            "rubric_sha256": _sha(self.rubric), "threshold_spec_sha256": _sha(self.threshold_spec),
            "case_rubrics": [[case_id, _sha(value)] for case_id, value in self.case_rubrics],
            "reviewers": [r.record() for r in self.reviewers], "coordinator": self.coordinator.record(),
            "assignments": [list(value) for value in self.assignments],
            "views": [{"view_sha256": view.digest(), "after_pair_id": view.after_pair_id,
                       "dimension": view.dimension, "authorization": auth.record()} for view, auth in self.views]}

    def digest(self) -> str:
        return canonical_sha256(self.record())


def freeze_assessment_spec(*, run: PairedRun, pack: dict, collection_id: str, frozen_at: str,
        rubric: bytes, threshold_spec: bytes, case_rubrics: Mapping[str, bytes],
        reviewers: tuple[ApprovedReviewer, ...], coordinator: ApprovedReviewer,
        assignments: tuple[tuple[str, str], ...],
        views: tuple[LongitudinalReviewView, ...] = (),
        view_policy: LongitudinalViewAuthorization | None = None) -> FrozenAssessmentSpec:
    validate_run(run)
    pack_sha = _sha(_pack_bytes(pack))
    authorized = []
    for view in views:
        if view_policy is None:
            raise PermissionError("longitudinal views require independent authorization")
        auth = view_policy.verify_view(view=view, review_pack_sha256=pack_sha,
            plan_sha256=run.plan.digest())
        if not isinstance(auth, VerifiedViewAuthorization):
            raise TypeError("view authority returned no verified authorization")
        authorized.append((view, auth))
    spec = FrozenAssessmentSpec(collection_id, run.plan.protocol, run.plan.digest(), pack_sha,
        frozen_at, rubric, threshold_spec, tuple(sorted(case_rubrics.items())), reviewers,
        coordinator, assignments, tuple(authorized))
    spec.validate(pack, view_policy=view_policy)
    return spec


@dataclass(frozen=True)
class HumanRating:
    rating_id: str
    collection_id: str
    spec_sha256: str
    reviewer_id: str
    pair_id: str
    pair_binding_sha256: str
    submitted_at: str
    labels: Mapping[str, str | None]
    notes: Mapping[str, str] = field(default_factory=dict, repr=False)

    def record(self) -> dict:
        labels, notes = dict(self.labels), dict(self.notes)
        for name in ("rating_id", "collection_id", "reviewer_id", "pair_id"):
            _exact_identifier(getattr(self, name), name)
        for name in ("spec_sha256", "pair_binding_sha256"):
            if require_sha256(getattr(self, name), name) != getattr(self, name):
                raise ValueError("rating digest is not canonical")
        _timestamp(self.submitted_at, "submitted_at")
        if set(labels) != DIMENSIONS or set(notes) - DIMENSIONS:
            raise ValueError("human rating must retain every separate dimension")
        if any(value is not None and not isinstance(value, str) for value in labels.values()):
            raise ValueError("human labels must be text or explicit unassessed null")
        for note in notes.values():
            require_text(note, "rating note", maximum=100_000, allow_newlines=True)
        return {"schema": "flora-human-rating-v1", **{name: getattr(self, name)
            for name in self.__dataclass_fields__ if name not in {"labels", "notes"}},
            "labels": labels, "notes": notes}

    def message(self) -> bytes:
        return canonical_json_bytes(self.record())


class AssessmentSignatureAuthority(Protocol):
    def verify_rating(self, *, reviewer: ApprovedReviewer, message: bytes, proof: bytes) -> None: ...
    def verify_seal(self, *, coordinator: ApprovedReviewer, message: bytes, proof: bytes) -> None: ...


class Ed25519AssessmentAuthority:
    """Public keys come from independently trusted reviewer/coordinator setup."""

    def __init__(self, *, reviewer_public_keys: Mapping[str, bytes], coordinator_public_key: bytes,
                 reviewer_approvals: Mapping[str, ApprovedReviewer], coordinator_approval: ApprovedReviewer):
        self._reviewers = dict(reviewer_public_keys)
        self._coordinator = coordinator_public_key
        self._approvals = dict(reviewer_approvals)
        self._coordinator_approval = coordinator_approval

    @staticmethod
    def _verify(approval: ApprovedReviewer, key: bytes, message: bytes, proof: bytes) -> None:
        approval.record()
        if not isinstance(key, bytes) or _sha(key) != approval.credential_sha256:
            raise PermissionError("trusted credential differs from frozen reviewer approval")
        if not isinstance(proof, bytes) or len(proof) != 64:
            raise ValueError("a real Ed25519 signature is required")
        Ed25519PublicKey.from_public_bytes(key).verify(proof, message)

    def verify_rating(self, *, reviewer, message, proof) -> None:
        key = self._reviewers.get(reviewer.reviewer_id)
        if key is None or self._approvals.get(reviewer.reviewer_id) != reviewer:
            raise PermissionError("reviewer has no independently configured credential")
        self._verify(reviewer, key, message, proof)

    def verify_seal(self, *, coordinator, message, proof) -> None:
        if coordinator != self._coordinator_approval:
            raise PermissionError("coordinator has no independently configured seal approval")
        self._verify(coordinator, self._coordinator, message, proof)


class BlindRatingCollection:
    """Append-only signed records. Private identity key is never an intake input."""

    def __init__(self, *, spec: FrozenAssessmentSpec, pack: dict,
                 authority: AssessmentSignatureAuthority,
                 view_policy: LongitudinalViewAuthorization | None = None):
        spec.validate(pack, view_policy=view_policy)
        self.spec, self.authority, self.view_policy = spec, authority, view_policy
        self._spec_sha = spec.digest()
        self._pack_bytes = _pack_bytes(pack)
        self._records: list[bytes] = []
        self._seal: dict | None = None
        self._lock = RLock()

    @property
    def sealed(self) -> bool:
        return self._seal is not None

    def _check(self) -> dict:
        pack = json.loads(self._pack_bytes)
        self.spec.validate(pack, view_policy=self.view_policy)
        if self.spec.digest() != self._spec_sha:
            raise ValueError("frozen assessment specification changed")
        return _pairs(pack)

    def submit(self, rating: HumanRating, *, proof: bytes) -> None:
        with self._lock:
            self._submit(rating, proof=proof)

    def _submit(self, rating: HumanRating, *, proof: bytes) -> None:
        if self.sealed:
            raise ValueError("sealed ratings cannot be changed or appended")
        pairs = self._check()
        record = rating.record()
        if (rating.collection_id != self.spec.collection_id or rating.spec_sha256 != self._spec_sha
                or (rating.pair_id, rating.reviewer_id) not in self.spec.assignments
                or rating.pair_binding_sha256 != pair_binding_sha256(pairs[rating.pair_id])
                or rating.submitted_at < self.spec.frozen_at):
            raise ValueError("rating differs from frozen pair/credential assignment or time")
        prior = [json.loads(value)["rating"] for value in self._records]
        if any(value["rating_id"] == rating.rating_id or
               (value["pair_id"], value["reviewer_id"]) == (rating.pair_id, rating.reviewer_id) for value in prior):
            raise ValueError("rating identity or assignment is immutable")
        labels = self.spec._labels()
        available = {(view.after_pair_id, view.dimension) for view, _ in self.spec.views}
        for dimension, label in record["labels"].items():
            if label is not None and label not in labels[dimension]:
                raise ValueError("human label is absent from actual frozen rubric")
            if dimension in LONGITUDINAL and label is not None and (rating.pair_id, dimension) not in available:
                raise ValueError("single-phase preferences cannot rate longitudinal behavior")
        reviewer = next(r for r in self.spec.reviewers if r.reviewer_id == rating.reviewer_id)
        message = canonical_json_bytes(record)
        self.authority.verify_rating(reviewer=reviewer, message=message, proof=proof)
        # Store a canonical copy, not references to caller-owned mutable maps.
        self._records.append(canonical_json_bytes({"rating": record,
            "reviewer_approval": reviewer.record(), "proof_base64": base64.b64encode(proof).decode(),
            "proof_sha256": _sha(proof)}))

    def seal_message(self, *, sealed_at: str) -> bytes:
        with self._lock:
            return self._seal_message(sealed_at=sealed_at)

    def _seal_message(self, *, sealed_at: str) -> bytes:
        self._check()
        _timestamp(sealed_at, "sealed_at")
        records = [json.loads(value) for value in self._records]
        assignments = {(r["rating"]["pair_id"], r["rating"]["reviewer_id"]) for r in records}
        if assignments != set(self.spec.assignments) or len(records) != len(self.spec.assignments):
            raise ValueError("rating collection is incomplete")
        if sealed_at < self.spec.frozen_at or any(r["rating"]["submitted_at"] > sealed_at for r in records):
            raise ValueError("collection seal time precedes a frozen input or rating")
        return canonical_json_bytes({"schema": "flora-blind-rating-seal-v1",
            "collection_id": self.spec.collection_id, "spec_sha256": self._spec_sha,
            "review_pack_sha256": self.spec.review_pack_sha256, "sealed_at": sealed_at,
            "rating_count": len(records), "ratings_sha256": canonical_sha256(records)})

    def seal(self, *, sealed_at: str, proof: bytes) -> None:
        with self._lock:
            self._seal_collection(sealed_at=sealed_at, proof=proof)

    def _seal_collection(self, *, sealed_at: str, proof: bytes) -> None:
        if self.sealed:
            raise ValueError("rating collection is already sealed")
        message = self.seal_message(sealed_at=sealed_at)
        self.authority.verify_seal(coordinator=self.spec.coordinator, message=message, proof=proof)
        self._seal = {"message": json.loads(message), "coordinator_approval": self.spec.coordinator.record(),
                      "proof_base64": base64.b64encode(proof).decode(), "proof_sha256": _sha(proof)}

    def export_bytes(self) -> bytes:
        with self._lock:
            return self._export_bytes()

    def _export_bytes(self) -> bytes:
        self._check()
        return canonical_json_bytes({"schema": "flora-blind-rating-collection-v1",
            "spec_sha256": self._spec_sha, "review_pack_sha256": self.spec.review_pack_sha256,
            "records": [json.loads(value) for value in self._records], "seal": self._seal})

    @classmethod
    def from_bytes(cls, value: bytes, *, spec: FrozenAssessmentSpec, pack: dict,
                   authority: AssessmentSignatureAuthority,
                   view_policy: LongitudinalViewAuthorization | None = None) -> "BlindRatingCollection":
        data = json.loads(value)
        if (set(data) != {"schema", "spec_sha256", "review_pack_sha256", "records", "seal"}
                or data["schema"] != "flora-blind-rating-collection-v1"
                or data["spec_sha256"] != spec.digest() or data["review_pack_sha256"] != spec.review_pack_sha256):
            raise ValueError("stored assessment format or frozen references changed")
        collection = cls(spec=spec, pack=pack, authority=authority, view_policy=view_policy)
        for record in data["records"]:
            if set(record) != {"rating", "reviewer_approval", "proof_base64", "proof_sha256"}:
                raise ValueError("stored rating/authentication record changed")
            fields = dict(record["rating"])
            if fields.pop("schema") != "flora-human-rating-v1" or set(fields) != set(HumanRating.__dataclass_fields__):
                raise ValueError("stored rating fields changed")
            rating = HumanRating(**fields)
            proof = base64.b64decode(record["proof_base64"], validate=True)
            collection.submit(rating, proof=proof)
            if json.loads(collection._records[-1]) != record:
                raise ValueError("stored rating provenance changed")
        seal = data["seal"]
        if seal is not None:
            if set(seal) != {"message", "coordinator_approval", "proof_base64", "proof_sha256"}:
                raise ValueError("stored collection seal changed")
            collection.seal(sealed_at=seal["message"]["sealed_at"],
                proof=base64.b64decode(seal["proof_base64"], validate=True))
            if collection._seal != seal:
                raise ValueError("stored collection seal provenance changed")
        return collection


def _validated_private_mapping(*, run: PairedRun, pack: dict, key: dict) -> dict:
    validate_run(run)
    if (set(key) != {"schema", "plan_sha256", "pairs", "excluded_pairs", "public_pack_sha256"}
            or key["schema"] != "flora-blind-review-key-v1" or key["plan_sha256"] != run.plan.digest()
            or key["public_pack_sha256"] != _sha(_pack_bytes(pack))):
        raise ValueError("private review key does not bind actual frozen run and pack")
    pairs = _pairs(pack)
    if set(key["pairs"]) != set(pairs):
        raise ValueError("private key omits or adds reviewed pairs")
    attempts = {(a.case_id, a.phase, a.arm): a for a in run.attempts}
    expected = set()
    excluded = 0
    for case in run.plan.protocol.cases:
        for phase in ("before", "after"):
            full = attempts[(case.case_id, phase, "flora_full")]
            for other in ("general_model_memory", "same_evidence_ablation"):
                baseline = attempts[(case.case_id, phase, other)]
                if full.status == baseline.status == "success":
                    expected.add((case.case_id, phase, other))
                else:
                    excluded += 1
    observed = set()
    for pair_id, identity in key["pairs"].items():
        if set(identity) != {"case_id", "host_id", "phase", "left", "right", "left_output_sha256", "right_output_sha256"}:
            raise ValueError("private pair identity fields changed")
        arms = {identity["left"], identity["right"]}
        if len(arms) != 2 or "flora_full" not in arms or not arms <= {"flora_full", "general_model_memory", "same_evidence_ablation"}:
            raise ValueError("private pair has incorrect comparison arms")
        other = next(arm for arm in arms if arm != "flora_full")
        group = (identity["case_id"], identity["phase"], other)
        if group not in expected or group in observed:
            raise ValueError("private key comparison matrix changed")
        observed.add(group)
        for side in ("left", "right"):
            attempt = attempts[(identity["case_id"], identity["phase"], identity[side])]
            if (attempt.host_id != identity["host_id"] or attempt.output_sha256 != identity[f"{side}_output_sha256"]
                    or _sha(pairs[pair_id][side].encode()) != attempt.output_sha256):
                raise ValueError("reviewed output differs from actual run receipt")
        if pairs[pair_id]["question"].encode() != run.questions[identity["case_id"]]:
            raise ValueError("reviewed question differs from actual run")
    if (observed != expected or isinstance(key["excluded_pairs"], bool)
            or not isinstance(key["excluded_pairs"], int) or key["excluded_pairs"] != excluded):
        raise ValueError("review key lost failure-inclusive comparisons")
    return key["pairs"]


def aggregate_sealed_assessment(*, run: PairedRun, pack: dict, private_key: dict,
                                collection: BlindRatingCollection) -> dict:
    """Post-seal descriptive labels and full denominators, never a win rule."""
    if not collection.sealed:
        raise ValueError("unblinding is forbidden before rating collection is sealed")
    pack = json.loads(_pack_bytes(pack))
    private_key = json.loads(canonical_json_bytes(private_key))
    # Reparse and verify every original signature and the independent seal.
    checked = BlindRatingCollection.from_bytes(collection.export_bytes(), spec=collection.spec,
        pack=pack, authority=collection.authority, view_policy=collection.view_policy)
    spec = checked.spec
    if spec.protocol.digest() != run.plan.protocol.digest() or spec.plan_sha256 != run.plan.digest():
        raise ValueError("assessment differs from actual complete evaluation protocol")
    identities = _validated_private_mapping(run=run, pack=pack, key=private_key)
    cases = {case.case_id: case for case in spec.protocol.cases}
    for view, _ in spec.views:
        before, after = identities[view.before_pair_id], identities[view.after_pair_id]
        before_pair = _pairs(pack)[view.before_pair_id]
        possible_a = {before[side] for side in ("left", "right")
                      if before_pair[side] == view.anonymous_a_before}
        possible_b = {before[side] for side in ("left", "right")
                      if before_pair[side] == view.anonymous_b_before}
        case = cases[after["case_id"]]
        if (before["case_id"] != after["case_id"] or before["host_id"] != after["host_id"]
                or before["phase"] != "before" or after["phase"] != "after"
                or after["left"] not in possible_a or after["right"] not in possible_b
                or {before["left"], before["right"]} != {after["left"], after["right"]}
                or view.intervention_event_id != case.intervention_event_id
                or (view.dimension == "unrelated_stability" and case.intervention != "irrelevant_correction")
                or (view.dimension == "needed_change" and case.intervention == "irrelevant_correction")):
            raise ValueError("longitudinal view changes anonymous arm identity, phase or intervention")
    def empty_group() -> dict:
        return {"possible_comparison_pairs": 0, "reviewed_pairs": 0, "excluded_pairs": 0,
            "excluded_pair_statuses": {}, "ratings": 0,
            "dimensions": {dim: {"assessed_ratings": 0, "unassessed_ratings": 0,
                "labels_by_flora_side": {"left": {}, "right": {}}} for dim in sorted(DIMENSIONS)}}

    groups = {}
    by_attempt = {(a.case_id, a.phase, a.arm): a for a in run.attempts}
    for case in spec.protocol.cases:
        for phase in ("before", "after"):
            full = by_attempt[(case.case_id, phase, "flora_full")]
            for comparator in ("general_model_memory", "same_evidence_ablation"):
                other = by_attempt[(case.case_id, phase, comparator)]
                group_id = f"{case.split}/{case.host_id}/{comparator}/{phase}/{case.intervention}"
                group = groups.setdefault(group_id, empty_group())
                group["possible_comparison_pairs"] += 1
                if full.status == other.status == "success":
                    group["reviewed_pairs"] += 1
                else:
                    group["excluded_pairs"] += 1
                    for role, attempt in (("flora_full", full), (comparator, other)):
                        if attempt.status != "success":
                            status_key = f"{role}/{attempt.status}"
                            statuses = group["excluded_pair_statuses"]
                            statuses[status_key] = statuses.get(status_key, 0) + 1
    for record_bytes in checked._records:
        rating = json.loads(record_bytes)["rating"]
        identity = identities[rating["pair_id"]]
        case = cases[identity["case_id"]]
        comparator = next(arm for arm in (identity["left"], identity["right"]) if arm != "flora_full")
        group_id = f"{case.split}/{identity['host_id']}/{comparator}/{identity['phase']}/{case.intervention}"
        group = groups[group_id]
        group["ratings"] += 1
        flora_side = "left" if identity["left"] == "flora_full" else "right"
        for dimension, label in rating["labels"].items():
            counts = group["dimensions"][dimension]
            if label is None:
                counts["unassessed_ratings"] += 1
            else:
                counts["assessed_ratings"] += 1
                labels = counts["labels_by_flora_side"][flora_side]
                labels[label] = labels.get(label, 0) + 1
    attempts = {}
    for attempt in run.attempts:
        case = cases[attempt.case_id]
        group_id = f"{case.split}/{attempt.host_id}/{attempt.arm}/{attempt.phase}/{case.intervention}"
        group = attempts.setdefault(group_id, {"attempts": 0, "statuses": {}})
        group["attempts"] += 1
        group["statuses"][attempt.status] = group["statuses"].get(attempt.status, 0) + 1
    return {"schema": "flora-human-assessment-descriptives-v1", "spec_sha256": spec.digest(),
        "collection_sha256": _sha(checked.export_bytes()), "plan_sha256": run.plan.digest(),
        "evidence_kind": run.plan.evidence_kind, "attempt_groups": attempts,
        "total_attempts": len(run.attempts), "possible_comparison_pairs": len(spec.protocol.cases) * 4,
        "reviewed_comparison_pairs": len(identities), "excluded_comparison_pairs": private_key["excluded_pairs"],
        "rating_groups": groups, "threshold_spec_sha256": spec.protocol.threshold_spec_sha256,
        "acceptance_decision": "not_evaluated", "uncertainty_estimation": "not_computed",
        "interpretation": "human categorical descriptions; no inferred advantage or customer benefit"}
