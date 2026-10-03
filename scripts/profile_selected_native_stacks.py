"""Fixed-tag owned-worker stack samples; never latency or authority proof.

No call/trace hook, delegate replacement, frame/local/payload retention or worker
interruption. Samples indicate observed wall residency, not CPU or call counts.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
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

_NATIVE_PATH = Path(__file__).with_name('profile_selected_native_boundaries.py')
_SPEC = importlib.util.spec_from_file_location('flora_native_sampling_reference', _NATIVE_PATH)
native = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = native
_SPEC.loader.exec_module(native)


class StackSampler:
    """Finite numeric rows; code identities classify observation, never authority."""

    def __init__(self, targets, *, owned_work_code, interval_seconds=0.05,
                 cap_seconds=180, maximum_workers=32, maximum_stack_depth=256,
                 frame_provider=sys._current_frames, clock=time.monotonic):
        if (not math.isfinite(cap_seconds) or not 0 < cap_seconds <= 180
                or not math.isfinite(interval_seconds) or not 0.01 <= interval_seconds <= 1
                or type(maximum_workers) is not int or not 1 <= maximum_workers <= 32
                or type(maximum_stack_depth) is not int or not 1 <= maximum_stack_depth <= 256):
            raise ValueError('bounded positive observation limits required')
        if type(owned_work_code) is not CodeType or any(type(c) is not CodeType for c in targets):
            raise ValueError('fixed original code objects required')
        self._codes = tuple(targets) + (owned_work_code,)
        self._targets = {id(c): target.tag for c, target in targets.items()}
        self._owned_code_id = id(owned_work_code)
        self._frames, self._clock = frame_provider, clock
        self.interval_seconds, self.cap_seconds = interval_seconds, cap_seconds
        self.maximum_workers, self.maximum_stack_depth = maximum_workers, maximum_stack_depth
        self._workers = {}
        self._stop, self.first_owned_sample = threading.Event(), threading.Event()
        self._lock, self._thread = threading.Lock(), None
        self._closed = False
        self.observer_errors = self.stack_depth_truncations = self.worker_limit_discarded_samples = 0
        self.thread_scan_truncations = self.polls = self.sampled_owned_stacks = 0
        self.start_monotonic = self.end_monotonic = None

    def __enter__(self):
        monitoring = getattr(sys, 'monitoring', None)
        if (sys.getprofile() is not None or sys.gettrace() is not None
                or threading.getprofile() is not None or threading.gettrace() is not None
                or monitoring is not None and any(monitoring.get_tool(tool) is not None
                    for tool in (monitoring.PROFILER_ID, monitoring.DEBUGGER_ID))):
            raise native.ProfileHookUnavailable('existing observer')
        if self._closed or self._thread is not None:
            raise RuntimeError('sampler is single use')
        self.start_monotonic = self._clock()
        self._thread = threading.Thread(target=self._run, name='flora-numeric-stack-sampler', daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
        return False

    def close(self):
        self._stop.set()
        with self._lock:
            self._closed = True
            if self.end_monotonic is None:
                self.end_monotonic = self._clock()
        if self._thread is not None:
            self._thread.join(timeout=1)

    def record_snapshot(self, thread_id, frame, now):
        """Inspect transient code/back links only; frames and locals are not saved."""
        with self._lock:
            if self._closed:
                return
            current, tags, owned = frame, [], False
            try:
                for _ in range(self.maximum_stack_depth):
                    if current is None:
                        break
                    code_id = id(current.f_code)
                    owned = owned or code_id == self._owned_code_id
                    tag = self._targets.get(code_id)
                    if tag is not None and tag not in tags:
                        tags.append(tag)
                    current = current.f_back
                else:
                    if current is not None:
                        self.stack_depth_truncations += 1
                        return
                if not owned:
                    return
                row = self._workers.get(thread_id)
                if row is None:
                    if len(self._workers) >= self.maximum_workers:
                        self.worker_limit_discarded_samples += 1
                        return
                    row = dict(first_sample_monotonic=now, last_sample_monotonic=now,
                               samples=0, observation_window_capped=False,
                               inclusive_fixed_tag_samples={}, deepest_fixed_tag_samples={})
                    self._workers[thread_id] = row
                if now - row['first_sample_monotonic'] >= self.cap_seconds:
                    row['observation_window_capped'] = True
                    return
                row['last_sample_monotonic'] = now
                row['samples'] += 1
                for tag in tags:
                    values = row['inclusive_fixed_tag_samples']
                    values[tag] = values.get(tag, 0) + 1
                deepest = tags[0] if tags else 'unmapped_owned_stack'
                values = row['deepest_fixed_tag_samples']
                values[deepest] = values.get(deepest, 0) + 1
                self.sampled_owned_stacks += 1
                self.first_owned_sample.set()
            finally:
                current = frame = None

    def _run(self):
        try:
            while not self._stop.is_set():
                snapshots = None
                frame = None
                try:
                    snapshots = self._frames()
                    now = self._clock()
                    self.polls += 1
                    if len(snapshots) > 128:
                        self.thread_scan_truncations += 1
                    for index, (thread_id, frame) in enumerate(snapshots.items()):
                        if index >= 128:
                            break
                        self.record_snapshot(thread_id, frame, now)
                finally:
                    frame = snapshots = None
                if self._stop.wait(self.interval_seconds):
                    break
        except BaseException:
            # Observation failure cannot raise into a fixture/worker or serialize its error.
            with self._lock:
                self.observer_errors += 1

    def summary(self):
        with self._lock:
            return dict(interval_seconds=self.interval_seconds, worker_observation_cap_seconds=self.cap_seconds,
                polls=self.polls, sampled_owned_stacks=self.sampled_owned_stacks,
                stack_depth_truncations=self.stack_depth_truncations,
                thread_scan_truncations=self.thread_scan_truncations,
                worker_limit_discarded_samples=self.worker_limit_discarded_samples,
                observer_errors=self.observer_errors,
                sampler_stopped=self._thread is None or not self._thread.is_alive(),
                workers=[dict(row, inclusive_fixed_tag_samples=dict(row['inclusive_fixed_tag_samples']),
                              deepest_fixed_tag_samples=dict(row['deepest_fixed_tag_samples']))
                         for row in self._workers.values()])


def source_hashes():
    values = native.source_hashes()
    values['native_stack_sampling_script'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return values


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cap-seconds', type=float, default=180)
    parser.add_argument('--interval-seconds', type=float, default=0.05)
    parser.add_argument('--output', type=Path, default=Path('selected-native-stack-samples.json'))
    args = parser.parse_args(argv)
    if (not math.isfinite(args.cap_seconds) or not 0 < args.cap_seconds <= 180
            or not math.isfinite(args.interval_seconds) or not 0.01 <= args.interval_seconds <= 1):
        parser.error('bounded finite sampling limits required')
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'tests/integration'))
    result, sampler, before, after = native.AggregateTestResult(), None, {}, {}
    status, module, case = 'setup_error', None, None
    console = native._discard_cli_output()
    try:
        try:
            module, case = native.original_case()
            targets, marker = native.native_targets(module)
            before = source_hashes()
            sampler = StackSampler(targets, owned_work_code=marker,
                cap_seconds=args.cap_seconds, interval_seconds=args.interval_seconds)
            with sampler:
                unittest.TestSuite((case,)).run(result)
            status = result.fixture_status()
        except native.ProfileHookUnavailable:
            status = 'existing_observer'
        except BaseException:
            status = 'diagnostic_error'
        finally:
            module = case = None
            if sampler is not None:
                sampler.close()
            try:
                after = source_hashes()
            except BaseException:
                status = 'source_hash_error'
        changed = sorted(name for name, digest in before.items() if after.get(name) != digest)
        if changed:
            status = 'source_changed'
        aggregate = None if sampler is None else sampler.summary()
        fixture_status = result.fixture_status() if result.testsRun else 'not_run'
        observation_status = ('not_started' if aggregate is None else
            'observer_error' if aggregate['observer_errors'] or not aggregate['sampler_stopped'] else
            'owned_work_unobserved' if not aggregate['sampled_owned_stacks'] else
            'partial' if (aggregate['stack_depth_truncations'] or aggregate['thread_scan_truncations']
                or aggregate['worker_limit_discarded_samples']
                or any(row['observation_window_capped'] for row in aggregate['workers'])) else 'sampled')
        # A successful fixture cannot turn a failed observer into a passed diagnostic.
        # Unobserved/partial coverage stays explicit rather than relabeling the fixture.
        if status == 'passed' and observation_status == 'observer_error':
            status = 'observer_error'
        head = os.environ.get('GITHUB_SHA', '')
        receipt = dict(schema_version=1, fixture_id=native.FIXTURE_ID,
            diagnostic_status=status, fixture_status=fixture_status,
            observation_status=observation_status, qualification=False, learned_behavior_run=False,
            response_budget_ms=native.PROTOCOL_RESPONSE_BUDGET_MS,
            published_head_sha=head if re.fullmatch('[0-9a-f]{40}', head) else None,
            outcome_counts=result.counts(), aggregate=aggregate,
            loaded_source_sha256_before=before, loaded_source_sha256_after=after,
            source_hashes_unchanged=not changed if before else None, changed_source_modules=changed,
            newly_loaded_source_modules=sorted(set(after)-set(before)),
            limits=['Owned identity is a sampled original-code ancestor, not exact job entry/lifecycle counts.',
                    'Observation window begins at each thread identifier first sampled owned frame and never resets.',
                    'Thread identifiers can be reused; distinct thread lifetimes and short jobs may be missed.',
                    'Fixed-interval wall samples are biased by GIL scheduling, native calls and thread activity.',
                    'Snapshots can be stale before inspection; no CPU, exact durations or call counts are inferred.',
                    'Deepest fixed tag includes untargeted descendants; inclusive tags overlap and cannot be summed.',
                    'Parent/setup attribution is unobserved; polling itself adds unmeasured diagnostic overhead.',
                    'No call/trace hooks, delegates or response/CI deadlines are changed.',
                    'Only fixed labels, numeric aggregates and source digests are saved; frames/locals/payloads are transient.',
                    'Closing/capping observation does not stop, cancel or wait for owned worker completion.'])
        args.output.write_text(json.dumps(receipt, sort_keys=True, indent=2)+'\n', encoding='utf-8')
    except BaseException:
        status = 'diagnostic_error'
    os.write(console, ('Selected native stack diagnostic: '+status+'\n').encode('ascii'))
    os.close(console)
    return 0 if status == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
