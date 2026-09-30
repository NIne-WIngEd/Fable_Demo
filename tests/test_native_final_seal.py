"""Native anchored-run boundaries on fictional SQL and model fixture bytes.

Actual selected custody authenticates anchors; these are not trained-model or
backend-performance qualifications. Full producer seal tests belong to the
preregistration/phase suites.
"""
from dataclasses import replace
from copy import copy
import asyncio
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from flora.comparison_run import PreparationRequest
from flora.selected.comparison_custody import XTDBComparisonCustody, SelectedRunEvidencePolicy
from flora.selected.native_arm import NativePhaseSnapshotBinding
import native_contract_fixture as support


class NativeSnapshotHeaderTest(unittest.TestCase):
    def test_v2_requires_all_canonical_anchor_body_and_event_references(self):
        legacy = NativePhaseSnapshotBinding("run", "snapshot", "flora_full")
        self.assertEqual(legacy.record(), {"schema": "flora-native-phase-snapshot-binding-v1",
            "run_id": "run", "snapshot_id": "snapshot", "arm": "flora_full"})
        full = replace(legacy, preregistration_sha256="a" * 64, snapshot_sha256="b" * 64,
            event_id="capture-event", event_sha256="c" * 64)
        self.assertEqual(full.record()["schema"], "flora-native-phase-snapshot-binding-v2")
        for name in ("preregistration_sha256", "snapshot_sha256", "event_id", "event_sha256"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "together"):
                replace(full, **{name: None}).record()
        for name, value in (("preregistration_sha256", "A" * 64), ("snapshot_sha256", "x"),
                            ("event_sha256", "C" * 64), ("event_id", "Capture Event")):
            with self.subTest(name=name), self.assertRaises(ValueError):
                replace(full, **{name: value}).record()


class NativeFinalBoundaryTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = support.NativeContractFixture(self.tmp.name)

    async def asyncTearDown(self):
        await self.f.close()
        self.tmp.cleanup()

    def request(self):
        return PreparationRequest("case-one", "after", self.f.question,
            self.f.histories[("case-one", "after")], self.f.plan)

    def selected_custody(self):
        custody = XTDBComparisonCustody(scope=self.f.scope, authority_namespace_id=self.f.namespace,
            connection=self.f.f.connection, registry=self.f.runtime.sources,
            objects=self.f.runtime.objects, log=self.f.runtime.log)
        def bound_current_reader(runtime, lineage):
            owned = copy(custody)
            owned._physical_custody = getattr(custody, "_physical_custody", custody)
            owned.connection, owned.registry, owned.objects = runtime.sources.connection, runtime.sources, runtime.objects
            owned.raw_custody = type(custody.raw_custody)(registry=runtime.sources, objects=runtime.objects)
            lineage.history_authority = SelectedRunEvidencePolicy(custody=owned, run_id="native-fixture-run",
                permissions=runtime.source_policy)
        self.f.read_hook = bound_current_reader
        return custody

    def anchor(self, custody):
        return custody._put(run_id="native-fixture-run", artifact_id="preregistration",
            kind="preregistration_anchor", content=b"fictional anchored design",
            parents=(self.f.histories[("case-one", "after")].event_ids[0],),
            metadata={"preregistration_sha256": "a" * 64}, occurred_at=self.f.runtime.clock())

    async def test_unregistered_custody_is_explicit_fixture_only(self):
        adapter = self.f.new_adapter(allow_unregistered_fixture_run=False)
        with self.assertRaisesRegex(PermissionError, "actual registered selected custody"):
            await adapter.prepare(self.request())
        self.assertEqual(self.f.opened_connections, [])

    async def test_fixture_flag_cannot_bypass_actual_selected_custody(self):
        custody = self.selected_custody()
        with self.assertRaisesRegex(ValueError, "only for explicitly unregistered"):
            self.f.new_adapter(custody=custody)

    async def test_actual_durable_anchor_blocks_dispatch_when_optional_authority_omitted(self):
        custody = self.selected_custody()
        self.anchor(custody)
        adapter = self.f.new_adapter(custody=custody, allow_unregistered_fixture_run=False)
        with patch.object(self.f.worker, "verify_identity", side_effect=AssertionError("qualified before seal")):
            with self.assertRaisesRegex(PermissionError, "actual final binding"):
                await adapter.prepare(self.request())
        self.assertTrue(all(connection.closed for connection in self.f.opened_connections))

    async def test_canonical_anchor_without_registry_index_cannot_downgrade_to_legacy(self):
        custody = self.selected_custody()
        original = custody.connection.execute
        def lose_index(query, parameters):
            if query.startswith("INSERT") and parameters[0] == custody._key("native-fixture-run", "preregistration"):
                raise RuntimeError("fictional interrupted anchor index")
            return original(query, parameters)
        with patch.object(custody.connection, "execute", side_effect=lose_index), self.assertRaises(RuntimeError):
            self.anchor(custody)
        adapter = self.f.new_adapter(custody=custody, allow_unregistered_fixture_run=False)
        with self.assertRaisesRegex(PermissionError, "explicit index reconciliation"):
            await adapter.prepare(self.request())
        self.assertTrue(all(connection.closed for connection in self.f.opened_connections))

    async def test_anchor_added_during_worker_qualification_blocks_private_preparation(self):
        custody = self.selected_custody()
        adapter = self.f.new_adapter(custody=custody, allow_unregistered_fixture_run=False)
        with patch.object(self.f.worker, "verify_identity", side_effect=lambda: self.anchor(custody)):
            with self.assertRaisesRegex(PermissionError, "actual final binding"):
                await adapter.prepare(self.request())
        self.assertTrue(all(connection.closed for connection in self.f.opened_connections))

    async def test_current_metadata_stall_is_owned_and_timed_without_blocking_event_loop(self):
        custody = self.selected_custody()
        self.f.plan = replace(self.f.plan, protocol=replace(self.f.plan.protocol, wall_time_budget_ms=120))
        self.f.lineage.run_plan_sha256 = self.f.plan.digest()
        adapter = self.f.new_adapter(custody=custody, allow_unregistered_fixture_run=False)
        started, release = threading.Event(), threading.Event()
        original = custody.connection.execute
        def stalled(sql, parameters):
            if sql.startswith("SELECT * FROM flora_comparison_artifacts"):
                started.set()
                release.wait(1)
            return original(sql, parameters)
        ticks = []
        async def tick():
            while not release.is_set():
                ticks.append(True)
                await asyncio.sleep(.01)
        ticker = asyncio.create_task(tick())
        beginning = time.monotonic()
        try:
            with patch.object(custody.connection, "execute", side_effect=stalled):
                with self.assertRaises(TimeoutError):
                    await adapter.prepare(self.request())
            self.assertTrue(started.is_set())
            self.assertGreater(len(ticks), 3)
            self.assertLess(time.monotonic() - beginning, .8)
            self.assertEqual(self.f.custody.registrations, [])
        finally:
            release.set()
            await ticker
            await self.f.reads.aclose()

    async def test_anchored_header_never_uses_fictional_phase_authority(self):
        entry = self.f.frozen.entry("case-one", "after")
        anchored = replace(entry, phase_snapshot=NativePhaseSnapshotBinding("native-fixture-run", "after", "flora_full",
            "a" * 64, "b" * 64, "capture", "c" * 64))
        with self.assertRaisesRegex(PermissionError, "actual selected final authority"):
            await self.f.reads.prepare_context(anchored)
        self.assertTrue(all(connection.closed for connection in self.f.opened_connections))

    async def test_native_header_cannot_mix_anchored_and_legacy_phases(self):
        before, after = self.f.frozen.entries
        anchored = replace(after, phase_snapshot=NativePhaseSnapshotBinding("native-fixture-run", "after", "flora_full",
            "a" * 64, "b" * 64, "capture", "c" * 64))
        with self.assertRaisesRegex(ValueError, "complete snapshots"):
            replace(self.f.frozen, entries=(before, anchored)).record()

    async def test_owned_read_detects_actual_anchor_before_any_private_plaintext(self):
        custody = self.selected_custody()
        self.anchor(custody)
        def bind_actual_authority(runtime, lineage):
            selected = XTDBComparisonCustody(scope=runtime.scope,
                authority_namespace_id=runtime.authority_namespace_id,
                connection=runtime.sources.connection, registry=runtime.sources,
                objects=runtime.objects, log=runtime.log)
            lineage.history_authority = SelectedRunEvidencePolicy(custody=selected,
                run_id="native-fixture-run", permissions=runtime.source_policy)
        self.f.read_hook = bind_actual_authority
        backend = self.f.runtime.objects.backend
        with patch.object(backend, "get_object", side_effect=AssertionError("opened before final seal")) as opened:
            with self.assertRaisesRegex(PermissionError, "actual final binding"):
                await self.f.reads.prepare_context(self.f.frozen.entry("case-one", "after"))
            opened.assert_not_called()
        self.assertTrue(all(connection.closed for connection in self.f.opened_connections))

    async def test_fixture_cannot_accept_anchored_plan_even_without_snapshot(self):
        phase_bindings = {("case-one", phase, arm): binding
            for phase in ("before", "after") for arm, binding in self.f.plan.arm_bindings.items()}
        plan = replace(self.f.plan, phase_bindings=phase_bindings, preregistration_sha256="a" * 64)
        adapter = self.f.new_adapter(run_plan=plan)
        with self.assertRaisesRegex(PermissionError, "actual registered selected custody"):
            await adapter.prepare(replace(self.request(), plan=plan))
        self.assertEqual(self.f.opened_connections, [])


if __name__ == "__main__":
    unittest.main()
