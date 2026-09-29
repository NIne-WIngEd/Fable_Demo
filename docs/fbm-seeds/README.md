# FloRA builder seeds

FloRA captures one compact, reusable process trace per material infrastructure or experiment-design step. These rows follow A.L.I.C.E.'s [FBM trace schema v0.1](https://github.com/NIne-WIngEd/A.L.I.C.E/blob/fable-builder-model/docs/fable-builder/TRACE_SCHEMA_v0.1.md) and parallel-capture rule. The matching JSONL is copied into the `fable-builder-model` branch so the builder workstream can use it alongside A.L.I.C.E. construction traces.

Each trace records an observable operation, safe references, constraints, validation, and a failure lesson. It is a seed for later FBM training or evaluation, not FBM weights and not a claim that FloRA can already build itself. Private host content, credentials, hidden reasoning, and raw model output stay out of this public record.

Capture new milestones in the same schema as work proceeds. A failed test and its repair should remain linked. Logging must not delay the actual build.
