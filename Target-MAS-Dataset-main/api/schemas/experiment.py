"""Pydantic schemas for experiments, fixed baselines, and reports."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class BaselineResponse(BaseModel):
    workflow_id: str
    fixed_baseline_reference_id: Optional[str] = None
    source: str = "historical_runtime_traces"
    execution_mode: str = "historical_recorded_execution"
    re_executed: bool = False
    groq_api_calls: int = 0
    trace_directory: Optional[str] = None
    total_historical_traces_found: int = 0
    matched_input_count: int = 0
    unmatched_input_count: int = 0
    excluded_records: List[Dict[str, Any]] = Field(default_factory=list)
    execution_order: List[str] = Field(default_factory=list)
    historical_model: str = "openai/gpt-oss-120b"
    metrics: Dict[str, Any] = Field(default_factory=dict)
    traces: List[Dict[str, Any]] = Field(default_factory=list)
    replay_traces: List[Dict[str, Any]] = Field(default_factory=list)


class QualityCriteriaInput(BaseModel):
    min_faithfulness: Optional[float] = 0.70
    min_context_precision: Optional[float] = 0.70
    min_context_recall: Optional[float] = 0.70
    max_regression_vs_foundation: Optional[float] = 0.10
    require_all_metrics_available: bool = True


class EquivalenceCriteriaInput(BaseModel):
    min_structural_decision_score: Optional[float] = 0.75
    min_semantic_cosine: Optional[float] = 0.75
    min_llm_judge_score: Optional[float] = 0.75
    max_decision_flips: Optional[int] = 0
    max_regression_vs_foundation: Optional[float] = 0.10


class ExperimentStartRequest(BaseModel):
    workflow_id: str
    experiment_type: Literal[
        "two_phase_study",
        "dimension_ablation_suite",
        "combined_single_workflow",
    ] = "two_phase_study"
    selected_dimensions: Optional[List[str]] = None
    num_runs: int = Field(default=1, ge=1, le=20)
    approved_scope_reference: Optional[str] = None
    evaluation_mode: Literal["equivalence", "ragas"] = "equivalence"
    enable_equivalence_llm_judge: bool = False
    quality_criteria: Optional[QualityCriteriaInput] = None
    equivalence_criteria: Optional[EquivalenceCriteriaInput] = None
    enable_trace_replay_fallback: bool = False


class ExperimentStatusResponse(BaseModel):
    experiment_id: str
    workflow_id: str
    experiment_type: str
    status: Literal["queued", "running", "completed", "failed"]
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    num_runs: int = 1
    selected_dimensions: Optional[List[str]] = None
    current_phase: Optional[str] = None
    error: Optional[str] = None
    experiment_dir: Optional[str] = None
    json_report_path: Optional[str] = None
    markdown_report_path: Optional[str] = None


class ExperimentResultsResponse(BaseModel):
    experiment_id: str
    workflow_id: str
    experiment_type: str
    evaluation_mode: Optional[str] = None
    status: str
    fixed_optimization_foundation: List[str] = Field(default_factory=list)
    baseline_runtime_results: Dict[str, Any] = Field(default_factory=dict)
    phase_a_foundation: Dict[str, Any] = Field(default_factory=dict)
    phase_b_variable_dimensions: Dict[str, Any] = Field(default_factory=dict)
    phase_c_combined: Dict[str, Any] = Field(default_factory=dict)
    comparative_configurations: List[Dict[str, Any]] = Field(default_factory=list)
    pareto_selection: Dict[str, Any] = Field(default_factory=dict)
    ragas_evaluation_model_usage: Dict[str, Any] = Field(default_factory=dict)
    per_dimension_results: Dict[str, Any] = Field(default_factory=dict)
    combined_result: Optional[Dict[str, Any]] = None
    single_experiment_result: Optional[Dict[str, Any]] = None
    limitations: List[str] = Field(default_factory=list)
    original_integrity_after: Dict[str, Any] = Field(default_factory=dict)


class ReportBundleResponse(BaseModel):
    experiment_id: str
    workflow_id: str
    report_kind: str
    json_report_path: Optional[str] = None
    markdown_report_path: Optional[str] = None
    json_report: Optional[Dict[str, Any]] = None
    markdown_report: Optional[str] = None
    sub_reports: List[Dict[str, Any]] = Field(default_factory=list)
