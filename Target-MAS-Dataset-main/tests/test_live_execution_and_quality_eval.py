"""
Validation Test Suite for Live Execution, Schema Diagnosis, Output Quality Evaluation,
Matched Baseline vs. Optimized Execution, and 7-Section Reporting (Checks 1-14).
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

from common.validation import RecruiterSummaryOutput
from mcp_server import tools as evidence_tools
from optimization_agent.agent import OptimizationDiscoveryAgent
from optimization_agent.sandbox import (
    SandboxExperimentRunner,
    SandboxManager,
    SandboxWorkflowRunner,
    build_optimization_graph_with_sandbox_execution,
    classify_final_experiment_assessment,
    compute_directory_hashes,
    evaluate_agent_output_quality,
    evaluate_experiment,
)
from optimization_agent.sandbox.validation import validate_sandbox


def _make_recruitment_like_workflow(base_dir: Path, workflow_id: str = "sample_live_wf") -> Path:
    wf_dir = base_dir / workflow_id
    wf_dir.mkdir(parents=True, exist_ok=True)
    wf_json = {
        "workflow_id": workflow_id,
        "name": "Sample Recruitment Screening Live",
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
                "output_fields": ["candidate_id", "technical_skills", "education", "experience_records"],
            },
            {
                "agent_id": "job_criteria_agent",
                "role": "Job Criteria Analyst",
                "dependencies": ["resume_intake_agent"],
                "input_fields": ["job"],
                "output_fields": ["job_id", "job_title", "mandatory_criteria", "preferred_criteria"],
            },
            {
                "agent_id": "evidence_mapping_agent",
                "role": "Evidence Mapper",
                "dependencies": ["qualification_agent", "job_criteria_agent"],
                "input_fields": ["technical_skills", "mandatory_criteria"],
                "output_fields": ["candidate_id", "job_id", "mappings", "supported_count", "unsupported_count"],
            },
            {
                "agent_id": "recruiter_summary_agent",
                "role": "Executive Recruiter Summary Synthesizer",
                "dependencies": ["evidence_mapping_agent"],
                "input_fields": ["candidate_id", "job_id", "mappings"],
                "output_fields": [
                    "run_id",
                    "application_id",
                    "candidate_id",
                    "candidate_name",
                    "job_id",
                    "job_title",
                    "executive_candidate_overview",
                    "criteria_matrix",
                    "key_strengths",
                    "evidence_gaps",
                    "identified_inconsistencies",
                    "recommended_follow_up_questions",
                    "deterministic_match_score",
                    "score_calculation_method",
                    "score_limitations",
                ],
            },
        ],
    }
    (wf_dir / "workflow.json").write_text(json.dumps(wf_json, indent=2), encoding="utf-8")

    py_defs = {
        "intake_agent.py": 'AGENT_ID = "resume_intake_agent"\nROLE = "Resume Intake Specialist"\nGOAL = "Parse resume."\n',
        "qualification_agent.py": 'AGENT_ID = "qualification_agent"\nROLE = "Qualification Analyst"\nGOAL = "Extract skills."\n',
        "job_criteria_agent.py": 'AGENT_ID = "job_criteria_agent"\nROLE = "Job Criteria Analyst"\nGOAL = "Extract job criteria."\n',
        "evidence_mapping_agent.py": 'AGENT_ID = "evidence_mapping_agent"\nROLE = "Evidence Mapper"\nGOAL = "Map evidence."\n',
        "recruiter_summary_agent.py": 'AGENT_ID = "recruiter_summary_agent"\nROLE = "Executive Recruiter Summary Synthesizer"\nGOAL = "Summarize screening without autonomous hiring decisions."\n',
    }
    for fname, body in py_defs.items():
        (wf_dir / fname).write_text(body, encoding="utf-8")

    return wf_dir


def _make_schema_valid_payloads(candidate_id: str = "CAND-001", job_id: str = "JOB-01") -> Dict[str, Dict[str, Any]]:
    return {
        "resume_intake_agent": {
            "application_id": "APP-001",
            "candidate_id": candidate_id,
            "candidate_name": "Dakota Chen",
            "contact_info_present": True,
            "sections_identified": ["education", "experience", "skills"],
            "missing_sections": [],
            "raw_sections": {"skills": ["Python"]},
            "source_evidence_ids": ["EVD-1"],
            "intake_notes": [],
        },
        "qualification_agent": {
            "candidate_id": candidate_id,
            "technical_skills": [
                {
                    "category": "technical_skill",
                    "item_name": "Python",
                    "proficiency_or_duration": "5y",
                    "supporting_excerpt": "5 years Python",
                    "evidence_id": "EVD-1",
                }
            ],
            "education": [],
            "certifications": [],
            "experience_records": [
                {
                    "category": "experience",
                    "item_name": "Backend Engineer",
                    "proficiency_or_duration": "5 years",
                    "supporting_excerpt": "Built APIs",
                    "evidence_id": "EVD-2",
                }
            ],
            "projects": [],
            "extraction_warnings": [],
        },
        "job_criteria_agent": {
            "job_id": job_id,
            "job_title": "Senior Cloud Backend Engineer",
            "mandatory_criteria": [
                {
                    "criterion_id": "CRIT-M1",
                    "category": "technical_skill",
                    "requirement_type": "mandatory",
                    "description": "Python backend",
                    "is_ambiguous": False,
                }
            ],
            "preferred_criteria": [],
            "total_criteria_count": 1,
            "parsing_notes": [],
        },
        "evidence_mapping_agent": {
            "candidate_id": candidate_id,
            "job_id": job_id,
            "mappings": [
                {
                    "criterion_id": "CRIT-M1",
                    "requirement_type": "mandatory",
                    "status": "supported",
                    "candidate_evidence": "5 years Python",
                    "evidence_ids": ["EVD-1"],
                    "is_missing_qualification": False,
                    "is_missing_evidence_only": False,
                    "notes": "Supported by resume.",
                }
            ],
            "supported_count": 1,
            "unsupported_count": 0,
            "partially_supported_count": 0,
            "unclear_count": 0,
        },
        "recruiter_summary_agent": {
            "run_id": "live_test_run",
            "application_id": "APP-001",
            "candidate_id": candidate_id,
            "candidate_name": "Dakota Chen",
            "job_id": job_id,
            "job_title": "Senior Cloud Backend Engineer",
            "executive_candidate_overview": "Candidate matches mandatory Python criterion.",
            "criteria_matrix": [
                {
                    "criterion_id": "CRIT-M1",
                    "requirement_type": "mandatory",
                    "status": "supported",
                    "candidate_evidence": "5 years Python",
                    "evidence_ids": ["EVD-1"],
                    "is_missing_qualification": False,
                    "is_missing_evidence_only": False,
                    "notes": "Supported",
                }
            ],
            "key_strengths": ["5 years Python experience (EVD-1)."],
            "evidence_gaps": [],
            "identified_inconsistencies": [],
            "recommended_follow_up_questions": ["Walk through your largest distributed Python system."],
            "deterministic_match_score": 100.0,
            "score_calculation_method": "Mandatory 70%, Preferred 30%",
            "score_limitations": "Keyword overlap only.",
            "human_review_required": True,
            "non_autonomous_decision_statement": "This is an automated screening assistant summary. It does NOT make autonomous hiring decisions.",
            "validation_warnings": [],
        },
    }


def _scope(workflow_id: str, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "workflow_id": workflow_id,
        "approval_status": "approved",
        "approved_candidate_ids": [c["candidate_id"] for c in candidates],
        "approved_candidates": candidates,
    }


# ---------------------------------------------------------------------------
# Check 1: Diagnose Existing Historical RecruiterSummaryOutput Failures
# ---------------------------------------------------------------------------
def test_check_01_historical_recruiter_summary_failure_diagnosed_without_weakening_schema():
    data, err = evidence_tools._load_evidence("recruitment_screening")
    assert err is None
    tdir = evidence_tools._find_traces_dir("recruitment_screening", data)
    assert tdir is not None and tdir.exists()

    required_fields = {k for k, v in RecruiterSummaryOutput.model_fields.items() if v.is_required()}
    assert {
        "identified_inconsistencies",
        "recommended_follow_up_questions",
        "score_calculation_method",
        "score_limitations",
    }.issubset(required_fields)

    invalid_count = 0
    for tf in sorted(tdir.glob("*.json")):
        td = json.loads(tf.read_text(encoding="utf-8"))
        for ex in td.get("agent_executions") or []:
            if ex.get("agent_id") == "recruiter_summary_agent":
                with pytest.raises(Exception):
                    RecruiterSummaryOutput.model_validate(ex.get("output"))
                invalid_count += 1
    assert invalid_count == 30


# ---------------------------------------------------------------------------
# Check 2: Incomplete Replay Records Flagged & Never Marked Semantically Valid
# ---------------------------------------------------------------------------
def test_check_02_incomplete_replay_flagged_and_never_treated_as_valid_quality(tmp_path: Path):
    exp_dir = tmp_path / "experiments"
    cand = {
        "candidate_id": "MODEL-RESUME_INTAKE_AGENT",
        "dimension": "model_selection",
        "target_agents": ["resume_intake_agent"],
        "selected_model": "openai/gpt-oss-20b",
    }
    runner = SandboxExperimentRunner(
        experiments_base_dir=exp_dir,
        groq_client_factory=lambda _k: (_ for _ in ()).throw(ConnectionError("offline blocked")),
        enable_trace_replay_fallback=True,
        run_matched_baseline=True,
    )
    out = runner.run(_scope("recruitment_screening", [cand]), experiment_id="exp_hist_flag", num_runs=1)

    assert len(out["runtime_results"]["invalid_replay_samples"]) >= 1
    recruiter_evals = [
        e for e in out["quality_evaluation"]["optimized_quality"]["agent_evaluations"]
        if e["agent_id"] == "recruiter_summary_agent"
    ]
    assert len(recruiter_evals) == 1
    assert recruiter_evals[0]["evaluation_status"] == "insufficient_sample"
    assert recruiter_evals[0]["structural_validity"] == "failed"
    assert recruiter_evals[0]["semantic_quality"] == "unavailable"
    assert out["final_experiment_assessment"]["status"] == "inconclusive"


# ---------------------------------------------------------------------------
# Check 3: Live Execution Fails Loudly When enable_trace_replay_fallback=False
# ---------------------------------------------------------------------------
def test_check_03_live_failure_does_not_fallback_silently(tmp_path: Path):
    agents_dir = tmp_path / "agents"
    exp_dir = tmp_path / "experiments"
    _make_recruitment_like_workflow(agents_dir, "sample_live_wf")

    def _failing_client_factory(_key: str):
        raise RuntimeError("Simulated Groq API outage 503")

    cand = {
        "candidate_id": "MODEL-INTAKE",
        "dimension": "model_selection",
        "target_agents": ["resume_intake_agent"],
        "selected_model": "openai/gpt-oss-20b",
    }
    runner = SandboxExperimentRunner(
        agents_base_dir=agents_dir,
        experiments_base_dir=exp_dir,
        enable_trace_replay_fallback=False,
        groq_client_factory=_failing_client_factory,
        run_matched_baseline=False,
    )
    out = runner.run(_scope("sample_live_wf", [cand]), experiment_id="exp_live_fail", num_runs=1)

    rt = out["runtime_results"]
    assert rt["execution_passed"] is False
    assert "offline_trace_replay_sandbox" not in rt["execution_modes"]
    assert len(rt["api_errors"]) >= 1
    assert rt["api_errors"][0]["agent_id"] == "resume_intake_agent"
    assert "Simulated Groq API outage" in rt["api_errors"][0]["error"]
    assert out["final_experiment_assessment"]["status"] == "failed"


# ---------------------------------------------------------------------------
# Checks 4 & 5: Mocked Groq SDK Live Execution Captures Usage, Models & Key Masking
# ---------------------------------------------------------------------------
def test_check_04_and_05_mocked_groq_live_execution_usage_and_traces(tmp_path: Path):
    agents_dir = tmp_path / "agents"
    exp_dir = tmp_path / "experiments"
    _make_recruitment_like_workflow(agents_dir, "sample_live_wf")
    payloads = _make_schema_valid_payloads()

    seen_calls: List[Dict[str, Any]] = []

    def _mock_groq_factory(_raw_key: str):
        class _Completions:
            def create(self, **kwargs):
                model = kwargs["model"]
                user_msg = json.loads(kwargs["messages"][1]["content"])
                # Detect agent from schema/role in system prompt
                sys_msg = kwargs["messages"][0]["content"]
                aid = next(
                    a for a in payloads
                    if (a == "resume_intake_agent" and "Resume Intake" in sys_msg)
                    or (a == "qualification_agent" and "Qualification Analyst" in sys_msg)
                    or (a == "job_criteria_agent" and "Job Criteria Analyst" in sys_msg)
                    or (a == "evidence_mapping_agent" and "Evidence Mapper" in sys_msg)
                    or (a == "recruiter_summary_agent" and "Recruiter Summary" in sys_msg)
                )
                seen_calls.append({"agent_id": aid, "model": model, "user_msg": user_msg})
                pt = 210 if model == "openai/gpt-oss-20b" else 420
                ct = 95 if model == "openai/gpt-oss-20b" else 180
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payloads[aid])))],
                    usage=SimpleNamespace(prompt_tokens=pt, completion_tokens=ct, total_tokens=pt + ct),
                )

        return SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))

    cand = {
        "candidate_id": "MODEL-INTAKE",
        "dimension": "model_selection",
        "target_agents": ["resume_intake_agent"],
        "selected_model": "openai/gpt-oss-20b",
    }
    runner = SandboxExperimentRunner(
        agents_base_dir=agents_dir,
        experiments_base_dir=exp_dir,
        enable_trace_replay_fallback=False,
        groq_client_factory=_mock_groq_factory,
        run_matched_baseline=True,
        interleave_runs=True,
    )
    out = runner.run(_scope("sample_live_wf", [cand]), experiment_id="exp_mock_groq", num_runs=2)

    assert out["runtime_results"]["execution_passed"] is True
    assert out["runtime_results"]["execution_modes"] == ["live_llm_execution"]
    assert out["runtime_results"]["usage_sources"] == ["api_reported"]
    assert out["runtime_results"]["schema_validation_summary"]["all_schemas_valid"] is True

    # Verify model override ran llama-3.1-8b-instant only on optimized resume_intake_agent
    opt_trace = out["runtime_results"]["traces"][0]
    intake_exec = next(e for e in opt_trace["agent_executions"] if e["agent_id"] == "resume_intake_agent")
    assert intake_exec["model"] == "openai/gpt-oss-20b"
    assert intake_exec["prompt_tokens"] == 210
    assert intake_exec["completion_tokens"] == 95
    assert intake_exec["tokens"] == 305
    assert "gsk_" not in json.dumps(out["execution_report"])  # Never leak raw keys


# ---------------------------------------------------------------------------
# Checks 6 & 7: Identical Inputs & Multi-Run Support
# ---------------------------------------------------------------------------
def test_check_06_and_07_identical_inputs_and_multi_run(tmp_path: Path):
    agents_dir = tmp_path / "agents"
    exp_dir = tmp_path / "experiments"
    data_dir = tmp_path / "data"
    wf_data_dir = data_dir / "sample_live_wf"
    wf_data_dir.mkdir(parents=True, exist_ok=True)
    (wf_data_dir / "records.json").write_text(
        json.dumps([
            {"candidate_id": "C1", "job_id": "J1"},
            {"candidate_id": "C2", "job_id": "J2"},
            {"candidate_id": "C3", "job_id": "J3"},
        ]),
        encoding="utf-8",
    )
    hist_dir = tmp_path / "hist_traces"
    hist_dir.mkdir(parents=True, exist_ok=True)
    for i, (cid, jid) in enumerate([("C1", "J1"), ("C2", "J2"), ("C3", "J3")], 1):
        (hist_dir / f"hist_{i}.json").write_text(
            json.dumps({
                "run_id": f"hist_{i}",
                "workflow_name": "sample_live_wf",
                "status": "SUCCESS",
                "duration_seconds": 1.5,
                "prompt_tokens": 140,
                "completion_tokens": 60,
                "total_tokens": 200,
                "agent_executions": [
                    {"agent_id": "resume_intake_agent", "output": {"candidate_id": cid, "job_id": jid}}
                ],
            }),
            encoding="utf-8",
        )
    _make_recruitment_like_workflow(agents_dir, "sample_live_wf")

    payloads = _make_schema_valid_payloads()

    def _rec_llm(aid, model_id, sys_p, usr_p, ctx):
        return {
            "output": payloads[aid],
            "prompt_tokens": 120,
            "completion_tokens": 60,
            "tokens": 180,
            "assigned_key_identifier": "MOCK_KEY",
            "mode": "live_llm_execution",
        }

    runner = SandboxExperimentRunner(
        agents_base_dir=agents_dir,
        experiments_base_dir=exp_dir,
        data_base_dir=data_dir,
        baseline_traces_dir=hist_dir,
        llm_callable=_rec_llm,
    )
    out = runner.run(
        _scope(
            "sample_live_wf",
            [{"candidate_id": "M1", "dimension": "model_selection", "target_agents": ["resume_intake_agent"], "selected_model": "openai/gpt-oss-20b"}],
        ),
        experiment_id="exp_multirun",
        num_runs=3,
    )
    assert out["runtime_results"]["runs_executed"] == 3
    assert out["baseline_runtime_results"]["re_executed"] is False
    assert out["baseline_runtime_results"]["groq_api_calls"] == 0
    assert (
        out["baseline_runtime_results"]["input_dataset_hashes"]
        == out["runtime_results"]["input_dataset_hashes"]
    )
    assert len(set(out["runtime_results"]["input_dataset_hashes"])) == 3
    assert out["evaluation_results"]["comparison"]["comparability"]["inputs_comparable"] is True


# ---------------------------------------------------------------------------
# Checks 8 & 9: Pydantic Validity != Semantic Quality; Unavailable Never Fabricated
# ---------------------------------------------------------------------------
def test_check_08_and_09_structural_vs_semantic_separation_and_unavailable():
    valid_rec = _make_schema_valid_payloads()["recruiter_summary_agent"]
    # Without judge -> structural passed, semantic MUST be 'unavailable' (not 'passed')
    res_no_judge = evaluate_agent_output_quality(
        "recruiter_summary_agent",
        valid_rec,
        workflow_id="recruitment_screening",
        execution_record={"status": "SUCCESS", "mode": "live_llm_execution"},
        enable_llm_judge=False,
    )
    assert res_no_judge["structural_validity"] == "passed"
    assert res_no_judge["semantic_quality"] == "unavailable"

    # With strict judge detecting hallucination even on Pydantic-valid JSON -> semantic failed
    def _strict_judge(**_kw):
        return {
            "correctness": "failed",
            "completeness": "passed",
            "consistency": "passed",
            "instruction_adherence": "passed",
            "semantic_quality": "failed",
            "identified_issues": ["Claimed AWS certification not supported by resume."],
            "rationale": "Factual hallucination despite valid JSON schema.",
        }

    res_with_judge = evaluate_agent_output_quality(
        "recruiter_summary_agent",
        valid_rec,
        workflow_id="recruitment_screening",
        workflow_input={"resume": {"candidate_id": "CAND-001"}, "job": {"job_id": "JOB-01"}},
        execution_record={"status": "SUCCESS", "mode": "live_llm_execution"},
        judge_callable=_strict_judge,
    )
    assert res_with_judge["structural_validity"] == "passed"
    assert res_with_judge["semantic_quality"] == "failed"
    assert res_with_judge["correctness"] == "failed"


# ---------------------------------------------------------------------------
# Checks 10, 11, 12, 13: Metrics, Candidate Traceability, Integrity & All 6 Outcomes
# ---------------------------------------------------------------------------
def test_check_10_to_13_metrics_traceability_integrity_and_all_6_outcomes(tmp_path: Path):
    agents_dir = tmp_path / "agents"
    exp_dir = tmp_path / "experiments"
    orig_dir = _make_recruitment_like_workflow(agents_dir, "sample_live_wf")
    pre_hashes = compute_directory_hashes(orig_dir)

    payloads = _make_schema_valid_payloads()

    def _fast_opt_llm(aid, model_id, sys_p, usr_p, ctx):
        # Simulate lower tokens on optimized model & compressed handoff
        pt = 100 if model_id == "openai/gpt-oss-20b" else 200
        return {
            "output": payloads[aid],
            "prompt_tokens": pt,
            "completion_tokens": 50,
            "tokens": pt + 50,
            "assigned_key_identifier": "MOCK",
            "mode": "live_llm_execution",
        }

    def _passing_judge(**_kw):
        return {
            "correctness": "passed",
            "completeness": "passed",
            "consistency": "passed",
            "instruction_adherence": "passed",
            "semantic_quality": "passed",
            "identified_issues": [],
            "rationale": "Verified factual alignment.",
        }

    candidates = [
        {"candidate_id": "P1", "dimension": "workflow_parallelization", "target_agents": ["qualification_agent", "job_criteria_agent"]},
        {"candidate_id": "M1", "dimension": "model_selection", "target_agents": ["resume_intake_agent"], "selected_model": "openai/gpt-oss-20b"},
    ]
    runner = SandboxExperimentRunner(
        agents_base_dir=agents_dir,
        experiments_base_dir=exp_dir,
        llm_callable=_fast_opt_llm,
        judge_callable=_passing_judge,
        run_matched_baseline=True,
    )
    out = runner.run(_scope("sample_live_wf", candidates), experiment_id="exp_complete", num_runs=2)

    assert compute_directory_hashes(orig_dir) == pre_hashes
    assert out["original_integrity_after"]["original_unchanged"] is True

    # Check 10: 10 metrics present cleanly
    comp = out["evaluation_results"]["comparison"]
    for key in (
        "mean_workflow_latency",
        "median_workflow_latency",
        "mean_agent_latency",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "execution_cost",
        "execution_success_rate",
        "output_structural_validity",
        "semantic_quality",
    ):
        assert key in comp

    # Check 11: Candidate traceability without false single-candidate attribution
    assert len(out["evaluation_results"]["candidate_outcomes"]) == 2
    for co in out["evaluation_results"]["candidate_outcomes"]:
        assert "Multiple candidates (2)" in co["attribution_note"]
        assert co["modification_applied"] is True

    # Check 13: Test all 6 final assessment classification states
    base_ok = {"schema_validation_passed": True, "execution_modes": ["live_llm_execution"], "semantic_quality_status": "passed"}
    opt_ok = {"schema_validation_passed": True, "execution_modes": ["live_llm_execution"], "successful_runs": 2, "semantic_quality_status": "passed"}
    flags_ok = {"modification_applied": True, "validation_passed": True, "execution_passed": True, "evaluation_passed": True}

    assert classify_final_experiment_assessment(
        outcome_flags={**flags_ok, "execution_passed": False},
        comparison=comp,
        quality_evaluation={"has_quality_regression": False},
        baseline_metrics=base_ok,
        optimized_metrics=opt_ok,
        inputs_comparable=True,
    )["status"] == "failed"

    assert classify_final_experiment_assessment(
        outcome_flags=flags_ok,
        comparison=comp,
        quality_evaluation={"has_quality_regression": True, "identified_regressions": [{"agent_id": "recruiter_summary_agent", "metric": "semantic_quality"}]},
        baseline_metrics=base_ok,
        optimized_metrics=opt_ok,
        inputs_comparable=True,
    )["status"] == "quality_regression"

    assert classify_final_experiment_assessment(
        outcome_flags=flags_ok,
        comparison=comp,
        quality_evaluation={"has_quality_regression": False},
        baseline_metrics=base_ok,
        optimized_metrics={**opt_ok, "execution_modes": ["offline_trace_replay_sandbox"]},
        inputs_comparable=True,
    )["status"] == "inconclusive"

    comp_gain = {
        "mean_workflow_latency": {"improvement_pct": 15.0},
        "median_workflow_latency": {"improvement_pct": 12.0},
        "total_tokens": {"improvement_pct": 10.0},
        "execution_cost": {"improvement_pct_catalog_normalized": 18.0},
    }
    assert classify_final_experiment_assessment(
        outcome_flags=flags_ok,
        comparison=comp_gain,
        quality_evaluation={"has_quality_regression": False},
        baseline_metrics=base_ok,
        optimized_metrics=opt_ok,
        inputs_comparable=True,
    )["status"] == "successful"

    comp_tradeoff = {
        "mean_workflow_latency": {"improvement_pct": -12.0},
        "median_workflow_latency": {"improvement_pct": -10.0},
        "total_tokens": {"improvement_pct": 25.0},
        "execution_cost": {"improvement_pct_catalog_normalized": 30.0},
    }
    assert classify_final_experiment_assessment(
        outcome_flags=flags_ok,
        comparison=comp_tradeoff,
        quality_evaluation={"has_quality_regression": False},
        baseline_metrics=base_ok,
        optimized_metrics=opt_ok,
        inputs_comparable=True,
    )["status"] == "successful_with_tradeoffs"

    comp_flat = {
        "mean_workflow_latency": {"improvement_pct": 0.4},
        "median_workflow_latency": {"improvement_pct": 0.2},
        "total_tokens": {"improvement_pct": 0.0},
        "execution_cost": {"improvement_pct_catalog_normalized": 0.5},
    }
    assert classify_final_experiment_assessment(
        outcome_flags=flags_ok,
        comparison=comp_flat,
        quality_evaluation={"has_quality_regression": False},
        baseline_metrics=base_ok,
        optimized_metrics=opt_ok,
        inputs_comparable=True,
    )["status"] == "no_significant_improvement"


# ---------------------------------------------------------------------------
# Check 14: End-to-End LangGraph Pipeline With Baseline+Optimized+Quality+Report
# ---------------------------------------------------------------------------
def test_check_14_langgraph_pipeline_runs_baseline_optimized_quality_and_report(tmp_path: Path):
    payloads = _make_schema_valid_payloads()

    def _mock_live_llm(aid, model_id, sys_p, usr_p, ctx):
        out = payloads.get(aid) or {"candidate_id": "CAND-001", "job_id": "JOB-01", "status": "ok"}
        return {
            "output": out,
            "prompt_tokens": 150,
            "completion_tokens": 60,
            "tokens": 210,
            "assigned_key_identifier": "MOCK_KEY",
            "mode": "live_llm_execution",
        }

    def _mock_judge(**_kw):
        return {
            "correctness": "passed",
            "completeness": "passed",
            "consistency": "passed",
            "instruction_adherence": "passed",
            "semantic_quality": "passed",
            "identified_issues": [],
            "rationale": "All checks passed.",
        }

    agent = OptimizationDiscoveryAgent()
    graph = build_optimization_graph_with_sandbox_execution(
        llm_callable=_mock_live_llm,
        runtime_runs=2,
        judge_callable=_mock_judge,
    )
    cfg = {"configurable": {"thread_id": "test-live-e2e-thread"}}
    initial_state = {
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
        "sandbox_options": {"experiments_base_dir": str(tmp_path / "experiments"), "num_runs": 2},
    }
    graph.invoke(initial_state, cfg)
    resumed = agent.resume_and_run_sandbox(
        graph,
        cfg,
        "recruitment_screening",
        selected_candidate_ids=[
            "PARALLEL-QUALIFICATION_AGENT-JOB_CRITERIA_AGENT",
            "MODEL-RESUME_INTAKE_AGENT",
        ],
        risk_acknowledged_candidate_ids=[
            "PARALLEL-QUALIFICATION_AGENT-JOB_CRITERIA_AGENT",
            "MODEL-RESUME_INTAKE_AGENT",
        ],
        persist=False,
    )
    assert resumed["stage_status"]["sandbox_historical_baseline_loading"] == "completed"
    assert resumed["stage_status"]["sandbox_optimized_execution"] == "completed"
    assert resumed["stage_status"]["sandbox_quality_evaluation"] == "completed"
    assert resumed["stage_status"]["sandbox_performance_comparison"] == "completed"
    assert resumed["stage_status"]["sandbox_experiment_report"] == "completed"

    rep = json.loads(Path(resumed["experiment_report_path"]).read_text(encoding="utf-8"))
    md = (Path(resumed["experiment_report_path"]).parent / "execution_report.md").read_text(encoding="utf-8")
    for sec in (
        "## 1. Experiment Metadata",
        "## 2. Applied Modifications",
        "## 3. Validation Results",
        "## 4. Runtime Execution",
        "## 5. Output Quality Evaluation",
        "## 6. Before-and-After Comparison",
        "## 7. Final Experiment Assessment",
    ):
        assert sec in md
    assert rep["final_experiment_assessment"]["status"] in {
        "successful",
        "successful_with_tradeoffs",
        "no_significant_improvement",
        "quality_regression",
        "inconclusive",
        "failed",
    }
