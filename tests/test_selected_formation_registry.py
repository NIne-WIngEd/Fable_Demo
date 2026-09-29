"""Deterministic registration/custody checks; real XTDB qualification is separate.

The injected SQL call recorder checks the boundary and immutable-write shape.
It is not an alternative database implementation or backend result.
"""

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest

from cognitive_kernel.canonical import CognitiveKernelContractError, normalize_timestamp
from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from cognitive_kernel.formation_contracts import FormationEvidenceRef
from cognitive_kernel.formation_sources import RegisteredFormationStore
from flora.selected.experience import CommittedExperience
from flora.selected.formation_registry import (
    RegisteredEncryptedFormationCustody, XTDBFormationSourceRegistry,
)
from flora.selected.object_store import EncryptedObjectPlane, LocalObjectBackend


class _Cursor:
    def __init__(self, rows):
        names = tuple(rows[0]) if rows else ()
        self.description = [SimpleNamespace(name=name) for name in names]
        self.rows = [tuple(row[name] for name in names) for row in rows]

    def fetchall(self):
        return self.rows


class _SQLCalls:
    def __init__(self):
        self.rows = {}
        self.calls = []
        self.adapters = SimpleNamespace(
            types={"text": SimpleNamespace(oid=25)},
            register_dumper=lambda *_: None)

    @contextmanager
    def transaction(self):
        yield

    def execute(self, statement, parameters):
        self.calls.append((statement, parameters))
        table = re.search(r"(?:FROM|INTO) (\w+)", statement).group(1)
        if statement.startswith("INSERT"):
            names = re.search(r"\(([^)]+)\) VALUES", statement).group(1).split(", ")
            row = dict(zip(names, parameters))
            self.rows[(table, row["_id"])] = row
            return _Cursor([])
        row = self.rows.get((table, parameters[0]))
        if statement.startswith("ASSERT NOT"):
            if row is not None:
                raise ValueError("synthetic assertion rejected immutable replacement")
            return _Cursor([])
        if statement.startswith("ASSERT EXISTS"):
            if row is None or row["record_sha256"] != parameters[1]:
                raise ValueError("synthetic assertion rejected changed raw reference")
            return _Cursor([])
        return _Cursor([row] if row is not None else [])


class _CommittedLog:
    def __init__(self, scope, entries):
        self.scope = scope
        self.entries = tuple(entries)

    def replay_committed(self):
        return self.entries


class _SyntheticOwnerVerifier:
    def __init__(self, allowed):
        self.allowed = allowed

    def authenticated_owner_source(self, event, evidence):
        return self.allowed


class FormationRegistryContractTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.scope = ProductHostScope.create(
            product_id="friday", host_instance_id="fictional-registry-host",
            schema_version="1.0.0", encryption_domain="fictional-registry-key")
        self.backend = LocalObjectBackend(Path(self.directory.name) / "objects")
        self.objects = EncryptedObjectPlane(scope=self.scope, key=b"r" * 32,
                                            backend=self.backend)
        self.connection = _SQLCalls()
        self.registry = self._registry()
        self.raw = self.objects.put(b"fictional raw source; not a real host's history")
        self.event = self._event()
        self.recorded_at = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
        self.log = _CommittedLog(self.scope, [CommittedExperience(
            event=self.event, stream_position=0, recorded_at=self.recorded_at)])
        self.evidence = self._evidence()

    def _registry(self, *, scope=None, namespace="registered-test-sources"):
        return XTDBFormationSourceRegistry(
            scope=scope or self.scope, authority_namespace_id=namespace,
            connection=self.connection)

    def _event(self, *, provenance="generated_reconstruction", parents=()):
        return ExperienceEvent.create(
            event_type="observation", scope=self.scope,
            occurred_at="2026-09-01T10:00:00Z",
            content_digest=self.raw.plaintext_sha256,
            provenance=ProvenanceReference.create(
                provenance_type=provenance,
                source_reference_ids=("original-fixture-source",),
                derivation_activity_id="fictional-source-registration",
                responsible_component="synthetic-test"),
            retention_class="ordinary_experience", storage_tier="raw_buffer",
            parent_event_ids=parents, payload_reference=self.raw.object_id)

    def _evidence(self, *, event=None, role="generated_reconstruction", **overrides):
        event = event or self.event
        fields = dict(
            ref_id=event.event_id, scope=self.scope,
            authority_namespace_id="registered-test-sources",
            content_digest=self.raw.plaintext_sha256, role=role, modality="text",
            subject_ref="fictional-source-person", speaker_ref="fictional-speaker",
            source_item_ref="original-fixture-source",
            observed_at=event.occurred_at,
            recorded_at=normalize_timestamp(self.recorded_at.isoformat(), "recorded_at"),
            duplicate_group_ref="fictional-duplicate-group", parent_refs=event.parent_event_ids)
        fields.update(overrides)
        return FormationEvidenceRef(**fields)

    def _register(self, evidence=None, **overrides):
        fields = dict(evidence=evidence or self.evidence, raw=self.raw,
                      log=self.log, objects=self.objects)
        fields.update(overrides)
        return self.registry.register(**fields)

    def test_restart_recovers_source_and_cipher_bound_raw_without_reference_map(self):
        source = self._register()
        restarted = self._registry()
        plane = EncryptedObjectPlane(scope=self.scope, key=b"r" * 32,
                                     backend=LocalObjectBackend(self.backend.root))
        custody = RegisteredEncryptedFormationCustody(registry=restarted, objects=plane)
        store = RegisteredFormationStore(
            scope=self.scope, authority_namespace_id="registered-test-sources",
            registry=restarted, custody=custody, permits=lambda *_: True)
        self.assertEqual(store.resolve(self.event.event_id), self.evidence)
        self.assertEqual(restarted.lookup(self.event.event_id), source)
        self.assertEqual(restarted.raw_reference(self.raw.object_id), self.raw)
        self.assertEqual(store.read(self.evidence), self.objects.get(self.raw))
        self.assertIsNone(store.resolve("unknown-source"))
        with self.assertRaisesRegex(ValueError, "no registered raw"):
            custody.read(self.scope, "a" * 64)
        self.assertNotIn("fictional raw source", json.dumps(list(self.connection.rows.values())))

    def test_idempotency_and_namespace_isolation(self):
        first = self._register()
        self.assertEqual(self._register(), first)
        self.assertEqual(sum(sql.startswith("INSERT") for sql, _ in self.connection.calls), 2)
        with self.assertRaisesRegex(ValueError, "immutable"):
            self._register(replace(self.evidence, duplicate_group_ref="another-group"))
        self.assertIsNone(self._registry(namespace="other-authority").lookup(self.event.event_id))
        other = ProductHostScope.create(
            product_id="friday", host_instance_id="other-host", schema_version="1.0.0",
            encryption_domain="other-key")
        self.assertIsNone(self._registry(scope=other).lookup(self.event.event_id))
        with self.assertRaisesRegex(ValueError, "crosses scope"):
            self._register(replace(self.evidence, scope=other))

    def test_duplicate_identity_and_committed_parent_metadata_survive_reconstruction(self):
        self._register()
        child = self._event(parents=(self.event.event_id,))
        log = _CommittedLog(self.scope, [
            CommittedExperience(event=self.event, stream_position=0,
                                recorded_at=self.recorded_at),
            CommittedExperience(event=child, stream_position=1,
                                recorded_at=self.recorded_at)])
        evidence = self._evidence(event=child)
        self._register(evidence, log=log)
        recovered = self._registry().lookup(child.event_id).evidence
        self.assertEqual(recovered, evidence)
        self.assertEqual(recovered.parent_refs, (self.event.event_id,))
        self.assertEqual(recovered.duplicate_group_ref, self.evidence.duplicate_group_ref)
        self.assertEqual(sum(table == "flora_formation_raw_references"
                             for table, _ in self.connection.rows), 1)
        missing_parent_log = _CommittedLog(self.scope, [CommittedExperience(
            event=child, stream_position=1, recorded_at=self.recorded_at)])
        with self.assertRaisesRegex(ValueError, "absent or later causal parents"):
            self._register(evidence, log=missing_parent_log)

    def test_generated_origin_cannot_become_owner_even_with_synthetic_verifier(self):
        with self.assertRaisesRegex(ValueError, "source provenance"):
            self._register(self._evidence(
                role="authenticated_owner_statement", speaker_ref=self.scope.host_instance_id),
                owner_verifier=_SyntheticOwnerVerifier(True))
        owner_event = self._event(provenance="owner_attested_canonical")
        log = _CommittedLog(self.scope, [CommittedExperience(
            event=owner_event, stream_position=0, recorded_at=self.recorded_at)])
        owner = self._evidence(event=owner_event, role="authenticated_owner_statement",
                               speaker_ref=self.scope.host_instance_id)
        for verifier in (None, _SyntheticOwnerVerifier(False)):
            with self.assertRaisesRegex(ValueError, "independently authenticated"):
                self._register(owner, log=log, owner_verifier=verifier)
        with self.assertRaisesRegex(ValueError, "different speaker"):
            self._register(replace(owner, speaker_ref="someone-else"), log=log,
                           owner_verifier=_SyntheticOwnerVerifier(True))
        self.assertEqual(self._register(owner, log=log,
                                       owner_verifier=_SyntheticOwnerVerifier(True)).evidence, owner)

    def test_committed_time_parent_and_original_item_are_not_model_declarations(self):
        for evidence in (
            replace(self.evidence, recorded_at=self.evidence.observed_at),
            replace(self.evidence, observed_at=self.evidence.recorded_at),
            replace(self.evidence, parent_refs=("invented-parent",)),
            replace(self.evidence, source_item_ref="invented-native-item"),
            replace(self.evidence, ref_id="invented-source"),
        ):
            with self.subTest(evidence=evidence):
                with self.assertRaises(ValueError):
                    self._register(evidence)
        for recorded_at in (None, self.recorded_at.replace(tzinfo=None)):
            with self.assertRaisesRegex(ValueError, "aware Kurrent"):
                self._register(log=_CommittedLog(self.scope, [CommittedExperience(
                    event=self.event, stream_position=0, recorded_at=recorded_at)]))
        changed_raw = self.objects.put(b"different fictional source")
        with self.assertRaisesRegex(ValueError, "committed source metadata"):
            self._register(raw=changed_raw)

    def test_metadata_tamper_and_ciphertext_tamper_fail_closed(self):
        self._register()
        row = self.connection.rows[("flora_registered_formation_sources",
                                    self.registry._key("source", self.event.event_id))]
        original = row["record_json"]
        record = json.loads(original)
        record["evidence"]["speaker_ref"] = "changed-speaker"
        row["record_json"] = json.dumps(record)
        with self.assertRaisesRegex(ValueError, "metadata changed"):
            self.registry.lookup(self.event.event_id)
        row["record_json"] = original
        raw_row = self.connection.rows[("flora_formation_raw_references",
                                        self.registry._key("raw", self.raw.object_id))]
        raw_original = raw_row["record_json"]
        record = json.loads(raw_original)
        record["size"] += 1
        raw_row["record_json"] = json.dumps(record)
        with self.assertRaisesRegex(ValueError, "metadata changed"):
            self.registry.raw_reference(self.raw.object_id)
        raw_row["record_json"] = raw_original
        path = self.backend._path(self.objects.namespace, self.raw.object_id)
        sealed = bytearray(path.read_bytes())
        sealed[-1] ^= 1
        path.write_bytes(sealed)
        with self.assertRaisesRegex(ValueError, "ciphertext differs"):
            RegisteredEncryptedFormationCustody(
                registry=self.registry, objects=self.objects).read(self.scope, self.raw.object_id)

    def test_current_permission_revocation_before_and_during_read(self):
        self._register()
        permitted = [True]
        custody = RegisteredEncryptedFormationCustody(registry=self.registry, objects=self.objects)
        store = RegisteredFormationStore(
            scope=self.scope, authority_namespace_id="registered-test-sources",
            registry=self.registry, custody=custody, permits=lambda *_: permitted[0])
        permitted[0] = False
        self.assertFalse(store.permits_formation(self.evidence))
        with self.assertRaisesRegex(CognitiveKernelContractError, "permission revoked"):
            store.read(self.evidence)
        permitted[0] = True

        class RevokingCustody:
            def read(inner, scope, object_ref):
                content = custody.read(scope, object_ref)
                permitted[0] = False
                return content

        store.custody = RevokingCustody()
        with self.assertRaisesRegex(CognitiveKernelContractError, "revoked"):
            store.read(self.evidence)


if __name__ == "__main__":
    unittest.main()
