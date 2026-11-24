# Target MAS & Agentic Workplace Architecture

Clean modular layout of the optimization backend, thin FastAPI bridge, and PixiJS virtual office frontend.

## Directory Map

- `Agents/` — Original 10 CrewAI Target MAS workflows (`contract_review`, `customer_support`, `expense_reimbursement`, `incident_triage`, `inventory_replenishment`, `invoice_processing`, `market_research`, `procurement_supplier_selection`, `recruitment_screening`, `sales_lead_qualification`). Never mutated by sandbox experiments.
- `common/` — Shared CrewAI/Groq LLM runner, API key manager, validation schemas, and Arize Phoenix tracing.
- `data/` — Per-workflow synthetic input datasets paired with `Ingestion_Traces_final/`.
- `ingestion/` & `evidence_aggregation/` — Static AST + trace ingestion generating `Workflow_Evidence/`.
- `mcp_server/` — 10 read-only MCP evidence tools (`tools.py`, `server.py`) queried during discovery & model selection.
- `optimization_agent/` — LangGraph optimization discovery engine (`agent.py`, `discovery.py`, `tradeoff.py`, `report.py`), human approval (`review/`), JEV model selection (`model_selection/`), and isolated subprocess execution & RAGAS/Pareto evaluation (`sandbox/`).
- `api/` — Thin localhost FastAPI + WebSocket bridge (`main.py`, `routes/`, `schemas/`, `services/`). Never re-executes historical baselines or duplicates optimization/RAGAS/Pareto logic.
- `frontend/src/` — Retro pixel-art office UI (`React` + `TypeScript` + `PixiJS v8` + `Zustand`):
  - `App.tsx`, `main.tsx` — App shell & error boundary wrapper.
  - `pages/` — 5 flat top-level navigation views (`OfficePage.tsx`, `ExperimentsPage.tsx`, `QualityLabPage.tsx`, `PerformanceReviewPage.tsx`, `ReportsPage.tsx`).
  - `components/` — Reusable UI widgets (`Header.tsx`, `DimensionToolbar.tsx`, `DimensionLensBanner.tsx`, `TraceSimulationBar.tsx`, `AgentInspector.tsx`, `ActivityFeed.tsx`, `ErrorBoundary.tsx`).
  - `office/` — Dynamic PixiJS engine (`dimensionMapper.ts`, `officeLayout.ts`, `officeStations.ts`, `agentSprite.ts`, `officeAnimations.ts`, `officeScene.ts`, `OfficeCanvas.tsx`).
  - `store/` — Zustand state (`workplaceStore.ts`), WebSocket client (`socketClient.ts`), and zero-Groq historical trace replay (`traceSimulator.ts`).
  - `services/`, `styles/`, `types/` — Typed REST client, muted-by-default 8-bit WebAudio cues, retro tokens/CSS, and shared TypeScript contracts.
- `tests/` — Automated pytest verification suite across MCP tools, optimization discovery, candidate review, local subprocess execution, RAGAS/Pareto selection, and FastAPI endpoints.

## Running Locally (2 Terminals)

```powershell
# Terminal 1 — FastAPI Backend (port 8000)
Set-Location Target-MAS-Dataset-main
$env:PYTHONPATH = "."
py -3.12 -m uvicorn api.main:app --host 127.0.0.1 --port 8000

# Terminal 2 — Vite React + PixiJS Frontend (port 5173)
Set-Location Target-MAS-Dataset-main/frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

Open **http://127.0.0.1:5173/**.
