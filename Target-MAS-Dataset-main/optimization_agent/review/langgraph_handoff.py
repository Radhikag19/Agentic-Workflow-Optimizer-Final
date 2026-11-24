"""
Minimal Deterministic LangGraph Pause/Resume and Approval Handoff Mechanism.

Logical sequence:
S1..S10 (MCP Retrieval) -> S11 (Discovery) -> S12 (Trade-off Assessment)
-> S13 (Report Generation) -> User Candidate Review -> Approval -> Next Stage Handoff.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, Optional, Sequence

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
from optimization_agent.review.session import CandidateReviewSession
from optimization_agent.state import OptimizationAgentState
from optimization_agent.tradeoff import tradeoff_assessment


def _build_session_from_state(state: OptimizationAgentState) -> CandidateReviewSession:
    final_report = state.get("final_report") or {}
    if isinstance(final_report, dict) and (
        final_report.get("report_metadata") or final_report.get("workflow_baseline")
    ):
        return CandidateReviewSession.from_report(final_report)

    wf_id = str(state.get("workflow_id") or "").strip()
    cands = list(state.get("optimization_candidates") or [])
    return CandidateReviewSession(workflow_id=wf_id, candidates=cands, report_data=final_report)


def prepare_candidate_review_node(state: OptimizationAgentState) -> Dict[str, Any]:
    """
    Build deterministic review inventory, dimension counts, and default preselection
    from the Stage 13 report without mutating candidates or auto-approving.
    """
    track_status = dict(state.get("stage_status") or {})
    retrieval_errors = list(state.get("retrieval_errors") or [])

    try:
        session = _build_session_from_state(state)
        review_payload = {
            "workflow_id": session.workflow_id,
            "summary": session.get_workflow_summary(),
            "dimension_counts": session.get_dimension_counts(),
            "default_preselected_candidate_ids": list(session.eligible_candidate_ids),
            "exploratory_tier_4_candidate_ids": list(session.exploratory_candidate_ids),
            "selection_summary": session.get_selection_summary(),
        }
        track_status["prepare_candidate_review"] = "completed"
        return {
            "stage_status": track_status,
            "candidate_review_session": review_payload,
            "approval_status": "pending_user_review",
        }
    except Exception as e:
        track_status["prepare_candidate_review"] = "failed"
        retrieval_errors.append({"stage": "prepare_candidate_review", "error": str(e)})
        return {
            "stage_status": track_status,
            "retrieval_errors": retrieval_errors,
            "approval_status": "error",
        }


def apply_user_approval_node(state: OptimizationAgentState) -> Dict[str, Any]:
    """
    Validate and record user's explicit candidate selection & risk acknowledgements,
    producing the Approved Optimization Scope without mutating workflow code.
    """
    track_status = dict(state.get("stage_status") or {})
    retrieval_errors = list(state.get("retrieval_errors") or [])
    decision = state.get("user_approval_decision")

    if not isinstance(decision, dict):
        msg = "Missing user_approval_decision payload; approval rejected."
        track_status["apply_user_approval"] = "rejected"
        retrieval_errors.append({"stage": "apply_user_approval", "error": msg})
        return {
            "stage_status": track_status,
            "retrieval_errors": retrieval_errors,
            "approval_status": "rejected",
            "approved_candidates": [],
            "approved_optimization_scope": {},
        }

    try:
        session = _build_session_from_state(state)
        decision_wf = decision.get("workflow_id")
        if decision_wf is not None and str(decision_wf).strip() != session.workflow_id:
            raise ValueError(
                f"Workflow isolation violation: decision for '{decision_wf}' cannot approve "
                f"candidates for '{session.workflow_id}'."
            )

        selected_ids = list(decision.get("selected_candidate_ids") or [])
        ack_ids = list(decision.get("risk_acknowledged_candidate_ids") or [])

        # Validate every ID explicitly against current workflow inventory
        session.clear_selection()
        for cid in selected_ids:
            session.select_candidate(cid)
        for cid in ack_ids:
            session.acknowledge_risk(cid, acknowledged=True)

        scope = session.approve(
            expected_workflow_id=decision_wf or session.workflow_id,
            persist=bool(decision.get("persist", True)),
            output_dir=decision.get("output_dir"),
        )
        track_status["apply_user_approval"] = "completed"
        return {
            "stage_status": track_status,
            "approval_status": "approved",
            "approved_optimization_scope": scope,
            "approved_candidates": copy.deepcopy(scope["approved_candidates"]),
        }
    except Exception as e:
        track_status["apply_user_approval"] = "rejected"
        retrieval_errors.append({"stage": "apply_user_approval", "error": str(e)})
        return {
            "stage_status": track_status,
            "retrieval_errors": retrieval_errors,
            "approval_status": "rejected",
            "approved_candidates": [],
            "approved_optimization_scope": {},
        }


def handoff_approved_scope_to_next_stage(approved_scope: Dict[str, Any]) -> Dict[str, Any]:
    """
    Construct the deterministic downstream stage payload strictly from the
    user-approved scope. Never executes mutations or optimization experiments.
    """
    if not isinstance(approved_scope, dict) or approved_scope.get("approval_status") != "approved":
        raise ValueError("Cannot hand off to next optimization stage without an approved scope.")

    approved_candidates = copy.deepcopy(approved_scope.get("approved_candidates") or [])
    if not approved_candidates:
        raise ValueError("Approved scope contains zero candidate objects.")

    wf_id = str(approved_scope.get("workflow_id") or "").strip()
    if not wf_id:
        raise ValueError("Approved scope is missing workflow_id.")

    return {
        "workflow_id": wf_id,
        "approval_status": "approved",
        "selected_dimensions": list(approved_scope.get("selected_dimensions") or []),
        "approved_candidate_count": len(approved_candidates),
        "approved_candidate_ids": list(approved_scope.get("approved_candidate_ids") or []),
        "approved_candidates": approved_candidates,
        "approved_optimization_scope": copy.deepcopy(approved_scope),
        "ready_for_downstream_execution": True,
        "workflow_mutated": False,
    }


def next_optimization_stage_handoff_node(state: OptimizationAgentState) -> Dict[str, Any]:
    """
    Deterministic LangGraph node receiving ONLY the user-approved candidate objects.
    Performs no workflow modification or optimization experiments.
    """
    track_status = dict(state.get("stage_status") or {})
    retrieval_errors = list(state.get("retrieval_errors") or [])

    scope = state.get("approved_optimization_scope") or {}
    if state.get("approval_status") != "approved" or not isinstance(scope, dict) or not scope:
        track_status["next_optimization_stage_handoff"] = "skipped"
        return {
            "stage_status": track_status,
            "next_stage_input": {
                "workflow_id": state.get("workflow_id"),
                "approval_status": state.get("approval_status", "rejected"),
                "ready_for_downstream_execution": False,
                "approved_candidates": [],
                "workflow_mutated": False,
            },
        }

    try:
        if str(scope.get("workflow_id") or "") != str(state.get("workflow_id") or ""):
            raise ValueError("Workflow mismatch between state and approved_optimization_scope.")

        handoff_payload = handoff_approved_scope_to_next_stage(scope)
        track_status["next_optimization_stage_handoff"] = "completed"
        return {
            "stage_status": track_status,
            "next_stage_input": handoff_payload,
        }
    except Exception as e:
        track_status["next_optimization_stage_handoff"] = "failed"
        retrieval_errors.append({"stage": "next_optimization_stage_handoff", "error": str(e)})
        return {
            "stage_status": track_status,
            "retrieval_errors": retrieval_errors,
            "next_stage_input": {"ready_for_downstream_execution": False, "error": str(e)},
        }


def build_optimization_graph_with_approval(checkpointer: Optional[Any] = None) -> Any:
    """
    Build the full optimization discovery + human review/approval LangGraph pipeline:
    Stages 1-13 -> prepare_candidate_review -> [interrupt for user selection]
    -> apply_user_approval -> next_optimization_stage_handoff -> END.
    """
    builder = StateGraph(OptimizationAgentState)

    # Preserve Stages 1 to 13 identically
    builder.add_node("stage_1_discovery", stage_1_discovery)
    builder.add_node("stage_2_overview", stage_2_overview)
    builder.add_node("stage_3_graph", stage_3_graph)
    builder.add_node("stage_4_profiles", stage_4_profiles)
    builder.add_node("stage_5_prompts", stage_5_prompts)
    builder.add_node("stage_6_latency", stage_6_latency)
    builder.add_node("stage_7_tokens", stage_7_tokens)
    builder.add_node("stage_8_cost", stage_8_cost)
    builder.add_node("stage_9_comparison", stage_9_comparison)
    builder.add_node("stage_10_evidence", stage_10_evidence)
    builder.add_node("discovery_analysis", discovery_analysis)
    builder.add_node("tradeoff_assessment", tradeoff_assessment)
    builder.add_node("generate_report", generate_report)

    # Add deterministic review, approval, and handoff nodes
    builder.add_node("prepare_candidate_review", prepare_candidate_review_node)
    builder.add_node("apply_user_approval", apply_user_approval_node)
    builder.add_node("next_optimization_stage_handoff", next_optimization_stage_handoff_node)

    builder.add_edge(START, "stage_1_discovery")
    builder.add_edge("stage_1_discovery", "stage_2_overview")
    builder.add_edge("stage_2_overview", "stage_3_graph")
    builder.add_edge("stage_3_graph", "stage_4_profiles")
    builder.add_edge("stage_4_profiles", "stage_5_prompts")
    builder.add_edge("stage_5_prompts", "stage_6_latency")
    builder.add_edge("stage_6_latency", "stage_7_tokens")
    builder.add_edge("stage_7_tokens", "stage_8_cost")
    builder.add_edge("stage_8_cost", "stage_9_comparison")
    builder.add_edge("stage_9_comparison", "stage_10_evidence")
    builder.add_edge("stage_10_evidence", "discovery_analysis")
    builder.add_edge("discovery_analysis", "tradeoff_assessment")
    builder.add_edge("tradeoff_assessment", "generate_report")

    builder.add_edge("generate_report", "prepare_candidate_review")
    builder.add_edge("prepare_candidate_review", "apply_user_approval")
    builder.add_edge("apply_user_approval", "next_optimization_stage_handoff")
    builder.add_edge("next_optimization_stage_handoff", END)

    cp = checkpointer if checkpointer is not None else MemorySaver()
    return builder.compile(checkpointer=cp, interrupt_before=["apply_user_approval"])


def resume_graph_with_approval(
    compiled_graph: Any,
    config: Dict[str, Any],
    workflow_id: str,
    selected_candidate_ids: Sequence[str],
    risk_acknowledged_candidate_ids: Sequence[str] = (),
    persist: bool = True,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Inject the user's explicit candidate approval decision into a paused LangGraph
    thread and resume execution through approval and downstream handoff.
    """
    snapshot = compiled_graph.get_state(config)
    paused_values = snapshot.values if hasattr(snapshot, "values") else {}
    paused_wf = str(paused_values.get("workflow_id") or "").strip()
    if paused_wf and paused_wf != workflow_id:
        raise ValueError(
            f"Workflow isolation violation: paused thread is for '{paused_wf}', "
            f"cannot apply approval for '{workflow_id}'."
        )

    decision = {
        "workflow_id": workflow_id,
        "selected_candidate_ids": list(selected_candidate_ids),
        "risk_acknowledged_candidate_ids": list(risk_acknowledged_candidate_ids),
        "persist": persist,
        "output_dir": output_dir,
    }
    compiled_graph.update_state(config, {"user_approval_decision": decision})
    return compiled_graph.invoke(None, config)
