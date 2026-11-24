"""
Streamlit UI Component for Candidate Review, Dimension Filtering,
Individual Selection, Risk Acknowledgement, and Final User Approval.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import streamlit as st

from optimization_agent.review.langgraph_handoff import handoff_approved_scope_to_next_stage
from optimization_agent.review.models import TIER_ORDER
from optimization_agent.review.session import CandidateReviewSession

_TYPE_LABELS = {
    "agent": "Agent-Level",
    "multi_agent": "Multi-Agent",
    "handoff": "Agent-to-Agent Handoff",
    "workflow": "Workflow-Level",
}


def _report_signature(workflow_id: str, report_data: Dict[str, Any]) -> str:
    meta = report_data.get("report_metadata") or {}
    return f"{workflow_id}:{meta.get('timestamp', '')}:{meta.get('total_optimization_candidates_found', '')}"


def _sync_widget_keys_from_session(session: CandidateReviewSession) -> None:
    wf = session.workflow_id
    for cand in session.candidates:
        cid = str(cand.get("candidate_id") or "")
        st.session_state[f"rev_sel_{wf}_{cid}"] = cid in session.selected_candidate_ids
        st.session_state[f"rev_risk_{wf}_{cid}"] = cid in session.risk_acknowledged_candidate_ids


def _get_or_init_review_session(workflow_id: str, report_data: Dict[str, Any]) -> CandidateReviewSession:
    sig_key = f"rev_sig_{workflow_id}"
    sess_key = f"rev_session_{workflow_id}"
    sig = _report_signature(workflow_id, report_data)

    if sess_key not in st.session_state or st.session_state.get(sig_key) != sig:
        session = CandidateReviewSession.from_report(report_data)
        st.session_state[sess_key] = session
        st.session_state[sig_key] = sig
        st.session_state[f"rev_filter_{workflow_id}"] = []
        st.session_state.pop(f"rev_handoff_{workflow_id}", None)
        _sync_widget_keys_from_session(session)

    return st.session_state[sess_key]


def _render_candidate_card(
    session: CandidateReviewSession,
    cand: Dict[str, Any],
    *,
    is_exploratory_section: bool = False,
) -> None:
    wf = session.workflow_id
    cid = str(cand.get("candidate_id") or "")
    card = session.get_candidate_card(cid)
    ident = card["identification"]
    obs = card["observed_problem"]
    prop = card["proposed_optimization"]
    ben = card["expected_benefits"]
    ev_val = card["evidence_and_validation"]
    risk_info = ev_val["risk_info"]
    ctype = card["candidate_type"]
    ctype_label = _TYPE_LABELS.get(ctype, ctype)

    sel_key = f"rev_sel_{wf}_{cid}"
    if sel_key not in st.session_state:
        st.session_state[sel_key] = cid in session.selected_candidate_ids

    risk_key = f"rev_risk_{wf}_{cid}"
    if risk_key not in st.session_state:
        st.session_state[risk_key] = cid in session.risk_acknowledged_candidate_ids

    with st.container(border=True):
        top_c1, top_c2 = st.columns([4, 2])
        with top_c1:
            is_selected = st.checkbox(
                f"**{ident['title']}** (`{ident['candidate_id']}`)",
                key=sel_key,
            )
            session.set_candidate_selected(cid, bool(is_selected))

        with top_c2:
            st.caption(
                f"Tier: **{ident['tier']}** | Status: **{ev_val['validation_status']}** | Scope: **{ctype_label}**"
            )

        # Section A: Candidate Identification
        targets_str = ", ".join(f"`{t}`" for t in ident["target_agents"]) if ident["target_agents"] else "Not available"
        st.markdown(
            f"**A. Identification:** Dimension: `{ident['dimension_label']}` | "
            f"Candidate ID: `{ident['candidate_id']}` | Tier: `{ident['tier']}` | Target Agents: {targets_str}"
        )

        # Section B: Observed Problem
        st.markdown(f"**B. Observed Problem:** {obs['description']}")

        # Section C: Proposed Optimization
        st.markdown(f"**C. Proposed Optimization:** {prop['proposed_solution']}")

        # Specialized Type Views
        if "handoff_details" in card:
            hd = card["handoff_details"]
            removed_str = ", ".join(f"`{f}`" for f in hd["fields_removed"]) or "None"
            retained_str = ", ".join(f"`{f}`" for f in hd["fields_retained"]) or "None"
            st.markdown(
                f"- **Handoff Route:** `{hd['producer_agent']}` -> `{hd['consumer_agent']}` | "
                f"**Payload Tokens:** {hd['original_payload_tokens']} -> {hd['proposed_payload_tokens']} "
                f"(Estimated savings: {hd['estimated_tokens_saved']} / {hd['savings_percentage']})"
            )
            st.markdown(f"- **Fields Removed:** {removed_str}")
            st.markdown(f"- **Fields Retained:** {retained_str}")
            with st.expander(f"Inspect Original vs. Proposed Handoff Payloads ({cid})", expanded=False):
                pcol1, pcol2 = st.columns(2)
                with pcol1:
                    st.caption("Original Payload Sample")
                    if isinstance(hd["original_payload"], dict):
                        st.json(hd["original_payload"])
                    else:
                        st.write(hd["original_payload"])
                with pcol2:
                    st.caption("Proposed Compact Payload Sample")
                    if isinstance(hd["proposed_payload"], dict):
                        st.json(hd["proposed_payload"])
                    else:
                        st.write(hd["proposed_payload"])

        if "model_selection_details" in card:
            msd = card["model_selection_details"]
            proposed_str = ", ".join(f"`{m}`" for m in msd["proposed_models"]) if msd["proposed_models"] else "Not available"
            st.markdown(
                f"- **Model Routing Details:** Current Model: `{msd['current_model']}` | "
                f"Proposed Model(s): {proposed_str} | Task Complexity: `{msd['task_complexity']}`"
            )

        if "prompt_artifact" in card:
            pa = card["prompt_artifact"]
            with st.expander(f"Inspect `{pa['kind']}` ({cid})", expanded=False):
                st.code(pa["content"], language="text")

        # Section D: Expected Benefits (Strictly Projected)
        st.markdown(
            f"**D. Expected Benefits (Projected Only):** "
            f"Latency: **{ben['projected_latency_improvement']}** | "
            f"Tokens: **{ben['projected_token_savings']}** | "
            f"Cost: **{ben['projected_cost_savings']}**"
        )
        if ben["other_benefits"]:
            st.caption("Additional projected notes: " + " | ".join(ben["other_benefits"]))

        # Section E: Evidence & Validation
        st.markdown(
            f"**E. Evidence & Validation:** "
            f"Evidence Quality: `{ev_val['evidence_quality']}` | "
            f"Validation Status: `{ev_val['validation_status']}` | "
            f"Confidence: `{ev_val['confidence']}` | "
            f"Quality Risk: `{ev_val['output_quality_risk']}` | "
            f"Complexity: `{ev_val['implementation_complexity']}`"
        )

        if ev_val["requires_validation"] or ev_val["is_exploratory"] or ev_val["is_insufficient_evidence"]:
            st.warning(f"**Validation Requirement:** {ev_val['validation_requirement']}")

        if risk_info["requires_risk_acknowledgement"]:
            if bool(is_selected):
                ack_val = st.checkbox(
                    f"Acknowledge explicit risk for `{cid}` ({risk_info['risk_summary']})",
                    key=risk_key,
                )
                session.acknowledge_risk(cid, acknowledged=bool(ack_val))
            else:
                st.caption(f"Identified Risk Note: {risk_info['risk_summary']}")

        with st.expander(f"Inspect Measured Evidence & Trade-Offs ({cid})", expanded=False):
            if isinstance(obs["measured_evidence"], dict):
                st.json(obs["measured_evidence"])
            else:
                st.write(obs["measured_evidence"])
            st.json(cand.get("tradeoffs_and_risks") or {"note": "Not available"})


def render_candidate_review_interface(
    workflow_id: str,
    report_data: Dict[str, Any],
    reports_dir: Optional[Path] = None,
) -> None:
    """Render the full Candidate Review, Filtering, Selection, and Approval interface."""
    if not report_data:
        st.info(f"No optimization report loaded for workflow '{workflow_id}'.")
        return

    session = _get_or_init_review_session(workflow_id, report_data)
    wf = session.workflow_id
    wf_summary = session.get_workflow_summary()
    dim_counts = session.get_dimension_counts()

    # ------------------------------------------------------------------
    # 1. Workflow Summary Header
    # ------------------------------------------------------------------
    st.markdown(f"### Workflow: `{wf}`")
    st.caption(
        "Review discovered optimization opportunities, inspect supporting evidence and risks, "
        "select specific candidates, and authorize the approved scope for the next pipeline stage. "
        "Approval records scope only and does not modify source files or execute experiments."
    )

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Total Candidates", wf_summary["total_candidates"])
    m2.metric("Tier 1", wf_summary["tier_1_count"])
    m3.metric("Tier 2", wf_summary["tier_2_count"])
    m4.metric("Tier 3", wf_summary["tier_3_count"])
    m5.metric("Tier 4 (Exploratory)", wf_summary["tier_4_count"])
    m6.metric(
        "Dimensions with Candidates",
        f"{wf_summary['dimensions_with_candidates']} / {wf_summary['total_dimensions']}",
    )

    st.divider()

    # ------------------------------------------------------------------
    # 2. Optimization Dimension Filter
    # ------------------------------------------------------------------
    st.markdown("#### Optimization Dimension Filter")
    dim_option_keys = [d["dimension_key"] for d in dim_counts]
    dim_format_map = {d["dimension_key"]: f"{d['label']} ({d['count']})" for d in dim_counts}

    filter_key = f"rev_filter_{wf}"
    fcol1, fcol2 = st.columns([4, 1])
    with fcol1:
        chosen_dims = st.multiselect(
            "Filter by Optimization Dimension (leave empty to display all dimensions)",
            options=dim_option_keys,
            format_func=lambda k: dim_format_map.get(k, k),
            key=filter_key,
        )
    with fcol2:
        st.write("")
        st.write("")
        if st.button("Reset Filter", key=f"rev_reset_filter_{wf}", use_container_width=True):
            st.session_state[filter_key] = []
            session.reset_dimension_filter()
            st.rerun()

    session.set_dimension_filter(chosen_dims)

    # ------------------------------------------------------------------
    # 3. Render Grouped Candidate Cards (Tiers 1-3)
    # ------------------------------------------------------------------
    grouped_sections = session.get_grouped_filtered_candidates(include_tier_4=False)
    for group in grouped_sections:
        cands = group["candidates"]
        # When no filter is active, still display dimension header when it has candidates,
        # OR show empty state explicitly if user selected specific dimensions.
        if chosen_dims or cands:
            st.markdown(f"#### {group['label']} ({len(cands)} candidate{'s' if len(cands) != 1 else ''})")
            if not cands:
                st.info(group["empty_state_message"] or f"No candidates found for {group['label']}.")
            else:
                for cand in cands:
                    _render_candidate_card(session, cand, is_exploratory_section=False)

    # Separate Exploratory Tier 4 section
    tier_4_cands = session.get_tier_4_exploratory_candidates()
    if tier_4_cands:
        st.divider()
        st.markdown(f"#### Exploratory Opportunities — Tier 4 ({len(tier_4_cands)} — Not Preselected)")
        st.caption(
            "Tier 4 candidates lack sufficient empirical evidence and are excluded from default preselection."
        )
        for cand in tier_4_cands:
            _render_candidate_card(session, cand, is_exploratory_section=True)

    st.divider()

    # ------------------------------------------------------------------
    # 4. Live Selection Summary & Quick Actions (Computed AFTER checkboxes)
    # ------------------------------------------------------------------
    sel_summary = session.get_selection_summary()

    st.markdown("#### Live Selection Summary")
    s1, s2, s3, s4, s5 = st.columns(5)
    s1.metric("Total Discovered", sel_summary["total_discovered"])
    s2.metric("Currently Selected", sel_summary["selected_count"])
    s3.metric("Requires Validation", sel_summary["selected_requiring_validation"])
    s4.metric("Explicitly Identified Risks", sel_summary["selected_with_explicit_risks"])
    s5.metric("Unacknowledged Risks", sel_summary["unacknowledged_risk_count"])

    tier_breakdown = " | ".join(
        f"{t}: {sel_summary['selected_by_tier'].get(t, 0)}" for t in TIER_ORDER
    )
    dim_breakdown = " | ".join(
        f"{d['label']}: {sel_summary['selected_by_dimension'].get(d['dimension_key'], 0)}"
        for d in dim_counts
        if sel_summary["selected_by_dimension"].get(d["dimension_key"], 0) > 0
    ) or "None selected"
    st.caption(f"**Selected by Tier:** {tier_breakdown}")
    st.caption(f"**Selected by Dimension:** {dim_breakdown}")
    st.caption(
        "Note: Preselection and bulk selection actions do not approve candidates. "
        "Do not sum candidate-level projected savings as guaranteed cumulative workflow savings."
    )

    act_c1, act_c2, act_c3 = st.columns([1, 1, 2])
    with act_c1:
        if st.button("Select All Eligible", key=f"rev_sel_all_{wf}", use_container_width=True):
            session.select_all_eligible()
            _sync_widget_keys_from_session(session)
            st.rerun()
    with act_c2:
        if st.button("Clear Selection", key=f"rev_clear_{wf}", use_container_width=True):
            session.clear_selection()
            _sync_widget_keys_from_session(session)
            st.rerun()
    with act_c3:
        approve_clicked = st.button(
            "Approve Selected Optimization Candidates",
            type="primary",
            key=f"rev_approve_{wf}",
            use_container_width=True,
        )

    # ------------------------------------------------------------------
    # 5. Final Approval Action & Handoff Output
    # ------------------------------------------------------------------
    if approve_clicked:
        readiness = session.validate_approval_readiness(expected_workflow_id=wf)
        if not readiness["ready"]:
            for err in readiness["errors"]:
                st.error(err)
        else:
            scope = session.approve(
                expected_workflow_id=wf,
                persist=True,
                output_dir=reports_dir,
            )
            handoff_payload = handoff_approved_scope_to_next_stage(scope)
            st.session_state[f"rev_handoff_{wf}"] = handoff_payload
            st.success(
                f"Approved {len(scope['approved_candidate_ids'])} optimization candidate(s) for `{wf}` "
                "and passed the approved scope to the next optimization stage. "
                "No source files were mutated and no experiments were executed."
            )

    saved_handoff = st.session_state.get(f"rev_handoff_{wf}")
    if saved_handoff:
        scope = saved_handoff["approved_optimization_scope"]
        with st.expander("Approved Optimization Scope JSON", expanded=True):
            st.json(scope)
            st.download_button(
                "Download Approved Optimization Scope JSON",
                data=json.dumps(scope, indent=2),
                file_name=f"{wf}_approved_optimization_scope.json",
                mime="application/json",
                key=f"rev_dl_scope_{wf}",
            )
