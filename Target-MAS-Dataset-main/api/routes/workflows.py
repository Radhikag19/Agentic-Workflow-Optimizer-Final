"""Workflow Inventory, Overview, and Fixed Historical Baseline Routes."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, Request

from api.schemas.agent import (
    ApproveScopeRequest,
    WorkflowOverviewResponse,
    WorkflowReviewResponse,
    WorkflowSummary,
)
from api.schemas.experiment import BaselineResponse

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


@router.get("", response_model=List[WorkflowSummary])
def list_workflows(request: Request) -> List[WorkflowSummary]:
    artifacts = request.app.state.artifact_service
    return [WorkflowSummary(**item) for item in artifacts.list_workflows()]


@router.get("/{workflow_id}/overview", response_model=WorkflowOverviewResponse)
def get_workflow_overview(workflow_id: str, request: Request) -> WorkflowOverviewResponse:
    artifacts = request.app.state.artifact_service
    try:
        data = artifacts.get_workflow_overview(workflow_id)
        return WorkflowOverviewResponse(**data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{workflow_id}/baseline", response_model=BaselineResponse)
def get_workflow_baseline(workflow_id: str, request: Request, max_traces: int = 10) -> BaselineResponse:
    """Return fixed historical baseline traces & metrics read-only (never executes baseline)."""
    artifacts = request.app.state.artifact_service
    try:
        data = artifacts.get_historical_baseline(workflow_id, max_traces=max(1, min(max_traces, 30)))
        return BaselineResponse(**data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{workflow_id}/review", response_model=WorkflowReviewResponse)
def get_workflow_review(workflow_id: str, request: Request) -> WorkflowReviewResponse:
    """Return discovered candidates and human-gate approval metadata for a workflow."""
    artifacts = request.app.state.artifact_service
    try:
        data = artifacts.get_review_candidates(workflow_id)
        return WorkflowReviewResponse(**data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{workflow_id}/approve")
def approve_workflow_scope(
    workflow_id: str,
    payload: ApproveScopeRequest,
    request: Request,
):
    """Persist human-approved optimization candidates via CandidateReviewSession."""
    artifacts = request.app.state.artifact_service
    try:
        return artifacts.approve_workflow_candidates(
            workflow_id,
            selected_candidate_ids=payload.selected_candidate_ids,
            risk_acknowledged_candidate_ids=payload.risk_acknowledged_candidate_ids,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
