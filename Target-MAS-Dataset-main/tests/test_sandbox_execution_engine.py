"""
Validation test suite for the Sandbox Optimization Execution Engine (Tests 1-14).
"""

import json
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

# Ensure package root is importable
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from optimization_agent.agent import OptimizationDiscoveryAgent
from optimization_agent.sandbox.candidate_router import (
    EXECUTOR_REGISTRY,
    CandidateExecutionRouter,
)
from optimization_agent.sandbox.evaluation.evaluator import evaluate_experiment
from optimization_agent.sandbox.executors import (
    AgentConsolidationExecutor,
    DataHandoffExecutor,
    ModelSelectionExecutor,
    ParallelizationExecutor,
    PromptOptimizationExecutor,
)
from optimization_agent.sandbox.experiment import SandboxExperimentRunner
from optimization_agent.sandbox.langgraph_nodes import (
    build_optimization_graph_with_sandbox_execution,
)
from optimization_agent.sandbox.manager import SandboxManager, compute_directory_hashes
from optimization_agent.sandbox.runtime.runner import SandboxWorkflowRunner
from optimization_agent.sandbox.validation.validator import validate_sandbox


def _make_sample_workflow(base_dir: Path, workflow_id: str = "sample_wf") -> Path:
    """Create a realistic isolated MAS workflow copy for deterministic unit testing."""
    wf_dir = base_dir / workflow_id
    wf_dir.mkdir(parents=True, exist_ok=True)

    workflow_json = {
        "workflow_id": workflow_id,
        "name": "Sample Recruitment Screening",
        "baseline_model": "openai/gpt-oss-120b",
        "llm_provider": "Groq",
        "assigned_groq_key_env": "GROQ_API_KEY_TEST",
        "agents": [
            {
                "agent_id": "resume_intake_agent",
                "role": "Resume Intake Specialist",
                "dependencies": [],
                "input_fields": ["candidate_id", "resume_text"],
                "output_fields": ["candidate_id", "raw_sections", "resume_summary", "metadata"],
            },
            {
                "agent_id": "qualification_agent",
                "role": "Qualification Analyst",
                "dependencies": ["resume_intake_agent"],
                "input_fields": ["candidate_id", "raw_sections"],
                "output_fields": ["matched_skills", "degrees", "certifications", "verbose_notes"],
            },
            {
                "agent_id": "job_criteria_agent",
                "role": "Job Criteria Analyst",
                "dependencies": ["resume_intake_agent"],
                "input_fields": ["job_id", "job_text"],
                "output_fields": ["required_skills", "preferred_skills"],
            },
            {
                "agent_id": "experience_assessment_agent",
                "role": "Experience Assessor",
                "dependencies": ["qualification_agent", "job_criteria_agent"],
                "input_fields": ["matched_skills", "required_skills"],
                "output_fields": ["years_experience", "domain_fit_score", "justification"],
            },
            {
                "agent_id": "screening_review_agent",
                "role": "Screening Reviewer",
                "dependencies": ["experience_assessment_agent"],
                "input_fields": ["years_experience", "domain_fit_score"],
                "output_fields": ["final_decision", "review_summary"],
            },
        ],
    }
    (wf_dir / "workflow.json").write_text(json.dumps(workflow_json, indent=2), encoding="utf-8")

    agents_py = {
        "intake_agent.py": (
            'AGENT_ID = "resume_intake_agent"\n'
            'ROLE = "Resume Intake Specialist"\n'
            'GOAL = "Parse candidate resume into structured sections."\n'
            'BACKSTORY = "Structured HR parser with verbose formatting instructions."\n'
        ),
        "qualification_agent.py": (
            'AGENT_ID = "qualification_agent"\n'
            'ROLE = "Qualification Analyst"\n'
            'GOAL = "Extract skills, degrees and certifications."\n'
            'BACKSTORY = "Evaluates technical and academic qualifications."\n'
        ),
        "job_criteria_agent.py": (
            'AGENT_ID = "job_criteria_agent"\n'
            'ROLE = "Job Criteria Analyst"\n'
            'GOAL = "Extract job criteria and requirements."\n'
            'BACKSTORY = "Parses job requisition details."\n'
        ),
        "experience_assessment_agent.py": (
            'AGENT_ID = "experience_assessment_agent"\n'
            'ROLE = "Experience Assessor"\n'
            'GOAL = "Assess candidate experience against criteria."\n'
            'BACKSTORY = "Experienced recruiter evaluating career progression."\n'
        ),
        "screening_review_agent.py": (
            'AGENT_ID = "screening_review_agent"\n'
            'ROLE = "Screening Reviewer"\n'
            'GOAL = "Produce final screening recommendation."\n'
            'BACKSTORY = "Senior hiring committee lead."\n'
        ),
    }
    for fname, body in agents_py.items():
        (wf_dir / fname).write_text(body, encoding="utf-8")

    return wf_dir


def _make_approved_scope(workflow_id: str, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "workflow_id": workflow_id,
        "approval_status": "approved",
        "approved_candidate_ids": [c["candidate_id"] for c in candidates],
        "approved_candidates": candidates,
        "approval_metadata": {"approved_by": "pytest", "status": "approved"},
    }


def _mock_llm_callable(
    agent_id: str,
    model_id: str,
    system_prompt: str,
    user_prompt: str,
    context: Dict[str, Any],
) -> Dict[str, Any]:
    outputs = {
        "resume_intake_agent": {
            "candidate_id": "cand_01",
            "raw_sections": {"experience": "5 years Python"},
            "resume_summary": "Strong Python engineer",
            "metadata": {"source": "pdf"},
        },
        "qualification_agent": {
            "matched_skills": ["Python", "SQL"],
            "degrees": ["B.S. CS"],
            "certifications": ["AWS"],
            "verbose_notes": "Very long narrative that downstream does not need...",
        },
        "job_criteria_agent": {
            "required_skills": ["Python"],
            "preferred_skills": ["LangGraph"],
        },
        "experience_assessment_agent": {
            "years_experience": 5,
            "domain_fit_score": 0.9,
            "justification": "Matches required Python and SQL stack.",
        },
        "screening_review_agent": {
            "final_decision": "advance",
            "review_summary": "Recommended for technical round.",
        },
        "consolidated_qualification_experience_assessment": {
            "years_experience": 5,
            "domain_fit_score": 0.9,
            "justification": "Combined qualification & experience output.",
        },
    }
    pt = max(50, len(system_prompt) // 4 + len(user_prompt) // 4)
    ct = 80
    return {
        "output": outputs.get(agent_id, {"status": "ok"}),
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "tokens": pt + ct,
        "assigned_key_identifier": "TEST_MOCK_CALLABLE",
        "mode": "test_mock_callable",
    }


# ---------------------------------------------------------------------------
# Test 1: Sandbox Isolation (custom workflow + real recruitment_screening)
# ---------------------------------------------------------------------------
def test_01_sandbox_isolation_preserves_original_hashes(tmp_path: Path):
    agents_dir = tmp_path / "agents"
    exp_dir = tmp_path / "experiments"
    orig_dir = _make_sample_workflow(agents_dir, "sample_wf")
    pre_hashes = compute_directory_hashes(orig_dir)

    scope = _make_approved_scope(
        "sample_wf",
        [
            {
                "candidate_id": "MODEL-RESUME_INTAKE_AGENT",
                "dimension": "model_selection",
                "target_agents": ["resume_intake_agent"],
                "selected_model": "llama-3.1-8b-instant",
            }
        ],
    )
    mgr = SandboxManager(agents_base_dir=agents_dir, experiments_base_dir=exp_dir)
    env = mgr.prepare_sandbox(scope, experiment_id="exp_iso")

    assert env.sandbox_workflow_dir.exists()
    assert env.sandbox_workflow_dir != orig_dir
    assert (env.experiment_dir / "approved_scope.json").exists()
    assert (env.experiment_dir / "experiment_metadata.json").exists()

    # Mutate sandbox copy and verify original remains untouched
    (env.sandbox_workflow_dir / "intake_agent.py").write_text("# modified in sandbox\n", encoding="utf-8")
    integrity = mgr.verify_original_unchanged(env)
    assert integrity["original_unchanged"] is True
    assert compute_directory_hashes(orig_dir) == pre_hashes


# ---------------------------------------------------------------------------
# Test 2: Approved Candidate Filtering
# ---------------------------------------------------------------------------
def test_02_approved_candidate_filtering(tmp_path: Path):
    agents_dir = tmp_path / "agents"
    exp_dir = tmp_path / "experiments"
    _make_sample_workflow(agents_dir, "sample_wf")

    scope = {
        "workflow_id": "sample_wf",
        "approval_status": "approved",
        "approved_candidate_ids": ["MODEL-RESUME_INTAKE_AGENT"],
        "approved_candidates": [
            {
                "candidate_id": "MODEL-RESUME_INTAKE_AGENT",
                "dimension": "model_selection",
                "target_agents": ["resume_intake_agent"],
                "selected_model": "llama-3.1-8b-instant",
            },
            {
                "candidate_id": "PROMPT-UNAPPROVED",
                "dimension": "prompt_optimization",
                "target_agents": ["screening_review_agent"],
                "optimized_prompt": "Should NOT execute",
            },
        ],
    }
    mgr = SandboxManager(agents_base_dir=agents_dir, experiments_base_dir=exp_dir)
    env = mgr.prepare_sandbox(scope, experiment_id="exp_filter")
    res = CandidateExecutionRouter().execute_approved_candidates(env)

    executed_ids = [r["candidate_id"] for r in res["candidate_results"]]
    assert executed_ids == ["MODEL-RESUME_INTAKE_AGENT"]
    assert "PROMPT-UNAPPROVED" not in executed_ids
    review_src = (env.sandbox_workflow_dir / "screening_review_agent.py").read_text(encoding="utf-8")
    assert "OPTIMIZED_PROMPT" not in review_src


# ---------------------------------------------------------------------------
# Test 3: Candidate Routing Across All 5 Dimensions
# ---------------------------------------------------------------------------
def test_03_candidate_routing_covers_all_five_dimensions():
    expected = {
        "agent_consolidation",
        "workflow_parallelization",
        "model_selection",
        "prompt_optimization",
        "communication_data_handoff",
    }
    assert set(EXECUTOR_REGISTRY.keys()) == expected
    router = CandidateExecutionRouter()
    for dim in expected:
        assert dim in router.registry
        assert callable(router.registry[dim]().execute)


# ---------------------------------------------------------------------------
# Test 4: Consolidation Execution
# ---------------------------------------------------------------------------
def test_04_agent_consolidation_executor(tmp_path: Path):
    agents_dir = tmp_path / "agents"
    exp_dir = tmp_path / "experiments"
    _make_sample_workflow(agents_dir, "sample_wf")

    candidate = {
        "candidate_id": "CONSOLIDATE-QUAL-EXP",
        "dimension": "agent_consolidation",
        "target_agents": ["qualification_agent", "experience_assessment_agent"],
        "unified_prompt": "Extract candidate qualifications and score experience in a single structured pass.",
        "supporting_evidence": {
            "consolidated_responsibilities": {
                "combined_role": "Unified Qualification and Experience Analyst",
                "combined_goal": "Extract qualifications and assess experience in one pass.",
            }
        },
    }
    mgr = SandboxManager(agents_base_dir=agents_dir, experiments_base_dir=exp_dir)
    env = mgr.prepare_sandbox(_make_approved_scope("sample_wf", [candidate]), experiment_id="exp_cons")

    result = AgentConsolidationExecutor().execute(env, candidate)
    assert result["status"] == "applied"
    expected_id = "consolidated_qualification_experience_assessment"

    wf = json.loads((env.sandbox_workflow_dir / "workflow.json").read_text(encoding="utf-8"))
    agent_ids = [a["agent_id"] for a in wf["agents"]]
    assert expected_id in agent_ids
    assert "qualification_agent" not in agent_ids
    assert "experience_assessment_agent" not in agent_ids

    # Downstream agent must now depend on consolidated agent
    reviewer = next(a for a in wf["agents"] if a["agent_id"] == "screening_review_agent")
    assert expected_id in reviewer["dependencies"]
    assert "experience_assessment_agent" not in reviewer["dependencies"]
    assert (env.sandbox_workflow_dir / f"{expected_id}.py").exists()


# ---------------------------------------------------------------------------
# Test 5: Parallelization Execution (True Concurrency + Dependency Rejection)
# ---------------------------------------------------------------------------
def test_05_parallelization_executor_concurrent_and_dep_guard(tmp_path: Path):
    agents_dir = tmp_path / "agents"
    exp_dir = tmp_path / "experiments"
    _make_sample_workflow(agents_dir, "sample_wf")

    # 5a. Independent pair -> applied and executed concurrently across threads
    parallel_cand = {
        "candidate_id": "PARALLEL-QUALIFICATION_AGENT-JOB_CRITERIA_AGENT",
        "dimension": "workflow_parallelization",
        "target_agents": ["qualification_agent", "job_criteria_agent"],
    }
    mgr = SandboxManager(agents_base_dir=agents_dir, experiments_base_dir=exp_dir)
    env = mgr.prepare_sandbox(_make_approved_scope("sample_wf", [parallel_cand]), experiment_id="exp_par_ok")
    res = ParallelizationExecutor().execute(env, parallel_cand)
    assert res["status"] == "applied"

    active_threads: Dict[str, str] = {}
    lock = threading.Lock()

    def _threaded_llm(aid, model_id, sys_p, usr_p, ctx):
        if aid in ("qualification_agent", "job_criteria_agent"):
            with lock:
                active_threads[aid] = threading.current_thread().name
            time.sleep(0.08)
        return _mock_llm_callable(aid, model_id, sys_p, usr_p, ctx)

    runner = SandboxWorkflowRunner(llm_callable=_threaded_llm)
    rt = runner.run(env, num_runs=1)
    assert rt["execution_passed"] is True
    assert rt["concurrent_waves_executed"] == [["qualification_agent", "job_criteria_agent"]]
    assert active_threads["qualification_agent"] != active_threads["job_criteria_agent"]

    # 5b. Dependent pair -> rejected safely
    bad_cand = {
        "candidate_id": "PARALLEL-BAD",
        "dimension": "workflow_parallelization",
        "target_agents": ["resume_intake_agent", "qualification_agent"],
    }
    env2 = mgr.prepare_sandbox(_make_approved_scope("sample_wf", [bad_cand]), experiment_id="exp_par_bad")
    bad_res = ParallelizationExecutor().execute(env2, bad_cand)
    assert bad_res["status"] == "failed"


# ---------------------------------------------------------------------------
# Test 6: Model Selection Execution
# ---------------------------------------------------------------------------
def test_06_model_selection_executor(tmp_path: Path):
    agents_dir = tmp_path / "agents"
    exp_dir = tmp_path / "experiments"
    _make_sample_workflow(agents_dir, "sample_wf")

    cand = {
        "candidate_id": "MODEL-RESUME_INTAKE_AGENT",
        "dimension": "model_selection",
        "target_agents": ["resume_intake_agent"],
        "selected_model": "llama-3.1-8b-instant",
    }
    mgr = SandboxManager(agents_base_dir=agents_dir, experiments_base_dir=exp_dir)
    env = mgr.prepare_sandbox(_make_approved_scope("sample_wf", [cand]), experiment_id="exp_model")
    res = ModelSelectionExecutor().execute(env, cand)

    assert res["status"] == "applied"
    assert res["details"]["model_transitions"]["resume_intake_agent"]["previous_model"] == "openai/gpt-oss-120b"
    assert res["details"]["model_transitions"]["resume_intake_agent"]["updated_model"] == "llama-3.1-8b-instant"

    intake_py = (env.sandbox_workflow_dir / "intake_agent.py").read_text(encoding="utf-8")
    assert "MODEL_OVERRIDE = 'llama-3.1-8b-instant'" in intake_py or 'MODEL_OVERRIDE = "llama-3.1-8b-instant"' in intake_py

    # Other agents must remain on baseline model and provider/key_env preserved
    wf = json.loads((env.sandbox_workflow_dir / "workflow.json").read_text(encoding="utf-8"))
    qual = next(a for a in wf["agents"] if a["agent_id"] == "qualification_agent")
    assert qual.get("model", wf["baseline_model"]) == "openai/gpt-oss-120b"
    assert wf["llm_provider"] == "Groq"
    assert wf["assigned_groq_key_env"] == "GROQ_API_KEY_TEST"


# ---------------------------------------------------------------------------
# Test 7: Prompt Optimization Execution
# ---------------------------------------------------------------------------
def test_07_prompt_optimization_executor(tmp_path: Path):
    agents_dir = tmp_path / "agents"
    exp_dir = tmp_path / "experiments"
    _make_sample_workflow(agents_dir, "sample_wf")

    cand = {
        "candidate_id": "PROMPT-EXPERIENCE_ASSESSMENT_AGENT",
        "dimension": "prompt_optimization",
        "target_agents": ["experience_assessment_agent"],
        "optimized_prompt": "Extract years_experience, domain_fit_score, and justification as strict JSON.",
    }
    mgr = SandboxManager(agents_base_dir=agents_dir, experiments_base_dir=exp_dir)
    env = mgr.prepare_sandbox(_make_approved_scope("sample_wf", [cand]), experiment_id="exp_prompt")
    res = PromptOptimizationExecutor().execute(env, cand)

    assert res["status"] == "applied"
    rec = res["details"]["prompt_updates"]["experience_assessment_agent"]
    assert rec["original_prompt_preview"] != rec["optimized_prompt"]
    exp_py = (env.sandbox_workflow_dir / "experience_assessment_agent.py").read_text(encoding="utf-8")
    assert "OPTIMIZED_PROMPT" in exp_py
    # Untargeted agent must NOT have OPTIMIZED_PROMPT
    intake_py = (env.sandbox_workflow_dir / "intake_agent.py").read_text(encoding="utf-8")
    assert "OPTIMIZED_PROMPT" not in intake_py


# ---------------------------------------------------------------------------
# Test 8: Communication & Data-Handoff Optimization Execution
# ---------------------------------------------------------------------------
def test_08_data_handoff_executor_edge_scoping_and_runtime_projection(tmp_path: Path):
    agents_dir = tmp_path / "agents"
    exp_dir = tmp_path / "experiments"
    _make_sample_workflow(agents_dir, "sample_wf")

    cand = {
        "candidate_id": "HANDOFF-QUALIFICATION_AGENT-TO-EXPERIENCE_ASSESSMENT_AGENT",
        "dimension": "communication_data_handoff",
        "target_agents": ["qualification_agent", "experience_assessment_agent"],
        "proposed_compact_payload_schema": {
            "retained_fields": ["matched_skills", "degrees", "certifications"],
            "excluded_fields": ["verbose_notes"],
            "typed_delta_projection": True,
        },
        "supporting_evidence": {
            "producer_agent": "qualification_agent",
            "consumer_agent": "experience_assessment_agent",
            "consumer_required_fields": ["matched_skills"],
        },
    }
    mgr = SandboxManager(agents_base_dir=agents_dir, experiments_base_dir=exp_dir)
    env = mgr.prepare_sandbox(_make_approved_scope("sample_wf", [cand]), experiment_id="exp_handoff")
    res = DataHandoffExecutor().execute(env, cand)
    assert res["status"] == "applied"

    runner = SandboxWorkflowRunner(llm_callable=_mock_llm_callable)
    rt = runner.run(env, num_runs=1)
    assert rt["execution_passed"] is True
    audits = rt["traces"][0]["handoff_audits"]

    proj_edge = next(a for a in audits if a["edge"] == "qualification_agent->experience_assessment_agent")
    assert proj_edge["projected"] is True
    assert "verbose_notes" not in proj_edge["retained_fields"]
    assert "matched_skills" in proj_edge["retained_fields"]

    # Unapproved edge must NOT be projected
    other_edge = next(a for a in audits if a["edge"] == "job_criteria_agent->experience_assessment_agent")
    assert other_edge["projected"] is False


# ---------------------------------------------------------------------------
# Test 9: Multiple Approved Candidates Across Dimensions
# ---------------------------------------------------------------------------
def test_09_multiple_approved_candidates_across_dimensions(tmp_path: Path):
    agents_dir = tmp_path / "agents"
    exp_dir = tmp_path / "experiments"
    _make_sample_workflow(agents_dir, "sample_wf")

    candidates = [
        {
            "candidate_id": "PARALLEL-QUALIFICATION_AGENT-JOB_CRITERIA_AGENT",
            "dimension": "workflow_parallelization",
            "target_agents": ["qualification_agent", "job_criteria_agent"],
        },
        {
            "candidate_id": "MODEL-RESUME_INTAKE_AGENT",
            "dimension": "model_selection",
            "target_agents": ["resume_intake_agent"],
            "selected_model": "llama-3.1-8b-instant",
        },
        {
            "candidate_id": "PROMPT-EXPERIENCE_ASSESSMENT_AGENT",
            "dimension": "prompt_optimization",
            "target_agents": ["experience_assessment_agent"],
            "optimized_prompt": "Concise scoring prompt.",
        },
        {
            "candidate_id": "HANDOFF-QUALIFICATION_AGENT-TO-EXPERIENCE_ASSESSMENT_AGENT",
            "dimension": "communication_data_handoff",
            "target_agents": ["qualification_agent", "experience_assessment_agent"],
            "proposed_compact_payload_schema": {
                "retained_fields": ["matched_skills"],
                "excluded_fields": ["verbose_notes"],
            },
            "supporting_evidence": {
                "producer_agent": "qualification_agent",
                "consumer_agent": "experience_assessment_agent",
                "consumer_required_fields": ["matched_skills"],
            },
        },
    ]
    runner = SandboxExperimentRunner(
        agents_base_dir=agents_dir,
        experiments_base_dir=exp_dir,
        llm_callable=_mock_llm_callable,
    )
    out = runner.run(_make_approved_scope("sample_wf", candidates), experiment_id="exp_multi", num_runs=1)
    assert out["evaluation_results"]["outcome_flags"]["modification_applied"] is True
    assert out["evaluation_results"]["outcome_flags"]["validation_passed"] is True
    assert out["evaluation_results"]["outcome_flags"]["execution_passed"] is True
    assert len(out["execution_results"]["applied_candidate_ids"]) == 4


# ---------------------------------------------------------------------------
# Test 10: Conflicting Modifications Detected Explicitly
# ---------------------------------------------------------------------------
def test_10_conflicting_modifications_detected(tmp_path: Path):
    agents_dir = tmp_path / "agents"
    exp_dir = tmp_path / "experiments"
    _make_sample_workflow(agents_dir, "sample_wf")

    candidates = [
        {
            "candidate_id": "MODEL-INTAKE-FAST",
            "dimension": "model_selection",
            "target_agents": ["resume_intake_agent"],
            "selected_model": "llama-3.1-8b-instant",
        },
        {
            "candidate_id": "MODEL-INTAKE-MID",
            "dimension": "model_selection",
            "target_agents": ["resume_intake_agent"],
            "selected_model": "qwen/qwen3-32b",
        },
    ]
    mgr = SandboxManager(agents_base_dir=agents_dir, experiments_base_dir=exp_dir)
    env = mgr.prepare_sandbox(_make_approved_scope("sample_wf", candidates), experiment_id="exp_conflict")
    res = CandidateExecutionRouter().execute_approved_candidates(env)

    assert len(res["conflicts"]) >= 1
    assert set(res["conflicting_candidate_ids"]) == {"MODEL-INTAKE-FAST", "MODEL-INTAKE-MID"}
    statuses = {r["candidate_id"]: r["status"] for r in res["candidate_results"]}
    assert statuses["MODEL-INTAKE-FAST"] == "conflict"
    assert statuses["MODEL-INTAKE-MID"] == "conflict"


# ---------------------------------------------------------------------------
# Test 11: Validation Failures Halt Runtime Execution & Preserve Original
# ---------------------------------------------------------------------------
def test_11_validation_failures_detected(tmp_path: Path):
    agents_dir = tmp_path / "agents"
    exp_dir = tmp_path / "experiments"
    orig_dir = _make_sample_workflow(agents_dir, "sample_wf")

    cand = {
        "candidate_id": "MODEL-RESUME_INTAKE_AGENT",
        "dimension": "model_selection",
        "target_agents": ["resume_intake_agent"],
        "selected_model": "llama-3.1-8b-instant",
    }
    mgr = SandboxManager(agents_base_dir=agents_dir, experiments_base_dir=exp_dir)
    env = mgr.prepare_sandbox(_make_approved_scope("sample_wf", [cand]), experiment_id="exp_bad_val")
    exec_res = CandidateExecutionRouter().execute_approved_candidates(env)

    # Inject invalid Python syntax into sandbox only
    (env.sandbox_workflow_dir / "intake_agent.py").write_text("def broken(:\n", encoding="utf-8")
    val_res = validate_sandbox(env, exec_res)

    assert val_res["validation_passed"] is False
    assert val_res["python_syntax_checks"]["passed"] is False
    assert val_res["original_workflow_integrity"]["original_unchanged"] is True
    # Confirm original intake_agent.py compiles cleanly
    compile((orig_dir / "intake_agent.py").read_text(encoding="utf-8"), "intake_agent.py", "exec")


# ---------------------------------------------------------------------------
# Test 12: Runtime Execution Writes Canonical Traces
# ---------------------------------------------------------------------------
def test_12_runtime_execution_writes_traces(tmp_path: Path):
    agents_dir = tmp_path / "agents"
    exp_dir = tmp_path / "experiments"
    _make_sample_workflow(agents_dir, "sample_wf")

    cand = {
        "candidate_id": "MODEL-RESUME_INTAKE_AGENT",
        "dimension": "model_selection",
        "target_agents": ["resume_intake_agent"],
        "selected_model": "llama-3.1-8b-instant",
    }
    mgr = SandboxManager(agents_base_dir=agents_dir, experiments_base_dir=exp_dir)
    env = mgr.prepare_sandbox(_make_approved_scope("sample_wf", [cand]), experiment_id="exp_rt")
    rt = SandboxWorkflowRunner(llm_callable=_mock_llm_callable).run(env, num_runs=2)

    assert rt["execution_passed"] is True
    assert rt["runs_executed"] == 2
    assert len(rt["trace_files"]) == 2
    for tf in rt["trace_files"]:
        trace_obj = json.loads(Path(tf).read_text(encoding="utf-8"))
        assert trace_obj["status"] == "SUCCESS"
        assert len(trace_obj["agent_executions"]) == 5


# ---------------------------------------------------------------------------
# Test 13: Before-and-After Evaluation Separates Outcome Flags & Quality Honestly
# ---------------------------------------------------------------------------
def test_13_before_and_after_evaluation_honesty(tmp_path: Path):
    agents_dir = tmp_path / "agents"
    exp_dir = tmp_path / "experiments"
    _make_sample_workflow(agents_dir, "sample_wf")

    cand = {
        "candidate_id": "MODEL-RESUME_INTAKE_AGENT",
        "dimension": "model_selection",
        "target_agents": ["resume_intake_agent"],
        "selected_model": "llama-3.1-8b-instant",
    }
    mgr = SandboxManager(agents_base_dir=agents_dir, experiments_base_dir=exp_dir)
    env = mgr.prepare_sandbox(_make_approved_scope("sample_wf", [cand]), experiment_id="exp_eval")
    exec_res = CandidateExecutionRouter().execute_approved_candidates(env)
    val_res = validate_sandbox(env, exec_res)
    rt = SandboxWorkflowRunner(llm_callable=_mock_llm_callable).run(env, num_runs=1)
    ev = evaluate_experiment(env, exec_res, val_res, rt)

    flags = ev["outcome_flags"]
    assert set(flags.keys()) == {
        "modification_applied",
        "validation_passed",
        "execution_passed",
        "evaluation_passed",
    }
    assert ev["optimized_metrics"]["semantic_quality_evaluation"] == "unavailable"
    assert (env.experiment_dir / "comparison.json").exists()
    assert (env.experiment_dir / "baseline_metrics.json").exists()
    assert (env.experiment_dir / "optimized_metrics.json").exists()


# ---------------------------------------------------------------------------
# Test 14: Experiment Report Generation & End-to-End LangGraph Approval->Sandbox Flow
# ---------------------------------------------------------------------------
def test_14_reports_and_end_to_end_langgraph_flow(tmp_path: Path):
    orig_dir = ROOT_DIR / "Agents" / "recruitment_screening"
    pre_hashes = compute_directory_hashes(orig_dir)

    agent = OptimizationDiscoveryAgent()
    graph = build_optimization_graph_with_sandbox_execution(runtime_runs=1)
    cfg = {"configurable": {"thread_id": "test-sandbox-e2e-thread"}}

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
        "sandbox_options": {
            "experiments_base_dir": str(tmp_path / "experiments"),
            "enable_trace_replay_fallback": True,
        },
    }
    graph.invoke(initial_state, cfg)
    snapshot = graph.get_state(cfg)
    assert "apply_user_approval" in snapshot.next

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
    report_path = Path(resumed["experiment_report_path"])
    assert report_path.exists()
    md_path = report_path.parent / "execution_report.md"
    assert md_path.exists()
    report_json = json.loads(report_path.read_text(encoding="utf-8"))
    assert report_json["workflow_id"] == "recruitment_screening"
    assert report_json["validation_results"]["original_workflow_integrity"]["original_unchanged"] is True
    assert report_json["outcome_flags"]["modification_applied"] is True
    assert report_json["outcome_flags"]["validation_passed"] is True
    assert report_json["outcome_flags"]["execution_passed"] is True
    assert compute_directory_hashes(orig_dir) == pre_hashes
