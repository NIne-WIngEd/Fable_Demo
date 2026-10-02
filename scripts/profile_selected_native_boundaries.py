"""Observe original owned native readers; all aggregate timings are nonqualifying.

No selected function is wrapped or replaced. Every classified worker has its
own numeric stack and thread CPU window. Closing observation never cancels,
waits for or stops a read, including one that outlives the fixture driver.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import inspect
import json
import math
import os
from pathlib import Path
import re
import sys
import threading
import time
from types import CodeType
import unittest


_OBSERVER_PATH = Path(__file__).with_name("profile_selected_transport_boundaries.py")
_SPEC = importlib.util.spec_from_file_location("flora_native_transport_observer", _OBSERVER_PATH)
transport = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = transport
_SPEC.loader.exec_module(transport)
AggregateTestResult = transport.AggregateTestResult
DiagnosticSoftCap = transport.DiagnosticSoftCap
ProfileHookUnavailable = transport.ProfileHookUnavailable
Target = transport.Target

FIXTURE_MODULE = "test_selected_native_comparison"
FIXTURE_CLASS = "SelectedNativeComparisonIntegrationTest"
FIXTURE_METHOD = "test_actual_phase_context_execution_parent_and_private_run_custody"
FIXTURE_ID = ".".join((FIXTURE_MODULE, FIXTURE_CLASS, FIXTURE_METHOD))
PROTOCOL_RESPONSE_BUDGET_MS = 60000
MAX_WORKER_LEDGERS = 32
MAX_STACK_DEPTH = 256


class NumericLedger:
    """Only a fixed tag index, numeric clocks/counters, and ordinary containers."""

    def __init__(self, tags, wall, cpu):
        self.rows = [[0, 0, 0, 0, 0, 0] for _ in tags]
        self.stack = []
        self.start_wall = self.last_wall = wall
        self.start_cpu = self.last_cpu = cpu
        self.rpc_depth = self.owned_depth = 0
        self.stack_overflow = 0
        self.observation_disabled = False

    def finish(self, wall, cpu, *, returned):
        index, start_wall, start_cpu, child_wall, child_cpu, rpc = self.stack.pop()
        self.rpc_depth -= int(rpc)
        elapsed_wall, elapsed_cpu = max(0, wall - start_wall), max(0, cpu - start_cpu)
        row = self.rows[index]
        row[1] += int(returned)
        row[2] += elapsed_wall
        row[3] += elapsed_cpu
        row[4] += max(0, elapsed_wall - child_wall)
        row[5] += max(0, elapsed_cpu - child_cpu)
        if self.stack:
            self.stack[-1][3] += elapsed_wall
            self.stack[-1][4] += elapsed_cpu

    def observe(self, event, index, rpc, wall, cpu):
        self.last_wall, self.last_cpu = wall, cpu
        if self.observation_disabled:
            return
        if event == "call":
            if len(self.stack) >= MAX_STACK_DEPTH:
                self.stack_overflow += 1
                self.observation_disabled = True
                return
            self.rows[index][0] += 1
            self.stack.append([index, wall, cpu, 0, 0, rpc])
            self.rpc_depth += int(rpc)
        elif self.stack and self.stack[-1][0] == index:
            self.finish(wall, cpu, returned=True)

    def close_numeric_window(self):
        open_spans, active_rpcs = len(self.stack), self.rpc_depth
        while self.stack:
            self.finish(self.last_wall, self.last_cpu, returned=False)
        return open_spans, active_rpcs

    def summary(self, tags):
        return dict(window_wall_seconds=max(0, self.last_wall - self.start_wall) / 1e9,
            window_thread_cpu_seconds=max(0, self.last_cpu - self.start_cpu) / 1e9,
            stack_overflow=self.stack_overflow,
            functions=[dict(tag=tag, calls=row[0], return_events=row[1],
                wall_seconds=row[2] / 1e9, thread_cpu_seconds=row[3] / 1e9,
                exclusive_wall_seconds=row[4] / 1e9,
                exclusive_thread_cpu_seconds=row[5] / 1e9,
                wall_minus_thread_cpu_seconds=max(0, row[2] - row[3]) / 1e9)
                for tag, row in zip(tags, self.rows)])


class OwnedThreadObserver:
    """Future-thread dispatch; classify only an exact original owned-work code.

    No thread ID/name is retained. threading.local separates reused OS thread
    identifiers. Inherited hooks on survivors remove only themselves on their
    next Python event; a later installed hook is never overwritten.
    """

    def __init__(self, targets, *, owned_work_code, cap_seconds=180,
                 wall_clock=time.perf_counter_ns, cpu_clock=time.thread_time_ns,
                 maximum_worker_ledgers=MAX_WORKER_LEDGERS,
                 parent_rpc_only_before_owned=False):
        if cap_seconds is not None and (not math.isfinite(cap_seconds) or not 0 < cap_seconds <= 180):
            raise ValueError("cap must be positive, finite and at most 180 seconds")
        if type(maximum_worker_ledgers) is not int or not 1 <= maximum_worker_ledgers <= MAX_WORKER_LEDGERS:
            raise ValueError("bounded worker ledger count required")
        if type(parent_rpc_only_before_owned) is not bool:
            raise ValueError("parent setup scope must be an explicit boolean")
        if any(code.co_flags & (inspect.CO_GENERATOR | inspect.CO_COROUTINE | inspect.CO_ASYNC_GENERATOR)
                for code in targets):
            raise ValueError("only ordinary synchronous original code objects")
        if not any(code is owned_work_code for code in targets):
            raise ValueError("the original owned marker must be a fixed target")
        self.codes = tuple(targets)
        self.tags = tuple(target.tag for target in targets.values())
        if len(set(self.tags)) != len(self.tags):
            raise ValueError("one fixed tag per original code")
        self.targets = {id(code): (index, target.rpc) for index, (code, target) in enumerate(targets.items())}
        self.owned_code_id = id(owned_work_code)
        self.cap_ns = None if cap_seconds is None else int(cap_seconds * 1e9)
        self.wall_clock, self.cpu_clock = wall_clock, cpu_clock
        self.maximum_worker_ledgers = maximum_worker_ledgers
        self.parent_rpc_only_before_owned = parent_rpc_only_before_owned
        self.local = threading.local()
        self.lock = threading.Lock()
        self.workers = []
        self.parent = None
        self.closed = self.installed = False
        self.parent_hook = self._parent_profile
        self.worker_hook = self._worker_profile
        self.previous_parent_hook = self.previous_future_hook = None
        self.start_wall = self.end_wall = None
        self.active_owned_work = self.owned_entries = self.worker_ledger_overflow = 0
        self.first_owned_entry_offset_ns = None
        self.open_spans_at_close = self.active_rpcs_at_close = self.active_owned_work_at_close = 0
        self.parent_hook_changed = self.future_hook_changed = False
        self.stopped_before_parent_rpc = False
        self.cap_deferred_entries = self.observer_errors = 0

    @staticmethod
    def monitoring_occupied():
        monitoring = getattr(sys, "monitoring", None)
        # Local monitoring events need not appear in get_events. Conservatively
        # refuse any reserved tool rather than inspect arbitrary loaded code.
        return monitoring is not None and any(monitoring.get_tool(tool) is not None for tool in range(6))

    def __enter__(self):
        if self.installed or self.closed:
            raise RuntimeError("observer is single-use")
        if sys.getprofile() is not None or threading.getprofile() is not None or self.monitoring_occupied():
            raise ProfileHookUnavailable("existing current/future profile or monitoring tool")
        self.previous_parent_hook, self.previous_future_hook = sys.getprofile(), threading.getprofile()
        wall, cpu = self.wall_clock(), self.cpu_clock()
        self.start_wall, self.parent = wall, NumericLedger(self.tags, wall, cpu)
        try:
            threading.setprofile(self.worker_hook)
            sys.setprofile(self.parent_hook)
            self.installed = True
        except BaseException:
            if sys.getprofile() is self.parent_hook:
                sys.setprofile(self.previous_parent_hook)
            if threading.getprofile() is self.worker_hook:
                threading.setprofile(self.previous_future_hook)
            self.closed = True
            raise
        return self

    def __exit__(self, exc_type, exc, traceback):
        with self.lock:
            self.closed = True
            self.end_wall = self.wall_clock()
            self.parent.last_wall, self.parent.last_cpu = self.end_wall, self.cpu_clock()
            self.active_owned_work_at_close = self.active_owned_work
            for ledger in (self.parent, *self.workers):
                spans, rpcs = ledger.close_numeric_window()
                self.open_spans_at_close += spans
                self.active_rpcs_at_close += rpcs
        # Restore only our own hooks. Native code may have installed a new one.
        self.parent_hook_changed = sys.getprofile() is not self.parent_hook
        self.future_hook_changed = threading.getprofile() is not self.worker_hook
        if not self.parent_hook_changed:
            sys.setprofile(self.previous_parent_hook)
        if not self.future_hook_changed:
            threading.setprofile(self.previous_future_hook)
        self.installed = False
        return False

    def _remove_own_worker_hook(self):
        if sys.getprofile() is self.worker_hook:
            sys.setprofile(self.previous_future_hook)

    def _worker_profile(self, frame, event, arg):
        # frame/arg are transient interpreter arguments; neither is stored.
        if self.closed:
            self._remove_own_worker_hook()
            return
        if event not in ("call", "return"):
            return
        code_id = id(frame.f_code)
        marker = code_id == self.owned_code_id
        ledger = getattr(self.local, "ledger", None)
        depth = getattr(self.local, "owned_depth", 0)
        if not marker and not depth:
            return
        target = self.targets.get(code_id)
        if not marker and target is None:
            return
        try:
            wall, cpu = self.wall_clock(), self.cpu_clock()
            with self.lock:
                if self.closed:
                    return
                if marker and event == "call":
                    if self.first_owned_entry_offset_ns is None:
                        self.first_owned_entry_offset_ns = max(0, wall - self.start_wall)
                    self.owned_entries += 1
                    self.active_owned_work += 1
                    self.local.owned_depth = depth + 1
                    if ledger is None and not getattr(self.local, "overflow", False):
                        if len(self.workers) >= self.maximum_worker_ledgers:
                            self.worker_ledger_overflow += 1
                            self.local.overflow = True
                        else:
                            ledger = NumericLedger(self.tags, wall, cpu)
                            self.workers.append(ledger)
                            self.local.ledger = ledger
                if ledger is not None and target is not None:
                    ledger.observe(event, *target, wall, cpu)
                if marker and event == "return" and depth:
                    self.active_owned_work -= 1
                    self.local.owned_depth = depth - 1
        except BaseException:
            # Observation failure never changes the owned read's protocol.
            self.observer_errors += 1
            self._remove_own_worker_hook()

    def _parent_profile(self, frame, event, arg):
        if self.closed or event not in ("call", "return"):
            return
        target = self.targets.get(id(frame.f_code))
        if target is None:
            return
        # Native CLI setup keeps RPC nesting/cap safety but does not attribute
        # non-RPC parent spans before the first exact owned worker entry. The
        # original start/cap clock is untouched, and workers are unchanged.
        if self.parent_rpc_only_before_owned and not self.owned_entries and not target[1]:
            return
        wall, cpu = self.wall_clock(), self.cpu_clock()
        stop = False
        try:
            with self.lock:
                if self.closed:
                    return
                if event == "call" and target[1] and self.cap_ns is not None and wall - self.start_wall >= self.cap_ns:
                    active_rpcs = self.parent.rpc_depth + sum(ledger.rpc_depth for ledger in self.workers)
                    if not active_rpcs and not self.active_owned_work:
                        self.stopped_before_parent_rpc = stop = True
                        self.parent.last_wall, self.parent.last_cpu = wall, cpu
                        self.parent.close_numeric_window()
                    else:
                        self.cap_deferred_entries += 1
                if not stop:
                    self.parent.observe(event, *target, wall, cpu)
        except BaseException:
            self.observer_errors += 1
            if sys.getprofile() is self.parent_hook:
                sys.setprofile(self.previous_parent_hook)
            return
        if stop:
            # CPython clears only this parent's hook when a callback raises.
            # Never raise a cap/error in an owned worker or active selected RPC.
            raise DiagnosticSoftCap()

    def summary(self):
        if not self.closed or self.end_wall is None:
            raise RuntimeError("closed numeric snapshot required")
        elapsed = max(0, self.end_wall - self.start_wall)
        return dict(elapsed_seconds=elapsed / 1e9,
            overshoot_seconds=0 if self.cap_ns is None else max(0, elapsed - self.cap_ns) / 1e9,
            stopped_before_parent_rpc=self.stopped_before_parent_rpc,
            cap_deferred_parent_entries=self.cap_deferred_entries,
            classified_owned_work_entries=self.owned_entries,
            first_owned_entry_offset_seconds=(None if self.first_owned_entry_offset_ns is None
                else self.first_owned_entry_offset_ns / 1e9),
            retained_worker_ledgers=len(self.workers), worker_ledger_overflow=self.worker_ledger_overflow,
            active_owned_work_at_close=self.active_owned_work_at_close,
            open_tagged_spans_at_close=self.open_spans_at_close,
            active_observed_rpcs_at_close=self.active_rpcs_at_close,
            observer_errors=self.observer_errors,
            parent_hook_changed=self.parent_hook_changed, future_hook_changed=self.future_hook_changed,
            parent=self.parent.summary(self.tags), workers=[worker.summary(self.tags) for worker in self.workers])


def _nested_code(function, name):
    code = transport._target_function(function)
    matches = [value for value in code.co_consts if isinstance(value, CodeType) and value.co_name == name]
    if len(matches) != 1:
        raise ValueError("fixed original closure must have exactly one code object")
    return matches[0]


def original_case():
    module = importlib.import_module(FIXTURE_MODULE)
    return module, getattr(module, FIXTURE_CLASS)(FIXTURE_METHOD)


def native_targets(module):
    from flora.selected import (context, context_guard, experiment_runtime,
        judgment_lineage, native_reads, selected_authority_frame, selected_history_contribution)
    reads = native_reads.SelectedNativeReadServices
    frame = selected_authority_frame.SharedSelectedAuthorityFrame
    physical = selected_authority_frame._FramePhysicalData
    history = selected_history_contribution.SelectedHistoryContribution
    method = getattr(getattr(module, FIXTURE_CLASS), FIXTURE_METHOD)
    targets = transport.selected_targets()
    fixed = (("fixture.original_native_case", method),
        ("native.phase_session", reads._phase_session),
        ("native.install_phase_source_gate", reads._install_phase_source_gate),
        ("runtime.context", experiment_runtime.FloRAExperimentRuntime._context),
        ("context.assemble", context.assemble_context),
        ("lineage.authorize_context", judgment_lineage.NativeJudgmentLineageVerifier.authorize_context),
        ("lineage.context", judgment_lineage.NativeJudgmentLineageVerifier.context_lineage),
        ("context.prepare_current", context_guard.prepare_current_context),
        ("context.metadata_current", context_guard.PreparedCurrentContext.metadata_current),
        ("shared.frame.create", selected_authority_frame.create_shared_selected_frame),
        ("shared.frame.initialize", frame.__init__),
        ("shared.frame.base_bindings", frame._base_bindings),
        ("shared.frame.binding", frame.binding),
        ("shared.frame.finish", frame.finish),
        ("shared.frame.physical_closure", physical.closure),
        ("shared.frame.physical_reobserve", physical.reobserve),
        ("shared.history.initialize", history.__init__),
        ("shared.history.permissions", history.validate_permissions),
        ("shared.history.member", history.member),
        ("shared.history.manifest_reobserve", history.reobserve_manifest))
    for tag, function in fixed:
        targets[transport._target_function(function)] = Target(tag)
    closures = (("native.owned_work", reads._read, "work"),
        ("native.prepare_context", reads.prepare_context, "action"),
        ("native.authorize_context", reads.authorize_context, "action"),
        ("native.fixture_guard", reads._phase_session, "fixture_guard"),
        ("native.phase_now", reads._install_phase_source_gate, "phase_now"))
    for tag, function, name in closures:
        targets[_nested_code(function, name)] = Target(tag)
    return targets, _nested_code(reads._read, "work")


def source_hashes():
    result = {}
    for name, module in tuple(sys.modules.items()):
        if not name.startswith(("flora.", "cognitive_kernel.", "test_selected_", "flora_native_comparison_")):
            continue
        filename = getattr(module, "__file__", None)
        if filename:
            result[name] = hashlib.sha256(Path(filename).read_bytes()).hexdigest()
    result["native_diagnostic_script"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result["shared_transport_diagnostic"] = hashlib.sha256(_OBSERVER_PATH.read_bytes()).hexdigest()
    return result


def build_receipt(*, status, result, observer, cap_seconds, before, after):
    summary = observer.summary() if observer is not None and observer.end_wall is not None else None
    changed = sorted(name for name, digest in before.items() if after.get(name) != digest)
    return dict(schema_version=1, fixture_id=FIXTURE_ID, diagnostic_status=status,
        qualification=False, response_budget_ms=PROTOCOL_RESPONSE_BUDGET_MS,
        soft_cap_seconds=cap_seconds,
        cap_policy="parent_next_outer_rpc_only_without_active_observed_rpc_or_owned_work",
        cap_outcome=("not_observed" if summary is None else "stopped_before_parent_rpc"
            if summary["stopped_before_parent_rpc"] else "completed_after_cap"
            if summary["overshoot_seconds"] else "within_cap"),
        coverage=("parent_rpc_only_before_first_owned_entry_then_fixed_parent_and_owned_worker_tags"
            if observer is not None and observer.parent_rpc_only_before_owned
            else "parent_and_future_threads_classified_by_exact_original_owned_work_code"),
        parent_non_rpc_setup_observed=(not observer.parent_rpc_only_before_owned
            if observer is not None else None),
        coverage_limits=["observer_overhead_precludes_latency_qualification",
            "return_events_include_exception_unwind_and_do_not_attest_authorization_success",
            "preexisting_threads_child_processes_and_unclassified_threads_not_measured",
            "coroutine_and_generator_spans_not_targeted",
            "thread_windows_can_include_idle_or_untagged_work_between_owned_jobs",
            "worker_wall_spans_may_overlap_and_must_not_be_added_to_parent_elapsed",
            "open_spans_close_at_that_threads_last_numeric_sample_not_another_threads_cpu_clock",
            "closed_survivor_dispatchers_remove_only_themselves_on_next_python_event",
            "idle_or_c_blocked_survivors_can_retain_inert_dispatcher_until_next_event",
            "queued_owned_jobs_entering_only_after_close_are_unobserved",
            "ledger_or_stack_overflow_and_hook_changes_make_coverage_incomplete"] +
            (["non_rpc_parent_setup_is_unobserved_before_first_exact_owned_entry"]
                if observer is not None and observer.parent_rpc_only_before_owned else []),
        outcome_counts=result.counts(), aggregate=summary,
        loaded_source_sha256_before=before, loaded_source_sha256_after=after,
        source_hashes_unchanged=(not changed if before else None), changed_source_modules=changed,
        newly_loaded_source_modules=sorted(set(after) - set(before)))


def _discard_cli_output():
    """Fresh CLI only: suppress late worker output through normal process exit.

    The saved fd receives only a fixed final status. There is deliberately no
    fd/Python-stream restoration window while untouched workers can survive.
    Normal interpreter/executor shutdown still owns those workers.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    console = os.dup(1)
    sink = open(os.devnull, "w")
    os.dup2(sink.fileno(), 1)
    os.dup2(sink.fileno(), 2)
    sys.stdout = sys.stderr = sink
    return console


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cap-seconds", type=float, default=180)
    parser.add_argument("--output", type=Path, default=Path("selected-native-profile.json"))
    arguments = parser.parse_args(argv)
    if not math.isfinite(arguments.cap_seconds) or not 0 < arguments.cap_seconds <= 180:
        parser.error("cap must be positive, finite and at most 180 seconds")
    cap_seconds = arguments.cap_seconds
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tests" / "integration"))
    result, observer = AggregateTestResult(), None
    status, before, after = "setup_error", {}, {}
    module = case = None
    # main belongs to a fresh CLI process, not an embedded/reusable caller.
    console = _discard_cli_output()
    try:
        try:
            module, case = original_case()
            targets, marker = native_targets(module)
            before = source_hashes()
            observer = OwnedThreadObserver(targets, owned_work_code=marker, cap_seconds=cap_seconds,
                parent_rpc_only_before_owned=True)
            with observer:
                unittest.TestSuite((case,)).run(result)
            status = result.fixture_status()
        except ProfileHookUnavailable:
            status = "existing_profile_hook"
        except DiagnosticSoftCap:
            status = "capped"
        except BaseException:
            status = "diagnostic_error"
        finally:
            module = case = None
            try:
                after = source_hashes()
            except BaseException:
                status = "source_hash_error"
        if before and any(after.get(name) != digest for name, digest in before.items()):
            status = "source_changed"
        receipt = build_receipt(status=status, result=result, observer=observer,
            cap_seconds=cap_seconds, before=before, after=after)
        published_head = os.environ.get("GITHUB_SHA", "")
        receipt["published_head_sha"] = published_head if re.fullmatch(r"[0-9a-f]{40}", published_head) else None
        arguments.output.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    except BaseException:
        status = "diagnostic_error"
    # Only fixed vocabulary, never fixture or error strings, reaches this fd.
    os.write(console, ("Selected native aggregate diagnostic: " + status + "\n").encode("ascii"))
    os.close(console)
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
