# Fable Demo

One narrow test of Fable's personal foundation, built on the same A.L.I.C.E. memory and Experience Ledger code intended for the full product. This repository does **not** train a substitute personality model. That model is being developed separately and will connect here after it qualifies.

## The first claim

When a person corrects something Fable remembers, can its memory path retrieve the current statement, preserve the source trail, and avoid using a future correction to answer an earlier question?

The first fixture contains synthetic statements and later corrections. Every evaluation question has a timestamp and frozen expected and forbidden evidence IDs. Each chronological cutoff opens a fresh A.L.I.C.E. Memory Core, writes memories and corrections through its public APIs, rebuilds its actual private lexical index, and searches with its existing temporal and correction filters. The metadata events are also written through the real hash-chained Experience Ledger. The ledger never receives the fixture's plaintext.

Two raw-history comparators see the same visible statements, topic, search term, and one-evidence budget: lexical overlap and a stronger most-recent rule. This is a plumbing and correction test; it does not test Fable's personality, decisions, experience-driven improvement, or conversations.

## Reproduce

Use Python 3.11+ and a checkout of [`NIne-WIngEd/A.L.I.C.E`](https://github.com/NIne-WIngEd/A.L.I.C.E) at commit `5f9b9ccb2628eb2a5512d8624b9a78bcc9c7fe38`. From a directory containing both checkouts:

```bash
git clone https://github.com/NIne-WIngEd/A.L.I.C.E.git
git -C A.L.I.C.E checkout 5f9b9ccb2628eb2a5512d8624b9a78bcc9c7fe38
PYTHONPATH=A.L.I.C.E/src:Fable_Demo/src python -m fable_demo.cli Fable_Demo/fixtures/correction_v1.json
PYTHONPATH=A.L.I.C.E/src:Fable_Demo/src python -m unittest discover -s Fable_Demo/tests -v
```

All live stores are created in a temporary directory outside either repository. The committed fixture is entirely synthetic.

## Status and next evidence gate

The initial three-case fixture passes on A.L.I.C.E.'s memory path. Raw lexical overlap misses two corrections, while the simple most-recent comparator also passes all three. **This is not evidence that Fable beats a strong memory baseline.** It establishes a reproducible, production-aligned path for the next experiment.

Next, freeze longer synthetic histories and held-out decisions with conflicting roles, changing preferences, corrections, and later outcomes. Connect the qualified personality model's native judgment interface without retraining or replacing it here. Compare against a strong general-model-plus-memory baseline on the *same* history, evidence access, and response budget; assess the behavior and reasons, not just keyword retrieval. Only if that claim holds, add a small Fable Builder Model path for other consenting people's data and test transfer to new hosts. No synthetic history will be presented as a real user's result.

The A.L.I.C.E. architecture keeps logical authority separate from its physical implementation. Its present SQLite Memory Core and Experience Ledger are valid reference backends; a vector or graph engine is not a settled requirement for this first claim. This demo calls their real APIs instead of replacing their behavior with its own database or toy retrieval layer.
