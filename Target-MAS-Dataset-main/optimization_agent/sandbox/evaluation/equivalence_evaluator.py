"""
3-Layer Behavioral Equivalence Evaluation & Acceptance Gate:
Directly compares Before (historical baseline output) vs. After (fresh optimized output)
without RAG retrieval bias:
  - Layer 1: Deterministic Structural & Decision Match (Key F1, Booleans/Enums, Numeric Tolerance)
  - Layer 2: Semantic Cosine Similarity on Narrative Prose (SentenceTransformer or TF-IDF fallback)
  - Layer 3: Optional 1-Call Pairwise LLM-as-a-Judge (isolated token/cost accounting)
"""

from __future__ import annotations

import importlib.util
import json
import math
import statistics
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from optimization_agent.key_manager import GroqKeyManager, get_default_key_manager
from optimization_agent.sandbox.evaluation.ragas_evaluator import (
    _estimate_eval_cost,
    _match_baseline_trace,
    _new_eval_usage_tracker,
    _strip_reasoning_and_fences,
)

EQUIVALENCE_METRICS_ORDER: Tuple[str, ...] = (
    "structural_decision_score",
    "semantic_cosine_similarity",
    "llm_judge_equivalence",
)

_DECISION_KEY_HINTS: Tuple[str, ...] = (
    "status",
    "approved",
    "passed",
    "required",
    "risk",
    "severity",
    "priority",
    "decision",
    "tier",
    "valid",
    "eligible",
    "recommendation",
    "verdict",
    "action",
)

_EMBED_MODEL_CACHE: Dict[str, Any] = {}


@dataclass
class EquivalenceAcceptanceCriteria:
    """User-configurable 3-layer behavioral equivalence acceptance thresholds."""

    min_structural_decision_score: Optional[float] = 0.75
    min_semantic_cosine: Optional[float] = 0.75
    min_llm_judge_score: Optional[float] = 0.75
    max_decision_flips: Optional[int] = 0
    max_regression_vs_foundation: Optional[float] = 0.10

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "EquivalenceAcceptanceCriteria":
        if not isinstance(data, dict):
            return cls()
        return cls(
            min_structural_decision_score=(
                float(data["min_structural_decision_score"])
                if data.get("min_structural_decision_score") is not None
                else 0.75
            ),
            min_semantic_cosine=(
                float(data["min_semantic_cosine"])
                if data.get("min_semantic_cosine") is not None
                else 0.75
            ),
            min_llm_judge_score=(
                float(data["min_llm_judge_score"])
                if data.get("min_llm_judge_score") is not None
                else 0.75
            ),
            max_decision_flips=(
                int(data["max_decision_flips"])
                if data.get("max_decision_flips") is not None
                else 0
            ),
            max_regression_vs_foundation=(
                float(data["max_regression_vs_foundation"])
                if data.get("max_regression_vs_foundation") is not None
                else 0.10
            ),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_IGNORED_METADATA_KEYS = frozenset({
    "run_id",
    "experiment_id",
    "suite_id",
    "study_id",
    "trace_id",
    "timestamp",
    "generated_at",
})


def _flatten_json(obj: Any, prefix: str = "") -> Dict[str, Any]:
    """Recursively flatten JSON objects/arrays into dotted leaf `(path, value)` pairs."""
    out: Dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k) in _IGNORED_METADATA_KEYS:
                continue
            key_path = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, (dict, list)) and v:
                out.update(_flatten_json(v, key_path))
            else:
                out[key_path] = v
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            item_path = f"{prefix}[{idx}]"
            if isinstance(item, (dict, list)) and item:
                out.update(_flatten_json(item, item_path))
            else:
                out[item_path] = item
    else:
        out[prefix or "$"] = obj
    return out


def _is_decision_leaf(path: str, val: Any) -> bool:
    if isinstance(val, bool):
        return True
    if not isinstance(val, str):
        return False
    cleaned = val.strip()
    if not cleaned or len(cleaned) > 32:
        return False
    leaf_name = path.split(".")[-1].split("[")[0].lower()
    if any(h in leaf_name for h in _DECISION_KEY_HINTS):
        return True
    return " " not in cleaned and ("_" in cleaned or cleaned.isupper())


def _is_numeric_leaf(val: Any) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(float(val))


def compute_structural_decision_equivalence(
    baseline_output: Any,
    optimized_output: Any,
    *,
    numeric_tolerance: float = 0.05,
) -> Dict[str, Any]:
    """
    Layer 1 (Deterministic): Compare key overlap, boolean/enum decisions, and numeric values
    between Baseline and Optimized JSON outputs.
    """
    if isinstance(baseline_output, str):
        try:
            baseline_output = json.loads(baseline_output)
        except Exception:
            pass
    if isinstance(optimized_output, str):
        try:
            optimized_output = json.loads(optimized_output)
        except Exception:
            pass

    if not isinstance(baseline_output, (dict, list)) or not isinstance(optimized_output, (dict, list)):
        b_s = str(baseline_output or "").strip()
        o_s = str(optimized_output or "").strip()
        exact = 1.0 if (b_s and b_s == o_s) else 0.0
        return {
            "key_f1": exact,
            "decision_match_rate": exact if (b_s or o_s) else None,
            "numeric_match_rate": None,
            "decision_flip_count": 0,
            "decision_mismatches": [],
            "layer1_score": exact,
        }

    flat_b = _flatten_json(baseline_output)
    flat_o = _flatten_json(optimized_output)
    keys_b = set(flat_b.keys())
    keys_o = set(flat_o.keys())
    shared = sorted(keys_b & keys_o)

    if not keys_b and not keys_o:
        key_f1 = 1.0
    elif not keys_b or not keys_o:
        key_f1 = 0.0
    else:
        key_f1 = round((2.0 * len(shared)) / (len(keys_b) + len(keys_o)), 4)

    decision_total = 0
    decision_matches = 0
    decision_mismatches: List[Dict[str, Any]] = []
    numeric_total = 0
    numeric_matches = 0

    for k in shared:
        vb = flat_b[k]
        vo = flat_o[k]
        if _is_decision_leaf(k, vb) or _is_decision_leaf(k, vo):
            decision_total += 1
            norm_b = vb if isinstance(vb, bool) else str(vb).strip().lower()
            norm_o = vo if isinstance(vo, bool) else str(vo).strip().lower()
            if norm_b == norm_o and type(vb) is type(vo):
                decision_matches += 1
            elif not isinstance(vb, bool) and not isinstance(vo, bool) and norm_b == norm_o:
                decision_matches += 1
            else:
                decision_mismatches.append({
                    "field": k,
                    "baseline_value": vb,
                    "optimized_value": vo,
                    "is_boolean_flip": isinstance(vb, bool) or isinstance(vo, bool),
                })
        elif _is_numeric_leaf(vb) and _is_numeric_leaf(vo):
            numeric_total += 1
            fb, fo = float(vb), float(vo)
            if abs(fb - fo) <= numeric_tolerance * max(1.0, abs(fb)):
                numeric_matches += 1

    decision_rate = round(decision_matches / decision_total, 4) if decision_total > 0 else None
    numeric_rate = round(numeric_matches / numeric_total, 4) if numeric_total > 0 else None

    weighted_parts: List[Tuple[float, float]] = [(0.4, key_f1)]
    if decision_rate is not None:
        weighted_parts.append((0.4, decision_rate))
    if numeric_rate is not None:
        weighted_parts.append((0.2, numeric_rate))

    w_sum = sum(w for w, _ in weighted_parts)
    layer1_score = round(sum(w * v for w, v in weighted_parts) / w_sum, 4) if w_sum > 0 else 0.0

    return {
        "key_f1": key_f1,
        "decision_match_rate": decision_rate,
        "numeric_match_rate": numeric_rate,
        "decision_flip_count": len(decision_mismatches),
        "decision_mismatches": decision_mismatches,
        "layer1_score": layer1_score,
    }


def _extract_narrative_text(obj: Any) -> str:
    """Extract clean prose/content text from structured JSON or plain text for embedding similarity."""
    if obj is None:
        return ""
    if isinstance(obj, str):
        try:
            parsed = json.loads(obj)
            if isinstance(parsed, (dict, list)):
                obj = parsed
            else:
                return obj.strip()
        except Exception:
            return obj.strip()

    chunks: List[str] = []
    if isinstance(obj, dict):
        for k, v in _flatten_json(obj).items():
            if v in (None, "", [], {}) or isinstance(v, bool):
                continue
            leaf = k.split(".")[-1].split("[")[0]
            if leaf in ("run_id", "timestamp", "experiment_id"):
                continue
            chunks.append(f"{leaf}: {v}")
    elif isinstance(obj, list):
        chunks.append(" ".join(str(x) for x in obj))
    else:
        chunks.append(str(obj))
    return " ".join(chunks).strip()


def _get_sentence_transformer_model() -> Optional[Any]:
    if "model" in _EMBED_MODEL_CACHE:
        return _EMBED_MODEL_CACHE["model"]
    if importlib.util.find_spec("sentence_transformers") is None:
        _EMBED_MODEL_CACHE["model"] = None
        return None
    try:
        from sentence_transformers import SentenceTransformer

        _EMBED_MODEL_CACHE["model"] = SentenceTransformer("all-MiniLM-L6-v2")
    except Exception:
        _EMBED_MODEL_CACHE["model"] = None
    return _EMBED_MODEL_CACHE["model"]


def compute_semantic_cosine_similarity(
    baseline_output: Any,
    optimized_output: Any,
) -> Dict[str, Any]:
    """
    Layer 2 (Offline Local Similarity): Compute cosine similarity between Baseline & Optimized
    narrative text using SentenceTransformer embeddings when installed, or dual word+char TF-IDF.
    """
    b_txt = _extract_narrative_text(baseline_output)
    o_txt = _extract_narrative_text(optimized_output)

    if not b_txt and not o_txt:
        return {"cosine_similarity": None, "backend": "none", "baseline_chars": 0, "optimized_chars": 0}
    if not b_txt or not o_txt:
        return {
            "cosine_similarity": 0.0,
            "backend": "empty_mismatch",
            "baseline_chars": len(b_txt),
            "optimized_chars": len(o_txt),
        }
    if b_txt == o_txt:
        return {
            "cosine_similarity": 1.0,
            "backend": "exact_match",
            "baseline_chars": len(b_txt),
            "optimized_chars": len(o_txt),
        }

    st_model = _get_sentence_transformer_model()
    if st_model is not None:
        embs = st_model.encode([b_txt, o_txt], normalize_embeddings=True)
        sim = float(np.clip(float(np.dot(embs[0], embs[1])), 0.0, 1.0))
        return {
            "cosine_similarity": round(sim, 4),
            "backend": "sentence_transformers:all-MiniLM-L6-v2",
            "baseline_chars": len(b_txt),
            "optimized_chars": len(o_txt),
        }

    try:
        word_vec = TfidfVectorizer(ngram_range=(1, 1), lowercase=True, min_df=1)
        w_mat = word_vec.fit_transform([b_txt, o_txt])
        word_sim = float(cosine_similarity(w_mat[0:1], w_mat[1:2])[0, 0])

        char_vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), lowercase=True, min_df=1)
        c_mat = char_vec.fit_transform([b_txt, o_txt])
        char_sim = float(cosine_similarity(c_mat[0:1], c_mat[1:2])[0, 0])

        blended = float(np.clip(0.55 * word_sim + 0.45 * char_sim, 0.0, 1.0))
    except Exception:
        blended = 0.0

    return {
        "cosine_similarity": round(blended, 4),
        "backend": "tfidf_word_char_cosine",
        "baseline_chars": len(b_txt),
        "optimized_chars": len(o_txt),
    }


def evaluate_pairwise_llm_judge(
    *,
    agent_id: str,
    baseline_output: Any,
    optimized_output: Any,
    judge_callable: Optional[Callable[..., Dict[str, Any]]] = None,
    key_mgr: Optional[GroqKeyManager] = None,
    model_id: str = "openai/gpt-oss-120b",
    usage_tracker: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Layer 3 (Optional 1-Call Pairwise LLM Judge): Directly compares Baseline vs. Optimized outputs
    for decision agreement, key fact retention, and lack of hallucinations.
    """
    b_str = json.dumps(baseline_output, default=str)[:4500]
    o_str = json.dumps(optimized_output, default=str)[:4500]

    if judge_callable is not None:
        raw = judge_callable(agent_id=agent_id, baseline_output=baseline_output, optimized_output=optimized_output)
        score = float(raw.get("overall_equivalence", raw.get("score", 0.0)))
        if usage_tracker is not None:
            usage_tracker["api_calls"] += int(raw.get("api_calls", 1))
            usage_tracker["total_tokens"] += int(raw.get("total_tokens", 0))
        return {
            "decision_agreement": raw.get("decision_agreement", score),
            "fact_retention": raw.get("fact_retention", score),
            "no_new_hallucinations": raw.get("no_new_hallucinations", score),
            "overall_equivalence": round(score, 4),
            "rationale": str(raw.get("rationale") or ""),
        }

    from groq import Groq

    mgr = key_mgr or get_default_key_manager()
    raw_key, _, _ = mgr.get_key_for_task("tradeoff_assessment")
    client = Groq(api_key=raw_key, timeout=45.0)
    prompt = (
        f"Compare BEFORE (baseline) vs AFTER (optimized) output for agent '{agent_id}'.\n"
        "Return ONLY JSON with floats in [0.0, 1.0]: "
        '{"decision_agreement": float, "fact_retention": float, "no_new_hallucinations": float, "overall_equivalence": float, "rationale": str}.\n\n'
        f"BASELINE OUTPUT:\n{b_str}\n\nOPTIMIZED OUTPUT:\n{o_str}"
    )
    resp = client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": "You evaluate behavioral equivalence between two multi-agent workflow outputs."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=512,
    )
    content = _strip_reasoning_and_fences(resp.choices[0].message.content or "{}")
    parsed = json.loads(content)
    usage = getattr(resp, "usage", None)
    if usage_tracker is not None:
        pt = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        ct = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
        usage_tracker["api_calls"] += 1
        usage_tracker["prompt_tokens"] += pt
        usage_tracker["completion_tokens"] += ct
        usage_tracker["total_tokens"] += pt + ct
        usage_tracker["estimated_cost_usd"] = round(
            usage_tracker["estimated_cost_usd"] + _estimate_eval_cost(model_id, pt, ct),
            6,
        )
    overall = float(parsed.get("overall_equivalence", 0.0))
    return {
        "decision_agreement": parsed.get("decision_agreement", overall),
        "fact_retention": parsed.get("fact_retention", overall),
        "no_new_hallucinations": parsed.get("no_new_hallucinations", overall),
        "overall_equivalence": round(max(0.0, min(1.0, overall)), 4),
        "rationale": str(parsed.get("rationale") or ""),
    }


def _resolve_baseline_agent_output(
    aid: str,
    consolidated_from: List[str],
    base_execs: Dict[str, Dict[str, Any]],
    base_trace: Optional[Dict[str, Any]],
    terminal_aid: Optional[str],
) -> Any:
    if aid in base_execs:
        return base_execs[aid].get("output")
    if consolidated_from:
        last_orig = consolidated_from[-1]
        if last_orig in base_execs and base_execs[last_orig].get("output") is not None:
            return base_execs[last_orig].get("output")
        parts = {
            orig_id: base_execs[orig_id].get("output")
            for orig_id in consolidated_from
            if orig_id in base_execs and base_execs[orig_id].get("output") is not None
        }
        return parts or None
    if base_trace is not None and aid == terminal_aid and base_trace.get("final_output") is not None:
        return base_trace.get("final_output")
    return None


def evaluate_behavioral_equivalence(
    *,
    baseline_runtime_results: Optional[Dict[str, Any]],
    optimized_runtime_results: Optional[Dict[str, Any]],
    target_agents: Optional[Sequence[str]] = None,
    enable_llm_judge: bool = False,
    judge_callable: Optional[Callable[..., Dict[str, Any]]] = None,
    numeric_tolerance: float = 0.05,
    key_mgr: Optional[GroqKeyManager] = None,
) -> Dict[str, Any]:
    """
    Evaluate Before-vs-After behavioral equivalence across all 3 layers:
      Layer 1 (Structural & Decision), Layer 2 (Semantic Cosine), Layer 3 (Optional LLM Judge).
    """
    base_traces = list((baseline_runtime_results or {}).get("traces") or [])
    opt_traces = list((optimized_runtime_results or {}).get("traces") or [])
    base_by_hash = {str(t["input_hash"]): t for t in base_traces if isinstance(t, dict) and t.get("input_hash")}
    base_by_run_id = {str(t["run_id"]): t for t in base_traces if isinstance(t, dict) and t.get("run_id")}
    target_set = set(target_agents) if target_agents else None

    backend_name = "pairwise_llm_judge" if (enable_llm_judge or judge_callable is not None) else "offline_deterministic_cosine"
    usage_tracker = _new_eval_usage_tracker("openai/gpt-oss-120b", backend_name)

    samples: List[Dict[str, Any]] = []
    per_sample_scores: List[Dict[str, Any]] = []
    by_agent: Dict[str, Dict[str, List[float]]] = {}

    l1_vals: List[float] = []
    l2_vals: List[float] = []
    l3_vals: List[float] = []
    total_flips = 0
    semantic_backend = "none"

    for idx, opt_trace in enumerate(opt_traces):
        if not isinstance(opt_trace, dict):
            continue
        base_trace = _match_baseline_trace(opt_trace, base_by_hash, base_by_run_id, base_traces, idx)
        if base_trace is None:
            continue

        base_execs = {
            str(e.get("agent_id")): e
            for e in (base_trace.get("agent_executions") or [])
            if isinstance(e, dict) and e.get("agent_id")
        }
        opt_execs = [
            e for e in (opt_trace.get("agent_executions") or [])
            if isinstance(e, dict) and e.get("agent_id")
        ]
        if not opt_execs:
            continue
        terminal_aid = str(opt_execs[-1].get("agent_id"))

        for ag_ex in opt_execs:
            aid = str(ag_ex.get("agent_id"))
            consolidated_from = [str(x) for x in (ag_ex.get("consolidated_from") or [])]
            if target_set is not None:
                if aid not in target_set and not (set(consolidated_from) & target_set):
                    if aid != terminal_aid:
                        continue

            opt_out = ag_ex.get("output")
            base_out = _resolve_baseline_agent_output(aid, consolidated_from, base_execs, base_trace, terminal_aid)
            if opt_out is None or base_out is None:
                continue

            l1 = compute_structural_decision_equivalence(base_out, opt_out, numeric_tolerance=numeric_tolerance)
            l2 = compute_semantic_cosine_similarity(base_out, opt_out)
            if l2["backend"] not in ("none", "empty_mismatch", "exact_match"):
                semantic_backend = l2["backend"]
            elif semantic_backend == "none":
                semantic_backend = l2["backend"]

            l3: Optional[Dict[str, Any]] = None
            if enable_llm_judge or judge_callable is not None:
                try:
                    l3 = evaluate_pairwise_llm_judge(
                        agent_id=aid,
                        baseline_output=base_out,
                        optimized_output=opt_out,
                        judge_callable=judge_callable,
                        key_mgr=key_mgr,
                        usage_tracker=usage_tracker,
                    )
                except Exception as exc:
                    l3 = {"overall_equivalence": None, "error": str(exc)}

            l1_score = float(l1["layer1_score"])
            l1_vals.append(l1_score)
            total_flips += int(l1["decision_flip_count"])

            l2_score = l2.get("cosine_similarity")
            if isinstance(l2_score, (int, float)):
                l2_vals.append(float(l2_score))

            l3_score = l3.get("overall_equivalence") if isinstance(l3, dict) else None
            if isinstance(l3_score, (int, float)):
                l3_vals.append(float(l3_score))

            bucket = by_agent.setdefault(aid, {"l1": [], "l2": [], "l3": []})
            bucket["l1"].append(l1_score)
            if isinstance(l2_score, (int, float)):
                bucket["l2"].append(float(l2_score))
            if isinstance(l3_score, (int, float)):
                bucket["l3"].append(float(l3_score))

            sample_id = f"{opt_trace.get('run_id')}:{aid}"
            per_sample_scores.append({
                "sample_id": sample_id,
                "agent_id": aid,
                "evaluation_level": "workflow" if aid == terminal_aid else "agent",
                "structural_decision_score": l1_score,
                "key_f1": l1["key_f1"],
                "decision_match_rate": l1["decision_match_rate"],
                "decision_flip_count": l1["decision_flip_count"],
                "decision_mismatches": l1["decision_mismatches"],
                "semantic_cosine_similarity": l2_score,
                "semantic_backend": l2["backend"],
                "llm_judge_equivalence": l3_score if l3 is not None else "disabled",
                "llm_judge_rationale": (l3 or {}).get("rationale") if isinstance(l3, dict) else None,
            })
            samples.append({
                "sample_id": sample_id,
                "run_id": opt_trace.get("run_id"),
                "agent_id": aid,
                "evaluation_level": "workflow" if aid == terminal_aid else "agent",
                "reference": json.dumps(base_out, default=str)[:800],
                "response": json.dumps(opt_out, default=str)[:800],
                "structural_decision_score": l1_score,
                "semantic_cosine_similarity": l2_score,
                "decision_flip_count": l1["decision_flip_count"],
                "decision_mismatches": l1["decision_mismatches"],
                "llm_judge_equivalence": l3_score if l3 is not None else "disabled",
            })

    if not per_sample_scores:
        return {
            "status": "unavailable",
            "evaluation_mode": "equivalence",
            "structural_decision_score": "unavailable",
            "semantic_cosine_similarity": "unavailable",
            "semantic_backend": semantic_backend,
            "llm_judge_equivalence": "disabled" if not (enable_llm_judge or judge_callable) else "unavailable",
            "overall_equivalence_score": "unavailable",
            "decision_flip_count": 0,
            "agent_level_scores": {},
            "samples": [],
            "per_sample_scores": [],
            "evaluation_model_usage": usage_tracker,
        }

    mean_l1 = round(statistics.mean(l1_vals), 4)
    mean_l2: Any = round(statistics.mean(l2_vals), 4) if l2_vals else "unavailable"
    mean_l3: Any = (
        round(statistics.mean(l3_vals), 4)
        if l3_vals
        else ("disabled" if not (enable_llm_judge or judge_callable) else "unavailable")
    )
    active_scores = [mean_l1] + ([float(mean_l2)] if isinstance(mean_l2, float) else []) + (
        [float(mean_l3)] if isinstance(mean_l3, float) else []
    )
    overall = round(statistics.mean(active_scores), 4)

    agent_level_scores = {
        aid: {
            "structural_decision_score": round(statistics.mean(b["l1"]), 4),
            "semantic_cosine_similarity": round(statistics.mean(b["l2"]), 4) if b["l2"] else "unavailable",
            "llm_judge_equivalence": (
                round(statistics.mean(b["l3"]), 4)
                if b["l3"]
                else ("disabled" if not (enable_llm_judge or judge_callable) else "unavailable")
            ),
        }
        for aid, b in by_agent.items()
    }

    return {
        "status": "evaluated",
        "evaluation_mode": "equivalence",
        "structural_decision_score": mean_l1,
        "semantic_cosine_similarity": mean_l2,
        "semantic_backend": semantic_backend,
        "llm_judge_equivalence": mean_l3,
        "overall_equivalence_score": overall,
        "decision_flip_count": total_flips,
        "agent_level_scores": agent_level_scores,
        "samples": samples,
        "per_sample_scores": per_sample_scores,
        "evaluation_model_usage": usage_tracker,
    }


def evaluate_equivalence_acceptance(
    eq_result: Optional[Dict[str, Any]],
    criteria: Optional[EquivalenceAcceptanceCriteria],
    *,
    execution_passed: bool,
    validation_passed: bool,
    schema_valid: bool,
    foundation_eq_scores: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate 3-layer equivalence quality gate without RAGAS retrieval penalties."""
    if not validation_passed or not execution_passed or not schema_valid:
        reasons = []
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
            "threshold_checks": {},
            "regression_checks": {},
        }

    if not isinstance(eq_result, dict) or eq_result.get("status") != "evaluated":
        return {
            "quality_accepted": False,
            "status": "inconclusive",
            "reasons": ["Matched baseline/optimized outputs unavailable for behavioral equivalence evaluation."],
            "threshold_checks": {},
            "regression_checks": {},
        }

    eff = criteria if isinstance(criteria, EquivalenceAcceptanceCriteria) else EquivalenceAcceptanceCriteria()
    threshold_checks: Dict[str, Any] = {}
    regression_checks: Dict[str, Any] = {}
    failed: List[str] = []

    l1_val = eq_result.get("structural_decision_score")
    if eff.min_structural_decision_score is not None:
        ok = isinstance(l1_val, (int, float)) and float(l1_val) >= float(eff.min_structural_decision_score)
        threshold_checks["structural_decision_score"] = {
            "required_min": eff.min_structural_decision_score,
            "actual": l1_val,
            "passed": ok,
        }
        if not ok:
            failed.append(f"structural_decision_score={l1_val} < required {eff.min_structural_decision_score:.2f}")

    l2_val = eq_result.get("semantic_cosine_similarity")
    if eff.min_semantic_cosine is not None:
        ok = isinstance(l2_val, (int, float)) and float(l2_val) >= float(eff.min_semantic_cosine)
        threshold_checks["semantic_cosine_similarity"] = {
            "required_min": eff.min_semantic_cosine,
            "actual": l2_val,
            "passed": ok,
        }
        if not ok:
            failed.append(f"semantic_cosine_similarity={l2_val} < required {eff.min_semantic_cosine:.2f}")

    l3_val = eq_result.get("llm_judge_equivalence")
    if l3_val not in ("disabled", None) and eff.min_llm_judge_score is not None:
        ok = isinstance(l3_val, (int, float)) and float(l3_val) >= float(eff.min_llm_judge_score)
        threshold_checks["llm_judge_equivalence"] = {
            "required_min": eff.min_llm_judge_score,
            "actual": l3_val,
            "passed": ok,
        }
        if not ok:
            failed.append(f"llm_judge_equivalence={l3_val} < required {eff.min_llm_judge_score:.2f}")

    flips = int(eq_result.get("decision_flip_count") or 0)
    if eff.max_decision_flips is not None:
        ok = flips <= int(eff.max_decision_flips)
        threshold_checks["decision_flip_count"] = {
            "max_allowed": eff.max_decision_flips,
            "actual": flips,
            "passed": ok,
        }
        if not ok:
            failed.append(f"decision_flip_count={flips} > allowed {eff.max_decision_flips}")

    if eff.max_regression_vs_foundation is not None and isinstance(foundation_eq_scores, dict):
        for key in ("structural_decision_score", "semantic_cosine_similarity"):
            base_v = foundation_eq_scores.get(key)
            cur_v = eq_result.get(key)
            if isinstance(base_v, (int, float)) and isinstance(cur_v, (int, float)):
                drop = round(float(base_v) - float(cur_v), 4)
                ok = drop <= float(eff.max_regression_vs_foundation)
                regression_checks[key] = {
                    "foundation_score": float(base_v),
                    "current_score": float(cur_v),
                    "drop": drop,
                    "passed": ok,
                }
                if not ok:
                    failed.append(f"{key} regressed by {drop:.4f} vs foundation (max {eff.max_regression_vs_foundation:.4f})")

    accepted = len(failed) == 0
    return {
        "quality_accepted": accepted,
        "status": "accepted" if accepted else "rejected",
        "reasons": failed or ["All 3-layer behavioral equivalence thresholds satisfied."],
        "threshold_checks": threshold_checks,
        "regression_checks": regression_checks,
    }
