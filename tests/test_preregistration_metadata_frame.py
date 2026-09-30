"""Actual typed slot predicates over controlled SQL/Kurrent transports.

Original integration setup supplies signed fictional producers. These tests
qualify metadata boundaries/call counts, not physical latency or learning.
"""
import ast
from collections import Counter
from copy import deepcopy
from contextlib import ExitStack
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

from kurrentdbclient import StreamState
from flora.selected.experiment_preregistration import _SlotMetadataFrame
from flora.selected.phase_source_fence import OneGuardSelectedMetadata
from metadata_batch_fixture import install_current_metadata_batch
from test_selected_formation_registry import _SQLCalls
from test_phase_snapshots import PhaseSQL


class _RecordedKurrentClient:
    def __init__(self, *args, **kwargs):
        self.streams, self.calls = {}, Counter()
    def close(self):
        pass
    def get_stream(self, *, stream_name):
        self.calls['get_stream'] += 1
        return tuple(self.streams.get(stream_name, ()))
    def append_to_stream(self, *, stream_name, current_version, events):
        rows = self.streams.setdefault(stream_name, [])
        if current_version != (StreamState.NO_STREAM if not rows else len(rows)-1):
            raise ValueError('controlled stale canonical append')
        for event in events:
            if any(prior.id == event.id for prior in rows):
                raise ValueError('controlled duplicate canonical event')
            rows.append(SimpleNamespace(id=event.id,type=event.type,data=event.data,
                stream_position=len(rows),recorded_at=datetime.now(timezone.utc)))


def _typed_fixture():
    # Truncate only the original integration fixture after complete registration
    # and its expected premature-AFTER denial, before any private phase capture.
    root=Path(__file__).parent
    integration=root/'integration'
    if str(integration) not in sys.path:
        sys.path.insert(0,str(integration))
    path=integration/'test_selected_experiment_preregistration.py'
    spec=importlib.util.spec_from_file_location('flora_slot_metadata_typed_fixture',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tree=ast.parse(path.read_text(),filename=str(path))
    klass=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='SelectedPreregisteredPhaseRoutesTest')
    method=next(n for n in klass.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_anchor_before_seal_actual_head'))
    for index,node in enumerate(method.body):
        if isinstance(node,ast.For) and isinstance(node.iter,ast.Name) and node.iter.id=='slots':
            method.body=method.body[:index]+[ast.parse('return (store, f, slots[0], context_plan, histories[("case", "before")])').body[0]]
            break
    namespace=dict(vars(module))
    rewritten=ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[]))
    exec(compile(rewritten,str(path),'exec'),namespace)
    setattr(module.SelectedPreregisteredPhaseRoutesTest,method.name,namespace[method.name])
    connection=PhaseSQL(_SQLCalls())
    connection.close=lambda:None
    install_current_metadata_batch(connection)
    fabric=module.support._rf._fabric_fixture
    with ExitStack() as stack:
        stack.enter_context(patch.object(fabric.psycopg,'connect',lambda *a,**kw:connection))
        stack.enter_context(patch.object(fabric,'KurrentDBClient',_RecordedKurrentClient))
        case=module.SelectedPreregisteredPhaseRoutesTest(method.name)
        case.setUp()
        result=getattr(case,method.name)()
    return case,connection,result


class PreregistrationMetadataFrameTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case,cls.connection,(cls.store,cls.f,cls.slot,cls.plan,cls.history)=_typed_fixture()
        cls.addClassCleanup(cls.case.doCleanups)

    def arguments(self):
        return dict(capture=True,snapshot_id=self.slot.snapshot_id,case_id=self.slot.case_id,
            phase=self.slot.phase,arm=self.slot.arm,history=self.history,plan=self.plan)

    def setUp(self):
        # Isolation of explicitly controlled transports, not a live-head reset.
        rows = deepcopy(self.connection.rows)
        streams = {name: list(values) for name,values in self.f.log.client.streams.items()}
        self.addCleanup(setattr,self.connection,'rows',rows)
        self.addCleanup(setattr,self.f.log.client,'streams',streams)

    def measure(self, *, framed):
        from flora.selected.experiment_preregistration import XTDBExperimentPreregistrationCustody
        from flora.selected.experiment_manifests import SelectedSourceAuthority
        methods={XTDBExperimentPreregistrationCustody._current.__code__:'current',
            XTDBExperimentPreregistrationCustody._check_current.__code__:'predicates',
            SelectedSourceAuthority.gate.__code__:'gate'}
        counts=Counter()
        def profile(frame,event,arg):
            if event=='call' and frame.f_code in methods:
                counts[methods[frame.f_code]]+=1
        sql=len(self.connection.calls)
        replays=self.f.log.client.calls['get_stream']
        previous=sys.getprofile()
        sys.setprofile(profile)
        try:
            if framed:
                value=self.store._authorize_slot(**self.arguments())
            else:
                value=self.store._authorize_slot_body(**self.arguments())
        finally:
            sys.setprofile(previous)
        return value,counts,len(self.connection.calls)-sql,self.f.log.client.calls['get_stream']-replays

    def test_both_current_and_all_gate_predicates_survive_finite_same_call_batch(self):
        before=self.measure(framed=False)
        after=self.measure(framed=True)
        self.assertEqual(after[0],before[0])
        self.assertEqual(after[1],before[1])
        self.assertEqual(after[1]['current'],2)
        self.assertEqual(after[1]['predicates'],2)
        self.assertGreater(after[1]['gate'],10)
        self.assertLess(after[2],before[2])
        self.assertLess(after[3],before[3])
        self.assertIsNone(self.store._active_slot_frame())
        self.assertIsNotNone(_SlotMetadataFrame.create(self.store,plan=self.plan))
        print('[preregistration-metadata-frame] SQL=%d->%d canonical-replays=%d->%d current=%d predicates=%d gates=%d'
            % (before[2],after[2],before[3],after[3],after[1]['current'],after[1]['predicates'],after[1]['gate']),flush=True)

    def test_custom_reader_and_wrapped_sampler_use_original_uncached_route(self):
        actual = self.store.manifests.metadata
        calls = []
        def metadata(*args,**kwargs):
            calls.append(self.store._active_slot_frame())
            return actual(*args,**kwargs)
        with patch.object(self.store.manifests,'metadata',metadata):
            self.assertIsNone(_SlotMetadataFrame.create(self.store,plan=self.plan))
            self.store._authorize_slot(**self.arguments())
        self.assertTrue(calls)
        self.assertTrue(all(frame is None for frame in calls))
        original = OneGuardSelectedMetadata.prime_source_purposes
        def prime(*args,**kwargs):
            return original(*args,**kwargs)
        with patch.object(OneGuardSelectedMetadata,'prime_source_purposes',prime):
            self.assertIsNone(_SlotMetadataFrame.create(self.store,plan=self.plan))
            self.store._authorize_slot(**self.arguments())

    def test_final_fence_rejects_new_absent_provider_row_in_both_scopes(self):
        from cognitive_kernel.canonical import canonical_sha256
        from flora.selected.provider_attempt_custody import _TABLE
        task = next(iter(self.store.spec.provider_task_ids.values()))
        key = canonical_sha256([self.store.comparison.scope_digest,self.store.run_id,task,'task'])
        original = self.connection.execute
        for scope in (self.store.comparison.scope_digest,'0'*64):
            with self.subTest(scope=scope):
                changed = False
                def execute(sql,parameters):
                    nonlocal changed
                    if 'AS flora_current_metadata_fence LIMIT' in sql and not changed:
                        changed = True
                        self.connection.rows[(_TABLE,key)] = dict(_id=key,scope_digest=scope,
                            record_sha256='1'*64,record_json='{}')
                    return original(sql,parameters)
                try:
                    with patch.object(self.connection,'execute',execute):
                        with self.assertRaisesRegex(PermissionError,'terminal current row'):
                            self.store._authorize_slot(**self.arguments())
                    self.assertTrue(changed)
                finally:
                    self.connection.rows.pop((_TABLE,key),None)
        self.assertIsNone(self.store._active_slot_frame())

    def test_final_replay_rejects_new_canonical_stage_and_evaluation_without_index(self):
        from cognitive_kernel.contracts import ProvenanceReference
        from cognitive_kernel.experience import ExperienceEvent
        from flora.comparator import sha
        original = self.f.log.client.get_stream
        initial = list(self.f.log.client.streams[self.f.log.stream])
        cases = [('comparison_artifact','comparison:'+self.store.comparison._key(
            self.store.run_id,self.store.artifact_id('before_seal'))),
            ('qualified_model_input',self.slot.evaluation_invocation_id)]
        for kind,activity in cases:
            with self.subTest(kind=kind):
                calls = 0
                def get_stream(*,stream_name):
                    nonlocal calls
                    calls += 1
                    if calls == 2:
                        event = ExperienceEvent.create(event_type=kind,scope=self.f.scope,
                            occurred_at=self.f.fabric._time(),content_digest=sha(b'fictional late canonical marker'),
                            provenance=ProvenanceReference.create(provenance_type='generated_reconstruction',
                                source_reference_ids=('controlled-marker-object',),derivation_activity_id=activity,
                                responsible_component='comparison_custody'),retention_class='ordinary_experience',
                            storage_tier='raw_buffer',payload_reference='controlled-marker-object',parent_event_ids=())
                        self.f.log.append(event,expected_revision=len(initial)-1)
                    return original(stream_name=stream_name)
                try:
                    with patch.object(self.f.log.client,'get_stream',get_stream):
                        with self.assertRaisesRegex(PermissionError,'stage/update/evaluation canonical evidence changed'):
                            self.store._authorize_slot(**self.arguments())
                    self.assertEqual(calls,2)
                finally:
                    self.f.log.client.streams[self.f.log.stream] = list(initial)

    def test_final_sql_rejects_late_reader_namespace_and_input_drift(self):
        original_execute = self.connection.execute
        original_replay = self.f.log.replay
        original_namespace = self.store.comparison.authority_namespace_id
        original_plan = self.plan.purpose
        original_questions = self.store.questions
        original_dependencies = self.store.dependencies
        for kind in ('reader','namespace','plan','questions','dependencies'):
            with self.subTest(kind=kind):
                changed = False
                def execute(sql,parameters):
                    nonlocal changed
                    result = original_execute(sql,parameters)
                    if 'AS flora_current_metadata_fence LIMIT' in sql:
                        changed = True
                        if kind == 'reader':
                            self.f.log.replay = lambda: []
                        elif kind == 'namespace':
                            self.store.comparison.authority_namespace_id = 'changed-namespace'
                        elif kind == 'plan':
                            object.__setattr__(self.plan,'purpose','changed-purpose')
                        elif kind == 'questions':
                            self.store.questions = {key:b'changed question' for key in original_questions}
                        else:
                            self.store.dependencies = deepcopy(original_dependencies)
                            self.store.dependencies['cohort']['content_sha256'] = '0'*64
                    return result
                try:
                    with patch.object(self.connection,'execute',execute):
                        with self.assertRaises(PermissionError):
                            self.store._authorize_slot(**self.arguments())
                    self.assertTrue(changed)
                finally:
                    self.f.log.__dict__.pop('replay',None)
                    self.store.comparison.authority_namespace_id = original_namespace
                    object.__setattr__(self.plan,'purpose',original_plan)
                    self.store.questions = original_questions
                    self.store.dependencies = original_dependencies
        self.assertEqual(self.f.log.replay,original_replay)

    def test_last_actual_metadata_callback_owner_withdrawal_is_fenced_and_not_cached(self):
        from flora.selected.formation_policy import FormationPermissionAction, formation_permission_payload
        frozen = self.store._source_gates[0]
        source = self.f.registry.lookup(frozen['event_id'])
        prior = self.f.policy.current_action(frozen['event_id'],frozen['purpose'])
        previous_request = self.f.policy._stored_action(prior.action_id)['request_event_id']
        original = self.connection.execute
        withdrawn = False
        def execute(sql,parameters):
            nonlocal withdrawn
            if 'AS flora_current_metadata_fence LIMIT' in sql and not withdrawn:
                withdrawn = True
                action = FormationPermissionAction.create(scope=self.f.scope,authority_namespace_id=self.f.namespace,
                    action_id='slot-frame-late-owner-revoke',source_ref_id=source.evidence.ref_id,
                    source_registration_sha256=source.registration_sha256,purpose=frozen['purpose'],decision='revoke',
                    generation=prior.generation+1,previous_action_sha256=prior.action_sha256,
                    authorization_ref='fictional-enrolled-owner',authorized_at=self.f.fabric._time())
                event,raw = self.f.fabric._append(formation_permission_payload(action),
                    event_type='formation_permission_action',parents=(source.evidence.ref_id,previous_request),at=action.authorized_at)
                self.f.private.register_formation_permission(action=action,request_event_id=event.event_id,
                    raw=raw,log=self.f.log,objects=self.f.objects)
                self.f._persist_proof(event,'formation_permission')
                self.f.policy.apply(action,request_event_id=event.event_id,log=self.f.log,objects=self.f.objects,
                    references=self.f.references,verifier=self.f.owner_verifier)
            return original(sql,parameters)
        with patch.object(self.connection,'execute',execute):
            with self.assertRaisesRegex(PermissionError,'terminal current row'):
                self.store._authorize_slot(**self.arguments())
        self.assertTrue(withdrawn)
        with self.assertRaises(PermissionError):
            self.store._authorize_slot(**self.arguments())
        self.assertIsNone(self.store._active_slot_frame())
