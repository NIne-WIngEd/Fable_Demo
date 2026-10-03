"""Ownership, bounded sampling and payload/lifetime limits of the diagnostic."""
import gc
import importlib.util
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import threading
from types import SimpleNamespace
import unittest
from weakref import ref

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/profile_selected_native_stacks.py'
if SCRIPT.is_file():
    spec = importlib.util.spec_from_file_location('flora_native_stack_sampler_test', SCRIPT)
    diagnostic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(diagnostic)
else:
    diagnostic = SimpleNamespace(StackSampler=None)

def owned():
    pass

def leaf():
    pass

def frame(code, parent=None, **extra):
    return SimpleNamespace(f_code=code, f_back=parent, **extra)

class NativeStackSamplerTest(unittest.TestCase):
    def sampler(self, **kwargs):
        self.assertIsNotNone(diagnostic.StackSampler, 'fixed-tag native stack sampler is missing')
        return diagnostic.StackSampler({owned.__code__: SimpleNamespace(tag='owned'),
            leaf.__code__: SimpleNamespace(tag='leaf')}, owned_work_code=owned.__code__, **kwargs)

    def test_only_exact_owned_ancestor_is_classified_and_recursive_tags_count_once(self):
        sampler = self.sampler()
        root = frame(owned.__code__)
        sampler.record_snapshot(1, frame(leaf.__code__, frame(leaf.__code__, root)), 10)
        sampler.record_snapshot(2, frame(leaf.__code__), 10)
        sampler.record_snapshot(3, frame(owned.__code__.replace()), 10)
        report = sampler.summary()
        self.assertEqual(report['sampled_owned_stacks'], 1)
        self.assertEqual(report['workers'][0]['deepest_fixed_tag_samples'], {'leaf': 1})
        self.assertEqual(report['workers'][0]['inclusive_fixed_tag_samples'], {'leaf': 1, 'owned': 1})

    def test_window_starts_at_first_sample_and_never_resets_between_owned_jobs(self):
        sampler = self.sampler(cap_seconds=1)
        root = frame(owned.__code__)
        sampler.record_snapshot(1, root, 10)
        sampler.record_snapshot(1, root, 10.5)
        sampler.record_snapshot(1, root, 11)
        sampler.record_snapshot(1, root, 15)
        sampler.record_snapshot(2, root, 15)
        rows = sampler.summary()['workers']
        self.assertEqual([r['samples'] for r in rows], [2, 1])
        self.assertTrue(rows[0]['observation_window_capped'])
        self.assertEqual(rows[0]['first_sample_monotonic'], 10)
        self.assertEqual(rows[0]['last_sample_monotonic'], 10.5)

    def test_depth_and_worker_bounds_are_reported_without_unbounded_retention(self):
        sampler = self.sampler(maximum_workers=1, maximum_stack_depth=2)
        root = frame(owned.__code__)
        sampler.record_snapshot(1, root, 1)
        sampler.record_snapshot(2, root, 1)
        sampler.record_snapshot(3, frame(leaf.__code__, frame(leaf.__code__, root)), 1)
        report = sampler.summary()
        self.assertEqual(len(report['workers']), 1)
        self.assertEqual(report['worker_limit_discarded_samples'], 1)
        self.assertEqual(report['stack_depth_truncations'], 1)

    def test_frames_locals_and_payload_objects_are_not_retained_or_serialized(self):
        sampler = self.sampler()
        class Payload:
            pass
        payload = Payload()
        weak = ref(payload)
        stack = frame(owned.__code__, f_locals={'private': payload, 'text': 'PRIVATE_PAYLOAD_SENTINEL'})
        sampler.record_snapshot(1, stack, 1)
        del payload, stack
        gc.collect()
        self.assertIsNone(weak())
        self.assertNotIn('PRIVATE_PAYLOAD_SENTINEL', json.dumps(sampler.summary()))

    def test_existing_observer_is_preserved_and_not_replaced(self):
        sampler = self.sampler()
        before = sys.getprofile()
        def prior(frame, event, arg):
            pass
        sys.setprofile(prior)
        try:
            with self.assertRaises(diagnostic.native.ProfileHookUnavailable):
                sampler.__enter__()
            self.assertIs(sys.getprofile(), prior)
        finally:
            sys.setprofile(before)

    def test_sampler_failure_is_numeric_and_does_not_raise_into_work(self):
        failed = threading.Event()
        def broken():
            failed.set()
            raise RuntimeError('PRIVATE_FAILURE_SENTINEL')
        sampler = self.sampler(frame_provider=broken, interval_seconds=0.01)
        with sampler:
            self.assertTrue(failed.wait(2))
        report = sampler.summary()
        self.assertEqual(report['observer_errors'], 1)
        self.assertTrue(report['sampler_stopped'])
        self.assertNotIn('PRIVATE_FAILURE_SENTINEL', json.dumps(report))

    def test_live_thread_is_sampled_without_hooks_or_stopping_the_owned_work(self):
        entered, release = threading.Event(), threading.Event()
        def leaf_work():
            entered.set()
            release.wait(5)
        def owned_work():
            leaf_work()
        self.assertIsNotNone(diagnostic.StackSampler, 'fixed-tag native stack sampler is missing')
        sampler = diagnostic.StackSampler({owned_work.__code__: SimpleNamespace(tag='owned'),
            leaf_work.__code__: SimpleNamespace(tag='leaf')}, owned_work_code=owned_work.__code__, interval_seconds=0.01)
        hooks = sys.getprofile(), sys.gettrace(), threading.getprofile(), threading.gettrace()
        worker = threading.Thread(target=owned_work)
        try:
            worker.start()
            self.assertTrue(entered.wait(2))
            with sampler:
                self.assertTrue(sampler.first_owned_sample.wait(2))
            self.assertTrue(worker.is_alive())
            self.assertEqual(hooks, (sys.getprofile(), sys.gettrace(), threading.getprofile(), threading.gettrace()))
            self.assertGreaterEqual(sampler.summary()['sampled_owned_stacks'], 1)
        finally:
            release.set()
            worker.join(2)

    def test_closed_observer_cannot_append_later_samples(self):
        sampler = self.sampler()
        sampler.close()
        sampler.record_snapshot(1, frame(owned.__code__), 1)
        self.assertEqual(sampler.summary()['sampled_owned_stacks'], 0)

    def test_invalid_limits_fail_before_launching_an_observer(self):
        for kwargs in ({'cap_seconds': 181}, {'cap_seconds': float('nan')},
                       {'interval_seconds': 0}, {'maximum_workers': 0}, {'maximum_stack_depth': 0}):
            with self.subTest(kwargs=kwargs):
                self.assertIsNotNone(diagnostic.StackSampler, 'fixed-tag native stack sampler is missing')
                with self.assertRaises(ValueError):
                    self.sampler(**kwargs)

    def cli_receipt(self, provider, fail_fixture=False):
        harness = '''
import importlib.util, pathlib, sys, threading, types, unittest
spec=importlib.util.spec_from_file_location('controlled_stack_cli',sys.argv[1])
d=importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
ready=threading.Event(); active=[]
def owned(): pass
def provider():
    ready.set()
    if sys.argv[3]=='broken': raise RuntimeError('PRIVATE_CLI_FAILURE_SENTINEL')
    return {} if sys.argv[3]=='empty' else {1:types.SimpleNamespace(f_code=owned.__code__,f_back=None)}
original=d.StackSampler
def factory(targets,**kwargs):
    s=original(targets,frame_provider=provider,**kwargs); active.append(s); return s
d.StackSampler=factory
class Case(unittest.TestCase):
    def runTest(self):
        if sys.argv[3]=='healthy': self.assertTrue(active[0].first_owned_sample.wait(2))
        else:
            self.assertTrue(ready.wait(2))
            if sys.argv[3]=='broken': active[0]._thread.join(2)
        if sys.argv[4]=='fail': self.fail('PRIVATE_FIXTURE_FAILURE_SENTINEL')
d.native.original_case=lambda:(types.SimpleNamespace(),Case())
d.native.native_targets=lambda module:({owned.__code__:types.SimpleNamespace(tag='owned')},owned.__code__)
d.source_hashes=lambda:{'controlled_source':'a'*64}
raise SystemExit(d.main(['--output',sys.argv[2]]))
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'numeric.json'
            proc = subprocess.run([sys.executable, '-c', harness, str(SCRIPT), str(path), provider,
                                   'fail' if fail_fixture else 'pass'], capture_output=True, text=True, timeout=10)
            self.assertTrue(path.is_file(), proc.stderr)
            self.assertNotIn('PRIVATE_', proc.stdout+proc.stderr)
            return proc.returncode, json.loads(path.read_text())

    def test_cli_sampler_error_does_not_become_a_successful_fixture_diagnostic(self):
        code, receipt = self.cli_receipt('broken')
        self.assertEqual(code, 1)
        self.assertEqual(receipt['fixture_status'], 'passed')
        self.assertEqual(receipt['diagnostic_status'], 'observer_error')
        self.assertEqual(receipt['aggregate']['observer_errors'], 1)

    def test_cli_zero_samples_are_explicit_unobserved_coverage(self):
        code, receipt = self.cli_receipt('empty')
        self.assertEqual(receipt['observation_status'], 'owned_work_unobserved')
        self.assertEqual(receipt['aggregate']['sampled_owned_stacks'], 0)
        self.assertEqual(receipt['fixture_status'], 'passed')

    def test_cli_healthy_sampling_preserves_passing_and_failed_fixture_outcomes(self):
        for failed in (False, True):
            with self.subTest(failed=failed):
                code, receipt = self.cli_receipt('healthy', fail_fixture=failed)
                self.assertEqual(code, int(failed))
                self.assertEqual(receipt['observation_status'], 'sampled')
                self.assertEqual(receipt['fixture_status'], 'failed' if failed else 'passed')
                self.assertFalse(receipt['qualification'])

if __name__ == '__main__':
    unittest.main()
