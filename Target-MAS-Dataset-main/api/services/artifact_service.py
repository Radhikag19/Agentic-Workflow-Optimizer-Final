"""
Read-only artifact loader for Target MAS workflows, historical baselines, approved scopes,
and saved experiment/study reports. Never executes baseline agents or exposes API keys.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from api.services.ast_metadata import extract_workflow_agent_metadata, normalize_responsibilities
from mcp_server import tools as evidence_tools
from optimization_agent.key_manager import GroqKeyManager, get_default_key_manager
from optimization_agent.review.models import (
    get_dimension_label,
    get_risk_info,
    normalize_dimension_key,
    normalize_tier,
)
from optimization_agent.review.session import CandidateReviewSession
from optimization_agent.sandbox.evaluation.baseline_loader import (
    load_historical_baseline_evidence,
)
from optimization_agent.sandbox.executors.base import BaseOptimizationExecutor

_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,120}$")
_SECRET_TOKEN_RE = re.compile(r"(?:gsk_|sk-)[A-Za-z0-9_.-]{4,}")


def validate_safe_id(value: str, label: str = "id") -> str:
    cleaned = str(value or "").strip()
    if not cleaned or not _SAFE_ID_RE.match(cleaned) or ".." in cleaned:
        raise ValueError(f"Invalid {label}: {value!r}")
    return cleaned


class ArtifactService:
    """Safely exposes workspace MAS artifacts without touching original files or re-executing baseline."""

    def __init__(
        self,
        project_root: Optional[Path] = None,
        key_mgr: Optional[GroqKeyManager] = None,
    ):
        self.project_root = (
            Path(project_root).resolve()
            if project_root
            else Path(__file__).resolve().parent.parent.parent
        )
        self.agents_dir = (self.project_root / "Agents").resolve()
        self.reports_dir = (self.project_root / "reports").resolve()
        self.experiments_dir = (self.reports_dir / "experiments").resolve()
        self.evidence_dir = (self.project_root / "Workflow_Evidence").resolve()
        self.data_dir = (self.project_root / "data").resolve()
        self.key_mgr = key_mgr or get_default_key_manager()
        self._ast_helper = BaseOptimizationExecutor()

    def sanitize_obj(self, obj: Any) -> Any:
        raw = json.dumps(obj, default=str)
        scrubbed = self.key_mgr.sanitize_text(raw)
        scrubbed = _SECRET_TOKEN_RE.sub("[REDACTED_API_KEY]", scrubbed)
        return json.loads(scrubbed)

    def _resolve_workflow_dir(self, workflow_id: str) -> Path:
        wf_id = validate_safe_id(workflow_id, "workflow_id")
        wf_dir = (self.agents_dir / wf_id).resolve()
        if not wf_dir.is_relative_to(self.agents_dir) or not wf_dir.exists():
            raise FileNotFoundError(f"Workflow '{wf_id}' not found.")
        return wf_dir

    def _resolve_trace_dir(self, workflow_id: str) -> Optional[Path]:
        candidates = [
            self.project_root.parent / "Ingestion_Traces_final" / "Ingestion_Traces" / workflow_id,
            self.project_root / "Ingestion_Traces_final" / "Ingestion_Traces" / workflow_id,
        ]
        for c in candidates:
            if c.exists() and c.is_dir():
                return c.resolve()
        return None

    def list_workflows(self) -> List[Dict[str, Any]]:
        if not self.agents_dir.exists():
            return []
        out: List[Dict[str, Any]] = []
        for wf_dir in sorted(self.agents_dir.iterdir()):
            if not wf_dir.is_dir() or wf_dir.name.startswith(".") or wf_dir.name == "__pycache__":
                continue
            wf_json_p = wf_dir / "workflow.json"
            if not wf_json_p.exists():
                continue
            wf_id = wf_dir.name
            try:
                wf_data = json.loads(wf_json_p.read_text(encoding="utf-8"))
            except Exception:
                continue

            trace_dir = self._resolve_trace_dir(wf_id)
            trace_count = 0
            if trace_dir is not None:
                trace_count = len([
                    p for p in trace_dir.glob("*.json")
                    if "summary" not in p.name.lower()
                ])

            scope_p = self.reports_dir / f"{wf_id}_approved_optimization_scope.json"
            approved_count = 0
            if scope_p.exists():
                try:
                    sc = json.loads(scope_p.read_text(encoding="utf-8"))
                    approved_count = len(sc.get("approved_candidate_ids") or [])
                except Exception:
                    pass

            disc_p = self.reports_dir / f"{wf_id}_optimization_report.json"
            out.append(self.sanitize_obj({
                "workflow_id": wf_id,
                "workflow_name": wf_data.get("workflow_name") or wf_data.get("name") or wf_id,
                "agent_count": len(wf_data.get("agents") or []),
                "baseline_model": wf_data.get("baseline_model") or wf_data.get("fixed_model") or "openai/gpt-oss-120b",
                "llm_provider": wf_data.get("llm_provider") or "Groq",
                "has_historical_traces": trace_count > 0,
                "historical_trace_count": trace_count,
                "has_approved_scope": scope_p.exists(),
                "approved_candidate_count": approved_count,
                "has_discovery_report": disc_p.exists(),
            }))
        return out

    def get_agents(self, workflow_id: str) -> List[Dict[str, Any]]:
        wf_dir = self._resolve_workflow_dir(workflow_id)
        wf_data = json.loads((wf_dir / "workflow.json").read_text(encoding="utf-8"))
        source_meta = extract_workflow_agent_metadata(wf_dir, wf_data, self._ast_helper)

        ev_dir_str = str(self.evidence_dir) if self.evidence_dir.exists() else None
        ev_summary: Dict[str, Any] = {}
        try:
            if (self.evidence_dir / workflow_id / "workflow_evidence.json").exists():
                tok_m = evidence_tools.get_token_metrics(workflow_id, evidence_dir=ev_dir_str).get("agent_token_metrics") or {}
                lat_m = evidence_tools.get_latency_metrics(workflow_id, evidence_dir=ev_dir_str).get("agent_latency_metrics") or {}
                cost_m = evidence_tools.get_cost_metrics(workflow_id, evidence_dir=ev_dir_str).get("agent_cost_metrics") or {}
                ev_summary = {"tok": tok_m, "lat": lat_m, "cost": cost_m}
        except Exception:
            ev_summary = {}

        profiles: List[Dict[str, Any]] = []
        base_model = wf_data.get("baseline_model") or wf_data.get("fixed_model") or "openai/gpt-oss-120b"
        for ag in wf_data.get("agents") or []:
            if not isinstance(ag, dict):
                continue
            aid_raw = ag.get("agent_id") or ag.get("id")
            if not aid_raw:
                continue
            aid = str(aid_raw)
            meta = source_meta.get(aid) or {}
            role = meta.get("role") or ag.get("role") or ag.get("name") or aid
            goal = meta.get("goal") or ag.get("goal") or (
                ag.get("responsibilities") if isinstance(ag.get("responsibilities"), str) else None
            )
            helpers = list(meta.get("helpers") or [])
            prompt_parts = [
                f"Goal: {goal}" if goal else "",
                f"Backstory: {meta['backstory']}" if meta.get("backstory") else "",
                f"Task Prompt:\n{meta['task_desc']}" if meta.get("task_desc") else "",
            ]
            prompt_txt = "\n".join(p for p in prompt_parts if p)

            in_fields = list(ag.get("input_fields") or ag.get("inputs") or [])
            out_fields = list(ag.get("output_fields") or ag.get("outputs") or [])
            resps = normalize_responsibilities(ag.get("responsibilities"))
            if not resps and goal:
                resps = [goal]

            tok_info = (ev_summary.get("tok") or {}).get(aid) or {}
            lat_info = (ev_summary.get("lat") or {}).get(aid) or {}
            cost_info = (ev_summary.get("cost") or {}).get(aid) or {}
            profiles.append(self.sanitize_obj({
                "agent_id": aid,
                "agent_name": ag.get("agent_name") or ag.get("name") or aid.replace("_", " ").title(),
                "role": role,
                "goal": goal,
                "responsibilities": resps,
                "dependencies": list(ag.get("dependencies") or []),
                "input_fields": in_fields,
                "output_fields": out_fields,
                "model": ag.get("model") or base_model,
                "original_prompt_preview": prompt_txt[:950] if prompt_txt else f"Role: {role}",
                "execution_style": "hybrid_python_plus_llm" if helpers else "pure_llm",
                "helper_functions": helpers,
                "historical_mean_latency_seconds": lat_info.get("mean_seconds"),
                "historical_mean_tokens": tok_info.get("mean_total_tokens") or tok_info.get("mean_tokens"),
                "historical_mean_cost_usd": cost_info.get("mean_cost_usd"),
            }))
        return profiles

    def get_historical_baseline(self, workflow_id: str, max_traces: int = 10) -> Dict[str, Any]:
        """Load fixed historical baseline evidence read-only (NEVER executes baseline workflow)."""
        wf_dir = self._resolve_workflow_dir(workflow_id)
        wf_data = json.loads((wf_dir / "workflow.json").read_text(encoding="utf-8"))
        ev_dir_str = str(self.evidence_dir) if self.evidence_dir.exists() else None
        trace_dir = self._resolve_trace_dir(workflow_id)

        bundle = load_historical_baseline_evidence(
            workflow_id,
            baseline_traces_dir=trace_dir,
            evidence_dir=ev_dir_str,
            data_base_dir=self.data_dir if self.data_dir.exists() else None,
            max_matched_records=max_traces,
        )
        traces = list(bundle.get("traces") or [])
        replay_traces: List[Dict[str, Any]] = list(traces[:max_traces])
        if not replay_traces and trace_dir is not None and trace_dir.exists():
            for tf in sorted(trace_dir.glob("*.json")):
                if "summary" in tf.name.lower():
                    continue
                try:
                    raw_t = json.loads(tf.read_text(encoding="utf-8"))
                    if isinstance(raw_t, dict):
                        raw_t["execution_mode"] = "historical_recorded_execution"
                        replay_traces.append(raw_t)
                except Exception:
                    continue
                if len(replay_traces) >= max_traces:
                    break

        metric_traces = traces if traces else replay_traces
        hist_summary = dict(bundle.get("historical_metrics") or {})
        hist_summary.update({
            "workflow_mean_latency_seconds": (
                sum(float(t.get("duration_seconds") or 0.0) for t in metric_traces) / len(metric_traces)
                if metric_traces else hist_summary.get("mean_latency_seconds")
            ),
            "workflow_mean_tokens": (
                sum(float(t.get("total_tokens") or 0.0) for t in metric_traces) / len(metric_traces)
                if metric_traces else hist_summary.get("mean_tokens")
            ),
        })
        raw_order = wf_data.get("execution_order") or [
            (a.get("agent_id") or a.get("id"))
            for a in (wf_data.get("agents") or [])
            if isinstance(a, dict) and (a.get("agent_id") or a.get("id"))
        ]
        return self.sanitize_obj({
            "workflow_id": workflow_id,
            "fixed_baseline_reference_id": bundle.get("fixed_baseline_reference_id"),
            "source": bundle.get("source") or "historical_runtime_traces",
            "execution_mode": "historical_recorded_execution",
            "re_executed": False,
            "groq_api_calls": 0,
            "trace_directory": bundle.get("trace_directory"),
            "total_historical_traces_found": int(bundle.get("total_historical_traces_found") or 0),
            "matched_input_count": int(bundle.get("matched_input_count") or 0),
            "unmatched_input_count": int(bundle.get("unmatched_input_count") or 0),
            "excluded_records": list(bundle.get("excluded_records") or []),
            "execution_order": list(raw_order),
            "historical_model": wf_data.get("baseline_model") or wf_data.get("fixed_model") or "openai/gpt-oss-120b",
            "metrics": hist_summary,
            "traces": traces[:max_traces],
            "replay_traces": replay_traces,
        })

    def load_approved_scope_for_workflow(
        self,
        workflow_id: str,
        approved_scope_reference: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        wf_id = validate_safe_id(workflow_id, "workflow_id")
        if approved_scope_reference:
            ref_name = Path(approved_scope_reference).name
            validate_safe_id(ref_name, "approved_scope_reference")
            candidate_path = (self.reports_dir / ref_name).resolve()
            if not candidate_path.is_relative_to(self.reports_dir) or not candidate_path.exists():
                raise FileNotFoundError(f"Approved scope '{ref_name}' not found under reports/.")
        else:
            candidate_path = (self.reports_dir / f"{wf_id}_approved_optimization_scope.json").resolve()
            if not candidate_path.exists():
                return None

        raw = json.loads(candidate_path.read_text(encoding="utf-8"))
        if raw.get("workflow_id") and raw.get("workflow_id") != wf_id:
            raise ValueError(f"Scope workflow_id '{raw.get('workflow_id')}' does not match '{wf_id}'.")
        return self.sanitize_obj(raw)

    def load_discovered_candidates(self, workflow_id: str) -> Dict[str, List[Dict[str, Any]]]:
        wf_id = validate_safe_id(workflow_id, "workflow_id")
        disc_p = (self.reports_dir / f"{wf_id}_optimization_report.json").resolve()
        grouped: Dict[str, List[Dict[str, Any]]] = {
            "communication_data_handoff": [],
            "workflow_parallelization": [],
            "model_selection": [],
            "prompt_optimization": [],
            "agent_consolidation": [],
        }
        if not disc_p.exists():
            return grouped
        try:
            rep = json.loads(disc_p.read_text(encoding="utf-8"))
        except Exception:
            return grouped

        mapping = (
            ("communication_data_handoff", "communication_optimization_opportunities"),
            ("workflow_parallelization", "workflow_parallelization_opportunities"),
            ("model_selection", "model_selection_recommendations"),
            ("prompt_optimization", "prompt_optimization_opportunities"),
            ("agent_consolidation", "agent_consolidation_opportunities"),
        )
        for canon, raw_key in mapping:
            sec = rep.get(raw_key)
            if isinstance(sec, list):
                grouped[canon] = sec
            elif isinstance(sec, dict) and isinstance(sec.get("candidates"), list):
                grouped[canon] = sec["candidates"]
        return self.sanitize_obj(grouped)

    def get_workflow_overview(self, workflow_id: str) -> Dict[str, Any]:
        wf_dir = self._resolve_workflow_dir(workflow_id)
        wf_data = json.loads((wf_dir / "workflow.json").read_text(encoding="utf-8"))
        agents = self.get_agents(workflow_id)
        baseline = self.get_historical_baseline(workflow_id, max_traces=3)
        approved_scope = self.load_approved_scope_for_workflow(workflow_id)
        discovered = self.load_discovered_candidates(workflow_id)

        approved_cands = list((approved_scope or {}).get("approved_candidates") or [])
        return self.sanitize_obj({
            "workflow_id": workflow_id,
            "workflow_name": wf_data.get("workflow_name") or wf_data.get("name") or workflow_id,
            "baseline_model": wf_data.get("baseline_model") or wf_data.get("fixed_model") or "openai/gpt-oss-120b",
            "llm_provider": wf_data.get("llm_provider") or "Groq",
            "agents": agents,
            "execution_order": baseline["execution_order"],
            "historical_baseline": {
                k: baseline[k]
                for k in (
                    "fixed_baseline_reference_id",
                    "re_executed",
                    "groq_api_calls",
                    "matched_input_count",
                    "unmatched_input_count",
                    "total_historical_traces_found",
                    "historical_model",
                    "metrics",
                )
            },
            "approved_scope": approved_scope,
            "approved_candidates": approved_cands,
            "discovered_candidates_by_dimension": discovered,
        })

    def get_review_candidates(self, workflow_id: str) -> Dict[str, Any]:
        """Return Human Gate (S11) candidate review inventory with tier & risk metadata."""
        self._resolve_workflow_dir(workflow_id)
        wf_id = validate_safe_id(workflow_id, "workflow_id")
        approved_scope = self.load_approved_scope_for_workflow(wf_id)
        approved_ids = set((approved_scope or {}).get("approved_candidate_ids") or [])

        disc_p = (self.reports_dir / f"{wf_id}_optimization_report.json").resolve()
        if not disc_p.exists():
            return self.sanitize_obj({
                "workflow_id": wf_id,
                "has_discovery_report": False,
                "has_approved_scope": bool(approved_scope and approved_ids),
                "approved_candidate_ids": sorted(approved_ids),
                "summary": {},
                "dimension_counts": [],
                "candidates": [],
            })

        session = CandidateReviewSession.from_workflow_id(wf_id, reports_dir=self.reports_dir)
        eligible_set = set(session.eligible_candidate_ids)
        items: List[Dict[str, Any]] = []
        for cand in session.candidates:
            cid = str(cand.get("candidate_id") or "")
            dim_key = normalize_dimension_key(cand.get("dimension"))
            risk_info = get_risk_info(cand)
            items.append({
                "candidate_id": cid,
                "dimension": dim_key,
                "dimension_label": get_dimension_label(dim_key),
                "title": cand.get("title") or cid,
                "tier": normalize_tier(cand),
                "target_agents": list(cand.get("target_agents") or []),
                "observed_problem": cand.get("observed_problem") or "",
                "proposed_solution": cand.get("proposed_solution") or "",
                "requires_validation": bool(cand.get("requires_validation", False)),
                "requires_risk_acknowledgement": bool(risk_info["requires_risk_acknowledgement"]),
                "risk_level": risk_info.get("output_quality_risk") or "Not available",
                "risk_warning": risk_info.get("risk_summary") or "",
                "eligible": cid in eligible_set,
                "already_approved": cid in approved_ids,
            })

        return self.sanitize_obj({
            "workflow_id": wf_id,
            "has_discovery_report": True,
            "has_approved_scope": bool(approved_scope and approved_ids),
            "approved_candidate_ids": sorted(approved_ids),
            "summary": session.get_workflow_summary(),
            "dimension_counts": session.get_dimension_counts(),
            "candidates": items,
        })

    def approve_workflow_candidates(
        self,
        workflow_id: str,
        selected_candidate_ids: List[str],
        risk_acknowledged_candidate_ids: List[str],
    ) -> Dict[str, Any]:
        """Validate selections & risk acknowledgements via CandidateReviewSession and persist scope."""
        self._resolve_workflow_dir(workflow_id)
        wf_id = validate_safe_id(workflow_id, "workflow_id")
        session = CandidateReviewSession.from_workflow_id(wf_id, reports_dir=self.reports_dir)
        session.clear_selection()
        selected_set = {str(cid) for cid in selected_candidate_ids}
        for cid in selected_candidate_ids:
            try:
                session.select_candidate(str(cid))
            except KeyError as exc:
                raise ValueError(str(exc)) from exc

        for cid in risk_acknowledged_candidate_ids:
            cid_str = str(cid)
            if cid_str in selected_set:
                try:
                    session.acknowledge_risk(cid_str, True)
                except KeyError as exc:
                    raise ValueError(str(exc)) from exc

        scope = session.approve(
            expected_workflow_id=wf_id,
            persist=True,
            output_dir=self.reports_dir,
        )
        return self.sanitize_obj(scope)

    def scan_saved_experiments(self) -> List[Dict[str, Any]]:
        """Discover saved studies/ablation suites/single experiments under reports/experiments/."""
        if not self.experiments_dir.exists():
            return []
        found: List[Dict[str, Any]] = []
        for wf_dir in sorted(self.experiments_dir.iterdir()):
            if not wf_dir.is_dir():
                continue
            wf_id = wf_dir.name
            for exp_dir in sorted(wf_dir.iterdir()):
                if not exp_dir.is_dir():
                    continue
                exp_id = exp_dir.name
                study_j = exp_dir / "study_report.json"
                ablation_j = exp_dir / "ablation_comparison_report.json"
                exec_j = exp_dir / "execution_report.json"
                if study_j.exists():
                    kind, rep_p, md_p = "two_phase_study", study_j, exp_dir / "study_report.md"
                elif ablation_j.exists():
                    kind, rep_p, md_p = "dimension_ablation_suite", ablation_j, exp_dir / "ablation_comparison_report.md"
                elif exec_j.exists():
                    kind, rep_p, md_p = "combined_single_workflow", exec_j, exp_dir / "execution_report.md"
                else:
                    continue
                try:
                    data = json.loads(rep_p.read_text(encoding="utf-8"))
                except Exception:
                    continue
                found.append(self.sanitize_obj({
                    "experiment_id": exp_id,
                    "workflow_id": wf_id,
                    "experiment_type": kind,
                    "status": "completed",
                    "created_at": str(data.get("generated_at") or ""),
                    "started_at": str(data.get("generated_at") or ""),
                    "completed_at": str(data.get("generated_at") or ""),
                    "num_runs": int(data.get("num_runs") or data.get("runs_executed") or 1),
                    "experiment_dir": str(exp_dir),
                    "json_report_path": str(rep_p),
                    "markdown_report_path": str(md_p) if md_p.exists() else None,
                    "raw_report": data,
                }))
        return found

    def get_saved_report_bundle(self, experiment_id: str) -> Optional[Dict[str, Any]]:
        exp_id = validate_safe_id(experiment_id, "experiment_id")
        for item in self.scan_saved_experiments():
            if item["experiment_id"] != exp_id:
                continue
            exp_dir = Path(item["experiment_dir"])
            json_p = Path(item["json_report_path"])
            md_p = Path(item["markdown_report_path"]) if item.get("markdown_report_path") else None
            sub_reports: List[Dict[str, Any]] = []
            for sub_json in sorted(exp_dir.rglob("execution_report.json")):
                if sub_json.resolve() == json_p.resolve():
                    continue
                rel = sub_json.relative_to(exp_dir).as_posix()
                sub_md = sub_json.with_suffix(".md")
                sub_reports.append({
                    "relative_path": rel,
                    "json_report_path": str(sub_json),
                    "markdown_report_path": str(sub_md) if sub_md.exists() else None,
                })
            return self.sanitize_obj({
                "experiment_id": exp_id,
                "workflow_id": item["workflow_id"],
                "report_kind": item["experiment_type"],
                "json_report_path": str(json_p),
                "markdown_report_path": str(md_p) if md_p and md_p.exists() else None,
                "json_report": item["raw_report"],
                "markdown_report": md_p.read_text(encoding="utf-8") if md_p and md_p.exists() else None,
                "sub_reports": sub_reports,
            })
        return None
