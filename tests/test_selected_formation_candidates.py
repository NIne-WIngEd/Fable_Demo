"""Deterministic candidate custody checks, not real XTDB qualification.

SQL and Experience calls are injected boundary recorders. Source preparation,
registered custody, canonical contracts and local AES-GCM objects are real.
No formation model, learned selector or alternative database is supplied.
"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

from cryptography.exceptions import InvalidTag

from cognitive_kernel.canonical import canonical_json_bytes
from cognitive_kernel.claim_contracts import CanonicalTaggedValue
from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from cognitive_kernel.formation_context_planner import FormationPlanningRequest
from cognitive_kernel.formation_contracts import FormationProposal, MemoryProposalBundle
from cognitive_kernel.formation_sources import RegisteredFormationStore
from flora.selected.decision_outcome import RecordedEvent
from flora.selected.experience import CommittedExperience
from flora.selected.formation_candidates import XTDBFormationProposalCandidates
from flora.selected.formation_context import (
    prepare_selected_formation, record_selected_formation_delivery,
    register_experience_source,
)
from flora.selected.formation_registry import (
    RegisteredEncryptedFormationCustody, XTDBFormationSourceRegistry,
)
from flora.selected.object_store import EncryptedObjectPlane, LocalObjectBackend

# Share the existing SQL shape recorder in both direct-file and discovery runs.
_TESTS = str(Path(__file__).resolve().parent)
if _TESTS not in sys.path:
    sys.path.insert(0, _TESTS)
from test_selected_formation_registry import _SQLCalls


class _FailingSQLCalls(_SQLCalls):
    """One injected index-write failure; this does not model transactions."""

    def __init__(self):
        super().__init__()
        self.fail_next_insert = False

    def execute(self, statement, parameters):
        if self.fail_next_insert and statement.startswith("INSERT"):
            self.fail_next_insert = False
            raise RuntimeError("injected candidate index failure")
        return super().execute(statement, parameters)


class _RecordedLog:
    """Deterministic scoped replay and expected-revision append recorder."""

    def __init__(self, scope):
        self.scope = scope
        self.entries = []
        self.append_calls = []

    def replay(self):
        return [entry.event for entry in self.entries]

    def replay_committed(self):
        return tuple(self.entries)

    def append(self, event, *, expected_revision):
        event.validate()
        if event.scope != self.scope:
            raise ValueError("injected log received a foreign-scope event")
        if expected_revision != len(self.entries) - 1:
            raise ValueError("injected log received a stale revision")
        self.append_calls.append((event, expected_revision))
        self.entries.append(CommittedExperience(
            event=event, stream_position=len(self.entries),
            recorded_at=datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
            + timedelta(minutes=len(self.entries)),
        ))


class _Values:
    """Independent scoped value service; model references alone grant no value."""

    def __init__(self, scope, namespace, values):
        self.scope = scope
        self.namespace = namespace
        self.values = dict(values)
        self.calls = []

    def resolve(self, scope, authority_namespace_id, value_ref):
        self.calls.append((scope, authority_namespace_id, value_ref))
        if scope != self.scope or authority_namespace_id != self.namespace:
            return None
        return self.values.get(value_ref)


class SelectedFormationCandidatesTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.scope = ProductHostScope.create(
            product_id="friday", host_instance_id="fictional-candidate-host",
            schema_version="1.0.0", encryption_domain="fictional-candidate-key",
        )
        self.namespace = "candidate-test-authority"
        self.backend = LocalObjectBackend(Path(self.directory.name) / "objects")
        self.objects = EncryptedObjectPlane(
            scope=self.scope, key=b"c" * 32, backend=self.backend)
        self.connection = _FailingSQLCalls()
        self.registry = self._registry()
        self.log = _RecordedLog(self.scope)
        self.permitted = [True]
        self.source_raw = self.objects.put(b"fictional source secret one")
        first = self._source(self.source_raw, "fictional-original-one", ())
        self.log.append(first, expected_revision=-1)
        self.second_raw = self.objects.put(b"fictional source secret two")
        second = self._source(
            self.second_raw, "fictional-original-two", (first.event_id,))
        self.log.append(second, expected_revision=0)
        for event, raw in ((first, self.source_raw), (second, self.second_raw)):
            register_experience_source(
                event_id=event.event_id, raw=raw, registry=self.registry,
                log=self.log, objects=self.objects, role="generated_reconstruction",
                modality="text", subject_ref=self.scope.host_instance_id,
                speaker_ref="fictional-source-speaker",
                source_item_ref=event.provenance.source_reference_ids[0],
                duplicate_group_ref="fictional-duplicate-group",
            )
        self.prepared = prepare_selected_formation(
            request=FormationPlanningRequest(
                scope=self.scope, authority_namespace_id=self.namespace,
                experience_refs=(second.event_id,),
                as_of="2026-09-29T12:02:00.000000Z",
            ),
            registry=self.registry, objects=self.objects,
            permits=lambda *_: self.permitted[0],
        )
        self.delivery = record_selected_formation_delivery(
            prepared=self.prepared, log=self.log, objects=self.objects,
            occurred_at="2026-09-29T12:03:00Z", expected_revision=1,
            request_id="fictional-formation-request",
        )
        self.artifact = "a" * 64
        self.value_one = CanonicalTaggedValue.create(
            type_tag="text", value="fictional candidate value secret one")
        self.value_two = CanonicalTaggedValue.create(
            type_tag="map", value={"fixture": "fictional candidate value secret two"})
        self.values = _Values(self.scope, self.namespace, {
            "candidate-value-one": self.value_one,
            "candidate-value-two": self.value_two,
        })
        packet = self.prepared.assembled.packet
        self.bundle = MemoryProposalBundle(
            scope=self.scope, authority_namespace_id=self.namespace,
            bundle_id="fictional-candidate-bundle",
            experience_refs=packet.experience_refs,
            context_digest=packet.content_digest(), model_artifact_digest=self.artifact,
            inference_run_id="fictional-inference-run",
            proposals=tuple(FormationProposal(
                proposal_id=f"fictional-proposal-{number}", kind="preference",
                domain="host", subject_ref=self.scope.host_instance_id,
                value_ref=f"candidate-value-{name}",
                evidence_refs=(packet.experience_refs[0],),
                epistemic_status="reconstruction",
            ) for number, name in ((1, "one"), (2, "two"))),
        )
        self.candidates = self._candidates()

    def _registry(self, *, objects=None):
        return XTDBFormationSourceRegistry(
            scope=(objects or self.objects).scope,
            authority_namespace_id=self.namespace, connection=self.connection)

    def _candidates(self, *, scope=None, namespace=None):
        return XTDBFormationProposalCandidates(
            scope=scope or self.scope,
            authority_namespace_id=namespace or self.namespace,
            connection=self.connection,
        )

    def _source(self, raw, original_id, parents):
        return ExperienceEvent.create(
            event_type="observation", scope=self.scope,
            occurred_at="2026-09-01T10:00:00Z",
            content_digest=raw.plaintext_sha256,
            provenance=ProvenanceReference.create(
                provenance_type="generated_reconstruction",
                source_reference_ids=(original_id,),
                derivation_activity_id="fictional-source-ingress",
                responsible_component="synthetic-test",
            ),
            retention_class="ordinary_experience", storage_tier="raw_buffer",
            parent_event_ids=parents, payload_reference=raw.object_id,
        )

    def _record(self, **overrides):
        values = dict(
            prepared=self.prepared, delivery=self.delivery, bundle=self.bundle,
            log=self.log, objects=self.objects,
            expected_model_artifact_sha256=self.artifact,
            occurred_at="2026-09-29T12:04:00Z",
            expected_revision=len(self.log.replay()) - 1,
            value_resolver=self.values,
        )
        values.update(overrides)
        return self.candidates.record(**values)

    def _read(self, **overrides):
        values = dict(
            bundle_id=self.bundle.bundle_id, log=self.log, objects=self.objects,
            source_store=self.prepared.store,
        )
        values.update(overrides)
        return self.candidates.read_candidate(**values)

    def _restart_store(self, objects):
        registry = self._registry(objects=objects)
        return RegisteredFormationStore(
            scope=self.scope, authority_namespace_id=self.namespace,
            registry=registry,
            custody=RegisteredEncryptedFormationCustody(registry=registry, objects=objects),
            permits=lambda *_: self.permitted[0],
        )

    def test_restart_recovers_bundle_values_and_lineage_without_raw_reference_map(self):
        recorded = self._record()
        restarted_objects = EncryptedObjectPlane(
            scope=self.scope, key=b"c" * 32,
            backend=LocalObjectBackend(self.backend.root),
        )
        recovered = self._candidates().read_candidate(
            self.bundle.bundle_id, log=self.log, objects=restarted_objects,
            source_store=self._restart_store(restarted_objects),
        )
        self.assertEqual(recovered.bundle, self.bundle)
        self.assertEqual(recovered.packet, self.prepared.assembled.packet)
        self.assertEqual(recovered.recorded, recorded)
        self.assertEqual(recorded.bundle_sha256, self.bundle.content_digest())
        self.assertEqual(dict(recovered.values), {
            "candidate-value-one": self.value_one, "candidate-value-two": self.value_two,
        })
        self.assertEqual(canonical_json_bytes(recovered.delivery_record),
                         canonical_json_bytes(self.prepared.receipt_record()))
        self.assertIn(self.delivery.event.event_id, recorded.event.parent_event_ids)
        resolution_pass = [
            (self.scope, self.namespace, "candidate-value-one"),
            (self.scope, self.namespace, "candidate-value-two"),
        ]
        self.assertEqual(self.values.calls, resolution_pass * 2)
        sql_metadata = json.dumps(list(self.connection.rows.values()))
        for secret in ("fictional source secret", "fictional candidate value secret"):
            self.assertNotIn(secret, sql_metadata)
        self.assertFalse(any("claim" in table or "state" in table
                             for table, _ in self.connection.rows))

    def test_idempotent_record_and_retry_after_append_before_index_failure(self):
        revision = len(self.log.replay()) - 1
        before = len(self.log.append_calls)
        self.connection.fail_next_insert = True
        with self.assertRaisesRegex(RuntimeError, "injected candidate index failure"):
            self._record(expected_revision=revision)
        self.assertEqual(len(self.log.append_calls), before + 1)
        appended = self.log.replay()[-1]
        self.candidates = self._candidates()
        with self.assertRaises(ValueError):
            self._record(expected_revision=revision, occurred_at="2026-09-29T12:05:00Z")
        self.assertEqual(len(self.log.append_calls), before + 1)
        recorded = self._record(expected_revision=revision)
        self.assertEqual(recorded.event, appended)
        self.assertEqual(len(self.log.append_calls), before + 1)
        self.assertEqual(self._record(expected_revision=revision), recorded)
        self.assertEqual(len(self.log.append_calls), before + 1)
        with self.assertRaises(ValueError):
            self._record(expected_revision=revision, occurred_at="2026-09-29T12:05:00Z")
        self.assertEqual(len(self.log.append_calls), before + 1)
        self.assertEqual(self._read().recorded, recorded)

    def test_artifact_context_and_every_value_ref_are_independently_required(self):
        mutations = (
            {"expected_model_artifact_sha256": "b" * 64},
            {"bundle": replace(self.bundle, context_digest="b" * 64)},
            {"bundle": replace(self.bundle, experience_refs=("invented-experience",))},
            {"value_resolver": _Values(self.scope, self.namespace, {
                "candidate-value-one": self.value_one})},
            {"value_resolver": _Values(self.scope, "foreign-authority", self.values.values)},
            {"value_resolver": _Values(self.scope, self.namespace, {
                "candidate-value-one": self.value_one,
                "candidate-value-two": replace(self.value_two, value_sha256="b" * 64)})},
        )
        before = len(self.log.append_calls)
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                with self.assertRaises(ValueError):
                    self._record(**mutation)
                self.assertEqual(len(self.log.append_calls), before)
        with self.assertRaises(TypeError):
            self._record(value_resolver=None)
        self.assertEqual(len(self.log.append_calls), before)

    def test_revision_and_immutable_bundle_reuse_fail_before_append(self):
        before = len(self.log.append_calls)
        for revision in (True, -2, 1.5, 1):
            with self.subTest(revision=revision):
                with self.assertRaises(ValueError):
                    self._record(expected_revision=revision)
                self.assertEqual(len(self.log.append_calls), before)
        self._record()
        before = len(self.log.append_calls)
        changed_values = _Values(self.scope, self.namespace, {
            **self.values.values,
            "candidate-value-one": CanonicalTaggedValue.create(
                type_tag="text", value="different fictional candidate value"),
        })
        with self.assertRaises(ValueError):
            self._record(value_resolver=changed_values)
        self.assertEqual(len(self.log.append_calls), before)

    def test_delivery_must_be_present_exact_and_bound_to_prepared_receipt(self):
        missing_log = _RecordedLog(self.scope)
        missing_log.entries = self.log.entries[:-1]
        with self.assertRaises(ValueError):
            self._record(log=missing_log, expected_revision=1)
        unrelated = self.objects.put(b"fictional non-receipt delivery")
        with self.assertRaises(ValueError):
            self._record(delivery=RecordedEvent(self.delivery.event, unrelated))
        bad_event = ExperienceEvent.create(
            event_type="formation_context_delivery", scope=self.scope,
            occurred_at=self.delivery.event.occurred_at,
            content_digest=unrelated.plaintext_sha256,
            provenance=self.delivery.event.provenance,
            retention_class="ordinary_experience", storage_tier="raw_buffer",
            parent_event_ids=self.delivery.event.parent_event_ids,
            payload_reference=unrelated.object_id,
        )
        self.log.append(bad_event, expected_revision=2)
        with self.assertRaises(ValueError):
            self._record(delivery=RecordedEvent(bad_event, unrelated))
        with self.assertRaises(ValueError):
            self._record(occurred_at="2026-09-29T12:02:00Z")

    def test_current_policy_is_rechecked_for_record_and_read(self):
        self.permitted[0] = False
        with self.assertRaises(ValueError):
            self._record()
        self.permitted[0] = True
        self._record()
        self.permitted[0] = False
        with self.assertRaises(ValueError):
            self._read()

    def test_delivery_purpose_and_historical_cutoff_remain_bound(self):
        self._record()
        other_purpose = RegisteredFormationStore(
            scope=self.scope, authority_namespace_id=self.namespace,
            registry=self.registry, custody=self.prepared.store.custody,
            permits=lambda *_: True, purpose="other-purpose",
        )
        with self.assertRaises(ValueError):
            self._read(source_store=other_purpose)
        before = len(self.log.append_calls)
        for cutoff in ("2026-09-29T12:00:00.000000Z", "2026-09-29T12:05:00.000000Z"):
            with self.subTest(cutoff=cutoff):
                prepared = replace(self.prepared, request=replace(
                    self.prepared.request, as_of=cutoff))
                # Use a real, replayed receipt so rejection must check cutoff
                # semantics rather than merely detect a mismatching raw object.
                delivery = record_selected_formation_delivery(
                    prepared=prepared, log=self.log, objects=self.objects,
                    occurred_at="2026-09-29T12:03:00Z",
                    expected_revision=len(self.log.replay()) - 1,
                    request_id=f"fictional-cutoff-{len(self.log.replay())}",
                )
                before += 1
                bundle = replace(self.bundle, bundle_id=f"cutoff-bundle-{len(self.log.replay())}")
                with self.assertRaises(ValueError):
                    self._record(prepared=prepared, delivery=delivery, bundle=bundle)
                self.assertEqual(len(self.log.append_calls), before)

    def test_revocation_of_one_source_while_another_is_read_rejects_whole_operation(self):
        packet = self.prepared.assembled.packet
        first_ref, second_ref = packet.evidence
        allowed = {first_ref.ref_id: True, second_ref.ref_id: True}
        self.prepared.store.permits = lambda source, _: allowed[source.evidence.ref_id]
        original = self.prepared.store.custody

        class RevokingCustody:
            def read(inner, scope, object_ref):
                content = original.read(scope, object_ref)
                if object_ref == self.second_raw.object_id:
                    allowed[first_ref.ref_id] = False
                return content

        self.prepared.store.custody = RevokingCustody()
        before = len(self.log.append_calls)
        with self.assertRaises(ValueError):
            self._record()
        self.assertEqual(len(self.log.append_calls), before)
        allowed[first_ref.ref_id] = True
        self.prepared.store.custody = original
        self._record()
        self.prepared.store.custody = RevokingCustody()
        with self.assertRaises(ValueError):
            self._read()

    def test_current_source_bytes_are_reopened_after_delivery_and_on_recovery(self):
        original_custody = self.prepared.store.custody

        class ChangedCustody:
            def read(inner, scope, object_ref):
                return b"changed fictional source bytes"

        self.prepared.store.custody = ChangedCustody()
        with self.assertRaises(ValueError):
            self._record()
        self.prepared.store.custody = original_custody
        self._record()
        self.prepared.store.custody = ChangedCustody()
        with self.assertRaises(ValueError):
            self._read()

    def test_candidate_metadata_and_ciphertext_tamper_fail_closed(self):
        before = set(self.connection.rows)
        recorded = self._record()
        candidate_keys = set(self.connection.rows) - before
        self.assertEqual(len(candidate_keys), 1)
        row = self.connection.rows[candidate_keys.pop()]
        original = row["record_json"]
        metadata = json.loads(original)
        metadata["authority_namespace_id"] = "changed-authority"
        row["record_json"] = json.dumps(metadata)
        with self.assertRaises(ValueError):
            self._read()
        row["record_json"] = original
        path = self.backend._path(self.objects.namespace, recorded.raw.object_id)
        sealed = bytearray(path.read_bytes())
        sealed[-1] ^= 1
        path.write_bytes(sealed)
        with self.assertRaises((ValueError, InvalidTag)):
            self._read()

    def test_source_registry_change_and_source_ciphertext_tamper_fail_closed(self):
        self._record()
        source_id = self.prepared.assembled.packet.experience_refs[0]
        row = self.connection.rows[("flora_registered_formation_sources",
                                    self.registry._key("source", source_id))]
        original = row["record_json"]
        metadata = json.loads(original)
        metadata["evidence"]["speaker_ref"] = "changed-speaker"
        row["record_json"] = json.dumps(metadata)
        with self.assertRaises(ValueError):
            self._read()
        row["record_json"] = original
        path = self.backend._path(self.objects.namespace, self.second_raw.object_id)
        sealed = bytearray(path.read_bytes())
        sealed[-1] ^= 1
        path.write_bytes(sealed)
        with self.assertRaises((ValueError, InvalidTag)):
            self._read()

    def test_scope_and_authority_isolation(self):
        other_scope = ProductHostScope.create(
            product_id="friday", host_instance_id="other-fictional-host",
            schema_version="1.0.0", encryption_domain="other-fictional-key")
        for bundle in (
            replace(self.bundle, scope=other_scope),
            replace(self.bundle, authority_namespace_id="foreign-authority"),
        ):
            with self.subTest(bundle=bundle):
                with self.assertRaises(ValueError):
                    self._record(bundle=bundle)
        other_objects = EncryptedObjectPlane(
            scope=other_scope, key=b"o" * 32, backend=self.backend)
        with self.assertRaises(ValueError):
            self._record(objects=other_objects)
        self._record()
        with self.assertRaises(ValueError):
            self._read(objects=other_objects)
        with self.assertRaises(KeyError):
            self._candidates(namespace="foreign-authority").read_candidate(
                self.bundle.bundle_id, log=self.log, objects=self.objects,
                source_store=self.prepared.store)
        with self.assertRaises(ValueError):
            self._candidates(scope=other_scope).read_candidate(
                self.bundle.bundle_id, log=self.log, objects=self.objects,
                source_store=self.prepared.store)


if __name__ == "__main__":
    unittest.main()
