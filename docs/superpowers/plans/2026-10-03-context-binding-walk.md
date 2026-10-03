# Fresh context binding walk implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the duplicate recursive function verification inside an existing fresh frame binding pass.

**Architecture:** Keep the frame's explicit traversal of owned function captures and closure readers. Extract the function's own code/closure/global checks into a private shallow method; the existing recursive `verify()` remains complete for phase producers. Each frame node gets its owned identity check and shallow check on every invocation, with no retained successful result.

**Tech Stack:** Existing Python contracts, native ARM64 Docker, GitHub physical-engine CI.

**Spec:** `docs/ALICE_MIDDLE_LAYER_DESIGN_AUDIT_2026-10-02.md`, conditional pure-proof follow-up, second proposal.

## Global constraints

- FloRA is a narrow prototype for the frozen causal personal-judgment experiment.
- Personality and MFM are built in other chats, not in FloRA.
- Every owned weak seal, function code, closure/global binding, reader seal and opaque callback code pin remains fresh.
- Keep physical reobservation, independent controllers and terminal fences.
- Keep the existing 10,000 ms standalone, 60,000 ms native and 60-minute CI limits.
- Origin seal materialization is deferred so this change has one attributable mechanism.

## Review focus

- Replaced captured objects must reject before their dereference/equality effects.
- In-place leaf code, closure and global changes must reject on a later pass.
- Closure reader changes must still reject; frame tests cover terminal reader mutation.
- Recursive phase verification must still cover nested functions.
- The new shallow method's identity and code must be pinned before use by a real frame.

## Task 1: One walk, complete fresh checks

**Files:** Modify `src/flora/selected/selected_phase_authority.py` and `src/flora/selected/selected_authority_frame.py`; create `tests/test_shared_context_bindings.py`. Existing frame/phase/observer tests stay intact.

**Interfaces:** Consume `_FunctionBinding.verify(self)`, `_ReaderBinding.verify(self)` and frame `_verify_binding(binding)`. Produce private `_FunctionBinding._verify_shallow(self) -> None`; keep recursive `verify()` and all serving interfaces unchanged.

- [x] Write a real three-level captured-function/reader fixture. Observe original verifier code without replacing it. Assert one own function check per node per invocation, one reader check, and no captured callback execution.
- [x] Run `python -m unittest -v test_shared_context_bindings` in the pinned native Docker image. Expected: the one-walk test fails because leaf/middle checks repeat; mutation checks pass.
- [x] Extract the unchanged own checks into `_verify_shallow`; recursive `verify()` calls it and visits nested captures. Frame `_verify_binding` calls the shallow method after its existing explicit nested/reader walk, and calls full reader verification in the reader branch.
- [x] Verify fresh code/closure/global mutation rejection, replacement rejection before effects, recursive phase coverage and method code/identity pins. Run the new tests plus existing phase and focused frame tests. Expected: no failures.
- [x] Run the existing complete component command from CI and original frame suite on native ARM64; save complete logs privately and publish numeric/source-pinned receipts. Report any failures/warnings explicitly. Expected: component success; physical latency remains a separate gate.
- [x] Review the final bounded diff with a fresh reviewer, resolve material findings with tests, then commit/publish to the existing development branch. Record FBM procedure seed, latest context/checkpoint and draft PR; dispatch one source-pinned physical diagnostic. Stop when only outstanding runs remain.

## Execution rulings and evidence

- User's repeated instruction to continue authorizes this existing conditional repair. Implementation proceeds inline in the clean, task-owned recovery checkout on `codex/flora-shared-source-caps`; no new worktree or approval ceremony is needed.
- Baseline ordinary PR CI `37073825647` at `d0f90655` passed all 973 component cases; response latency remains failed. New checks must not erase that failed evidence.
- Four-tag profile `37073820659` attributes 13.555 s exclusive / 30.056 s inclusive CPU to 245,532 frame context-binding calls. Nested inclusive values overlap and are not added to child costs.
- Primary-source applicability was rechecked at the pinned Graphiti `search.py` and Graphify `cache.py` sources in `docs/LATENCY_RESEARCH_2026-10-02.md`: share compatible derived work while retaining separate consumers and freshness. This is an adaptation of that principle, not their authority design.

- Fresh reviewer: no issues requested. All 80 final module logs verify 978 cases,
  zero skips/final failures and unchanged source. Preserve the first worker
  PID-marker failure and eight warnings, plus 16 warning occurrences in its
  successful 13-case repeat. Runtime `4b88946f` is published; PR/push CI and
  once-dispatched native run 37109188927 are pending. No latency or cleanup
  qualification follows from completing this implementation plan.
