# Selected assessment custody and key release

`src/flora/selected/assessment_custody.py` connects [blind human assessment](BLIND_HUMAN_ASSESSMENT.md) to the existing selected comparison stack: XTDB immutable references, KurrentDB canonical events, the registered source/permission system and encrypted local objects. It adds no alternative datastore, learned model or automated judge.

Actual reviewers, their independent approval credentials, signed ratings, actual rubrics and preregistered acceptance criteria must still be supplied. Missing materials remain missing. The integration fixture's sample labels and criteria bytes are explicitly fictional; they are not a final evaluation design or evidence of personal judgment.

## Producer registration

`XTDBAssessmentCustody.register_spec(...)` is a producer operation. It recovers the actual registered run and authorized blind review pack, validates every materialized rubric/threshold/case reference and records the exact spec in encrypted custody. Its canonical event points to the registered plan, run and review pack.

The producer necessarily knows which systems produced the answers. That producer role must remain separate from reviewers and blind collection services. Collectors receive only the spec and blind pack through their permitted adapter. `recover_spec`, rating intake, collection recovery and preparation of a seal do **not** open arm-labeled run/output plaintext.

The existing public comparison read path also denies the `comparison_assessment:*` purpose for run, plan, history, context, question, output and key artifacts. Permission for their participation as ancestors does not become direct collector access to their labeled content. The assessment-purpose allowlist contains only spec, rating and seal artifacts.

Registration records custody. It grants no access to the new artifact or its parents. Independently authorized purpose actions must exist before subsequent reads.

## Immutable human records

- `assessment_purpose(run_id, collection_id)` defines the collection-specific source-use purpose.
- `assessment_rating_id(run_id, collection_id, pair_id, reviewer_id)` creates the required assignment-derived rating ID. The reviewer signs that ID in the actual `HumanRating`; the adapter never rewrites a signed submission. This prevents two processes or interrupted placements from using one arbitrary rating ID for different assignments.
- `submit_rating(...)` authenticates the exact copied submission with independently configured reviewer approval, checks its frozen pair/output binding and persists an encrypted immutable rating artifact. It neither generates a label nor judges the answer.
- Exact retries return the original artifact. A changed signed rating cannot overwrite its assignment. Append-before-registry placement follows the existing comparison custody's canonical-event recovery route.
- `recover_collection(...)` opens each existing expected assignment under current collection permission, rechecks signatures, reconstructs a canonical assignment order and checks every gathered rating's permission again before returning. A later read cannot hide the withdrawal of an earlier rating.

Rating metadata hashes the same authenticated snapshot as the stored record. Human notes stay in encrypted custody. This method seed and the repository contain no actual ratings or private reviewer keys.

## A durable seal comes before key access

`prepare_seal_message(...)` succeeds only when all expected assignments exist. The independently approved coordinator signs those exact bytes. `seal_collection(...)` verifies the signature and places an encrypted seal capsule whose canonical parents include the spec and **every actual rating artifact**.

Recovery verifies both the original signed records and coordinator signature. It also compares the sealed record list to the separately persisted individual ratings. A self-declared `sealed` flag, supplied digest, fabricated receipt or mismatched capsule cannot authorize unblinding.

Public `XTDBComparisonCustody.read(...)` always denies the private key, even with a `comparison_unblind` grant. There is no public permission-only key export. `release_private_key(...)` is the selected adapter's authorized release route:

1. Recover the actual spec, expected signed ratings and independently signed durable seal.
2. Use the internal comparison key hook under current `comparison_unblind` permission, including its full original/derivative parent closure.
3. After the seal has been verified, recover the actual labeled run and validate the private mapping, complete failure matrix and any fixed anonymous longitudinal views.
4. Recheck the collection seal, review permission and unblinding permission after I/O before returning the key.

`aggregate_after_seal(...)` uses the same release gate and returns the descriptive report. It makes no acceptance decision and computes no uncertainty method that has not been preregistered. All failures and unassessed dimensions remain visible.

Assessment, review, local producer/recovery and unblinding purposes are separate. A host can authorize collection without authorizing unblinding. A withdrawal during collection or release stops the operation.

These are application boundaries for independently configured services. A trusted local producer holding the host's decryption key or direct database access can inspect its own storage; Python method privacy is not an OS security boundary. Reviewer accounts/processes must have only the blind service interface and their approved material, not producer credentials or backend access.

## API sequence

`register_spec` → authorize the spec/ancestors for the collection purpose → `submit_rating` → authorize each rating → `prepare_seal_message` → obtain coordinator signature → `seal_collection` → authorize the seal → `release_private_key` or `aggregate_after_seal`.

Use the actual source-purpose action path for those grants. There is no convenience auto-grant or invented reviewer/threshold default.

## Verification

- `tests/test_assessment_custody.py`: eleven component checks cover encrypted snapshot recovery, immutable retries, authenticated seal comparison, no pre-seal labeled run access, deterministic assignment identity, current per-source permission, delayed withdrawal, scope and missing-material guards. Its comparison transcript is a call fixture, not a substitute datastore or backend qualification.
- `tests/integration/test_selected_assessment_custody.py`: real XTDB/KurrentDB/encrypted object and owner-signed permission actions. It exercises actual durable spec/rating/seal placement, missing and invalid seals, purpose separation, connection/registry recreation, exact retry and withdrawal of key release. Its supplied outputs and human submissions are fictional contract fixtures; no model inference or human study occurs.

Real selected-backend qualification remains pending until that integration test passes in CI. Passing it establishes this custody/release slice, not a successful FloRA experiment, complete Stage G or a full Fable release.
