"""Observe the unchanged chronological fixture; never qualify its latency.

Reuse the aggregate transport observer and its safe outer-RPC soft cap. Only
fixed original synchronous code objects are added, including the declared
capture helper whose first entry follows the fixture's rejected AFTER attempt.
No function return count attests a published capture, seal, route or response.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import sys
from types import CodeType
import unittest


_OBSERVER_PATH = Path(__file__).with_name("profile_selected_transport_boundaries.py")
_SPEC = importlib.util.spec_from_file_location("flora_chronology_transport_observer", _OBSERVER_PATH)
transport = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = transport
_SPEC.loader.exec_module(transport)
BoundaryObserver = transport.BoundaryObserver
AggregateTestResult = transport.AggregateTestResult
DiagnosticSoftCap = transport.DiagnosticSoftCap
ProfileHookUnavailable = transport.ProfileHookUnavailable
Target = transport.Target
discarded_fixture_output = transport.discarded_fixture_output

FIXTURE_MODULE = "test_selected_experiment_preregistration"
FIXTURE_CLASS = "SelectedPreregisteredPhaseRoutesTest"
FIXTURE_METHOD = "test_anchor_before_seal_actual_head_update_after_capture_final_seal_and_four_routes"
FIXTURE_ID = ".".join((FIXTURE_MODULE, FIXTURE_CLASS, FIXTURE_METHOD))
CAPTURE_HELPER_TAG = "fixture.declared_capture_helper"
PROTOCOL_RESPONSE_BUDGET_MS = 60000


def _nested_code(function, name):
    """Select one original direct closure code constant, without making a callable."""
    code = transport._target_function(function)
    matches = [value for value in code.co_consts
        if isinstance(value, CodeType) and value.co_name == name]
    if len(matches) != 1:
        raise ValueError("fixed original closure must have exactly one code object")
    # The reused observer also rejects resumable targets when it is constructed.
    return matches[0]


def original_case():
    module = importlib.import_module(FIXTURE_MODULE)
    return module, getattr(module, FIXTURE_CLASS)(FIXTURE_METHOD)


def chronology_targets(module):
    """Add a small fixed set; none of the installed selected delegates is replaced."""
    from flora.selected import context, experiment_preregistration, experiment_runtime
    from flora.selected import judgment_lineage, phase_snapshots
    custody = experiment_preregistration.XTDBExperimentPreregistrationCustody
    phase = phase_snapshots.XTDBPhaseSnapshotCustody
    method = getattr(getattr(module, FIXTURE_CLASS), FIXTURE_METHOD)
    targets = transport.selected_targets()
    fixed = (
        ("fixture.chronological_body", method),
        ("phase.capture", phase.capture),
        ("phase.slot_capture", phase._slot_capture),
        ("prereg.authorize_slot", custody._authorize_slot),
        ("prereg.authorize_slot_body", custody._authorize_slot_body),
        ("prereg.current", custody._current),
        ("prereg.check_current", custody._check_current),
        ("prereg.history_metadata", experiment_preregistration.PreregisteredHistoryAuthority.authorize_history_metadata),
        ("runtime.context", experiment_runtime.FloRAExperimentRuntime._context),
        ("context.assemble", context.assemble_context),
        ("lineage.context", judgment_lineage.NativeJudgmentLineageVerifier.context_lineage),
        ("lineage.preregistered_context", phase_snapshots.PreregisteredPhaseCaptureLineageVerifier.context_lineage),
    )
    for tag, function in fixed:
        code = transport._target_function(function)
        if code in targets:
            raise ValueError("fixed original target has multiple tags")
        targets[code] = Target(tag)
    for tag, function, name in (
            (CAPTURE_HELPER_TAG, method, "capture"),
            ("phase.capture_guard", phase.capture, "capture_guard"),
            ("phase.personal_gate", phase.capture, "personal_gate")):
        code = _nested_code(function, name)
        if code in targets:
            raise ValueError("fixed original closure has multiple tags")
        targets[code] = Target(tag)
    return targets


def source_hashes():
    """Hash loaded selected/contract/fixture sources without retaining their bytes."""
    hashes = {}
    for name, module in tuple(sys.modules.items()):
        if not (name.startswith(("flora.", "cognitive_kernel.", "test_selected_"))):
            continue
        filename = getattr(module, "__file__", None)
        if filename and Path(filename).suffix == ".py":
            hashes[name] = hashlib.sha256(Path(filename).read_bytes()).hexdigest()
    hashes["chronology_diagnostic_script"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    hashes["transport_observer_script"] = hashlib.sha256(_OBSERVER_PATH.read_bytes()).hexdigest()
    return dict(sorted(hashes.items()))


def build_receipt(*, status, result, observer, cap_seconds, before, after):
    summary = observer.summary() if observer is not None and observer._end_wall is not None else None
    helper_entered = bool(summary and any(row["tag"] == CAPTURE_HELPER_TAG and row["calls"]
        for row in summary["functions"]))
    changed = sorted(name for name, digest in before.items() if after.get(name) != digest)
    return dict(schema_version=1, diagnostic_status=status,
        fixture_id=FIXTURE_ID, qualification=False,
        response_budget_ms=PROTOCOL_RESPONSE_BUDGET_MS,
        completion=("completed" if status == "passed" else "incomplete"),
        soft_cap_seconds=cap_seconds,
        cap_policy="next_selected_outer_rpc_entry_original_active_timeout",
        cap_outcome=("not_observed" if summary is None else
            "stopped_before_rpc" if summary["stopped_before_rpc"] else
            "completed_after_cap" if summary["overshoot_seconds"] > 0 else "within_cap"),
        declared_capture_helper_entry_observed=helper_entered,
        capture_publication_evidence="not_collected_by_aggregate_hook",
        coverage="original_synchronous_parent_thread_only_setup_included",
        coverage_limits=["child_processes_and_other_threads_not_observed",
            "async_generator_and_coroutine_spans_not_targeted",
            "native_work_and_scheduling_appear_as_wall_residual_or_rpc_wait",
            "return_counts_include_exception_unwind_and_are_not_publication_receipts",
            "observer_overhead_precludes_latency_qualification"],
        outcome_counts=result.counts(), aggregate=summary,
        loaded_source_sha256_before=before, loaded_source_sha256_after=after,
        source_hashes_unchanged=(not changed if before else None), changed_source_modules=changed,
        newly_loaded_source_modules=sorted(set(after) - set(before)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cap-seconds", type=float, default=180)
    parser.add_argument("--output", type=Path, default=Path("selected-chronology-profile.json"))
    arguments = parser.parse_args(argv)
    if not math.isfinite(arguments.cap_seconds) or not 0 < arguments.cap_seconds <= 180:
        parser.error("cap must be positive, finite and at most 180 seconds")
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tests" / "integration"))
    result, observer = AggregateTestResult(), None
    status, before, after = "setup_error", {}, {}
    module = case = None
    with discarded_fixture_output():
        try:
            module, case = original_case()
            targets = chronology_targets(module)
            before = source_hashes()
            observer = BoundaryObserver(targets, cap_seconds=arguments.cap_seconds)
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
        cap_seconds=arguments.cap_seconds, before=before, after=after)
    published_head = os.environ.get("GITHUB_SHA", "")
    receipt["published_head_sha"] = published_head if re.fullmatch(r"[0-9a-f]{40}", published_head) else None
    arguments.output.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    print("Selected chronology aggregate diagnostic: " + status)
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
