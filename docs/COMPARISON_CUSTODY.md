# Paired-run custody on the selected engines

This milestone gives the paired comparison runner durable, host-isolated inputs,
receipts and review artifacts. It uses **KurrentDB, XTDB and encrypted local
objects**, the same engines exercised by FloRA's current memory slice. It does
not add a personality model, MFM, comparator model, provider client or model
inference substitute.

The behavioral goal remains [the frozen experiment goal](EXPERIMENT_GOAL.md).
Custody proves which bytes and records a run used; it cannot prove that a model
understood them, learned correctly or beat another model.

## What is persisted

| Artifact | Encrypted content | Immutable lineage |
| --- | --- | --- |
| Plan | Full registered protocol, model/producer bindings, budgets and question hashes | Original events in the isolated host slice |
| Phase history | Ordered original-event references, registration hashes and history digest | That phase's original events only |
| Question | Actual frozen question bytes | Before-phase originals only |
| Delivered context | Actual `LocalContext` receipt and content bytes | Its exact registered `context_delivery` event |
| Output | Exact successful recorded verdict bytes | Its registered native `decision` event |
| Rejected output | Supplied failed/invalid candidate bytes, when available | Authorized originals; never presented as a valid native verdict |
| Run | Every attempt receipt, including failures and missing usage/cost | Plan, input histories, questions, actual success contexts and stored outputs |
| Blind pack | Exact question/output pairs without direct arm identity fields | Exact stored questions and successful outputs |
| Private identity key | Pair-to-arm/case/phase mapping and exclusion count | The matching blind pack |

Each artifact has an immutable XTDB metadata row, a canonical Kurrent event and
a registered encrypted raw-object reference. Reads compare the row, canonical
event, source registration and decrypted content digest. The public review pack
does not expose failure diagnostics, arm bindings or the private key. Actual
response text remains unchanged; the method does not certify that a model's own
words reveal no identity cues.

## Interfaces and workflow

Implementation: [comparison_custody.py](../src/flora/selected/comparison_custody.py).
The existing adapter runner remains documented in
[PAIRED_COMPARISON_RUNNER.md](PAIRED_COMPARISON_RUNNER.md).

1. `XTDBComparisonCustody.register_inputs(...)` binds a complete, single-host
   run plan, actual questions and before/after histories to registered originals.
   Histories must match the protocol hashes; after history retains its before
   prefix and includes the registered intervention. Every original's parent
   closure must stay inside its phase. A shared question cannot acquire an
   intervention source through its parent closure.
2. `SelectedRunEvidencePolicy.authorize_history(...)` checks the registered
   history, real Kurrent event, registered raw reference, exact plaintext and
   **current** evaluation-purpose permission. The runner calls this policy at
   its existing pre/post execution checkpoints. The permission marker records
   fresh source-registration/action hashes; it is never a cached grant.
3. A supplied native adapter registers its actual delivery/decision through
   `register_recorded(...)` and persists the exact delivered input through
   `register_context(...)`. This accepts existing contracts; it does not create
   an inference client or qualify its producer.
4. `save_run(...)` validates the entire matrix. Successful bytes must match the
   canonical decision, frozen producer/model declaration, registered delivery
   and durable actual context. Actual context bytes must fit the frozen budget.
   Native-update ablation context equality and observed execution budgets remain
   enforced by `validate_run`. Failed attempts remain in the denominator;
   unavailable cost/token information is never estimated.
5. `recover_run(...)` and `recover_history(...)` reconstruct original references,
   questions, output bytes and typed contracts from the selected stores. They
   require current permission again, including after raw reads. No caller-held
   raw-reference or event map is required. Host encryption keys remain external
   inputs to the selected encrypted object plane.
6. `save_blind_review(...)` binds the existing randomized review pack/key to
   actual successful output artifacts. It rejects omitted eligible pairs,
   duplicate comparisons, changed bytes and incorrect failure exclusions.
   `export_review(...)` rechecks current permission across the pack's entire
   source closure before returning it.

An artifact's immutable identity supports placement retry: if Kurrent append and
source registration committed but the XTDB artifact insert failed, retry locates
and verifies that exact append rather than producing a second event. Conflicting
content, metadata or parent lineage under the same artifact ID is rejected.

## Unknown after checkpoints: separate capture from evaluation

The prepared-synthetic two-stage path registers an actual experiment anchor
before any update. `register_preregistered_inputs(...)` records its original
histories and questions without requiring a final model or context digest.
Qualified before and after captures later supply the observed bindings. The
final `PairedRunPlan` uses schema v3 and includes `preregistration_sha256` in its
digest; its complete phase bindings belong to the final seal.

`register_inputs(..., final_authority=...)` then accepts that plan only through
the actual `RegisteredExperimentFinalBinding`. Selected evaluation context,
result verification and run custody check this same current authority. Omitting
the argument or supplying an older plan cannot make an anchored run a legacy
run: the store checks its durable anchor, including a committed append whose
index still needs explicit reconciliation. Guarded copies keep the same physical
owner identity and check authority at private reads, object writes and canonical
appends. History-only authority remains available for authorized capture before
the final seal; it does not grant evaluation authority.

Generic artifact reads refuse preregistration controls. Their dedicated recovery
route verifies the declared slot table, ordering and current producer proofs.
These contracts remain infrastructure checks, not evidence that a model learned.

## Permissions stay separate

Registration records custody; it grants no use permission. Existing signed owner
actions and `XTDBFormationPermissionPolicy` supply the current source-purpose
authority, including parent-closure checks.

| Purpose | Permitted route |
| --- | --- |
| `evaluation_purpose(run_id, case_id, phase)` | That case/phase's authorized original history; before and after have distinct purpose IDs |
| `comparison_local_recovery` | Locally recover the private plan and complete run |
| `comparison_review` | Export currently authorized questions and response pairs |
| `comparison_unblind` | Current grant required by the selected assessment adapter's verified sealed-collection release |
| `comparison_external:<provider_id>` | Explicit disclosure authorization for that provider; local/review grants do not imply it |

Evaluation-purpose reads refuse full plan/run and review artifacts; an after
history manifest cannot be opened through a before-phase route. Public `read`
refuses the private identity key under every purpose, including an unblind grant;
there is no permission-only `export_private_key` route. The selected assessment
adapter verifies the actual complete signed rating collection, independent seal
and exact run/pack binding before using an internal key-read hook. That hook
still checks fresh `comparison_unblind` permission before and after raw reads.
`permits_external_disclosure(...)` only checks this separate current authority;
it sends no data and provides no provider transport. For an actual transfer the
transport must recheck authority at the transfer boundary. Signed-seal validation
belongs to the independent assessment workflow. These local Python interfaces
do not prevent an owner who holds raw storage keys from reading their own raw
data or calling internal implementation methods.

## Evidence and remaining work

- **Local contract checks:** five regressions cover canonical plan recovery,
  phase separation, revocation during raw I/O, private-key route isolation and
  orchestration artifacts excluded from inference routes.
- **Selected-store qualification test prepared:**
  [test_comparison_custody.py](../tests/integration/test_comparison_custody.py)
  uses real XTDB/Kurrent clients and encrypted objects. It tests exact registered
  originals, interruption/retry, actual-context custody, all six attempt statuses
  in a failure-inclusive matrix, connection reconstruction, review revocation
  and separate disclosure/key purposes. Its fictional outputs are explicitly
  supplied contract data, not model predictions. **CI execution is pending for
  this milestone; writing this test is not a passing selected-engine result.**
- Connection reconstruction is the test's recovery claim. Independent service
  restart, disaster recovery and encryption-key recovery are not qualified here.
- Actual personality/MFM and serious comparator adapters, held-out behavior,
  consenting-host benefit, longitudinal human ratings, final thresholds and
  builder reproduction remain separate work. Pair preferences alone do not
  establish appropriate change or unrelated stability across phases.
- The seed for this milestone is a procedure trace. It is not an FBM training
  dataset or evidence of a working builder.
