# Current history permission without repeated original decryption

The existing comparison input registration and full history recovery authenticate
the actual encrypted originals and stored manifest. Once that history is held
locally, `verify_current_history_metadata` checks its current authority without
opening those objects again. It grants no read, builds no model and stores no
positive permission decision for later calls.

The helper accepts the actual `SelectedRunEvidencePolicy`, registered comparison
custody, source registry and purpose policy. `authorize_history_metadata` is its
boolean delegation entry point. Operational backend failures still raise.

## What the fence proves

- Every held original's plaintext hash matches its real canonical committed
  Experience event, scoped registration and durable raw reference.
- The current originals form the exact registered phase history, including order,
  source parents and canonical commit positions. Every parent must belong to that
  history and precede its child. Originals must precede the manifest's commit.
- Every original and parent has its current exact phase-purpose grant. A later
  call resolves current grants again.
- The held history reconstructs the actual stored manifest body. Its hash must
  match both the artifact's content digest and the canonical manifest event's
  content digest.
- Scope, selected service bindings, the artifact, original registrations, raw
  references, commit metadata and purpose grants remain exact after slow lookups.

The body reconstruction uses the custody writer's existing encoding and schema:

```json
{
  "schema": "flora-comparison-history-manifest-v1",
  "case_id": "...",
  "phase": "before",
  "history_sha256": "...",
  "sources": [
    {"event_id": "...", "registration_sha256": "...", "event_sha256": "..."}
  ]
}
```

Checking only the mutable outer `metadata.history_sha256` would leave that
content binding unproved. The helper reconstructs and hashes the body itself;
it does not substitute outer metadata for the encrypted manifest's digest.

## Reuse and current checks

Only actual metadata rows may be sampled within this one call. The original
connections are retained and never patched. Actual permission closure checks
still run, and fresh original readers fence every captured source and grant
afterward. No ciphertext, plaintext object, permission result or semantic verdict
is memoized. The already held original bytes are hashed locally, not retrieved
again.

The returned `CurrentHistoryAuthority` is a typed observation of that call. It is
not a permission receipt for a later operation. Subsequent private reads, native
execution and output acceptance still need their own current authority gates.
The helper uses the originals' existing evaluation-purpose grants; it does not
add a new grant for opening a manifest, because it opens no manifest bytes.

## Evidence and limits

Eleven tests pass with the real selected registry, comparison custody and purpose
policy implementations, real encrypted initial custody and Ed25519 permission
authentication, using controlled SQL/log ports. Tests cover no private byte I/O,
reordered and after-in-before histories, forged manifest content metadata, held
plaintext mutation, cross-scope inputs, source/parent withdrawal, withdrawal
during the final original's grant lookup, raw-reference change during grant
work, and consent withdrawal during the final uncached raw-reference read.
The final current grant checks follow every slower source/raw-reference read.

These are authority and custody tests. They do not qualify physical engines,
measured latency, a learned model or before-phase training exclusion. The helper
proves the registered history's actual content binding and current use authority;
the independently frozen experiment plan and producer phase proof remain
responsible for whether that registered phase is scientifically valid. The
fence is also not a transaction across metadata stores and object custody.

Implementation: `src/flora/selected/history_fence.py`.
Tests: `tests/test_history_fence.py`.
