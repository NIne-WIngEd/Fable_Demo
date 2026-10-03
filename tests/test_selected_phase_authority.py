"""Selected producer identity contracts; controlled transport, no latency claim."""
from copy import copy
from dataclasses import replace
import gc
import sys
from types import MethodType, SimpleNamespace
import unittest
from unittest.mock import patch
from weakref import ref

from flora.selected import selected_phase_authority as selected
from flora.selected.comparison_custody import evaluation_purpose
from flora.selected.context import ContextPlan
from flora.selected.formation_policy import XTDBFormationPermissionPolicy
from flora.selected.governed_development import XTDBGovernedPersonalDevelopment
from flora.selected.judgment_context import RegisteredJudgmentContextPolicy
from flora.selected.native_arm import NativeInvocationEntry
from flora.selected.native_phase_gate import (
    copy_native_phase_view, install_native_phase_gate, transfer_native_phase_gate,
)
from flora.selected.native_reads import SelectedNativeReadServices
import test_selected_history_fence as fixtures


class FixtureOwner:
    def __init__(self, **fields):
        self.__dict__.update(fields)


def _phase_pass_calls(operation):
    """Observe native verifier calls without replacing a pinned dependency."""
    calls = {"origins": [], "seals": [], "descriptors": [], "readers": [], "callbacks": []}
    codes = {selected._Origin.verify.__code__: ("origins", "self"),
        selected._verify_origin_seal.__code__: ("seals", "origin"),
        selected._ReaderBinding.verify.__code__: ("readers", "self")}
    callbacks = tuple(selected._CALLBACK_CODES.values())
    def observe(frame, event, argument):
        if event != "call":
            return
        match = codes.get(frame.f_code)
        if match is not None:
            key, name = match
            calls[key].append(id(frame.f_locals[name]))
        if frame.f_code is selected._verify_identity.__code__:
            value = frame.f_locals["value"]
            if type(value) is selected.SelectedPhaseAuthorityDescriptor:
                calls["descriptors"].append(id(value))
        if frame.f_code in callbacks:
            calls["callbacks"].append(frame.f_code.co_name)
    previous = sys.getprofile()
    try:
        sys.setprofile(observe)
        operation()
    finally:
        sys.setprofile(previous)
    return calls


class SelectedPhaseAuthorityTest(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.SelectedHistoryFenceTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        h, f = fixture.h, fixture.f
        state = XTDBGovernedPersonalDevelopment(scope=f.scope,
            authority_namespace_id=f.namespace, connection=f.connection,
            registry=h.registry, policy=h.permissions)
        context = RegisteredJudgmentContextPolicy(claims=f.claims, state=state,
            log=fixture.log, registry=h.registry, permissions=h.permissions)
        self.runtime = FixtureOwner(scope=f.scope, authority_namespace_id=f.namespace,
            sources=h.registry, log=fixture.log, source_policy=h.permissions,
            context_policy=context, state=state)
        self.initial_authority = fixture.policy
        self.lineage = FixtureOwner(history_authority=fixture.policy)
        self.entry = NativeInvocationEntry("case", "before", "fixture-phase",
            ContextPlan("fixture-context", "personal_judgment", exact_claim_ids=("fixture-claim",)), "a" * 64)
        self.history = h.before

    def install(self):
        SelectedNativeReadServices._install_phase_source_gate(
            SimpleNamespace(runtime=self.runtime, lineage=self.lineage), self.entry, self.history)
        return selected.selected_phase_authority(self.runtime.source_policy, "permits")

    def gate_cells(self):
        gate = self.runtime.source_policy.permits.__func__
        return dict(zip(gate.__code__.co_freevars, gate.__closure__))

    def install_peer(self):
        """Issue another native producer over the same exact held history."""
        state = copy(self.runtime.state)
        state.policy = self.fixture.h.permissions
        context = RegisteredJudgmentContextPolicy(claims=self.fixture.f.claims, state=state,
            log=self.fixture.log, registry=self.fixture.h.registry,
            permissions=self.fixture.h.permissions)
        runtime = FixtureOwner(scope=self.fixture.f.scope,
            authority_namespace_id=self.fixture.f.namespace, sources=self.fixture.h.registry,
            log=self.fixture.log, source_policy=self.fixture.h.permissions,
            context_policy=context, state=state)
        lineage = FixtureOwner(history_authority=self.initial_authority)
        SelectedNativeReadServices._install_phase_source_gate(
            SimpleNamespace(runtime=runtime, lineage=lineage), self.entry, self.history)
        return runtime, lineage

    def test_actual_selected_installer_issues_exact_origin_without_validation_io(self):
        descriptor = self.install()
        self.assertIsNotNone(descriptor)
        self.assertEqual((descriptor.case_id, descriptor.phase), ("case", "before"))
        self.assertEqual(descriptor.history_sha256, self.history.digest())
        self.assertEqual(descriptor.original_event_ids, self.history.event_ids)
        self.assertIsNotNone(selected.selected_phase_authority(self.runtime.context_policy, "allow_event"))
        calls = len(self.fixture.f.connection.calls), len(self.fixture.client.reads)
        private = self.fixture.h.custody.raw_custody
        with patch.object(private, "read", side_effect=AssertionError("private IO")):
            self.assertIs(descriptor.verify(), descriptor)
        self.assertEqual(calls, (len(self.fixture.f.connection.calls), len(self.fixture.client.reads)))

    def test_pair_shares_origin_body_but_rechecks_each_descriptor_and_parent(self):
        permission = self.install()
        copied = copy_native_phase_view(self.runtime.source_policy)
        inherited = selected.selected_phase_authority(copied, "permits")
        event = selected.selected_phase_authority(self.runtime.context_policy, "allow_event")
        io = len(self.fixture.f.connection.calls), len(self.fixture.client.reads)
        observed = _phase_pass_calls(lambda: self.assertIsNone(
            selected._verify_selected_phase_pair(inherited, event)))
        self.assertEqual(observed["origins"], [id(permission._origin)])
        self.assertEqual(observed["seals"], [id(permission._origin)] * 3)
        self.assertEqual(observed["descriptors"], [id(inherited), id(permission), id(event)])
        for descriptor in (inherited, permission, event):
            self.assertEqual(observed["readers"].count(id(descriptor._reader)), 1)
        self.assertEqual(observed["callbacks"], [])
        self.assertEqual(io, (len(self.fixture.f.connection.calls), len(self.fixture.client.reads)))

    def test_pair_and_public_verification_start_fresh_pure_passes(self):
        permission = self.install()
        copied = copy_native_phase_view(self.runtime.source_policy)
        inherited = selected.selected_phase_authority(copied, "permits")
        event = selected.selected_phase_authority(self.runtime.context_policy, "allow_event")
        def verify_again():
            selected._verify_selected_phase_pair(inherited, event)
            selected._verify_selected_phase_pair(inherited, event)
            self.assertIs(inherited.verify(), inherited)
            self.assertIs(inherited.verify(), inherited)
        observed = _phase_pass_calls(verify_again)
        self.assertEqual(observed["origins"], [id(permission._origin)] * 4)
        self.assertEqual(len(observed["seals"]), 10)
        event_value = self.history.sources[0].event
        previous = event_value.event_type
        try:
            event_value.__dict__["event_type"] = "in-place mutation"
            with self.assertRaisesRegex(PermissionError, "held material or scope changed"):
                selected._verify_selected_phase_pair(inherited, event)
            with self.assertRaisesRegex(PermissionError, "held material or scope changed"):
                inherited.verify()
        finally:
            event_value.__dict__["event_type"] = previous
        selected._verify_selected_phase_pair(inherited, event)

    def test_distinct_issued_origins_with_same_history_each_run_their_body(self):
        permission = self.install()
        peer, lineage = self.install_peer()
        event = selected.selected_phase_authority(peer.context_policy, "allow_event")
        self.assertEqual(permission.history_sha256, event.history_sha256)
        self.assertIsNot(permission._origin, event._origin)
        observed = _phase_pass_calls(lambda: selected._verify_selected_phase_pair(permission, event))
        self.assertEqual(observed["origins"], [id(permission._origin), id(event._origin)])
        self.assertEqual(observed["callbacks"], [])

    def test_second_descriptor_and_inherited_parent_cannot_skip_private_checks(self):
        permission = self.install()
        event = selected.selected_phase_authority(self.runtime.context_policy, "allow_event")
        copied = copy_native_phase_view(self.runtime.context_policy)
        inherited = selected.selected_phase_authority(copied, "allow_event")
        effects = []
        class Effectful:
            def __getattribute__(self, name):
                effects.append(name)
                raise AssertionError("replacement descriptor inspected")
            def __call__(self, *args):
                effects.append("callback")
        for target in (event, inherited):
            forged = replace(target)
            with self.subTest(kind="unissued", target=target._name):
                with self.assertRaisesRegex(PermissionError, "privately issued"):
                    selected._verify_selected_phase_pair(permission, forged)
            for name in ("_reader", "_gate", "_origin", "_parents"):
                previous = object.__getattribute__(target, name)
                try:
                    replacement = (replace(event),) if name == "_parents" else Effectful()
                    object.__setattr__(target, name, replacement)
                    with self.subTest(kind=name, target=target._name), self.assertRaises(PermissionError):
                        selected._verify_selected_phase_pair(permission, target)
                    self.assertEqual(effects, [])
                finally:
                    object.__setattr__(target, name, previous)
        original = self.runtime.context_policy.allow_event
        try:
            self.runtime.context_policy.allow_event = Effectful()
            with self.assertRaises(PermissionError):
                selected._verify_selected_phase_pair(permission, inherited)
            self.assertEqual(effects, [])
        finally:
            self.runtime.context_policy.allow_event = original
        selected._verify_selected_phase_pair(permission, inherited)

    def test_pair_rejects_inherited_native_class_code_and_reader_mutation_before_effects(self):
        permission = self.install()
        copied = copy_native_phase_view(self.runtime.context_policy)
        inherited = selected.selected_phase_authority(copied, "allow_event")
        parent = inherited._parents[0]
        effects = []
        class AlteredDescriptor(selected.SelectedPhaseAuthorityDescriptor):
            def verify(self):
                effects.append("descriptor")
        original_class = type(parent)
        try:
            object.__setattr__(parent, "__class__", AlteredDescriptor)
            with self.assertRaisesRegex(PermissionError, "native class changed"):
                selected._verify_selected_phase_pair(permission, inherited)
            self.assertEqual(effects, [])
        finally:
            object.__setattr__(parent, "__class__", original_class)
        original_owner = parent._reader.owner
        try:
            object.__setattr__(parent._reader, "owner", copy(original_owner))
            with self.assertRaises(PermissionError):
                selected._verify_selected_phase_pair(permission, inherited)
            self.assertEqual(effects, [])
        finally:
            object.__setattr__(parent._reader, "owner", original_owner)
        function = parent._gate.function
        original_code = function.__code__
        try:
            function.__code__ = original_code.replace(co_name="mutated-parent-gate")
            with self.assertRaises(PermissionError):
                selected._verify_selected_phase_pair(permission, inherited)
            self.assertEqual(effects, [])
        finally:
            function.__code__ = original_code
        def replacement(*args, observed=effects):
            observed.append("verifier")
        for function in (selected._Origin.verify, selected.SelectedPhaseAuthorityDescriptor.verify):
            original_code = function.__code__
            try:
                function.__code__ = replacement.__code__
                with self.assertRaisesRegex(PermissionError, "verifier code changed"):
                    selected._verify_selected_phase_pair(permission, inherited)
                self.assertEqual(effects, [])
            finally:
                function.__code__ = original_code
        selected._verify_selected_phase_pair(permission, inherited)

    def test_pair_helpers_are_pinned_before_replacement_or_descriptor_effects(self):
        permission = self.install()
        event = selected.selected_phase_authority(self.runtime.context_policy, "allow_event")
        effects = []
        def replacement(*args, observed=effects):
            observed.append("replacement")
        for name in ("_verify_selected_phase_tree", "_verify_selected_phase_pair"):
            original = getattr(selected, name)
            with self.subTest(helper=name), patch.object(selected, name, replacement):
                with self.assertRaisesRegex(PermissionError, "verifier binding"):
                    permission.verify()
                self.assertEqual(effects, [])
            code = original.__code__
            try:
                original.__code__ = replacement.__code__
                with self.assertRaisesRegex(PermissionError, "verifier binding"):
                    selected.selected_phase_authority(self.runtime.source_policy, "permits")
                self.assertEqual(effects, [])
            finally:
                original.__code__ = code
        selected._verify_selected_phase_pair(permission, event)

    def test_pure_pass_accepts_no_caller_seen_state_or_effectful_root_container(self):
        permission = self.install()
        event = selected.selected_phase_authority(self.runtime.context_policy, "allow_event")
        effects = []
        class Effectful:
            def __iter__(self):
                effects.append("iteration")
                raise AssertionError("custom roots iterated")
            def __len__(self):
                effects.append("length")
                raise AssertionError("custom roots measured")
        with self.assertRaises(PermissionError):
            selected._verify_selected_phase_tree(Effectful())
        with self.assertRaises(TypeError):
            selected._verify_selected_phase_pair(permission, event, {id(permission._origin)})
        with self.assertRaises(TypeError):
            permission.verify({id(permission._origin)})
        self.assertEqual(effects, [])

    def test_descriptor_does_not_cache_phase_or_member_success(self):
        self.install()
        source = self.runtime.sources.lookup(self.history.event_ids[0])
        purpose = evaluation_purpose("run", "case", "before")
        counts = []
        for _ in range(2):
            before = len(self.fixture.f.connection.calls), len(self.fixture.client.reads)
            self.assertTrue(self.runtime.source_policy.permits(source, purpose))
            after = len(self.fixture.f.connection.calls), len(self.fixture.client.reads)
            counts.append((after[0] - before[0], after[1] - before[1]))
        self.assertTrue(all(sql > 0 and physical > 0 for sql, physical in counts))
        self.assertEqual(counts[0], counts[1])

    def test_generic_custom_callbacks_never_receive_descriptor_and_still_run(self):
        calls = []
        owner = copy(self.runtime.source_policy)
        install_native_phase_gate(owner, "permits", canonical_predicate=XTDBFormationPermissionPolicy.permits,
            phase_now=lambda: calls.append("phase") or True,
            phase_member=lambda event: calls.append(("member", event)) or True)
        setattr(owner, selected._HOLD, {"permits": SimpleNamespace(verify=lambda: True)})
        self.assertIsNone(selected.selected_phase_authority(owner, "permits"))
        source = self.runtime.sources.lookup(self.history.event_ids[0])
        purpose = evaluation_purpose("run", "case", "before")
        self.assertTrue(owner.permits(source, purpose))
        self.assertEqual(calls, ["phase", ("member", source.evidence.ref_id)])

    def test_wrapped_original_predicate_gets_no_descriptor_without_changing_execution(self):
        original = self.runtime.source_policy.permits
        calls = []
        def custom(source, purpose):
            calls.append(source.evidence.ref_id)
            return original(source, purpose)
        self.runtime.source_policy.permits = custom
        self.assertIsNone(self.install())
        calls.clear()
        source = self.runtime.sources.lookup(self.history.event_ids[0])
        self.assertTrue(self.runtime.source_policy.permits(source, evaluation_purpose("run", "case", "before")))
        self.assertTrue(calls)

    def test_default_history_domain_keeps_existing_gates_without_descriptor(self):
        self.initial_authority.history_metadata_domain = "whole-stream-history-metadata-v1"
        self.initial_authority.maximum_history_sources = None
        self.assertIsNone(self.install())
        source = self.runtime.sources.lookup(self.history.event_ids[0])
        self.assertTrue(self.runtime.source_policy.permits(source, evaluation_purpose("run", "case", "before")))

    def test_replaced_controller_domain_cap_permissions_and_physical_readers_reject(self):
        descriptor = self.install()
        cases = (
            (self.lineage, "history_authority", copy(self.lineage.history_authority)),
            (self.lineage.history_authority, "history_metadata_domain", "whole-stream-history-metadata-v1"),
            (self.lineage.history_authority, "maximum_history_sources", 17),
            (self.lineage.history_authority, "permissions", copy(self.lineage.history_authority.permissions)),
            (self.runtime, "sources", copy(self.runtime.sources)),
            (self.runtime, "source_policy", copy(self.runtime.source_policy)),
            (self.runtime, "context_policy", copy(self.runtime.context_policy)),
            (self.runtime.sources, "connection", SimpleNamespace(execute=lambda *_: None)),
            (self.runtime.sources, "lookup", lambda *_: None),
            (self.runtime.log, "lookup_committed", lambda **_: None),
            (self.runtime.log.client, "get_stream", lambda **_: ()),
            (self.entry, "phase", "after"),
        )
        for owner, name, replacement in cases:
            fields = object.__getattribute__(owner, "__dict__")
            existed, original = name in fields, fields.get(name)
            with self.subTest(name=name):
                fields[name] = replacement
                with self.assertRaises(PermissionError):
                    descriptor.verify()
                if existed:
                    fields[name] = original
                else:
                    del fields[name]
                self.assertIs(descriptor.verify(), descriptor)

    def test_original_initial_controller_changes_reject(self):
        descriptor = self.install()
        self.initial_authority.maximum_history_sources = True
        with self.assertRaises(PermissionError):
            descriptor.verify()

    def test_independent_issuance_seal_rejects_descriptor_and_origin_field_swaps(self):
        descriptor = self.install()
        cases = ((descriptor, "_origin", copy(descriptor._origin)),
            (descriptor, "_parents", (descriptor,)),
            (descriptor, "_gate", copy(descriptor._gate)),
            (descriptor, "_reader", copy(descriptor._reader)),
            (descriptor._gate, "code", (lambda *_: True).__code__),
            (descriptor._origin, "phase", "after"),
            (descriptor._origin, "readers", ()),
            (descriptor._origin.readers[0], "owner", copy(descriptor._origin.readers[0].owner)))
        for owner, name, replacement in cases:
            original = object.__getattribute__(owner, name)
            with self.subTest(name=name):
                object.__setattr__(owner, name, replacement)
                with self.assertRaises(PermissionError):
                    selected.selected_phase_authority(self.runtime.source_policy, "permits")
                object.__setattr__(owner, name, original)
                descriptor.verify()

    def test_unknown_owner_lookup_and_copy_do_not_call_custom_hash_or_equality(self):
        class Custom:
            def __hash__(self):
                raise AssertionError("unknown owner hash called")
            def __eq__(self, other):
                raise AssertionError("unknown owner equality called")
            def permits(self, source, purpose):
                return True
        owner = Custom()
        install_native_phase_gate(owner, "permits", canonical_predicate=Custom.permits,
            phase_now=lambda: True, phase_member=lambda _: True)
        self.assertIsNone(selected.selected_phase_authority(owner, "permits"))
        copied = copy_native_phase_view(owner)
        self.assertIsNone(selected.selected_phase_authority(copied, "permits"))
        source = SimpleNamespace(evidence=SimpleNamespace(ref_id="fixture"))
        self.assertTrue(copied.permits(source, "fixture"))

    def test_private_inheritance_cannot_certify_unrelated_custom_phase_callbacks(self):
        self.install()
        target = copy(self.runtime.source_policy)
        del target.permits
        install_native_phase_gate(target, "permits", canonical_predicate=XTDBFormationPermissionPolicy.permits,
            phase_now=lambda: True, phase_member=lambda _: True)
        self.assertIs(selected._inherit_selected_phase_authority(self.runtime.source_policy, "permits", target), False)
        self.assertIsNone(selected.selected_phase_authority(target, "permits"))
        effects = []
        class UnknownTarget:
            def __getattribute__(self, name):
                effects.append(name)
                raise AssertionError("unknown target getter called")
        self.assertIs(selected._inherit_selected_phase_authority(
            self.runtime.source_policy, "permits", UnknownTarget()), False)
        self.assertEqual(effects, [])

    def test_lookup_rejects_modified_verifier_code_or_held_serializer(self):
        self.install()
        with patch.object(selected._Origin, "verify", new=lambda _: True):
            with self.assertRaisesRegex(PermissionError, "verifier class"):
                selected.selected_phase_authority(self.runtime.source_policy, "permits")
        with patch.object(selected, "_held_snapshot", new=lambda _: ()):
            with self.assertRaisesRegex(PermissionError, "native helper"):
                selected.selected_phase_authority(self.runtime.source_policy, "permits")

    def test_tampered_descriptor_fields_reject_before_custom_callbacks(self):
        descriptor = self.install()
        effects = []
        class Custom:
            def __hash__(self):
                effects.append("hash")
                raise AssertionError("custom hash called")
            def __eq__(self, other):
                effects.append("equality")
                raise AssertionError("custom equality called")
            def __iter__(self):
                effects.append("iteration")
                raise AssertionError("custom iteration called")
            @property
            def __dict__(self):
                effects.append("dictionary")
                raise AssertionError("custom dictionary called")
        for owner, name, replacement in ((descriptor, "_name", Custom()),
                (descriptor, "_gate", Custom()), (descriptor, "_reader", Custom()),
                (descriptor, "_origin", Custom()),
                (descriptor._origin, "readers", Custom()),
                (descriptor._origin, "readers", (Custom(),)),
                (descriptor._gate, "nested", Custom()),
                (descriptor._gate, "nested", (Custom(),))):
            original = object.__getattribute__(owner, name)
            with self.subTest(name=name):
                object.__setattr__(owner, name, replacement)
                with self.assertRaises(PermissionError):
                    selected.selected_phase_authority(self.runtime.source_policy, "permits")
                self.assertEqual(effects, [])
                object.__setattr__(owner, name, original)
                descriptor.verify()

    def test_held_plaintext_event_and_scope_mutations_reject_without_serialization(self):
        descriptor = self.install()
        mutations = ((self.history.sources[0], "plaintext", b"altered"),
            (self.history.sources[0].event, "event_type", "different"),
            (self.history.scope, "host_instance_id", "different"))
        for value, name, replacement in mutations:
            fields = object.__getattribute__(value, "__dict__")
            original = fields[name]
            with self.subTest(name=name):
                fields[name] = replacement
                with self.assertRaises(PermissionError):
                    descriptor.verify()
                fields[name] = original
                descriptor.verify()

    def test_original_membership_and_installed_callback_cells_are_bound(self):
        descriptor = self.install()
        cells = self.gate_cells()
        callback = cells["phase_member"].cell_contents
        cells["phase_member"].cell_contents = lambda _: True
        with self.assertRaises(PermissionError):
            descriptor.verify()
        cells["phase_member"].cell_contents = callback
        member_cells = dict(zip(callback.__code__.co_freevars, callback.__closure__))
        originals = member_cells["originals"].cell_contents
        removed = originals.pop(self.history.event_ids[0])
        with self.assertRaises(PermissionError):
            descriptor.verify()
        originals.clear()
        originals.update({source.event.event_id: source.event for source in self.history.sources})
        self.assertIs(removed, self.history.sources[0].event)
        descriptor.verify()

    def test_forged_descriptor_and_unissued_manual_gate_copy_are_not_native(self):
        descriptor = self.install()
        forged = replace(descriptor)
        with self.assertRaisesRegex(PermissionError, "privately issued"):
            forged.verify()
        copied = copy(self.runtime.source_policy)
        copied.permits = MethodType(self.runtime.source_policy.permits.__func__, copied)
        self.assertIsNone(selected.selected_phase_authority(copied, "permits"))

    def test_copy_preserves_original_gate_owner_and_rejects_later_original_tampering(self):
        descriptor = self.install()
        owner = self.runtime.source_policy
        copied = copy_native_phase_view(owner)
        copied_descriptor = selected.selected_phase_authority(copied, "permits")
        self.assertIsNot(copied_descriptor, descriptor)
        self.assertIs(copied_descriptor._origin, descriptor._origin)
        self.assertIs(copied.permits.__self__, copied)
        source = self.runtime.sources.lookup(self.history.event_ids[0])
        self.assertTrue(copied.permits(source, evaluation_purpose("run", "case", "before")))
        owner.permits = lambda *_: True
        with self.assertRaises(PermissionError):
            copied_descriptor.verify()
        with self.assertRaises(PermissionError):
            copied.permits(source, evaluation_purpose("run", "case", "before"))

    def test_transferred_selected_algorithm_retains_origin_and_live_callbacks(self):
        descriptor = self.install()
        from flora.selected.selected_context import SelectedJudgmentContextPolicy
        target = copy(self.runtime.context_policy)
        target.__class__ = SelectedJudgmentContextPolicy
        del target.allow_event
        self.assertTrue(transfer_native_phase_gate(self.runtime.context_policy, "allow_event", target,
            expected_original_predicate=RegisteredJudgmentContextPolicy.allow_event,
            selected_predicate=SelectedJudgmentContextPolicy.allow_event))
        inherited = selected.selected_phase_authority(target, "allow_event")
        self.assertIs(inherited._origin, descriptor._origin)
        before = len(self.fixture.client.reads)
        with self.assertRaisesRegex(PermissionError, "explicit evidence view"):
            target.allow_event(self.history.event_ids[0], "personal_judgment")
        self.assertGreater(len(self.fixture.client.reads), before)
        target.allow_event = lambda *_: True
        with self.assertRaises(PermissionError):
            inherited.verify()

    def test_private_issuance_registry_does_not_retain_closed_owner_cycles(self):
        descriptor = self.install()
        owner = self.runtime.source_policy
        owner_ref, descriptor_ref = ref(owner), ref(descriptor)
        self.assertIn((id(owner), "permits"), selected._ISSUED)
        del descriptor, owner
        del self.runtime, self.lineage
        gc.collect()
        self.assertIsNone(owner_ref())
        self.assertIsNone(descriptor_ref())


if __name__ == "__main__":
    unittest.main()
