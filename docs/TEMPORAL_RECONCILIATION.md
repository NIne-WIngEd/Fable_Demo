# Temporal reconciliation for derived claim indexes

After an XTDB Claim head changes, a caller can submit a metadata-only cleanup request to `ReconcileDerivedClaimWorkflow` on a self-hosted Temporal service. The request binds the host authority scope, claim ID, and exact projection digest. It contains no private content. The deterministic workflow ID makes duplicate starts address the same authority generation.

Separate activities prune Qdrant and LadybugDB. Each verifies the exact current XTDB head before it operates. Temporal retries a failed activity without repeating a previously completed activity. Both pruning methods are idempotent, and read-time filters continue to reject obsolete or quarantined entries even while cleanup is pending. A later Claim head needs a new workflow request.

The component test starts a real local Temporal dev server, fails the graph activity once, and verifies retry without repeating the vector activity. The selected-backend test runs the activities against real XTDB, Qdrant, and LadybugDB after a claim quarantine. The local test server uses in-memory persistence. This does not qualify server restart recovery, long running missions, complete erasure, model unlearning, or a production deployment topology.
