"""Selected encrypted human-assessment custody and signed-seal key release.

Reuse comparison custody's XTDB/Kurrent/source registry/object placement. No
rating, reviewer approval, rubric, threshold or learned result is invented.
Public comparison reads cannot open the private key; this adapter first
reconstructs and authenticates the complete durable sealed collection.
"""

from __future__ import annotations

import base64
import hashlib
import json

from cognitive_kernel.canonical import canonical_json_bytes, canonical_sha256, require_identifier
from ..blind_assessment import (
    ApprovedReviewer, AssessmentSignatureAuthority, BlindRatingCollection,
    FrozenAssessmentSpec, HumanRating, LongitudinalReviewView,
    LongitudinalViewAuthorization, VerifiedViewAuthorization,
    aggregate_sealed_assessment,
)
from ..evaluation_protocol import EvaluationCase, EvaluationProtocol
from .comparison_custody import ComparisonArtifact, XTDBComparisonCustody
from .formation_policy import XTDBFormationPermissionPolicy


def _identifier(value: str, label: str) -> None:
    if require_identifier(value, label) != value:
        raise ValueError(f"{label} must be canonical")


def assessment_purpose(run_id: str, collection_id: str) -> str:
    _identifier(run_id, "run_id")
    _identifier(collection_id, "collection_id")
    return "comparison_assessment:" + canonical_sha256([run_id, collection_id])


def assessment_artifact_id(collection_id: str, kind: str, *, pair_id: str | None = None,
                           reviewer_id: str | None = None) -> str:
    _identifier(collection_id, "collection_id")
    if kind not in {"spec", "rating", "seal"}:
        raise ValueError("unknown assessment artifact kind")
    material = [collection_id, kind]
    if kind == "rating":
        _identifier(pair_id, "pair_id")
        _identifier(reviewer_id, "reviewer_id")
        material.extend((pair_id, reviewer_id))
    elif pair_id is not None or reviewer_id is not None:
        raise ValueError("non-rating artifact cannot carry a pair/reviewer identity")
    return f"assessment_{kind}:" + canonical_sha256(material)


def assessment_rating_id(run_id: str, collection_id: str, pair_id: str, reviewer_id: str) -> str:
    """Assignment-derived identity prevents cross-process custom-ID collisions."""
    for name, value in (("run_id", run_id), ("collection_id", collection_id),
                        ("pair_id", pair_id), ("reviewer_id", reviewer_id)):
        _identifier(value, name)
    return "assessment_rating:" + canonical_sha256([run_id, collection_id, pair_id, reviewer_id])


def _spec_bytes(spec: FrozenAssessmentSpec) -> bytes:
    return canonical_json_bytes({"schema": "flora-assessment-spec-custody-v1",
        "spec": spec.record(), "protocol": spec.protocol.record(),
        "rubric_base64": base64.b64encode(spec.rubric).decode(),
        "threshold_spec_base64": base64.b64encode(spec.threshold_spec).decode(),
        "case_rubrics": [[case, base64.b64encode(content).decode()] for case, content in spec.case_rubrics],
        "views": [{"view": view.record(), "authorization": approval.record()} for view, approval in spec.views]})


def _spec_from_bytes(content: bytes) -> FrozenAssessmentSpec:
    body = json.loads(content)
    if (set(body) != {"schema", "spec", "protocol", "rubric_base64", "threshold_spec_base64", "case_rubrics", "views"}
            or body["schema"] != "flora-assessment-spec-custody-v1"):
        raise ValueError("stored assessment spec fields changed")
    protocol = dict(body["protocol"])
    if protocol.pop("schema") != "flora-evaluation-protocol-v1":
        raise ValueError("stored assessment protocol schema changed")
    protocol["cases"] = tuple(EvaluationCase(**case) for case in protocol["cases"])
    protocol["builder_transfer_host_ids"] = tuple(protocol["builder_transfer_host_ids"])
    record = body["spec"]
    views = []
    for item in body["views"]:
        if set(item) != {"view", "authorization"}:
            raise ValueError("stored longitudinal view fields changed")
        fields = dict(item["view"])
        if fields.pop("schema") != "flora-longitudinal-review-view-v1":
            raise ValueError("stored longitudinal view schema changed")
        views.append((LongitudinalReviewView(**fields), VerifiedViewAuthorization(**item["authorization"])))
    spec = FrozenAssessmentSpec(record["collection_id"], EvaluationProtocol(**protocol),
        record["plan_sha256"], record["review_pack_sha256"], record["frozen_at"],
        base64.b64decode(body["rubric_base64"], validate=True),
        base64.b64decode(body["threshold_spec_base64"], validate=True),
        tuple((case, base64.b64decode(value, validate=True)) for case, value in body["case_rubrics"]),
        tuple(ApprovedReviewer(**reviewer) for reviewer in record["reviewers"]),
        ApprovedReviewer(**record["coordinator"]),
        tuple(tuple(value) for value in record["assignments"]), tuple(views))
    if _spec_bytes(spec) != content:
        raise ValueError("stored assessment spec is not the exact canonical payload")
    return spec


class XTDBAssessmentCustody:
    """One isolated host/run; source-purpose permission never follows registration."""

    def __init__(self, *, comparison_custody: XTDBComparisonCustody,
                 signature_authority: AssessmentSignatureAuthority,
                 view_policy: LongitudinalViewAuthorization | None = None):
        self.comparison = comparison_custody
        self.authority, self.view_policy = signature_authority, view_policy

    def _permissions(self, permissions: XTDBFormationPermissionPolicy) -> None:
        if (permissions.scope != self.comparison.scope
                or permissions.authority_namespace_id != self.comparison.authority_namespace_id):
            raise ValueError("assessment permission policy crosses host or authority")

    def _inputs(self, *, run_id: str, permissions: XTDBFormationPermissionPolicy):
        self._permissions(permissions)
        run = self.comparison.recover_run(run_id=run_id, permissions=permissions,
                                          purpose="comparison_local_recovery")
        pack = self.comparison.export_review(run_id=run_id, permissions=permissions)
        return run, pack

    def _read(self, *, run_id: str, collection_id: str, kind: str,
              permissions: XTDBFormationPermissionPolicy,
              pair_id: str | None = None, reviewer_id: str | None = None) -> bytes:
        self._permissions(permissions)
        artifact_id = assessment_artifact_id(collection_id, kind, pair_id=pair_id, reviewer_id=reviewer_id)
        artifact = self.comparison.metadata(run_id, artifact_id)
        if (artifact is None or artifact.record["kind"] != f"assessment_{kind}"
                or artifact.record["metadata"]["collection_id"] != collection_id):
            raise ValueError("assessment artifact is absent or binds another collection/kind")
        return self.comparison.read(run_id=run_id, artifact_id=artifact_id, permissions=permissions,
                                    purpose=assessment_purpose(run_id, collection_id))

    def register_spec(self, *, run_id: str, spec: FrozenAssessmentSpec,
                      permissions: XTDBFormationPermissionPolicy, occurred_at: str) -> ComparisonArtifact:
        run, pack = self._inputs(run_id=run_id, permissions=permissions)
        spec.validate(pack, view_policy=self.view_policy)
        if (spec.plan_sha256 != run.plan.digest() or spec.protocol.digest() != run.plan.protocol.digest()
                or any(case.host_id != self.comparison.scope.host_instance_id for case in spec.protocol.cases)):
            raise ValueError("assessment spec differs from the exact registered isolated run")
        parents = tuple(sorted({self.comparison.metadata(run_id, key).event_id for key in ("plan", "run", "blind_pack")}))
        return self.comparison._put(run_id=run_id, artifact_id=assessment_artifact_id(spec.collection_id, "spec"),
            kind="assessment_spec", content=_spec_bytes(spec), parents=parents,
            metadata={"collection_id": spec.collection_id, "spec_sha256": spec.digest(),
                      "plan_sha256": spec.plan_sha256, "review_pack_sha256": spec.review_pack_sha256},
            occurred_at=occurred_at)

    def recover_spec(self, *, run_id: str, collection_id: str,
                     permissions: XTDBFormationPermissionPolicy) -> FrozenAssessmentSpec:
        self._permissions(permissions)
        # Registration is a producer operation and validated actual run bytes.
        # A blinded collector must not recover arm-labeled outputs here.
        pack = self.comparison.export_review(run_id=run_id, permissions=permissions)
        content = self._read(run_id=run_id, collection_id=collection_id, kind="spec", permissions=permissions)
        spec = _spec_from_bytes(content)
        spec.validate(pack, view_policy=self.view_policy)
        artifact = self.comparison.metadata(run_id, assessment_artifact_id(collection_id, "spec"))
        plan, run_record, pack_record = (self.comparison.metadata(run_id, key) for key in ("plan", "run", "blind_pack"))
        if (plan is None or run_record is None or pack_record is None
                or spec.collection_id != collection_id
                or spec.plan_sha256 != plan.record["metadata"]["plan_sha256"]
                or spec.plan_sha256 != run_record.record["metadata"]["plan_sha256"]
                or spec.review_pack_sha256 != pack_record.record["metadata"]["public_pack_sha256"]
                or set(artifact.record["parent_event_ids"]) != {plan.event_id, run_record.event_id, pack_record.event_id}
                or artifact.record["metadata"]["spec_sha256"] != spec.digest()
                or artifact.record["metadata"]["review_pack_sha256"] != spec.review_pack_sha256):
            raise ValueError("recovered assessment spec differs from durable run/pack bindings")
        return spec

    def recover_collection(self, *, run_id: str, collection_id: str,
                           permissions: XTDBFormationPermissionPolicy) -> BlindRatingCollection:
        spec = self.recover_spec(run_id=run_id, collection_id=collection_id, permissions=permissions)
        pack = self.comparison.export_review(run_id=run_id, permissions=permissions)
        collection = BlindRatingCollection(spec=spec, pack=pack, authority=self.authority, view_policy=self.view_policy)
        records = []
        for pair_id, reviewer_id in spec.assignments:
            artifact_id = assessment_artifact_id(collection_id, "rating", pair_id=pair_id, reviewer_id=reviewer_id)
            artifact = self.comparison.metadata(run_id, artifact_id)
            if artifact is None:
                continue
            payload = json.loads(self._read(run_id=run_id, collection_id=collection_id, kind="rating",
                pair_id=pair_id, reviewer_id=reviewer_id, permissions=permissions))
            if (set(payload) != {"schema", "spec_sha256", "record"}
                    or payload["schema"] != "flora-assessment-rating-custody-v1"
                    or payload["spec_sha256"] != spec.digest()
                    or payload["record"]["rating"]["pair_id"] != pair_id
                    or payload["record"]["rating"]["reviewer_id"] != reviewer_id
                    or payload["record"]["rating"]["rating_id"] !=
                       assessment_rating_id(run_id, collection_id, pair_id, reviewer_id)):
                raise ValueError("durable rating does not match its immutable assignment identity")
            records.append(payload["record"])
        # Individual records were assigned canonical order during initial
        # collection. A coordinator seal binds that order, not a DB scan order.
        records.sort(key=lambda value: spec.assignments.index((value["rating"]["pair_id"], value["rating"]["reviewer_id"])))
        exported = json.loads(collection.export_bytes())
        exported["records"] = records
        collection = BlindRatingCollection.from_bytes(canonical_json_bytes(exported), spec=spec, pack=pack,
            authority=self.authority, view_policy=self.view_policy)
        seal_id = assessment_artifact_id(collection_id, "seal")
        if self.comparison.metadata(run_id, seal_id) is not None:
            sealed_bytes = self._read(run_id=run_id, collection_id=collection_id, kind="seal", permissions=permissions)
            sealed = BlindRatingCollection.from_bytes(sealed_bytes, spec=spec, pack=pack,
                authority=self.authority, view_policy=self.view_policy)
            if not sealed.sealed:
                raise ValueError("stored seal artifact contains no independently authenticated seal")
            sealed_export, reconstructed = json.loads(sealed.export_bytes()), json.loads(collection.export_bytes())
            if sealed_export["records"] != reconstructed["records"]:
                raise ValueError("stored signed collection differs from the actual durable rating records")
            collection = sealed
        # Recheck full original/derivative closure after gathering all records.
        self._read(run_id=run_id, collection_id=collection_id, kind="spec", permissions=permissions)
        self.comparison.export_review(run_id=run_id, permissions=permissions)
        self._assert_collection_permissions(run_id=run_id, collection=collection, permissions=permissions)
        return collection

    def _assert_collection_permissions(self, *, run_id: str, collection: BlindRatingCollection,
                                       permissions: XTDBFormationPermissionPolicy,
                                       unplaced_assignment: tuple[str, str] | None = None) -> None:
        spec = collection.spec
        records = json.loads(collection.export_bytes())["records"]
        artifact_ids = [assessment_artifact_id(spec.collection_id, "spec")]
        for record in records:
            rating = record["rating"]
            assignment = (rating["pair_id"], rating["reviewer_id"])
            artifact_id = assessment_artifact_id(spec.collection_id, "rating",
                pair_id=assignment[0], reviewer_id=assignment[1])
            if assignment == unplaced_assignment and self.comparison.metadata(run_id, artifact_id) is None:
                continue
            artifact_ids.append(artifact_id)
        for artifact_id in artifact_ids:
            artifact = self.comparison.metadata(run_id, artifact_id)
            source = None if artifact is None else self.comparison.registry.lookup(artifact.event_id)
            if source is None or not permissions.permits(source, assessment_purpose(run_id, spec.collection_id)):
                raise PermissionError("assessment source permission was withdrawn during collection")
        pack = self.comparison.metadata(run_id, "blind_pack")
        source = None if pack is None else self.comparison.registry.lookup(pack.event_id)
        if source is None or not permissions.permits(source, "comparison_review"):
            raise PermissionError("review permission was withdrawn during assessment collection")

    def submit_rating(self, *, run_id: str, collection_id: str, rating: HumanRating,
                      proof: bytes, permissions: XTDBFormationPermissionPolicy,
                      occurred_at: str) -> ComparisonArtifact:
        spec = self.recover_spec(run_id=run_id, collection_id=collection_id, permissions=permissions)
        pack = self.comparison.export_review(run_id=run_id, permissions=permissions)
        probe = BlindRatingCollection(spec=spec, pack=pack, authority=self.authority, view_policy=self.view_policy)
        probe.submit(rating, proof=proof)
        record = json.loads(probe.export_bytes())["records"][0]
        rating_fields = {key: value for key, value in record["rating"].items() if key != "schema"}
        rating = HumanRating(**rating_fields)
        if rating.rating_id != assessment_rating_id(run_id, collection_id, rating.pair_id, rating.reviewer_id):
            raise ValueError("selected rating ID must be derived from its exact run/collection/assignment")
        payload = canonical_json_bytes({"schema": "flora-assessment-rating-custody-v1",
                                       "spec_sha256": spec.digest(), "record": record})
        artifact_id = assessment_artifact_id(collection_id, "rating", pair_id=rating.pair_id, reviewer_id=rating.reviewer_id)
        prior = self.comparison.metadata(run_id, artifact_id)
        if prior is not None:
            original = self._read(run_id=run_id, collection_id=collection_id, kind="rating",
                pair_id=rating.pair_id, reviewer_id=rating.reviewer_id, permissions=permissions)
            if original != payload:
                raise ValueError("durable human rating identity is immutable")
            return prior
        collection = self.recover_collection(run_id=run_id, collection_id=collection_id, permissions=permissions)
        collection.submit(rating, proof=proof)
        self._assert_collection_permissions(run_id=run_id, collection=collection, permissions=permissions,
            unplaced_assignment=(rating.pair_id, rating.reviewer_id))
        spec_artifact = self.comparison.metadata(run_id, assessment_artifact_id(collection_id, "spec"))
        pack_artifact = self.comparison.metadata(run_id, "blind_pack")
        return self.comparison._put(run_id=run_id, artifact_id=artifact_id, kind="assessment_rating", content=payload,
            parents=tuple(sorted((spec_artifact.event_id, pack_artifact.event_id))),
            metadata={"collection_id": collection_id, "spec_sha256": spec.digest(),
                      "pair_id": rating.pair_id, "reviewer_id": rating.reviewer_id,
                      "rating_sha256": hashlib.sha256(canonical_json_bytes(record["rating"])).hexdigest()}, occurred_at=occurred_at)

    def prepare_seal_message(self, *, run_id: str, collection_id: str, sealed_at: str,
                             permissions: XTDBFormationPermissionPolicy) -> bytes:
        collection = self.recover_collection(run_id=run_id, collection_id=collection_id, permissions=permissions)
        if collection.sealed:
            raise ValueError("durable collection is already sealed")
        return collection.seal_message(sealed_at=sealed_at)

    def seal_collection(self, *, run_id: str, collection_id: str, sealed_at: str, proof: bytes,
                        permissions: XTDBFormationPermissionPolicy, occurred_at: str) -> ComparisonArtifact:
        collection = self.recover_collection(run_id=run_id, collection_id=collection_id, permissions=permissions)
        artifact_id = assessment_artifact_id(collection_id, "seal")
        prior = self.comparison.metadata(run_id, artifact_id)
        if prior is not None:
            seal = json.loads(collection.export_bytes())["seal"]
            if (seal["message"]["sealed_at"] != sealed_at
                    or base64.b64decode(seal["proof_base64"], validate=True) != proof):
                raise ValueError("durable collection seal is immutable")
            return prior
        collection.seal(sealed_at=sealed_at, proof=proof)
        self._assert_collection_permissions(run_id=run_id, collection=collection, permissions=permissions)
        parents = [self.comparison.metadata(run_id, assessment_artifact_id(collection_id, "spec")).event_id]
        for pair_id, reviewer_id in collection.spec.assignments:
            parents.append(self.comparison.metadata(run_id, assessment_artifact_id(collection_id, "rating",
                pair_id=pair_id, reviewer_id=reviewer_id)).event_id)
        return self.comparison._put(run_id=run_id, artifact_id=artifact_id, kind="assessment_seal",
            content=collection.export_bytes(), parents=tuple(sorted(set(parents))),
            metadata={"collection_id": collection_id, "spec_sha256": collection.spec.digest(),
                      "sealed_at": sealed_at, "rating_count": len(collection.spec.assignments)}, occurred_at=occurred_at)

    def release_private_key(self, *, run_id: str, collection_id: str,
                            permissions: XTDBFormationPermissionPolicy) -> dict:
        collection = self.recover_collection(run_id=run_id, collection_id=collection_id, permissions=permissions)
        if not collection.sealed:
            raise PermissionError("private identity key requires a complete durable independently signed seal")
        # This is the only selected assessment path that calls the internal
        # key hook. The public comparison read/export routes always deny it.
        raw = self.comparison._read_private_key_for_sealed_assessment(run_id=run_id, permissions=permissions)
        private_key = json.loads(raw)
        run, pack = self._inputs(run_id=run_id, permissions=permissions)
        aggregate_sealed_assessment(run=run, pack=pack, private_key=private_key, collection=collection)
        # The signed seal's parent closure includes every rating/spec/original.
        self._read(run_id=run_id, collection_id=collection_id, kind="seal", permissions=permissions)
        self.comparison.export_review(run_id=run_id, permissions=permissions)
        # Recheck unblinding authority after all other custody/validation I/O.
        if self.comparison._read_private_key_for_sealed_assessment(run_id=run_id, permissions=permissions) != raw:
            raise ValueError("private identity key changed during sealed assessment release")
        self._assert_release_permissions(run_id=run_id, collection_id=collection_id, permissions=permissions)
        return private_key

    def _assert_release_permissions(self, *, run_id: str, collection_id: str,
                                    permissions: XTDBFormationPermissionPolicy) -> None:
        self._permissions(permissions)
        for artifact_id, purpose in (
                (assessment_artifact_id(collection_id, "seal"), assessment_purpose(run_id, collection_id)),
                ("blind_pack", "comparison_review"), ("blind_key", "comparison_unblind")):
            artifact = self.comparison.metadata(run_id, artifact_id)
            source = None if artifact is None else self.comparison.registry.lookup(artifact.event_id)
            if source is None or not permissions.permits(source, purpose):
                raise PermissionError("assessment, review or unblinding authority was withdrawn before release")

    def aggregate_after_seal(self, *, run_id: str, collection_id: str,
                             permissions: XTDBFormationPermissionPolicy) -> dict:
        private_key = self.release_private_key(run_id=run_id, collection_id=collection_id, permissions=permissions)
        collection = self.recover_collection(run_id=run_id, collection_id=collection_id, permissions=permissions)
        run, pack = self._inputs(run_id=run_id, permissions=permissions)
        summary = aggregate_sealed_assessment(run=run, pack=pack, private_key=private_key, collection=collection)
        self._read(run_id=run_id, collection_id=collection_id, kind="seal", permissions=permissions)
        self._assert_release_permissions(run_id=run_id, collection_id=collection_id, permissions=permissions)
        return summary
