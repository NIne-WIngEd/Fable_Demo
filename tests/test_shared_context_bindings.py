"""One fresh walk of real captured functions and reader bindings."""
import sys
import unittest
from unittest.mock import patch

from flora.selected import selected_authority_frame as frames
from flora.selected import selected_phase_authority as phase


_BOUND_GLOBAL = object()


class _Owner:
    def read(self):
        raise AssertionError("pure verification executed a reader")


class SharedContextBindingTest(unittest.TestCase):
    def setUp(self):
        self.owner = _Owner()
        self.reader = phase._ReaderBinding.capture(self.owner, "read")
        readers = (self.reader,)
        def leaf():
            return readers, _BOUND_GLOBAL
        def middle():
            return leaf()
        def root():
            return middle()
        self.binding = phase._FunctionBinding.capture(root)
        frames._register_binding(self.binding)
        self.middle = self.binding.nested[0]
        self.leaf = self.middle.nested[0]

    def verify(self):
        frames._require_frame_contracts()
        frames._verify_binding(self.binding)

    def test_each_function_and_reader_is_checked_once_per_fresh_walk(self):
        # The pre-repair own checks live in verify(); after extraction they
        # live in _verify_shallow(). Observe actual code, never replace it.
        own_check = getattr(phase._FunctionBinding, "_verify_shallow", phase._FunctionBinding.verify)
        checks, reader_checks, effects = [], [], []
        function_codes = {item.function.__code__ for item in (self.binding, self.middle, self.leaf)}
        def observe(frame, event, argument):
            if event == "call":
                if frame.f_code is own_check.__code__:
                    checks.append(id(frame.f_locals["self"]))
                elif frame.f_code is phase._ReaderBinding.verify.__code__:
                    reader_checks.append(id(frame.f_locals["self"]))
                elif frame.f_code in function_codes:
                    effects.append("captured function")
        previous = sys.getprofile()
        try:
            sys.setprofile(observe)
            self.verify()
            self.verify()
        finally:
            sys.setprofile(previous)
        expected = [id(self.leaf), id(self.middle), id(self.binding)]
        self.assertEqual(checks, expected * 2)
        self.assertEqual(reader_checks, [id(self.reader)] * 2)
        self.assertEqual(effects, [])

    def test_later_walk_rejects_leaf_code_closure_and_global_mutation(self):
        self.verify()
        original_code = self.leaf.function.__code__
        readers = ()
        def replacement():
            return readers, None
        try:
            self.leaf.function.__code__ = replacement.__code__
            with self.assertRaisesRegex(PermissionError, "actual callback binding changed"):
                self.verify()
        finally:
            self.leaf.function.__code__ = original_code
        cell, original = self.leaf.closure[0]
        try:
            cell.cell_contents = ()
            with self.assertRaisesRegex(PermissionError, "actual callback binding changed"):
                self.verify()
        finally:
            cell.cell_contents = original
        with patch.dict(globals(), {"_BOUND_GLOBAL": object()}):
            with self.assertRaisesRegex(PermissionError, "actual callback binding changed"):
                self.verify()
        self.verify()

    def test_replaced_capture_and_reader_fields_reject_before_effects(self):
        self.verify()
        effects = []
        class Effectful:
            def __getattribute__(self, name):
                effects.append(name)
                raise AssertionError("replacement dereferenced")
            def __eq__(self, other):
                effects.append("equality")
                raise AssertionError("replacement compared")
        for owner, field, value in ((self.middle, "nested", (Effectful(),)),
                (self.leaf, "function", Effectful()), (self.reader, "owner", Effectful())):
            original = object.__getattribute__(owner, field)
            try:
                object.__setattr__(owner, field, value)
                with self.subTest(field=field), self.assertRaisesRegex(PermissionError, "captured owner fields changed"):
                    self.verify()
                self.assertEqual(effects, [])
            finally:
                object.__setattr__(owner, field, original)
        self.verify()

    def test_full_phase_binding_verification_still_rejects_leaf_mutation(self):
        self.binding.verify()
        cell, original = self.leaf.closure[0]
        try:
            cell.cell_contents = ()
            with self.assertRaisesRegex(PermissionError, "actual callback binding changed"):
                self.binding.verify()
        finally:
            cell.cell_contents = original
        self.binding.verify()

    def test_own_check_identity_and_code_are_pinned_before_execution(self):
        name = "_verify_shallow" if hasattr(phase._FunctionBinding, "_verify_shallow") else "verify"
        original = getattr(phase._FunctionBinding, name)
        effects = []
        def replacement(self, observed=effects):
            observed.append("changed own check")
        with patch.object(phase._FunctionBinding, name, new=replacement):
            with self.assertRaisesRegex(PermissionError, "verifier class changed"):
                self.verify()
        code = original.__code__
        try:
            original.__code__ = replacement.__code__
            with self.assertRaisesRegex(PermissionError, "verifier code changed"):
                self.verify()
        finally:
            original.__code__ = code
        self.assertEqual(effects, [])


if __name__ == "__main__":
    unittest.main()
