"""Deterministic admission mechanics, not learned semantics/backend evidence.

The supplied semantic adapter/adjudication fixtures describe a fictional world.
They are not a judge or MFM. SQL call recording verifies single-transaction write
shape and rollback handling; selected-engine qualification is separate.
"""

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from cognitive_kernel.adjudication_contracts import (
    AdjudicationRecord, ClaimCandidate, ClaimConflictRecord, ClaimEvidenceRelation,
)
from cognitive_kernel.canonical import canonical_json_bytes, canonical_sha256
from cognitive_kernel.claim_contracts import CanonicalTaggedValue, ClaimIdentity, CurrentClaimProjection
from cognitive_kernel.contracts import ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from cognitive_kernel.formation_context_planner import FormationPlanningRequest
from cognitive_kernel.formation_contracts import FormationProposal, MemoryProposalBundle
from cognitive_kernel.memory_contracts import MemoryUnitEnvelope
from flora.selected.claims import XTDBClaimAuthority
from flora.selected.formation_admission import CandidateInterpretation, XTDBFormationClaimAdmission
from flora.selected.formation_context import (
    prepare_selected_formation, register_experience_source, record_selected_formation_delivery,
)
from flora.selected.revocation import quarantine_claim

_TESTS = str(Path(__file__).resolve().parent)
if _TESTS not in sys.path:
    sys.path.insert(0, _TESTS)
import test_selected_formation_candidates as _candidate_fixture


def fixture_envelope(scope, namespace, record_id, record_type, role, sources=(), *,
                     at="2026-09-29T12:05:00Z", digest="a" * 64):
    return MemoryUnitEnvelope.create(
        scope=scope, authority_namespace_id=namespace, record_id=record_id,
        record_type=record_type, authority_role=role, host_or_cluster_id=scope.host_instance_id,
        deployment_profile="single_workstation", created_at=at, valid_from=at, valid_to=None,
        transaction_time=at, logical_clock=1, causal_parents=(), source_records=sources,
        generation=1, state="committed", data_classification="highly_sensitive",
        retention_class="authoritative_source", deletion_state="active", provenance_digest=digest,
        content_digest=digest, writer="fictional-semantic-fixture", workflow_or_request_id=record_id,
        idempotency_namespace="fictional_claim_admission", idempotency_key=record_id)


class FixtureSemanticAdapter:
    """Externally supplied interpretation; no automatic meaning is inferred."""

    def __init__(self, *, claim_id="fictional-claim-one", identity=None,
                 at="2026-09-29T12:05:00Z", world_id="fictional-world"):
        self.claim_id, self.identity, self.at, self.world_id = claim_id, identity, at, world_id

    def to_candidate(self, *, recovered, proposal, value, request_digest):
        scope, namespace = recovered.bundle.scope, recovered.bundle.authority_namespace_id
        candidate_id = f"candidate-{proposal.proposal_id}"
        identity = self.identity or ClaimIdentity.create(
            envelope=fixture_envelope(scope, namespace, self.claim_id, "claim_identity", "claim_authority",
                                      at=self.at, digest=value.value_sha256),
            claim_id=self.claim_id, canonical_subject=CanonicalTaggedValue.create(
                type_tag="identifier", value=proposal.subject_ref),
            canonical_predicate="fictional.preference", canonical_value=value,
            semantic_scope=("host", self.world_id))
        source_metadata = {ref.ref_id: ref for ref in recovered.packet.evidence}
        relations = tuple(ClaimEvidenceRelation.create(
            envelope=fixture_envelope(scope, namespace, f"rel-{proposal.proposal_id}-{number}",
                                      "claim_evidence_relation", "candidate",
                                      (event_id, candidate_id), at=self.at),
            relation_id=f"rel-{proposal.proposal_id}-{number}", evidence_record_id=event_id,
            target_record_id=candidate_id, target_record_type="claim_candidate", relation_type="support",
            source_class=source_metadata[event_id].role, source_authority_class="experimental",
            extractor_component_id="fictional-semantic-adapter", extractor_version="fixture-v1",
            confidence=None) for number, event_id in enumerate(proposal.evidence_refs))
        candidate = ClaimCandidate.create(
            envelope=fixture_envelope(scope, namespace, candidate_id, "claim_candidate", "candidate",
                (self.claim_id, recovered.bundle.bundle_id, proposal.proposal_id,
                 recovered.recorded.event.event_id, *(relation.relation_id for relation in relations)),
                at=self.at, digest=request_digest),
            candidate_id=candidate_id, identity=identity, value=value,
            evidence_relation_ids=tuple(relation.relation_id for relation in relations),
            proposed_action="revise" if proposal.kind == "correction_request" else "add",
            extractor_component_id="fictional-semantic-adapter", extractor_version="fixture-v1",
            model_or_rule_id=recovered.bundle.model_artifact_digest, confidence=None,
            request_digest=request_digest)
        return CandidateInterpretation(candidate, relations)


def fixture_adjudication(bound, *, at="2026-09-29T12:05:00Z", conflict_id=None):
    candidate = bound.interpretation.candidate
    record_id = f"adjudication-{candidate.candidate_id}"
    return AdjudicationRecord.create(
        envelope=fixture_envelope(candidate.envelope.scope, candidate.envelope.authority_namespace_id,
            record_id, "adjudication_record", "claim_authority",
            (candidate.candidate_id, candidate.identity.claim_id, *candidate.evidence_relation_ids,
             *((conflict_id,) if conflict_id else ())), at=at),
        adjudication_id=record_id, candidate_id=candidate.candidate_id,
        claim_id=candidate.identity.claim_id, authority_class="experimental",
        authority_actor_id="fictional-reviewer", policy_profile="flora-fictional-world-v1",
        rule_id="supplied-fictional-verdict", rule_version="fixture-v1",
        evidence_relation_ids=candidate.evidence_relation_ids, confidence=None,
        outcome=candidate.proposed_action, execution_mode="production", canonical_effect=True,
        conflict_record_id=conflict_id, rationale_codes=("fixture-reviewed-meaning",),
        rollback_reference="fictional-rollback")


def fixture_conflict(bound, adjudication, previous):
    candidate = bound.interpretation.candidate
    return ClaimConflictRecord.create(
        envelope=fixture_envelope(candidate.envelope.scope, candidate.envelope.authority_namespace_id,
            adjudication.conflict_record_id, "claim_conflict_record", "claim_authority",
            (candidate.candidate_id, previous.current_claim_version_id, *candidate.evidence_relation_ids),
            at=adjudication.envelope.created_at),
        conflict_id=adjudication.conflict_record_id, claim_id=candidate.identity.claim_id,
        member_record_ids=(candidate.candidate_id, previous.current_claim_version_id),
        evidence_relation_ids=candidate.evidence_relation_ids, conflict_type="correction",
        resolution_state="resolved", detected_by="fictional-reviewer", detection_rule_id="fixture-correction",
        resolution_adjudication_id=adjudication.adjudication_id, rollback_reference=previous.projection_id)


def fixture_projection(record):
    envelope_record = dict(record["envelope"])
    scope = envelope_record.pop("scope")
    envelope_record.pop("envelope_sha256")
    from cognitive_kernel.contracts import ProductHostScope
    envelope = MemoryUnitEnvelope.create(scope=ProductHostScope.create(**scope), **envelope_record)
    projection = CurrentClaimProjection(**{**record, "envelope": envelope})
    projection.validate()
    return projection


class FixtureSemanticVerifier:
    """A fixture reviewer signs supplied verdicts; it does not judge semantics."""

    def __init__(self, scope, namespace, world_id="fictional-world"):
        self.scope, self.namespace, self.world_id = scope, namespace, world_id
        self.signer = Ed25519PrivateKey.generate()
        self.key = self.signer.public_key()
        self.proofs = {}

    def message(self, adjudication, candidate, recovered, world):
        return canonical_json_bytes({
            "domain": "FloRA-fixture-semantic-adjudication-v1",
            "scope": self.scope.metadata_record(), "authority_namespace_id": self.namespace,
            "experiment_world_id": world, "adjudication_sha256": adjudication.adjudication_sha256,
            "candidate_sha256": candidate.candidate_sha256,
            "bundle_sha256": recovered.bundle.content_digest(),
        })

    def approve_fixture(self, adjudication, bound):
        self.proofs[adjudication.adjudication_id] = self.signer.sign(self.message(
            adjudication, bound.interpretation.candidate, bound.recovered, self.world_id))

    def authenticated_adjudication(self, adjudication, candidate, recovered, experiment_world_id):
        if (candidate.envelope.scope != self.scope
                or candidate.envelope.authority_namespace_id != self.namespace
                or experiment_world_id != self.world_id):
            return False
        signature = self.proofs.get(adjudication.adjudication_id)
        if signature is None:
            return False
        try:
            self.key.verify(signature, self.message(adjudication, candidate, recovered, experiment_world_id))
        except InvalidSignature:
            return False
        return True


class _Cursor:
    def __init__(self, rows):
        names = tuple(rows[0]) if rows else ()
        self.description = [SimpleNamespace(name=name) for name in names]
        self.rows = [tuple(row[name] for name in names) for row in rows]

    def fetchall(self):
        return self.rows


class _AdmissionSQLCalls:
    def __init__(self, previous):
        self.rows, self.calls = deepcopy(previous.rows), previous.calls.copy()
        self.adapters = previous.adapters
        self.failure_table = None
        self.transaction_depth = 0
        self.before_transaction = None

    @contextmanager
    def transaction(self):
        if self.transaction_depth:
            raise ValueError("nested transaction would require unsupported SAVEPOINT")
        if self.before_transaction is not None:
            callback, self.before_transaction = self.before_transaction, None
            callback()
        snapshot = deepcopy(self.rows)
        self.transaction_depth += 1
        try:
            yield
        except Exception:
            self.rows = snapshot
            raise
        finally:
            self.transaction_depth -= 1

    def execute(self, sql, parameters):
        self.calls.append((sql, parameters))
        table = re.search(r"(?:FROM|INTO) (\w+)", sql).group(1)
        if sql.startswith("INSERT"):
            if self.failure_table == table:
                self.failure_table = None
                raise RuntimeError("injected authority insert failure")
            names = re.search(r"\(([^)]+)\) VALUES", sql).group(1).split(", ")
            row = dict(zip(names, parameters))
            self.rows[(table, row["_id"])] = row
            return _Cursor([])
        if "WHERE scope_digest =" in sql:
            found = [row for (name, _), row in self.rows.items()
                     if name == table and row["scope_digest"] == parameters[0]]
            sequence_filter = re.search(r"AND (store_sequence|source_position) >=", sql)
            if sequence_filter:
                found = [row for row in found if row[sequence_filter.group(1)] >= parameters[1]]
        else:
            row = self.rows.get((table, parameters[0]))
            found = [row] if row is not None else []
        if sql.startswith("SELECT MAX("):
            column = re.search(r"MAX\(CAST\((\w+) AS", sql).group(1)
            return _Cursor([{"maximum": max((row[column] for row in found), default=None)}])
        if sql.startswith("ASSERT NOT"):
            if found:
                raise ValueError("synthetic immutable/CAS absence assertion failed")
            return _Cursor([])
        if sql.startswith("ASSERT EXISTS"):
            digest_column = "projection_sha256" if "AND projection_sha256" in sql else "record_sha256"
            if not found or found[0][digest_column] != parameters[1]:
                raise ValueError("synthetic authority CAS assertion failed")
            return _Cursor([])
        return _Cursor(found)


class SelectedFormationAdmissionTest(unittest.TestCase):
    def setUp(self):
        self.fixture = _candidate_fixture.SelectedFormationCandidatesTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        for name, value in self.fixture.__dict__.items():
            if not name.startswith("_"):
                setattr(self, name, value)
        self.connection = _AdmissionSQLCalls(self.connection)
        self.fixture.connection = self.connection
        self.registry.connection = self.connection
        self.candidates.connection = self.connection
        self.fixture._record()
        self.authority = XTDBClaimAuthority(scope=self.scope, authority_namespace_id=self.namespace,
                                            connection=self.connection)
        self.gateway = XTDBFormationClaimAdmission(authority=self.authority, candidates=self.candidates,
                                                   experiment_world_id="fictional-world")
        self.store = self.prepared.store
        self.verifier = FixtureSemanticVerifier(self.scope, self.namespace)

    def _bound(self, proposal_id="fictional-proposal-1", *, adapter=None):
        return self.gateway.prepare(bundle_id=self.bundle.bundle_id, proposal_id=proposal_id,
            adapter=adapter or FixtureSemanticAdapter(), log=self.log, objects=self.objects,
            source_store=self.store)

    def _admit(self, bound, adjudication, *, source_store=None, **kwargs):
        return self.gateway.admit(bound, adjudication=adjudication, verifier=self.verifier,
            log=self.log, objects=self.objects,
            source_store=self.store if source_store is None else source_store, **kwargs)

    def test_signed_semantic_admission_is_atomic_idempotent_and_has_separate_sequences(self):
        bound = self._bound()
        adjudication = fixture_adjudication(bound)
        with self.assertRaisesRegex(ValueError, "independently authenticated"):
            self._admit(bound, adjudication)
        self.verifier.approve_fixture(adjudication, bound)
        before = deepcopy(self.connection.rows)
        self.connection.failure_table = "fable_claim_versions"
        with self.assertRaisesRegex(RuntimeError, "insert failure"):
            self._admit(bound, adjudication)
        self.assertEqual(self.connection.rows, before)
        receipt = self._admit(bound, adjudication)
        self.assertEqual((receipt.store_sequence, receipt.version_sequence), (1, 1))
        self.assertEqual(receipt.event_stream_position, 1)
        self.assertEqual(self.authority.load_current(receipt.claim_id)["source_position"], 1)
        snapshot = deepcopy(self.connection.rows)
        self.assertEqual(self._admit(bound, adjudication), receipt)
        self.assertEqual(self.connection.rows, snapshot)

    def test_property_slot_blocks_second_claim_with_conflicting_value(self):
        first = self._bound()
        decision = fixture_adjudication(first)
        self.verifier.approve_fixture(decision, first)
        self._admit(first, decision)
        other = self._bound("fictional-proposal-2", adapter=FixtureSemanticAdapter(claim_id="another-claim"))
        other_decision = fixture_adjudication(other)
        self.verifier.approve_fixture(other_decision, other)
        with self.assertRaisesRegex(ValueError, "semantic property already"):
            self._admit(other, other_decision)

    def test_model_value_mutation_and_revoked_source_cannot_reach_authority(self):
        bound = self._bound()
        decision = fixture_adjudication(bound)
        self.verifier.approve_fixture(decision, bound)
        wrong = replace(bound, interpretation=replace(bound.interpretation,
            candidate=replace(bound.interpretation.candidate, value=self.value_two)))
        with self.assertRaises(ValueError):
            self._admit(wrong, decision)
        self.permitted[0] = False
        before = deepcopy(self.connection.rows)
        source_objects = {self.registry.lookup(ref.ref_id).object_ref
                          for ref in self.prepared.assembled.packet.evidence}
        original_read = self.objects.backend.get_object
        def read(namespace, object_id):
            self.assertNotIn(object_id, source_objects,
                             "denied original entered candidate admission ciphertext read")
            return original_read(namespace, object_id)
        with patch.object(self.objects.backend, "get_object", side_effect=read):
            with self.assertRaisesRegex(PermissionError, "permission.*withdrawn"):
                self._admit(bound, decision)
        self.assertEqual(self.connection.rows, before)

    def test_derived_child_cannot_launder_synthetic_parent_into_owner_truth(self):
        parent = self.log.replay()[1]
        raw = self.objects.put(b"derived fictional preference")
        event = ExperienceEvent.create(event_type="observation", scope=self.scope,
            occurred_at="2026-09-29T12:10:00Z", content_digest=raw.plaintext_sha256,
            provenance=ProvenanceReference.create(provenance_type="derived_inference",
                source_reference_ids=(raw.object_id,), derivation_activity_id="fixture-derived-source",
                responsible_component="fixture-derived-component"),
            retention_class="ordinary_experience", storage_tier="raw_buffer",
            payload_reference=raw.object_id, parent_event_ids=(parent.event_id,))
        self.log.append(event, expected_revision=len(self.log.replay()) - 1)
        register_experience_source(event_id=event.event_id, raw=raw, registry=self.registry,
            log=self.log, objects=self.objects, role="derived_inference", modality="text")
        prepared = prepare_selected_formation(
            request=FormationPlanningRequest(scope=self.scope, authority_namespace_id=self.namespace,
                                             experience_refs=(event.event_id,)),
            registry=self.registry, objects=self.objects, permits=lambda *_: self.permitted[0])
        delivery = record_selected_formation_delivery(prepared=prepared, log=self.log, objects=self.objects,
            occurred_at="2026-09-29T12:11:00Z", expected_revision=len(self.log.replay()) - 1,
            request_id="derived-fixture-request")
        packet = prepared.assembled.packet
        bundle = MemoryProposalBundle(scope=self.scope, authority_namespace_id=self.namespace,
            bundle_id="derived-fixture-bundle", experience_refs=packet.experience_refs,
            context_digest=packet.content_digest(), model_artifact_digest=self.artifact,
            inference_run_id="derived-fixture-inference", proposals=(FormationProposal(
                proposal_id="derived-fixture-proposal", kind="preference", domain="host",
                subject_ref=self.scope.host_instance_id, value_ref="candidate-value-one",
                evidence_refs=(event.event_id,), epistemic_status="inference"),))
        self.candidates.record(prepared=prepared, delivery=delivery, bundle=bundle, log=self.log,
            objects=self.objects, expected_model_artifact_sha256=self.artifact,
            occurred_at="2026-09-29T12:12:00Z", expected_revision=len(self.log.replay()) - 1,
            value_resolver=self.values)
        bound = self.gateway.prepare(bundle_id=bundle.bundle_id, proposal_id=bundle.proposals[0].proposal_id,
            adapter=FixtureSemanticAdapter(at="2026-09-29T12:13:00Z"),
            log=self.log, objects=self.objects, source_store=prepared.store)
        experimental = fixture_adjudication(bound, at="2026-09-29T12:13:00Z")
        record = experimental.metadata_record()
        record.pop("adjudication_sha256")
        record.pop("schema_version")
        record["envelope"] = experimental.envelope
        record.update(authority_class="owner", policy_profile="fixture-owner-claim")
        owner_verdict = AdjudicationRecord.create(**record)
        self.verifier.approve_fixture(owner_verdict, bound)
        before = deepcopy(self.connection.rows)
        with self.assertRaisesRegex(ValueError, "isolated experimental authority"):
            self.gateway.admit(bound, adjudication=owner_verdict, verifier=self.verifier,
                log=self.log, objects=self.objects, source_store=prepared.store)
        self.assertEqual(self.connection.rows, before)
        self.verifier.approve_fixture(experimental, bound)
        self.gateway.admit(bound, adjudication=experimental, verifier=self.verifier,
            log=self.log, objects=self.objects, source_store=prepared.store)

    def test_controller_refuses_legacy_writes_and_untracked_sequence(self):
        first = self._bound()
        decision = fixture_adjudication(first)
        self.verifier.approve_fixture(decision, first)
        receipt = self._admit(first, decision)
        previous = fixture_projection(self.authority.load_current(receipt.claim_id))
        for write in (
            lambda: self.authority.put_identity(first.interpretation.candidate.identity),
            lambda: self.authority.put_evidence_relation(first.interpretation.relations[0]),
            lambda: self.authority.put_current(previous),
            lambda: quarantine_claim(prior=previous, request_event_id="unused-request",
                authority=self.authority, log=self.log, objects=self.objects, references={},
                vector=SimpleNamespace(scope=self.scope), verifier=None),
        ):
            with self.assertRaisesRegex(ValueError, "governed namespace"):
                write()
        other = self._bound("fictional-proposal-2", adapter=FixtureSemanticAdapter(claim_id="another-claim"))
        other_decision = fixture_adjudication(other)
        self.verifier.approve_fixture(other_decision, other)
        key = ("fable_claim_versions", "untracked-version-row")
        self.connection.rows[key] = {"_id": key[1], "scope_digest": self.authority.scope_digest,
                                     "store_sequence": 9}
        with self.assertRaisesRegex(ValueError, "untracked store sequence"):
            self._admit(other, other_decision)
        del self.connection.rows[key]
        counter_key = ("flora_claim_admission_namespace_counters",
                       self.authority._row_id("admission-namespace-counter"))
        row = self.connection.rows[counter_key]
        counter = json.loads(row["record_json"])
        counter.pop("record_sha256")
        counter["controller_id"] = "unrecognized-controller"
        counter["record_sha256"] = canonical_sha256(counter)
        row.update(record_json=json.dumps(counter), record_sha256=counter["record_sha256"])
        with self.assertRaisesRegex(ValueError, "different sequence controller"):
            self._admit(other, other_decision)

    def test_transaction_fence_catches_sequence_contamination_after_inventory_read(self):
        first = self._bound()
        decision = fixture_adjudication(first)
        self.verifier.approve_fixture(decision, first)
        self._admit(first, decision)
        identity = ClaimIdentity.create(
            envelope=fixture_envelope(self.scope, self.namespace, "new-property-claim",
                "claim_identity", "claim_authority", digest=self.value_two.value_sha256),
            claim_id="new-property-claim", canonical_subject=CanonicalTaggedValue.create(
                type_tag="identifier", value=self.scope.host_instance_id),
            canonical_predicate="fictional.other-preference", canonical_value=self.value_two,
            semantic_scope=("host", "fictional-world"))
        other = self._bound("fictional-proposal-2", adapter=FixtureSemanticAdapter(
            identity=identity, claim_id=identity.claim_id))
        other_decision = fixture_adjudication(other)
        self.verifier.approve_fixture(other_decision, other)
        key = ("fable_claim_versions", "racing-untracked-version")
        row = {"_id": key[1], "scope_digest": self.authority.scope_digest, "store_sequence": 2}
        before = deepcopy(self.connection.rows)
        self.connection.before_transaction = lambda: self.connection.rows.update({key: row})
        with self.assertRaisesRegex(ValueError, "absence assertion failed"):
            self._admit(other, other_decision)
        self.assertEqual(self.connection.rows, {**before, key: row})
        self.assertTrue(any("AND store_sequence >=" in sql for sql, _ in self.connection.calls))

    def test_exact_correction_preserves_identity_and_advances_namespace_sequence(self):
        first = self._bound()
        decision = fixture_adjudication(first)
        self.verifier.approve_fixture(decision, first)
        receipt = self._admit(first, decision)
        previous = fixture_projection(self.authority.load_current(receipt.claim_id))
        original_event = self.log.replay()[receipt.event_stream_position]
        raw = self.objects.put(b"fictional explicit correction source")
        event = ExperienceEvent.create(
            event_type="correction", scope=self.scope, occurred_at="2026-09-29T12:10:00Z",
            content_digest=raw.plaintext_sha256,
            provenance=ProvenanceReference.create(
                provenance_type="generated_reconstruction", source_reference_ids=(raw.object_id,),
                derivation_activity_id="fixture-correction", responsible_component="fictional-source"),
            retention_class="ordinary_experience", storage_tier="raw_buffer",
            payload_reference=raw.object_id, parent_event_ids=(original_event.event_id,))
        self.log.append(event, expected_revision=len(self.log.replay()) - 1)
        register_experience_source(event_id=event.event_id, raw=raw, registry=self.registry,
            log=self.log, objects=self.objects, role="generated_reconstruction", modality="text")
        prepared = prepare_selected_formation(
            request=FormationPlanningRequest(scope=self.scope, authority_namespace_id=self.namespace,
                                             experience_refs=(event.event_id,)),
            registry=self.registry, objects=self.objects, permits=lambda *_: self.permitted[0])
        delivery = record_selected_formation_delivery(
            prepared=prepared, log=self.log, objects=self.objects, occurred_at="2026-09-29T12:11:00Z",
            expected_revision=len(self.log.replay()) - 1, request_id="fixture-correction-formation")
        packet = prepared.assembled.packet
        bundle = MemoryProposalBundle(
            scope=self.scope, authority_namespace_id=self.namespace, bundle_id="fixture-correction-bundle",
            experience_refs=packet.experience_refs, context_digest=packet.content_digest(),
            model_artifact_digest=self.artifact, inference_run_id="fixture-correction-inference",
            proposals=(FormationProposal(proposal_id="fixture-correction-proposal", kind="correction_request",
                domain="host", subject_ref=self.scope.host_instance_id, value_ref="candidate-value-two",
                evidence_refs=(event.event_id,), epistemic_status="reconstruction",
                valid_from="2026-09-29T12:10:00Z", contradicts=(receipt.claim_version_id,)),))
        self.candidates.record(prepared=prepared, delivery=delivery, bundle=bundle, log=self.log,
            objects=self.objects, expected_model_artifact_sha256=self.artifact,
            occurred_at="2026-09-29T12:12:00Z", expected_revision=len(self.log.replay()) - 1,
            value_resolver=self.values)
        corrected = self.gateway.prepare(bundle_id=bundle.bundle_id, proposal_id=bundle.proposals[0].proposal_id,
            adapter=FixtureSemanticAdapter(identity=first.interpretation.candidate.identity,
                                           at="2026-09-29T12:13:00Z"),
            log=self.log, objects=self.objects, source_store=prepared.store)
        corrected_decision = fixture_adjudication(corrected, at="2026-09-29T12:13:00Z",
                                                  conflict_id="fixture-correction-conflict")
        conflict = fixture_conflict(corrected, corrected_decision, previous)
        self.verifier.approve_fixture(corrected_decision, corrected)
        # A preparation is an exact source closure, not a reusable permission
        # wrapper for another candidate. The earlier store must refuse this
        # correction even though all sources remain registered and permitted.
        before = deepcopy(self.connection.rows)
        original_ids = {ref.ref_id for ref in self.prepared.assembled.packet.evidence}
        source_objects = {self.registry.lookup(ref.ref_id).object_ref
                          for ref in packet.evidence if ref.ref_id not in original_ids}
        original_read = self.objects.backend.get_object
        def read(namespace, object_id):
            self.assertNotIn(object_id, source_objects,
                             "foreign closure entered candidate admission ciphertext read")
            return original_read(namespace, object_id)
        with patch.object(self.objects.backend, "get_object", side_effect=read):
            with self.assertRaisesRegex(PermissionError, "outside actual upstream resolved closure"):
                self._admit(corrected, corrected_decision)
        self.assertEqual(self.connection.rows, before)
        with self.assertRaisesRegex(ValueError, "exact available predecessor"):
            self._admit(corrected, corrected_decision, source_store=prepared.store)
        correction_receipt = self._admit(corrected, corrected_decision,
                                         source_store=prepared.store,
                                         expected_previous=previous, conflict=conflict)
        self.assertEqual((correction_receipt.store_sequence, correction_receipt.version_sequence), (2, 2))
        self.assertNotEqual(correction_receipt.event_stream_position, correction_receipt.store_sequence)
        current = self.authority.load_current(receipt.claim_id)
        self.assertEqual(current["current_claim_version_id"], correction_receipt.claim_version_id)
        self.assertEqual(current["source_position"], 2)
        version = self.authority.load_version(correction_receipt.claim_version_id)
        self.assertEqual(version["correction_of"], [receipt.claim_version_id])
        self.assertEqual(version["value"], self.value_two.metadata_record())
        self.assertEqual(self._admit(first, decision), receipt)
        self.assertEqual(self.authority.load_current(receipt.claim_id), current)


if __name__ == "__main__":
    unittest.main()
