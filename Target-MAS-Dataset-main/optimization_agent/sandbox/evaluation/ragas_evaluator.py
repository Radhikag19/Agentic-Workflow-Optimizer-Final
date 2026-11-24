"""
RAGAS Quality Evaluation & Acceptance Gate Integration.

Evaluates fresh optimized workflow outputs against actual supplied agent contexts and
corresponding historical baseline outputs (as `reference`) using:
  - Faithfulness (response supported by retrieved/supplied contexts)
  - Context Precision (relevant context ranked/present for reference)
  - Context Recall (context supports reference answer)

Never invents arbitrary thresholds, never fabricates missing contexts/scores, never
substitutes historical outputs for `retrieved_contexts`, and always tracks evaluation LLM
usage separately from target MAS workflow token/cost metrics.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import math
import re
import statistics
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from optimization_agent.key_manager import FAILOVER_KEYS, GroqKeyManager, get_default_key_manager
from optimization_agent.model_selection.groq_catalog import MODEL_CATALOG

RAGAS_METRICS_ORDER: Tuple[str, ...] = (
    "faithfulness",
    "context_precision",
    "context_recall",
)


@dataclass
class QualityAcceptanceCriteria:
    """User-configurable quality non-inferiority & selection constraints."""

    min_faithfulness: Optional[float] = None
    min_context_precision: Optional[float] = None
    min_context_recall: Optional[float] = None
    max_regression_vs_foundation: Optional[float] = None
    require_all_metrics_available: bool = True

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "QualityAcceptanceCriteria":
        if not isinstance(data, dict):
            return cls()
        return cls(
            min_faithfulness=float(data["min_faithfulness"]) if data.get("min_faithfulness") is not None else None,
            min_context_precision=(
                float(data["min_context_precision"]) if data.get("min_context_precision") is not None else None
            ),
            min_context_recall=(
                float(data["min_context_recall"]) if data.get("min_context_recall") is not None else None
            ),
            max_regression_vs_foundation=(
                float(data["max_regression_vs_foundation"])
                if data.get("max_regression_vs_foundation") is not None
                else None
            ),
            require_all_metrics_available=bool(data.get("require_all_metrics_available", True)),
        )

    def has_configured_thresholds(self) -> bool:
        return any(
            v is not None
            for v in (
                self.min_faithfulness,
                self.min_context_precision,
                self.min_context_recall,
                self.max_regression_vs_foundation,
            )
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def check_ragas_environment() -> Dict[str, Any]:
    """Inspect installed RAGAS / LangChain / Groq packages cleanly without throwing."""
    packages = ("ragas", "langchain-core", "langchain-groq", "groq", "datasets", "sentence-transformers")
    versions: Dict[str, Optional[str]] = {}
    for pkg in packages:
        try:
            versions[pkg] = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            versions[pkg] = None

    has_ragas = importlib.util.find_spec("ragas") is not None
    missing: List[str] = []
    if not has_ragas:
        missing.append(
            "Python package 'ragas' is not installed in the active environment "
            "(install locally with: pip install ragas)."
        )
    if versions.get("langchain-core") is None:
        missing.append("Python package 'langchain-core' is not installed.")
    if versions.get("groq") is None:
        missing.append("Python package 'groq' is not installed.")

    return {
        "ragas_installed": has_ragas,
        "versions": versions,
        "missing_integration_requirements": missing,
    }


def _estimate_eval_cost(model_id: str, prompt_tokens: int, completion_tokens: int) -> float:
    meta = MODEL_CATALOG.get(model_id) or MODEL_CATALOG["openai/gpt-oss-120b"]
    return round(
        (prompt_tokens / 1_000_000.0) * float(meta["input_price_per_million_usd"])
        + (completion_tokens / 1_000_000.0) * float(meta["output_price_per_million_usd"]),
        6,
    )


def _new_eval_usage_tracker(model_id: str, evaluator_backend: str) -> Dict[str, Any]:
    return {
        "evaluator_backend": evaluator_backend,
        "model": model_id,
        "api_calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "estimated_cost_usd": 0.0,
        "isolated_from_workflow_metrics": True,
    }


def _strip_reasoning_and_fences(raw_text: str) -> str:
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", str(raw_text or "")).strip()
    fence_match = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", cleaned, re.IGNORECASE)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    return cleaned


def _build_groq_langchain_chat_model(model_id: str, key_mgr: GroqKeyManager, usage_tracker: Dict[str, Any]) -> Any:
    """Create a minimal LangChain BaseChatModel backed by `groq.Groq` that isolates evaluator token usage."""
    from groq import Groq
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    primary_raw, _, _ = key_mgr.get_key_for_task("tradeoff_assessment")
    key_pool: List[str] = [primary_raw]
    for fk in list(FAILOVER_KEYS) + sorted((key_mgr._keys or {}).keys()):
        cand = str((key_mgr._keys or {}).get(fk) or "").strip()
        if cand and cand not in key_pool:
            key_pool.append(cand)
    rr_lock = threading.Lock()
    rr_idx = [0]

    def _next_key(offset: int = 0) -> str:
        with rr_lock:
            idx = (rr_idx[0] + offset) % len(key_pool)
            if offset == 0:
                rr_idx[0] += 1
            return key_pool[idx]

    class _TrackedGroqEvalChat(BaseChatModel):
        @property
        def _llm_type(self) -> str:
            return "awo_tracked_groq_ragas_evaluator"

        def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
            formatted = []
            for m in messages:
                role = "user"
                m_type = getattr(m, "type", "human")
                if m_type == "system":
                    role = "system"
                elif m_type == "ai":
                    role = "assistant"
                formatted.append({"role": role, "content": str(getattr(m, "content", m))})

            base_key = _next_key(0)
            last_exc: Optional[Exception] = None
            resp = None
            max_tries = min(6, max(4, len(key_pool)))
            for attempt in range(max_tries):
                active_key = base_key if attempt == 0 else _next_key(attempt)
                try:
                    client = Groq(api_key=active_key, timeout=60.0)
                    resp = client.chat.completions.create(
                        model=model_id,
                        messages=formatted,
                        temperature=0.0,
                        max_tokens=4096,
                        **({"stop": stop} if stop else {}),
                    )
                    break
                except Exception as exc:
                    last_exc = exc
                    err_low = str(exc).lower()
                    if ("429" in err_low or "rate" in err_low or "timeout" in err_low) and attempt < max_tries - 1:
                        time.sleep(min(6.0, 1.0 * (attempt + 1)))
                        continue
                    raise
            if resp is None and last_exc is not None:
                raise last_exc
            content = _strip_reasoning_and_fences(resp.choices[0].message.content or "")
            usage = getattr(resp, "usage", None)
            with rr_lock:
                if usage is not None:
                    pt = int(getattr(usage, "prompt_tokens", 0) or 0)
                    ct = int(getattr(usage, "completion_tokens", 0) or 0)
                    tt = int(getattr(usage, "total_tokens", pt + ct) or (pt + ct))
                    usage_tracker["api_calls"] += 1
                    usage_tracker["prompt_tokens"] += pt
                    usage_tracker["completion_tokens"] += ct
                    usage_tracker["total_tokens"] += tt
                    usage_tracker["estimated_cost_usd"] = round(
                        usage_tracker["estimated_cost_usd"] + _estimate_eval_cost(model_id, pt, ct),
                        6,
                    )
                else:
                    usage_tracker["api_calls"] += 1
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])

    return _TrackedGroqEvalChat()


def _serialize_payload_text(val: Any) -> Optional[str]:
    if val is None or val == "" or val == {} or val == []:
        return None
    if isinstance(val, str):
        return val.strip() or None
    return json.dumps(val, sort_keys=True, default=str)


def _match_baseline_trace(
    opt_trace: Dict[str, Any],
    base_by_hash: Dict[str, Dict[str, Any]],
    base_by_run_id: Dict[str, Dict[str, Any]],
    base_list: List[Dict[str, Any]],
    fallback_idx: int,
) -> Optional[Dict[str, Any]]:
    in_hash = opt_trace.get("input_hash")
    if in_hash and in_hash in base_by_hash:
        return base_by_hash[in_hash]
    snap = opt_trace.get("input_snapshot") or {}
    matched_rid = snap.get("matched_baseline_run_id") or opt_trace.get("matched_baseline_run_id")
    if matched_rid and matched_rid in base_by_run_id:
        return base_by_run_id[matched_rid]
    if base_list and len(base_list) == 1 and not in_hash:
        return base_list[0]
    if base_list and 0 <= fallback_idx < len(base_list) and not in_hash:
        return base_list[fallback_idx]
    return None


def _extract_agent_contexts(
    opt_trace: Dict[str, Any],
    agent_exec: Dict[str, Any],
) -> List[str]:
    """
    Extract genuinely supplied contexts for `agent_exec` without EVER substituting
    historical baseline outputs as retrieved contexts.
    """
    raw_ctx = agent_exec.get("supplied_contexts")
    if isinstance(raw_ctx, list):
        return [str(c) for c in raw_ctx if isinstance(c, (str, dict)) and str(c).strip()]

    # Reconstruct ONLY from real trace handoff_audits / input_snapshot if non-trivial
    contexts: List[str] = []
    aid = agent_exec.get("agent_id")
    for audit in (opt_trace.get("handoff_audits") or []):
        if not isinstance(audit, dict):
            continue
        edge = str(audit.get("edge") or "")
        if edge.endswith(f"->{aid}"):
            payload = audit.get("projected_payload") or audit.get("original_payload")
            if payload not in (None, "", {}, []):
                contexts.append(f"[handoff.{edge}] {json.dumps(payload, default=str)}")
    return contexts


def build_ragas_samples(
    baseline_runtime_results: Optional[Dict[str, Any]],
    optimized_runtime_results: Optional[Dict[str, Any]],
    *,
    target_agents: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """
    Construct canonical RAGAS sample records (`user_input`, `response`, `reference`, `retrieved_contexts`)
    matched cleanly between fresh optimized traces and corresponding historical baseline traces.
    """
    base_traces = list((baseline_runtime_results or {}).get("traces") or [])
    opt_traces = list((optimized_runtime_results or {}).get("traces") or [])

    base_by_hash = {str(t["input_hash"]): t for t in base_traces if isinstance(t, dict) and t.get("input_hash")}
    base_by_run_id = {str(t["run_id"]): t for t in base_traces if isinstance(t, dict) and t.get("run_id")}
    target_set = set(target_agents) if target_agents else None

    samples: List[Dict[str, Any]] = []
    missing_context_samples: List[Dict[str, Any]] = []
    missing_reference_samples: List[Dict[str, Any]] = []
    unmatched_traces: List[str] = []

    for idx, opt_trace in enumerate(opt_traces):
        if not isinstance(opt_trace, dict):
            continue
        base_trace = _match_baseline_trace(opt_trace, base_by_hash, base_by_run_id, base_traces, idx)
        if base_traces and base_trace is None:
            unmatched_traces.append(str(opt_trace.get("run_id") or f"run_{idx}"))

        base_execs = {
            str(e.get("agent_id")): e
            for e in ((base_trace or {}).get("agent_executions") or [])
            if isinstance(e, dict) and e.get("agent_id")
        }
        opt_execs = [
            e for e in (opt_trace.get("agent_executions") or [])
            if isinstance(e, dict) and e.get("agent_id")
        ]
        if not opt_execs:
            continue

        snap = opt_trace.get("input_snapshot") or {}
        terminal_aid = opt_execs[-1].get("agent_id")

        for ag_ex in opt_execs:
            aid = str(ag_ex.get("agent_id"))
            consolidated_from = ag_ex.get("consolidated_from") or []
            if target_set is not None:
                if aid not in target_set and not (set(consolidated_from) & target_set):
                    if aid != terminal_aid:
                        continue

            response_txt = _serialize_payload_text(ag_ex.get("output"))
            # Match baseline output for reference answer (handle consolidated agent groups cleanly)
            if aid in base_execs:
                reference_txt = _serialize_payload_text(base_execs[aid].get("output"))
            elif consolidated_from:
                cons_parts = {
                    orig_id: (base_execs[orig_id].get("output"))
                    for orig_id in consolidated_from
                    if orig_id in base_execs and base_execs[orig_id].get("output") is not None
                }
                reference_txt = (
                    _serialize_payload_text(cons_parts.get(consolidated_from[-1]))
                    if len(cons_parts) == 1 and consolidated_from[-1] in cons_parts
                    else _serialize_payload_text(cons_parts)
                )
            elif base_trace is not None and aid == terminal_aid and base_trace.get("final_output") is not None:
                reference_txt = _serialize_payload_text(base_trace.get("final_output"))
            else:
                reference_txt = None

            retrieved_contexts = _extract_agent_contexts(opt_trace, ag_ex)
            task_input = str(
                ag_ex.get("agent_task_input")
                or f"Execute {aid} on input {json.dumps(snap, default=str)}"
            )
            level = "workflow" if aid == terminal_aid else "agent"

            has_contexts = len(retrieved_contexts) > 0
            has_reference = bool(reference_txt)
            has_response = bool(response_txt)

            sample = {
                "sample_id": f"{opt_trace.get('run_id', f'run_{idx}')}:{aid}",
                "run_id": opt_trace.get("run_id"),
                "agent_id": aid,
                "evaluation_level": level,
                "user_input": task_input,
                "response": response_txt,
                "reference": reference_txt,
                "retrieved_contexts": retrieved_contexts,
                "has_contexts": has_contexts,
                "has_reference": has_reference,
                "has_response": has_response,
            }
            samples.append(sample)

            if not has_contexts:
                missing_context_samples.append({"sample_id": sample["sample_id"], "agent_id": aid})
            if not has_reference:
                missing_reference_samples.append({"sample_id": sample["sample_id"], "agent_id": aid})

    return {
        "samples": samples,
        "total_samples": len(samples),
        "missing_context_samples": missing_context_samples,
        "missing_reference_samples": missing_reference_samples,
        "unmatched_traces": unmatched_traces,
    }


def _clean_score(val: Any) -> Any:
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        return "unavailable"
    fval = float(val)
    if math.isnan(fval) or math.isinf(fval):
        return "unavailable"
    return round(fval, 4)


def _aggregate_metric_scores(per_sample_scores: List[Dict[str, Any]], metric: str) -> Any:
    vals = []
    for s in per_sample_scores:
        cleaned = _clean_score(s.get(metric))
        if isinstance(cleaned, (int, float)):
            vals.append(float(cleaned))
    if not vals:
        return "unavailable"
    return round(statistics.mean(vals), 4)


def _run_installed_ragas(
    eligible_samples: List[Dict[str, Any]],
    *,
    llm_model: str,
    key_mgr: GroqKeyManager,
    usage_tracker: Dict[str, Any],
    embeddings: Any = None,
) -> Dict[str, Any]:
    """Execute real installed RAGAS package against `EvaluationDataset` & Groq evaluator LLM."""
    from ragas import EvaluationDataset, SingleTurnSample, evaluate
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness, LLMContextPrecisionWithReference, LLMContextRecall
    from ragas.run_config import RunConfig

    chat_model = _build_groq_langchain_chat_model(llm_model, key_mgr, usage_tracker)
    ragas_llm = LangchainLLMWrapper(chat_model)

    dataset_items = [
        SingleTurnSample(
            user_input=s["user_input"],
            response=s["response"],
            reference=s["reference"] or "",
            retrieved_contexts=s["retrieved_contexts"],
        )
        for s in eligible_samples
    ]
    dataset = EvaluationDataset(samples=dataset_items)
    metrics = [
        Faithfulness(llm=ragas_llm),
        LLMContextPrecisionWithReference(llm=ragas_llm),
        LLMContextRecall(llm=ragas_llm),
    ]
    eval_kwargs: Dict[str, Any] = {
        "dataset": dataset,
        "metrics": metrics,
        "llm": ragas_llm,
        "show_progress": False,
        "run_config": RunConfig(timeout=90, max_retries=2, max_wait=15, max_workers=2),
    }
    if embeddings is not None:
        eval_kwargs["embeddings"] = embeddings

    result = evaluate(**eval_kwargs)
    df = result.to_pandas() if hasattr(result, "to_pandas") else None
    per_sample: List[Dict[str, Any]] = []
    if df is not None:
        for i, row in df.iterrows():
            base_s = eligible_samples[i] if i < len(eligible_samples) else {}
            per_sample.append({
                "sample_id": base_s.get("sample_id"),
                "agent_id": base_s.get("agent_id"),
                "evaluation_level": base_s.get("evaluation_level"),
                "faithfulness": _clean_score(row.get("faithfulness") if "faithfulness" in row else None),
                "context_precision": _clean_score(
                    row.get("llm_context_precision_with_reference")
                    if "llm_context_precision_with_reference" in row
                    else row.get("context_precision")
                ),
                "context_recall": _clean_score(row.get("context_recall") if "context_recall" in row else None),
            })
    return {
        "per_sample_scores": per_sample,
        "evaluation_model_usage": usage_tracker,
    }


def evaluate_with_ragas(
    baseline_runtime_results: Optional[Dict[str, Any]],
    optimized_runtime_results: Optional[Dict[str, Any]],
    *,
    target_agents: Optional[Sequence[str]] = None,
    ragas_runner: Optional[Callable[..., Dict[str, Any]]] = None,
    llm_model: str = "qwen/qwen3.8-27b",
    embeddings: Any = None,
    key_mgr: Optional[GroqKeyManager] = None,
) -> Dict[str, Any]:
    """
    Evaluate optimized agent/workflow outputs using RAGAS (`faithfulness`, `context_precision`,
    `context_recall`). Marks metrics as `unavailable` whenever contexts, references, or the
    `ragas` package are unavailable — never fabricating scores.
    """
    mgr = key_mgr or get_default_key_manager()
    sample_bundle = build_ragas_samples(
        baseline_runtime_results,
        optimized_runtime_results,
        target_agents=target_agents,
    )
    samples = sample_bundle["samples"]
    env_info = check_ragas_environment()
    usage_tracker = _new_eval_usage_tracker(
        llm_model,
        evaluator_backend="custom_ragas_runner" if ragas_runner is not None else "ragas_sdk",
    )

    if not samples:
        return {
            "status": "unavailable",
            "ragas_available": ragas_runner is not None or env_info["ragas_installed"],
            "faithfulness": "unavailable",
            "context_precision": "unavailable",
            "context_recall": "unavailable",
            "agent_level_scores": {},
            "workflow_level_scores": {},
            "samples": [],
            "per_sample_scores": [],
            "missing_context_samples": [],
            "missing_reference_samples": [],
            "unmatched_traces": sample_bundle["unmatched_traces"],
            "missing_integration_requirements": ["No executed optimized agent outputs available for RAGAS evaluation."],
            "evaluation_model_usage": usage_tracker,
            "environment": env_info,
        }

    # Filter samples strictly to those with actual contexts and responses (no fabricated contexts!)
    eligible_for_faithfulness = [s for s in samples if s["has_contexts"] and s["has_response"]]
    eligible_for_ref_metrics = [s for s in eligible_for_faithfulness if s["has_reference"]]

    if not eligible_for_faithfulness:
        return {
            "status": "unavailable",
            "ragas_available": ragas_runner is not None or env_info["ragas_installed"],
            "faithfulness": "unavailable",
            "context_precision": "unavailable",
            "context_recall": "unavailable",
            "agent_level_scores": {},
            "workflow_level_scores": {},
            "samples": samples,
            "per_sample_scores": [],
            "missing_context_samples": sample_bundle["missing_context_samples"],
            "missing_reference_samples": sample_bundle["missing_reference_samples"],
            "unmatched_traces": sample_bundle["unmatched_traces"],
            "missing_integration_requirements": [
                "No supplied retrieved_contexts available for optimized agent outputs; cannot evaluate RAGAS metrics."
            ],
            "evaluation_model_usage": usage_tracker,
            "environment": env_info,
        }

    per_sample_scores: List[Dict[str, Any]] = []
    missing_reqs: List[str] = list(env_info["missing_integration_requirements"]) if ragas_runner is None else []

    if ragas_runner is not None:
        raw_out = ragas_runner(eligible_for_faithfulness, list(RAGAS_METRICS_ORDER))
        raw_scores = list(raw_out.get("per_sample_scores") or [])
        by_id = {str(item.get("sample_id")): item for item in raw_scores if isinstance(item, dict) and item.get("sample_id")}

        for s in samples:
            sid = s["sample_id"]
            if not s["has_contexts"] or not s["has_response"]:
                per_sample_scores.append({
                    "sample_id": sid,
                    "agent_id": s["agent_id"],
                    "evaluation_level": s["evaluation_level"],
                    "faithfulness": "unavailable",
                    "context_precision": "unavailable",
                    "context_recall": "unavailable",
                    "reason": "missing_retrieved_contexts" if not s["has_contexts"] else "missing_response",
                })
                continue

            matched = by_id.get(sid)
            if matched is None and len(raw_scores) == len(eligible_for_faithfulness):
                idx = eligible_for_faithfulness.index(s)
                matched = raw_scores[idx]
            matched = matched or {}

            f_val = matched.get("faithfulness", "unavailable")
            cp_val = matched.get("context_precision", "unavailable") if s["has_reference"] else "unavailable"
            cr_val = matched.get("context_recall", "unavailable") if s["has_reference"] else "unavailable"
            per_sample_scores.append({
                "sample_id": sid,
                "agent_id": s["agent_id"],
                "evaluation_level": s["evaluation_level"],
                "faithfulness": f_val,
                "context_precision": cp_val,
                "context_recall": cr_val,
                "reason": None if s["has_reference"] else "missing_reference_for_context_metrics",
            })

        runner_usage = raw_out.get("evaluation_model_usage") or {}
        for k in ("api_calls", "prompt_tokens", "completion_tokens", "total_tokens", "estimated_cost_usd"):
            if runner_usage.get(k) is not None:
                usage_tracker[k] = runner_usage[k]
        if runner_usage.get("model"):
            usage_tracker["model"] = runner_usage["model"]
    else:
        if not env_info["ragas_installed"]:
            return {
                "status": "unavailable",
                "ragas_available": False,
                "faithfulness": "unavailable",
                "context_precision": "unavailable",
                "context_recall": "unavailable",
                "agent_level_scores": {},
                "workflow_level_scores": {},
                "samples": samples,
                "per_sample_scores": [],
                "missing_context_samples": sample_bundle["missing_context_samples"],
                "missing_reference_samples": sample_bundle["missing_reference_samples"],
                "unmatched_traces": sample_bundle["unmatched_traces"],
                "missing_integration_requirements": missing_reqs,
                "evaluation_model_usage": usage_tracker,
                "environment": env_info,
            }
        try:
            sdk_out = _run_installed_ragas(
                eligible_for_ref_metrics or eligible_for_faithfulness,
                llm_model=llm_model,
                key_mgr=mgr,
                usage_tracker=usage_tracker,
                embeddings=embeddings,
            )
            per_sample_scores = sdk_out["per_sample_scores"]
        except Exception as exc:
            sanitized = mgr.sanitize_text(str(exc))
            return {
                "status": "unavailable",
                "ragas_available": True,
                "faithfulness": "unavailable",
                "context_precision": "unavailable",
                "context_recall": "unavailable",
                "agent_level_scores": {},
                "workflow_level_scores": {},
                "samples": samples,
                "per_sample_scores": [],
                "missing_context_samples": sample_bundle["missing_context_samples"],
                "missing_reference_samples": sample_bundle["missing_reference_samples"],
                "unmatched_traces": sample_bundle["unmatched_traces"],
                "missing_integration_requirements": [f"RAGAS execution failed: {sanitized}"],
                "evaluation_model_usage": usage_tracker,
                "environment": env_info,
            }

    overall_scores = {m: _aggregate_metric_scores(per_sample_scores, m) for m in RAGAS_METRICS_ORDER}
    by_agent: Dict[str, List[Dict[str, Any]]] = {}
    for ps in per_sample_scores:
        by_agent.setdefault(str(ps.get("agent_id")), []).append(ps)

    agent_level_scores = {
        aid: {m: _aggregate_metric_scores(items, m) for m in RAGAS_METRICS_ORDER}
        for aid, items in by_agent.items()
    }
    wf_items = [ps for ps in per_sample_scores if ps.get("evaluation_level") == "workflow"]
    workflow_level_scores = (
        {m: _aggregate_metric_scores(wf_items, m) for m in RAGAS_METRICS_ORDER} if wf_items else dict(overall_scores)
    )
    all_avail = all(isinstance(overall_scores[m], (int, float)) for m in RAGAS_METRICS_ORDER)
    any_avail = any(isinstance(overall_scores[m], (int, float)) for m in RAGAS_METRICS_ORDER)
    status = "completed" if all_avail else ("partial" if any_avail else "unavailable")

    return {
        "status": status,
        "ragas_available": True,
        "faithfulness": overall_scores["faithfulness"],
        "context_precision": overall_scores["context_precision"],
        "context_recall": overall_scores["context_recall"],
        "agent_level_scores": agent_level_scores,
        "workflow_level_scores": workflow_level_scores,
        "samples": samples,
        "per_sample_scores": per_sample_scores,
        "missing_context_samples": sample_bundle["missing_context_samples"],
        "missing_reference_samples": sample_bundle["missing_reference_samples"],
        "unmatched_traces": sample_bundle["unmatched_traces"],
        "missing_integration_requirements": missing_reqs,
        "evaluation_model_usage": usage_tracker,
        "environment": env_info,
    }


def evaluate_quality_acceptance(
    ragas_result: Optional[Dict[str, Any]],
    criteria: Optional[QualityAcceptanceCriteria],
    *,
    execution_passed: bool,
    validation_passed: bool,
    schema_valid: bool,
    foundation_ragas_scores: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Evaluate RAGAS quality non-inferiority & selection constraints strictly without inventing thresholds.
    Returns `status`: 'accepted' | 'rejected' | 'inconclusive'.
    """
    reasons: List[str] = []
    threshold_checks: Dict[str, Any] = {}
    regression_checks: Dict[str, Any] = {}

    if not validation_passed or not execution_passed or not schema_valid:
        if not validation_passed:
            reasons.append("Sandbox validation failed.")
        if not execution_passed:
            reasons.append("Optimized runtime execution failed.")
        if not schema_valid:
            reasons.append("Optimized agent output schemas failed validation.")
        return {
            "quality_accepted": False,
            "status": "rejected",
            "reasons": reasons,
            "threshold_checks": threshold_checks,
            "regression_checks": regression_checks,
        }

    if not isinstance(ragas_result, dict):
        return {
            "quality_accepted": False,
            "status": "inconclusive",
            "reasons": ["RAGAS quality evaluation results are unavailable."],
            "threshold_checks": threshold_checks,
            "regression_checks": regression_checks,
        }

    eff_criteria = criteria if isinstance(criteria, QualityAcceptanceCriteria) else QualityAcceptanceCriteria()
    missing_metrics = [
        m for m in RAGAS_METRICS_ORDER if not isinstance(ragas_result.get(m), (int, float))
    ]
    if missing_metrics and eff_criteria.require_all_metrics_available:
        reasons.append(f"RAGAS metrics unavailable: {missing_metrics}.")
        return {
            "quality_accepted": False,
            "status": "inconclusive",
            "reasons": reasons,
            "threshold_checks": threshold_checks,
            "regression_checks": regression_checks,
        }

    if not eff_criteria.has_configured_thresholds():
        reasons.append(
            "No quality acceptance thresholds configured (min_faithfulness / min_context_precision / "
            "min_context_recall / max_regression_vs_foundation); refusing to invent thresholds."
        )
        return {
            "quality_accepted": False,
            "status": "inconclusive",
            "reasons": reasons,
            "threshold_checks": threshold_checks,
            "regression_checks": regression_checks,
        }

    failed_checks: List[str] = []
    min_map = {
        "faithfulness": eff_criteria.min_faithfulness,
        "context_precision": eff_criteria.min_context_precision,
        "context_recall": eff_criteria.min_context_recall,
    }
    for metric, min_val in min_map.items():
        if min_val is None:
            continue
        actual = ragas_result.get(metric)
        if not isinstance(actual, (int, float)):
            threshold_checks[metric] = {"required_min": min_val, "actual": actual, "passed": False}
            failed_checks.append(f"{metric} unavailable (required >= {min_val})")
        else:
            ok = float(actual) >= float(min_val)
            threshold_checks[metric] = {"required_min": min_val, "actual": float(actual), "passed": ok}
            if not ok:
                failed_checks.append(f"{metric}={actual:.4f} < configured minimum {min_val:.4f}")

    if eff_criteria.max_regression_vs_foundation is not None and isinstance(foundation_ragas_scores, dict):
        max_drop = float(eff_criteria.max_regression_vs_foundation)
        for metric in RAGAS_METRICS_ORDER:
            base_v = foundation_ragas_scores.get(metric)
            cur_v = ragas_result.get(metric)
            if isinstance(base_v, (int, float)) and isinstance(cur_v, (int, float)):
                drop = round(float(base_v) - float(cur_v), 4)
                ok = drop <= max_drop
                regression_checks[metric] = {
                    "foundation_score": float(base_v),
                    "current_score": float(cur_v),
                    "drop": drop,
                    "max_permitted_regression": max_drop,
                    "passed": ok,
                }
                if not ok:
                    failed_checks.append(
                        f"{metric} regressed by {drop:.4f} vs foundation (max permitted {max_drop:.4f})"
                    )

    if failed_checks:
        return {
            "quality_accepted": False,
            "status": "rejected",
            "reasons": failed_checks,
            "threshold_checks": threshold_checks,
            "regression_checks": regression_checks,
        }

    return {
        "quality_accepted": True,
        "status": "accepted",
        "reasons": ["All configured RAGAS quality thresholds and non-inferiority criteria passed."],
        "threshold_checks": threshold_checks,
        "regression_checks": regression_checks,
    }
