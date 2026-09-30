"""Run-local authenticated bytes, with uncached current authority on every use.

An issued object proves only that these exact held originals were authenticated
by the actual selected custody path. It is neither a permission grant nor a
wire token. The private issuance table retains no positive authority answers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from weakref import WeakKeyDictionary

from ..comparison_run import HistorySnapshot, PairedRunPlan, _sha


@dataclass(frozen=True)
class _IssuedHistory:
    policy: object = field(repr=False)
    plan: PairedRunPlan = field(repr=False)
    history: HistorySnapshot = field(repr=False)
    case_id: str
    phase: str
    plan_sha256: str
    history_sha256: str
    question_sha256: str
    controllers: tuple = field(repr=False)


_ISSUED: WeakKeyDictionary = WeakKeyDictionary()
_UNSPECIFIED = object()


def _controllers(policy):
    custody, permissions = policy.custody, policy.permissions
    registry, log, objects = custody.registry, custody.log, custody.objects
    lineage = policy.native_lineage
    authority = policy.final_authority
    final_controllers = () if authority is None else (
        authority.store, authority.store.comparison, authority.plan,
        authority.authorize_plan, authority.require_evaluation, authority.authorize_evaluation,
        authority.authorize_capture_custody, authority.authorize_attempt_capture)
    return (policy.run_id, custody, permissions, registry, log, objects,
        custody.raw_custody, custody.connection, custody.scope,
        registry.connection, permissions.connection, permissions.registry,
        registry._fetch, permissions._fetch, custody.connection.execute,
        getattr(log, "client", None),
        custody.raw_custody.registry, custody.raw_custody.objects,
        objects.backend, objects.get, objects._identity, objects._key,
        custody.authority_namespace_id, policy.final_authority, lineage,
        policy.require_final_authority, policy.authorize_history,
        policy.authorize_history_metadata, policy.authorize_context,
        custody.metadata, custody.require_final_authority,
        custody.raw_custody.read, log.replay, log.replay_committed,
        registry.lookup, registry.raw_reference, registry.raw_metadata,
        permissions.current_action, permissions.permits,
        None if lineage is None else lineage.authorize_context, final_controllers)


class AuthenticatedSelectedHistory:
    """Opaque local ownership of exact authenticated bytes, never an allow lease."""
    __slots__ = ("__weakref__",)

    def __repr__(self):
        return "AuthenticatedSelectedHistory(<private local history>)"

    def __init__(self, *, policy, plan: PairedRunPlan, case_id: str,
                 phase: str, history: HistorySnapshot):
        from .comparison_custody import SelectedRunEvidencePolicy, XTDBComparisonCustody
        from .formation_registry import RegisteredEncryptedFormationCustody
        from .object_store import EncryptedObjectPlane
        if (not isinstance(policy, SelectedRunEvidencePolicy)
                or not isinstance(plan, PairedRunPlan)
                or not isinstance(history, HistorySnapshot)):
            raise TypeError("authenticated history requires actual selected custody")
        plan.validate()
        if (policy.custody.connection is not policy.custody.registry.connection
                or policy.custody.connection is not policy.permissions.connection
                or policy.permissions.registry is not policy.custody.registry):
            raise PermissionError("history issuance requires one actual owned selected metadata connection")
        if (getattr(policy.require_final_authority, "__self__", None) is not policy
                or getattr(policy.require_final_authority, "__func__", None)
                    is not SelectedRunEvidencePolicy.require_final_authority
                or getattr(policy.custody.require_final_authority, "__self__", None) is not policy.custody
                or getattr(policy.custody.require_final_authority, "__func__", None)
                    is not XTDBComparisonCustody.require_final_authority):
            raise PermissionError("history authentication requires actual selected final authority controllers")
        authority = policy.final_authority
        if authority is not None:
            from .experiment_preregistration import RegisteredExperimentFinalBinding
            if (type(authority) is not RegisteredExperimentFinalBinding
                    or any(getattr(getattr(authority, name), "__self__", None) is not authority
                        or getattr(getattr(authority, name), "__func__", None)
                            is not getattr(RegisteredExperimentFinalBinding, name)
                        for name in ("authorize_plan", "require_evaluation", "authorize_evaluation",
                            "authorize_capture_custody", "authorize_attempt_capture"))):
                raise PermissionError("history authentication requires actual sealed final controllers")
        raw, objects = policy.custody.raw_custody, policy.custody.objects
        if (type(raw) is not RegisteredEncryptedFormationCustody
                or type(objects) is not EncryptedObjectPlane
                or getattr(raw.read, "__self__", None) is not raw
                or getattr(raw.read, "__func__", None) is not RegisteredEncryptedFormationCustody.read
                or getattr(objects.get, "__self__", None) is not objects
                or getattr(objects.get, "__func__", None) is not EncryptedObjectPlane.get
                or getattr(objects._identity, "__func__", None) is not EncryptedObjectPlane._identity
                or raw.registry is not policy.custody.registry or raw.objects is not objects):
            raise PermissionError("history authentication requires its actual registered AEAD custody reader")
        case = next((case for case in plan.protocol.cases if case.case_id == case_id), None)
        if (phase not in {"before", "after"} or case is None
                or history.scope.host_instance_id != case.host_id
                or history.digest() != getattr(case, f"{phase}_history_sha256")):
            raise PermissionError("authenticated history differs from its frozen phase")
        frozen_plan, frozen_history = plan.digest(), history.digest()
        frozen_question = plan.question_sha256_by_case[case_id]
        controllers = _controllers(policy)
        policy.require_final_authority(plan=plan)
        # Invoke the actual full selected implementation. A caller cannot issue
        # a proof by replacing authorize_history with a boolean allow callback.
        if SelectedRunEvidencePolicy.authorize_history(policy,
                case_id=case_id, phase=phase, history=history) is not True:
            raise PermissionError("original history failed actual custody authentication")
        if SelectedRunEvidencePolicy.authorize_history_metadata(policy,
                case_id=case_id, phase=phase, history=history) is not True:
            raise PermissionError("original history lacks actual current selected authority")
        if (_controllers(policy) != controllers or plan.digest() != frozen_plan
                or history.digest() != frozen_history
                or plan.question_sha256_by_case.get(case_id) != frozen_question):
            raise PermissionError("history custody changed during authentication")
        _ISSUED[self] = _IssuedHistory(policy, plan, history, case_id, phase,
            frozen_plan, frozen_history, frozen_question, controllers)


def _bound_history(proof, *, policy, plan: PairedRunPlan,
        case_id: str, phase: str, question: bytes, history=None,
        scope=None, history_sha256=None, event_ids=None) -> HistorySnapshot:
    """Pure identity validation; this private helper grants no current authority."""
    if type(proof) is not AuthenticatedSelectedHistory or proof not in _ISSUED:
        raise PermissionError("history authentication was not issued by selected custody")
    issued = _ISSUED[proof]
    held = issued.history
    if (policy is not issued.policy or plan is not issued.plan
                or case_id != issued.case_id or phase != issued.phase
                or plan.digest() != issued.plan_sha256
                or plan.question_sha256_by_case.get(case_id) != issued.question_sha256
                or not isinstance(question, bytes) or _sha(question) != issued.question_sha256
                or held.digest() != issued.history_sha256
                or (history is not None and history is not held)
                or (scope is not None and scope != held.scope)
                or (history_sha256 is not None and history_sha256 != issued.history_sha256)
                or (event_ids is not None and tuple(event_ids) != held.event_ids)
                or _controllers(policy) != issued.controllers):
        raise PermissionError("authenticated history crossed its actual owner or frozen inputs")
    return held


def current_authenticated_history(proof, **inputs) -> HistorySnapshot:
    """Resolve issued held bytes only after fresh actual current authorization."""
    from .comparison_custody import SelectedRunEvidencePolicy
    held = _bound_history(proof, **inputs)
    policy, plan = inputs["policy"], inputs["plan"]
    # Final authority runs before the fresh terminal source fence. Thus a
    # control callback cannot revoke an earlier source grant after acceptance.
    policy.require_final_authority(plan=plan)
    _bound_history(proof, **inputs)
    if SelectedRunEvidencePolicy.authorize_history_metadata(policy,
            case_id=inputs["case_id"], phase=inputs["phase"], history=held) is not True:
        raise PermissionError("authenticated originals lost current selected authority")
    _bound_history(proof, **inputs)
    return held


def _request_inputs(request, policy):
    return dict(policy=policy, plan=request.plan,
        case_id=request.case_id, phase=request.phase, question=request.question,
        history=getattr(request, "history", None), scope=getattr(request, "scope", None),
        history_sha256=getattr(request, "authorized_history_sha256", None),
        event_ids=getattr(request, "authorized_event_ids", None))


def require_authenticated_request_bindings(request, *, policy, expected_proof=_UNSPECIFIED):
    """Pure post-callback identity check, never permission to read or disclose."""
    proof = getattr(request, "authenticated_history", None)
    if expected_proof is not _UNSPECIFIED and proof is not expected_proof:
        raise PermissionError("request changed its issued history authentication during a boundary")
    if proof is not None:
        _bound_history(proof, **_request_inputs(request, policy))


def request_authenticated_history(request, *, policy):
    """None retains direct API's full authentication; malformed proof fails closed."""
    proof = getattr(request, "authenticated_history", None)
    if proof is None:
        return None
    return current_authenticated_history(proof, **_request_inputs(request, policy))
