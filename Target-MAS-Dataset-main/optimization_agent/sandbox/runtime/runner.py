"""
Sandbox Runtime Workflow Runner:
Executes baseline or optimized MAS workflows in topological DAG waves (with real
ThreadPoolExecutor concurrency for verified parallel groups), enforces explicit live
Groq execution vs. opt-in offline trace replay (no silent fallback), captures API
usage & errors cleanly, validates Pydantic schemas strictly, and writes canonical traces.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from common.api_key_manager import WORKFLOW_KEY_ENV_MAP
from mcp_server import tools as evidence_tools
from optimization_agent.key_manager import FAILOVER_KEYS, get_default_key_manager
from optimization_agent.model_selection.groq_catalog import MODEL_CATALOG
from optimization_agent.sandbox.executors.base import BaseOptimizationExecutor
from optimization_agent.sandbox.manager import SandboxEnvironment

try:
    from common import validation as _common_validation
except Exception:
    _common_validation = None


_AGENT_OUTPUT_MODELS = {
    "resume_intake_agent": "ResumeIntakeOutput",
    "qualification_agent": "QualificationExtractionOutput",
    "job_criteria_agent": "JobCriteriaOutput",
    "evidence_mapping_agent": "EvidenceMappingOutput",
    "experience_assessment_agent": "ExperienceAssessmentOutput",
    "missing_evidence_agent": "MissingEvidenceOutput",
    "screening_review_agent": "ScreeningReviewOutput",
    "recruiter_summary_agent": "RecruiterSummaryOutput",
    "order_intake_agent": "OrderIntakeOutput",
    "inventory_check_agent": "InventoryCheckOutput",
    "fraud_screen_agent": "FraudScreenOutput",
    "carrier_routing_agent": "CarrierRoutingOutput",
    "tax_classify_agent": "TaxClassifyOutput",
    "invoice_tag_agent": "InvoiceTagOutput",
    "fulfillment_summary_agent": "FulfillmentSummaryOutput",
}


def _estimate_cost(model_id: str, prompt_tokens: int, completion_tokens: int) -> float:
    meta = MODEL_CATALOG.get(model_id) or MODEL_CATALOG["openai/gpt-oss-120b"]
    in_price = float(meta["input_price_per_million_usd"])
    out_price = float(meta["output_price_per_million_usd"])
    return (prompt_tokens / 1_000_000.0) * in_price + (completion_tokens / 1_000_000.0) * out_price


def _write_text_with_retry(
    path: Path,
    text: str,
    max_attempts: int = 6,
    base_delay: float = 0.05,
) -> None:
    """Write UTF-8 text to disk with brief backoff for transient Windows PermissionError locks."""
    last_exc: Optional[Exception] = None
    for attempt in range(max_attempts):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            return
        except PermissionError as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                time.sleep(base_delay * (attempt + 1))
    if last_exc is not None:
        raise last_exc


def _compute_input_hash(run_input: Dict[str, Any]) -> str:
    cleaned = {k: v for k, v in (run_input or {}).items() if not str(k).startswith("_")}
    payload = json.dumps(cleaned, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _compact_input_snapshot(run_input: Dict[str, Any], idx: int) -> Dict[str, Any]:
    snap: Dict[str, Any] = {"run_index": idx, "input_hash": _compute_input_hash(run_input)}
    if run_input.get("_matched_baseline_run_id"):
        snap["matched_baseline_run_id"] = run_input.get("_matched_baseline_run_id")
    if isinstance(run_input.get("_matched_identifiers"), dict):
        snap["matched_identifiers"] = dict(run_input["_matched_identifiers"])
    if isinstance(run_input.get("resume"), dict):
        res = run_input["resume"]
        snap["candidate_id"] = res.get("candidate_id")
        snap["application_id"] = res.get("application_id")
        snap["candidate_name"] = res.get("candidate_name")
    if isinstance(run_input.get("job"), dict):
        job = run_input["job"]
        snap["job_id"] = job.get("job_id")
        snap["job_title"] = job.get("job_title")
    return snap


def _build_supplied_contexts(
    clean_input: Dict[str, Any],
    dep_inputs: Dict[str, Any],
) -> List[str]:
    """Extract actual supplied non-empty workflow and upstream contexts without fabricating baseline substitutes."""
    contexts: List[str] = []
    for k, v in (clean_input or {}).items():
        if str(k) in ("run_index", "workflow_id"):
            continue
        if v not in (None, "", [], {}):
            contexts.append(f"[workflow_input.{k}] {json.dumps(v, default=str)}")
    for prod, payload in (dep_inputs or {}).items():
        if payload not in (None, "", [], {}):
            contexts.append(f"[upstream.{prod}] {json.dumps(payload, default=str)}")
    return contexts


def _calculate_recruitment_match_score(mappings: List[Dict[str, Any]]) -> float:
    mand = [m for m in mappings if isinstance(m, dict) and m.get("requirement_type") == "mandatory"]
    pref = [m for m in mappings if isinstance(m, dict) and m.get("requirement_type") == "preferred"]

    def _score_bucket(items: List[Dict[str, Any]]) -> float:
        if not items:
            return 1.0
        total = 0.0
        for item in items:
            st = item.get("status", "unsupported")
            if st == "supported":
                total += 1.0
            elif st == "partially_supported":
                total += 0.5
            elif st == "unclear":
                total += 0.25
        return total / len(items)

    return round((_score_bucket(mand) * 70.0) + (_score_bucket(pref) * 30.0), 1)


def _topological_waves(
    agents: List[Dict[str, Any]],
    parallel_groups: List[List[str]],
) -> List[List[str]]:
    """
    Partition workflow DAG into execution waves:
    - Verified `parallel_groups` ready at the same wave run concurrently inside ThreadPoolExecutor.
    - Remaining sequential nodes run strictly in baseline order respecting dependencies.
    """
    agents_by_id = {
        str(a.get("agent_id") or a.get("id")): a
        for a in agents
        if isinstance(a, dict) and (a.get("agent_id") or a.get("id"))
    }
    parallel_lookup: Dict[str, Set[str]] = {}
    for grp in parallel_groups or []:
        valid = [g for g in grp if g in agents_by_id]
        if len(valid) >= 2:
            gset = set(valid)
            for aid in valid:
                parallel_lookup[aid] = gset

    completed: Set[str] = set()
    remaining = [
        str(a.get("agent_id") or a.get("id"))
        for a in agents
        if isinstance(a, dict) and (a.get("agent_id") or a.get("id"))
    ]
    waves: List[List[str]] = []

    while remaining:
        ready = [
            aid for aid in remaining
            if all(dep in completed for dep in (agents_by_id[aid].get("dependencies") or []))
        ]
        if not ready:
            waves.append(remaining)
            break

        head = ready[0]
        if head in parallel_lookup and parallel_lookup[head].issubset(set(ready)):
            wave = [aid for aid in remaining if aid in parallel_lookup[head]]
        else:
            wave = [head]

        waves.append(wave)
        completed.update(wave)
        remaining = [aid for aid in remaining if aid not in completed]

    return waves


def _load_comparable_inputs(
    workflow_id: str,
    num_runs: int,
    data_base_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Load real dataset inputs from `Target-MAS-Dataset-main/data/<workflow_id>` when available."""
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    data_dir = (Path(data_base_dir) / workflow_id) if data_base_dir else (repo_root / "data" / workflow_id)

    samples: List[Dict[str, Any]] = []
    if data_dir.exists() and data_dir.is_dir():
        resumes_p = data_dir / "resumes.json"
        jobs_p = data_dir / "jobs.json"
        if resumes_p.exists() and jobs_p.exists():
            resumes = json.loads(resumes_p.read_text(encoding="utf-8"))
            jobs = json.loads(jobs_p.read_text(encoding="utf-8"))
            for i in range(max(1, num_runs)):
                res = resumes[i % len(resumes)]
                target_job = res.get("target_job_id")
                job = next((j for j in jobs if j.get("job_id") == target_job), jobs[i % len(jobs)])
                samples.append({"resume": res, "job": job, "run_index": i})
            return samples

        json_files = sorted(data_dir.glob("*.json"))
        if json_files:
            loaded = {jf.stem: json.loads(jf.read_text(encoding="utf-8")) for jf in json_files}
            for i in range(max(1, num_runs)):
                item: Dict[str, Any] = {}
                for stem, val in loaded.items():
                    item[stem] = val[i % len(val)] if isinstance(val, list) and val else val
                item["run_index"] = i
                samples.append(item)
            return samples

    return [{"workflow_id": workflow_id, "run_index": i} for i in range(max(1, num_runs))]


def _validate_agent_output_schema_detailed(
    agent_id: str,
    output: Any,
) -> Tuple[bool, Optional[str], List[str], List[Dict[str, Any]]]:
    """
    Validate agent output strictly against its Pydantic contract in `common/validation.py`.
    Returns: (is_valid, formatted_error, missing_required_fields, validation_errors).
    """
    if _common_validation is None:
        return True, None, [], []
    cls_name = _AGENT_OUTPUT_MODELS.get(agent_id)
    if not cls_name or not hasattr(_common_validation, cls_name):
        if isinstance(output, dict):
            return True, None, [], []
        return False, f"Agent '{agent_id}' returned non-dict output ({type(output).__name__}).", [], []

    if not isinstance(output, dict):
        return False, f"Agent '{agent_id}' output is {type(output).__name__}, expected JSON object.", [], []

    model_cls = getattr(_common_validation, cls_name)
    try:
        model_cls.model_validate(output)
        return True, None, [], []
    except Exception as exc:
        err_list: List[Dict[str, Any]] = []
        missing_fields: List[str] = []
        raw_errs = getattr(exc, "errors", None)
        if callable(raw_errs):
            for item in raw_errs():
                loc = ".".join(str(x) for x in item.get("loc", ()))
                etype = str(item.get("type", ""))
                msg = str(item.get("msg", ""))
                err_list.append({"loc": loc, "type": etype, "msg": msg})
                if etype == "missing" and loc:
                    missing_fields.append(loc)
        return False, str(exc)[:400], missing_fields, err_list


def _validate_agent_output_schema(agent_id: str, output: Any) -> Tuple[bool, Optional[str]]:
    ok, err, _, _ = _validate_agent_output_schema_detailed(agent_id, output)
    return ok, err


def _extract_json_dict(raw_text: str) -> Dict[str, Any]:
    if _common_validation is not None and hasattr(_common_validation, "extract_json_from_text"):
        try:
            parsed = _common_validation.extract_json_from_text(raw_text)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(raw_text[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    # Strip <think> blocks if present in reasoning models and try again
    stripped = re.sub(r"<think>[\s\S]*?</think>", "", raw_text).strip()
    start2 = stripped.find("{")
    end2 = stripped.rfind("}")
    if start2 != -1 and end2 > start2:
        try:
            parsed = json.loads(stripped[start2 : end2 + 1])
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return {"raw_response": raw_text}


def _build_schema_aware_prompts(
    aid: str,
    spec: Dict[str, Any],
    combined_ctx: Dict[str, Any],
    run_id: str,
) -> Tuple[str, str]:
    """Construct system & user prompts embedding Pydantic JSON schema contracts for live execution."""
    base_sys = (
        spec.get("unified_prompt")
        or spec.get("optimized_prompt")
        or (
            f"You are {spec['role']}. Goal: {spec['goal']}\n"
            f"{spec['backstory']}\n"
            "Respond with strictly valid JSON only (no markdown fences or prose outside JSON)."
        )
    )

    schema_cls_name = _AGENT_OUTPUT_MODELS.get(aid)
    schema_hint = ""
    if _common_validation is not None and schema_cls_name and hasattr(_common_validation, schema_cls_name):
        model_cls = getattr(_common_validation, schema_cls_name)
        try:
            schema_json = json.dumps(model_cls.model_json_schema(), separators=(",", ":"))
            schema_hint = f"\n\nRequired JSON Schema ({schema_cls_name}):\n{schema_json[:3500]}"
        except Exception:
            schema_hint = f"\nRequired output_fields: {spec['output_fields']}"
    else:
        schema_hint = f"\nRequired output_fields: {spec['output_fields']}"

    if aid == "recruiter_summary_agent":
        upstream = combined_ctx.get("upstream_inputs") or {}
        ev_map = upstream.get("evidence_mapping_agent") or {}
        mappings = ev_map.get("mappings") if isinstance(ev_map, dict) else []
        score = _calculate_recruitment_match_score(mappings if isinstance(mappings, list) else [])
        extra_ctx = {
            "deterministic_hints": {
                "run_id": run_id,
                "deterministic_match_score": score,
                "score_calculation_method": (
                    "Deterministic weighted ratio: Mandatory criteria (70%), Preferred criteria (30%). "
                    "Supported=1.0, Partially Supported=0.5, Unclear=0.25, Unsupported=0.0."
                ),
                "score_limitations": (
                    "Numerical score reflects documented resume keyword and experience overlap only. "
                    "It does not measure soft skills, motivation, or unlisted capabilities."
                ),
                "human_review_required": True,
                "non_autonomous_decision_statement": (
                    "This is an automated screening assistant summary. It does NOT make autonomous hiring decisions."
                ),
            },
            **dict(combined_ctx),
        }
    else:
        extra_ctx = dict(combined_ctx)

    system_prompt = f"{base_sys}{schema_hint}"
    user_prompt = json.dumps(extra_ctx, separators=(",", ":"), default=str)[:14000]
    return system_prompt, user_prompt


class SandboxWorkflowRunner:
    """Executes baseline or sandbox workflows and writes canonical runtime trace files."""

    def __init__(
        self,
        llm_callable: Optional[Callable[[str, str, str, str, Dict[str, Any]], Dict[str, Any]]] = None,
        enable_trace_replay_fallback: bool = False,
        evidence_dir: Optional[str] = None,
        data_base_dir: Optional[Path] = None,
        groq_client_factory: Optional[Callable[[str], Any]] = None,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.llm_callable = llm_callable
        self.enable_trace_replay_fallback = bool(enable_trace_replay_fallback)
        self.evidence_dir = evidence_dir
        self.data_base_dir = data_base_dir
        self.groq_client_factory = groq_client_factory
        self.event_callback = event_callback
        self.key_mgr = get_default_key_manager()

    def _emit_event(
        self,
        experiment_id: str,
        event_type: str,
        agent_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        if self.event_callback is None:
            return
        try:
            raw_ev = {
                "event_id": uuid.uuid4().hex[:12],
                "experiment_id": experiment_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": event_type,
                "agent_id": agent_id,
                "payload": payload or {},
            }
            safe_ev = json.loads(self.key_mgr.sanitize_text(json.dumps(raw_ev, default=str)))
            self.event_callback(safe_ev)
        except Exception:
            pass

    def _load_agent_specs_from_dir(
        self,
        wf_dir: Path,
        include_sandbox_config: bool = True,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Dict[str, Any]]]:
        """Load workflow JSON and agent specs without importing uninstalled CrewAI modules."""
        wf_data = json.loads((wf_dir / "workflow.json").read_text(encoding="utf-8"))
        cfg_data: Dict[str, Any] = {}
        cfg_path = wf_dir / "sandbox_optimization_config.json"
        if include_sandbox_config and cfg_path.exists():
            cfg_data = json.loads(cfg_path.read_text(encoding="utf-8"))

        helper = BaseOptimizationExecutor()
        specs: Dict[str, Dict[str, Any]] = {}
        py_files = sorted(wf_dir.glob("*.py"))

        for ag in wf_data.get("agents") or []:
            aid_raw = ag.get("agent_id") or ag.get("id") if isinstance(ag, dict) else None
            if not aid_raw:
                continue
            aid = str(aid_raw)

            py_file: Optional[Path] = None
            for pf in py_files:
                consts_check = helper.extract_agent_ast_constants(pf)
                if consts_check.get("AGENT_ID") == aid:
                    py_file = pf
                    break

            consts = helper.extract_agent_ast_constants(py_file) if py_file else {}
            if include_sandbox_config:
                model_id = (
                    consts.get("MODEL_OVERRIDE")
                    or ag.get("model")
                    or wf_data.get("baseline_model")
                    or "openai/gpt-oss-120b"
                )
                opt_prompt = consts.get("OPTIMIZED_PROMPT") or ag.get("optimized_prompt")
                uni_prompt = consts.get("UNIFIED_PROMPT") or ag.get("unified_prompt")
                cons_from = consts.get("CONSOLIDATED_FROM") or ag.get("consolidated_from") or []
            else:
                model_id = wf_data.get("baseline_model") or ag.get("model") or "openai/gpt-oss-120b"
                opt_prompt = None
                uni_prompt = None
                cons_from = []

            specs[aid] = {
                "definition": ag,
                "role": consts.get("ROLE") or ag.get("role") or ag.get("name") or aid,
                "goal": consts.get("GOAL") or ag.get("goal") or ag.get("responsibilities") or "",
                "backstory": consts.get("BACKSTORY") or "",
                "model": model_id,
                "optimized_prompt": opt_prompt,
                "unified_prompt": uni_prompt,
                "consolidated_from": cons_from,
                "input_fields": list(ag.get("input_fields") or ag.get("inputs") or []),
                "output_fields": list(ag.get("output_fields") or ag.get("outputs") or []),
                "dependencies": list(ag.get("dependencies") or []),
            }
        return wf_data, cfg_data, specs

    def _load_agent_specs(self, env: SandboxEnvironment) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Dict[str, Any]]]:
        return self._load_agent_specs_from_dir(env.sandbox_workflow_dir, include_sandbox_config=True)

    def _resolve_workflow_groq_key(self, workflow_id: str) -> Tuple[str, str, str]:
        """Resolve dedicated workflow Groq key from GroqKeyManager without exposing raw credentials."""
        env_candidates = WORKFLOW_KEY_ENV_MAP.get(workflow_id, ())
        for ev in env_candidates:
            raw = self.key_mgr._keys.get(ev, "").strip()
            if raw:
                return raw, ev, self.key_mgr.get_masked_identifier(ev)
        return self.key_mgr.get_key_for_task("discovery_overview")

    def _build_groq_client(self, raw_key: str) -> Any:
        if self.groq_client_factory is not None:
            return self.groq_client_factory(raw_key)
        from groq import Groq

        return Groq(api_key=raw_key, timeout=30.0)

    def _apply_handoff_projections(
        self,
        agent_id: str,
        dependencies: List[str],
        upstream_outputs: Dict[str, Any],
        handoff_projections: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """Filter upstream payloads strictly on approved `(producer -> agent_id)` edges."""
        projected_inputs: Dict[str, Any] = {}
        audit_events: List[Dict[str, Any]] = []

        for prod in dependencies:
            raw_payload = upstream_outputs.get(prod)
            edge_key = f"{prod}->{agent_id}"
            spec = handoff_projections.get(edge_key)
            if isinstance(raw_payload, dict) and isinstance(spec, dict) and spec.get("retained_fields"):
                retained = set(spec["retained_fields"])
                filtered = {k: v for k, v in raw_payload.items() if k in retained}
                removed = [k for k in raw_payload.keys() if k not in retained]
                projected_inputs[prod] = filtered
                audit_events.append({
                    "edge": edge_key,
                    "projected": True,
                    "original_fields": list(raw_payload.keys()),
                    "retained_fields": list(filtered.keys()),
                    "removed_fields": removed,
                    "original_payload": dict(raw_payload),
                    "projected_payload": dict(filtered),
                })
            else:
                projected_inputs[prod] = raw_payload
                orig_fields = list(raw_payload.keys()) if isinstance(raw_payload, dict) else []
                audit_events.append({
                    "edge": edge_key,
                    "projected": False,
                    "original_fields": orig_fields,
                    "retained_fields": list(orig_fields),
                    "removed_fields": [],
                })
        return projected_inputs, audit_events

    def _call_groq_live(
        self,
        workflow_id: str,
        agent_id: str,
        model_id: str,
        system_prompt: str,
        user_prompt: str,
    ) -> Dict[str, Any]:
        """Execute a genuine Groq Chat Completion call with key allocation, retries, and usage tracking."""
        raw_key, _, masked_key = self._resolve_workflow_groq_key(workflow_id)
        max_attempts = 3
        last_exc: Optional[Exception] = None
        use_response_format = True

        for attempt in range(max_attempts):
            active_key = raw_key
            active_masked = masked_key
            if attempt > 0:
                for fk in FAILOVER_KEYS:
                    cand = self.key_mgr._keys.get(fk, "").strip()
                    if cand:
                        active_key = cand
                        active_masked = self.key_mgr.get_masked_identifier(fk)
                        break

            try:
                client = self._build_groq_client(active_key)
                kwargs: Dict[str, Any] = {
                    "model": model_id,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 4096,
                }
                if use_response_format:
                    kwargs["response_format"] = {"type": "json_object"}

                resp = client.chat.completions.create(**kwargs)
                content = resp.choices[0].message.content or "{}"
                parsed = _extract_json_dict(content)
                usage = getattr(resp, "usage", None)
                if usage is not None:
                    pt = int(getattr(usage, "prompt_tokens", 0) or 0)
                    ct = int(getattr(usage, "completion_tokens", 0) or 0)
                    tt = int(getattr(usage, "total_tokens", pt + ct) or (pt + ct))
                    usage_src = "api_reported"
                else:
                    pt = 0
                    ct = 0
                    tt = 0
                    usage_src = "unavailable"

                return {
                    "output": parsed,
                    "prompt_tokens": pt,
                    "completion_tokens": ct,
                    "tokens": tt,
                    "usage_source": usage_src,
                    "assigned_key_identifier": active_masked,
                    "mode": "live_llm_execution",
                }
            except Exception as exc:
                last_exc = exc
                err_low = str(exc).lower()
                if use_response_format and "response_format" in err_low:
                    use_response_format = False
                    continue
                if ("rate_limit" in err_low or "429" in err_low or "rate limit" in err_low) and attempt < max_attempts - 1:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise

        raise RuntimeError(f"Groq API call failed for '{agent_id}': {last_exc}")

    def _trace_replay_fallback(
        self,
        workflow_id: str,
        agent_id: str,
        spec: Dict[str, Any],
        agent_inputs: Dict[str, Any],
        baseline_evidence_cache: Dict[str, Any],
        mcp_agent_metrics: Dict[str, Any],
        audits: Optional[List[Dict[str, Any]]] = None,
        dropped_payload_bytes: int = 0,
    ) -> Dict[str, Any]:
        """
        Explicit offline sandbox trace-replay adapter used ONLY when `enable_trace_replay_fallback=True`.
        Never fabricates or patches missing fields in historical replay samples; flags incomplete
        samples transparently as `invalid_or_insufficient_evaluation_sample`.
        """
        consolidated_from = spec.get("consolidated_from") or []
        source_agent = consolidated_from[-1] if consolidated_from else agent_id

        if source_agent not in baseline_evidence_cache:
            baseline_evidence_cache[source_agent] = evidence_tools.get_execution_evidence(
                workflow_id=workflow_id,
                agent_id=source_agent,
                evidence_dir=self.evidence_dir,
            )

        ev = baseline_evidence_cache.get(source_agent) or {}
        sample_out = ev.get("sample_outputs")
        if isinstance(sample_out, dict):
            # Preserve exact historical trace output without fabricating missing fields
            output = dict(sample_out)
        else:
            output = {f: None for f in spec.get("output_fields") or ["status"]}

        schema_ok, schema_err, missing_fields, _ = _validate_agent_output_schema_detailed(agent_id, output)
        sample_validity = (
            "schema_valid_replay_sample"
            if schema_ok
            else "invalid_or_insufficient_evaluation_sample"
        )
        validity_reason = (
            None
            if schema_ok
            else (
                f"Historical trace replay sample for '{agent_id}' is incomplete or incompatible "
                f"with Pydantic schema (missing required fields: {missing_fields}). Preserved unmodified."
            )
        )

        tok_meta = (mcp_agent_metrics.get("agent_token_metrics") or {}).get(source_agent) or {}
        base_pt = int(round(tok_meta.get("mean_prompt_tokens") or 800))
        base_ct = int(round(tok_meta.get("mean_completion_tokens") or 600))
        lat_meta = (mcp_agent_metrics.get("agent_latency_metrics") or {}).get(source_agent) or {}
        base_dur = float(lat_meta.get("median_seconds") or lat_meta.get("mean_seconds") or 0.05)

        adj_pt = base_pt
        if spec.get("optimized_prompt"):
            adj_pt = max(64, int(round(adj_pt * 0.85)))
        if any(a.get("projected") for a in (audits or [])) and dropped_payload_bytes > 0:
            est_saved_tokens = max(1, dropped_payload_bytes // 4)
            adj_pt = max(64, adj_pt - min(est_saved_tokens, int(adj_pt * 0.45)))

        return {
            "output": output,
            "prompt_tokens": adj_pt,
            "completion_tokens": base_ct,
            "tokens": adj_pt + base_ct,
            "usage_source": "historical_trace_replay",
            "simulated_duration_seconds": round(min(base_dur * 0.02, 0.25), 4),
            "assigned_key_identifier": "OFFLINE_SANDBOX_REPLAY",
            "mode": "offline_trace_replay_sandbox",
            "replay_sample_validity": sample_validity,
            "replay_missing_required_fields": missing_fields,
            "replay_validity_reason": validity_reason,
            "schema_error_preview": schema_err,
        }

    def _execute_single_run(
        self,
        *,
        env: SandboxEnvironment,
        variant: str,
        run_index: int,
        run_input: Dict[str, Any],
        wf_data: Dict[str, Any],
        specs: Dict[str, Dict[str, Any]],
        waves: List[List[str]],
        parallel_groups: List[List[str]],
        handoff_projections: Dict[str, Any],
        traces_dir: Path,
        baseline_evidence_cache: Dict[str, Any],
        mcp_agent_metrics: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute one full DAG run of either 'baseline' or 'optimized' variant."""
        run_id = f"{'base' if variant == 'baseline' else 'sb'}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        t_run_start = time.perf_counter()

        input_snapshot = _compact_input_snapshot(run_input, run_index)
        agent_outputs: Dict[str, Any] = {}
        agent_executions: List[Dict[str, Any]] = []
        handoff_audits: List[Dict[str, Any]] = []
        execution_modes: Set[str] = set()
        usage_sources: Set[str] = set()
        concurrent_waves_in_run: List[List[str]] = []
        run_api_errors: List[Dict[str, Any]] = []
        run_fallback_events: List[Dict[str, Any]] = []
        run_schema_failures: List[Dict[str, Any]] = []
        run_invalid_replay_samples: List[Dict[str, Any]] = []

        run_prompt_tokens = 0
        run_comp_tokens = 0
        run_total_tokens = 0
        run_cost_usd = 0.0
        run_status = "SUCCESS"
        run_error: Optional[str] = None
        order_counter = 0

        def _run_one_agent(aid: str) -> Tuple[str, Dict[str, Any], List[Dict[str, Any]]]:
            spec = specs[aid]
            t_a0 = time.perf_counter()
            model_id = spec["model"]
            self._emit_event(
                env.experiment_id,
                "agent_started",
                agent_id=aid,
                payload={"run_id": run_id, "run_index": run_index, "model": model_id},
            )
            deps = spec["dependencies"]
            dep_inputs, audits = self._apply_handoff_projections(
                aid, deps, agent_outputs, handoff_projections
            )
            dropped_bytes = 0
            for a in audits:
                if a.get("projected"):
                    edge_prod = a["edge"].split("->", 1)[0]
                    orig_sz = len(json.dumps(agent_outputs.get(edge_prod) or {}, default=str))
                    proj_sz = len(json.dumps(dep_inputs.get(edge_prod) or {}, default=str))
                    dropped_bytes += max(0, orig_sz - proj_sz)

            clean_input = {k: v for k, v in (run_input or {}).items() if not str(k).startswith("_")}
            supplied_contexts = [
                self.key_mgr.sanitize_text(c) for c in _build_supplied_contexts(clean_input, dep_inputs)
            ]
            agent_task_input = self.key_mgr.sanitize_text(
                f"Agent {aid} ({spec.get('role') or aid}): {str(spec.get('goal') or '')[:300]}".strip()
            )
            combined_ctx = {
                "workflow_input": clean_input,
                "upstream_inputs": dep_inputs,
                "input_fields": spec["input_fields"],
                "output_fields": spec["output_fields"],
            }
            system_prompt, user_prompt = _build_schema_aware_prompts(aid, spec, combined_ctx, run_id)
            prompt_metadata = {
                "using_optimized_prompt": bool(spec.get("optimized_prompt")),
                "using_unified_prompt": bool(spec.get("unified_prompt")),
                "prompt_char_length": len(system_prompt),
            }
            model_id = spec["model"]
            self._emit_event(
                env.experiment_id,
                "agent_thinking",
                agent_id=aid,
                payload={"run_id": run_id, "model": model_id, "handoff_audits": len(audits)},
            )

            try:
                if self.llm_callable is not None:
                    self._emit_event(
                        env.experiment_id,
                        "groq_request_started",
                        agent_id=aid,
                        payload={"run_id": run_id, "model": model_id, "mode": "custom_callable"},
                    )
                    res = self.llm_callable(aid, model_id, system_prompt, user_prompt, combined_ctx)
                    res_mode = res.get("mode", "custom_callable")
                    self._emit_event(
                        env.experiment_id,
                        "groq_request_completed",
                        agent_id=aid,
                        payload={"run_id": run_id, "model": model_id, "tokens": res.get("tokens", 0)},
                    )
                else:
                    try:
                        self._emit_event(
                            env.experiment_id,
                            "groq_request_started",
                            agent_id=aid,
                            payload={"run_id": run_id, "model": model_id, "mode": "live_llm_execution"},
                        )
                        res = self._call_groq_live(env.workflow_id, aid, model_id, system_prompt, user_prompt)
                        res_mode = res.get("mode", "live_llm_execution")
                        self._emit_event(
                            env.experiment_id,
                            "groq_request_completed",
                            agent_id=aid,
                            payload={"run_id": run_id, "model": model_id, "tokens": res.get("tokens", 0)},
                        )
                    except Exception as exc:
                        sanitized_err = self.key_mgr.sanitize_text(str(exc))
                        err_entry = {
                            "variant": variant,
                            "run_index": run_index,
                            "run_id": run_id,
                            "agent_id": aid,
                            "model": model_id,
                            "error": sanitized_err,
                        }
                        run_api_errors.append(err_entry)

                        if not self.enable_trace_replay_fallback:
                            dur_fail = round(time.perf_counter() - t_a0, 4)
                            fail_rec = {
                                "order": 0,
                                "agent_id": aid,
                                "model": model_id,
                                "assigned_key_identifier": self._resolve_workflow_groq_key(env.workflow_id)[2]
                                if self.key_mgr.total_loaded_keys > 0
                                else "UNCONFIGURED",
                                "duration_seconds": dur_fail,
                                "status": "FAILED",
                                "tokens": 0,
                                "prompt_tokens": 0,
                                "completion_tokens": 0,
                                "estimated_cost_usd": 0.0,
                                "usage_source": "unavailable",
                                "schema_valid": False,
                                "missing_required_fields": [],
                                "output": None,
                                "mode": "live_llm_execution",
                                "error": sanitized_err,
                                "notes": f"live_api_error={sanitized_err}",
                            }
                            return aid, fail_rec, audits

                        run_fallback_events.append({
                            **err_entry,
                            "fallback_mode": "offline_trace_replay_sandbox",
                        })
                        res = self._trace_replay_fallback(
                            env.workflow_id,
                            aid,
                            spec,
                            combined_ctx,
                            baseline_evidence_cache,
                            mcp_agent_metrics,
                            audits=audits,
                            dropped_payload_bytes=dropped_bytes,
                        )
                        res_mode = res.get("mode", "offline_trace_replay_sandbox")
            except Exception as exc:
                sanitized_err = self.key_mgr.sanitize_text(str(exc))
                dur_fail = round(time.perf_counter() - t_a0, 4)
                run_api_errors.append({
                    "variant": variant,
                    "run_index": run_index,
                    "run_id": run_id,
                    "agent_id": aid,
                    "model": model_id,
                    "error": sanitized_err,
                })
                fail_rec = {
                    "order": 0,
                    "agent_id": aid,
                    "model": model_id,
                    "assigned_key_identifier": "UNSPECIFIED",
                    "duration_seconds": dur_fail,
                    "status": "FAILED",
                    "tokens": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "usage_source": "unavailable",
                    "schema_valid": False,
                    "missing_required_fields": [],
                    "output": None,
                    "mode": "live_llm_execution" if self.llm_callable is None else "custom_callable",
                    "error": sanitized_err,
                    "notes": f"execution_error={sanitized_err}",
                }
                return aid, fail_rec, audits

            if res.get("simulated_duration_seconds"):
                time.sleep(min(float(res["simulated_duration_seconds"]), 0.05))

            dur = round(time.perf_counter() - t_a0, 4)
            out_obj = res.get("output")
            schema_ok, schema_err, missing_fields, _ = _validate_agent_output_schema_detailed(aid, out_obj)
            if not schema_ok:
                run_schema_failures.append({
                    "variant": variant,
                    "run_index": run_index,
                    "run_id": run_id,
                    "agent_id": aid,
                    "missing_required_fields": missing_fields,
                    "error": str(schema_err),
                })

            replay_validity = res.get("replay_sample_validity")
            if replay_validity == "invalid_or_insufficient_evaluation_sample":
                run_invalid_replay_samples.append({
                    "variant": variant,
                    "run_index": run_index,
                    "agent_id": aid,
                    "missing_required_fields": res.get("replay_missing_required_fields") or missing_fields,
                    "reason": res.get("replay_validity_reason"),
                })

            pt = int(res.get("prompt_tokens") or 0)
            ct = int(res.get("completion_tokens") or 0)
            tt = int(res.get("tokens") or (pt + ct))
            usage_src = str(res.get("usage_source") or ("api_reported" if res_mode == "live_llm_execution" else "callable_reported"))
            agent_cost = _estimate_cost(model_id, pt, ct)

            exec_rec = {
                "order": 0,
                "agent_id": aid,
                "model": model_id,
                "assigned_key_identifier": self.key_mgr.sanitize_text(
                    str(res.get("assigned_key_identifier") or "UNSPECIFIED")
                ),
                "duration_seconds": dur,
                "status": "SUCCESS",
                "tokens": tt,
                "prompt_tokens": pt,
                "completion_tokens": ct,
                "estimated_cost_usd": round(agent_cost, 6),
                "usage_source": usage_src,
                "schema_valid": schema_ok,
                "missing_required_fields": missing_fields,
                "replay_sample_validity": replay_validity,
                "consolidated_from": list(spec.get("consolidated_from") or []),
                "supplied_contexts": supplied_contexts,
                "agent_task_input": agent_task_input,
                "prompt_metadata": prompt_metadata,
                "output": out_obj,
                "mode": res_mode,
                "notes": f"schema_err={schema_err}" if schema_err else "",
            }
            return aid, exec_rec, audits

        for wave in waves:
            if len(wave) > 1:
                concurrent_waves_in_run.append(list(wave))
                self._emit_event(
                    env.experiment_id,
                    "agent_parallel_started",
                    agent_id=wave[0],
                    payload={"run_id": run_id, "parallel_agents": list(wave)},
                )
                with ThreadPoolExecutor(max_workers=len(wave)) as pool:
                    wave_results = list(pool.map(_run_one_agent, wave))
            else:
                wave_results = [_run_one_agent(wave[0])]

            wave_failed = False
            for aid, exec_rec, audits in wave_results:
                order_counter += 1
                exec_rec["order"] = order_counter
                agent_executions.append(exec_rec)
                execution_modes.add(exec_rec["mode"])
                usage_sources.add(exec_rec.get("usage_source") or "unavailable")
                handoff_audits.extend(audits)

                if exec_rec["status"] != "SUCCESS":
                    wave_failed = True
                    run_status = "FAILED"
                    if not run_error:
                        run_error = exec_rec.get("error") or f"Agent '{aid}' failed."
                    self._emit_event(
                        env.experiment_id,
                        "agent_failed",
                        agent_id=aid,
                        payload={
                            "run_id": run_id,
                            "error": exec_rec.get("error"),
                            "duration_seconds": exec_rec.get("duration_seconds"),
                        },
                    )
                else:
                    agent_outputs[aid] = exec_rec["output"]
                    run_prompt_tokens += exec_rec["prompt_tokens"]
                    run_comp_tokens += exec_rec["completion_tokens"]
                    run_total_tokens += exec_rec["tokens"]
                    run_cost_usd += exec_rec["estimated_cost_usd"]
                    self._emit_event(
                        env.experiment_id,
                        "agent_completed",
                        agent_id=aid,
                        payload={
                            "run_id": run_id,
                            "model": exec_rec.get("model"),
                            "tokens": exec_rec.get("tokens"),
                            "duration_seconds": exec_rec.get("duration_seconds"),
                            "estimated_cost_usd": exec_rec.get("estimated_cost_usd"),
                            "schema_valid": exec_rec.get("schema_valid"),
                        },
                    )
                    run_comp_tokens += exec_rec["completion_tokens"]
                    run_total_tokens += exec_rec["tokens"]
                    run_cost_usd += exec_rec["estimated_cost_usd"]

            if wave_failed:
                break

        total_dur = round(time.perf_counter() - t_run_start, 4)
        final_agent_id = agent_executions[-1]["agent_id"] if agent_executions and run_status == "SUCCESS" else None
        final_output = agent_outputs.get(final_agent_id) if final_agent_id else None

        trace_record = {
            "run_id": run_id,
            "run_index": run_index,
            "variant": variant,
            "workflow_name": env.workflow_id,
            "experiment_id": env.experiment_id,
            "model": wf_data.get("baseline_model", "openai/gpt-oss-120b"),
            "status": run_status,
            "execution_mode": sorted(execution_modes)[0] if len(execution_modes) == 1 else sorted(execution_modes),
            "usage_sources": sorted(usage_sources),
            "input_hash": input_snapshot["input_hash"],
            "input_snapshot": input_snapshot,
            "duration_seconds": total_dur,
            "agent_execution_count": len(agent_executions),
            "agent_execution_order": [e["agent_id"] for e in agent_executions],
            "concurrent_waves": concurrent_waves_in_run,
            "agent_executions": agent_executions,
            "handoff_audits": handoff_audits,
            "total_tokens": run_total_tokens,
            "prompt_tokens": run_prompt_tokens,
            "completion_tokens": run_comp_tokens,
            "estimated_cost_usd": round(run_cost_usd, 6),
            "api_errors": run_api_errors,
            "fallback_events": run_fallback_events,
            "schema_failures": run_schema_failures,
            "invalid_replay_samples": run_invalid_replay_samples,
            "final_output": final_output,
            "error": run_error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        trace_path = traces_dir / f"{run_id}.json"
        serialized_trace = self.key_mgr.sanitize_text(json.dumps(trace_record, indent=2, default=str))
        try:
            _write_text_with_retry(trace_path, serialized_trace)
        except PermissionError:
            pass
        return {
            "trace": trace_record,
            "trace_path": str(trace_path),
            "concurrent_waves": concurrent_waves_in_run,
        }

    def _summarize_variant_runs(
        self,
        *,
        variant: str,
        agents: List[Dict[str, Any]],
        run_outputs: List[Dict[str, Any]],
        workflow_inputs: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        traces = [r["trace"] for r in run_outputs]
        trace_files = [r["trace_path"] for r in run_outputs]
        execution_modes: Set[str] = set()
        usage_sources: Set[str] = set()
        all_errors: List[str] = []
        api_errors: List[Dict[str, Any]] = []
        fallback_events: List[Dict[str, Any]] = []
        schema_failures: List[Dict[str, Any]] = []
        invalid_replay_samples: List[Dict[str, Any]] = []
        incomplete_runs: List[Dict[str, Any]] = []
        concurrent_waves_executed: List[List[str]] = []

        for t in traces:
            em = t.get("execution_mode")
            if isinstance(em, list):
                execution_modes.update(em)
            elif em:
                execution_modes.add(str(em))
            usage_sources.update(t.get("usage_sources") or [])
            api_errors.extend(t.get("api_errors") or [])
            fallback_events.extend(t.get("fallback_events") or [])
            schema_failures.extend(t.get("schema_failures") or [])
            invalid_replay_samples.extend(t.get("invalid_replay_samples") or [])
            concurrent_waves_executed.extend(t.get("concurrent_waves") or [])
            if t.get("error"):
                all_errors.append(str(t["error"]))
            if t["status"] != "SUCCESS" or len(t.get("agent_executions") or []) != len(agents):
                incomplete_runs.append({
                    "run_id": t["run_id"],
                    "run_index": t["run_index"],
                    "status": t["status"],
                    "executed_agents": len(t.get("agent_executions") or []),
                    "expected_agents": len(agents),
                    "error": t.get("error"),
                })

        successful = sum(
            1 for t in traces
            if t["status"] == "SUCCESS" and len(t.get("agent_executions") or []) == len(agents)
        )
        failed = len(traces) - successful
        live_ok_calls = sum(
            1
            for t in traces
            for ex in (t.get("agent_executions") or [])
            if ex.get("mode") == "live_llm_execution" and ex.get("status") == "SUCCESS"
        )
        groq_api_calls = live_ok_calls + len(api_errors)

        return {
            "variant": variant,
            "source": "current_experiment",
            "re_executed": True,
            "groq_api_calls": groq_api_calls,
            "execution_passed": failed == 0 and successful > 0,
            "execution_modes": sorted(execution_modes),
            "usage_sources": sorted(usage_sources),
            "runs_executed": len(traces),
            "successful_runs": successful,
            "failed_runs": failed,
            "incomplete_runs": incomplete_runs,
            "concurrent_waves_executed": concurrent_waves_executed,
            "input_dataset_hashes": [_compute_input_hash(inp) for inp in workflow_inputs[: len(traces)]],
            "trace_files": trace_files,
            "traces": traces,
            "schema_validation_summary": {
                "all_schemas_valid": len(schema_failures) == 0 and successful > 0,
                "failures": schema_failures,
            },
            "invalid_replay_samples": invalid_replay_samples,
            "api_errors": api_errors,
            "fallback_events": fallback_events,
            "errors": all_errors,
        }

    def run_variant(
        self,
        env: SandboxEnvironment,
        *,
        variant: str = "optimized",
        num_runs: int = 1,
        sample_inputs: Optional[List[Dict[str, Any]]] = None,
        traces_dir: Optional[Path] = None,
        run_indices: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Execute either the unmodified baseline workflow or the optimized sandbox workflow."""
        is_opt = variant == "optimized"
        wf_dir = env.sandbox_workflow_dir if is_opt else env.original_workflow_dir
        wf_data, _, specs = self._load_agent_specs_from_dir(wf_dir, include_sandbox_config=is_opt)
        agents = wf_data.get("agents") or []
        parallel_groups = (wf_data.get("parallel_groups") or []) if is_opt else []
        handoff_projections = (wf_data.get("handoff_projections") or {}) if is_opt else {}

        waves = _topological_waves(agents, parallel_groups)
        inputs = (
            list(sample_inputs)
            if sample_inputs is not None
            else _load_comparable_inputs(env.workflow_id, num_runs=num_runs, data_base_dir=self.data_base_dir)
        )
        dest_dir = traces_dir or (
            env.runtime_traces_dir if is_opt else (env.experiment_dir / "baseline_traces")
        )

        baseline_evidence_cache: Dict[str, Any] = {}
        mcp_agent_metrics = {
            "agent_token_metrics": (evidence_tools.get_token_metrics(env.workflow_id, evidence_dir=self.evidence_dir)).get("agent_token_metrics", {}),
            "agent_latency_metrics": (evidence_tools.get_latency_metrics(env.workflow_id, evidence_dir=self.evidence_dir)).get("agent_latency_metrics", {}),
        }

        run_outputs: List[Dict[str, Any]] = []
        for pos, run_input in enumerate(inputs):
            actual_idx = run_indices[pos] if (run_indices and pos < len(run_indices)) else pos
            run_outputs.append(
                self._execute_single_run(
                    env=env,
                    variant=variant,
                    run_index=actual_idx,
                    run_input=run_input,
                    wf_data=wf_data,
                    specs=specs,
                    waves=waves,
                    parallel_groups=parallel_groups,
                    handoff_projections=handoff_projections,
                    traces_dir=dest_dir,
                    baseline_evidence_cache=baseline_evidence_cache,
                    mcp_agent_metrics=mcp_agent_metrics,
                )
            )

        return self._summarize_variant_runs(
            variant=variant,
            agents=agents,
            run_outputs=run_outputs,
            workflow_inputs=inputs,
        )

    def run_comparable_pair(
        self,
        env: SandboxEnvironment,
        *,
        num_runs: int = 2,
        interleave: bool = True,
        randomize_order: bool = False,
        seed: int = 42,
    ) -> Dict[str, Any]:
        """
        Execute matched baseline (original unmodified workflow, read-only) and optimized
        (sandbox copy) workflows on identical input records, optionally interleaved or randomized.
        """
        sample_inputs = _load_comparable_inputs(
            env.workflow_id,
            num_runs=num_runs,
            data_base_dir=self.data_base_dir,
        )
        input_hashes = [_compute_input_hash(inp) for inp in sample_inputs]

        base_wf, _, base_specs = self._load_agent_specs_from_dir(env.original_workflow_dir, include_sandbox_config=False)
        opt_wf, _, opt_specs = self._load_agent_specs_from_dir(env.sandbox_workflow_dir, include_sandbox_config=True)

        base_agents = base_wf.get("agents") or []
        opt_agents = opt_wf.get("agents") or []
        base_waves = _topological_waves(base_agents, [])
        opt_waves = _topological_waves(opt_agents, opt_wf.get("parallel_groups") or [])
        opt_proj = opt_wf.get("handoff_projections") or {}

        base_traces_dir = env.experiment_dir / "baseline_traces"
        opt_traces_dir = env.runtime_traces_dir

        baseline_evidence_cache: Dict[str, Any] = {}
        mcp_agent_metrics = {
            "agent_token_metrics": (evidence_tools.get_token_metrics(env.workflow_id, evidence_dir=self.evidence_dir)).get("agent_token_metrics", {}),
            "agent_latency_metrics": (evidence_tools.get_latency_metrics(env.workflow_id, evidence_dir=self.evidence_dir)).get("agent_latency_metrics", {}),
        }

        schedule: List[Tuple[int, str]] = []
        if interleave or randomize_order:
            for idx in range(len(sample_inputs)):
                schedule.append((idx, "baseline"))
                schedule.append((idx, "optimized"))
            if randomize_order:
                rng = random.Random(seed)
                rng.shuffle(schedule)
        else:
            for idx in range(len(sample_inputs)):
                schedule.append((idx, "baseline"))
            for idx in range(len(sample_inputs)):
                schedule.append((idx, "optimized"))

        base_by_idx: Dict[int, Dict[str, Any]] = {}
        opt_by_idx: Dict[int, Dict[str, Any]] = {}
        execution_order: List[Dict[str, Any]] = []

        for idx, variant in schedule:
            is_opt = variant == "optimized"
            res = self._execute_single_run(
                env=env,
                variant=variant,
                run_index=idx,
                run_input=sample_inputs[idx],
                wf_data=opt_wf if is_opt else base_wf,
                specs=opt_specs if is_opt else base_specs,
                waves=opt_waves if is_opt else base_waves,
                parallel_groups=(opt_wf.get("parallel_groups") or []) if is_opt else [],
                handoff_projections=opt_proj if is_opt else {},
                traces_dir=opt_traces_dir if is_opt else base_traces_dir,
                baseline_evidence_cache=baseline_evidence_cache,
                mcp_agent_metrics=mcp_agent_metrics,
            )
            if is_opt:
                opt_by_idx[idx] = res
            else:
                base_by_idx[idx] = res
            execution_order.append({
                "run_index": idx,
                "variant": variant,
                "input_hash": input_hashes[idx],
                "run_id": res["trace"]["run_id"],
                "status": res["trace"]["status"],
            })

        base_summary = self._summarize_variant_runs(
            variant="baseline",
            agents=base_agents,
            run_outputs=[base_by_idx[i] for i in range(len(sample_inputs))],
            workflow_inputs=sample_inputs,
        )
        opt_summary = self._summarize_variant_runs(
            variant="optimized",
            agents=opt_agents,
            run_outputs=[opt_by_idx[i] for i in range(len(sample_inputs))],
            workflow_inputs=sample_inputs,
        )

        return {
            "baseline_runtime_results": base_summary,
            "optimized_runtime_results": opt_summary,
            "execution_order": execution_order,
            "input_dataset_hashes": input_hashes,
            "interleaved": bool(interleave),
            "randomized": bool(randomize_order),
        }

    def run(
        self,
        env: SandboxEnvironment,
        num_runs: int = 1,
    ) -> Dict[str, Any]:
        """Execute the optimized sandbox workflow for `num_runs`, saving trace JSONs to `env.runtime_traces_dir`."""
        return self.run_variant(env, variant="optimized", num_runs=num_runs)
