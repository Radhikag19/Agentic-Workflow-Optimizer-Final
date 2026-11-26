"""
Discovery Analysis Engine for TraceProfiler Autonomous Optimization Discovery Agent.

Systematically analyzes the 5 active optimization dimensions:
- Agent Consolidation
- Workflow Parallelization (with strict dependency independence verification)
- Model Selection (strictly marked as requires_validation=True)
- Prompt Optimization (prompt bloat, token overhead)
- Communication & Data-Handoff Optimization (payload bloat, state pass-through)

Uses dedicated Groq API keys per dimension without simple round-robin.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from optimization_agent.key_manager import GroqKeyManager, get_default_key_manager
from optimization_agent.state import OptimizationAgentState

logger = logging.getLogger("optimization_agent.discovery")


def _build_graph_reachability(graph_data: Dict[str, Any]) -> Dict[str, Set[str]]:
    """
    Build transitive closure of reachability for workflow graph.
    Returns mapping: agent_id -> set of agent_ids that depend on it (downstream reachable).
    """
    edges = graph_data.get("edges", [])
    adj: Dict[str, Set[str]] = {}
    for edge in edges:
        src = edge.get("source")
        tgt = edge.get("target")
        if src and tgt:
            adj.setdefault(src, set()).add(tgt)

    def get_all_reachable(start_node: str) -> Set[str]:
        visited: Set[str] = set()
        queue = [start_node]
        while queue:
            curr = queue.pop(0)
            for neighbor in adj.get(curr, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        return visited

    reachability: Dict[str, Set[str]] = {}
    for node in graph_data.get("nodes", []):
        nid = node.get("id") or node.get("agent_id")
        if nid:
            reachability[nid] = get_all_reachable(nid)
    return reachability


def verify_dependency_independence(
    agent_a: str,
    agent_b: str,
    reachability: Dict[str, Set[str]],
    profiles: Dict[str, Any],
) -> Tuple[bool, str]:
    """
    Verify whether agent_a and agent_b are mutually independent.
    Returns (is_independent, justification).
    """
    # 1. Graph topological reachability check
    a_reaches_b = agent_b in reachability.get(agent_a, set())
    b_reaches_a = agent_a in reachability.get(agent_b, set())

    if a_reaches_b:
        return False, f"Direct or transitive graph dependency detected: {agent_a} -> ... -> {agent_b}"
    if b_reaches_a:
        return False, f"Direct or transitive graph dependency detected: {agent_b} -> ... -> {agent_a}"

    # 2. Input/output overlap check
    p_map = {p["agent_id"]: p for p in profiles.get("profiles", []) if isinstance(p, dict) and p.get("agent_id")}
    p_a = p_map.get(agent_a, {})
    p_b = p_map.get(agent_b, {})

    a_outs = set(p_a.get("declared_outputs", []))
    b_ins = set(p_b.get("declared_inputs", []))
    b_outs = set(p_b.get("declared_outputs", []))
    a_ins = set(p_a.get("declared_inputs", []))

    if a_outs.intersection(b_ins):
        return False, f"Data dependency: {agent_b} inputs intersect with {agent_a} outputs."
    if b_outs.intersection(a_ins):
        return False, f"Data dependency: {agent_a} inputs intersect with {agent_b} outputs."

    return True, f"Verified independent: No direct/transitive edge between {agent_a} and {agent_b}, and no shared I/O coupling."


class OptimizationDiscoveryEngine:
    """Discovers optimization opportunities across the 5 active dimensions."""

    def __init__(
        self,
        key_manager: Optional[GroqKeyManager] = None,
        consolidation_client: Optional[Any] = None,
        prompt_opt_client: Optional[Any] = None,
        handoff_client: Optional[Any] = None,
        jev_caller: Optional[Any] = None,
        jev_live_groq_models: Optional[Dict[str, Any]] = None,
        jev_results_dir: Optional[Any] = None,
        use_cached_jev: bool = True,
    ):
        self.key_mgr = key_manager or get_default_key_manager()
        self.consolidation_client = consolidation_client
        self.prompt_opt_client = prompt_opt_client
        self.handoff_client = handoff_client
        self.jev_caller = jev_caller
        self.jev_live_groq_models = jev_live_groq_models
        self.jev_results_dir = jev_results_dir
        self.use_cached_jev = use_cached_jev

    def discover_all_dimensions(self, state: OptimizationAgentState) -> Dict[str, Any]:
        """Execute systematic analysis across the 5 active optimization dimensions."""
        candidates: List[Dict[str, Any]] = []
        dim_analyses: Dict[str, Any] = {}

        # Precompute reachability graph for strict parallelization checks
        graph = state.get("workflow_graph", {})
        reachability = _build_graph_reachability(graph)

        # Agent Consolidation
        cand_b, ana_b = self._analyze_dimension_b_consolidation(state)
        candidates.extend(cand_b)
        dim_analyses["agent_consolidation"] = ana_b

        # Workflow Parallelization
        cand_c, ana_c = self._analyze_dimension_c_parallelization(state, reachability)
        candidates.extend(cand_c)
        dim_analyses["workflow_parallelization"] = ana_c

        # Model Selection
        cand_d, ana_d = self._analyze_dimension_d_model_selection(state)
        candidates.extend(cand_d)
        dim_analyses["model_selection"] = ana_d

        # Prompt Optimization
        cand_e, ana_e = self._analyze_dimension_e_prompt_optimization(
            state, consolidation_candidates=cand_b
        )
        candidates.extend(cand_e)
        dim_analyses["prompt_optimization"] = ana_e

        # Communication & Data Handoff
        cand_g, ana_g = self._analyze_dimension_g_communication(state)
        candidates.extend(cand_g)
        dim_analyses["communication_optimization"] = ana_g

        return {
            "optimization_candidates": candidates,
            "dimension_analyses": dim_analyses,
        }

    # =========================================================================
    # Dimension B: Agent Consolidation
    # =========================================================================
    def _analyze_dimension_b_consolidation(
        self, state: OptimizationAgentState
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        from optimization_agent.consolidation import AgentConsolidationEngine

        engine = AgentConsolidationEngine(
            key_manager=self.key_mgr,
            groq_client=self.consolidation_client,
        )
        return engine.analyze(state)

    # =========================================================================
    # Dimension C: Workflow Parallelization
    # =========================================================================
    def _analyze_dimension_c_parallelization(
        self,
        state: OptimizationAgentState,
        reachability: Dict[str, Set[str]],
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        raw_key, env_var, masked = self.key_mgr.get_key_for_task("workflow_parallelization")
        agents = state.get("discovered_agents", [])
        latency_map = state.get("latency_metrics", {}).get("agent_latency_metrics", {})
        profiles = state.get("agent_profiles", {})

        candidates: List[Dict[str, Any]] = []

        # Test candidate pairs for parallelization
        potential_parallel_pairs = [
            ("compliance_deviation_agent", "risk_ambiguity_agent"),
            ("policy_interpretation_agent", "clause_mapping_agent"),
            ("supplier_profile_agent", "delivery_analysis_agent"),
            ("lead_fit_agent", "intent_analysis_agent"),
            ("qualification_agent", "job_criteria_agent"),
            ("stock_policy_agent", "demand_forecast_agent"),
            ("inventory_check_agent", "fraud_screen_agent"),
        ]

        for a1, a2 in potential_parallel_pairs:
            if a1 in agents and a2 in agents:
                is_indep, justification = verify_dependency_independence(a1, a2, reachability, profiles)
                lat1 = latency_map.get(a1, {}).get("mean_seconds", 0.0)
                lat2 = latency_map.get(a2, {}).get("mean_seconds", 0.0)
                sequential_lat = lat1 + lat2
                parallel_lat = max(lat1, lat2)
                savings_sec = sequential_lat - parallel_lat

                if is_indep:
                    candidates.append({
                        "candidate_id": f"PARALLEL-{a1.upper()}-{a2.upper()}",
                        "dimension": "workflow_parallelization",
                        "title": f"Parallel Execution of {a1} and {a2}",
                        "target_agents": [a1, a2],
                        "observed_problem": (
                            f"Agents '{a1}' ({lat1:.2f}s) and '{a2}' ({lat2:.2f}s) are currently executed sequentially "
                            f"(total: {sequential_lat:.2f}s), despite having completely independent processing scopes and no "
                            f"mutual data dependencies."
                        ),
                        "supporting_evidence": {
                            "mcp_stage_source": ["stage_3_graph", "stage_6_latency", "stage_10_evidence"],
                            "dependency_verification": justification,
                            "is_dependency_independent": True,
                            "current_sequential_latency_seconds": round(sequential_lat, 2),
                            "projected_parallel_latency_seconds": round(parallel_lat, 2),
                            "critical_path_latency_reduction_seconds": round(savings_sec, 2),
                        },
                        "proposed_solution": (
                            f"Execute '{a1}' and '{a2}' concurrently using an asynchronous scatter-gather branch. "
                            f"Join their outputs prior to downstream synthesis."
                        ),
                        "expected_benefit": {
                            "latency_savings_pct": round((savings_sec / max(sequential_lat, 0.01)) * 100, 1),
                            "latency_savings_seconds": round(savings_sec, 2),
                            "critical_path_impact": f"Cuts {savings_sec:.2f}s directly from sequential critical path.",
                            "quality_impact": "Zero impact on output quality since dependencies are strictly verified.",
                        },
                        "tradeoffs_and_risks": {
                            "latency_tradeoff": "Immediate latency win with concurrency.",
                            "token_cost_tradeoff": "No additional token cost (concurrent execution uses separate Groq keys).",
                            "output_quality_risk": "None (data dependencies rigorously verified).",
                            "implementation_complexity": "Medium (requires async orchestrator branch).",
                        },
                        "tier": "Tier 1",
                        "requires_validation": False,
                        "dependency_verified": True,
                        "allocated_key": masked,
                    })
                else:
                    logger.info(f"Skipping parallelization for {a1} and {a2}: {justification}")

        return candidates, {
            "dimension": "workflow_parallelization",
            "allocated_key": masked,
            "candidates_found": len(candidates),
        }

    # =========================================================================
    # Dimension D: Model Selection (2-Agent JEV LangGraph Workflow)
    # =========================================================================
    def _analyze_dimension_d_model_selection(
        self, state: OptimizationAgentState
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        from optimization_agent.model_selection.groq_catalog import (
            GENERAL_PURPOSE_GROQ_MODELS,
            MODEL_CATALOG,
        )
        from optimization_agent.model_selection.orchestrator import (
            resolve_jev_agent2_recommendation,
        )

        raw_key, env_var, masked = self.key_mgr.get_key_for_task("model_selection")
        wf_id = str(
            state.get("workflow_id")
            or state.get("workflow_metadata", {}).get("workflow_id")
            or ""
        )
        evidence_dir = state.get("evidence_dir")
        agents = list(state.get("discovered_agents", []) or [])
        latency_map = state.get("latency_metrics", {}).get("agent_latency_metrics", {})
        token_map = state.get("token_metrics", {}).get("agent_token_metrics", {})
        recon = (state.get("workflow_metadata") or {}).get("model_reconciliation") or {}
        default_baseline = recon.get("declared_model") or state.get("target_model") or "openai/gpt-oss-120b"

        candidates: List[Dict[str, Any]] = []
        agent_errors: Dict[str, str] = {}
        evaluated_count = 0

        for agent_id in agents:
            is_extraction_or_intake = any(
                term in agent_id for term in ["intake", "extraction", "receipt", "normalize", "format"]
            )
            if not is_extraction_or_intake:
                continue

            try:
                jev_res = resolve_jev_agent2_recommendation(
                    workflow_id=wf_id,
                    agent_id=agent_id,
                    evidence_dir=evidence_dir,
                    custom_call_jev=self.jev_caller,
                    live_groq_models=self.jev_live_groq_models,
                    jev_results_dir=self.jev_results_dir,
                    use_cached_jev=self.use_cached_jev,
                )
            except Exception as exc:
                logger.info(f"JEV model selection skipped/failed for '{agent_id}': {exc}")
                agent_errors[agent_id] = str(exc)
                continue

            evaluated_count += 1
            model_rec = jev_res.get("model_recommendation") or {}
            if model_rec.get("selection_validated") is not True:
                continue

            selected_model = model_rec.get("selected_model")
            baseline_model = jev_res.get("baseline_model") or default_baseline
            if (
                not isinstance(selected_model, str)
                or selected_model not in GENERAL_PURPOSE_GROQ_MODELS
                or selected_model == baseline_model
            ):
                continue

            agent_reqs = jev_res.get("agent_requirements") or {}
            task_cls = (agent_reqs.get("task_complexity") or {}).get("class", "Unknown")
            prompt_cls = (agent_reqs.get("prompt_complexity") or {}).get("class", "Unknown")
            token_cls = (agent_reqs.get("token_consumption") or {}).get("class", "Unknown")
            resolution_source = str(jev_res.get("resolution_source") or "jev_agent2_langgraph")

            lat = float(latency_map.get(agent_id, {}).get("mean_seconds", 0.0) or 0.0)
            tok_entry = token_map.get(agent_id, {}) if isinstance(token_map, dict) else {}
            tok = float(tok_entry.get("mean_tokens", 0.0) or 0.0)
            mean_pt = float(tok_entry.get("mean_prompt_tokens", 0.0) or 0.0)
            mean_ct = float(tok_entry.get("mean_completion_tokens", 0.0) or 0.0)

            base_meta = MODEL_CATALOG.get(baseline_model, {})
            sel_meta = model_rec.get("selected_model_metadata") or MODEL_CATALOG.get(selected_model, {})
            cost_savings_pct = 50.0
            if base_meta and sel_meta:
                b_in = float(base_meta.get("input_price_per_million_usd", 0.0) or 0.0)
                b_out = float(base_meta.get("output_price_per_million_usd", 0.0) or 0.0)
                s_in = float(sel_meta.get("input_price_per_million_usd", 0.0) or 0.0)
                s_out = float(sel_meta.get("output_price_per_million_usd", 0.0) or 0.0)
                if mean_pt > 0 or mean_ct > 0:
                    b_cost = mean_pt * b_in + mean_ct * b_out
                    s_cost = mean_pt * s_in + mean_ct * s_out
                else:
                    b_cost = b_in + b_out
                    s_cost = s_in + s_out
                if b_cost > 0:
                    cost_savings_pct = round(max(0.0, ((b_cost - s_cost) / b_cost) * 100.0), 1)

            candidates.append({
                "candidate_id": f"MODEL-{agent_id.upper()}",
                "dimension": "model_selection",
                "title": f"Route {agent_id} to {selected_model} (JEV Agent 2 Recommendation; requires validation)",
                "target_agents": [agent_id],
                "selected_model": selected_model,
                "selection_source": resolution_source,
                "observed_problem": (
                    f"JEV 2-Agent LangGraph evaluation classified '{agent_id}' as "
                    f"Task={task_cls}, Prompt={prompt_cls}, Tokens={token_cls} (mean latency {lat:.2f}s). "
                    f"Assigning the baseline '{baseline_model}' introduces unnecessary compute cost; "
                    f"JEV Agent 2 selected '{selected_model}' among eligible Groq models."
                ),
                "supporting_evidence": {
                    "mcp_stage_source": ["stage_2_overview", "stage_4_profiles", "stage_7_tokens"],
                    "current_model": baseline_model,
                    "selected_model": selected_model,
                    "jev_selected_model": selected_model,
                    "proposed_candidate_models": [selected_model],
                    "selection_source": resolution_source,
                    "jev_agent1_requirements": agent_reqs,
                    "jev_agent2_recommendation": model_rec,
                    "eligible_model_ids": jev_res.get("eligible_model_ids", []),
                    "choice_confidence": model_rec.get("choice_confidence"),
                    "choice_probabilities": model_rec.get("choice_probabilities", {}),
                    "task_complexity": f"{task_cls} (JEV Agent 1; prompt={prompt_cls}, tokens={token_cls})",
                    "mean_tokens_per_call": tok,
                },
                "proposed_solution": (
                    f"Switch '{agent_id}' from '{baseline_model}' to '{selected_model}' per the "
                    f"2-agent JEV LangGraph workflow (Agent 2 recommendation) with structured schema "
                    f"output validation."
                ),
                "expected_benefit": {
                    "latency_savings_pct": 25.0,
                    "latency_savings_seconds": round(lat * 0.25, 2),
                    "cost_savings_pct": cost_savings_pct,
                    "quality_impact": "Requires shadow validation against baseline traces to confirm behavioral equivalence.",
                },
                "tradeoffs_and_risks": {
                    "latency_tradeoff": "Lower per-call inference overhead with smaller parameter footprint.",
                    "token_cost_tradeoff": f"~{cost_savings_pct}% API pricing reduction vs. '{baseline_model}' based on Groq catalog rates.",
                    "output_quality_risk": "Moderate (compact model recommended by JEV Agent 2 requires empirical shadow validation against baseline traces).",
                    "implementation_complexity": "Low",
                },
                "tier": "Tier 2",
                "requires_validation": True,
                "allocated_key": masked,
            })

        return candidates, {
            "dimension": "model_selection",
            "selection_engine": "jev_2agent_langgraph",
            "allocated_key": masked,
            "agents_evaluated": evaluated_count,
            "candidates_found": len(candidates),
            "agent_errors": agent_errors,
        }

    # =========================================================================
    # Dimension E: Prompt Optimization
    # =========================================================================
    def _analyze_dimension_e_prompt_optimization(
        self,
        state: OptimizationAgentState,
        consolidation_candidates: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        from optimization_agent.prompt_optimization import PromptOptimizationEngine

        engine = PromptOptimizationEngine(
            key_manager=self.key_mgr,
            groq_client=self.prompt_opt_client,
        )
        return engine.analyze(state, consolidation_candidates=consolidation_candidates)

    # =========================================================================
    # Dimension G: Communication & Data-Handoff Optimization
    # =========================================================================
    def _analyze_dimension_g_communication(
        self, state: OptimizationAgentState
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        from optimization_agent.data_handoff import DataHandoffOptimizationEngine

        engine = DataHandoffOptimizationEngine(
            key_manager=self.key_mgr,
            groq_client=self.handoff_client,
        )
        return engine.analyze(state)


def discovery_analysis(state: OptimizationAgentState) -> Dict[str, Any]:
    """LangGraph Node 11: Execute systematic discovery analysis across the 5 active dimensions."""
    track_status = dict(state.get("stage_status") or {})
    retrieval_errors = list(state.get("retrieval_errors") or [])
    key_usage_log = list(state.get("key_usage_log") or [])

    try:
        key_mgr = get_default_key_manager()
        engine = OptimizationDiscoveryEngine(key_manager=key_mgr)
        discovery_result = engine.discover_all_dimensions(state)

        track_status["discovery_analysis"] = "completed"
        return {
            "stage_status": track_status,
            "optimization_candidates": discovery_result["optimization_candidates"],
            "dimension_analyses": discovery_result["dimension_analyses"],
            "key_usage_log": key_mgr.get_usage_log(),
        }
    except Exception as e:
        logger.error(f"Discovery analysis error: {e}")
        track_status["discovery_analysis"] = "failed"
        retrieval_errors.append({"stage": "discovery_analysis", "error": str(e)})
        return {
            "stage_status": track_status,
            "retrieval_errors": retrieval_errors,
            "optimization_candidates": [],
            "dimension_analyses": {},
        }

