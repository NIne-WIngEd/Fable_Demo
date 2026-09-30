"""Real selected policy/owner grants with controlled metadata SQL; no models.

The finite batch recorder checks query shape and same-call races. It is not
physical XTDB consistency or latency evidence. Claim rows below are explicit
metadata fixtures; they assert no learned or independently admitted semantics.
"""
import base64
from copy import copy, deepcopy
import inspect
import json
import re
import sys
import unittest
from unittest.mock import patch

from cognitive_kernel.canonical import canonical_sha256
from cognitive_kernel.contracts import ProductHostScope
from flora.selected.claims import XTDBClaimAuthority, _CURRENT
from flora.selected.formation_policy import FormationPermissionAction, formation_permission_payload
from flora.selected.judgment_context import RegisteredJudgmentContextPolicy
from flora.selected.owner_authorization import OwnerActionProof, owner_action_message
from flora.selected.personal_artifact_custody import _SourceAuthorizedObjectReads
from flora.selected.phase_source_fence import verify_current_phase_sources
import test_history_fence as fixtures
from metadata_batch_fixture import _Cursor


class PhaseSourceFenceTest(unittest.TestCase):
    def setUp(self):
        self.h = fixtures.HistoryFenceTest()
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.f = self.h.f
        self.registry, self.permissions = self.h.registry, self.h.permissions
        self.grant_count = 0
        for material in self.h.materials:
            self.grant(material.event.event_id)
        self.claims = XTDBClaimAuthority(scope=self.f.scope,
            authority_namespace_id=self.f.namespace, connection=self.f.connection)
        state = copy(self.f.state)
        state.registry, state.policy = self.registry, self.permissions
        self.policy = RegisteredJudgmentContextPolicy(claims=self.claims, state=state,
            log=self.f.log, registry=self.registry, permissions=self.permissions)

    def grant(self, event_id, decision="allow"):
        source = self.registry.lookup(event_id)
        prior = self.permissions.current_action(event_id, "personal_judgment")
        self.grant_count += 1
        action = FormationPermissionAction.create(scope=self.f.scope,
            authority_namespace_id=self.f.namespace, action_id=f"phase-fence-grant-{self.grant_count}",
            source_ref_id=event_id, source_registration_sha256=source.registration_sha256,
            purpose="personal_judgment", decision=decision, generation=1 if prior is None else prior.generation + 1,
            previous_action_sha256=None if prior is None else prior.action_sha256,
            authorization_ref="fictional-enrolled-owner", authorized_at="2026-09-29T18:00:00Z")
        parents = (event_id,)
        if prior is not None:
            parents += (self.permissions._stored_action(prior.action_id)["request_event_id"],)
        event = self.f.event(formation_permission_payload(action), event_type="formation_permission_action",
            timestamp=action.authorized_at, parents=parents)
        self.f.proofs[event.event_id] = OwnerActionProof("formation_permission", event.event_id, event.event_sha256,
            base64.b64encode(self.f.key.sign(owner_action_message(event, "formation_permission"))).decode())
        self.permissions.apply(action, request_event_id=event.event_id, log=self.f.log,
            objects=self.f.objects, references=self.f.references, verifier=self.f.verifier)

    def verify(self, **kwargs):
        return verify_current_phase_sources(policy=self.policy,
            source_event_ids=kwargs.pop("source_event_ids", self.h.before.event_ids), **kwargs)

    def original_cipher_guard(self, callback):
        original = self.f.objects.backend.get_object
        original_ids = {material.event.payload_reference for material in self.h.materials}
        def read(namespace, object_id):
            self.assertNotIn(object_id, original_ids, "metadata authority opened original ciphertext")
            return original(namespace, object_id)
        with patch.object(self.f.objects.backend, "get_object", side_effect=read):
            return callback()

    def claim_fixture(self):
        record = {"claim_id": "metadata-only-claim", "deletion_state": "active",
            "conflict_state": "none", "adjudication_state": "accepted", "projection_sha256": "a"*64,
            "envelope": {"scope": self.f.scope.metadata_record(), "authority_namespace_id": self.f.namespace}}
        key = self.claims._row_id(record["claim_id"])
        self.f.connection.rows[(_CURRENT, key)] = {"_id": key, "scope_digest": self.claims.scope_digest,
            "projection_sha256": record["projection_sha256"], "record_json": json.dumps(record)}
        return record, key

    def test_one_guard_samples_each_immutable_source_row_once_and_opens_no_private_bytes(self):
        before = len(self.f.connection.calls)
        self.original_cipher_guard(self.verify)
        calls = self.f.connection.calls[before:]
        batches = [sql for sql, _ in calls if "AS flora_current_metadata_fence LIMIT" in sql]
        self.assertEqual(len(batches), 1)
        source_reads = [(re.search(r"FROM (\w+)", sql).group(1), parameters[0])
            for sql, parameters in calls if sql.startswith("SELECT * FROM flora_formation_")
            and "FOR VALID_TIME ALL" in sql and "permission" not in sql]
        self.assertEqual(len(source_reads), len(set(source_reads)))
        self.verify()
        self.grant(self.h.before.event_ids[0], "revoke")
        with self.assertRaises(PermissionError):
            self.original_cipher_guard(self.verify)

    def test_actual_instance_mutated_source_and_permission_predicates_are_preserved(self):
        for service, name in ((self.policy, "allow_event"), (self.permissions, "permits")):
            with self.subTest(name=name):
                with patch.object(service, name, return_value=False) as denial:
                    with self.assertRaises(PermissionError):
                        self.original_cipher_guard(self.verify)
                    self.assertGreater(denial.call_count, 0)

    def test_last_phase_callback_cannot_change_actual_external_source_predicate(self):
        allowed, calls = True, 0
        original = self.policy.allow_event
        def permit(event_id, purpose):
            return allowed and original(event_id, purpose)
        def authority():
            nonlocal allowed, calls
            calls += 1
            if calls == 2:
                allowed = False
        with patch.object(self.policy, "allow_event", side_effect=permit):
            with self.assertRaisesRegex(PermissionError, "predicate changed"):
                self.original_cipher_guard(lambda: self.verify(authority_guard=authority))
        self.assertEqual(calls, 2)

    def test_reader_or_predicate_replacement_during_guard_is_not_hidden_by_copy(self):
        for service, name in ((self.policy, "allow_event"), (self.permissions, "permits"),
                              (self.registry, "lookup")):
            original, calls = getattr(service, name), 0
            def authority():
                nonlocal calls
                calls += 1
                if calls == 2:
                    setattr(service, name, lambda *_: False)
            try:
                with self.subTest(name=name), self.assertRaises(PermissionError):
                    self.original_cipher_guard(lambda: self.verify(authority_guard=authority))
            finally:
                setattr(service, name, original)

    def test_last_authority_callback_cannot_replace_the_actual_purpose(self):
        count = 0
        def authority():
            nonlocal count
            count += 1
            if count == 2:
                self.policy.purpose = "formation"
        with self.assertRaises(PermissionError):
            self.original_cipher_guard(lambda: self.verify(authority_guard=authority))
        self.assertEqual(count, 2)

    def test_last_final_grant_withdrawal_of_earlier_original_precedes_decryption(self):
        original = self.permissions.current_action
        lines, first = inspect.getsourcelines(verify_current_phase_sources)
        final_line = first + next(i for i, line in enumerate(lines)
            if "action = permissions.current_action(event_id, policy.purpose)" in line)
        changed = False
        def action(event_id, purpose):
            nonlocal changed
            result = original(event_id, purpose)
            frame, final = sys._getframe(1), False
            while frame is not None:
                if frame.f_code is verify_current_phase_sources.__code__ and frame.f_lineno == final_line:
                    final = True
                    break
                frame = frame.f_back
            if final and event_id == self.h.before.event_ids[0] and not changed:
                # Traversal pops input IDs, so the first original is the LAST
                # callback. Withdraw the already-checked second original.
                changed = True
                self.grant(self.h.before.event_ids[1], "revoke")
            return result
        raw = self.f.references[self.h.before.sources[0].event.payload_reference]
        checked = _SourceAuthorizedObjectReads(self.f.objects, self.verify)
        with patch.object(self.permissions, "current_action", side_effect=action):
            with self.assertRaises(PermissionError):
                self.original_cipher_guard(lambda: checked.get(raw))
        self.assertTrue(changed)

    def test_last_slow_authority_callback_quarantine_is_seen_by_terminal_statement(self):
        record, key = self.claim_fixture()
        count = 0
        def authority():
            nonlocal count
            count += 1
            if count == 2:
                current = deepcopy(record)
                current["deletion_state"] = "pending_delete"
                self.f.connection.rows[(_CURRENT, key)]["record_json"] = json.dumps(current)
        with self.assertRaises(PermissionError):
            self.original_cipher_guard(lambda: self.verify(claim_ids=(record["claim_id"],), authority_guard=authority))
        self.assertEqual(count, 2)

    def test_last_callback_cannot_mutate_sampled_raw_registration(self):
        count = 0
        key = self.registry._key("raw", self.h.before.sources[0].event.payload_reference)
        def authority():
            nonlocal count
            count += 1
            if count == 2:
                self.f.connection.rows[("flora_formation_raw_references", key)]["record_sha256"] = "9"*64
        with self.assertRaises(PermissionError):
            self.original_cipher_guard(lambda: self.verify(authority_guard=authority))

    def test_scope_forgery_and_foreign_connection_refuse_before_ciphertext(self):
        other = ProductHostScope.create(product_id="friday", host_instance_id="foreign-fence-host",
            schema_version="1.0.0", encryption_domain="foreign-fence-key")
        for field, value in (("scope", other), ("connection", object())):
            with self.subTest(field=field), patch.object(self.permissions, field, value):
                with self.assertRaises(PermissionError):
                    self.original_cipher_guard(self.verify)
        with patch.object(self.policy, "purpose", "memory_formation"):
            with self.assertRaises(PermissionError):
                self.original_cipher_guard(self.verify)

    def test_terminal_missing_duplicate_and_unexpected_rows_fail_closed(self):
        original = self.f.connection.execute
        for corruption in ("missing", "duplicate", "unexpected"):
            def execute(sql, parameters):
                cursor = original(sql, parameters)
                if "AS flora_current_metadata_fence LIMIT" not in sql:
                    return cursor
                names = [value.name for value in cursor.description]
                rows = [dict(zip(names, values)) for values in cursor.fetchall()]
                if corruption == "missing":
                    rows.pop()
                elif corruption == "duplicate":
                    rows[-1] = deepcopy(rows[0])
                else:
                    rows[-1]["_id"] = "f"*64
                return _Cursor(rows)
            with self.subTest(corruption=corruption), patch.object(self.f.connection, "execute", side_effect=execute):
                with self.assertRaises(PermissionError):
                    self.original_cipher_guard(self.verify)

    def test_explicit_cap_duplicate_and_unknown_nominations_refuse(self):
        cases = ({"maximum_rows": 1}, {"source_event_ids": ("missing-real-source",)},
                 {"source_event_ids": (self.h.before.event_ids[0],)*2})
        for arguments in cases:
            with self.subTest(arguments=arguments), self.assertRaises((ValueError, PermissionError)):
                self.original_cipher_guard(lambda: self.verify(**arguments))


if __name__ == "__main__":
    unittest.main()
