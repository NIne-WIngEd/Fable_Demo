"""Persistent, single-host capture runtime built on A.L.I.C.E.'s kernel stores.

This is the first demo component: local sealing -> raw buffer -> compact ledger.
It does not create claims, train models, or produce conversational responses.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import uuid

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .alice_adapter import ALICE_COMMIT

_MAGIC = b"FBD1"
_KINDS = {"statement", "correction", "decision", "outcome", "observation"}
_SUBJECTS = {"host", "assistant_self", "relationship"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _require_vault_location(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    repository = Path(__file__).resolve().parents[2]
    if resolved == repository or repository in resolved.parents:
        raise ValueError("the host vault must be outside the public Fable_Demo repository")
    return resolved


def _validate_link(observation: "Observation", parent: "Observation") -> None:
    from cognitive_kernel.canonical import normalize_timestamp

    if normalize_timestamp(observation.occurred_at, "occurred_at") < normalize_timestamp(parent.occurred_at, "parent.occurred_at"):
        raise ValueError("linked observation precedes its parent")
    if observation.kind == "outcome" and parent.kind != "decision":
        raise ValueError("outcome must refer to a decision")
    if observation.kind == "correction" and (parent.kind not in {"statement", "correction"} or parent.subject != observation.subject):
        raise ValueError("correction must refer to the same subject's statement or correction")


@dataclass(frozen=True)
class Observation:
    logical_id: str
    kind: str
    subject: str
    text: str
    occurred_at: str
    relates_to: str | None = None

    def validate(self) -> None:
        from cognitive_kernel.canonical import require_identifier, normalize_timestamp

        if require_identifier(self.logical_id, "logical_id") != self.logical_id:
            raise ValueError("logical_id must be canonical lowercase")
        if self.kind not in _KINDS or self.subject not in _SUBJECTS:
            raise ValueError("unknown observation kind or subject")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("observation text is required")
        normalize_timestamp(self.occurred_at, "occurred_at")
        if self.relates_to:
            if require_identifier(self.relates_to, "relates_to") != self.relates_to:
                raise ValueError("relates_to must be canonical lowercase")
        if self.kind in {"correction", "outcome"} and not self.relates_to:
            raise ValueError("corrections and outcomes must name a prior observation")

    def record(self) -> dict:
        self.validate()
        return {"logical_id": self.logical_id, "kind": self.kind, "subject": self.subject,
                "text": self.text, "occurred_at": self.occurred_at, "relates_to": self.relates_to}


class FableRuntime:
    """One persistent demo host. The caller must serialize writes per vault."""

    def __init__(self, vault: str | Path):
        from cognitive_kernel.contracts import ProductHostScope

        self.vault = _require_vault_location(Path(vault))
        manifest = json.loads((self.vault / "manifest.json").read_text())
        if manifest.get("version") != 1 or manifest.get("alice_commit") != ALICE_COMMIT:
            raise ValueError("unsupported host manifest or kernel version")
        self.scope = ProductHostScope.create(product_id=manifest["product_id"],
            host_instance_id=manifest["host_instance_id"], schema_version="1.0.0",
            encryption_domain=manifest["encryption_domain"])
        if self.scope.product_id != "friday":
            raise ValueError("not a Fable/Friday host scope")
        self.created_at = manifest["created_at"]
        key_path = self.vault / "demo.key"
        if os.name != "nt" and key_path.stat().st_mode & 0o077:
            raise PermissionError("demo key must not be accessible to group or others")
        self._key = key_path.read_bytes()
        if len(self._key) != 32:
            raise ValueError("invalid demo encryption key")

    @classmethod
    def initialize(cls, vault: str | Path) -> "FableRuntime":
        root = _require_vault_location(Path(vault))
        root.mkdir(parents=True, exist_ok=True)
        if any(root.iterdir()):
            raise FileExistsError("host vault must be an empty directory")
        created_at = _utc_now()
        manifest = {"version": 1, "product_id": "friday", "host_instance_id": f"host-{uuid.uuid4()}",
                    "encryption_domain": f"domain-{uuid.uuid4()}", "alice_commit": ALICE_COMMIT,
                    "created_at": created_at}
        key_path = root / "demo.key"
        descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(AESGCM.generate_key(bit_length=256))
            stream.flush()
            os.fsync(stream.fileno())
        (root / "manifest.json").write_bytes(_canonical(manifest))
        runtime = cls(root)
        with runtime._stores() as (raw, ledger):
            raw.verify_integrity()
            ledger.verify_integrity()
        return runtime

    @contextmanager
    def _stores(self):
        from cognitive_kernel.ledger_store import open_experience_ledger
        from cognitive_kernel.payload_store import open_raw_buffer_store

        with open_raw_buffer_store(self.vault / "raw", scope=self.scope, created_at=self.created_at) as raw:
            with open_experience_ledger(self.vault / "experience-ledger.sqlite3", scope=self.scope,
                                        created_at=self.created_at) as ledger:
                yield raw, ledger

    def _aad(self, logical_id: str) -> bytes:
        return f"{self.scope.storage_scope()}:{logical_id}".encode()

    def _seal(self, observation: Observation) -> bytes:
        nonce = os.urandom(12)
        return _MAGIC + nonce + AESGCM(self._key).encrypt(nonce, _canonical(observation.record()), self._aad(observation.logical_id))

    def _unseal(self, sealed: bytes, logical_id: str) -> Observation:
        if not sealed.startswith(_MAGIC) or len(sealed) < 33:
            raise ValueError("unrecognized sealed payload")
        value = json.loads(AESGCM(self._key).decrypt(sealed[4:16], sealed[16:], self._aad(logical_id)))
        observation = Observation(**value)
        observation.validate()
        if observation.logical_id != logical_id:
            raise ValueError("payload identity differs from raw reference")
        return observation

    def _append_missing(self, raw, ledger) -> dict[str, str]:
        from cognitive_kernel.contracts import ProvenanceReference
        from cognitive_kernel.experience import ExperienceEvent

        existing = {event.payload_reference: event.event_id for item in ledger.inspect()
                    for event in (ledger.load_event(item.event_id),) if event.payload_reference}
        by_logical = {raw.get_reference(ref).logical_record_id: event_id for ref, event_id in existing.items()}
        observations = {}
        for reference in raw.inspect():
            observation = self._unseal(raw.load_opaque_payload(reference.reference_id), reference.logical_record_id)
            if observation.relates_to:
                parent_observation = observations.get(observation.relates_to)
                if parent_observation is None:
                    raise ValueError(f"missing parent observation: {observation.relates_to}")
                _validate_link(observation, parent_observation)
            observations[observation.logical_id] = observation
            if reference.reference_id in existing:
                continue
            parent = by_logical.get(observation.relates_to) if observation.relates_to else None
            if observation.relates_to and parent is None:
                raise ValueError(f"missing parent observation: {observation.relates_to}")
            provenance = ProvenanceReference.create(
                provenance_type="evolved_identity" if observation.subject == "assistant_self" else "owner_attested_canonical",
                source_reference_ids=(reference.reference_id,), responsible_component="fable-demo-runtime",
                supersedes_record_ids=(parent,) if observation.kind == "correction" else (),
            )
            event = ExperienceEvent.create(event_type=f"{observation.subject}-{observation.kind}",
                scope=self.scope, occurred_at=observation.occurred_at,
                content_digest=reference.content_digest, provenance=provenance,
                retention_class=reference.retention_class, storage_tier="raw_buffer",
                parent_event_ids=(parent,) if parent else (),
                outcome_reference_ids=(parent,) if observation.kind == "outcome" else (),
                payload_reference=reference.reference_id)
            ledger.append_event(event, committed_at=observation.occurred_at)
            existing[reference.reference_id] = event.event_id
            by_logical[observation.logical_id] = event.event_id
        return by_logical

    def record(self, *, kind: str, subject: str, text: str, relates_to: str | None = None,
               logical_id: str | None = None, occurred_at: str | None = None) -> dict:
        observation = Observation(logical_id=logical_id or str(uuid.uuid4()), kind=kind, subject=subject,
                                  text=text, occurred_at=occurred_at or _utc_now(), relates_to=relates_to)
        observation.validate()
        with self._stores() as (raw, ledger):
            by_logical = self._append_missing(raw, ledger)
            if observation.logical_id in by_logical:
                raise ValueError("logical observation ID already exists")
            if relates_to and relates_to not in by_logical:
                raise ValueError("related observation does not exist")
            if relates_to:
                parent_reference = next(ref for ref in raw.inspect() if ref.logical_record_id == relates_to)
                parent_observation = self._unseal(raw.load_opaque_payload(parent_reference.reference_id), relates_to)
                _validate_link(observation, parent_observation)
            receipt = raw.capture(self._seal(observation), logical_record_id=observation.logical_id,
                media_type="application/vnd.fable.observation+json", sensitivity_class="private",
                retention_class="ordinary_experience", captured_at=observation.occurred_at)
            by_logical = self._append_missing(raw, ledger)
            return {"logical_id": observation.logical_id, "event_id": by_logical[observation.logical_id],
                    "raw_reference_id": receipt.reference.reference_id}

    def inspect(self) -> dict:
        with self._stores() as (raw, ledger):
            self._append_missing(raw, ledger)
            raw_report = raw.verify_integrity()
            ledger_report = ledger.verify_integrity()
            return {"host_instance_id": self.scope.host_instance_id,
                    "raw_references": raw_report.logical_reference_count,
                    "ledger_events": ledger_report.entry_count,
                    "ledger_head": ledger_report.head_entry_sha256}

    def history(self) -> list[Observation]:
        with self._stores() as (raw, ledger):
            self._append_missing(raw, ledger)
            return [self._unseal(raw.load_opaque_payload(reference.reference_id), reference.logical_record_id)
                    for reference in raw.inspect()]
