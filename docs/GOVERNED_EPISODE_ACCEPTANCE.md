# Governed episode acceptance in FloRA

This is infrastructure for the included FloRA experiment, aligned with the successor memory fabric. It does not build an MFM, personality model or semantic judge. Real episode interpretation and narrative content must arrive from the independently qualified MFM being built elsewhere.

The source architecture is A.L.I.C.E.'s `architecture/full-fable-v1-memory-fabric-20260927` execution plan, especially the episodic plane, personal-development lane and Stage G integration requirements. The earlier PostgreSQL simplification and released Phase 2 are not the experiment's authority.

## Included slice

- Store an externally supplied upstream `EpisodeRecord` candidate using selected XTDB, canonical Kurrent Experience and encrypted private artifacts.
- Preserve its original fields: evidence and Claim members, participants, missions, confidence, time boundaries, formation component/version, generation and superseded draft.
- Require current `personal_judgment` permission for every registered original and parent. Check exact current Claim versions. All original observations must precede episode formation.
- Bind a separate acceptance request to the exact candidate digest, immutable private artifact digest, qualified formation receipt, independent semantic adjudication reference/policy and current accepted publication predecessor.
- Require externally supplied authentication of both the qualified formation output and semantic admission. A request event, source grant, custody record or candidate cannot supply that authority itself.
- Atomically publish the accepted derived episode and current publication head in XTDB, asserting that the exact candidate remains the latest draft. Acceptance creates no canonical Claim or new original evidence.
- Keep draft lineage separate from publication lineage. Rejected drafts do not block a later qualified draft from becoming the first or next accepted publication.
- Recheck current grants, current Claims, accepted publication and external admission before accepted private material is used. A superseded accepted episode cannot remain an active source.
- Permit `ProjectionVersion.source_episode_ids` only through an optional actual `XTDBGovernedEpisodes` authority. The low-level personal-state reference rejects episode sources by default. Accepted episode IDs remain episode IDs; they are not flattened into raw evidence.
- Preserve those episode IDs on approved state revisions and rollback. A rollback target whose episode or source authority is no longer current is refused before that state's private bytes are opened.

## API and custody

`XTDBGovernedEpisodes` extends the existing selected candidate registry. Its `verifier` must provide these independent product interfaces:

| Interface | Required external responsibility |
| --- | --- |
| `qualified_formation(candidate, artifact, formation_receipt_ref)` | Authenticate actual qualified MFM output, exact private artifact and source/physical-availability lineage. A model name or invented receipt string is insufficient. |
| `authenticated_adjudication(request, candidate, artifact, event)` | Authenticate semantic admission against exact candidate/content, policy, independently supplied adjudication and request-bound accepted predecessor. Permission alone is insufficient. |

These interfaces authenticate durable external receipts. They must not rerun a substitute learned judge on every read. Their production implementation and real receipts are still external dependencies. The included allow-list tests exercise gates only.

`record_episode_acceptance_request()` writes the exact request into encrypted custody and canonical Experience. Trusted ingress separately registers that actual control event and grants its purpose-specific use. The typed episode narrative artifact stays in private derived custody and is never registered as an original source.

`accept()` publishes only after both external interfaces succeed. `current_lineage(episode_id, claims=..., log=...)` returns accepted contract/publication/request/source-closure metadata without opening private bytes. `read_accepted()` also verifies exact encrypted artifacts and supplied external admission. Current metadata gates immediately precede/follow each private read and each external verifier; authenticated attachment bytes are reused instead of reopened. `XTDBGovernedPersonalDevelopment(..., episodes=authority)` consumes the accepted authority for episode-derived state.

`DurablePersonalReferences` reconstructs exact private/original object references from selected custody registries. Fresh adapters need no caller-maintained content or proof maps. Externally enrolled keys and independently durable model/adjudication authorities remain outside this registry.

## Validation and limits

- Twenty-three governed-episode boundary methods cover independent admission, exact digest and attachment binding, restart without a private reference map, direct/extra-source denial, formation clocks, read-time denial, rejected drafts, accepted supersession, episode-derived state and unsafe rollback. Request, manifest, summary and external-admission denial prevent the next private read. The same gates cover candidate put/read, exact candidate-head nomination and ciphertext-to-plaintext custody boundaries.
- Eleven prior governed-development boundaries, four immediate source-freshness boundaries and six private-custody boundaries continue to pass. Per-original gates and a live Claim-reader authorizer prevent a prior read from opening a subsequently revoked source.
- `tests/integration/test_selected_governed_episodes.py` uses actual XTDB, Kurrent and encrypted filesystem adapters, real enrolled-owner signatures and current permission policy. It checks episode/state acceptance, fresh-client recovery, accepted-episode context/control receipts and source denial before derived plaintext. It requires selected-backend CI; compiling the file is not engine qualification.
- Fictional narratives and explicitly controlled admission receipts do not demonstrate learned formation, personal judgment, faithful behavior or comparative advantage.
- This is the supported evidence/Claim-backed episode slice. Candidate-member episodes, automatic semantic admission, uncertain-boundary interpretation and the complete autobiographical memory product remain dependent on qualified upstream work.
- Physical evidence availability at actual formation must be authenticated by the external formation receipt. An observed timestamp alone cannot prove the model could read that evidence then.
- Kurrent, private objects, permissions and XTDB publication are separate planes. A racing permission change can deny an operation after a durable write; every later consumer must revalidate current authority. Revocation is a use barrier, not erasure, execution rewind or model unlearning.
- No latency or five-year behavioral claim is established by these component checks. Qualified model integration and the frozen FloRA experiment are the next behavioral gates.
