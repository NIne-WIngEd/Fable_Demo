# FloRA

An experiment for one Fable claim: after a host corrects a relevant belief or preference and a decision has an outcome, does Fable's later **native judgment** change for the right reason, while keeping its evidence trail? The experiment will compare that behavior with a strong general model plus memory, using the same available history and response budget. Then a small builder must reproduce the capability for another isolated host.

The [frozen experiment goal](docs/EXPERIMENT_GOAL.md) defines the product comparison, mechanism ablation, cross-host builder test, and evidence rules. Numerical acceptance thresholds will be preregistered before the final evaluation.

Material build decisions and failures are captured as [FBM process seeds](docs/fbm-seeds/README.md) using the A.L.I.C.E. builder trace schema. They teach the future builder how this infrastructure was constructed; they are not trained builder weights.

**Status: infrastructure under construction.** There is no conversational demo, trained personality model, Memory Formation Model (MFM), builder, qualified behavioral result, or consumer release here yet. The personality and MFM are being developed in separate workstreams. This repository builds the other demo infrastructure and will integrate their qualified outputs when ready.

## Architecture boundary

The active path follows the A.L.I.C.E. Stage G–J successor design. The old Phase 2 runtime is void as an implementation basis for this demo. It was removed from `main`; the historical work remains in [commit `aad9ad4`](https://github.com/NIne-WIngEd/FloRA/tree/aad9ad46bd0def74755728ed967d5a003f66e93b). Passing tests there never qualified this experiment.

The [alignment and build map](docs/FloRA_ALIGNMENT.md) names the selected planes, what can be built independently, and the evidence required. For the portions exercised by the claim, we use the same logical contracts **and physical engines** chosen for the full system. We will not substitute a convenient local database and count its result as proof for XTDB, KurrentDB, Qdrant, or any other selected engine.

## What is implemented here

- `selected/object_store.py` starts the encrypted, content-addressed raw object plane. It keeps host-held keys out of stored objects, confines deduplication to the host and encryption domain, and verifies ciphertext on reads. The local placement implements an opaque object backend; S3-compatible placement, key custody, lifecycle deletion, and backend qualification are still open.
- `selected/experience.py` maps A.L.I.C.E.'s metadata-only Experience envelope to a scoped KurrentDB stream with expected-revision writes, deterministic event IDs, and verified replay. The Docker integration gate now exercises this against KurrentDB 26.1.1, including retry behavior, stale-revision rejection, replay, and persistence across a service restart.
- `selected/edge_ingress.py` buffers metadata-only device events in a host-scoped NATS JetStream stream and acknowledges delivery only after replay or an expected-revision KurrentDB commit. The current slice tests one device, duplicate delivery, and cross-host rejection; device-clock conflicts, durable recovery, and multi-device reconciliation remain open.
- `selected/claims.py` places validated A.L.I.C.E. claim identities, immutable evidence relations and versions, and current projections in XTDB v2. A committed version must cite its exact KurrentDB Experience source; current projection writes check the expected head. The Docker gate exercises valid-time correction reads, cross-host isolation, concurrent immutable writes, and restart persistence.
- `selected/formation_input.py` binds a manifest to same-host KurrentDB replay and verified raw content for the separately developed MFM. `selected/formation_gate.py` checks a proposal against independently registered evidence and leaves it for adjudication; it grants no claim authority or owner authentication on its own.
- `selected/source_native.py` reads exact evidence for an active current claim across XTDB, KurrentDB, and the encrypted object plane. It checks host scope, relation targets, replayed event IDs, and raw content digests; a caller must still decide whether it is authorized to expose plaintext to a model.
- `selected/decision_outcome.py` records a supplied verdict with verified source event IDs and an encrypted payload, then links a later independently sourced outcome observation to that decision in KurrentDB. It records lineage; it does not qualify the producer, judge correctness, or automatically revise personal state.
- `selected/vector_recollection.py` indexes a source-verified current claim in Qdrant by host and embedding generation. Query results are candidates checked against XTDB; reconciliation removes obsolete or unbound points after a correction. The read-time check remains necessary while cleanup lags. Synthetic vectors test the selected engine and authority filter, not semantic retrieval quality.
- Synthetic component tests and real-backend integration tests cover these boundaries. They are infrastructure evidence, not a Fable capability or behavioral result.

Owner-source authentication, complete conflict/deletion lineage, multi-device reconciliation, episodes, graph, qualified semantic/vector retrieval and wider source retrieval, Context Planner, personal-state projections, outcome revision, and workflow/recovery path remain open. No model or behavioral score is being inferred from the backend result. See the [backend integration handoff](docs/BACKEND_INTEGRATION_HANDOFF.md) for the exact green boundary.

## Dependencies and evidence gates

1. Build and verify the selected raw/event/claim authority path: encrypted objects, KurrentDB Experience, XTDB v2 Claims, and deterministic gate. Link each accepted claim to its exact source and preserve corrections, bitemporal queries, and deletion lineage.
2. Build the episode, graph, vector, source-native, context selection, host/relationship/self, and outcome paths needed for the chosen decision. Use the selected engines and record what evidence the judgment actually consumed.
3. Connect learned MFM formation and the separately qualified personality model. Neither is implemented by a hand-written stand-in in this repository.
4. Freeze synthetic histories and held-out decisions. Compare relevant and irrelevant judgment changes against a strong comparator with equal evidence, and test replay, isolation, latency, correction, and deletion. This is an experiment, not customer traction.
5. After that claim holds, have a small FBM rebuild the qualified slice for a second consenting or fictional host and test transfer across hosts.

The component checks run with Python 3.11+, `cryptography`, `kurrentdbclient~=1.3`, and A.L.I.C.E.'s product-neutral scope and formation contracts from `research/mfm-foundation-20260923@00583fb2`:

```bash
PYTHONPATH=../ALICE/src:src python -m unittest discover -s tests -v
```

Use synthetic data only. A repeatable Docker environment for the first selected backends now lives in `compose.integration.yml`. The GitHub Actions gate starts real KurrentDB, XTDB, NATS JetStream, and Qdrant services, runs the integration tests, restarts the authority services, verifies persistence, captures logs, and tears the stack down. For local use:

```bash
python -m pip install -e '.[backends]'
docker compose -f compose.integration.yml up -d
PYTHONPATH=../ALICE/src:src python -m unittest discover -s tests/integration -v
docker compose -f compose.integration.yml down -v
```

The workflow pins the A.L.I.C.E. contract checkout used by this demo. Do not substitute Phase 2 or a convenience database for the selected path.
