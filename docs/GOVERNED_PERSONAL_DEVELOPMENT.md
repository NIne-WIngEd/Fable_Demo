# Governed personal development in FloRA

The included infrastructure uses A.L.I.C.E.'s current product-neutral `ProjectionVersion` contract for host, relationship and assistant-self state. The actual personality model and MFM are developed elsewhere. This module supplies neither model nor a substitute for either one.

`XTDBGovernedPersonalDevelopment` wraps the selected XTDB personal-state registry. The existing low-level `XTDBPersonalStateCandidates` remains a component reference; experiment consumers requiring these guarantees must use the governed wrapper.

## Included workflow

- Register an externally supplied, source-bound candidate. Registration does not make it active.
- Check the original Experience sources, current claim versions and every registered Experience parent against current `personal_judgment` permissions before opening their bytes. A `memory_formation` grant alone does not authorize personal judgment.
- Activate the latest candidate only after an exact independently authenticated approval. The XTDB active head and immutable activation receipt commit in the same transaction. A candidate-head assertion prevents activation of a candidate replaced during the operation.
- Accept an externally supplied outcome-linked revision through the existing decision/outcome handoff. The decision, outcome, predecessor and permissions are checked. The content remains supplied; recording it does not prove learned revision.
- Read active state through current source authority and revalidate the head after materialization. Revoked evidence, superseded claims and permission changes during a read prevent use.
- Register rollback to an actually activated prior version. Rollback copies the target's exact private bytes and source lineage into a new `ProjectionVersion`, preserves the latest-candidate predecessor and records the explicit target. A new exact approval is required to activate it.
- Reject a rollback target whose evidence is now revoked or whose claim version is superseded. Replacing a revoked current state does not require reopening that unsafe state's evidence, provided the restore target remains authorized and current.

The wrapper preserves the distinction between the host, relationship and assistant self. It does not classify which subject a new experience concerns or decide what the experience means. Those meanings must come through qualified upstream model and authority interfaces.

## Storage and recovery

| Material | Selected physical plane |
| --- | --- |
| Original event and approval/action events | KurrentDB Experience log |
| Original content and state/approval bytes | Encrypted object custody |
| Registered source metadata and purpose-specific permission heads | XTDB |
| Immutable projection candidates and active state | XTDB |
| Activation receipts and rollback target/action bindings | XTDB |

Candidate storage and rollback-binding storage are separate commits. An interrupted binding write leaves a candidate that cannot be read or activated through the governed wrapper. Retrying the exact rollback can finish the binding. No failure path activates the target, restores an old permission grant, or guesses the missing authority.

The source planes are not one cross-plane transaction. A permission change racing a read may make an operation fail after a durable candidate or activation write. A persisted row does not override a current denial: consumers recheck through the governed wrapper before using state. This is a use barrier, not raw erasure, backup deletion, execution rewind or model unlearning.

## Qualification boundary

- `tests/test_governed_development.py` exercises signed approval, direct and parent permission, mid-read denial, candidate-only outcome revision, exact restore, unsafe target rejection, superseded claim rejection and interrupted rollback binding. Its SQL call recorder is a boundary test, not XTDB qualification.
- `tests/integration/test_governed_development.py` uses actual XTDB, KurrentDB, encrypted objects, durable source registration and purpose-specific permission policy. It checks activation, restoration after current-state revocation, fresh-connection read and subsequent source revocation. It is qualified only after the selected-backend CI run passes.
- State bytes and synthetic events in these tests are explicit fixtures. No behavioral advantage, learned personal development, native judgment or MFM formation quality is claimed.

## Remaining dependencies and limits

- Accepted `EpisodeRecord` lineage is still unsupported for personal-state authority. An episode candidate cannot promote itself into accepted state. The existing episode-candidate plane remains available for candidate custody.
- The actual MFM must produce and qualify state proposals; the actual personality model must consume qualified state and produce native judgment. A stored or activated fixture is not evidence of either capability.
- Production owner enrollment, key custody, durable proof lookup and policy selection remain external to this wrapper. The signed integration fixture supplies an enrolled key and explicit proof mapping; it does not implement enrollment.
- Callers currently supply private state/approval object references. The durable registered-original source plane is used for original source authority; complete process/service-restart custody of every derived private artifact needs the surrounding runtime's durable reference wiring.
- Numerical behavior thresholds, automatic approval policy and the full consumer update/unlearning workflow are separate qualification work.
