"""Runtime wiring mechanics only: no inference or model qualification evidence.

The external fixture adapter copies explicitly supplied outputs. Independent
fixture keys sign checkpoint receipts and execution bindings. SQL calls are
recorded, never substituted as the selected production engine.
"""
import base64
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cognitive_kernel.canonical import canonical_json_bytes, normalize_timestamp
from cognitive_kernel.formation_context_planner import FormationPlanningRequest

from flora.selected.artifact_registry import ArtifactManifest, XTDBModelArtifactRegistry
from flora.selected.context import ContextPlan
from flora.selected.experiment_runtime import (
    FloRAExperimentRuntime, RuntimeBlocked, RuntimeResult, RuntimeRoleBinding, SuppliedClaimAdmission,
)
from flora.selected.formation_candidates import _bundle_from_record
from flora.selected.governed_development import XTDBGovernedPersonalDevelopment
from flora.selected.judgment_context import RegisteredJudgmentContextPolicy
from flora.selected.personal_artifact_custody import DurablePersonalReferences, XTDBPersonalArtifactCustody

_TESTS = str(Path(__file__).resolve().parent)
if _TESTS not in sys.path:
    sys.path.insert(0, _TESTS)
import test_selected_formation_admission as _admission_fixture
import test_artifact_registry as _qualification_fixture


class _FixturePolicy:
    def __init__(self, registry, permitted):
        self.registry, self.permitted = registry, permitted
        self.scope, self.authority_namespace_id = registry.scope, registry.authority_namespace_id

    def permits(self, source, purpose):
        return self.permitted[0] and purpose in {"memory_formation", "personal_judgment"}


class _FixtureCodec:
    input_contract_id, input_contract_sha256 = "fictional-input-v1", "b" * 64
    output_contract_id, output_contract_sha256 = "fictional-output-v1", "c" * 64

    def formation_input(self, prepared):
        return canonical_json_bytes({"packet": prepared.assembled.packet.metadata_record(),
            "opened": [[ref, base64.b64encode(content).decode()]
                       for ref, content in prepared.assembled.opened_content]})

    def decode_formation(self, output):
        return _bundle_from_record(json.loads(output))

    def encode_formation_output(self, bundle):
        return canonical_json_bytes(bundle.metadata_record())

    def judgment_frame(self, *, context, task):
        # Deliberately a fictional producer codec, NOT a settled ACFP schema.
        return canonical_json_bytes({"fixture_context": context.receipt_record(),
                                    "task_base64": base64.b64encode(task).decode()})

    def validate_identity_decision(self, *, output, context):
        if json.loads(output) != {"fixture_only": "no learned verdict"}:
            raise ValueError("fictional producer output codec rejected changed output")


def _execution_message(adapter, invocation, result):
    return canonical_json_bytes({"domain": "fictional-execution-proof-v1",
        "adapter_id": adapter.adapter_id, "location": adapter.execution_location,
        "invocation": invocation.binding_record(), "output_sha256": hashlib.sha256(result.output).hexdigest()})


class _SuppliedOutputAdapter:
    adapter_id, execution_location = "fictional-supplied-output-adapter", "host_local"

    def __init__(self, key, bundle=None):
        self.key, self.bundle = key, bundle
        self.invocations, self.callback = [], None
        self.invalid_proof, self.changed_binding = False, False

    def invoke(self, invocation):
        self.invocations.append(invocation)
        output = (canonical_json_bytes(replace(self.bundle,
            bundle_id="runtime-" + invocation.invocation_id,
            model_artifact_digest=invocation.artifact.checkpoint_sha256,
            inference_run_id=invocation.invocation_id).metadata_record())
            if self.bundle else canonical_json_bytes({"fixture_only": "no learned verdict"}))
        result = RuntimeResult(invocation.invocation_id, invocation.artifact, invocation.input_sha256, output, b"pending")
        result = replace(result, execution_proof=self.key.sign(_execution_message(self, invocation, result)))
        if self.invalid_proof:
            result = replace(result, output=output + b" ")
        if self.changed_binding:
            result = replace(result, artifact=replace(result.artifact, generation=result.artifact.generation + 1))
        if self.callback:
            self.callback()
        return result


class _FixtureExecutionVerifier:
    def __init__(self, key):
        self.key = key

    def verified_execution(self, *, adapter, invocation, result):
        try:
            self.key.verify(result.execution_proof, _execution_message(adapter, invocation, result))
        except InvalidSignature:
            return False
        return True


class SelectedExperimentRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.fixture = _admission_fixture.SelectedFormationAdmissionTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        for name, value in self.fixture.__dict__.items():
            if not name.startswith("_"):
                setattr(self, name, value)
        self.source_policy = _FixturePolicy(self.registry, self.permitted)
        self.state = XTDBGovernedPersonalDevelopment(scope=self.scope, authority_namespace_id=self.namespace,
            connection=self.connection, registry=self.registry, policy=self.source_policy)
        self.artifacts = XTDBModelArtifactRegistry(scope=self.scope, authority_namespace_id=self.namespace,
            connection=self.connection, objects=self.objects)
        self.private = XTDBPersonalArtifactCustody(scope=self.scope,
            authority_namespace_id=self.namespace, connection=self.connection)
        self.references = DurablePersonalReferences(custody=self.private, originals=self.registry)
        self.context_policy = RegisteredJudgmentContextPolicy(claims=self.authority, state=self.state,
            log=self.log, registry=self.registry, permissions=self.source_policy)
        self.qualification_key, self.execution_key = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
        self.qualifier = _qualification_fixture._FictionalSignedVerifier(self.qualification_key.public_key())
        self.execution_verifier = _FixtureExecutionVerifier(self.execution_key.public_key())
        self.bindings, self.paths, self.manifests = {}, {}, {}
        self.codec = _FixtureCodec()
        self.clock_count = 0
        self.runtime = self._runtime()

    def _clock(self):
        self.clock_count += 1
        return normalize_timestamp((datetime(2026, 9, 29, 12, 20, tzinfo=timezone.utc)
                                    + timedelta(minutes=self.clock_count)).isoformat())

    def _runtime(self, **changes):
        inputs = dict(artifacts=self.artifacts, bindings=self.bindings, claims=self.authority,
            sources=self.registry, source_policy=self.source_policy, candidates=self.candidates,
            admission=self.gateway, state=self.state, log=self.log, objects=self.objects,
            references=self.references, context_policy=self.context_policy,
            state_approval_verifier=SimpleNamespace(authenticated_approval=lambda *_: False), clock=self._clock)
        inputs.update(changes)
        return FloRAExperimentRuntime(**inputs)

    def _admit_artifact(self, role):
        payload = ("fictional opaque checkpoint: " + role).encode()
        path = Path(self.directory.name) / (role + ".bin")
        path.write_bytes(payload)
        manifest = ArtifactManifest(self.scope, "fictional-" + role, role,
            "fictional-repo", "fictional-branch", "a" * 40, hashlib.sha256(payload).hexdigest(), len(payload),
            self.codec.input_contract_id, self.codec.input_contract_sha256,
            self.codec.output_contract_id, self.codec.output_contract_sha256)
        material = {"schema": "fictional-qualification-v1", "qualifier_id": "fictional-independent-qualifier",
            "qualification_id": "fictional-qualified-" + role, "manifest_sha256": manifest.manifest_sha256,
            "runtime_allowed": True}
        receipt = canonical_json_bytes({"payload": material, "signature": base64.b64encode(
            self.qualification_key.sign(canonical_json_bytes(material))).decode()})
        self.artifacts.admit(manifest=manifest, checkpoint_path=path, external_receipt=receipt, verifier=self.qualifier)
        adapter = _SuppliedOutputAdapter(self.execution_key, self.bundle if role == "memory_formation" else None)
        self.bindings[role] = RuntimeRoleBinding(path, self.codec, self.qualifier, adapter, self.execution_verifier)
        self.paths[role], self.manifests[role] = path, manifest
        self.runtime = self._runtime()
        return adapter

    def _form(self, invocation_id="fixture-formation-runtime"):
        return self.runtime.form_experience(request=FormationPlanningRequest(scope=self.scope,
            authority_namespace_id=self.namespace, experience_refs=self.prepared.request.experience_refs),
            invocation_id=invocation_id, value_resolver=self.values)

    def _accept(self, formation):
        proposal_id = formation.bundle.proposals[0].proposal_id
        adapter = _admission_fixture.FixtureSemanticAdapter(at="2026-09-29T13:00:00Z")
        bound = self.gateway.prepare(bundle_id=formation.bundle.bundle_id, proposal_id=proposal_id,
            adapter=adapter, log=self.log, objects=self.objects, source_store=formation.prepared.store)
        decision = _admission_fixture.fixture_adjudication(bound, at="2026-09-29T13:00:00Z")
        self.verifier.approve_fixture(decision, bound)
        return self.runtime.admit_proposal(formation, SuppliedClaimAdmission(proposal_id, adapter, decision, self.verifier))

    def test_exact_missing_roles_and_unsafe_low_level_state_or_ram_references_refuse(self):
        readiness = self.runtime.readiness()
        self.assertEqual([(item.role, item.missing) for item in readiness],
            [("memory_formation", ("role_binding",)), ("personality_judgment", ("role_binding",))])
        self._admit_artifact("memory_formation")
        self.assertEqual([(item.role, item.ready) for item in self.runtime.readiness()],
                         [("memory_formation", True), ("personality_judgment", False)])
        with self.assertRaises(RuntimeBlocked):
            self.runtime._require_all()
        with self.assertRaisesRegex(TypeError, "GovernedPersonalDevelopment"):
            self._runtime(state=SimpleNamespace(scope=self.scope))
        with self.assertRaisesRegex(TypeError, "durable original/private"):
            self._runtime(references={})

    def test_signed_execution_enters_durable_candidate_without_becoming_truth(self):
        self._admit_artifact("memory_formation")
        formation = self._form()
        self.assertEqual(formation.bundle.inference_run_id, "fixture-formation-runtime")
        self.assertEqual(formation.bundle.model_artifact_digest, self.manifests["memory_formation"].checkpoint_sha256)
        self.assertEqual(formation.execution.input_record.event.event_type, "qualified_model_input")
        self.assertEqual(formation.execution.output_record.event.parent_event_ids,
                         (formation.execution.input_record.event.event_id,))
        with self.assertRaises(KeyError):
            self.authority.load_current("fictional-claim-one")
        self.assertEqual(self.candidates.read_candidate(formation.bundle.bundle_id, log=self.log,
            objects=self.objects, source_store=formation.prepared.store).bundle, formation.bundle)

    def test_changed_or_unsigned_execution_never_records_candidate_output(self):
        adapter = self._admit_artifact("memory_formation")
        adapter.invalid_proof = True
        with self.assertRaisesRegex(ValueError, "independently verified"):
            self._form()
        self.assertFalse(any(event.event_type == "qualified_model_output" for event in self.log.replay()))
        self.assertEqual(sum(event.event_type == "qualified_model_attempt_failure" for event in self.log.replay()), 1)
        adapter.invalid_proof, adapter.changed_binding = False, True
        with self.assertRaisesRegex(ValueError, "exact artifact/input"):
            self._form("different-fixture-invocation")

    def test_changed_checkpoint_wrong_host_and_interface_fail_before_input_reads(self):
        self._admit_artifact("memory_formation")
        self.paths["memory_formation"].write_bytes(b"tampered opaque fixture")
        before = len(self.log.replay())
        with self.assertRaisesRegex(ValueError, "bytes differ"):
            self._form()
        self.assertEqual(len(self.log.replay()), before)
        wrong_host = replace(self.scope, host_instance_id="another-host")
        original = self.artifacts.resolve_current_for_runtime
        # Controlled boundary mutation; this does not enroll a foreign artifact.
        self.artifacts.resolve_current_for_runtime = lambda **_: SimpleNamespace(scope=wrong_host, role="memory_formation")
        with self.assertRaisesRegex(ValueError, "host or role"):
            self._form()
        self.artifacts.resolve_current_for_runtime = original

    def test_revocation_during_inference_stops_output_and_artifact_mutation_is_rechecked(self):
        adapter = self._admit_artifact("memory_formation")
        adapter.callback = lambda: self.permitted.__setitem__(0, False)
        with self.assertRaisesRegex(ValueError, "permitted|revoked|source changed"):
            self._form()
        self.assertFalse(any(event.event_type == "qualified_model_output" for event in self.log.replay()))
        self.permitted[0] = True
        adapter.callback = lambda: self.paths["memory_formation"].write_bytes(b"changed during fixture call")
        with self.assertRaisesRegex(ValueError, "bytes differ"):
            self._form("second-fixture-runtime")

    def test_registered_current_context_reaches_native_adapter_and_exact_decision_lineage(self):
        self._admit_artifact("memory_formation")
        personality = self._admit_artifact("personality_judgment")
        formation = self._form()
        accepted = self._accept(formation)
        judgment = self.runtime.judge(plan=ContextPlan(request_id="frozen-fixture-plan", purpose="personal_judgment",
            exact_claim_ids=(accepted.claim_id,), minimum_claims=1), task=b"fictional task",
            invocation_id="fixture-native-judgment")
        self.assertEqual(len(personality.invocations), 1)
        self.assertIn(judgment.execution.output_record.event.event_id, judgment.decision.event.parent_event_ids)
        self.assertEqual(judgment.execution.result.output, canonical_json_bytes({"fixture_only": "no learned verdict"}))
        # An altered public FormationRun cannot smuggle unrelated output into admission.
        changed = replace(formation, execution=replace(formation.execution,
            result=replace(formation.execution.result, output=b"changed output")))
        with self.assertRaisesRegex(ValueError, "durable input/output"):
            self._accept(changed)

    def test_recreation_recovers_exact_execution_and_current_permissions_still_apply(self):
        self._admit_artifact("memory_formation")
        self._admit_artifact("personality_judgment")
        formation = self._form()
        accepted = self._accept(formation)
        plan = ContextPlan(request_id="frozen-recovery-plan", purpose="personal_judgment",
                           exact_claim_ids=(accepted.claim_id,), minimum_claims=1)
        judgment = self.runtime.judge(plan=plan, task=b"fixed fictional task", invocation_id="recoverable-judgment")
        # Controlled missing-index injection models append/index recovery,
        # rather than treating caller-held RawObjectReference objects as durable.
        for key in list(self.connection.rows):
            if key[0] in {"flora_qualified_runtime_steps", "flora_qualified_runtime_raw_references"}:
                del self.connection.rows[key]
        recreated = self._runtime()
        recovered_formation = recreated.recover_formation(request=FormationPlanningRequest(scope=self.scope,
            authority_namespace_id=self.namespace, experience_refs=self.prepared.request.experience_refs),
            bundle_id=formation.bundle.bundle_id, invocation_id="fixture-formation-runtime")
        self.assertEqual(recovered_formation.execution.result, formation.execution.result)
        recovered = recreated.recover_judgment(plan=plan, task=b"fixed fictional task", invocation_id="recoverable-judgment")
        self.assertEqual(recovered.execution.result, judgment.execution.result)
        self.assertEqual(recovered.decision, judgment.decision)
        self.assertTrue(any(key[0] == "flora_qualified_runtime_steps" for key in self.connection.rows))
        with self.assertRaisesRegex(ValueError, "current artifact/context"):
            recreated.recover_judgment(plan=plan, task=b"changed task", invocation_id="recoverable-judgment")
        self.permitted[0] = False
        with self.assertRaisesRegex(PermissionError, "not permitted"):
            recreated.recover_judgment(plan=plan, task=b"fixed fictional task", invocation_id="recoverable-judgment")

    def test_cycle_executes_external_stages_without_manufacturing_governance_or_judgment(self):
        self._admit_artifact("memory_formation")
        self._admit_artifact("personality_judgment")
        stages = []
        def supplied_admissions(formation):
            stages.append("external-semantic-adjudication")
            proposal_id = formation.bundle.proposals[0].proposal_id
            adapter = _admission_fixture.FixtureSemanticAdapter(at="2026-09-29T13:00:00Z")
            bound = self.gateway.prepare(bundle_id=formation.bundle.bundle_id, proposal_id=proposal_id,
                adapter=adapter, log=self.log, objects=self.objects, source_store=formation.prepared.store)
            decision = _admission_fixture.fixture_adjudication(bound, at="2026-09-29T13:00:00Z")
            self.verifier.approve_fixture(decision, bound)
            return (SuppliedClaimAdmission(proposal_id, adapter, decision, self.verifier),)
        def supplied_states(admitted):
            stages.append("external-state-supply")
            self.assertEqual(len(admitted), 1)
            return ()  # This fixture does not claim a learned state update.
        formation, admitted, activated, judgment = self.runtime.run_cycle(
            request=FormationPlanningRequest(scope=self.scope, authority_namespace_id=self.namespace,
                                             experience_refs=self.prepared.request.experience_refs),
            formation_invocation_id="fixture-cycle-formation", value_resolver=self.values,
            supplied_admissions=supplied_admissions, supplied_states=supplied_states,
            plan=ContextPlan(request_id="frozen-cycle-plan", purpose="personal_judgment",
                exact_claim_ids=("fictional-claim-one",), minimum_claims=1),
            task=b"fictional cycle task", judgment_invocation_id="fixture-cycle-judgment")
        self.assertEqual(stages, ["external-semantic-adjudication", "external-state-supply"])
        self.assertEqual(len(admitted), 1)
        self.assertEqual(activated, ())
        self.assertEqual(formation.bundle.inference_run_id, "fixture-cycle-formation")
        self.assertEqual(judgment.execution.invocation.invocation_id, "fixture-cycle-judgment")


if __name__ == "__main__":
    unittest.main()
