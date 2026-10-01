"""Private identity for an actual selected-history phase producer.

An issued descriptor recognizes bindings only. It stores no successful allow,
head, qualification, private-read lease or metadata observation. Existing gates
still run their phase and member predicates on every invocation.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import CodeType, FunctionType, MethodType
from weakref import ref

from .comparison_custody import SelectedRunEvidencePolicy, XTDBComparisonCustody
from .experience import KurrentExperienceLog
from .formation_policy import XTDBFormationPermissionPolicy
from .formation_registry import XTDBFormationSourceRegistry
from .judgment_context import RegisteredJudgmentContextPolicy
from .native_phase_gate import _CREATED_GATES, _ORIGINAL_GATE_CODE, transfer_native_phase_gate
from .native_reads import SelectedNativeReadServices
from .selected_history_fence import (
    DOMAIN, _held_snapshot, _require_held_contracts, selected_phase_member,
)
from .source_closure import _ReaderBinding, _native_snapshot, _require_native_contracts


_ABSENT = object()
_ISSUED = {}
_TOKEN = object()
_HOLD = "_selected_phase_authority_hold"
_INSTALL = SelectedNativeReadServices._install_phase_source_gate
_INSTALL_CODE = _INSTALL.__code__
_CALLBACK_CODES = {code.co_name: code for code in _INSTALL_CODE.co_consts
                   if type(code) is CodeType and code.co_name in {
                       "phase_binding", "phase_now", "phase_member"}}
# There are selected and legacy phase_member bodies. Select the one which
# actually resolves bounded original membership, rather than whole replay.
_CALLBACK_CODES["phase_member"] = next(code for code in _INSTALL_CODE.co_consts
    if type(code) is CodeType and code.co_name == "phase_member"
    and "selected_phase_member" in code.co_freevars)
_CANONICAL = {
    SelectedRunEvidencePolicy: ("authorize_history", "authorize_history_metadata"),
    XTDBComparisonCustody: ("_key", "metadata", "metadata_selected"),
    XTDBFormationSourceRegistry: ("_key", "_fetch", "_decode", "lookup",
        "lookup_commitment", "raw_metadata", "raw_reference"),
    XTDBFormationPermissionPolicy: ("_key", "_fetch", "_decode", "_head",
        "_stored_action", "current_action", "permits"),
    KurrentExperienceLog: ("lookup_committed", "replay", "replay_committed"),
}
_METHODS = tuple((cls, name, getattr(cls, name), getattr(cls, name).__code__)
    for cls, names in _CANONICAL.items() for name in names)
_SELECTED_MEMBER = selected_phase_member
_SELECTED_MEMBER_CODE = selected_phase_member.__code__
_TRANSFER_CODE = next(code for code in transfer_native_phase_gate.__code__.co_consts
    if type(code) is CodeType and code.co_name == "gate")


def _fields(owner):
    values = object.__getattribute__(owner, "__dict__")
    if type(values) is not dict or any(type(key) is not str for key in values):
        raise PermissionError("selected phase needs ordinary native owner fields")
    return values


@dataclass(frozen=True)
class _FunctionBinding:
    function: object
    code: object
    closure: tuple
    globals: tuple
    nested: tuple

    @classmethod
    def capture(cls, function):
        if type(function) is not FunctionType:
            raise TypeError("selected phase callback must be an actual native function")
        return cls(function, function.__code__,
            tuple((cell, cell.cell_contents) for cell in function.__closure__ or ()),
            tuple((name, function.__globals__.get(name, _ABSENT))
                  for name in set(function.__code__.co_names)),
            tuple(cls.capture(cell.cell_contents) for cell in function.__closure__ or ()
                  if type(cell.cell_contents) is FunctionType and cell.cell_contents is not function))

    def verify(self):
        if (self.function.__code__ is not self.code
                or tuple(self.function.__closure__ or ()) != tuple(cell for cell, _ in self.closure)
                or any(cell.cell_contents is not value for cell, value in self.closure)
                or any(self.function.__globals__.get(name, _ABSENT) is not value
                       for name, value in self.globals)):
            raise PermissionError("selected phase actual callback binding changed")
        for nested in self.nested:
            nested.verify()


def _native_method(owner, name, expected):
    method = getattr(owner, name)
    if (type(method) is not MethodType or method.__self__ is not owner
            or method.__func__ is not expected):
        raise TypeError("selected phase has a custom native reader")


def _gate_binding(owner, name, *, original=True):
    method = getattr(owner, name)
    if (type(method) is not MethodType or method.__self__ is not owner
            or method.__func__ not in _CREATED_GATES
            or original and method.__func__.__code__ is not _ORIGINAL_GATE_CODE):
        raise TypeError("selected phase needs its privately created actual gate")
    binding = _FunctionBinding.capture(method.__func__)
    return method, binding, dict(zip(method.__func__.__code__.co_freevars,
                                   (cell.cell_contents for cell in method.__func__.__closure__)))


class _Origin:
    def __init__(self, *, runtime, lineage, entry, history, initial_authority,
                 original_permissions, phase_now, phase_member):
        _require_native_contracts()
        _require_held_contracts()
        self.runtime, self.lineage, self.entry, self.history = runtime, lineage, entry, history
        self.authority = authority = _fields(lineage)["history_authority"]
        self.initial_authority, self.original_permissions = initial_authority, original_permissions
        self.registry, self.log = registry, log = _fields(runtime)["sources"], _fields(runtime)["log"]
        self.permissions = permissions = _fields(authority)["permissions"]
        self.custody = custody = _fields(authority)["custody"]
        if (type(authority) is not SelectedRunEvidencePolicy
                or type(initial_authority) is not SelectedRunEvidencePolicy
                or type(custody) is not XTDBComparisonCustody
                or any(type(policy) is not XTDBFormationPermissionPolicy
                       for policy in (permissions, original_permissions))
                or type(registry) is not XTDBFormationSourceRegistry
                or type(log) is not KurrentExperienceLog):
            raise TypeError("selected phase origin has custom or unknown physical owners")
        self.cap = _fields(authority)["maximum_history_sources"]
        if (type(self.cap) is not int or self.cap < 2
                or type(authority.history_metadata_domain) is not str
                or authority.history_metadata_domain != DOMAIN
                or initial_authority.history_metadata_domain != DOMAIN
                or initial_authority.maximum_history_sources != self.cap):
            raise TypeError("selected phase origin lacks the exact selected domain and cap")
        self.connection = registry.connection
        self.scope = _native_snapshot(registry.scope)
        self.namespace = registry.authority_namespace_id
        if (permissions.registry is not registry or permissions.connection is not self.connection
                or custody.registry is not registry or custody.log is not log
                or custody.connection is not self.connection
                or any(_native_snapshot(value.scope) != self.scope
                       for value in (runtime, log, custody, permissions, initial_authority.custody))
                or any(value.authority_namespace_id != self.namespace
                       for value in (runtime, custody, permissions))):
            raise TypeError("selected phase actual origins do not share their physical scope")
        self.held = _held_snapshot(history)
        self.history_sha256 = history.digest()
        self.event_ids = history.event_ids
        self.case_id, self.phase = entry.case_id, entry.phase
        self.callbacks = phase_now, phase_member
        now_cells = dict(zip(phase_now.__code__.co_freevars,
                            (cell.cell_contents for cell in phase_now.__closure__ or ())))
        member_cells = dict(zip(phase_member.__code__.co_freevars,
                               (cell.cell_contents for cell in phase_member.__closure__ or ())))
        phase_binding = now_cells.get("phase_binding")
        if (phase_now.__code__ is not _CALLBACK_CODES["phase_now"]
                or phase_member.__code__ is not _CALLBACK_CODES["phase_member"]
                or type(phase_binding) is not FunctionType
                or phase_binding.__code__ is not _CALLBACK_CODES["phase_binding"]
                or member_cells.get("phase_binding") is not phase_binding
                or any(now_cells.get(key) is not value for key, value in (
                    ("authority", authority), ("entry", entry), ("history", history)))
                or any(member_cells.get(key) is not value for key, value in (
                    ("phase_registry", registry), ("phase_log", log),
                    ("phase_permissions", permissions), ("selected_phase_member", _SELECTED_MEMBER)))):
            raise TypeError("selected phase needs callbacks from its actual native installer")
        self.originals = member_cells["originals"]
        self.original_snapshot = self._original_snapshot()
        self.function_bindings = tuple(_FunctionBinding.capture(value)
            for value in (phase_now, phase_member, phase_binding))
        bindings = []
        for owner in (authority, initial_authority, custody, registry, permissions,
                      original_permissions, log):
            for name in _CANONICAL[type(owner)]:
                expected = next(function for cls, port, function, _ in _METHODS
                    if cls is type(owner) and port == name)
                _native_method(owner, name, expected)
                bindings.append(_ReaderBinding.capture(owner, name))
        for owner, names in (
            (runtime, ("sources", "log", "source_policy", "context_policy", "scope", "authority_namespace_id")),
            (lineage, ("history_authority",)), (entry, ("case_id", "phase")),
            (authority, ("custody", "permissions", "run_id", "history_metadata_domain", "maximum_history_sources")),
            (initial_authority, ("custody", "permissions", "run_id", "history_metadata_domain", "maximum_history_sources")),
            (custody, ("connection", "registry", "log", "objects", "raw_custody", "scope", "scope_digest", "authority_namespace_id")),
            (registry, ("connection", "scope", "scope_digest", "authority_namespace_id")),
            (permissions, ("connection", "registry", "scope", "scope_digest", "authority_namespace_id")),
            (original_permissions, ("connection", "registry", "scope", "scope_digest", "authority_namespace_id")),
            (log, ("client", "stream", "scope")),
            (registry.connection, ("execute",)), (log.client, ("get_stream",)),
            (custody.objects, ("scope", "namespace")),
        ):
            bindings.extend(_ReaderBinding.capture(owner, name) for name in names)
        self.readers = tuple(bindings)

    def _original_snapshot(self):
        if (type(self.originals) is not dict or any(type(key) is not str for key in self.originals)
                or tuple(self.originals) != self.event_ids):
            raise PermissionError("selected phase original membership changed")
        return tuple((key, _held_snapshot(value)) for key, value in self.originals.items())

    def verify(self):
        _require_descriptor_contracts()
        _require_native_contracts()
        _require_held_contracts()
        if (SelectedNativeReadServices._install_phase_source_gate is not _INSTALL
                or _INSTALL.__code__ is not _INSTALL_CODE
                or selected_phase_member is not _SELECTED_MEMBER
                or _SELECTED_MEMBER.__code__ is not _SELECTED_MEMBER_CODE
                or any(getattr(cls, name) is not function or function.__code__ is not code
                       for cls, name, function, code in _METHODS)):
            raise PermissionError("selected phase canonical producer code changed")
        for binding in self.readers + self.function_bindings:
            binding.verify()
        if (any(_native_snapshot(owner.scope) != self.scope
                for owner in (self.runtime, self.registry, self.permissions, self.log, self.custody))
                or _held_snapshot(self.history) != self.held
                or self._original_snapshot() != self.original_snapshot):
            raise PermissionError("selected phase held material or scope changed")


@dataclass(frozen=True)
class SelectedPhaseAuthorityDescriptor:
    """Private-issued producer identity; verification performs no live IO."""
    _token: object
    _origin: object
    _owner: object
    _name: str
    _method: object
    _gate: object
    _parents: tuple
    _reader: object

    @property
    def case_id(self):
        return self._origin.case_id

    @property
    def phase(self):
        return self._origin.phase

    @property
    def history_sha256(self):
        return self._origin.history_sha256

    @property
    def original_event_ids(self):
        return self._origin.event_ids

    def verify(self):
        _require_descriptor_contracts()
        if type(self) is not SelectedPhaseAuthorityDescriptor:
            raise PermissionError("selected phase descriptor native class changed")
        if type(self._name) is not str or self._token is not _TOKEN:
            raise PermissionError("selected phase descriptor native identity changed")
        registered = _ISSUED.get((id(self._owner), self._name))
        if (registered is None
                or registered.owner() is not self._owner or registered.descriptor() is not self):
            raise PermissionError("selected phase descriptor was not privately issued")
        # Reject replaced fields before looking inside any supplied replacement.
        # This ordering prevents custom hash, equality or dictionary callbacks
        # from running merely because someone mutated a frozen issued object.
        _verify_identity(self, registered.descriptor_seal[0], SelectedPhaseAuthorityDescriptor)
        _verify_function_seal(self._gate, registered.descriptor_seal[1])
        _verify_identity(self._reader, registered.descriptor_seal[2], _ReaderBinding)
        _verify_origin_seal(self._origin, registered.origin_seal)
        self._origin.verify()
        for parent in self._parents:
            parent.verify()
        self._reader.verify()
        self._gate.verify()
        method = getattr(self._owner, self._name)
        if (type(method) is not MethodType or method.__self__ is not self._owner
                or method.__func__ is not self._method.__func__):
            raise PermissionError("selected phase installed gate owner changed")
        return self


@dataclass(frozen=True)
class _Registration:
    owner: object
    descriptor: object
    descriptor_seal: tuple
    origin_seal: tuple


def _identity_seal(value):
    """Independent field identities; no strong owner references are retained."""
    fields = _fields(value)
    return type(value), id(fields), tuple((name, type(item), id(item))
        for name, item in fields.items())


def _function_seal(binding):
    return _identity_seal(binding), tuple(_function_seal(value) for value in binding.nested)


def _verify_identity(value, expected, native_class):
    if type(value) is not native_class or _identity_seal(value) != expected:
        raise PermissionError("selected phase issued descriptor or origin fields changed")


def _verify_function_seal(binding, expected):
    _verify_identity(binding, expected[0], _FunctionBinding)
    for value, nested in zip(binding.nested, expected[1]):
        _verify_function_seal(value, nested)


def _origin_seal(origin):
    return (_identity_seal(origin), tuple(_identity_seal(value) for value in origin.readers),
            tuple(_function_seal(value) for value in origin.function_bindings))


def _verify_origin_seal(origin, expected):
    _verify_identity(origin, expected[0], _Origin)
    for value, snapshot in zip(origin.readers, expected[1]):
        _verify_identity(value, snapshot, _ReaderBinding)
    for value, snapshot in zip(origin.function_bindings, expected[2]):
        _verify_function_seal(value, snapshot)


def _descriptor_seal(descriptor):
    return (_identity_seal(descriptor), _function_seal(descriptor._gate),
            _identity_seal(descriptor._reader))


def _register(owner, name, origin, parents=()):
    method, gate, _ = _gate_binding(owner, name, original=False)
    descriptor = SelectedPhaseAuthorityDescriptor(_TOKEN, origin, owner, name, method,
        gate, parents, _ReaderBinding.capture(owner, name))
    # Weak issuance references do not keep closed sessions alive. Owner-held
    # descriptors and gate/origin cycles are collected together normally.
    key = id(owner), name
    def discard(weak_owner):
        registered = _ISSUED.get(key)
        if registered is not None and registered.owner is weak_owner:
            del _ISSUED[key]
    _ISSUED[key] = _Registration(ref(owner, discard), ref(descriptor),
        _descriptor_seal(descriptor), _origin_seal(origin))
    held = dict(_fields(owner).get(_HOLD, {}))
    held[name] = descriptor
    setattr(owner, _HOLD, held)
    descriptor.verify()
    return descriptor


def _issue_selected_phase_authority(*, runtime, lineage, entry, history,
        initial_authority, original_permissions, phase_now, phase_member):
    """Optional recognition only: unsupported existing gates keep running."""
    try:
        origin = _Origin(runtime=runtime, lineage=lineage, entry=entry, history=history,
            initial_authority=initial_authority, original_permissions=original_permissions,
            phase_now=phase_now, phase_member=phase_member)
        if (type(runtime.source_policy) is not XTDBFormationPermissionPolicy
                or type(runtime.context_policy) is not RegisteredJudgmentContextPolicy):
            raise TypeError("selected phase installation has custom gate owners")
        for owner, name, predicate in ((runtime.source_policy, "permits", XTDBFormationPermissionPolicy.permits),
                (runtime.context_policy, "allow_event", RegisteredJudgmentContextPolicy.allow_event)):
            method, _, cells = _gate_binding(owner, name)
            original = cells.get("original")
            if (cells.get("owner") is not owner or cells.get("name") != name
                    or cells.get("canonical") is not True
                    or type(original) is not MethodType or original.__self__ is not owner
                    or original.__func__ is not predicate or cells.get("installed") != method
                    or cells.get("phase_now") is not phase_now or cells.get("phase_member") is not phase_member):
                raise TypeError("selected phase installed callbacks are custom or detached")
        origin.verify()
    except (AttributeError, KeyError, PermissionError, TypeError, ValueError):
        return False
    _register(runtime.source_policy, "permits", origin)
    _register(runtime.context_policy, "allow_event", origin)
    return True


def selected_phase_authority(owner, name):
    """Return a current privately issued identity, or None for unknown gates."""
    _require_descriptor_contracts()
    if type(name) is not str:
        return None
    registered = _ISSUED.get((id(owner), name))
    if registered is None or registered.owner() is not owner:
        return None
    descriptor = registered.descriptor()
    return None if descriptor is None else _DESCRIPTOR_VERIFY(descriptor)


def _inherit_selected_phase_authority(source_owner, name, target_owner):
    descriptor = selected_phase_authority(source_owner, name)
    if descriptor is None:
        return False
    from .selected_context import SelectedJudgmentContextPolicy
    if type(target_owner) not in (type(source_owner), SelectedJudgmentContextPolicy):
        return False
    method, _, cells = _gate_binding(target_owner, name, original=False)
    if method.__func__ is not descriptor._method.__func__:
        checker = cells.get("binding_current")
        binding_cells = ({} if type(checker) is not FunctionType else
            dict(zip(checker.__code__.co_freevars,
                     (cell.cell_contents for cell in checker.__closure__ or ()))))
        if (type(target_owner) is not SelectedJudgmentContextPolicy
                or method.__func__.__code__ is not _TRANSFER_CODE
                or binding_cells.get("source_owner") is not source_owner or cells.get("name") != name
                or binding_cells.get("source_gate") is not descriptor._method.__func__
                or binding_cells.get("source_installed") != descriptor._method
                or cells.get("phase_now") is not descriptor._origin.callbacks[0]
                or cells.get("phase_member") is not descriptor._origin.callbacks[1]
                or cells.get("selected_predicate") is not SelectedJudgmentContextPolicy.allow_event):
            return False
    _register(target_owner, name, descriptor._origin, (descriptor,))
    return True


def _require_descriptor_contracts():
    for name, function, code in _HELPERS:
        if globals().get(name) is not function or function.__code__ is not code:
            raise PermissionError("selected phase descriptor verifier binding changed")
    for cls, shape in _CLASS_SHAPES:
        current = vars(cls)
        extra = "__slotnames__" not in dict(shape) and "__slotnames__" in current
        if (len(current) != len(shape) + int(extra)
                or any(current.get(name) is not value for name, value in shape)
                or extra and (type(current["__slotnames__"]) is not list or current["__slotnames__"])):
            raise PermissionError("selected phase descriptor verifier class changed")
    if any(function.__code__ is not code for function, code in _CLASS_CODES):
        raise PermissionError("selected phase descriptor verifier code changed")
    if any(globals().get(name) is not value or type(value) is FunctionType and value.__code__ is not code
           for name, value, code in _EXTERNAL_HELPERS):
        raise PermissionError("selected phase descriptor native helper changed")


_DESCRIPTOR_VERIFY = SelectedPhaseAuthorityDescriptor.verify
_HELPERS = tuple((function.__name__, function, function.__code__) for function in (
    _fields, _native_method, _gate_binding, _identity_seal, _origin_seal,
    _function_seal, _verify_identity, _verify_function_seal, _verify_origin_seal,
    _descriptor_seal, _register, _issue_selected_phase_authority, selected_phase_authority,
    _inherit_selected_phase_authority, _require_descriptor_contracts))
_CLASS_SHAPES = tuple((cls, tuple(vars(cls).items())) for cls in (
    _FunctionBinding, _Origin, SelectedPhaseAuthorityDescriptor, _Registration))
_CLASS_CODES = tuple((function, function.__code__) for _, shape in _CLASS_SHAPES
    for _, value in shape for function in (
        (value.fget, value.fset, value.fdel) if type(value) is property else
        (value.__func__ if isinstance(value, (classmethod, staticmethod)) else value,))
    if type(function) is FunctionType)
_EXTERNAL_HELPERS = tuple((name, value, value.__code__ if type(value) is FunctionType else None)
    for name, value in (("_ReaderBinding", _ReaderBinding), ("_native_snapshot", _native_snapshot),
        ("_held_snapshot", _held_snapshot), ("_require_native_contracts", _require_native_contracts),
        ("_require_held_contracts", _require_held_contracts), ("_DESCRIPTOR_VERIFY", _DESCRIPTOR_VERIFY)))
