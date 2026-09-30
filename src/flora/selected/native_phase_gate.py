"""Copy-aware native phase predicates; no authority result is retained.

Only gates created here can be rebound to a same-call sampled metadata view.
Their phase callback and original predicate stay closed over their actual owner.
Arbitrary supplied predicates keep that owner and run again on every call.
"""
from __future__ import annotations

from copy import copy
from types import MethodType
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


def copy_native_phase_view(service):
    """Copy only our identified phase predicates onto the new metadata owner."""
    result = copy(service)
    for name in ("permits", "allow_event"):
        method = getattr(service, name, None)
        if (isinstance(method, MethodType) and method.__self__ is service
                and method.__func__ in _CREATED_GATES):
            setattr(result, name, MethodType(method.__func__, result))
    return result
