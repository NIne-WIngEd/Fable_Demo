"""Synthetic workflow used only to qualify selected Temporal restart recovery.

No model or semantic inference is represented. The first activity must remain
completed while a waiting workflow survives server/database/worker restart.
"""

from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn
class SelectedTemporalRestartProbe:
    def __init__(self):
        self.phase = "starting"
        self.resumed = False

    @workflow.query
    def current_phase(self) -> str:
        return self.phase

    @workflow.signal
    def resume(self) -> None:
        self.resumed = True

    @workflow.run
    async def run(self, marker: str) -> dict:
        options = dict(start_to_close_timeout=timedelta(seconds=20),
                       retry_policy=RetryPolicy(maximum_attempts=3))
        first = await workflow.execute_activity(
            "flora-temporal-restart-effect-v1", {"marker": marker, "stage": 1}, **options)
        self.phase = "waiting"
        await workflow.wait_condition(lambda: self.resumed)
        second = await workflow.execute_activity(
            "flora-temporal-restart-effect-v1", {"marker": marker, "stage": 2}, **options)
        self.phase = "completed"
        return {"marker": marker, "first": first, "second": second}
