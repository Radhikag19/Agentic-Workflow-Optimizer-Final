"""
Output Quality Evaluator for Sandbox Optimization Experiments:
Evaluates agent and workflow outputs across 5 explicit criteria:
1. structural_validity (Pydantic contract adherence)
2. correctness (grounding against input/evidence; LLM-judge or unavailable when semantic reference lacks)
3. completeness (required fields & non-empty declared outputs)
4. consistency (cross-agent IDs, counts, deterministic score formulas)
5. instruction_adherence (role constraints, non-autonomous hiring rule, evidence traceability)

Never treats valid JSON/Pydantic syntax as proof of semantic correctness, and never
fabricates quality scores when evidence or semantic judgment is unavailable.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from optimization_agent.key_manager import GroqKeyManager, get_default_key_manager
from optimization_agent.sandbox.runtime.runner import (
    _calculate_recruitment_match_score,
    _extract_json_dict,
    _validate_agent_output_schema_detailed,
)


def _norm_status(val: Any) -> str:
    s = str(val or "").strip().lower()
    if s in ("passed", "failed", "unavailable"):
        return s
    return "unavailable"


def _evaluate_deterministic_checks(
    agent_id: str,
    output: Any,
    *,
    workflow_input: Optional[Dict[str, Any]],
    upstream_outputs: Optional[Dict[str, Any]],
    agent_spec: Optional[Dict[str, Any]],
    execution_record: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    issues: List[str] = []
    rec = execution_record or {}
    w_in = workflow_input or {}
    up = upstream_outputs or {}
    spec = agent_spec or {}

    if rec.get("status") == "FAILED" or output is None:
        return {
            "structural_validity": "failed",
            "correctness": "failed",
            "completeness": "failed",
            "consistency": "failed",
            "instruction_adherence": "failed",
            "semantic_quality": "unavailable",
            "identified_issues": [f"Agent execution failed or returned empty output: {rec.get('error') or 'null output'}"],
            "rationale": "Execution failed before a structured output was produced.",
            "evaluation_status": "failed",
        }

    schema_ok, schema_err, missing_fields, _ = _validate_agent_output_schema_detailed(agent_id, output)
    structural_status = "passed" if schema_ok else "failed"
    if not schema_ok:
        issues.append(f"Schema validation failed: {schema_err}")

    if rec.get("replay_sample_validity") == "invalid_or_insufficient_evaluation_sample":
        issues.append(
            "Replayed historical sample is incomplete / missing required fields "
            f"{rec.get('replay_missing_required_fields') or missing_fields}."
        )
        return {
            "structural_validity": "failed",
            "correctness": "unavailable",
            "completeness": "failed",
            "consistency": "unavailable",
            "instruction_adherence": "failed",
            "semantic_quality": "unavailable",
            "identified_issues": issues,
            "rationale": "Historical trace sample is insufficient for reliable semantic evaluation.",
            "evaluation_status": "insufficient_sample",
        }

    if not isinstance(output, dict):
        return {
            "structural_validity": "failed",
            "correctness": "failed",
            "completeness": "failed",
            "consistency": "failed",
            "instruction_adherence": "failed",
            "semantic_quality": "unavailable",
            "identified_issues": issues or ["Output is not a JSON object."],
            "rationale": "Output is not a structured JSON object.",
            "evaluation_status": "completed",
        }

    # Completeness: missing required fields or declared output fields absent
    declared_fields = list(spec.get("output_fields") or [])
    missing_declared = [f for f in declared_fields if f not in output]
    if missing_fields or missing_declared:
        completeness_status = "failed"
        if missing_fields:
            issues.append(f"Missing required schema fields: {missing_fields}")
        if missing_declared:
            issues.append(f"Missing declared workflow output_fields: {missing_declared}")
    else:
        completeness_status = "passed"

    # Consistency & Instruction Adherence deterministic checks
    consistency_checks: List[bool] = []
    adherence_checks: List[bool] = [True]  # valid JSON dict parsed cleanly
    correctness_checks: List[bool] = []

    res_in = w_in.get("resume") if isinstance(w_in.get("resume"), dict) else {}
    job_in = w_in.get("job") if isinstance(w_in.get("job"), dict) else {}

    # Grounding against workflow input where IDs exist
    if res_in.get("candidate_id") and "candidate_id" in output:
        ok_cid = output.get("candidate_id") == res_in.get("candidate_id")
        correctness_checks.append(ok_cid)
        if not ok_cid:
            issues.append(
                f"Input grounding mismatch on candidate_id: expected '{res_in.get('candidate_id')}', got '{output.get('candidate_id')}'."
            )
    if job_in.get("job_id") and "job_id" in output:
        ok_jid = output.get("job_id") == job_in.get("job_id")
        correctness_checks.append(ok_jid)
        if not ok_jid:
            issues.append(
                f"Input grounding mismatch on job_id: expected '{job_in.get('job_id')}', got '{output.get('job_id')}'."
            )

    # Cross-agent ID consistency
    for aid_up, up_out in up.items():
        if isinstance(up_out, dict):
            if up_out.get("candidate_id") and output.get("candidate_id"):
                ok_up = up_out["candidate_id"] == output["candidate_id"]
                consistency_checks.append(ok_up)
                if not ok_up:
                    issues.append(f"candidate_id diverges from upstream '{aid_up}'.")
            if up_out.get("job_id") and output.get("job_id"):
                ok_j = up_out["job_id"] == output["job_id"]
                consistency_checks.append(ok_j)
                if not ok_j:
                    issues.append(f"job_id diverges from upstream '{aid_up}'.")

    # Agent-specific domain invariants
    if agent_id == "evidence_mapping_agent":
        mappings = output.get("mappings")
        if isinstance(mappings, list):
            s_cnt = int(output.get("supported_count", 0))
            u_cnt = int(output.get("unsupported_count", 0))
            p_cnt = int(output.get("partially_supported_count", 0))
            c_cnt = int(output.get("unclear_count", 0))
            if (s_cnt + u_cnt + p_cnt + c_cnt) == len(mappings):
                consistency_checks.append(True)
            else:
                consistency_checks.append(False)
                issues.append(
                    f"evidence_mapping_agent count mismatch: sum={s_cnt+u_cnt+p_cnt+c_cnt}, len(mappings)={len(mappings)}."
                )

    elif agent_id == "recruiter_summary_agent":
        if output.get("human_review_required") is True:
            adherence_checks.append(True)
        else:
            adherence_checks.append(False)
            issues.append("Instruction violation: human_review_required must be True.")

        if "final_recommendation" in output and output.get("final_recommendation") in ("REJECT", "HIRE", "NOT_QUALIFIED"):
            adherence_checks.append(False)
            issues.append(
                f"Instruction violation: output contains autonomous hiring decision field final_recommendation='{output.get('final_recommendation')}'."
            )

        matrix = output.get("criteria_matrix")
        if isinstance(matrix, list) and "deterministic_match_score" in output:
            expected_score = _calculate_recruitment_match_score(matrix)
            try:
                actual_score = float(output["deterministic_match_score"])
                if abs(expected_score - actual_score) <= 0.15:
                    consistency_checks.append(True)
                else:
                    consistency_checks.append(False)
                    issues.append(
                        f"deterministic_match_score={actual_score} disagrees with criteria_matrix formula={expected_score}."
                    )
            except Exception:
                consistency_checks.append(False)
                issues.append("deterministic_match_score is non-numeric.")

    consistency_status = (
        ("passed" if all(consistency_checks) else "failed")
        if consistency_checks
        else "unavailable"
    )
    adherence_status = "passed" if all(adherence_checks) else "failed"
    correctness_status = (
        ("passed" if all(correctness_checks) else "failed")
        if correctness_checks
        else "unavailable"
    )

    return {
        "structural_validity": structural_status,
        "correctness": correctness_status,
        "completeness": completeness_status,
        "consistency": consistency_status,
        "instruction_adherence": adherence_status,
        "semantic_quality": "unavailable",
        "identified_issues": issues,
        "rationale": "Deterministic structural, completeness, and domain invariant checks completed.",
        "evaluation_status": "completed",
    }


def _run_llm_judge(
    *,
    workflow_id: str,
    agent_id: str,
    output: Dict[str, Any],
    workflow_input: Optional[Dict[str, Any]],
    upstream_outputs: Optional[Dict[str, Any]],
    agent_spec: Optional[Dict[str, Any]],
    judge_callable: Optional[Callable[..., Dict[str, Any]]] = None,
    key_mgr: Optional[GroqKeyManager] = None,
) -> Optional[Dict[str, Any]]:
    if judge_callable is not None:
        return judge_callable(
            agent_id=agent_id,
            output=output,
            workflow_input=workflow_input or {},
            upstream_outputs=upstream_outputs or {},
            agent_spec=agent_spec or {},
        )

    mgr = key_mgr or get_default_key_manager()
    try:
        raw_key, _, _ = mgr.get_key_for_task("tradeoff_assessment")
    except Exception:
        return None

    try:
        from groq import Groq

        client = Groq(api_key=raw_key, timeout=20.0)
        prompt = {
            "task": "Evaluate MAS agent output quality conservatively. Never rubber-stamp.",
            "agent_id": agent_id,
            "role": (agent_spec or {}).get("role"),
            "goal": (agent_spec or {}).get("goal"),
            "workflow_input": workflow_input or {},
            "upstream_outputs": upstream_outputs or {},
            "agent_output": output,
            "required_json_keys": [
                "correctness",
                "completeness",
                "consistency",
                "instruction_adherence",
                "semantic_quality",
                "identified_issues",
                "rationale",
            ],
            "allowed_verdicts": ["passed", "failed", "unavailable"],
        }
        resp = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": "You are a strict QA evaluator for multi-agent outputs. Return JSON only.",
                },
                {"role": "user", "content": json.dumps(prompt, default=str)[:9000]},
            ],
            temperature=0.0,
            max_tokens=800,
            response_format={"type": "json_object"},
        )
        return _extract_json_dict(resp.choices[0].message.content or "{}")
    except Exception:
        return None


def evaluate_agent_output_quality(
    agent_id: str,
    output: Any,
    *,
    workflow_id: str = "",
    workflow_input: Optional[Dict[str, Any]] = None,
    upstream_outputs: Optional[Dict[str, Any]] = None,
    agent_spec: Optional[Dict[str, Any]] = None,
    execution_record: Optional[Dict[str, Any]] = None,
    judge_callable: Optional[Callable[..., Dict[str, Any]]] = None,
    enable_llm_judge: bool = False,
    key_mgr: Optional[GroqKeyManager] = None,
) -> Dict[str, Any]:
    """
    Evaluate a single agent execution across structural validity and semantic quality dimensions.
    Returns structured evaluation fields without conflating schema validity with semantic quality.
    """
    det = _evaluate_deterministic_checks(
        agent_id,
        output,
        workflow_input=workflow_input,
        upstream_outputs=upstream_outputs,
        agent_spec=agent_spec,
        execution_record=execution_record,
    )

    if det["evaluation_status"] in ("failed", "insufficient_sample"):
        return {"agent_id": agent_id, **det}

    mode = str((execution_record or {}).get("mode") or "")
    has_reference = bool(workflow_input or upstream_outputs)

    # Invoke semantic evaluator ONLY when callable supplied OR enable_llm_judge=True on live outputs
    judge_res: Optional[Dict[str, Any]] = None
    if judge_callable is not None or (enable_llm_judge and mode == "live_llm_execution" and has_reference):
        judge_res = _run_llm_judge(
            workflow_id=workflow_id,
            agent_id=agent_id,
            output=output,
            workflow_input=workflow_input,
            upstream_outputs=upstream_outputs,
            agent_spec=agent_spec,
            judge_callable=judge_callable,
            key_mgr=key_mgr,
        )

    if isinstance(judge_res, dict):
        issues = list(det["identified_issues"])
        for ji in judge_res.get("identified_issues") or []:
            if str(ji) not in issues:
                issues.append(str(ji))

        # Deterministic failure always overrides an optimistic judge verdict
        def _combine(det_val: str, judge_key: str) -> str:
            if det_val == "failed":
                return "failed"
            j_val = _norm_status(judge_res.get(judge_key))
            if j_val != "unavailable":
                return j_val
            return det_val

        return {
            "agent_id": agent_id,
            "structural_validity": det["structural_validity"],
            "correctness": _combine(det["correctness"], "correctness"),
            "completeness": _combine(det["completeness"], "completeness"),
            "consistency": _combine(det["consistency"], "consistency"),
            "instruction_adherence": _combine(det["instruction_adherence"], "instruction_adherence"),
            "semantic_quality": (
                "failed"
                if det["structural_validity"] == "failed" and _norm_status(judge_res.get("semantic_quality")) == "failed"
                else _norm_status(judge_res.get("semantic_quality"))
            ),
            "identified_issues": issues,
            "rationale": str(judge_res.get("rationale") or det["rationale"]),
            "evaluation_status": "completed",
        }

    # Without a semantic judge, semantic_quality stays explicitly 'unavailable'
    return {
        "agent_id": agent_id,
        "structural_validity": det["structural_validity"],
        "correctness": det["correctness"],
        "completeness": det["completeness"],
        "consistency": det["consistency"],
        "instruction_adherence": det["instruction_adherence"],
        "semantic_quality": "unavailable",
        "identified_issues": det["identified_issues"],
        "rationale": (
            f"{det['rationale']} Semantic LLM-judge did not run; semantic_quality remains 'unavailable'."
        ),
        "evaluation_status": det["evaluation_status"],
    }


def _aggregate_variant_quality(
    traces: List[Dict[str, Any]],
    specs_by_agent: Dict[str, Dict[str, Any]],
    *,
    workflow_id: str,
    judge_callable: Optional[Callable[..., Dict[str, Any]]] = None,
    enable_llm_judge: bool = False,
) -> Dict[str, Any]:
    """Evaluate all traces for a single workflow variant using identical criteria."""
    dimensions = (
        "structural_validity",
        "correctness",
        "completeness",
        "consistency",
        "instruction_adherence",
        "semantic_quality",
    )
    per_agent_evals: List[Dict[str, Any]] = []
    by_agent: Dict[str, List[Dict[str, Any]]] = {}

    for t in traces or []:
        w_in = t.get("input_snapshot") or {}
        execs = t.get("agent_executions") or []
        prior_outputs: Dict[str, Any] = {}
        for ex in execs:
            aid = ex.get("agent_id")
            if not aid:
                continue
            ev = evaluate_agent_output_quality(
                aid,
                ex.get("output"),
                workflow_id=workflow_id,
                workflow_input={"resume": {"candidate_id": w_in.get("candidate_id"), "application_id": w_in.get("application_id"), "candidate_name": w_in.get("candidate_name")}, "job": {"job_id": w_in.get("job_id"), "job_title": w_in.get("job_title")}},
                upstream_outputs=dict(prior_outputs),
                agent_spec=specs_by_agent.get(aid) or {},
                execution_record=ex,
                judge_callable=judge_callable,
                enable_llm_judge=enable_llm_judge,
            )
            ev["run_id"] = t.get("run_id")
            ev["run_index"] = t.get("run_index")
            per_agent_evals.append(ev)
            by_agent.setdefault(aid, []).append(ev)
            if ex.get("status") == "SUCCESS" and ex.get("output") is not None:
                prior_outputs[aid] = ex.get("output")

    dimension_summary: Dict[str, Any] = {}
    for dim in dimensions:
        vals = [e.get(dim) for e in per_agent_evals if e.get(dim) in ("passed", "failed")]
        if not vals:
            dimension_summary[dim] = {
                "status": "unavailable",
                "pass_rate_pct": None,
                "passed_count": 0,
                "failed_count": 0,
                "evaluated_count": 0,
            }
        else:
            p_cnt = sum(1 for v in vals if v == "passed")
            f_cnt = len(vals) - p_cnt
            rate = round((p_cnt / len(vals)) * 100.0, 2)
            dimension_summary[dim] = {
                "status": "passed" if f_cnt == 0 else "failed",
                "pass_rate_pct": rate,
                "passed_count": p_cnt,
                "failed_count": f_cnt,
                "evaluated_count": len(vals),
            }

    return {
        "evaluated_executions": len(per_agent_evals),
        "dimension_summary": dimension_summary,
        "agent_evaluations": per_agent_evals,
        "by_agent": by_agent,
    }


def _load_specs_summary(wf_dir: Any) -> Dict[str, Dict[str, Any]]:
    from pathlib import Path

    p = Path(wf_dir)
    wf_json = p / "workflow.json"
    if not wf_json.exists():
        return {}
    data = json.loads(wf_json.read_text(encoding="utf-8"))
    return {
        a["agent_id"]: a
        for a in (data.get("agents") or [])
        if isinstance(a, dict) and a.get("agent_id")
    }


def evaluate_workflow_quality(
    *,
    workflow_id: str,
    baseline_runtime_results: Optional[Dict[str, Any]],
    optimized_runtime_results: Dict[str, Any],
    original_workflow_dir: Any,
    sandbox_workflow_dir: Any,
    judge_callable: Optional[Callable[..., Dict[str, Any]]] = None,
    enable_llm_judge: bool = False,
) -> Dict[str, Any]:
    """
    Evaluate output quality across baseline and optimized runs and detect quality regressions.
    """
    base_specs = _load_specs_summary(original_workflow_dir)
    opt_specs = _load_specs_summary(sandbox_workflow_dir)

    base_traces = list((baseline_runtime_results or {}).get("traces") or [])
    opt_traces = list((optimized_runtime_results or {}).get("traces") or [])

    base_summary = _aggregate_variant_quality(
        base_traces,
        base_specs,
        workflow_id=workflow_id,
        judge_callable=judge_callable,
        enable_llm_judge=enable_llm_judge,
    ) if base_traces else {
        "evaluated_executions": 0,
        "dimension_summary": {
            dim: {"status": "unavailable", "pass_rate_pct": None, "passed_count": 0, "failed_count": 0, "evaluated_count": 0}
            for dim in ("structural_validity", "correctness", "completeness", "consistency", "instruction_adherence", "semantic_quality")
        },
        "agent_evaluations": [],
        "by_agent": {},
    }

    opt_summary = _aggregate_variant_quality(
        opt_traces,
        opt_specs,
        workflow_id=workflow_id,
        judge_callable=judge_callable,
        enable_llm_judge=enable_llm_judge,
    )

    # Identify per-agent regressions between baseline and optimized
    regressions: List[Dict[str, Any]] = []
    check_dims = (
        "structural_validity",
        "correctness",
        "completeness",
        "consistency",
        "instruction_adherence",
        "semantic_quality",
    )
    for aid, opt_list in opt_summary["by_agent"].items():
        base_list = base_summary["by_agent"].get(aid) or []
        if not base_list:
            continue
        for dim in check_dims:
            base_vals = [x.get(dim) for x in base_list if x.get(dim) in ("passed", "failed")]
            opt_vals = [x.get(dim) for x in opt_list if x.get(dim) in ("passed", "failed")]
            if base_vals and opt_vals:
                base_rate = sum(1 for v in base_vals if v == "passed") / len(base_vals)
                opt_rate = sum(1 for v in opt_vals if v == "passed") / len(opt_vals)
                if opt_rate < base_rate:
                    regressions.append({
                        "agent_id": aid,
                        "metric": dim,
                        "baseline_pass_rate_pct": round(base_rate * 100.0, 2),
                        "optimized_pass_rate_pct": round(opt_rate * 100.0, 2),
                        "issues": [i for x in opt_list for i in (x.get("identified_issues") or [])][:5],
                    })

    # Clean up internal by_agent helper mapping before JSON serialization
    base_clean = {k: v for k, v in base_summary.items() if k != "by_agent"}
    opt_clean = {k: v for k, v in opt_summary.items() if k != "by_agent"}

    return {
        "workflow_id": workflow_id,
        "baseline_quality": base_clean,
        "optimized_quality": opt_clean,
        "identified_regressions": regressions,
        "has_quality_regression": len(regressions) > 0,
    }
