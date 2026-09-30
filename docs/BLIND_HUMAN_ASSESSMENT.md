# Blind human assessment

`src/flora/blind_assessment.py` prepares rating intake and descriptive reporting for the [frozen FloRA experiment](EXPERIMENT_GOAL.md). It accepts human submissions. It contains no automated judge, personality model, MFM, generated rating or numerical win threshold.

The actual pilot must still supply the rubric, acceptance criteria, evaluation cohort and consenting reviewers. This module's tests use fictional receipts and signature keys to check collection mechanics; they are not a behavioral result.

## Freeze the actual assessment materials

`freeze_assessment_spec(...)` consumes a validated `PairedRun` and its blinded review pack, with:

- Actual scoring-rubric bytes matching `EvaluationProtocol.scoring_rubric_sha256`.
- Actual threshold-specification bytes matching `threshold_spec_sha256`. These stay referenced; this module does not interpret an acceptance rule.
- Every actual sealed case rubric matching its case's registered digest.
- Approved reviewers, their exact credential hashes and approval references, plus an independently approved collection coordinator.
- The complete pair/reviewer assignment matrix, including at least one assigned reviewer for every reviewable pair.
- Any separately authorized longitudinal views used for change or stability assessment.

The rubric format is `flora-human-assessment-rubric-v1`: its `dimensions` map must contain `personal_fit`, `reason_fit`, `needed_change` and `unrelated_stability`. Each has an actual human-readable `instruction` and distinct `labels`. The format does not prescribe those labels, scores, sample sizes or a pass threshold. A `null` submission marks a dimension unassessed rather than inventing a label or zero score.

Rubrics must give reviewers enough independently authorized context to assess the requested dimension. A signature proves which approved credential submitted a rating; it does not prove reviewer expertise, independence or that the person understood the evidence. Those require recruitment and assessment design outside the collector.

## Collect without the identity key

`BlindRatingCollection` receives the frozen spec, blind pack and independently configured signature authority. Its intake does not accept the private arm identity key.

Each `HumanRating` binds its collection, frozen spec, reviewer, opaque pair, exact question/output digest binding, submission time, separate dimension labels and any human notes. `submit(...)` checks the frozen assignment and authenticates the exact original message. The included `Ed25519AssessmentAuthority` requires independently configured public keys **and approval records**; a caller cannot invent an approval reference to qualify itself.

There is no edit/delete operation. Submissions are copied into immutable canonical records. Duplicate IDs or a second submission for the same pair/reviewer assignment are refused, including concurrent intake. Reviewers must have distinct credentials; the coordinator must use a separate approved identity and credential. After the expected assignments are complete, the coordinator signs `seal_message(...)`; `seal(...)` verifies that independent signature. An incomplete collection or a self-declared hash is insufficient. After sealing, new submissions are refused.

`export_bytes()` is a standalone private JSON record containing the original submitted ratings, approval provenance, signatures and collection seal. `from_bytes(...)` rechecks the current spec, every rating signature and the coordinator signature. Changing a stored rating and recomputing a checksum cannot preserve validity. Times use the kernel's canonical UTC representation, such as `2026-09-29T10:01:00.000000Z`.

These records can contain personal human notes. Keep them in authorized encrypted custody; do not commit actual ratings or credentials to the public repository. The current module provides serialization, not the selected-store rating persistence adapter. [Selected comparison custody](../src/flora/selected/comparison_custody.py) already separates encrypted review-pack and identity-key artifacts; connecting rating/spec/seal custody and a seal-enforced identity-key export remains a separate integration.

## Change and stability need a different view

The original blind pack randomizes left/right independently for each phase. Rating one answer cannot show whether judgment changed appropriately or stayed stable over time. Such ratings must leave `needed_change` and `unrelated_stability` unassessed.

`LongitudinalReviewView` supplies the actual before/after answers with constant anonymous A/B identity, the common question and authorized correction/outcome context. A is the after pair's left side, B its right side. The producer uses the private identity key to arrange the before answers consistently; that producer role is distinct from the blinded reviewer and rating collector.

The private view manifest binds original pair/output bytes and the actual intervention event. Reviewers receive `review_record()`, which excludes the original event ID. A trusted `LongitudinalViewAuthorization` must independently authorize the exact view, pack and plan and return its approval/proof references. The collector rechecks that authority; withdrawal stops use. This is an adapter boundary, not a fabricated claim that actual host permission has been obtained.

Before reporting, the module checks those views against the private key and complete run: same host/case/comparator, actual before/after phases, constant anonymous arms, exact outputs and the declared intervention. Relevant correction/outcome cases can support the needed-change dimension; the existing protocol's irrelevant-correction cases can support unrelated stability. Without an authorized view, a non-null longitudinal label is refused.

## Unblind and describe after sealing

`aggregate_sealed_assessment(...)` refuses an unsealed collection. It revalidates the frozen protocol, materialized rubric references, all signatures, the collection seal and the actual private mapping against every run output and question. Missing pairs, altered outputs, changed case splits or erased exclusions prevent a report.

The report keeps:

- Every attempt, including timeout, refusal, unavailability, invalid result and budget failure, in per-host/arm/phase status counts.
- The total possible, reviewed and excluded comparison-pair counts.
- Human label counts and unassessed counts separately for each dimension, host, comparator, phase, intervention and pilot/held-out split.
- The original label orientation, stratified by whether FloRA was on the left or right. It does not infer preference semantics that the actual rubric did not specify.

Planned comparison strata remain in the report when every pair in that stratum fails, with explicit possible/reviewed/excluded counts and failure statuses. No missing rating group can silently disappear from its denominator.

The report states `acceptance_decision: not_evaluated` and `uncertainty_estimation: not_computed`. It does not turn missing dimensions, excluded failures or a synthetic result into a win, a confidence interval, customer traction or real-host benefit. A preregistered acceptance/uncertainty analysis must later consume the actual rubric and threshold specification explicitly.

That separate deterministic step is now available through [explicit sealed-assessment analysis](SEALED_ASSESSMENT_ANALYSIS.md). Its pure preflight accepts actual pilot-supplied rule and rubric bytes before held-out outputs exist. After independently signed collection sealing, it applies only the exact supported rule already frozen in the protocol, preserves failed pairs and per-host results, and reports conditional rule decisions. The descriptive aggregate above remains unchanged. Actual study design and complete independent Part1 producer/result qualification remain separate dependencies.

The collector enforces its own unblinding API boundary. It cannot stop a producer who already holds the private key from disclosing it through another channel. Actual reviewer separation, restricted key access and selected-store permission controls are operational requirements.

## Verification

`tests/test_blind_assessment.py` exercises signed recovery, exact output/spec/credential binding, immutable copied inputs, incomplete/forged seals, tampered ratings, actual rubric materialization, missing criteria, longitudinal identity/intervention and permission checks, split changes, and failure retention. These are human-input contract fixtures, not an evaluation of the actual models.
