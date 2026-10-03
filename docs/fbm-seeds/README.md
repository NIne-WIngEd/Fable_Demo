# FloRA builder seeds

FloRA captures one compact, reusable process trace per material infrastructure or experiment-design step. These rows follow A.L.I.C.E.'s [FBM trace schema v0.1](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/fable-builder-model/docs/fable-builder/TRACE_SCHEMA_v0.1.md). FloRA is the source of these seeds; the builder workstream can refer to them here when it needs them.

Each trace records an observable operation, safe references, constraints, validation, and a failure lesson. It is a seed for later FBM training or evaluation, not FBM weights and not a claim that FloRA can already build itself. Private host content, credentials, hidden reasoning, and raw model output stay out of this public record.

Capture new milestones in the same schema as work proceeds. A failed test and its repair should remain linked. Logging must not delay the actual build.

Run `python docs/fbm-seeds/validate_traces.py` from the repository root to check required fields, unique IDs, UTC timestamps and schema values. This validates record shape; it does not certify a trace's claims, privacy, or eligibility as a training case.

The schema's linked-case boundary also requires concrete eligible inputs, permission roles, a choice set, an independently checkable target or unresolved state, authority and outcome records, and source/generator split lineage before a procedure seed becomes a supervised or evaluable FBM example. Those linked cases and the actual builder remain separate work. The [readiness audit](../EXPERIMENT_READINESS_AUDIT.md) records the seed-field repair and the remaining experiment boundary.

## Latest construction records — 2026-10-03

The corpus now contains **118 validated procedure traces**. This count describes
schema-valid records; it does not certify their claims or training eligibility.
New material construction, failure and recovery steps continue to be captured here.

| Record | Observable operation |
| --- | --- |
| [Completed older CI recovery](2026-10-03_completed_contract_cost_ci_recovery.jsonl) | Recover exact run checkouts and retain component/physical failures. |
| [Single fresh binding walk](2026-10-03_single_fresh_context_binding_walk.jsonl) | Remove measured duplicate traversal while retaining fresh own checks. |
| [Full components](2026-10-03_full_binding_components_and_publication.jsonl) | Verify 978 final cases after the retained worker failure and warning-bearing repeat. |
| [Published source and dispatch](2026-10-03_published_binding_walk_and_physical_dispatch.jsonl) | Bind the reviewed runtime to exact blobs and once-dispatched gates. |
| [Completed current CI](2026-10-03_completed_binding_ci_recovery.jsonl) | Verify all 26 jobs and retain the separate failed restart process. |
| [Unobserved cost and stack sampling](2026-10-03_unobserved_cost_and_owned_stack_sampler.jsonl) | Discriminate observer bias before another runtime change. |
| [Failed diagnostic and partial CI](2026-10-03_source_verified_binding_diagnostic.jsonl) | Verify loaded source, preserve failed response/process outcomes and avoid misleading timing comparisons. |

The latest result and unfinished gates are in the
[October 3 checkpoint](../VERIFICATION_CHECKPOINT_2026-10-03.md). Earlier records
remain linked snapshots; new outcomes do not rewrite an earlier failure or pending dispatch.
