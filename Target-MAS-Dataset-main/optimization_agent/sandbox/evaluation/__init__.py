"""Sandbox Before-and-After Performance & Output Quality Evaluation Package."""

from optimization_agent.sandbox.evaluation.baseline_loader import (
    compute_canonical_input_hash,
    extract_record_identifiers,
    load_historical_baseline_evidence,
    match_baseline_traces_to_inputs,
)
from optimization_agent.sandbox.evaluation.evaluator import (
    classify_final_experiment_assessment,
    evaluate_experiment,
)
from optimization_agent.sandbox.evaluation.quality_evaluator import (
    evaluate_agent_output_quality,
    evaluate_workflow_quality,
)
from optimization_agent.sandbox.evaluation.ragas_evaluator import (
    RAGAS_METRICS_ORDER,
    QualityAcceptanceCriteria,
    build_ragas_samples,
    check_ragas_environment,
    evaluate_quality_acceptance,
    evaluate_with_ragas,
)
from optimization_agent.sandbox.evaluation.workflow_selector import (
    evaluate_dimension_result,
    select_best_workflows_pareto,
)

__all__ = [
    "RAGAS_METRICS_ORDER",
    "QualityAcceptanceCriteria",
    "build_ragas_samples",
    "check_ragas_environment",
    "classify_final_experiment_assessment",
    "compute_canonical_input_hash",
    "evaluate_agent_output_quality",
    "evaluate_dimension_result",
    "evaluate_experiment",
    "evaluate_quality_acceptance",
    "evaluate_with_ragas",
    "evaluate_workflow_quality",
    "extract_record_identifiers",
    "load_historical_baseline_evidence",
    "match_baseline_traces_to_inputs",
    "select_best_workflows_pareto",
]
