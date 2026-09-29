"""Deterministic policy-boundary checks, not XTDB/Kurrent qualification.

The SQL call recorder asserts immutable/CAS write shape and supplies read
responses. It is not a replacement database or a durability experiment. Real
encrypted objects and canonical Experience/source contracts exercise request
binding and the upstream RegisteredFormationStore read barrier.
"""

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import re
import tempfile
from types import SimpleNamespace
import unittest

from cognitive_kernel.canonical import CognitiveKernelContractError, normalize_timestamp
from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from cognitive_kernel.formation_contracts import FormationEvidenceRef
from cognitive_kernel.formation_sources import RegisteredFormationSource, RegisteredFormationStore
from flora.selected.formation_policy import (
    FormationPermissionAction, XTDBFormationPermissionPolicy,
    formation_permission_payload,
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
        self.rows, self.calls = {}, []
        self.adapters = SimpleNamespace(
            types={"text": SimpleNamespace(oid=25)}, register_dumper=lambda *_: None)

    @contextmanager
    def transaction(self):
        snapshot = deepcopy(self.rows)
        try:
            yield
        except Exception:
            self.rows = snapshot
            raise

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
                raise ValueError("synthetic immutable/CAS absence assertion failed")
            return _Cursor([])
        if statement.startswith("ASSERT EXISTS"):
            if row is None or row["record_sha256"] != parameters[1]:
                raise ValueError("synthetic current-head CAS assertion failed")
            return _Cursor([])
        return _Cursor([row] if row is not None else [])


class _Registry:
    def __init__(self, scope, namespace):
        self.scope, self.authority_namespace_id = scope, namespace
        self.sources = {}

    def lookup(self, ref_id):
        return self.sources.get(ref_id)


class _Log:
    def __init__(self, scope):
        self.scope, self.events = scope, []

    def replay(self):
        return self.events.copy()


class _Verifier:
    def __init__(self, permitted=True):
        self.permitted = permitted
        self.calls = []

    def authorized_action(self, action, source, event):
        self.calls.append((action, source, event))
        return self.permitted


class FormationPolicyContractTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.scope = ProductHostScope.create(
            product_id="friday", host_instance_id="fictional-policy-host",
            schema_version="1.0.0", encryption_domain="fictional-policy-key")
        self.namespace = "fictional-policy-sources"
        self.objects = EncryptedObjectPlane(
            scope=self.scope, key=b"p" * 32,
            backend=LocalObjectBackend(self.directory.name))
        self.connection = _SQLCalls()
        self.registry = _Registry(self.scope, self.namespace)
        self.log = _Log(self.scope)
        self.references = {}
        self.counter = 0
        self.policy = self._policy()
        self.original = self._source(b"fictional original source")
        self.derived = self._source(b"fictional source with a registered parent",
                                    parents=(self.original.evidence.ref_id,))
        self.verifier = _Verifier()

    def _policy(self):
        return XTDBFormationPermissionPolicy(
            scope=self.scope, authority_namespace_id=self.namespace,
            connection=self.connection, registry=self.registry)

    def _event(self, content, event_type, timestamp, parents=()):
        raw = self.objects.put(content)
        self.references[raw.object_id] = raw
        event = ExperienceEvent.create(
            event_type=event_type, scope=self.scope, occurred_at=timestamp,
            content_digest=raw.plaintext_sha256,
            provenance=ProvenanceReference.create(
                provenance_type="owner_attested_canonical",
                source_reference_ids=(raw.object_id,), responsible_component="fictional-ingress"),
            retention_class="ordinary_experience", storage_tier="raw_buffer",
            payload_reference=raw.object_id, parent_event_ids=parents)
        self.log.events.append(event)
        return event

    def _source(self, content, parents=()):
        event = self._event(content, "observation", "2026-09-29T10:00:00Z", parents)
        source = RegisteredFormationSource.create(
            evidence=FormationEvidenceRef(
                ref_id=event.event_id, scope=self.scope,
                authority_namespace_id=self.namespace, content_digest=event.content_digest,
                role="historical_experience", modality="text", parent_refs=parents),
            object_ref=event.payload_reference)
        self.registry.sources[event.event_id] = source
        return source

    def _request(self, source, decision="allow", previous=None, *, action_id=None,
                 purpose="memory_formation", include_predecessor=True):
        self.counter += 1
        timestamp = normalize_timestamp((datetime(2026, 9, 29, 12, tzinfo=timezone.utc)
                                         + timedelta(seconds=self.counter)).isoformat())
        action = FormationPermissionAction.create(
            scope=self.scope, authority_namespace_id=self.namespace,
            action_id=action_id or f"permission-{self.counter}",
            source_ref_id=source.evidence.ref_id,
            source_registration_sha256=source.registration_sha256,
            purpose=purpose, decision=decision, generation=(1 if previous is None else
                                                          previous[0].generation + 1),
            previous_action_sha256=None if previous is None else previous[0].action_sha256,
            authorization_ref=f"independent-owner-proof-{self.counter}", authorized_at=timestamp)
        parents = (source.evidence.ref_id,)
        if previous is not None and include_predecessor:
            parents += (previous[1].event_id,)
        event = self._event(formation_permission_payload(action),
                            "formation_permission_action", timestamp, parents)
        return action, event

    def _apply(self, request, *, verifier=None, policy=None):
        return (policy or self.policy).apply(
            request[0], request_event_id=request[1].event_id, log=self.log,
            objects=self.objects, references=self.references,
            verifier=self.verifier if verifier is None else verifier)

    def _store(self, *, policy=None, on_read=None):
        outer = self

        class Custody:
            def read(self, scope, object_ref):
                content = outer.objects.get(outer.references[object_ref])
                if on_read is not None:
                    on_read()
                return content

        return RegisteredFormationStore(
            scope=self.scope, authority_namespace_id=self.namespace,
            registry=self.registry, custody=Custody(), permits=(policy or self.policy).permits)

    def test_absent_permission_and_recorded_unauthorized_request_do_not_grant_use(self):
        request = self._request(self.original)
        self.assertFalse(self.policy.permits(self.original, "memory_formation"))
        with self.assertRaisesRegex(ValueError, "independently authorized"):
            self._apply(request, verifier=_Verifier(False))
        self.assertEqual(self.connection.rows, {})
        with self.assertRaisesRegex(CognitiveKernelContractError, "permission revoked"):
            self._store().read(self.original.evidence)
        self._apply(request)
        self.assertTrue(self.policy.permits(self.original, "memory_formation"))
        self.assertFalse(self.policy.permits(self.original, "model_training"))

    def test_revocation_is_fresh_after_recreation_and_old_grant_retry_is_noop(self):
        grant = self._request(self.original)
        self._apply(grant)
        self.assertEqual(self._store().read(self.original.evidence), b"fictional original source")
        revoked = self._request(self.original, "revoke", grant)
        self._apply(revoked)
        recreated = self._policy()
        self.assertEqual(recreated.current_action(self.original.evidence.ref_id,
                                                  "memory_formation"), revoked[0])
        self.assertFalse(recreated.permits(self.original, "memory_formation"))
        writes_before = sum(sql.startswith("INSERT") for sql, _ in self.connection.calls)
        self._apply(grant, policy=recreated)
        self.assertEqual(sum(sql.startswith("INSERT") for sql, _ in self.connection.calls),
                         writes_before)
        with self.assertRaisesRegex(CognitiveKernelContractError, "permission revoked"):
            self._store(policy=recreated).read(self.original.evidence)

    def test_parent_revocation_blocks_derived_read_before_and_during_custody(self):
        original_grant = self._request(self.original)
        self._apply(original_grant)
        self._apply(self._request(self.derived))
        self.assertTrue(self.policy.permits(self.derived, "memory_formation"))
        revoke = self._request(self.original, "revoke", original_grant)
        with self.assertRaisesRegex(CognitiveKernelContractError, "revoked"):
            self._store(on_read=lambda: self._apply(revoke)).read(self.derived.evidence)
        self.assertFalse(self._policy().permits(self.derived, "memory_formation"))
        with self.assertRaisesRegex(CognitiveKernelContractError, "permission revoked"):
            self._store().read(self.derived.evidence)

    def test_canonical_request_scope_raw_and_predecessor_are_verified(self):
        grant = self._request(self.original)
        with self.assertRaisesRegex(ValueError, "lacks replayed"):
            self.policy.apply(grant[0], request_event_id="not-replayed", log=self.log,
                              objects=self.objects, references=self.references, verifier=self.verifier)
        with self.assertRaisesRegex(ValueError, "encrypted raw request"):
            self.policy.apply(grant[0], request_event_id=grant[1].event_id, log=self.log,
                              objects=self.objects, references={}, verifier=self.verifier)
        foreign = FormationPermissionAction.create(**{
            key: value for key, value in grant[0].__dict__.items() if key != "action_sha256"
        } | {"authority_namespace_id": "foreign-authority"})
        with self.assertRaisesRegex(ValueError, "crosses scope or authority"):
            self._apply((foreign, grant[1]))
        self._apply(grant)
        missing_parent = self._request(self.original, "deny", grant, include_predecessor=False)
        with self.assertRaisesRegex(ValueError, "stale or unbound"):
            self._apply(missing_parent)
        initial_again = self._request(self.original)
        with self.assertRaisesRegex(ValueError, "stale or unbound"):
            self._apply(initial_again)
        valid_next = self._request(self.original, "deny", grant)
        self._apply(valid_next)
        reused = self._request(self.original, "allow", valid_next,
                               action_id=grant[0].action_id)
        with self.assertRaisesRegex(ValueError, "identifier is immutable"):
            self._apply(reused)

    def test_tampered_or_missing_head_fails_closed_without_reviving_old_grant(self):
        grant = self._request(self.original)
        self._apply(grant)
        key = self.policy._key("head", self.original.evidence.ref_id, "memory_formation")
        row = self.connection.rows[("flora_formation_permission_current", key)]
        material = json.loads(row["record_json"])
        material["action_sha256"] = "f" * 64
        row["record_json"] = json.dumps(material)
        with self.assertRaisesRegex(ValueError, "metadata changed"):
            self._policy().permits(self.original, "memory_formation")
        del self.connection.rows[("flora_formation_permission_current", key)]
        self.assertFalse(self._policy().permits(self.original, "memory_formation"))
        with self.assertRaisesRegex(ValueError, "explicit recovery required"):
            self._apply(grant)


if __name__ == "__main__":
    unittest.main()
