"""NATS JetStream edge intake before canonical KurrentDB Experience commit.

JetStream buffers metadata-only device events. It is not a second Experience
authority. A message is acknowledged only after exact canonical replay or
an expected-revision append has succeeded.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from cognitive_kernel.canonical import require_identifier
from cognitive_kernel.contracts import ProductHostScope
from cognitive_kernel.experience import ExperienceEvent

from .experience import KurrentExperienceLog


def _scope_key(scope: ProductHostScope) -> str:
    scope.validate()
    return hashlib.sha256(scope.storage_scope().encode()).hexdigest()


@dataclass(frozen=True)
class EdgePacket:
    device_id: str
    device_clock: int
    event: ExperienceEvent

    def encode(self) -> bytes:
        require_identifier(self.device_id, "device_id")
        if isinstance(self.device_clock, bool) or not isinstance(self.device_clock, int) or self.device_clock < 0:
            raise ValueError("device_clock must be nonnegative")
        self.event.validate()
        return json.dumps({
            "schema": "flora-edge-v1",
            "device_id": self.device_id,
            "device_clock": self.device_clock,
            "event": self.event.metadata_record(),
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False).encode("utf-8")

    @classmethod
    def decode(cls, data: bytes) -> "EdgePacket":
        record = json.loads(data)
        if record["schema"] != "flora-edge-v1":
            raise ValueError("unknown edge packet schema")
        packet = cls(record["device_id"], record["device_clock"],
                     ExperienceEvent.from_metadata_record(record["event"]))
        if packet.encode() != data:
            raise ValueError("edge packet is not canonically encoded")
        return packet


class JetStreamEdgeIngress:
    """One private host stream with device-scoped subjects and durable intake."""

    def __init__(self, *, scope: ProductHostScope, jetstream: Any):
        self.scope = scope
        self.js = jetstream
        digest = _scope_key(scope)
        self.stream = "FLOEDGE" + digest[:24].upper()
        self.subject_prefix = f"flora.edge.{digest}"
        self.durable = "canonical-reconciler"
        self._subscription: Any | None = None

    async def create_stream(self) -> None:
        # Provisioning is explicit. Existing streams must be checked by the
        # deployment plane for compatible subjects and retention settings.
        await self.js.add_stream(name=self.stream,
                                 subjects=[self.subject_prefix + ".*"])

    def subject(self, device_id: str) -> str:
        require_identifier(device_id, "device_id")
        token = hashlib.sha256(device_id.encode()).hexdigest()[:24]
        return f"{self.subject_prefix}.{token}"

    async def publish(self, packet: EdgePacket) -> None:
        if packet.event.scope != self.scope:
            raise ValueError("edge packet crosses its host scope")
        data = packet.encode()
        ack = await self.js.publish(
            self.subject(packet.device_id), data,
            headers={"Nats-Msg-Id": hashlib.sha256(data).hexdigest()})
        if ack.stream != self.stream:
            raise ValueError("edge publish was not stored in the host stream")

    async def reconcile_one(self, *, log: KurrentExperienceLog,
                            timeout: float = 3.0) -> EdgePacket:
        if log.scope != self.scope:
            raise ValueError("canonical log crosses host scope")
        if self._subscription is None:
            self._subscription = await self.js.pull_subscribe(
                self.subject_prefix + ".*", durable=self.durable,
                stream=self.stream)
        messages = await self._subscription.fetch(1, timeout=timeout)
        message = messages[0]
        packet = EdgePacket.decode(message.data)
        if (packet.event.scope != self.scope
                or message.subject != self.subject(packet.device_id)):
            raise ValueError("edge message subject or scope differs from its event")
        replayed = log.replay()
        existing = next((item for item in replayed
                         if item.event_id == packet.event.event_id), None)
        if existing is not None:
            if existing != packet.event:
                raise ValueError("reused Experience event ID differs from canonical record")
        else:
            log.append(packet.event, expected_revision=len(replayed) - 1)
        await message.ack()
        return packet
