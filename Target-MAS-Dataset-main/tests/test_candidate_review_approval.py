"""
Comprehensive Validation Suite for Candidate Review, User Selection, and Approval
across the 5 active optimization dimensions:
- Agent Consolidation
- Workflow Parallelization
- Model Selection
- Prompt Optimization
- Communication & Data-Handoff Optimization
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict

import pytest
from langgraph.checkpoint.memory import MemorySaver

from optimization_agent.agent import OptimizationDiscoveryAgent, build_optimization_graph
from optimization_agent.review import (
    CandidateReviewSession,
    build_optimization_graph_with_approval,
    resume_graph_with_approval,
)

REPO_REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
RECRUITMENT_REPORT_PATH = REPO_REPORTS_DIR / "recruitment_screening_optimization_report.json"
CONTRACT_REPORT_PATH = REPO_REPORTS_DIR / "contract_review_optimization_report.json"


@pytest.fixture
def recruitment_report() -> Dict[str, Any]:
    assert RECRUITMENT_REPORT_PATH.exists(), f"Missing report: {RECRUITMENT_REPORT_PATH}"
    return json.loads(RECRUITMENT_REPORT_PATH.read_text(encoding="utf-8"))


# =============================================================================
# Test 1: Report loading
# =============================================================================
def test_01_report_loading(recruitment_report: Dict[str, Any]):
    session = CandidateReviewSession.from_report(recruitment_report)
    summary = session.get_workflow_summary()

    assert summary["workflow_id"] == "recruitment_screening"
    assert summary["total_candidates"] == 12
    assert summary["tier_1_count"] == 1
    assert summary["tier_2_count"] == 11
    assert summary["tier_3_count"] == 0
    assert summary["tier_4_count"] == 0
    assert summary["dimensions_with_candidates"] == 3
    assert summary["total_dimensions"] == 5


# =============================================================================
# Test 2: Dimension counts
# =============================================================================
def test_02_dimension_counts(recruitment_report: Dict[str, Any]):
    session = CandidateReviewSession.from_report(recruitment_report)
    dim_counts = session.get_dimension_counts()

    assert len(dim_counts) == 5
    by_label = {d["label"]: d["count"] for d in dim_counts}
    assert by_label == {
        "Agent Consolidation": 0,
        "Workflow Parallelization": 1,
        "Model Selection": 1,
        "Prompt Optimization": 0,
        "Communication & Data-Handoff Optimization": 10,
    }


# =============================================================================
# Test 3: Default selection (Tiers 1-3 preselected; Tier 4 excluded)
# =============================================================================
def test_03_default_selection_and_tier_4_exclusion(recruitment_report: Dict[str, Any]):
    session = CandidateReviewSession.from_report(recruitment_report)
    assert len(session.selected_candidate_ids) == 12
    assert session.approval_status == "pending_user_review"
    assert session.approved_scope is None

    sel_sum = session.get_selection_summary()
    assert sel_sum["selected_count"] == 12
    assert sel_sum["selected_by_tier"] == {"Tier 1": 1, "Tier 2": 11, "Tier 3": 0, "Tier 4": 0}

    # Synthetic multi-tier report verifying Tier 3 included & Tier 4 excluded
    synthetic_report = {
        "report_metadata": {"workflow_id": "multi_tier_wf"},
        "workflow_parallelization_opportunities": [
            {
                "candidate_id": "T1-CAND",
                "dimension": "workflow_parallelization",
                "title": "Tier 1 cand",
                "target_agents": ["a1", "a2"],
                "tier": "Tier 1",
                "requires_validation": False,
                "supporting_evidence": {"mcp_stage_source": ["stage_3"]},
                "tradeoffs_and_risks": {"output_quality_risk": "Low"},
            },
            {
                "candidate_id": "T3-CAND",
                "dimension": "workflow_parallelization",
                "title": "Tier 3 cand",
                "target_agents": ["a3", "a4"],
                "tier": "Tier 3",
                "requires_validation": True,
                "supporting_evidence": {"mcp_stage_source": ["stage_3"]},
                "tradeoffs_and_risks": {"output_quality_risk": "High"},
            },
        ],
        "model_selection_recommendations": [
            {
                "candidate_id": "T4-CAND",
                "dimension": "model_selection",
                "title": "Tier 4 exploratory cand",
                "target_agents": ["a5"],
                "tier": "Tier 4",
                "requires_validation": True,
                "supporting_evidence": {"evidence_status": "insufficient_evidence"},
                "tradeoffs_and_risks": {"output_quality_risk": "Moderate"},
            },
        ],
    }
    syn_session = CandidateReviewSession.from_report(synthetic_report)
    assert syn_session.selected_candidate_ids == {"T1-CAND", "T3-CAND"}
    assert syn_session.exploratory_candidate_ids == ["T4-CAND"]
    assert [c["candidate_id"] for c in syn_session.get_tier_4_exploratory_candidates()] == ["T4-CAND"]


# =============================================================================
# Test 4: Individual selection & bulk helpers
# =============================================================================
def test_04_individual_selection_and_bulk_actions(recruitment_report: Dict[str, Any]):
    session = CandidateReviewSession.from_report(recruitment_report)
    first_id = "PARALLEL-QUALIFICATION_AGENT-JOB_CRITERIA_AGENT"

    session.deselect_candidate(first_id)
    assert first_id not in session.selected_candidate_ids
    assert session.get_selection_summary()["selected_count"] == 11
    assert session.approval_status == "pending_user_review"

    session.select_candidate(first_id)
    assert first_id in session.selected_candidate_ids
    assert session.get_selection_summary()["selected_count"] == 12

    session.clear_selection()
    assert session.get_selection_summary()["selected_count"] == 0
    assert session.approval_status == "pending_user_review"

    session.select_all_eligible()
    assert session.get_selection_summary()["selected_count"] == 12
    assert session.approval_status == "pending_user_review"


# =============================================================================
# Test 5: Dimension filtering (non-destructive)
# =============================================================================
def test_05_dimension_filtering(recruitment_report: Dict[str, Any]):
    session = CandidateReviewSession.from_report(recruitment_report)
    orig_snapshot = copy.deepcopy(session.candidates)

    session.set_dimension_filter(["Communication & Data-Handoff Optimization"])
    filtered = session.get_filtered_candidates()
    assert len(filtered) == 10
    assert all(c["dimension"] == "communication_data_handoff" for c in filtered)

    # Underlying candidates & selections unchanged by filtering
    assert session.candidates == orig_snapshot
    assert len(session.selected_candidate_ids) == 12

    session.reset_dimension_filter()
    assert len(session.get_filtered_candidates()) == 12


# =============================================================================
# Test 6: Individual handoff selection (2 of 10)
# =============================================================================
def test_06_individual_handoff_selection(
    recruitment_report: Dict[str, Any],
    tmp_path: Path,
):
    session = CandidateReviewSession.from_report(recruitment_report)
    session.set_dimension_filter(["communication_data_handoff"])
    handoff_cands = session.get_filtered_candidates()
    assert len(handoff_cands) == 10

    chosen_two = [
        handoff_cands[0]["candidate_id"],
        handoff_cands[7]["candidate_id"],
    ]
    session.clear_selection()
    for cid in chosen_two:
        session.select_candidate(cid)
        session.acknowledge_risk(cid, True)

    scope = session.approve(persist=True, output_dir=tmp_path)
    assert scope["approved_candidate_ids"] == chosen_two
    assert len(scope["approved_candidates"]) == 2
    assert len(scope["excluded_candidate_ids"]) == 10
    assert scope["selected_dimensions"] == ["communication_data_handoff"]


# =============================================================================
# Test 7: Empty dimensions
# =============================================================================
def test_07_empty_dimensions(recruitment_report: Dict[str, Any]):
    session = CandidateReviewSession.from_report(recruitment_report)

    for empty_dim in ("agent_consolidation", "prompt_optimization"):
        session.set_dimension_filter([empty_dim])
        grouped = session.get_grouped_filtered_candidates()
        assert len(grouped) == 1
        assert grouped[0]["dimension_key"] == empty_dim
        assert grouped[0]["count"] == 0
        assert grouped[0]["candidates"] == []
        assert "No optimization candidates were discovered" in grouped[0]["empty_state_message"]


# =============================================================================
# Test 8: Validation status independent from tier
# =============================================================================
def test_08_validation_status_separate_from_tier(recruitment_report: Dict[str, Any]):
    session = CandidateReviewSession.from_report(recruitment_report)

    model_card = session.get_candidate_card("MODEL-RESUME_INTAKE_AGENT")
    assert model_card["identification"]["tier"] == "Tier 2"
    assert model_card["evidence_and_validation"]["validation_status"] == "Requires validation"
    assert "shadow testing" in model_card["evidence_and_validation"]["validation_requirement"].lower()
    assert "MODEL-RESUME_INTAKE_AGENT" in session.eligible_candidate_ids

    handoff_card = session.get_candidate_card("HANDOFF-RESUME_INTAKE_AGENT-TO-QUALIFICATION_AGENT")
    assert handoff_card["identification"]["tier"] == "Tier 2"
    assert handoff_card["evidence_and_validation"]["validation_status"] == "Requires validation"
    assert "downstream agents" in handoff_card["evidence_and_validation"]["validation_requirement"].lower()

    tier1_card = session.get_candidate_card("PARALLEL-QUALIFICATION_AGENT-JOB_CRITERIA_AGENT")
    assert tier1_card["identification"]["tier"] == "Tier 1"
    assert tier1_card["evidence_and_validation"]["validation_status"] == "Ready for consideration"


# =============================================================================
# Test 9: Different candidate types & missing-field handling
# =============================================================================
def test_09_different_candidate_types_and_missing_fields(recruitment_report: Dict[str, Any]):
    session = CandidateReviewSession.from_report(recruitment_report)

    # 1. Agent-level (Model Selection on single intake agent)
    model_card = session.get_candidate_card("MODEL-RESUME_INTAKE_AGENT")
    assert model_card["candidate_type"] == "agent"
    assert model_card["identification"]["target_agents"] == ["resume_intake_agent"]
    assert model_card["evidence_and_validation"]["confidence"] == "Not available"
    msd = model_card["model_selection_details"]
    assert msd["current_model"] == "openai/gpt-oss-120b"
    assert "openai/gpt-oss-20b" in msd["proposed_models"]
    assert "llama-3.3-70b-versatile" not in msd["proposed_models"]

    # 2. Multi-agent (Parallelization pair)
    multi_card = session.get_candidate_card("PARALLEL-QUALIFICATION_AGENT-JOB_CRITERIA_AGENT")
    assert multi_card["candidate_type"] == "multi_agent"
    assert multi_card["identification"]["target_agents"] == ["qualification_agent", "job_criteria_agent"]
    assert multi_card["expected_benefits"]["projected_cost_savings"] == "Not available"

    # 3. Handoff-level
    handoff_card = session.get_candidate_card("HANDOFF-EXPERIENCE_ASSESSMENT_AGENT-TO-SCREENING_REVIEW_AGENT")
    assert handoff_card["candidate_type"] == "handoff"
    hd = handoff_card["handoff_details"]
    assert hd["producer_agent"] == "experience_assessment_agent"
    assert hd["consumer_agent"] == "screening_review_agent"
    assert isinstance(hd["original_payload"], dict)
    assert isinstance(hd["proposed_payload"], dict)
    assert hd["fields_removed"] == ["relevance_summary", "transferable_skills"]
    assert "strengths" in hd["fields_retained"]
    assert "216" in hd["estimated_tokens_saved"]

    # 4. Multi-agent / workflow-scope candidate (>=3 consolidated agents)
    cons_session = CandidateReviewSession(
        workflow_id="wf_cons",
        candidates=[
            {
                "candidate_id": "CONS-CHAIN-1",
                "dimension": "agent_consolidation",
                "title": "Consolidate 3 sequential agents",
                "target_agents": ["a1", "a2", "a3"],
                "tier": "Tier 2",
                "requires_validation": True,
                "supporting_evidence": {"evidence_status": "sufficient"},
            }
        ],
    )
    wf_card = cons_session.get_candidate_card("CONS-CHAIN-1")
    assert wf_card["candidate_type"] == "workflow"
    assert wf_card["expected_benefits"]["projected_latency_improvement"] == "Not available"


# =============================================================================
# Test 10: Risk acknowledgement & empty selection enforcement
# =============================================================================
def test_10_risk_acknowledgement_and_empty_selection_blocking(
    recruitment_report: Dict[str, Any],
    tmp_path: Path,
):
    session = CandidateReviewSession.from_report(recruitment_report)

    readiness = session.validate_approval_readiness()
    assert readiness["ready"] is False
    assert "MODEL-RESUME_INTAKE_AGENT" in readiness["unacknowledged_risk_ids"]
    with pytest.raises(ValueError, match="Risk acknowledgement required"):
        session.approve(persist=False)

    # Empty selection also blocks approval
    session.clear_selection()
    empty_check = session.validate_approval_readiness()
    assert empty_check["ready"] is False
    assert any("At least one optimization candidate" in e for e in empty_check["errors"])
    with pytest.raises(ValueError, match="At least one"):
        session.approve(persist=False)

    # Select and acknowledge a Tier 2 risk candidate -> succeeds
    session.select_candidate("MODEL-RESUME_INTAKE_AGENT")
    session.acknowledge_risk("MODEL-RESUME_INTAKE_AGENT", True)
    scope = session.approve(persist=True, output_dir=tmp_path)
    assert scope["approval_status"] == "approved"
    assert scope["risk_acknowledged_candidate_ids"] == ["MODEL-RESUME_INTAKE_AGENT"]


# =============================================================================
# Test 11: LangGraph pause/resume approval & handoff to next stage
# =============================================================================
def test_11_langgraph_approval_and_handoff(tmp_path: Path):
    graph = build_optimization_graph_with_approval(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "test-approval-thread-1"}}

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
    }

    paused_state = graph.invoke(initial_state, config)
    snapshot = graph.get_state(config)
    assert "apply_user_approval" in snapshot.next
    assert paused_state["approval_status"] == "pending_user_review"
    assert paused_state["stage_status"]["prepare_candidate_review"] == "completed"

    selected_subset = [
        "PARALLEL-QUALIFICATION_AGENT-JOB_CRITERIA_AGENT",
        "MODEL-RESUME_INTAKE_AGENT",
        "HANDOFF-MISSING_EVIDENCE_AGENT-TO-SCREENING_REVIEW_AGENT",
    ]
    ack_subset = [
        "MODEL-RESUME_INTAKE_AGENT",
        "HANDOFF-MISSING_EVIDENCE_AGENT-TO-SCREENING_REVIEW_AGENT",
    ]

    final_state = resume_graph_with_approval(
        compiled_graph=graph,
        config=config,
        workflow_id="recruitment_screening",
        selected_candidate_ids=selected_subset,
        risk_acknowledged_candidate_ids=ack_subset,
        persist=True,
        output_dir=str(tmp_path),
    )

    assert final_state["approval_status"] == "approved"
    assert final_state["stage_status"]["apply_user_approval"] == "completed"
    assert final_state["stage_status"]["next_optimization_stage_handoff"] == "completed"

    next_in = final_state["next_stage_input"]
    assert next_in["workflow_id"] == "recruitment_screening"
    assert next_in["ready_for_downstream_execution"] is True
    assert next_in["workflow_mutated"] is False
    assert next_in["approved_candidate_ids"] == selected_subset
    assert [c["candidate_id"] for c in next_in["approved_candidates"]] == selected_subset

    persisted = tmp_path / "recruitment_screening_approved_optimization_scope.json"
    assert persisted.exists()
    persisted_data = json.loads(persisted.read_text(encoding="utf-8"))
    assert persisted_data["approved_candidate_ids"] == selected_subset


# =============================================================================
# Test 12: Data preservation (no field/evidence loss)
# =============================================================================
def test_12_data_preservation(
    recruitment_report: Dict[str, Any],
    tmp_path: Path,
):
    session = CandidateReviewSession.from_report(recruitment_report)
    target_id = "HANDOFF-QUALIFICATION_AGENT-TO-EXPERIENCE_ASSESSMENT_AGENT"

    raw_list = recruitment_report["communication_optimization_opportunities"]["candidates"]
    original_cand = next(c for c in raw_list if c["candidate_id"] == target_id)

    session.clear_selection()
    session.select_candidate(target_id)
    session.acknowledge_risk(target_id, True)
    scope = session.approve(persist=True, output_dir=tmp_path)

    approved_cand = scope["approved_candidates"][0]
    assert approved_cand == original_cand
    assert approved_cand["supporting_evidence"] == original_cand["supporting_evidence"]
    assert approved_cand["proposed_compact_payload_schema"] == original_cand["proposed_compact_payload_schema"]
    assert approved_cand["expected_benefit"] == original_cand["expected_benefit"]
    assert approved_cand["tradeoffs_and_risks"] == original_cand["tradeoffs_and_risks"]


# =============================================================================
# Test 13: Workflow isolation
# =============================================================================
def test_13_workflow_isolation(recruitment_report: Dict[str, Any]):
    session = CandidateReviewSession.from_report(recruitment_report)

    session.acknowledge_all_selected_risks()
    with pytest.raises(ValueError, match="Workflow isolation mismatch"):
        session.approve(expected_workflow_id="contract_review", persist=False)

    contract_report = json.loads(CONTRACT_REPORT_PATH.read_text(encoding="utf-8"))
    contract_session = CandidateReviewSession.from_report(contract_report)
    foreign_id = next(
        cid for cid in contract_session.eligible_candidate_ids
        if cid not in {c["candidate_id"] for c in session.candidates}
    )
    with pytest.raises(KeyError):
        session.select_candidate(foreign_id)

    with pytest.raises(ValueError, match="Cross-workflow candidate rejected"):
        CandidateReviewSession(
            workflow_id="recruitment_screening",
            candidates=[{"candidate_id": "X-1", "workflow_id": "contract_review"}],
        )


# =============================================================================
# Test 14: Regression & Streamlit UI integration
# =============================================================================
def test_14_regression_s11_s12_s13_and_streamlit_ui(recruitment_report: Dict[str, Any], tmp_path: Path):
    graph = build_optimization_graph()
    assert graph is not None

    agent = OptimizationDiscoveryAgent()
    state = agent.run("contract_review")
    for stage in (
        "discovery_analysis",
        "tradeoff_assessment",
        "generate_report",
    ):
        assert state["stage_status"][stage] == "completed"
    final_rep = state["final_report"]
    assert final_rep["report_metadata"]["workflow_id"] == "contract_review"
    for removed in (
        "agent_pruning_opportunities",
        "tool_optimization_opportunities",
        "additional_optimization_opportunities",
    ):
        assert removed not in final_rep

    from streamlit.testing.v1 import AppTest

    app_script = tmp_path / "review_smoke_app.py"
    script_body = (
        "import json\n"
        "from pathlib import Path\n"
        "from optimization_agent.review.ui import render_candidate_review_interface\n"
        f"data = json.loads(Path({str(RECRUITMENT_REPORT_PATH)!r}).read_text(encoding='utf-8'))\n"
        f"render_candidate_review_interface('recruitment_screening', data, reports_dir=Path({str(tmp_path)!r}))\n"
    )
    app_script.write_text(script_body, encoding="utf-8")

    at = AppTest.from_file(str(app_script), default_timeout=20)
    at.run()
    assert not at.exception
    metric_values = {m.label: m.value for m in at.metric}
    assert metric_values["Total Candidates"] == "12"
    assert metric_values["Tier 1"] == "1"
    assert metric_values["Tier 2"] == "11"
    assert metric_values["Currently Selected"] == "12"
