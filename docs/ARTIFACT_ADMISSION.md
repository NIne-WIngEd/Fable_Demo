# Artifact admission and runtime wiring

FloRA can now register externally qualified model artifacts in the selected XTDB stack and recover their role bindings after a process restart. This registers references; it does not load a checkpoint, run a model or establish learned capability.

**Actual MFM and personality export adapters remain pending.** Neither role is made ready by a caller-provided checkpoint hash. The integration tests use fictional bytes and an independent test signing key only to check the registry, custody and admission rules.

## What is bound

| Field | Purpose |
|---|---|
| Exact product, host, schema and encryption scope | An artifact cannot be admitted into another person's registry |
| Role: `memory_formation` or `personality_judgment` | Qualification for one role cannot silently authorize the other |
| Repository, branch and exact source commit | Identify the producer that exported the artifact |
| Checkpoint byte count and SHA-256 | Check the actual local bytes without deserializing them |
| Input and output contract IDs and SHA-256 values | Bind the interfaces the external producer and runtime actually qualified |
| Independent qualification ID, qualifier and exact receipt bytes | Preserve the external qualification evidence in encrypted custody |
| Predecessor artifact and role generation | Prevent stale activation and preserve immutable admission history |

The scope and authority namespace determine every registry key. Admissions and qualification IDs are immutable. Current role bindings use a compare-and-set transaction against the previous generation. Replaying an old admission returns its old receipt and does not reactivate it over a newer generation.

The manifest contains artifact references, not the host's absolute checkpoint path. Qualification receipt bytes use FloRA's existing encrypted object plane; XTDB holds the scoped manifest and custody references. A binary checkpoint is only read as bytes for hashing.

## Qualification is an external authority boundary

`ArtifactQualificationVerifier.verify(manifest, receipt)` must be supplied by trusted runtime configuration. It must validate the producer's actual receipt, its authentic issuing authority, the exact manifest binding, capability permission for the selected role and compatibility with the exact input/output contract references. Any current withdrawal of qualification must be respected when the verifier is called again.

`VerifiedArtifactQualification` is the result of that adapter, not a receipt format a caller can use to qualify itself. A checkpoint receipt, training status, matching schema or self-declared `qualified` flag is insufficient. The registry refuses unsigned or unauthorized receipts when the supplied verifier refuses them; it does not manufacture a settled MFM/EIPM qualification protocol.

Contract hashes must come from the external producer's actual exported interfaces. Inventing a string and hashing it does not establish compatibility. In particular, an eventual personality adapter must qualify the host-specific judgment export, rather than treating an N0 research checkpoint as a complete personal model. If an actual export contains several model/state files, its adapter must bind the full export's required files and provenance before authorizing a hashable checkpoint package. This generic file boundary does not currently interpret multi-file training checkpoints.

## Runtime binding

`XTDBModelArtifactRegistry.admit(...)` verifies local checkpoint bytes and the independent receipt, stores the encrypted receipt and atomically registers an immutable admission plus the next role generation. It expects a standalone XTDB connection transaction; callers must not wrap it in a nested transaction that requires unsupported XTDB savepoints.

`resolve_current_for_runtime(...)` retrieves the current role from XTDB, recovers its encrypted receipt without an in-memory qualification map, rechecks the independent qualifier, compares the caller's exact expected interfaces and hashes the actual local checkpoint again. Missing or changed checkpoint bytes, changed qualification evidence, an unqualified role, another host/namespace and a changing role head all prevent a runtime wiring result.

The returned `RuntimeWiringManifest` is a checked reference set. There is no inference implementation here. The eventual inference adapter must consume the same bound bytes safely and account for changes between binding and use. Existing supplied-output recording paths remain declarations until they are explicitly wired to this qualification boundary; the registry's existence alone does not qualify their outputs.

## Sources and validation

- A.L.I.C.E. MFM `4f287a488bc908bd04f99255ee01b794bacba50b`: `docs/MFM_LEARNING_ADMISSION_2026-09-29.md` and `docs/MFM_FULL_CAPABILITY_BUILD_PLAN_2026-09-29.md`. These distinguish formation contracts, supplied candidates and diagnostic fixtures from trained, promoted MFM capability.
- A.L.I.C.E. personality `5e29f7f69ba4a5d031c7036639b67bebbcdc0bd2`: `docs/eipm/EIPM_ROLE_AND_OBJECTIVE_CONTRACT_v1.0.md`, `configs/eipm/n0/n0_v02_full_envelope_checkpoint_contract_v1.json` and `scripts/eipm/n0/export_n0_v02_initial.py`. The checkpoint contract explicitly says its receipt is not N0 completion; the initial export explicitly says random initialization with no model training.
- [Architecture audit](ARCHITECTURE_READINESS_AUDIT.md): artifact lineage is an independent infrastructure gap, while learned MFM/personality outputs remain model dependencies.
- `tests/test_artifact_registry.py`: byte integrity, independent signature authority, exact scope/role/source/interface binding and denial checks.
- `tests/integration/test_artifact_registry.py`: real XTDB persistence/recovery, encrypted receipt custody, role generations, stale activation, immutable IDs and missing/tampered checkpoints. Until this run passes against the selected backend, it is an implemented check rather than backend qualification evidence.

No test in this slice certifies personality judgment, learned formation, causal personal development or a successful FloRA experiment.
