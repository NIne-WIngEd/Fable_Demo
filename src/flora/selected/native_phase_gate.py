"""Copy-aware native phase predicates; no authority result is retained.

Only gates created here can be rebound to a same-call sampled metadata view.
Their phase callback and original predicate stay closed over their actual owner.
Arbitrary supplied predicates keep that owner and run again on every call.
"""
from __future__ import annotations

from copy import copy
from types import CodeType, FunctionType, MethodType
from weakref import WeakSet


_CREATED_GATES: WeakSet = WeakSet()


def install_native_phase_gate(owner, name, *, canonical_predicate, phase_now, phase_member):
    """Install an actual phase callback around this owner's live predicate."""
    if name not in {"permits", "allow_event"}:
        raise ValueError("native phase gate has an unsupported predicate")
    original = getattr(owner, name)
    if not all(callable(value) for value in (original, canonical_predicate, phase_now, phase_member)):
        raise TypeError("native phase gate needs its actual predicate and phase callbacks")
    canonical = (isinstance(original, MethodType) and original.__self__ is owner
                 and original.__func__ is canonical_predicate)
    installed = None

    def gate(current, source, purpose):
        # The original owned wrapper stays fixed even while its metadata view
        # is copied. No mutable, separately supplied gate configuration exists.
        if getattr(owner, name) != installed:
            raise PermissionError("native phase predicate binding changed")
        event_id = source.evidence.ref_id if name == "permits" else source
        allowed = False
        if phase_now() and phase_member(event_id):
            # A known selected algorithm resolves rows through its current
            # sampled view. Custom callbacks retain their exact existing owner.
            result = (original.__func__(current, source, purpose) if canonical
                      else original(source, purpose))
            allowed = result is True
        if getattr(owner, name) != installed:
            raise PermissionError("native phase predicate binding changed during callback")
        return allowed

    installed = MethodType(gate, owner)
    _CREATED_GATES.add(gate)
    setattr(owner, name, installed)


_ORIGINAL_GATE_CODE = next(value for value in install_native_phase_gate.__code__.co_consts
                           if type(value) is CodeType and value.co_name == "gate")


def transfer_native_phase_gate(source_owner, name, target_owner, *,
                               expected_original_predicate, selected_predicate):
    """Preserve a known original phase gate around an explicit new algorithm.

    Only a gate created here around the exact expected original predicate can
    transfer. Arbitrary callbacks and nested/custom predicate chains reject.
    The source owner's installed gate must remain current before and after
    callbacks. The original phase/member functions run on every invocation.
    A same-call metadata copy may rebind the selected algorithm to its view;
    it never detaches the source gate's original owner or phase callbacks.
    """
    original = getattr(source_owner, name)
    if (isinstance(original, MethodType) and original.__self__ is source_owner
            and original.__func__ is expected_original_predicate):
        return False
    known = (isinstance(original, MethodType) and original.__self__ is source_owner
             and original.__func__ in _CREATED_GATES
             and original.__func__.__code__ is _ORIGINAL_GATE_CODE)
    if not known:
        raise TypeError("selected route cannot replace a custom source predicate")
    # Derive configuration from the actual installed closure. A separately
    # mutable function attribute cannot establish which phase callbacks run.
    cells = dict(zip(original.__func__.__code__.co_freevars, original.__func__.__closure__))
    if set(cells) != {"owner", "name", "original", "canonical", "phase_now", "phase_member", "installed"}:
        raise TypeError("selected route has an unsupported native phase closure")
    owner, port, predicate, canonical, phase_now, phase_member, source_installed = (
        cells[key].cell_contents for key in ("owner", "name", "original", "canonical",
                                            "phase_now", "phase_member", "installed"))
    if (owner is not source_owner or port != name or canonical is not True
            or not isinstance(predicate, MethodType) or predicate.__self__ is not source_owner
            or predicate.__func__ is not expected_original_predicate or original != source_installed):
        raise TypeError("selected route cannot replace a custom or nested native phase predicate")
    selected = getattr(target_owner, name)
    if (not isinstance(selected, MethodType) or selected.__self__ is not target_owner
            or selected.__func__ is not selected_predicate):
        raise TypeError("selected route needs its exact selected predicate")
    installed = None
    closure_binding = tuple((cells[key], cells[key].cell_contents) for key in sorted(cells))
    source_gate = original.__func__
    predicate_code = selected_predicate.__code__
    source_predicate_code = expected_original_predicate.__code__
    callback_codes = tuple((value, value.__code__) for candidate in (phase_now, phase_member)
        for value in (candidate.__func__ if isinstance(candidate, MethodType) else candidate,)
        if isinstance(value, FunctionType))

    def binding_current():
        if (source_gate.__code__ is not _ORIGINAL_GATE_CODE
                or selected_predicate.__code__ is not predicate_code
                or expected_original_predicate.__code__ is not source_predicate_code
                or any(cell.cell_contents is not value for cell, value in closure_binding)
                or any(function.__code__ is not code for function, code in callback_codes)
                or getattr(source_owner, name) != source_installed
                or getattr(target_owner, name) != installed):
            raise PermissionError("selected route original phase predicate binding changed")

    def gate(current, source, purpose):
        binding_current()
        event_id = source.evidence.ref_id if name == "permits" else source
        active = phase_now()
        binding_current()
        member = phase_member(event_id) if active else False
        binding_current()
        allowed = selected_predicate(current, source, purpose) is True if active and member else False
        binding_current()
        return allowed

    installed = MethodType(gate, target_owner)
    _CREATED_GATES.add(gate)
    setattr(target_owner, name, installed)
    from .selected_phase_authority import _inherit_selected_phase_authority
    _inherit_selected_phase_authority(source_owner, name, target_owner)
    return True


def copy_native_phase_view(service):
    """Copy only our identified phase predicates onto the new metadata owner."""
    result = copy(service)
    for name in ("permits", "allow_event"):
        method = getattr(service, name, None)
        if (isinstance(method, MethodType) and method.__self__ is service
                and method.__func__ in _CREATED_GATES):
            setattr(result, name, MethodType(method.__func__, result))
            from .selected_phase_authority import _inherit_selected_phase_authority
            _inherit_selected_phase_authority(service, name, result)
    return result
