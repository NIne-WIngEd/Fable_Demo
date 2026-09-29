# FloRA experiment goal — frozen 2026-09-29

## The question

When a person corrects Fable or a decision has an outcome, does its later **native personal judgment** change for the right reason, stay stable on unrelated decisions, and beat a strong general model with memory? Can an automated builder reproduce that capability for another isolated person?

This is the goal of FloRA. A working database, a convincing conversation, or one good story alone does not answer it.

## Evidence we need

1. **A relevant change, not a reflex.** Record a judgment before and after a correction or outcome. The later judgment should change when the new evidence matters. Irrelevant corrections should leave it stable. Record the source and the reason for each change.
2. **A serious product comparison.** Give a well-built general-model-plus-memory baseline the same authorized raw history and comparable response budget. Its retrieval, summary, and correction handling must be competent. Compare held-out decisions that were not used to tune either system.
3. **An attribution test.** Compare the full FloRA path with an ablation that receives the same selected evidence but lacks FloRA's personal judgment update. This distinguishes an advantage from better evidence selection from an advantage in the learned judgment mechanism. Both are useful results; report them separately.
4. **A transfer test.** A small Fable Builder Model must build the qualified slice for additional isolated hosts from their authorized data. Hand-tuning a second personality does not count as builder success.
5. **A real-host check.** Synthetic longitudinal histories can test the mechanism and its controls. Claims about helping people require consenting real hosts, their real corrections and outcomes, and blind assessment of personal fit. Hosts should not be told which system produced a paired answer.

## Rules before scoring

- Freeze the histories, held-out decisions, comparator implementation, allowed evidence, budgets, scoring rubric, sample size, and win threshold **before** the final evaluation. Use a pilot only to design that protocol; do not tune on its held-out set.
- Report relevant-change success and irrelevant-change errors separately. Include blind preference, evidence and reason accuracy, latency, and failures. Give uncertainty and per-host results, not only an aggregate win rate.
- Run the end-to-end result on FloRA's selected physical path. Fast isolated checks may help development; they are not a substitute for a selected-stack result. Report backend reliability and performance separately from judgment quality.
- Keep feature assistance and data access comparable across arms. A general API model may help express a decision, but an API-written answer alone is not evidence of native personal judgment.
- Label a synthetic-only result as a mechanism result. Do not present it as customer traction, real-host benefit, or proof that Fable can build frontier feature models.
- Publish losses and failure cases. If the advantage comes from memory organization rather than judgment updating, say so.

## What is frozen and what is pending

The **question, comparisons, transfer requirement, and evidence rules above are frozen as FloRA's goal**. Numerical thresholds and the actual evaluation cohort are not yet frozen. They require a pilot and a dated, versioned preregistration before final data is run. Changes to this goal must be explicit revisions; earlier results keep the goal version under which they were measured.

Personality and MFM are separate workstreams. FloRA builds the other infrastructure and cannot claim the behavioral result until their qualified outputs are integrated.
