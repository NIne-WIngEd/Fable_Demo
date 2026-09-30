"""Episode custody/admission boundaries; controlled proofs are not model qualification."""
from datetime import datetime, timezone
from dataclasses import replace
import unittest
from cognitive_kernel.canonical import canonical_sha256
from cognitive_kernel.memory_contracts import MemoryUnitEnvelope
from cognitive_kernel.projection_contracts import EpisodeRecord, ProjectionVersion
from flora.selected.experience import CommittedExperience
from flora.selected.governed_development import XTDBGovernedPersonalDevelopment
from flora.selected.governed_episodes import (
    EpisodeAcceptanceRequest, XTDBGovernedEpisodes, record_episode_acceptance_request,
)
from flora.selected.personal_artifact_custody import DurablePersonalReferences, XTDBPersonalArtifactCustody
from flora.selected.personal_state import XTDBPersonalStateCandidates
import test_governed_development as helpers


class _SuppliedAdmissionFixture:
    """Explicit allow-list, never a learned MFM or a semantic judge."""
    def __init__(self):
        self.qualified, self.adjudicated = set(), set()
        self.on_adjudication = None

    def qualified_formation(self, candidate, artifact, reference):
        return (candidate.episode_sha256, artifact.artifact_id, reference) in self.qualified

    def authenticated_adjudication(self, request, candidate, artifact, event):
        if self.on_adjudication is not None:
            self.on_adjudication()
        return (request.request_sha256, event.event_sha256) in self.adjudicated


class GovernedEpisodeBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.f = helpers.GovernedDevelopmentContractTest()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        f = self.f
        f.log.replay_committed = lambda: tuple(CommittedExperience(event, i,
            datetime(2026, 9, 29, 14, tzinfo=timezone.utc)) for i, event in enumerate(f.log.events))
        def append(event, *, expected_revision):
            if expected_revision != len(f.log.events) - 1:
                raise ValueError("synthetic stale append")
            f.log.events.append(event)
        f.log.append = append
        self.custody = XTDBPersonalArtifactCustody(scope=f.scope,
            authority_namespace_id=f.namespace, connection=f.connection)
        self.references = DurablePersonalReferences(custody=self.custody, originals=f.registry)
        self.admission = _SuppliedAdmissionFixture()
        self.episodes = self.new_episodes()

    def new_episodes(self):
        f = self.f
        return XTDBGovernedEpisodes(scope=f.scope, authority_namespace_id=f.namespace,
            connection=f.connection, registry=f.registry, policy=f.policy,
            custody=self.custody, verifier=self.admission)

    def inputs(self):
        f = self.f
        return dict(claims=f.claims, log=f.log, objects=f.objects, references=self.references)

    def candidate(self, number=1, previous=None, extra=()):
        f = self.f
        version, _ = f.version(number, previous=previous)
        summary = f.objects.put(f"supplied fictional episode {number} summary".encode())
        content = f.objects.put(f"supplied fictional episode {number} narrative".encode())
        episode_id = f"fictional-episode-v{number}"
        envelope = MemoryUnitEnvelope.create(**{**{k:v for k,v in version.envelope.__dict__.items() if k != "envelope_sha256"},
            "record_id": episode_id, "record_type": "episode",
            "source_records": tuple(sorted((f.source_one.event_id,) + extra)),
            "content_digest": content.plaintext_sha256})
        episode = EpisodeRecord.create(envelope=envelope, episode_id=episode_id,
            episode_kind="life_event", episode_state="candidate",
            member_evidence_ids=(f.source_one.event_id,),
            participant_ids=(f.scope.host_instance_id,),
            mission_node_ids=("fictional-mission",),
            valid_from="2026-09-29T10:00:00Z", valid_to=None,
            formed_at="2026-09-29T11:00:00Z", formation_component_id="external-qualified-mfm",
            formation_version="fixture-only", summary_content_digest=summary.plaintext_sha256,
            full_content_digest=content.plaintext_sha256, confidence=0.8,
            generation=number, supersedes_episode_id=previous)
        artifact = self.custody.record(artifact_id=f"fictional-episode-artifact-v{number}", kind="episode",
            contract=episode.metadata_record(), attachments=(("summary", summary), ("content", content)),
            parent_event_ids=(f.source_one.event_id,), log=f.log, objects=f.objects,
            occurred_at="2026-09-29T13:00:00Z", expected_revision=len(f.log.events)-1)
        self.episodes.put_candidate(episode, thread_id="fictional-thread", summary=summary,
            content=content, expected_previous_episode_id=previous, **self.inputs())
        return episode, artifact, summary, content

    def request(self, candidate, artifact, previous=None, *, qualify=True, adjudicate=True):
        f = self.f
        request = EpisodeAcceptanceRequest.create(scope=f.scope, authority_namespace_id=f.namespace,
            request_id=f"fictional-adjudication-{candidate.generation}", thread_id="fictional-thread",
            candidate_episode_id=candidate.episode_id, candidate_episode_sha256=candidate.episode_sha256,
            candidate_artifact_id=artifact.artifact_id, candidate_artifact_sha256=artifact.record_sha256,
            formation_receipt_ref="externally-qualified-mfm-receipt",
            adjudication_ref=f"external-semantic-admission-{candidate.generation}",
            adjudication_policy_sha256="b"*64,
            expected_previous_episode_id=None if previous is None else previous.episode_id,
            expected_previous_episode_sha256=None if previous is None else previous.episode_sha256,
            adjudicated_at="2026-09-29T13:30:00Z")
        recorded = record_episode_acceptance_request(request=request,
            parent_event_ids=candidate.member_evidence_ids, log=f.log, objects=f.objects,
            expected_revision=len(f.log.events)-1)
        f.references[recorded.raw.object_id] = recorded.raw
        f.register_source(recorded.event)
        f.policy.allowed.add((recorded.event.event_id, "personal_judgment"))
        if qualify:
            self.admission.qualified.add((candidate.episode_sha256, artifact.artifact_id, request.formation_receipt_ref))
        if adjudicate:
            self.admission.adjudicated.add((request.request_sha256, recorded.event.event_sha256))
        return request, recorded.event

    def accept(self, candidate, artifact, previous=None):
        request, event = self.request(candidate, artifact, previous)
        receipt = self.episodes.accept(request=request, request_event_id=event.event_id, **self.inputs())
        return receipt, request, event

    def derived_state(self, episode_id, number=1, previous=None):
        f = self.f
        supplied, raw = f.version(number, claim_ids=(episode_id,), previous=previous)
        state = ProjectionVersion.create(**{**{k: v for k,v in supplied.__dict__.items()
            if k != "projection_sha256"}, "source_claim_version_ids": (),
            "source_evidence_ids": (), "source_episode_ids": (episode_id,)})
        self.custody.record(artifact_id=f"episode-derived-state-{number}", kind="projection",
            contract=state.metadata_record(), attachments=(("content",raw),),
            parent_event_ids=(f.source_one.event_id,), log=f.log, objects=f.objects,
            occurred_at="2026-09-29T13:30:00Z", expected_revision=len(f.log.events)-1)
        return state, raw

    def test_exact_supplied_candidate_can_be_published_without_changing_upstream_lineage(self):
        episode, artifact, _, _ = self.candidate()
        receipt, request, event = self.accept(episode, artifact)
        self.assertEqual(self.episodes.accept(request=request, request_event_id=event.event_id,
            **self.inputs()), receipt)
        accepted = self.episodes.read_accepted(episode.episode_id, **self.inputs())
        self.assertEqual(accepted.record["episode_state"], "accepted")
        self.assertEqual(accepted.record["member_evidence_ids"], list(episode.member_evidence_ids))
        self.assertEqual(accepted.record["mission_node_ids"], ["fictional-mission"])
        self.assertEqual(accepted.content, b"supplied fictional episode 1 narrative")
        self.assertEqual(self.episodes._candidate_metadata(episode.episode_id)[0], episode)
        self.assertNotIn("narrative", repr(accepted))
        f = self.f
        f.references.clear()
        self.episodes = self.new_episodes()
        self.references = DurablePersonalReferences(custody=self.custody, originals=f.registry)
        self.assertEqual(self.episodes.read_accepted(episode.episode_id, **self.inputs()), accepted)

    def test_missing_qualification_or_independent_admission_cannot_self_promote(self):
        episode, artifact, _, _ = self.candidate()
        request, event = self.request(episode, artifact, adjudicate=False)
        with self.assertRaisesRegex(ValueError, "qualified formation and independent"):
            self.episodes.accept(request=request, request_event_id=event.event_id, **self.inputs())
        self.assertIsNone(self.episodes._head("fictional-thread"))
        self.admission.adjudicated.add((request.request_sha256, event.event_sha256))
        self.admission.qualified.clear()
        with self.assertRaisesRegex(ValueError, "qualified formation and independent"):
            self.episodes.accept(request=request, request_event_id=event.event_id, **self.inputs())
        self.assertIsNone(self.episodes._head("fictional-thread"))

    def test_permission_denial_precedes_any_derived_private_content_read(self):
        episode, artifact, summary, content = self.candidate()
        receipt, _, event = self.accept(episode, artifact)
        self.f.policy.allowed.remove((event.event_id, "personal_judgment"))
        opened = []
        self.enterContext(helpers.observe_private_opens(opened))
        with self.assertRaisesRegex(ValueError, "request authority"):
            self.episodes.read_accepted(episode.episode_id, **self.inputs())
        self.assertEqual(opened, [])

    def test_revoked_extra_original_is_part_of_metadata_only_closure(self):
        f = self.f
        episode, artifact, _, _ = self.candidate(extra=(f.source_two.event_id,))
        self.accept(episode, artifact)
        self.assertIn(f.source_two.event_id, self.episodes.current_lineage(episode.episode_id,
            claims=f.claims, log=f.log)[3])
        f.policy.allowed.remove((f.source_two.event_id, "personal_judgment"))
        opened = []
        self.enterContext(helpers.observe_private_opens(opened))
        with self.assertRaisesRegex(ValueError, "source use"):
            self.episodes.current_lineage(episode.episode_id, claims=f.claims, log=f.log)
        self.assertEqual(opened, [])

    def test_wrong_exact_contract_or_custody_digest_never_publishes(self):
        episode, artifact, _, _ = self.candidate()
        request, event = self.request(episode, artifact)
        wrong = EpisodeAcceptanceRequest.create(**{**{k:v for k,v in request.__dict__.items()
            if k != "request_sha256"}, "candidate_artifact_sha256": "c"*64})
        with self.assertRaisesRegex(ValueError, "request authority"):
            self.episodes.accept(request=wrong, request_event_id=event.event_id, **self.inputs())
        self.assertIsNone(self.episodes._head("fictional-thread"))
        self.custody.metadata = lambda _: None
        with self.assertRaisesRegex(ValueError, "exact earlier private"):
            self.episodes.accept(request=request, request_event_id=event.event_id, **self.inputs())
        self.assertIsNone(self.episodes._head("fictional-thread"))

    def test_denial_during_external_admission_never_publishes(self):
        episode, artifact, _, _ = self.candidate()
        request, event = self.request(episode, artifact)
        self.admission.on_adjudication = lambda: self.f.policy.allowed.discard(
            (self.f.source_one.event_id,"personal_judgment"))
        with self.assertRaisesRegex(ValueError, "not currently permitted"):
            self.episodes.accept(request=request, request_event_id=event.event_id, **self.inputs())
        self.assertIsNone(self.episodes._head("fictional-thread"))

    def test_new_accepted_generation_supersedes_current_use_not_original_candidate(self):
        first, a1, _, _ = self.candidate()
        p1, request1, event1 = self.accept(first,a1)
        second, a2, _, _ = self.candidate(2,first.episode_id)
        p2, _, _ = self.accept(second,a2,p1)
        with self.assertRaisesRegex(ValueError,"stale, superseded"):
            self.episodes.read_accepted(first.episode_id,**self.inputs())
        self.assertEqual(self.episodes.accept(request=request1,request_event_id=event1.event_id,
            **self.inputs()),p1)
        self.assertEqual(self.episodes._head("fictional-thread")["episode_id"],second.episode_id)
        self.assertEqual(self.episodes.read_accepted(second.episode_id,**self.inputs()).publication,p2)

    def test_episode_state_requires_actual_accepted_authority_and_rechecks_before_state_bytes(self):
        f=self.f
        episode, artifact, _, _=self.candidate()
        version, raw=self.derived_state(episode.episode_id)
        base=XTDBPersonalStateCandidates(scope=f.scope,authority_namespace_id=f.namespace,
            connection=f.connection)
        with self.assertRaisesRegex(ValueError,"governed accepted episode"):
            base.put_candidate(version,content=raw,**self.inputs())
        governed=XTDBGovernedPersonalDevelopment(scope=f.scope,authority_namespace_id=f.namespace,
            connection=f.connection,registry=f.registry,policy=f.policy,episodes=self.episodes)
        with self.assertRaisesRegex(ValueError,"no governed accepted"):
            governed.put_candidate(version,content=raw,**self.inputs())
        self.accept(episode,artifact)
        governed.put_candidate(version,content=raw,**self.inputs())
        self.assertEqual(governed.read_latest_candidate(**f.identity(),**self.inputs()).record["source_episode_ids"],
                         [episode.episode_id])
        f.policy.allowed.remove((f.source_one.event_id,"personal_judgment"))
        opened=[]
        self.enterContext(helpers.observe_private_opens(opened))
        with self.assertRaisesRegex(ValueError,"source use"):
            governed.read_latest_candidate(**f.identity(),**self.inputs())
        self.assertNotIn(raw.object_id,opened)

    def test_semantic_admission_revocation_is_rechecked_at_state_materialization(self):
        f=self.f
        episode,artifact,_,_=self.candidate()
        self.accept(episode,artifact)
        version,raw=self.derived_state(episode.episode_id)
        governed=XTDBGovernedPersonalDevelopment(scope=f.scope,authority_namespace_id=f.namespace,
            connection=f.connection,registry=f.registry,policy=f.policy,episodes=self.episodes)
        governed.put_candidate(version,content=raw,**self.inputs())
        self.admission.adjudicated.clear()
        opened=[]
        self.enterContext(helpers.observe_private_opens(opened))
        with self.assertRaisesRegex(ValueError,"qualified formation and independent"):
            governed.read_latest_candidate(**f.identity(),**self.inputs())
        self.assertNotIn(raw.object_id,opened)

    def test_stale_expected_accepted_predecessor_cannot_publish_new_generation(self):
        first,a1,_,_=self.candidate()
        p1,_,_=self.accept(first,a1)
        second,a2,_,_=self.candidate(2,first.episode_id)
        bad=replace(p1,episode_sha256="e"*64)
        request,event=self.request(second,a2,bad)
        with self.assertRaisesRegex(ValueError,"stale publication predecessor"):
            self.episodes.accept(request=request,request_event_id=event.event_id,**self.inputs())
        self.assertEqual(self.episodes._head("fictional-thread")["episode_id"],first.episode_id)

    def test_rejected_drafts_do_not_block_later_qualified_publication(self):
        first,a1,_,_=self.candidate()
        request,event=self.request(first,a1,adjudicate=False)
        with self.assertRaisesRegex(ValueError,"independent semantic"):
            self.episodes.accept(request=request,request_event_id=event.event_id,**self.inputs())
        second,a2,_,_=self.candidate(2,first.episode_id)
        p2,_,_=self.accept(second,a2)
        self.assertEqual(self.episodes.read_accepted(second.episode_id,**self.inputs()).record[
            "supersedes_episode_id"],first.episode_id)
        third,a3,_,_=self.candidate(3,second.episode_id)
        request,event=self.request(third,a3,p2,adjudicate=False)
        with self.assertRaisesRegex(ValueError,"independent semantic"):
            self.episodes.accept(request=request,request_event_id=event.event_id,**self.inputs())
        fourth,a4,_,_=self.candidate(4,third.episode_id)
        p4,_,_=self.accept(fourth,a4,p2)
        accepted=self.episodes.read_accepted(fourth.episode_id,**self.inputs())
        self.assertEqual(accepted.record["generation"],4)
        self.assertEqual(accepted.record["supersedes_episode_id"],third.episode_id)
        self.assertEqual(accepted.publication,p4)

    def test_later_indirect_original_cannot_enter_an_earlier_episode(self):
        f=self.f
        late=f.event(b"fictional later evidence",timestamp="2026-09-29T12:00:00Z")
        f.register_source(late)
        f.policy.allowed.add((late.event_id,"personal_judgment"))
        with self.assertRaisesRegex(ValueError,"observed after formation"):
            self.candidate(extra=(late.event_id,))
        self.assertIsNone(self.episodes._head("fictional-thread"))

    def test_candidate_permission_revocation_during_derived_read_cannot_return_bytes(self):
        f=self.f
        _,_,summary,content=self.candidate()
        opened=[]
        def revoke(object_id):
            if object_id==summary.object_id:
                f.policy.allowed.discard((f.source_one.event_id,"personal_judgment"))
        self.enterContext(helpers.observe_private_opens(opened, revoke))
        with self.assertRaisesRegex(ValueError,"not currently permitted"):
            self.episodes.read_latest_candidate(thread_id="fictional-thread",**self.inputs())
        self.assertIn(summary.object_id,opened)
        self.assertNotIn(content.object_id,opened)

    def test_rollback_cannot_restore_a_superseded_episode_derived_state(self):
        f=self.f
        first,a1,_,_=self.candidate()
        p1,_,_=self.accept(first,a1)
        governed=XTDBGovernedPersonalDevelopment(scope=f.scope,authority_namespace_id=f.namespace,
            connection=f.connection,registry=f.registry,policy=f.policy,episodes=self.episodes)
        version,raw=self.derived_state(first.episode_id)
        governed.put_candidate(version,content=raw,**self.inputs())
        def approve(record,expected):
            approval=f.approval(record,expected)
            from flora.selected.governed_development import _version_from_record
            self.custody.register_approval(approval_event_id=approval.event_id,
                candidate=_version_from_record(record),expected_active_version_id=expected,
                raw=f.references[approval.payload_reference],log=f.log,objects=f.objects)
            return governed.activate(**f.identity(),approval_event_id=approval.event_id,
                expected_active_version_id=expected,verifier=f.verifier,**self.inputs())
        approve(version.metadata_record(),None)
        second_state,state_raw=f.version(2,source=f.source_two,previous=version.version_id)
        self.custody.record(artifact_id="fictional-direct-state-v2",kind="projection",
            contract=second_state.metadata_record(),attachments=(("content",state_raw),),
            parent_event_ids=(f.source_two.event_id,),log=f.log,objects=f.objects,
            occurred_at="2026-09-29T13:30:00Z",expected_revision=len(f.log.events)-1)
        governed.put_candidate(second_state,content=state_raw,
            expected_previous_version_id=version.version_id,**self.inputs())
        approve(second_state.metadata_record(),version.version_id)
        second_episode,a2,_,_=self.candidate(2,first.episode_id)
        self.accept(second_episode,a2,p1)
        opened=[]
        self.enterContext(helpers.observe_private_opens(opened))
        with self.assertRaisesRegex(ValueError,"stale, superseded"):
            governed.register_rollback(rollback_id="unsafe-episode-rollback",version_id="restored-state-v3",
                target_version_id=version.version_id,expected_active_version_id=second_state.version_id,
                expected_latest_version_id=second_state.version_id,produced_at="2026-09-29T14:00:00Z",
                verifier=f.verifier,**self.inputs())
        self.assertNotIn(raw.object_id,opened)
        self.assertEqual(governed.read_active(**f.identity(),verifier=f.verifier,
            **self.inputs()).record["version_id"],second_state.version_id)

    def test_external_admission_denial_prevents_any_later_private_read(self):
        f=self.f
        episode,artifact,summary,content=self.candidate()
        self.accept(episode,artifact)
        denied=[]
        opened=[]
        after_denial=[]
        def revoke():
            denied.append(True)
            f.policy.allowed.discard((f.source_one.event_id,"personal_judgment"))
        self.admission.on_adjudication=revoke
        def track(object_id):
            if denied:
                after_denial.append(object_id)
        self.enterContext(helpers.observe_private_opens(opened, before_open=track))
        with self.assertRaisesRegex(ValueError,"source use"):
            self.episodes.read_accepted(episode.episode_id,**self.inputs())
        self.assertTrue(denied)
        self.assertEqual(after_denial,[])

    def test_summary_read_revocation_prevents_content_open_inside_private_custody(self):
        f=self.f
        episode,artifact,summary,content=self.candidate()
        self.accept(episode,artifact)
        opened=[]
        def revoke_on_summary(object_id):
            if object_id==summary.object_id:
                f.policy.allowed.discard((f.source_one.event_id,"personal_judgment"))
        self.enterContext(helpers.observe_private_opens(opened, revoke_on_summary))
        with self.assertRaisesRegex(ValueError,"source use"):
            self.episodes.read_accepted(episode.episode_id,**self.inputs())
        self.assertIn(summary.object_id,opened)
        self.assertNotIn(content.object_id,opened)

    def test_manifest_read_revocation_prevents_both_private_attachments(self):
        f=self.f
        episode,artifact,summary,content=self.candidate()
        self.accept(episode,artifact)
        opened=[]
        def revoke_on_manifest(object_id):
            if object_id==artifact.manifest.object_id:
                f.policy.allowed.discard((f.source_one.event_id,"personal_judgment"))
        self.enterContext(helpers.observe_private_opens(opened, revoke_on_manifest))
        with self.assertRaisesRegex(ValueError,"source use"):
            self.episodes.read_accepted(episode.episode_id,**self.inputs())
        self.assertIn(artifact.manifest.object_id,opened)
        self.assertNotIn(summary.object_id,opened)
        self.assertNotIn(content.object_id,opened)

    def test_adjudication_request_read_revocation_prevents_candidate_private_open(self):
        f=self.f
        episode,artifact,summary,content=self.candidate()
        request,event=self.request(episode,artifact)
        opened=[]
        def revoke_on_request(object_id):
            if object_id==event.payload_reference:
                f.policy.allowed.discard((f.source_one.event_id,"personal_judgment"))
        self.enterContext(helpers.observe_private_opens(opened, revoke_on_request))
        with self.assertRaisesRegex(ValueError,"source use"):
            self.episodes.accept(request=request,request_event_id=event.event_id,**self.inputs())
        self.assertIn(event.payload_reference,opened)
        self.assertNotIn(artifact.manifest.object_id,opened)
        self.assertNotIn(summary.object_id,opened)
        self.assertNotIn(content.object_id,opened)
        self.assertIsNone(self.episodes._head("fictional-thread"))

    def test_candidate_read_summary_denial_blocks_later_content_plaintext(self):
        f=self.f
        _,_,summary,content=self.candidate()
        opened=[]
        def deny_on_summary(object_id):
            if object_id==summary.object_id:
                f.policy.allowed.discard((f.source_one.event_id,"personal_judgment"))
        self.enterContext(helpers.observe_private_opens(opened, deny_on_summary))
        with self.assertRaisesRegex(ValueError,"source use"):
            self.episodes.read_latest_candidate(thread_id="fictional-thread",**self.inputs())
        self.assertIn(summary.object_id,opened)
        self.assertNotIn(content.object_id,opened)

    def test_candidate_put_summary_denial_blocks_later_content_plaintext(self):
        f=self.f
        episode,_,summary,content=self.candidate()
        opened=[]
        def deny_on_summary(object_id):
            if object_id==summary.object_id:
                f.policy.allowed.discard((f.source_one.event_id,"personal_judgment"))
        self.enterContext(helpers.observe_private_opens(opened, deny_on_summary))
        with self.assertRaisesRegex(ValueError,"source use"):
            self.episodes.put_candidate(episode,thread_id="fictional-thread",summary=summary,
                content=content,**self.inputs())
        self.assertIn(summary.object_id,opened)
        self.assertNotIn(content.object_id,opened)

    def test_superseded_unaccepted_candidate_refused_before_its_private_artifact(self):
        f=self.f
        first,artifact,summary,content=self.candidate()
        request,event=self.request(first,artifact)
        self.candidate(2,first.episode_id)
        opened=[]
        self.enterContext(helpers.observe_private_opens(opened))
        with self.assertRaisesRegex(ValueError,"stale candidate head"):
            self.episodes.accept(request=request,request_event_id=event.event_id,**self.inputs())
        self.assertNotIn(artifact.manifest.object_id,opened)
        self.assertNotIn(summary.object_id,opened)
        self.assertNotIn(content.object_id,opened)

    def test_request_cipher_lookup_denial_prevents_request_plaintext_get(self):
        f=self.f
        episode,artifact,_,_=self.candidate()
        request,event=self.request(episode,artifact)
        backend_get=f.objects.backend.get_object
        opened=[]
        def deny_on_cipher(namespace,object_id):
            cipher=backend_get(namespace,object_id)
            if object_id==event.payload_reference:
                f.policy.allowed.discard((f.source_one.event_id,"personal_judgment"))
            return cipher
        f.objects.backend.get_object=deny_on_cipher
        self.enterContext(helpers.observe_private_opens(opened))
        with self.assertRaisesRegex(ValueError,"source use"):
            self.episodes.accept(request=request,request_event_id=event.event_id,**self.inputs())
        self.assertNotIn(event.payload_reference,opened)
        self.assertNotIn(artifact.manifest.object_id,opened)

    def test_candidate_head_race_during_gate_capture_cannot_open_a_different_draft(self):
        f=self.f
        self.candidate()
        original_fetch=self.episodes._fetch
        reads=[]
        def advance_during_capture(table,key,**kwargs):
            if table=="flora_episode_candidate_heads":
                reads.append(key)
                if len(reads)==2:
                    f.connection.rows[(table,key)]["episode_id"]="fictional-newer-draft"
            return original_fetch(table,key,**kwargs)
        self.episodes._fetch=advance_during_capture
        opened=[]
        self.enterContext(helpers.observe_private_opens(opened))
        with self.assertRaisesRegex(ValueError,"changed before private read"):
            self.episodes.read_latest_candidate(thread_id="fictional-thread",**self.inputs())
        self.assertEqual(opened,[])
