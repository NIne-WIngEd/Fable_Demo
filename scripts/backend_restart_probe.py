"""Write or verify a synthetic persistence probe across backend restarts."""

from __future__ import annotations

import argparse
import hashlib
import os
import time

import psycopg
from kurrentdbclient import KurrentDBClient

from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from flora.selected.claims import configure_xtdb_connection
from flora.selected.experience import KurrentExperienceLog

MARKER = "selected-backend-persistence-v1"
PROBE_ID = "flora-selected-backend-restart-probe"


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


def verify_probe(*, retry_seconds: int = 0) -> None:
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
                return
            last_observation = f"row={row!r}"
        except psycopg.Error as exc:
            last_observation = f"{type(exc).__name__}: {exc}"
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"XTDB restart probe unavailable after {retry_seconds}s; "
                f"last observation: {last_observation}"
            )
        time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("write", "verify"))
    parser.add_argument("--retry-seconds", type=int, default=0)
    args = parser.parse_args()
    if args.retry_seconds < 0:
        parser.error("--retry-seconds must be nonnegative")
    if args.mode == "write":
        write_probe()
    else:
        verify_probe(retry_seconds=args.retry_seconds)


if __name__ == "__main__":
    main()
