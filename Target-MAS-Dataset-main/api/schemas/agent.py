"""Pydantic schemas for Target MAS workflow metadata and agent profiles."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AgentProfile(BaseModel):
    agent_id: str
    agent_name: str
    role: str
    goal: Optional[str] = None
    responsibilities: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    input_fields: List[str] = Field(default_factory=list)
    output_fields: List[str] = Field(default_factory=list)
    model: str = "openai/gpt-oss-120b"
    original_prompt_preview: Optional[str] = None
    execution_style: str = "pure_llm"
    helper_functions: List[str] = Field(default_factory=list)
    historical_mean_latency_seconds: Optional[float] = None
    historical_mean_tokens: Optional[float] = None
    historical_mean_cost_usd: Optional[float] = None


class WorkflowSummary(BaseModel):
    workflow_id: str
    workflow_name: str
    agent_count: int
    baseline_model: str = "openai/gpt-oss-120b"
    llm_provider: str = "Groq"
    has_historical_traces: bool = False
    historical_trace_count: int = 0
    has_approved_scope: bool = False
    approved_candidate_count: int = 0
    has_discovery_report: bool = False


class WorkflowOverviewResponse(BaseModel):
    workflow_id: str
    workflow_name: str
    baseline_model: str = "openai/gpt-oss-120b"
    llm_provider: str = "Groq"
    agents: List[AgentProfile] = Field(default_factory=list)
    execution_order: List[str] = Field(default_factory=list)
    historical_baseline: Dict[str, Any] = Field(default_factory=dict)
    approved_scope: Optional[Dict[str, Any]] = None
    approved_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    discovered_candidates_by_dimension: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)


class WorkflowReviewResponse(BaseModel):
    workflow_id: str
    has_discovery_report: bool = False
    has_approved_scope: bool = False
    approved_candidate_ids: List[str] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)
    dimension_counts: List[Dict[str, Any]] = Field(default_factory=list)
    candidates: List[Dict[str, Any]] = Field(default_factory=list)


class ApproveScopeRequest(BaseModel):
    selected_candidate_ids: List[str] = Field(default_factory=list)
    risk_acknowledged_candidate_ids: List[str] = Field(default_factory=list)
