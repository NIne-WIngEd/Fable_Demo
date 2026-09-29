"""Real persistent Temporal recovery gate; no memory/model capability claim."""

import argparse
import asyncio
from datetime import timedelta
import os
import time

import psycopg
from temporalio import activity
from temporalio.api.workflowservice.v1 import DescribeNamespaceRequest
from temporalio.client import Client, WorkflowExecutionStatus
from temporalio.common import WorkflowIDReusePolicy
from temporalio.worker import Worker

from flora.selected.claims import configure_xtdb_connection, _rows
from flora.selected.temporal_recovery_probe import SelectedTemporalRestartProbe

MARKER = "fictional-persistent-temporal-probe-v1"
WORKFLOW_ID = "flora-selected-persistent-temporal-probe-v1"
QUEUE = "flora-selected-persistent-temporal-probe-v1"
TABLE = "flora_temporal_restart_effects"


def _connection():
    connection = psycopg.connect(os.environ.get(
        "XTDB_DSN", "postgresql://xtdb@127.0.0.1:5432/xtdb"), autocommit=True)
    configure_xtdb_connection(connection)
    return connection


def _effect_count(stage: int) -> int:
    with _connection() as connection:
        rows = _rows(connection.execute(
            f"SELECT invocations FROM {TABLE} WHERE _id = %s", (f"{MARKER}:{stage}",)))
        if len(rows) > 1:
            raise RuntimeError("ambiguous Temporal probe effect")
        return int(rows[0]["invocations"]) if rows else 0


@activity.defn(name="flora-temporal-restart-effect-v1")
async def record_effect(request: dict) -> dict:
    if request.get("marker") != MARKER or request.get("stage") not in (1, 2):
        raise ValueError("wrong synthetic Temporal probe request")
    stage = request["stage"]
    count = _effect_count(stage)
    key = f"{MARKER}:{stage}"
    with _connection() as connection:
        with connection.transaction():
            if count == 0:
                connection.execute(
                    f"ASSERT NOT EXISTS (SELECT 1 FROM {TABLE} WHERE _id = %s::text)", (key,))
            else:
                connection.execute(
                    f"ASSERT EXISTS (SELECT 1 FROM {TABLE} WHERE _id = %s::text AND invocations = %s)",
                    (key, count))
            connection.execute(
                f"INSERT INTO {TABLE} (_id, invocations) VALUES (%s::text, %s)", (key, count + 1))
    return {"stage": stage, "invocations": count + 1}


async def _client() -> Client:
    return await Client.connect(os.environ.get("TEMPORAL_ADDRESS", "127.0.0.1:7233"))


async def health(retry_seconds: int) -> None:
    deadline = time.monotonic() + retry_seconds
    last = "not connected"
    while True:
        try:
            client = await asyncio.wait_for(_client(), timeout=5)
            if not await client.service_client.check_health(timeout=timedelta(seconds=5)):
                raise RuntimeError("Temporal gRPC health is false")
            await client.workflow_service.describe_namespace(
                DescribeNamespaceRequest(namespace="default"), timeout=timedelta(seconds=5))
            print("Persistent Temporal server and namespace ready")
            return
        except Exception as error:
            last = type(error).__name__
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Persistent Temporal health unavailable: {last}")
        await asyncio.sleep(min(1, max(0, deadline - time.monotonic())))


async def write() -> None:
    if _effect_count(1) or _effect_count(2):
        raise RuntimeError("Temporal recovery fixture must start without effects")
    client = await _client()
    async with Worker(client, task_queue=QUEUE, workflows=[SelectedTemporalRestartProbe],
                      activities=[record_effect]):
        handle = await client.start_workflow(
            SelectedTemporalRestartProbe.run, MARKER, id=WORKFLOW_ID, task_queue=QUEUE,
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE)
        deadline = time.monotonic() + 40
        while await handle.query(SelectedTemporalRestartProbe.current_phase) != "waiting":
            if time.monotonic() >= deadline:
                raise RuntimeError("Temporal probe did not reach its pending checkpoint")
            await asyncio.sleep(0.1)
        if (_effect_count(1), _effect_count(2)) != (1, 0):
            raise RuntimeError("Temporal checkpoint has wrong completed/pending effects")
        print("Temporal workflow waiting; first activity completed once")


async def verify() -> None:
    client = await _client()
    handle = client.get_workflow_handle(WORKFLOW_ID)
    description = await handle.describe()
    if description.status != WorkflowExecutionStatus.RUNNING:
        raise RuntimeError("Pending Temporal workflow did not survive restart")
    history = await handle.fetch_history()
    completed = [event for event in history.events
                 if event.HasField("activity_task_completed_event_attributes")]
    if len(completed) != 1 or (_effect_count(1), _effect_count(2)) != (1, 0):
        raise RuntimeError("Completed activity history/effect was not retained")
    async with Worker(client, task_queue=QUEUE, workflows=[SelectedTemporalRestartProbe],
                      activities=[record_effect]):
        if await handle.query(SelectedTemporalRestartProbe.current_phase) != "waiting":
            raise RuntimeError("Restored Temporal worker did not replay the pending checkpoint")
        await handle.signal(SelectedTemporalRestartProbe.resume)
        result = await asyncio.wait_for(handle.result(), timeout=40)
        if result != {"marker": MARKER, "first": {"stage": 1, "invocations": 1},
                      "second": {"stage": 2, "invocations": 1}}:
            raise RuntimeError("Restored Temporal result differs from exact activity history")
        if (_effect_count(1), _effect_count(2)) != (1, 1):
            raise RuntimeError("Temporal replay reran a completed activity or duplicated an effect")
    print("Persistent Temporal workflow recovered and resumed without repeating the completed activity")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("health", "write", "verify"))
    parser.add_argument("--retry-seconds", type=int, default=0)
    args = parser.parse_args()
    if args.retry_seconds < 0:
        parser.error("retry-seconds must be nonnegative")
    if args.mode == "health":
        asyncio.run(health(args.retry_seconds))
    elif args.mode == "write":
        asyncio.run(write())
    else:
        asyncio.run(verify())


if __name__ == "__main__":
    main()
