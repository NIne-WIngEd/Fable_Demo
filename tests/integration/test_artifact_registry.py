"""Real XTDB artifact registry/custody tests, with no learned model.

Fictional opaque checkpoint bytes are never deserialized. The independent test
key signs a fixture qualification protocol, not an MFM/EIPM capability receipt.
"""

import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import tempfile
from threading import Barrier
import unittest
import uuid

import psycopg
from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from cognitive_kernel.canonical import canonical_json_bytes
from cognitive_kernel.contracts import ProductHostScope
from flora.selected.artifact_registry import (
    ArtifactManifest, VerifiedArtifactQualification, XTDBModelArtifactRegistry,
)
from flora.selected.object_store import EncryptedObjectPlane, LocalObjectBackend


class _FictionalIndependentVerifier:
    def __init__(self, public_key):
        self.public_key = public_key

    def verify(self, *, manifest, receipt):
        record = json.loads(receipt)
        if set(record) != {"payload", "signature"}:
            raise ValueError("invalid fixture qualification wrapper")
        payload = record["payload"]
        if (set(payload) != {"schema", "qualifier_id", "qualification_id", "manifest_sha256", "runtime_allowed"}
                or payload["schema"] != "fictional-qualification-v1"
                or payload["qualifier_id"] != "fictional-independent-qualifier"):
            raise ValueError("invalid fixture qualification schema or qualifier")
        self.public_key.verify(base64.b64decode(record["signature"], validate=True),
                               canonical_json_bytes(payload))
        return VerifiedArtifactQualification(payload["qualification_id"], payload["qualifier_id"],
            payload["schema"], payload["manifest_sha256"], hashlib.sha256(receipt).hexdigest(),
            payload["runtime_allowed"])


class ArtifactRegistrySelectedBackendTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.checkpoint = self.root / "fictional-checkpoint.bin"
        self.bytes = b"opaque fictional checkpoint for registry testing: not a neural model"
        self.checkpoint.write_bytes(self.bytes)
        self.scope = ProductHostScope.create(product_id="friday", host_instance_id=f"artifact-{uuid.uuid4().hex}",
            schema_version="1.0.0", encryption_domain="fictional-artifact-integration")
        self.namespace = "fictional-artifact-registry"
        self.key = Ed25519PrivateKey.generate()
        self.verifier = _FictionalIndependentVerifier(self.key.public_key())
        self.dsn = os.environ.get("XTDB_DSN", "postgresql://xtdb@127.0.0.1:5432/xtdb")
        self.connection = psycopg.connect(self.dsn, autocommit=True)
        self.addCleanup(self.connection.close)
        self.objects = EncryptedObjectPlane(scope=self.scope, key=b"a" * 32,
            backend=LocalObjectBackend(self.root / "private-objects"))
        self.registry = self._registry(self.connection)
        self.manifest = ArtifactManifest(self.scope, "fictional-mfm-v1", "memory_formation",
            "fictional-repository", "fictional-branch", "a" * 40, hashlib.sha256(self.bytes).hexdigest(),
            len(self.bytes), "fictional-input-v1", "b" * 64, "fictional-output-v1", "c" * 64)

    def _registry(self, connection, *, namespace=None, scope=None, objects=None):
        return XTDBModelArtifactRegistry(scope=scope or self.scope,
            authority_namespace_id=namespace or self.namespace, connection=connection,
            objects=objects or self.objects)

    def _receipt(self, manifest=None, *, qualification_id="fictional-qualified-v1", key=None, **changes):
        payload = {"schema": "fictional-qualification-v1", "qualifier_id": "fictional-independent-qualifier",
            "qualification_id": qualification_id, "manifest_sha256": (manifest or self.manifest).manifest_sha256,
            "runtime_allowed": True}
        payload.update(changes)
        signature = (key or self.key).sign(canonical_json_bytes(payload))
        return canonical_json_bytes({"payload": payload, "signature": base64.b64encode(signature).decode()})

    def _admit(self, manifest=None, **changes):
        fields = dict(manifest=manifest or self.manifest, checkpoint_path=self.checkpoint,
            external_receipt=self._receipt(manifest), verifier=self.verifier)
        fields.update(changes)
        return self.registry.admit(**fields)

    def _resolve(self, *, registry=None, manifest=None, **changes):
        model = manifest or self.manifest
        fields = dict(role=model.role, checkpoint_path=self.checkpoint,
            expected_input_contract_id=model.input_contract_id,
            expected_input_contract_sha256=model.input_contract_sha256,
            expected_output_contract_id=model.output_contract_id,
            expected_output_contract_sha256=model.output_contract_sha256, verifier=self.verifier)
        fields.update(changes)
        return (registry or self.registry).resolve_current_for_runtime(**fields)

    def test_custody_and_registry_recover_without_caller_qualification_map(self):
        admitted = self._admit()
        self.assertEqual(admitted.generation, 1)
        self.assertFalse(admitted.idempotent_replay)
        self.assertTrue(self._admit().idempotent_replay)
        with psycopg.connect(self.dsn, autocommit=True) as reopened:
            plane = EncryptedObjectPlane(scope=self.scope, key=b"a" * 32,
                backend=LocalObjectBackend(self.root / "private-objects"))
            recovered = self._registry(reopened, objects=plane)
            wiring = self._resolve(registry=recovered)
            self.assertEqual(wiring.artifact_id, self.manifest.artifact_id)
            self.assertEqual(wiring.generation, 1)
            self.assertEqual(wiring.checkpoint_sha256, self.manifest.checkpoint_sha256)
            self.checkpoint.write_bytes(b"tampered checkpoint after process recreation")
            with self.assertRaisesRegex(ValueError, "bytes differ"):
                self._resolve(registry=recovered)
        self.assertNotIn(str(self.checkpoint), json.dumps(self.manifest.metadata_record()))

    def test_second_generation_stale_cas_and_old_retry_preserve_current_head(self):
        first = self._admit()
        second_model = replace(self.manifest, artifact_id="fictional-mfm-v2", source_commit="d" * 40)
        receipt = self._receipt(second_model, qualification_id="fictional-qualified-v2")
        with self.assertRaisesRegex(ValueError, "stale"):
            self._admit(second_model, external_receipt=receipt)
        second = self._admit(second_model, external_receipt=receipt,
            expected_previous_artifact_id=first.artifact_id, expected_previous_generation=1)
        self.assertEqual(second.generation, 2)
        self.assertTrue(self._admit().idempotent_replay)
        self.assertEqual(self._resolve().artifact_id, second_model.artifact_id)
        self.assertEqual(self._resolve().generation, 2)
        third_model = replace(self.manifest, artifact_id="fictional-mfm-v3")
        with self.assertRaisesRegex(ValueError, "stale"):
            self._admit(third_model,
                external_receipt=self._receipt(third_model, qualification_id="fictional-qualified-v3"),
                expected_previous_artifact_id=first.artifact_id, expected_previous_generation=1)

    def test_immutable_receipt_and_artifact_identity_cannot_be_rebound(self):
        first = self._admit()
        next_model = replace(self.manifest, artifact_id="fictional-mfm-v2")
        with self.assertRaisesRegex(ValueError, "qualification ID is immutable"):
            self._admit(next_model, expected_previous_artifact_id=first.artifact_id,
                expected_previous_generation=1)
        changed_same_id = replace(self.manifest, source_commit="d" * 40)
        with self.assertRaisesRegex(ValueError, "admission ID was reused"):
            self._admit(changed_same_id,
                external_receipt=self._receipt(changed_same_id, qualification_id="different-qualification"))

    def test_scope_namespace_and_expected_contract_fail_closed(self):
        self._admit()
        with self.assertRaisesRegex(ValueError, "no admitted"):
            self._resolve(registry=self._registry(self.connection, namespace="other-namespace"))
        other_scope = replace(self.scope, host_instance_id="other-artifact-host")
        plane = EncryptedObjectPlane(scope=other_scope, key=b"z" * 32,
            backend=LocalObjectBackend(self.root / "other-private-objects"))
        other = self._registry(self.connection, scope=other_scope, objects=plane)
        with self.assertRaisesRegex(ValueError, "no admitted"):
            self._resolve(registry=other)
        with self.assertRaisesRegex(ValueError, "crosses host scope"):
            other.admit(manifest=self.manifest, checkpoint_path=self.checkpoint,
                external_receipt=self._receipt(), verifier=self.verifier)
        with self.assertRaisesRegex(ValueError, "runtime interface"):
            self._resolve(expected_output_contract_sha256="e" * 64)
        with self.assertRaisesRegex(ValueError, "no admitted"):
            self._resolve(role="personality_judgment")

    def test_invalid_or_denied_external_receipts_never_create_current_role(self):
        for fields in ({"schema": "unknown-schema"}, {"qualifier_id": "other-qualifier"},
                       {"runtime_allowed": False}):
            with self.subTest(fields=fields):
                with self.assertRaises(ValueError):
                    self._admit(external_receipt=self._receipt(**fields))
        with self.assertRaises(InvalidSignature):
            self._admit(external_receipt=self._receipt(key=Ed25519PrivateKey.generate()))
        with self.assertRaisesRegex(ValueError, "no admitted"):
            self._resolve()

    def test_runtime_rechecks_independent_qualification_and_missing_checkpoint(self):
        self._admit()
        with self.assertRaises(InvalidSignature):
            self._resolve(verifier=_FictionalIndependentVerifier(Ed25519PrivateKey.generate().public_key()))
        self.checkpoint.unlink()
        with self.assertRaisesRegex(ValueError, "absent"):
            self._resolve()
        # Custody survives independently of the removed checkpoint, but cannot
        # make that missing artifact usable.
        with psycopg.connect(self.dsn, autocommit=True) as reopened:
            with self.assertRaisesRegex(ValueError, "absent"):
                self._resolve(registry=self._registry(reopened))

    def test_changed_encrypted_qualification_custody_prevents_runtime_binding(self):
        receipt = self._receipt()
        self._admit(external_receipt=receipt)
        raw = self.objects.put(receipt)
        path = self.objects.backend._path(self.objects.namespace, raw.object_id)
        encrypted = path.read_bytes()
        path.write_bytes(encrypted[:-1] + bytes([encrypted[-1] ^ 1]))
        with self.assertRaises(InvalidTag):
            self._resolve()

    def test_racing_writers_cannot_both_activate_the_same_predecessor(self):
        first = self._admit()
        barrier = Barrier(2)
        models = [replace(self.manifest, artifact_id=f"fictional-racing-mfm-{i}") for i in range(2)]
        outer = self

        class BarrierVerifier:
            def __init__(self):
                self.calls = 0

            def verify(self, **fields):
                result = outer.verifier.verify(**fields)
                self.calls += 1
                if self.calls == 2:
                    # Both writers have read generation 1. The selected DB's
                    # transaction assertion, rather than a Python lock, must
                    # decide which current-role write can commit.
                    barrier.wait(timeout=30)
                return result

        def race(index):
            model = models[index]
            with psycopg.connect(self.dsn, autocommit=True) as connection:
                registry = self._registry(connection)
                try:
                    return registry.admit(manifest=model, checkpoint_path=self.checkpoint,
                        external_receipt=self._receipt(model, qualification_id=f"fictional-racing-qualified-{index}"),
                        verifier=BarrierVerifier(), expected_previous_artifact_id=first.artifact_id,
                        expected_previous_generation=1)
                except psycopg.Error:
                    return None

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(race, range(2)))
        winners = [result for result in results if result is not None]
        self.assertEqual(len(winners), 1)
        self.assertEqual(self._resolve().artifact_id, winners[0].artifact_id)
        self.assertEqual(self._resolve().generation, 2)


if __name__ == "__main__":
    unittest.main()
