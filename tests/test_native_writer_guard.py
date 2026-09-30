"""Physical socket ownership/fault mechanics with a fictional driver/verifier.

These are not psycopg, XTDB deployment or exclusive factory qualifications.
"""
from dataclasses import replace
import hashlib
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cognitive_kernel.canonical import canonical_sha256
from cognitive_kernel.contracts import ProductHostScope
from flora.selected.native_writer_guard import (
    NativeWriterConfiguration, NativeWriterGuard, VerifiedNativeWriterOwnership,
)
from flora.selected.native_worker import NativeWorkerManifest
from test_bounded_xtdb_reads import SocketDriver


class NativeWriterGuardTest(unittest.TestCase):
    def make(self, *, allowance=50, driver=None):
        scope = ProductHostScope.create(product_id="friday", host_instance_id="writer-fixture",
            schema_version="1.0.0", encryption_domain="writer-fixture-key")
        configuration = NativeWriterConfiguration(scope, "writer-namespace", "exclusive-fixture-owner",
            "fictional-driver", "a" * 64, allowance, 100)
        driver = SocketDriver() if driver is None else driver
        driver.pgconn = SimpleNamespace(backend_pid=1234)
        self.addCleanup(driver.peer.close)
        self.addCleanup(driver.socket.close)
        verifier = SimpleNamespace(verify_native_writer=lambda *, request, receipt:
            VerifiedNativeWriterOwnership("fixture-qualifier", "fixture-qualification",
                canonical_sha256(request), hashlib.sha256(receipt).hexdigest(), True))
        with patch.dict(sys.modules, psycopg=SimpleNamespace(Connection=SocketDriver, __version__="fictional-driver")):
            guard = NativeWriterGuard(connection=driver, configuration=configuration, verifier=verifier,
                qualification_receipt=b"supplied fictional ownership proof", qualifier_id="fixture-qualifier",
                qualification_id="fixture-qualification")
        guard.verify_identity()
        return driver, guard

    def test_stalled_actual_socket_wakes_owner_and_never_reuses_poisoned_writer(self):
        driver, guard = self.make()
        started = time.monotonic()
        with self.assertRaisesRegex(TimeoutError, "operation deadline"):
            with guard.operation(remaining_seconds=1) as lease:
                lease.require_active(driver)
                driver.execute("SELECT fixture", ())
        self.assertLess(time.monotonic() - started, .8)
        self.assertEqual(driver.closes, [threading.get_ident()])
        with self.assertRaises(PermissionError):
            guard.operation(remaining_seconds=1)
        self.assertEqual(len(driver.calls), 1)

    def test_success_preserves_exact_driver_and_disarms_old_watchdog(self):
        driver, guard = self.make()
        driver.peer.sendall(b"first")
        with guard.operation(remaining_seconds=1) as lease:
            self.assertIs(guard.connection, driver)
            self.assertEqual(driver.execute("INSERT fixture", ()), b"first")
            lease.require_active(driver)
        time.sleep(.08)
        driver.peer.sendall(b"second")
        with guard.operation(remaining_seconds=1):
            self.assertEqual(driver.execute("SELECT fixture", ()), b"second")
        self.assertEqual(driver.closes, [])
        self.assertIsNone(guard._active)

    def test_task_remaining_time_caps_larger_frozen_writer_allowance(self):
        driver, guard = self.make(allowance=1000)
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            with guard.operation(remaining_seconds=.04):
                driver.execute("SELECT fixture", ())
        self.assertLess(time.monotonic() - started, .6)

    def test_fault_poisoning_keeps_partial_work_and_prevents_continuation(self):
        driver, guard = self.make()
        marker = []
        with self.assertRaisesRegex(RuntimeError, "fixture fault"):
            with guard.operation(remaining_seconds=1):
                marker.append("partial canonical fixture")
                raise RuntimeError("fixture fault")
        self.assertEqual(marker, ["partial canonical fixture"])
        self.assertEqual(driver.closes, [threading.get_ident()])
        with self.assertRaises(PermissionError):
            guard.require_identity()

    def test_cross_thread_owner_and_overlapping_scope_refused_before_driver(self):
        driver, guard = self.make(allowance=1000)
        denied = []
        def other():
            try:
                guard.operation(remaining_seconds=1)
            except RuntimeError:
                denied.append(True)
        thread = threading.Thread(target=other)
        thread.start(); thread.join(1)
        self.assertEqual(denied, [True])
        with guard.operation(remaining_seconds=1):
            with self.assertRaisesRegex(PermissionError, "overlap"):
                with guard.operation(remaining_seconds=1):
                    self.fail("overlapping writer opened")
        self.assertEqual(driver.calls, [])

    def test_duplicate_guard_cannot_claim_an_existing_connection(self):
        driver, guard = self.make()
        with patch.dict(sys.modules, psycopg=SimpleNamespace(Connection=SocketDriver, __version__="fictional-driver")):
            with self.assertRaisesRegex(PermissionError, "already belongs"):
                NativeWriterGuard(connection=driver, configuration=guard.configuration, verifier=guard.verifier,
                    qualification_receipt=guard.qualification_receipt, qualifier_id="fixture-qualifier",
                    qualification_id="fixture-qualification")

    def test_changed_config_or_invalid_ownership_proof_cannot_touch_driver(self):
        driver, guard = self.make()
        guard.configuration = replace(guard.configuration, owner_id="changed-owner")
        with self.assertRaises(PermissionError):
            guard.operation(remaining_seconds=1)
        guard.configuration = replace(guard.configuration, owner_id="exclusive-fixture-owner")
        guard._verified = None
        guard.verifier.verify_native_writer = lambda **kwargs: None
        with self.assertRaises(PermissionError):
            guard.verify_identity()
        self.assertEqual(driver.calls, [])

    def test_changed_current_proof_refuses_driver_before_opening_operation(self):
        driver, guard = self.make()
        for changed in (replace(guard._verified, allowed=False),
                        replace(guard._verified, qualifier_id="changed-qualifier"),
                        replace(guard._verified, qualification_id="changed-qualification")):
            guard._verified = changed
            with self.assertRaises(PermissionError):
                guard.operation(remaining_seconds=1)
        self.assertEqual(driver.calls, [])

    def test_worker_manifest_writer_hashes_are_complete_and_preserve_legacy_record(self):
        scope = ProductHostScope.create(product_id="friday", host_instance_id="writer-fixture",
            schema_version="1.0.0", encryption_domain="writer-fixture-key")
        manifest = NativeWorkerManifest(scope, "writer-namespace", "fixture-worker",
            *("a" * 64 for _ in range(8)), 10, 10, 10, 10, 10, 10)
        legacy = manifest.record()
        self.assertEqual(legacy["schema"], "flora-native-worker-manifest-v1")
        self.assertNotIn("writer_guard_artifact_sha256", legacy)
        self.assertNotIn("writer_guard_configuration_sha256", legacy)
        self.assertEqual(manifest.manifest_sha256, canonical_sha256(legacy))
        for changed in (replace(manifest, writer_guard_artifact_sha256="b" * 64),
                        replace(manifest, writer_guard_configuration_sha256="c" * 64)):
            with self.assertRaisesRegex(ValueError, "supplied together"):
                changed.record()
        guarded = replace(manifest, writer_guard_artifact_sha256="b" * 64,
            writer_guard_configuration_sha256="c" * 64)
        self.assertEqual(guarded.record()["schema"], "flora-native-worker-manifest-v2")
        self.assertNotEqual(guarded.manifest_sha256, manifest.manifest_sha256)

    def test_failed_watchdog_setup_and_raising_close_shutdown_actual_socket(self):
        driver, guard = self.make()
        with patch.object(threading.Thread, "start", side_effect=RuntimeError("fixture setup")), \
                patch.object(driver, "close", side_effect=OSError("fixture close fault")):
            with self.assertRaisesRegex(RuntimeError, "retirement failed"):
                with guard.operation(remaining_seconds=1):
                    self.fail("setup failure exposed writer")
        driver.socket.settimeout(.2)
        self.assertEqual(driver.socket.recv(1), b"")
        with self.assertRaises(PermissionError):
            guard.require_identity()

    def test_unsupported_real_driver_is_rejected_without_guessing_owner(self):
        driver, guard = self.make()
        with self.assertRaises(TypeError):
            NativeWriterGuard(connection=driver, configuration=guard.configuration, verifier=guard.verifier,
                qualification_receipt=guard.qualification_receipt, qualifier_id="fixture-qualifier",
                qualification_id="fixture-qualification")


if __name__ == "__main__":
    unittest.main()
