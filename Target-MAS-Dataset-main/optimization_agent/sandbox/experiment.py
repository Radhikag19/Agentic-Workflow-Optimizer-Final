"""
Sandbox Experiment Orchestrator:
Coordinates fixed historical baseline evidence loading + input matching and
optimized-only local Python subprocess execution:
  Scope -> Sandbox Preparation -> Candidate Routing -> Sandbox Validation ->
  Load Fixed Historical Baseline Traces -> Match Baseline & Optimized Inputs ->
  Execute ONLY Optimized Workflow (Local Subprocess) -> Quality Evaluation ->
  Baseline vs. Optimized Comparison -> Report Generation -> Original Integrity Check.
"""

from __future__ import annotations

import copy
import datetime
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from optimization_agent.sandbox.candidate_router import (
    DIMENSION_EXECUTION_ORDER,
    CandidateExecutionRouter,
    _canonical_dimension,
)
from optimization_agent.sandbox.evaluation import (
    QualityAcceptanceCriteria,
    evaluate_dimension_result,
    evaluate_experiment,
    evaluate_quality_acceptance,
    evaluate_with_ragas,
    evaluate_workflow_quality,
    load_historical_baseline_evidence,
    select_best_workflows_pareto,
)
from optimization_agent.sandbox.manager import (
    SandboxManager,
    compute_directory_hashes,
    load_approved_scope,
    resolve_original_workflow_dir,
)
from optimization_agent.sandbox.reports import (
    generate_ablation_suite_reports,
    generate_experiment_reports,
    generate_two_phase_study_reports,
)
from optimization_agent.sandbox.runtime import (
    LocalSubprocessExecutionManager,
    SandboxWorkflowRunner,
)
from optimization_agent.sandbox.runtime.runner import _load_comparable_inputs
from optimization_agent.sandbox.validation import validate_sandbox


def normalize_selected_dimensions(
    selected_dimensions: Optional[List[str]],
) -> Optional[List[str]]:
    """
    Normalize and validate an optional user-specified list of optimization dimensions.
    Returns None when unrestricted (so all canonical dimensions with approved candidates run).
    """
    if selected_dimensions is None:
        return None
    normalized: List[str] = []
    seen: set[str] = set()
    valid_dims = set(DIMENSION_EXECUTION_ORDER)
    for raw_dim in selected_dimensions:
        canon = _canonical_dimension(raw_dim)
        if canon not in valid_dims:
            raise ValueError(
                f"Unknown optimization dimension {raw_dim!r}; expected one of {list(DIMENSION_EXECUTION_ORDER)}."
            )
        if canon not in seen:
            seen.add(canon)
            normalized.append(canon)
    return normalized


def build_dimension_scoped_approval(
    approved_scope: Dict[str, Any],
    dimensions: List[str],
) -> Optional[Dict[str, Any]]:
    """
    Return a deep copy of `approved_scope` restricted to approved candidates matching `dimensions`,
    or None if no approved candidate belongs to any requested dimension.
    """
    target_dims = {_canonical_dimension(d) for d in dimensions}
    approved_id_set = set(approved_scope.get("approved_candidate_ids") or [])
    filtered = [
        copy.deepcopy(cand)
        for cand in (approved_scope.get("approved_candidates") or [])
        if isinstance(cand, dict)
        and cand.get("candidate_id") in approved_id_set
        and _canonical_dimension(cand.get("dimension")) in target_dims
    ]
    if not filtered:
        return None

    scoped = copy.deepcopy(approved_scope)
    scoped["approved_candidate_ids"] = [str(c["candidate_id"]) for c in filtered]
    scoped["approved_candidates"] = filtered
    return scoped


def _build_ablation_comparison_rows(
    baseline_bundle: Dict[str, Any],
    first_eval: Dict[str, Any],
    per_dimension_results: Dict[str, Dict[str, Any]],
    combined_result: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Assemble uniform side-by-side rows for baseline, each isolated dimension, and combined."""
    base_metrics = dict(first_eval.get("baseline_metrics") or {})
    rows: List[Dict[str, Any]] = [
        {
            "label": "fixed_historical_baseline",
            "scope_kind": "historical_baseline",
            "applied_candidate_ids": [],
            "runs_executed": base_metrics.get("total_runs") or baseline_bundle.get("runs_executed") or 0,
            "successful_runs": base_metrics.get("successful_runs") or baseline_bundle.get("successful_runs") or 0,
            "mean_latency_seconds": base_metrics.get("mean_latency_seconds"),
            "latency_improvement_pct": 0.0,
            "mean_tokens": base_metrics.get("mean_tokens"),
            "token_improvement_pct": 0.0,
            "mean_cost_usd_catalog_normalized": base_metrics.get("mean_cost_usd_catalog_normalized"),
            "cost_improvement_pct": 0.0,
            "groq_api_calls": 0,
            "structural_validity_pass_rate_pct": base_metrics.get("structural_validity_pass_rate_pct"),
            "assessment_status": "HISTORICAL_FIXED",
            "json_report_path": None,
            "markdown_report_path": None,
        }
    ]

    def _row_from_run(label: str, scope_kind: str, res: Dict[str, Any]) -> Dict[str, Any]:
        eval_res = res.get("evaluation_results") or {}
        opt_m = eval_res.get("optimized_metrics") or {}
        comp = eval_res.get("comparison") or {}
        rt = res.get("runtime_results") or {}
        return {
            "label": label,
            "scope_kind": scope_kind,
            "applied_candidate_ids": list((res.get("execution_results") or {}).get("applied_candidate_ids") or []),
            "runs_executed": rt.get("runs_executed") or 0,
            "successful_runs": rt.get("successful_runs") or 0,
            "mean_latency_seconds": opt_m.get("mean_latency_seconds"),
            "latency_improvement_pct": (comp.get("mean_workflow_latency") or {}).get("improvement_pct"),
            "mean_tokens": opt_m.get("mean_tokens"),
            "token_improvement_pct": (comp.get("total_tokens") or {}).get("improvement_pct"),
            "mean_cost_usd_catalog_normalized": opt_m.get("mean_cost_usd_catalog_normalized"),
            "cost_improvement_pct": (comp.get("execution_cost") or {}).get("improvement_pct_catalog_normalized"),
            "groq_api_calls": int(rt.get("groq_api_calls") or opt_m.get("groq_api_calls") or 0),
            "structural_validity_pass_rate_pct": opt_m.get("structural_validity_pass_rate_pct"),
            "assessment_status": (res.get("final_experiment_assessment") or {}).get("status"),
            "json_report_path": res.get("json_report_path"),
            "markdown_report_path": res.get("markdown_report_path"),
        }

    for dim, dim_res in per_dimension_results.items():
        rows.append(_row_from_run(dim, "isolated_dimension", dim_res))

    if combined_result is not None:
        rows.append(_row_from_run("combined_all_selected_dimensions", "combined_single_workflow", combined_result))

    return rows


_PHASE_A_DIMENSIONS: Tuple[str, ...] = (
    "communication_data_handoff",
    "workflow_parallelization",
)
_PHASE_B_DIMENSIONS: Tuple[str, ...] = (
    "prompt_optimization",
    "agent_consolidation",
    "model_selection",
)


def _accumulate_eval_usage(total: Dict[str, Any], ragas_res: Dict[str, Any]) -> None:
    u = (ragas_res or {}).get("evaluation_model_usage") or {}
    total["api_calls"] += int(u.get("api_calls") or 0)
    total["prompt_tokens"] += int(u.get("prompt_tokens") or 0)
    total["completion_tokens"] += int(u.get("completion_tokens") or 0)
    total["total_tokens"] += int(u.get("total_tokens") or 0)
    total["estimated_cost_usd"] = round(
        total["estimated_cost_usd"] + float(u.get("estimated_cost_usd") or 0.0),
        6,
    )


def _evaluate_study_configuration(
    *,
    name: str,
    scope_kind: str,
    dimension_key: str,
    applied_dimensions: List[str],
    exp_result: Dict[str, Any],
    baseline_bundle: Dict[str, Any],
    criteria: QualityAcceptanceCriteria,
    ragas_runner: Optional[Callable[..., Dict[str, Any]]],
    foundation_ragas_scores: Optional[Dict[str, Any]] = None,
    is_foundation_gate: bool = False,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Run RAGAS + acceptance gate + dimension evaluation and return a uniform selection row."""
    target_agents: List[str] = []
    for r in (exp_result.get("execution_results") or {}).get("candidate_results") or []:
        for aid in (r.get("target_agents") or []):
            if aid not in target_agents:
                target_agents.append(aid)

    ragas_res = evaluate_with_ragas(
        baseline_runtime_results=baseline_bundle,
        optimized_runtime_results=exp_result.get("runtime_results"),
        target_agents=target_agents or None,
        ragas_runner=ragas_runner,
    )
    opt_m = (exp_result.get("evaluation_results") or {}).get("optimized_metrics") or {}
    val_passed = bool((exp_result.get("validation_results") or {}).get("validation_passed", False))
    exec_passed = bool((exp_result.get("runtime_results") or {}).get("execution_passed", False))
    schema_valid = bool(opt_m.get("schema_validation_passed", False))

    acceptance = evaluate_quality_acceptance(
        ragas_res,
        criteria,
        execution_passed=exec_passed,
        validation_passed=val_passed,
        schema_valid=schema_valid,
        foundation_ragas_scores=foundation_ragas_scores,
    )
    dim_eval = evaluate_dimension_result(
        dimension_key,
        exp_result,
        ragas_res,
        acceptance,
        is_foundation_gate=is_foundation_gate,
    )
    config_row = {
        "name": name,
        "scope_kind": scope_kind,
        "dimension": dimension_key,
        "applied_dimensions": list(applied_dimensions),
        "applied_candidate_ids": list((exp_result.get("execution_results") or {}).get("applied_candidate_ids") or []),
        "experiment_id": exp_result.get("experiment_id"),
        "validation_passed": val_passed,
        "execution_passed": exec_passed,
        "schema_valid": schema_valid,
        "mean_latency_seconds": opt_m.get("mean_latency_seconds"),
        "median_latency_seconds": opt_m.get("median_latency_seconds"),
        "mean_prompt_tokens": opt_m.get("mean_prompt_tokens"),
        "mean_completion_tokens": opt_m.get("mean_completion_tokens"),
        "mean_tokens": opt_m.get("mean_tokens"),
        "mean_cost_usd": opt_m.get("mean_cost_usd_catalog_normalized"),
        "faithfulness": ragas_res.get("faithfulness"),
        "context_precision": ragas_res.get("context_precision"),
        "context_recall": ragas_res.get("context_recall"),
        "quality_accepted": bool(dim_eval.get("accepted", False)),
        "quality_status": acceptance.get("status"),
        "quality_reasons": list(dim_eval.get("gate_reasons") or acceptance.get("reasons") or []),
        "json_report_path": exp_result.get("json_report_path"),
        "markdown_report_path": exp_result.get("markdown_report_path"),
    }
    return ragas_res, acceptance, dim_eval, config_row


class SandboxExperimentRunner:
    """Deterministic runner pairing fixed historical baseline evidence with optimized-only subprocess runs."""

    def __init__(
        self,
        agents_base_dir: Optional[Union[str, Path]] = None,
        experiments_base_dir: Optional[Union[str, Path]] = None,
        llm_callable: Optional[Callable[..., Dict[str, Any]]] = None,
        enable_trace_replay_fallback: bool = False,
        evidence_dir: Optional[str] = None,
        data_base_dir: Optional[Union[str, Path]] = None,
        groq_client_factory: Optional[Callable[[str], Any]] = None,
        judge_callable: Optional[Callable[..., Dict[str, Any]]] = None,
        enable_llm_judge: bool = False,
        baseline_traces_dir: Optional[Union[str, Path]] = None,
        baseline_metrics_artifact: Optional[Union[str, Path]] = None,
        max_matched_baseline_records: Optional[int] = None,
        execution_backend: str = "local_subprocess",
        process_timeout_seconds: float = 300.0,
        subprocess_runner: Optional[Callable[..., Any]] = None,
        per_run_subprocess: bool = True,
        ragas_runner: Optional[Callable[..., Dict[str, Any]]] = None,
        quality_acceptance_criteria: Optional[Union[QualityAcceptanceCriteria, Dict[str, Any]]] = None,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        # Deprecated options kept cleanly as no-ops (baseline is never re-executed)
        run_matched_baseline: bool = False,
        interleave_runs: bool = False,
    ):
        self.manager = SandboxManager(
            agents_base_dir=agents_base_dir,
            experiments_base_dir=experiments_base_dir,
        )
        self.router = CandidateExecutionRouter()
        self.enable_trace_replay_fallback = bool(enable_trace_replay_fallback)
        self.evidence_dir = evidence_dir
        self.data_base_dir = Path(data_base_dir).resolve() if data_base_dir else None
        self.judge_callable = judge_callable
        self.enable_llm_judge = enable_llm_judge
        self.baseline_traces_dir = baseline_traces_dir
        self.baseline_metrics_artifact = baseline_metrics_artifact
        self.max_matched_baseline_records = max_matched_baseline_records
        self.execution_backend = str(execution_backend or "local_subprocess")
        self.llm_callable = llm_callable
        self.groq_client_factory = groq_client_factory
        self.subprocess_runner = subprocess_runner
        self.per_run_subprocess = bool(per_run_subprocess)
        self.ragas_runner = ragas_runner
        self.event_callback = event_callback
        self.quality_acceptance_criteria = (
            quality_acceptance_criteria
            if isinstance(quality_acceptance_criteria, QualityAcceptanceCriteria)
            else QualityAcceptanceCriteria.from_dict(quality_acceptance_criteria)
        )

        self.runner = SandboxWorkflowRunner(
            llm_callable=llm_callable,
            enable_trace_replay_fallback=self.enable_trace_replay_fallback,
            evidence_dir=evidence_dir,
            data_base_dir=self.data_base_dir,
            groq_client_factory=groq_client_factory,
            event_callback=event_callback,
        )
        self.process_manager = LocalSubprocessExecutionManager(
            timeout_seconds=process_timeout_seconds,
            python_executable=sys.executable,
            subprocess_runner=subprocess_runner,
        )

    def _emit_event(
        self,
        experiment_id: str,
        event_type: str,
        agent_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        if self.event_callback is None:
            return
        try:
            self.event_callback({
                "event_id": uuid.uuid4().hex[:12],
                "experiment_id": experiment_id,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "event_type": event_type,
                "agent_id": agent_id,
                "payload": payload or {},
            })
        except Exception:
            pass

    def _should_use_local_subprocess(self) -> bool:
        if self.subprocess_runner is not None:
            return True
        return (
            self.execution_backend == "local_subprocess"
            and self.llm_callable is None
            and self.groq_client_factory is None
        )

    def run(
        self,
        approved_scope: Union[Dict[str, Any], str, Path],
        *,
        experiment_id: Optional[str] = None,
        experiment_dir_override: Optional[Union[str, Path]] = None,
        preloaded_baseline_bundle: Optional[Dict[str, Any]] = None,
        num_runs: int = 2,
    ) -> Dict[str, Any]:
        # Stages 1-2: Sandbox Preparation & Candidate Routing
        env = self.manager.prepare_sandbox(
            approved_scope,
            experiment_id=experiment_id,
            experiment_dir_override=experiment_dir_override,
        )
        self._emit_event(
            env.experiment_id,
            "experiment_started",
            payload={"workflow_id": env.workflow_id, "num_runs": num_runs},
        )
        self._emit_event(
            env.experiment_id,
            "sandbox_created",
            payload={"sandbox_workflow_dir": str(env.sandbox_workflow_dir)},
        )
        execution_results = self.router.execute_approved_candidates(env)
        for cand_res in execution_results.get("candidate_results") or []:
            if cand_res.get("status") == "applied":
                self._emit_event(
                    env.experiment_id,
                    "candidate_applied",
                    payload={
                        "candidate_id": cand_res.get("candidate_id"),
                        "dimension": cand_res.get("dimension"),
                        "target_agents": cand_res.get("target_agents") or [],
                    },
                )

        # Stage 3: Validate Modified Sandbox Workflow
        validation_results = validate_sandbox(env, execution_results)
        self._emit_event(
            env.experiment_id,
            "validation_completed",
            payload={"validation_passed": bool(validation_results.get("validation_passed"))},
        )

        # Stage 4: Load Fixed Historical Baseline Traces & Metrics ONCE (Zero Baseline Subprocesses / Groq Calls)
        if preloaded_baseline_bundle is not None:
            baseline_bundle = copy.deepcopy(preloaded_baseline_bundle)
        else:
            baseline_bundle = load_historical_baseline_evidence(
                env.workflow_id,
                baseline_traces_dir=self.baseline_traces_dir,
                baseline_metrics_artifact=self.baseline_metrics_artifact,
                evidence_dir=self.evidence_dir,
                data_base_dir=self.data_base_dir,
                max_matched_records=self.max_matched_baseline_records,
            )

        # Persist matched input provenance metadata (zero raw secrets)
        matching_meta = {
            "fixed_baseline_reference_id": baseline_bundle["fixed_baseline_reference_id"],
            "trace_directory": baseline_bundle["trace_directory"],
            "total_historical_traces_found": baseline_bundle["total_historical_traces_found"],
            "matched_input_count": baseline_bundle["matched_input_count"],
            "unmatched_input_count": baseline_bundle["unmatched_input_count"],
            "excluded_records": baseline_bundle["excluded_records"],
            "matched_identifiers": baseline_bundle["matched_identifiers"],
            "matched_run_ids": baseline_bundle["matched_run_ids"],
            "matched_input_hashes": baseline_bundle["matched_input_hashes"],
        }
        (env.experiment_dir / "baseline_matching_metadata.json").write_text(
            json.dumps(matching_meta, indent=2), encoding="utf-8"
        )

        active_backend = (
            "local_subprocess"
            if self._should_use_local_subprocess()
            else ("in_process_callable" if (self.llm_callable or self.groq_client_factory) else self.execution_backend)
        )

        # Stage 5: Execute ONLY the Optimized Workflow on Matched Inputs (Repeated `num_runs` Times)
        matched_inputs: List[Dict[str, Any]] = list(baseline_bundle.get("matched_inputs") or [])
        if matched_inputs:
            exec_sample_pool = matched_inputs
        else:
            exec_sample_pool = _load_comparable_inputs(
                env.workflow_id,
                num_runs=num_runs,
                data_base_dir=self.data_base_dir,
            )

        if validation_results["validation_passed"]:
            if self._should_use_local_subprocess():
                runtime_results = self.process_manager.run_optimized_workflow(
                    env,
                    sample_inputs=exec_sample_pool,
                    num_runs=num_runs,
                    enable_trace_replay_fallback=self.enable_trace_replay_fallback,
                    evidence_dir=self.evidence_dir,
                    data_base_dir=self.data_base_dir,
                    per_run_subprocess=self.per_run_subprocess,
                )
            else:
                eff_runs = max(1, int(num_runs))
                repeated_inputs = [exec_sample_pool[i % len(exec_sample_pool)] for i in range(eff_runs)]
                runtime_results = self.runner.run_variant(
                    env,
                    variant="optimized",
                    num_runs=eff_runs,
                    sample_inputs=repeated_inputs,
                    run_indices=list(range(eff_runs)),
                )
        else:
            runtime_results = {
                "variant": "optimized",
                "source": "current_experiment",
                "re_executed": False,
                "groq_api_calls": 0,
                "trace_directory": str(env.runtime_traces_dir.resolve()),
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
                "errors": ["Optimized execution skipped because sandbox validation failed."],
            }

        # Stage 6: Output Quality Evaluation, Fixed-Baseline vs. Optimized Comparison & Reports
        self._emit_event(
            env.experiment_id,
            "quality_evaluation_started",
            payload={"workflow_id": env.workflow_id},
        )
        quality_evaluation = evaluate_workflow_quality(
            workflow_id=env.workflow_id,
            baseline_runtime_results=baseline_bundle,
            optimized_runtime_results=runtime_results,
            original_workflow_dir=env.original_workflow_dir,
            sandbox_workflow_dir=env.sandbox_workflow_dir,
            judge_callable=self.judge_callable,
            enable_llm_judge=self.enable_llm_judge,
        )

        evaluation_results = evaluate_experiment(
            env=env,
            execution_results=execution_results,
            validation_results=validation_results,
            runtime_results=runtime_results,
            evidence_dir=self.evidence_dir,
            baseline_runtime_results=baseline_bundle,
            quality_evaluation=quality_evaluation,
            judge_callable=self.judge_callable,
            enable_llm_judge=self.enable_llm_judge,
        )

        report_bundle = generate_experiment_reports(
            env=env,
            execution_results=execution_results,
            validation_results=validation_results,
            runtime_results=runtime_results,
            evaluation_results=evaluation_results,
            baseline_runtime_results=baseline_bundle,
            quality_evaluation=quality_evaluation,
        )

        # Stage 7: Final Post-Experiment Integrity Verification on Original Workflow
        integrity_after = SandboxManager.verify_original_unchanged(env)
        assess_status = (evaluation_results.get("final_experiment_assessment") or {}).get("status")
        self._emit_event(
            env.experiment_id,
            "quality_evaluation_completed",
            payload={"assessment_status": assess_status},
        )
        self._emit_event(
            env.experiment_id,
            "experiment_completed" if runtime_results.get("execution_passed") else "experiment_failed",
            payload={"assessment_status": assess_status, "json_report_path": report_bundle["json_report_path"]},
        )

        return {
            "experiment_id": env.experiment_id,
            "workflow_id": env.workflow_id,
            "execution_backend": active_backend,
            "experiment_dir": str(env.experiment_dir),
            "sandbox_workflow_dir": str(env.sandbox_workflow_dir),
            "original_workflow_dir": str(env.original_workflow_dir),
            "sandbox_metadata": env.to_dict(),
            "execution_results": execution_results,
            "validation_results": validation_results,
            "baseline_runtime_results": baseline_bundle,
            "runtime_results": runtime_results,
            "quality_evaluation": quality_evaluation,
            "evaluation_results": evaluation_results,
            "final_experiment_assessment": evaluation_results["final_experiment_assessment"],
            "original_integrity_after": integrity_after,
            "json_report_path": report_bundle["json_report_path"],
            "markdown_report_path": report_bundle["markdown_report_path"],
            "execution_report": report_bundle["execution_report"],
            "execution_markdown_report": report_bundle["execution_markdown_report"],
        }

    def run_dimension_ablation_suite(
        self,
        approved_scope: Union[Dict[str, Any], str, Path],
        *,
        suite_id: Optional[str] = None,
        selected_dimensions: Optional[List[str]] = None,
        include_combined: bool = True,
        num_runs: int = 2,
    ) -> Dict[str, Any]:
        """
        Execute non-stacked isolated per-dimension experiments (each on a fresh sandbox copy
        of the original workflow) plus an optional combined single-workflow experiment, comparing
        every configuration against the same fixed historical baseline loaded once.
        """
        scope = load_approved_scope(approved_scope)
        wf_id = scope["workflow_id"]
        norm_selected = normalize_selected_dimensions(selected_dimensions)
        candidate_dimensions = (
            norm_selected if norm_selected is not None else list(DIMENSION_EXECUTION_ORDER)
        )

        eff_suite_id = suite_id or (
            f"suite_{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        )
        suite_dir = (self.manager.experiments_base_dir / wf_id / eff_suite_id).resolve()
        suite_dir.mkdir(parents=True, exist_ok=True)

        orig_dir = resolve_original_workflow_dir(wf_id, agents_base_dir=self.manager.agents_base_dir)
        pre_orig_hashes = compute_directory_hashes(orig_dir)

        # Load fixed historical baseline ONCE for the entire suite (zero baseline executions)
        baseline_bundle = load_historical_baseline_evidence(
            wf_id,
            baseline_traces_dir=self.baseline_traces_dir,
            baseline_metrics_artifact=self.baseline_metrics_artifact,
            evidence_dir=self.evidence_dir,
            data_base_dir=self.data_base_dir,
            max_matched_records=self.max_matched_baseline_records,
        )

        per_dimension_results: Dict[str, Dict[str, Any]] = {}
        executed_dimensions: List[str] = []
        skipped_dimensions: List[Dict[str, str]] = []

        # Track 1: Isolated, non-stacked per-dimension runs
        for dim in candidate_dimensions:
            dim_scope = build_dimension_scoped_approval(scope, [dim])
            if dim_scope is None:
                skipped_dimensions.append({"dimension": dim, "reason": "no_approved_candidates"})
                continue

            dim_res = self.run(
                dim_scope,
                experiment_id=f"{eff_suite_id}__dim_{dim}",
                experiment_dir_override=suite_dir / "per_dimension" / dim,
                preloaded_baseline_bundle=baseline_bundle,
                num_runs=num_runs,
            )
            per_dimension_results[dim] = dim_res
            executed_dimensions.append(dim)

        # Track 2: Combined single-workflow run applying all executed dimensions together (preserved)
        combined_result: Optional[Dict[str, Any]] = None
        if include_combined and executed_dimensions:
            combined_scope = build_dimension_scoped_approval(scope, executed_dimensions)
            if combined_scope is not None:
                combined_result = self.run(
                    combined_scope,
                    experiment_id=f"{eff_suite_id}__combined",
                    experiment_dir_override=suite_dir / "combined",
                    preloaded_baseline_bundle=baseline_bundle,
                    num_runs=num_runs,
                )

        # Suite-wide post-execution original integrity check
        post_orig_hashes = compute_directory_hashes(orig_dir)
        changed = [rel for rel, dig in pre_orig_hashes.items() if post_orig_hashes.get(rel) != dig]
        missing = [rel for rel in pre_orig_hashes if rel not in post_orig_hashes]
        added = [rel for rel in post_orig_hashes if rel not in pre_orig_hashes]
        integrity_after = {
            "original_unchanged": not changed and not missing and not added,
            "checked_file_count": len(pre_orig_hashes),
            "changed_files": changed,
            "missing_files": missing,
            "added_files": added,
        }

        first_res = (
            next(iter(per_dimension_results.values()))
            if per_dimension_results
            else (combined_result or {})
        )
        first_eval = dict(first_res.get("evaluation_results") or {})
        comparison_rows = _build_ablation_comparison_rows(
            baseline_bundle=baseline_bundle,
            first_eval=first_eval,
            per_dimension_results=per_dimension_results,
            combined_result=combined_result,
        )

        suite_payload: Dict[str, Any] = {
            "suite_id": eff_suite_id,
            "workflow_id": wf_id,
            "suite_dir": str(suite_dir),
            "selected_dimensions": norm_selected,
            "executed_dimensions": executed_dimensions,
            "skipped_dimensions": skipped_dimensions,
            "include_combined": bool(include_combined),
            "num_runs": int(num_runs),
            "baseline_runtime_results": baseline_bundle,
            "per_dimension_results": per_dimension_results,
            "combined_result": combined_result,
            "comparison_rows": comparison_rows,
            "original_integrity_after": integrity_after,
        }

        suite_reports = generate_ablation_suite_reports(suite_dir, suite_payload)
        suite_payload["json_report_path"] = suite_reports["json_report_path"]
        suite_payload["markdown_report_path"] = suite_reports["markdown_report_path"]
        suite_payload["ablation_report"] = suite_reports["ablation_report"]
        suite_payload["ablation_markdown_report"] = suite_reports["ablation_markdown_report"]
        return suite_payload

    def run_two_phase_optimization_study(
        self,
        approved_scope: Union[Dict[str, Any], str, Path],
        *,
        study_id: Optional[str] = None,
        quality_criteria: Optional[Union[QualityAcceptanceCriteria, Dict[str, Any]]] = None,
        ragas_runner: Optional[Callable[..., Dict[str, Any]]] = None,
        selected_variable_dimensions: Optional[List[str]] = None,
        num_runs: int = 2,
    ) -> Dict[str, Any]:
        """
        Execute the strict Two-Phase + Combined Optimization Study against fixed historical baseline:
          - Phase A: Data Handoff only & Parallelization only -> establish Fixed Optimization Foundation.
          - Phase B: Fixed Foundation + each remaining variable dimension independently (no leakage).
          - Phase C: Combined configuration (Fixed Foundation + all executed variable dimensions).
          - Selection: Pareto-efficient workflow selection over latency, tokens, cost & RAGAS quality.
        """
        scope = load_approved_scope(approved_scope)
        wf_id = scope["workflow_id"]
        eff_study_id = study_id or (
            f"study_{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        )
        study_dir = (self.manager.experiments_base_dir / wf_id / eff_study_id).resolve()
        study_dir.mkdir(parents=True, exist_ok=True)

        eff_criteria = (
            quality_criteria
            if isinstance(quality_criteria, QualityAcceptanceCriteria)
            else (
                QualityAcceptanceCriteria.from_dict(quality_criteria)
                if quality_criteria is not None
                else self.quality_acceptance_criteria
            )
        )
        eff_ragas_runner = ragas_runner if ragas_runner is not None else self.ragas_runner

        var_dims = list(_PHASE_B_DIMENSIONS)
        if selected_variable_dimensions is not None:
            norm_vars = normalize_selected_dimensions(selected_variable_dimensions) or []
            bad_vars = [d for d in norm_vars if d not in _PHASE_B_DIMENSIONS]
            if bad_vars:
                raise ValueError(
                    f"Phase B variable dimensions must be in {list(_PHASE_B_DIMENSIONS)}, got {bad_vars}."
                )
            var_dims = norm_vars

        orig_dir = resolve_original_workflow_dir(wf_id, agents_base_dir=self.manager.agents_base_dir)
        pre_orig_hashes = compute_directory_hashes(orig_dir)

        # Fixed historical baseline loaded ONCE (zero baseline re-executions / zero Groq calls)
        baseline_bundle = load_historical_baseline_evidence(
            wf_id,
            baseline_traces_dir=self.baseline_traces_dir,
            baseline_metrics_artifact=self.baseline_metrics_artifact,
            evidence_dir=self.evidence_dir,
            data_base_dir=self.data_base_dir,
            max_matched_records=self.max_matched_baseline_records,
        )

        eval_usage_totals = {
            "api_calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_usd": 0.0,
            "isolated_from_workflow_metrics": True,
        }
        experiment_ids: List[str] = []
        comparative_rows: List[Dict[str, Any]] = []
        limitations: List[str] = [
            "Historical baseline metrics are from prior recorded executions rather than live concurrent re-execution."
        ]

        # ---------------- Phase A: Fixed Optimization Foundation ----------------
        phase_a_exp_results: Dict[str, Dict[str, Any]] = {}
        phase_a_evals: Dict[str, Dict[str, Any]] = {}
        phase_a_ragas: Dict[str, Dict[str, Any]] = {}
        phase_a_skipped: List[Dict[str, str]] = []
        phase_a_rows: List[Dict[str, Any]] = []
        fixed_foundation: List[str] = []

        for dim in _PHASE_A_DIMENSIONS:
            dim_scope = build_dimension_scoped_approval(scope, [dim])
            if dim_scope is None:
                phase_a_skipped.append({"dimension": dim, "reason": "no_approved_candidates"})
                limitations.append(f"Phase A '{dim}' had no approved candidates and was excluded from the fixed foundation.")
                continue

            exp_id = f"{eff_study_id}__phase_a_{dim}"
            experiment_ids.append(exp_id)
            exp_res = self.run(
                dim_scope,
                experiment_id=exp_id,
                experiment_dir_override=study_dir / "phase_a" / dim,
                preloaded_baseline_bundle=baseline_bundle,
                num_runs=num_runs,
            )
            rag_res, acc_res, dim_ev, cfg_row = _evaluate_study_configuration(
                name=f"phase_a_{dim}",
                scope_kind="phase_a_foundation_candidate",
                dimension_key=dim,
                applied_dimensions=[dim],
                exp_result=exp_res,
                baseline_bundle=baseline_bundle,
                criteria=eff_criteria,
                ragas_runner=eff_ragas_runner,
                is_foundation_gate=True,
            )
            _accumulate_eval_usage(eval_usage_totals, rag_res)
            phase_a_exp_results[dim] = exp_res
            phase_a_ragas[dim] = rag_res
            phase_a_evals[dim] = dim_ev
            phase_a_rows.append(cfg_row)
            comparative_rows.append(cfg_row)

            if dim_ev["accepted"]:
                fixed_foundation.append(dim)
            else:
                limitations.append(
                    f"Phase A foundation gate rejected/did not accept '{dim}': {dim_ev.get('gate_reasons') or acc_res.get('reasons')}."
                )

        # Verify joint fixed foundation if both accepted (or reuse single accepted Phase A run)
        fixed_foundation_result: Optional[Dict[str, Any]] = None
        fixed_foundation_verification: Optional[Dict[str, Any]] = None
        fixed_foundation_row: Optional[Dict[str, Any]] = None
        foundation_ragas_scores: Optional[Dict[str, Any]] = None

        if len(fixed_foundation) == 2:
            ff_scope = build_dimension_scoped_approval(scope, fixed_foundation)
            if ff_scope is not None:
                ff_exp_id = f"{eff_study_id}__phase_a_fixed_foundation"
                experiment_ids.append(ff_exp_id)
                fixed_foundation_result = self.run(
                    ff_scope,
                    experiment_id=ff_exp_id,
                    experiment_dir_override=study_dir / "phase_a" / "fixed_foundation",
                    preloaded_baseline_bundle=baseline_bundle,
                    num_runs=num_runs,
                )
                ff_rag, _, ff_ev, ff_row = _evaluate_study_configuration(
                    name="fixed_foundation",
                    scope_kind="fixed_foundation",
                    dimension_key="fixed_foundation",
                    applied_dimensions=list(fixed_foundation),
                    exp_result=fixed_foundation_result,
                    baseline_bundle=baseline_bundle,
                    criteria=eff_criteria,
                    ragas_runner=eff_ragas_runner,
                )
                _accumulate_eval_usage(eval_usage_totals, ff_rag)
                fixed_foundation_verification = ff_ev
                fixed_foundation_row = ff_row
                comparative_rows.append(ff_row)
                foundation_ragas_scores = ff_ev["ragas"]
        elif len(fixed_foundation) == 1:
            sole_dim = fixed_foundation[0]
            fixed_foundation_result = phase_a_exp_results[sole_dim]
            fixed_foundation_verification = phase_a_evals[sole_dim]
            fixed_foundation_row = phase_a_rows[0]
            foundation_ragas_scores = phase_a_evals[sole_dim]["ragas"]

        # ---------------- Phase B: Remaining 3 Variable Dimensions ----------------
        phase_b_exp_results: Dict[str, Dict[str, Any]] = {}
        phase_b_evals: Dict[str, Dict[str, Any]] = {}
        phase_b_ragas: Dict[str, Dict[str, Any]] = {}
        phase_b_skipped: List[Dict[str, str]] = []
        phase_b_rows: List[Dict[str, Any]] = []
        executed_var_dims: List[str] = []

        for var_dim in var_dims:
            target_dims = list(fixed_foundation) + [var_dim]
            var_only_check = build_dimension_scoped_approval(scope, [var_dim])
            if var_only_check is None:
                phase_b_skipped.append({"dimension": var_dim, "reason": "no_approved_candidates"})
                continue

            var_scope = build_dimension_scoped_approval(scope, target_dims)
            assert var_scope is not None
            exp_id = f"{eff_study_id}__phase_b_{var_dim}"
            experiment_ids.append(exp_id)
            exp_res = self.run(
                var_scope,
                experiment_id=exp_id,
                experiment_dir_override=study_dir / "phase_b" / var_dim,
                preloaded_baseline_bundle=baseline_bundle,
                num_runs=num_runs,
            )
            rag_res, _, dim_ev, cfg_row = _evaluate_study_configuration(
                name=f"foundation_plus_{var_dim}" if fixed_foundation else var_dim,
                scope_kind="variable_on_foundation",
                dimension_key=var_dim,
                applied_dimensions=target_dims,
                exp_result=exp_res,
                baseline_bundle=baseline_bundle,
                criteria=eff_criteria,
                ragas_runner=eff_ragas_runner,
                foundation_ragas_scores=foundation_ragas_scores,
            )
            _accumulate_eval_usage(eval_usage_totals, rag_res)
            phase_b_exp_results[var_dim] = exp_res
            phase_b_ragas[var_dim] = rag_res
            phase_b_evals[var_dim] = dim_ev
            phase_b_rows.append(cfg_row)
            comparative_rows.append(cfg_row)
            executed_var_dims.append(var_dim)

        # ---------------- Phase C: Combined Best Workflow ----------------
        combined_dims = list(fixed_foundation) + list(executed_var_dims)
        combined_result: Optional[Dict[str, Any]] = None
        combined_eval: Optional[Dict[str, Any]] = None
        combined_ragas: Optional[Dict[str, Any]] = None
        combined_row: Optional[Dict[str, Any]] = None
        interaction_notes: List[str] = []

        if combined_dims:
            comb_scope = build_dimension_scoped_approval(scope, combined_dims)
            if comb_scope is not None:
                comb_exp_id = f"{eff_study_id}__phase_c_combined"
                experiment_ids.append(comb_exp_id)
                combined_result = self.run(
                    comb_scope,
                    experiment_id=comb_exp_id,
                    experiment_dir_override=study_dir / "phase_c" / "combined",
                    preloaded_baseline_bundle=baseline_bundle,
                    num_runs=num_runs,
                )
                combined_ragas, _, combined_eval, combined_row = _evaluate_study_configuration(
                    name="combined_workflow",
                    scope_kind="combined",
                    dimension_key="combined",
                    applied_dimensions=combined_dims,
                    exp_result=combined_result,
                    baseline_bundle=baseline_bundle,
                    criteria=eff_criteria,
                    ragas_runner=eff_ragas_runner,
                    foundation_ragas_scores=foundation_ragas_scores,
                )
                _accumulate_eval_usage(eval_usage_totals, combined_ragas)
                comparative_rows.append(combined_row)

                if not combined_eval["accepted"]:
                    interaction_notes.append(
                        f"Combined configuration did not pass quality acceptance: {(combined_eval.get('quality_acceptance') or {}).get('reasons')}."
                    )
                for var_dim, p_row in zip(executed_var_dims, phase_b_rows):
                    if p_row["quality_accepted"] and not combined_row["quality_accepted"]:
                        interaction_notes.append(
                            f"Individual configuration '{p_row['name']}' passed quality acceptance whereas combined did not."
                        )

        # Prepend historical baseline reference row to comparative_rows
        first_exp = (
            combined_result
            or (next(iter(phase_b_exp_results.values())) if phase_b_exp_results else None)
            or (next(iter(phase_a_exp_results.values())) if phase_a_exp_results else {})
        )
        base_m = (first_exp.get("evaluation_results") or {}).get("baseline_metrics") or {}
        baseline_comp_row = {
            "name": "fixed_historical_baseline",
            "scope_kind": "historical_baseline",
            "dimension": "baseline",
            "applied_dimensions": [],
            "applied_candidate_ids": [],
            "experiment_id": baseline_bundle.get("fixed_baseline_reference_id"),
            "validation_passed": True,
            "execution_passed": True,
            "schema_valid": base_m.get("schema_validation_passed"),
            "mean_latency_seconds": base_m.get("mean_latency_seconds"),
            "median_latency_seconds": base_m.get("median_latency_seconds"),
            "mean_prompt_tokens": base_m.get("mean_prompt_tokens"),
            "mean_completion_tokens": base_m.get("mean_completion_tokens"),
            "mean_tokens": base_m.get("mean_tokens"),
            "mean_cost_usd": base_m.get("mean_cost_usd_catalog_normalized"),
            "faithfulness": "reference_only",
            "context_precision": "reference_only",
            "context_recall": "reference_only",
            "quality_accepted": None,
            "quality_status": "HISTORICAL_REFERENCE",
        }
        all_comp_rows = [baseline_comp_row] + comparative_rows

        # Pareto Selection excludes baseline reference row & honors fixed_foundation when established
        pareto_candidates: List[Dict[str, Any]] = []
        if fixed_foundation_row is not None and len(fixed_foundation) == 2:
            pareto_candidates.append(fixed_foundation_row)
        else:
            pareto_candidates.extend(phase_a_rows)
        pareto_candidates.extend(phase_b_rows)
        if combined_row is not None:
            pareto_candidates.append(combined_row)

        pareto_selection = select_best_workflows_pareto(pareto_candidates)

        if baseline_bundle.get("unmatched_input_count"):
            limitations.append(
                f"{baseline_bundle['unmatched_input_count']} historical trace(s) could not be matched by identifier and were excluded."
            )
        if any(
            r.get("faithfulness") == "unavailable"
            or r.get("context_precision") == "unavailable"
            or r.get("context_recall") == "unavailable"
            for r in comparative_rows
        ):
            limitations.append(
                "One or more RAGAS metrics were marked 'unavailable' due to missing RAGAS dependencies, contexts, or reference answers."
            )

        post_orig_hashes = compute_directory_hashes(orig_dir)
        changed = [rel for rel, dig in pre_orig_hashes.items() if post_orig_hashes.get(rel) != dig]
        missing = [rel for rel in pre_orig_hashes if rel not in post_orig_hashes]
        added = [rel for rel in post_orig_hashes if rel not in pre_orig_hashes]
        integrity_after = {
            "original_unchanged": not changed and not missing and not added,
            "checked_file_count": len(pre_orig_hashes),
            "changed_files": changed,
            "missing_files": missing,
            "added_files": added,
        }

        study_payload: Dict[str, Any] = {
            "study_id": eff_study_id,
            "workflow_id": wf_id,
            "study_dir": str(study_dir),
            "num_runs": int(num_runs),
            "live_execution_mode": "in_process_mock_or_callable"
            if not self._should_use_local_subprocess()
            else ("offline_trace_replay_sandbox" if self.enable_trace_replay_fallback else "local_subprocess_live_groq"),
            "quality_acceptance_criteria": eff_criteria.to_dict(),
            "experiment_ids": experiment_ids,
            "baseline_runtime_results": baseline_bundle,
            "fixed_optimization_foundation": fixed_foundation,
            "phase_a_foundation": {
                "dimension_evaluations": phase_a_evals,
                "ragas_evaluations": phase_a_ragas,
                "experiment_results": phase_a_exp_results,
                "skipped_dimensions": phase_a_skipped,
                "fixed_foundation_verification": fixed_foundation_verification,
                "fixed_foundation_experiment_result": fixed_foundation_result,
            },
            "phase_b_variable_dimensions": {
                "executed_dimensions": executed_var_dims,
                "skipped_dimensions": phase_b_skipped,
                "dimension_evaluations": phase_b_evals,
                "ragas_evaluations": phase_b_ragas,
                "experiment_results": phase_b_exp_results,
            },
            "phase_c_combined": {
                "applied_dimensions": combined_dims,
                "experiment_result": combined_result,
                "ragas_evaluation": combined_ragas,
                "evaluation": combined_eval,
                "interaction_notes": interaction_notes,
            },
            "comparative_configurations": all_comp_rows,
            "pareto_selection": pareto_selection,
            "ragas_evaluation_model_usage": eval_usage_totals,
            "limitations": limitations,
            "original_integrity_after": integrity_after,
        }

        study_reports = generate_two_phase_study_reports(study_dir, study_payload)
        study_payload["json_report_path"] = study_reports["json_report_path"]
        study_payload["markdown_report_path"] = study_reports["markdown_report_path"]
        study_payload["study_report"] = study_reports["study_report"]
        study_payload["study_markdown_report"] = study_reports["study_markdown_report"]
        return study_payload
