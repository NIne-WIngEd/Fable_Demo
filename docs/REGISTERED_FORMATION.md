# Registered MFM input on the selected fabric

FloRA now follows the current A.L.I.C.E. MFM source/context interface at `research/mfm-foundation-20260923@4f287a488bc908bd04f99255ee01b794bacba50b`, formation schema **1.2.0**. This replaces the primitive replay manifest as the intended inference input. The old Phase 2 runtime is not involved.

## Source registration

- The trusted ingestion service supplies the source role, modality and any known subject, speaker, original source item or duplicate group. Missing identity stays unknown; MFM cannot register its own authority.
- KurrentDB supplies the actual event, append position and physical record time. An old event imported today does not become evidence that was available years ago.
- XTDB stores immutable registration and raw-reference metadata. Source identity, raw content digest, original provenance and parent events must agree. Generated reconstruction cannot become authenticated owner speech.
- The encrypted object plane retains the bytes and host-held key. XTDB stores ciphertext checksums and custody references, not the key or plaintext. A new process can reopen the source without the caller's original dictionary.
- Elevated owner roles require an independent verifier at trusted ingress. Production authentication proof enrollment, persistence and recovery remain separate work; a registration is not proof that the source's interpretation is correct.

## Routing and assembly

- An independent query registry supplies exact Claim IDs, graph seeds and any real embedding vector. Route strings do not contain model-authored source IDs or vectors.
- Exact Claim, Qdrant and LadybugDB adapters return original Experience IDs after checking current authority and source custody. These are candidates; relevance remains unqualified.
- A.L.I.C.E.'s `gather_formation_candidates` and `assemble_formation_context` resolve registered evidence, enforce host/authority scope and current permissions, and open original parents before derived children.
- The exact-read selector is an upstream reference policy, not a learned context planner. Synthetic vector mechanics do not demonstrate semantic retrieval.
- Historical `as_of` checks physical record time. Present permission still applies to historical evidence.
- `record_formation_read` binds the exact opened content digests, source registrations, retrieval planes and original-evidence closure. FloRA can persist this metadata receipt in encrypted custody and KurrentDB before submitting real MFM output.

The receipt means **bytes delivered to an input interface**. It does not mean model attention, correct formation, accepted memory or native judgment. `PreparedSelectedFormation.revalidate()` must succeed before consuming or recording the input. Inference will require a separately qualified MFM artifact.

## Private qualification preflight

`prepare_selected_formation(..., before_private_assembly=qualify_role)` now
supports the same two privacy boundaries as native judgment: an already denied
source or parent stops before private qualification proof reads, and an
unqualified model stops before original source plaintext.

FloRA runs the actual upstream assembler once. It records the sources resolved
through the real `RegisteredFormationStore`; its first read occurs only after
independent routing, registered eligibility, selector validation and complete
selected parent closure. That real boundary captures exact source/raw-reference
metadata, checks current purpose permission and invokes
`qualify_role(metadata_guard)`. The hook must return `None`, use the guard around
private qualification proof I/O and supply actual role qualification. It adds
no qualification itself. Fresh authority checks run again after the hook and
before custody reads.

The source object plane also checks that metadata guard before and after every
inner ciphertext fetch, before AES decryption, and after plaintext reads. Current
grants follow slower metadata and permission-closure work. An empty preparation
with no actual source read is refused; upstream formation already requires
nonempty mandatory experience.

`PreparedSelectedFormation.metadata_current()` exposes the metadata-only inner
proof/read barrier. It opens no original bytes and caches no allow decision.
`revalidate()` additionally checks the exact opened-content receipt. Eight local
tests use actual upstream assembly, the selected registry/purpose policy, real
encrypted custody and enrolled Ed25519 grants with controlled SQL/log ports.
They cover single-selector ordering, denied parent/unqualified role, qualification
withdrawal, source metadata change and withdrawal during a real ciphertext fetch
before source AES. They establish custody behavior, not model quality or physical
engine latency.

## Verification boundary

Deterministic contract tests cover registration integrity, metadata/provenance escalation, host isolation, permission races and stale retrieval hits. [Run 36623668349](https://github.com/NIne-WIngEd/FloRA/actions/runs/36623668349) passed the source/context commit `9b1f024`: physical Kurrent time, XTDB registration reconstruction, encrypted source reopening, original parent closure, historical cutoff and a current-policy delivery check. Its restart probe recreated the registered input after restarting KurrentDB and XTDB.

[Run 36625507265](https://github.com/NIne-WIngEd/FloRA/actions/runs/36625507265) passed `0e0a69af`: durable signed source permissions, denial of wrong-key authorization, parent revocation, old-grant retry, candidate output/value recovery and current-source rejection after revocation. The restart probe recovered a registered source with its persisted signed permission after authority services restarted. Delivery also rejects a timestamp earlier than physical source availability. This is selected-store infrastructure evidence, not a model result.

## Governed source use and proposal custody

- `XTDBFormationPermissionPolicy` holds immutable allow/deny/revoke actions and a serialized current head for each original source and purpose. Registration itself grants no use.
- Applying an action requires its exact encrypted request in canonical Kurrent Experience plus an independently verified authorization. Host-bound Ed25519 signatures use a separate `formation_permission` domain. Key enrollment and recovery remain external product work.
- Current permission is checked across every registered parent, before and after custody reads. Missing decisions deny use. An old grant retry is a no-op after a later denial. This policy does not erase raw objects or invalidate every derivative or trained weight.
- `XTDBFormationProposalCandidates` records an externally supplied `MemoryProposalBundle`, its delivery/input receipts and independently resolved canonical proposed values. It stores the private material encrypted and an immutable index in XTDB.
- Original sources are reopened on submission and recovery. Scope, purpose, historical availability, actual delivery, proposed values and output artifact digest must match. Exact retry recovers a Kurrent append that preceded an interrupted XTDB registration.
- Neither a stored proposal nor a pinned output hash is accepted memory or a qualified model. Semantic admission and the real MFM's output quality are separate boundaries.

Proposal-to-Claim admission, accepted episode/state governance, qualified artifact registry, adaptive planning and complete influence invalidation remain follow-up work. Nothing here supplies a personality/MFM substitute or establishes the frozen experiment's behavioral claim.
