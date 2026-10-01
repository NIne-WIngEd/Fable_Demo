# Stored action codec reuse

The completed transport diagnostic on published commit `6a1afd975093e7684f9ca8c0d960e04ce892547a` identified repeated stored-action validation as the largest measured exclusive Python CPU boundary: 25,590 `_stored_action` calls accounted for 19.624 seconds under the observer. The ordinary physical gate still exceeded its unchanged 10,000 ms limit: BEFORE 16,540 ms and AFTER 21,989 ms. Its provider callback fixture passed. Profiling is diagnostic evidence, not latency qualification.

## Narrow change

Every actual `_key` and `_fetch` delegate runs first, once and in its original order. Only after those effects can an exact native policy reuse decoded fields from identical current row bytes that already passed the complete original validation. The binding includes the actual connection and registry, current scope and authority namespace, lookup key, action ID, row ID, scope digest, record digest and exact encoded JSON.

These immutable recorded fields include authorization metadata and the recorded decision. They do not replace a current head, allow verdict, proof verification or permission/qualification result. All existing current-head reads, permission callbacks and terminal row fences remain unchanged.

The memo retains private primitive snapshots and returns fresh nested dictionaries and lists, including any extra JSON fields accepted by the original codec. It is limited to 256 records and 2 MiB of encoded row bytes. A single copy-on-write owner/map/byte-count state keeps default shallow copies and eviction accounting coherent. Oversized or non-memoizable data uses the original path.

Native helper identities, constructors, schemas and receiver descriptors remain live. Custom or effectful rows, policy/scope receivers, decoder overrides, or changed native machinery use the complete original validation body. The actual same-call sampled `_fetch` views remain eligible because their callbacks still run before classification. Deep extra JSON accepted by the original codec remains accepted even when Python snapshot/restore bookkeeping reaches its recursion limit.

## Controlled matched evidence

Both immutable snapshots use the same published tree and the same selected paired workload, stopped immediately after its timing receipt. Only `formation_policy.py` changes in the candidate. The controlled client carries encoded bytes through the actual Kurrent codec and native SDK records; the existing SQL recorder and fictional producer ports are diagnostic fixtures. They do not qualify real backends or model capability.

| Complete workload | Published baseline | Candidate before final runtime-setting correction |
| --- | ---: | ---: |
| Unprofiled total | 9.808 s | 9.077 s |
| BEFORE receipt | 3,198 ms | 3,110 ms |
| AFTER receipt | 5,042 ms | 4,466 ms |
| SQL calls | 6,120 | 6,120 |
| Fresh `get_stream` calls | 3,419 | 3,419 |
| Current transported records | 87,350 | 87,350 |
| Current transported encoded bytes | 98,302,270 | 98,302,270 |

The quiet unprofiled pair improved by 0.731 seconds (7.45%). Under cProfile, total time changed from 29.133 to 28.178 seconds and cumulative `_stored_action` time from 8.763 to 7.624 seconds. Its direct native decoder calls changed from 25,577 to 1,822, with 23,755 immutable codec hits. Eligibility itself cost 5.253 profiled seconds, and fresh restoration cost 0.221 seconds; these costs are included rather than hidden.

Actual `_stored_action` (25,590), `_key` (43,876), native `_fetch` (150), `_head` (12,807), `current_action` (9,668), `permits` (1,817) and terminal current-row fences (559) remained equal. Native stream envelope decoding remains 35 decodes and 87,315 fresh materializations. No current authority result is reused.

## Compatibility checks and limits

Focused negative controls cover current revocation, missing/duplicate/changed rows, recomputed malicious JSON, post-fetch scope and helper withdrawal, modified returned nested values, custom descriptors and explicit `_decode=None`, private-helper replacement, deep accepted JSON, and coherent copies/eviction. The broader pre-correction run passed 96 tests; independent review passed 71 tests against the same frozen source and tests.

The final compatibility review also found that Python's live integer digit limit affects the genuine native JSON decoder. A warmed 1,000-digit extra integer must fall back and raise exactly as fresh decoding does when that limit is reduced; prior successful decoding cannot override the current decoder setting. The final source binds both the genuine setting getter and the live setting after actual key/fetch effects. A changed setting or unknown getter retains original validation, without calling an unknown getter or imposing a new data limit.

The controlled measurements above are not a physical deadline pass. The next published physical CI run remains decisive, with the same response budget and actual selected engines. No personality model, MFM, substitute judge or feature model was built here.

Final source SHA-256: `c3050590d7ccc0926989fd1118636d93750f5f99a0fb4cadeaa02d2108ae19d7`. Final test SHA-256: `4e313c23594ec899dc65545928f0984ad553e7e843ad2c37e2cce2a0751e1121`. The pre-correction matched candidate source was `7654a3c8f9e7ad4d41f73ec175936406ec72f1e7851c1368470b73d0d1b49378`; its measurements are retained as historical exact-source evidence.

The single final unprofiled candidate run completed in **9.514 seconds**, with BEFORE **3,440 ms** and AFTER **4,609 ms**. It loaded the final `c3050590…` source unchanged, retained exactly 6,120 SQL calls, 3,419 fresh stream calls, 87,350 current records and 98,302,270 encoded bytes, and matched all SQL leaf/shape, named inclusive-boundary and stream-caller counters. This is a separate final receipt, rather than the earlier quiet pair or a new cProfile result. The driver's inherited `source_snapshot` text mentions an experience overlay; the recorded loaded hashes establish that this candidate overlays only the action policy.

After the correction, 54 policy/source-fence/preregistration tests passed in 45.647 seconds; independent final review passed all 29 action codec tests in 1.002 seconds with source/test hashes unchanged. Trace shape validation and `git diff --check` pass. The physical deadline remains unqualified.
