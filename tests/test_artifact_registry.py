"""Artifact byte/qualification boundary tests, without model inference.

The signed receipts and checkpoint bytes are fictional test fixtures. Passing
these tests qualifies neither MFM nor EIPM. Durable XTDB checks are separate.
"""

import base64
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from cognitive_kernel.canonical import canonical_json_bytes
from cognitive_kernel.contracts import ProductHostScope
from flora.selected.artifact_registry import (
    ArtifactManifest, VerifiedArtifactQualification, verify_local_artifact,
)


class _FictionalSignedVerifier:
    """Independent key and receipt schema for registry mechanics only."""

    def __init__(self, public_key):
        self.public_key = public_key

    def verify(self, *, manifest, receipt):
        wrapper = json.loads(receipt)
        if set(wrapper) != {"payload", "signature"}:
            raise ValueError("invalid fictional qualification wrapper")
        payload = wrapper["payload"]
        if (set(payload) != {"schema", "qualifier_id", "qualification_id", "manifest_sha256", "runtime_allowed"}
                or payload["schema"] != "fictional-qualification-v1"
                or payload["qualifier_id"] != "fictional-independent-qualifier"):
            raise ValueError("invalid fictional qualification schema or qualifier")
        self.public_key.verify(base64.b64decode(wrapper["signature"], validate=True),
                               canonical_json_bytes(payload))
        return VerifiedArtifactQualification(
            payload["qualification_id"], payload["qualifier_id"], payload["schema"],
            payload["manifest_sha256"], hashlib.sha256(receipt).hexdigest(),
            payload["runtime_allowed"])


class ArtifactQualificationBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "fictional-checkpoint.bin"
        self.payload = b"fictional opaque checkpoint bytes: NEVER deserialize or infer"
        self.path.write_bytes(self.payload)
        self.scope = ProductHostScope.create(product_id="friday", host_instance_id="fictional-artifact-host",
            schema_version="1.0.0", encryption_domain="fictional-artifact-domain")
        self.manifest = ArtifactManifest(self.scope, "fictional-mfm-v1", "memory_formation",
            "fictional-source-repository", "fictional-source-branch", "a" * 40,
            hashlib.sha256(self.payload).hexdigest(), len(self.payload),
            "fictional-input-v1", "b" * 64, "fictional-output-v1", "c" * 64)
        self.key = Ed25519PrivateKey.generate()
        self.verifier = _FictionalSignedVerifier(self.key.public_key())

    def _receipt(self, manifest=None, *, key=None, **changes):
        payload = {"schema": "fictional-qualification-v1", "qualifier_id": "fictional-independent-qualifier",
            "qualification_id": "fictional-qualified-v1",
            "manifest_sha256": (manifest or self.manifest).manifest_sha256, "runtime_allowed": True}
        payload.update(changes)
        signature = (key or self.key).sign(canonical_json_bytes(payload))
        return canonical_json_bytes({"payload": payload, "signature": base64.b64encode(signature).decode()})

    def _verify(self, *, manifest=None, receipt=None, verifier=None):
        return verify_local_artifact(manifest=manifest or self.manifest, checkpoint_path=self.path,
            receipt=receipt or self._receipt(), verifier=verifier or self.verifier)

    def test_opaque_bytes_and_signed_exact_manifest_are_required(self):
        qualification = self._verify()
        self.assertEqual(qualification.manifest_sha256, self.manifest.manifest_sha256)
        self.assertEqual(qualification.qualifier_id, "fictional-independent-qualifier")
        self.assertEqual(ArtifactManifest.from_record(self.manifest.metadata_record()), self.manifest)
        self.assertNotIn(str(self.path), json.dumps(self.manifest.metadata_record()))

    def test_missing_replaced_and_wrong_size_checkpoint_fail(self):
        self.path.unlink()
        with self.assertRaisesRegex(ValueError, "absent"):
            self._verify()
        self.path.write_bytes(self.payload + b"modified")
        with self.assertRaisesRegex(ValueError, "bytes differ"):
            self._verify()
        self.path.write_bytes(self.payload)
        with self.assertRaisesRegex(ValueError, "bytes differ"):
            self._verify(manifest=replace(self.manifest, checkpoint_size=len(self.payload) + 1))

    def test_checkpoint_mutation_during_external_verification_fails(self):
        outer = self

        class MutatingVerifier:
            def verify(self, **fields):
                qualification = outer.verifier.verify(**fields)
                outer.path.write_bytes(b"changed by external verifier I/O")
                return qualification

        with self.assertRaisesRegex(ValueError, "bytes differ"):
            self._verify(verifier=MutatingVerifier())

    def test_untrusted_key_unsigned_digest_or_changed_signed_payload_fail(self):
        with self.assertRaises(InvalidSignature):
            self._verify(receipt=self._receipt(key=Ed25519PrivateKey.generate()))
        with self.assertRaises(ValueError):
            self._verify(receipt=canonical_json_bytes({"manifest_sha256": self.manifest.manifest_sha256}))
        changed = json.loads(self._receipt())
        changed["payload"]["runtime_allowed"] = False
        with self.assertRaises(InvalidSignature):
            self._verify(receipt=canonical_json_bytes(changed))

    def test_signed_denial_and_unknown_receipt_schema_or_qualifier_fail(self):
        with self.assertRaisesRegex(ValueError, "does not authorize"):
            self._verify(receipt=self._receipt(runtime_allowed=False))
        for fields in ({"schema": "unknown-schema"}, {"qualifier_id": "different-qualifier"}):
            with self.assertRaisesRegex(ValueError, "schema or qualifier"):
                self._verify(receipt=self._receipt(**fields))

    def test_receipt_cannot_move_to_another_host_role_source_or_interface(self):
        other_scope = replace(self.scope, host_instance_id="other-fictional-host")
        for fields in ({"scope": other_scope}, {"role": "personality_judgment"},
                {"source_commit": "d" * 40}, {"output_contract_sha256": "d" * 64}):
            with self.subTest(fields=fields):
                with self.assertRaisesRegex(ValueError, "exact scoped manifest"):
                    self._verify(manifest=replace(self.manifest, **fields))

    def test_noncanonical_fields_and_manifest_extensions_fail(self):
        for fields in ({"artifact_id": " Mixed-Case "}, {"source_commit": "A" * 40},
                {"input_contract_sha256": "B" * 64}, {"checkpoint_size": True},
                {"role": "conversation"}, {"source_branch": " padded-branch "}):
            with self.subTest(fields=fields):
                with self.assertRaises(ValueError):
                    replace(self.manifest, **fields).validate()
        with self.assertRaisesRegex(ValueError, "schema or fields"):
            ArtifactManifest.from_record({**self.manifest.metadata_record(), "checkpoint_path": str(self.path)})

    def test_nonqualification_adapter_return_and_changed_receipt_binding_fail(self):
        class HashOnlyVerifier:
            def verify(self, **_):
                return {"checkpoint_sha256": "a" * 64, "qualified": True}

        with self.assertRaisesRegex(TypeError, "independently bound"):
            self._verify(verifier=HashOnlyVerifier())
        qualification = self._verify()
        with self.assertRaisesRegex(ValueError, "exact scoped manifest"):
            replace(qualification, receipt_sha256="e" * 64).validate_binding(self.manifest, self._receipt())


if __name__ == "__main__":
    unittest.main()
