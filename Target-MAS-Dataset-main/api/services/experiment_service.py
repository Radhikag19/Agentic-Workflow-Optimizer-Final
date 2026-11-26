"""
Experiment Execution & Registry Service.
Delegates all actual optimization, validation, RAGAS quality assessment, and Pareto
selection strictly to `SandboxExperimentRunner` without duplicating any logic.
"""

from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from api.schemas.experiment import ExperimentStartRequest
from api.services.artifact_service import ArtifactService, validate_safe_id
from api.services.event_service import EventService
from optimization_agent.sandbox.evaluation.equivalence_evaluator import (
    EquivalenceAcceptanceCriteria,
)
from optimization_agent.sandbox.evaluation.ragas_evaluator import QualityAcceptanceCriteria
from optimization_agent.sandbox.experiment import SandboxExperimentRunner


class DuplicateExperimentError(RuntimeError):
    """Raised when an experiment for the same workflow & type is already active."""


class ExperimentService:
    """Coordinates async background experiment execution and reconstructs persisted states."""

    def __init__(
        self,
        artifact_service: Optional[ArtifactService] = None,
        event_service: Optional[EventService] = None,
    ):
        self.artifacts = artifact_service or ArtifactService()
        self.events = event_service or EventService()
        self._lock = threading.Lock()
        self._records: Dict[str, Dict[str, Any]] = {}
        self._results: Dict[str, Dict[str, Any]] = {}
        self._hydrate_saved_experiments()

    def _hydrate_saved_experiments(self) -> None:
        for item in self.artifacts.scan_saved_experiments():
            eid = item["experiment_id"]
            self._records[eid] = {
                "experiment_id": eid,
                "workflow_id": item["workflow_id"],
                "experiment_type": item["experiment_type"],
                "status": "completed",
                "created_at": item["created_at"],
                "started_at": item["started_at"],
                "completed_at": item["completed_at"],
                "num_runs": item["num_runs"],
                "selected_dimensions": None,
                "current_phase": "completed",
                "error": None,
                "experiment_dir": item["experiment_dir"],
                "json_report_path": item["json_report_path"],
                "markdown_report_path": item["markdown_report_path"],
                "has_results": True,
            }

    def list_experiments(self, workflow_id: Optional[str] = None) -> List[Dict[str, Any]]:
        self._hydrate_saved_experiments()
        with self._lock:
            items = list(self._records.values())
        if workflow_id:
            wf_id = validate_safe_id(workflow_id, "workflow_id")
            items = [i for i in items if i["workflow_id"] == wf_id]
        items.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
        return self.artifacts.sanitize_obj(items)

    def get_status(self, experiment_id: str) -> Optional[Dict[str, Any]]:
        exp_id = validate_safe_id(experiment_id, "experiment_id")
        with self._lock:
            rec = self._records.get(exp_id)
            if rec is not None:
                return self.artifacts.sanitize_obj(dict(rec))
        self._hydrate_saved_experiments()
        with self._lock:
            rec = self._records.get(exp_id)
            return self.artifacts.sanitize_obj(dict(rec)) if rec else None

    def get_results(self, experiment_id: str) -> Optional[Dict[str, Any]]:
        exp_id = validate_safe_id(experiment_id, "experiment_id")
        with self._lock:
            if exp_id in self._results:
                return self.artifacts.sanitize_obj(self._results[exp_id])
            rec = self._records.get(exp_id)

        if rec is None:
            self._hydrate_saved_experiments()
            with self._lock:
                rec = self._records.get(exp_id)
        if rec is None:
            return None

        bundle = self.artifacts.get_saved_report_bundle(exp_id)
        if not bundle or not isinstance(bundle.get("json_report"), dict):
            return {
                "experiment_id": exp_id,
                "workflow_id": rec["workflow_id"],
                "experiment_type": rec["experiment_type"],
                "status": rec["status"],
                "limitations": [rec["error"]] if rec.get("error") else [],
            }
        return self._format_results_from_report(exp_id, rec, bundle["json_report"])

    def _format_results_from_report(
        self,
        exp_id: str,
        rec: Dict[str, Any],
        rep: Dict[str, Any],
    ) -> Dict[str, Any]:
        kind = rec["experiment_type"]
        if kind == "two_phase_study":
            setup = rep.get("experimental_setup") or {}
            ev_mode = rep.get("evaluation_mode") or setup.get("evaluation_mode") or "ragas"
            return self.artifacts.sanitize_obj({
                "experiment_id": exp_id,
                "workflow_id": rec["workflow_id"],
                "experiment_type": kind,
                "evaluation_mode": ev_mode,
                "status": rec["status"],
                "fixed_optimization_foundation": rep.get("fixed_optimization_foundation") or [],
                "baseline_runtime_results": {
                    "fixed_baseline_reference_id": setup.get("fixed_baseline_reference_id"),
                    "re_executed": False,
                    "groq_api_calls": 0,
                    "matched_input_count": setup.get("matched_input_count"),
                    "unmatched_input_count": setup.get("excluded_input_count"),
                    "excluded_records": setup.get("excluded_records") or [],
                },
                "phase_a_foundation": rep.get("phase_a_foundation") or {},
                "phase_b_variable_dimensions": rep.get("phase_b_variable_dimensions") or {},
                "phase_c_combined": rep.get("phase_c_combined") or {},
                "comparative_configurations": rep.get("comparative_metrics") or [],
                "pareto_selection": rep.get("best_configuration_selection") or {},
                "ragas_evaluation_model_usage": setup.get("ragas_evaluation_model_usage") or {},
                "limitations": rep.get("limitations") or [],
                "original_integrity_after": rep.get("original_integrity_after") or {},
            })
        if kind == "dimension_ablation_suite":
            return self.artifacts.sanitize_obj({
                "experiment_id": exp_id,
                "workflow_id": rec["workflow_id"],
                "experiment_type": kind,
                "status": rec["status"],
                "baseline_runtime_results": rep.get("baseline_evidence") or {},
                "comparative_configurations": rep.get("comparison_rows") or [],
                "original_integrity_after": rep.get("original_integrity_after") or {},
            })
        return self.artifacts.sanitize_obj({
            "experiment_id": exp_id,
            "workflow_id": rec["workflow_id"],
            "experiment_type": kind,
            "status": rec["status"],
            "baseline_runtime_results": rep.get("baseline_evidence") or {},
            "single_experiment_result": rep,
            "original_integrity_after": (rep.get("validation_results") or {}).get("original_workflow_integrity") or {},
        })

    def _format_live_payload(self, exp_id: str, exp_type: str, wf_id: str, res: Dict[str, Any]) -> Dict[str, Any]:
        if exp_type == "two_phase_study":
            return self.artifacts.sanitize_obj({
                "experiment_id": exp_id,
                "workflow_id": wf_id,
                "experiment_type": exp_type,
                "evaluation_mode": res.get("evaluation_mode") or "ragas",
                "status": "completed",
                "fixed_optimization_foundation": res.get("fixed_optimization_foundation") or [],
                "baseline_runtime_results": res.get("baseline_runtime_results") or {},
                "phase_a_foundation": res.get("phase_a_foundation") or {},
                "phase_b_variable_dimensions": res.get("phase_b_variable_dimensions") or {},
                "phase_c_combined": res.get("phase_c_combined") or {},
                "comparative_configurations": res.get("comparative_configurations") or [],
                "pareto_selection": res.get("pareto_selection") or {},
                "ragas_evaluation_model_usage": res.get("ragas_evaluation_model_usage") or {},
                "limitations": res.get("limitations") or [],
                "original_integrity_after": res.get("original_integrity_after") or {},
            })
        if exp_type == "dimension_ablation_suite":
            return self.artifacts.sanitize_obj({
                "experiment_id": exp_id,
                "workflow_id": wf_id,
                "experiment_type": exp_type,
                "status": "completed",
                "baseline_runtime_results": res.get("baseline_runtime_results") or {},
                "comparative_configurations": res.get("comparison_rows") or [],
                "per_dimension_results": res.get("per_dimension_results") or {},
                "combined_result": res.get("combined_result"),
                "original_integrity_after": res.get("original_integrity_after") or {},
            })
        return self.artifacts.sanitize_obj({
            "experiment_id": exp_id,
            "workflow_id": wf_id,
            "experiment_type": exp_type,
            "status": "completed",
            "baseline_runtime_results": res.get("baseline_runtime_results") or {},
            "single_experiment_result": res.get("execution_report") or res,
            "original_integrity_after": res.get("original_integrity_after") or {},
        })

    def start_experiment(
        self,
        req: ExperimentStartRequest,
        *,
        runner_factory: Optional[Any] = None,
    ) -> Dict[str, Any]:
        wf_id = validate_safe_id(req.workflow_id, "workflow_id")
        scope = self.artifacts.load_approved_scope_for_workflow(wf_id, req.approved_scope_reference)
        if scope is None:
            raise ValueError(
                f"No approved_optimization_scope JSON found for '{wf_id}'. "
                "Complete human candidate approval in the Experiments tab (or Streamlit S11) first."
            )

        with self._lock:
            for existing in self._records.values():
                if (
                    existing["workflow_id"] == wf_id
                    and existing["experiment_type"] == req.experiment_type
                    and existing["status"] in ("queued", "running")
                ):
                    raise DuplicateExperimentError(
                        f"An active '{req.experiment_type}' experiment ({existing['experiment_id']}) is already running for '{wf_id}'."
                    )

            exp_id = f"wp_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
            created_at = datetime.now(timezone.utc).isoformat()
            exp_dir = (self.artifacts.experiments_dir / wf_id / exp_id).resolve()
            record = {
                "experiment_id": exp_id,
                "workflow_id": wf_id,
                "experiment_type": req.experiment_type,
                "status": "queued",
                "created_at": created_at,
                "started_at": None,
                "completed_at": None,
                "num_runs": req.num_runs,
                "selected_dimensions": req.selected_dimensions,
                "current_phase": "queued",
                "error": None,
                "experiment_dir": str(exp_dir),
                "json_report_path": None,
                "markdown_report_path": None,
                "has_results": False,
            }
            self._records[exp_id] = record

        worker_thread = threading.Thread(
            target=self._run_experiment_thread,
            args=(exp_id, wf_id, scope, req, runner_factory),
            daemon=True,
        )
        worker_thread.start()
        return self.artifacts.sanitize_obj(dict(record))

    def _run_experiment_thread(
        self,
        exp_id: str,
        wf_id: str,
        scope: Dict[str, Any],
        req: ExperimentStartRequest,
        runner_factory: Optional[Any],
    ) -> None:
        with self._lock:
            self._records[exp_id]["status"] = "running"
            self._records[exp_id]["started_at"] = datetime.now(timezone.utc).isoformat()
            self._records[exp_id]["current_phase"] = "preparing"

        self.events.publish({
            "experiment_id": exp_id,
            "event_type": "experiment_started",
            "payload": {"workflow_id": wf_id, "experiment_type": req.experiment_type, "num_runs": req.num_runs},
        })

        exp_root = (self.artifacts.experiments_dir / wf_id / exp_id).resolve()
        stop_tail = threading.Event()

        def _tail_loop() -> None:
            while not stop_tail.is_set():
                self.events.poll_jsonl_into_stream(exp_id, exp_root)
                time.sleep(0.35)

        tailer = threading.Thread(target=_tail_loop, daemon=True)
        tailer.start()

        def _forward_event(ev: Dict[str, Any]) -> None:
            self.events.publish(ev, override_experiment_id=exp_id)
            etype = str(ev.get("event_type") or "")
            if etype in ("sandbox_created", "candidate_applied", "validation_completed", "quality_evaluation_started"):
                with self._lock:
                    self._records[exp_id]["current_phase"] = etype

        try:
            trace_dir = self.artifacts._resolve_trace_dir(wf_id)
            ev_dir_str = str(self.artifacts.evidence_dir) if self.artifacts.evidence_dir.exists() else None
            if runner_factory is not None:
                runner = runner_factory(event_callback=_forward_event)
            else:
                runner = SandboxExperimentRunner(
                    agents_base_dir=self.artifacts.agents_dir,
                    experiments_base_dir=self.artifacts.experiments_dir,
                    enable_trace_replay_fallback=req.enable_trace_replay_fallback,
                    evidence_dir=ev_dir_str,
                    data_base_dir=self.artifacts.data_dir if self.artifacts.data_dir.exists() else None,
                    baseline_traces_dir=trace_dir,
                    execution_backend="local_subprocess",
                    per_run_subprocess=True,
                    event_callback=_forward_event,
                )

            if req.experiment_type == "two_phase_study":
                criteria = (
                    QualityAcceptanceCriteria.from_dict(req.quality_criteria.model_dump())
                    if req.quality_criteria is not None
                    else QualityAcceptanceCriteria(
                        min_faithfulness=0.70,
                        min_context_precision=0.70,
                        min_context_recall=0.70,
                        max_regression_vs_foundation=0.10,
                    )
                )
                eq_criteria = (
                    EquivalenceAcceptanceCriteria.from_dict(req.equivalence_criteria.model_dump())
                    if req.equivalence_criteria is not None
                    else EquivalenceAcceptanceCriteria()
                )
                study_kwargs: Dict[str, Any] = {
                    "study_id": exp_id,
                    "quality_criteria": criteria,
                    "selected_variable_dimensions": req.selected_dimensions or None,
                    "num_runs": req.num_runs,
                }
                if req.evaluation_mode == "equivalence":
                    study_kwargs["evaluation_mode"] = "equivalence"
                    study_kwargs["equivalence_criteria"] = eq_criteria
                    study_kwargs["enable_equivalence_llm_judge"] = req.enable_equivalence_llm_judge
                res = runner.run_two_phase_optimization_study(scope, **study_kwargs)
            elif req.experiment_type == "dimension_ablation_suite":
                res = runner.run_dimension_ablation_suite(
                    scope,
                    suite_id=exp_id,
                    selected_dimensions=req.selected_dimensions,
                    include_combined=True,
                    num_runs=req.num_runs,
                )
            else:
                res = runner.run(scope, experiment_id=exp_id, num_runs=req.num_runs)

            stop_tail.set()
            tailer.join(timeout=1.5)
            self.events.poll_jsonl_into_stream(exp_id, exp_root)

            formatted = self._format_live_payload(exp_id, req.experiment_type, wf_id, res)
            with self._lock:
                self._results[exp_id] = formatted
                rec = self._records[exp_id]
                rec["status"] = "completed"
                rec["current_phase"] = "completed"
                rec["completed_at"] = datetime.now(timezone.utc).isoformat()
                rec["json_report_path"] = res.get("json_report_path")
                rec["markdown_report_path"] = res.get("markdown_report_path")
                rec["has_results"] = True

            self.events.publish({
                "experiment_id": exp_id,
                "event_type": "experiment_completed",
                "payload": {
                    "workflow_id": wf_id,
                    "experiment_type": req.experiment_type,
                    "json_report_path": res.get("json_report_path"),
                    "markdown_report_path": res.get("markdown_report_path"),
                },
            })
        except Exception as exc:
            stop_tail.set()
            tailer.join(timeout=1.5)
            safe_err = self.artifacts.key_mgr.sanitize_text(str(exc))
            with self._lock:
                rec = self._records[exp_id]
                rec["status"] = "failed"
                rec["current_phase"] = "failed"
                rec["completed_at"] = datetime.now(timezone.utc).isoformat()
                rec["error"] = safe_err
            self.events.publish({
                "experiment_id": exp_id,
                "event_type": "experiment_failed",
                "payload": {"error": safe_err},
            })
