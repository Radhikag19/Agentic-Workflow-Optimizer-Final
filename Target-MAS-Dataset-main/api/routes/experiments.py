"""Experiment Start, Status, and Results Routes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request

from api.schemas.experiment import (
    ExperimentResultsResponse,
    ExperimentStartRequest,
    ExperimentStatusResponse,
)
from api.services.experiment_service import DuplicateExperimentError

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


@router.get("", response_model=List[ExperimentStatusResponse])
def list_experiments(request: Request, workflow_id: Optional[str] = None) -> List[ExperimentStatusResponse]:
    svc = request.app.state.experiment_service
    try:
        return [ExperimentStatusResponse(**item) for item in svc.list_experiments(workflow_id=workflow_id)]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/start", response_model=ExperimentStatusResponse)
def start_experiment(payload: ExperimentStartRequest, request: Request) -> ExperimentStatusResponse:
    svc = request.app.state.experiment_service
    custom_factory = getattr(request.app.state, "custom_runner_factory", None)
    try:
        rec = svc.start_experiment(payload, runner_factory=custom_factory)
        return ExperimentStatusResponse(**rec)
    except DuplicateExperimentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{experiment_id}", response_model=ExperimentStatusResponse)
def get_experiment_status(experiment_id: str, request: Request) -> ExperimentStatusResponse:
    svc = request.app.state.experiment_service
    try:
        rec = svc.get_status(experiment_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Experiment '{experiment_id}' not found.")
    return ExperimentStatusResponse(**rec)


@router.get("/{experiment_id}/results", response_model=ExperimentResultsResponse)
def get_experiment_results(experiment_id: str, request: Request) -> ExperimentResultsResponse:
    svc = request.app.state.experiment_service
    try:
        res = svc.get_results(experiment_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if res is None:
        raise HTTPException(status_code=404, detail=f"Results for '{experiment_id}' not found.")
    return ExperimentResultsResponse(**res)


@router.get("/{experiment_id}/events")
def get_experiment_events(experiment_id: str, request: Request) -> List[Dict[str, Any]]:
    ev_svc = request.app.state.event_service
    return ev_svc.get_history(experiment_id)
