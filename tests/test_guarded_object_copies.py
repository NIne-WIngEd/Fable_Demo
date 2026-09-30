"""Selected authority around copied comparator/provider ciphertext facades.

Actual typed source policy and enrolled-owner actions use controlled row
transports. These tests do not qualify physical engine latency or models.
"""
from copy import copy
import unittest
from unittest.mock import patch

from flora.selected.experiment_manifests import _GuardedObjects
from flora.selected.object_store import AESGCM
from flora.selected.provider_attempt_custody import _CheckedObjects
import test_phase_source_fence as fixtures


class GuardedObjectCopiesTest(unittest.TestCase):
    def setUp(self):
        self.h = fixtures.PhaseSourceFenceTest()
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.f = self.h.f
        self.event_id = self.h.h.before.event_ids[0]
        self.material = self.h.h.before.sources[0]
        self.reference = self.f.references[self.material.event.payload_reference]
        self.checks = 0

    def check(self):
        self.checks += 1
        self.h.verify()

    def test_copies_keep_constant_live_checks_and_queries(self):
        for kind, expected in ((_GuardedObjects, 4), (_CheckedObjects, 6)):
            with self.subTest(kind=kind.__name__):
                reader = kind(self.f.objects, self.check)
                for _ in range(5):
                    old_checks, old_queries = self.checks, len(self.f.connection.calls)
                    self.assertEqual(reader.get(self.reference), self.material.plaintext)
                    self.assertEqual(self.checks - old_checks, expected)
                    self.assertEqual(len(self.f.connection.calls) - old_queries, expected * 3)
                    reader = copy(reader)
                self.h.grant(self.event_id, "revoke")
                with self.assertRaises(PermissionError):
                    reader.get(self.reference)
                self.h.grant(self.event_id)

    def test_copies_isolate_planes_and_preserve_distinct_installed_guards(self):
        for kind in (_GuardedObjects, _CheckedObjects):
            with self.subTest(kind=kind.__name__):
                distinct = []
                inner = _GuardedObjects(self.f.objects, lambda: distinct.append("inner"))
                original = kind(inner, self.check)
                copied = copy(original)
                self.assertIsNot(copied, original)
                self.assertIsNot(copied.objects, original.objects)
                self.assertIsNot(copied.backend, original.backend)
                old_checks = self.checks
                self.assertEqual(copied.get(self.reference), self.material.plaintext)
                self.assertEqual(self.checks - old_checks, 4 if kind is _GuardedObjects else 6)
                # The independently installed inner ciphertext guard survives.
                self.assertEqual(distinct, ["inner"] * 2)
                original_backend = original.backend
                copied.backend = copy(copied.backend)
                self.assertIs(original.backend, original_backend)
                self.assertIsNot(copied.backend, original.backend)
                # Replacing an inner facade's backend on the copy is isolated.
                copied.objects.backend = copy(copied.objects.backend)
                self.assertIs(original.backend, original_backend)

    def test_supported_check_rebinding_is_rejected_on_original_and_copies(self):
        for kind in (_GuardedObjects, _CheckedObjects):
            original = kind(self.f.objects, self.check)
            for reader in (original, copy(original), copy(copy(original))):
                with self.assertRaises(AttributeError):
                    reader.check = lambda: None
                self.assertEqual(reader.check, self.check)
        self.h.grant(self.event_id, "revoke")
        for kind in (_GuardedObjects, _CheckedObjects):
            with self.assertRaises(PermissionError):
                copy(copy(kind(self.f.objects, self.check))).get(self.reference)

    def test_owner_withdrawal_during_cipher_fetch_blocks_get_put_and_recovery_before_aead(self):
        for kind in (_GuardedObjects, _CheckedObjects):
            for operation in ("get", "put", "recovery"):
                with self.subTest(kind=kind.__name__, operation=operation):
                    self.h.grant(self.event_id)
                    reader = copy(copy(kind(self.f.objects, self.check)))
                    backend = self.f.objects.backend
                    actual_fetch = backend.get_object
                    target_aad = f"{self.f.scope.storage_scope()}:{self.reference.object_id}".encode()
                    withdrawn, opened = False, []
                    def fetch(namespace, object_id):
                        nonlocal withdrawn
                        sealed = actual_fetch(namespace, object_id)
                        if object_id == self.reference.object_id and not withdrawn:
                            withdrawn = True
                            self.h.grant(self.event_id, "revoke")
                        return sealed
                    def cipher(key):
                        actual = AESGCM(key)
                        class ObservedCipher:
                            encrypt = actual.encrypt
                            def decrypt(self, *args):
                                if args[2] == target_aad:
                                    opened.append(True)
                                return actual.decrypt(*args)
                        return ObservedCipher()
                    with patch.object(backend, "get_object", side_effect=fetch), \
                         patch("flora.selected.object_store.AESGCM", side_effect=cipher):
                        with self.assertRaises(PermissionError):
                            if operation == "get":
                                reader.get(self.reference)
                            elif operation == "put":
                                reader.put(self.material.plaintext)
                            else:
                                reader.recover_reference(object_id=self.reference.object_id,
                                    expected_plaintext_sha256=self.reference.plaintext_sha256)
                    self.assertTrue(withdrawn)
                    self.assertEqual(opened, [])


if __name__ == "__main__":
    unittest.main()
