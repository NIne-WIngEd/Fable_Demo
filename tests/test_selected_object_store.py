from pathlib import Path
import tempfile
import unittest

from cognitive_kernel.contracts import ProductHostScope
from flora.selected.object_store import EncryptedObjectPlane, LocalObjectBackend


def _scope(host: str) -> ProductHostScope:
    return ProductHostScope.create(product_id="friday", host_instance_id=host,
        schema_version="1.0.0", encryption_domain=f"key-{host}")


class SelectedObjectPlaneTest(unittest.TestCase):
    def test_restart_isolation_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "objects"
            scope = _scope("host-one")
            key = b"a" * 32
            plane = EncryptedObjectPlane(scope=scope, key=key, backend=LocalObjectBackend(root))
            payload = b"fictional host-private observation"
            reference = plane.put(payload)
            self.assertEqual(plane.put(payload), reference)
            self.assertEqual(EncryptedObjectPlane(scope=scope, key=key,
                backend=LocalObjectBackend(root)).get(reference), payload)
            other = EncryptedObjectPlane(scope=_scope("host-two"), key=b"b" * 32,
                backend=LocalObjectBackend(root))
            self.assertNotEqual(other.put(payload).object_id, reference.object_id)
            with self.assertRaisesRegex(ValueError, "different host"):
                other.get(reference)
            path = plane.backend._path(plane.namespace, reference.object_id)
            self.assertNotIn(payload, path.read_bytes())
            sealed = bytearray(path.read_bytes())
            sealed[-1] ^= 1
            path.write_bytes(sealed)
            with self.assertRaises(Exception):
                plane.get(reference)


if __name__ == "__main__":
    unittest.main()
