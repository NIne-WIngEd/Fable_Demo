"""Actual orchestration/receipt checks with supplied fictional model outputs.

Worker fixture programs relay fixture receipts; they are not model factories.
The signed fictional meter is not evidence of actual model resource usage.
"""
import asyncio
from dataclasses import replace
import importlib.util
from pathlib import Path
import sys
import tempfile
import threading
import unittest

from flora.comparison_run import ArmExecutionFailure, ArmStopped, ExecutionRequest, PreparationRequest
from flora.selected.native_arm import FrozenNativeArmPlan


spec = importlib.util.spec_from_file_location("flora_native_arm_support", Path(__file__).parent / "native_contract_fixture.py")
support = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = support
spec.loader.exec_module(support)


class NativeArmContractTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = support.NativeContractFixture(self.tmp.name)

    async def asyncTearDown(self):
        await self.f.close()
        self.tmp.cleanup()

    def prep(self, phase="after", **changes):
        return replace(PreparationRequest("case-one", phase, self.f.question,
            self.f.histories[("case-one", phase)], self.f.plan), **changes)

    def execution(self, **changes):
        history = self.f.histories[("case-one", "after")]
        return replace(ExecutionRequest("case-one", "after", self.f.question, self.f.scope,
            history.digest(), history.event_ids, self.f.context, self.f.plan.arm_bindings["flora_full"], self.f.plan), **changes)

    async def execute(self):
        await self.f.adapter.prepare(self.prep())
        return await self.f.adapter.execute(self.execution())

    async def test_exact_actual_native_receipts_usage_and_registration_order(self):
        result = await self.execute()
        self.assertEqual(result.output, self.f.judgment.execution.result.output)
        self.assertEqual(result.usage, self.f.meter.usage)
        self.assertEqual(self.f.custody.registrations,
            [self.f.judgment.delivery, self.f.judgment.execution.output_record, self.f.judgment.decision])
        self.assertEqual(len(self.f.custody.contexts), 1)
        key = ("case-one", "after", "flora_full")
        self.assertEqual(self.f.adapter.execution_records[key], (self.execution(), result))
        with self.assertRaises(TypeError):
            self.f.adapter.execution_records[key] = None
        self.assertTrue(all(c.closed for c in self.f.opened_connections))

    async def test_missing_worker_codec_meter_or_reader_is_explicitly_unavailable(self):
        for name in ("worker", "codec", "reads", "meter"):
            adapter = self.f.new_adapter(**{name: None})
            with self.assertRaises(ArmStopped) as stopped:
                await adapter.prepare(self.prep())
            self.assertEqual(stopped.exception.status, "unavailable")
        self.assertEqual(self.f.custody.registrations, [])

    async def test_withheld_update_arm_remains_unavailable_without_actual_producer_route(self):
        frozen = replace(self.f.frozen, arm="same_evidence_ablation")
        bindings = dict(self.f.plan.arm_bindings)
        bindings[frozen.arm] = replace(bindings[frozen.arm], lineage_sha256=frozen.lineage_sha256)
        plan = replace(self.f.plan, arm_bindings=bindings)
        adapter = self.f.new_adapter(run_plan=plan, frozen=frozen)
        with self.assertRaises(ArmStopped) as stopped:
            await adapter.prepare(replace(self.prep(), plan=plan))
        self.assertEqual(stopped.exception.status, "unavailable")

    async def test_changed_frozen_context_question_history_and_worker_ports_are_rejected(self):
        for request in (self.prep(question=b"changed"),
                        self.prep(history=self.f.histories[("case-one", "before")])):
            with self.assertRaises(ValueError):
                await self.f.adapter.prepare(request)
        await self.f.adapter.prepare(self.prep())
        changed = replace(self.f.context, items=(replace(self.f.context.items[0], content=b"changed"),))
        with self.assertRaises(ValueError):
            await self.f.adapter.execute(self.execution(context=changed))
        self.f.codec.artifact_sha256 = "e" * 64
        with self.assertRaises(ValueError):
            await self.f.adapter.execute(self.execution())
        self.assertEqual(self.f.custody.registrations, [])

    async def test_changed_completion_or_meter_observation_never_registers_native_result(self):
        self.f.codec.change_completion = True
        with self.assertRaises(ValueError):
            await self.execute()
        self.assertEqual(self.f.custody.registrations, [])
        self.assertEqual(dict(self.f.adapter.observed_usage), {})

    async def test_invalid_meter_receipt_keeps_usage_unknown(self):
        self.f.meter.invalid = True
        with self.assertRaises(ValueError):
            await self.execute()
        self.assertEqual(dict(self.f.adapter.observed_usage), {})
        self.assertEqual(self.f.custody.registrations, [])

    async def test_current_phase_revocation_after_verified_meter_keeps_known_usage(self):
        self.f.meter.callback = lambda: self.f.f.permitted.__setitem__(0, False)
        with self.assertRaises(ArmExecutionFailure) as stopped:
            await self.execute()
        self.assertEqual(stopped.exception.usage, self.f.meter.usage)
        self.assertEqual(stopped.exception.status, "invalid_result")
        self.assertEqual(self.f.custody.registrations, [])
        self.assertEqual(dict(self.f.adapter.execution_records), {})

    async def test_each_registration_is_preceded_by_fresh_authority(self):
        original = self.f.custody.register_recorded
        def revoke(recorded):
            original(recorded)
            self.f.f.permitted[0] = False
        self.f.custody.register_recorded = revoke
        with self.assertRaises(ArmStopped) as stopped:
            await self.execute()
        self.assertEqual(stopped.exception.status, "refused")
        self.assertEqual(stopped.exception.usage, self.f.meter.usage)
        self.assertEqual(self.f.custody.registrations, [self.f.judgment.delivery])
        self.assertEqual(self.f.custody.contexts, [])
        self.assertEqual(dict(self.f.adapter.execution_records), {})

    async def test_cancelled_encoder_does_not_block_event_loop_or_commit_later(self):
        await self.f.adapter.prepare(self.prep())
        started, release = threading.Event(), threading.Event()
        original = self.f.codec.encode_request
        def delayed(**kwargs):
            started.set()
            release.wait(2)
            return original(**kwargs)
        self.f.codec.encode_request = delayed
        task = asyncio.create_task(self.f.adapter.execute(self.execution()))
        try:
            for _ in range(200):
                if started.is_set():
                    break
                await asyncio.sleep(.005)
            self.assertTrue(started.is_set())
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertEqual(self.f.adapter._passive_reads.pending_count, 1)
            with self.assertRaisesRegex(ValueError, "already executing or accepted"):
                await self.f.adapter.execute(self.execution())
            release.set()
            for _ in range(100):
                if self.f.adapter._passive_reads.pending_count == 0:
                    break
                await asyncio.sleep(.005)
            self.assertEqual(self.f.adapter._passive_reads.pending_count, 0)
            self.assertEqual(self.f.custody.registrations, [])
            self.assertEqual(dict(self.f.adapter.execution_records), {})
        finally:
            release.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def test_native_invocation_cannot_execute_twice_or_without_preparation(self):
        with self.assertRaisesRegex(ValueError, "prepared deadline"):
            await self.f.adapter.execute(self.execution())
        await self.execute()
        with self.assertRaises(ValueError):
            await self.f.adapter.execute(self.execution())
        with self.assertRaises(ValueError):
            await self.f.adapter.prepare(self.prep())


if __name__ == "__main__":
    unittest.main()
