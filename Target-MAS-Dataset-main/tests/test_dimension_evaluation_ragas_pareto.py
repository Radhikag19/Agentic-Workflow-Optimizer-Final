"""
Comprehensive 20-Requirement Validation Suite for Dimension-Wise Optimization Evaluation,
RAGAS Quality Assessment, Two-Phase + Combined Study, and Pareto Best-Workflow Selection.

Uses mocked subprocess execution and mocked RAGAS evaluators (zero paid Groq API calls).
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
    QualityAcceptanceCriteria,
    SandboxExperimentRunner,
    build_ragas_samples,
    compute_directory_hashes,
    evaluate_quality_acceptance,
    evaluate_with_ragas,
    select_best_workflows_pareto,
)
from optimization_agent.sandbox.runtime.worker import WORKER_STDOUT_PREFIX


def _build_full_5dim_fixture(tmp_path: Path):
    agents_dir = tmp_path / "agents"
    exp_dir = tmp_path / "experiments"
    data_dir = tmp_path / "data"
    hist_dir = tmp_path / "hist_traces"

    wf_dir = agents_dir / "study_wf"
    wf_dir.mkdir(parents=True, exist_ok=True)
    wf_json = {
        "workflow_id": "study_wf",
        "name": "5-Dimension Study Workflow",
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
            {
                "agent_id": "screening_review_agent",
                "role": "Screening Reviewer",
                "dependencies": ["experience_assessment_agent"],
                "input_fields": ["candidate_id", "years_experience"],
                "output_fields": ["candidate_id", "review_decision"],
            },
            {
                "agent_id": "recruiter_summary_agent",
                "role": "Recruiter Summary Writer",
                "dependencies": ["screening_review_agent"],
                "input_fields": ["candidate_id", "review_decision"],
                "output_fields": ["run_id", "candidate_id", "summary"],
            },
        ],
    }
    (wf_dir / "workflow.json").write_text(json.dumps(wf_json, indent=2), encoding="utf-8")
    (wf_dir / "workflow.py").write_text("# baseline\n", encoding="utf-8")
    for fname, aid, role in [
        ("intake_agent.py", "resume_intake_agent", "Resume Intake Specialist"),
        ("qualification_agent.py", "qualification_agent", "Qualification Analyst"),
        ("job_criteria_agent.py", "job_criteria_agent", "Job Criteria Analyst"),
        ("experience_assessment_agent.py", "experience_assessment_agent", "Experience Assessor"),
        ("screening_review_agent.py", "screening_review_agent", "Screening Reviewer"),
        ("recruiter_summary_agent.py", "recruiter_summary_agent", "Recruiter Summary Writer"),
    ]:
        (wf_dir / fname).write_text(
            f'AGENT_ID = "{aid}"\nROLE = "{role}"\nGOAL = "Execute {aid}."\nBACKSTORY = "Structured agent."\n',
            encoding="utf-8",
        )

    wf_data = data_dir / "study_wf"
    wf_data.mkdir(parents=True, exist_ok=True)
    (wf_data / "resumes.json").write_text(
        json.dumps([{"application_id": "APP-001", "candidate_id": "CAND-001", "candidate_name": "Dakota Chen", "target_job_id": "JOB-01"}]),
        encoding="utf-8",
    )
    (wf_data / "jobs.json").write_text(
        json.dumps([{"job_id": "JOB-01", "title": "Senior Cloud Engineer"}]),
        encoding="utf-8",
    )

    hist_dir.mkdir(parents=True, exist_ok=True)
    (hist_dir / "trace01.json").write_text(
        json.dumps({
            "run_id": "hist_study_01",
            "workflow_name": "study_wf",
            "status": "SUCCESS",
            "duration_seconds": 12.0,
            "prompt_tokens": 1200,
            "completion_tokens": 400,
            "total_tokens": 1600,
            "agent_executions": [
                {"agent_id": "resume_intake_agent", "duration_seconds": 2.0, "output": {"application_id": "APP-001", "candidate_id": "CAND-001", "candidate_name": "Dakota Chen", "contact_info_present": True, "sections_identified": ["skills"]}},
                {"agent_id": "qualification_agent", "duration_seconds": 2.0, "output": {"candidate_id": "CAND-001", "technical_skills": ["Python", "AWS"], "verbose_notes": "long redundant historical text"}},
                {"agent_id": "job_criteria_agent", "duration_seconds": 2.0, "output": {"job_id": "JOB-01", "mandatory_criteria": ["Python"]}},
                {"agent_id": "experience_assessment_agent", "duration_seconds": 2.0, "output": {"candidate_id": "CAND-001", "years_experience": 6}},
                {"agent_id": "screening_review_agent", "duration_seconds": 2.0, "output": {"candidate_id": "CAND-001", "review_decision": "advance"}},
                {"agent_id": "recruiter_summary_agent", "duration_seconds": 2.0, "output": {"run_id": "hist_study_01", "candidate_id": "CAND-001", "summary": "Qualified candidate"}},
            ],
        }),
        encoding="utf-8",
    )

    # All 5 non-conflicting approved candidates
    candidates = [
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
        {
            "candidate_id": "PAR-QUAL-JOB",
            "dimension": "workflow_parallelization",
            "target_agents": ["qualification_agent", "job_criteria_agent"],
        },
        {
            "candidate_id": "PROMPT-EXP",
            "dimension": "prompt_optimization",
            "target_agents": ["experience_assessment_agent"],
            "optimized_prompt": "Assess candidate experience concisely as valid JSON.",
        },
        {
            "candidate_id": "CONS-REVIEW-SUMMARY",
            "dimension": "agent_consolidation",
            "target_agents": ["screening_review_agent", "recruiter_summary_agent"],
            "unified_prompt": "Perform screening review and recruiter summary in one JSON output.",
        },
        {
            "candidate_id": "MODEL-INTAKE",
            "dimension": "model_selection",
            "target_agents": ["resume_intake_agent"],
            "selected_model": "llama-3.1-8b-instant",
        },
    ]
    scope = {
        "workflow_id": "study_wf",
        "approval_status": "approved",
        "approved_candidate_ids": [c["candidate_id"] for c in candidates],
        "approved_candidates": candidates,
    }
    return agents_dir, exp_dir, data_dir, hist_dir, wf_dir, scope


def _make_study_mock_subproc(
    calls_log: List[Dict[str, Any]],
    *,
    parallel_latency_gain: bool = True,
    omit_contexts: bool = False,
):
    def _mock_subproc(cmd, **kwargs):
        req_path = Path(cmd[cmd.index("--request-file") + 1])
        resp_path = Path(cmd[cmd.index("--response-file") + 1])
        req = json.loads(req_path.read_text(encoding="utf-8"))
        assert req["variant"] == "optimized"
        assert req["enable_trace_replay_fallback"] is False

        wf_dir = Path(req["workflow_directory"])
        wf_data = json.loads((wf_dir / "workflow.json").read_text(encoding="utf-8"))
        sb_cfg = json.loads((wf_dir / "sandbox_optimization_config.json").read_text(encoding="utf-8"))
        has_handoff = bool(wf_data.get("handoff_projections"))
        has_par = bool(wf_data.get("parallel_groups"))
        has_prompt = bool(sb_cfg.get("prompt_overrides"))
        has_cons = bool(sb_cfg.get("consolidations"))
        has_model = bool(wf_data.get("agent_model_overrides"))

        calls_log.append({
            "experiment_id": req["experiment_id"],
            "has_handoff": has_handoff,
            "has_par": has_par,
            "has_prompt": has_prompt,
            "has_cons": has_cons,
            "has_model": has_model,
        })

        # Distinct realistic trade-off surface so Pareto selection has real work to do
        dur = 12.0
        if has_handoff:
            dur -= 0.5
        if has_par and parallel_latency_gain:
            dur -= 2.5
        if has_prompt:
            dur -= 0.4
        if has_cons:
            dur -= 1.2
        if has_model:
            dur -= 2.8  # lowest latency & cost

        pt = 1200
        ct = 400
        if has_handoff:
            pt -= 220
        if has_prompt:
            pt -= 350  # lowest token total on prompt_optimization
        if has_cons:
            pt -= 180
            ct -= 90
        cost = round((pt / 1_000_000.0) * 0.15 + (ct / 1_000_000.0) * 0.60, 6)
        if has_model:
            cost = round(cost * 0.65, 6)

        intake_model = (
            (wf_data.get("agent_model_overrides") or {}).get("resume_intake_agent", {}).get("updated_model")
            or "openai/gpt-oss-120b"
        )
        traces_dir = Path(req["trace_directory"])
        traces_dir.mkdir(parents=True, exist_ok=True)
        traces = []
        trace_files = []

        valid_outputs = {
            "resume_intake_agent": {"application_id": "APP-001", "candidate_id": "CAND-001", "candidate_name": "Dakota Chen", "contact_info_present": True, "sections_identified": ["skills"]},
            "qualification_agent": {"candidate_id": "CAND-001", "technical_skills": [], "education": [], "certifications": [], "experience_records": [], "projects": [], "extraction_warnings": []},
            "job_criteria_agent": {"job_id": "JOB-01", "role_title": "Senior Cloud Engineer", "mandatory_requirements": [], "preferred_requirements": [], "scoring_rubric_notes": [], "ambiguities_flagged": []},
            "experience_assessment_agent": {"candidate_id": "CAND-001", "relevant_experience_summary": "6 years", "total_relevant_years_estimate": 6.0, "seniority_alignment": "strong", "domain_progression": [], "career_gaps_or_anomalies": [], "risk_flags": []},
            "screening_review_agent": {"candidate_id": "CAND-001", "overall_fit": "strong", "key_strengths": [], "key_gaps": [], "risk_factors": [], "recommended_decision": "advance", "justification": "Strong fit"},
            "recruiter_summary_agent": {"run_id": "opt_0", "candidate_id": "CAND-001", "job_id": "JOB-01", "deterministic_match_score": 100.0, "score_calculation_method": "weighted", "score_limitations": "resume only", "human_review_required": True, "non_autonomous_decision_statement": "assistive", "recommendation_summary": "Advance", "identified_inconsistencies": [], "recommended_follow_up_questions": [], "evidence_citations": []},
        }

        for idx, run_idx in enumerate(req.get("run_indices") or [0]):
            ag_execs = []
            for ag in wf_data.get("agents") or []:
                aid = ag["agent_id"]
                c_from = ag.get("consolidated_from") or []
                out_obj = valid_outputs.get(aid) or valid_outputs["recruiter_summary_agent"]
                ctx_list = [] if omit_contexts else [f"[workflow_input.resume] CAND-001", f"[upstream_for] {aid}"]
                ag_execs.append({
                    "order": len(ag_execs) + 1,
                    "agent_id": aid,
                    "consolidated_from": c_from,
                    "model": intake_model if aid == "resume_intake_agent" else "openai/gpt-oss-120b",
                    "duration_seconds": round(dur / max(1, len(wf_data.get("agents") or [])), 4),
                    "status": "SUCCESS",
                    "tokens": (pt + ct) // max(1, len(wf_data.get("agents") or [])),
                    "prompt_tokens": pt // max(1, len(wf_data.get("agents") or [])),
                    "completion_tokens": ct // max(1, len(wf_data.get("agents") or [])),
                    "estimated_cost_usd": round(cost / max(1, len(wf_data.get("agents") or [])), 6),
                    "usage_source": "api_reported",
                    "schema_valid": True,
                    "supplied_contexts": ctx_list,
                    "agent_task_input": f"Execute {aid} for CAND-001",
                    "output": out_obj,
                    "mode": "live_llm_execution",
                })
            audits = []
            if has_handoff:
                audits.append({
                    "edge": "qualification_agent->experience_assessment_agent",
                    "projected": True,
                    "original_fields": ["candidate_id", "technical_skills", "verbose_notes"],
                    "retained_fields": ["candidate_id", "technical_skills"],
                    "removed_fields": ["verbose_notes"],
                    "original_payload": {"candidate_id": "CAND-001", "technical_skills": ["Python"], "verbose_notes": "long"},
                    "projected_payload": {"candidate_id": "CAND-001", "technical_skills": ["Python"]},
                })
            t_obj = {
                "run_id": f"opt_{req['experiment_id']}_{run_idx}",
                "run_index": run_idx,
                "variant": "optimized",
                "workflow_name": req["workflow_id"],
                "experiment_id": req["experiment_id"],
                "status": "SUCCESS",
                "execution_mode": "live_llm_execution",
                "usage_sources": ["api_reported"],
                "duration_seconds": dur,
                "concurrent_waves": [["qualification_agent", "job_criteria_agent"]] if has_par else [],
                "handoff_audits": audits,
                "agent_executions": ag_execs,
                "total_tokens": pt + ct,
                "prompt_tokens": pt,
                "completion_tokens": ct,
                "estimated_cost_usd": cost,
            }
            tf = traces_dir / f"opt_{idx}.json"
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
            "groq_api_calls": len(traces) * len(traces[0]["agent_executions"]),
            "agent_execution_results": {
                "variant": "optimized",
                "source": "current_experiment",
                "re_executed": True,
                "groq_api_calls": len(traces) * len(traces[0]["agent_executions"]),
                "execution_passed": True,
                "execution_modes": ["live_llm_execution"],
                "usage_sources": ["api_reported"],
                "runs_executed": len(traces),
                "successful_runs": len(traces),
                "failed_runs": 0,
                "incomplete_runs": [],
                "concurrent_waves_executed": [["qualification_agent", "job_criteria_agent"]] if has_par else [],
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
            "execution_duration": 0.2,
            "python_executable": sys.executable,
            "sys_path_head": req["workflow_directory"],
            "error_details": None,
        }
        resp_path.write_text(json.dumps(payload), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout=f"{WORKER_STDOUT_PREFIX}{{}}\n", stderr="")

    return _mock_subproc


def _make_mock_ragas_runner(score_overrides_by_agent: Dict[str, Dict[str, float]] = None, seen_samples_out: List[Dict[str, Any]] = None):
    overrides = score_overrides_by_agent or {}

    def _runner(samples: List[Dict[str, Any]], requested_metrics: List[str]) -> Dict[str, Any]:
        if seen_samples_out is not None:
            seen_samples_out.extend(samples)
        per_sample = []
        for s in samples:
            assert s["retrieved_contexts"], "RAGAS runner must only receive samples with real supplied contexts"
            assert s["reference"] != s["retrieved_contexts"][0], "reference must never be substituted for retrieved_contexts"
            ov = overrides.get(s["agent_id"]) or {}
            per_sample.append({
                "sample_id": s["sample_id"],
                "agent_id": s["agent_id"],
                "faithfulness": ov.get("faithfulness", 0.90),
                "context_precision": ov.get("context_precision", 0.88),
                "context_recall": ov.get("context_recall", 0.87),
            })
        return {
            "per_sample_scores": per_sample,
            "evaluation_model_usage": {
                "model": "openai/gpt-oss-120b",
                "api_calls": len(samples),
                "prompt_tokens": 500 * len(samples),
                "completion_tokens": 120 * len(samples),
                "total_tokens": 620 * len(samples),
                "estimated_cost_usd": round(0.0005 * len(samples), 6),
            },
        }

    return _runner


_PASSING_CRITERIA = QualityAcceptanceCriteria(
    min_faithfulness=0.80,
    min_context_precision=0.75,
    min_context_recall=0.75,
    max_regression_vs_foundation=0.05,
)


def test_01_to_10_and_12_to_14_and_17_to_19_full_two_phase_and_combined_study(tmp_path: Path):
    """Covers Requirements 1-10, 12-14, 17-19 across all 5 dimensions, RAGAS mapping, Phase A/B/C & integrity."""
    agents_dir, exp_dir, data_dir, hist_dir, orig_wf_dir, scope = _build_full_5dim_fixture(tmp_path)
    pre_hashes = compute_directory_hashes(orig_wf_dir)
    calls_log: List[Dict[str, Any]] = []
    seen_ragas_samples: List[Dict[str, Any]] = []

    runner = SandboxExperimentRunner(
        agents_base_dir=agents_dir,
        experiments_base_dir=exp_dir,
        data_base_dir=data_dir,
        baseline_traces_dir=hist_dir,
        execution_backend="local_subprocess",
        enable_trace_replay_fallback=False,
        per_run_subprocess=False,
        subprocess_runner=_make_study_mock_subproc(calls_log),
        judge_callable=lambda **_k: {"correctness": "passed", "completeness": "passed", "consistency": "passed", "instruction_adherence": "passed", "semantic_quality": "passed", "identified_issues": [], "rationale": "ok"},
    )
    study = runner.run_two_phase_optimization_study(
        scope,
        study_id="study_full_5dim",
        quality_criteria=_PASSING_CRITERIA,
        ragas_runner=_make_mock_ragas_runner(seen_samples_out=seen_ragas_samples),
        num_runs=2,
    )

    # Req 17 & 18 & 19: Historical baseline never re-executed, original unchanged
    assert study["baseline_runtime_results"]["re_executed"] is False
    assert study["baseline_runtime_results"]["groq_api_calls"] == 0
    assert study["original_integrity_after"]["original_unchanged"] is True
    assert compute_directory_hashes(orig_wf_dir) == pre_hashes

    # Req 1 & 2: Data Handoff token evaluation & RAGAS
    hnd_ev = study["phase_a_foundation"]["dimension_evaluations"]["communication_data_handoff"]
    assert hnd_ev["primary_objective"] == "token_reduction"
    assert hnd_ev["token_improvement_pct"] > 0
    assert hnd_ev["supporting_metrics"]["handoff_evidence"]["modified_edges"][0]["removed_fields"] == ["verbose_notes"]
    assert hnd_ev["ragas"]["faithfulness"] == 0.9

    # Req 3 & 4: Parallelization latency evaluation (mean/median) & RAGAS
    par_ev = study["phase_a_foundation"]["dimension_evaluations"]["workflow_parallelization"]
    assert par_ev["primary_objective"] == "latency_reduction"
    assert par_ev["latency_improvement_pct"] > 0
    assert "median_workflow_latency_seconds" in par_ev["supporting_metrics"]
    assert par_ev["ragas"]["context_precision"] == 0.88

    # Req 12 & 13: Fixed foundation accepted & enforced without Phase B variable leakage
    assert study["fixed_optimization_foundation"] == ["communication_data_handoff", "workflow_parallelization"]
    phase_b_calls = {c["experiment_id"]: c for c in calls_log if "__phase_b_" in c["experiment_id"]}
    assert len(phase_b_calls) == 3

    for eid, flags in phase_b_calls.items():
        assert flags["has_handoff"] is True and flags["has_par"] is True
    assert phase_b_calls["study_full_5dim__phase_b_prompt_optimization"]["has_prompt"] is True
    assert phase_b_calls["study_full_5dim__phase_b_prompt_optimization"]["has_cons"] is False
    assert phase_b_calls["study_full_5dim__phase_b_prompt_optimization"]["has_model"] is False
    assert phase_b_calls["study_full_5dim__phase_b_agent_consolidation"]["has_cons"] is True
    assert phase_b_calls["study_full_5dim__phase_b_agent_consolidation"]["has_prompt"] is False
    assert phase_b_calls["study_full_5dim__phase_b_agent_consolidation"]["has_model"] is False
    assert phase_b_calls["study_full_5dim__phase_b_model_selection"]["has_model"] is True
    assert phase_b_calls["study_full_5dim__phase_b_model_selection"]["has_prompt"] is False
    assert phase_b_calls["study_full_5dim__phase_b_model_selection"]["has_cons"] is False

    # Req 5, 6, 7, 8: Phase B variable dimension metrics & RAGAS
    prm_ev = study["phase_b_variable_dimensions"]["dimension_evaluations"]["prompt_optimization"]
    assert len(prm_ev["supporting_metrics"]["prompt_changes"]) == 1
    assert prm_ev["ragas"]["context_recall"] == 0.87

    cons_ev = study["phase_b_variable_dimensions"]["dimension_evaluations"]["agent_consolidation"]
    assert set(["mean_workflow_latency_seconds", "input_tokens", "total_tokens", "estimated_cost_usd"]).issubset(cons_ev["primary_metrics"].keys())
    assert cons_ev["ragas"]["faithfulness"] == 0.9

    mod_ev = study["phase_b_variable_dimensions"]["dimension_evaluations"]["model_selection"]
    assert mod_ev["supporting_metrics"]["model_verification"]["all_overrides_used_at_runtime"] is True
    assert mod_ev["ragas"]["faithfulness"] == 0.9

    # Req 14: Combined includes all 5 dimensions
    comb = study["phase_c_combined"]
    assert comb["applied_dimensions"] == [
        "communication_data_handoff",
        "workflow_parallelization",
        "prompt_optimization",
        "agent_consolidation",
        "model_selection",
    ]
    assert study["ragas_evaluation_model_usage"]["isolated_from_workflow_metrics"] is True
    assert study["ragas_evaluation_model_usage"]["api_calls"] > 0

    # Req 9 & 10: Reference & context mapping verified cleanly
    assert seen_ragas_samples and all(s["reference"] and s["retrieved_contexts"] for s in seen_ragas_samples)

    # 7-section Study JSON & Markdown Reports generated
    md_text = Path(study["markdown_report_path"]).read_text(encoding="utf-8")
    for sec in (
        "## 1. Experimental Setup",
        "## 2. Fixed Foundation Evaluation",
        "## 3. Individual Variable-Dimension Evaluation",
        "## 4. Combined Optimization",
        "## 5. Comparative Metrics",
        "## 6. Best Configuration Selection",
        "## 7. Limitations and Final Assessment",
    ):
        assert sec in md_text


def test_11_missing_contexts_and_missing_ragas_mark_unavailable_and_inconclusive():
    """Req 11: Missing contexts (or uninstalled ragas package) mark RAGAS unavailable & inconclusive."""
    base_rt = {
        "traces": [{
            "run_id": "base_0",
            "input_hash": "h0",
            "agent_executions": [{"agent_id": "resume_intake_agent", "output": {"candidate_id": "C1"}}],
        }]
    }
    opt_no_ctx = {
        "traces": [{
            "run_id": "opt_0",
            "input_hash": "h0",
            "agent_executions": [{"agent_id": "resume_intake_agent", "supplied_contexts": [], "output": {"candidate_id": "C1"}}],
        }]
    }
    sample_info = build_ragas_samples(base_rt, opt_no_ctx)
    assert sample_info["samples"][0]["has_contexts"] is False
    assert sample_info["samples"][0]["reference"] == '{"candidate_id": "C1"}'

    called = {"n": 0}
    rag_missing_ctx = evaluate_with_ragas(
        base_rt,
        opt_no_ctx,
        ragas_runner=lambda *_a: called.__setitem__("n", called["n"] + 1) or {},
    )
    assert called["n"] == 0
    assert rag_missing_ctx["faithfulness"] == "unavailable"
    assert rag_missing_ctx["context_precision"] == "unavailable"
    assert rag_missing_ctx["context_recall"] == "unavailable"

    # Quality acceptance with unavailable metrics MUST be inconclusive
    acc = evaluate_quality_acceptance(
        rag_missing_ctx,
        _PASSING_CRITERIA,
        execution_passed=True,
        validation_passed=True,
        schema_valid=True,
    )
    assert acc["quality_accepted"] is False
    assert acc["status"] == "inconclusive"

    # Without custom runner in an environment missing `ragas`, reports missing integration requirement honestly
    opt_with_ctx = {
        "traces": [{
            "run_id": "opt_0",
            "input_hash": "h0",
            "agent_executions": [{"agent_id": "resume_intake_agent", "supplied_contexts": ["resume text"], "output": {"candidate_id": "C1"}}],
        }]
    }
    rag_no_pkg = evaluate_with_ragas(base_rt, opt_with_ctx, ragas_runner=None)
    if not rag_no_pkg["ragas_available"]:
        assert rag_no_pkg["status"] == "unavailable"
        assert rag_no_pkg["missing_integration_requirements"]


def test_12b_and_15_failed_quality_gate_prevents_foundation_and_variable_acceptance(tmp_path: Path):
    """Req 12 & 15: Failed Phase A gate refuses forcing dimension into foundation; low RAGAS rejects cheap/fast model."""
    agents_dir, exp_dir, data_dir, hist_dir, _, scope = _build_full_5dim_fixture(tmp_path)
    calls_log: List[Dict[str, Any]] = []

    runner = SandboxExperimentRunner(
        agents_base_dir=agents_dir,
        experiments_base_dir=exp_dir,
        data_base_dir=data_dir,
        baseline_traces_dir=hist_dir,
        execution_backend="local_subprocess",
        enable_trace_replay_fallback=False,
        per_run_subprocess=False,
        subprocess_runner=_make_study_mock_subproc(calls_log),
    )
    # Fail quality specifically on qualification_agent / resume_intake_agent (low faithfulness=0.45)
    strict_ragas = _make_mock_ragas_runner(
        score_overrides_by_agent={
            "resume_intake_agent": {"faithfulness": 0.45, "context_precision": 0.90, "context_recall": 0.90},
            "job_criteria_agent": {"faithfulness": 0.50, "context_precision": 0.90, "context_recall": 0.90},
        }
    )
    study = runner.run_two_phase_optimization_study(
        scope,
        study_id="study_gate_reject",
        quality_criteria=_PASSING_CRITERIA,
        ragas_runner=strict_ragas,
        selected_variable_dimensions=["prompt_optimization", "model_selection"],
        num_runs=1,
    )

    # Parallelization failed quality gate -> MUST NOT be forced into fixed_optimization_foundation
    assert "workflow_parallelization" not in study["fixed_optimization_foundation"]
    assert study["phase_a_foundation"]["dimension_evaluations"]["workflow_parallelization"]["accepted"] is False

    # Model selection had low faithfulness (0.45 < 0.80) despite big latency & cost gain -> rejected & excluded from Pareto!
    mod_ev = study["phase_b_variable_dimensions"]["dimension_evaluations"]["model_selection"]
    assert mod_ev["accepted"] is False
    excluded_names = [e["name"] for e in study["pareto_selection"]["excluded_configurations"]]
    assert any("model_selection" in n for n in excluded_names)


def test_16_and_20_pareto_selection_multiple_alternatives_and_agent_entrypoint(tmp_path: Path):
    """Req 16 & 20: Pareto frontier excludes quality-ineligible configs and returns multiple alternatives cleanly."""
    configs = [
        {
            "name": "cfg_best_latency_and_cost",
            "scope_kind": "variable_on_foundation",
            "validation_passed": True,
            "execution_passed": True,
            "quality_accepted": True,
            "quality_status": "accepted",
            "mean_latency_seconds": 5.5,
            "mean_tokens": 1100,
            "mean_cost_usd": 0.00030,
        },
        {
            "name": "cfg_best_tokens",
            "scope_kind": "variable_on_foundation",
            "validation_passed": True,
            "execution_passed": True,
            "quality_accepted": True,
            "quality_status": "accepted",
            "mean_latency_seconds": 7.5,
            "mean_tokens": 780,
            "mean_cost_usd": 0.00038,
        },
        {
            "name": "cfg_dominated",
            "scope_kind": "variable_on_foundation",
            "validation_passed": True,
            "execution_passed": True,
            "quality_accepted": True,
            "quality_status": "accepted",
            "mean_latency_seconds": 8.0,
            "mean_tokens": 1200,
            "mean_cost_usd": 0.00050,
        },
        {
            "name": "cfg_cheap_but_quality_failed",
            "scope_kind": "variable_on_foundation",
            "validation_passed": True,
            "execution_passed": True,
            "quality_accepted": False,
            "quality_status": "rejected",
            "mean_latency_seconds": 2.0,
            "mean_tokens": 300,
            "mean_cost_usd": 0.00010,
        },
    ]
    sel = select_best_workflows_pareto(configs)
    assert sel["weighted_scoring_used"] is False
    assert [e["name"] for e in sel["excluded_configurations"]] == ["cfg_cheap_but_quality_failed"]
    assert [p["name"] for p in sel["pareto_efficient_configurations"]] == [
        "cfg_best_latency_and_cost",
        "cfg_best_tokens",
    ]
    assert sel["best_latency_configuration"]["name"] == "cfg_best_latency_and_cost"
    assert sel["best_cost_efficiency_configuration"]["name"] == "cfg_best_latency_and_cost"
    assert sel["best_token_efficiency_configuration"]["name"] == "cfg_best_tokens"
    assert sel["recommended_overall_configuration"] is None  # Multiple Pareto alternatives reported cleanly

    agent = OptimizationDiscoveryAgent()
    assert hasattr(agent, "run_sandbox_optimization_study")
