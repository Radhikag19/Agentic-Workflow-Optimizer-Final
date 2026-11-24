"""
Local Python Subprocess Worker Entry Point for MAS Execution.

Invoked by `LocalSubprocessExecutionManager` via `sys.executable -m optimization_agent.sandbox.runtime.worker`
with explicit `cwd`, isolated `PYTHONPATH`, and filtered Groq API environment variables.
Communicates exclusively via sanitized JSON request/response payloads without ever
accepting or logging raw API keys in CLI arguments or JSON files.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from optimization_agent.key_manager import get_default_key_manager
from optimization_agent.sandbox.manager import SandboxEnvironment
from optimization_agent.sandbox.runtime.runner import SandboxWorkflowRunner, _write_text_with_retry

WORKER_STDOUT_PREFIX = "AWO_WORKER_RESULT_JSON:"


def _check_runtime_dependencies(enable_trace_replay_fallback: bool) -> Optional[str]:
    """Verify required local packages are installed; never attempts auto-installation."""
    missing: List[str] = []
    if importlib.util.find_spec("pydantic") is None:
        missing.append("pydantic")
    if not enable_trace_replay_fallback and importlib.util.find_spec("groq") is None:
        missing.append("groq")
    if missing:
        return (
            f"Missing required Python package(s) in local environment ({sys.executable}): "
            f"{', '.join(missing)}. Install them in your active Python environment and retry."
        )
    return None


def _build_env_descriptor(request: Dict[str, Any]) -> SandboxEnvironment:
    """Reconstruct read-only/sandbox path descriptor inside the worker subprocess."""
    exp_dir = Path(request["experiment_dir"]).resolve()
    sb_dir = Path(request["sandbox_workflow_directory"]).resolve()
    orig_dir = Path(request["original_workflow_directory"]).resolve()
    traces_dir = Path(request["trace_directory"]).resolve()

    scope_path = exp_dir / "approved_scope.json"
    approved_scope = (
        json.loads(scope_path.read_text(encoding="utf-8"))
        if scope_path.exists()
        else {"workflow_id": request["workflow_id"], "approved_candidate_ids": []}
    )
    return SandboxEnvironment(
        experiment_id=str(request["experiment_id"]),
        workflow_id=str(request["workflow_id"]),
        experiment_dir=exp_dir,
        sandbox_workflow_dir=sb_dir,
        runtime_traces_dir=traces_dir,
        original_workflow_dir=orig_dir,
        approved_scope=approved_scope,
        approved_scope_path=scope_path,
        experiment_metadata_path=exp_dir / "experiment_metadata.json",
        original_file_hashes={},
        original_to_sandbox_map={},
        sandbox_to_original_map={},
        created_at="",
    )


def execute_worker_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a single baseline or optimized workflow worker request deterministically."""
    t0 = time.perf_counter()
    key_mgr = get_default_key_manager()

    exp_id = str(request.get("experiment_id") or "")
    wf_id = str(request.get("workflow_id") or "")
    variant = str(request.get("variant") or "optimized")
    wf_dir = Path(str(request.get("workflow_directory") or ".")).resolve()
    trace_dir = Path(str(request.get("trace_directory") or (wf_dir / "traces"))).resolve()
    enable_replay = bool(request.get("enable_trace_replay_fallback", False))
    evidence_dir = request.get("evidence_dir")
    data_base_dir_raw = request.get("data_base_dir")
    data_base_dir = Path(data_base_dir_raw).resolve() if data_base_dir_raw else None
    sample_inputs = request.get("sample_inputs")
    run_indices = request.get("run_indices")
    num_runs = int(request.get("num_runs") or (len(sample_inputs) if isinstance(sample_inputs, list) else 1))

    # Disallow baseline re-execution: fixed historical baseline evidence must be reused instead
    if variant == "baseline":
        err_msg = (
            "Baseline re-execution is disabled: fixed historical baseline traces and metrics "
            "must be reused rather than executing baseline agents."
        )
        return {
            "experiment_id": exp_id,
            "workflow_id": wf_id,
            "variant": variant,
            "execution_mode": "disabled",
            "execution_status": "FAILED",
            "workflow_directory": str(wf_dir),
            "run_id": None,
            "run_ids": [],
            "groq_api_calls": 0,
            "agent_execution_results": {
                "variant": variant,
                "execution_passed": False,
                "groq_api_calls": 0,
                "errors": [err_msg],
                "traces": [],
            },
            "trace_directory": str(trace_dir),
            "api_errors": [],
            "execution_duration": round(time.perf_counter() - t0, 4),
            "python_executable": sys.executable,
            "sys_path_head": sys.path[0] if sys.path else "",
            "error_details": err_msg,
        }

    # Enforce strict module resolution priority for the target workflow directory
    wf_dir_str = str(wf_dir)
    if not sys.path or sys.path[0] != wf_dir_str:
        sys.path = [wf_dir_str] + [p for p in sys.path if p != wf_dir_str]

    dep_err = _check_runtime_dependencies(enable_replay)
    if dep_err:
        return {
            "experiment_id": exp_id,
            "workflow_id": wf_id,
            "variant": variant,
            "execution_mode": "offline_trace_replay_sandbox" if enable_replay else "live_llm_execution",
            "execution_status": "FAILED",
            "workflow_directory": str(wf_dir),
            "run_id": None,
            "run_ids": [],
            "agent_execution_results": {
                "variant": variant,
                "execution_passed": False,
                "execution_modes": ["live_llm_execution"],
                "usage_sources": ["unavailable"],
                "runs_executed": 0,
                "successful_runs": 0,
                "failed_runs": num_runs,
                "incomplete_runs": [],
                "concurrent_waves_executed": [],
                "input_dataset_hashes": [],
                "trace_files": [],
                "traces": [],
                "schema_validation_summary": {"all_schemas_valid": False, "failures": []},
                "invalid_replay_samples": [],
                "api_errors": [],
                "fallback_events": [],
                "errors": [dep_err],
            },
            "trace_directory": str(trace_dir),
            "api_errors": [],
            "execution_duration": round(time.perf_counter() - t0, 4),
            "python_executable": sys.executable,
            "sys_path_head": sys.path[0],
            "error_details": dep_err,
        }

    try:
        env_desc = _build_env_descriptor(request)
        event_log_raw = request.get("event_log_file")
        event_cb: Optional[Callable[[Dict[str, Any]], None]] = None
        if event_log_raw:
            ev_path = Path(str(event_log_raw)).resolve()
            ev_path.parent.mkdir(parents=True, exist_ok=True)
            ev_lock = threading.Lock()

            def _append_event(ev: Dict[str, Any]) -> None:
                line = key_mgr.sanitize_text(json.dumps(ev, default=str)) + "\n"
                with ev_lock:
                    with ev_path.open("a", encoding="utf-8") as fh:
                        fh.write(line)

            event_cb = _append_event

        runner = SandboxWorkflowRunner(
            enable_trace_replay_fallback=enable_replay,
            evidence_dir=evidence_dir,
            data_base_dir=data_base_dir,
            event_callback=event_cb,
        )
        run_res = runner.run_variant(
            env_desc,
            variant=variant,
            num_runs=num_runs,
            sample_inputs=sample_inputs if isinstance(sample_inputs, list) else None,
            traces_dir=trace_dir,
            run_indices=run_indices if isinstance(run_indices, list) else None,
        )
        traces = list(run_res.get("traces") or [])
        run_ids = [t.get("run_id") for t in traces if t.get("run_id")]
        modes = list(run_res.get("execution_modes") or [])
        exec_mode = modes[0] if len(modes) == 1 else (modes or ("offline_trace_replay_sandbox" if enable_replay else "live_llm_execution"))
        status = "SUCCESS" if run_res.get("execution_passed") else "FAILED"
        errs = list(run_res.get("errors") or [])

        return {
            "experiment_id": exp_id,
            "workflow_id": wf_id,
            "variant": variant,
            "execution_mode": exec_mode,
            "execution_status": status,
            "workflow_directory": str(wf_dir),
            "run_id": run_ids[0] if run_ids else None,
            "run_ids": run_ids,
            "groq_api_calls": int(run_res.get("groq_api_calls") or 0),
            "agent_execution_results": run_res,
            "trace_directory": str(trace_dir),
            "api_errors": list(run_res.get("api_errors") or []),
            "execution_duration": round(time.perf_counter() - t0, 4),
            "python_executable": sys.executable,
            "sys_path_head": sys.path[0],
            "error_details": "; ".join(errs) if errs else None,
        }
    except Exception as exc:
        sanitized = key_mgr.sanitize_text(f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=5)}")
        return {
            "experiment_id": exp_id,
            "workflow_id": wf_id,
            "variant": variant,
            "execution_mode": "offline_trace_replay_sandbox" if enable_replay else "live_llm_execution",
            "execution_status": "FAILED",
            "workflow_directory": str(wf_dir),
            "run_id": None,
            "run_ids": [],
            "agent_execution_results": {
                "variant": variant,
                "execution_passed": False,
                "execution_modes": ["live_llm_execution"],
                "usage_sources": ["unavailable"],
                "runs_executed": 0,
                "successful_runs": 0,
                "failed_runs": num_runs,
                "incomplete_runs": [],
                "concurrent_waves_executed": [],
                "input_dataset_hashes": [],
                "trace_files": [],
                "traces": [],
                "schema_validation_summary": {"all_schemas_valid": False, "failures": []},
                "invalid_replay_samples": [],
                "api_errors": [],
                "fallback_events": [],
                "errors": [sanitized],
            },
            "trace_directory": str(trace_dir),
            "api_errors": [],
            "execution_duration": round(time.perf_counter() - t0, 4),
            "python_executable": sys.executable,
            "sys_path_head": sys.path[0],
            "error_details": sanitized,
        }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="AWO Local Subprocess Workflow Worker")
    parser.add_argument("--request-file", type=str, default=None, help="Path to non-secret worker request JSON.")
    parser.add_argument("--response-file", type=str, default=None, help="Path to write structured worker response JSON.")
    args = parser.parse_args(argv)

    key_mgr = get_default_key_manager()
    try:
        if args.request_file:
            req_data = json.loads(Path(args.request_file).read_text(encoding="utf-8"))
        else:
            req_data = json.loads(sys.stdin.read())
        payload = execute_worker_request(req_data)
        exit_code = 0
    except Exception as exc:
        err_msg = key_mgr.sanitize_text(f"Worker startup failed: {exc}")
        payload = {
            "experiment_id": "",
            "workflow_id": "",
            "execution_mode": "unknown",
            "execution_status": "FAILED",
            "workflow_directory": str(Path.cwd()),
            "run_id": None,
            "agent_execution_results": {"execution_passed": False, "errors": [err_msg], "traces": []},
            "trace_directory": "",
            "api_errors": [],
            "execution_duration": 0.0,
            "python_executable": sys.executable,
            "error_details": err_msg,
        }
        exit_code = 1

    sanitized_json = key_mgr.sanitize_text(json.dumps(payload, default=str))
    if args.response_file:
        resp_p = Path(args.response_file)
        try:
            _write_text_with_retry(resp_p, sanitized_json)
        except PermissionError:
            pass

    # Emit delimited machine-readable result so diagnostic prints never corrupt parsing
    sys.stdout.write(f"\n{WORKER_STDOUT_PREFIX}{sanitized_json}\n")
    sys.stdout.flush()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
