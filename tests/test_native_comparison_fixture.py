"""Native comparison fixture binding mechanics, not physical backend evidence.

The SQL recorder and producer/phase receipts are existing fictional component
fixtures. Selected metadata custody, encrypted proof reads, enrolled-key checks,
the comparison fixture's actual binder and runtime authority guards are real.
"""
import ast
from copy import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from flora.selected.comparison_custody import SelectedRunEvidencePolicy, XTDBComparisonCustody
from flora.selected.experiment_runtime import _AuthorizedRuntimeReads
from flora.selected.native_reads import ReadOnlyNativeSQLConnection
from flora.selected.owner_authorization import Ed25519OwnerActionVerifier
from flora.selected.personal_artifact_custody import DurableOwnerProofLookup

import native_contract_fixture as support


def _actual_comparison_history_binder(custody):
    """Execute the integration fixture callback without replacing its body."""
    path = Path(__file__).parent / "integration" / "test_selected_native_comparison.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    callbacks = [node for node in ast.walk(tree)
                 if isinstance(node, ast.FunctionDef) and node.name == "bind_actual_history"]
    if len(callbacks) != 1:
        raise AssertionError("native comparison fixture must expose exactly one history binder")
    namespace = {"copy": copy, "custody": custody,
                 "SelectedRunEvidencePolicy": SelectedRunEvidencePolicy}
    exec(compile(ast.Module(body=callbacks, type_ignores=[]), str(path), "exec"), namespace)
    return namespace["bind_actual_history"]


class NativeComparisonFixtureBindingTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.native = support.NativeContractFixture(self.directory.name)
        self.addAsyncCleanup(self.native.close)
        f = self.native.f
        self.approval = self.native.test._activate_state()
        owner = self.native.runtime.state_approval_verifier
        self.public_key = owner.key.public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.proof = owner.proofs[self.approval.event_id]
        self.recorded_proof = f.private.record_owner_proof(proof=self.proof,
            owner_public_key=self.public_key, log=f.log, objects=f.objects,
            occurred_at="2026-09-29T14:30:00Z", expected_revision=len(f.log.replay()) - 1)
        owner.proofs.clear()
        self.native.runtime.state_approval_verifier = Ed25519OwnerActionVerifier(scope=f.scope,
            owner_public_key=self.public_key, proofs=DurableOwnerProofLookup(custody=f.private,
                log=f.log, objects=f.objects, owner_public_key=self.public_key))
        self.request = json.loads(f.objects.get(f.references.get(self.approval.payload_reference)))
        self.custody = XTDBComparisonCustody(scope=f.scope, authority_namespace_id=f.namespace,
            connection=f.connection, registry=f.registry, objects=f.objects, log=f.log)

    def bound_runtime(self):
        connection = ReadOnlyNativeSQLConnection(support.FixtureRawReadConnection(self.native),
                                                 read_timeout_ms=1000)
        self.addCleanup(connection.close)
        session = self.native._bind(connection)
        _actual_comparison_history_binder(self.custody)(session.runtime, session.lineage)
        return session.runtime, session.lineage

    async def test_actual_comparison_binder_recovers_enrolled_approval_on_owned_custody(self):
        original = self.native.runtime.state_approval_verifier
        runtime, lineage = self.bound_runtime()
        self.assertEqual(runtime.context_integrity_domain, "selected-current-context-v1")
        self.assertEqual(runtime.maximum_context_sources, 128)
        self.assertEqual(lineage.history_authority.history_metadata_domain, "selected-history-metadata-v1")
        self.assertEqual(lineage.history_authority.maximum_history_sources, 32)
        owner = runtime.state_approval_verifier
        self.assertIsNot(owner, original)
        self.assertIsNot(owner.proofs, original.proofs)
        self.assertIs(owner.proofs.custody, runtime.original_references.custody)
        self.assertIsNot(owner.proofs.custody, original.proofs.custody)
        self.assertIs(owner.proofs.custody.connection, runtime.sources.connection)
        self.assertIs(original.proofs.custody, self.native.f.private)
        self.assertIs(lineage.history_authority.custody.connection, runtime.sources.connection)
        self.assertIs(lineage.history_authority.permissions, runtime.source_policy)
        checks, fetched = [], []
        backend = self.native.runtime.objects.backend
        fetch = backend.get_object
        def current():
            checks.append(True)
        def observe(namespace, object_id):
            fetched.append(object_id)
            return fetch(namespace, object_id)
        guarded = runtime._guarded_state_verifier(_AuthorizedRuntimeReads(runtime.objects, current))
        with patch.object(backend, "get_object", side_effect=observe):
            self.assertTrue(guarded.authenticated_approval(self.approval, self.request))
        self.assertIn(self.recorded_proof.manifest.object_id, fetched)
        self.assertTrue(checks)
        self.assertEqual(guarded.proofs.get(self.approval.event_id), self.proof)

    async def test_live_withdrawal_before_proof_fetch_denies_bound_approval(self):
        runtime, _ = self.bound_runtime()
        allowed, checks, fetched, metadata_reads = [True], [], [], []
        def current():
            checks.append(allowed[0])
            if not allowed[0]:
                raise PermissionError("fixture current proof authority withdrawn")
        guarded = runtime._guarded_state_verifier(_AuthorizedRuntimeReads(runtime.objects, current))
        backend = self.native.runtime.objects.backend
        fetch = backend.get_object
        def observe(namespace, object_id):
            fetched.append(object_id)
            return fetch(namespace, object_id)
        metadata = runtime.state_approval_verifier.proofs.custody.metadata
        def withdraw_after_metadata(artifact_id):
            record = metadata(artifact_id)
            metadata_reads.append(artifact_id)
            allowed[0] = False
            return record
        with patch.object(backend, "get_object", side_effect=observe):
            self.assertTrue(guarded.authenticated_approval(self.approval, self.request))
            self.assertTrue(fetched)
            fetched.clear()
            with patch.object(runtime.state_approval_verifier.proofs.custody, "metadata",
                              side_effect=withdraw_after_metadata):
                with self.assertRaisesRegex(PermissionError, "proof authority withdrawn"):
                    guarded.authenticated_approval(self.approval, self.request)
        self.assertTrue(metadata_reads)
        self.assertFalse(checks[-1])
        self.assertEqual(fetched, [])


if __name__ == "__main__":
    unittest.main()
