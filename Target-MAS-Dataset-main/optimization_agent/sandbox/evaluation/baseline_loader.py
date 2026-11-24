"""
Deterministic Historical Baseline Evidence Loader & Input Matcher.

Loads fixed historical runtime traces and metrics read-only (never re-executing
baseline agents, never launching baseline subprocesses, never calling Groq, and
never fabricating missing metrics). Matches historical traces to dataset input
records using explicit record identifiers rather than fragile array index order.
"""

from __future__ import annotations

import copy
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mcp_server import tools as evidence_tools
from optimization_agent.model_selection.groq_catalog import MODEL_CATALOG

_IDENTIFIER_KEYS: Tuple[str, ...] = (
    "application_id",
    "candidate_id",
    "job_id",
    "target_job_id",
    "request_id",
    "sku_id",
    "warehouse_id",
    "contract_id",
    "document_id",
    "invoice_id",
    "ticket_id",
    "lead_id",
    "incident_id",
    "claim_id",
    "expense_id",
    "employee_id",
    "case_id",
    "competitor_id",
    "doc_id",
    "runbook_id",
    "record_id",
    "id",
)


def compute_canonical_input_hash(record: Dict[str, Any]) -> str:
    """Hash canonical input record ignoring internal keys prefixed with '_'."""
    cleaned = {k: v for k, v in (record or {}).items() if not str(k).startswith("_")}
    return hashlib.sha256(json.dumps(cleaned, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def extract_record_identifiers(obj: Any) -> Dict[str, str]:
    """
    Extract canonical record identifiers from either a historical trace dict
    or a dataset input record without relying on trace index order.
    """
    ids: Dict[str, str] = {}

    def _scan_dict(d: Any) -> None:
        if not isinstance(d, dict):
            return
        for key in _IDENTIFIER_KEYS:
            val = d.get(key)
            if isinstance(val, (str, int)) and str(val).strip():
                norm_key = "job_id" if key == "target_job_id" else key
                ids.setdefault(norm_key, str(val).strip())

    if not isinstance(obj, dict):
        return ids

    # Check common structured sub-objects
    _scan_dict(obj.get("input_snapshot"))
    _scan_dict(obj.get("resume"))
    _scan_dict(obj.get("job"))
    fo = obj.get("final_output")
    if isinstance(fo, str) and fo.strip().startswith("{"):
        try:
            fo_parsed = json.loads(fo)
            if isinstance(fo_parsed, dict):
                _scan_dict(fo_parsed)
                if isinstance(fo_parsed.get("intake"), dict):
                    _scan_dict(fo_parsed.get("intake"))
        except Exception:
            pass
    else:
        _scan_dict(fo)
    for ex in obj.get("agent_executions") or []:
        if isinstance(ex, dict):
            _scan_dict(ex.get("output"))
    _scan_dict(obj)
    return ids


def _resolve_data_dir(workflow_id: str, data_base_dir: Optional[Path] = None) -> Path:
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    return (Path(data_base_dir).resolve() / workflow_id) if data_base_dir else (repo_root / "data" / workflow_id)


def load_workflow_dataset_index(
    workflow_id: str,
    data_base_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Load dataset records for `workflow_id` along with lookup indices for identifier matching.
    """
    data_dir = _resolve_data_dir(workflow_id, data_base_dir=data_base_dir)
    if not data_dir.exists() or not data_dir.is_dir():
        return {"kind": "empty", "records": [], "jobs_by_id": {}, "data_dir": str(data_dir)}

    resumes_p = data_dir / "resumes.json"
    jobs_p = data_dir / "jobs.json"
    if resumes_p.exists() and jobs_p.exists():
        resumes = json.loads(resumes_p.read_text(encoding="utf-8"))
        jobs = json.loads(jobs_p.read_text(encoding="utf-8"))
        jobs_by_id = {
            str(j.get("job_id")).strip(): j
            for j in jobs
            if isinstance(j, dict) and j.get("job_id")
        }
        records: List[Dict[str, Any]] = []
        for r in resumes:
            if not isinstance(r, dict):
                continue
            jid = str(r.get("target_job_id") or r.get("job_id") or "").strip()
            job = jobs_by_id.get(jid)
            if job is not None:
                records.append({"resume": r, "job": job})
        return {
            "kind": "recruitment",
            "records": records,
            "resumes": [r for r in resumes if isinstance(r, dict)],
            "jobs_by_id": jobs_by_id,
            "data_dir": str(data_dir),
        }

    # Generic JSON dataset loading (unwrapping dict-wrapped lists cleanly and prioritizing primary entity files)
    _PRIMARY_ORDER = {
        "expense_claims.json": 0,
        "historical_incidents.json": 0,
        "tickets.json": 0,
        "competitors.json": 0,
        "contracts.json": 0,
        "invoices.json": 0,
        "leads.json": 0,
        "procurement_requests.json": 0,
        "inventory_records.json": 0,
    }
    json_files = sorted(data_dir.glob("*.json"), key=lambda p: (_PRIMARY_ORDER.get(p.name, 5), p.name))
    all_records: List[Dict[str, Any]] = []
    by_filename: Dict[str, List[Dict[str, Any]]] = {}
    for jf in json_files:
        try:
            loaded = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        file_recs: List[Dict[str, Any]] = []
        if isinstance(loaded, list):
            file_recs = [entry for entry in loaded if isinstance(entry, dict)]
        elif isinstance(loaded, dict):
            list_items: List[Dict[str, Any]] = []
            for v in loaded.values():
                if isinstance(v, list):
                    list_items.extend(entry for entry in v if isinstance(entry, dict))
            file_recs = list_items if list_items else [loaded]
        by_filename[jf.name] = file_recs
        all_records.extend(file_recs)

    return {
        "kind": "generic",
        "records": all_records,
        "by_filename": by_filename,
        "jobs_by_id": {},
        "data_dir": str(data_dir),
    }


def _extract_content_signals(trace_obj: Dict[str, Any]) -> Dict[str, Any]:
    """Extract deterministic non-ID content attributes (incident title/service, competitors) when IDs are absent."""
    signals: Dict[str, Any] = {}
    for ex in trace_obj.get("agent_executions") or []:
        if not isinstance(ex, dict):
            continue
        out = ex.get("output")
        if isinstance(out, dict):
            if out.get("normalized_title") and not signals.get("title"):
                signals["title"] = str(out["normalized_title"]).strip()
            if out.get("affected_service") and not signals.get("service"):
                signals["service"] = str(out["affected_service"]).strip()
            if isinstance(out.get("target_competitors"), list) and not signals.get("target_competitors"):
                signals["target_competitors"] = [str(c).strip() for c in out["target_competitors"] if str(c).strip()]
    fo = trace_obj.get("final_output")
    if isinstance(fo, str) and fo.strip().startswith("{"):
        try:
            fo_d = json.loads(fo)
            intake = fo_d.get("intake") if isinstance(fo_d, dict) else None
            if isinstance(intake, dict):
                signals.setdefault("title", str(intake.get("normalized_title") or "").strip())
                signals.setdefault("service", str(intake.get("affected_service") or "").strip())
        except Exception:
            pass
    return signals


def _match_one_trace_to_dataset(
    trace_ids: Dict[str, str],
    dataset_index: Dict[str, Any],
    trace_obj: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Match extracted trace identifiers cleanly against dataset records.
    Returns (matched_input_record, reason_if_unmatched).
    """
    kind = dataset_index.get("kind")
    if kind == "recruitment":
        if not trace_ids:
            return None, "Trace contains no recognizable input record identifiers."
        resumes: List[Dict[str, Any]] = dataset_index.get("resumes") or []
        jobs_by_id: Dict[str, Dict[str, Any]] = dataset_index.get("jobs_by_id") or {}

        app_id = trace_ids.get("application_id")
        cand_id = trace_ids.get("candidate_id")
        job_id = trace_ids.get("job_id")

        matched_resume: Optional[Dict[str, Any]] = None
        for r in resumes:
            r_app = str(r.get("application_id") or "").strip()
            r_cand = str(r.get("candidate_id") or "").strip()
            if app_id and r_app == app_id:
                if cand_id and r_cand and r_cand != cand_id:
                    continue
                matched_resume = r
                break
            if cand_id and not app_id and r_cand == cand_id:
                matched_resume = r
                break

        if matched_resume is None:
            return (
                None,
                f"No dataset resume matched trace identifiers application_id={app_id!r}, candidate_id={cand_id!r}.",
            )

        target_jid = job_id or str(matched_resume.get("target_job_id") or "").strip()
        if target_jid not in jobs_by_id:
            return None, f"No dataset job matched trace job_id={target_jid!r}."

        return {"resume": copy.deepcopy(matched_resume), "job": copy.deepcopy(jobs_by_id[target_jid])}, ""

    # Generic record matching using primary non-trivial identifier overlap
    records: List[Dict[str, Any]] = dataset_index.get("records") or []
    priority_keys = [
        "claim_id",
        "request_id",
        "contract_id",
        "document_id",
        "invoice_id",
        "ticket_id",
        "lead_id",
        "incident_id",
        "expense_id",
        "sku_id",
        "application_id",
        "candidate_id",
        "record_id",
        "id",
    ]
    for pk in priority_keys:
        if pk not in trace_ids:
            continue
        t_val = trace_ids[pk]
        for rec in records:
            r_ids = extract_record_identifiers(rec)
            if r_ids.get(pk) == t_val:
                if "job_id" in trace_ids and "job_id" in r_ids and r_ids["job_id"] != trace_ids["job_id"]:
                    continue
                if "warehouse_id" in trace_ids and "warehouse_id" in r_ids and r_ids["warehouse_id"] != trace_ids["warehouse_id"]:
                    continue
                return copy.deepcopy(rec), ""

    # Secondary deterministic content matching (exact entity attributes — never index order)
    if trace_obj:
        signals = _extract_content_signals(trace_obj)
        by_fn = dataset_index.get("by_filename") or {}

        # Incident triage: match normalized_title + service against historical_incidents.json
        if signals.get("title"):
            norm_t = signals["title"].lower()
            svc = (signals.get("service") or "").lower()
            for inc in by_fn.get("historical_incidents.json", []) or records:
                ititle = str(inc.get("title") or "").strip().lower()
                isvc = str(inc.get("service") or "").strip().lower()
                if ititle and (ititle in norm_t or norm_t in ititle) and (not svc or not isvc or svc == isvc):
                    return copy.deepcopy(inc), ""

        # Market research: match target competitors against competitors.json
        if signals.get("target_competitors"):
            comp_recs = by_fn.get("competitors.json", [])
            matched_comps = [
                c for c in comp_recs
                if str(c.get("name") or "").lower() in {x.lower() for x in signals["target_competitors"]}
            ]
            if matched_comps:
                return {
                    "target_competitors": signals["target_competitors"],
                    "competitors": copy.deepcopy(matched_comps),
                }, ""

    if not trace_ids:
        return None, "Trace contains no recognizable input record identifiers."
    return None, f"No dataset record matched trace identifiers {trace_ids}."


def match_baseline_traces_to_inputs(
    traces: List[Tuple[str, Dict[str, Any]]],
    workflow_id: str,
    *,
    data_base_dir: Optional[Path] = None,
    max_records: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Deterministically match historical baseline traces `(trace_file_path, trace_dict)` to
    exact dataset records by identifier, excluding any unmatched traces explicitly.
    """
    dataset_index = load_workflow_dataset_index(workflow_id, data_base_dir=data_base_dir)
    matched_entries: List[Dict[str, Any]] = []
    excluded_records: List[Dict[str, Any]] = []

    for tf_path, trace_obj in traces:
        if max_records is not None and len(matched_entries) >= max_records:
            break

        run_id = str(trace_obj.get("run_id") or Path(tf_path).stem)
        t_ids = extract_record_identifiers(trace_obj)
        matched_rec, unmatched_reason = _match_one_trace_to_dataset(t_ids, dataset_index, trace_obj=trace_obj)
        if matched_rec is None:
            excluded_records.append({
                "trace_file": tf_path,
                "run_id": run_id,
                "extracted_identifiers": t_ids,
                "reason": unmatched_reason,
            })
            continue

        canonical_hash = compute_canonical_input_hash(matched_rec)
        trace_copy = copy.deepcopy(trace_obj)
        trace_copy["input_hash"] = canonical_hash
        trace_copy["input_snapshot"] = {
            "matched_baseline_run_id": run_id,
            "input_hash": canonical_hash,
            **t_ids,
        }
        trace_copy["execution_mode"] = "historical_recorded_execution"

        # Tag non-hashed internal provenance so optimized runs carry baseline reference without changing hash
        opt_input = copy.deepcopy(matched_rec)
        opt_input["_matched_baseline_run_id"] = run_id
        opt_input["_matched_identifiers"] = dict(t_ids)

        matched_entries.append({
            "trace_file": tf_path,
            "run_id": run_id,
            "trace": trace_copy,
            "input_record": opt_input,
            "input_hash": canonical_hash,
            "identifiers": t_ids,
        })

    return {
        "matched_entries": matched_entries,
        "excluded_records": excluded_records,
        "matched_input_count": len(matched_entries),
        "unmatched_input_count": len(excluded_records),
        "data_dir": dataset_index.get("data_dir"),
        "matching_status": "matched" if matched_entries else "no_matched_records",
    }


def _compute_historical_metrics(
    *,
    wf_id: str,
    trace_dir: Optional[str],
    matched_traces: List[Dict[str, Any]],
    fixed_ref_id: str,
    matched_hashes: List[str],
    matched_count: int,
    unmatched_count: int,
    excluded_records: List[Dict[str, Any]],
    reused_artifact: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compute baseline metrics strictly from non-null historical trace fields; never fabricates missing fields."""
    if reused_artifact is not None and isinstance(reused_artifact, dict) and reused_artifact.get("total_runs"):
        art = copy.deepcopy(reused_artifact)
        art.setdefault("source", "historical_runtime_traces")
        art.setdefault("execution_mode", "historical_recorded_execution")
        art.setdefault("execution_modes", ["historical_recorded_execution"])
        art["re_executed"] = False
        art["groq_api_calls"] = 0
        art.setdefault("trace_directory", trace_dir)
        art["fixed_baseline_reference_id"] = fixed_ref_id
        art["input_dataset_hashes"] = matched_hashes
        art["matched_input_count"] = matched_count
        art["unmatched_input_count"] = unmatched_count
        art["excluded_records"] = excluded_records
        return art

    total_runs = len(matched_traces)
    ok_traces = [t for t in matched_traces if str(t.get("status") or "").upper() == "SUCCESS"]
    ok_count = len(ok_traces)

    durs = [float(t["duration_seconds"]) for t in ok_traces if t.get("duration_seconds") is not None]
    toks = [float(t["total_tokens"]) for t in ok_traces if t.get("total_tokens") is not None]
    ptoks = [float(t["prompt_tokens"]) for t in ok_traces if t.get("prompt_tokens") is not None]
    ctoks = [float(t["completion_tokens"]) for t in ok_traces if t.get("completion_tokens") is not None]
    telemetry_costs = [float(t["estimated_cost_usd"]) for t in ok_traces if t.get("estimated_cost_usd") is not None]
    timestamps = [str(t["timestamp"]) for t in matched_traces if t.get("timestamp")]

    # Agent-level historical aggregation + catalog-normalized baseline cost (only if tokens exist)
    per_agent_buckets: Dict[str, Dict[str, Any]] = {}
    all_agent_durs: List[float] = []
    run_catalog_costs: List[float] = []
    m120 = MODEL_CATALOG["openai/gpt-oss-120b"]

    for t in ok_traces:
        run_cat_cost: Optional[float] = None
        if t.get("prompt_tokens") is not None and t.get("completion_tokens") is not None:
            run_cat_cost = (
                (float(t["prompt_tokens"]) / 1_000_000.0) * float(m120["input_price_per_million_usd"])
                + (float(t["completion_tokens"]) / 1_000_000.0) * float(m120["output_price_per_million_usd"])
            )
            run_catalog_costs.append(run_cat_cost)

        for ex in t.get("agent_executions") or []:
            aid = ex.get("agent_id")
            if not aid:
                continue
            b = per_agent_buckets.setdefault(
                aid,
                {"durations": [], "tokens": [], "prompt_tokens": [], "completion_tokens": [], "costs": [], "models": set()},
            )
            if ex.get("duration_seconds") is not None:
                d = float(ex["duration_seconds"])
                b["durations"].append(d)
                all_agent_durs.append(d)
            if ex.get("tokens") is not None:
                b["tokens"].append(float(ex["tokens"]))
            if ex.get("prompt_tokens") is not None:
                b["prompt_tokens"].append(float(ex["prompt_tokens"]))
            if ex.get("completion_tokens") is not None:
                b["completion_tokens"].append(float(ex["completion_tokens"]))
            if ex.get("estimated_cost_usd") is not None:
                b["costs"].append(float(ex["estimated_cost_usd"]))
            if ex.get("model"):
                b["models"].add(str(ex["model"]))

    per_agent_metrics: Dict[str, Any] = {}
    for aid, b in per_agent_buckets.items():
        per_agent_metrics[aid] = {
            "runs_count": len(b["durations"]) or len(b["tokens"]),
            "models_observed": sorted(b["models"]),
            "mean_latency_seconds": round(sum(b["durations"]) / len(b["durations"]), 4) if b["durations"] else None,
            "mean_tokens": round(sum(b["tokens"]) / len(b["tokens"]), 1) if b["tokens"] else None,
            "mean_prompt_tokens": round(sum(b["prompt_tokens"]) / len(b["prompt_tokens"]), 1) if b["prompt_tokens"] else None,
            "mean_completion_tokens": round(sum(b["completion_tokens"]) / len(b["completion_tokens"]), 1) if b["completion_tokens"] else None,
            "mean_cost_usd": round(sum(b["costs"]) / len(b["costs"]), 6) if b["costs"] else None,
        }

    mean_cost_cat = (
        round(sum(run_catalog_costs) / len(run_catalog_costs), 6)
        if run_catalog_costs
        else (round(sum(telemetry_costs) / len(telemetry_costs), 6) if telemetry_costs else None)
    )

    return {
        "workflow_id": wf_id,
        "source": "historical_runtime_traces",
        "execution_mode": "historical_recorded_execution",
        "execution_modes": ["historical_recorded_execution"],
        "re_executed": False,
        "groq_api_calls": 0,
        "trace_directory": trace_dir,
        "fixed_baseline_reference_id": fixed_ref_id,
        "measurement_period": {
            "earliest_trace_timestamp": min(timestamps) if timestamps else None,
            "latest_trace_timestamp": max(timestamps) if timestamps else None,
        },
        "total_runs": total_runs,
        "successful_runs": ok_count,
        "failed_runs": max(0, total_runs - ok_count),
        "success_rate_pct": round((ok_count / total_runs) * 100.0, 2) if total_runs > 0 else None,
        "mean_latency_seconds": round(sum(durs) / len(durs), 4) if durs else None,
        "median_latency_seconds": round(float(statistics.median(durs)), 4) if durs else None,
        "mean_agent_latency_seconds": round(sum(all_agent_durs) / len(all_agent_durs), 4) if all_agent_durs else None,
        "mean_tokens": round(sum(toks) / len(toks), 1) if toks else None,
        "mean_prompt_tokens": round(sum(ptoks) / len(ptoks), 1) if ptoks else None,
        "mean_completion_tokens": round(sum(ctoks) / len(ctoks), 1) if ctoks else None,
        "mean_cost_usd_telemetry": round(sum(telemetry_costs) / len(telemetry_costs), 6) if telemetry_costs else None,
        "mean_cost_usd_catalog_normalized": mean_cost_cat,
        "cost_calculation_basis": (
            "historical_trace_catalog_normalized_from_recorded_tokens"
            if run_catalog_costs
            else ("historical_trace_telemetry" if telemetry_costs else "unavailable")
        ),
        "schema_validation_passed": None,
        "structural_validity_pass_rate_pct": None,
        "semantic_quality_evaluation": "unavailable",
        "semantic_quality_status": "unavailable",
        "semantic_quality_pass_rate_pct": None,
        "per_agent_metrics": per_agent_metrics,
        "input_dataset_hashes": matched_hashes,
        "matched_input_count": matched_count,
        "unmatched_input_count": unmatched_count,
        "excluded_records": excluded_records,
    }


def _resolve_historical_traces_dir(
    workflow_id: str,
    *,
    baseline_traces_dir: Optional[Any] = None,
    evidence_dir: Optional[str] = None,
) -> Optional[Path]:
    if baseline_traces_dir is not None:
        p = Path(baseline_traces_dir).resolve()
        return p if p.exists() and p.is_dir() else None

    data, err = evidence_tools._load_evidence(workflow_id, evidence_dir=evidence_dir)
    if not err and isinstance(data, dict):
        tdir = evidence_tools._find_traces_dir(workflow_id, data)
        if tdir and tdir.exists() and tdir.is_dir():
            return tdir.resolve()

    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    for cand in (
        repo_root.parent / "Ingestion_Traces_final" / "Ingestion_Traces" / workflow_id,
        repo_root / "runs" / workflow_id,
    ):
        if cand.exists() and cand.is_dir():
            return cand.resolve()
    return None


def load_historical_baseline_evidence(
    workflow_id: str,
    *,
    baseline_traces_dir: Optional[Any] = None,
    baseline_metrics_artifact: Optional[Any] = None,
    evidence_dir: Optional[str] = None,
    data_base_dir: Optional[Path] = None,
    max_matched_records: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Load fixed historical baseline traces & metrics strictly read-only, match traces to
    canonical dataset records by explicit identifiers, and return zero-execution baseline bundle.
    """
    trace_dir = _resolve_historical_traces_dir(
        workflow_id,
        baseline_traces_dir=baseline_traces_dir,
        evidence_dir=evidence_dir,
    )

    loaded_traces: List[Tuple[str, Dict[str, Any]]] = []
    if trace_dir is not None:
        for tf in sorted(trace_dir.glob("*.json")):
            try:
                obj = json.loads(tf.read_text(encoding="utf-8"))
            except Exception:
                continue
            # Skip aggregate summary files that lack run_id + agent_executions
            if not isinstance(obj, dict) or "agent_executions" not in obj or not obj.get("run_id"):
                continue
            loaded_traces.append((str(tf), obj))

    match_res = match_baseline_traces_to_inputs(
        loaded_traces,
        workflow_id,
        data_base_dir=data_base_dir,
        max_records=max_matched_records,
    )
    matched_entries = match_res["matched_entries"]
    matched_traces = [e["trace"] for e in matched_entries]
    matched_inputs = [e["input_record"] for e in matched_entries]
    matched_hashes = [e["input_hash"] for e in matched_entries]
    matched_run_ids = [e["run_id"] for e in matched_entries]
    matched_files = [e["trace_file"] for e in matched_entries]

    ref_payload = f"{workflow_id}|{trace_dir}|{','.join(matched_run_ids)}"
    fixed_ref_id = f"hist_{hashlib.sha256(ref_payload.encode('utf-8')).hexdigest()[:12]}"

    reused_art: Optional[Dict[str, Any]] = None
    if baseline_metrics_artifact is not None:
        if isinstance(baseline_metrics_artifact, dict):
            reused_art = baseline_metrics_artifact
        else:
            art_p = Path(baseline_metrics_artifact)
            if art_p.exists():
                try:
                    reused_art = json.loads(art_p.read_text(encoding="utf-8"))
                except Exception:
                    reused_art = None

    hist_metrics = _compute_historical_metrics(
        wf_id=workflow_id,
        trace_dir=str(trace_dir) if trace_dir else None,
        matched_traces=matched_traces,
        fixed_ref_id=fixed_ref_id,
        matched_hashes=matched_hashes,
        matched_count=match_res["matched_input_count"],
        unmatched_count=match_res["unmatched_input_count"],
        excluded_records=match_res["excluded_records"],
        reused_artifact=reused_art,
    )

    ok_runs = sum(1 for t in matched_traces if str(t.get("status") or "").upper() == "SUCCESS")
    return {
        "variant": "baseline",
        "source": "historical_runtime_traces",
        "execution_mode": "historical_recorded_execution",
        "execution_modes": ["historical_recorded_execution"],
        "re_executed": False,
        "groq_api_calls": 0,
        "trace_directory": str(trace_dir) if trace_dir else None,
        "fixed_baseline_reference_id": fixed_ref_id,
        "total_historical_traces_found": len(loaded_traces),
        "matched_input_count": match_res["matched_input_count"],
        "unmatched_input_count": match_res["unmatched_input_count"],
        "excluded_records": match_res["excluded_records"],
        "matching_status": match_res["matching_status"],
        "matched_inputs": matched_inputs,
        "matched_input_hashes": matched_hashes,
        "matched_identifiers": [e["identifiers"] for e in matched_entries],
        "matched_run_ids": matched_run_ids,
        "trace_files": matched_files,
        "traces": matched_traces,
        "runs_executed": len(matched_traces),
        "successful_runs": ok_runs,
        "failed_runs": len(matched_traces) - ok_runs,
        "execution_passed": ok_runs > 0,
        "input_dataset_hashes": matched_hashes,
        "usage_sources": ["historical_recorded_trace"],
        "api_errors": [],
        "errors": [],
        "historical_metrics": hist_metrics,
    }
