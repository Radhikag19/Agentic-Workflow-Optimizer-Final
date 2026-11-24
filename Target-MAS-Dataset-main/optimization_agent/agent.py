"""
LangGraph Workflow Orchestration for TraceProfiler Autonomous Optimization Discovery Agent.

Orchestrates the 13 sequential execution stages:
Stages 1 to 10: TraceProfiler MCP Evidence Server retrieval
Stage 11: Systematic multi-dimensional optimization discovery
Stage 12: Feasibility and trade-off assessment
Stage 13: Structured JSON and human-readable Markdown report compilation
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from langgraph.graph import END, START, StateGraph

from optimization_agent.discovery import discovery_analysis
from optimization_agent.key_manager import get_default_key_manager
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
from optimization_agent.state import OptimizationAgentState
from optimization_agent.tradeoff import tradeoff_assessment

logger = logging.getLogger("optimization_agent.agent")


def build_optimization_graph() -> Any:
    """Build and compile the 13-stage sequential LangGraph StateGraph."""
    builder = StateGraph(OptimizationAgentState)

    # Register all 13 nodes
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

    # Strictly sequential execution order
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
    builder.add_edge("generate_report", END)

    return builder.compile()


class OptimizationDiscoveryAgent:
    """
    Autonomous Optimization Discovery Agent using LangGraph and LangChain.
    Systematically inspects target multi-agent systems via MCP evidence tools,
    discovers optimization candidates across 5 dimensions, and produces reports.
    """

    def __init__(self, key_manager=None):
        self.key_manager = key_manager or get_default_key_manager()
        self.graph = build_optimization_graph()

    def run(
        self,
        workflow_id: str,
        evidence_dir: Optional[str] = None,
        target_model: str = "openai/gpt-oss-120b",
    ) -> OptimizationAgentState:
        """
        Execute the end-to-end optimization discovery pipeline for a target workflow.
        """
        initial_state: OptimizationAgentState = {
            "workflow_id": workflow_id,
            "evidence_dir": evidence_dir,
            "target_model": target_model,
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

        logger.info(f"Starting Autonomous Optimization Discovery for workflow '{workflow_id}'...")
        final_state = self.graph.invoke(initial_state)
        logger.info(f"Completed optimization discovery pipeline for workflow '{workflow_id}'.")
        return final_state

    def run_until_approval(
        self,
        workflow_id: str,
        evidence_dir: Optional[str] = None,
        target_model: str = "openai/gpt-oss-120b",
        thread_id: Optional[str] = None,
        checkpointer: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Execute Stages 1-13 + review preparation and pause before user approval.
        Returns {'graph', 'config', 'state', 'snapshot'}.
        """
        from optimization_agent.review.langgraph_handoff import build_optimization_graph_with_approval

        approval_graph = build_optimization_graph_with_approval(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": thread_id or f"awo-{workflow_id}"}}
        initial_state: OptimizationAgentState = {
            "workflow_id": workflow_id,
            "evidence_dir": evidence_dir,
            "target_model": target_model,
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
        paused_state = approval_graph.invoke(initial_state, config)
        snapshot = approval_graph.get_state(config)
        return {
            "graph": approval_graph,
            "config": config,
            "state": paused_state,
            "snapshot": snapshot,
        }

    def resume_after_approval(
        self,
        approval_graph: Any,
        config: Dict[str, Any],
        workflow_id: str,
        selected_candidate_ids: list[str],
        risk_acknowledged_candidate_ids: list[str] = (),
        persist: bool = True,
        output_dir: Optional[str] = None,
    ) -> OptimizationAgentState:
        """Resume a paused approval graph with explicit user candidate selections."""
        from optimization_agent.review.langgraph_handoff import resume_graph_with_approval

        return resume_graph_with_approval(
            compiled_graph=approval_graph,
            config=config,
            workflow_id=workflow_id,
            selected_candidate_ids=selected_candidate_ids,
            risk_acknowledged_candidate_ids=risk_acknowledged_candidate_ids,
            persist=persist,
            output_dir=output_dir,
        )

    def run_sandbox_experiment(
        self,
        approved_scope: Any,
        *,
        experiment_id: Optional[str] = None,
        num_runs: int = 2,
        llm_callable: Any = None,
        enable_trace_replay_fallback: bool = False,
        groq_client_factory: Any = None,
        judge_callable: Any = None,
        enable_llm_judge: bool = False,
        baseline_traces_dir: Any = None,
        baseline_metrics_artifact: Any = None,
        execution_backend: str = "local_subprocess",
        process_timeout_seconds: float = 300.0,
    ) -> Dict[str, Any]:
        """Run sandbox experiment comparing fixed historical baseline vs. optimized execution."""
        from optimization_agent.sandbox.experiment import SandboxExperimentRunner

        runner = SandboxExperimentRunner(
            llm_callable=llm_callable,
            enable_trace_replay_fallback=enable_trace_replay_fallback,
            groq_client_factory=groq_client_factory,
            judge_callable=judge_callable,
            enable_llm_judge=enable_llm_judge,
            baseline_traces_dir=baseline_traces_dir,
            baseline_metrics_artifact=baseline_metrics_artifact,
            execution_backend=execution_backend,
            process_timeout_seconds=process_timeout_seconds,
        )
        return runner.run(
            approved_scope,
            experiment_id=experiment_id,
            num_runs=num_runs,
        )

    def run_sandbox_dimension_suite(
        self,
        approved_scope: Any,
        *,
        suite_id: Optional[str] = None,
        selected_dimensions: Optional[list[str]] = None,
        include_combined: bool = True,
        num_runs: int = 2,
        llm_callable: Any = None,
        enable_trace_replay_fallback: bool = False,
        groq_client_factory: Any = None,
        judge_callable: Any = None,
        enable_llm_judge: bool = False,
        baseline_traces_dir: Any = None,
        baseline_metrics_artifact: Any = None,
        execution_backend: str = "local_subprocess",
        process_timeout_seconds: float = 300.0,
        per_run_subprocess: bool = True,
    ) -> Dict[str, Any]:
        """Run isolated non-stacked per-dimension sandbox experiments plus optional combined run."""
        from optimization_agent.sandbox.experiment import SandboxExperimentRunner

        runner = SandboxExperimentRunner(
            llm_callable=llm_callable,
            enable_trace_replay_fallback=enable_trace_replay_fallback,
            groq_client_factory=groq_client_factory,
            judge_callable=judge_callable,
            enable_llm_judge=enable_llm_judge,
            baseline_traces_dir=baseline_traces_dir,
            baseline_metrics_artifact=baseline_metrics_artifact,
            execution_backend=execution_backend,
            process_timeout_seconds=process_timeout_seconds,
            per_run_subprocess=per_run_subprocess,
        )
        return runner.run_dimension_ablation_suite(
            approved_scope,
            suite_id=suite_id,
            selected_dimensions=selected_dimensions,
            include_combined=include_combined,
            num_runs=num_runs,
        )

    def run_sandbox_optimization_study(
        self,
        approved_scope: Any,
        *,
        study_id: Optional[str] = None,
        quality_criteria: Any = None,
        ragas_runner: Any = None,
        selected_variable_dimensions: Optional[list[str]] = None,
        num_runs: int = 2,
        llm_callable: Any = None,
        enable_trace_replay_fallback: bool = False,
        groq_client_factory: Any = None,
        judge_callable: Any = None,
        enable_llm_judge: bool = False,
        baseline_traces_dir: Any = None,
        baseline_metrics_artifact: Any = None,
        execution_backend: str = "local_subprocess",
        process_timeout_seconds: float = 300.0,
        per_run_subprocess: bool = True,
    ) -> Dict[str, Any]:
        """Run the Two-Phase Fixed Foundation + Individual Variable + Combined Study with RAGAS & Pareto selection."""
        from optimization_agent.sandbox.experiment import SandboxExperimentRunner

        runner = SandboxExperimentRunner(
            llm_callable=llm_callable,
            enable_trace_replay_fallback=enable_trace_replay_fallback,
            groq_client_factory=groq_client_factory,
            judge_callable=judge_callable,
            enable_llm_judge=enable_llm_judge,
            baseline_traces_dir=baseline_traces_dir,
            baseline_metrics_artifact=baseline_metrics_artifact,
            execution_backend=execution_backend,
            process_timeout_seconds=process_timeout_seconds,
            per_run_subprocess=per_run_subprocess,
        )
        return runner.run_two_phase_optimization_study(
            approved_scope,
            study_id=study_id,
            quality_criteria=quality_criteria,
            ragas_runner=ragas_runner,
            selected_variable_dimensions=selected_variable_dimensions,
            num_runs=num_runs,
        )

    def resume_and_run_sandbox(
        self,
        sandbox_graph: Any,
        config: Dict[str, Any],
        workflow_id: str,
        selected_candidate_ids: list[str],
        risk_acknowledged_candidate_ids: list[str] = (),
        persist: bool = True,
        output_dir: Optional[str] = None,
    ) -> OptimizationAgentState:
        """Resume an interrupted approval+sandbox graph with explicit selections."""
        from optimization_agent.review.langgraph_handoff import resume_graph_with_approval

        return resume_graph_with_approval(
            compiled_graph=sandbox_graph,
            config=config,
            workflow_id=workflow_id,
            selected_candidate_ids=selected_candidate_ids,
            risk_acknowledged_candidate_ids=risk_acknowledged_candidate_ids,
            persist=persist,
            output_dir=output_dir,
        )

