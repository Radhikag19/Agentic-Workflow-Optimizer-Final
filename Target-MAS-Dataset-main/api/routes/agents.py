"""Agent Profile & Historical Metrics Routes."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, Request

from api.schemas.agent import AgentProfile

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("/{workflow_id}", response_model=List[AgentProfile])
def get_workflow_agents(workflow_id: str, request: Request) -> List[AgentProfile]:
    artifacts = request.app.state.artifact_service
    try:
        return [AgentProfile(**item) for item in artifacts.get_agents(workflow_id)]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
