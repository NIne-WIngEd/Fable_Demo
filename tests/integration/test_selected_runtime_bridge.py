"""Actual selected-fabric orchestration and recovery; no learned model evidence.

Opaque checkpoints, producer codecs, supplied outputs and signed qualification/
execution receipts are fictional fixtures. Kurrent/XTDB/custody/source policy/
Claim admission/governed state/context and process recreation are actual paths.
"""
import base64
from dataclasses import replace
import hashlib
import importlib.util
from pathlib import Path
import sys
import unittest
import uuid

import psycopg
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cognitive_kernel.canonical import canonical_json_bytes
from cognitive_kernel.claim_contracts import CanonicalTaggedValue
from cognitive_kernel.formation_context_planner import FormationPlanningRequest
from cognitive_kernel.projection_contracts import ProjectionVersion
from flora.selected.artifact_registry import ArtifactManifest, XTDBModelArtifactRegistry
from flora.selected.claims import XTDBClaimAuthority
from flora.selected.context import ContextPlan, StateRoute
from flora.selected.experiment_runtime import (
    FloRAExperimentRuntime, RuntimeRoleBinding, SuppliedClaimAdmission, SuppliedStateActivation,
)
from flora.selected.formation_admission import XTDBFormationClaimAdmission
from flora.selected.formation_candidates import XTDBFormationProposalCandidates
from flora.selected.formation_context import register_experience_source
from flora.selected.formation_policy import (
    FormationPermissionAction, XTDBFormationPermissionPolicy, formation_permission_payload,
)
from flora.selected.formation_registry import XTDBFormationSourceRegistry
from flora.selected.governed_development import XTDBGovernedPersonalDevelopment
from flora.selected.judgment_context import RegisteredJudgmentContextPolicy
from flora.selected.owner_authorization import Ed25519OwnerActionVerifier, OwnerActionProof, owner_action_message
from flora.selected.personal_artifact_custody import (
    DurableOwnerProofLookup, DurablePersonalReferences, XTDBPersonalArtifactCustody,
)
from flora.selected.personal_state import activation_request

_TESTS = str(Path(__file__).resolve().parents[1])
_INTEGRATION = str(Path(__file__).resolve().parent)
for path in (_TESTS, _INTEGRATION):
    if path not in sys.path:
        sys.path.insert(0, path)
def _fixture(name, path):
    # Unit and selected-backend suites deliberately have different fixtures.
    # Resolve exact files rather than whichever duplicate module name discovery
    # happened to cache first.
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_runtime_fixture = _fixture("flora_runtime_unit_fixture", Path(_TESTS) / "test_selected_experiment_runtime.py")
_semantic_fixture = _fixture("flora_semantic_unit_fixture", Path(_TESTS) / "test_selected_formation_admission.py")
_artifact_fixture = _fixture("flora_artifact_unit_fixture", Path(_TESTS) / "test_artifact_registry.py")
_fabric_fixture = _fixture("flora_admission_backend_fixture", Path(_INTEGRATION) / "test_formation_admission.py")


class SelectedExperimentRuntimeIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.fabric = _fabric_fixture.FormationAdmissionIntegrationTest()
        self.fabric.setUp()
        self.addCleanup(self.fabric.doCleanups)
        self.scope, self.namespace = self.fabric.scope, self.fabric.namespace
        self.objects, self.log = self.fabric.objects, self.fabric.log
        self.codec = _runtime_fixture._FixtureCodec()
        self.qualification_key, self.execution_key = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
        self.qualifier = _artifact_fixture._FictionalSignedVerifier(self.qualification_key.public_key())
        self.execution_verifier = _runtime_fixture._FixtureExecutionVerifier(self.execution_key.public_key())
        self.bindings = {}
        self._bind_services(self.fabric.connection)

    def _bind_services(self, connection):
        self.connection = connection
        self.registry = XTDBFormationSourceRegistry(scope=self.scope, authority_namespace_id=self.namespace,
                                                     connection=connection)
        self.policy = XTDBFormationPermissionPolicy(scope=self.scope, authority_namespace_id=self.namespace,
            connection=connection, registry=self.registry)
        self.claims = XTDBClaimAuthority(scope=self.scope, authority_namespace_id=self.namespace, connection=connection)
        self.candidates = XTDBFormationProposalCandidates(scope=self.scope, authority_namespace_id=self.namespace,
                                                          connection=connection)
        self.admission = XTDBFormationClaimAdmission(authority=self.claims, candidates=self.candidates,
                                                     experiment_world_id="fictional-world")
        self.state = XTDBGovernedPersonalDevelopment(scope=self.scope, authority_namespace_id=self.namespace,
            connection=connection, registry=self.registry, policy=self.policy)
        self.artifacts = XTDBModelArtifactRegistry(scope=self.scope, authority_namespace_id=self.namespace,
                                                  connection=connection, objects=self.objects)
        self.private = XTDBPersonalArtifactCustody(scope=self.scope, authority_namespace_id=self.namespace,
                                                  connection=connection)
        self.references = DurablePersonalReferences(custody=self.private, originals=self.registry)
        public = self.fabric.signer.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.owner_verifier = Ed25519OwnerActionVerifier(scope=self.scope, owner_public_key=public,
            proofs=DurableOwnerProofLookup(custody=self.private, log=self.log, objects=self.objects,
                                          owner_public_key=public))
        self.context_policy = RegisteredJudgmentContextPolicy(claims=self.claims, state=self.state, log=self.log,
                                                              registry=self.registry, permissions=self.policy)
        self.runtime = FloRAExperimentRuntime(artifacts=self.artifacts, bindings=self.bindings, claims=self.claims,
            sources=self.registry, source_policy=self.policy, candidates=self.candidates, admission=self.admission,
            state=self.state, log=self.log, objects=self.objects, references=self.references,
            context_policy=self.context_policy, state_approval_verifier=self.owner_verifier, clock=self.fabric._time)

    def _persist_proof(self, event, action):
        proof = OwnerActionProof(action, event.event_id, event.event_sha256,
            base64.b64encode(self.fabric.signer.sign(owner_action_message(event, action))).decode())
        public = self.fabric.signer.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.private.record_owner_proof(proof=proof, owner_public_key=public, log=self.log, objects=self.objects,
            occurred_at=self.fabric._time(), expected_revision=len(self.log.replay()) - 1)

    def _judgment_permission(self, source, decision="allow"):
        prior = self.policy.current_action(source.evidence.ref_id, "personal_judgment")
        prior_event = None if prior is None else self.policy._stored_action(prior.action_id)["request_event_id"]
        action = FormationPermissionAction.create(scope=self.scope, authority_namespace_id=self.namespace,
            action_id="judgment-permission-" + uuid.uuid4().hex, source_ref_id=source.evidence.ref_id,
            source_registration_sha256=source.registration_sha256, purpose="personal_judgment", decision=decision,
            generation=1 if prior is None else prior.generation + 1,
            previous_action_sha256=None if prior is None else prior.action_sha256,
            authorization_ref="fictional-enrolled-owner", authorized_at=self.fabric._time())
        event, raw = self.fabric._append(formation_permission_payload(action), event_type="formation_permission_action",
            parents=(source.evidence.ref_id,) if prior is None else (source.evidence.ref_id, prior_event),
            at=action.authorized_at, provenance="owner_attested_canonical")
        self.private.register_formation_permission(action=action, request_event_id=event.event_id, raw=raw,
                                                  log=self.log, objects=self.objects)
        self._persist_proof(event, "formation_permission")
        self.policy.apply(action, request_event_id=event.event_id, log=self.log, objects=self.objects,
                          references=self.references, verifier=self.owner_verifier)

    def _artifact(self, role, bundle=None):
        payload = ("fictional opaque checkpoint for runtime qualification mechanics: " + role).encode()
        path = Path(self.fabric.directory.name) / (role + ".checkpoint")
        path.write_bytes(payload)
        manifest = ArtifactManifest(self.scope, "fictional-" + role, role, "fictional-repo", "fictional-branch",
            "a" * 40, hashlib.sha256(payload).hexdigest(), len(payload), self.codec.input_contract_id,
            self.codec.input_contract_sha256, self.codec.output_contract_id, self.codec.output_contract_sha256)
        material = {"schema": "fictional-qualification-v1", "qualifier_id": "fictional-independent-qualifier",
            "qualification_id": "fictional-qualified-" + role, "manifest_sha256": manifest.manifest_sha256,
            "runtime_allowed": True}
        receipt = canonical_json_bytes({"payload": material, "signature": base64.b64encode(
            self.qualification_key.sign(canonical_json_bytes(material))).decode()})
        self.artifacts.admit(manifest=manifest, checkpoint_path=path, external_receipt=receipt, verifier=self.qualifier)
        adapter = _runtime_fixture._SuppliedOutputAdapter(self.execution_key, bundle)
        self.bindings[role] = RuntimeRoleBinding(path, self.codec, self.qualifier, adapter, self.execution_verifier)
        self._bind_services(self.connection)
        return adapter, path

    def _state_activation(self, accepted, source):
        raw, at = self.objects.put(b"fictional supplied host-state projection; not learned"), self.fabric._time()
        version_id = "fictional-runtime-owner-v1"
        envelope = _semantic_fixture.fixture_envelope(self.scope, self.namespace, version_id,
            "projection_version", "registered_projection", (accepted.claim_version_id,), at=at,
            digest=raw.plaintext_sha256)
        version = ProjectionVersion.create(envelope=envelope, projection_id="fictional-runtime-owner-state",
            version_id=version_id, projection_type="owner_model", subject_type="owner",
            subject_id=self.scope.host_instance_id, modalities=("symbolic",), generation=1,
            source_claim_version_ids=(accepted.claim_version_id,), valid_from=at, valid_to=None, produced_at=at,
            projection_state="candidate", responsible_component="fictional-supplied-state", model_id=None,
            model_version=None, content_digest=raw.plaintext_sha256, supersedes_version_id=None)
        self.private.record(artifact_id=version_id, kind="projection", contract=version.metadata_record(),
            attachments=(("content", raw),), parent_event_ids=(source.event_id,), log=self.log, objects=self.objects,
            occurred_at=self.fabric._time(), expected_revision=len(self.log.replay()) - 1)
        approval, approval_raw = self.fabric._append(activation_request(version.metadata_record(),
            expected_active_version_id=None), event_type="state_activation_approval", provenance="owner_attested_canonical")
        self.private.register_approval(approval_event_id=approval.event_id, candidate=version,
            expected_active_version_id=None, raw=approval_raw, log=self.log, objects=self.objects)
        self._persist_proof(approval, "state_activation")
        registered = register_experience_source(event_id=approval.event_id, raw=approval_raw, registry=self.registry,
            log=self.log, objects=self.objects, role="generated_reconstruction", modality="structured")
        self._judgment_permission(registered)
        self.runtime.activate_personal_state(SuppliedStateActivation(version, raw, approval.event_id, None, None))
        return version

    def test_actual_runtime_admission_governed_context_recovery_and_denial(self):
        self.assertTrue(all(not role.ready for role in self.runtime.readiness()))
        original = self.fabric._source(b"fictional runtime original preference")
        source = self.registry.lookup(original.event_id)
        self._judgment_permission(source)
        fixture_bundle, _ = self.fabric._bundle(original, prefix="runtime-fixture")
        formation_adapter, _ = self._artifact("memory_formation", fixture_bundle)
        personality_adapter, personality_path = self._artifact("personality_judgment")
        self.assertTrue(all(role.ready for role in self.runtime.readiness()))
        request = FormationPlanningRequest(scope=self.scope, authority_namespace_id=self.namespace,
                                           experience_refs=(original.event_id,))
        values = _fabric_fixture._Values(self.scope, self.namespace, {
            "value-one": CanonicalTaggedValue.create(type_tag="text", value="fictional value one"),
            "value-two": CanonicalTaggedValue.create(type_tag="text", value="fictional value two")})
        formed = self.runtime.form_experience(request=request, invocation_id="actual-fixture-formation",
                                              value_resolver=values)
        at = self.fabric._time()
        semantic_adapter = _semantic_fixture.FixtureSemanticAdapter(at=at)
        proposal_id = formed.bundle.proposals[0].proposal_id
        bound = self.admission.prepare(bundle_id=formed.bundle.bundle_id, proposal_id=proposal_id,
            adapter=semantic_adapter, log=self.log, objects=self.objects, source_store=formed.prepared.store)
        adjudication = _semantic_fixture.fixture_adjudication(bound, at=at)
        self.fabric.semantic_proof.approve_fixture(adjudication, bound)
        accepted = self.runtime.admit_proposal(formed, SuppliedClaimAdmission(proposal_id, semantic_adapter,
            adjudication, self.fabric.semantic_proof))
        version = self._state_activation(accepted, original)
        plan = ContextPlan(request_id="frozen-runtime-integration-plan", purpose="personal_judgment",
            exact_claim_ids=(accepted.claim_id,), minimum_claims=1,
            state_routes=(StateRoute("owner", self.scope.host_instance_id, version.projection_id),))
        judged = self.runtime.judge(plan=plan, task=b"same fictional task", invocation_id="actual-fixture-judgment")
        self.assertEqual([item.kind for item in judged.context.items], ["claim", "state:owner"])
        self.assertEqual(len(personality_adapter.invocations), 1)
        self.assertIn(judged.execution.output_record.event.event_id, judged.decision.event.parent_event_ids)

        # Recreate selected authority/custody services without caller raw/proof
        # dictionaries. The immutable actual XTDB records recover both stages.
        dsn = self.connection.info.dsn
        self.connection.close()
        reopened = psycopg.connect(dsn, autocommit=True)
        self.addCleanup(reopened.close)
        self._bind_services(reopened)
        recovered = self.runtime.recover_formation(request=request, bundle_id=formed.bundle.bundle_id,
                                                   invocation_id="actual-fixture-formation")
        self.assertEqual(recovered.execution.result, formed.execution.result)
        recovered_judgment = self.runtime.recover_judgment(plan=plan, task=b"same fictional task",
                                                          invocation_id="actual-fixture-judgment")
        self.assertEqual(recovered_judgment.decision, judged.decision)

        # A failed producer proof remains a delivered attempt in canonical
        # Experience; no candidate authority or successful output is fabricated.
        formation_adapter.invalid_proof = True
        with self.assertRaisesRegex(ValueError, "independently verified"):
            self.runtime.form_experience(request=request, invocation_id="failed-fixture-formation", value_resolver=values)
        self.assertTrue(any(event.event_type == "qualified_model_attempt_failure"
                            and event.provenance.derivation_activity_id == "failed-fixture-formation"
                            for event in self.log.replay()))
        personality_path.write_bytes(b"changed checkpoint after runtime recreation")
        with self.assertRaisesRegex(ValueError, "bytes differ"):
            self.runtime.recover_judgment(plan=plan, task=b"same fictional task", invocation_id="actual-fixture-judgment")
        personality_path.write_bytes(("fictional opaque checkpoint for runtime qualification mechanics: personality_judgment").encode())
        self._judgment_permission(self.registry.lookup(original.event_id), "revoke")
        with self.assertRaises(PermissionError):
            self.runtime.recover_judgment(plan=plan, task=b"same fictional task", invocation_id="actual-fixture-judgment")


if __name__ == "__main__":
    unittest.main()
