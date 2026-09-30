"""Fresh actual selected-store passive sessions; fictional model/phase outputs.

This exercises physical custody/Claim/context/permission reads. It does not
qualify deployment backend deadline faults, learned behavior or real meter data.
"""
import asyncio
from dataclasses import replace
import hashlib
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

import psycopg
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cognitive_kernel.claim_contracts import CanonicalTaggedValue
from cognitive_kernel.formation_context_planner import FormationPlanningRequest
from flora.comparison_run import ArmResult, HistorySnapshot, MeasuredUsage, SourceMaterial, _context_bytes
from flora.selected.artifact_registry import XTDBModelArtifactRegistry
from flora.selected.claims import XTDBClaimAuthority
from flora.selected.context import ContextPlan
from flora.selected.experiment_runtime import FloRAExperimentRuntime, SuppliedClaimAdmission
from flora.selected.formation_admission import XTDBFormationClaimAdmission
from flora.selected.formation_candidates import XTDBFormationProposalCandidates
from flora.selected.formation_policy import XTDBFormationPermissionPolicy
from flora.selected.formation_registry import XTDBFormationSourceRegistry
from flora.selected.governed_development import XTDBGovernedPersonalDevelopment
from flora.selected.judgment_context import RegisteredJudgmentContextPolicy
from flora.selected.judgment_lineage import NativeJudgmentLineageVerifier
from flora.selected.native_arm import NativeInvocationEntry, NativePhaseSnapshotBinding
from flora.selected.native_reads import (
    InitializedNativeSessionFactory, NativeReadManifest, NativeReadSession, SelectedNativeReadServices,
)
from flora.selected.owner_authorization import Ed25519OwnerActionVerifier
from flora.selected.phase_routes import SelectedPhaseRoute
from flora.selected.phase_snapshots import XTDBPhaseSnapshotCustody
from flora.selected.personal_artifact_custody import DurableOwnerProofLookup, DurablePersonalReferences, XTDBPersonalArtifactCustody


def fixture(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_ROOT = Path(__file__).resolve().parents[1]
_runtime = fixture("flora_native_reads_backend_fixture", Path(__file__).parent / "test_selected_runtime_bridge.py")
_phase = fixture("flora_native_reads_phase_fixture", _ROOT / "test_selected_judgment_lineage.py")


class SelectedNativeReadSessionIntegrationTest(unittest.TestCase):
    def test_fresh_guarded_real_sessions_recover_existing_receipts_and_respect_live_revocation(self):
        f = _runtime.SelectedExperimentRuntimeIntegrationTest()
        f.setUp()
        self.addCleanup(f.doCleanups)
        original = f.fabric._source(b"fictional native reader original source")
        f._judgment_permission(f.registry.lookup(original.event_id))
        bundle, _ = f.fabric._bundle(original, prefix="native-read-fixture")
        f.qualifier = _phase.FictionalPhaseQualifier(f.qualification_key.public_key())
        f._artifact("memory_formation", bundle)
        f._artifact("personality_judgment")
        formed = f.runtime.form_experience(request=FormationPlanningRequest(scope=f.scope,
            authority_namespace_id=f.namespace, experience_refs=(original.event_id,)), invocation_id="native-reader-formation",
            value_resolver=_runtime._fabric_fixture._Values(f.scope, f.namespace, {
                "value-one": CanonicalTaggedValue.create(type_tag="text", value="fictional one"),
                "value-two": CanonicalTaggedValue.create(type_tag="text", value="fictional two")}))
        adapter = _runtime._semantic_fixture.FixtureSemanticAdapter(at=f.fabric._time())
        proposal = formed.bundle.proposals[0].proposal_id
        bound = f.admission.prepare(bundle_id=formed.bundle.bundle_id, proposal_id=proposal, adapter=adapter,
            log=f.log, objects=f.objects, source_store=formed.prepared.store)
        adjudication = _runtime._semantic_fixture.fixture_adjudication(bound, at=f.fabric._time())
        f.fabric.semantic_proof.approve_fixture(adjudication, bound)
        accepted = f.runtime.admit_proposal(formed, SuppliedClaimAdmission(proposal, adapter, adjudication, f.fabric.semantic_proof))
        plan = ContextPlan(request_id="native-reader-context", purpose="personal_judgment",
                           exact_claim_ids=(accepted.claim_id,), minimum_claims=1)
        task, invocation_id = b"same fictional native reader task", "native-reader-judgment"
        judgment = f.runtime.judge(plan=plan, task=task, invocation_id=invocation_id)
        for binding in f.bindings.values():
            binding.adapter.invoke = lambda *_: self.fail("passive selected reader invoked inference")
        history = HistorySnapshot(f.scope, (SourceMaterial(original,
            f.objects.get(f.references.get(original.payload_reference))),))
        entry = NativeInvocationEntry("case-one", "after", invocation_id, plan,
                                      hashlib.sha256(_context_bytes(judgment.context)).hexdigest())
        request = SimpleNamespace(scope=f.scope, case_id="case-one", phase="after", context=judgment.context,
            question=task, authorized_history_sha256=history.digest(), authorized_event_ids=history.event_ids,
            plan=SimpleNamespace(preregistration_sha256=None, digest=lambda: "9" * 64,
                question_sha256_by_case={"case-one": hashlib.sha256(task).hexdigest()}), binding=SimpleNamespace(
                producer_component="fictional-supplied-output-adapter",
                model_artifact_sha256=judgment.execution.invocation.artifact.checkpoint_sha256))
        result = ArmResult(judgment.execution.result.output, judgment.delivery, judgment.decision,
                          MeasuredUsage("fictional-feature", 4, 8, 3, 0))
        archive = XTDBPhaseSnapshotCustody(runtime=f.runtime, run_id="native-reader-phase-fixture",
            run_plan_sha256="9" * 64, clock=f.fabric._time)
        capture_lineage = NativeJudgmentLineageVerifier(runtime=f.runtime, run_plan_sha256="9" * 64,
            history_authority=_phase.FrozenHistoryAuthority({("case-one", "after"): history}),
            history_for=lambda case, phase: history, invocation_id_for=lambda request, result: invocation_id,
            phase_receipt_for=lambda snapshot: _phase.fictional_phase_receipt(snapshot, f.qualification_key))
        snapshot = archive.capture(snapshot_id="native-reader-after", case_id="case-one", phase="after",
            arm="flora_full", plan=plan, lineage=capture_lineage, history=history)
        f._judgment_permission(f.registry.lookup(archive.metadata(snapshot.snapshot_id)["event_id"]))
        phase_entry = replace(entry, phase_snapshot=NativePhaseSnapshotBinding(
            archive.run_id, snapshot.snapshot_id, "flora_full"))
        use_archive = [False]
        dsn, opened, closed = f.connection.info.dsn, [], []
        def opener(*, read_timeout_ms):
            self.assertEqual(read_timeout_ms, 5000)
            connection = psycopg.connect(dsn, autocommit=True, connect_timeout=5)
            opened.append(connection)
            return connection
        public = f.fabric.signer.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        def binder(connection):
            registry = XTDBFormationSourceRegistry(scope=f.scope, authority_namespace_id=f.namespace, connection=connection)
            policy = XTDBFormationPermissionPolicy(scope=f.scope, authority_namespace_id=f.namespace,
                connection=connection, registry=registry)
            claims = XTDBClaimAuthority(scope=f.scope, authority_namespace_id=f.namespace, connection=connection)
            candidates = XTDBFormationProposalCandidates(scope=f.scope, authority_namespace_id=f.namespace, connection=connection)
            state = XTDBGovernedPersonalDevelopment(scope=f.scope, authority_namespace_id=f.namespace,
                connection=connection, registry=registry, policy=policy)
            artifacts = XTDBModelArtifactRegistry(scope=f.scope, authority_namespace_id=f.namespace,
                connection=connection, objects=f.objects)
            private = XTDBPersonalArtifactCustody(scope=f.scope, authority_namespace_id=f.namespace, connection=connection)
            references = DurablePersonalReferences(custody=private, originals=registry)
            owner = Ed25519OwnerActionVerifier(scope=f.scope, owner_public_key=public,
                proofs=DurableOwnerProofLookup(custody=private, log=f.log, objects=f.objects, owner_public_key=public))
            runtime = FloRAExperimentRuntime(artifacts=artifacts, bindings=f.bindings, claims=claims, sources=registry,
                source_policy=policy, candidates=candidates,
                admission=XTDBFormationClaimAdmission(authority=claims, candidates=candidates), state=state,
                log=f.log, objects=f.objects, references=references,
                context_policy=RegisteredJudgmentContextPolicy(claims=claims, state=state,
                    log=f.log, registry=registry, permissions=policy), state_approval_verifier=owner, clock=f.fabric._time)
            runtime.private.register = lambda *_: self.fail("passive recovery tried to register a private artifact")
            lineage = NativeJudgmentLineageVerifier(runtime=runtime, run_plan_sha256="9" * 64,
                history_authority=_phase.FrozenHistoryAuthority({("case-one", "after"): history}),
                history_for=lambda case, phase: history, invocation_id_for=lambda request, result: invocation_id,
                phase_receipt_for=lambda snapshot: _phase.fictional_phase_receipt(snapshot, f.qualification_key))
            def resolve(*, entry, request, artifact_permissions):
                custody = XTDBPhaseSnapshotCustody(runtime=runtime, run_id=entry.phase_snapshot.run_id,
                    run_plan_sha256=lineage.run_plan_sha256, clock=runtime.clock,
                    artifact_permissions=artifact_permissions)
                return SelectedPhaseRoute(custody=custody, snapshot_id=entry.phase_snapshot.snapshot_id,
                    history=history, history_authority=lineage.history_authority,
                    historical_bindings=runtime.bindings, invocation_id_for=lineage.invocation_id_for)
            return NativeReadSession(runtime, lineage, (connection,), resolve if use_archive[0] else None)
        factory = InitializedNativeSessionFactory(artifact_sha256="2" * 64, configuration_sha256="3" * 64,
            connection_opener=opener, bind_initialized=binder, backend_read_timeout_ms=5000)
        manifest = NativeReadManifest(f.scope, f.namespace, "2" * 64, "3" * 64, 1, 60000, 5000,
                                      allow_current_fixture_route=True)
        async def exercise():
            reads = SelectedNativeReadServices(manifest=manifest, factory=factory)
            production = SelectedNativeReadServices(manifest=replace(manifest,
                allow_current_fixture_route=False), factory=factory)
            try:
                self.assertEqual(await reads.prepare_context(entry), judgment.context)
                recovered = await reads.recover_judgment(entry=entry, request=request)
                self.assertEqual(recovered, judgment)
                verified = await reads.verify_native_result(entry=entry, request=request, result=result)
                self.assertEqual(verified.qualified_output, judgment.execution.output_record)
                self.assertEqual(len(opened), 3)
                self.assertTrue(all(connection.closed for connection in opened))
                use_archive[0] = True
                self.assertEqual(await production.prepare_context(phase_entry), judgment.context)
                self.assertEqual(len(opened), 4)
                self.assertTrue(all(connection.closed for connection in opened))
                use_archive[0] = False
                f._judgment_permission(f.registry.lookup(original.event_id), "revoke")
                self.assertFalse(await reads.authorize_context(entry=entry, request=request,
                    context=judgment.context, arm="flora_full"))
                with self.assertRaises(PermissionError):
                    await reads.recover_judgment(entry=entry, request=request)
                use_archive[0] = True
                with self.assertRaises((ValueError, PermissionError)):
                    await production.prepare_context(phase_entry)
            finally:
                await reads.aclose()
                await production.aclose()
        asyncio.run(exercise())
        self.assertTrue(all(connection.closed for connection in opened))


if __name__ == "__main__":
    unittest.main()
