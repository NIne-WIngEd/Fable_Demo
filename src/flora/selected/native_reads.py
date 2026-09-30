"""Bounded passive reads of the actual selected runtime and phase lineage.

The explicit deployment factory opens initialized, read-only sessions. Model
inference and custody reconciliation are forbidden in these callbacks. Cancelling
an await does not terminate a database driver: its independently qualified read
deadlines still apply, and its thread retains ownership until the session closes.
"""
from __future__ import annotations

import asyncio
from copy import copy
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import inspect
from pathlib import Path
import threading
from typing import Callable, ContextManager, Protocol

from cognitive_kernel.canonical import canonical_sha256, require_identifier, require_sha256
from cognitive_kernel.contracts import ProductHostScope

from ..comparison_run import ArmResult, ExecutionRequest, PreparationRequest, _context_bytes
from .experiment_runtime import FloRAExperimentRuntime, JudgmentRun
from .judgment_lineage import NativeJudgmentLineageVerifier, VerifiedNativeJudgmentResult, _INTERNAL_EVENT_TYPES
from .native_arm import NativeInvocationEntry
from .native_worker import _await_owned_read
from .phase_routes import SelectedPhaseRoute
from .comparison_custody import SelectedRunEvidencePolicy
from .personal_artifact_custody import DurableOwnerProofLookup


def _positive(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(name + " must be a positive integer")


@dataclass(frozen=True)
class NativeReadManifest:
    scope: ProductHostScope
    authority_namespace_id: str
    session_factory_artifact_sha256: str
    session_factory_configuration_sha256: str
    maximum_concurrent_reads: int
    maximum_read_wall_time_ms: int
    backend_read_timeout_ms: int
    allow_current_fixture_route: bool = False

    def record(self):
        self.scope.validate()
        if require_identifier(self.authority_namespace_id, "authority_namespace_id") != self.authority_namespace_id:
            raise ValueError("native reader needs a canonical authority namespace")
        for name in ("session_factory_artifact_sha256", "session_factory_configuration_sha256"):
            if require_sha256(getattr(self, name), name) != getattr(self, name):
                raise ValueError("native read factory hashes must be canonical")
        for name in ("maximum_concurrent_reads", "maximum_read_wall_time_ms", "backend_read_timeout_ms"):
            _positive(getattr(self, name), name)
        if self.backend_read_timeout_ms > self.maximum_read_wall_time_ms:
            raise ValueError("backend read timeout exceeds the passive-read deadline")
        if not isinstance(self.allow_current_fixture_route, bool):
            raise ValueError("native fixture route choice must be explicit")
        return {"schema": "flora-native-read-manifest-v1", **vars(self), "scope": self.scope.metadata_record()}

    @property
    def configuration_sha256(self):
        return canonical_sha256(self.record())


class ReadOnlyNativeSQLConnection:
    """Narrow guard for qualified selected-store SELECT templates.

    This is not a general SQL parser or a security boundary for arbitrary code.
    The independently qualified initialized binder gets this wrapper, not the
    underlying connection. It forbids DDL, reconciliation, transactions and
    stacked statements in the actual passive read route.
    """
    def __init__(self, connection, *, read_timeout_ms: int):
        _positive(read_timeout_ms, "read_timeout_ms")
        self.__connection = connection
        self.read_timeout_ms, self.owner_thread_id = read_timeout_ms, threading.get_ident()
        self.closed = False

    def execute(self, sql, parameters=()):
        if self.closed or threading.get_ident() != self.owner_thread_id:
            raise RuntimeError("native SQL read connection is closed or owned by another thread")
        if (not isinstance(sql, str) or not sql.lstrip().upper().startswith("SELECT ")
                or ";" in sql or "\0" in sql):
            raise PermissionError("native passive read route accepts qualified single SELECT templates only")
        return self.__connection.execute(sql, parameters)

    @property
    def adapters(self):
        # Connection-local type adaptation is configuration, not schema/data
        # mutation. Selected constructors may install their existing TEXT dumper.
        if self.closed or threading.get_ident() != self.owner_thread_id:
            raise RuntimeError("native SQL connection is closed or owned by another thread")
        return self.__connection.adapters

    @property
    def prepare_threshold(self):
        if self.closed or threading.get_ident() != self.owner_thread_id:
            raise RuntimeError("native SQL connection is closed or owned by another thread")
        return self.__connection.prepare_threshold

    @prepare_threshold.setter
    def prepare_threshold(self, value):
        if self.closed or threading.get_ident() != self.owner_thread_id:
            raise RuntimeError("native SQL connection is closed or owned by another thread")
        if value is not None:
            raise PermissionError("native selected reads must disable cached prepared plans")
        # Driver configuration cannot grant SQL mutation. XTDB schemas grow as
        # selected services initialize; a cached empty-table plan is unsafe.
        self.__connection.prepare_threshold = None

    def transaction(self, *args, **kwargs):
        raise PermissionError("native passive reads cannot begin write transactions")

    def close(self):
        if threading.get_ident() != self.owner_thread_id:
            raise RuntimeError("native SQL connection must close in its owning read thread")
        if not self.closed:
            self.closed = True
            self.__connection.close()


@dataclass(frozen=True)
class NativeReadSession:
    runtime: FloRAExperimentRuntime
    lineage: NativeJudgmentLineageVerifier
    connections: tuple[ReadOnlyNativeSQLConnection, ...]
    phase_route_for: Callable | None = None


class NativeReadSessionFactory(Protocol):
    artifact_sha256: str
    configuration_sha256: str
    def open_initialized_read_session(self) -> ContextManager[NativeReadSession]: ...


class InitializedNativeSessionFactory:
    """Own a fresh connection and bind initialized services without constructors.

    The supplied opener must enforce the actual driver/server deadline and use
    read-only credentials or equivalent driver restrictions. The binder must
    reference existing selected tables and durable artifacts; it must not create
    schema, enroll authorities, infer, repair indexes or reuse live write-session
    connections. Factory/transitive opener/binder qualification is external.
    """
    def __init__(self, *, artifact_sha256: str, configuration_sha256: str,
                 connection_opener: Callable, bind_initialized: Callable,
                 backend_read_timeout_ms: int):
        for name, value in (("artifact_sha256", artifact_sha256), ("configuration_sha256", configuration_sha256)):
            if require_sha256(value, name) != value:
                raise ValueError("session factory hashes must be canonical")
        if not callable(connection_opener) or not callable(bind_initialized):
            raise TypeError("native factory requires an explicit bounded opener and initialized binder")
        _positive(backend_read_timeout_ms, "backend_read_timeout_ms")
        self.artifact_sha256, self.configuration_sha256 = artifact_sha256, configuration_sha256
        self.connection_opener, self.bind_initialized = connection_opener, bind_initialized
        self.backend_read_timeout_ms = backend_read_timeout_ms

    @contextmanager
    def open_initialized_read_session(self):
        # The opener receives the qualified deadline explicitly. No connection
        # or credential is inferred from the environment.
        raw = self.connection_opener(read_timeout_ms=self.backend_read_timeout_ms)
        connection = ReadOnlyNativeSQLConnection(raw, read_timeout_ms=self.backend_read_timeout_ms)
        try:
            session = self.bind_initialized(connection)
            if not isinstance(session, NativeReadSession) or session.connections != (connection,):
                raise ValueError("initialized binder must use the exact freshly owned read connection")
            yield session
        finally:
            connection.close()


class SelectedNativeReadServices:
    """Concrete actual-runtime reader, with bounded concurrency and no writes.

    An expired/cancelled operation keeps its thread slot until the session has
    closed. Thus retries cannot accumulate detached readers. The event loop only
    awaits passive work; qualification, actual inference and accepted custody
    writes remain separate operations.
    """
    def __init__(self, *, manifest: NativeReadManifest, factory: NativeReadSessionFactory):
        manifest.record()
        if (factory.artifact_sha256 != manifest.session_factory_artifact_sha256
                or factory.configuration_sha256 != manifest.session_factory_configuration_sha256
                or not callable(getattr(factory, "open_initialized_read_session", None))):
            raise ValueError("native session factory differs from frozen reader manifest")
        self.manifest, self.factory = manifest, factory
        self.artifact_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.configuration_sha256 = manifest.configuration_sha256
        self._manifest_sha256 = manifest.configuration_sha256
        self._executor = ThreadPoolExecutor(max_workers=manifest.maximum_concurrent_reads,
                                            thread_name_prefix="flora-selected-native-read")
        self._slots = asyncio.Semaphore(manifest.maximum_concurrent_reads)
        self._pending = set()
        self._closed = False

    def _check_configuration(self):
        if (self._closed or self.manifest.configuration_sha256 != self._manifest_sha256
                or self.configuration_sha256 != self._manifest_sha256
                or self.artifact_sha256 != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
                or self.factory.artifact_sha256 != self.manifest.session_factory_artifact_sha256
                or self.factory.configuration_sha256 != self.manifest.session_factory_configuration_sha256):
            raise ValueError("native passive reader configuration changed or closed")

    def _check_session(self, session):
        if (not isinstance(session, NativeReadSession) or not isinstance(session.runtime, FloRAExperimentRuntime)
                or not isinstance(session.lineage, NativeJudgmentLineageVerifier)
                or session.lineage.runtime is not session.runtime
                or session.runtime.scope != self.manifest.scope
                or session.runtime.authority_namespace_id != self.manifest.authority_namespace_id
                or not session.connections or len(set(map(id, session.connections))) != len(session.connections)
                or any(not isinstance(c, ReadOnlyNativeSQLConnection) or c.closed
                       or c.owner_thread_id != threading.get_ident()
                       or c.read_timeout_ms > self.manifest.backend_read_timeout_ms for c in session.connections)):
            raise ValueError("native session lacks exact initialized runtime, lineage and owned read connections")
        runtime = session.runtime
        planes = (runtime.artifacts, runtime.claims, runtime.sources, runtime.source_policy,
                  runtime.candidates, runtime.state, runtime.private,
                  runtime.original_references.custody)
        if runtime.state.episodes is not None:
            planes += (runtime.state.episodes,)
        if any(getattr(plane, "connection", None) not in session.connections for plane in planes):
            raise ValueError("native read service retained a live unguarded selected-store connection")
        authority = session.lineage.history_authority
        if isinstance(authority, SelectedRunEvidencePolicy):
            authority_planes = (authority.custody, authority.custody.registry,
                                authority.permissions, authority.permissions.registry)
            if any(getattr(plane, "connection", None) not in session.connections for plane in authority_planes):
                raise ValueError("native phase history authority retained an unowned selected-store connection")
        proofs = getattr(runtime.state_approval_verifier, "proofs", None)
        if isinstance(proofs, DurableOwnerProofLookup) and proofs.custody.connection not in session.connections:
            raise ValueError("native owner proof lookup retained an unowned selected-store connection")
        for target in (runtime.recover_judgment, session.lineage.verify_native_result_details):
            if "reconcile" not in inspect.signature(target).parameters:
                raise ValueError("native runtime has no strictly read-only recovery path")

    async def _read(self, action):
        self._check_configuration()
        deadline = asyncio.get_running_loop().time() + self.manifest.maximum_read_wall_time_ms / 1000
        async with asyncio.timeout_at(deadline):
            await self._slots.acquire()
            try:
                self._check_configuration()
                def work():
                    self._check_configuration()
                    with self.factory.open_initialized_read_session() as session:
                        self._check_session(session)
                        result = action(session)
                        self._check_session(session)
                        self._check_configuration()
                        return result
                future = asyncio.get_running_loop().run_in_executor(self._executor, work)
            except BaseException:
                self._slots.release()
                raise
            self._pending.add(future)
            def finished(done):
                self._pending.discard(done)
                self._slots.release()
                if not done.cancelled():
                    done.exception()  # Consume a private exception after a cancelled await.
            future.add_done_callback(finished)
            # Poll without cancelling the owned future. Its slot belongs to its
            # physical thread until all session cleanup is finished.
            return await _await_owned_read(future)

    @staticmethod
    def _history(session, entry, request):
        if request.case_id != entry.case_id or request.phase != entry.phase:
            raise ValueError("native passive request differs from frozen invocation")
        if request.plan.digest() != session.lineage.run_plan_sha256:
            raise ValueError("native passive request changed frozen run plan")
        history = session.lineage.history_for(entry.case_id, entry.phase)
        if isinstance(request, PreparationRequest):
            if request.history != history:
                raise ValueError("native preparation differs from independent phase history")
        elif (request.scope != session.runtime.scope or request.authorized_history_sha256 != history.digest()
                or request.authorized_event_ids != history.event_ids):
            raise ValueError("native execution differs from independent phase history")
        return history

    @staticmethod
    def _install_phase_source_gate(session, entry, history):
        """Deny future original plaintext before context/recovery opens it.

        Typed semantic authority still needs its frozen phase snapshot route.
        This current-reader guard checks original closure and live consent; it
        does not pretend a cached receipt is a historical Claim/state authority.
        """
        lineage, runtime = session.lineage, session.runtime
        if (history.scope != runtime.scope or lineage.history_authority.authorize_history(
                case_id=entry.case_id, phase=entry.phase, history=history) is not True):
            raise PermissionError("native read lacks current independent phase authority")
        authority = lineage.history_authority
        if isinstance(authority, SelectedRunEvidencePolicy):
            # Its permission reader may be the very runtime policy we fence
            # below. A separately scoped original-policy copy prevents recursive
            # history->permissions->history calls while reading the same live rows.
            authority = copy(authority)
            authority.permissions = copy(runtime.source_policy)
            lineage.history_authority = authority
        def phase_now():
            method = authority.authorize_history
            if isinstance(authority, SelectedRunEvidencePolicy):
                method = authority.authorize_history_metadata
            return method(case_id=entry.case_id, phase=entry.phase, history=history) is True
        events = {event.event_id: event for event in runtime.log.replay()}
        originals = {source.event.event_id: source.event for source in history.sources}
        if any(events.get(event_id) != event or event.event_type in _INTERNAL_EVENT_TYPES
               for event_id, event in originals.items()):
            raise ValueError("native phase history changed or promoted internal control into originals")
        def phase_member(event_id, seen=None):
            event = events.get(event_id)
            if event is None or event.scope != runtime.scope:
                return False
            if event.event_type not in _INTERNAL_EVENT_TYPES:
                return event_id in originals
            if event.event_type in {"comparison_artifact", "provider_attempt_artifact",
                                    "phase_snapshot_artifact", "experiment_manifest_artifact"}:
                return False
            visited = set() if seen is None else seen
            if event_id in visited:
                return False
            visited.add(event_id)
            # Approval source closure is typed in allow_state/current_lineage;
            # a signed approval may itself have no original parent edge.
            if not event.parent_event_ids:
                return event.event_type == "state_activation_approval"
            return all(phase_member(parent, set(visited)) for parent in event.parent_event_ids)
        policy, context_policy = runtime.source_policy, runtime.context_policy
        permits, allow_event = policy.permits, context_policy.allow_event
        def phase_permits(source, purpose):
            return (phase_now()
                    and phase_member(source.evidence.ref_id) and permits(source, purpose) is True)
        def phase_allow_event(event_id, purpose):
            return phase_now() and phase_member(event_id) and allow_event(event_id, purpose) is True
        policy.permits = phase_permits
        context_policy.allow_event = phase_allow_event

    def _phase_session(self, session, entry, request=None, *, arm=None):
        """Resolve the exact archive on this freshly owned read connection.

        Resolver code is part of the explicitly qualified session factory. A
        returned runtime, cached context, or plausible snapshot is insufficient:
        the actual selected route and its actual lineage must be kept together.
        """
        entry.record()
        history = (session.lineage.history_for(entry.case_id, entry.phase) if request is None
                   else self._history(session, entry, request))
        artifact_permissions = copy(session.runtime.source_policy)
        self._install_phase_source_gate(session, entry, history)
        binding = entry.phase_snapshot
        if binding is None:
            if not self.manifest.allow_current_fixture_route or session.phase_route_for is not None:
                raise PermissionError("native production reads require an exact selected phase snapshot route")
            def fixture_guard():
                if session.lineage.history_authority.authorize_history(case_id=entry.case_id,
                        phase=entry.phase, history=history) is not True:
                    raise PermissionError("native fixture phase permission changed before private I/O")
            return session, history, fixture_guard, arm or "flora_full", None
        if not callable(session.phase_route_for):
            raise PermissionError("native phase snapshot has no qualified fresh-session resolver")
        if arm is not None and arm != binding.arm:
            raise ValueError("native requested arm differs from frozen phase snapshot binding")
        if request is not None:
            if not isinstance(request, (PreparationRequest, ExecutionRequest)):
                raise TypeError("selected native phase routes require an exact execution/preparation request")
            if isinstance(request, ExecutionRequest) and request.binding != request.plan.binding_for(
                    entry.case_id, entry.phase, binding.arm):
                raise ValueError("native request binding differs from frozen phase snapshot arm")
        route = session.phase_route_for(entry=entry, request=request,
                                       artifact_permissions=artifact_permissions)
        def same_phase_authority(actual, expected):
            if actual is expected:
                return True
            # Actual archive recovery wraps this controller's inner object
            # reads with its custody-only permission barrier. Keep its exact
            # live policy, original registry/log, run and owned SQL connection.
            return (isinstance(actual, SelectedRunEvidencePolicy)
                    and isinstance(expected, SelectedRunEvidencePolicy)
                    and actual.run_id == expected.run_id
                    and actual.permissions is expected.permissions
                    and actual.custody.connection is expected.custody.connection
                    and actual.custody.registry is expected.custody.registry
                    and actual.custody.log is expected.custody.log)
        if (not isinstance(route, SelectedPhaseRoute) or route.custody.runtime is not session.runtime
                or route.custody.connection not in session.connections
                or route.lineage.runtime is not route.runtime
                or route.history != history
                or route.history_authority is not session.lineage.history_authority
                or not same_phase_authority(route.lineage.history_authority, session.lineage.history_authority)
                or route.lineage.run_plan_sha256 != session.lineage.run_plan_sha256):
            raise ValueError("native resolver returned an unrelated or unowned selected phase route")
        routed = NativeReadSession(route.runtime, route.lineage, session.connections)
        self._check_session(routed)
        captured = route.snapshot.record
        metadata = route.custody.metadata(binding.snapshot_id)
        if (route.custody.run_id != binding.run_id or route.snapshot.snapshot_id != binding.snapshot_id
                or route.custody.run_plan_sha256 != session.lineage.run_plan_sha256
                or metadata is None or metadata["snapshot_sha256"] != route.snapshot.snapshot_sha256
                or any(captured[name] != value for name, value in (
                    ("run_id", binding.run_id), ("snapshot_id", binding.snapshot_id),
                    ("case_id", entry.case_id), ("phase", entry.phase), ("arm", binding.arm),
                    ("run_plan_sha256", session.lineage.run_plan_sha256), ("history_sha256", history.digest())))
                or tuple(captured["original_event_ids"]) != tuple(sorted(history.event_ids))
                or route.snapshot.plan != entry.context_plan):
            raise ValueError("native selected archive differs from exact frozen invocation/history")
        def guard():
            route.custody.authorize(snapshot_id=binding.snapshot_id, history=history,
                history_authority=route.history_authority, expected=metadata)
        guard()
        return routed, history, guard, binding.arm, captured["context_receipt"]

    @staticmethod
    def _check_context(entry, context, captured_receipt=None):
        if (context.plan != entry.context_plan
                or hashlib.sha256(_context_bytes(context)).hexdigest() != entry.context_sha256
                or (captured_receipt is not None and context.receipt_record() != captured_receipt)):
            raise ValueError("native context differs from frozen plan/content and actual phase receipt")

    async def prepare_context(self, entry):
        entry.record()
        def action(session):
            routed, history, guard, arm, receipt = self._phase_session(session, entry)
            guard()
            context = routed.runtime._context(entry.context_plan, authority_guard=guard)
            self._check_context(entry, context, receipt)
            guard()
            return context
        return await self._read(action)

    async def authorize_context(self, *, entry, request, context, arm):
        def action(session):
            routed, history, guard, route_arm, receipt = self._phase_session(session, entry, request, arm=arm)
            self._check_context(entry, context, receipt)
            guard()
            allowed = routed.lineage.authorize_context(case_id=entry.case_id, phase=entry.phase,
                history=history, context=context, arm=route_arm, authority_guard=guard)
            guard()
            return allowed
        return await self._read(action)

    async def recover_judgment(self, *, entry, request) -> JudgmentRun:
        def action(session):
            routed, history, guard, arm, receipt = self._phase_session(session, entry, request)
            self._check_context(entry, request.context, receipt)
            guard()
            if routed.lineage.authorize_context(case_id=entry.case_id, phase=entry.phase,
                    history=history, context=request.context, arm=arm, authority_guard=guard) is not True:
                raise PermissionError("native recovery lost current phase permission")
            guard()
            actual = routed.runtime.recover_judgment(plan=entry.context_plan, task=request.question,
                invocation_id=entry.invocation_id, reconcile=False, authority_guard=guard)
            self._check_context(entry, actual.context, receipt)
            if routed.lineage.authorize_context(case_id=entry.case_id, phase=entry.phase,
                    history=history, context=request.context, arm=arm, authority_guard=guard) is not True:
                raise PermissionError("native phase permission changed during passive recovery")
            guard()
            return actual
        return await self._read(action)

    async def verify_native_result(self, *, entry, request, result: ArmResult) -> VerifiedNativeJudgmentResult:
        def action(session):
            routed, history, guard, arm, receipt = self._phase_session(session, entry, request)
            self._check_context(entry, request.context, receipt)
            guard()
            actual = routed.lineage.verify_native_result_details(request, result, reconcile=False,
                authority_guard=guard)
            if actual.invocation_id != entry.invocation_id:
                raise ValueError("native passive result recovered a different invocation")
            guard()
            return actual
        return await self._read(action)

    async def aclose(self):
        self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=True)
        # Thread cleanup retains ownership. Closing does not turn cancellation
        # into permission to infer or write, nor claim to kill a driver thread.
        if self._pending:
            async with asyncio.timeout(self.manifest.maximum_read_wall_time_ms / 1000):
                await asyncio.gather(*[asyncio.shield(future) for future in tuple(self._pending)],
                                     return_exceptions=True)
