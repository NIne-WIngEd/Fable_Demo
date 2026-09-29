# Durable private personal-artifact custody

The successor memory fabric keeps originals and durable payloads in encrypted object custody, with immutable contracts and provenance on the selected authority planes. Derived state is not reclassified as original evidence to make it persistent.

`XTDBPersonalArtifactCustody` binds supplied `ProjectionVersion` and `EpisodeRecord` contracts, private content references, exact approval/permission requests and enrolled-owner proof artifacts to real Kurrent events. XTDB stores immutable custody metadata. Private bytes stay in the existing encrypted object plane, whose backend abstraction remains suitable for local disk or S3-compatible placement.

## Supported operations

- `record(...)` appends an encrypted typed projection or episode manifest. It binds complete upstream contract metadata, exact attachment digests and ciphertext metadata, direct Experience parents and physical Kurrent record time. A projection manifest can include an explicit rollback target and predecessor through the unchanged upstream envelope.
- `register_approval(...)` registers an already appended exact state-activation approval payload. It preserves the candidate digest and expected active predecessor; it does not authenticate approval or activate state.
- `register_formation_permission(...)` registers an already appended exact permission request. It applies no permission authority.
- `record_owner_proof(...)` checks a signature against the externally enrolled key and exact original event before storing its encrypted proof artifact. The key is never accepted from the proof itself.
- `read(...)` reconstructs typed contracts and attachments through immutable XTDB metadata, actual Kurrent event/position/time binding, ciphertext integrity and authenticated decryption.
- `reconcile_event(...)` finishes custody registration after append succeeds but the XTDB transaction fails. The encrypted object plane authenticates the recovered reference using its format, AEAD, keyed identity and expected digest; custody additionally requires the typed contract and exact event validation. Supported event kinds are deliberately limited. Approval recovery also needs the scoped immutable candidate registry. Recovery applies no semantic or permission authority.

## Runtime wiring

`DurablePersonalReferences(custody=..., originals=...)` supplies the existing `.get(object_id)` reference interface. It resolves original references through the original-source registry and derived/private references through the new custody registry, rejecting conflicting metadata. It opens no bytes.

`DurableOwnerProofLookup(custody=..., log=..., objects=..., owner_public_key=...)` supplies the owner verifier's `.get(event_id)` proof interface. The enrolled key's digest is checked before private proof materialization; the exact event and signature are reverified on lookup. Enrollment and secret-key custody remain external trust-root configuration.

The governed personal-state wrapper checks current original/parent permissions before opening derived candidate bytes, and rechecks current authority after reads. The context policy additionally requires a properly registered and explicitly permitted approval event. Durable custody does not turn a grant for memory formation into a grant for native judgment.

## Qualification and migration

- Six contract methods check reconstruction without caller reference/proof maps, exact retry, missing-event and wrong-key rejection before private reads, source denial before derived content, durable rollback targets, and post-append index-failure reconciliation. Controlled SQL and recorded-time fixtures do not qualify the physical engines.
- `tests/integration/test_selected_personal_artifact_custody.py` uses actual XTDB, KurrentDB, encrypted storage, original registration, permission authority and enrolled-key proofs. It creates a supplied fictional state, approves it, restores an earlier version, reconnects every selected adapter, reads through durable resolvers, assembles governed judgment context, and verifies that source revocation blocks private bytes. It is qualified only after selected-backend CI passes.
- Existing rows that relied on caller maps are not silently migrated. Reconcile exact canonical manifests/actions where sufficient lineage exists; otherwise supply the original contract/reference through the explicit registration interface. A missing event, contract, key or source authority is not guessed or repaired by relabeling a derivative as original evidence.
- These are custody and authorization mechanisms. They provide no model inference, learned episode segmentation, semantic admission, personal-development result, behavioral advantage, erasure or model unlearning.
