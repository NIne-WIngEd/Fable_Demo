"""Write or verify a synthetic persistence probe across backend restarts."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import time

import psycopg
import nats
from kurrentdbclient import KurrentDBClient

from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from flora.selected.claims import configure_xtdb_connection
from flora.selected.experience import KurrentExperienceLog
from flora.selected.edge_ingress import EdgePacket, JetStreamEdgeIngress

MARKER = "selected-backend-persistence-v1"
PROBE_ID = "flora-selected-backend-restart-probe"
EDGE_MARKER = "selected-edge-persistence-v1"


def _scope() -> ProductHostScope:
    return ProductHostScope.create(
        product_id="friday",
        host_instance_id="restart-probe",
        schema_version="1.0.0",
        encryption_domain="restart-probe-key",
    )


def _event() -> ExperienceEvent:
    payload = MARKER.encode()
    return ExperienceEvent.create(
        event_type="observation",
        scope=_scope(),
        occurred_at="2026-09-28T20:30:00Z",
        content_digest=hashlib.sha256(payload).hexdigest(),
        provenance=ProvenanceReference.create(
            provenance_type="derived_inference",
            source_reference_ids=("restart-probe-source",),
            derivation_activity_id="restart-probe",
            responsible_component="synthetic-test",
        ),
        retention_class="ordinary_experience",
        storage_tier="raw_buffer",
        payload_reference="restart-probe-source",
    )


def _edge_scope() -> ProductHostScope:
    return ProductHostScope.create(
        product_id="friday", host_instance_id="edge-restart-probe",
        schema_version="1.0.0", encryption_domain="edge-restart-probe-key",
    )


def _edge_packet() -> EdgePacket:
    payload = EDGE_MARKER.encode()
    event = ExperienceEvent.create(
        event_type="observation", scope=_edge_scope(),
        occurred_at="2026-09-29T13:00:00Z",
        content_digest=hashlib.sha256(payload).hexdigest(),
        provenance=ProvenanceReference.create(
            provenance_type="derived_inference",
            source_reference_ids=("edge-restart-source",),
            derivation_activity_id="edge-restart-probe",
            responsible_component="synthetic-test",
        ),
        retention_class="ordinary_experience", storage_tier="raw_buffer",
        payload_reference="edge-restart-source",
    )
    return EdgePacket("synthetic-restart-device", 1, event)


async def _edge_probe(*, write: bool = False, consume: bool = False) -> None:
    client = await nats.connect(os.environ.get(
        "NATS_URI", "nats://127.0.0.1:4222"))
    event_client = KurrentDBClient(os.environ.get(
        "KURRENTDB_URI", "kurrentdb://127.0.0.1:2113?tls=false"))
    try:
        ingress = JetStreamEdgeIngress(scope=_edge_scope(),
                                       jetstream=client.jetstream())
        log = KurrentExperienceLog(scope=_edge_scope(), client=event_client)
        if write:
            await ingress.create_stream()
            await ingress.publish(_edge_packet())
        info = await ingress.js.stream_info(ingress.stream)
        if info.state.messages != 1:
            raise RuntimeError("pending edge packet did not survive in JetStream")
        if log.replay():
            raise RuntimeError("edge packet reached Kurrent before reconciliation")
        if consume:
            if await ingress.reconcile_one(log=log) != _edge_packet():
                raise RuntimeError("recovered edge packet differs from publication")
            if log.replay() != [_edge_packet().event]:
                raise RuntimeError("recovered edge packet was not committed exactly once")
    finally:
        event_client.close()
        await client.close()


def write_probe() -> None:
    client = KurrentDBClient(
        os.environ.get(
            "KURRENTDB_URI",
            "kurrentdb://127.0.0.1:2113?tls=false",
        )
    )
    try:
        log = KurrentExperienceLog(scope=_scope(), client=client)
        log.append(_event(), expected_revision=-1)
    finally:
        client.close()

    dsn = os.environ.get(
        "XTDB_DSN",
        "postgresql://xtdb@127.0.0.1:5432/xtdb",
    )
    with psycopg.connect(dsn, autocommit=True) as connection:
        configure_xtdb_connection(connection)
        connection.execute(
            "INSERT INTO flora_backend_restart_probe (_id, marker) "
            "VALUES (%s::text, %s::text)",
            (PROBE_ID, MARKER),
        )
    asyncio.run(_edge_probe(write=True))


def verify_probe(*, retry_seconds: int = 0,
                 consume_edge: bool = False) -> None:
    client = KurrentDBClient(
        os.environ.get(
            "KURRENTDB_URI",
            "kurrentdb://127.0.0.1:2113?tls=false",
        )
    )
    try:
        replayed = KurrentExperienceLog(
            scope=_scope(),
            client=client,
        ).replay()
        if replayed != [_event()]:
            raise RuntimeError("KurrentDB restart probe did not replay exactly")
    finally:
        client.close()

    dsn = os.environ.get(
        "XTDB_DSN",
        "postgresql://xtdb@127.0.0.1:5432/xtdb",
    )
    deadline = time.monotonic() + retry_seconds
    last_observation = "not queried"
    while True:
        try:
            with psycopg.connect(dsn, autocommit=True) as connection:
                configure_xtdb_connection(connection)
                row = connection.execute(
                    "SELECT marker FROM flora_backend_restart_probe WHERE _id = %s",
                    (PROBE_ID,),
                ).fetchone()
            if row == (MARKER,):
                print(f"XTDB probe visible: {PROBE_ID}")
                break
            last_observation = f"row={row!r}"
        except psycopg.Error as exc:
            last_observation = f"{type(exc).__name__}: {exc}"
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"XTDB restart probe unavailable after {retry_seconds}s; "
                f"last observation: {last_observation}"
            )
        time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))
    asyncio.run(_edge_probe(consume=consume_edge))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("write", "verify"))
    parser.add_argument("--retry-seconds", type=int, default=0)
    parser.add_argument("--consume-edge", action="store_true")
    args = parser.parse_args()
    if args.retry_seconds < 0:
        parser.error("--retry-seconds must be nonnegative")
    if args.mode == "write":
        if args.consume_edge:
            parser.error("--consume-edge requires verify mode")
        write_probe()
    else:
        verify_probe(retry_seconds=args.retry_seconds,
                     consume_edge=args.consume_edge)


if __name__ == "__main__":
    main()
