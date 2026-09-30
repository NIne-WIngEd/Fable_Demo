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
still run. The second source/raw/grant pass can use those same row decoders only
when the source registry and permission policy are exact native classes with
unmodified reader, key and decoder functions. Genuine functions are captured at
module load, and eligibility is checked again after the second real artifact
read and canonical replay. Instance overrides, subclasses, class patches and
module decoder callbacks retain the complete uncached second pass. Both actual
artifact reads, both canonical replays and all causal/content comparisons remain.
No ciphertext, plaintext object, permission result or semantic verdict is
memoized. Held original bytes are hashed locally, not retrieved again.

After all actual grant callbacks, one finite selected XTDB statement checks all
sampled source/raw/action/current-head rows together. This catches a callback on
the final original that revokes an earlier grant after its sequential check.
The full initial history path retains its real private authentication and
finishes with this metadata fence. The permission-marker path also rechecks
current metadata after its final callbacks. The row sample is discarded after
this call. See
[the terminal metadata fence](PHASE_SOURCE_METADATA_FENCE.md) for its exact
current-row boundary and explicit limits.

The returned `CurrentHistoryAuthority` is a typed observation of that call. It is
not a permission receipt for a later operation. Subsequent private reads, native
execution and output acceptance still need their own current authority gates.
The helper uses the originals' existing evaluation-purpose grants; it does not
add a new grant for opening a manifest, because it opens no manifest bytes.

## Evidence and limits

Twenty-five tests pass with the real selected registry, comparison custody and purpose
policy implementations, real encrypted initial custody and Ed25519 permission
authentication, using controlled SQL/log ports. Tests cover no private byte I/O,
reordered and after-in-before histories, forged manifest content metadata, held
plaintext mutation, cross-scope inputs, source/parent withdrawal, withdrawal
during the final original's grant lookup, raw-reference change during grant
work, consent withdrawal during the final uncached raw-reference read, and
withdrawal specifically during the last callback of the final grant pass,
initial private authentication followed by that final metadata fence, and
withdrawal during the final permission-marker callback.
The native second-pass fixtures fall from 24 to 10 SQL calls for two originals,
and from 31 to 10 for three. They retain both real artifact reads and both
canonical replays. Additional regressions cover owner withdrawal and raw-row
mutation during the second replay, decoder rebinding, live custom callback
denial, and subclass/instance fallback, including a late alias of an equal bound
native function. The count and decoder-rebinding regressions fail against the
published prior implementation.
The terminal current-row query follows every slower source/raw-reference and
grant callback. It grants no authority after the query's snapshot.

These are authority and custody tests. They do not qualify physical engines,
measured latency, a learned model or before-phase training exclusion. The helper
proves the registered history's actual content binding and current use authority;
the independently frozen experiment plan and producer phase proof remain
responsible for whether that registered phase is scientifically valid. The
fence is also not a transaction across metadata stores and object custody.

Implementation: `src/flora/selected/history_fence.py`.
Tests: `tests/test_history_fence.py`.
