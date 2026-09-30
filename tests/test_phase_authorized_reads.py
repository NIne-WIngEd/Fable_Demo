"""Actual selected authority around copied phase ciphertext readers.

The controlled row/object transports qualify guard behavior and query counts;
they provide no physical engine latency or learned producer evidence.
"""
from copy import copy
import unittest
from unittest.mock import patch

from flora.selected.experiment_runtime import _AuthorizedRuntimeBackend, _AuthorizedRuntimeReads
from flora.selected.object_store import AESGCM
from flora.selected.phase_snapshots import PhaseAuthorizedObjectReads
import test_phase_source_fence as fixtures


class PhaseAuthorizedReadsTest(unittest.TestCase):
    def setUp(self):
        self.h = fixtures.PhaseSourceFenceTest()
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.f = self.h.f
        self.event_id = self.h.h.before.event_ids[0]
        self.reference = self.f.references[self.h.h.before.sources[0].event.payload_reference]
        self.check_count = 0

    def check(self):
        self.check_count += 1
        return self.h.verify()

    def test_repeated_copies_keep_one_installed_guard_and_fresh_queries(self):
        reader = PhaseAuthorizedObjectReads(self.f.objects, self.check)
        for _ in range(4):
            before_checks = self.check_count
            before_queries = len(self.f.connection.calls)
            self.assertEqual(reader.get(self.reference), self.h.h.before.sources[0].plaintext)
            self.assertEqual(self.check_count - before_checks, 4)
            self.assertEqual(len(self.f.connection.calls) - before_queries, 12)
            reader = copy(reader)
        self.h.grant(self.event_id, "revoke")
        with self.assertRaises(PermissionError):
            reader.get(self.reference)

    def test_copy_owns_facade_plane_and_top_backend_without_stripping_distinct_guards(self):
        reader = PhaseAuthorizedObjectReads(self.f.objects, self.check)
        extra_checks = []
        original_backend = reader.backend
        reader.backend = _AuthorizedRuntimeBackend(original_backend, lambda: extra_checks.append("current"))
        copied = copy(reader)
        self.assertIsNot(copied, reader)
        self.assertIsNot(copied.objects, reader.objects)
        self.assertIsNot(copied.backend, reader.backend)
        self.assertIs(copied.backend.backend, original_backend)
        self.assertEqual(copied.get(self.reference), self.h.h.before.sources[0].plaintext)
        self.assertEqual(self.check_count, 4)
        self.assertEqual(len(extra_checks), 2)
        copied.backend = _AuthorizedRuntimeBackend(copied.backend, lambda: extra_checks.append("later"))
        self.assertIs(reader.backend.backend, original_backend)
        self.assertIsNot(copied.backend, reader.backend)
        before = self.check_count
        self.assertEqual(copied.get(self.reference), self.h.h.before.sources[0].plaintext)
        self.assertEqual(self.check_count - before, 4)
        self.assertEqual(extra_checks[-4:], ["later", "current", "current", "later"])
        runtime_checks = []
        runtime = _AuthorizedRuntimeReads(copied, lambda: runtime_checks.append("runtime"))
        self.assertEqual(runtime.get(self.reference), self.h.h.before.sources[0].plaintext)
        self.assertEqual(len(runtime_checks), 4)

    def test_installed_authorizer_cannot_be_replaced_on_original_or_copy(self):
        reader = PhaseAuthorizedObjectReads(self.f.objects, self.check)
        copied = copy(reader)
        for facade in (reader, copied):
            with self.assertRaises(AttributeError):
                facade.source_authorizer = lambda: True
        self.h.grant(self.event_id, "revoke")
        for facade in (reader, copied):
            with self.assertRaises(PermissionError):
                facade.get(self.reference)

    def test_cipher_fetch_withdrawal_denies_get_put_and_recovery_before_aead(self):
        for operation in ("get", "put", "recovery"):
            with self.subTest(operation=operation):
                # Each operation begins with a fresh actual owner grant.
                self.h.grant(self.event_id)
                reader = copy(copy(PhaseAuthorizedObjectReads(self.f.objects, self.check)))
                backend = self.f.objects.backend
                original = backend.get_object
                decrypts = []
                guarded_aad = f"{self.f.scope.storage_scope()}:{self.reference.object_id}".encode()
                withdrawn = False
                def fetch(namespace, object_id):
                    nonlocal withdrawn
                    sealed = original(namespace, object_id)
                    if object_id == self.reference.object_id and not withdrawn:
                        withdrawn = True
                        self.h.grant(self.event_id, "revoke")
                    return sealed
                def cipher(key):
                    actual = AESGCM(key)
                    class CheckedCipher:
                        encrypt = actual.encrypt
                        def decrypt(self, *args):
                            if args[2] == guarded_aad:
                                decrypts.append(True)
                            return actual.decrypt(*args)
                    return CheckedCipher()
                with patch.object(backend, "get_object", side_effect=fetch), \
                     patch("flora.selected.object_store.AESGCM", side_effect=cipher):
                    with self.assertRaises(PermissionError):
                        if operation == "get":
                            reader.get(self.reference)
                        elif operation == "put":
                            reader.put(self.h.h.before.sources[0].plaintext)
                        else:
                            reader.recover_reference(object_id=self.reference.object_id,
                                expected_plaintext_sha256=self.reference.plaintext_sha256)
                self.assertTrue(withdrawn)
                self.assertEqual(decrypts, [])


if __name__ == "__main__":
    unittest.main()
