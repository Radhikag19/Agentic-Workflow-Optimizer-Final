"""
Agentic Workplace FastAPI Application & Live WebSocket Server.
Strictly localhost-restricted visual/control integration layer over the existing
Python optimization engine (`SandboxExperimentRunner` & fixed historical baselines).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from api.routes import agents_router, experiments_router, reports_router, workflows_router
from api.services.artifact_service import ArtifactService, validate_safe_id
from api.services.event_service import EventService
from api.services.experiment_service import ExperimentService


def create_app(
    *,
    project_root: Optional[Path] = None,
    custom_runner_factory: Optional[Any] = None,
) -> FastAPI:
    app = FastAPI(
        title="Agentic Workplace API",
        description="Localhost FastAPI & WebSocket bridge for Agentic Workflow Optimizer",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    artifact_service = ArtifactService(project_root=project_root)
    event_service = EventService(key_mgr=artifact_service.key_mgr)
    experiment_service = ExperimentService(
        artifact_service=artifact_service,
        event_service=event_service,
    )

    app.state.artifact_service = artifact_service
    app.state.event_service = event_service
    app.state.experiment_service = experiment_service
    app.state.custom_runner_factory = custom_runner_factory

    @app.get("/api/health")
    def health_check() -> dict[str, str]:
        return {"status": "ok", "service": "agentic-workplace-api"}

    app.include_router(workflows_router)
    app.include_router(agents_router)
    app.include_router(experiments_router)
    app.include_router(reports_router)

    @app.websocket("/ws/experiments/{experiment_id}")
    async def experiment_events_ws(websocket: WebSocket, experiment_id: str) -> None:
        try:
            exp_id = validate_safe_id(experiment_id, "experiment_id")
        except ValueError:
            await websocket.close(code=1008)
            return

        event_service.bind_event_loop(asyncio.get_running_loop())
        await websocket.accept()
        queue = event_service.subscribe(exp_id)
        try:
            # Replay recorded events on connect/reconnect cleanly
            for past_ev in event_service.get_history(exp_id):
                await websocket.send_json(past_ev)

            while True:
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=20.0)
                    await websocket.send_json(ev)
                except asyncio.TimeoutError:
                    await websocket.send_json({
                        "event_id": "heartbeat",
                        "experiment_id": exp_id,
                        "timestamp": "",
                        "event_type": "heartbeat",
                        "agent_id": None,
                        "payload": {},
                    })
        except WebSocketDisconnect:
            pass
        finally:
            event_service.unsubscribe(exp_id, queue)

    return app


app = create_app()
