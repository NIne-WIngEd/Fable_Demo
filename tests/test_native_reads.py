"""Passive selected-reader ownership/order mechanics; SQL remains a fixture.

Actual runtime/current lineage readers are exercised, with strict existing
custody. These cases do not qualify real backend deadlines or model outputs.
"""
import asyncio
from copy import copy
from dataclasses import replace
import importlib.util
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from metadata_batch_fixture import install_current_metadata_batch

from flora.comparison_run import ArmResult, ExecutionRequest, PreparationRequest
from flora.selected.native_reads import ReadOnlyNativeSQLConnection
from flora.selected.native_reads import SelectedNativeReadServices
from flora.selected.native_arm import NativePhaseSnapshotBinding
from flora.selected.phase_routes import SelectedPhaseRoute
from flora.selected.phase_snapshots import XTDBPhaseSnapshotCustody
from flora.selected.comparison_custody import XTDBComparisonCustody, SelectedRunEvidencePolicy, evaluation_purpose
from flora.selected.formation_policy import FormationPermissionAction, XTDBFormationPermissionPolicy, formation_permission_payload
from cognitive_kernel.contracts import ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent


spec = importlib.util.spec_from_file_location("flora_native_reads_support", Path(__file__).parent / "native_contract_fixture.py")
support = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = support
spec.loader.exec_module(support)

phase_spec = importlib.util.spec_from_file_location("flora_native_read_phase_support",
    Path(__file__).parent / "test_phase_snapshots.py")
phase_support = importlib.util.module_from_spec(phase_spec)
sys.modules[phase_spec.name] = phase_support
phase_spec.loader.exec_module(phase_support)


class NativeReadOwnershipTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = support.NativeContractFixture(self.tmp.name)
        self.entry = self.f.frozen.entry("case-one", "after")

    async def asyncTearDown(self):
        await self.f.close()
        self.tmp.cleanup()

    def request(self):
        history = self.f.histories[("case-one", "after")]
        return ExecutionRequest("case-one", "after", self.f.question, self.f.scope, history.digest(),
            history.event_ids, self.f.context, self.f.plan.arm_bindings["flora_full"], self.f.plan)

    async def test_actual_context_recovery_and_phase_proof_use_fresh_read_only_sessions(self):
        before = len(self.f.f.connection.calls)
        context = await self.f.reads.prepare_context(self.entry)
        self.assertEqual(context, self.f.context)
        self.assertTrue(await self.f.reads.authorize_context(entry=self.entry, request=self.request(),
            context=context, arm="flora_full"))
        actual = await self.f.reads.recover_judgment(entry=self.entry, request=self.request())
        result = ArmResult(actual.execution.result.output, actual.delivery, actual.decision, self.f.meter.usage)
        proof = await self.f.reads.verify_native_result(entry=self.entry, request=self.request(), result=result)
        self.assertEqual(actual, self.f.judgment)
        self.assertEqual(proof.qualified_output, actual.execution.output_record)
        self.assertEqual(len(self.f.opened_connections), 4)
        self.assertEqual(len(self.f.closed_connections), 4)
        self.assertTrue(all(sql.lstrip().startswith("SELECT ") for sql, params in self.f.f.connection.calls[before:]))

    async def test_constructor_or_recovery_write_attempt_is_denied_and_connection_closes(self):
        self.f.binder_hook = lambda connection: connection.execute("CREATE TABLE bad (x INT)")
        with self.assertRaises(PermissionError):
            await self.f.reads.prepare_context(self.entry)
        self.assertEqual(len(self.f.closed_connections), 1)
        self.f.binder_hook = None
        self.f.read_hook = lambda runtime, lineage: setattr(runtime.private, "read",
            lambda *args, **kwargs: runtime.private.connection.execute("INSERT INTO bad (x) VALUES (1)"))
        with self.assertRaises(PermissionError):
            await self.f.reads.recover_judgment(entry=self.entry, request=self.request())
        self.assertTrue(all(connection.closed for connection in self.f.opened_connections))

    async def test_cancelled_read_keeps_slot_until_thread_cleanup_and_never_infers_or_writes(self):
        started, release = threading.Event(), threading.Event()
        def delay(runtime, lineage):
            original = runtime._context
            def context(plan, **kwargs):
                started.set()
                release.wait(.3)
                return original(plan, **kwargs)
            runtime._context = context
        self.f.read_hook = delay
        task = asyncio.create_task(self.f.reads.prepare_context(self.entry))
        for _ in range(100):
            if started.is_set():
                break
            await asyncio.sleep(.003)
        self.assertTrue(started.is_set())
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        second = asyncio.create_task(self.f.reads.prepare_context(self.entry))
        await asyncio.sleep(.025)
        self.assertEqual(len(self.f.opened_connections), 1)
        self.assertEqual(len(self.f.closed_connections), 0)
        release.set()
        # With no unrelated event-loop timer, physical cleanup must wake the
        # waiter promptly instead of waiting for the15s component deadline.
        async with asyncio.timeout(3):
            await second
        self.assertEqual(len(self.f.opened_connections), 2)
        self.assertEqual(len(self.f.closed_connections), 2)
        self.assertEqual(self.f.custody.registrations, [])

    async def test_frozen_history_and_current_phase_permission_are_independent(self):
        request = self.request()
        with self.assertRaises(ValueError):
            await self.f.reads.authorize_context(entry=self.entry,
                request=replace(request, authorized_event_ids=()), context=self.f.context, arm="flora_full")
        self.f.f.permitted[0] = False
        self.assertFalse(await self.f.reads.authorize_context(entry=self.entry,
            request=request, context=self.f.context, arm="flora_full"))
        with self.assertRaises(PermissionError):
            await self.f.reads.recover_judgment(entry=self.entry, request=request)

    async def test_changed_factory_or_live_write_connection_is_rejected(self):
        original = self.f.factory.configuration_sha256
        self.f.factory.configuration_sha256 = "e" * 64
        with self.assertRaises(ValueError):
            await self.f.reads.prepare_context(self.entry)
        self.f.factory.configuration_sha256 = original
        self.f.read_hook = lambda runtime, lineage: setattr(runtime.artifacts, "connection", self.f.f.connection)
        with self.assertRaisesRegex(ValueError, "unguarded"):
            await self.f.reads.prepare_context(self.entry)

    async def test_denied_phase_or_future_original_is_rejected_before_plaintext_read(self):
        opened = []
        backend = self.f.runtime.objects.backend
        original = backend.get_object
        def observe(namespace, object_id):
            opened.append(object_id)
            return original(namespace, object_id)
        with patch.object(backend, "get_object", side_effect=observe):
            self.f.lineage.history_authority.allowed = False
            with self.assertRaises(PermissionError):
                await self.f.reads.prepare_context(self.entry)
            self.assertEqual(opened, [])
            self.f.lineage.history_authority.allowed = True
            before = self.f.frozen.entry("case-one", "before")
            with self.assertRaises(PermissionError):
                await self.f.reads.prepare_context(before)
            self.assertEqual(opened, [])

    async def test_phase_withdrawal_during_private_receipt_metadata_blocks_inner_decryption(self):
        """The pre-recovery check cannot authorize a later private object read."""
        revoked, opened = [False], []
        backend = self.f.runtime.objects.backend
        original_get = backend.get_object
        def watched_get(namespace, object_id):
            if revoked[0]:
                opened.append(object_id)
            return original_get(namespace, object_id)
        def delayed_metadata(runtime, lineage):
            fetch = runtime.private._fetch
            def withdraw_after_fetch(table, key):
                result = fetch(table, key)
                if (table == runtime.private.records and result is not None
                        and result.get("stage") == "qualified_model_input"):
                    lineage.history_authority.allowed = False
                    revoked[0] = True
                return result
            runtime.private._fetch = withdraw_after_fetch
        self.f.read_hook = delayed_metadata
        # Guarded planes deliberately invoke the real EncryptedObjectPlane
        # implementation. Observe the shared ciphertext backend, not an
        # overridable instance get/recover_reference method bypassed by it.
        with patch.object(backend, "get_object", side_effect=watched_get):
            with self.assertRaises(PermissionError):
                await self.f.reads.recover_judgment(entry=self.entry, request=self.request())
            self.assertTrue(revoked[0])
            self.assertEqual(opened, [])
            self.assertEqual(self.f.custody.registrations, [])

    async def test_closed_reader_cannot_dispatch_new_sessions(self):
        await self.f.reads.aclose()
        with self.assertRaises(ValueError):
            await self.f.reads.prepare_context(self.entry)
        self.assertEqual(self.f.opened_connections, [])

    async def test_model_phase_gate_does_not_mutate_shared_original_controller_policies(self):
        shared = []
        def capture(runtime, lineage):
            shared.append((runtime, runtime.source_policy, runtime.state, runtime.context_policy))
        self.f.read_hook = capture
        self.assertEqual(await self.f.reads.prepare_context(self.entry), self.f.context)
        runtime, original, original_state, original_context = shared[0]
        self.assertIsNot(runtime.source_policy, original)
        self.assertIsNot(runtime.state, original_state)
        self.assertIsNot(runtime.context_policy, original_context)
        self.assertIs(runtime.state.policy, runtime.source_policy)
        self.assertIs(runtime.context_policy.state, runtime.state)
        self.assertIs(runtime.context_policy.permissions, runtime.source_policy)
        self.assertIs(original_state.policy, original)
        self.assertIs(original_context.permissions, original)
        self.assertIs(original.permits.__self__, original)
        self.assertIs(original_context.allow_event.__self__, original_context)

    async def selected_route(self):
        """Actual selected-route code on explicitly fictional SQL/proof bytes."""
        connection = phase_support.PhaseSQL(self.f.f.connection)
        self.f.f.connection = connection
        for plane in (self.f.runtime.artifacts, self.f.runtime.claims, self.f.runtime.sources,
                      self.f.runtime.source_policy, self.f.runtime.candidates, self.f.runtime.state,
                      self.f.runtime.private, self.f.runtime.original_references.custody):
            plane.connection = connection
        self.entry = replace(self.entry,
            phase_snapshot=NativePhaseSnapshotBinding("native-fixture-run", "native-after-archive", "flora_full"))
        self.f.frozen = replace(self.f.frozen, entries=tuple(
            self.entry if entry.phase == "after" else entry for entry in self.f.frozen.entries))
        bindings = dict(self.f.plan.arm_bindings)
        bindings["flora_full"] = replace(bindings["flora_full"], lineage_sha256=self.f.frozen.lineage_sha256)
        self.f.plan = replace(self.f.plan, arm_bindings=bindings)
        self.f.lineage.run_plan_sha256 = self.f.plan.digest()
        custody = XTDBPhaseSnapshotCustody(runtime=self.f.runtime, run_id="native-fixture-run",
            run_plan_sha256=self.f.plan.digest(), clock=self.f.runtime.clock,
            allow_unregistered_fixture_route=True)
        self.snapshot = custody.capture(snapshot_id="native-after-archive", case_id="case-one", phase="after",
            arm="flora_full", plan=self.entry.context_plan, lineage=self.f.lineage,
            history=self.f.histories[("case-one", "after")])
        binder = self.f.factory.bind_initialized
        self.routes = []
        self.phase_hook = None
        def bind(connection):
            session = binder(connection)
            def resolve(*, entry, request, artifact_permissions):
                self.assertIs(session.runtime.claims.connection, connection)
                custody = XTDBPhaseSnapshotCustody(runtime=session.runtime, run_id=entry.phase_snapshot.run_id,
                    run_plan_sha256=session.lineage.run_plan_sha256, clock=session.runtime.clock,
                    artifact_permissions=artifact_permissions, allow_unregistered_fixture_route=True)
                route = SelectedPhaseRoute(custody=custody, snapshot_id=entry.phase_snapshot.snapshot_id,
                    history=session.lineage.history_for(entry.case_id, entry.phase),
                    history_authority=session.lineage.history_authority,
                    historical_bindings=session.runtime.bindings,
                    invocation_id_for=session.lineage.invocation_id_for)
                if self.phase_hook is not None:
                    self.phase_hook(route.runtime, route.lineage)
                self.routes.append(route)
                return route
            return replace(session, phase_route_for=resolve)
        self.f.factory.bind_initialized = bind
        await self.f.reads.aclose()
        self.f.read_manifest = replace(self.f.read_manifest, allow_current_fixture_route=False,
            maximum_read_wall_time_ms=30000)
        self.f.reads = SelectedNativeReadServices(manifest=self.f.read_manifest, factory=self.f.factory)

    async def test_production_reader_requires_predeclared_archive_and_fresh_resolver(self):
        await self.f.reads.aclose()
        self.f.read_manifest = replace(self.f.read_manifest, allow_current_fixture_route=False)
        self.f.reads = SelectedNativeReadServices(manifest=self.f.read_manifest, factory=self.f.factory)
        with self.assertRaisesRegex(PermissionError, "exact selected phase"):
            await self.f.reads.prepare_context(self.entry)
        entry = replace(self.entry, phase_snapshot=NativePhaseSnapshotBinding("run", "snapshot", "flora_full"))
        with self.assertRaisesRegex(PermissionError, "fresh-session resolver"):
            await self.f.reads.prepare_context(entry)
        self.assertTrue(all(connection.closed for connection in self.f.opened_connections))

    async def test_selected_phase_route_uses_actual_pinned_runtime_and_lineage_on_each_read(self):
        await self.selected_route()
        context = await self.f.reads.prepare_context(self.entry)
        self.assertEqual(context, self.f.context)
        self.assertTrue(await self.f.reads.authorize_context(entry=self.entry, request=self.request(),
            context=context, arm="flora_full"))
        judgment = await self.f.reads.recover_judgment(entry=self.entry, request=self.request())
        result = ArmResult(judgment.execution.result.output, judgment.delivery, judgment.decision, self.f.meter.usage)
        proof = await self.f.reads.verify_native_result(entry=self.entry, request=self.request(), result=result)
        self.assertEqual(judgment, self.f.judgment)
        self.assertEqual(proof.invocation_id, self.entry.invocation_id)
        self.assertEqual(len(self.routes), 4)
        self.assertEqual(len({id(route.runtime) for route in self.routes}), 4)
        self.assertTrue(all(route.lineage.runtime is route.runtime for route in self.routes))
        self.assertTrue(all(connection.closed for connection in self.f.opened_connections))
        self.assertEqual(self.f.custody.registrations, [])

    async def test_selected_phase_binding_run_snapshot_arm_and_context_are_exact(self):
        await self.selected_route()
        for binding in (replace(self.entry.phase_snapshot, run_id="other-run"),
                        replace(self.entry.phase_snapshot, snapshot_id="other-snapshot"),
                        replace(self.entry.phase_snapshot, arm="same_evidence_ablation")):
            with self.assertRaises((ValueError, PermissionError)):
                await self.f.reads.prepare_context(replace(self.entry, phase_snapshot=binding))
        with self.assertRaisesRegex(ValueError, "requested arm"):
            await self.f.reads.authorize_context(entry=self.entry, request=self.request(),
                context=self.f.context, arm="same_evidence_ablation")
        with self.assertRaisesRegex(ValueError, "frozen plan/content"):
            await self.f.reads.prepare_context(replace(self.entry, context_sha256="f" * 64))
        with self.assertRaises((ValueError, PermissionError)):
            await self.f.reads.prepare_context(replace(self.entry, phase="before"))

    async def test_plain_current_runtime_cannot_substitute_for_selected_phase_route(self):
        await self.selected_route()
        binder = self.f.factory.bind_initialized
        def invalid(connection):
            session = binder(connection)
            return replace(session, phase_route_for=lambda **kwargs: session)
        self.f.factory.bind_initialized = invalid
        with self.assertRaisesRegex(ValueError, "unrelated or unowned"):
            await self.f.reads.prepare_context(self.entry)
        self.assertEqual(self.routes, [])

    async def test_changed_production_question_or_context_is_denied_before_archive_plaintext(self):
        await self.selected_route()
        backend, opened = self.f.runtime.objects.backend, []
        original_get = backend.get_object
        def observe(namespace, object_id):
            opened.append(object_id)
            return original_get(namespace, object_id)
        altered = replace(self.f.context,
            items=(replace(self.f.context.items[0], content=b"changed fixture context"),))
        with patch.object(backend, "get_object", side_effect=observe):
            for request in (replace(self.request(), question=b"changed fixture question"),
                            replace(self.request(), context=altered)):
                with self.assertRaisesRegex(ValueError, "frozen question|frozen plan/content"):
                    await self.f.reads.recover_judgment(entry=self.entry, request=request)
                self.assertEqual(opened, [])
                self.assertEqual(self.routes, [])

    async def test_withdrawal_after_archive_constructor_prevents_recovery_private_fetch(self):
        await self.selected_route()
        revoked, opened = [False], []
        backend, original_get = self.f.runtime.objects.backend, self.f.runtime.objects.backend.get_object
        def observe(namespace, object_id):
            if revoked[0]:
                opened.append(object_id)
            return original_get(namespace, object_id)
        def withdraw(runtime, lineage):
            self.f.lineage.history_authority.allowed = False
            revoked[0] = True
        self.phase_hook = withdraw
        with patch.object(backend, "get_object", side_effect=observe):
            with self.assertRaises(PermissionError):
                await self.f.reads.recover_judgment(entry=self.entry, request=self.request())
        self.assertTrue(revoked[0])
        self.assertEqual(opened, [])
        self.assertEqual(self.f.custody.registrations, [])

    async def test_selected_route_metadata_revocation_blocks_private_receipt_recovery(self):
        await self.selected_route()
        revoked, reads = [False], []
        backend = self.f.runtime.objects.backend
        original_get = backend.get_object
        def observe(namespace, object_id):
            if revoked[0]:
                reads.append(object_id)
            return original_get(namespace, object_id)
        def withdraw(runtime, lineage):
            original = runtime.private._fetch
            def fetch(table, key):
                result = original(table, key)
                if table == runtime.private.records and result is not None and result.get("stage") == "qualified_model_input":
                    self.f.lineage.history_authority.allowed = False
                    revoked[0] = True
                return result
            runtime.private._fetch = fetch
        self.phase_hook = withdraw
        with patch.object(backend, "get_object", side_effect=observe):
            with self.assertRaises(PermissionError):
                await self.f.reads.recover_judgment(entry=self.entry, request=self.request())
            self.assertTrue(revoked[0])
            self.assertEqual(reads, [])

    async def test_actual_selected_history_controller_uses_separate_policy_without_recursion(self):
        """Actual custody/controller/current grants on explicit fictional SQL."""
        runtime, run_id = self.f.runtime, "native-fixture-run"
        install_current_metadata_batch(runtime.claims.connection)
        policy = XTDBFormationPermissionPolicy(scope=runtime.scope,
            authority_namespace_id=runtime.authority_namespace_id,
            connection=runtime.claims.connection, registry=runtime.sources)
        runtime.source_policy, runtime.state.policy, runtime.context_policy.permissions = policy, policy, policy
        action_number = 0
        def grant(event_id, purpose, decision="allow"):
            nonlocal action_number
            action_number += 1
            source = runtime.sources.lookup(event_id)
            previous = policy.current_action(event_id, purpose)
            prior_record = None if previous is None else policy._stored_action(previous.action_id)
            action = FormationPermissionAction.create(scope=runtime.scope,
                authority_namespace_id=runtime.authority_namespace_id,
                action_id="native-controller-fixture-" + str(action_number),
                source_ref_id=event_id, source_registration_sha256=source.registration_sha256,
                purpose=purpose, decision=decision, generation=1 if previous is None else previous.generation + 1,
                previous_action_sha256=None if previous is None else previous.action_sha256,
                authorization_ref="fictional-supplied-owner-proof", authorized_at=runtime.clock())
            raw = runtime.objects.put(formation_permission_payload(action))
            parents = (event_id,) if prior_record is None else tuple(sorted((event_id, prior_record["request_event_id"])))
            event = ExperienceEvent.create(event_type="formation_permission_action", scope=runtime.scope,
                occurred_at=action.authorized_at, content_digest=raw.plaintext_sha256,
                provenance=ProvenanceReference.create(provenance_type="generated_reconstruction",
                    source_reference_ids=parents, derivation_activity_id="native_controller_fixture",
                    responsible_component="fictional-supplied-owner-proof"),
                retention_class="ordinary_experience", storage_tier="raw_buffer",
                parent_event_ids=parents, payload_reference=raw.object_id)
            runtime.log.append(event, expected_revision=len(runtime.log.replay()) - 1)
            policy.apply(action, request_event_id=event.event_id, log=runtime.log,
                objects=runtime.objects, references={raw.object_id: raw},
                verifier=SimpleNamespace(authorized_action=lambda *args: True))
        for event_id in self.f.histories[("case-one", "after")].event_ids:
            grant(event_id, "personal_judgment")
        custody = XTDBComparisonCustody(scope=runtime.scope, authority_namespace_id=runtime.authority_namespace_id,
            connection=runtime.claims.connection, registry=runtime.sources, objects=runtime.objects, log=runtime.log)
        custody.register_inputs(run_id=run_id, plan=self.f.plan, histories=self.f.histories,
            questions={"case-one": self.f.question}, occurred_at=runtime.clock())
        for phase in ("before", "after"):
            history = self.f.histories[("case-one", phase)]
            purpose = evaluation_purpose(run_id, "case-one", phase)
            frame = custody.metadata(run_id, "history:case-one:" + phase)
            for event_id in history.event_ids + (frame.event_id,):
                grant(event_id, purpose)
        # One lineage call authenticates selected history once. Later actual
        # producer callbacks must use current metadata and refuse withdrawal,
        # without reopening the already authenticated originals.
        authority = SelectedRunEvidencePolicy(custody=custody, run_id=run_id, permissions=policy)
        lineage = copy(self.f.lineage)
        lineage.history_authority = authority
        authenticate = authority.authorize_history
        raw_read = custody.raw_custody.read
        initial_calls = []
        def authenticate_once(**kwargs):
            custody.raw_custody.read = raw_read
            initial_calls.append(kwargs["phase"])
            allowed = authenticate(**kwargs)
            custody.raw_custody.read = lambda *args: self.fail("lineage reopened held history ciphertext")
            return allowed
        authority.authorize_history = authenticate_once
        try:
            lineage.context_lineage(case_id="case-one", phase="after",
                history=self.f.histories[("case-one", "after")], context=self.f.context)
            self.assertEqual(initial_calls, ["after"])
            qualifier = runtime.bindings["memory_formation"].qualification_verifier
            prior_callback = qualifier.callback
            qualifier.callback = lambda: grant(self.f.histories[("case-one", "after")].event_ids[0],
                evaluation_purpose(run_id, "case-one", "after"), "revoke")
            try:
                with self.assertRaises(PermissionError):
                    lineage.context_lineage(case_id="case-one", phase="after",
                        history=self.f.histories[("case-one", "after")], context=self.f.context)
                self.assertEqual(initial_calls, ["after", "after"])
            finally:
                qualifier.callback = prior_callback
                grant(self.f.histories[("case-one", "after")].event_ids[0],
                    evaluation_purpose(run_id, "case-one", "after"))
        finally:
            custody.raw_custody.read = raw_read
        controllers, session_authentications = [], []
        def actual_controller(session_runtime, lineage):
            selected_custody = XTDBComparisonCustody(scope=session_runtime.scope,
                authority_namespace_id=session_runtime.authority_namespace_id,
                connection=session_runtime.claims.connection, registry=session_runtime.sources,
                objects=session_runtime.objects, log=session_runtime.log)
            lineage.history_authority = SelectedRunEvidencePolicy(custody=selected_custody,
                run_id=run_id, permissions=session_runtime.source_policy)
            full_authenticate = lineage.history_authority.authorize_history
            calls = []
            session_authentications.append(calls)
            def authenticate_history(**kwargs):
                calls.append(kwargs["phase"])
                return full_authenticate(**kwargs)
            lineage.history_authority.authorize_history = authenticate_history
            controllers.append((session_runtime, lineage))
        self.f.read_hook = actual_controller
        self.assertEqual(await self.f.reads.prepare_context(self.entry), self.f.context)
        self.assertEqual(session_authentications, [["after"]])
        self.assertTrue(await self.f.reads.authorize_context(entry=self.entry, request=self.request(),
            context=self.f.context, arm="flora_full"))
        self.assertEqual(session_authentications, [["after"], ["after", "after"]])
        for session_runtime, lineage in controllers:
            self.assertIsNot(lineage.history_authority.permissions, session_runtime.source_policy)
            self.assertIs(lineage.history_authority.permissions.connection, session_runtime.claims.connection)
        grant(self.f.histories[("case-one", "after")].event_ids[0],
              evaluation_purpose(run_id, "case-one", "after"), "revoke")
        with self.assertRaises(PermissionError):
            await self.f.reads.prepare_context(self.entry)


class ReadOnlySQLGuardTest(unittest.TestCase):
    def test_stacked_queries_transactions_and_cross_thread_access_are_denied(self):
        class Connection:
            closed = False
            prepare_threshold = 5
            def execute(self, sql, params):
                return (sql, params)
            def close(self):
                self.closed = True
        raw = Connection()
        connection = ReadOnlyNativeSQLConnection(raw, read_timeout_ms=100)
        self.assertEqual(connection.prepare_threshold, 5)
        connection.prepare_threshold = None
        self.assertIsNone(raw.prepare_threshold)
        with self.assertRaises(PermissionError):
            connection.prepare_threshold = 1
        self.assertEqual(connection.execute("SELECT * FROM approved WHERE _id = %s", ("x",))[1], ("x",))
        for sql in ("SELECT 1; DROP TABLE bad", "DELETE FROM bad", "ASSERT EXISTS (SELECT 1)", "SET foo = 1"):
            with self.assertRaises(PermissionError):
                connection.execute(sql)
        with self.assertRaises(PermissionError):
            connection.transaction()
        errors = []
        def foreign():
            try:
                connection.execute("SELECT 1")
            except RuntimeError as error:
                errors.append(error)
        thread = threading.Thread(target=foreign)
        thread.start()
        thread.join()
        self.assertEqual(len(errors), 1)
        connection.close()
        self.assertTrue(raw.closed)


if __name__ == "__main__":
    unittest.main()
