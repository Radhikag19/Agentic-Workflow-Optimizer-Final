"""
Integration & Unit Tests for the 3-Layer Behavioral Equivalence Evaluation Architecture:
  - Layer 1: Deterministic Structural & Decision Match (Key F1, Booleans/Enums, Numeric Tolerance)
  - Layer 2: Offline Semantic Cosine Similarity on Narrative Prose
  - Layer 3: Optional 1-Call Pairwise LLM Judge (isolated token accounting)
  - Two-Phase Pareto Study + Report Generation under `evaluation_mode="equivalence"`
"""

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from types import SimpleNamespace

from optimization_agent.sandbox.evaluation.equivalence_evaluator import (
    EquivalenceAcceptanceCriteria,
    compute_semantic_cosine_similarity,
    compute_structural_decision_equivalence,
    evaluate_behavioral_equivalence,
    evaluate_equivalence_acceptance,
)
from optimization_agent.sandbox.experiment import SandboxExperimentRunner
from optimization_agent.sandbox.runtime.worker import WORKER_STDOUT_PREFIX


def _make_demo_recruitment_trace(run_id: str, overview: str, human_review: bool, status: str, match_score: float):
    final_payload = {
        "candidate_id": "CAND-001",
        "executive_candidate_overview": overview,
        "criteria_matrix": [{"criterion_id": "M1", "status": status, "requirement_type": "mandatory"}],
        "deterministic_match_score": match_score,
        "human_review_required": human_review,
    }
    return {
        "run_id": run_id,
        "input_hash": "hash_cand_001",
        "status": "SUCCESS",
        "duration_seconds": 12.0,
        "total_tokens": 1800,
        "prompt_tokens": 1100,
        "completion_tokens": 700,
        "estimated_cost_usd": 0.002,
        "final_output": final_payload,
        "agent_executions": [
            {
                "agent_id": "recruiter_summary_agent",
                "duration_seconds": 12.0,
                "tokens": 1800,
                "prompt_tokens": 1100,
                "completion_tokens": 700,
                "output": final_payload,
            }
        ],
    }


def test_01_layer1_catches_decision_flip_despite_high_layer2_cosine():
    base_out = _make_demo_recruitment_trace(
        "base_1",
        "Candidate has 9 years of frontend HTML CSS WordPress experience and lacks AWS Kubernetes backend skills.",
        True,
        "unsupported",
        15.0,
    )["final_output"]
    flipped_out = _make_demo_recruitment_trace(
        "opt_1",
        "Candidate has 9 years of frontend HTML CSS WordPress experience and lacks AWS Kubernetes backend skills.",
        False,
        "supported",
        85.0,
    )["final_output"]

    l1 = compute_structural_decision_equivalence(base_out, flipped_out)
    l2 = compute_semantic_cosine_similarity(base_out, flipped_out)

    # Prose is almost identical so cosine is high, MUST be caught by Layer 1 decision flips!
    assert l2["cosine_similarity"] is not None and l2["cosine_similarity"] > 0.85
    assert l1["decision_flip_count"] == 2
    assert any(m["field"] == "human_review_required" and m["is_boolean_flip"] for m in l1["decision_mismatches"])

    eq_res = evaluate_behavioral_equivalence(
        baseline_runtime_results={"traces": [_make_demo_recruitment_trace("base_1", base_out["executive_candidate_overview"], True, "unsupported", 15.0)]},
        optimized_runtime_results={"traces": [_make_demo_recruitment_trace("opt_1", flipped_out["executive_candidate_overview"], False, "supported", 85.0)]},
        enable_llm_judge=False,
    )
    gate = evaluate_equivalence_acceptance(
        eq_res,
        EquivalenceAcceptanceCriteria(min_structural_decision_score=0.75, min_semantic_cosine=0.75, max_decision_flips=0),
        execution_passed=True,
        validation_passed=True,
        schema_valid=True,
    )
    assert eq_res["evaluation_model_usage"]["api_calls"] == 0
    assert gate["quality_accepted"] is False
    assert gate["status"] == "rejected"


def test_02_paraphrased_equivalent_output_passes_with_zero_api_calls():
    base_trace = _make_demo_recruitment_trace(
        "base_1",
        "Dakota Chen holds a BS in Computer Science and 9 years building frontend web apps with HTML CSS and WordPress, lacking AWS cloud and Go backend experience.",
        True,
        "unsupported",
        15.2,
    )
    opt_trace = _make_demo_recruitment_trace(
        "opt_1",
        "Dakota Chen earned a Computer Science BS and has 9 years developing web frontend applications in HTML, CSS, and WordPress; AWS cloud and Go backend skills are missing.",
        True,
        "unsupported",
        15.0,
    )

    eq_res = evaluate_behavioral_equivalence(
        baseline_runtime_results={"traces": [base_trace]},
        optimized_runtime_results={"traces": [opt_trace]},
        enable_llm_judge=False,
    )
    gate = evaluate_equivalence_acceptance(
        eq_res,
        EquivalenceAcceptanceCriteria(min_structural_decision_score=0.80, min_semantic_cosine=0.75, max_decision_flips=0),
        execution_passed=True,
        validation_passed=True,
        schema_valid=True,
    )
    assert eq_res["structural_decision_score"] == 1.0
    assert eq_res["semantic_cosine_similarity"] >= 0.70
    assert eq_res["decision_flip_count"] == 0
    assert eq_res["evaluation_model_usage"]["api_calls"] == 0
    assert gate["quality_accepted"] is True
    assert gate["status"] == "accepted"


def _build_local_study_fixture(tmp_path: Path):
    """Self-contained minimal 3-agent MAS workflow + historical trace + approved scope fixture."""
    agents_dir = tmp_path / "Agents"
    wf_dir = agents_dir / "eq_demo_wf"
    wf_dir.mkdir(parents=True)
    exp_dir = tmp_path / "experiments"
    exp_dir.mkdir(parents=True)
    data_dir = tmp_path / "data"
    wf_data_dir = data_dir / "eq_demo_wf"
    wf_data_dir.mkdir(parents=True, exist_ok=True)
    trace_dir = tmp_path / "traces"
    trace_dir.mkdir(parents=True)

    (wf_dir / "a1.py").write_text(
        'AGENT_ID = "a1"\nROLE = "Extractor"\nGOAL = "Extract skills"\nBACKSTORY = "Exact"\n',
        encoding="utf-8",
    )
    (wf_dir / "a2.py").write_text(
        'AGENT_ID = "a2"\nROLE = "Criteria"\nGOAL = "Parse criteria"\nBACKSTORY = "Exact"\n',
        encoding="utf-8",
    )
    (wf_dir / "a3.py").write_text(
        'AGENT_ID = "a3"\nROLE = "Summary"\nGOAL = "Summarize"\nBACKSTORY = "Exact"\n',
        encoding="utf-8",
    )
    (wf_dir / "workflow.py").write_text(
        'def run_workflow(input_data=None):\n    return {"ok": True}\n',
        encoding="utf-8",
    )
    (wf_dir / "workflow.json").write_text(
        json.dumps({
            "workflow_name": "eq_demo_wf",
            "baseline_model": "openai/gpt-oss-120b",
            "execution_order": ["a1", "a2", "a3"],
            "agents": [
                {"agent_id": "a1", "role": "Extractor", "dependencies": [], "input_fields": ["resume"], "output_fields": ["skills", "extra"]},
                {"agent_id": "a2", "role": "Criteria", "dependencies": [], "input_fields": ["job"], "output_fields": ["criteria"]},
                {"agent_id": "a3", "role": "Summary", "dependencies": ["a1", "a2"], "input_fields": ["skills", "criteria"], "output_fields": ["summary", "approved"]},
            ],
        }),
        encoding="utf-8",
    )

    from optimization_agent.sandbox.evaluation.baseline_loader import compute_canonical_input_hash

    sample_input = {"candidate_id": "CAND-1", "resume": {"candidate_id": "CAND-1", "skills": ["python", "aws"]}, "job": {"criteria": ["python"]}}
    (wf_data_dir / "inputs.json").write_text(json.dumps([sample_input]), encoding="utf-8")
    in_hash = compute_canonical_input_hash(sample_input)
    base_a1 = {"candidate_id": "CAND-1", "skills": ["python", "aws"], "status": "verified"}
    base_a2 = {"criteria": ["python"], "status": "ready"}
    base_a3 = {"summary": "Candidate qualified with Python and AWS cloud skills.", "approved": True}
    (trace_dir / "hist_01.json").write_text(
        json.dumps({
            "run_id": "hist_01",
            "workflow_name": "eq_demo_wf",
            "status": "SUCCESS",
            "duration_seconds": 2.0,
            "total_tokens": 900,
            "prompt_tokens": 450,
            "completion_tokens": 450,
            "estimated_cost_usd": 0.0009,
            "input_hash": in_hash,
            "input_snapshot": sample_input,
            "final_output": base_a3,
            "agent_executions": [
                {"agent_id": "a1", "duration_seconds": 0.8, "tokens": 450, "prompt_tokens": 250, "completion_tokens": 200, "model": "openai/gpt-oss-120b", "output": base_a1},
                {"agent_id": "a2", "duration_seconds": 0.6, "tokens": 225, "prompt_tokens": 100, "completion_tokens": 125, "model": "openai/gpt-oss-120b", "output": base_a2},
                {"agent_id": "a3", "duration_seconds": 0.6, "tokens": 225, "prompt_tokens": 100, "completion_tokens": 125, "model": "openai/gpt-oss-120b", "output": base_a3},
            ],
        }),
        encoding="utf-8",
    )

    scope = {
        "workflow_id": "eq_demo_wf",
        "approval_status": "approved",
        "approved_candidate_ids": ["H1", "P1", "M1"],
        "approved_candidates": [
            {
                "candidate_id": "H1",
                "dimension": "communication_data_handoff",
                "target_agents": ["a1", "a3"],
                "proposed_compact_payload_schema": {
                    "retained_fields": ["candidate_id", "skills"],
                    "excluded_fields": ["extra"],
                },
                "supporting_evidence": {
                    "producer_agent": "a1",
                    "consumer_agent": "a3",
                    "fields_retained": ["candidate_id", "skills"],
                    "fields_excluded": ["extra"],
                    "consumer_required_fields": ["skills"],
                },
            },
            {
                "candidate_id": "P1",
                "dimension": "workflow_parallelization",
                "target_agents": ["a1", "a2"],
            },
            {
                "candidate_id": "M1",
                "dimension": "model_selection",
                "target_agents": ["a1"],
                "selected_model": "openai/gpt-oss-20b",
                "recommended_model": "openai/gpt-oss-20b",
                "supporting_evidence": {
                    "current_model": "openai/gpt-oss-120b",
                    "proposed_candidate_models": [{"model": "openai/gpt-oss-20b"}],
                },
            },
        ],
    }
    return agents_dir, exp_dir, data_dir, trace_dir, scope, sample_input, in_hash


def test_03_optional_layer3_judge_and_two_phase_pareto_study(tmp_path: Path):
    agents_dir, exp_dir, data_dir, trace_dir, scope, _sample_input, in_hash = _build_local_study_fixture(tmp_path)

    def _mock_subproc(cmd, **_kwargs):
        req_path = Path(cmd[cmd.index("--request-file") + 1])
        resp_path = Path(cmd[cmd.index("--response-file") + 1])
        req = json.loads(req_path.read_text(encoding="utf-8"))
        wf_dir = Path(req["workflow_directory"])
        wf_data = json.loads((wf_dir / "workflow.json").read_text(encoding="utf-8"))

        has_handoff = bool(wf_data.get("handoff_projections"))
        has_par = bool(wf_data.get("parallel_groups"))
        has_model = bool(wf_data.get("agent_model_overrides"))

        lat = 2.0 - (0.3 if has_handoff else 0.0) - (0.4 if has_par else 0.0) - (0.3 if has_model else 0.0)
        tok = 900 - (120 if has_handoff else 0) - (60 if has_model else 0)
        a1_model = (
            (wf_data.get("agent_model_overrides") or {}).get("a1", {}).get("updated_model")
            or "openai/gpt-oss-120b"
        )
        traces_dir = Path(req["trace_directory"])
        traces_dir.mkdir(parents=True, exist_ok=True)
        a_out = {"candidate_id": "CAND-1", "skills": ["python", "aws"], "status": "verified"}
        trace = {
            "run_id": f"{req['experiment_id']}_r0",
            "run_index": 0,
            "variant": "optimized",
            "workflow_name": req["workflow_id"],
            "experiment_id": req["experiment_id"],
            "status": "SUCCESS",
            "execution_mode": "live_llm_execution",
            "usage_sources": ["api_reported"],
            "input_hash": in_hash,
            "duration_seconds": round(lat, 3),
            "prompt_tokens": tok // 2,
            "completion_tokens": tok - (tok // 2),
            "total_tokens": tok,
            "estimated_cost_usd": round(tok * 0.000001, 6),
            "concurrent_waves": [["a1", "a2"]] if has_par else [],
            "handoff_audits": (
                [{"edge": "a1->a3", "projected": True, "original_fields": ["candidate_id", "skills", "extra"], "retained_fields": ["candidate_id", "skills"], "removed_fields": ["extra"]}]
                if has_handoff
                else []
            ),
            "agent_executions": [
                {"agent_id": "a1", "status": "SUCCESS", "mode": "live_llm_execution", "usage_source": "api_reported", "duration_seconds": lat * 0.4, "tokens": tok // 2, "prompt_tokens": tok // 4, "completion_tokens": tok // 4, "model": a1_model, "schema_valid": True, "output": a_out},
                {"agent_id": "a2", "status": "SUCCESS", "mode": "live_llm_execution", "usage_source": "api_reported", "duration_seconds": lat * 0.3, "tokens": tok // 4, "prompt_tokens": tok // 8, "completion_tokens": tok // 8, "model": "openai/gpt-oss-120b", "schema_valid": True, "output": {"criteria": ["python"], "status": "ready"}},
                {"agent_id": "a3", "status": "SUCCESS", "mode": "live_llm_execution", "usage_source": "api_reported", "duration_seconds": lat * 0.3, "tokens": tok // 4, "prompt_tokens": tok // 8, "completion_tokens": tok // 8, "model": "openai/gpt-oss-120b", "schema_valid": True, "output": {"summary": "Candidate qualified with Python and AWS cloud skills.", "approved": True}},
            ],
            "final_output": {"summary": "Candidate qualified with Python and AWS cloud skills.", "approved": True},
        }
        tf = traces_dir / "opt_0.json"
        tf.write_text(json.dumps(trace), encoding="utf-8")
        result_payload = {
            "experiment_id": req["experiment_id"],
            "workflow_id": req["workflow_id"],
            "variant": "optimized",
            "execution_mode": "live_llm_execution",
            "execution_status": "SUCCESS",
            "workflow_directory": req["workflow_directory"],
            "run_id": trace["run_id"],
            "run_ids": [trace["run_id"]],
            "groq_api_calls": 3,
            "agent_execution_results": {
                "variant": "optimized",
                "source": "current_experiment",
                "re_executed": True,
                "groq_api_calls": 3,
                "execution_passed": True,
                "execution_modes": ["live_llm_execution"],
                "usage_sources": ["api_reported"],
                "runs_executed": 1,
                "successful_runs": 1,
                "failed_runs": 0,
                "incomplete_runs": [],
                "concurrent_waves_executed": [["a1", "a2"]] if has_par else [],
                "trace_files": [str(tf)],
                "traces": [trace],
                "schema_validation_summary": {"all_schemas_valid": True, "failures": []},
                "invalid_replay_samples": [],
                "api_errors": [],
                "fallback_events": [],
                "errors": [],
            },
            "trace_directory": str(traces_dir),
            "api_errors": [],
            "execution_duration": round(lat, 3),
            "python_executable": sys.executable,
            "sys_path_head": req["workflow_directory"],
            "error_details": None,
        }
        resp_path.write_text(json.dumps(result_payload), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout=WORKER_STDOUT_PREFIX + json.dumps(result_payload), stderr="")

    runner = SandboxExperimentRunner(
        agents_base_dir=agents_dir,
        experiments_base_dir=exp_dir,
        data_base_dir=data_dir,
        baseline_traces_dir=trace_dir,
        execution_backend="local_subprocess",
        subprocess_runner=_mock_subproc,
        judge_callable=lambda **_kw: {"overall_equivalence": 0.94, "api_calls": 1, "total_tokens": 220, "rationale": "Semantically equivalent"},
    )
    study = runner.run_two_phase_optimization_study(
        scope,
        study_id="eq_pareto_test",
        evaluation_mode="equivalence",
        enable_equivalence_llm_judge=True,
        equivalence_criteria={
            "min_structural_decision_score": 0.75,
            "min_semantic_cosine": 0.70,
            "min_llm_judge_score": 0.75,
            "max_decision_flips": 0,
        },
        num_runs=1,
    )

    assert study["evaluation_mode"] == "equivalence"
    assert len(study["pareto_selection"]["pareto_efficient_configurations"]) >= 1
    assert study["pareto_selection"]["best_latency_configuration"] is not None
    assert Path(study["markdown_report_path"]).exists()
    md = study["study_markdown_report"]
    assert "Struct/Decision (L1)" in md
    assert "Semantic Cosine (L2)" in md
    assert study["ragas_evaluation_model_usage"]["api_calls"] > 0


def test_04_real_recruitment_screening_trace_scores():
    hist_p = ROOT_DIR.parent / "Ingestion_Traces_final" / "Ingestion_Traces" / "recruitment_screening" / "live_20261031_162602_trace01.json"
    opt_p = ROOT_DIR / "reports" / "experiments" / "recruitment_screening" / "live_validation_recruitment_screening" / "phase_c" / "combined" / "runtime_traces" / "sb_20261124_152216_01d01f.json"
    if not hist_p.exists() or not opt_p.exists():
        return

    base_trace = json.loads(hist_p.read_text(encoding="utf-8"))
    opt_trace = json.loads(opt_p.read_text(encoding="utf-8"))
    # Align single baseline trace to the optimized trace input_hash for direct before/after comparison
    base_trace["input_hash"] = opt_trace.get("input_hash") or "aligned_hash"

    eq_res = evaluate_behavioral_equivalence(
        baseline_runtime_results={"traces": [base_trace]},
        optimized_runtime_results={"traces": [opt_trace]},
        target_agents=["resume_intake_agent"],
        enable_llm_judge=False,
    )
    assert eq_res["status"] == "evaluated"
    assert eq_res["evaluation_model_usage"]["api_calls"] == 0
    assert eq_res["structural_decision_score"] >= 0.70
    assert eq_res["semantic_cosine_similarity"] >= 0.60
