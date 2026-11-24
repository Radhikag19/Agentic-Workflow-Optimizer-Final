"""
Optimization Agent Package.

Provides the Autonomous Optimization Discovery Agent using LangGraph, LangChain,
and the TraceProfiler MCP Evidence Server.
"""

from optimization_agent.agent import OptimizationDiscoveryAgent, build_optimization_graph
from optimization_agent.key_manager import GroqKeyManager, get_default_key_manager, mask_key
from optimization_agent.state import OptimizationAgentState, OptimizationCandidate
from optimization_agent.model_selection import (
    run_model_selection,
    build_model_selection_graph,
    AWOModelSelectionState,
)
from optimization_agent.review import (
    CandidateReviewSession,
    build_optimization_graph_with_approval,
    handoff_approved_scope_to_next_stage,
    resume_graph_with_approval,
)
from optimization_agent.sandbox import (
    CandidateExecutionRouter,
    EXECUTOR_REGISTRY,
    SandboxExperimentRunner,
    build_optimization_graph_with_sandbox_execution,
)

__all__ = [
    "OptimizationDiscoveryAgent",
    "build_optimization_graph",
    "build_optimization_graph_with_approval",
    "build_optimization_graph_with_sandbox_execution",
    "resume_graph_with_approval",
    "handoff_approved_scope_to_next_stage",
    "CandidateReviewSession",
    "SandboxExperimentRunner",
    "CandidateExecutionRouter",
    "EXECUTOR_REGISTRY",
    "OptimizationAgentState",
    "OptimizationCandidate",
    "GroqKeyManager",
    "get_default_key_manager",
    "mask_key",
    "run_model_selection",
    "build_model_selection_graph",
    "AWOModelSelectionState",
]
