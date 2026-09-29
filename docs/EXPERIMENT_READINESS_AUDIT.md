# FloRA experiment readiness audit — 2026-09-29

**Conclusion:** the experiment goal is coherent, and the selected-backend work is useful. The repository has not exhausted the work possible before personality and MFM are ready. It has input fixtures and fairness validators, rather than an executable comparison and assessment pipeline.

## Why this lane exists

- The full Fable release and an experiment proving one load-bearing claim are different deliverables. FloRA is the parallel research lane; it does not lower Fable v1's release gate.
- Part 1 connects the existing personality workstream to the selected memory infrastructure and tests whether a correction or observed outcome changes a later, unseen native judgment for the right reason.
- Part 2 begins after that capability succeeds: a limited FBM must rebuild the same qualified slice for other isolated hosts from their authorized data. Reusing the first host's identity weights or hand-designing the second host is not builder transfer.
- There is no disposable judgment model in this plan. Personality and MFM remain separate workstreams; this repository builds the surrounding infrastructure.
- The physical path must match the selected A.L.I.C.E. Stage G–J successor contracts and engines for the portions exercised. Historical Phase 2 checks cannot qualify it.

Source context: the uploaded *Write-Fable-Readme.pdf*, pp. 43–50 and 55–61; *Docker-Environment-Setup.pdf*, pp. 1–3; and *Evaluating-a-YC-startup-pitch-idea (2).pdf*, pp. 16–22. These are context for the agreed method, not independent evidence that a product works. Private source chats are not copied into this repository. The earlier YC-pitch PDF versions repeat the discussion leading to the narrow experiment. Numerical suggestions and forecasts in that discussion are not frozen acceptance criteria.

## The claim and its controls

The [frozen goal](EXPERIMENT_GOAL.md) correctly requires:

- A relevant correction or outcome changes judgment with an accurate evidence trail.
- An irrelevant correction leaves the unrelated judgment stable.
- A serious general-model-plus-memory baseline receives the same authorized raw history and comparable feature assistance and budget. It may select its own evidence competently.
- A separate ablation receives the same selected evidence as FloRA and withholds the specified native judgment-update mechanism. This distinguishes a context advantage from a judgment advantage.
- A second isolated host is built by the limited builder without per-host manual redesign.
- Synthetic mechanism results, consenting real-host benefit, and customer traction are reported as different evidence.

The withheld mechanism still needs an executable definition tied to the selected development contract. A changed judgment does not automatically mean changed personality weights: governed personal state can change while a qualified personality checkpoint remains fixed. Record what was actually updated and withheld.

## What exists and what remains

| Step | Present evidence | Work possible before the models |
| --- | --- | --- |
| Input preparation | A public fictional multi-year pilot, three intervention types, exact before/after source lists, two-phase KurrentDB/raw intake | Generalize case ingestion and checkpoints; build training/pilot/held-out separation, sealed assessment artifacts, and additional independently authored host/case inputs. The present nine-event before history is a development fixture, not a workload-scale result. |
| Experimental fairness | `EvaluationProtocol` and `AttemptReceipt` check declared history hashes, arm/phase completeness, equal declared budgets, and same-evidence ablation | Materialize and verify referenced artifacts; implement the paired runner, output persistence, actual token/call/time accounting, and failure-inclusive receipts. Declared hashes alone do not verify the implementation they name. |
| Product comparator | A comparator design hash is required | Implement a competent general-model memory/retrieval/correction path and its feature-engine adapter. Verify its plumbing with synthetic responses; run and calibrate the real comparison only after the required engines and credentials are available. |
| Mechanism ablation | Equal selected-evidence hashes are required | Define and implement the withheld native-update path and its artifact/version record without substituting a new model. Qualifying its behavior requires the real models. |
| Assessment | The goal names blinding, evidence/reason accuracy, relevant/irrelevant metrics, latency, uncertainty, per-host results, and losses | Build randomized blinded review packs, independent rating intake, split checks, deterministic metric/report code, and complete failure reporting. No such executable assessment pipeline is present at the audited baseline. |
| Builder preparation | Compact public process traces and an isolated transfer-host field | Validate seed schema and feedback linkage; specify reproducible input/output custody, recipe and artifact lineage. Actual FBM training and the transfer experiment follow a qualified Part 1 result. |

## Actual model-dependent boundary

- MFM must produce qualified memory proposals from the authorized raw experiences; a deterministic gate alone is not learned formation.
- The personality workstream must produce qualified native judgment from delivered evidence and personal state; supplied test verdicts are not native judgment.
- An integrated pilot must establish the model-dependent behavior, failure modes and operating budget before numerical thresholds and the final cohort are preregistered.
- The final held-out comparison, real-host assessment, and limited FBM reproduction cannot be claimed from infrastructure tests.

The current `AttemptReceipt` has no failure/timeout/refusal state or actual token usage, and its validator rejects elapsed time beyond the budget. That is useful as a success-path guard but does not yet implement the goal's requirement to retain failed attempts. A full runner must preserve those failures rather than omit them from a denominator.

## FBM seed correction

The audit found 18 unique procedure traces, with the required `authority` field missing from 13 rows. The repair states only each operation's permitted scope and limits. [The seed validator](fbm-seeds/validate_traces.py) now checks required fields, stable IDs, timestamps and schema values, with regressions for missing authority and duplicate IDs.

A.L.I.C.E.'s active [trace schema v0.1](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/fable-builder-model/docs/fable-builder/TRACE_SCHEMA_v0.1.md) distinguishes a procedure seed from a trainable/evaluable linked case. Such a case needs concrete eligible inputs, subject/source and permission roles, a choice set including stop/defer where appropriate, an independently checkable target or unresolved state, the authority decision, observed outcome, and source/generator split lineage. Schema-valid traces alone are not an adequate FBM dataset or a demonstrated builder.

This audit preserves the goal and two-part scope. It corrects the premature stopping point; it does not supply missing model results, sample sizes, thresholds, customer evidence or release dates.
