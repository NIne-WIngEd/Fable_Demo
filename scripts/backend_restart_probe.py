"""Write or verify a synthetic persistence probe across backend restarts."""

from __future__ import annotations

import argparse
import asyncio
import base64
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import tempfile
import time

import psycopg
import nats
from kurrentdbclient import KurrentDBClient
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.canonical import normalize_timestamp
from cognitive_kernel.experience import ExperienceEvent
from cognitive_kernel.formation_context_planner import FormationPlanningRequest
from flora.selected.claims import configure_xtdb_connection
from flora.selected.experience import KurrentExperienceLog
from flora.selected.edge_ingress import EdgePacket, JetStreamEdgeIngress
from flora.selected.formation_context import prepare_selected_formation, register_experience_source
from flora.selected.formation_registry import XTDBFormationSourceRegistry
from flora.selected.formation_policy import (
    FormationPermissionAction, XTDBFormationPermissionPolicy,
    formation_permission_payload,
)
from flora.selected.object_store import EncryptedObjectPlane, LocalObjectBackend
from flora.selected.owner_authorization import (
    Ed25519OwnerActionVerifier, OwnerActionProof, owner_action_message,
)

MARKER = "selected-backend-persistence-v1"
PROBE_ID = "flora-selected-backend-restart-probe"
EDGE_MARKER = "selected-edge-persistence-v1"
FORMATION_MARKER = b"fictional registered formation persistence probe"
FORMATION_NAMESPACE = "formation-restart-probe"


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


def _formation_scope() -> ProductHostScope:
    return ProductHostScope.create(
        product_id="friday", host_instance_id="formation-restart-probe",
        schema_version="1.0.0", encryption_domain="formation-restart-probe-key")


def _formation_probe(*, write: bool = False) -> None:
    """Reopen XTDB source/custody registration after a real backend restart.

    Fixed fictional key/material belong only to this CI probe. Production keys
    and source permissions are independently provisioned and are not supplied
    by this test. No learned formation is claimed.
    """
    scope = _formation_scope()
    objects = EncryptedObjectPlane(
        scope=scope, key=b"m" * 32,
        backend=LocalObjectBackend(Path(tempfile.gettempdir()) / "flora-formation-restart-objects"))
    raw = objects.put(FORMATION_MARKER) if write else None
    client = KurrentDBClient(os.environ.get(
        "KURRENTDB_URI", "kurrentdb://127.0.0.1:2113?tls=false"))
    try:
        log = KurrentExperienceLog(scope=scope, client=client)
        if write:
            event = ExperienceEvent.create(
                event_type="observation", scope=scope,
                occurred_at="2020-01-01T12:00:00Z", content_digest=raw.plaintext_sha256,
                provenance=ProvenanceReference.create(
                    provenance_type="generated_reconstruction",
                    source_reference_ids=("formation-restart-fixture",),
                    derivation_activity_id="formation-restart-probe",
                    responsible_component="synthetic-test"),
                retention_class="ordinary_experience", storage_tier="raw_buffer",
                payload_reference=raw.object_id)
            log.append(event, expected_revision=-1)
        committed = log.replay_committed()
        if len(committed) != (1 if write else 2) or committed[0].recorded_at is None:
            raise RuntimeError("registered formation probe lacks exact physical replay")
        entry = committed[0]
        with psycopg.connect(os.environ.get(
                "XTDB_DSN", "postgresql://xtdb@127.0.0.1:5432/xtdb"), autocommit=True) as connection:
            registry = XTDBFormationSourceRegistry(
                scope=scope, authority_namespace_id=FORMATION_NAMESPACE, connection=connection)
            if write:
                register_experience_source(
                    event_id=entry.event.event_id, raw=raw, registry=registry,
                    log=log, objects=objects, role="generated_reconstruction", modality="text",
                    source_item_ref="formation-restart-fixture")
            source = registry.lookup(entry.event.event_id)
            if source is None or source.evidence.recorded_at != normalize_timestamp(
                    entry.recorded_at.isoformat(), "recorded_at"):
                raise RuntimeError("registered source/availability metadata did not recover")
            policy = XTDBFormationPermissionPolicy(
                scope=scope, authority_namespace_id=FORMATION_NAMESPACE,
                connection=connection, registry=registry)
            if write:
                action = FormationPermissionAction.create(
                    scope=scope, authority_namespace_id=FORMATION_NAMESPACE,
                    action_id="formation-restart-grant", source_ref_id=entry.event.event_id,
                    source_registration_sha256=source.registration_sha256,
                    purpose="memory_formation", decision="allow", generation=1,
                    previous_action_sha256=None, authorization_ref="fictional-restart-owner-proof",
                    authorized_at=datetime.now(timezone.utc).isoformat())
                request_raw = objects.put(formation_permission_payload(action))
                request = ExperienceEvent.create(
                    event_type="formation_permission_action", scope=scope,
                    occurred_at=action.authorized_at,
                    content_digest=request_raw.plaintext_sha256,
                    provenance=ProvenanceReference.create(
                        provenance_type="derived_inference",
                        source_reference_ids=(entry.event.event_id,),
                        derivation_activity_id=action.action_id,
                        responsible_component="synthetic-test"),
                    retention_class="ordinary_experience", storage_tier="raw_buffer",
                    parent_event_ids=(entry.event.event_id,), payload_reference=request_raw.object_id)
                log.append(request, expected_revision=0)
                register_experience_source(
                    event_id=request.event_id, raw=request_raw, registry=registry,
                    log=log, objects=objects, role="derived_inference", modality="structured")
                private_key = Ed25519PrivateKey.generate()
                proof = OwnerActionProof(
                    "formation_permission", request.event_id, request.event_sha256,
                    base64.b64encode(private_key.sign(
                        owner_action_message(request, "formation_permission"))).decode("ascii"))
                verifier = Ed25519OwnerActionVerifier(
                    scope=scope, owner_public_key=private_key.public_key().public_bytes(
                        Encoding.Raw, PublicFormat.Raw), proofs={request.event_id: proof})
                policy.apply(action, request_event_id=request.event_id,
                             log=log, objects=objects, references=registry, verifier=verifier)
            prepared = prepare_selected_formation(
                request=FormationPlanningRequest(scope, FORMATION_NAMESPACE,
                                                 (entry.event.event_id,)),
                registry=registry, objects=objects,
                permits=policy.permits)
            if prepared.assembled.opened_content != ((entry.event.event_id, FORMATION_MARKER),):
                raise RuntimeError("registered encrypted formation custody did not recover")
            print("Registered formation source, physical time, signed permission and encrypted custody recovered")
    finally:
        client.close()


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
    _formation_probe(write=True)


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
    _formation_probe()


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
