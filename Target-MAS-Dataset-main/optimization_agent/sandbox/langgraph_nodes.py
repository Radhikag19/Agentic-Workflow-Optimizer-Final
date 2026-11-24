"""
LangGraph Nodes and End-to-End Approval-to-Sandbox Graph Builder.
Connects `next_optimization_stage_handoff` deterministically into:
  sandbox_preparation -> candidate_router_execution -> sandbox_validation ->
  sandbox_historical_baseline_loading -> sandbox_optimized_execution ->
  sandbox_quality_evaluation -> sandbox_performance_comparison ->
  sandbox_experiment_report -> END.

Baseline agents and baseline subprocesses are NEVER executed.
"""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from optimization_agent.discovery import discovery_analysis
from optimization_agent.pipeline import (
    stage_1_discovery,
    stage_2_overview,
    stage_3_graph,
    stage_4_profiles,
    stage_5_prompts,
    stage_6_latency,
    stage_7_tokens,
    stage_8_cost,
    stage_9_comparison,
    stage_10_evidence,
)
from optimization_agent.report import generate_report
from optimization_agent.review.langgraph_handoff import (
    apply_user_approval_node,
    next_optimization_stage_handoff_node,
    prepare_candidate_review_node,
)
from optimization_agent.sandbox.candidate_router import CandidateExecutionRouter
from optimization_agent.sandbox.evaluation import (
    evaluate_experiment,
    evaluate_workflow_quality,
    load_historical_baseline_evidence,
)
from optimization_agent.sandbox.manager import SandboxEnvironment, SandboxManager
from optimization_agent.sandbox.reports import generate_experiment_reports
from optimization_agent.sandbox.runtime import (
    LocalSubprocessExecutionManager,
    SandboxWorkflowRunner,
)
from optimization_agent.sandbox.runtime.runner import _load_comparable_inputs
from optimization_agent.sandbox.validation import validate_sandbox
from optimization_agent.state import OptimizationAgentState
from optimization_agent.tradeoff import tradeoff_assessment

# Process-local caches keyed by experiment_id so non-JSON-serializable runtime helpers stay clean
_ENV_CACHE: Dict[str, SandboxEnvironment] = {}
_INPUT_CACHE: Dict[str, List[Dict[str, Any]]] = {}


def _skipped_runtime_payload(variant: str, reason: str) -> Dict[str, Any]:
    return {
        "variant": variant,
        "source": "current_experiment",
        "re_executed": False,
        "groq_api_calls": 0,
        "execution_passed": False,
        "execution_modes": [],
        "usage_sources": [],
        "runs_executed": 0,
        "successful_runs": 0,
        "failed_runs": 0,
        "incomplete_runs": [],
        "concurrent_waves_executed": [],
        "input_dataset_hashes": [],
        "trace_files": [],
        "traces": [],
        "schema_validation_summary": {"all_schemas_valid": False, "failures": []},
        "invalid_replay_samples": [],
        "api_errors": [],
        "fallback_events": [],
        "errors": [reason],
    }


def sandbox_preparation_node(state: OptimizationAgentState) -> Dict[str, Any]:
    """Prepare isolated sandbox environment from `next_stage_input` or `approved_optimization_scope`."""
    track = dict(state.get("stage_status") or {})
    errors = list(state.get("retrieval_errors") or [])

    next_in = state.get("next_stage_input") or {}
    scope = (
        next_in.get("approved_optimization_scope")
        or state.get("approved_optimization_scope")
        or {}
    )
    if not scope or scope.get("approval_status") != "approved":
        track["sandbox_preparation"] = "skipped"
        return {
            "stage_status": track,
            "sandbox_experiment_metadata": {"skipped": True, "reason": "No approved optimization scope."},
            "sandbox_path": "",
        }

    try:
        opts = dict(state.get("sandbox_options") or {})
        mgr = SandboxManager(
            agents_base_dir=opts.get("agents_base_dir"),
            experiments_base_dir=opts.get("experiments_base_dir"),
        )
        env = mgr.prepare_sandbox(scope, experiment_id=opts.get("experiment_id"))
        _ENV_CACHE[env.experiment_id] = env
        track["sandbox_preparation"] = "completed"
        return {
            "stage_status": track,
            "sandbox_experiment_metadata": env.to_dict(),
            "sandbox_path": str(env.sandbox_workflow_dir),
        }
    except Exception as exc:
        track["sandbox_preparation"] = "failed"
        errors.append({"stage": "sandbox_preparation", "error": str(exc)})
        return {
            "stage_status": track,
            "retrieval_errors": errors,
            "sandbox_experiment_metadata": {"error": str(exc)},
            "sandbox_path": "",
        }


def candidate_router_execution_node(state: OptimizationAgentState) -> Dict[str, Any]:
    """Route approved candidates through dimension-specific deterministic executors."""
    track = dict(state.get("stage_status") or {})
    errors = list(state.get("retrieval_errors") or [])
    meta = state.get("sandbox_experiment_metadata") or {}
    exp_id = meta.get("experiment_id")
    env = _ENV_CACHE.get(exp_id) if exp_id else None

    if env is None:
        track["candidate_router_execution"] = "skipped"
        return {"stage_status": track, "sandbox_execution_results": {"skipped": True}}

    try:
        res = CandidateExecutionRouter().execute_approved_candidates(env)
        track["candidate_router_execution"] = "completed"
        return {"stage_status": track, "sandbox_execution_results": res}
    except Exception as exc:
        track["candidate_router_execution"] = "failed"
        errors.append({"stage": "candidate_router_execution", "error": str(exc)})
        return {
            "stage_status": track,
            "retrieval_errors": errors,
            "sandbox_execution_results": {"error": str(exc), "modification_applied": False},
        }


def sandbox_validation_node(state: OptimizationAgentState) -> Dict[str, Any]:
    """Validate sandbox syntax, config, dependencies, and original workflow integrity."""
    track = dict(state.get("stage_status") or {})
    meta = state.get("sandbox_experiment_metadata") or {}
    exp_id = meta.get("experiment_id")
    env = _ENV_CACHE.get(exp_id) if exp_id else None

    if env is None:
        track["sandbox_validation"] = "skipped"
        return {"stage_status": track, "sandbox_validation_results": {"validation_passed": False}}

    exec_res = state.get("sandbox_execution_results") or {}
    val_res = validate_sandbox(env, exec_res)
    track["sandbox_validation"] = "completed"
    return {"stage_status": track, "sandbox_validation_results": val_res}


def sandbox_historical_baseline_loading_node(
    state: OptimizationAgentState,
    runtime_runs: int = 2,
) -> Dict[str, Any]:
    """
    Load fixed historical baseline traces & metrics read-only ONCE and match exact
    dataset inputs by record identifier. Zero baseline agents or subprocesses run.
    """
    track = dict(state.get("stage_status") or {})
    meta = state.get("sandbox_experiment_metadata") or {}
    exp_id = meta.get("experiment_id")
    env = _ENV_CACHE.get(exp_id) if exp_id else None

    if env is None:
        track["sandbox_historical_baseline_loading"] = "skipped"
        return {"stage_status": track, "sandbox_baseline_runtime_results": {}}

    opts = dict(state.get("sandbox_options") or {})
    data_base = Path(opts["data_base_dir"]).resolve() if opts.get("data_base_dir") else None
    bundle = load_historical_baseline_evidence(
        env.workflow_id,
        baseline_traces_dir=opts.get("baseline_traces_dir"),
        baseline_metrics_artifact=opts.get("baseline_metrics_artifact"),
        evidence_dir=state.get("evidence_dir"),
        data_base_dir=data_base,
        max_matched_records=opts.get("max_matched_baseline_records"),
    )

    num_runs = int(opts.get("num_runs", runtime_runs))
    matched_inputs = list(bundle.get("matched_inputs") or [])
    if not matched_inputs:
        matched_inputs = _load_comparable_inputs(
            env.workflow_id,
            num_runs=num_runs,
            data_base_dir=data_base,
        )
    _INPUT_CACHE[env.experiment_id] = matched_inputs
    track["sandbox_historical_baseline_loading"] = "completed"
    return {"stage_status": track, "sandbox_baseline_runtime_results": bundle}


def sandbox_optimized_execution_node(
    state: OptimizationAgentState,
    llm_callable: Optional[Callable[..., Dict[str, Any]]] = None,
    runtime_runs: int = 2,
    groq_client_factory: Optional[Callable[[str], Any]] = None,
) -> Dict[str, Any]:
    """Execute ONLY the validated optimized sandbox workflow on the matched historical inputs."""
    track = dict(state.get("stage_status") or {})
    meta = state.get("sandbox_experiment_metadata") or {}
    exp_id = meta.get("experiment_id")
    env = _ENV_CACHE.get(exp_id) if exp_id else None
    val_res = state.get("sandbox_validation_results") or {}

    if env is None or not val_res.get("validation_passed"):
        track["sandbox_optimized_execution"] = "skipped"
        return {
            "stage_status": track,
            "sandbox_runtime_results": _skipped_runtime_payload(
                "optimized",
                "Skipped because sandbox validation did not pass.",
            ),
        }

    opts = dict(state.get("sandbox_options") or {})
    num_runs = max(1, int(opts.get("num_runs", runtime_runs)))
    data_base = Path(opts["data_base_dir"]).resolve() if opts.get("data_base_dir") else None
    sample_pool = _INPUT_CACHE.get(env.experiment_id) or _load_comparable_inputs(
        env.workflow_id,
        num_runs=num_runs,
        data_base_dir=data_base,
    )

    backend = str(opts.get("execution_backend", "local_subprocess"))
    custom_factory = opts.get("groq_client_factory") or groq_client_factory
    use_subprocess = (
        opts.get("subprocess_runner") is not None
        or (backend == "local_subprocess" and llm_callable is None and custom_factory is None)
    )

    if use_subprocess:
        proc_mgr = LocalSubprocessExecutionManager(
            timeout_seconds=float(opts.get("process_timeout_seconds", 300.0)),
            subprocess_runner=opts.get("subprocess_runner"),
        )
        opt_res = proc_mgr.run_optimized_workflow(
            env,
            sample_inputs=sample_pool,
            num_runs=num_runs,
            enable_trace_replay_fallback=bool(opts.get("enable_trace_replay_fallback", False)),
            evidence_dir=state.get("evidence_dir"),
            data_base_dir=data_base,
            per_run_subprocess=bool(opts.get("per_run_subprocess", True)),
        )
    else:
        repeated = [sample_pool[i % len(sample_pool)] for i in range(num_runs)]
        runner = SandboxWorkflowRunner(
            llm_callable=llm_callable,
            enable_trace_replay_fallback=bool(opts.get("enable_trace_replay_fallback", False)),
            evidence_dir=state.get("evidence_dir"),
            data_base_dir=data_base,
            groq_client_factory=custom_factory,
        )
        opt_res = runner.run_variant(
            env,
            variant="optimized",
            num_runs=num_runs,
            sample_inputs=repeated,
            run_indices=list(range(num_runs)),
        )

    track["sandbox_optimized_execution"] = "completed"
    return {"stage_status": track, "sandbox_runtime_results": opt_res}


# Backward-compatible aliases
sandbox_runtime_execution_node = sandbox_optimized_execution_node


def sandbox_quality_evaluation_node(
    state: OptimizationAgentState,
    judge_callable: Optional[Callable[..., Dict[str, Any]]] = None,
    enable_llm_judge: bool = False,
) -> Dict[str, Any]:
    """Evaluate fixed historical baseline (structural/invariant checks) and optimized outputs."""
    track = dict(state.get("stage_status") or {})
    meta = state.get("sandbox_experiment_metadata") or {}
    exp_id = meta.get("experiment_id")
    env = _ENV_CACHE.get(exp_id) if exp_id else None

    if env is None:
        track["sandbox_quality_evaluation"] = "skipped"
        return {"stage_status": track, "sandbox_quality_evaluation": {}}

    opts = dict(state.get("sandbox_options") or {})
    base_rt = state.get("sandbox_baseline_runtime_results")
    if isinstance(base_rt, dict) and not base_rt.get("traces"):
        base_rt = None

    q_eval = evaluate_workflow_quality(
        workflow_id=env.workflow_id,
        baseline_runtime_results=base_rt,
        optimized_runtime_results=state.get("sandbox_runtime_results") or {},
        original_workflow_dir=env.original_workflow_dir,
        sandbox_workflow_dir=env.sandbox_workflow_dir,
        judge_callable=opts.get("judge_callable") or judge_callable,
        enable_llm_judge=bool(opts.get("enable_llm_judge", enable_llm_judge)),
    )
    track["sandbox_quality_evaluation"] = "completed"
    return {"stage_status": track, "sandbox_quality_evaluation": q_eval}


def sandbox_performance_comparison_node(state: OptimizationAgentState) -> Dict[str, Any]:
    """Compare fixed historical baseline evidence vs. optimized runtime metrics and outcomes."""
    track = dict(state.get("stage_status") or {})
    meta = state.get("sandbox_experiment_metadata") or {}
    exp_id = meta.get("experiment_id")
    env = _ENV_CACHE.get(exp_id) if exp_id else None

    if env is None:
        track["sandbox_performance_comparison"] = "skipped"
        return {"stage_status": track, "sandbox_evaluation_results": {}}

    base_rt = state.get("sandbox_baseline_runtime_results")
    if isinstance(base_rt, dict) and not base_rt.get("traces"):
        base_rt = None

    eval_res = evaluate_experiment(
        env=env,
        execution_results=state.get("sandbox_execution_results") or {},
        validation_results=state.get("sandbox_validation_results") or {},
        runtime_results=state.get("sandbox_runtime_results") or {},
        evidence_dir=state.get("evidence_dir"),
        baseline_runtime_results=base_rt,
        quality_evaluation=state.get("sandbox_quality_evaluation") or None,
    )
    track["sandbox_performance_comparison"] = "completed"
    return {"stage_status": track, "sandbox_evaluation_results": eval_res}


# Backward-compatible alias
sandbox_evaluation_node = sandbox_performance_comparison_node


def sandbox_experiment_report_node(state: OptimizationAgentState) -> Dict[str, Any]:
    """Write JSON & Markdown sandbox experiment reports."""
    track = dict(state.get("stage_status") or {})
    meta = state.get("sandbox_experiment_metadata") or {}
    exp_id = meta.get("experiment_id")
    env = _ENV_CACHE.get(exp_id) if exp_id else None

    if env is None:
        track["sandbox_experiment_report"] = "skipped"
        return {"stage_status": track, "experiment_report_path": ""}

    base_rt = state.get("sandbox_baseline_runtime_results")
    if isinstance(base_rt, dict) and not base_rt.get("traces"):
        base_rt = None

    rep = generate_experiment_reports(
        env=env,
        execution_results=state.get("sandbox_execution_results") or {},
        validation_results=state.get("sandbox_validation_results") or {},
        runtime_results=state.get("sandbox_runtime_results") or {},
        evaluation_results=state.get("sandbox_evaluation_results") or {},
        baseline_runtime_results=base_rt,
        quality_evaluation=state.get("sandbox_quality_evaluation") or None,
    )
    _INPUT_CACHE.pop(exp_id, None)
    track["sandbox_experiment_report"] = "completed"
    return {
        "stage_status": track,
        "experiment_report_path": rep["json_report_path"],
        "sandbox_experiment_report": rep["execution_report"],
    }


def build_optimization_graph_with_sandbox_execution(
    checkpointer: Optional[Any] = None,
    llm_callable: Optional[Callable[..., Dict[str, Any]]] = None,
    runtime_runs: int = 2,
    groq_client_factory: Optional[Callable[[str], Any]] = None,
    judge_callable: Optional[Callable[..., Dict[str, Any]]] = None,
    enable_llm_judge: bool = False,
) -> Any:
    """
    Build the complete Discovery -> Review/Approval [interrupt] -> Fixed Baseline + Optimized Subprocess LangGraph pipeline.
    Sequence after approval handoff:
      sandbox_preparation -> candidate_router_execution -> sandbox_validation ->
      sandbox_historical_baseline_loading -> sandbox_optimized_execution ->
      sandbox_quality_evaluation -> sandbox_performance_comparison -> sandbox_experiment_report -> END
    """
    builder = StateGraph(OptimizationAgentState)

    for name, fn in (
        ("stage_1_discovery", stage_1_discovery),
        ("stage_2_overview", stage_2_overview),
        ("stage_3_graph", stage_3_graph),
        ("stage_4_profiles", stage_4_profiles),
        ("stage_5_prompts", stage_5_prompts),
        ("stage_6_latency", stage_6_latency),
        ("stage_7_tokens", stage_7_tokens),
        ("stage_8_cost", stage_8_cost),
        ("stage_9_comparison", stage_9_comparison),
        ("stage_10_evidence", stage_10_evidence),
        ("discovery_analysis", discovery_analysis),
        ("tradeoff_assessment", tradeoff_assessment),
        ("generate_report", generate_report),
        ("prepare_candidate_review", prepare_candidate_review_node),
        ("apply_user_approval", apply_user_approval_node),
        ("next_optimization_stage_handoff", next_optimization_stage_handoff_node),
        ("sandbox_preparation", sandbox_preparation_node),
        ("candidate_router_execution", candidate_router_execution_node),
        ("sandbox_validation", sandbox_validation_node),
        (
            "sandbox_historical_baseline_loading",
            partial(sandbox_historical_baseline_loading_node, runtime_runs=runtime_runs),
        ),
        (
            "sandbox_optimized_execution",
            partial(
                sandbox_optimized_execution_node,
                llm_callable=llm_callable,
                runtime_runs=runtime_runs,
                groq_client_factory=groq_client_factory,
            ),
        ),
        (
            "sandbox_quality_evaluation",
            partial(
                sandbox_quality_evaluation_node,
                judge_callable=judge_callable,
                enable_llm_judge=enable_llm_judge,
            ),
        ),
        ("sandbox_performance_comparison", sandbox_performance_comparison_node),
        ("sandbox_experiment_report", sandbox_experiment_report_node),
    ):
        builder.add_node(name, fn)

    node_order = [
        "stage_1_discovery",
        "stage_2_overview",
        "stage_3_graph",
        "stage_4_profiles",
        "stage_5_prompts",
        "stage_6_latency",
        "stage_7_tokens",
        "stage_8_cost",
        "stage_9_comparison",
        "stage_10_evidence",
        "discovery_analysis",
        "tradeoff_assessment",
        "generate_report",
        "prepare_candidate_review",
        "apply_user_approval",
        "next_optimization_stage_handoff",
        "sandbox_preparation",
        "candidate_router_execution",
        "sandbox_validation",
        "sandbox_historical_baseline_loading",
        "sandbox_optimized_execution",
        "sandbox_quality_evaluation",
        "sandbox_performance_comparison",
        "sandbox_experiment_report",
    ]
    builder.add_edge(START, node_order[0])
    for src, dst in zip(node_order, node_order[1:]):
        builder.add_edge(src, dst)
    builder.add_edge(node_order[-1], END)

    cp = checkpointer if checkpointer is not None else MemorySaver()
    return builder.compile(checkpointer=cp, interrupt_before=["apply_user_approval"])
