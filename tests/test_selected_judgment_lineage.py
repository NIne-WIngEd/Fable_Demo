"""Native lineage mechanics, not learned qualification or backend evidence.

Opaque signed phase receipts below attest a fictional test snapshot only. SQL
calls are recorded; actual selected-fabric qualification is separate.
"""
import base64
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import re
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cognitive_kernel.canonical import canonical_json_bytes
from cognitive_kernel.contracts import ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from cognitive_kernel.projection_contracts import EpisodeRecord, ProjectionVersion
from flora.comparison_run import HistorySnapshot, SourceMaterial
from flora.selected.context import ContextPlan, StateRoute
from flora.selected.experiment_runtime import RuntimeBlocked, SuppliedStateActivation
from flora.selected.formation_context import register_experience_source
from flora.selected.governed_episodes import EpisodeAcceptanceRequest, XTDBGovernedEpisodes, record_episode_acceptance_request
from flora.selected.judgment_lineage import NativeJudgmentLineageVerifier, VerifiedPhaseArtifactSnapshot
from flora.selected.owner_authorization import Ed25519OwnerActionVerifier, OwnerActionProof, owner_action_message
from flora.selected.personal_state import activation_request


def _fixture(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parent / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_runtime_fixture = _fixture("flora_lineage_runtime_unit_fixture", "test_selected_experiment_runtime.py")
_artifact_fixture = _fixture("flora_lineage_artifact_unit_fixture", "test_artifact_registry.py")
_runtime_fixture._qualification_fixture = _artifact_fixture
_semantic_fixture = _fixture("flora_lineage_semantic_unit_fixture", "test_selected_formation_admission.py")


class FictionalPhaseQualifier(_artifact_fixture._FictionalSignedVerifier):
    """No real training is inspected: signed fixture requests exercise binding."""
    callback = None

    def verify_phase_snapshot(self, *, request, receipt):
        wrapper = json.loads(receipt)
        payload = wrapper["payload"]
        self.public_key.verify(base64.b64decode(wrapper["signature"], validate=True), canonical_json_bytes(payload))
        if payload["schema"] != "fictional-phase-snapshot-v1":
            raise ValueError("unknown fictional phase schema")
        if self.callback:
            self.callback()
        return VerifiedPhaseArtifactSnapshot(**{key: payload[key] for key in (
            "qualifier_id", "qualification_id", "artifact_manifest_sha256", "request_sha256",
            "training_source_snapshot_sha256", "allowed_for_phase")},
            receipt_sha256=hashlib.sha256(receipt).hexdigest())


def fictional_phase_receipt(request, key, **changes):
    payload = {"schema": "fictional-phase-snapshot-v1", "qualifier_id": request.artifact.qualifier_id,
        "qualification_id": request.artifact.qualification_id,
        "artifact_manifest_sha256": request.artifact.manifest_sha256,
        "request_sha256": request.request_sha256,
        "training_source_snapshot_sha256": "e" * 64, "allowed_for_phase": True}
    payload.update(changes)
    return canonical_json_bytes({"payload": payload,
        "signature": base64.b64encode(key.sign(canonical_json_bytes(payload))).decode()})


class FrozenHistoryAuthority:
    def __init__(self, histories):
        self.histories = histories
        self.allowed = True

    def authorize_history(self, *, case_id, phase, history):
        expected = self.histories.get((case_id, phase))
        return self.allowed and expected is not None and expected.digest() == history.digest()


class _StateSQLCalls(_semantic_fixture._AdmissionSQLCalls):
    """Record the additional governed-state CAS shape, never an engine."""
    def execute(self, sql, parameters):
        if sql.startswith("ASSERT EXISTS") and ("AND version_id =" in sql or "AND episode_id =" in sql):
            self.calls.append((sql, parameters))
            table = re.search(r"FROM (\w+)", sql).group(1)
            row = self.rows.get((table, parameters[0]))
            column = "version_id" if "AND version_id =" in sql else "episode_id"
            if (row is None or row[column] != parameters[1]
                    or (len(parameters) == 3 and row["approval_event_id"] != parameters[2])):
                raise ValueError("synthetic state CAS failed")
            return _semantic_fixture._Cursor([])
        return super().execute(sql, parameters)


class SuppliedEpisodeAdmissionFixture:
    """Exact independent fixture allow-list, not MFM inference or a judge."""
    def __init__(self):
        self.qualified, self.adjudicated = set(), set()

    def qualified_formation(self, candidate, artifact, formation_receipt_ref):
        return (candidate.episode_sha256, artifact.artifact_id, formation_receipt_ref) in self.qualified

    def authenticated_adjudication(self, request, candidate, artifact, event):
        return (request.request_sha256, candidate.episode_sha256, artifact.artifact_id,
                event.event_sha256) in self.adjudicated


class SelectedJudgmentLineageTest(unittest.TestCase):
    def setUp(self):
        self.fixture = _runtime_fixture.SelectedExperimentRuntimeTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.connection = _StateSQLCalls(self.fixture.connection)
        for name in ("registry", "candidates", "authority", "state", "artifacts", "private"):
            getattr(self.fixture, name).connection = self.fixture.connection
        self.fixture._admit_artifact("memory_formation")
        self.fixture._admit_artifact("personality_judgment")
        self.qualifier = FictionalPhaseQualifier(self.fixture.qualification_key.public_key())
        self.fixture.bindings = {role: replace(binding, qualification_verifier=self.qualifier)
                                 for role, binding in self.fixture.bindings.items()}
        self.fixture.runtime = self.fixture._runtime()
        formation = self.fixture._form()
        self.accepted = self.fixture._accept(formation)
        self.original_events = self.fixture.log.replay()[:2]
        materials = tuple(SourceMaterial(event, self.fixture.objects.get(
            self.fixture.references.get(event.payload_reference))) for event in self.original_events)
        self.histories = {("case-one", "before"): HistorySnapshot(self.fixture.scope, materials[:1]),
                          ("case-one", "after"): HistorySnapshot(self.fixture.scope, materials)}
        self.plan = ContextPlan(request_id="lineage-fixture-context", purpose="personal_judgment",
                                exact_claim_ids=(self.accepted.claim_id,))
        self.runtime, self.invocations = self.fixture.runtime, {}
        self.verifier = self._verifier()

    def _verifier(self, **changes):
        kwargs = dict(runtime=self.runtime, history_authority=FrozenHistoryAuthority(self.histories),
            run_plan_sha256="9" * 64, history_for=lambda case, phase: self.histories[(case, phase)],
            invocation_id_for=lambda request, result: self.invocations[(request.case_id, request.phase)],
            phase_receipt_for=lambda request: fictional_phase_receipt(request, self.fixture.qualification_key))
        kwargs.update(changes)
        return NativeJudgmentLineageVerifier(**kwargs)

    def _lineage(self, *, phase="after", context=None, verifier=None):
        return (verifier or self.verifier).context_lineage(case_id="case-one", phase=phase,
            history=self.histories[("case-one", phase)], context=context or self.runtime._context(self.plan))

    def _activate_state(self, episode_id=None):
        f = self.fixture
        raw = f.objects.put(b"fictional private host-state; not learned")
        at, version_id = "2026-09-29T14:00:00Z", "lineage-owner-v1"
        sources = (self.accepted.claim_version_id,) if episode_id is None else (episode_id,)
        envelope = _semantic_fixture.fixture_envelope(f.scope, f.namespace, version_id, "projection_version",
            "registered_projection", sources, at=at, digest=raw.plaintext_sha256)
        version = ProjectionVersion.create(envelope=envelope, projection_id="lineage-owner-state", version_id=version_id,
            projection_type="owner_model", subject_type="owner", subject_id=f.scope.host_instance_id,
            modalities=("symbolic",), generation=1,
            source_claim_version_ids=(self.accepted.claim_version_id,) if episode_id is None else (),
            source_episode_ids=() if episode_id is None else (episode_id,),
            valid_from=at, valid_to=None, produced_at=at, projection_state="candidate",
            responsible_component="fictional-supplied-state", model_id=None, model_version=None,
            content_digest=raw.plaintext_sha256, supersedes_version_id=None)
        f.private.record(artifact_id=version_id, kind="projection", contract=version.metadata_record(),
            attachments=(("content", raw),), parent_event_ids=(self.original_events[1].event_id,),
            log=f.log, objects=f.objects, occurred_at=at, expected_revision=len(f.log.replay()) - 1)
        approval_raw = f.objects.put(activation_request(
            version.metadata_record(), expected_active_version_id=None))
        approval = ExperienceEvent.create(event_type="state_activation_approval", scope=f.scope, occurred_at=at,
            content_digest=approval_raw.plaintext_sha256, payload_reference=approval_raw.object_id,
            retention_class="ordinary_experience", storage_tier="raw_buffer",
            provenance=ProvenanceReference.create(provenance_type="generated_reconstruction",
                source_reference_ids=(approval_raw.object_id,), derivation_activity_id="fixture-approval",
                responsible_component="fixture-owner"))
        f.log.append(approval, expected_revision=len(f.log.replay()) - 1)
        f.private.register_approval(approval_event_id=approval.event_id, candidate=version,
            expected_active_version_id=None, raw=approval_raw, log=f.log, objects=f.objects)
        key = Ed25519PrivateKey.generate()
        proof = OwnerActionProof("state_activation", approval.event_id, approval.event_sha256,
            base64.b64encode(key.sign(owner_action_message(approval, "state_activation"))).decode())
        f.runtime.state_approval_verifier = Ed25519OwnerActionVerifier(scope=f.scope,
            owner_public_key=key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw),
            proofs={approval.event_id: proof})
        register_experience_source(event_id=approval.event_id, raw=approval_raw, registry=f.registry,
            log=f.log, objects=f.objects, role="generated_reconstruction", modality="structured")
        f.runtime.activate_personal_state(SuppliedStateActivation(version, raw, approval.event_id, None, None))
        self.plan = replace(self.plan, state_routes=(StateRoute("owner", f.scope.host_instance_id, version.projection_id),))
        return approval

    def _episode(self, *, accept=True):
        f = self.fixture
        self.episode_verifier = SuppliedEpisodeAdmissionFixture()
        episodes = XTDBGovernedEpisodes(scope=f.scope, authority_namespace_id=f.namespace,
            connection=f.connection, registry=f.registry, policy=f.source_policy,
            custody=f.private, verifier=self.episode_verifier)
        f.state.episodes = episodes
        summary, content = f.objects.put(b"fictional episode summary"), f.objects.put(b"fictional episode content")
        envelope = _semantic_fixture.fixture_envelope(f.scope, f.namespace, "lineage-episode", "episode",
            "registered_projection", (self.original_events[1].event_id,), at="2026-09-29T13:00:00Z",
            digest=content.plaintext_sha256)
        candidate = EpisodeRecord.create(envelope=envelope, episode_id="lineage-episode",
            episode_kind="life_event", episode_state="candidate", member_evidence_ids=(self.original_events[1].event_id,),
            participant_ids=(f.scope.host_instance_id,), valid_from="2026-09-29T13:00:00Z", valid_to=None,
            formed_at="2026-09-29T13:00:00Z", formation_component_id="fictional-qualified-mfm",
            formation_version="fixture-only", summary_content_digest=summary.plaintext_sha256,
            full_content_digest=content.plaintext_sha256, confidence=None, generation=1)
        artifact = f.private.record(artifact_id="lineage-episode-artifact", kind="episode",
            contract=candidate.metadata_record(), attachments=(("summary", summary), ("content", content)),
            parent_event_ids=(self.original_events[1].event_id,), log=f.log, objects=f.objects,
            occurred_at="2026-09-29T13:10:00Z", expected_revision=len(f.log.replay())-1)
        inputs = dict(claims=f.authority, log=f.log, objects=f.objects, references=f.references)
        episodes.put_candidate(candidate, thread_id="lineage-episode-thread", summary=summary,
                               content=content, **inputs)
        if not accept:
            return candidate, None
        request = EpisodeAcceptanceRequest.create(scope=f.scope, authority_namespace_id=f.namespace,
            request_id="lineage-episode-adjudication", thread_id="lineage-episode-thread",
            candidate_episode_id=candidate.episode_id, candidate_episode_sha256=candidate.episode_sha256,
            candidate_artifact_id=artifact.artifact_id, candidate_artifact_sha256=artifact.record_sha256,
            formation_receipt_ref="fictional-episode-formation-receipt", adjudication_ref="fictional-episode-review",
            adjudication_policy_sha256="b"*64, expected_previous_episode_id=None,
            expected_previous_episode_sha256=None, adjudicated_at="2026-09-29T13:30:00Z")
        recorded = record_episode_acceptance_request(request=request,
            parent_event_ids=(self.original_events[1].event_id,), log=f.log, objects=f.objects,
            expected_revision=len(f.log.replay())-1)
        f.log.entries[-1] = replace(f.log.entries[-1], recorded_at=datetime(2026,9,29,14,tzinfo=timezone.utc))
        register_experience_source(event_id=recorded.event.event_id, raw=recorded.raw, registry=f.registry,
            log=f.log, objects=f.objects, role="derived_inference", modality="structured")
        self.episode_verifier.qualified.add((candidate.episode_sha256, artifact.artifact_id, request.formation_receipt_ref))
        self.episode_verifier.adjudicated.add((request.request_sha256, candidate.episode_sha256,
                                              artifact.artifact_id, recorded.event.event_sha256))
        episodes.accept(request=request, request_event_id=recorded.event.event_id, **inputs)
        return candidate, recorded.event

    def test_exact_original_closure_phase_snapshots_and_current_claim_hashes(self):
        lineage = self._lineage()
        self.assertEqual(lineage.original_event_ids, tuple(sorted(event.event_id for event in self.original_events)))
        self.assertFalse(lineage.internal)
        self.assertEqual(len(lineage.phase_snapshots), 2)
        self.assertEqual(lineage.claims[0].version_id, self.accepted.claim_version_id)
        self.assertEqual(lineage.context_receipt_sha256, self.runtime._context(self.plan).receipt_record()["receipt_sha256"])
        with self.assertRaisesRegex(ValueError, "exceeds frozen phase"):
            self._lineage(phase="before")
        self.assertFalse(self.verifier.authorize_context(case_id="case-one", phase="after",
            history=self.histories[("case-one", "after")], context=self.runtime._context(self.plan), arm="general_model_memory"))

    def test_source_ids_alone_cannot_hide_changed_content_or_claim_value(self):
        context = self.runtime._context(self.plan)
        for changed in (replace(context.items[0], content=b"other exact bytes"),
                        replace(context.items[0], claim_value={"invented": "other claim"})):
            with self.assertRaisesRegex(ValueError, "content/value/current authority"):
                self._lineage(context=replace(context, items=(changed,)))

    def test_comparison_and_provider_audit_are_never_shared_original_history(self):
        original_history = self.histories[("case-one", "after")]
        for event_type in ("comparison_artifact", "provider_attempt_artifact"):
            raw = self.fixture.objects.put(("fictional internal " + event_type).encode())
            event = ExperienceEvent.create(event_type=event_type, scope=self.fixture.scope,
                occurred_at="2026-09-29T12:00:00Z", content_digest=raw.plaintext_sha256,
                payload_reference=raw.object_id, retention_class="ordinary_experience", storage_tier="raw_buffer",
                provenance=ProvenanceReference.create(provenance_type="generated_reconstruction",
                    source_reference_ids=(raw.object_id,), derivation_activity_id="fixture-internal-audit",
                    responsible_component="fixture-audit"))
            self.fixture.log.append(event, expected_revision=len(self.fixture.log.replay())-1)
            register_experience_source(event_id=event.event_id, raw=raw, registry=self.fixture.registry,
                log=self.fixture.log, objects=self.fixture.objects, role="generated_reconstruction", modality="structured")
            self.histories[("case-one", "after")] = replace(original_history,
                sources=original_history.sources + (SourceMaterial(event, self.fixture.objects.get(raw)),))
            # Even a mistakenly frozen, currently purpose-permitted history
            # cannot turn control/audit content into original user evidence.
            with self.assertRaisesRegex(ValueError, "internal approvals/execution"):
                self._lineage()

    def test_missing_actual_phase_adapter_and_wrong_phase_receipts_fail_closed(self):
        binding = self.fixture.bindings["personality_judgment"]
        self.runtime.bindings["personality_judgment"] = replace(binding,
            qualification_verifier=_artifact_fixture._FictionalSignedVerifier(self.fixture.qualification_key.public_key()))
        with self.assertRaises(RuntimeBlocked):
            self._lineage()
        self.runtime.bindings["personality_judgment"] = binding
        for changes in ({"request_sha256": "0" * 64}, {"allowed_for_phase": False},
                        {"artifact_manifest_sha256": "1" * 64}, {"training_source_snapshot_sha256": "INVALID"}):
            verifier = self._verifier(phase_receipt_for=lambda request, changes=changes:
                fictional_phase_receipt(request, self.fixture.qualification_key, **changes))
            with self.assertRaises(ValueError):
                self._lineage(verifier=verifier)
        wrong_key = Ed25519PrivateKey.generate()
        self.assertFalse(self._verifier(phase_receipt_for=lambda request: fictional_phase_receipt(request, wrong_key))
            .authorize_context(case_id="case-one", phase="after", history=self.histories[("case-one", "after")],
                               context=self.runtime._context(self.plan), arm="flora_full"))

    def test_internal_approval_is_auditable_and_never_shared_user_history(self):
        approval = self._activate_state()
        context = self.runtime._context(self.plan)
        self.assertIn(approval.event_id, context.source_event_ids)
        lineage = self._lineage(context=context)
        self.assertEqual(lineage.internal[0].event_id, approval.event_id)
        self.assertEqual(lineage.personal_state[0].approval_event_id, approval.event_id)
        self.assertNotIn(approval.event_id, lineage.original_event_ids)
        self.assertTrue(self.verifier.authorize_context(case_id="case-one", phase="after",
            history=self.histories[("case-one", "after")], context=context, arm="same_evidence_ablation"))
        extra = SourceMaterial(approval, self.fixture.objects.get(self.fixture.references.get(approval.payload_reference)))
        self.histories[("case-one", "after")] = replace(self.histories[("case-one", "after")],
            sources=self.histories[("case-one", "after")].sources + (extra,))
        with self.assertRaisesRegex(ValueError, "internal approvals"):
            self._lineage(context=context)

    def test_revocation_or_checkpoint_change_during_phase_proof_stops_authorization(self):
        self.qualifier.callback = lambda: self.fixture.permitted.__setitem__(0, False)
        with self.assertRaises((ValueError, PermissionError)):
            self._lineage()
        self.fixture.permitted[0] = True
        self.qualifier.callback = lambda: self.fixture.paths["memory_formation"].write_bytes(b"changed during proof")
        with self.assertRaisesRegex(ValueError, "bytes differ"):
            self._lineage()

    def test_independent_phase_history_revocation_during_qualifier_io_refuses(self):
        authority = FrozenHistoryAuthority(self.histories)
        verifier = self._verifier(history_authority=authority)
        self.qualifier.callback = lambda: setattr(authority, "allowed", False)
        with self.assertRaisesRegex(PermissionError, "phase history authority changed"):
            self._lineage(verifier=verifier)

    def test_accepted_episode_control_and_private_narrative_are_typed_without_original_promotion(self):
        candidate, control = self._episode()
        approval = self._activate_state(candidate.episode_id)
        context = self.runtime._context(self.plan)
        self.assertEqual(context.items[1].control_event_ids, (control.event_id,))
        lineage = self._lineage(context=context)
        self.assertEqual(lineage.personal_state[0].source_episode_ids, (candidate.episode_id,))
        self.assertEqual({item.record_type for item in lineage.internal}, {"state_activation_approval", "episode_acceptance"})
        self.assertEqual({item.event_id for item in lineage.internal}, {approval.event_id, control.event_id})
        self.assertEqual(lineage.episodes[0].candidate_episode_sha256, candidate.episode_sha256)
        self.assertNotIn(control.event_id, lineage.original_event_ids)
        self.assertEqual(set(lineage.original_event_ids), {item.event_id for item in self.original_events})
        changed = replace(context.items[1], control_event_ids=())
        with self.assertRaisesRegex(ValueError, "content/value/current authority"):
            self._lineage(context=replace(context, items=(context.items[0], changed)))
        self.episode_verifier.adjudicated.clear()
        with self.assertRaisesRegex(ValueError, "qualified formation and independent"):
            self._lineage(context=context)

    def test_episode_candidate_cannot_influence_state_before_independent_publication(self):
        candidate, _ = self._episode(accept=False)
        with self.assertRaisesRegex(ValueError, "no governed accepted publication"):
            self._activate_state(candidate.episode_id)

    def test_episode_only_context_still_requires_phase_originals_and_current_semantic_authority(self):
        candidate, _ = self._episode()
        self._activate_state(candidate.episode_id)
        self.plan = replace(self.plan, exact_claim_ids=())
        context = self.runtime._context(self.plan)
        with self.assertRaisesRegex(ValueError, "exceeds frozen phase"):
            self._lineage(phase="before", context=context)
        self.qualifier.callback = self.episode_verifier.adjudicated.clear
        with self.assertRaisesRegex(ValueError, "qualified formation and independent"):
            self._lineage(context=context)

    def test_native_result_requires_actual_invocation_exact_task_output_and_current_plan(self):
        judgment = self.runtime.judge(plan=self.plan, task=b"fixture common question", invocation_id="native-lineage-call")
        history = self.histories[("case-one", "after")]
        self.invocations[("case-one", "after")] = "native-lineage-call"
        request = SimpleNamespace(scope=self.fixture.scope, case_id="case-one", phase="after",
            authorized_history_sha256=history.digest(), authorized_event_ids=history.event_ids,
            context=judgment.context, question=b"fixture common question", plan=SimpleNamespace(digest=lambda: "9" * 64),
            binding=SimpleNamespace(model_artifact_sha256=self.fixture.manifests["personality_judgment"].checkpoint_sha256,
                                    producer_component="fictional-supplied-output-adapter"))
        result = SimpleNamespace(output=judgment.execution.result.output, delivery=judgment.delivery, decision=judgment.decision)
        actual = self.verifier.verify_native_result(request, result)
        self.assertEqual(actual, judgment.execution.output_record)
        self.assertEqual(judgment.decision.event.parent_event_ids[0], actual.event.event_id)
        with self.assertRaisesRegex(ValueError, "actual qualified execution"):
            self.verifier.verify_native_result(request, SimpleNamespace(**{**vars(result), "output": b"invented"}))
        with self.assertRaises(ValueError):
            self.verifier.verify_native_result(SimpleNamespace(**{**vars(request), "question": b"different question"}), result)
        with self.assertRaisesRegex(ValueError, "frozen phase history"):
            self.verifier.verify_native_result(SimpleNamespace(**{**vars(request),
                "plan": SimpleNamespace(digest=lambda: "8" * 64)}), result)
        self.invocations[("case-one", "after")] = "unregistered-call"
        with self.assertRaises((ValueError, KeyError)):
            self.verifier.verify_native_result(request, result)


if __name__ == "__main__":
    unittest.main()
