"""
Before-and-After Performance, Candidate, and Quality Evaluator for Sandbox Experiments.
Supports matched baseline vs. optimized runtime trace comparisons on identical inputs
alongside MCP historical baseline reference metrics.
Never fabricates missing metrics, never attributes combined savings blindly to each
candidate, and never mixes offline replay timing with live LLM latency.
"""

from __future__ import annotations

import json
import statistics
from typing import Any, Callable, Dict, List, Optional

from mcp_server import tools as evidence_tools
from optimization_agent.model_selection.groq_catalog import MODEL_CATALOG
from optimization_agent.sandbox.evaluation.baseline_loader import _compute_historical_metrics
from optimization_agent.sandbox.evaluation.quality_evaluator import evaluate_workflow_quality
from optimization_agent.sandbox.manager import SandboxEnvironment


def _pct_improvement(
    baseline: Optional[float],
    optimized: Optional[float],
    *,
    higher_is_better: bool = False,
) -> Optional[float]:
    if baseline is None or optimized is None:
        return None
    if higher_is_better:
        if baseline == 0:
            if optimized == 0:
                return 0.0
            return None
        return round(((optimized - baseline) / baseline) * 100.0, 2)
    if baseline <= 0:
        return None
    return round(((baseline - optimized) / baseline) * 100.0, 2)


def _mean(vals: List[float]) -> Optional[float]:
    return (sum(vals) / len(vals)) if vals else None


def _median(vals: List[float]) -> Optional[float]:
    return float(statistics.median(vals)) if vals else None


def _extract_variant_metrics(
    *,
    wf_id: str,
    experiment_id: Optional[str],
    variant: str,
    runtime_results: Dict[str, Any],
    quality_variant_summary: Dict[str, Any],
) -> Dict[str, Any]:
    traces = list(runtime_results.get("traces") or [])
    ok_traces = [
        t for t in traces
        if t.get("status") == "SUCCESS"
        and len(t.get("agent_executions") or []) > 0
    ]

    durs = [float(t["duration_seconds"]) for t in ok_traces if t.get("duration_seconds") is not None]
    toks = [float(t["total_tokens"]) for t in ok_traces if t.get("total_tokens") is not None]
    ptoks = [float(t["prompt_tokens"]) for t in ok_traces if t.get("prompt_tokens") is not None]
    ctoks = [float(t["completion_tokens"]) for t in ok_traces if t.get("completion_tokens") is not None]
    costs = [float(t["estimated_cost_usd"]) for t in ok_traces if t.get("estimated_cost_usd") is not None]

    # Per-agent telemetry across ok_traces
    per_agent_raw: Dict[str, Dict[str, Any]] = {}
    all_agent_durs: List[float] = []
    for t in ok_traces:
        for ex in t.get("agent_executions") or []:
            aid = ex.get("agent_id")
            if not aid:
                continue
            bucket = per_agent_raw.setdefault(
                aid,
                {
                    "durations": [],
                    "tokens": [],
                    "prompt_tokens": [],
                    "completion_tokens": [],
                    "costs": [],
                    "models": set(),
                    "schema_valid": [],
                },
            )
            if ex.get("duration_seconds") is not None:
                d = float(ex["duration_seconds"])
                bucket["durations"].append(d)
                all_agent_durs.append(d)
            if ex.get("tokens") is not None:
                bucket["tokens"].append(float(ex["tokens"]))
            if ex.get("prompt_tokens") is not None:
                bucket["prompt_tokens"].append(float(ex["prompt_tokens"]))
            if ex.get("completion_tokens") is not None:
                bucket["completion_tokens"].append(float(ex["completion_tokens"]))
            if ex.get("estimated_cost_usd") is not None:
                bucket["costs"].append(float(ex["estimated_cost_usd"]))
            if ex.get("model"):
                bucket["models"].add(str(ex["model"]))
            if ex.get("schema_valid") is not None:
                bucket["schema_valid"].append(bool(ex["schema_valid"]))

    per_agent_metrics: Dict[str, Any] = {}
    for aid, b in per_agent_raw.items():
        sv = b["schema_valid"]
        per_agent_metrics[aid] = {
            "runs_count": len(b["durations"]),
            "models_observed": sorted(b["models"]),
            "mean_latency_seconds": round(_mean(b["durations"]), 4) if b["durations"] else None,
            "mean_tokens": round(_mean(b["tokens"]), 1) if b["tokens"] else None,
            "mean_prompt_tokens": round(_mean(b["prompt_tokens"]), 1) if b["prompt_tokens"] else None,
            "mean_completion_tokens": round(_mean(b["completion_tokens"]), 1) if b["completion_tokens"] else None,
            "mean_cost_usd": round(_mean(b["costs"]), 6) if b["costs"] else None,
            "schema_valid_rate_pct": round((sum(1 for v in sv if v) / len(sv)) * 100.0, 2) if sv else None,
        }

    runs_executed = int(runtime_results.get("runs_executed") or 0)
    success_runs = int(runtime_results.get("successful_runs") or 0)
    success_rate = round((success_runs / runs_executed) * 100.0, 2) if runs_executed > 0 else None

    schema_summary = runtime_results.get("schema_validation_summary") or {}
    all_schemas_valid = bool(schema_summary.get("all_schemas_valid", False)) if ok_traces else False

    dim_summary = (quality_variant_summary or {}).get("dimension_summary") or {}
    struct_summary = dim_summary.get("structural_validity") or {}
    sem_summary = dim_summary.get("semantic_quality") or {}

    usage_sources = list(runtime_results.get("usage_sources") or [])
    exec_modes = list(runtime_results.get("execution_modes") or [])
    invalid_replays = list(runtime_results.get("invalid_replay_samples") or [])
    if invalid_replays:
        sem_status: Any = "unavailable"
        sem_rate: Optional[float] = None
    else:
        sem_status = sem_summary.get("status", "unavailable")
        sem_rate = sem_summary.get("pass_rate_pct")

    cost_basis = (
        "estimated_from_model_catalog_using_api_reported_tokens"
        if "api_reported" in usage_sources
        else (
            "estimated_from_model_catalog_using_callable_tokens"
            if "callable_reported" in usage_sources
            else (
                "estimated_from_historical_replay"
                if "historical_trace_replay" in usage_sources
                else "unavailable"
            )
        )
    )

    per_run_metrics: List[Dict[str, Any]] = []
    for t in traces:
        execs = t.get("agent_executions") or []
        per_run_metrics.append({
            "run_id": t.get("run_id"),
            "run_index": t.get("run_index"),
            "matched_baseline_run_id": (t.get("input_snapshot") or {}).get("matched_baseline_run_id"),
            "input_hash": t.get("input_hash"),
            "status": t.get("status"),
            "execution_mode": t.get("execution_mode"),
            "duration_seconds": t.get("duration_seconds"),
            "prompt_tokens": t.get("prompt_tokens"),
            "completion_tokens": t.get("completion_tokens"),
            "total_tokens": t.get("total_tokens"),
            "estimated_cost_usd": t.get("estimated_cost_usd"),
            "schema_valid": all(bool(ex.get("schema_valid", True)) for ex in execs) if execs else False,
        })

    return {
        "workflow_id": wf_id,
        "experiment_id": experiment_id,
        "variant": variant,
        "source": runtime_results.get("source") or f"Matched Sandbox Runtime ({variant})",
        "re_executed": bool(runtime_results.get("re_executed", True)),
        "groq_api_calls": int(runtime_results.get("groq_api_calls") or 0),
        "trace_directory": runtime_results.get("trace_directory"),
        "execution_status": "SUCCESS" if runtime_results.get("execution_passed") else "FAILED",
        "execution_modes": exec_modes,
        "usage_sources": usage_sources,
        "cost_calculation_basis": cost_basis,
        "process_metadata": runtime_results.get("process_metadata"),
        "total_runs": runs_executed,
        "successful_runs": success_runs,
        "failed_runs": int(runtime_results.get("failed_runs") or 0),
        "incomplete_runs": list(runtime_results.get("incomplete_runs") or []),
        "success_rate_pct": success_rate,
        "mean_latency_seconds": round(_mean(durs), 4) if durs else None,
        "median_latency_seconds": round(_median(durs), 4) if durs else None,
        "mean_agent_latency_seconds": round(_mean(all_agent_durs), 4) if all_agent_durs else None,
        "mean_tokens": round(_mean(toks), 1) if toks else None,
        "mean_prompt_tokens": round(_mean(ptoks), 1) if ptoks else None,
        "mean_completion_tokens": round(_mean(ctoks), 1) if ctoks else None,
        "mean_cost_usd_catalog_normalized": round(_mean(costs), 6) if costs else None,
        "schema_validation_passed": all_schemas_valid,
        "structural_validity_pass_rate_pct": struct_summary.get("pass_rate_pct"),
        "schema_validation_failures": list(schema_summary.get("failures") or []),
        "invalid_replay_samples": invalid_replays,
        "semantic_quality_evaluation": sem_status if sem_rate is None else sem_rate,
        "semantic_quality_status": sem_status,
        "semantic_quality_pass_rate_pct": sem_rate,
        "api_errors": list(runtime_results.get("api_errors") or []),
        "per_run_metrics": per_run_metrics,
        "per_agent_metrics": per_agent_metrics,
        "input_dataset_hashes": list(runtime_results.get("input_dataset_hashes") or []),
    }


def _build_mcp_baseline_reference(wf_id: str, evidence_dir: Optional[str]) -> Dict[str, Any]:
    ov = evidence_tools.get_workflow_overview(wf_id, evidence_dir=evidence_dir)
    lat = evidence_tools.get_latency_metrics(wf_id, evidence_dir=evidence_dir)
    tok = evidence_tools.get_token_metrics(wf_id, evidence_dir=evidence_dir)
    cost = evidence_tools.get_cost_metrics(wf_id, evidence_dir=evidence_dir)

    wf_lat = lat.get("workflow_latency") or {}
    wf_tok = tok.get("workflow_tokens") or {}
    wf_cost = cost.get("workflow_cost") or {}

    base_total_runs = ov.get("total_runs_recorded", 0)
    base_success_runs = ov.get("successful_runs", 0)
    base_success_rate = (
        round((base_success_runs / base_total_runs) * 100.0, 2)
        if base_total_runs and base_total_runs > 0
        else None
    )

    base_mean_pt = wf_tok.get("mean_prompt_tokens")
    base_mean_ct = wf_tok.get("mean_completion_tokens")
    base_cat_120b_cost: Optional[float] = None
    if base_mean_pt is not None and base_mean_ct is not None:
        m120 = MODEL_CATALOG["openai/gpt-oss-120b"]
        base_cat_120b_cost = round(
            (float(base_mean_pt) / 1_000_000.0) * float(m120["input_price_per_million_usd"])
            + (float(base_mean_ct) / 1_000_000.0) * float(m120["output_price_per_million_usd"]),
            6,
        )

    ag_lat_map = lat.get("agent_latency_metrics") or {}
    ag_tok_map = tok.get("agent_token_metrics") or {}
    all_agent_means = [
        float(v["mean_seconds"]) for v in ag_lat_map.values() if isinstance(v, dict) and v.get("mean_seconds") is not None
    ]
    per_agent_mcp: Dict[str, Any] = {}
    for aid in set(ag_lat_map.keys()) | set(ag_tok_map.keys()):
        lm = ag_lat_map.get(aid) or {}
        tm = ag_tok_map.get(aid) or {}
        per_agent_mcp[aid] = {
            "mean_latency_seconds": lm.get("mean_seconds"),
            "median_latency_seconds": lm.get("median_seconds"),
            "mean_tokens": tm.get("mean_tokens"),
            "mean_prompt_tokens": tm.get("mean_prompt_tokens"),
            "mean_completion_tokens": tm.get("mean_completion_tokens"),
        }

    return {
        "workflow_id": wf_id,
        "source": "TraceProfiler MCP Evidence Server",
        "execution_modes": ["historical_mcp_baseline"],
        "total_runs": base_total_runs,
        "successful_runs": base_success_runs,
        "failed_runs": max(0, (base_total_runs or 0) - (base_success_runs or 0)),
        "success_rate_pct": base_success_rate,
        "mean_latency_seconds": wf_lat.get("mean_seconds"),
        "median_latency_seconds": wf_lat.get("median_seconds"),
        "mean_agent_latency_seconds": round(_mean(all_agent_means), 4) if all_agent_means else None,
        "mean_tokens": wf_tok.get("mean_tokens"),
        "mean_prompt_tokens": base_mean_pt,
        "mean_completion_tokens": base_mean_ct,
        "mean_cost_usd_telemetry": wf_cost.get("mean_cost_usd"),
        "mean_cost_usd_catalog_normalized": base_cat_120b_cost,
        "cost_calculation_basis": cost.get("calculation_basis", "trace_telemetry_estimates"),
        "schema_validation_passed": None,
        "structural_validity_pass_rate_pct": None,
        "semantic_quality_evaluation": "unavailable",
        "semantic_quality_status": "unavailable",
        "semantic_quality_pass_rate_pct": None,
        "per_agent_metrics": per_agent_mcp,
    }


def classify_final_experiment_assessment(
    *,
    outcome_flags: Dict[str, Any],
    comparison: Dict[str, Any],
    quality_evaluation: Dict[str, Any],
    baseline_metrics: Dict[str, Any],
    optimized_metrics: Dict[str, Any],
    inputs_comparable: bool,
) -> Dict[str, Any]:
    """
    Classify the experiment strictly into one of the 6 canonical outcomes:
      - successful
      - successful_with_tradeoffs
      - no_significant_improvement
      - quality_regression
      - inconclusive
      - failed
    Never marks an experiment successful merely because modifications were applied.
    """
    reasons: List[str] = []

    if (
        not outcome_flags.get("modification_applied")
        or not outcome_flags.get("validation_passed")
        or not outcome_flags.get("execution_passed")
    ):
        if not outcome_flags.get("modification_applied"):
            reasons.append("No approved modifications were applied.")
        if not outcome_flags.get("validation_passed"):
            reasons.append("Sandbox validation failed.")
        if not outcome_flags.get("execution_passed"):
            reasons.append("Optimized workflow runtime execution failed or produced incomplete runs.")
        return {"status": "failed", "reasons": reasons}

    # Offline replay or incomplete replay samples cannot substantiate real regressions or wins
    opt_modes = set(optimized_metrics.get("execution_modes") or [])
    base_modes = set(baseline_metrics.get("execution_modes") or [])
    is_offline = "offline_trace_replay_sandbox" in opt_modes or "offline_trace_replay_sandbox" in base_modes
    has_invalid_replays = bool(optimized_metrics.get("invalid_replay_samples")) or bool(
        baseline_metrics.get("invalid_replay_samples")
    )

    if is_offline:
        reasons.append("Execution used offline_trace_replay_sandbox rather than live LLM execution.")
    if has_invalid_replays:
        reasons.append("Replayed historical samples were incomplete / missing required schema fields.")
    if not inputs_comparable:
        reasons.append("Baseline and optimized runs were not executed on matched identical input datasets.")
    if (optimized_metrics.get("successful_runs") or 0) < 1:
        reasons.append("Fewer than 1 successful optimized run recorded.")
    if optimized_metrics.get("semantic_quality_status") == "unavailable":
        reasons.append("Semantic quality evaluation is unavailable.")

    if is_offline or has_invalid_replays or not inputs_comparable:
        return {"status": "inconclusive", "reasons": reasons}

    # Check verified quality regressions on live/comparable runs
    if quality_evaluation.get("has_quality_regression"):
        regs = quality_evaluation.get("identified_regressions") or []
        reasons.append(
            f"Quality regression detected on {len(regs)} agent metric(s): "
            + ", ".join(f"{r['agent_id']}.{r['metric']}" for r in regs[:4])
        )
        return {"status": "quality_regression", "reasons": reasons}

    if optimized_metrics.get("schema_validation_failures"):
        reasons.append(
            f"Output schema validation failed ({len(optimized_metrics['schema_validation_failures'])} error(s))."
        )

    if not outcome_flags.get("evaluation_passed"):
        reasons.append("Schema validation or quality threshold did not pass.")
        return {"status": "quality_regression" if baseline_metrics.get("schema_validation_passed") else "inconclusive", "reasons": reasons}

    # Live / callable matched evaluation with verified quality -> measure benefit vs trade-offs
    benefit_metrics = {
        "mean_workflow_latency": (comparison.get("mean_workflow_latency") or {}).get("improvement_pct"),
        "median_workflow_latency": (comparison.get("median_workflow_latency") or {}).get("improvement_pct"),
        "total_tokens": (comparison.get("total_tokens") or {}).get("improvement_pct"),
        "execution_cost": (comparison.get("execution_cost") or {}).get("improvement_pct_catalog_normalized"),
    }
    valid_deltas = {k: v for k, v in benefit_metrics.items() if v is not None}
    meaningful_gains = [k for k, v in valid_deltas.items() if v >= 2.0]
    meaningful_tradeoffs = [k for k, v in valid_deltas.items() if v <= -2.0]

    if meaningful_gains and meaningful_tradeoffs:
        reasons.append(
            f"Measurable gains on {meaningful_gains} with trade-offs on {meaningful_tradeoffs}."
        )
        return {"status": "successful_with_tradeoffs", "reasons": reasons}
    if meaningful_gains:
        reasons.append(f"Measurable improvement verified on {meaningful_gains} without quality loss.")
        return {"status": "successful", "reasons": reasons}

    reasons.append("Workflow executed reliably with acceptable quality, but no >=2% latency/token/cost gain observed.")
    return {"status": "no_significant_improvement", "reasons": reasons}


def evaluate_experiment(
    env: SandboxEnvironment,
    execution_results: Dict[str, Any],
    validation_results: Dict[str, Any],
    runtime_results: Dict[str, Any],
    evidence_dir: Optional[str] = None,
    baseline_runtime_results: Optional[Dict[str, Any]] = None,
    quality_evaluation: Optional[Dict[str, Any]] = None,
    judge_callable: Optional[Callable[..., Dict[str, Any]]] = None,
    enable_llm_judge: bool = False,
) -> Dict[str, Any]:
    """
    Evaluate baseline vs. optimized workflows across performance, structural validity,
    semantic quality, candidate traceability, and overall 6-state experiment outcome.
    Persists baseline_metrics.json, optimized_metrics.json, quality_evaluation.json, and comparison.json.
    """
    wf_id = env.workflow_id

    # 1. Quality evaluation across baseline (if matched runs exist) and optimized runs
    qual_eval = quality_evaluation or evaluate_workflow_quality(
        workflow_id=wf_id,
        baseline_runtime_results=baseline_runtime_results,
        optimized_runtime_results=runtime_results,
        original_workflow_dir=env.original_workflow_dir,
        sandbox_workflow_dir=env.sandbox_workflow_dir,
        judge_callable=judge_callable,
        enable_llm_judge=enable_llm_judge,
    )

    # 2. Baseline & Optimized Metrics
    optimized_metrics = _extract_variant_metrics(
        wf_id=wf_id,
        experiment_id=env.experiment_id,
        variant="optimized",
        runtime_results=runtime_results,
        quality_variant_summary=qual_eval.get("optimized_quality") or {},
    )
    if not optimized_metrics.get("trace_directory"):
        optimized_metrics["trace_directory"] = str(env.runtime_traces_dir.resolve())

    historical_mcp = _build_mcp_baseline_reference(wf_id, evidence_dir)
    if (
        baseline_runtime_results is not None
        and baseline_runtime_results.get("execution_mode") == "historical_recorded_execution"
    ):
        opt_hash_set = set(optimized_metrics.get("input_dataset_hashes") or [])
        all_base_traces = list(baseline_runtime_results.get("traces") or [])
        matched_base_traces = (
            [t for t in all_base_traces if t.get("input_hash") in opt_hash_set]
            if opt_hash_set and all_base_traces
            else all_base_traces
        )
        if matched_base_traces and len(matched_base_traces) < len(all_base_traces):
            baseline_metrics = _compute_historical_metrics(
                wf_id=wf_id,
                trace_dir=baseline_runtime_results.get("trace_directory"),
                matched_traces=matched_base_traces,
                fixed_ref_id=str(baseline_runtime_results.get("fixed_baseline_reference_id") or ""),
                matched_hashes=[t["input_hash"] for t in matched_base_traces if t.get("input_hash")],
                matched_count=int(baseline_runtime_results.get("matched_input_count") or len(matched_base_traces)),
                unmatched_count=int(baseline_runtime_results.get("unmatched_input_count") or 0),
                excluded_records=list(baseline_runtime_results.get("excluded_records") or []),
            )
        else:
            baseline_metrics = dict(baseline_runtime_results.get("historical_metrics") or {})
            if not baseline_metrics:
                baseline_metrics = _compute_historical_metrics(
                    wf_id=wf_id,
                    trace_dir=baseline_runtime_results.get("trace_directory"),
                    matched_traces=matched_base_traces,
                    fixed_ref_id=str(baseline_runtime_results.get("fixed_baseline_reference_id") or ""),
                    matched_hashes=list(baseline_runtime_results.get("matched_input_hashes") or []),
                    matched_count=int(baseline_runtime_results.get("matched_input_count") or 0),
                    unmatched_count=int(baseline_runtime_results.get("unmatched_input_count") or 0),
                    excluded_records=list(baseline_runtime_results.get("excluded_records") or []),
                )
        base_q_dim = (qual_eval.get("baseline_quality") or {}).get("dimension_summary") or {}
        base_sv_info = base_q_dim.get("structural_validity") or {}
        baseline_metrics["structural_validity_pass_rate_pct"] = base_sv_info.get("pass_rate_pct")
        baseline_metrics["schema_validation_passed"] = (
            (base_sv_info.get("status") == "passed") if base_sv_info.get("evaluated_count", 0) > 0 else None
        )
        baseline_metrics["re_executed"] = False
        baseline_metrics["groq_api_calls"] = 0
        baseline_metrics["historical_mcp_reference"] = {
            "total_runs": historical_mcp["total_runs"],
            "mean_latency_seconds": historical_mcp["mean_latency_seconds"],
            "mean_tokens": historical_mcp["mean_tokens"],
        }
    elif baseline_runtime_results is not None and (baseline_runtime_results.get("traces") or []):
        baseline_metrics = _extract_variant_metrics(
            wf_id=wf_id,
            experiment_id=env.experiment_id,
            variant="baseline",
            runtime_results=baseline_runtime_results,
            quality_variant_summary=qual_eval.get("baseline_quality") or {},
        )
        baseline_metrics["historical_mcp_reference"] = {
            "total_runs": historical_mcp["total_runs"],
            "mean_latency_seconds": historical_mcp["mean_latency_seconds"],
            "mean_tokens": historical_mcp["mean_tokens"],
        }
    else:
        baseline_metrics = historical_mcp

    # Verify dataset comparability & execution mode parity
    base_hashes = baseline_metrics.get("input_dataset_hashes") or []
    opt_hashes = optimized_metrics.get("input_dataset_hashes") or []
    inputs_comparable = bool(base_hashes and opt_hashes and set(opt_hashes).issubset(set(base_hashes)))

    opt_modes = set(optimized_metrics.get("execution_modes") or [])
    base_modes = set(baseline_metrics.get("execution_modes") or [])
    is_offline_replay = (
        "offline_trace_replay_sandbox" in opt_modes
        or "offline_trace_replay_sandbox" in base_modes
    )
    modes_compatible = (not is_offline_replay) and bool(opt_modes) and (
        bool(base_modes)
        and (
            base_modes == opt_modes
            or "historical_recorded_execution" in base_modes
            or "custom_callable" in str(opt_modes)
        )
    )

    # 3. 10-Metric Before-and-After Comparison
    mean_lat_imp = _pct_improvement(baseline_metrics.get("mean_latency_seconds"), optimized_metrics.get("mean_latency_seconds"))
    med_lat_imp = _pct_improvement(baseline_metrics.get("median_latency_seconds"), optimized_metrics.get("median_latency_seconds"))
    mean_ag_lat_imp = _pct_improvement(baseline_metrics.get("mean_agent_latency_seconds"), optimized_metrics.get("mean_agent_latency_seconds"))

    in_tok_imp = _pct_improvement(baseline_metrics.get("mean_prompt_tokens"), optimized_metrics.get("mean_prompt_tokens"))
    out_tok_imp = _pct_improvement(baseline_metrics.get("mean_completion_tokens"), optimized_metrics.get("mean_completion_tokens"))
    tot_tok_imp = _pct_improvement(baseline_metrics.get("mean_tokens"), optimized_metrics.get("mean_tokens"))
    cost_imp = _pct_improvement(
        baseline_metrics.get("mean_cost_usd_catalog_normalized"),
        optimized_metrics.get("mean_cost_usd_catalog_normalized"),
    )

    # Higher-is-better quality & reliability comparisons
    base_sr = baseline_metrics.get("success_rate_pct")
    opt_sr = optimized_metrics.get("success_rate_pct")
    sr_imp = _pct_improvement(base_sr, opt_sr, higher_is_better=True)

    base_sv = baseline_metrics.get("structural_validity_pass_rate_pct")
    opt_sv = optimized_metrics.get("structural_validity_pass_rate_pct")
    sv_imp = _pct_improvement(base_sv, opt_sv, higher_is_better=True)

    base_sq = baseline_metrics.get("semantic_quality_pass_rate_pct")
    opt_sq = optimized_metrics.get("semantic_quality_pass_rate_pct")
    sq_imp = _pct_improvement(base_sq, opt_sq, higher_is_better=True)

    # Per-agent latency & token breakdown
    base_ag = baseline_metrics.get("per_agent_metrics") or {}
    opt_ag = optimized_metrics.get("per_agent_metrics") or {}
    per_agent_comparison: Dict[str, Any] = {}
    for aid in sorted(set(base_ag.keys()) | set(opt_ag.keys())):
        bm = base_ag.get(aid) or {}
        om = opt_ag.get(aid) or {}
        per_agent_comparison[aid] = {
            "baseline_mean_latency_seconds": bm.get("mean_latency_seconds"),
            "optimized_mean_latency_seconds": om.get("mean_latency_seconds"),
            "latency_improvement_pct": (
                None if is_offline_replay else _pct_improvement(bm.get("mean_latency_seconds"), om.get("mean_latency_seconds"))
            ),
            "baseline_mean_tokens": bm.get("mean_tokens"),
            "optimized_mean_tokens": om.get("mean_tokens"),
            "token_improvement_pct": (
                None if is_offline_replay else _pct_improvement(bm.get("mean_tokens"), om.get("mean_tokens"))
            ),
        }

    comparison: Dict[str, Any] = {
        "comparison_type": (
            "historical_baseline_vs_live_optimized"
            if ("historical_recorded_execution" in base_modes and not is_offline_replay)
            else (
                "historical_baseline_vs_offline_replay"
                if "historical_recorded_execution" in base_modes
                else "matched_experiment_comparison"
            )
        ),
        "comparability": {
            "inputs_comparable": inputs_comparable,
            "modes_compatible_for_live_claims": modes_compatible and not is_offline_replay,
            "baseline_re_executed": bool(baseline_metrics.get("re_executed", False)),
            "baseline_measurement_period": baseline_metrics.get("measurement_period"),
            "fixed_baseline_reference_id": baseline_metrics.get("fixed_baseline_reference_id"),
            "matched_input_count": baseline_metrics.get("matched_input_count"),
            "unmatched_input_count": baseline_metrics.get("unmatched_input_count"),
            "baseline_runs": baseline_metrics.get("total_runs", 0),
            "optimized_runs": optimized_metrics.get("total_runs", 0),
            "baseline_modes": sorted(base_modes),
            "optimized_modes": sorted(opt_modes),
        },
        "mean_workflow_latency": {
            "baseline_seconds": baseline_metrics.get("mean_latency_seconds"),
            "optimized_seconds": optimized_metrics.get("mean_latency_seconds"),
            "improvement_pct": None if (is_offline_replay and not modes_compatible) else mean_lat_imp,
            "raw_replay_delta_pct": mean_lat_imp if is_offline_replay else None,
        },
        "median_workflow_latency": {
            "baseline_seconds": baseline_metrics.get("median_latency_seconds"),
            "optimized_seconds": optimized_metrics.get("median_latency_seconds"),
            "improvement_pct": None if (is_offline_replay and not modes_compatible) else med_lat_imp,
            "raw_replay_delta_pct": med_lat_imp if is_offline_replay else None,
        },
        "mean_agent_latency": {
            "baseline_seconds": baseline_metrics.get("mean_agent_latency_seconds"),
            "optimized_seconds": optimized_metrics.get("mean_agent_latency_seconds"),
            "improvement_pct": None if (is_offline_replay and not modes_compatible) else mean_ag_lat_imp,
            "per_agent": per_agent_comparison,
        },
        # Backward-compatible aliases kept intact
        "latency": {
            "baseline_mean_seconds": baseline_metrics.get("mean_latency_seconds"),
            "optimized_mean_seconds": optimized_metrics.get("mean_latency_seconds"),
            "improvement_pct": None if (is_offline_replay and not modes_compatible) else mean_lat_imp,
            "comparable_for_live_claim": (not is_offline_replay) and inputs_comparable,
            "note": (
                "Measured wall-clock timing reflects simulated replay latency in offline mode; "
                "not claimed as live API latency savings."
                if is_offline_replay
                else "Measured live workflow execution latency on matched inputs."
            ),
        },
        "input_tokens": {
            "baseline_mean_tokens": baseline_metrics.get("mean_prompt_tokens"),
            "optimized_mean_tokens": optimized_metrics.get("mean_prompt_tokens"),
            "improvement_pct": None if is_offline_replay else in_tok_imp,
        },
        "output_tokens": {
            "baseline_mean_tokens": baseline_metrics.get("mean_completion_tokens"),
            "optimized_mean_tokens": optimized_metrics.get("mean_completion_tokens"),
            "improvement_pct": None if is_offline_replay else out_tok_imp,
        },
        "total_tokens": {
            "baseline_mean_tokens": baseline_metrics.get("mean_tokens"),
            "optimized_mean_tokens": optimized_metrics.get("mean_tokens"),
            "improvement_pct": None if is_offline_replay else tot_tok_imp,
        },
        "token_consumption": {
            "baseline_mean_tokens": baseline_metrics.get("mean_tokens"),
            "optimized_mean_tokens": optimized_metrics.get("mean_tokens"),
            "improvement_pct": None if is_offline_replay else tot_tok_imp,
        },
        "execution_cost": {
            "baseline_telemetry_usd": baseline_metrics.get("mean_cost_usd_telemetry"),
            "baseline_catalog_normalized_usd": baseline_metrics.get("mean_cost_usd_catalog_normalized"),
            "optimized_catalog_normalized_usd": optimized_metrics.get("mean_cost_usd_catalog_normalized"),
            "improvement_pct_catalog_normalized": None if is_offline_replay else cost_imp,
            "cost_basis": optimized_metrics.get("cost_calculation_basis", "estimated_from_model_catalog"),
        },
        "execution_success_rate": {
            "baseline_pct": base_sr,
            "optimized_pct": opt_sr,
            "delta_pct_points": round(opt_sr - base_sr, 2) if base_sr is not None and opt_sr is not None else None,
            "improvement_pct": sr_imp,
        },
        "output_structural_validity": {
            "baseline_pass_rate_pct": base_sv,
            "optimized_pass_rate_pct": opt_sv,
            "improvement_pct": sv_imp,
        },
        "semantic_quality": {
            "baseline_status_or_pct": base_sq if base_sq is not None else "unavailable",
            "optimized_status_or_pct": opt_sq if opt_sq is not None else "unavailable",
            "improvement_pct": sq_imp,
            "identified_regressions": qual_eval.get("identified_regressions") or [],
        },
        "output_quality": {
            "baseline_quality": base_sq if base_sq is not None else "unavailable",
            "optimized_schema_valid": optimized_metrics.get("schema_validation_passed", False),
            "semantic_quality_evaluation": opt_sq if opt_sq is not None else optimized_metrics.get("semantic_quality_status", "unavailable"),
            "identified_regressions": qual_eval.get("identified_regressions") or [],
            "note": (
                "Structural Pydantic validity, deterministic quality checks, and semantic quality are evaluated separately; "
                "unavailable semantic quality is never fabricated."
            ),
        },
    }

    # 4. 4 Outcome Stage Flags
    mod_applied = bool(execution_results.get("modification_applied", False))
    val_passed = bool(validation_results.get("validation_passed", False))
    exec_passed = bool(runtime_results.get("execution_passed", False))
    all_schemas_valid = bool(optimized_metrics.get("schema_validation_passed", False))
    eval_passed = bool(
        mod_applied
        and val_passed
        and exec_passed
        and all_schemas_valid
        and not qual_eval.get("has_quality_regression", False)
        and (opt_sr is not None and opt_sr > 0.0)
    )

    outcome_flags = {
        "modification_applied": mod_applied,
        "validation_passed": val_passed,
        "execution_passed": exec_passed,
        "evaluation_passed": eval_passed,
    }

    assessment = classify_final_experiment_assessment(
        outcome_flags=outcome_flags,
        comparison=comparison,
        quality_evaluation=qual_eval,
        baseline_metrics=baseline_metrics,
        optimized_metrics=optimized_metrics,
        inputs_comparable=inputs_comparable or (baseline_runtime_results is None),
    )

    # 5. Candidate-Level Traceability (without blind per-candidate attribution in multi-candidate runs)
    applied_count = len(execution_results.get("applied_candidate_ids") or [])
    shared_attribution_note = (
        f"Multiple candidates ({applied_count}) applied concurrently in this experiment; combined workflow deltas "
        "reflect joint execution and are not attributed to individual candidates without isolated ablation runs."
        if applied_count > 1
        else "Single candidate experiment."
    )

    opt_q_by_agent: Dict[str, List[Dict[str, Any]]] = {}
    for ev in (qual_eval.get("optimized_quality") or {}).get("agent_evaluations") or []:
        opt_q_by_agent.setdefault(ev.get("agent_id", ""), []).append(ev)

    base_q_by_agent: Dict[str, List[Dict[str, Any]]] = {}
    for ev in (qual_eval.get("baseline_quality") or {}).get("agent_evaluations") or []:
        base_q_by_agent.setdefault(ev.get("agent_id", ""), []).append(ev)

    candidate_outcomes = []
    for res in execution_results.get("candidate_results") or []:
        c_status = res.get("status")
        targets = list(res.get("target_agents") or [])
        det = res.get("details") or {}
        edge = (
            f"{det['producer_agent']}->{det['consumer_agent']}"
            if det.get("producer_agent") and det.get("consumer_agent")
            else None
        )
        base_obs = {aid: base_ag.get(aid) for aid in targets if aid in base_ag}
        opt_obs = {aid: opt_ag.get(aid) for aid in targets if aid in opt_ag}
        q_impact = {
            aid: {
                "baseline_structural": [e.get("structural_validity") for e in base_q_by_agent.get(aid, [])],
                "optimized_structural": [e.get("structural_validity") for e in opt_q_by_agent.get(aid, [])],
                "optimized_semantic": [e.get("semantic_quality") for e in opt_q_by_agent.get(aid, [])],
            }
            for aid in targets
        }

        failures = [res["error"]] if res.get("error") else []
        if not val_passed:
            failures.append("Sandbox validation failed.")
        if not exec_passed:
            failures.append("Optimized runtime execution failed or incomplete.")

        if c_status == "applied" and eval_passed and not res.get("requires_validation"):
            c_eval_res = "passed"
        elif c_status == "applied" and val_passed and exec_passed:
            c_eval_res = "applied_requires_further_validation"
        elif c_status in ("failed", "conflict"):
            c_eval_res = "failed"
        else:
            c_eval_res = str(c_status or "unknown")

        # Preserve prior 'outcome' label alongside comprehensive traceability fields
        prior_outcome = (
            "succeeded_in_sandbox"
            if c_status == "applied" and val_passed and exec_passed and not res.get("requires_validation")
            else (
                "applied_requires_further_validation"
                if c_status == "applied" and val_passed and exec_passed
                else ("failed" if c_status in ("failed", "conflict") else str(c_status))
            )
        )

        candidate_outcomes.append({
            "candidate_id": res.get("candidate_id"),
            "dimension": res.get("dimension"),
            "target_agents": targets,
            "handoff_edge": edge,
            "modification_applied": c_status == "applied",
            "modification_status": c_status,
            "modified_files": list(res.get("modified_files") or []),
            "validation_result": "passed" if val_passed else "failed",
            "execution_result": "passed" if exec_passed else "failed",
            "baseline_metric_observations": base_obs,
            "optimized_metric_observations": opt_obs,
            "output_quality_impact": q_impact,
            "evaluation_result": c_eval_res,
            "outcome": prior_outcome,
            "requires_validation": bool(res.get("requires_validation", False)),
            "failure_reasons": failures,
            "attribution_note": shared_attribution_note,
        })

    # Persist artifacts into experiment directory
    (env.experiment_dir / "baseline_metrics.json").write_text(
        json.dumps(baseline_metrics, indent=2), encoding="utf-8"
    )
    (env.experiment_dir / "optimized_metrics.json").write_text(
        json.dumps(optimized_metrics, indent=2), encoding="utf-8"
    )
    (env.experiment_dir / "quality_evaluation.json").write_text(
        json.dumps(qual_eval, indent=2), encoding="utf-8"
    )
    (env.experiment_dir / "comparison.json").write_text(
        json.dumps(comparison, indent=2), encoding="utf-8"
    )

    return {
        "baseline_metrics": baseline_metrics,
        "optimized_metrics": optimized_metrics,
        "quality_evaluation": qual_eval,
        "comparison": comparison,
        "combined_experiment_impact": comparison,
        "outcome_flags": outcome_flags,
        "final_experiment_assessment": assessment,
        "candidate_outcomes": candidate_outcomes,
    }
