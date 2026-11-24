"""
Experiment Report Generator:
Compiles structured JSON (`execution_report.json`) and 7-section Markdown
(`execution_report.md`) reports for every sandbox optimization experiment with
secret sanitization and full candidate/metric/quality traceability.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from optimization_agent.key_manager import get_default_key_manager
from optimization_agent.sandbox.manager import SandboxEnvironment


def _determine_overall_status(
    execution_results: Dict[str, Any],
    validation_results: Dict[str, Any],
    runtime_results: Dict[str, Any],
    evaluation_results: Dict[str, Any],
) -> str:
    assess = evaluation_results.get("final_experiment_assessment") or {}
    if assess.get("status"):
        return str(assess["status"])

    flags = evaluation_results.get("outcome_flags") or {}
    if not flags.get("modification_applied"):
        if execution_results.get("conflicts") or execution_results.get("failed_candidate_ids"):
            return "failed"
        return "inconclusive"
    if not flags.get("validation_passed") or not flags.get("execution_passed"):
        return "failed"
    return "inconclusive"


def _fmt_val(v: Any, suffix: str = "") -> str:
    if v is None:
        return "unavailable"
    return f"{v}{suffix}"


def generate_experiment_reports(
    env: SandboxEnvironment,
    execution_results: Dict[str, Any],
    validation_results: Dict[str, Any],
    runtime_results: Dict[str, Any],
    evaluation_results: Dict[str, Any],
    baseline_runtime_results: Optional[Dict[str, Any]] = None,
    quality_evaluation: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate and persist 7-section `execution_report.json` and `execution_report.md`."""
    key_mgr = get_default_key_manager()
    overall_status = _determine_overall_status(
        execution_results, validation_results, runtime_results, evaluation_results
    )
    assessment = evaluation_results.get("final_experiment_assessment") or {
        "status": overall_status,
        "reasons": [],
    }
    qual_eval = quality_evaluation or evaluation_results.get("quality_evaluation") or {}

    candidate_results = list(execution_results.get("candidate_results") or [])
    modifications_summary = [
        {
            "candidate_id": r.get("candidate_id"),
            "dimension": r.get("dimension"),
            "status": r.get("status"),
            "target_agents": r.get("target_agents"),
            "modified_files": r.get("modified_files"),
            "description": r.get("description"),
            "details": r.get("details"),
            "error": r.get("error"),
        }
        for r in candidate_results
    ]

    wf_cfg_path = env.sandbox_workflow_dir / "workflow.json"
    wf_cfg = json.loads(wf_cfg_path.read_text(encoding="utf-8")) if wf_cfg_path.exists() else {}
    model_provider_info = {
        "baseline_model": wf_cfg.get("baseline_model"),
        "llm_provider": wf_cfg.get("llm_provider", "Groq"),
        "assigned_groq_key_env": wf_cfg.get("assigned_groq_key_env"),
        "agent_model_overrides": wf_cfg.get("agent_model_overrides") or {},
    }

    baseline_rt_summary = (
        {
            "source": baseline_runtime_results.get("source") or "historical_runtime_traces",
            "execution_mode": baseline_runtime_results.get("execution_mode") or "historical_recorded_execution",
            "re_executed": bool(baseline_runtime_results.get("re_executed", False)),
            "groq_api_calls": int(baseline_runtime_results.get("groq_api_calls") or 0),
            "trace_directory": baseline_runtime_results.get("trace_directory"),
            "fixed_baseline_reference_id": baseline_runtime_results.get("fixed_baseline_reference_id"),
            "matched_input_count": baseline_runtime_results.get("matched_input_count"),
            "unmatched_input_count": baseline_runtime_results.get("unmatched_input_count"),
            "excluded_records": baseline_runtime_results.get("excluded_records") or [],
            "execution_passed": baseline_runtime_results.get("execution_passed"),
            "execution_modes": baseline_runtime_results.get("execution_modes"),
            "runs_executed": baseline_runtime_results.get("runs_executed"),
            "successful_runs": baseline_runtime_results.get("successful_runs"),
            "failed_runs": baseline_runtime_results.get("failed_runs"),
            "trace_files": baseline_runtime_results.get("trace_files"),
            "schema_validation_summary": baseline_runtime_results.get("schema_validation_summary"),
            "invalid_replay_samples": baseline_runtime_results.get("invalid_replay_samples"),
            "api_errors": baseline_runtime_results.get("api_errors"),
            "errors": baseline_runtime_results.get("errors"),
        }
        if baseline_runtime_results is not None
        else {
            "source": "historical_mcp_reference",
            "execution_mode": "historical_recorded_execution",
            "re_executed": False,
            "groq_api_calls": 0,
            "note": "Historical MCP metrics used as baseline reference.",
        }
    )

    base_metrics_obj = evaluation_results.get("baseline_metrics", {})
    opt_metrics_obj = evaluation_results.get("optimized_metrics", {})

    baseline_pm = (baseline_runtime_results or {}).get("process_metadata") or {}
    opt_pm = runtime_results.get("process_metadata") or {}
    exec_backend = (
        opt_pm.get("execution_backend")
        or ("in_process_callable" if "custom_callable" in str(runtime_results.get("execution_modes")) else "in_process")
    )
    process_execution_metadata = {
        "execution_backend": exec_backend,
        "python_executable": opt_pm.get("python_executable"),
        "baseline_re_executed": bool(baseline_rt_summary.get("re_executed", False)),
        "baseline_process_exit_code": baseline_pm.get("exit_code") if baseline_rt_summary.get("re_executed") else None,
        "baseline_execution_status": (
            "HISTORICAL_FIXED"
            if not baseline_rt_summary.get("re_executed", False)
            else (baseline_pm.get("execution_status") or "UNKNOWN")
        ),
        "baseline_groq_api_calls": 0,
        "baseline_api_errors": [],
        "optimized_process_exit_code": opt_pm.get("exit_code"),
        "optimized_process_exit_codes": opt_pm.get("process_exit_codes"),
        "optimized_execution_status": opt_pm.get("execution_status")
        or ("SUCCESS" if runtime_results.get("execution_passed") else "FAILED"),
        "optimized_process_duration_seconds": opt_pm.get("process_duration_seconds"),
        "optimized_groq_api_calls": int(runtime_results.get("groq_api_calls") or opt_metrics_obj.get("groq_api_calls") or 0),
        "optimized_api_errors": runtime_results.get("api_errors") or [],
        "execution_modes": list(runtime_results.get("execution_modes") or []),
    }

    input_matching_summary = {
        "fixed_baseline_reference_id": base_metrics_obj.get("fixed_baseline_reference_id") or baseline_rt_summary.get("fixed_baseline_reference_id"),
        "matched_input_count": base_metrics_obj.get("matched_input_count") if base_metrics_obj.get("matched_input_count") is not None else baseline_rt_summary.get("matched_input_count"),
        "unmatched_input_count": base_metrics_obj.get("unmatched_input_count") if base_metrics_obj.get("unmatched_input_count") is not None else baseline_rt_summary.get("unmatched_input_count"),
        "excluded_records": base_metrics_obj.get("excluded_records") or baseline_rt_summary.get("excluded_records") or [],
        "num_optimized_runs": int(runtime_results.get("runs_executed") or 0),
    }

    baseline_evidence_section = {
        "source": "historical_runtime_traces",
        "execution_mode": "historical_recorded_execution",
        "re_executed": False,
        "groq_api_calls": 0,
        "trace_directory": base_metrics_obj.get("trace_directory") or baseline_rt_summary.get("trace_directory"),
        "fixed_baseline_reference_id": input_matching_summary["fixed_baseline_reference_id"],
        "measurement_period": base_metrics_obj.get("measurement_period"),
        "available_historical_metrics": base_metrics_obj,
    }

    optimized_execution_section = {
        "source": "current_experiment",
        "execution_mode": list(runtime_results.get("execution_modes") or []),
        "re_executed": True,
        "groq_api_calls": process_execution_metadata["optimized_groq_api_calls"],
        "trace_directory": runtime_results.get("trace_directory") or str(env.runtime_traces_dir.resolve()),
        "num_optimized_runs": int(runtime_results.get("runs_executed") or 0),
        "per_run_metrics": opt_metrics_obj.get("per_run_metrics") or [],
        "aggregate_metrics": opt_metrics_obj,
    }

    report_json: Dict[str, Any] = {
        "experiment_id": env.experiment_id,
        "workflow_id": env.workflow_id,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "comparison_nature": "historical_baseline_evidence_vs_fresh_optimized_execution",
        "execution_backend": exec_backend,
        "process_execution_metadata": process_execution_metadata,
        "input_matching": input_matching_summary,
        "baseline_evidence": baseline_evidence_section,
        "optimized_execution": optimized_execution_section,
        "execution_modes": list(runtime_results.get("execution_modes") or []),
        "runs_executed": int(runtime_results.get("runs_executed") or 0),
        "model_and_provider_info": model_provider_info,
        "original_workflow_location": str(env.original_workflow_dir),
        "sandbox_workflow_location": str(env.sandbox_workflow_dir),
        "approved_candidate_ids": list(execution_results.get("approved_candidate_ids") or []),
        "applied_candidate_ids": list(execution_results.get("applied_candidate_ids") or []),
        "failed_candidate_ids": list(execution_results.get("failed_candidate_ids") or []),
        "conflicting_candidate_ids": list(execution_results.get("conflicting_candidate_ids") or []),
        "candidates_requiring_manual_intervention": list(
            execution_results.get("manual_intervention_candidate_ids") or []
        ),
        "conflicts": list(execution_results.get("conflicts") or []),
        "modified_files": list(execution_results.get("modified_files") or []),
        "modifications": modifications_summary,
        "candidate_outcomes": list(evaluation_results.get("candidate_outcomes") or []),
        "validation_results": validation_results,
        "baseline_runtime_execution_results": baseline_rt_summary,
        "runtime_execution_results": {
            "execution_passed": runtime_results.get("execution_passed"),
            "execution_modes": runtime_results.get("execution_modes"),
            "usage_sources": runtime_results.get("usage_sources"),
            "runs_executed": runtime_results.get("runs_executed"),
            "successful_runs": runtime_results.get("successful_runs"),
            "failed_runs": runtime_results.get("failed_runs"),
            "incomplete_runs": runtime_results.get("incomplete_runs"),
            "concurrent_waves_executed": runtime_results.get("concurrent_waves_executed"),
            "trace_files": runtime_results.get("trace_files"),
            "schema_validation_summary": runtime_results.get("schema_validation_summary"),
            "invalid_replay_samples": runtime_results.get("invalid_replay_samples"),
            "api_errors": runtime_results.get("api_errors"),
            "fallback_events": runtime_results.get("fallback_events"),
            "errors": runtime_results.get("errors"),
        },
        "quality_evaluation": qual_eval,
        "baseline_metrics": evaluation_results.get("baseline_metrics", {}),
        "optimized_metrics": evaluation_results.get("optimized_metrics", {}),
        "before_and_after_comparison": evaluation_results.get("comparison", {}),
        "outcome_flags": evaluation_results.get("outcome_flags", {}),
        "final_experiment_assessment": assessment,
        "overall_experiment_status": overall_status,
    }

    sanitized_json_str = key_mgr.sanitize_text(json.dumps(report_json, indent=2, default=str))
    report_json = json.loads(sanitized_json_str)

    json_path = env.experiment_dir / "execution_report.json"
    md_path = env.experiment_dir / "execution_report.md"
    json_path.write_text(sanitized_json_str, encoding="utf-8")

    # Build 7-section Markdown Report
    flags = report_json["outcome_flags"]
    comp = report_json["before_and_after_comparison"]
    mean_wf = comp.get("mean_workflow_latency") or {}
    med_wf = comp.get("median_workflow_latency") or {}
    ag_lat = comp.get("mean_agent_latency") or {}
    in_tok = comp.get("input_tokens") or {}
    out_tok = comp.get("output_tokens") or {}
    tot_tok = comp.get("total_tokens") or {}
    cost_c = comp.get("execution_cost") or {}
    succ_c = comp.get("execution_success_rate") or {}
    sv_c = comp.get("output_structural_validity") or {}
    sq_c = comp.get("semantic_quality") or {}

    base_q_dim = ((qual_eval.get("baseline_quality") or {}).get("dimension_summary") or {})
    opt_q_dim = ((qual_eval.get("optimized_quality") or {}).get("dimension_summary") or {})
    regressions = qual_eval.get("identified_regressions") or []

    lines: List[str] = [
        f"# Sandbox Optimization Experiment Report: `{env.workflow_id}`",
        "",
        "## 1. Experiment Metadata",
        "",
        f"- **Workflow ID:** `{env.workflow_id}`",
        f"- **Experiment ID:** `{env.experiment_id}`",
        f"- **Execution Backend:** `{process_execution_metadata['execution_backend']}`",
        f"- **Python Executable:** `{process_execution_metadata['python_executable'] or 'in_process'}`",
        f"- **Execution Mode(s):** `{report_json['execution_modes']}`",
        f"- **Runs Executed:** `{report_json['runs_executed']}`",
        f"- **Baseline Model / Provider:** `{model_provider_info.get('baseline_model')}` / `{model_provider_info.get('llm_provider')}` (key env: `{model_provider_info.get('assigned_groq_key_env')}`)",
        f"- **Model Overrides Applied:** `{model_provider_info.get('agent_model_overrides')}`",
        f"- **Approved Candidate IDs ({len(report_json['approved_candidate_ids'])}):** {', '.join(f'`{x}`' for x in report_json['approved_candidate_ids']) or 'None'}",
        f"- **Original Workflow:** `{env.original_workflow_dir}`",
        f"- **Sandbox Workflow:** `{env.sandbox_workflow_dir}`",
        f"- **Generated At:** {report_json['generated_at']}",
        "",
        "## 2. Applied Modifications",
        "",
        f"- **Applied ({len(report_json['applied_candidate_ids'])}):** {', '.join(f'`{x}`' for x in report_json['applied_candidate_ids']) or 'None'}",
        f"- **Failed ({len(report_json['failed_candidate_ids'])}):** {', '.join(f'`{x}`' for x in report_json['failed_candidate_ids']) or 'None'}",
        f"- **Conflicts ({len(report_json['conflicting_candidate_ids'])}):** {', '.join(f'`{x}`' for x in report_json['conflicting_candidate_ids']) or 'None'}",
        f"- **Manual Intervention ({len(report_json['candidates_requiring_manual_intervention'])}):** {', '.join(f'`{x}`' for x in report_json['candidates_requiring_manual_intervention']) or 'None'}",
        f"- **Modified Files:** {', '.join(f'`{x}`' for x in report_json['modified_files']) or 'None'}",
        "",
    ]

    for m in modifications_summary:
        lines.append(f"- **`{m['candidate_id']}`** (`{m['dimension']}`) — Status: `{m['status']}` — {m['description']}")
    lines.extend(["", "## 3. Validation Results", ""])
    lines.extend([
        f"- **Original Workflow Unchanged (SHA-256 Verified):** `{validation_results.get('original_workflow_integrity', {}).get('original_unchanged')}`",
        f"- **Python Syntax Checks Passed:** `{validation_results.get('python_syntax_checks', {}).get('passed')}` ({validation_results.get('python_syntax_checks', {}).get('files_checked', 0)} files)",
        f"- **Configuration Validation Passed:** `{validation_results.get('configuration_validation', {}).get('passed')}`",
        f"- **Dependency & Reference Integrity Passed:** `{validation_results.get('reference_integrity', {}).get('passed') and validation_results.get('dependency_integrity', {}).get('passed')}`",
        f"- **Output Schema Validation Passed (Optimized):** `{(runtime_results.get('schema_validation_summary') or {}).get('all_schemas_valid')}`",
        "",
        "## 4. Runtime Execution & Baseline Evidence",
        "",
        "### Fixed Historical Baseline Evidence",
        f"- **Source:** `{baseline_evidence_section['source']}` | **Execution Mode:** `{baseline_evidence_section['execution_mode']}` | **Re-executed:** `{baseline_evidence_section['re_executed']}` | **Groq API Calls:** `{baseline_evidence_section['groq_api_calls']}`",
        f"- **Fixed Baseline Reference ID:** `{input_matching_summary['fixed_baseline_reference_id']}` | **Trace Directory:** `{baseline_evidence_section['trace_directory']}`",
        f"- **Input Matching:** matched=`{input_matching_summary['matched_input_count']}`, unmatched=`{input_matching_summary['unmatched_input_count']}`, excluded=`{len(input_matching_summary['excluded_records'])}`",
        "",
        "### Fresh Optimized Subprocess Execution",
        f"- **Source:** `{optimized_execution_section['source']}` | **Execution Mode(s):** `{optimized_execution_section['execution_mode']}` | **Re-executed:** `{optimized_execution_section['re_executed']}` | **Groq API Calls:** `{optimized_execution_section['groq_api_calls']}`",
        f"- **Trace Directory:** `{optimized_execution_section['trace_directory']}`",
        f"- **Optimized Runs:** runs=`{runtime_results.get('runs_executed')}`, succeeded=`{runtime_results.get('successful_runs')}`, failed=`{runtime_results.get('failed_runs')}`, process_exit=`{process_execution_metadata['optimized_process_exit_code']}`, status=`{process_execution_metadata['optimized_execution_status']}`, duration=`{_fmt_val(process_execution_metadata['optimized_process_duration_seconds'], 's')}`",
        f"- **Optimized API Errors Captured:** `{len(process_execution_metadata['optimized_api_errors'])}`",
        f"- **Incomplete / Invalid Replay Samples Flagged:** `{len(runtime_results.get('invalid_replay_samples') or [])}`",
        f"- **Workflow-Level vs. Agent-Level Latency (Historical Baseline vs. Fresh Optimized):** Baseline WF mean `{_fmt_val(mean_wf.get('baseline_seconds'), 's')}` (Agent mean `{_fmt_val(ag_lat.get('baseline_seconds'), 's')}`) -> Optimized WF mean `{_fmt_val(mean_wf.get('optimized_seconds'), 's')}` (Agent mean `{_fmt_val(ag_lat.get('optimized_seconds'), 's')}`)",
        "",
        "## 5. Output Quality Evaluation",
        "",
        "| Quality Dimension | Baseline Status (Pass Rate) | Optimized Status (Pass Rate) |",
        "| :--- | :--- | :--- |",
    ])
    for dim in ("structural_validity", "correctness", "completeness", "consistency", "instruction_adherence", "semantic_quality"):
        bq = base_q_dim.get(dim) or {}
        oq = opt_q_dim.get(dim) or {}
        lines.append(
            f"| `{dim}` | `{bq.get('status', 'unavailable')}` ({_fmt_val(bq.get('pass_rate_pct'), '%')}) | "
            f"`{oq.get('status', 'unavailable')}` ({_fmt_val(oq.get('pass_rate_pct'), '%')}) |"
        )
    lines.append(f"\n- **Identified Regressions:** `{len(regressions)}`")
    for reg in regressions:
        lines.append(f"  - `{reg.get('agent_id')}.{reg.get('metric')}`: {reg.get('baseline_pass_rate_pct')}% -> {reg.get('optimized_pass_rate_pct')}%")

    lines.extend([
        "",
        "## 6. Before-and-After Comparison",
        "",
        "| Metric | Baseline | Optimized | Improvement |",
        "| :--- | :--- | :--- | :--- |",
        f"| Mean Workflow Latency | {_fmt_val(mean_wf.get('baseline_seconds'), 's')} | {_fmt_val(mean_wf.get('optimized_seconds'), 's')} | {_fmt_val(mean_wf.get('improvement_pct'), '%')} |",
        f"| Median Workflow Latency | {_fmt_val(med_wf.get('baseline_seconds'), 's')} | {_fmt_val(med_wf.get('optimized_seconds'), 's')} | {_fmt_val(med_wf.get('improvement_pct'), '%')} |",
        f"| Mean Agent Latency | {_fmt_val(ag_lat.get('baseline_seconds'), 's')} | {_fmt_val(ag_lat.get('optimized_seconds'), 's')} | {_fmt_val(ag_lat.get('improvement_pct'), '%')} |",
        f"| Input Tokens | {_fmt_val(in_tok.get('baseline_mean_tokens'))} | {_fmt_val(in_tok.get('optimized_mean_tokens'))} | {_fmt_val(in_tok.get('improvement_pct'), '%')} |",
        f"| Output Tokens | {_fmt_val(out_tok.get('baseline_mean_tokens'))} | {_fmt_val(out_tok.get('optimized_mean_tokens'))} | {_fmt_val(out_tok.get('improvement_pct'), '%')} |",
        f"| Total Tokens | {_fmt_val(tot_tok.get('baseline_mean_tokens'))} | {_fmt_val(tot_tok.get('optimized_mean_tokens'))} | {_fmt_val(tot_tok.get('improvement_pct'), '%')} |",
        f"| Execution Cost ({cost_c.get('cost_basis')}) | ${cost_c.get('baseline_catalog_normalized_usd')} | ${cost_c.get('optimized_catalog_normalized_usd')} | {_fmt_val(cost_c.get('improvement_pct_catalog_normalized'), '%')} |",
        f"| Execution Success Rate | {_fmt_val(succ_c.get('baseline_pct'), '%')} | {_fmt_val(succ_c.get('optimized_pct'), '%')} | {_fmt_val(succ_c.get('improvement_pct'), '%')} |",
        f"| Structural Validity | {_fmt_val(sv_c.get('baseline_pass_rate_pct'), '%')} | {_fmt_val(sv_c.get('optimized_pass_rate_pct'), '%')} | {_fmt_val(sv_c.get('improvement_pct'), '%')} |",
        f"| Semantic Quality | `{sq_c.get('baseline_status_or_pct')}` | `{sq_c.get('optimized_status_or_pct')}` | {_fmt_val(sq_c.get('improvement_pct'), '%')} |",
        "",
        "## 7. Final Experiment Assessment",
        "",
        f"- **Final Assessment Status:** `{assessment.get('status')}`",
        f"- **Stage Flags:** `modification_applied={flags.get('modification_applied')}`, `validation_passed={flags.get('validation_passed')}`, `execution_passed={flags.get('execution_passed')}`, `evaluation_passed={flags.get('evaluation_passed')}`",
        "- **Rationale:**",
    ])
    for r in assessment.get("reasons") or ["None"]:
        lines.append(f"  - {r}")

    lines.extend(["", "### Candidate-Level Traceability", ""])
    for co in report_json.get("candidate_outcomes") or []:
        lines.append(
            f"- `{co.get('candidate_id')}` (`{co.get('dimension')}`): applied=`{co.get('modification_applied')}`, "
            f"validation=`{co.get('validation_result')}`, execution=`{co.get('execution_result')}`, "
            f"evaluation=`{co.get('evaluation_result')}`"
        )

    sanitized_md = key_mgr.sanitize_text("\n".join(lines))
    md_path.write_text(sanitized_md, encoding="utf-8")

    return {
        "json_report_path": str(json_path),
        "markdown_report_path": str(md_path),
        "execution_report": report_json,
        "execution_markdown_report": sanitized_md,
    }


def generate_ablation_suite_reports(
    suite_dir: Path,
    suite_payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate JSON and Markdown comparison reports across isolated per-dimension and combined runs."""
    key_mgr = get_default_key_manager()
    target_dir = Path(suite_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    rows = list(suite_payload.get("comparison_rows") or [])
    skipped = list(suite_payload.get("skipped_dimensions") or [])
    baseline_bundle = suite_payload.get("baseline_runtime_results") or {}
    integrity = suite_payload.get("original_integrity_after") or {}

    report_obj: Dict[str, Any] = {
        "suite_id": suite_payload.get("suite_id"),
        "workflow_id": suite_payload.get("workflow_id"),
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "suite_dir": str(target_dir),
        "selected_dimensions": suite_payload.get("selected_dimensions"),
        "executed_dimensions": list(suite_payload.get("executed_dimensions") or []),
        "skipped_dimensions": skipped,
        "include_combined": bool(suite_payload.get("include_combined", True)),
        "num_runs": int(suite_payload.get("num_runs") or 0),
        "baseline_evidence": {
            "source": baseline_bundle.get("source") or "historical_runtime_traces",
            "execution_mode": baseline_bundle.get("execution_mode") or "historical_recorded_execution",
            "re_executed": bool(baseline_bundle.get("re_executed", False)),
            "groq_api_calls": int(baseline_bundle.get("groq_api_calls") or 0),
            "fixed_baseline_reference_id": baseline_bundle.get("fixed_baseline_reference_id"),
            "trace_directory": baseline_bundle.get("trace_directory"),
            "matched_input_count": baseline_bundle.get("matched_input_count"),
            "unmatched_input_count": baseline_bundle.get("unmatched_input_count"),
        },
        "comparison_rows": rows,
        "original_integrity_after": integrity,
    }

    sanitized_json = key_mgr.sanitize_text(json.dumps(report_obj, indent=2, default=str))
    report_obj = json.loads(sanitized_json)

    json_path = target_dir / "ablation_comparison_report.json"
    md_path = target_dir / "ablation_comparison_report.md"
    json_path.write_text(sanitized_json, encoding="utf-8")

    executed_str = ", ".join(f"`{d}`" for d in report_obj["executed_dimensions"]) or "None"
    skipped_str = ", ".join(f"`{s.get('dimension')}`" for s in skipped) or "None"
    md_lines: List[str] = [
        f"# Per-Dimension & Combined Optimization Ablation Report: `{report_obj.get('workflow_id')}`",
        "",
        "## 1. Suite Metadata",
        "",
        f"- **Suite ID:** `{report_obj.get('suite_id')}`",
        f"- **Workflow ID:** `{report_obj.get('workflow_id')}`",
        f"- **Selected Dimensions Filter:** `{report_obj.get('selected_dimensions')}` (`None` = all dimensions with approved candidates)",
        f"- **Executed Dimensions ({len(report_obj['executed_dimensions'])}):** {executed_str}",
        f"- **Skipped Dimensions ({len(skipped)}):** {skipped_str}",
        f"- **Combined Run Included:** `{report_obj['include_combined']}`",
        f"- **Runs Per Configuration (`num_runs`):** `{report_obj['num_runs']}`",
        f"- **Generated At:** {report_obj['generated_at']}",
        "",
        "## 2. Fixed Historical Baseline Reference",
        "",
        f"- **Source:** `{report_obj['baseline_evidence']['source']}` | **Execution Mode:** `{report_obj['baseline_evidence']['execution_mode']}`",
        f"- **Re-executed:** `{report_obj['baseline_evidence']['re_executed']}` | **Groq API Calls:** `{report_obj['baseline_evidence']['groq_api_calls']}`",
        f"- **Fixed Baseline Reference ID:** `{report_obj['baseline_evidence']['fixed_baseline_reference_id']}`",
        f"- **Matched Inputs:** `{report_obj['baseline_evidence']['matched_input_count']}` (unmatched: `{report_obj['baseline_evidence']['unmatched_input_count']}`)",
        "",
        "## 3. Isolated Per-Dimension vs. Combined Comparison",
        "",
        "| Configuration | Scope | Applied Candidates | Runs Passed / Executed | Mean Latency (s) | Latency Delta (%) | Mean Tokens | Token Delta (%) | Mean Cost (USD) | Cost Delta (%) | Groq Calls | Structural Validity (%) | Assessment | Report |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for row in rows:
        cands = ", ".join(f"`{c}`" for c in (row.get("applied_candidate_ids") or [])) or "-"
        runs_str = f"{row.get('successful_runs')}/{row.get('runs_executed')}"
        rep_ref = f"`{row.get('markdown_report_path')}`" if row.get("markdown_report_path") else "-"
        md_lines.append(
            f"| `{row.get('label')}` | `{row.get('scope_kind')}` | {cands} | {runs_str} | "
            f"{_fmt_val(row.get('mean_latency_seconds'))} | {_fmt_val(row.get('latency_improvement_pct'), '%')} | "
            f"{_fmt_val(row.get('mean_tokens'))} | {_fmt_val(row.get('token_improvement_pct'), '%')} | "
            f"{_fmt_val(row.get('mean_cost_usd_catalog_normalized'))} | {_fmt_val(row.get('cost_improvement_pct'), '%')} | "
            f"{_fmt_val(row.get('groq_api_calls'))} | {_fmt_val(row.get('structural_validity_pass_rate_pct'), '%')} | "
            f"`{row.get('assessment_status')}` | {rep_ref} |"
        )

    if skipped:
        md_lines.extend(["", "## 4. Skipped Dimensions", ""])
        for item in skipped:
            md_lines.append(f"- `{item.get('dimension')}`: `{item.get('reason')}`")

    md_lines.extend([
        "",
        "## 5. Original Workflow Integrity",
        "",
        f"- **Original Workflow Unchanged (SHA-256 Verified):** `{integrity.get('original_unchanged')}` (files checked: `{integrity.get('checked_file_count')}`)",
    ])

    sanitized_md = key_mgr.sanitize_text("\n".join(md_lines))
    md_path.write_text(sanitized_md, encoding="utf-8")

    return {
        "json_report_path": str(json_path),
        "markdown_report_path": str(md_path),
        "ablation_report": report_obj,
        "ablation_markdown_report": sanitized_md,
    }


def generate_two_phase_study_reports(
    study_dir: Path,
    study_payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate the 7-section consolidated JSON and Markdown report for the Two-Phase + Combined Study."""
    key_mgr = get_default_key_manager()
    target_dir = Path(study_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    baseline_b = study_payload.get("baseline_runtime_results") or {}
    phase_a = study_payload.get("phase_a_foundation") or {}
    phase_b = study_payload.get("phase_b_variable_dimensions") or {}
    phase_c = study_payload.get("phase_c_combined") or {}
    comp_rows = list(study_payload.get("comparative_configurations") or [])
    pareto = study_payload.get("pareto_selection") or {}
    limitations = list(study_payload.get("limitations") or [])
    integrity = study_payload.get("original_integrity_after") or {}

    report_obj: Dict[str, Any] = {
        "study_id": study_payload.get("study_id"),
        "workflow_id": study_payload.get("workflow_id"),
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "study_dir": str(target_dir),
        "num_runs": int(study_payload.get("num_runs") or 0),
        "quality_acceptance_criteria": study_payload.get("quality_acceptance_criteria"),
        "fixed_optimization_foundation": list(study_payload.get("fixed_optimization_foundation") or []),
        "experimental_setup": {
            "workflow_id": study_payload.get("workflow_id"),
            "fixed_baseline_reference_id": baseline_b.get("fixed_baseline_reference_id"),
            "baseline_re_executed": bool(baseline_b.get("re_executed", False)),
            "baseline_groq_api_calls": int(baseline_b.get("groq_api_calls") or 0),
            "matched_input_count": baseline_b.get("matched_input_count"),
            "excluded_input_count": baseline_b.get("unmatched_input_count"),
            "excluded_records": baseline_b.get("excluded_records") or [],
            "experiment_ids": list(study_payload.get("experiment_ids") or []),
            "num_optimized_runs": int(study_payload.get("num_runs") or 0),
            "live_execution_mode": study_payload.get("live_execution_mode"),
            "ragas_evaluation_model_usage": study_payload.get("ragas_evaluation_model_usage"),
        },
        "phase_a_foundation": phase_a,
        "phase_b_variable_dimensions": phase_b,
        "phase_c_combined": phase_c,
        "comparative_metrics": comp_rows,
        "best_configuration_selection": pareto,
        "limitations": limitations,
        "original_integrity_after": integrity,
    }

    sanitized_json = key_mgr.sanitize_text(json.dumps(report_obj, indent=2, default=str))
    report_obj = json.loads(sanitized_json)

    json_path = target_dir / "study_report.json"
    md_path = target_dir / "study_report.md"
    json_path.write_text(sanitized_json, encoding="utf-8")

    setup = report_obj["experimental_setup"]
    exp_ids_str = ", ".join(f"`{eid}`" for eid in setup["experiment_ids"]) or "None"
    foundation_str = ", ".join(f"`{d}`" for d in report_obj["fixed_optimization_foundation"]) or "None"

    lines: List[str] = [
        f"# Dimension-Wise Optimization, RAGAS Quality & Pareto Selection Report: `{report_obj.get('workflow_id')}`",
        "",
        "## 1. Experimental Setup",
        "",
        f"- **Workflow ID:** `{setup['workflow_id']}`",
        f"- **Study ID:** `{report_obj.get('study_id')}`",
        f"- **Fixed Baseline Reference:** `{setup['fixed_baseline_reference_id']}` (re_executed=`{setup['baseline_re_executed']}`, groq_api_calls=`{setup['baseline_groq_api_calls']}`)",
        f"- **Matched Inputs:** `{setup['matched_input_count']}` | **Excluded / Unmatched Inputs:** `{setup['excluded_input_count']}`",
        f"- **Experiment IDs:** {exp_ids_str}",
        f"- **Optimized Runs Per Config (`num_runs`):** `{setup['num_optimized_runs']}`",
        f"- **Execution Mode:** `{setup['live_execution_mode']}`",
        f"- **Quality Acceptance Criteria:** `{report_obj.get('quality_acceptance_criteria')}`",
        "",
        "## 2. Fixed Foundation Evaluation",
        "",
        f"- **Accepted Fixed Optimization Foundation:** {foundation_str}",
    ]

    for dim in ("communication_data_handoff", "workflow_parallelization"):
        d_info = (phase_a.get("dimension_evaluations") or {}).get(dim)
        if not d_info:
            lines.append(f"- `{dim}`: skipped (no approved candidates)")
            continue
        rag = d_info.get("ragas") or {}
        lines.append(
            f"- **`{dim}`**: accepted=`{d_info.get('accepted')}`, status=`{(d_info.get('quality_acceptance') or {}).get('status')}`, "
            f"latency_delta=`{_fmt_val(d_info.get('latency_improvement_pct'), '%')}`, token_delta=`{_fmt_val(d_info.get('token_improvement_pct'), '%')}`, "
            f"RAGAS=(F:`{rag.get('faithfulness')}`, CP:`{rag.get('context_precision')}`, CR:`{rag.get('context_recall')}`)"
        )
    if phase_a.get("fixed_foundation_verification"):
        ff_v = phase_a["fixed_foundation_verification"]
        ff_rag = ff_v.get("ragas") or {}
        lines.append(
            f"- **`fixed_foundation` Combined Gate**: latency=`{_fmt_val(ff_v.get('mean_latency_seconds'), 's')}`, "
            f"tokens=`{_fmt_val(ff_v.get('mean_tokens'))}`, cost=`${_fmt_val(ff_v.get('mean_cost_usd'))}`, "
            f"RAGAS=(F:`{ff_rag.get('faithfulness')}`, CP:`{ff_rag.get('context_precision')}`, CR:`{ff_rag.get('context_recall')}`)"
        )

    lines.extend(["", "## 3. Individual Variable-Dimension Evaluation", ""])
    var_evals = phase_b.get("dimension_evaluations") or {}
    if not var_evals:
        lines.append("- No variable-dimension experiments executed.")
    for dim, d_info in var_evals.items():
        rag = d_info.get("ragas") or {}
        lines.append(
            f"- **Fixed Foundation + `{dim}`**: accepted=`{d_info.get('accepted')}`, "
            f"quality_status=`{(d_info.get('quality_acceptance') or {}).get('status')}`, "
            f"latency=`{_fmt_val(d_info.get('mean_latency_seconds'), 's')}` ({_fmt_val(d_info.get('latency_improvement_pct'), '%')}), "
            f"tokens=`{_fmt_val(d_info.get('mean_tokens'))}` ({_fmt_val(d_info.get('token_improvement_pct'), '%')}), "
            f"cost=`${_fmt_val(d_info.get('mean_cost_usd'))}` ({_fmt_val(d_info.get('cost_improvement_pct'), '%')}), "
            f"RAGAS=(F:`{rag.get('faithfulness')}`, CP:`{rag.get('context_precision')}`, CR:`{rag.get('context_recall')}`)"
        )

    lines.extend(["", "## 4. Combined Optimization", ""])
    comb_eval = phase_c.get("evaluation")
    if not comb_eval:
        lines.append("- Combined optimization was not executed.")
    else:
        c_rag = comb_eval.get("ragas") or {}
        lines.append(
            f"- **Applied Dimensions:** {', '.join(f'`{d}`' for d in (phase_c.get('applied_dimensions') or []))}"
        )
        lines.append(
            f"- **Performance & Quality:** latency=`{_fmt_val(comb_eval.get('mean_latency_seconds'), 's')}`, "
            f"tokens=`{_fmt_val(comb_eval.get('mean_tokens'))}`, cost=`${_fmt_val(comb_eval.get('mean_cost_usd'))}`, "
            f"quality_accepted=`{comb_eval.get('accepted')}`, "
            f"RAGAS=(F:`{c_rag.get('faithfulness')}`, CP:`{c_rag.get('context_precision')}`, CR:`{c_rag.get('context_recall')}`)"
        )
        if phase_c.get("interaction_notes"):
            lines.append(f"- **Interactions / Regressions:** {'; '.join(phase_c['interaction_notes'])}")

    lines.extend([
        "",
        "## 5. Comparative Metrics",
        "",
        "| Configuration | Scope | Execution Passed | Mean Latency (s) | Input Tokens | Output Tokens | Total Tokens | Cost (USD) | Faithfulness | Context Precision | Context Recall | Quality Status |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ])
    for row in comp_rows:
        lines.append(
            f"| `{row.get('name')}` | `{row.get('scope_kind')}` | `{row.get('execution_passed')}` | "
            f"{_fmt_val(row.get('mean_latency_seconds'))} | {_fmt_val(row.get('mean_prompt_tokens'))} | "
            f"{_fmt_val(row.get('mean_completion_tokens'))} | {_fmt_val(row.get('mean_tokens'))} | "
            f"{_fmt_val(row.get('mean_cost_usd'))} | `{row.get('faithfulness')}` | "
            f"`{row.get('context_precision')}` | `{row.get('context_recall')}` | `{row.get('quality_status')}` |"
        )

    lines.extend(["", "## 6. Best Configuration Selection", ""])
    pareto_names = [p.get("name") for p in (pareto.get("pareto_efficient_configurations") or [])]
    lines.extend([
        f"- **Pareto-Efficient Configurations (Non-Dominated, Quality-Accepted):** {', '.join(f'`{n}`' for n in pareto_names) or 'None'}",
        f"- **Best Latency Configuration:** `{(pareto.get('best_latency_configuration') or {}).get('name') or 'None'}`",
        f"- **Best Token-Efficiency Configuration:** `{(pareto.get('best_token_efficiency_configuration') or {}).get('name') or 'None'}`",
        f"- **Best Cost-Efficiency Configuration:** `{(pareto.get('best_cost_efficiency_configuration') or {}).get('name') or 'None'}`",
        f"- **Recommended Overall Configuration:** `{(pareto.get('recommended_overall_configuration') or {}).get('name') or 'None (see selection note)'}`",
        f"- **Selection Note:** {pareto.get('selection_note')}",
    ])

    lines.extend(["", "## 7. Limitations and Final Assessment", ""])
    lines.append(
        f"- **Original Workflow Unchanged (SHA-256 Verified):** `{integrity.get('original_unchanged')}`"
    )
    eval_usage = setup.get("ragas_evaluation_model_usage") or {}
    lines.append(
        f"- **Isolated RAGAS Evaluator Usage (Excluded from Workflow Tokens/Cost):** "
        f"calls=`{eval_usage.get('api_calls')}`, tokens=`{eval_usage.get('total_tokens')}`, cost=`${eval_usage.get('estimated_cost_usd')}`"
    )
    for lim in limitations or ["Historical baseline traces come from prior recorded runs rather than live concurrent re-execution."]:
        lines.append(f"- {lim}")

    sanitized_md = key_mgr.sanitize_text("\n".join(lines))
    md_path.write_text(sanitized_md, encoding="utf-8")

    return {
        "json_report_path": str(json_path),
        "markdown_report_path": str(md_path),
        "study_report": report_obj,
        "study_markdown_report": sanitized_md,
    }
