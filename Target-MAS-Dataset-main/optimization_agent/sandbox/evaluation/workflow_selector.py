"""
Dimension-Specific Performance Evaluation & Pareto-Efficient Best Workflow Selection.

Evaluates each of the 5 optimization dimensions according to its dimension-specific
primary/supporting metrics and RAGAS acceptance status, then selects the Pareto-efficient
(non-dominated) configurations over (latency, total_tokens, estimated_cost) subject to
quality acceptance — never inventing weighted scores or bypassing quality constraints.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _collect_handoff_evidence(exp_result: Dict[str, Any]) -> Dict[str, Any]:
    rt = exp_result.get("runtime_results") or {}
    exec_res = exp_result.get("execution_results") or {}
    edges: Dict[str, Dict[str, Any]] = {}
    for trace in (rt.get("traces") or []):
        for audit in (trace.get("handoff_audits") or []):
            if not isinstance(audit, dict) or not audit.get("projected"):
                continue
            edge = str(audit.get("edge") or "")
            if edge and edge not in edges:
                edges[edge] = {
                    "edge": edge,
                    "retained_fields": list(audit.get("retained_fields") or []),
                    "removed_fields": list(audit.get("removed_fields") or []),
                    "original_fields": list(audit.get("original_fields") or []),
                    "has_original_payload": audit.get("original_payload") is not None,
                    "has_projected_payload": audit.get("projected_payload") is not None,
                }
    required_preserved = all(
        r.get("status") == "applied"
        for r in (exec_res.get("candidate_results") or [])
        if r.get("dimension") == "communication_data_handoff"
    )
    return {
        "modified_edges": list(edges.values()),
        "required_downstream_fields_preserved": required_preserved and bool(edges or exec_res.get("modification_applied")),
    }


def _collect_prompt_before_after(exp_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    sb_dir_str = exp_result.get("sandbox_workflow_dir")
    records: List[Dict[str, Any]] = []
    if sb_dir_str:
        cfg_p = Path(sb_dir_str) / "sandbox_optimization_config.json"
        if cfg_p.exists():
            try:
                cfg = json.loads(cfg_p.read_text(encoding="utf-8"))
                for aid, rec in (cfg.get("prompt_overrides") or {}).items():
                    records.append({
                        "agent_id": aid,
                        "candidate_id": rec.get("candidate_id"),
                        "original_prompt_preview": rec.get("original_prompt_preview"),
                        "original_prompt_char_length": rec.get("original_prompt_char_length"),
                        "optimized_prompt": rec.get("optimized_prompt"),
                        "optimized_prompt_char_length": rec.get("optimized_prompt_char_length"),
                    })
            except Exception:
                pass
    return records


def _collect_model_verification(exp_result: Dict[str, Any]) -> Dict[str, Any]:
    rt = exp_result.get("runtime_results") or {}
    sb_dir_str = exp_result.get("sandbox_workflow_dir")
    expected_overrides: Dict[str, Any] = {}
    if sb_dir_str:
        wf_p = Path(sb_dir_str) / "workflow.json"
        if wf_p.exists():
            try:
                wf_data = json.loads(wf_p.read_text(encoding="utf-8"))
                expected_overrides = wf_data.get("agent_model_overrides") or {}
            except Exception:
                pass
    observed_models: Dict[str, set] = {}
    for trace in (rt.get("traces") or []):
        for ex in (trace.get("agent_executions") or []):
            aid = ex.get("agent_id")
            if aid and ex.get("model"):
                observed_models.setdefault(str(aid), set()).add(str(ex["model"]))

    verified: Dict[str, bool] = {}
    for aid, info in expected_overrides.items():
        upd = (info or {}).get("updated_model")
        verified[aid] = bool(upd and upd in observed_models.get(aid, set()))

    return {
        "expected_overrides": expected_overrides,
        "observed_models_in_traces": {k: sorted(v) for k, v in observed_models.items()},
        "all_overrides_used_at_runtime": bool(expected_overrides) and all(verified.values()),
    }


def evaluate_dimension_result(
    dimension: str,
    exp_result: Dict[str, Any],
    ragas_result: Dict[str, Any],
    acceptance: Dict[str, Any],
    *,
    is_foundation_gate: bool = False,
) -> Dict[str, Any]:
    """
    Evaluate a single optimization configuration using dimension-specific primary metrics,
    supporting diagnostics, RAGAS scores, and quality acceptance gates.
    """
    eval_res = exp_result.get("evaluation_results") or {}
    opt_m = eval_res.get("optimized_metrics") or {}
    comp = eval_res.get("comparison") or {}
    rt = exp_result.get("runtime_results") or {}
    exec_res = exp_result.get("execution_results") or {}
    val_res = exp_result.get("validation_results") or {}

    lat_pct = (comp.get("mean_workflow_latency") or {}).get("improvement_pct")
    med_lat_pct = (comp.get("median_workflow_latency") or {}).get("improvement_pct")
    tok_pct = (comp.get("total_tokens") or {}).get("improvement_pct")
    cost_pct = (comp.get("execution_cost") or {}).get("improvement_pct_catalog_normalized")

    base_diag: Dict[str, Any] = {
        "dimension": dimension,
        "experiment_id": exp_result.get("experiment_id"),
        "applied_candidate_ids": list(exec_res.get("applied_candidate_ids") or []),
        "validation_passed": bool(val_res.get("validation_passed", False)),
        "execution_passed": bool(rt.get("execution_passed", False)),
        "mean_latency_seconds": opt_m.get("mean_latency_seconds"),
        "median_latency_seconds": opt_m.get("median_latency_seconds"),
        "latency_improvement_pct": lat_pct,
        "median_latency_improvement_pct": med_lat_pct,
        "mean_prompt_tokens": opt_m.get("mean_prompt_tokens"),
        "mean_completion_tokens": opt_m.get("mean_completion_tokens"),
        "mean_tokens": opt_m.get("mean_tokens"),
        "token_improvement_pct": tok_pct,
        "mean_cost_usd": opt_m.get("mean_cost_usd_catalog_normalized"),
        "cost_improvement_pct": cost_pct,
        "ragas": {
            "status": ragas_result.get("status"),
            "faithfulness": ragas_result.get("faithfulness"),
            "context_precision": ragas_result.get("context_precision"),
            "context_recall": ragas_result.get("context_recall"),
        },
        "equivalence": (
            {
                "status": ragas_result.get("status"),
                "structural_decision_score": ragas_result.get("structural_decision_score"),
                "semantic_cosine_similarity": ragas_result.get("semantic_cosine_similarity"),
                "llm_judge_equivalence": ragas_result.get("llm_judge_equivalence"),
                "overall_equivalence_score": ragas_result.get("overall_equivalence_score"),
                "decision_flip_count": ragas_result.get("decision_flip_count"),
            }
            if ragas_result.get("evaluation_mode") == "equivalence"
            else None
        ),
        "quality_acceptance": acceptance,
        "accepted": bool(acceptance.get("quality_accepted", False)),
    }

    if dimension == "communication_data_handoff":
        handoff_ev = _collect_handoff_evidence(exp_result)
        base_diag["primary_objective"] = "token_reduction"
        base_diag["primary_metrics"] = {
            "total_tokens": opt_m.get("mean_tokens"),
            "token_improvement_pct": tok_pct,
        }
        base_diag["supporting_metrics"] = {
            "input_tokens": opt_m.get("mean_prompt_tokens"),
            "output_tokens": opt_m.get("mean_completion_tokens"),
            "handoff_evidence": handoff_ev,
        }
        if is_foundation_gate:
            gate_reasons = list(acceptance.get("reasons") or [])
            proj_ok = bool(exec_res.get("modification_applied")) and handoff_ev["required_downstream_fields_preserved"]
            if not proj_ok:
                gate_reasons.append("Data Handoff projections were not applied cleanly or required fields missing.")
            base_diag["accepted"] = bool(acceptance.get("quality_accepted") and proj_ok)
            base_diag["gate_reasons"] = gate_reasons

    elif dimension == "workflow_parallelization":
        waves = list(rt.get("concurrent_waves_executed") or [])
        base_diag["primary_objective"] = "latency_reduction"
        base_diag["primary_metrics"] = {
            "mean_workflow_latency_seconds": opt_m.get("mean_latency_seconds"),
            "latency_improvement_pct": lat_pct,
        }
        base_diag["supporting_metrics"] = {
            "median_workflow_latency_seconds": opt_m.get("median_latency_seconds"),
            "median_latency_improvement_pct": med_lat_pct,
            "mean_agent_latency_seconds": opt_m.get("mean_agent_latency_seconds"),
            "concurrent_waves_executed": waves,
            "per_agent_metrics": opt_m.get("per_agent_metrics") or {},
        }
        if is_foundation_gate:
            gate_reasons = list(acceptance.get("reasons") or [])
            lat_ok = isinstance(lat_pct, (int, float)) and float(lat_pct) > 0.0
            struct_ok = bool(exec_res.get("modification_applied")) and bool(val_res.get("validation_passed"))
            if not struct_ok:
                gate_reasons.append("Parallelization structure was not validly applied.")
            if not lat_ok:
                gate_reasons.append(f"Parallelization did not demonstrate positive latency benefit (latency_improvement_pct={lat_pct}).")
            base_diag["accepted"] = bool(acceptance.get("quality_accepted") and struct_ok and lat_ok)
            base_diag["gate_reasons"] = gate_reasons

    elif dimension == "prompt_optimization":
        base_diag["primary_objective"] = "latency_token_cost_with_quality"
        base_diag["primary_metrics"] = {
            "mean_workflow_latency_seconds": opt_m.get("mean_latency_seconds"),
            "total_tokens": opt_m.get("mean_tokens"),
            "estimated_cost_usd": opt_m.get("mean_cost_usd_catalog_normalized"),
        }
        base_diag["supporting_metrics"] = {
            "prompt_changes": _collect_prompt_before_after(exp_result),
        }

    elif dimension == "agent_consolidation":
        base_diag["primary_objective"] = "latency_token_cost_consolidation"
        base_diag["primary_metrics"] = {
            "mean_workflow_latency_seconds": opt_m.get("mean_latency_seconds"),
            "median_workflow_latency_seconds": opt_m.get("median_latency_seconds"),
            "input_tokens": opt_m.get("mean_prompt_tokens"),
            "output_tokens": opt_m.get("mean_completion_tokens"),
            "total_tokens": opt_m.get("mean_tokens"),
            "estimated_cost_usd": opt_m.get("mean_cost_usd_catalog_normalized"),
        }
        base_diag["supporting_metrics"] = {
            "per_agent_metrics": opt_m.get("per_agent_metrics") or {},
            "consolidation_details": [
                r.get("details")
                for r in (exec_res.get("candidate_results") or [])
                if r.get("dimension") == "agent_consolidation"
            ],
        }

    elif dimension == "model_selection":
        model_verif = _collect_model_verification(exp_result)
        base_diag["primary_objective"] = "latency_and_cost_reduction"
        base_diag["primary_metrics"] = {
            "mean_workflow_latency_seconds": opt_m.get("mean_latency_seconds"),
            "median_workflow_latency_seconds": opt_m.get("median_latency_seconds"),
            "estimated_cost_usd": opt_m.get("mean_cost_usd_catalog_normalized"),
            "cost_improvement_pct": cost_pct,
        }
        base_diag["supporting_metrics"] = {
            "total_tokens_diagnostic": opt_m.get("mean_tokens"),
            "input_tokens_diagnostic": opt_m.get("mean_prompt_tokens"),
            "output_tokens_diagnostic": opt_m.get("mean_completion_tokens"),
            "model_verification": model_verif,
        }
        if not model_verif["all_overrides_used_at_runtime"]:
            base_diag["accepted"] = False
            base_diag["gate_reasons"] = list(acceptance.get("reasons") or []) + [
                "Selected model was not observed in live execution traces for all target agents."
            ]

    else:
        base_diag["primary_objective"] = "joint_latency_token_cost_quality"
        base_diag["primary_metrics"] = {
            "mean_workflow_latency_seconds": opt_m.get("mean_latency_seconds"),
            "total_tokens": opt_m.get("mean_tokens"),
            "estimated_cost_usd": opt_m.get("mean_cost_usd_catalog_normalized"),
        }
        base_diag["supporting_metrics"] = {}

    return base_diag


def _dominates(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """
    Return True iff configuration `a` Pareto-dominates `b` over `(mean_latency_seconds,
    mean_tokens, mean_cost_usd)` — strictly better on at least one objective and no worse on any.
    """
    objs = ("mean_latency_seconds", "mean_tokens", "mean_cost_usd")
    strictly_better = False
    comparable_count = 0
    for k in objs:
        va = a.get(k)
        vb = b.get(k)
        if not isinstance(va, (int, float)) or not isinstance(vb, (int, float)):
            continue
        comparable_count += 1
        if float(va) > float(vb):
            return False
        if float(va) < float(vb):
            strictly_better = True
    return comparable_count > 0 and strictly_better


def select_best_workflows_pareto(configurations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Identify Pareto-efficient workflow configurations strictly among quality-accepted,
    validation-passed, execution-passed candidates — never inventing weighted scores.
    """
    eligible: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []

    for cfg in configurations:
        reasons: List[str] = []
        if not cfg.get("validation_passed", False):
            reasons.append("validation_failed")
        if not cfg.get("execution_passed", False):
            reasons.append("execution_failed")
        if not cfg.get("quality_accepted", False):
            q_status = cfg.get("quality_status") or "rejected_or_inconclusive"
            reasons.append(f"quality_{q_status}")

        has_any_metric = any(
            isinstance(cfg.get(k), (int, float))
            for k in ("mean_latency_seconds", "mean_tokens", "mean_cost_usd")
        )
        if not has_any_metric:
            reasons.append("no_comparable_performance_metrics")

        if reasons:
            excluded.append({**cfg, "exclusion_reasons": reasons})
        else:
            eligible.append(dict(cfg))

    pareto: List[Dict[str, Any]] = []
    for cand in eligible:
        if not any(_dominates(other, cand) for other in eligible if other is not cand):
            pareto.append(cand)

    def _best_by(key: str) -> Optional[Dict[str, Any]]:
        with_val = [c for c in eligible if isinstance(c.get(key), (int, float))]
        if not with_val:
            return None
        return min(with_val, key=lambda c: float(c[key]))

    combined_entry = next((c for c in configurations if c.get("scope_kind") == "combined"), None)

    if len(pareto) == 1:
        recommended = pareto[0]
        note = (
            f"Single Pareto-efficient configuration '{recommended.get('name')}' dominates all other "
            "quality-accepted configurations across latency, tokens, and cost."
        )
    elif len(pareto) > 1:
        recommended = None
        names = [str(p.get("name")) for p in pareto]
        note = (
            f"Multiple Pareto-efficient configurations exist ({names}); reporting all non-dominated "
            "alternatives cleanly rather than inventing an arbitrary weighted preference."
        )
    else:
        recommended = None
        note = "No quality-accepted, successfully executed configurations are eligible for Pareto selection."

    return {
        "objectives": ["minimize:mean_latency_seconds", "minimize:mean_tokens", "minimize:mean_cost_usd"],
        "weighted_scoring_used": False,
        "eligible_configurations": eligible,
        "excluded_configurations": excluded,
        "pareto_efficient_configurations": pareto,
        "best_latency_configuration": _best_by("mean_latency_seconds"),
        "best_token_efficiency_configuration": _best_by("mean_tokens"),
        "best_cost_efficiency_configuration": _best_by("mean_cost_usd"),
        "combined_configuration_summary": combined_entry,
        "recommended_overall_configuration": recommended,
        "selection_note": note,
    }
