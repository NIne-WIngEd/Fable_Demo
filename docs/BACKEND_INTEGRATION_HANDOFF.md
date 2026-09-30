# Selected-backend integration handoff — 2026-09-28

This note is the takeover point after provisioning the first Docker-capable successor-fabric environment for FloRA.

## Expanded gate status — 2026-09-30 UTC

The repaired checkpoint `950fe8321902b681ae798f455779e281985d04a0`
passed all 524 component tests in
[run 36742030115](https://github.com/NIne-WIngEd/FloRA/actions/runs/36742030115).
Its core group passed 29 of 30 physical cases, including the actual terminal
XTDB source fence. The comparator's two expected successes instead exceeded
its **10-second** fixture response budget. Core restart probes were skipped.
The chronology and native groups reached their one-hour job caps. Chronology
completed the coordinator case; no internal preregistration stage can be
established from that cancelled log. Native completed two lineage cases but
failed comparison and errored in pilot cases before cancellation. Passive-reader
and writer-fault cases were unreached. Neither group has a qualifying receipt.

The preceding native job reached the one-hour job cap before the final unittest
summary. Two lineage cases passed, but earlier native and pilot errors had no
final traceback, and the passive-reader and writer-fault cases were unreached.
The next runner prints each failure immediately and completed-case durations.
Chronology prints fixed-label milestones
only after their actual stages succeed; these diagnostics contain no host
payloads or model outputs.

The first split run,
[36753308831](https://github.com/NIne-WIngEd/FloRA/actions/runs/36753308831)
at `3b1183534eef8894db6f66a4e65d55953a838a60`, exposed crashes coinciding with
the new harness diagnostic: native, transport, lineage, core and both history
jobs exited with segmentation faults during timed stack dumps. Those exits
establish no result for their unfinished cases or response budgets. Chronology
completed cohort, recipe, anchor and original-input registration, but published
no BEFORE capture and reached no later seal, update or final binding. Timed
stack dumping has been removed for the retry; causation remains unproven.
the selected backends were still healthy after the transport crash. The actual
PGconn watchdog case passed in 0.866 seconds. The passive-reader case stopped
on a missing `preregistration_sha256` field in its explicitly unanchored fixture;
that fixture now supplies `None`. Fresh final-authority checks remain intact.

Controlled call-count profiles expose repeated immutable data reopening and
metadata traversal inside nested fresh authority checks. Repairs authenticate
held material on entry, then continue to check current permission and source
metadata at every private boundary. Observations are confined to one guard and
the terminal current-row check remains mandatory. Lower controlled query counts
are not physical timing or learned-behavior evidence.

The follow-up [run 36738250266](https://github.com/NIne-WIngEd/FloRA/actions/runs/36738250266)
at `432e7dbdd08cb0b76864c0351476302b0cf8de4c` passed all 523 component tests.
Its core group passed 26 of 30 physical tests; four failed because XTDB rejects
a cast parameter in the terminal permission query's `LIMIT` clause. The history
group passed the coordinator gate; the other three tests stopped at initial
BEFORE capture on the same query error. They did not establish the later
capture/update/final-seal timeline. Core restart probes were skipped.

The repair renders only the validated sampled-row count plus one as an integer
literal. Every source value remains bound, and the terminal statement still
checks the complete current metadata together. A separate reproduced native
watchdog exit race is fixed by observing expiry under the watchdog lock before
disarming it. Focused regressions pass; these repairs require a new physical
run. Native results and the 60-second response budget remain unqualified until
their exact-commit gate completes.

The historical receipts below qualify their own earlier checkpoints. They do
not qualify the expanded two-stage experiment workflow. Run
[36660341118](https://github.com/NIne-WIngEd/FloRA/actions/runs/36660341118)
at `f94a020b43aaaaa4b614caa826d398b64a2067df` passed component checks but
failed its physical suite: 39 tests, two failures and fourteen errors. Restart
steps were skipped. The failures exposed an XTDB read-first transaction before
runtime DML, private-wrapper copying, earlier formation refusal types and a
replacement-artifact fixture. Repairs require another exact-commit engine run.

The current contract reference is
`research/mfm-foundation-20260923@4f287a488bc908bd04f99255ee01b794bacba50b`
(formation schema 1.2.0). The workflow now runs component contracts and exhaustive
`core`, `transport`, `native`, `lineage`, `readers`, `history` and `history-routes`
engine groups in parallel. This separates the long lineage and chronology cases
from the passive-reader, writer-fault and restart gates. New integration modules
default to `core`.
Discovery rejects duplicate identities or import failures. Every test must run
exactly once across the groups. The core group also runs actual storage and
persistent Temporal restart probes. All jobs must pass at the same commit.

Response budgets stay exactly as registered: the standalone comparator fixture
uses 10 seconds; the newer native/preregistered fixture declares 60 seconds.
The CI job cap stays one hour. Successful fixture wiring cannot replace a timing
receipt, actual producer exports or learned behavior evidence. No personality
or MFM is built by these infrastructure tests.

## Historical checkpoint — 2026-09-29

That checkpoint's green receipt is [run 36574921127](https://github.com/NIne-WIngEd/FloRA/actions/runs/36574921127). Since the original handoff, the selected-backend gate has also passed Qdrant current-claim indexing, source-bound authority filtering and obsolete-point cleanup; a pending NATS event across restart; separate XTDB host/relationship/assistant-self candidate state; exact KurrentDB approval and activation with a synthetic verifier; and an outcome-linked revision that stays a candidate while the older approved state remains active. See the [alignment map](FloRA_ALIGNMENT.md) and [candidate-state boundary](PERSONAL_STATE_CANDIDATES.md) for scope and gaps. This is infrastructure evidence, not a trained memory, native judgment, or builder transfer result.

The earlier receipts and original engineering checklist below are preserved as historical checkpoints; their "next" list no longer describes every completed slice.

The original green receipt below is historical. The later [run 36541803371](https://github.com/NIne-WIngEd/FloRA/actions/runs/36541803371) passed at commit `1fba75318b807c95312104e44bcaaf2741f0945d`. It additionally exercises immutable evidence relations, a one-winner XTDB relation race, formation input from actual KurrentDB replay, a deterministic pre-adjudication gate, source binding of a claim version to its replayed event position, and expected-head current projection writes. The restart probe is read before shutdown and then polled for at most 30 seconds after restart. One prior run failed an immediate XTDB post-health read; its rerun passed, so recovery timing is plausible but not proven as the root cause.

Owner-source authentication, full conflict adjudication, deletion/influence removal, projection rebuild, and all later planes remain open. A synthetic owner-source verifier is not authentication. This checkpoint is backend integration evidence, not a qualified memory or behavioral result.

The subsequent [run 36542838235](https://github.com/NIne-WIngEd/FloRA/actions/runs/36542838235) passed at `489bce9099008074b12e1b537b77b5520fc12aa1`. It adds exact source reads spanning XTDB, KurrentDB replay, and encrypted raw objects across an as-of correction, plus a real NATS JetStream metadata-only intake that commits to KurrentDB before acknowledging. This is one device/duplicate-delivery evidence. It does not establish durable NATS recovery, device-clock conflict policy, multi-device reconciliation, or permission to disclose retrieved plaintext to a model.

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

- authenticated owner-source verification and an end-to-end `MemoryProposalBundle -> adjudication -> Claim Authority` commit;
- complete proposal-to-claim evidence lineage;
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
PYTHONPATH=alice-reference/src:src python scripts/backend_restart_probe.py verify --retry-seconds 15
docker compose -f compose.integration.yml restart kurrentdb xtdb
# wait until both health endpoints are ready
PYTHONPATH=alice-reference/src:src python scripts/backend_restart_probe.py verify --retry-seconds 30

docker compose -f compose.integration.yml down -v
```

For CI, `.github/workflows/flora.yml` is the authoritative repeatable receipt.
