"""
Data Models, Normalization, Validation/Risk Evaluation, and Card View Builders
for Candidate Review, Selection, and User Approval.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple


CANONICAL_DIMENSIONS: Tuple[Dict[str, Any], ...] = (
    {
        "key": "agent_consolidation",
        "label": "Agent Consolidation",
        "report_section": "agent_consolidation_opportunities",
        "aliases": ("agent_consolidation",),
    },
    {
        "key": "workflow_parallelization",
        "label": "Workflow Parallelization",
        "report_section": "workflow_parallelization_opportunities",
        "aliases": ("workflow_parallelization",),
    },
    {
        "key": "model_selection",
        "label": "Model Selection",
        "report_section": "model_selection_recommendations",
        "aliases": ("model_selection",),
    },
    {
        "key": "prompt_optimization",
        "label": "Prompt Optimization",
        "report_section": "prompt_optimization_opportunities",
        "aliases": ("prompt_optimization",),
    },
    {
        "key": "communication_data_handoff",
        "label": "Communication & Data-Handoff Optimization",
        "report_section": "communication_optimization_opportunities",
        "aliases": ("communication_data_handoff", "communication_optimization"),
    },
)

TIER_ORDER: Tuple[str, ...] = ("Tier 1", "Tier 2", "Tier 3", "Tier 4")
ELIGIBLE_TIERS: Tuple[str, ...] = ("Tier 1", "Tier 2", "Tier 3")

_DIMENSION_LOOKUP: Dict[str, str] = {}
_DIMENSION_LABELS: Dict[str, str] = {}
for _dim in CANONICAL_DIMENSIONS:
    _DIMENSION_LABELS[_dim["key"]] = _dim["label"]
    _DIMENSION_LOOKUP[_dim["key"].lower()] = _dim["key"]
    _DIMENSION_LOOKUP[_dim["label"].lower()] = _dim["key"]
    for _alias in _dim["aliases"]:
        _DIMENSION_LOOKUP[_alias.lower()] = _dim["key"]


def normalize_dimension_key(raw_dimension: Optional[str]) -> str:
    """Resolve raw dimension key, alias, or display label to its canonical key."""
    if not isinstance(raw_dimension, str) or not raw_dimension.strip():
        return "other"
    cleaned = raw_dimension.strip().lower()
    return _DIMENSION_LOOKUP.get(cleaned, raw_dimension.strip())


def get_dimension_label(dimension_key: Optional[str]) -> str:
    """Return human-readable label for a canonical or aliased dimension key."""
    norm = normalize_dimension_key(dimension_key)
    return _DIMENSION_LABELS.get(norm, str(dimension_key or "Other"))


def normalize_tier(candidate: Dict[str, Any]) -> str:
    """Resolve short tier string ('Tier 1'..'Tier 4') from candidate metadata."""
    raw_tier = str(candidate.get("tier") or "").strip()
    for t in TIER_ORDER:
        if raw_tier.lower() == t.lower():
            return t

    feas = str(candidate.get("feasibility_tier") or "").lower()
    for idx, t in enumerate(TIER_ORDER, 1):
        if f"tier {idx}" in feas:
            return t

    supp = candidate.get("supporting_evidence")
    if not supp or (isinstance(supp, dict) and supp.get("evidence_status") == "insufficient_evidence"):
        return "Tier 4"
    return "Tier 2" if candidate.get("requires_validation") else "Tier 1"


def extract_candidates_from_report(
    report_data: Dict[str, Any],
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Extract workflow_id and verbatim deep-copied candidate objects across all
    5 active report sections, handling both list-based and dict-based section schemas.
    """
    if not isinstance(report_data, dict):
        raise ValueError("Report data must be a dictionary.")

    meta = report_data.get("report_metadata") or {}
    baseline = report_data.get("workflow_baseline") or {}
    workflow_id = str(
        meta.get("workflow_id")
        or baseline.get("workflow_id")
        or report_data.get("workflow_id")
        or ""
    ).strip()

    if not workflow_id:
        raise ValueError("Unable to determine workflow_id from optimization discovery report.")

    extracted: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()

    for dim_meta in CANONICAL_DIMENSIONS:
        section_name = dim_meta["report_section"]
        section_val = report_data.get(section_name)
        if isinstance(section_val, list):
            raw_cands = section_val
        elif isinstance(section_val, dict):
            raw_cands = section_val.get("candidates") or []
        else:
            raw_cands = []

        for idx, cand in enumerate(raw_cands):
            if not isinstance(cand, dict):
                continue
            cand_copy = copy.deepcopy(cand)
            cid = str(cand_copy.get("candidate_id") or f"{dim_meta['key'].upper()}-{idx + 1}")
            if cid in seen_ids:
                continue
            seen_ids.add(cid)
            extracted.append(cand_copy)

    return workflow_id, extracted


def classify_candidate_type(candidate: Dict[str, Any]) -> str:
    """
    Classify candidate scope type:
    'handoff' | 'workflow' | 'multi_agent' | 'agent'
    """
    dim_key = normalize_dimension_key(candidate.get("dimension"))
    supp = candidate.get("supporting_evidence") or {}
    target_agents = list(candidate.get("target_agents") or [])
    cid = str(candidate.get("candidate_id") or "")

    if dim_key == "communication_data_handoff" or (
        isinstance(supp, dict) and supp.get("producer_agent") and supp.get("consumer_agent")
    ):
        return "handoff"
    if len(target_agents) >= 3:
        return "workflow"
    if len(target_agents) >= 2:
        return "multi_agent"
    return "agent"


def _find_action_plan_entry(
    candidate_id: str,
    action_plan: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not isinstance(action_plan, dict) or not candidate_id:
        return None
    for plan_key in (
        "tier_1_immediate_implementation",
        "tier_2_implementation_with_validation",
        "tier_3_proceed_with_caution",
        "tier_4_insufficient_evidence",
    ):
        for item in action_plan.get(plan_key) or []:
            if isinstance(item, dict) and item.get("candidate_id") == candidate_id:
                return item
    return None


def get_validation_info(
    candidate: Dict[str, Any],
    action_plan: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Evaluate validation status and requirements independently of tier classification.
    """
    tier = normalize_tier(candidate)
    dim_key = normalize_dimension_key(candidate.get("dimension"))
    supp = candidate.get("supporting_evidence")
    req_val = bool(candidate.get("requires_validation", False))
    cid = str(candidate.get("candidate_id") or "")

    is_insufficient = (
        not supp
        or (isinstance(supp, dict) and supp.get("evidence_status") == "insufficient_evidence")
        or (isinstance(supp, str) and "insufficient" in supp.lower())
    )

    if is_insufficient:
        status = "Insufficient evidence"
    elif tier == "Tier 4":
        status = "Exploratory"
    elif req_val:
        status = "Requires validation"
    else:
        status = "Ready for consideration"

    plan_entry = _find_action_plan_entry(cid, action_plan)
    plan_req = plan_entry.get("validation_requirements") if isinstance(plan_entry, dict) else None

    if not req_val and not is_insufficient and tier != "Tier 4":
        requirement_text = "Not required"
    elif is_insufficient:
        requirement_text = (
            (plan_entry.get("observation_recommendation") if isinstance(plan_entry, dict) else None)
            or "Collect additional empirical runtime traces before implementation."
        )
    elif dim_key == "model_selection":
        requirement_text = (
            "Requires shadow testing against baseline execution traces to verify "
            "output schema accuracy and domain edge cases on the compact model."
        )
    elif dim_key == "communication_data_handoff":
        requirement_text = (
            "Requires shadow validation that downstream agents retain all necessary "
            "information under the compact handoff payload schema."
        )
    elif dim_key in ("agent_consolidation", "prompt_optimization"):
        requirement_text = (
            "Requires regression validation against baseline execution traces to ensure "
            "all schemas, constraints, and responsibilities remain intact."
        )
    elif plan_req:
        requirement_text = str(plan_req)
    else:
        requirement_text = "Requires shadow execution testing against baseline traces prior to deployment."

    return {
        "requires_validation": req_val,
        "is_insufficient_evidence": is_insufficient,
        "is_exploratory": tier == "Tier 4",
        "validation_status": status,
        "validation_requirement": requirement_text,
    }


def get_risk_info(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """
    Determine whether candidate has explicitly identified unresolved risks requiring
    user acknowledgement prior to approval.
    """
    tier = normalize_tier(candidate)
    risks = candidate.get("tradeoffs_and_risks") or {}
    quality_risk = str(risks.get("output_quality_risk") or "Not available")
    complexity = str(risks.get("implementation_complexity") or "Not available")
    latency_tradeoff = str(risks.get("latency_tradeoff") or "Not available")
    token_cost_tradeoff = str(risks.get("token_cost_tradeoff") or "Not available")
    shared_storage_dep = bool(risks.get("shared_storage_reference_dependency", False))
    explicit_unresolved = candidate.get("unresolved_risks")

    q_lower = quality_risk.lower()
    has_quality_risk = any(term in q_lower for term in ("moderate", "high", "elevated", "severe"))
    has_explicit_unresolved = bool(explicit_unresolved)
    is_tier_3 = tier == "Tier 3"

    has_explicit_risk = has_quality_risk or has_explicit_unresolved or shared_storage_dep or is_tier_3

    risk_reasons: List[str] = []
    if has_quality_risk:
        risk_reasons.append(f"Output quality risk: {quality_risk}")
    if shared_storage_dep:
        risk_reasons.append("Depends on shared storage reference resolution.")
    if is_tier_3:
        risk_reasons.append("Classified as Tier 3 (elevated architectural or quality trade-off).")
    if isinstance(explicit_unresolved, list) and explicit_unresolved:
        risk_reasons.extend(str(item) for item in explicit_unresolved)
    elif isinstance(explicit_unresolved, str) and explicit_unresolved.strip():
        risk_reasons.append(explicit_unresolved.strip())

    return {
        "has_explicit_risk": has_explicit_risk,
        "requires_risk_acknowledgement": has_explicit_risk,
        "output_quality_risk": quality_risk,
        "implementation_complexity": complexity,
        "latency_tradeoff": latency_tradeoff,
        "token_cost_tradeoff": token_cost_tradeoff,
        "shared_storage_reference_dependency": shared_storage_dep,
        "risk_summary": "; ".join(risk_reasons) if risk_reasons else f"Output quality risk: {quality_risk}",
    }


def _fmt_metric(value: Any, suffix: str = "") -> str:
    if value is None or value == "":
        return "Not available"
    return f"{value}{suffix}"


def _extract_confidence(candidate: Dict[str, Any]) -> Any:
    if candidate.get("confidence") is not None:
        return candidate["confidence"]
    supp = candidate.get("supporting_evidence") or {}
    if not isinstance(supp, dict):
        return "Not available"
    if supp.get("confidence") is not None:
        return supp["confidence"]
    groq_sem = supp.get("groq_semantic_analysis")
    if isinstance(groq_sem, dict):
        val_res = groq_sem.get("validated_result")
        if isinstance(val_res, dict) and val_res.get("confidence") is not None:
            return val_res["confidence"]
    return "Not available"


def build_candidate_card_view(
    candidate: Dict[str, Any],
    action_plan: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build a read-only, display-ready view dictionary covering sections A-E plus
    handoff/model/prompt specialized details without inventing missing fields.
    """
    dim_key = normalize_dimension_key(candidate.get("dimension"))
    dim_label = get_dimension_label(dim_key)
    tier = normalize_tier(candidate)
    cand_type = classify_candidate_type(candidate)
    val_info = get_validation_info(candidate, action_plan=action_plan)
    risk_info = get_risk_info(candidate)

    supp = candidate.get("supporting_evidence")
    supp_dict = supp if isinstance(supp, dict) else {}
    benefit = candidate.get("expected_benefit")
    benefit_dict = benefit if isinstance(benefit, dict) else {}
    target_agents = list(candidate.get("target_agents") or [])

    # Section D: Expected benefits (strictly projected; never fabricated)
    if "latency_savings_pct" in benefit_dict:
        lat_txt = f"{benefit_dict['latency_savings_pct']}%"
        if benefit_dict.get("latency_savings_seconds") is not None:
            lat_txt += f" ({benefit_dict['latency_savings_seconds']}s)"
    elif benefit_dict.get("latency_savings_seconds") is not None:
        lat_txt = f"{benefit_dict['latency_savings_seconds']}s"
    else:
        lat_txt = "Not available"

    if "token_savings_pct" in benefit_dict:
        tok_txt = f"{benefit_dict['token_savings_pct']}%"
        if benefit_dict.get("tokens_saved_per_handoff") is not None:
            tok_txt += f" ({benefit_dict['tokens_saved_per_handoff']} tokens/handoff)"
        elif benefit_dict.get("tokens_saved") is not None:
            tok_txt += f" ({benefit_dict['tokens_saved']} tokens)"
    elif benefit_dict.get("tokens_saved") is not None:
        tok_txt = f"{benefit_dict['tokens_saved']} tokens"
    else:
        tok_txt = "Not available"

    if benefit_dict.get("cost_savings_pct") is not None:
        cost_txt = f"{benefit_dict['cost_savings_pct']}%"
    else:
        cost_txt = "Not available"

    other_benefits: List[str] = []
    for k in ("critical_path_impact", "quality_impact", "byte_savings_pct", "measurement_type"):
        if benefit_dict.get(k) not in (None, ""):
            suffix = "%" if k == "byte_savings_pct" else ""
            other_benefits.append(f"{k}: {benefit_dict[k]}{suffix}")

    evidence_quality = _fmt_metric(
        supp_dict.get("evidence_quality")
        or supp_dict.get("evidence_basis")
        or ("mcp_grounded" if supp_dict.get("mcp_stage_source") else None)
    )

    view: Dict[str, Any] = {
        "candidate_type": cand_type,
        "identification": {
            "candidate_id": candidate.get("candidate_id") or "Not available",
            "title": candidate.get("title") or "Untitled Candidate",
            "dimension_key": dim_key,
            "dimension_label": dim_label,
            "tier": tier,
            "feasibility_tier": candidate.get("feasibility_tier") or tier,
            "target_agents": target_agents,
        },
        "observed_problem": {
            "description": candidate.get("observed_problem") or "Not available",
            "measured_evidence": supp if supp else "Not available",
        },
        "proposed_optimization": {
            "proposed_solution": candidate.get("proposed_solution") or "Not available",
            "affected_agents": target_agents,
        },
        "expected_benefits": {
            "projected_latency_improvement": lat_txt,
            "projected_token_savings": tok_txt,
            "projected_cost_savings": cost_txt,
            "other_benefits": other_benefits,
        },
        "evidence_and_validation": {
            "evidence_quality": evidence_quality,
            "validation_status": val_info["validation_status"],
            "requires_validation": val_info["requires_validation"],
            "is_exploratory": val_info["is_exploratory"],
            "is_insufficient_evidence": val_info["is_insufficient_evidence"],
            "validation_requirement": val_info["validation_requirement"],
            "confidence": _extract_confidence(candidate),
            "output_quality_risk": risk_info["output_quality_risk"],
            "implementation_complexity": risk_info["implementation_complexity"],
            "risk_info": risk_info,
        },
    }

    if cand_type == "handoff":
        view["handoff_details"] = {
            "producer_agent": supp_dict.get("producer_agent") or (target_agents[0] if len(target_agents) >= 1 else "Not available"),
            "consumer_agent": supp_dict.get("consumer_agent") or (target_agents[1] if len(target_agents) >= 2 else "Not available"),
            "original_payload_tokens": _fmt_metric(supp_dict.get("original_payload_tokens"), " tokens"),
            "proposed_payload_tokens": _fmt_metric(supp_dict.get("proposed_payload_tokens"), " tokens"),
            "estimated_tokens_saved": _fmt_metric(supp_dict.get("tokens_saved"), " tokens"),
            "savings_percentage": _fmt_metric(supp_dict.get("savings_percentage"), "%"),
            "original_payload": supp_dict.get("original_payload_sample") if supp_dict.get("original_payload_sample") is not None else "Not available",
            "proposed_payload": supp_dict.get("proposed_compact_payload_sample") if supp_dict.get("proposed_compact_payload_sample") is not None else "Not available",
            "fields_removed": list(supp_dict.get("fields_excluded") or []),
            "fields_retained": list(supp_dict.get("fields_retained") or []),
        }

    if dim_key == "model_selection":
        view["model_selection_details"] = {
            "current_model": supp_dict.get("current_model") or "Not available",
            "selected_model": candidate.get("selected_model")
            or supp_dict.get("selected_model")
            or supp_dict.get("jev_selected_model")
            or "Not available",
            "selection_source": candidate.get("selection_source")
            or supp_dict.get("selection_source")
            or "Not available",
            "proposed_models": list(supp_dict.get("proposed_candidate_models") or []),
            "task_complexity": supp_dict.get("task_complexity") or "Not available",
            "validation_requirement": val_info["validation_requirement"],
        }

    if candidate.get("unified_prompt"):
        view["prompt_artifact"] = {
            "kind": "unified_prompt",
            "content": candidate["unified_prompt"],
        }
    elif candidate.get("optimized_prompt"):
        view["prompt_artifact"] = {
            "kind": "optimized_prompt",
            "content": candidate["optimized_prompt"],
        }

    return view
