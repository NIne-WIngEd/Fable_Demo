# Explicit analysis after a signed human assessment seal

FloRA can now apply an explicitly supplied, frozen numerical rule to its authenticated human ratings. This completes the deterministic analysis step without creating a judge, a model, ratings, study thresholds or a claim that FloRA won.

The original [`aggregate_sealed_assessment`](../src/flora/blind_assessment.py) remains descriptive. Its `not_evaluated` and `not_computed` fields are unchanged. The separate [`analyze_sealed_assessment`](../src/flora/sealed_analysis.py) API returns arithmetic and conditional rule decisions.

## Freeze the actual choices before held-out evaluation

The pilot must supply the actual rubric, cohort, label meanings, failure treatment, metric coverage, sampling design, uncertainty parameters and acceptance criteria. `validate_analysis_spec(threshold_spec=..., rubric=...)` structurally checks those actual bytes without needing a model, run, review pack, ratings or seal. It generates none of them.

The rule uses schema `flora-sealed-assessment-analysis-v1`. Its exact canonical JSON bytes occupy the existing `EvaluationProtocol.threshold_spec_sha256` binding. Freeze that protocol in the existing durable [preregistration](EXPERIMENT_PREREGISTRATION.md) before the held-out evaluation. Changing a score or threshold changes the frozen digest and invalidates an earlier run/spec binding. The preflight function alone does not establish a durable preregistration or prove when a rule was chosen.

Every metric explicitly supplies:

| Field | Required meaning |
| --- | --- |
| `dimension`, `comparator`, `phase`, `split`, `interventions` | The actual assessment dimension and declared comparison stratum. Pilot and held-out scopes remain separate. |
| `label_scores` | A score for **every actual rubric label**, separately for FloRA on the left and on the right. Label names have no built-in preference meaning. |
| `unassessed_score`, `excluded_pair_score` | Supplied scores for a null human assessment and a pair excluded because an arm failed. No observation disappears from the planned pair denominator. |
| `denominator` | Explicitly `all_planned_pairs`; reviewed-only analysis is unsupported. |
| `reviewer_aggregation`, `point_weighting` | Explicitly `equal_reviewers_within_pair` and `equal_planned_pairs`. First average human scores within a pair, then average the planned pair scores. |
| `uncertainty` | The supported method, cluster unit, confidence, resample count, seed, minimum cluster count, sampling assumptions, resampling algorithm and quantile definition. |
| `criteria` | Explicit comparisons of `point`, `lower` or `upper` with an actual supplied bound using `ge`, `le`, `gt` or `lt`. |

Scores, confidence and bounds are canonical rational strings, such as `"1/3"`, rather than floating-point numbers. These examples describe syntax; they are not proposed experiment values. The top-level `acceptance_combination` must explicitly be `all_criteria`. The implementation supplies no default success thresholds, score mappings, failure scores or confidence level.

## Authenticate, then calculate

Analysis first snapshots and reconstructs the actual signed collection. The existing aggregate then revalidates the independent coordinator seal, every original rating signature, actual rubric/threshold/case bytes, complete run, private arm mapping, question/output binding, authorized longitudinal views and failure-inclusive comparisons. Numerical work begins only after these checks succeed.

A metric retains one score per planned case/comparator/phase pair. Multiple reviewers are averaged within that pair. They do not become extra independent experimental units. Failed pairs retain the explicitly supplied excluded-pair score; null labels retain the explicitly supplied unassessed score. Reports preserve each case, each host, all attempts and their statuses, pair denominators, missing ratings, pilot/held-out selectors and `evidence_kind`.

Longitudinal labels still require the existing actual authorized before/after view. The analysis module cannot infer a needed change or unrelated stability from isolated answers or replace missing human labels with an automated assessment.

## One supported uncertainty computation

`cluster_percentile_v1` resamples entire declared `case` or `host` clusters with replacement. Every selected cluster carries all its pair scores. Each replicate computes the same equal-planned-pair mean. Unequal cluster sizes can therefore produce different replicate denominators.

The rule must explicitly name `sha256_counter_rejection_v1`: each uniform cluster index comes from SHA-256 of canonical JSON `["flora-cluster-draw-v1", seed, counter]`. A rejection step removes modulo bias; counters increase for every attempted draw. This fixes repeatability independently of a Python random-generator version.

The explicit `linear_order_statistics_v1` quantile sorts the replicate means. For probability `p`, its rank is `p * (B - 1)`, and it linearly interpolates the neighboring order statistics using exact rational arithmetic. The interval endpoints use probabilities `(1 - confidence) / 2` and `(1 + confidence) / 2`.

The method follows the general percentile resampling procedure documented by [SciPy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html) and the whole-cluster resampling structure described in [Loy and Korobova's primary publication](https://journal.r-project.org/articles/RJ-2023-015/). Their discussions also make the boundary clear: the sampling process determines an appropriate resampling scheme. Implementing this computation does not qualify case independence, host sampling, generalization, coverage or multiplicity control for FloRA's actual study. The report always records `sampling_design_qualified=false`; an actual study requires an independent review of the supplied design.

The pilot must supply `minimum_clusters`, at least two. Below it, including a single host when host clustering is declared, the interval is `not_estimable_insufficient_clusters` with null endpoints. A criterion needing a missing endpoint is not evaluable. Two clusters are a computational minimum, not an endorsement that two establish reliable uncertainty.

Supported implementation limits are 64 metrics, 100,000 resamples per metric, 1,000,000 requested cluster draws per metric, a 256-bit nonnegative seed and rational strings of at most 128 characters. Oversized requests are refused; they are never silently run with smaller parameters. These are resource bounds, not research thresholds.

## Selected custody and result meaning

`XTDBAssessmentCustody.analyze_after_seal(...)` uses the existing typed comparison and assessment custody. It requires the durable signed seal before private-key release, recovers exact run/pack/spec/ratings, performs analysis, then reads the actual seal again and checks its bytes against the authenticated collection. It samples the three actual release roots and their complete registered parent DAGs under the separate assessment, review and unblinding purposes. Every actual or custom permission delegate still runs. A final bounded XTDB statement observes all sampled source/raw/action/head rows together **after** those callbacks. A last callback withdrawing an earlier root or deep parent cannot preserve a previously checked release grant. The statement uses the existing 4,096-row selected metadata cap and provides no authorization lease after its snapshot.

The report says `accepted_under_supplied_criteria`, `rejected_under_supplied_criteria` or `not_evaluable`. These mean only that the supplied numerical comparisons were met, were not met, or lacked a required value. They do not mean a behavioral advantage, real-host benefit, customer traction or a qualified Part1 result. `part1_qualified` remains false, including for an accepted fictional or synthetic rule result.

The complete independent `Part1ResultValidator` remains a named external dependency. Its missing inputs are the actual qualified MFM/personality producer exports and codecs, their accepted native/ablation artifacts and historical phase/update-exclusion qualification, and a reviewed real pilot-derived study design and acceptance policy. The current Part1 material names `native_artifacts` and `phase_snapshots` do not define enough producer semantics to infer that qualification from arbitrary signed bytes. Existing custody can authenticate, bind, recover and recheck them; deterministic analysis can recompute a numerical report. Neither can invent what those producers' qualified behavior means or replace the independent qualification authority.

## Verification boundary

The focused tests use explicitly fictional signed-human inputs. They cover exact scoring and orientation, closed-form quantiles, deterministic draw vectors, reviewer clustering, excluded/null denominator retention, empty strata, one-host uncertainty, protocol/spec/key tampering, unsealed rejection, strict rule equality, preflight without outputs and resource bounds. Separate actual selected registry/policy tests use the existing controlled SQL/log ports and enrolled-owner signatures; the final unblinding callback persists an actual typed revocation of an earlier assessment root or deep parent, and the terminal statement denies return. Removing that statement reproduces the escape. Existing blind descriptive tests remain unchanged.

The existing actual XTDB/Kurrent/encrypted-object assessment integration fixture now also exercises an explicit fictional analysis rule. After arithmetic completes, its final unblinding callback revokes the actual earlier assessment seal grant in XTDB before report return. That extension requires the next exact-commit physical CI receipt. Local contract success is not a selected-backend or behavioral result.
