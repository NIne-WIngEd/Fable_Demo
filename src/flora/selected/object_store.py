"""Host-local placement of the encrypted, content-addressed raw-object plane.

The backend handles opaque objects only. A later S3-compatible backend can
implement the same operations without changing host keys, object identity, or
event references. Key generation and custody belong to the local trust root.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path
import re
import uuid
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cognitive_kernel.contracts import ProductHostScope

_OBJECT_ID = re.compile(r"^[0-9a-f]{64}$")
_MAGIC = b"FBO1"


class OpaqueObjectBackend(Protocol):
    def put_if_absent(self, namespace: str, object_id: str, payload: bytes) -> None: ...
    def get_object(self, namespace: str, object_id: str) -> bytes: ...


class LocalObjectBackend:
    """Atomic immutable object placement beneath a private local directory."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        repository = Path(__file__).resolve().parents[3]
        if self.root == repository or repository in self.root.parents:
            raise ValueError("private object storage must be outside the public repository")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != "nt" and self.root.stat().st_mode & 0o077:
            raise PermissionError("object root must be private to this OS user")

    def _path(self, namespace: str, object_id: str) -> Path:
        if not re.fullmatch(r"[a-z0-9-]+", namespace) or not _OBJECT_ID.fullmatch(object_id):
            raise ValueError("invalid object namespace or identifier")
        return self.root / namespace / object_id[:2] / object_id

    def put_if_absent(self, namespace: str, object_id: str, payload: bytes) -> None:
        path = self._path(namespace, object_id)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = path.parent / f".{uuid.uuid4().hex}.tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                pass  # The caller verifies the already stored object's content.
            if os.name != "nt":
                directory = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)

    def get_object(self, namespace: str, object_id: str) -> bytes:
        return self._path(namespace, object_id).read_bytes()


@dataclass(frozen=True)
class RawObjectReference:
    scope: ProductHostScope
    object_id: str
    plaintext_sha256: str
    size: int


class EncryptedObjectPlane:
    """Keyed deduplication is confined to one product/host/encryption domain."""

    def __init__(self, *, scope: ProductHostScope, key: bytes, backend: OpaqueObjectBackend):
        scope.validate()
        if not isinstance(key, bytes) or len(key) != 32:
            raise ValueError("a 256-bit host-held key is required")
        self.scope = scope
        self._key = key
        self.backend = backend
        self.namespace = hashlib.sha256(scope.storage_scope().encode()).hexdigest()[:40]

    def _identity(self, content: bytes) -> str:
        return hmac.new(self._key, content, hashlib.sha256).hexdigest()

    def put(self, content: bytes) -> RawObjectReference:
        if not isinstance(content, bytes):
            raise TypeError("raw object content must be bytes")
        object_id = self._identity(content)
        nonce = os.urandom(12)
        aad = f"{self.scope.storage_scope()}:{object_id}".encode()
        sealed = _MAGIC + nonce + AESGCM(self._key).encrypt(nonce, content, aad)
        self.backend.put_if_absent(self.namespace, object_id, sealed)
        reference = RawObjectReference(self.scope, object_id, hashlib.sha256(content).hexdigest(), len(content))
        if self.get(reference) != content:
            raise ValueError("existing object content differs from the submitted bytes")
        return reference

    def get(self, reference: RawObjectReference) -> bytes:
        if reference.scope != self.scope or not _OBJECT_ID.fullmatch(reference.object_id):
            raise ValueError("object reference belongs to a different host or is malformed")
        sealed = self.backend.get_object(self.namespace, reference.object_id)
        if not sealed.startswith(_MAGIC) or len(sealed) < 32:
            raise ValueError("invalid encrypted object envelope")
        aad = f"{self.scope.storage_scope()}:{reference.object_id}".encode()
        content = AESGCM(self._key).decrypt(sealed[4:16], sealed[16:], aad)
        if (self._identity(content) != reference.object_id
                or hashlib.sha256(content).hexdigest() != reference.plaintext_sha256
                or len(content) != reference.size):
            raise ValueError("object identity or content digest mismatch")
        return content
