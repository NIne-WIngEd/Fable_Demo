# Exact evidence graph in LadybugDB

The embedded graph contains only host-scoped keys for current Claim versions and Experience events. A `FloRACites` edge carries the exact registered relation ID and type. It stores neither private source content nor a new fact. The selected engine is LadybugDB 0.21.0, with a separate database path per host.

Projection starts only after `read_current_sources` verifies XTDB, KurrentDB, and encrypted raw content. A graph query returns candidate claims sharing a specified source event. Every hit is rechecked against XTDB's current version, all evidence relations, and raw source bytes before context can use it. Thus an obsolete version remains invisible immediately after a correction or source quarantine, even if graph cleanup has not run. `prune_noncurrent` removes obsolete derived claim nodes and is safe to retry.

This deliberately tests **one selected physical graph view**. It does not infer entities, episode boundaries, causality, relevance, or semantic bridges. A graph route in `ContextPlan` is explicit and local policy must permit its source event. Learned relation formation, adaptive traversal, NebulaGraph scale-out, and graph latency remain open.
