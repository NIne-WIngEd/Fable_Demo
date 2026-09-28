# Fable Demo

One narrow test of Fable's personal foundation, built on the same A.L.I.C.E. memory and Experience Ledger code intended for the full product. This repository does **not** train a substitute personality model. That model is being developed separately and will connect here after it qualifies.

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
