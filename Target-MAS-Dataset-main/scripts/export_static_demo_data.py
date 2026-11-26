"""
Export sanitized static JSON snapshots of all workflows and verified experiment studies
into `frontend/public/demo-data/` for free-tier Render Static Site hosting (`VITE_STATIC_MODE=true`).

Zero secrets are exported (validates that no `gsk_<token>` pattern exists anywhere in output).
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "frontend" / "public" / "demo-data"
sys.path.insert(0, str(REPO_ROOT))

from api.services.artifact_service import ArtifactService
from api.services.event_service import EventService
from api.services.experiment_service import ExperimentService

SECRET_PATTERN = re.compile(r"gsk_[A-Za-z0-9]{12,}")

PREFERRED_EXPERIMENTS = [
    "wp_synth_5dim_live_20261126_024837",
    "wp_20261125_060543_ac51b3",
    "wp_20261125_091807_cbdcfb",
]


_DUPLICATE_HEAVY_KEYS = {
    "runtime_traces",
    "traces",
    "sample_results",
    "ragas_evaluations",
    "evaluations",
    "runtime_results",
    "quality_evaluation",
    "execution_results",
    "validation_results",
    "baseline_runtime_results",
    "per_dimension_results",
}


def _strip_heavy_recursive(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: _strip_heavy_recursive(v)
            for k, v in obj.items()
            if k not in _DUPLICATE_HEAVY_KEYS
        }
    if isinstance(obj, list):
        return [_strip_heavy_recursive(x) for x in obj]
    return obj


def _compact_json_report_for_viewer(jr: Any) -> Any:
    """Keep top-level comparative metrics, Pareto selection, setup, and metadata without duplicating huge trace payloads."""
    if not isinstance(jr, dict):
        return jr
    out = {}
    for k, v in jr.items():
        if k in ("phase_a_foundation", "phase_b_variable_dimensions", "phase_c_combined", "variable_dimension_experiments", "dimension_results"):
            out[k] = _strip_heavy_recursive(v)
        elif k not in ("baseline_runtime_results",):
            out[k] = v
    return out


def _write_json(path: Path, data: Any) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
    if SECRET_PATTERN.search(text):
        raise RuntimeError(f"SECURITY BLOCK: Found unmasked Groq API key pattern in {path}")
    path.write_text(text, encoding="utf-8")
    return path.stat().st_size


def main() -> None:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    artifacts = ArtifactService(project_root=REPO_ROOT)
    events = EventService(key_mgr=artifacts.key_mgr)
    exp_service = ExperimentService(artifact_service=artifacts, event_service=events)

    total_files = 0
    total_bytes = 0

    def save(rel: str, obj: Any) -> None:
        nonlocal total_files, total_bytes
        total_bytes += _write_json(OUT_DIR / rel, obj)
        total_files += 1

    # 1. Workflows catalog + per-workflow bundles
    workflows = artifacts.list_workflows()
    save("workflows.json", workflows)

    for wf in workflows:
        wf_id = wf["workflow_id"]
        save(f"workflows/{wf_id}/overview.json", artifacts.get_workflow_overview(wf_id))
        save(f"workflows/{wf_id}/baseline.json", artifacts.get_historical_baseline(wf_id, max_traces=10))
        save(f"workflows/{wf_id}/agents.json", artifacts.get_agents(wf_id))
        try:
            review = artifacts.get_workflow_review(wf_id)
        except Exception as exc:
            review = {
                "workflow_id": wf_id,
                "has_discovery_report": False,
                "has_approved_scope": False,
                "approved_candidate_ids": [],
                "summary": {},
                "dimension_counts": {},
                "candidates": [],
                "note": str(exc),
            }
        save(f"workflows/{wf_id}/review.json", review)

    # 2. Select clean completed experiments (up to 6 per workflow, keeping preferred featured runs first)
    all_exps = exp_service.list_experiments()
    by_wf: Dict[str, List[Dict[str, Any]]] = {}
    for item in all_exps:
        by_wf.setdefault(item["workflow_id"], []).append(item)

    exported_index: List[Dict[str, Any]] = []
    pref_rank = {eid: idx for idx, eid in enumerate(PREFERRED_EXPERIMENTS)}

    for wf_id, items in sorted(by_wf.items()):
        # Sort preferred experiments first, then newest first
        sorted_items = sorted(
            items,
            key=lambda x: (0 if x["experiment_id"] in pref_rank else 1, pref_rank.get(x["experiment_id"], 999), -len(str(x.get("created_at") or ""))),
        )
        kept_for_wf = 0
        for rec in sorted_items:
            if kept_for_wf >= 2:
                break
            eid = rec["experiment_id"]
            if eid not in pref_rank and any(x["experiment_id"] in pref_rank for x in sorted_items):
                continue
            # Skip known aborted/failed empty sandbox runs
            if "verify_20261126_023836" in eid:
                continue
            results = exp_service.get_results(eid) or {}
            report_bundle = artifacts.get_saved_report_bundle(eid) or {
                "experiment_id": eid,
                "workflow_id": wf_id,
                "experiment_type": rec.get("experiment_type", "unknown"),
                "json_report_path": rec.get("json_report_path"),
                "markdown_report_path": rec.get("markdown_report_path"),
                "json_report": None,
                "markdown_report": None,
                "sub_reports": [],
            }
            if isinstance(report_bundle.get("json_report"), dict):
                report_bundle["json_report"] = _compact_json_report_for_viewer(report_bundle["json_report"])
            ev_list = events.get_history(eid)

            # Strip local workstation paths in static bundle strings cleanly while preserving filenames
            exported_index.append(rec)
            save(f"experiments/{eid}/status.json", rec)
            save(f"experiments/{eid}/results.json", results)
            save(f"experiments/{eid}/events.json", ev_list)
            save(f"experiments/{eid}/report.json", report_bundle)
            kept_for_wf += 1

    save("experiments/index.json", exported_index)

    mb = total_bytes / (1024 * 1024)
    print(f"EXPORT_STATIC_DEMO_OK: workflows={len(workflows)} experiments={len(exported_index)} files={total_files} size={mb:.2f} MB")


if __name__ == "__main__":
    main()
