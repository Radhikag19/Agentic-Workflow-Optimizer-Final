"""
Validation Tests for Isolated (Non-Stacked) Per-Dimension Optimization Ablation
and Preserved Combined Single-Workflow Execution.
Uses mocked subprocesses and synthetic traces so zero paid Groq calls are made.
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
    SandboxExperimentRunner,
    build_dimension_scoped_approval,
    compute_directory_hashes,
    normalize_selected_dimensions,
)
from optimization_agent.sandbox.runtime.worker import WORKER_STDOUT_PREFIX


def _make_sample_workflow_and_evidence(tmp_path: Path):
    agents_dir = tmp_path / "agents"
    exp_dir = tmp_path / "experiments"
    data_dir = tmp_path / "data"
    hist_dir = tmp_path / "hist_traces"

    wf_dir = agents_dir / "ablation_wf"
    wf_dir.mkdir(parents=True, exist_ok=True)
    wf_json = {
        "workflow_id": "ablation_wf",
        "name": "Ablation Test Workflow",
        "baseline_model": "openai/gpt-oss-120b",
        "llm_provider": "Groq",
        "assigned_groq_key_env": "GROQ_API_KEY_5",
        "agents": [
            {
                "agent_id": "resume_intake_agent",
                "role": "Resume Intake Specialist",
                "dependencies": [],
                "input_fields": ["resume"],
                "output_fields": [
                    "application_id",
                    "candidate_id",
                    "candidate_name",
                    "contact_info_present",
                    "sections_identified",
                ],
            },
            {
                "agent_id": "qualification_agent",
                "role": "Qualification Analyst",
                "dependencies": ["resume_intake_agent"],
                "input_fields": ["candidate_id", "sections_identified"],
                "output_fields": ["candidate_id", "technical_skills"],
            },
            {
                "agent_id": "job_criteria_agent",
                "role": "Job Criteria Analyst",
                "dependencies": ["resume_intake_agent"],
                "input_fields": ["job"],
                "output_fields": ["job_id", "mandatory_criteria"],
            },
            {
                "agent_id": "experience_assessment_agent",
                "role": "Experience Assessor",
                "dependencies": ["qualification_agent", "job_criteria_agent"],
                "input_fields": ["candidate_id", "technical_skills", "mandatory_criteria"],
                "output_fields": ["candidate_id", "years_experience"],
            },
        ],
    }
    (wf_dir / "workflow.json").write_text(json.dumps(wf_json, indent=2), encoding="utf-8")
    (wf_dir / "workflow.py").write_text("# baseline workflow runner\n", encoding="utf-8")
    (wf_dir / "intake_agent.py").write_text(
        'AGENT_ID = "resume_intake_agent"\nROLE = "Resume Intake Specialist"\nGOAL = "Parse resume."\n',
        encoding="utf-8",
    )
    (wf_dir / "qualification_agent.py").write_text(
        'AGENT_ID = "qualification_agent"\nROLE = "Qualification Analyst"\nGOAL = "Extract skills."\n',
        encoding="utf-8",
    )
    (wf_dir / "job_criteria_agent.py").write_text(
        'AGENT_ID = "job_criteria_agent"\nROLE = "Job Criteria Analyst"\nGOAL = "Parse job."\n',
        encoding="utf-8",
    )
    (wf_dir / "experience_assessment_agent.py").write_text(
        'AGENT_ID = "experience_assessment_agent"\nROLE = "Experience Assessor"\nGOAL = "Assess experience."\n',
        encoding="utf-8",
    )

    wf_data_dir = data_dir / "ablation_wf"
    wf_data_dir.mkdir(parents=True, exist_ok=True)
    (wf_data_dir / "resumes.json").write_text(
        json.dumps([
            {
                "application_id": "APP-001",
                "candidate_id": "CAND-001",
                "candidate_name": "Dakota Chen",
                "target_job_id": "JOB-01",
            }
        ]),
        encoding="utf-8",
    )
    (wf_data_dir / "jobs.json").write_text(
        json.dumps([{"job_id": "JOB-01", "title": "Senior Cloud Engineer"}]),
        encoding="utf-8",
    )

    hist_dir.mkdir(parents=True, exist_ok=True)
    (hist_dir / "trace01.json").write_text(
        json.dumps({
            "run_id": "hist_ablation_01",
            "workflow_name": "ablation_wf",
            "status": "SUCCESS",
            "duration_seconds": 8.0,
            "prompt_tokens": 900,
            "completion_tokens": 300,
            "total_tokens": 1200,
            "agent_executions": [
                {
                    "agent_id": "resume_intake_agent",
                    "duration_seconds": 2.0,
                    "output": {
                        "application_id": "APP-001",
                        "candidate_id": "CAND-001",
                        "candidate_name": "Dakota Chen",
                        "contact_info_present": True,
                        "sections_identified": ["education", "skills"],
                    },
                },
                {
                    "agent_id": "qualification_agent",
                    "duration_seconds": 2.0,
                    "output": {"candidate_id": "CAND-001", "technical_skills": []},
                },
                {
                    "agent_id": "job_criteria_agent",
                    "duration_seconds": 2.0,
                    "output": {"job_id": "JOB-01", "mandatory_criteria": []},
                },
                {
                    "agent_id": "experience_assessment_agent",
                    "duration_seconds": 2.0,
                    "output": {"candidate_id": "CAND-001", "years_experience": 5},
                },
            ],
        }),
        encoding="utf-8",
    )

    candidates = [
        {
            "candidate_id": "PAR-QUAL-JOB",
            "dimension": "workflow_parallelization",
            "target_agents": ["qualification_agent", "job_criteria_agent"],
        },
        {
            "candidate_id": "MODEL-INTAKE",
            "dimension": "model_selection",
            "target_agents": ["resume_intake_agent"],
            "selected_model": "openai/gpt-oss-20b",
        },
        {
            "candidate_id": "PROMPT-EXP",
            "dimension": "prompt_optimization",
            "target_agents": ["experience_assessment_agent"],
            "optimized_prompt": "Compact experience prompt returning strict JSON.",
        },
        {
            "candidate_id": "HANDOFF-QUAL-EXP",
            "dimension": "communication_data_handoff",
            "target_agents": ["qualification_agent", "experience_assessment_agent"],
            "proposed_compact_payload_schema": {
                "retained_fields": ["candidate_id", "technical_skills"],
                "excluded_fields": ["verbose_notes"],
            },
            "supporting_evidence": {
                "producer_agent": "qualification_agent",
                "consumer_agent": "experience_assessment_agent",
                "consumer_required_fields": ["candidate_id"],
            },
        },
    ]
    scope = {
        "workflow_id": "ablation_wf",
        "approval_status": "approved",
        "approved_candidate_ids": [c["candidate_id"] for c in candidates],
        "approved_candidates": candidates,
    }
    return agents_dir, exp_dir, data_dir, hist_dir, wf_dir, scope


def _make_mock_subprocess(calls_log: List[Dict[str, Any]]):
    def _mock_subproc(cmd, **kwargs):
        req_path = Path(cmd[cmd.index("--request-file") + 1])
        resp_path = Path(cmd[cmd.index("--response-file") + 1])
        req = json.loads(req_path.read_text(encoding="utf-8"))
        assert req["variant"] == "optimized"
        calls_log.append({
            "experiment_id": req["experiment_id"],
            "workflow_dir": req["workflow_directory"],
        })

        traces_dir = Path(req["trace_directory"])
        traces_dir.mkdir(parents=True, exist_ok=True)
        wf_data = json.loads((Path(req["workflow_directory"]) / "workflow.json").read_text(encoding="utf-8"))
        is_parallel = bool(wf_data.get("parallel_groups"))
        dur = 4.5 if is_parallel else 6.0

        traces = []
        trace_files = []
        for idx, run_idx in enumerate(req.get("run_indices") or [0]):
            trace_obj = {
                "run_id": f"opt_{req['experiment_id']}_{run_idx}",
                "run_index": run_idx,
                "variant": "optimized",
                "workflow_name": req["workflow_id"],
                "experiment_id": req["experiment_id"],
                "status": "SUCCESS",
                "execution_mode": "live_llm_execution",
                "usage_sources": ["api_reported"],
                "duration_seconds": dur,
                "agent_executions": [
                    {
                        "order": 1,
                        "agent_id": "resume_intake_agent",
                        "model": "openai/gpt-oss-20b",
                        "duration_seconds": 1.0,
                        "status": "SUCCESS",
                        "tokens": 200,
                        "prompt_tokens": 140,
                        "completion_tokens": 60,
                        "estimated_cost_usd": 0.00002,
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
                        "duration_seconds": 1.0,
                        "status": "SUCCESS",
                        "tokens": 200,
                        "prompt_tokens": 140,
                        "completion_tokens": 60,
                        "estimated_cost_usd": 0.00005,
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
                    {
                        "order": 3,
                        "agent_id": "job_criteria_agent",
                        "model": "openai/gpt-oss-120b",
                        "duration_seconds": 1.0,
                        "status": "SUCCESS",
                        "tokens": 200,
                        "prompt_tokens": 140,
                        "completion_tokens": 60,
                        "estimated_cost_usd": 0.00005,
                        "usage_source": "api_reported",
                        "schema_valid": True,
                        "mode": "live_llm_execution",
                        "output": {
                            "job_id": "JOB-01",
                            "role_title": "Senior Cloud Engineer",
                            "mandatory_requirements": [],
                            "preferred_requirements": [],
                            "scoring_rubric_notes": [],
                            "ambiguities_flagged": [],
                        },
                    },
                    {
                        "order": 4,
                        "agent_id": "experience_assessment_agent",
                        "model": "openai/gpt-oss-120b",
                        "duration_seconds": 1.0,
                        "status": "SUCCESS",
                        "tokens": 200,
                        "prompt_tokens": 140,
                        "completion_tokens": 60,
                        "estimated_cost_usd": 0.00005,
                        "usage_source": "api_reported",
                        "schema_valid": True,
                        "mode": "live_llm_execution",
                        "output": {
                            "candidate_id": "CAND-001",
                            "relevant_experience_summary": "5 years cloud engineering",
                            "total_relevant_years_estimate": 5.0,
                            "seniority_alignment": "strong",
                            "domain_progression": [],
                            "career_gaps_or_anomalies": [],
                            "risk_flags": [],
                        },
                    },
                ],
                "total_tokens": 800,
                "prompt_tokens": 560,
                "completion_tokens": 240,
                "estimated_cost_usd": 0.00017,
            }
            tf = traces_dir / f"opt_{run_idx}_{idx}.json"
            tf.write_text(json.dumps(trace_obj), encoding="utf-8")
            traces.append(trace_obj)
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
            "groq_api_calls": 4 * len(traces),
            "agent_execution_results": {
                "variant": "optimized",
                "source": "current_experiment",
                "re_executed": True,
                "groq_api_calls": 4 * len(traces),
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
            "execution_duration": 0.25,
            "python_executable": sys.executable,
            "sys_path_head": req["workflow_directory"],
            "error_details": None,
        }
        resp_path.write_text(json.dumps(payload), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout=f"{WORKER_STDOUT_PREFIX}{{}}\n", stderr="")

    return _mock_subproc


_JUDGE_PASS = lambda **_k: {
    "correctness": "passed",
    "completeness": "passed",
    "consistency": "passed",
    "instruction_adherence": "passed",
    "semantic_quality": "passed",
    "identified_issues": [],
    "rationale": "All outputs verified.",
}


def test_01_all_dimensions_non_stacked_isolation_and_combined(tmp_path: Path):
    agents_dir, exp_dir, data_dir, hist_dir, orig_wf_dir, scope = _make_sample_workflow_and_evidence(tmp_path)
    pre_hashes = compute_directory_hashes(orig_wf_dir)
    calls_log: List[Dict[str, Any]] = []

    runner = SandboxExperimentRunner(
        agents_base_dir=agents_dir,
        experiments_base_dir=exp_dir,
        data_base_dir=data_dir,
        baseline_traces_dir=hist_dir,
        execution_backend="local_subprocess",
        per_run_subprocess=False,
        subprocess_runner=_make_mock_subprocess(calls_log),
        judge_callable=_JUDGE_PASS,
    )
    suite = runner.run_dimension_ablation_suite(
        scope,
        suite_id="suite_all",
        selected_dimensions=None,
        include_combined=True,
        num_runs=2,
    )

    assert suite["executed_dimensions"] == [
        "workflow_parallelization",
        "model_selection",
        "prompt_optimization",
        "communication_data_handoff",
    ]
    assert suite["skipped_dimensions"] == [{"dimension": "agent_consolidation", "reason": "no_approved_candidates"}]
    assert suite["baseline_runtime_results"]["re_executed"] is False
    assert suite["baseline_runtime_results"]["groq_api_calls"] == 0
    assert len(calls_log) == 5  # 4 isolated dimensions + 1 combined

    # Verify strict non-stacked isolation in each per-dimension sandbox_workflow
    par_wf = json.loads((Path(suite["per_dimension_results"]["workflow_parallelization"]["sandbox_workflow_dir"]) / "workflow.json").read_text(encoding="utf-8"))
    assert par_wf.get("parallel_groups") == [["qualification_agent", "job_criteria_agent"]]
    assert not par_wf.get("agent_model_overrides")
    assert not par_wf.get("handoff_projections")

    mod_wf = json.loads((Path(suite["per_dimension_results"]["model_selection"]["sandbox_workflow_dir"]) / "workflow.json").read_text(encoding="utf-8"))
    assert "resume_intake_agent" in (mod_wf.get("agent_model_overrides") or {})
    assert not mod_wf.get("parallel_groups")
    assert not mod_wf.get("handoff_projections")

    prm_sb = Path(suite["per_dimension_results"]["prompt_optimization"]["sandbox_workflow_dir"])
    prm_wf = json.loads((prm_sb / "workflow.json").read_text(encoding="utf-8"))
    assert "OPTIMIZED_PROMPT" in (prm_sb / "experience_assessment_agent.py").read_text(encoding="utf-8")
    assert not prm_wf.get("parallel_groups")
    assert not prm_wf.get("agent_model_overrides")

    hnd_wf = json.loads((Path(suite["per_dimension_results"]["communication_data_handoff"]["sandbox_workflow_dir"]) / "workflow.json").read_text(encoding="utf-8"))
    assert "qualification_agent->experience_assessment_agent" in (hnd_wf.get("handoff_projections") or {})
    assert not hnd_wf.get("parallel_groups")
    assert not hnd_wf.get("agent_model_overrides")

    # Verify combined single-workflow sandbox applies all 4 dimensions together
    comb = suite["combined_result"]
    assert comb is not None
    assert comb["execution_results"]["applied_candidate_ids"] == [
        "PAR-QUAL-JOB",
        "MODEL-INTAKE",
        "PROMPT-EXP",
        "HANDOFF-QUAL-EXP",
    ]
    comb_sb = Path(comb["sandbox_workflow_dir"])
    comb_wf = json.loads((comb_sb / "workflow.json").read_text(encoding="utf-8"))
    assert comb_wf.get("parallel_groups") == [["qualification_agent", "job_criteria_agent"]]
    assert "resume_intake_agent" in (comb_wf.get("agent_model_overrides") or {})
    assert "OPTIMIZED_PROMPT" in (comb_sb / "experience_assessment_agent.py").read_text(encoding="utf-8")
    assert "qualification_agent->experience_assessment_agent" in (comb_wf.get("handoff_projections") or {})

    # Verify ablation suite reports and zero mutation on original workflow
    assert Path(suite["json_report_path"]).exists()
    assert Path(suite["markdown_report_path"]).exists()
    labels = [r["label"] for r in suite["comparison_rows"]]
    assert labels == [
        "fixed_historical_baseline",
        "workflow_parallelization",
        "model_selection",
        "prompt_optimization",
        "communication_data_handoff",
        "combined_all_selected_dimensions",
    ]
    assert suite["original_integrity_after"]["original_unchanged"] is True
    assert compute_directory_hashes(orig_wf_dir) == pre_hashes


def test_02_user_chosen_dimensions_filter_and_optional_combined(tmp_path: Path):
    agents_dir, exp_dir, data_dir, hist_dir, _, scope = _make_sample_workflow_and_evidence(tmp_path)
    calls_log: List[Dict[str, Any]] = []

    runner = SandboxExperimentRunner(
        agents_base_dir=agents_dir,
        experiments_base_dir=exp_dir,
        data_base_dir=data_dir,
        baseline_traces_dir=hist_dir,
        execution_backend="local_subprocess",
        per_run_subprocess=False,
        subprocess_runner=_make_mock_subprocess(calls_log),
        judge_callable=_JUDGE_PASS,
    )
    suite = runner.run_dimension_ablation_suite(
        scope,
        suite_id="suite_subset",
        selected_dimensions=["model_selection", "communication_optimization"],
        include_combined=False,
        num_runs=1,
    )

    assert suite["selected_dimensions"] == ["model_selection", "communication_data_handoff"]
    assert suite["executed_dimensions"] == ["model_selection", "communication_data_handoff"]
    assert suite["skipped_dimensions"] == []
    assert suite["combined_result"] is None
    assert len(calls_log) == 2
    assert set(suite["per_dimension_results"].keys()) == {"model_selection", "communication_data_handoff"}


def test_03_skipped_empty_dimension_and_invalid_dimension_error(tmp_path: Path):
    agents_dir, exp_dir, data_dir, hist_dir, _, scope = _make_sample_workflow_and_evidence(tmp_path)

    with pytest.raises(ValueError, match="Unknown optimization dimension"):
        normalize_selected_dimensions(["nonexistent_dimension"])

    assert build_dimension_scoped_approval(scope, ["agent_consolidation"]) is None

    runner = SandboxExperimentRunner(
        agents_base_dir=agents_dir,
        experiments_base_dir=exp_dir,
        data_base_dir=data_dir,
        baseline_traces_dir=hist_dir,
        execution_backend="local_subprocess",
        per_run_subprocess=False,
        subprocess_runner=_make_mock_subprocess([]),
        judge_callable=_JUDGE_PASS,
    )
    suite = runner.run_dimension_ablation_suite(
        scope,
        suite_id="suite_skip",
        selected_dimensions=["agent_consolidation", "model_selection"],
        include_combined=True,
        num_runs=1,
    )
    assert suite["executed_dimensions"] == ["model_selection"]
    assert suite["skipped_dimensions"] == [{"dimension": "agent_consolidation", "reason": "no_approved_candidates"}]


def test_04_agent_suite_entrypoint_and_legacy_combined_run_preserved(tmp_path: Path):
    agents_dir, exp_dir, data_dir, hist_dir, orig_wf_dir, scope = _make_sample_workflow_and_evidence(tmp_path)
    agent = OptimizationDiscoveryAgent()
    assert hasattr(agent, "run_sandbox_dimension_suite")

    # Verify legacy combined SandboxExperimentRunner.run(...) stays untouched and functional
    calls_log: List[Dict[str, Any]] = []
    runner = SandboxExperimentRunner(
        agents_base_dir=agents_dir,
        experiments_base_dir=exp_dir,
        data_base_dir=data_dir,
        baseline_traces_dir=hist_dir,
        execution_backend="local_subprocess",
        per_run_subprocess=False,
        subprocess_runner=_make_mock_subprocess(calls_log),
        judge_callable=_JUDGE_PASS,
    )
    single_out = runner.run(scope, experiment_id="legacy_combined", num_runs=2)
    assert len(calls_log) == 1
    assert single_out["execution_results"]["applied_candidate_ids"] == [
        "PAR-QUAL-JOB",
        "MODEL-INTAKE",
        "PROMPT-EXP",
        "HANDOFF-QUAL-EXP",
    ]
    assert single_out["original_integrity_after"]["original_unchanged"] is True
