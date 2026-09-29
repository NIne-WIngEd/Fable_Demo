# Fable Demo

A work-in-progress prototype for one Fable capability. It is currently a narrow experience and explicit-memory plumbing slice over A.L.I.C.E.'s released stores. The personality model is being built separately. **The Fable demo has not been built end to end.**

## Built now: the experience path

`fable-runtime` can create an isolated host vault, locally seal an observation, capture it in A.L.I.C.E.'s content-addressed Raw Buffer, and append a linked metadata event to A.L.I.C.E.'s Experience Ledger. It reopens across processes, verifies both stores, and finishes a ledger append if a process stopped after raw capture. Host, assistant-self, and relationship observations are distinct. Corrections and outcomes point to a prior observation of the right kind.

This is a working infrastructure slice, **not yet a conversational Fable**. The demo key currently lives in a permission-restricted file in the host vault; production Fable needs OS-backed key custody and a full retention/deletion lifecycle. The runtime is single-writer and does not claim cross-store atomic transactions. The Phase 2 ordinary Memory Core stores plaintext inside the private vault. **Use synthetic data only in this demo.**

```bash
git clone https://github.com/NIne-WIngEd/A.L.I.C.E.git
git -C A.L.I.C.E checkout 5f9b9ccb2628eb2a5512d8624b9a78bcc9c7fe38
git clone https://github.com/NIne-WIngEd/Fable_Demo.git
python -m pip install -e Fable_Demo
PYTHONPATH=A.L.I.C.E/src python -m fable_demo.runtime_cli init /tmp/my-fable-demo
printf 'I prefer a written brief before a meeting.\n' | PYTHONPATH=A.L.I.C.E/src python -m fable_demo.runtime_cli record /tmp/my-fable-demo --kind statement --subject host
PYTHONPATH=A.L.I.C.E/src python -m fable_demo.runtime_cli inspect /tmp/my-fable-demo
```

Use a vault path outside either repository. `history` shows metadata; `history --reveal` explicitly decrypts text.

For a recorded host statement, copy its returned `logical_id` into `stage --id ID --key deep_work --category goal`. Staging creates a non-authoritative candidate. `confirm --candidate ID` promotes it only after A.L.I.C.E.'s deterministic assessment. `memory --key deep_work` reads the current confirmed claim. For a correction, record it with `--kind correction --relates-to ORIGINAL_LOGICAL_ID`, then run `correct --id CORRECTION_LOGICAL_ID --key deep_work --category goal`; confirm the candidate with `--target-memory ORIGINAL_MEMORY_ID`. This invokes A.L.I.C.E.'s transition-aware correction path and keeps the older record in history.

`memory-history --key deep_work` shows current and superseded versions with source links. `state --host-key deep_work` assembles current host claims and their correction history, separately labeled assistant-self and relationship observations, and linked decisions and outcomes. It is an evidence packet for the separately built personality model. It makes no judgment and does not claim those observations are learned self or relationship models.

`formation-context --id OBSERVATION_ID --host-key deep_work` assembles a bounded packet for the future Memory Formation Model: the source observation, its direct parent when linked, and only the current host claims explicitly selected by the caller. It carries event and raw-reference IDs and a packet fingerprint. It does not extract or promote a claim. This packet describes current state at assembly time, not an as-of historical replay.

## Actual build status

| Component | Status | Boundary |
| --- | --- | --- |
| Raw experience capture and ledger | Thin slice built | One host, single writer, synthetic data; reuses A.L.I.C.E.'s released stores. |
| Explicit host memory and correction | Thin slice built | Operator supplies a key and confirmation. No learned formation or automatic understanding of raw data. |
| State and formation packets | Thin slice built | Caller selects host keys. Self and relationship entries are observations, not learned models. |
| Personality and native judgment | Not integrated | A separate workstream is building the model. There is no live decision loop here. |
| Memory Formation Model and adaptive retrieval | Not built | No autonomous candidate extraction, topic selection, or relevance planning. |
| Learned host, assistant-self, and relationship state | Not built | No demonstrated personal development or causal influence on judgment. |
| Outcome-driven revision | Not built | The ledger can link a decision and its outcome; the outcome does not yet change future judgment. |
| Fable Builder Model and second-host transfer | Not built | No automatic model building from another person's data. |
| Conversational product and privacy lifecycle | Not built | No conversation controller, feature API boundary, owner-facing app, production key custody, or complete deletion/rollback. |

For the **first demo claim**, the next work is to establish a narrow learned state and native judgment loop, integrate the separate personality model, make corrections or outcomes change later behavior for a justified reason, and compare that behavior with a strong baseline on the same synthetic history. The second part would ask a small builder to reproduce the capability for another consenting host. Merely attaching the personality model to today's packet will not finish the demo.

A.L.I.C.E.'s Phase 2 SQLite Memory Core is the current released reference authority. Its broader destination considers an event fabric, claim authority, graph, vector, and workflow planes. This demo uses the actual implemented kernel stores for its first component. A passing test on a reference backend will not be presented as proof that every future backend or the complete Fable architecture works.

## Earlier evaluation scaffolding

The files below were prepared before the persistent runtime. They remain diagnostics and future trial material; they are not a finished demo or a YC performance result.

## The first claim

When a person corrects something Fable remembers, can its memory path retrieve the current statement, preserve the source trail, and avoid using a future correction to answer an earlier question?

The first fixture contains synthetic statements and later corrections. Every evaluation question has a timestamp and frozen expected and forbidden evidence IDs. Each chronological cutoff opens a fresh A.L.I.C.E. Memory Core, writes memories and corrections through its public APIs, and compares its authoritative temporal resolver with its existing lexical search. The metadata events are also written through the real hash-chained Experience Ledger. The ledger never receives the fixture's plaintext.

Two raw-history comparators see the same visible statements, topic, search term, and one-evidence budget: lexical overlap and a stronger most-recent rule. This is a plumbing and correction test; it does not test Fable's personality, decisions, experience-driven improvement, or conversations.

## Reproduce

Use Python 3.11+ and a checkout of [`NIne-WIngEd/A.L.I.C.E`](https://github.com/NIne-WIngEd/A.L.I.C.E) at commit `5f9b9ccb2628eb2a5512d8624b9a78bcc9c7fe38`. From a directory containing both checkouts:

```bash
git clone https://github.com/NIne-WIngEd/A.L.I.C.E.git
git -C A.L.I.C.E checkout 5f9b9ccb2628eb2a5512d8624b9a78bcc9c7fe38
git clone https://github.com/NIne-WIngEd/Fable_Demo.git
PYTHONPATH=A.L.I.C.E/src:Fable_Demo/src python -m fable_demo.cli Fable_Demo/fixtures/correction_v1.json
PYTHONPATH=A.L.I.C.E/src:Fable_Demo/src python -m fable_demo.cli Fable_Demo/fixtures/longitudinal_v1.json
PYTHONPATH=A.L.I.C.E/src:Fable_Demo/src python -m fable_demo.cli Fable_Demo/fixtures/outcome_chain_v1.json --at 2025-03-10T09:00:00Z --topic work_style --question "Should I accept another recurring evening meeting?"
PYTHONPATH=A.L.I.C.E/src:Fable_Demo/src python -m unittest discover -s Fable_Demo/tests -v
```

All live stores are created in a temporary directory outside either repository. The committed fixture is entirely synthetic.

## Status and next evidence gate

The initial three-case fixture passes on A.L.I.C.E.'s temporal resolver and lexical search. Raw lexical overlap misses two corrections, while the simple most-recent comparator also passes all three. **This is not evidence that Fable beats a strong memory baseline.** It establishes a reproducible, production-aligned path for the next experiment.

The separate `outcome_chain_v1.json` fixture exercises the real Experience Ledger's decision-to-outcome references and integrity check. It does **not** claim that an outcome has changed Fable's judgment. That still requires the qualified personality model and a tested learning path.

The `--at`, `--topic`, and `--question` form prepares a bounded evidence packet. It retrieves current source-linked memories through A.L.I.C.E.'s temporal resolver and authorized content service, including the goal, earlier decision, and observed outcome in the synthetic example. The packet makes no recommendation. The caller supplies the topic key; discovering that key from an open-ended conversation is still unresolved.

`fixtures/frozen_trials_v1.json` contains two versioned evidence packets: one before the outcome and one after it. Each has a SHA-256 fingerprint. When the qualified personality model is ready, give it the packet, not the trial spec or scoring rubric. Give a general-model-plus-memory comparator the same packet and response budget. `fable_demo.blind.pair` refuses missing trials or packet-hash mismatches and produces a review sheet with a separate answer key. Human reviewers must rate the behavior; this repository does not invent model responses or assign judgment scores.

Freeze the review criteria before seeing responses: [`rubric/behavior_v1.md`](rubric/behavior_v1.md). The rubric checks how Fable behaves and speaks, including whether it knows when to disagree, rather than scoring only the final yes or no.

`longitudinal_v1.json` freezes 20 questions over four synthetic topics and 20 months. Its generator is in `scripts/generate_longitudinal_fixture.py`. With the topic key supplied, the authoritative temporal resolver finds all 20 current memories. The existing lexical search misses 6 because it ranks a small global candidate set before filtering old or other-topic records. The simple recency comparator finds all 20. This is a retrieval gap to address in A.L.I.C.E.'s serving path, not evidence of an end-to-end advantage. Generated scenarios are also too templated to serve as independent product evidence.

Next, freeze longer synthetic histories and held-out decisions with conflicting roles, changing preferences, corrections, and later outcomes. Connect the qualified personality model's native judgment interface without retraining or replacing it here. Compare against a strong general-model-plus-memory baseline on the *same* history, evidence access, and response budget; assess the behavior and reasons, not just keyword retrieval. Only if that claim holds, add a small Fable Builder Model path for other consenting people's data and test transfer to new hosts. No synthetic history will be presented as a real user's result.

The A.L.I.C.E. architecture keeps logical authority separate from its physical implementation. Its present SQLite Memory Core and Experience Ledger are valid reference backends; a vector or graph engine is not a settled requirement for this first claim. This demo calls their real APIs instead of replacing their behavior with its own database or toy retrieval layer.

Before using other hosts' data, the A.L.I.C.E. memory contract's `rayan_statement` and `rayan_confirmed` fields need a product-neutral host mapping. This is a portability gap, not a demonstrated multi-user builder.
