"""Actual selected backend lineage wiring; fictional producer outputs/proofs.

This certifies no learned behavior or actual exclusion of training data. The
qualified fixture receipts only exercise the independent phase-proof boundary.
"""
from dataclasses import replace
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

import psycopg
from cognitive_kernel.claim_contracts import CanonicalTaggedValue
from cognitive_kernel.formation_context_planner import FormationPlanningRequest
from cognitive_kernel.projection_contracts import EpisodeRecord, ProjectionVersion
from flora.comparison_run import HistorySnapshot, SourceMaterial
from flora.selected.context import ContextPlan, StateRoute
from flora.selected.experiment_runtime import SuppliedClaimAdmission, SuppliedStateActivation
from flora.selected.formation_context import register_experience_source
from flora.selected.governed_episodes import EpisodeAcceptanceRequest, XTDBGovernedEpisodes, record_episode_acceptance_request
from flora.selected.judgment_lineage import NativeJudgmentLineageVerifier
from flora.selected.personal_state import activation_request


def _fixture(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_ROOT = Path(__file__).resolve().parents[1]
_lineage_fixture = _fixture("flora_lineage_exact_unit_fixture", _ROOT / "test_selected_judgment_lineage.py")
_runtime_fixture = _fixture("flora_lineage_exact_backend_fixture", Path(__file__).parent / "test_selected_runtime_bridge.py")


class SelectedJudgmentLineageIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.fabric = _runtime_fixture.SelectedExperimentRuntimeIntegrationTest()
        self.fabric.setUp()
        self.addCleanup(self.fabric.doCleanups)

    def test_exact_approved_native_state_history_output_recreation_and_revocation(self):
        self._scenario()

    def test_exact_accepted_episode_control_and_native_state_lineage_after_recreation(self):
        self._scenario(with_episode=True)

    def _episodes(self):
        f = self.fabric
        episodes = XTDBGovernedEpisodes(scope=f.scope, authority_namespace_id=f.namespace,
            connection=f.connection, registry=f.registry, policy=f.policy,
            custody=f.private, verifier=self.episode_verifier)
        f.state.episodes = episodes
        return episodes

    def _episode_state(self, source):
        f = self.fabric
        self.episode_verifier = _lineage_fixture.SuppliedEpisodeAdmissionFixture()
        episodes = self._episodes()
        summary, content = f.objects.put(b"fictional backend episode summary"), f.objects.put(b"fictional backend episode narrative")
        at = f.fabric._time()
        envelope = _runtime_fixture._semantic_fixture.fixture_envelope(f.scope, f.namespace,
            "native-lineage-episode", "episode", "registered_projection", (source.event_id,),
            at=at, digest=content.plaintext_sha256)
        episode = EpisodeRecord.create(envelope=envelope, episode_id="native-lineage-episode",
            episode_kind="life_event", episode_state="candidate", member_evidence_ids=(source.event_id,),
            participant_ids=(f.scope.host_instance_id,), valid_from=at, valid_to=None, formed_at=at,
            formation_component_id="fictional-external-mfm", formation_version="fixture-only",
            summary_content_digest=summary.plaintext_sha256, full_content_digest=content.plaintext_sha256,
            confidence=None, generation=1)
        artifact = f.private.record(artifact_id="native-lineage-episode-artifact", kind="episode",
            contract=episode.metadata_record(), attachments=(("summary", summary), ("content", content)),
            parent_event_ids=(source.event_id,), log=f.log, objects=f.objects,
            occurred_at=f.fabric._time(), expected_revision=len(f.log.replay())-1)
        inputs = dict(claims=f.claims, log=f.log, objects=f.objects, references=f.references)
        episodes.put_candidate(episode, thread_id="native-lineage-episode-thread", summary=summary, content=content, **inputs)
        request = EpisodeAcceptanceRequest.create(scope=f.scope, authority_namespace_id=f.namespace,
            request_id="native-lineage-episode-adjudication", thread_id="native-lineage-episode-thread",
            candidate_episode_id=episode.episode_id, candidate_episode_sha256=episode.episode_sha256,
            candidate_artifact_id=artifact.artifact_id, candidate_artifact_sha256=artifact.record_sha256,
            formation_receipt_ref="fictional-external-mfm-receipt", adjudication_ref="fictional-independent-episode-review",
            adjudication_policy_sha256="b"*64, expected_previous_episode_id=None, expected_previous_episode_sha256=None,
            adjudicated_at=f.fabric._time())
        recorded = record_episode_acceptance_request(request=request, parent_event_ids=(source.event_id,),
            log=f.log, objects=f.objects, expected_revision=len(f.log.replay())-1)
        registered = register_experience_source(event_id=recorded.event.event_id, raw=recorded.raw,
            registry=f.registry, log=f.log, objects=f.objects, role="derived_inference", modality="structured")
        f._judgment_permission(registered)
        self.episode_verifier.qualified.add((episode.episode_sha256, artifact.artifact_id, request.formation_receipt_ref))
        self.episode_verifier.adjudicated.add((request.request_sha256, episode.episode_sha256,
                                              artifact.artifact_id, recorded.event.event_sha256))
        episodes.accept(request=request, request_event_id=recorded.event.event_id, **inputs)
        raw, at = f.objects.put(b"fictional episode-derived approved state; not learned"), f.fabric._time()
        envelope = _runtime_fixture._semantic_fixture.fixture_envelope(f.scope, f.namespace,
            "native-episode-owner-v1", "projection_version", "registered_projection", (episode.episode_id,),
            at=at, digest=raw.plaintext_sha256)
        version = ProjectionVersion.create(envelope=envelope, projection_id="native-episode-owner-state",
            version_id="native-episode-owner-v1", projection_type="owner_model", subject_type="owner",
            subject_id=f.scope.host_instance_id, modalities=("symbolic",), generation=1,
            source_episode_ids=(episode.episode_id,), valid_from=at, valid_to=None, produced_at=at,
            projection_state="candidate", responsible_component="fictional-supplied-state", model_id=None,
            model_version=None, content_digest=raw.plaintext_sha256, supersedes_version_id=None)
        f.private.record(artifact_id=version.version_id, kind="projection", contract=version.metadata_record(),
            attachments=(("content", raw),), parent_event_ids=(source.event_id,), log=f.log,
            objects=f.objects, occurred_at=f.fabric._time(), expected_revision=len(f.log.replay())-1)
        approval, approval_raw = f.fabric._append(activation_request(version.metadata_record(),
            expected_active_version_id=None), event_type="state_activation_approval")
        f.private.register_approval(approval_event_id=approval.event_id, candidate=version,
            expected_active_version_id=None, raw=approval_raw, log=f.log, objects=f.objects)
        f._persist_proof(approval, "state_activation")
        registered = register_experience_source(event_id=approval.event_id, raw=approval_raw,
            registry=f.registry, log=f.log, objects=f.objects, role="generated_reconstruction", modality="structured")
        f._judgment_permission(registered)
        f.runtime.activate_personal_state(SuppliedStateActivation(version, raw, approval.event_id, None, None))
        return version

    def _scenario(self, *, with_episode=False):
        f = self.fabric
        original = f.fabric._source(b"fictional lineage fixture source")
        f._judgment_permission(f.registry.lookup(original.event_id))
        bundle, _ = f.fabric._bundle(original, prefix="lineage-fixture")
        f.qualifier = _lineage_fixture.FictionalPhaseQualifier(f.qualification_key.public_key())
        f._artifact("memory_formation", bundle)
        f._artifact("personality_judgment")
        formed = f.runtime.form_experience(request=FormationPlanningRequest(scope=f.scope,
            authority_namespace_id=f.namespace, experience_refs=(original.event_id,)),
            invocation_id="lineage-formation", value_resolver=_runtime_fixture._fabric_fixture._Values(
                f.scope, f.namespace, {"value-one": CanonicalTaggedValue.create(type_tag="text", value="fictional one"),
                                      "value-two": CanonicalTaggedValue.create(type_tag="text", value="fictional two")}))
        at, proposal_id = f.fabric._time(), formed.bundle.proposals[0].proposal_id
        adapter = _runtime_fixture._semantic_fixture.FixtureSemanticAdapter(at=at)
        bound = f.admission.prepare(bundle_id=formed.bundle.bundle_id, proposal_id=proposal_id,
            adapter=adapter, log=f.log, objects=f.objects, source_store=formed.prepared.store)
        adjudication = _runtime_fixture._semantic_fixture.fixture_adjudication(bound, at=at)
        f.fabric.semantic_proof.approve_fixture(adjudication, bound)
        accepted = f.runtime.admit_proposal(formed, SuppliedClaimAdmission(
            proposal_id, adapter, adjudication, f.fabric.semantic_proof))
        version = self._episode_state(original) if with_episode else f._state_activation(accepted, original)
        plan = ContextPlan(request_id="selected-lineage-plan", purpose="personal_judgment",
            exact_claim_ids=(accepted.claim_id,), minimum_claims=1,
            state_routes=(StateRoute("owner", f.scope.host_instance_id, version.projection_id),))
        judged = f.runtime.judge(plan=plan, task=b"same lineage task", invocation_id="lineage-native-call")
        history = HistorySnapshot(f.scope, (SourceMaterial(original,
            f.objects.get(f.references.get(original.payload_reference))),))
        histories = {("case-one", "after"): history}
        request = SimpleNamespace(scope=f.scope, case_id="case-one", phase="after", context=judged.context,
            question=b"same lineage task", authorized_history_sha256=history.digest(), authorized_event_ids=history.event_ids,
            plan=SimpleNamespace(digest=lambda: "9" * 64),
            binding=SimpleNamespace(producer_component="fictional-supplied-output-adapter",
                model_artifact_sha256=judged.execution.invocation.artifact.checkpoint_sha256))
        result = SimpleNamespace(output=judged.execution.result.output, delivery=judged.delivery, decision=judged.decision)

        def verifier():
            return NativeJudgmentLineageVerifier(runtime=f.runtime, run_plan_sha256="9" * 64,
                history_authority=_lineage_fixture.FrozenHistoryAuthority(histories),
                history_for=lambda case, phase: histories[(case, phase)],
                invocation_id_for=lambda request, result: "lineage-native-call",
                phase_receipt_for=lambda snapshot: _lineage_fixture.fictional_phase_receipt(snapshot, f.qualification_key))

        verified = verifier().verify_native_result_details(request, result)
        self.assertEqual(verified.context_lineage.original_event_ids, (original.event_id,))
        self.assertIn(judged.context.items[1].approval_event_id,
                      {item.event_id for item in verified.context_lineage.internal})
        if with_episode:
            self.assertEqual(verified.context_lineage.episodes[0].episode_id, "native-lineage-episode")
            self.assertEqual({item.record_type for item in verified.context_lineage.internal},
                             {"state_activation_approval", "episode_acceptance"})
        self.assertEqual(verified.qualified_output, judged.execution.output_record)
        with self.assertRaises(ValueError):
            verifier().verify_native_result(request, SimpleNamespace(**{**vars(result), "output": b"changed"}))
        dsn = f.connection.info.dsn
        f.connection.close()
        reopened = psycopg.connect(dsn, autocommit=True)
        self.addCleanup(reopened.close)
        f._bind_services(reopened)
        if with_episode:
            self._episodes()
        self.assertEqual(verifier().verify_native_result_details(request, result), verified)
        f._judgment_permission(f.registry.lookup(original.event_id), "revoke")
        self.assertFalse(verifier().authorize_context(case_id="case-one", phase="after", history=history,
                                                      context=judged.context, arm="flora_full"))
        with self.assertRaises((ValueError, PermissionError)):
            verifier().verify_native_result(request, result)


if __name__ == "__main__":
    unittest.main()
