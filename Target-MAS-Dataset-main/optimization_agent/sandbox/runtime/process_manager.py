"""
Local Python Subprocess Execution Manager for Optimized Sandbox Workflows.

Launches ONLY the optimized (`sandbox_workflow_dir`) MAS workflow in isolated local OS
Python subprocesses using `sys.executable`, explicit `cwd=sandbox_workflow_dir`, isolated
`PYTHONPATH`, and filtered Groq API credentials via `GroqKeyManager` — without ever
re-executing baseline agents, without launching baseline subprocesses, and without
passing secrets via CLI args or request JSON.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from common.api_key_manager import WORKFLOW_KEY_ENV_MAP
from optimization_agent.key_manager import FAILOVER_KEYS, GroqKeyManager, get_default_key_manager
from optimization_agent.sandbox.evaluation.baseline_loader import compute_canonical_input_hash
from optimization_agent.sandbox.manager import SandboxEnvironment
from optimization_agent.sandbox.runtime.runner import _write_text_with_retry

WORKER_STDOUT_PREFIX = "AWO_WORKER_RESULT_JSON:"

_SAFE_SYSTEM_ENV_VARS: Tuple[str, ...] = (
    "PATH",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "PATHEXT",
    "HOME",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "SSL_CERT_FILE",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "PYTHONIOENCODING",
    "PYTHONUTF8",
)


def _compute_input_hash(run_input: Dict[str, Any]) -> str:
    return compute_canonical_input_hash(run_input)


def build_subprocess_env(
    *,
    workflow_id: str,
    workflow_dir: Path,
    project_root: Path,
    key_mgr: Optional[GroqKeyManager] = None,
) -> Dict[str, str]:
    """
    Construct a minimal environment dictionary for the optimized worker subprocess:
    - Places `workflow_dir` FIRST on `PYTHONPATH`, followed by `project_root`, ensuring
      module imports resolve to the active sandbox copy rather than original workflow files.
    - Forwards only required OS variables and the workflow's designated Groq API keys
      (plus failover keys) loaded from local `.env` / `os.environ`.
    """
    sub_env: Dict[str, str] = {}
    for var in _SAFE_SYSTEM_ENV_VARS:
        val = os.environ.get(var)
        if val:
            sub_env[var] = val

    sub_env["PYTHONPATH"] = f"{workflow_dir.resolve()}{os.pathsep}{project_root.resolve()}"
    sub_env["AWO_ACTIVE_WORKFLOW_DIR"] = str(workflow_dir.resolve())
    sub_env["PYTHONUNBUFFERED"] = "1"
    sub_env["PYTHONIOENCODING"] = "utf-8"

    mgr = key_mgr or get_default_key_manager()
    required_key_vars: List[str] = list(WORKFLOW_KEY_ENV_MAP.get(workflow_id, ()))
    for extra_var in ("GROQ_API_KEY_1", "GROQ_API_KEY_11", "GROQ_API_KEY_12", "GROQ_API_KEY"):
        if extra_var not in required_key_vars:
            required_key_vars.append(extra_var)
    for fk in FAILOVER_KEYS:
        if fk not in required_key_vars:
            required_key_vars.append(fk)

    for key_var in required_key_vars:
        raw_val = (mgr._keys.get(key_var) or os.environ.get(key_var) or "").strip()
        if raw_val:
            sub_env[key_var] = raw_val

    return sub_env


def _parse_worker_stdout(stdout_text: str) -> Optional[Dict[str, Any]]:
    for line in reversed((stdout_text or "").splitlines()):
        stripped = line.strip()
        if stripped.startswith(WORKER_STDOUT_PREFIX):
            raw_json = stripped[len(WORKER_STDOUT_PREFIX) :].strip()
            try:
                parsed = json.loads(raw_json)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
    return None


class LocalSubprocessExecutionManager:
    """Launches ONLY the optimized workflow in isolated local Python subprocesses."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 300.0,
        python_executable: Optional[str] = None,
        subprocess_runner: Optional[Callable[..., Any]] = None,
    ):
        self.timeout_seconds = float(timeout_seconds)
        self.python_executable = python_executable or sys.executable
        self.subprocess_runner = subprocess_runner or subprocess.run
        self.key_mgr = get_default_key_manager()
        self.project_root = Path(__file__).resolve().parent.parent.parent.parent

    def run_workflow_subprocess(
        self,
        env: SandboxEnvironment,
        *,
        variant: str = "optimized",
        sample_inputs: List[Dict[str, Any]],
        enable_trace_replay_fallback: bool = False,
        evidence_dir: Optional[str] = None,
        data_base_dir: Optional[Path] = None,
        traces_dir: Optional[Path] = None,
        run_indices: Optional[List[int]] = None,
        run_label: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Execute ONLY 'optimized' (`sandbox_workflow_dir`) in a separate local Python OS process."""
        if variant != "optimized":
            raise ValueError(
                f"Baseline subprocess execution is disabled (got variant={variant!r}); "
                "load fixed historical baseline evidence instead."
            )

        workflow_dir = env.sandbox_workflow_dir.resolve()
        dest_traces_dir = (traces_dir or env.runtime_traces_dir).resolve()
        dest_traces_dir.mkdir(parents=True, exist_ok=True)

        logs_dir = (env.experiment_dir / "process_logs").resolve()
        logs_dir.mkdir(parents=True, exist_ok=True)
        label = run_label or "optimized"
        req_path = logs_dir / f"{label}_request.json"
        resp_path = logs_dir / f"{label}_response.json"
        event_log_path = logs_dir / f"{label}_events.jsonl"

        # Request JSON strictly contains zero credentials
        worker_request = {
            "experiment_id": env.experiment_id,
            "workflow_id": env.workflow_id,
            "variant": "optimized",
            "workflow_directory": str(workflow_dir),
            "original_workflow_directory": str(env.original_workflow_dir.resolve()),
            "sandbox_workflow_directory": str(env.sandbox_workflow_dir.resolve()),
            "experiment_dir": str(env.experiment_dir.resolve()),
            "trace_directory": str(dest_traces_dir),
            "event_log_file": str(event_log_path),
            "enable_trace_replay_fallback": bool(enable_trace_replay_fallback),
            "evidence_dir": evidence_dir,
            "data_base_dir": str(data_base_dir.resolve()) if data_base_dir else None,
            "sample_inputs": sample_inputs,
            "run_indices": run_indices if run_indices is not None else list(range(len(sample_inputs))),
            "num_runs": len(sample_inputs),
        }
        _write_text_with_retry(
            req_path,
            self.key_mgr.sanitize_text(json.dumps(worker_request, indent=2, default=str)),
        )

        sub_env = build_subprocess_env(
            workflow_id=env.workflow_id,
            workflow_dir=workflow_dir,
            project_root=self.project_root,
            key_mgr=self.key_mgr,
        )
        cmd = [
            self.python_executable,
            "-m",
            "optimization_agent.sandbox.runtime.worker",
            "--request-file",
            str(req_path),
            "--response-file",
            str(resp_path),
        ]
        eff_timeout = float(timeout_seconds if timeout_seconds is not None else self.timeout_seconds)
        input_hashes = [_compute_input_hash(inp) for inp in sample_inputs]

        t0 = time.perf_counter()
        timed_out = False
        exit_code: int = -1
        stdout_text = ""
        stderr_text = ""
        worker_payload: Optional[Dict[str, Any]] = None
        proc_error: Optional[str] = None

        try:
            completed = self.subprocess_runner(
                cmd,
                cwd=str(workflow_dir),
                env=sub_env,
                capture_output=True,
                text=True,
                timeout=eff_timeout,
            )
            exit_code = int(getattr(completed, "returncode", -1))
            stdout_text = self.key_mgr.sanitize_text(str(getattr(completed, "stdout", "") or ""))
            stderr_text = self.key_mgr.sanitize_text(str(getattr(completed, "stderr", "") or ""))
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            exit_code = -1
            stdout_text = self.key_mgr.sanitize_text(str(getattr(exc, "stdout", "") or ""))
            stderr_text = self.key_mgr.sanitize_text(str(getattr(exc, "stderr", "") or ""))
            proc_error = f"Local optimized subprocess '{label}' timed out after {eff_timeout:.1f}s."
        except Exception as exc:
            exit_code = -1
            proc_error = self.key_mgr.sanitize_text(f"Subprocess launch failed for '{label}': {exc}")

        elapsed = round(time.perf_counter() - t0, 4)

        if resp_path.exists():
            try:
                worker_payload = json.loads(resp_path.read_text(encoding="utf-8"))
            except Exception as exc:
                proc_error = proc_error or f"Failed to parse worker response JSON: {exc}"
        if worker_payload is None and stdout_text:
            worker_payload = _parse_worker_stdout(stdout_text)
            if worker_payload is not None and not resp_path.exists():
                try:
                    _write_text_with_retry(
                        resp_path,
                        self.key_mgr.sanitize_text(json.dumps(worker_payload, default=str)),
                    )
                except PermissionError:
                    pass

        _write_text_with_retry(logs_dir / f"{label}_stdout.log", stdout_text)
        _write_text_with_retry(logs_dir / f"{label}_stderr.log", stderr_text)

        if timed_out or exit_code != 0 or worker_payload is None:
            err_msg = proc_error or (
                (worker_payload or {}).get("error_details")
                or stderr_text.strip()
                or f"Worker subprocess '{label}' exited with code {exit_code}."
            )
            err_msg = self.key_mgr.sanitize_text(str(err_msg))
            inner_res = (worker_payload or {}).get("agent_execution_results") or {}
            return {
                "variant": "optimized",
                "source": "current_experiment",
                "re_executed": True,
                "groq_api_calls": int(
                    (worker_payload or {}).get("groq_api_calls")
                    or inner_res.get("groq_api_calls")
                    or len(inner_res.get("api_errors") or [])
                ),
                "execution_passed": False,
                "execution_modes": inner_res.get("execution_modes")
                or (["offline_trace_replay_sandbox"] if enable_trace_replay_fallback else ["live_llm_execution"]),
                "usage_sources": inner_res.get("usage_sources") or ["unavailable"],
                "runs_executed": int(inner_res.get("runs_executed") or 0),
                "successful_runs": 0,
                "failed_runs": max(len(sample_inputs), int(inner_res.get("failed_runs") or len(sample_inputs))),
                "incomplete_runs": list(inner_res.get("incomplete_runs") or []),
                "concurrent_waves_executed": list(inner_res.get("concurrent_waves_executed") or []),
                "input_dataset_hashes": input_hashes,
                "trace_files": list(inner_res.get("trace_files") or []),
                "traces": list(inner_res.get("traces") or []),
                "trace_directory": str(dest_traces_dir),
                "schema_validation_summary": inner_res.get("schema_validation_summary")
                or {"all_schemas_valid": False, "failures": []},
                "invalid_replay_samples": list(inner_res.get("invalid_replay_samples") or []),
                "api_errors": list(inner_res.get("api_errors") or []),
                "fallback_events": list(inner_res.get("fallback_events") or []),
                "errors": [err_msg],
                "process_metadata": {
                    "execution_backend": "local_subprocess",
                    "python_executable": self.python_executable,
                    "workflow_directory": str(workflow_dir),
                    "cwd": str(workflow_dir),
                    "exit_code": exit_code,
                    "process_exit_codes": [exit_code],
                    "timed_out": timed_out,
                    "execution_status": "FAILED",
                    "execution_mode": (worker_payload or {}).get("execution_mode")
                    or ("offline_trace_replay_sandbox" if enable_trace_replay_fallback else "live_llm_execution"),
                    "process_duration_seconds": elapsed,
                    "sys_path_head": (worker_payload or {}).get("sys_path_head"),
                    "error_details": err_msg,
                },
            }

        inner = dict(worker_payload.get("agent_execution_results") or {})
        for trace_file, trace_obj in zip(inner.get("trace_files") or [], inner.get("traces") or []):
            if trace_file and isinstance(trace_obj, dict):
                tf_path = Path(str(trace_file))
                if not tf_path.exists():
                    try:
                        _write_text_with_retry(
                            tf_path,
                            self.key_mgr.sanitize_text(json.dumps(trace_obj, indent=2, default=str)),
                        )
                    except PermissionError:
                        pass
        worker_status = str(worker_payload.get("execution_status") or "FAILED")
        if exit_code != 0 or worker_status != "SUCCESS":
            inner["execution_passed"] = False
        if not inner.get("input_dataset_hashes"):
            inner["input_dataset_hashes"] = input_hashes
        inner["source"] = "current_experiment"
        inner["re_executed"] = True
        inner["trace_directory"] = str(dest_traces_dir)
        if "groq_api_calls" not in inner:
            inner["groq_api_calls"] = int(worker_payload.get("groq_api_calls") or 0)

        inner["process_metadata"] = {
            "execution_backend": "local_subprocess",
            "python_executable": worker_payload.get("python_executable") or self.python_executable,
            "workflow_directory": str(workflow_dir),
            "cwd": str(workflow_dir),
            "exit_code": exit_code,
            "process_exit_codes": [exit_code],
            "timed_out": False,
            "execution_status": worker_status,
            "execution_mode": worker_payload.get("execution_mode"),
            "process_duration_seconds": float(worker_payload.get("execution_duration") or elapsed),
            "sys_path_head": worker_payload.get("sys_path_head"),
            "error_details": worker_payload.get("error_details"),
        }
        return inner

    @staticmethod
    def _merge_subprocess_results(
        parts: List[Dict[str, Any]],
        expected_hashes: List[str],
        trace_directory: Path,
    ) -> Dict[str, Any]:
        traces: List[Dict[str, Any]] = []
        trace_files: List[str] = []
        modes = set()
        usage_srcs = set()
        errors: List[str] = []
        api_errors: List[Dict[str, Any]] = []
        fallback_events: List[Dict[str, Any]] = []
        schema_failures: List[Dict[str, Any]] = []
        invalid_replays: List[Dict[str, Any]] = []
        incomplete_runs: List[Dict[str, Any]] = []
        waves: List[List[str]] = []
        exit_codes: List[int] = []
        durations: List[float] = []
        timed_out = False
        successful = 0
        failed = 0
        runs_exec = 0
        groq_calls = 0

        for p in parts:
            traces.extend(p.get("traces") or [])
            trace_files.extend(p.get("trace_files") or [])
            modes.update(p.get("execution_modes") or [])
            usage_srcs.update(p.get("usage_sources") or [])
            errors.extend(p.get("errors") or [])
            api_errors.extend(p.get("api_errors") or [])
            fallback_events.extend(p.get("fallback_events") or [])
            schema_failures.extend((p.get("schema_validation_summary") or {}).get("failures") or [])
            invalid_replays.extend(p.get("invalid_replay_samples") or [])
            incomplete_runs.extend(p.get("incomplete_runs") or [])
            waves.extend(p.get("concurrent_waves_executed") or [])
            successful += int(p.get("successful_runs") or 0)
            failed += int(p.get("failed_runs") or 0)
            runs_exec += int(p.get("runs_executed") or 0)
            groq_calls += int(p.get("groq_api_calls") or 0)

            pm = p.get("process_metadata") or {}
            exit_codes.append(int(pm.get("exit_code", -1)))
            if pm.get("process_duration_seconds") is not None:
                durations.append(float(pm["process_duration_seconds"]))
            if pm.get("timed_out"):
                timed_out = True

        first_pm = (parts[0].get("process_metadata") or {}) if parts else {}
        non_zero = [c for c in exit_codes if c != 0]
        agg_exit = non_zero[0] if non_zero else 0
        all_passed = bool(parts) and all(bool(p.get("execution_passed")) for p in parts) and agg_exit == 0 and not timed_out

        return {
            "variant": "optimized",
            "source": "current_experiment",
            "re_executed": True,
            "groq_api_calls": groq_calls,
            "trace_directory": str(trace_directory.resolve()),
            "execution_passed": all_passed,
            "execution_modes": sorted(modes),
            "usage_sources": sorted(usage_srcs),
            "runs_executed": runs_exec,
            "successful_runs": successful,
            "failed_runs": failed,
            "incomplete_runs": incomplete_runs,
            "concurrent_waves_executed": waves,
            "input_dataset_hashes": expected_hashes,
            "trace_files": trace_files,
            "traces": traces,
            "schema_validation_summary": {
                "all_schemas_valid": len(schema_failures) == 0 and successful > 0,
                "failures": schema_failures,
            },
            "invalid_replay_samples": invalid_replays,
            "api_errors": api_errors,
            "fallback_events": fallback_events,
            "errors": errors,
            "process_metadata": {
                "execution_backend": "local_subprocess",
                "python_executable": first_pm.get("python_executable"),
                "workflow_directory": first_pm.get("workflow_directory"),
                "cwd": first_pm.get("cwd"),
                "exit_code": agg_exit,
                "process_exit_codes": exit_codes,
                "timed_out": timed_out,
                "execution_status": "SUCCESS" if all_passed else "FAILED",
                "execution_mode": sorted(modes)[0] if len(modes) == 1 else sorted(modes),
                "process_duration_seconds": round(sum(durations), 4),
                "sys_path_head": first_pm.get("sys_path_head"),
                "error_details": "; ".join(errors) if errors else None,
            },
        }

    def run_optimized_workflow(
        self,
        env: SandboxEnvironment,
        *,
        sample_inputs: List[Dict[str, Any]],
        num_runs: Optional[int] = None,
        enable_trace_replay_fallback: bool = False,
        evidence_dir: Optional[str] = None,
        data_base_dir: Optional[Path] = None,
        per_run_subprocess: bool = True,
        timeout_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Execute ONLY the optimized workflow across `num_runs` repetitions using matched
        input records, launching one or more isolated local Python subprocesses.
        Never executes baseline agents or baseline subprocesses.
        """
        if not sample_inputs:
            raise ValueError("sample_inputs must be non-empty for optimized workflow execution.")

        eff_runs = max(1, int(num_runs if num_runs is not None else len(sample_inputs)))
        repeated_inputs = [sample_inputs[i % len(sample_inputs)] for i in range(eff_runs)]
        expected_hashes = [_compute_input_hash(inp) for inp in repeated_inputs]

        _write_text_with_retry(
            env.experiment_dir / "matched_inputs.json",
            self.key_mgr.sanitize_text(json.dumps(repeated_inputs, indent=2, default=str)),
        )

        if per_run_subprocess and eff_runs > 1:
            parts: List[Dict[str, Any]] = []
            for idx in range(eff_runs):
                part = self.run_workflow_subprocess(
                    env,
                    variant="optimized",
                    sample_inputs=[repeated_inputs[idx]],
                    run_indices=[idx],
                    run_label=f"optimized_run{idx}",
                    enable_trace_replay_fallback=enable_trace_replay_fallback,
                    evidence_dir=evidence_dir,
                    data_base_dir=data_base_dir,
                    timeout_seconds=timeout_seconds,
                )
                parts.append(part)
            return self._merge_subprocess_results(parts, expected_hashes, env.runtime_traces_dir)

        return self.run_workflow_subprocess(
            env,
            variant="optimized",
            sample_inputs=repeated_inputs,
            run_indices=list(range(eff_runs)),
            run_label="optimized",
            enable_trace_replay_fallback=enable_trace_replay_fallback,
            evidence_dir=evidence_dir,
            data_base_dir=data_base_dir,
            timeout_seconds=timeout_seconds,
        )
