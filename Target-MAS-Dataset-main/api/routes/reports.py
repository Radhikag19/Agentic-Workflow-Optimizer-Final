"""Experiment Reports Route."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from api.schemas.experiment import ReportBundleResponse

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/{experiment_id}", response_model=ReportBundleResponse)
def get_experiment_reports(experiment_id: str, request: Request) -> ReportBundleResponse:
    artifacts = request.app.state.artifact_service
    try:
        bundle = artifacts.get_saved_report_bundle(experiment_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if bundle is None:
        raise HTTPException(status_code=404, detail=f"Reports for '{experiment_id}' not found.")
    return ReportBundleResponse(**bundle)
