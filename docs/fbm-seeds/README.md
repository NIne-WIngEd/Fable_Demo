# FloRA builder seeds

FloRA captures one compact, reusable process trace per material infrastructure or experiment-design step. These rows follow A.L.I.C.E.'s [FBM trace schema v0.1](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/fable-builder-model/docs/fable-builder/TRACE_SCHEMA_v0.1.md). FloRA is the source of these seeds; the builder workstream can refer to them here when it needs them.

Each trace records an observable operation, safe references, constraints, validation, and a failure lesson. It is a seed for later FBM training or evaluation, not FBM weights and not a claim that FloRA can already build itself. Private host content, credentials, hidden reasoning, and raw model output stay out of this public record.

Capture new milestones in the same schema as work proceeds. A failed test and its repair should remain linked. Logging must not delay the actual build.

Run `python docs/fbm-seeds/validate_traces.py` from the repository root to check required fields, unique IDs, UTC timestamps and schema values. This validates record shape; it does not certify a trace's claims, privacy, or eligibility as a training case.

The schema's linked-case boundary also requires concrete eligible inputs, permission roles, a choice set, an independently checkable target or unresolved state, authority and outcome records, and source/generator split lineage before a procedure seed becomes a supervised or evaluable FBM example. Those linked cases and the actual builder remain separate work. The [readiness audit](../EXPERIMENT_READINESS_AUDIT.md) records the seed-field repair and the remaining experiment boundary.
