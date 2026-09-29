"""Human-rating contract fixtures, not behavioral or selected-backend results."""

from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import random
from threading import Barrier
import time
import unittest

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from cognitive_kernel.canonical import canonical_json_bytes
from flora.blind_assessment import (
    ApprovedReviewer, BlindRatingCollection, DIMENSIONS, Ed25519AssessmentAuthority,
    HumanRating, LongitudinalReviewView, VerifiedViewAuthorization,
    aggregate_sealed_assessment, freeze_assessment_spec, pair_binding_sha256,
)
from flora.comparison_run import (
    ArmBinding, MeasuredUsage, PairedRun, PairedRunPlan, RunAttempt, create_blind_review,
)
from flora.evaluation_protocol import ARMS, EvaluationCase, EvaluationProtocol


def sha(value):
    return hashlib.sha256(value).hexdigest()


def run_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


class FictionalReviewPermission:
    def allow_review(self, **_):
        return True

    def allow_question(self, **_):
        return True


class FictionalViewPermission:
    """Fixture-owned authorizations; no actual host permission claim."""

    def __init__(self, views):
        self.allowed = {view.digest() for view in views}

    def verify_view(self, *, view, review_pack_sha256, plan_sha256):
        if view.digest() not in self.allowed:
            raise PermissionError("fictional view authorization withdrawn")
        return VerifiedViewAuthorization(view.digest(), review_pack_sha256, plan_sha256,
            "fictional-authorized-longitudinal-view", sha(b"fictional independently approved view receipt"))


class BlindAssessmentContractTest(unittest.TestCase):
    def setUp(self):
        self.rubric = canonical_json_bytes({"schema": "flora-human-assessment-rubric-v1",
            "dimensions": {dim: {"instruction": f"Fictional human instruction for {dim}",
                "labels": ["prefer_left", "prefer_right", "tie"]} for dim in sorted(DIMENSIONS)}})
        self.threshold = canonical_json_bytes({"fixture_only": True, "no_actual_acceptance_rule": True})
        self.case_rubrics = {f"fixture-case-{i}": f"fictional sealed case expectation {i}".encode() for i in range(3)}
        self.cases = tuple(EvaluationCase(f"fixture-case-{i}", "fictional-assessment-host",
            intervention, "heldout", sha(f"before-history-{i}".encode()), sha(f"after-history-{i}".encode()),
            sha(self.case_rubrics[f"fixture-case-{i}"]), f"fictional-intervention-{i}")
            for i, intervention in enumerate(("relevant_correction", "irrelevant_correction", "observed_outcome")))
        protocol = EvaluationProtocol("fictional-assessment-protocol", "a" * 64, "2026-09-29T09:00:00Z",
            "fictional-feature-engine", 100, 1000, self.cases, "b" * 64, sha(self.rubric),
            sha(self.threshold), "d" * 64, ("fictional-transfer-host",))
        self.questions = {case.case_id: f"Fictional question {case.case_id}?".encode() for case in self.cases}
        bindings = {arm: ArmBinding(f"fictional-{arm}", sha(arm.encode()), sha(f"lineage-{arm}".encode()),
            "fictional declared update") for arm in ARMS}
        plan = PairedRunPlan(protocol, bindings, 100, 10000, 1,
            {case: sha(question) for case, question in self.questions.items()})
        attempts = []
        for case in self.cases:
            for phase in ("before", "after"):
                history = getattr(case, f"{phase}_history_sha256")
                common = sha(run_bytes({"history_sha256": history,
                                       "question_sha256": sha(self.questions[case.case_id])}))
                originals = ("fictional-original",) if phase == "before" else ("fictional-original", case.intervention_event_id)
                for arm in sorted(ARMS):
                    output = f"Réponse fictional {case.case_id}/{phase}/{arm}".encode()
                    attempts.append(RunAttempt(case.case_id, case.host_id, arm, phase, plan.digest(), history,
                        originals, common, "e" * 64, "success", 20,
                        MeasuredUsage(protocol.feature_engine_id, 1, 2, 3, 1), sha(output),
                        f"fictional-decision-{case.case_id}-{phase}-{arm}", bindings[arm].lineage_sha256, output))
        self.run = PairedRun(plan, tuple(attempts), self.questions)
        self.pack, self.key = create_blind_review(self.run, policy=FictionalReviewPermission(), rng=random.Random(13))
        self.reviewer_key, self.coordinator_key = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
        reviewer_public = self.reviewer_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        coordinator_public = self.coordinator_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.reviewer = ApprovedReviewer("fictional-human-rater", sha(reviewer_public), "fictional-rater-approval")
        self.coordinator = ApprovedReviewer("fictional-collection-coordinator", sha(coordinator_public), "fictional-seal-approval")
        self.authority = Ed25519AssessmentAuthority(reviewer_public_keys={self.reviewer.reviewer_id: reviewer_public},
            coordinator_public_key=coordinator_public, reviewer_approvals={self.reviewer.reviewer_id: self.reviewer},
            coordinator_approval=self.coordinator)
        self.spec = self._spec()

    def _spec(self, *, run=None, pack=None, views=(), policy=None, **changes):
        fields = dict(run=run or self.run, pack=pack or self.pack, collection_id="fictional-rating-collection",
            frozen_at="2026-09-29T10:00:00.000000Z", rubric=self.rubric, threshold_spec=self.threshold,
            case_rubrics=self.case_rubrics, reviewers=(self.reviewer,), coordinator=self.coordinator,
            assignments=tuple((pair["pair_id"], self.reviewer.reviewer_id) for pair in (pack or self.pack)["pairs"]),
            views=views, view_policy=policy)
        fields.update(changes)
        return freeze_assessment_spec(**fields)

    def _collection(self, *, spec=None, pack=None, policy=None):
        return BlindRatingCollection(spec=spec or self.spec, pack=pack or self.pack,
            authority=self.authority, view_policy=policy)

    def _rating(self, pair, *, spec=None, **changes):
        frozen = spec or self.spec
        fields = dict(rating_id=f"fictional-rating-{pair['pair_id']}", collection_id=frozen.collection_id,
            spec_sha256=frozen.digest(), reviewer_id=self.reviewer.reviewer_id, pair_id=pair["pair_id"],
            pair_binding_sha256=pair_binding_sha256(pair), submitted_at="2026-09-29T10:01:00.000000Z",
            labels={"personal_fit": "prefer_left", "reason_fit": "tie",
                    "needed_change": None, "unrelated_stability": None},
            notes={"reason_fit": "A fictional human note, not a model-generated assessment."})
        fields.update(changes)
        return HumanRating(**fields)

    def _fill(self, collection, *, pack=None, spec=None, labels_by_pair=None):
        for pair in (pack or self.pack)["pairs"]:
            fields = {} if not labels_by_pair or pair["pair_id"] not in labels_by_pair else {"labels": labels_by_pair[pair["pair_id"]]}
            rating = self._rating(pair, spec=spec or collection.spec, **fields)
            collection.submit(rating, proof=self.reviewer_key.sign(rating.message()))

    def _seal(self, collection):
        time = "2026-09-29T10:02:00.000000Z"
        collection.seal(sealed_at=time, proof=self.coordinator_key.sign(collection.seal_message(sealed_at=time)))

    def _view(self, *, case_index=0, comparator="general_model_memory", dimension="needed_change"):
        identities = self.key["pairs"]
        matching = {value["phase"]: pair_id for pair_id, value in identities.items()
            if value["case_id"] == f"fixture-case-{case_index}" and comparator in {value["left"], value["right"]}}
        before_id, after_id = matching["before"], matching["after"]
        pairs = {pair["pair_id"]: pair for pair in self.pack["pairs"]}
        before, after = pairs[before_id], pairs[after_id]
        arm_a, arm_b = identities[after_id]["left"], identities[after_id]["right"]
        a_side = next(side for side in ("left", "right") if identities[before_id][side] == arm_a)
        b_side = next(side for side in ("left", "right") if identities[before_id][side] == arm_b)
        return LongitudinalReviewView(f"fictional-view-{case_index}-{dimension}", dimension,
            before_id, after_id, after["question"], "Fictional authorized correction/outcome context.",
            before[a_side], after["left"], before[b_side], after["right"], self.cases[case_index].intervention_event_id)

    def test_signed_intake_seal_recovery_and_separate_descriptive_dimensions(self):
        collection = self._collection()
        self._fill(collection)
        self._seal(collection)
        recovered = BlindRatingCollection.from_bytes(collection.export_bytes(), spec=self.spec,
            pack=self.pack, authority=self.authority)
        self.assertTrue(recovered.sealed)
        self.assertEqual(collection.export_bytes(), recovered.export_bytes())
        summary = aggregate_sealed_assessment(run=self.run, pack=self.pack, private_key=self.key, collection=recovered)
        self.assertEqual(summary["total_attempts"], 18)
        self.assertEqual(summary["possible_comparison_pairs"], 12)
        self.assertEqual(summary["reviewed_comparison_pairs"], 12)
        self.assertEqual(summary["acceptance_decision"], "not_evaluated")
        self.assertEqual(summary["uncertainty_estimation"], "not_computed")
        self.assertTrue(all(group["dimensions"]["needed_change"]["assessed_ratings"] == 0
                            for group in summary["rating_groups"].values()))

    def test_unblinding_incomplete_seal_and_unsigned_seal_are_rejected(self):
        collection = self._collection()
        with self.assertRaisesRegex(ValueError, "before.*sealed"):
            aggregate_sealed_assessment(run=self.run, pack=self.pack, private_key=self.key, collection=collection)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            collection.seal_message(sealed_at="2026-09-29T10:02:00.000000Z")
        self._fill(collection)
        with self.assertRaises(InvalidSignature):
            collection.seal(sealed_at="2026-09-29T10:02:00.000000Z", proof=b"x" * 64)

    def test_wrong_rater_key_approval_output_binding_or_pair_are_rejected(self):
        collection = self._collection()
        pair = self.pack["pairs"][0]
        rating = self._rating(pair)
        with self.assertRaises(InvalidSignature):
            collection.submit(rating, proof=Ed25519PrivateKey.generate().sign(rating.message()))
        for fields in ({"pair_binding_sha256": "a" * 64}, {"reviewer_id": "unapproved-rater"},
                       {"pair_id": "unknown-pair"}, {"spec_sha256": "b" * 64}):
            altered = replace(rating, **fields)
            with self.subTest(fields=fields):
                with self.assertRaises(ValueError):
                    collection.submit(altered, proof=self.reviewer_key.sign(altered.message()))
        altered_approval = replace(self.reviewer, authorization_ref="caller-invented-approval")
        spec = self._spec(reviewers=(altered_approval,))
        rejected = self._collection(spec=spec)
        rating = self._rating(pair, spec=spec)
        with self.assertRaisesRegex(PermissionError, "independently configured"):
            rejected.submit(rating, proof=self.reviewer_key.sign(rating.message()))

    def test_original_rating_maps_are_copied_and_duplicates_edits_after_seal_rejected(self):
        collection = self._collection()
        pair = self.pack["pairs"][0]
        rating = self._rating(pair)
        collection.submit(rating, proof=self.reviewer_key.sign(rating.message()))
        rating.labels["reason_fit"] = "prefer_right"
        self.assertEqual(json.loads(collection.export_bytes())["records"][0]["rating"]["labels"]["reason_fit"], "tie")
        with self.assertRaisesRegex(ValueError, "immutable"):
            collection.submit(rating, proof=self.reviewer_key.sign(rating.message()))
        for pair in self.pack["pairs"][1:]:
            rating = self._rating(pair)
            collection.submit(rating, proof=self.reviewer_key.sign(rating.message()))
        self._seal(collection)
        with self.assertRaisesRegex(ValueError, "cannot be changed"):
            collection.submit(self._rating(pair), proof=b"x" * 64)

    def test_independent_coordinator_and_distinct_reviewer_credentials_required(self):
        for coordinator in (self.reviewer, replace(self.reviewer, reviewer_id="another-coordinator-id")):
            with self.assertRaisesRegex(ValueError, "separate approved identity and credential"):
                self._spec(coordinator=coordinator)
        second_reviewer = replace(self.reviewer, reviewer_id="another-rater-same-key")
        with self.assertRaisesRegex(ValueError, "distinct approved reviewers"):
            self._spec(reviewers=(self.reviewer, second_reviewer))

    def test_concurrent_duplicate_intake_is_serialized_and_can_still_seal_recover(self):
        outer = self

        class SlowSignatureAuthority:
            def verify_rating(self, **fields):
                time.sleep(0.02)  # Authentication I/O can release the GIL.
                outer.authority.verify_rating(**fields)

            def verify_seal(self, **fields):
                outer.authority.verify_seal(**fields)

        collection = BlindRatingCollection(spec=self.spec, pack=self.pack, authority=SlowSignatureAuthority())
        rating = self._rating(self.pack["pairs"][0])
        proof = self.reviewer_key.sign(rating.message())
        barrier = Barrier(2)

        def submit(_):
            barrier.wait(timeout=2)
            try:
                collection.submit(rating, proof=proof)
                return True
            except ValueError:
                return False

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(submit, range(2)))
        self.assertEqual(results.count(True), 1)
        self.assertEqual(len(json.loads(collection.export_bytes())["records"]), 1)
        for pair in self.pack["pairs"][1:]:
            rating = self._rating(pair)
            collection.submit(rating, proof=self.reviewer_key.sign(rating.message()))
        self._seal(collection)
        recovered = BlindRatingCollection.from_bytes(collection.export_bytes(), spec=self.spec,
            pack=self.pack, authority=self.authority)
        self.assertTrue(recovered.sealed)

    def test_stored_rating_or_self_declared_seal_cannot_be_rehashed_to_pass(self):
        collection = self._collection()
        self._fill(collection)
        self._seal(collection)
        export = json.loads(collection.export_bytes())
        export["records"][0]["rating"]["labels"]["reason_fit"] = "prefer_right"
        with self.assertRaises(InvalidSignature):
            BlindRatingCollection.from_bytes(canonical_json_bytes(export), spec=self.spec, pack=self.pack, authority=self.authority)
        export = json.loads(collection.export_bytes())
        export["seal"]["message"]["rating_count"] = 0
        with self.assertRaisesRegex(ValueError, "seal provenance"):
            BlindRatingCollection.from_bytes(canonical_json_bytes(export), spec=self.spec, pack=self.pack, authority=self.authority)

    def test_actual_rubric_threshold_case_and_protocol_completeness_required(self):
        for fields in ({"rubric": b"wrong bytes"}, {"threshold_spec": b"wrong thresholds"},
                       {"case_rubrics": {}}, {"assignments": self.spec.assignments[1:]}):
            with self.subTest(fields=fields):
                with self.assertRaises(ValueError):
                    self._spec(**fields)
        changed_pack = json.loads(json.dumps(self.pack))
        changed_pack["pairs"][0]["left"] += "changed"
        with self.assertRaisesRegex(ValueError, "actual review pack"):
            self.spec.validate(changed_pack)

    def test_single_phase_pack_cannot_rate_change_stability_or_unknown_labels(self):
        collection = self._collection()
        pair = self.pack["pairs"][0]
        for dimension, label in (("needed_change", "tie"), ("unrelated_stability", "tie"), ("personal_fit", "unknown-label")):
            labels = dict(self._rating(pair).labels)
            labels[dimension] = label
            rating = self._rating(pair, labels=labels)
            with self.assertRaises(ValueError):
                collection.submit(rating, proof=self.reviewer_key.sign(rating.message()))

    def test_authorized_longitudinal_views_have_fixed_anonymous_mapping_and_separate_metrics(self):
        views = (self._view(), self._view(case_index=1, dimension="unrelated_stability"))
        policy = FictionalViewPermission(views)
        spec = self._spec(views=views, policy=policy)
        collection = self._collection(spec=spec, policy=policy)
        labels_by_pair = {}
        for view in views:
            labels = dict(self._rating(next(p for p in self.pack["pairs"] if p["pair_id"] == view.after_pair_id)).labels)
            labels[view.dimension] = "prefer_left"
            labels_by_pair[view.after_pair_id] = labels
            self.assertNotIn("intervention_event_id", view.review_record())
        self._fill(collection, spec=spec, labels_by_pair=labels_by_pair)
        self._seal(collection)
        summary = aggregate_sealed_assessment(run=self.run, pack=self.pack, private_key=self.key, collection=collection)
        for dimension in ("needed_change", "unrelated_stability"):
            self.assertEqual(sum(group["dimensions"][dimension]["assessed_ratings"]
                for group in summary["rating_groups"].values()), 1)

    def test_swapped_longitudinal_identity_wrong_intervention_or_permission_withdrawal_rejected(self):
        original = self._view()
        for view in (replace(original, anonymous_a_before=original.anonymous_b_before,
                             anonymous_b_before=original.anonymous_a_before),
                     replace(original, intervention_event_id="wrong-original-intervention")):
            policy = FictionalViewPermission((view,))
            spec = self._spec(views=(view,), policy=policy)
            collection = self._collection(spec=spec, policy=policy)
            self._fill(collection, spec=spec)
            self._seal(collection)
            with self.assertRaisesRegex(ValueError, "anonymous arm identity"):
                aggregate_sealed_assessment(run=self.run, pack=self.pack, private_key=self.key, collection=collection)
        with self.assertRaises(PermissionError):
            self._spec(views=(original,))
        policy = FictionalViewPermission((original,))
        spec = self._spec(views=(original,), policy=policy)
        collection = self._collection(spec=spec, policy=policy)
        policy.allowed.clear()
        with self.assertRaises(PermissionError):
            collection.submit(self._rating(self.pack["pairs"][0], spec=spec), proof=b"x" * 64)

    def test_output_mapping_missing_pairs_duplicate_pairs_and_case_split_tampering_rejected(self):
        collection = self._collection()
        self._fill(collection)
        self._seal(collection)
        for mutate in (lambda key: key["pairs"].pop(next(iter(key["pairs"]))),
                       lambda key: key["pairs"][next(iter(key["pairs"]))].update(left_output_sha256="a" * 64),
                       lambda key: key.update(excluded_pairs=1)):
            key = json.loads(json.dumps(self.key))
            mutate(key)
            with self.assertRaises(ValueError):
                aggregate_sealed_assessment(run=self.run, pack=self.pack, private_key=key, collection=collection)
        altered = replace(self.cases[0], split="pilot")
        protocol = replace(self.run.plan.protocol, cases=(altered, *self.cases[1:]))
        run = replace(self.run, plan=replace(self.run.plan, protocol=protocol))
        with self.assertRaises(ValueError):
            aggregate_sealed_assessment(run=run, pack=self.pack, private_key=self.key, collection=collection)

    def test_all_failure_attempts_and_excluded_comparisons_stay_in_denominator(self):
        attempts = tuple(replace(attempt, status="timeout", elapsed_ms=1001, usage=None, output=None,
            output_sha256=None, decision_event_id=None) if attempt.case_id == self.cases[0].case_id
            and attempt.phase == "after" and attempt.arm == "flora_full" else attempt for attempt in self.run.attempts)
        run = replace(self.run, attempts=attempts)
        pack, key = create_blind_review(run, policy=FictionalReviewPermission(), rng=random.Random(3))
        spec = self._spec(run=run, pack=pack)
        collection = self._collection(spec=spec, pack=pack)
        self._fill(collection, spec=spec, pack=pack)
        self._seal(collection)
        summary = aggregate_sealed_assessment(run=run, pack=pack, private_key=key, collection=collection)
        self.assertEqual(summary["total_attempts"], 18)
        self.assertEqual(summary["possible_comparison_pairs"], 12)
        self.assertEqual(summary["reviewed_comparison_pairs"], 10)
        self.assertEqual(summary["excluded_comparison_pairs"], 2)
        self.assertEqual(sum(group["statuses"].get("timeout", 0) for group in summary["attempt_groups"].values()), 1)
        excluded_groups = [group for group_id, group in summary["rating_groups"].items()
                           if group_id.endswith("/after/relevant_correction")]
        self.assertEqual(len(excluded_groups), 2)
        self.assertTrue(all(group["possible_comparison_pairs"] == group["excluded_pairs"] == 1
                            and group["reviewed_pairs"] == group["ratings"] == 0 for group in excluded_groups))


if __name__ == "__main__":
    unittest.main()
