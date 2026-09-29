# Selected-backend integration handoff — 2026-09-28

This note is the takeover point after provisioning the first Docker-capable successor-fabric environment for Fable Demo.

## Authority boundary

- A.L.I.C.E. Phase 2 is not an active implementation basis here.
- The demo follows the Stage G/H/I/J successor direction and selected-stack-first doctrine.
- Runtime contracts are checked out from A.L.I.C.E. commit `00583fb25fbe07c1452519992de2bc8055dcebd5` because it contains the product-neutral Experience, Claim, Memory, and MFM formation contracts required by this slice.
- The physical backends in this gate are the selected engines, not local stand-ins.

## Docker environment now available

`compose.integration.yml` starts:

- KurrentDB `docker.kurrent.io/kurrent-latest/kurrentdb:26.1.1` on port 2113.
- XTDB v2 `ghcr.io/xtdb/xtdb:2.1.0` on pgwire port 5432 and HTTP port 8080.
- Named volumes preserve service state across the workflow's explicit restart.
- The workflow destroys the volumes at final teardown so CI runs stay isolated.

The workflow verifies Docker and Docker Compose, installs `.[backends]`, runs component tests, boots both services, waits for their health endpoints, executes real-backend tests, writes persistence probes, restarts both services, verifies the probes, uploads logs, then tears everything down.

## Green receipt

Implementation head: `c3b7170eb23a2e6092e1b5b0aea5e0a008c55ba3`

GitHub Actions run: `36506427726`

Result: **SUCCESS**

Evidence artifact: `selected-backend-evidence`, artifact ID `11007725857`, SHA-256 `f635c4cd385341ddfc9dbd040171fa61de2c023bb826372af149869417d0042e`.

The green run proves this narrow infrastructure boundary:

1. KurrentDB accepts the Fable Experience envelope with expected revision semantics.
2. Retrying the same immutable event is idempotent.
3. A stale expected revision is rejected.
4. Experience replay returns the expected ordered events.
5. KurrentDB probe state survives an explicit service restart.
6. XTDB stores project-owned ClaimIdentity, ClaimVersion, and CurrentClaimProjection records.
7. XTDB valid-time reads return the pre-correction projection before the correction date and the revised projection afterward.
8. Scoped row identity prevents another host from reading the first host's current claim through the adapter.
9. XTDB probe state survives an explicit service restart.
10. The existing component contract tests remain green.

A real XTDB pgwire incompatibility was found during qualification: Psycopg sends ordinary Python strings with unknown OID 0, while XTDB requires typed non-null DML parameters. The adapter now installs a connection-local TEXT dumper so strings carry the PostgreSQL text OID. This was fixed from observed service behavior, not hidden with an emulator.

## What this does NOT prove

Do not call this full Stage G qualification or a Fable capability result. Still open:

- deterministic `MemoryProposalBundle -> Claim Authority` gate;
- exact evidence-relation persistence from proposal to accepted/revised claim;
- complete conflict/adjudication cases;
- projection rebuild from authority history;
- deletion, cryptographic erasure and influence-removal lineage;
- NATS JetStream ingress and device reconciliation;
- governed episodes;
- LadybugDB/NebulaGraph and Qdrant recollection planes;
- Temporal workflow/recovery path and local cache semantics;
- Context Planner and consumed-evidence receipts;
- host/relationship/self development and outcome revision;
- MFM integration;
- personality/native judgment integration;
- held-out behavioral comparator;
- FBM transfer to a second isolated host.

## Immediate next engineering slice

Continue the **Authority** lane before expanding sideways:

1. Implement a deterministic formation/adjudication gate that accepts the separately learned MFM proposal contract but cannot let a proposal make itself authoritative.
2. Persist evidence relations and exact source IDs with every accepted/revised claim.
3. Add expected-current-version/idempotency protection for claim writes.
4. Exercise correction, conflict, supersession, as-of reads, projection rebuild and deletion lineage against the real XTDB service.
5. Tie accepted claim commits back to the corresponding KurrentDB Experience positions.
6. Only after that boundary is green, move to the next service needed by the causal demo.

Keep tests synthetic. Do not introduce personality or fake MFM weights into this repository while those workstreams are separate.

## Reproducing the current gate

```bash
python -m pip install -e '.[backends]'
docker compose -f compose.integration.yml up -d

# The workflow checks out the pinned A.L.I.C.E. contract tree at alice-reference.
PYTHONPATH=alice-reference/src:src python -m unittest discover -s tests -v
PYTHONPATH=alice-reference/src:src python -m unittest discover -s tests/integration -v

PYTHONPATH=alice-reference/src:src python scripts/backend_restart_probe.py write
docker compose -f compose.integration.yml restart kurrentdb xtdb
# wait until both health endpoints are ready
PYTHONPATH=alice-reference/src:src python scripts/backend_restart_probe.py verify

docker compose -f compose.integration.yml down -v
```

For CI, `.github/workflows/demo.yml` is the authoritative repeatable receipt.
