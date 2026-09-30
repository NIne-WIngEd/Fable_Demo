"""Phase-view contracts on fictional SQL/producers; not selected-engine evidence."""
from copy import deepcopy
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import sys
import unittest

from cognitive_kernel.canonical import canonical_json_bytes, canonical_sha256
from flora.selected.phase_snapshots import XTDBPhaseSnapshotCustody, SelectedPhaseSnapshot, plan_record, FrozenPhaseUpdatePolicy, verify_update_policy, PhaseAuthorizedObjectReads, _TABLE
from flora.selected.phase_routes import SelectedPhaseRoute, PhaseSnapshotReference, recognize_phase_snapshot, SelectedPhaseLineageRouter
from flora.selected.claims import _CURRENT
from flora.selected.personal_state import _ACTIVE


def fixture(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parent / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_f = fixture("flora_phase_lineage_fixture", "test_selected_judgment_lineage.py")


class PhaseSQL(_f._StateSQLCalls):
    def __init__(self, prior):
        super().__init__(prior)
        self.histories = {key: [deepcopy(value)] for (table, key), value in self.rows.items() if table == _CURRENT}
    def execute(self, sql, parameters):
        if sql.startswith("SELECT record_json") and "FOR SYSTEM_TIME ALL" in sql:
            rows = [{**value, "_valid_from": None, "_valid_to": None, "_system_from": None, "_system_to": None}
                for value in self.histories.get(parameters[0], ())]
            return _f._semantic_fixture._Cursor(rows)
        value = super().execute(sql, parameters)
        if sql.startswith("INSERT INTO " + _CURRENT):
            import re
            names = re.search(r"\(([^)]+)\) VALUES", sql).group(1).split(", ")
            row = dict(zip(names, parameters))
            self.histories.setdefault(row["_id"], []).append(deepcopy(row))
        return value


class PhaseSnapshotTest(unittest.TestCase):
    def setUp(self):
        self.lineage_fixture = _f.SelectedJudgmentLineageTest()
        self.lineage_fixture.setUp()
        self.addCleanup(self.lineage_fixture.doCleanups)
        self.f = self.lineage_fixture.fixture
        connection = PhaseSQL(self.f.connection)
        for plane in (self.f.registry, self.f.candidates, self.f.authority, self.f.gateway,
                      self.f.state, self.f.artifacts, self.f.private, self.f.runtime.private):
            plane.connection = connection
        self.f.connection = connection
        self.lineage_fixture._activate_state()
        self.live, self.plan = self.f.runtime, self.lineage_fixture.plan
        self.history = self.lineage_fixture.histories[("case-one", "after")]
        self.verifier = self.lineage_fixture._verifier()
        self.custody = XTDBPhaseSnapshotCustody(runtime=self.live, run_id="phase-run",
            run_plan_sha256="9" * 64, clock=self.f._clock, allow_unregistered_fixture_route=True)
        self.snapshot = self.custody.capture(snapshot_id="phase-one", case_id="case-one", phase="after", arm="flora_full",
            plan=self.plan, lineage=self.verifier, history=self.history)

    def route(self, **changes):
        values = dict(custody=self.custody, snapshot_id=self.snapshot.snapshot_id, history=self.history,
            history_authority=self.verifier.history_authority, historical_bindings=self.live.bindings,
            invocation_id_for=lambda request, result: "phase-judgment")
        values.update(changes)
        return SelectedPhaseRoute(**values)

    def test_capture_recovery_rebinds_actual_services_and_independent_phase_receipts(self):
        recovered = self.custody.recover(snapshot_id="phase-one", history=self.history, history_authority=self.verifier.history_authority)
        self.assertEqual(recovered.record, self.snapshot.record)
        route = self.route()
        self.assertEqual(route.runtime._context(self.plan).receipt_record(), self.snapshot.record["context_receipt"])
        self.assertIs(route.runtime.context_policy.claims, route.runtime.claims)
        self.assertIs(route.runtime.context_policy.state, route.runtime.state)
        self.assertIs(route.runtime.admission.authority, route.runtime.claims)
        self.assertIsNot(route.runtime.claims, self.live.claims)
        with self.assertRaises(PermissionError):
            route.runtime.form_experience()

    def test_live_authority_guard_is_raise_only_for_actual_context_assembly(self):
        route = self.route()
        self.assertIsNone(route.guard_live())
        self.assertEqual(route.runtime._context(self.plan, authority_guard=route.guard_live).receipt_record(),
            self.snapshot.record["context_receipt"])

    def test_head_replacement_uses_pinned_actual_historical_claim_projection(self):
        captured = self.snapshot.record["claims"][0]
        key = self.live.claims._row_id(captured["claim_id"])
        before = deepcopy(self.f.connection.rows[(_CURRENT, key)])
        current = json.loads(before["record_json"])
        current["projection_id"] = "fictional-new-projection"
        current["projection_sha256"] = "f" * 64
        self.f.connection.rows[(_CURRENT, key)]["record_json"] = json.dumps(current)
        route = self.route()
        self.assertEqual(route.runtime.claims.load_current(captured["claim_id"]), captured["projection"])
        self.assertEqual(self.live.claims.load_current(captured["claim_id"])["projection_id"], "fictional-new-projection")
        self.assertEqual(route.runtime._context(self.plan).receipt_record(), self.snapshot.record["context_receipt"])

    def test_cached_manifest_cannot_invent_a_historical_projection(self):
        key = self.live.claims._row_id(self.snapshot.record["claims"][0]["claim_id"])
        self.f.connection.histories[key] = []
        with self.assertRaises((ValueError, PermissionError)):
            self.route()

    def test_live_claim_quarantine_and_permission_withdrawal_precede_private_reads(self):
        captured = self.snapshot.record["claims"][0]
        key = self.live.claims._row_id(captured["claim_id"])
        row = self.f.connection.rows[(_CURRENT, key)]
        value = json.loads(row["record_json"])
        value["deletion_state"] = "pending_deletion"
        row["record_json"] = json.dumps(value)
        old_get = self.f.objects.backend.get_object
        self.f.objects.backend.get_object = lambda *_: self.fail("quarantined snapshot reached private ciphertext read")
        try:
            with self.assertRaises(ValueError):
                self.route()
        finally:
            self.f.objects.backend.get_object = old_get
        row["record_json"] = json.dumps(captured["projection"])
        self.f.permitted[0] = False
        self.f.objects.backend.get_object = lambda *_: self.fail("withdrawn snapshot reached private ciphertext read")
        try:
            with self.assertRaises(PermissionError):
                self.route()
        finally:
            self.f.objects.backend.get_object = old_get

    def test_existing_bound_route_rechecks_withdrawal_before_any_context_decrypt(self):
        route = self.route()
        self.f.permitted[0] = False
        old_get = self.f.objects.backend.get_object
        self.f.objects.backend.get_object = lambda *_: self.fail("bound phase route bypassed withdrawn source")
        try:
            with self.assertRaises((ValueError, PermissionError)):
                route.runtime._context(self.plan)
        finally:
            self.f.objects.backend.get_object = old_get

    def test_runtime_final_authority_guard_blocks_dispatch_after_slow_qualification(self):
        self.live.clock = lambda: "2026-09-29T15:00:00Z"
        binding = self.live.bindings["personality_judgment"]
        old_verify = binding.qualification_verifier.verify
        allowed, fired = [True], [False]
        def guard():
            if not allowed[0]:
                raise PermissionError("fixture final binding withdrawn before dispatch")
        def slow_verify(**kwargs):
            result = old_verify(**kwargs)
            frame = sys._getframe(1)
            while frame is not None:
                if frame.f_code.co_name == "_execute" and "input_record" in frame.f_locals:
                    allowed[0], fired[0] = False, True
                    break
                frame = frame.f_back
            return result
        binding.qualification_verifier.verify = slow_verify
        count = len(binding.adapter.invocations)
        try:
            with self.assertRaisesRegex(PermissionError, "final binding withdrawn"):
                self.live.judge(plan=self.plan, task=b"fictional guarded final task",
                    invocation_id="final-dispatch-race", authority_guard=guard)
        finally:
            binding.qualification_verifier.verify = old_verify
        self.assertTrue(fired[0])
        self.assertEqual(len(binding.adapter.invocations), count)
        self.assertFalse(any(event.event_type in {"qualified_model_output", "decision"}
            and event.provenance.derivation_activity_id == "final-dispatch-race" for event in self.live.log.replay()))

    def test_dispatch_guard_requalifies_after_last_slow_artifact_lookup(self):
        self.live.clock = lambda: "2026-09-29T15:00:00Z"
        binding = self.live.bindings["personality_judgment"]
        old_verify = binding.qualification_verifier.verify
        allowed, fired, checked = [True], [False], []
        def dispatch():
            checked.append(True)
            if not allowed[0]:
                raise PermissionError("fixture independent update qualification withdrawn")
        def slow_verify(**kwargs):
            result = old_verify(**kwargs)
            frame = sys._getframe(1)
            while frame is not None:
                if frame.f_code.co_name == "_execute" and "input_record" in frame.f_locals:
                    allowed[0], fired[0] = False, True
                    break
                frame = frame.f_back
            return result
        binding.qualification_verifier.verify = slow_verify
        count = len(binding.adapter.invocations)
        try:
            with self.assertRaises(PermissionError):
                self.live.judge(plan=self.plan, task=b"fictional dispatch qualification task",
                    invocation_id="last-qualification-race", authority_guard=lambda: None, dispatch_guard=dispatch)
        finally:
            binding.qualification_verifier.verify = old_verify
        self.assertTrue(fired[0])
        self.assertTrue(checked, "actual dispatch boundary did not requalify the withdrawn update proof")
        self.assertEqual(len(binding.adapter.invocations), count)

    def test_unregistered_mechanics_need_explicit_legacy_fixture_opt_in(self):
        with self.assertRaisesRegex(TypeError, "explicit fixture opt-in"):
            XTDBPhaseSnapshotCustody(runtime=self.live, run_id="unregistered-mechanics",
                run_plan_sha256="9" * 64, clock=self.f._clock)

    def test_exact_historical_checkpoint_is_required_after_recreation(self):
        path = self.live.bindings["personality_judgment"].checkpoint_path
        Path(path).write_bytes(b"wrong historical checkpoint bytes")
        with self.assertRaises(ValueError):
            self.route()

    def test_declared_shape_or_altered_producer_receipt_cannot_become_qualified(self):
        bad = deepcopy(self.snapshot.record)
        bad["producer_receipts"][0]["receipt_base64"] = "Y2hhbmdlZA=="
        with self.assertRaisesRegex(ValueError, "receipt bytes"):
            SelectedPhaseSnapshot(bad).validate()
        self.verifier.history_authority.allowed = False
        with self.assertRaises(PermissionError):
            self.route()

    def test_mutable_accelerator_route_must_first_freeze_exact_nominations(self):
        with self.assertRaisesRegex(ValueError, "frozen exact"):
            plan_record(replace(self.plan, query_vector=(0.1,), vector_limit=1))

    def test_snapshot_identity_cannot_be_recaptured_as_an_updated_phase(self):
        with self.assertRaisesRegex(ValueError, "already frozen"):
            self.custody.capture(snapshot_id="phase-one", case_id="case-one", phase="after", arm="flora_full",
                plan=self.plan, lineage=self.verifier, history=self.history)

    def test_capture_denied_evaluation_authority_precedes_every_private_backend_read(self):
        self.verifier.history_authority.allowed = False
        original = self.f.objects.backend.get_object
        self.f.objects.backend.get_object = lambda *_: self.fail("denied phase capture opened private ciphertext")
        try:
            with self.assertRaisesRegex(PermissionError, "history authority"):
                self.custody.capture(snapshot_id="denied-phase", case_id="case-one", phase="after", arm="flora_full",
                    plan=self.plan, lineage=self.verifier, history=self.history)
            self.assertIsNone(self.custody.intent("denied-phase"))
        finally:
            self.f.objects.backend.get_object = original

    def test_quarantine_during_slow_source_check_precedes_snapshot_decryption(self):
        captured = self.snapshot.record["claims"][0]
        key = self.live.claims._row_id(captured["claim_id"])
        old_sources = self.custody._sources_now
        def slow_sources(source_ids, **kwargs):
            result = old_sources(source_ids, **kwargs)
            row = self.f.connection.rows[(_CURRENT, key)]
            changed = json.loads(row["record_json"])
            changed["deletion_state"] = "pending_deletion"
            row["record_json"] = json.dumps(changed)
            return result
        self.custody._sources_now = slow_sources
        old_get = self.f.objects.backend.get_object
        self.f.objects.backend.get_object = lambda *_: self.fail("slow source check allowed quarantined private fetch")
        try:
            with self.assertRaises(ValueError):
                self.custody.recover(snapshot_id="phase-one", history=self.history, history_authority=self.verifier.history_authority)
        finally:
            self.f.objects.backend.get_object = old_get

    def test_postcipher_permission_check_quarantine_precedes_aead_decryption(self):
        from unittest.mock import patch
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        original = self.f.objects.backend.get_object
        fired, decrypts = [False], []
        captured = self.snapshot.record["claims"][0]
        snapshot_object = self.custody.metadata("phase-one")["object_id"]
        def fetch(namespace, object_id):
            sealed = original(namespace, object_id)
            frame, inside_get = sys._getframe(1), False
            while frame is not None:
                filename = Path(frame.f_code.co_filename).name
                inside_get |= filename == "object_store.py" and frame.f_code.co_name == "get"
                frame = frame.f_back
            if not fired[0] and inside_get and object_id == snapshot_object:
                fired[0] = True
                row = self.f.connection.rows[(_CURRENT, self.live.claims._row_id(captured["claim_id"]))]
                current = json.loads(row["record_json"])
                current["deletion_state"] = "pending_deletion"
                row["record_json"] = json.dumps(current)
            return sealed
        decrypt = AESGCM.decrypt
        def check_decrypt(aes, *args):
            if fired[0]:
                decrypts.append(True)
            return decrypt(aes, *args)
        with patch.object(self.f.objects.backend, "get_object", fetch), patch.object(AESGCM, "decrypt", check_decrypt):
            with self.assertRaises(ValueError):
                self.custody.recover(snapshot_id="phase-one", history=self.history, history_authority=self.verifier.history_authority)
        self.assertTrue(fired[0], "fixture did not reach the actual postcipher permission window")
        self.assertEqual(decrypts, [])

    def test_archive_permission_is_separate_from_original_only_model_context(self):
        metadata = self.custody.metadata("phase-one")
        original = self.live.source_policy.permits
        self.live.source_policy.permits = lambda source, purpose: source.evidence.ref_id != metadata["event_id"] and original(source, purpose)
        self.assertFalse(self.live.context_policy.allow_event(metadata["event_id"], "personal_judgment"))
        recovered = self.custody.recover(snapshot_id="phase-one", history=self.history, history_authority=self.verifier.history_authority)
        self.assertEqual(recovered.record, self.snapshot.record)
        self.assertEqual(self.route().runtime._context(self.plan).receipt_record(), self.snapshot.record["context_receipt"])

    def test_history_withdrawn_while_reading_append_revision_cannot_append_phase_event(self):
        old_replay = self.live.log.replay
        initial = tuple(old_replay())
        def revision_read():
            import inspect
            entries = old_replay()
            caller = inspect.currentframe().f_back
            if caller.f_code.co_name == "capture" and "event" in caller.f_locals:
                self.verifier.history_authority.allowed = False
            return entries
        self.live.log.replay = revision_read
        try:
            with self.assertRaises(PermissionError):
                self.custody.capture(snapshot_id="revision-race", case_id="case-one", phase="after", arm="flora_full",
                    plan=self.plan, lineage=self.verifier, history=self.history)
            self.assertEqual(tuple(old_replay()), initial)
            self.assertIsNone(self.custody.metadata("revision-race"))
        finally:
            self.live.log.replay = old_replay

    def _drop_index(self):
        self.f.connection.rows.pop((_TABLE, self.custody._key("phase-one")))

    def _reconcile(self, **changes):
        values = dict(snapshot_id="phase-one", history=self.history, history_authority=self.verifier.history_authority,
            historical_bindings=self.live.bindings, invocation_id_for=lambda request, result: "phase-judgment")
        values.update(changes)
        return self.custody.reconcile(**values)

    def test_orphan_index_reconciliation_reuses_exact_canonical_capture_without_append(self):
        before = tuple(self.live.log.replay())
        self._drop_index()
        with self.assertRaises(ValueError):
            self.custody.recover(snapshot_id="phase-one", history=self.history, history_authority=self.verifier.history_authority)
        with self.assertRaisesRegex(PermissionError, "partial phase capture intent"):
            self.custody.capture(snapshot_id="phase-one", case_id="case-one", phase="after", arm="flora_full",
                plan=self.plan, lineage=self.verifier, history=self.history)
        self.assertEqual(self._reconcile().record, self.snapshot.record)
        self.assertEqual(self._reconcile().record, self.snapshot.record)
        self.assertEqual(tuple(self.live.log.replay()), before)
        self.assertEqual(self.route().snapshot.record, self.snapshot.record)

    def test_orphan_repair_cannot_adopt_a_moved_live_claim_head(self):
        self._drop_index()
        captured = self.snapshot.record["claims"][0]
        row = self.f.connection.rows[(_CURRENT, self.live.claims._row_id(captured["claim_id"]))]
        changed = json.loads(row["record_json"])
        changed["projection_id"], changed["projection_sha256"] = "later-production-projection", "f" * 64
        row["record_json"] = json.dumps(changed)
        with self.assertRaisesRegex(PermissionError, "head moved"):
            self._reconcile()
        self.assertIsNone(self.custody.metadata("phase-one"))

    def test_orphan_head_moved_during_final_permission_check_precedes_index_write(self):
        self._drop_index()
        captured = self.snapshot.record["claims"][0]
        from unittest.mock import patch
        original_gate = XTDBPhaseSnapshotCustody._phase_metadata_gate
        fired = [False]
        def slow_gate(custody, snapshot_id, expected):
            result = original_gate(custody, snapshot_id, expected)
            frame, final_repair_gate = sys._getframe(1), False
            while frame is not None:
                final_repair_gate |= (frame.f_code.co_name == "reconcile"
                    and frame.f_locals.get("route") is not None)
                frame = frame.f_back
            if not fired[0] and final_repair_gate:
                fired[0] = True
                row = self.f.connection.rows[(_CURRENT, self.live.claims._row_id(captured["claim_id"]))]
                changed = json.loads(row["record_json"])
                changed["projection_id"], changed["projection_sha256"] = "later-during-permission", "f" * 64
                row["record_json"] = json.dumps(changed)
            return result
        with patch.object(XTDBPhaseSnapshotCustody, "_phase_metadata_gate", slow_gate):
            with self.assertRaisesRegex(PermissionError, "head moved"):
                self._reconcile()
        self.assertTrue(fired[0])
        self.assertIsNone(self.custody.metadata("phase-one"))

    def test_orphan_repair_respects_withdrawal_and_actual_checkpoint_before_index_write(self):
        self._drop_index()
        self.f.permitted[0] = False
        old_get = self.f.objects.backend.get_object
        self.f.objects.backend.get_object = lambda *_: self.fail("withdrawn orphan repair performed a private ciphertext read")
        try:
            with self.assertRaises(PermissionError):
                self._reconcile()
        finally:
            self.f.objects.backend.get_object = old_get
        self.assertIsNone(self.custody.metadata("phase-one"))
        self.f.permitted[0] = True
        Path(self.live.bindings["personality_judgment"].checkpoint_path).write_bytes(b"unqualified wrong checkpoint")
        with self.assertRaises(ValueError):
            self._reconcile()
        self.assertIsNone(self.custody.metadata("phase-one"))

    def test_intent_hash_is_bound_to_actual_canonical_event_not_cached_manifest(self):
        row = self.f.connection.rows[("flora_selected_phase_capture_intents", self.custody._key("phase-one"))]
        intent = json.loads(row["record_json"])
        intent["claim_ids"] = []
        intent["record_sha256"] = canonical_sha256({key: value for key, value in intent.items() if key != "record_sha256"})
        row["record_json"], row["record_sha256"] = json.dumps(intent), intent["record_sha256"]
        old_get = self.f.objects.backend.get_object
        self.f.objects.backend.get_object = lambda *_: self.fail("changed intent reached private capture ciphertext read")
        try:
            with self.assertRaisesRegex(ValueError, "canonical intent"):
                self.route()
        finally:
            self.f.objects.backend.get_object = old_get

    def test_lifecycle_recognition_requires_exact_typed_qualified_snapshot(self):
        metadata = self.custody.metadata("phase-one")
        event = next(event for event in self.live.log.replay() if event.event_id == metadata["event_id"])
        reference = PhaseSnapshotReference("phase-run", "phase-one", self.snapshot.snapshot_sha256,
            event.event_id, "case-one", "after", "flora_full")
        values = dict(reference=reference, event=event, custody=self.custody, history=self.history,
            history_authority=self.verifier.history_authority, historical_bindings=self.live.bindings,
            invocation_id_for=lambda request, result: "phase-judgment")
        self.assertIs(recognize_phase_snapshot(**values), reference)
        with self.assertRaises(PermissionError):
            recognize_phase_snapshot(**{**values, "reference": replace(reference, case_id="another-case")})
        self.verifier.history_authority.allowed = False
        with self.assertRaises(PermissionError):
            recognize_phase_snapshot(**values)

    def test_live_metadata_fence_rejects_mutation_of_the_authenticated_private_manifest(self):
        route = self.route()
        context = route.runtime._context(self.plan)
        route.snapshot.record["arm"] = "same_evidence_ablation"
        old_get = self.f.objects.backend.get_object
        self.f.objects.backend.get_object = lambda *_: self.fail("changed phase manifest reached private fetch")
        try:
            with self.assertRaisesRegex(PermissionError, "manifest changed"):
                route.check_live()
            with self.assertRaisesRegex(PermissionError, "manifest changed"):
                route.lineage.context_lineage(case_id="case-one", phase="after", history=self.history,
                    context=context)
        finally:
            self.f.objects.backend.get_object = old_get

    def test_before_ablation_does_not_claim_a_withheld_future_update(self):
        record = {**self.snapshot.record, "phase": "before", "arm": "same_evidence_ablation"}
        self.assertIsNone(verify_update_policy(runtime=self.live, snapshot_record=record, receipt=None))
        record["update_policy"] = FrozenPhaseUpdatePolicy("withhold_personal_judgment_update", "prior", "f" * 64,
            (self.history.event_ids[-1],)).record()
        with self.assertRaisesRegex(ValueError, "future update"):
            verify_update_policy(runtime=self.live, snapshot_record=record, receipt=b"not-a-proof")

    def test_after_ablation_requires_exact_independent_update_exclusion_adapter(self):
        record = {**self.snapshot.record, "arm": "same_evidence_ablation",
            "update_policy": FrozenPhaseUpdatePolicy("withhold_personal_judgment_update", "prior", "f" * 64,
                (self.history.event_ids[-1],)).record()}
        with self.assertRaisesRegex(PermissionError, "actual independent"):
            verify_update_policy(runtime=self.live, snapshot_record=record, receipt=None)
        with self.assertRaisesRegex(PermissionError, "no update-exclusion adapter"):
            verify_update_policy(runtime=self.live, snapshot_record=record, receipt=b"shape-is-not-proof")
        record["update_policy"]["excluded_update_event_ids"] = ["not-canonical"]
        with self.assertRaisesRegex(ValueError, "absent canonical"):
            verify_update_policy(runtime=self.live, snapshot_record=record, receipt=b"shape-is-not-proof")

    def test_signed_fixture_update_exclusion_binds_actual_after_ablation_and_rechecks_denial(self):
        """Fixture binding only; the signer inspects no real trained update."""
        import base64
        import hashlib
        class FixtureUpdateQualifier(_f.FictionalPhaseQualifier):
            denied = False
            def verify_phase_update_policy(self, *, request, receipt):
                wrapper = json.loads(receipt)
                payload = wrapper["payload"]
                self.public_key.verify(base64.b64decode(wrapper["signature"], validate=True), canonical_json_bytes(payload))
                if self.denied or payload["request_sha256"] != canonical_sha256(request):
                    raise PermissionError("fixture producer denied exact update policy")
                return {**payload, "schema": "flora-qualified-phase-update-exclusion-v1",
                    "receipt_sha256": hashlib.sha256(receipt).hexdigest()}
        qualifier = FixtureUpdateQualifier(self.f.qualification_key.public_key())
        self.live.bindings = {role: replace(binding, qualification_verifier=qualifier) for role, binding in self.live.bindings.items()}
        # This contract scenario starts after both fixture observations. Its
        # correction is a newly appended source after that before capture.
        before_history = self.history
        self.lineage_fixture.histories[("case-one", "before")] = before_history
        before = self.custody.capture(snapshot_id="fixture-before-full", case_id="case-one", phase="before", arm="flora_full",
            plan=self.plan, lineage=self.verifier, history=before_history)
        from cognitive_kernel.experience import ExperienceEvent
        from cognitive_kernel.contracts import ProvenanceReference
        from flora.comparison_run import HistorySnapshot, SourceMaterial
        from flora.selected.formation_context import register_experience_source
        correction_bytes = b"fictional correction after the captured before context"
        correction_raw = self.f.objects.put(correction_bytes)
        correction = ExperienceEvent.create(event_type="user_correction", scope=self.live.scope, occurred_at=self.f._clock(),
            content_digest=correction_raw.plaintext_sha256, provenance=ProvenanceReference.create(provenance_type="generated_reconstruction",
                source_reference_ids=(self.history.event_ids[-1],), derivation_activity_id="fixture-new-correction", responsible_component="fictional-test"),
            retention_class="ordinary_experience", storage_tier="raw_buffer", parent_event_ids=(self.history.event_ids[-1],),
            payload_reference=correction_raw.object_id)
        self.live.log.append(correction, expected_revision=len(self.live.log.replay()) - 1)
        register_experience_source(event_id=correction.event_id, raw=correction_raw, registry=self.f.registry,
            log=self.live.log, objects=self.f.objects, role="generated_reconstruction", modality="structured")
        self.history = HistorySnapshot(self.live.scope, self.history.sources + (SourceMaterial(correction, correction_bytes),))
        self.lineage_fixture.histories[("case-one", "after")] = self.history
        policy = FrozenPhaseUpdatePolicy("withhold_personal_judgment_update", before.snapshot_id, before.snapshot_sha256,
            (correction.event_id,))
        artifact = self.live._resolve("personality_judgment")[1]
        actual_lineage = self.verifier.context_lineage(case_id="case-one", phase="after", history=self.history,
            context=self.live._context(self.plan))
        request = {"schema": "flora-phase-update-exclusion-request-v1", "scope": self.live.scope.metadata_record(),
            "authority_namespace_id": self.live.authority_namespace_id, "run_id": "phase-run", "run_plan_sha256": "9"*64,
            "case_id": "case-one", "phase": "after", "arm": "same_evidence_ablation", "history_sha256": self.history.digest(),
            "context_lineage_sha256": actual_lineage.lineage_sha256, "update_policy": policy.record(),
            "artifact_manifest_sha256": artifact.manifest_sha256}
        payload = {"schema": "fictional-qualified-update-exclusion-v1", "request_sha256": canonical_sha256(request),
            "artifact_manifest_sha256": artifact.manifest_sha256, "qualifier_id": artifact.qualifier_id,
            "qualification_id": artifact.qualification_id, "allowed": True}
        receipt = canonical_json_bytes({"payload": payload,
            "signature": base64.b64encode(self.f.qualification_key.sign(canonical_json_bytes(payload))).decode()})
        captured = self.custody.capture(snapshot_id="fixture-after-ablation", case_id="case-one", phase="after", arm="same_evidence_ablation",
            plan=self.plan, lineage=self.verifier, history=self.history, update_policy=policy, update_receipt=receipt)
        route = self.route(snapshot_id=captured.snapshot_id)
        context = route.runtime._context(self.plan)
        route.lineage.context_lineage(case_id="case-one", phase="after", history=self.history, context=context)
        qualifier.denied = True
        with self.assertRaisesRegex(PermissionError, "producer denied"):
            route.lineage.context_lineage(case_id="case-one", phase="after", history=self.history, context=context)

    def test_nested_backend_wrapper_survives_proxy_copy_without_mutating_live_plane(self):
        from flora.selected.experiment_runtime import _AuthorizedRuntimeReads
        reference = self.f.references.get(self.history.sources[0].event.payload_reference)
        original = self.f.objects.backend
        count = [0]
        def gate():
            count[0] += 1
        wrapped = _AuthorizedRuntimeReads(PhaseAuthorizedObjectReads(self.f.objects, lambda: True), gate)
        self.assertIs(self.f.objects.backend, original)
        self.assertIsNot(wrapped.objects.backend, original)
        self.assertEqual(wrapped.get(reference), self.history.sources[0].plaintext)
        self.assertGreaterEqual(count[0], 4)  # outer and actual ciphertext pre/post

    def _router_arguments(self):
        import hashlib
        from flora.comparison_run import _context_bytes
        from flora.selected.native_arm import NativePhaseSnapshotBinding, NativeInvocationEntry, FrozenNativeArmPlan
        from flora.selected.comparison_custody import XTDBComparisonCustody, SelectedRunEvidencePolicy
        from flora.selected.formation_policy import XTDBFormationPermissionPolicy
        cf = fixture("flora_phase_router_contract_fixture", "comparator_fixtures.py")
        histories, question, run_plan = cf.inputs(self.live.scope.host_instance_id, actual_sources=list(self.history.sources))
        context_sha256 = hashlib.sha256(_context_bytes(self.live._context(self.plan))).hexdigest()
        snapshots, arms = {}, {}
        for arm in ("flora_full", "same_evidence_ablation"):
            entries = []
            for phase in ("before", "after"):
                binding = NativePhaseSnapshotBinding("router-run", arm + "-" + phase, arm)
                snapshots[("case", phase, arm)] = binding
                entries.append(NativeInvocationEntry("case", phase, arm + "-invocation-" + phase,
                    self.plan, context_sha256, binding))
            arms[arm] = FrozenNativeArmPlan(self.live.scope, self.live.authority_namespace_id, arm, "a"*64, tuple(entries))
        bindings = dict(run_plan.arm_bindings)
        actual_sha = self.live._resolve("personality_judgment")[1].checkpoint_sha256
        for arm in arms:
            bindings[arm] = replace(bindings[arm], model_artifact_sha256=actual_sha, lineage_sha256=arms[arm].lineage_sha256)
        run_plan = replace(run_plan, arm_bindings=bindings)
        custody = XTDBPhaseSnapshotCustody(runtime=self.live, run_id="router-run", run_plan_sha256=run_plan.digest(), clock=self.f._clock, allow_unregistered_fixture_route=True)
        comparison = XTDBComparisonCustody(scope=self.live.scope, authority_namespace_id=self.live.authority_namespace_id,
            connection=self.f.connection, registry=self.f.registry, objects=self.f.objects, log=self.live.log)
        comparison.register_inputs(run_id="router-run", plan=run_plan, histories=histories,
            questions={"case": question}, occurred_at=self.f._clock())
        permissions = XTDBFormationPermissionPolicy(scope=self.live.scope, authority_namespace_id=self.live.authority_namespace_id,
            connection=self.f.connection, registry=self.f.registry)
        authority = SelectedRunEvidencePolicy(custody=comparison, run_id="router-run", permissions=permissions)
        return dict(custody=custody, run_plan=run_plan, histories=histories, history_authority=authority,
            bindings_by_snapshot={binding.snapshot_id: self.live.bindings for binding in snapshots.values()},
            snapshots=snapshots, frozen_native_arms=arms)

    def test_router_header_binds_actual_frozen_native_configuration_but_does_not_qualify_missing_archives(self):
        values = self._router_arguments()
        router = SelectedPhaseLineageRouter(**values)
        self.assertEqual(router.binding_sha256, canonical_sha256(router.record()))
        self.assertIs(router.runtime, self.live)
        self.assertEqual(router.history_for("case", "after"), values["histories"][("case", "after")])
        with self.assertRaisesRegex(ValueError, "snapshot is absent"):
            router.route_for(case_id="case", phase="after", arm="flora_full")
        with self.assertRaisesRegex(PermissionError, "no frozen native"):
            router.route_for(case_id="case", phase="after", arm="general_model_memory")

    def test_router_refuses_untyped_or_cross_arm_entries_and_nonselected_eval_authority(self):
        values = self._router_arguments()
        changed = {**values["snapshots"], ("case", "before", "flora_full"): "plausible-snapshot-id"}
        with self.assertRaisesRegex(TypeError, "typed predeclared"):
            SelectedPhaseLineageRouter(**{**values, "snapshots": changed})
        wrong = dict(values["snapshots"])
        wrong[("case", "before", "flora_full")] = wrong[("case", "before", "same_evidence_ablation")]
        with self.assertRaisesRegex(ValueError, "run/native arm"):
            SelectedPhaseLineageRouter(**{**values, "snapshots": wrong})
        with self.assertRaisesRegex(TypeError, "selected evaluation authority"):
            SelectedPhaseLineageRouter(**{**values, "history_authority": self.verifier.history_authority})


if __name__ == "__main__":
    unittest.main()
