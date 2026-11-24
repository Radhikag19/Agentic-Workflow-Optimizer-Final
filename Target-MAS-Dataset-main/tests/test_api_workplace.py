"""
Integration Tests for the Agentic Workplace FastAPI & WebSocket Layer.
Verifies workflow/agent/baseline/experiment/report endpoints, live event streaming,
zero baseline re-execution, path-traversal protection, duplicate prevention, and zero key leaks.
"""

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from api.main import create_app


def test_01_workflows_agents_and_fixed_baseline_readonly():
    app = create_app(project_root=ROOT_DIR)
    client = TestClient(app)

    r_health = client.get("/api/health")
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "ok"

    r_wfs = client.get("/api/workflows")
    assert r_wfs.status_code == 200
    wf_ids = [w["workflow_id"] for w in r_wfs.json()]
    assert "recruitment_screening" in wf_ids
    assert "contract_review" in wf_ids

    r_ov = client.get("/api/workflows/recruitment_screening/overview")
    assert r_ov.status_code == 200
    ov = r_ov.json()
    assert len(ov["agents"]) == 8
    assert ov["historical_baseline"]["re_executed"] is False
    assert ov["historical_baseline"]["groq_api_calls"] == 0

    # Generic adaptability: contract_review (10 agents) works cleanly too
    r_cr = client.get("/api/agents/contract_review")
    assert r_cr.status_code == 200
    assert len(r_cr.json()) == 10

    r_base = client.get("/api/workflows/recruitment_screening/baseline")
    assert r_base.status_code == 200
    base = r_base.json()
    assert base["re_executed"] is False
    assert base["groq_api_calls"] == 0
    assert base["matched_input_count"] == 10
    assert base["total_historical_traces_found"] == 30
    assert len(base["traces"]) == 10
    assert "gsk_" not in json.dumps(base)

    r_base_full = client.get("/api/workflows/recruitment_screening/baseline?max_traces=30")
    assert r_base_full.status_code == 200
    assert r_base_full.json()["matched_input_count"] == 30
    assert len(r_base_full.json()["traces"]) == 30


def test_02_path_traversal_blocked_and_saved_study_results_accessible():
    app = create_app(project_root=ROOT_DIR)
    client = TestClient(app)

    assert client.get("/api/workflows/..%2F..%2Fetc/overview").status_code in (400, 404)
    assert client.get("/api/reports/..%2Fsecret").status_code in (400, 404)

    r_exps = client.get("/api/experiments")
    assert r_exps.status_code == 200
    exp_ids = [e["experiment_id"] for e in r_exps.json()]
    if "live_validation_recruitment_screening" in exp_ids:
        r_res = client.get("/api/experiments/live_validation_recruitment_screening/results")
        assert r_res.status_code == 200
        data = r_res.json()
        assert data["baseline_runtime_results"]["re_executed"] is False
        assert data["baseline_runtime_results"]["groq_api_calls"] == 0
        assert len(data["comparative_configurations"]) >= 4

        r_rep = client.get("/api/reports/live_validation_recruitment_screening")
        assert r_rep.status_code == 200
        assert "## 1. Experimental Setup" in (r_rep.json().get("markdown_report") or "")


def test_03_start_experiment_websocket_stream_and_duplicate_guard(tmp_path: Path):
    # Isolated project fixture using real runner mock to verify async start, WS stream, and dup guard
    (tmp_path / "Agents" / "demo_wf").mkdir(parents=True)
    (tmp_path / "Agents" / "demo_wf" / "workflow.json").write_text(
        json.dumps({"workflow_name": "demo_wf", "agents": [{"agent_id": "a1", "role": "R1", "dependencies": []}]}),
        encoding="utf-8",
    )
    (tmp_path / "reports" / "experiments").mkdir(parents=True)
    (tmp_path / "reports" / "demo_wf_approved_optimization_scope.json").write_text(
        json.dumps({
            "workflow_id": "demo_wf",
            "approval_status": "approved",
            "approved_candidate_ids": ["C1"],
            "approved_candidates": [{"candidate_id": "C1", "dimension": "model_selection", "target_agents": ["a1"]}],
        }),
        encoding="utf-8",
    )

    class _FakeRunner:
        def __init__(self, event_callback=None):
            self.cb = event_callback

        def run_two_phase_optimization_study(self, scope, *, study_id=None, **_kw):
            time.sleep(0.15)
            if self.cb:
                self.cb({"experiment_id": study_id, "event_type": "agent_started", "agent_id": "a1", "payload": {"model": "openai/gpt-oss-20b"}})
                self.cb({"experiment_id": study_id, "event_type": "agent_completed", "agent_id": "a1", "payload": {"tokens": 120}})
            out_dir = tmp_path / "reports" / "experiments" / "demo_wf" / study_id
            out_dir.mkdir(parents=True, exist_ok=True)
            j_p = out_dir / "study_report.json"
            m_p = out_dir / "study_report.md"
            j_p.write_text(json.dumps({"study_id": study_id, "workflow_id": "demo_wf"}), encoding="utf-8")
            m_p.write_text("# Demo Study", encoding="utf-8")
            return {
                "study_id": study_id,
                "workflow_id": "demo_wf",
                "fixed_optimization_foundation": ["communication_data_handoff"],
                "baseline_runtime_results": {"re_executed": False, "groq_api_calls": 0},
                "comparative_configurations": [],
                "pareto_selection": {},
                "ragas_evaluation_model_usage": {},
                "limitations": [],
                "original_integrity_after": {"original_unchanged": True},
                "json_report_path": str(j_p),
                "markdown_report_path": str(m_p),
            }

    app = create_app(project_root=tmp_path, custom_runner_factory=_FakeRunner)
    client = TestClient(app)

    r_start = client.post(
        "/api/experiments/start",
        json={"workflow_id": "demo_wf", "experiment_type": "two_phase_study", "num_runs": 1},
    )
    assert r_start.status_code == 200
    exp_id = r_start.json()["experiment_id"]

    # Duplicate active run rejected with 409
    r_dup = client.post(
        "/api/experiments/start",
        json={"workflow_id": "demo_wf", "experiment_type": "two_phase_study", "num_runs": 1},
    )
    assert r_dup.status_code == 409

    received_types = []
    with client.websocket_connect(f"/ws/experiments/{exp_id}") as ws:
        for _ in range(10):
            msg = ws.receive_json()
            received_types.append(msg["event_type"])
            if msg["event_type"] == "experiment_completed":
                break

    assert "experiment_started" in received_types
    assert "agent_started" in received_types
    assert "agent_completed" in received_types
    assert "experiment_completed" in received_types

    r_res = client.get(f"/api/experiments/{exp_id}/results")
    assert r_res.status_code == 200
    assert r_res.json()["fixed_optimization_foundation"] == ["communication_data_handoff"]


def test_04_all_10_workflows_agents_prompts_helpers_and_baseline_matching():
    app = create_app(project_root=ROOT_DIR)
    client = TestClient(app)

    wfs = client.get("/api/workflows").json()
    assert len(wfs) == 10

    matched_by_wf = {}
    for w in wfs:
        wid = w["workflow_id"]
        ov = client.get(f"/api/workflows/{wid}/overview")
        ags = client.get(f"/api/agents/{wid}")
        base = client.get(f"/api/workflows/{wid}/baseline?max_traces=30")
        assert ov.status_code == 200
        assert ags.status_code == 200
        assert base.status_code == 200

        ag_list = ags.json()
        assert len(ag_list) >= 6, f"{wid} returned only {len(ag_list)} agents"
        for a in ag_list:
            assert isinstance(a["responsibilities"], list)
            assert len(a["input_fields"]) > 0, f"{wid}.{a['agent_id']} missing input_fields"
            assert len(a["output_fields"]) > 0, f"{wid}.{a['agent_id']} missing output_fields"
            assert a.get("original_prompt_preview"), f"{wid}.{a['agent_id']} missing prompt preview"
            assert a.get("execution_style") in ("pure_llm", "hybrid_python_plus_llm")

        bjson = base.json()
        assert bjson["re_executed"] is False
        assert bjson["groq_api_calls"] == 0
        assert len(bjson["replay_traces"]) > 0
        matched_by_wf[wid] = bjson["matched_input_count"]

    assert matched_by_wf["expense_reimbursement"] > 0
    assert matched_by_wf["incident_triage"] > 0
    assert matched_by_wf["market_research"] > 0


def test_05_human_gate_review_and_approve_scope_and_execution_modes(tmp_path: Path):
    (tmp_path / "Agents" / "demo_wf").mkdir(parents=True)
    (tmp_path / "Agents" / "demo_wf" / "workflow.json").write_text(
        json.dumps({"workflow_name": "demo_wf", "agents": [{"agent_id": "a1", "role": "R1", "dependencies": []}]}),
        encoding="utf-8",
    )
    (tmp_path / "reports" / "experiments").mkdir(parents=True)
    (tmp_path / "reports" / "demo_wf_optimization_report.json").write_text(
        json.dumps({
            "workflow_id": "demo_wf",
            "model_selection_recommendations": [
                {
                    "candidate_id": "MOD-A1",
                    "dimension": "model_selection",
                    "title": "Compact model for a1",
                    "target_agents": ["a1"],
                    "tier": "Tier 2",
                    "requires_validation": True,
                    "supporting_evidence": {"current_model": "openai/gpt-oss-120b"},
                    "tradeoffs_and_risks": {
                        "output_quality_risk": "Moderate risk on edge cases",
                        "implementation_complexity": "Low",
                    },
                }
            ],
            "prompt_optimization_opportunities": [
                {
                    "candidate_id": "PROMPT-A1",
                    "dimension": "prompt_optimization",
                    "title": "Compress prompt for a1",
                    "target_agents": ["a1"],
                    "tier": "Tier 1",
                    "requires_validation": False,
                    "supporting_evidence": {"avg_tokens": 1200},
                    "tradeoffs_and_risks": {
                        "output_quality_risk": "Low",
                        "implementation_complexity": "Low",
                    },
                }
            ],
        }),
        encoding="utf-8",
    )

    class _FakeModeRunner:
        def __init__(self, event_callback=None):
            self.cb = event_callback

        def run_two_phase_optimization_study(self, scope, *, study_id=None, **_kw):
            return {"study_id": study_id, "workflow_id": scope["workflow_id"]}

        def run_dimension_ablation_suite(self, scope, *, suite_id=None, **_kw):
            return {"suite_id": suite_id, "workflow_id": scope["workflow_id"]}

    app = create_app(project_root=tmp_path, custom_runner_factory=_FakeModeRunner)
    client = TestClient(app)

    r_rev = client.get("/api/workflows/demo_wf/review")
    assert r_rev.status_code == 200
    rev = r_rev.json()
    assert rev["has_discovery_report"] is True
    assert rev["has_approved_scope"] is False
    cands = {c["candidate_id"]: c for c in rev["candidates"]}
    assert cands["MOD-A1"]["requires_risk_acknowledgement"] is True
    assert cands["PROMPT-A1"]["requires_risk_acknowledgement"] is False

    # Missing risk acknowledgement must fail cleanly with 400
    r_bad = client.post(
        "/api/workflows/demo_wf/approve",
        json={"selected_candidate_ids": ["MOD-A1", "PROMPT-A1"], "risk_acknowledged_candidate_ids": []},
    )
    assert r_bad.status_code == 400

    # Approve with risk acknowledged persists approved scope JSON
    r_ok = client.post(
        "/api/workflows/demo_wf/approve",
        json={
            "selected_candidate_ids": ["MOD-A1", "PROMPT-A1"],
            "risk_acknowledged_candidate_ids": ["MOD-A1"],
        },
    )
    assert r_ok.status_code == 200
    assert (tmp_path / "reports" / "demo_wf_approved_optimization_scope.json").exists()

    # Both execution modes start cleanly once approved
    r_pareto = client.post(
        "/api/experiments/start",
        json={"workflow_id": "demo_wf", "experiment_type": "two_phase_study", "num_runs": 1},
    )
    assert r_pareto.status_code == 200

    r_custom = client.post(
        "/api/experiments/start",
        json={
            "workflow_id": "demo_wf",
            "experiment_type": "dimension_ablation_suite",
            "selected_dimensions": ["model_selection", "prompt_optimization"],
            "num_runs": 1,
        },
    )
    assert r_custom.status_code == 200

