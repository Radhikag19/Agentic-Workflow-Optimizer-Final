"""
Validation Test Suite for Fixed Historical Baseline + Optimized-Only Local Subprocess Execution.
Covers all 15 validation requirements (Section 9) without making real paid Groq API calls.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from optimization_agent.agent import OptimizationDiscoveryAgent
from optimization_agent.sandbox import (
    LocalSubprocessExecutionManager,
    SandboxExperimentRunner,
    SandboxManager,
    build_optimization_graph_with_sandbox_execution,
    compute_directory_hashes,
    load_historical_baseline_evidence,
    match_baseline_traces_to_inputs,
)


def _setup_fixture_env(tmp_path: Path):
    agents_dir = tmp_path / "agents"
    exp_dir = tmp_path / "experiments"
    data_dir = tmp_path / "data"
    traces_dir = tmp_path / "historical_traces"

    wf_id = "sample_fixed_wf"
    wf_dir = agents_dir / wf_id
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / "workflow.json").write_text(
        json.dumps(
            {
                "workflow_id": wf_id,
                "name": "Sample Fixed Baseline Workflow",
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
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (wf_dir / "intake_agent.py").write_text(
        'AGENT_ID = "resume_intake_agent"\nROLE = "Resume Intake Specialist"\nGOAL = "Parse resume."\n',
        encoding="utf-8",
    )
    (wf_dir / "qualification_agent.py").write_text(
        'AGENT_ID = "qualification_agent"\nROLE = "Qualification Analyst"\nGOAL = "Extract skills."\n',
        encoding="utf-8",
    )
    (wf_dir / "helper_mod.py").write_text('WHICH = "original_wf"\n', encoding="utf-8")

    # Dataset with two distinct records
    wf_data_dir = data_dir / wf_id
    wf_data_dir.mkdir(parents=True, exist_ok=True)
    (wf_data_dir / "resumes.json").write_text(
        json.dumps(
            [
                {"application_id": "APP-101", "candidate_id": "CAND-101", "candidate_name": "Alice Smith", "target_job_id": "JOB-A"},
                {"application_id": "APP-102", "candidate_id": "CAND-102", "candidate_name": "Bob Jones", "target_job_id": "JOB-B"},
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    (wf_data_dir / "jobs.json").write_text(
        json.dumps(
            [
                {"job_id": "JOB-A", "title": "Backend Engineer"},
                {"job_id": "JOB-B", "title": "Data Engineer"},
            ],
            indent=2,
        ),
        encoding="utf-8",
    )

    # Historical traces: trace_b (CAND-102 FIRST -> tests non-order matching!), trace_a (CAND-101), trace_unmatched (CAND-999)
    traces_dir.mkdir(parents=True, exist_ok=True)
    trace_b = {
        "run_id": "hist_trace_b",
        "workflow_name": wf_id,
        "status": "SUCCESS",
        "duration_seconds": 12.5,
        "prompt_tokens": 900,
        "completion_tokens": 300,
        "total_tokens": 1200,
        "estimated_cost_usd": 0.0005,
        "timestamp": "2026-10-31T10:00:00+00:00",
        "agent_executions": [
            {
                "agent_id": "resume_intake_agent",
                "duration_seconds": 6.0,
                "prompt_tokens": 500,
                "completion_tokens": 150,
                "tokens": 650,
                "output": {
                    "application_id": "APP-102",
                    "candidate_id": "CAND-102",
                    "candidate_name": "Bob Jones",
                    "contact_info_present": True,
                    "sections_identified": ["skills"],
                },
            },
            {
                "agent_id": "qualification_agent",
                "duration_seconds": 6.5,
                "prompt_tokens": 400,
                "completion_tokens": 150,
                "tokens": 550,
                "output": {"candidate_id": "CAND-102", "job_id": "JOB-B", "technical_skills": []},
            },
        ],
    }
    trace_a = {
        "run_id": "hist_trace_a",
        "workflow_name": wf_id,
        "status": "SUCCESS",
        "duration_seconds": 10.5,
        "prompt_tokens": 800,
        "completion_tokens": 250,
        "total_tokens": 1050,
        "estimated_cost_usd": 0.0004,
        "timestamp": "2026-10-31T10:01:00+00:00",
        "agent_executions": [
            {
                "agent_id": "resume_intake_agent",
                "duration_seconds": 5.0,
                "prompt_tokens": 450,
                "completion_tokens": 120,
                "tokens": 570,
                "output": {
                    "application_id": "APP-101",
                    "candidate_id": "CAND-101",
                    "candidate_name": "Alice Smith",
                    "contact_info_present": True,
                    "sections_identified": ["education"],
                },
            },
            {
                "agent_id": "qualification_agent",
                "duration_seconds": 5.5,
                "prompt_tokens": 350,
                "completion_tokens": 130,
                "tokens": 480,
                "output": {"candidate_id": "CAND-101", "job_id": "JOB-A", "technical_skills": []},
            },
        ],
    }
    trace_unmatched = {
        "run_id": "hist_trace_unmatched",
        "workflow_name": wf_id,
        "status": "SUCCESS",
        "duration_seconds": 8.0,
        "agent_executions": [
            {
                "agent_id": "resume_intake_agent",
                "output": {"application_id": "APP-999", "candidate_id": "CAND-999"},
            }
        ],
    }
    (traces_dir / "01_hist_trace_b.json").write_text(json.dumps(trace_b, indent=2), encoding="utf-8")
    (traces_dir / "02_hist_trace_a.json").write_text(json.dumps(trace_a, indent=2), encoding="utf-8")
    (traces_dir / "03_hist_unmatched.json").write_text(json.dumps(trace_unmatched, indent=2), encoding="utf-8")

    return wf_id, agents_dir, exp_dir, data_dir, traces_dir


def _mock_opt_subproc_factory(seen_calls: List[Dict[str, Any]]):
    def _mock_subproc(cmd, **kwargs):
        req = json.loads(Path(cmd[cmd.index("--request-file") + 1]).read_text(encoding="utf-8"))
        resp_p = Path(cmd[cmd.index("--response-file") + 1])
        seen_calls.append({"variant": req["variant"], "cwd": kwargs["cwd"], "cmd": list(cmd), "req": req})

        # Strictly fail if baseline is ever invoked!
        assert req["variant"] == "optimized", f"Unexpected baseline subprocess invocation: {req['variant']}"

        wf_data = json.loads((Path(req["workflow_directory"]) / "workflow.json").read_text(encoding="utf-8"))
        intake_model = (
            (wf_data.get("agent_model_overrides") or {}).get("resume_intake_agent", {}).get("updated_model")
            or wf_data.get("baseline_model")
        )
        sample_inputs = req["sample_inputs"]
        run_indices = req.get("run_indices") or list(range(len(sample_inputs)))
        traces_dir = Path(req["trace_directory"])
        traces_dir.mkdir(parents=True, exist_ok=True)

        traces = []
        trace_files = []
        for pos, inp in enumerate(sample_inputs):
            ridx = run_indices[pos] if pos < len(run_indices) else pos
            res_rec = inp.get("resume") or {}
            job_rec = inp.get("job") or {}
            cid = res_rec.get("candidate_id", "CAND-000")
            aid = res_rec.get("application_id", "APP-000")
            cname = res_rec.get("candidate_name", "Unknown")

            t_obj = {
                "run_id": f"opt_live_{ridx}",
                "run_index": ridx,
                "variant": "optimized",
                "workflow_name": req["workflow_id"],
                "experiment_id": req["experiment_id"],
                "status": "SUCCESS",
                "execution_mode": "live_llm_execution",
                "usage_sources": ["api_reported"],
                "input_hash": __import__("optimization_agent.sandbox.evaluation.baseline_loader", fromlist=["compute_canonical_input_hash"]).compute_canonical_input_hash(inp),
                "input_snapshot": {
                    "run_index": ridx,
                    "candidate_id": cid,
                    "application_id": aid,
                    "job_id": job_rec.get("job_id"),
                    "matched_baseline_run_id": inp.get("_matched_baseline_run_id"),
                },
                "duration_seconds": 3.5,
                "prompt_tokens": 500,
                "completion_tokens": 180,
                "total_tokens": 680,
                "estimated_cost_usd": 0.00025,
                "agent_executions": [
                    {
                        "order": 1,
                        "agent_id": "resume_intake_agent",
                        "model": intake_model,
                        "duration_seconds": 1.5,
                        "status": "SUCCESS",
                        "prompt_tokens": 250,
                        "completion_tokens": 90,
                        "tokens": 340,
                        "estimated_cost_usd": 0.00010,
                        "usage_source": "api_reported",
                        "schema_valid": True,
                        "mode": "live_llm_execution",
                        "output": {
                            "application_id": aid,
                            "candidate_id": cid,
                            "candidate_name": cname,
                            "contact_info_present": True,
                            "sections_identified": ["skills"],
                        },
                    },
                    {
                        "order": 2,
                        "agent_id": "qualification_agent",
                        "model": "openai/gpt-oss-120b",
                        "duration_seconds": 2.0,
                        "status": "SUCCESS",
                        "prompt_tokens": 250,
                        "completion_tokens": 90,
                        "tokens": 340,
                        "estimated_cost_usd": 0.00015,
                        "usage_source": "api_reported",
                        "schema_valid": True,
                        "mode": "live_llm_execution",
                        "output": {
                            "candidate_id": cid,
                            "technical_skills": [],
                            "education": [],
                            "certifications": [],
                            "experience_records": [],
                            "projects": [],
                            "extraction_warnings": [],
                        },
                    },
                ],
            }
            tf = traces_dir / f"opt_live_{ridx}.json"
            tf.write_text(json.dumps(t_obj), encoding="utf-8")
            traces.append(t_obj)
            trace_files.append(str(tf))

        payload = {
            "experiment_id": req["experiment_id"],
            "workflow_id": req["workflow_id"],
            "variant": "optimized",
            "execution_mode": "live_llm_execution",
            "execution_status": "SUCCESS",
            "workflow_directory": req["workflow_directory"],
            "run_id": traces[0]["run_id"],
            "run_ids": [t["run_id"] for t in traces],
            "groq_api_calls": len(traces) * 2,
            "agent_execution_results": {
                "variant": "optimized",
                "source": "current_experiment",
                "re_executed": True,
                "groq_api_calls": len(traces) * 2,
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
            "execution_duration": 0.4,
            "python_executable": sys.executable,
            "sys_path_head": req["workflow_directory"],
            "error_details": None,
        }
        resp_p.write_text(json.dumps(payload), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    return _mock_subproc


# ---------------------------------------------------------------------------
# Checks 1-5 & 10-13: Fixed Baseline, Zero Baseline Subprocess, Exact Matching & Integrity
# ---------------------------------------------------------------------------
def test_01_fixed_historical_baseline_no_baseline_subprocess_and_matching(tmp_path: Path):
    wf_id, agents_dir, exp_dir, data_dir, traces_dir = _setup_fixture_env(tmp_path)
    pre_trace_hashes = compute_directory_hashes(traces_dir)
    pre_wf_hashes = compute_directory_hashes(agents_dir / wf_id)

    seen_calls: List[Dict[str, Any]] = []
    scope = {
        "workflow_id": wf_id,
        "approval_status": "approved",
        "approved_candidate_ids": ["MODEL-INTAKE", "PROMPT-QUAL"],
        "approved_candidates": [
            {
                "candidate_id": "MODEL-INTAKE",
                "dimension": "model_selection",
                "target_agents": ["resume_intake_agent"],
                "selected_model": "llama-3.1-8b-instant",
            },
            {
                "candidate_id": "PROMPT-QUAL",
                "dimension": "prompt_optimization",
                "target_agents": ["qualification_agent"],
                "optimized_prompt": "Concise qualification JSON.",
            },
        ],
    }

    runner = SandboxExperimentRunner(
        agents_base_dir=agents_dir,
        experiments_base_dir=exp_dir,
        data_base_dir=data_dir,
        baseline_traces_dir=traces_dir,
        execution_backend="local_subprocess",
        enable_trace_replay_fallback=False,
        subprocess_runner=_mock_opt_subproc_factory(seen_calls),
        judge_callable=lambda **_kw: {
            "correctness": "passed",
            "completeness": "passed",
            "consistency": "passed",
            "instruction_adherence": "passed",
            "semantic_quality": "passed",
            "identified_issues": [],
            "rationale": "Verified.",
        },
    )
    out = runner.run(scope, experiment_id="exp_fixed_vs_opt", num_runs=5)

    # Checks 1-3: Zero baseline subprocesses & zero baseline Groq calls
    assert all(c["variant"] == "optimized" for c in seen_calls)
    assert len(seen_calls) == 5  # Repeated 5 optimized runs
    assert all(Path(c["cwd"]) == Path(out["sandbox_workflow_dir"]).resolve() for c in seen_calls)
    assert all(c["cmd"][0] == sys.executable for c in seen_calls)
    assert not (Path(out["experiment_dir"]) / "baseline_traces").exists()

    rep = json.loads(Path(out["json_report_path"]).read_text(encoding="utf-8"))
    assert rep["baseline_evidence"]["re_executed"] is False
    assert rep["baseline_evidence"]["groq_api_calls"] == 0
    assert rep["baseline_evidence"]["execution_mode"] == "historical_recorded_execution"
    assert rep["optimized_execution"]["re_executed"] is True
    assert rep["optimized_execution"]["groq_api_calls"] == 10
    assert rep["optimized_execution"]["num_optimized_runs"] == 5
    assert len(rep["optimized_execution"]["per_run_metrics"]) == 5

    # Checks 10-11: Identifier matching (CAND-102 first, CAND-101 second, CAND-999 excluded!)
    matching = rep["input_matching"]
    assert matching["matched_input_count"] == 2
    assert matching["unmatched_input_count"] == 1
    assert matching["excluded_records"][0]["run_id"] == "hist_trace_unmatched"
    assert seen_calls[0]["req"]["sample_inputs"][0]["resume"]["candidate_id"] == "CAND-102"
    assert seen_calls[1]["req"]["sample_inputs"][0]["resume"]["candidate_id"] == "CAND-101"

    # Check 5: Original historical traces & original workflow files untouched
    assert compute_directory_hashes(traces_dir) == pre_trace_hashes
    assert compute_directory_hashes(agents_dir / wf_id) == pre_wf_hashes
    assert out["final_experiment_assessment"]["status"] == "successful"

    md = Path(out["markdown_report_path"]).read_text(encoding="utf-8")
    assert "Fixed Historical Baseline Evidence" in md
    assert "Fresh Optimized Subprocess Execution" in md


def test_02_baseline_subprocess_and_worker_explicitly_rejected(tmp_path: Path):
    wf_id, agents_dir, exp_dir, data_dir, _ = _setup_fixture_env(tmp_path)
    mgr = SandboxManager(agents_base_dir=agents_dir, experiments_base_dir=exp_dir)
    env = mgr.prepare_sandbox(
        {"workflow_id": wf_id, "approval_status": "approved", "approved_candidate_ids": ["M1"], "approved_candidates": [{"candidate_id": "M1", "dimension": "model_selection", "target_agents": ["resume_intake_agent"], "selected_model": "llama-3.1-8b-instant"}]},
        experiment_id="exp_reject_base",
    )
    proc_mgr = LocalSubprocessExecutionManager()
    with pytest.raises(ValueError, match="Baseline subprocess execution is disabled"):
        proc_mgr.run_workflow_subprocess(env, variant="baseline", sample_inputs=[{"run_index": 0}])

    from optimization_agent.sandbox.runtime.worker import execute_worker_request

    w_res = execute_worker_request({
        "experiment_id": "e1",
        "workflow_id": wf_id,
        "variant": "baseline",
        "workflow_directory": str(env.original_workflow_dir),
        "original_workflow_directory": str(env.original_workflow_dir),
        "sandbox_workflow_directory": str(env.sandbox_workflow_dir),
        "experiment_dir": str(env.experiment_dir),
        "trace_directory": str(env.experiment_dir / "t"),
    })
    assert w_res["execution_status"] == "FAILED"
    assert w_res["groq_api_calls"] == 0


def test_03_missing_baseline_metrics_remain_none_never_fabricated(tmp_path: Path):
    wf_id, _, _, data_dir, traces_dir = _setup_fixture_env(tmp_path)
    # Strip tokens & cost from historical trace to verify missing metrics remain None
    sparse = {
        "run_id": "sparse_trace_01",
        "workflow_name": wf_id,
        "status": "SUCCESS",
        "duration_seconds": 9.0,
        "agent_executions": [
            {"agent_id": "resume_intake_agent", "output": {"application_id": "APP-101", "candidate_id": "CAND-101"}}
        ],
    }
    sparse_dir = tmp_path / "sparse_traces"
    sparse_dir.mkdir()
    (sparse_dir / "sparse_01.json").write_text(json.dumps(sparse), encoding="utf-8")

    bundle = load_historical_baseline_evidence(
        wf_id,
        baseline_traces_dir=sparse_dir,
        data_base_dir=data_dir,
    )
    hm = bundle["historical_metrics"]
    assert hm["mean_latency_seconds"] == 9.0
    assert hm["mean_tokens"] is None
    assert hm["mean_prompt_tokens"] is None
    assert hm["mean_completion_tokens"] is None
    assert hm["mean_cost_usd_catalog_normalized"] is None
    assert hm["cost_calculation_basis"] == "unavailable"


def test_04_real_recruitment_screening_historical_traces_match_dataset_and_langgraph_path(tmp_path: Path):
    bundle = load_historical_baseline_evidence("recruitment_screening", max_matched_records=3)
    assert bundle["re_executed"] is False
    assert bundle["groq_api_calls"] == 0
    assert bundle["matched_input_count"] == 3
    assert bundle["execution_mode"] == "historical_recorded_execution"
    assert bundle["matched_identifiers"][0]["candidate_id"] == "CAND-001"
    assert bundle["matched_identifiers"][1]["candidate_id"] == "CAND-002"

    # End-to-end LangGraph without any baseline execution node
    agent = OptimizationDiscoveryAgent()
    graph = build_optimization_graph_with_sandbox_execution(
        runtime_runs=2,
        llm_callable=lambda aid, *_a: {
            "output": {"application_id": "APP-001", "candidate_id": "CAND-001", "job_id": "JOB-01"},
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "tokens": 150,
            "assigned_key_identifier": "MOCK",
            "mode": "live_llm_execution",
        },
        judge_callable=lambda **_k: {"correctness": "passed", "completeness": "passed", "consistency": "passed", "instruction_adherence": "passed", "semantic_quality": "passed", "identified_issues": [], "rationale": "OK"},
    )
    cfg = {"configurable": {"thread_id": "test-fixed-base-lg"}}
    graph.invoke(
        {
            "workflow_id": "recruitment_screening",
            "evidence_dir": None,
            "target_model": "openai/gpt-oss-120b",
            "stage_status": {},
            "retrieval_errors": [],
            "analysis_limitations": [],
            "agent_run_comparisons": {},
            "execution_evidence": {},
            "optimization_candidates": [],
            "dimension_analyses": {},
            "tradeoff_assessments": [],
            "tier_classifications": {"tier_1": [], "tier_2": [], "tier_3": [], "tier_4": []},
            "final_report": {},
            "final_markdown_report": "",
            "key_usage_log": [],
            "sandbox_options": {"experiments_base_dir": str(tmp_path / "lg_exp"), "num_runs": 2},
        },
        cfg,
    )
    resumed = agent.resume_and_run_sandbox(
        graph,
        cfg,
        "recruitment_screening",
        selected_candidate_ids=["MODEL-RESUME_INTAKE_AGENT"],
        risk_acknowledged_candidate_ids=["MODEL-RESUME_INTAKE_AGENT"],
        persist=False,
    )
    assert resumed["stage_status"]["sandbox_historical_baseline_loading"] == "completed"
    assert resumed["stage_status"]["sandbox_optimized_execution"] == "completed"
    assert "sandbox_baseline_execution" not in resumed["stage_status"]
    rep = json.loads(Path(resumed["experiment_report_path"]).read_text(encoding="utf-8"))
    assert rep["baseline_evidence"]["re_executed"] is False
    assert rep["baseline_evidence"]["groq_api_calls"] == 0
