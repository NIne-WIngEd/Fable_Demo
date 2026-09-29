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

## Verification boundary

Deterministic contract tests cover registration integrity, metadata/provenance escalation, host isolation, permission races and stale retrieval hits. A real selected-backend integration test covers physical Kurrent time, XTDB registration reconstruction, encrypted source reopening, original parent closure, historical cutoff and revoked delivery. The restart probe also recreates the registered input after restarting KurrentDB and XTDB. Current commit qualification is pending its GitHub Actions run.

The durable formation-use policy, proposal admission, accepted episode/state governance, qualified artifact registry, adaptive planning and complete influence invalidation remain independent follow-up work. Nothing here supplies a personality/MFM substitute or establishes the frozen experiment's behavioral claim.
