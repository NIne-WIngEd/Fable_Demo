# Frozen experiment and limited-builder manifests

This infrastructure preserves the experiment inputs and the proposed limited
FBM construction recipe. It creates no personality model, MFM, FBM, synthetic
life history, target, threshold or result. Those remain separate workstreams.

It follows the [frozen FloRA goal](EXPERIMENT_GOAL.md) and A.L.I.C.E.'s
`FBM_DATA_AND_SEED_PROGRAM_2026-09-26.md`: procedure traces are useful methods;
qualified builder cases need actual authorized input, target and outcome
evidence. A collection of valid JSON records cannot replace that evidence.

## What is stored

| Manifest | Concrete binding | Status this infrastructure can establish |
| --- | --- | --- |
| Cohort | Actual registered original sources, physical Kurrent lineage, source and generator families, generator configuration, scenario ancestry, person roles and frozen split rules | Shape only, or exact source lineage attested by an independently enrolled key |
| Recipe | Actual supplied selected-slice code bytes, dependency bytes, artifact-role interfaces, source choices and stop/defer contract | Prepared recipe; no qualified builder export |
| Linked case | Actual cohort input/target/target-authority/outcome references, proposed operation, alternatives, resolution state and source-person roles | Shape only; training and evaluation eligibility remain false |
| Part1 qualification | Actual registered assessment/spec/result/rubric/threshold/artifact/phase-proof material, exact cohort and recipe, signed independent result qualification | Available only with an independently enrolled result key and the actual result-validator implementation |
| Transfer preparation | Qualified Part1, an additional host's actual cohort, frozen cross-cohort isolation rules and optional independently signed transfer-lineage eligibility | Prepared policy or qualified input lineage; execution remains blocked by the missing actual FBM export qualifier |

`XTDBExperimentManifestCustody` uses encrypted local objects, canonical Kurrent
Experience and the immutable XTDB table `flora_experiment_manifest_artifacts`.
No SQLite substitute or model stub is used as the selected store. IDs are scoped
to the actual host, authority namespace and experiment. Retries preserve the same
body; an identity cannot be reused for a changed manifest.

The manifests have the private `experiment_manifest_artifact` event type. Generic
comparison recovery and `SelectedSourceAuthority.read` refuse internal artifacts
before opening payload bytes; native original history also excludes them.
An `original=false` flag or qualification grant cannot bypass private custody.
Family names, person roles, recipes and linked-case
payloads stay in encrypted objects. The index contains source gates and binding
digests, not those private descriptions or target text.

## Isolation is an explicit policy

Each present split pair must declare all five axes as either disjoint or allowed
to share: source family, generator family, scenario ancestry, person family and
original-source ancestry. Training, pilot, heldout and transfer are distinct
split names. There is no hidden default that permits sharing, and no invented
blanket rule that forbids a legitimate shared identity-neutral source pack.

The validator rejects overlap on the declared-disjoint axes, even when host IDs
differ. It follows original ancestor IDs and content hashes, so a copied source
under a new host or source name does not establish independence. Scenario roots
and parent scenarios are checked together. An independently enrolled lineage
signer must attest the exact actual family/alias ancestry and frozen policy
before the cohort is labelled lineage-qualified. Caller-provided family labels
alone leave it shape only. The signer still needs a genuine source/generator
lineage producer; this milestone does not manufacture one.

Recipes cannot mark heldout or transfer material as training eligible by changing
a choice label. A linked case remains unqualified even if someone supplies a
target reference and calls its resolution accepted. Independent target authority,
observed outcomes, rights and producer qualification still need to establish
that the case is usable training or evaluation data.

## Actual host permission at every boundary

`SelectedSourceAuthority` resolves actual isolated host registries, Kurrent logs,
encrypted-object references and owner permission policies. It checks the exact
committed event, registration, raw digest, parents and physical availability.
No foreign-host grant is created or represented as a local owner's permission.

Cross-host source bindings are typed metadata. Foreign source IDs do not become
fictional parents in the local Kurrent stream. Local control parents and exact
foreign source gates are preserved separately. A guard digest in the canonical
event binds the index's source gates and dependencies; merely recomputing an XTDB
row checksum cannot remove a foreign-source guard.

- Source use requires the current `experiment_cohort_<split>:<experiment digest>`
  purpose in the source's own host policy.
- Manifest creation requires a current local control-anchor capture grant.
- Private recovery requires the manifest's own read grant, current dependency
  read grants and the frozen current source gates.
- Part1's actual sealed or heldout material needs its separate
  `experiment_manifest_qualification:<experiment digest>` purpose.

Checks occur before and after ciphertext fetch, before AEAD decryption and after
plaintext reads, including nested placement and raw-reference recovery. Each
reader wraps a copied object plane; it does not mutate a shared host backend.
Slow dependency checks are followed by fresh source gates immediately before
canonical append. Slow result validation also requires fresh source gates.
Registration or a previous grant is not a cached authorization. Withdrawal
during an already authorized in-flight storage write can leave an encrypted
orphan or canonical control append; it cannot return an authorized manifest or
grant inference access. These gates are not a cross-plane transaction or a
claim about production latency.

## Part1 and Part2 stay honest

The Part1 result key is separately enrolled from the lineage key. Its signed
claim binds the exact cohort, recipe, protocol, plan and actual source materials.
`Part1ResultValidator` is mandatory: it must verify the real blind-assessment
seal, rubric, thresholds, native/comparator/ablation qualification, phase
exclusions, budgets, failures and acceptance decision. No default validator is
supplied, and a SHA or a signed Boolean alone cannot unlock Part1.

Private result material also needs an exact `RegisteredPart1MaterialReader`
route. The independent result signature binds the reader artifact and the full
registered route digest as well as each source gate. The dispatcher uses the
actual implemented selected controllers:

- Comparison material uses `XTDBComparisonCustody.read` with its separate
  current custody purpose and exact run/artifact/kind. Blind keys, assessment
  bypasses and unknown private kinds are refused.
- Assessment spec and seal use `XTDBAssessmentCustody.recover_collection` and
  require an independently authenticated actual sealed collection. A stored
  object merely labelled `assessment_seal` is insufficient.
- Phase snapshots require actual frozen history, its current authority and
  supplied historical `RuntimeRoleBinding` objects. `SelectedPhaseRoute`
  reconstructs the pinned context and rechecks the real producer qualification,
  phase exclusions and update-exclusion receipt. Storage recovery alone cannot
  declare a phase qualified. This route does not invoke or train a model.
- Provider observations require `XTDBProviderAttemptCustody.recover`, its current
  private audit authority and the exact signed task/authorization/observation
  chain. Capture permission alone cannot replace private audit permission.

All routes bind the actual isolated registry, log, object plane and event; every
nested private read keeps current qualification authority around its ciphertext
boundary. Original evidence follows the ordinary source reader. Unknown internal
material stops until its dedicated controller is implemented and enrolled. The
dispatcher connects these existing custody paths; actual producer codecs and
the independent semantic result validator are still supplied externally.

Transfer preparation recovers that qualified Part1 again, checks distinct actual
hosts and the declared cross-cohort rules, and requires a separate signed
transfer claim to attest qualified isolation and exclusion of first-host private
derivatives. An unqualified transfer policy stays explicitly unqualified. Even
qualified transfer inputs have `execution_ready=false`: the actual limited FBM
export and its producer qualification are absent. This module refuses a bare
export-digest readiness claim. It does not train or execute the builder.

## Verification boundary

Twenty-six local tests pass using fictional registry/SQL ports and real local
encryption. They check frozen policy coverage, renamed-host and copied-source
leakage, independent signatures, immutable identities, private source withdrawal,
guard tampering, actual recipe bytes, unqualified linked cases and blocked builder
readiness. They reproduce foreign withdrawal during actual ciphertext fetch
before AEAD, withdrawal during slow dependency checks before append, generic
private-reader bypass, typed comparison locator/purpose checks, validator-time
private-purpose withdrawal and an absent actual assessment seal. Signed Part1 tests use a clearly fictional
result-validator port; they establish permission and binding mechanics, not a
successful experiment.

The uniquely named selected-backend test uses real XTDB, Kurrent and encrypted
local objects for two fictional hosts. It covers durable cohort/recipe/case
recreation, foreign permission withdrawal, typed comparison recovery,
generic-reader exclusion and rejection before decryption. That physical-engine
gate is pending CI. No actual cohort,
heldout rubric, threshold, model artifact or Part1 empirical result was supplied.
