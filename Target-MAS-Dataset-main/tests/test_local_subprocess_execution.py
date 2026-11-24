"""
Validation Test Suite for Local Python Subprocess Execution (Requirements 1-15).
Uses mocked subprocesses, mocked live Groq responses, and real OS subprocess
execution without making actual paid Groq API requests.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from optimization_agent.key_manager import GroqKeyManager
from optimization_agent.sandbox import (
    LocalSubprocessExecutionManager,
    SandboxExperimentRunner,
    SandboxManager,
    build_subprocess_env,
    compute_directory_hashes,
)
from optimization_agent.sandbox.runtime.worker import WORKER_STDOUT_PREFIX


def _make_wf(base_dir: Path, workflow_id: str = "recruitment_like") -> Path:
    wf_dir = base_dir / workflow_id
    wf_dir.mkdir(parents=True, exist_ok=True)
    wf_json = {
        "workflow_id": workflow_id,
        "name": "Local Subprocess Test Workflow",
        "baseline_model": "openai/gpt-oss-120b",
        "llm_provider": "Groq",
        "assigned_groq_key_env": "GROQ_API_KEY_5",
        "agents": [
            {
                "agent_id": "resume_intake_agent",
                "role": "Resume Intake Specialist",
                "dependencies": [],
                "input_fields": ["resume"],
                "output_fields": ["application_id", "candidate_id", "candidate_name", "contact_info_present", "sections_identified"],
            },
            {
                "agent_id": "qualification_agent",
                "role": "Qualification Analyst",
                "dependencies": ["resume_intake_agent"],
                "input_fields": ["candidate_id", "sections_identified"],
                "output_fields": ["candidate_id", "technical_skills"],
            },
        ],
    }
    (wf_dir / "workflow.json").write_text(json.dumps(wf_json, indent=2), encoding="utf-8")
    (wf_dir / "intake_agent.py").write_text(
        'AGENT_ID = "resume_intake_agent"\nROLE = "Resume Intake Specialist"\nGOAL = "Parse resume."\n',
        encoding="utf-8",
    )
    (wf_dir / "qualification_agent.py").write_text(
        'AGENT_ID = "qualification_agent"\nROLE = "Qualification Analyst"\nGOAL = "Extract skills."\n',
        encoding="utf-8",
    )
    (wf_dir / "local_helper.py").write_text('ORIGIN_TAG = "original_workflow"\n', encoding="utf-8")
    return wf_dir


def _scope(workflow_id: str, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "workflow_id": workflow_id,
        "approval_status": "approved",
        "approved_candidate_ids": [c["candidate_id"] for c in candidates],
        "approved_candidates": candidates,
    }


def _live_mock_trace_factory(workflow_id: str, variant: str, resp_path: Path, req: Dict[str, Any]) -> Dict[str, Any]:
    traces_dir = Path(req["trace_directory"])
    traces_dir.mkdir(parents=True, exist_ok=True)
    wf_data = json.loads((Path(req["workflow_directory"]) / "workflow.json").read_text(encoding="utf-8"))
    model_overrides = wf_data.get("agent_model_overrides") or {}
    intake_model = (model_overrides.get("resume_intake_agent") or {}).get("updated_model") or wf_data.get("baseline_model", "openai/gpt-oss-120b")

    sample_inputs = req["sample_inputs"]
    traces = []
    trace_files = []
    for idx, _ in enumerate(sample_inputs):
        pt = 150 if variant == "optimized" else 220
        ct = 60 if variant == "optimized" else 90
        trace_obj = {
            "run_id": f"{variant}_run_{idx}",
            "run_index": idx,
            "variant": variant,
            "workflow_name": workflow_id,
            "experiment_id": req["experiment_id"],
            "status": "SUCCESS",
            "execution_mode": "live_llm_execution",
            "usage_sources": ["api_reported"],
            "input_hash": f"hash_{idx}",
            "input_snapshot": {"run_index": idx, "candidate_id": "CAND-001", "job_id": "JOB-01"},
            "duration_seconds": 0.45 if variant == "optimized" else 0.70,
            "agent_executions": [
                {
                    "order": 1,
                    "agent_id": "resume_intake_agent",
                    "model": intake_model,
                    "duration_seconds": 0.25 if variant == "optimized" else 0.40,
                    "status": "SUCCESS",
                    "tokens": pt + ct,
                    "prompt_tokens": pt,
                    "completion_tokens": ct,
                    "estimated_cost_usd": 0.00004 if variant == "optimized" else 0.00009,
                    "usage_source": "api_reported",
                    "schema_valid": True,
                    "mode": "live_llm_execution",
                    "output": {
                        "application_id": "APP-001",
                        "candidate_id": "CAND-001",
                        "candidate_name": "Dakota Chen",
                        "contact_info_present": True,
                        "sections_identified": ["education", "skills"],
                    },
                },
                {
                    "order": 2,
                    "agent_id": "qualification_agent",
                    "model": "openai/gpt-oss-120b",
                    "duration_seconds": 0.20 if variant == "optimized" else 0.30,
                    "status": "SUCCESS",
                    "tokens": 200,
                    "prompt_tokens": 120,
                    "completion_tokens": 80,
                    "estimated_cost_usd": 0.00010,
                    "usage_source": "api_reported",
                    "schema_valid": True,
                    "mode": "live_llm_execution",
                    "output": {
                        "candidate_id": "CAND-001",
                        "technical_skills": [],
                        "education": [],
                        "certifications": [],
                        "experience_records": [],
                        "projects": [],
                        "extraction_warnings": [],
                    },
                },
            ],
            "total_tokens": pt + ct + 200,
            "prompt_tokens": pt + 120,
            "completion_tokens": ct + 80,
            "estimated_cost_usd": 0.00010 if variant == "optimized" else 0.00019,
        }
        tf = traces_dir / f"{variant}_run_{idx}.json"
        tf.write_text(json.dumps(trace_obj), encoding="utf-8")
        traces.append(trace_obj)
        trace_files.append(str(tf))

    payload = {
        "experiment_id": req["experiment_id"],
        "workflow_id": workflow_id,
        "variant": variant,
        "execution_mode": "live_llm_execution",
        "execution_status": "SUCCESS",
        "workflow_directory": req["workflow_directory"],
        "run_id": traces[0]["run_id"],
        "run_ids": [t["run_id"] for t in traces],
        "agent_execution_results": {
            "variant": variant,
            "execution_passed": True,
            "execution_modes": ["live_llm_execution"],
            "usage_sources": ["api_reported"],
            "runs_executed": len(traces),
            "successful_runs": len(traces),
            "failed_runs": 0,
            "incomplete_runs": [],
            "concurrent_waves_executed": [],
            "trace_files": trace_files,
            "traces": traces,
            "schema_validation_summary": {"all_schemas_valid": True, "failures": []},
            "invalid_replay_samples": [],
            "api_errors": [],
            "fallback_events": [],
            "errors": [],
        },
        "trace_directory": str(traces_dir),
        "api_errors": [],
        "execution_duration": 0.5,
        "python_executable": sys.executable,
        "error_details": None,
    }
    resp_path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


# ---------------------------------------------------------------------------
# Requirements 1-4: Directories, sys.executable, cwd Isolation
# ---------------------------------------------------------------------------
def test_01_to_04_baseline_and_optimized_subprocess_paths_cwd_and_executable(tmp_path: Path):
    agents_dir = tmp_path / "agents"
    exp_dir = tmp_path / "experiments"
    orig_dir = _make_wf(agents_dir, "recruitment_like")

    invocations: List[Dict[str, Any]] = []

    def _mock_subproc(cmd, **kwargs):
        req_file = Path(cmd[cmd.index("--request-file") + 1])
        resp_file = Path(cmd[cmd.index("--response-file") + 1])
        req = json.loads(req_file.read_text(encoding="utf-8"))
        invocations.append({"cmd": cmd, "cwd": kwargs["cwd"], "env": kwargs["env"], "req": req})
        _live_mock_trace_factory("recruitment_like", req["variant"], resp_file, req)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    cand = {
        "candidate_id": "MODEL-RESUME_INTAKE_AGENT",
        "dimension": "model_selection",
        "target_agents": ["resume_intake_agent"],
        "selected_model": "llama-3.1-8b-instant",
    }
    runner = SandboxExperimentRunner(
        agents_base_dir=agents_dir,
        experiments_base_dir=exp_dir,
        execution_backend="local_subprocess",
        per_run_subprocess=False,
        subprocess_runner=_mock_subproc,
    )
    out = runner.run(_scope("recruitment_like", [cand]), experiment_id="exp_paths", num_runs=2)

    assert len(invocations) == 1
    opt_inv = invocations[0]

    # Executable == sys.executable and ONLY optimized subprocess ran (no baseline subprocess)
    assert opt_inv["cmd"][0] == sys.executable
    assert opt_inv["req"]["variant"] == "optimized"
    assert Path(opt_inv["cwd"]) == Path(out["sandbox_workflow_dir"]).resolve()
    assert Path(opt_inv["cwd"]) != orig_dir.resolve()
    assert Path(opt_inv["req"]["workflow_directory"]) == Path(out["sandbox_workflow_dir"]).resolve()
    assert out["baseline_runtime_results"]["re_executed"] is False
    assert out["baseline_runtime_results"]["groq_api_calls"] == 0


# ---------------------------------------------------------------------------
# Requirement 5: Secure Groq Credential Passing Without Exposure
# ---------------------------------------------------------------------------
def test_05_groq_credentials_passed_via_env_only_never_in_cli_or_request_json(tmp_path: Path):
    agents_dir = tmp_path / "agents"
    exp_dir = tmp_path / "experiments"
    _make_wf(agents_dir, "recruitment_screening")

    secret_k5 = "gsk_FAKE_SECRET_KEY_5_FOR_TESTING_999999999999"
    secret_f15 = "gsk_FAKE_FAILOVER_15_FOR_TESTING_888888888888"
    mgr = GroqKeyManager(key_pool={"GROQ_API_KEY_5": secret_k5, "GROQ_API_KEY_15": secret_f15})

    wf_dir = (agents_dir / "recruitment_screening").resolve()
    sub_env = build_subprocess_env(
        workflow_id="recruitment_screening",
        workflow_dir=wf_dir,
        project_root=ROOT_DIR,
        key_mgr=mgr,
    )
    assert sub_env["GROQ_API_KEY_5"] == secret_k5
    assert sub_env["GROQ_API_KEY_15"] == secret_f15

    # Run mocked subprocess and ensure request JSON & reports contain zero secrets
    seen_req = {}

    def _mock_subproc(cmd, **kwargs):
        req_file = Path(cmd[cmd.index("--request-file") + 1])
        resp_file = Path(cmd[cmd.index("--response-file") + 1])
        seen_req["cmd"] = list(cmd)
        seen_req["raw_req"] = req_file.read_text(encoding="utf-8")
        req = json.loads(seen_req["raw_req"])
        _live_mock_trace_factory("recruitment_screening", req["variant"], resp_file, req)
        return SimpleNamespace(returncode=0, stdout=f"diagnostic {secret_k5}", stderr="")

    runner = SandboxExperimentRunner(
        agents_base_dir=agents_dir,
        experiments_base_dir=exp_dir,
        interleave_runs=False,
        subprocess_runner=_mock_subproc,
    )
    out = runner.run(
        _scope(
            "recruitment_screening",
            [{"candidate_id": "M1", "dimension": "model_selection", "target_agents": ["resume_intake_agent"], "selected_model": "llama-3.1-8b-instant"}],
        ),
        experiment_id="exp_sec",
        num_runs=1,
    )
    assert secret_k5 not in " ".join(seen_req["cmd"])
    assert secret_k5 not in seen_req["raw_req"]
    assert secret_k5 not in Path(out["json_report_path"]).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Requirement 6: Real OS Subprocess Import Isolation (Sandbox vs. Original)
# ---------------------------------------------------------------------------
def test_06_optimized_subprocess_resolves_imports_from_sandbox_copy(tmp_path: Path):
    agents_dir = tmp_path / "agents"
    exp_dir = tmp_path / "experiments"
    orig_dir = _make_wf(agents_dir, "recruitment_like")

    mgr = SandboxManager(agents_base_dir=agents_dir, experiments_base_dir=exp_dir)
    env = mgr.prepare_sandbox(
        _scope(
            "recruitment_like",
            [{"candidate_id": "M1", "dimension": "model_selection", "target_agents": ["resume_intake_agent"], "selected_model": "llama-3.1-8b-instant"}],
        ),
        experiment_id="exp_iso_imp",
    )
    # Modify sandbox helper ONLY; original still has ORIGIN_TAG = "original_workflow"
    (env.sandbox_workflow_dir / "local_helper.py").write_text('ORIGIN_TAG = "sandbox_copy"\n', encoding="utf-8")

    base_env = build_subprocess_env(workflow_id="recruitment_like", workflow_dir=orig_dir, project_root=ROOT_DIR)
    opt_env = build_subprocess_env(workflow_id="recruitment_like", workflow_dir=env.sandbox_workflow_dir, project_root=ROOT_DIR)

    p_base = subprocess.run(
        [sys.executable, "-c", "import local_helper; print(local_helper.ORIGIN_TAG)"],
        cwd=str(orig_dir),
        env=base_env,
        capture_output=True,
        text=True,
        check=True,
    )
    p_opt = subprocess.run(
        [sys.executable, "-c", "import local_helper; print(local_helper.ORIGIN_TAG)"],
        cwd=str(env.sandbox_workflow_dir),
        env=opt_env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert p_base.stdout.strip() == "original_workflow"
    assert p_opt.stdout.strip() == "sandbox_copy"


# ---------------------------------------------------------------------------
# Requirements 7 & 12: Real Worker Subprocess JSON Output & Explicit Replay
# ---------------------------------------------------------------------------
def test_07_and_12_real_os_subprocess_worker_replay_and_structured_json(tmp_path: Path):
    exp_dir = tmp_path / "experiments"
    mgr = SandboxManager(experiments_base_dir=exp_dir)
    env = mgr.prepare_sandbox(
        _scope(
            "recruitment_screening",
            [{"candidate_id": "MODEL-RESUME_INTAKE_AGENT", "dimension": "model_selection", "target_agents": ["resume_intake_agent"], "selected_model": "llama-3.3-70b-versatile"}],
        ),
        experiment_id="exp_real_worker",
    )
    proc_mgr = LocalSubprocessExecutionManager(timeout_seconds=60.0)
    res = proc_mgr.run_workflow_subprocess(
        env,
        variant="optimized",
        sample_inputs=[{"run_index": 0}],
        enable_trace_replay_fallback=True,
    )
    pm = res["process_metadata"]
    assert pm["execution_backend"] == "local_subprocess"
    assert pm["python_executable"] == sys.executable
    assert pm["exit_code"] == 0, f"Subprocess failed: pm={pm}, errors={res.get('errors')}"
    assert pm["execution_status"] == "SUCCESS"
    assert pm["sys_path_head"] == str(env.sandbox_workflow_dir.resolve())
    assert res["execution_passed"] is True
    assert res["execution_modes"] == ["offline_trace_replay_sandbox"]


# ---------------------------------------------------------------------------
# Requirement 8: Non-Zero Subprocess Exit Code Handling
# ---------------------------------------------------------------------------
def test_08_nonzero_process_exit_code_fails_loudly(tmp_path: Path):
    agents_dir = tmp_path / "agents"
    exp_dir = tmp_path / "experiments"
    _make_wf(agents_dir, "recruitment_like")
    mgr = SandboxManager(agents_base_dir=agents_dir, experiments_base_dir=exp_dir)
    env = mgr.prepare_sandbox(
        _scope("recruitment_like", [{"candidate_id": "M1", "dimension": "model_selection", "target_agents": ["resume_intake_agent"], "selected_model": "llama-3.1-8b-instant"}]),
        experiment_id="exp_exit_err",
    )

    def _failing_subproc(*_a, **_kw):
        return SimpleNamespace(returncode=2, stdout="", stderr="ModuleNotFoundError: missing dep")

    proc_mgr = LocalSubprocessExecutionManager(subprocess_runner=_failing_subproc)
    res = proc_mgr.run_workflow_subprocess(env, variant="optimized", sample_inputs=[{"run_index": 0}])

    assert res["execution_passed"] is False
    assert res["process_metadata"]["exit_code"] == 2
    assert res["process_metadata"]["execution_status"] == "FAILED"
    assert "missing dep" in res["errors"][0]


# ---------------------------------------------------------------------------
# Requirement 9: Subprocess Timeout Handling
# ---------------------------------------------------------------------------
def test_09_subprocess_timeout_handled_cleanly(tmp_path: Path):
    agents_dir = tmp_path / "agents"
    exp_dir = tmp_path / "experiments"
    _make_wf(agents_dir, "recruitment_like")
    mgr = SandboxManager(agents_base_dir=agents_dir, experiments_base_dir=exp_dir)
    env = mgr.prepare_sandbox(
        _scope("recruitment_like", [{"candidate_id": "M1", "dimension": "model_selection", "target_agents": ["resume_intake_agent"], "selected_model": "llama-3.1-8b-instant"}]),
        experiment_id="exp_timeout",
    )

    def _timeout_subproc(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=5.0, output="partial", stderr="hung")

    proc_mgr = LocalSubprocessExecutionManager(timeout_seconds=5.0, subprocess_runner=_timeout_subproc)
    res = proc_mgr.run_workflow_subprocess(env, variant="optimized", sample_inputs=[{"run_index": 0}])

    assert res["execution_passed"] is False
    assert res["process_metadata"]["timed_out"] is True
    assert res["process_metadata"]["execution_status"] == "FAILED"
    assert "timed out" in res["errors"][0].lower()


# ---------------------------------------------------------------------------
# Requirement 10: Live API Connection Errors in Real OS Subprocess Without Fallback
# ---------------------------------------------------------------------------
def test_10_real_os_subprocess_live_api_error_never_falls_back(tmp_path: Path):
    exp_dir = tmp_path / "experiments"
    orig_hashes_before = compute_directory_hashes(ROOT_DIR / "Agents" / "recruitment_screening")

    runner = SandboxExperimentRunner(
        experiments_base_dir=exp_dir,
        execution_backend="local_subprocess",
        enable_trace_replay_fallback=False,
        run_matched_baseline=True,
        interleave_runs=False,
        process_timeout_seconds=45.0,
    )
    out = runner.run(
        _scope(
            "recruitment_screening",
            [{"candidate_id": "MODEL-RESUME_INTAKE_AGENT", "dimension": "model_selection", "target_agents": ["resume_intake_agent"], "selected_model": "llama-3.3-70b-versatile"}],
        ),
        experiment_id="exp_live_os_err",
        num_runs=1,
    )

    # In network-blocked sandbox, live Groq fails clearly with no offline replay fallback
    assert out["execution_backend"] == "local_subprocess"
    assert "offline_trace_replay_sandbox" not in (out["runtime_results"].get("execution_modes") or [])
    if not out["runtime_results"]["execution_passed"]:
        assert len(out["runtime_results"]["api_errors"]) >= 1
        assert out["final_experiment_assessment"]["status"] == "failed"

    assert out["original_integrity_after"]["original_unchanged"] is True
    assert compute_directory_hashes(ROOT_DIR / "Agents" / "recruitment_screening") == orig_hashes_before


# ---------------------------------------------------------------------------
# Requirements 11, 13, 14, 15: End-to-End Local Subprocess + Reports + Integrity
# ---------------------------------------------------------------------------
def test_11_13_14_15_full_subprocess_experiment_pipeline_with_mocked_live_and_reports(tmp_path: Path):
    agents_dir = tmp_path / "agents"
    exp_dir = tmp_path / "experiments"
    orig_dir = _make_wf(agents_dir, "recruitment_like")
    pre_hashes = compute_directory_hashes(orig_dir)

    data_dir = tmp_path / "data" / "recruitment_like"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "resumes.json").write_text(
        json.dumps([{"application_id": "APP-001", "candidate_id": "CAND-001", "candidate_name": "Dakota Chen", "target_job_id": "JOB-01"}]),
        encoding="utf-8",
    )
    (data_dir / "jobs.json").write_text(
        json.dumps([{"job_id": "JOB-01", "title": "Senior Cloud Backend Engineer"}]),
        encoding="utf-8",
    )
    hist_dir = tmp_path / "hist_traces"
    hist_dir.mkdir(parents=True, exist_ok=True)
    (hist_dir / "trace01.json").write_text(
        json.dumps({
            "run_id": "hist_01",
            "workflow_name": "recruitment_like",
            "status": "SUCCESS",
            "duration_seconds": 5.0,
            "prompt_tokens": 500,
            "completion_tokens": 200,
            "total_tokens": 700,
            "agent_executions": [
                {"agent_id": "resume_intake_agent", "duration_seconds": 2.5, "output": {"application_id": "APP-001", "candidate_id": "CAND-001", "candidate_name": "Dakota Chen", "contact_info_present": True, "sections_identified": ["education", "skills"]}},
                {"agent_id": "qualification_agent", "duration_seconds": 2.5, "output": {"candidate_id": "CAND-001", "job_id": "JOB-01", "technical_skills": []}},
            ],
        }),
        encoding="utf-8",
    )

    def _mock_live_subproc(cmd, **kwargs):
        req = json.loads(Path(cmd[cmd.index("--request-file") + 1]).read_text(encoding="utf-8"))
        assert req["variant"] == "optimized"
        resp_p = Path(cmd[cmd.index("--response-file") + 1])
        _live_mock_trace_factory("recruitment_like", req["variant"], resp_p, req)
        return SimpleNamespace(returncode=0, stdout=f"{WORKER_STDOUT_PREFIX}{{}}\n", stderr="")

    cands = [
        {
            "candidate_id": "MODEL-INTAKE",
            "dimension": "model_selection",
            "target_agents": ["resume_intake_agent"],
            "selected_model": "llama-3.1-8b-instant",
        },
        {
            "candidate_id": "PROMPT-UNAPPROVED",
            "dimension": "prompt_optimization",
            "target_agents": ["qualification_agent"],
            "optimized_prompt": "Must be ignored",
        },
    ]
    scope = {
        "workflow_id": "recruitment_like",
        "approval_status": "approved",
        "approved_candidate_ids": ["MODEL-INTAKE"],
        "approved_candidates": cands,
    }
    runner = SandboxExperimentRunner(
        agents_base_dir=agents_dir,
        experiments_base_dir=exp_dir,
        data_base_dir=tmp_path / "data",
        baseline_traces_dir=hist_dir,
        execution_backend="local_subprocess",
        enable_trace_replay_fallback=False,
        subprocess_runner=_mock_live_subproc,
        judge_callable=lambda **_k: {
            "correctness": "passed",
            "completeness": "passed",
            "consistency": "passed",
            "instruction_adherence": "passed",
            "semantic_quality": "passed",
            "identified_issues": [],
            "rationale": "Verified.",
        },
    )
    out = runner.run(scope, experiment_id="exp_full_subproc", num_runs=2)

    assert out["execution_results"]["applied_candidate_ids"] == ["MODEL-INTAKE"]
    assert out["final_experiment_assessment"]["status"] == "successful"
    assert out["original_integrity_after"]["original_unchanged"] is True
    assert compute_directory_hashes(orig_dir) == pre_hashes

    rep_json = json.loads(Path(out["json_report_path"]).read_text(encoding="utf-8"))
    pm = rep_json["process_execution_metadata"]
    assert pm["execution_backend"] == "local_subprocess"
    assert pm["python_executable"] == sys.executable
    assert pm["baseline_re_executed"] is False
    assert pm["baseline_process_exit_code"] is None
    assert pm["baseline_execution_status"] == "HISTORICAL_FIXED"
    assert pm["optimized_process_exit_code"] == 0
    assert pm["optimized_execution_status"] == "SUCCESS"

    rep_md = Path(out["markdown_report_path"]).read_text(encoding="utf-8")
    assert "## 1. Experiment Metadata" in rep_md
    assert "local_subprocess" in rep_md
    assert "## 7. Final Experiment Assessment" in rep_md
