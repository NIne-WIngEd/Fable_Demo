"""Fictional registry/SQL contracts with real local encryption; no model result."""
import base64
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
import json
import inspect
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cognitive_kernel.canonical import canonical_sha256, normalize_timestamp
from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from cognitive_kernel.formation_contracts import FormationEvidenceRef
from cognitive_kernel.formation_sources import RegisteredFormationSource
from flora.comparator import encoded, sha
from flora.selected.experience import CommittedExperience
from flora.selected.object_store import EncryptedObjectPlane, LocalObjectBackend
from flora.selected.experiment_manifests import (
    CohortEntry, RegisteredPart1Material, RegisteredPart1MaterialReader, SelectedSourceAuthority,
    SplitIsolationRule, XTDBExperimentManifestCustody,
    cohort_source_purpose, manifest_purpose, validate_cohort,
)


class FixtureLog:
    def __init__(self, scope):
        self.scope, self.events = scope, []
    def replay(self):
        return tuple(self.events)
    def replay_committed(self):
        return tuple(CommittedExperience(event, index, datetime(2026, 9, 29, tzinfo=timezone.utc))
            for index, event in enumerate(self.events))
    def append(self, event, *, expected_revision):
        if expected_revision != len(self.events) - 1:
            raise ValueError("fictional stale revision")
        self.events.append(event)


class FixtureRegistry:
    def __init__(self, scope, namespace, objects):
        self.scope, self.authority_namespace_id, self.objects = scope, namespace, objects
        self.sources, self.raws = {}, {}
    def lookup(self, event_id):
        return self.sources.get(event_id)
    def raw_reference(self, object_id):
        return self.raws.get(object_id)
    def raw_metadata(self, object_id):
        raw = self.raws.get(object_id)
        if raw is None:
            return None
        cipher = self.objects.backend.get_object(self.objects.namespace, object_id)
        return {"object_namespace": self.objects.namespace, "ciphertext_size": len(cipher), "ciphertext_sha256": sha(cipher)}
    def register(self, event, raw, role):
        evidence = FormationEvidenceRef(ref_id=event.event_id, scope=self.scope, authority_namespace_id=self.authority_namespace_id,
            content_digest=event.content_digest, role=role, modality="structured", subject_ref=None, speaker_ref=None,
            source_item_ref=None, duplicate_group_ref=None, observed_at=event.occurred_at,
            recorded_at=normalize_timestamp("2026-09-29T00:00:00Z"), parent_refs=event.parent_event_ids)
        source = RegisteredFormationSource.create(evidence=evidence, object_ref=raw.object_id)
        self.sources[event.event_id], self.raws[raw.object_id] = source, raw
        return source


class FixturePermissions:
    def __init__(self, registry):
        self.scope, self.authority_namespace_id, self.registry = registry.scope, registry.authority_namespace_id, registry
        self.allowed = set()
    def permits(self, source, purpose):
        if source is None:
            return False
        pending, seen = [source.evidence.ref_id], set()
        while pending:
            event_id = pending.pop()
            if event_id in seen:
                continue
            registered = self.registry.lookup(event_id)
            if registered is None or (event_id, purpose) not in self.allowed:
                return False
            pending.extend(registered.evidence.parent_refs)
            seen.add(event_id)
        return True


class FixtureConnection:
    """Shape-only row port; physical XTDB transactions are separately tested."""
    def __init__(self):
        self.records = {}
    def execute(self, query, params):
        if query.startswith("SELECT"):
            row = self.records.get(params[0])
            columns = () if row is None else tuple(row)
            return SimpleNamespace(description=[SimpleNamespace(name=name) for name in columns],
                fetchall=lambda: [] if row is None else [tuple(row[name] for name in columns)])
        if query.startswith("ASSERT"):
            if params[0] in self.records:
                raise ValueError("fictional immutable row conflict")
            return None
        if query.startswith("INSERT"):
            self.records[params[0]] = dict(zip(("_id", "scope_digest", "record_sha256", "record_json"), params))
            return None
        raise AssertionError("unrecognized fixture SQL boundary")
    @contextmanager
    def transaction(self):
        yield


def public(key):
    return key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


class ExperimentManifestContractsTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.keys = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
        self.authorities, self.events = [], []
        for index in range(2):
            scope = ProductHostScope.create(product_id="friday", host_instance_id="fictional-host-" + str(index),
                schema_version="1.0.0", encryption_domain="key-" + str(index))
            objects = EncryptedObjectPlane(scope=scope, key=bytes([80 + index]) * 32,
                backend=LocalObjectBackend(Path(self.directory.name) / str(index)))
            registry, log = FixtureRegistry(scope, "fictional-authority-" + str(index), objects), FixtureLog(scope)
            permissions = FixturePermissions(registry)
            authority = SelectedSourceAuthority(registry, log, permissions, objects)
            raw = objects.put(("Fictional source " + str(index)).encode())
            event = ExperienceEvent.create(event_type="observation", scope=scope, occurred_at="2020-01-01T00:00:00Z",
                content_digest=raw.plaintext_sha256, provenance=ProvenanceReference.create(provenance_type="generated_reconstruction",
                    source_reference_ids=("fictional-source-" + str(index),), derivation_activity_id="manifest-fixture",
                    responsible_component="synthetic-test"), retention_class="ordinary_experience", storage_tier="raw_buffer",
                payload_reference=raw.object_id)
            log.append(event, expected_revision=-1)
            registry.register(event, raw, "generated_reconstruction")
            for purpose in (manifest_purpose("exp", "capture"), manifest_purpose("exp", "read"),
                            manifest_purpose("exp", "qualification"), *(cohort_source_purpose("exp", split)
                            for split in ("training", "pilot", "heldout", "transfer"))):
                permissions.allowed.add((event.event_id, purpose))
            self.authorities.append(authority)
            self.events.append(event)
        self.connection = FixtureConnection()
        configure = patch("flora.selected.experiment_manifests.configure_xtdb_connection")
        configure.start()
        self.addCleanup(configure.stop)
        registration = patch("flora.selected.experiment_manifests.register_experience_source", self.register_source)
        registration.start()
        self.addCleanup(registration.stop)
        self.store = self.make_store()
        self.entries = tuple(CohortEntry("entry-" + str(index), authority.authority_id, self.events[index].event_id,
            "training" if index == 0 else "heldout", "family-" + str(index), "common-generator", "a" * 64,
            "scenario-" + str(index), (), "person-" + str(index), "host", "authorized_history")
            for index, authority in enumerate(self.authorities))
        self.rules = (SplitIsolationRule("heldout", "training",
            tuple(sorted({"source_family", "scenario_ancestry", "person_family", "source_ancestry"})), ("generator_family",)),)

    def register_source(self, *, event_id, raw, registry, log, objects, role, **kwargs):
        event = next(event for event in log.replay() if event.event_id == event_id)
        self.assertEqual(objects.get(raw), registry.objects.get(raw))
        return registry.register(event, raw, role)

    def make_store(self, validator=None, reader=None):
        return XTDBExperimentManifestCustody(experiment_id="exp", local=self.authorities[0],
            authorities=tuple(self.authorities), connection=self.connection, control_anchor_event_id=self.events[0].event_id,
            lineage_public_key=public(self.keys[0]), approved_lineage_key_sha256=sha(public(self.keys[0])),
            qualification_public_key=public(self.keys[1]), approved_qualification_key_sha256=sha(public(self.keys[1])),
            part1_validator=validator, part1_material_reader=reader, clock=lambda: "2026-09-30T00:00:00Z")

    def grant_read(self, record):
        self.authorities[0].permissions.allowed.add((record["event_id"], manifest_purpose("exp", "read")))

    def cohort_claim(self, entries=None):
        entries = self.entries if entries is None else entries
        cohort = {"entries": [entry.record() for entry in entries], "rules": [rule.record() for rule in self.rules],
            "bindings": {entry.entry_id: self.store.authorities[entry.authority_id].binding(entry.event_id) for entry in entries}}
        return {"schema": "flora-cohort-lineage-attestation-v1", "experiment_id": "exp",
            "enrolled_key_sha256": sha(public(self.keys[0])), "actual_family_ancestry_verified": True,
            "cohort_sha256": canonical_sha256(cohort)}

    def prepared_cohort(self, qualified=False):
        claim = self.cohort_claim() if qualified else None
        record = self.store.register_cohort(cohort_id="cohort", entries=self.entries, rules=self.rules,
            lineage_claim=claim, lineage_proof=None if claim is None else self.keys[0].sign(encoded(claim)))
        self.grant_read(record)
        return record

    def prepared_recipe(self):
        self.prepared_cohort()
        record = self.store.register_recipe(recipe_id="recipe", cohort_id="cohort",
            code_files=(("src/flora/selected/example.py", b"# supplied fixture code, not a builder\n"),),
            dependency_lock=b"supplied fixture lock", role_contracts=(("personality", b"supplied interface only"),),
            source_choices=(("entry-0", "eligible"), ("entry-1", "stop")), stop_defer_contract=b"explicit supplied stop/defer policy")
        self.grant_read(record)
        return record

    def test_cohort_shape_does_not_qualify_and_private_foreign_ids_are_not_local_parents(self):
        record = self.prepared_cohort()
        cohort = self.store.recover(kind="cohort", manifest_id="cohort")
        self.assertEqual(cohort["status"], "shape_only")
        self.assertNotIn(self.events[1].event_id, record["parent_event_ids"])
        self.assertIn(self.events[0].event_id, record["parent_event_ids"])
        self.assertNotIn("common-generator", self.connection.records[next(iter(self.connection.records))]["record_json"])

    def test_renamed_host_cannot_hide_shared_declared_disjoint_source_or_person_family(self):
        for field in ("source_family", "person_family", "scenario_root"):
            changed = (self.entries[0], replace(self.entries[1], **{field: getattr(self.entries[0], field)}))
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "leaks declared-disjoint"):
                self.store.register_cohort(cohort_id="leak", entries=changed, rules=self.rules)

    def test_every_present_split_pair_needs_complete_frozen_shared_vs_disjoint_policy(self):
        with self.assertRaisesRegex(ValueError, "frozen rule"):
            self.store.register_cohort(cohort_id="missing", entries=self.entries, rules=())
        bad = SplitIsolationRule("heldout", "training", ("source_family",), ())
        with self.assertRaisesRegex(ValueError, "partition"):
            bad.record()

    def test_independent_actual_lineage_signature_needed_and_receipt_cannot_move_to_changed_cohort(self):
        claim = self.cohort_claim()
        with self.assertRaises(InvalidSignature):
            self.store.register_cohort(cohort_id="wrong-key", entries=self.entries, rules=self.rules,
                lineage_claim=claim, lineage_proof=self.keys[1].sign(encoded(claim)))
        with self.assertRaisesRegex(ValueError, "exact cohort"):
            self.store.register_cohort(cohort_id="changed", entries=(replace(self.entries[0], person_role="different"), self.entries[1]),
                rules=self.rules, lineage_claim=claim, lineage_proof=self.keys[0].sign(encoded(claim)))
        self.prepared_cohort(qualified=True)
        self.assertEqual(self.store.recover(kind="cohort", manifest_id="cohort")["status"], "lineage_qualified")

    def test_same_manifest_id_is_immutable_across_semantic_body_changes(self):
        first = self.prepared_cohort()
        self.assertEqual(self.store.register_cohort(cohort_id="cohort", entries=self.entries, rules=self.rules), first)
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.store.register_cohort(cohort_id="cohort", entries=(replace(self.entries[0], usage_role="different"), self.entries[1]), rules=self.rules)

    def test_current_foreign_source_permission_denies_before_private_manifest_decrypt(self):
        self.prepared_cohort()
        authority = self.authorities[1]
        authority.permissions.allowed.remove((self.events[1].event_id, cohort_source_purpose("exp", "heldout")))
        with patch.object(self.authorities[0].objects, "get", side_effect=AssertionError("must not decrypt")) as reader:
            with self.assertRaises(PermissionError):
                self.store.recover(kind="cohort", manifest_id="cohort")
            reader.assert_not_called()

    def test_source_permission_withdrawal_during_cipher_fetch_cannot_return_manifest(self):
        record = self.prepared_cohort()
        local, foreign = self.authorities
        original = local.objects.backend.get_object
        def withdraw(namespace, object_id):
            value = original(namespace, object_id)
            if object_id == record["object_id"] and any(frame.function == "get" and frame.filename.endswith("object_store.py") for frame in inspect.stack()):
                foreign.permissions.allowed.discard((self.events[1].event_id, cohort_source_purpose("exp", "heldout")))
            return value
        with patch.object(local.objects.backend, "get_object", side_effect=withdraw), \
                patch.object(AESGCM, "decrypt", side_effect=AssertionError("withdrawn ciphertext must remain sealed")) as decrypt:
            with self.assertRaises(PermissionError):
                self.store.recover(kind="cohort", manifest_id="cohort")
            decrypt.assert_not_called()

    def test_restored_instance_bound_codec_cannot_bypass_copied_cipher_fence(self):
        # Restoring an instrumentation patch as a bound INSTANCE method leaves
        # __self__ on the original plane. A shallow copy must never trust it.
        record = self.prepared_cohort()
        local, foreign = self.authorities
        local.objects.get = local.objects.get
        local.objects.recover_reference = local.objects.recover_reference
        original = local.objects.backend.get_object
        def withdraw(namespace, object_id):
            value = original(namespace, object_id)
            if object_id == record["object_id"] and any(frame.function == "get" and frame.filename.endswith("object_store.py") for frame in inspect.stack()):
                foreign.permissions.allowed.discard((self.events[1].event_id, cohort_source_purpose("exp", "heldout")))
            return value
        with patch.object(local.objects.backend, "get_object", side_effect=withdraw), \
                patch.object(AESGCM, "decrypt", side_effect=AssertionError("withdrawn manifest reached AEAD")) as decrypt:
            with self.assertRaises(PermissionError):
                self.store.recover(kind="cohort", manifest_id="cohort")
            decrypt.assert_not_called()

    def test_original_source_reader_checks_current_authority_before_and_after_actual_decrypt(self):
        authority = self.authorities[1]
        gate = self.store._gate(authority.authority_id, self.events[1].event_id, cohort_source_purpose("exp", "heldout"))
        self.assertEqual(authority.read(gate), b"Fictional source 1")
        original = authority.objects.backend.get_object
        def withdraw(namespace, object_id):
            value = original(namespace, object_id)
            if any(frame.function == "get" and frame.filename.endswith("object_store.py") for frame in inspect.stack()):
                authority.permissions.allowed.remove((self.events[1].event_id, gate["purpose"]))
            return value
        with patch.object(authority.objects.backend, "get_object", side_effect=withdraw):
            with self.assertRaises(PermissionError):
                authority.read(gate)

    def test_generic_source_reader_cannot_open_private_manifest_or_other_internal_material(self):
        record = self.prepared_cohort()
        local, foreign = self.authorities
        purpose = manifest_purpose("exp", "qualification")
        local.permissions.allowed.add((record["event_id"], purpose))
        gate = self.store._gate(local.authority_id, record["event_id"], purpose, original=False)
        foreign.permissions.allowed.remove((self.events[1].event_id, cohort_source_purpose("exp", "heldout")))
        with patch.object(AESGCM, "decrypt", side_effect=AssertionError("no private plaintext")) as decrypt:
            with self.assertRaisesRegex(PermissionError, "dedicated typed"):
                local.read(gate)
            decrypt.assert_not_called()
        for event_type in ("comparison_artifact", "provider_attempt_artifact", "phase_snapshot_artifact"):
            event = self.append_material(b"private " + event_type.encode(), event_type=event_type)
            gate = self.store._gate(local.authority_id, event.event_id, purpose, original=False)
            with self.subTest(event_type=event_type), self.assertRaisesRegex(PermissionError, "dedicated typed"):
                local.read(gate)

    def test_dependency_check_withdrawal_stops_canonical_append(self):
        record = self.prepared_cohort()
        local, foreign = self.authorities
        permits = local.permissions.permits
        armed = {"value": False}
        def clock():
            armed["value"] = True
            return "2026-09-30T00:00:00Z"
        def withdraw(source, purpose):
            result = permits(source, purpose)
            if armed["value"] and source.evidence.ref_id == record["event_id"] and purpose == manifest_purpose("exp", "read"):
                armed["value"] = False
                foreign.permissions.allowed.remove((self.events[1].event_id, cohort_source_purpose("exp", "heldout")))
            return result
        self.store.clock = clock
        before = len(local.log.events)
        with patch.object(local.permissions, "permits", side_effect=withdraw), self.assertRaises(PermissionError):
            self.store.register_recipe(recipe_id="withdrawn", cohort_id="cohort", code_files=(("a.py", b"code"),),
                dependency_lock=b"lock", role_contracts=(("mfm", b"interface"),), source_choices=(("entry-0", "eligible"),),
                stop_defer_contract=b"stop")
        self.assertEqual(len(local.log.events), before)

    def test_recipe_binds_actual_bytes_and_cannot_mark_heldout_as_training_eligible(self):
        record = self.prepared_recipe()
        recipe = self.store.recover(kind="recipe", manifest_id="recipe")
        self.assertEqual(base64.b64decode(recipe["code_files"][0][1]["base64"]), b"# supplied fixture code, not a builder\n")
        with self.assertRaises(PermissionError):
            self.store.register_recipe(recipe_id="leak", cohort_id="cohort", code_files=(("a.py", b"code"),),
                dependency_lock=b"lock", role_contracts=(("mfm", b"contract"),), source_choices=(("entry-1", "eligible"),), stop_defer_contract=b"stop")

    def test_linked_case_needs_split_exact_input_target_outcome_and_is_never_auto_gold(self):
        self.prepared_recipe()
        with self.assertRaisesRegex(ValueError, "target and outcome"):
            self.store.register_linked_case(case_id="missing", recipe_id="recipe", split="training", input_entry_ids=("entry-0",),
                proposal=b"supplied proposal", resolution="accepted")
        with self.assertRaises(ValueError):
            self.store.register_linked_case(case_id="split-leak", recipe_id="recipe", split="training", input_entry_ids=("entry-1",),
                proposal=b"supplied proposal", resolution="unresolved")
        record = self.store.register_linked_case(case_id="defer", recipe_id="recipe", split="training", input_entry_ids=("entry-0",),
            proposal=b"supplied defer operation", resolution="deferred")
        self.grant_read(record)
        case = self.store.recover(kind="linked_case", manifest_id="defer")
        self.assertFalse(case["training_eligible"])
        self.assertFalse(case["evaluation_eligible"])
        self.assertEqual(case["status"], "shape_only")

    def test_part1_cannot_become_qualified_with_bare_digest_or_unsigned_result(self):
        self.prepared_cohort(qualified=True)
        recipe = self.store.register_recipe(recipe_id="recipe", cohort_id="cohort", code_files=(("a.py", b"code"),),
            dependency_lock=b"lock", role_contracts=(("mfm", b"interface only"),), source_choices=(("entry-0", "eligible"),), stop_defer_contract=b"stop")
        self.grant_read(recipe)
        with self.assertRaises((PermissionError, InvalidSignature)):
            self.store.register_part1_qualification(qualification_id="false", cohort_id="cohort", recipe_id="recipe",
                claim={"cohort_sha256": self.store.metadata("cohort", "cohort")["content_sha256"],
                       "recipe_sha256": recipe["content_sha256"]}, proof=b"not-a-proof")

    def test_source_controls_cannot_become_original_dataset_history(self):
        record = self.prepared_cohort()
        with self.assertRaisesRegex(ValueError, "original evidence"):
            self.authorities[0].binding(record["event_id"])


    def append_material(self, content, event_type="comparison_artifact", authority_index=0):
        authority = self.authorities[authority_index]
        raw = authority.objects.put(content)
        event = ExperienceEvent.create(event_type=event_type, scope=authority.registry.scope,
            occurred_at="2026-09-30T00:00:00Z", content_digest=raw.plaintext_sha256,
            provenance=ProvenanceReference.create(provenance_type="derived_inference" if event_type == "comparison_artifact" else "generated_reconstruction",
                source_reference_ids=("fictional-material",), derivation_activity_id="fixture-material-" + str(len(authority.log.events)),
                responsible_component="synthetic-test"), retention_class="ordinary_experience", storage_tier="raw_buffer",
            payload_reference=raw.object_id)
        authority.log.append(event, expected_revision=len(authority.log.events) - 1)
        authority.registry.register(event, raw, "derived_inference" if event_type == "comparison_artifact" else "generated_reconstruction")
        for purpose in (manifest_purpose("exp", "capture"), manifest_purpose("exp", "read"), manifest_purpose("exp", "qualification"),
                        *(cohort_source_purpose("exp", split) for split in ("training", "pilot", "heldout", "transfer"))):
            authority.permissions.allowed.add((event.event_id, purpose))
        return event

    def actual_fixture_part1(self, validator_result=True, withdraw=False):
        """Actual bytes/signatures, fictional qualification port; no empirical result."""
        self.prepared_cohort(qualified=True)
        choices = tuple((entry.entry_id, "eligible" if entry.split == "training" else "stop") for entry in self.entries)
        recipe = self.store.register_recipe(recipe_id="recipe", cohort_id="cohort", code_files=(("a.py", b"fixture code"),),
            dependency_lock=b"fixture lock", role_contracts=(("mfm", b"fixture interface"),),
            source_choices=choices, stop_defer_contract=b"fixture stop")
        self.grant_read(recipe)
        names = ("sealed_assessment", "assessment_spec", "result", "rubric", "thresholds", "native_artifacts", "phase_snapshots")
        expected, gates = {}, {}
        for name in names:
            content = encoded({"schema": "fictional-qualification-material", "role": name, "not_a_model_result": True})
            event = self.append_material(content, event_type="observation")
            expected[name] = content
            gates[name] = self.store._gate(self.authorities[0].authority_id, event.event_id,
                manifest_purpose("exp", "qualification"), original=False)
        authority = self.authorities[0]
        class FixtureValidator:
            artifact_sha256 = "d" * 64
            def verify(self, *, claim, materials):
                if withdraw:
                    authority.permissions.allowed.discard((gates["result"]["event_id"], gates["result"]["purpose"]))
                return validator_result and materials == expected
        self.store = self.make_store(FixtureValidator())
        claim = {"schema": "flora-part1-result-qualification-v1", "experiment_id": "exp",
            "cohort_sha256": self.store.metadata("cohort", "cohort")["content_sha256"], "recipe_sha256": recipe["content_sha256"],
            "protocol_sha256": "b" * 64, "plan_sha256": "c" * 64, "enrolled_key_sha256": sha(public(self.keys[1])),
            "validator_artifact_sha256": "d" * 64, "material_reader_artifact_sha256": None, "material_routes_sha256": None,
            "accepted": True, "failure_inclusive": True, "materials": gates}
        return claim, self.keys[1].sign(encoded(claim)), gates

    def test_recomputed_xtdb_checksum_cannot_remove_guard_bound_foreign_sources(self):
        self.prepared_cohort()
        key = self.store._id("cohort", "cohort")
        body = json.loads(self.connection.records[key]["record_json"])
        body["source_gates"] = [gate for gate in body["source_gates"] if gate["authority_id"] == self.authorities[0].authority_id]
        body["record_sha256"] = canonical_sha256({k: v for k, v in body.items() if k != "record_sha256"})
        self.connection.records[key]["record_sha256"] = body["record_sha256"]
        self.connection.records[key]["record_json"] = json.dumps(body)
        with patch.object(self.authorities[0].objects, "get", side_effect=AssertionError("must not decrypt")) as reader:
            with self.assertRaisesRegex(ValueError, "exact Kurrent"):
                self.store.recover(kind="cohort", manifest_id="cohort")
            reader.assert_not_called()

    def test_copied_bytes_under_distinct_host_and_source_labels_still_leak_source_ancestry(self):
        event = self.append_material(b"Fictional source 0", event_type="observation", authority_index=1)
        copied = replace(self.entries[1], event_id=event.event_id)
        with self.assertRaisesRegex(ValueError, "source_ancestry"):
            self.store.register_cohort(cohort_id="copied", entries=(self.entries[0], copied), rules=self.rules)

    def test_signed_part1_reads_actual_material_and_requires_independent_validator(self):
        claim, proof, gates = self.actual_fixture_part1()
        with self.assertRaises(PermissionError):
            self.make_store().register_part1_qualification(qualification_id="missing", cohort_id="cohort", recipe_id="recipe", claim=claim, proof=proof)
        record = self.store.register_part1_qualification(qualification_id="part1", cohort_id="cohort", recipe_id="recipe", claim=claim, proof=proof)
        self.grant_read(record)
        self.assertEqual(self.store.recover(kind="part1", manifest_id="part1")["status"], "independently_qualified_part1")
        self.authorities[0].permissions.allowed.remove((gates["result"]["event_id"], gates["result"]["purpose"]))
        with patch.object(self.authorities[0].objects, "get", side_effect=AssertionError("no private read")) as reader:
            with self.assertRaises(PermissionError):
                self.store.recover(kind="part1", manifest_id="part1")
            reader.assert_not_called()

    def test_slow_part1_validator_cannot_qualify_after_source_withdrawal(self):
        claim, proof, _ = self.actual_fixture_part1(withdraw=True)
        with self.assertRaises(PermissionError):
            self.store.register_part1_qualification(qualification_id="withdrawn", cohort_id="cohort", recipe_id="recipe", claim=claim, proof=proof)
        self.assertIsNone(self.store.metadata("part1", "withdrawn"))

    def test_transfer_inputs_never_claim_execution_or_auto_builder_export(self):
        self.entries, self.rules = (self.entries[0],), ()
        claim, proof, _ = self.actual_fixture_part1()
        result = self.store.register_part1_qualification(qualification_id="part1", cohort_id="cohort", recipe_id="recipe", claim=claim, proof=proof)
        self.grant_read(result)
        entry = CohortEntry("transfer-entry", self.authorities[1].authority_id, self.events[1].event_id, "transfer",
            "separate-family", "common-generator", "a" * 64, "separate-scenario", (), "separate-person", "host", "authorized_history")
        cohort = {"entries": [entry.record()], "rules": [], "bindings": {entry.entry_id: self.authorities[1].binding(entry.event_id)}}
        lineage = {"schema": "flora-cohort-lineage-attestation-v1", "experiment_id": "exp",
            "enrolled_key_sha256": sha(public(self.keys[0])), "actual_family_ancestry_verified": True, "cohort_sha256": canonical_sha256(cohort)}
        transfer = self.store.register_cohort(cohort_id="transfer", entries=(entry,), rules=(), lineage_claim=lineage,
            lineage_proof=self.keys[0].sign(encoded(lineage)))
        self.grant_read(transfer)
        rules = (SplitIsolationRule("training", "transfer",
            tuple(sorted({"source_family", "scenario_ancestry", "person_family", "source_ancestry"})), ("generator_family",)),)
        ready = self.store.register_transfer_readiness(readiness_id="prepared", qualification_id="part1", transfer_cohort_id="transfer", transfer_rules=rules)
        self.grant_read(ready)
        payload = self.store.recover(kind="transfer", manifest_id="prepared")
        self.assertFalse(payload["execution_ready"])
        self.assertEqual(payload["status"], "transfer_policy_prepared_unqualified")
        with self.assertRaisesRegex(ValueError, "no bare"):
            self.store.register_transfer_readiness(readiness_id="fake-export", qualification_id="part1", transfer_cohort_id="transfer",
                transfer_rules=rules, builder_export_qualification={"sha256": "f" * 64})

    def comparison_material(self, kind="run", artifact_id="run"):
        from flora.selected.comparison_custody import XTDBComparisonCustody
        local = self.authorities[0]
        with patch("flora.selected.comparison_custody.configure_xtdb_connection"), \
                patch("flora.selected.comparison_custody.register_experience_source", self.register_source):
            comparison = XTDBComparisonCustody(scope=local.registry.scope,
                authority_namespace_id=local.registry.authority_namespace_id, connection=self.connection,
                registry=local.registry, objects=local.objects, log=local.log)
            artifact = comparison._put(run_id="run", artifact_id=artifact_id, kind=kind,
                content=encoded({"schema": "fictional-run", "not_an_empirical_result": True}),
                parents=(self.events[0].event_id,), metadata={}, occurred_at="2026-09-30T00:00:00Z")
        for purpose in (manifest_purpose("exp", "qualification"), "comparison_local_recovery"):
            local.permissions.allowed.update(((artifact.event_id, purpose), (self.events[0].event_id, purpose)))
        gate = self.store._gate(local.authority_id, artifact.event_id, manifest_purpose("exp", "qualification"), original=False)
        route = RegisteredPart1Material("result", local.authority_id, artifact.event_id, "comparison",
            tuple(sorted({"run_id": "run", "artifact_id": artifact_id, "artifact_kind": kind,
                "custody_purpose": "comparison_local_recovery"}.items())), comparison)
        return comparison, artifact, gate, route

    def test_typed_comparison_material_requires_exact_locator_and_independent_controller_purpose(self):
        comparison, artifact, gate, route = self.comparison_material()
        local = self.authorities[0]
        reader = RegisteredPart1MaterialReader(routes=(route,), artifact_sha256="e" * 64)
        with self.assertRaisesRegex(PermissionError, "dedicated typed"):
            local.read(gate)
        actual = reader.read(name="result", authority=local, gate=gate)
        self.assertEqual(sha(actual), artifact.record["content_sha256"])
        wrong = replace(route, parameters=tuple(sorted({**dict(route.parameters), "artifact_id": "absent"}.items())))
        with self.assertRaisesRegex(PermissionError, "locator"):
            RegisteredPart1MaterialReader(routes=(wrong,), artifact_sha256="e" * 64).read(name="result", authority=local, gate=gate)
        local.permissions.allowed.remove((artifact.event_id, "comparison_local_recovery"))
        with patch.object(AESGCM, "decrypt", side_effect=AssertionError("must remain sealed")) as decrypt:
            with self.assertRaises(PermissionError):
                reader.read(name="result", authority=local, gate=gate)
            decrypt.assert_not_called()
        self.assertIs(comparison.objects, local.objects)

    def test_typed_comparison_cannot_open_blind_key_or_unknown_private_kind(self):
        for kind in ("blind_key", "assessment_seal", "unknown_internal"):
            _, _, gate, route = self.comparison_material(kind=kind, artifact_id="fixture-" + kind)
            reader = RegisteredPart1MaterialReader(routes=(route,), artifact_sha256="e" * 64)
            with self.subTest(kind=kind), patch.object(AESGCM, "decrypt", side_effect=AssertionError("no private plaintext")) as decrypt:
                with self.assertRaisesRegex(PermissionError, "dedicated qualified"):
                    reader.read(name="result", authority=self.authorities[0], gate=gate)
                decrypt.assert_not_called()

    def test_typed_controller_purpose_withdrawal_during_cipher_fetch_prevents_decryption(self):
        _, artifact, gate, route = self.comparison_material()
        local = self.authorities[0]
        reader = RegisteredPart1MaterialReader(routes=(route,), artifact_sha256="e" * 64)
        original = local.objects.backend.get_object
        triggered = {"value": False}
        def withdraw(namespace, object_id):
            value = original(namespace, object_id)
            if object_id == artifact.record["object_id"] and any(frame.function == "get" and frame.filename.endswith("object_store.py") for frame in inspect.stack()):
                triggered["value"] = True
                local.permissions.allowed.discard((artifact.event_id, "comparison_local_recovery"))
            return value
        with patch.object(local.objects.backend, "get_object", side_effect=withdraw), \
                patch.object(AESGCM, "decrypt", side_effect=AssertionError("withdrawn ciphertext must remain sealed")) as decrypt:
            with self.assertRaises(PermissionError):
                reader.read(name="result", authority=local, gate=gate)
            self.assertTrue(triggered["value"])
            decrypt.assert_not_called()

    def test_part1_internal_material_needs_actual_dispatcher_and_signed_route_binding(self):
        claim, _, gates = self.actual_fixture_part1()
        _, _, gate, route = self.comparison_material()
        claim["materials"]["result"] = gate
        with self.assertRaisesRegex(PermissionError, "actual registered typed"):
            self.store.register_part1_qualification(qualification_id="blocked", cohort_id="cohort", recipe_id="recipe",
                claim=claim, proof=self.keys[1].sign(encoded(claim)))
        reader = RegisteredPart1MaterialReader(routes=(route,), artifact_sha256="e" * 64)
        validator = self.store.part1_validator
        self.store = self.make_store(validator, reader)
        claim["material_reader_artifact_sha256"] = reader.artifact_sha256
        claim["material_routes_sha256"] = "f" * 64
        with self.assertRaises(PermissionError):
            self.store.register_part1_qualification(qualification_id="rebound", cohort_id="cohort", recipe_id="recipe",
                claim=claim, proof=self.keys[1].sign(encoded(claim)))
        self.assertIsNone(self.store.metadata("part1", "blocked"))

    def test_declared_assessment_seal_does_not_bypass_actual_collection_authentication(self):
        from flora.selected.assessment_custody import XTDBAssessmentCustody, assessment_artifact_id
        comparison, artifact, gate, _ = self.comparison_material(kind="assessment_seal",
            artifact_id=assessment_artifact_id("collection", "seal"))
        assessment = XTDBAssessmentCustody(comparison_custody=comparison, signature_authority=None)
        route = RegisteredPart1Material("sealed_assessment", self.authorities[0].authority_id, artifact.event_id,
            "assessment_seal", (("collection_id", "collection"), ("run_id", "run")), assessment)
        reader = RegisteredPart1MaterialReader(routes=(route,), artifact_sha256="e" * 64)
        # An indexed artifact labelled 'seal' is insufficient. The actual
        # controller refuses its absent spec/blind pack/signed collection.
        with patch.object(AESGCM, "decrypt", side_effect=AssertionError("unqualified seal remains private")) as decrypt:
            with self.assertRaises((ValueError, PermissionError)):
                reader.read(name="sealed_assessment", authority=self.authorities[0], gate=gate)
            decrypt.assert_not_called()

    def test_read_grant_check_withdrawal_is_caught_before_manifest_decrypt(self):
        record = self.prepared_cohort()
        local, foreign = self.authorities
        permits = local.permissions.permits
        fired = {"value": False}
        def withdraw(source, purpose):
            result = permits(source, purpose)
            if not fired["value"] and source.evidence.ref_id == record["event_id"] and purpose == manifest_purpose("exp", "read"):
                fired["value"] = True
                foreign.permissions.allowed.remove((self.events[1].event_id, cohort_source_purpose("exp", "heldout")))
            return result
        with patch.object(local.permissions, "permits", side_effect=withdraw), \
                patch.object(AESGCM, "decrypt", side_effect=AssertionError("withdrawn manifest stays sealed")) as decrypt:
            with self.assertRaises(PermissionError):
                self.store.recover(kind="cohort", manifest_id="cohort")
            self.assertTrue(fired["value"])
            decrypt.assert_not_called()

    def test_slow_result_validation_does_not_freeze_private_controller_permission(self):
        claim, _, _ = self.actual_fixture_part1()
        _, artifact, gate, route = self.comparison_material()
        local = self.authorities[0]
        reader = RegisteredPart1MaterialReader(routes=(route,), artifact_sha256="e" * 64)
        class FictionalSlowValidator:
            artifact_sha256 = "d" * 64
            def verify(self, *, claim, materials):
                local.permissions.allowed.remove((artifact.event_id, "comparison_local_recovery"))
                return True  # Fictional port: no experiment/model result asserted.
        self.store = self.make_store(FictionalSlowValidator(), reader)
        claim["materials"]["result"] = gate
        claim["material_reader_artifact_sha256"] = reader.artifact_sha256
        claim["material_routes_sha256"] = reader.binding_sha256
        with self.assertRaises(PermissionError):
            self.store.register_part1_qualification(qualification_id="controller-withdrawn", cohort_id="cohort", recipe_id="recipe",
                claim=claim, proof=self.keys[1].sign(encoded(claim)))
        self.assertIsNone(self.store.metadata("part1", "controller-withdrawn"))


if __name__ == "__main__":
    unittest.main()
