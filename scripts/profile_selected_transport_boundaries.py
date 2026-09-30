"""Aggregate-only failure diagnostic; its profiled timings never qualify latency.

Observe original Python code objects without replacing selected delegates. The
soft cap stops only before a new selected RPC body; an active native call keeps
its original timeout. No frames, payloads, queries or failure text are retained.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import dataclass
import hashlib
import importlib
import inspect
import json
import math
import os
from pathlib import Path
import sys
import time
from types import CodeType
import unittest


class DiagnosticSoftCap(BaseException):
    """The next selected RPC was not entered; an active call was not interrupted."""


class ProfileHookUnavailable(RuntimeError):
    """A prior observer must remain untouched."""


@dataclass(frozen=True)
class Target:
    tag: str
    rpc: bool = False


class BoundaryObserver:
    """Keep fixed tags and numeric aggregate clocks, never live call frames."""

    def __init__(self, targets: dict[CodeType, Target], *, cap_seconds=180,
                 wall_clock=time.perf_counter_ns, cpu_clock=time.thread_time_ns):
        if not math.isfinite(cap_seconds) or cap_seconds <= 0:
            raise ValueError("positive finite cap required")
        if any(code.co_flags & (inspect.CO_GENERATOR | inspect.CO_COROUTINE |
                                inspect.CO_ASYNC_GENERATOR) for code in targets):
            raise ValueError("only ordinary synchronous Python entry points")
        # Hold selected code objects alive and use identity, avoiding both code
        # equality aliases and recursive code-constant hashing on every event.
        self._target_codes = tuple(targets)
        self._targets = {id(code): target for code, target in targets.items()}
        self._cap_ns = int(cap_seconds * 1_000_000_000)
        self._wall_clock = wall_clock
        self._cpu_clock = cpu_clock
        self._rows = {target.tag: [0, 0, 0, 0, 0, 0] for target in targets.values()}
        self._stack = []
        self._rpc_depth = 0
        self._installed = False
        self._previous_hook = None
        self._start_wall = self._start_cpu = 0
        self._end_wall = self._end_cpu = None
        self.stopped_before_rpc = False

    def __enter__(self):
        # Both Python hooks and unsupported C profilers are preserved untouched.
        monitoring = getattr(sys, "monitoring", None)
        if (sys.getprofile() is not None or (monitoring is not None and
                monitoring.get_tool(monitoring.PROFILER_ID) is not None)):
            raise ProfileHookUnavailable("existing profile hook")
        self._previous_hook = None
        self._start_wall = self._wall_clock()
        self._start_cpu = self._cpu_clock()
        self._installed = True
        try:
            sys.setprofile(self._profile)
        except BaseException:
            self._installed = False
            raise
        return self

    def __exit__(self, exc_type, exc, traceback):
        if self._installed:
            sys.setprofile(self._previous_hook)
            self._installed = False
        self._end_wall = self._wall_clock()
        self._end_cpu = self._cpu_clock()
        self._close_open(self._end_wall, self._end_cpu)
        return False

    def _finish(self, wall, cpu, *, completed):
        tag, start_wall, start_cpu, child_wall, child_cpu, rpc = self._stack.pop()
        self._rpc_depth -= int(rpc)
        elapsed_wall = max(0, wall - start_wall)
        elapsed_cpu = max(0, cpu - start_cpu)
        row = self._rows[tag]
        row[1] += int(completed)
        row[2] += elapsed_wall
        row[3] += elapsed_cpu
        row[4] += max(0, elapsed_wall - child_wall)
        row[5] += max(0, elapsed_cpu - child_cpu)
        if self._stack:
            self._stack[-1][3] += elapsed_wall
            self._stack[-1][4] += elapsed_cpu

    def _close_open(self, wall, cpu):
        while self._stack:
            self._finish(wall, cpu, completed=False)

    def _profile(self, frame, event, arg):
        # The interpreter supplies frame/arg transiently. Neither is saved.
        if event not in ("call", "return"):
            return
        target = self._targets.get(id(frame.f_code))
        if target is None:
            return
        wall = self._wall_clock()
        cpu = self._cpu_clock()
        if event == "call":
            if target.rpc and self._rpc_depth == 0 and wall - self._start_wall >= self._cap_ns:
                self.stopped_before_rpc = True
                self._close_open(wall, cpu)
                # CPython unsets a profile hook that raises. Cleanup is therefore
                # free to finish; __exit__ restores the prior hook in every case.
                raise DiagnosticSoftCap()
            self._rows[target.tag][0] += 1
            self._stack.append([target.tag, wall, cpu, 0, 0, target.rpc])
            self._rpc_depth += int(target.rpc)
        elif self._stack and self._stack[-1][0] == target.tag:
            self._finish(wall, cpu, completed=True)

    def summary(self):
        wall = self._end_wall if self._end_wall is not None else self._wall_clock()
        cpu = self._end_cpu if self._end_cpu is not None else self._cpu_clock()
        elapsed = max(0, wall - self._start_wall)
        elapsed_cpu = max(0, cpu - self._start_cpu)
        functions = []
        for tag, row in sorted(self._rows.items()):
            functions.append(dict(tag=tag, calls=row[0], completed_calls=row[1],
                wall_seconds=row[2] / 1e9, thread_cpu_seconds=row[3] / 1e9,
                exclusive_wall_seconds=row[4] / 1e9,
                exclusive_thread_cpu_seconds=row[5] / 1e9,
                wait_scheduling_other_thread_seconds=max(0, row[2] - row[3]) / 1e9))
        return dict(elapsed_seconds=elapsed / 1e9,
            thread_cpu_seconds=elapsed_cpu / 1e9,
            overshoot_seconds=max(0, elapsed - self._cap_ns) / 1e9,
            stopped_before_rpc=self.stopped_before_rpc,
            residual_wall_seconds=max(0, elapsed - sum(r[4] for r in self._rows.values())) / 1e9,
            residual_thread_cpu_seconds=max(0, elapsed_cpu - sum(r[5] for r in self._rows.values())) / 1e9,
            functions=functions)


class AggregateTestResult(unittest.TestResult):
    """Unittest outcome counts without test objects or formatted error strings."""

    def __init__(self):
        super().__init__()
        self.failure_count = self.error_count = self.skip_count = 0
        self.expected_failure_count = self.unexpected_success_count = 0
        self.success_count = self.cap_count = 0

    def addSuccess(self, test):
        self.success_count += 1

    def addFailure(self, test, err):
        self.failure_count += 1

    def addError(self, test, err):
        if issubclass(err[0], DiagnosticSoftCap):
            self.cap_count += 1
            self.stop()
        else:
            self.error_count += 1

    def addSubTest(self, test, subtest, err):
        if err is not None:
            if issubclass(err[0], DiagnosticSoftCap):
                self.cap_count += 1
                self.stop()
            elif issubclass(err[0], test.failureException):
                self.failure_count += 1
            else:
                self.error_count += 1

    def addSkip(self, test, reason):
        self.skip_count += 1

    def addExpectedFailure(self, test, err):
        self.expected_failure_count += 1

    def addUnexpectedSuccess(self, test):
        self.unexpected_success_count += 1

    def wasSuccessful(self):
        return not (self.failure_count or self.error_count or self.cap_count or
                    self.unexpected_success_count)

    def fixture_status(self):
        if self.cap_count:
            return "capped"
        if self.error_count:
            return "error"
        if self.failure_count or self.unexpected_success_count:
            return "failed"
        if self.skip_count and not self.success_count:
            return "skipped"
        return "passed"

    def counts(self):
        return dict(tests=self.testsRun, passed=self.success_count,
            failures=self.failure_count, errors=self.error_count,
            skipped=self.skip_count, expected_failures=self.expected_failure_count,
            unexpected_successes=self.unexpected_success_count, capped=self.cap_count)


@contextmanager
def discarded_fixture_output():
    """Discard Python and native fd output without buffering any fixture text."""
    saved = []
    with open(os.devnull, "w") as sink:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
            for fd in (1, 2):
                saved.append((fd, os.dup(fd)))
                os.dup2(sink.fileno(), fd)
            with redirect_stdout(sink), redirect_stderr(sink):
                yield
        finally:
            for fd, original in saved:
                os.dup2(original, fd)
                os.close(original)


def _target_function(function):
    """Unwrap SDK decorators without modifying the original installed callable."""
    function = inspect.unwrap(function)
    if not inspect.isfunction(function):
        raise TypeError("a known original Python function is required")
    return function.__code__


def selected_targets():
    """Only fixed original synchronous selected boundaries are observable."""
    from kurrentdbclient import KurrentDBClient
    from psycopg import Connection, Cursor
    from flora.selected import comparison_custody, experience, formation_policy
    from flora.selected import formation_registry, history_fence, phase_source_fence
    fixed = (
        ("rpc.kurrent_get_stream", KurrentDBClient.get_stream, True),
        ("rpc.psycopg_execute", Connection.execute, True),
        ("rpc.psycopg_fetchall", Cursor.fetchall, True),
        ("experience.replay_committed", experience.KurrentExperienceLog.replay_committed, False),
        ("experience.decode_event", experience.decode_event, False),
        ("experience.native_gateway", experience._native_codec_gateway, False),
        ("experience.native_contracts", experience._native_contracts_current, False),
        ("experience.restore_envelope", experience._restore_envelope, False),
        ("history.verify_metadata", history_fence._verify_current_history_metadata, False),
        ("history.verify_external_metadata", history_fence.verify_history_and_external_metadata, False),
        ("source.prime_rows", phase_source_fence.OneGuardSelectedMetadata._prime_rows, False),
        ("source.final_rows", phase_source_fence.OneGuardSelectedMetadata.verify_final_current_rows, False),
        ("registry.fetch", formation_registry.XTDBFormationSourceRegistry._fetch, False),
        ("comparison.metadata", comparison_custody.XTDBComparisonCustody.metadata, False),
        ("permissions.current_action", formation_policy.XTDBFormationPermissionPolicy.current_action, False),
        ("permissions.stored_action", formation_policy.XTDBFormationPermissionPolicy._stored_action, False),
        ("permissions.permits", formation_policy.XTDBFormationPermissionPolicy.permits, False),
    )
    return {_target_function(function): Target(tag, rpc) for tag, function, rpc in fixed}


def loaded_source_hashes():
    result = {}
    for name in ("flora.selected.experience", "flora.selected.history_fence",
                 "flora.selected.phase_source_fence", "flora.selected.formation_registry",
                 "flora.selected.formation_policy", "flora.selected.comparison_custody"):
        module = importlib.import_module(name)
        result[name] = hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
    result["diagnostic_script"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cap-seconds", type=float, default=180)
    parser.add_argument("--output", type=Path, default=Path("selected-transport-profile.json"))
    arguments = parser.parse_args(argv)
    if not math.isfinite(arguments.cap_seconds) or not 0 < arguments.cap_seconds <= 180:
        parser.error("cap must be positive, finite and at most 180 seconds")
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tests" / "integration"))
    result = AggregateTestResult()
    observer = None
    status = "setup_error"
    hashes = {}
    # Import/setup errors and fixture failures must not become payload logs.
    with discarded_fixture_output():
        try:
            targets = selected_targets()
            hashes = loaded_source_hashes()
            module = importlib.import_module("test_selected_comparator_memory")
            case = module.SelectedComparatorIntegrationTest(
                "test_phase_isolated_hybrid_memory_and_separately_authorized_signed_exchange")
            observer = BoundaryObserver(targets, cap_seconds=arguments.cap_seconds)
            with observer:
                unittest.TestSuite((case,)).run(result)
            status = result.fixture_status()
        except ProfileHookUnavailable:
            status = "existing_profile_hook"
        except DiagnosticSoftCap:
            status = "capped"
        except BaseException:
            # Deliberately retain no exception, traceback, or fixture object.
            status = "diagnostic_error"
    summary = observer.summary() if observer is not None and observer._end_wall is not None else None
    receipt = dict(schema_version=1, diagnostic_status=status,
        qualification=False, response_budget_ms=10000,
        soft_cap_seconds=arguments.cap_seconds,
        cap_policy="next_selected_rpc_entry_original_active_timeout",
        cap_outcome=("stopped_before_rpc" if summary and summary["stopped_before_rpc"]
            else "completed_after_cap" if summary and summary["overshoot_seconds"] > 0
            else "within_cap"),
        outcome_counts=result.counts(), aggregate=summary,
        loaded_source_sha256=hashes)
    arguments.output.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    # Fixed console status only; the artifact contains the aggregate evidence.
    print("Selected transport aggregate diagnostic: " + status)
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
