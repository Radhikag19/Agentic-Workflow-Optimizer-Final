"""
Deterministic Candidate Router and Conflict Detector for Sandbox Optimization Execution.
Routes ONLY explicitly approved candidates to their dimension executors in deterministic
order and surfaces conflicting modifications rather than silently overwriting them.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Set, Tuple

from optimization_agent.sandbox.executors import (
    AgentConsolidationExecutor,
    BaseOptimizationExecutor,
    DataHandoffExecutor,
    ModelSelectionExecutor,
    ParallelizationExecutor,
    PromptOptimizationExecutor,
)
from optimization_agent.sandbox.manager import SandboxEnvironment

EXECUTOR_REGISTRY = {
    "agent_consolidation": AgentConsolidationExecutor,
    "workflow_parallelization": ParallelizationExecutor,
    "model_selection": ModelSelectionExecutor,
    "prompt_optimization": PromptOptimizationExecutor,
    "communication_data_handoff": DataHandoffExecutor,
}

DIMENSION_EXECUTION_ORDER: Tuple[str, ...] = (
    "agent_consolidation",
    "workflow_parallelization",
    "model_selection",
    "prompt_optimization",
    "communication_data_handoff",
)


def _canonical_dimension(raw_dim: Optional[str]) -> str:
    cleaned = str(raw_dim or "").strip()
    if cleaned == "communication_optimization":
        return "communication_data_handoff"
    return cleaned


def detect_conflicts(approved_candidates: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """
    Detect conflicting modifications across approved candidates before execution.
    Returns (conflict_records, conflicting_candidate_id -> reason).
    Never silently drops or overwrites conflicting proposals.
    """
    conflicts: List[Dict[str, Any]] = []
    conflicting_reasons: Dict[str, str] = {}

    def _flag_pair(cid_a: str, cid_b: str, reason: str, conflict_type: str) -> None:
        conflicts.append({
            "conflict_type": conflict_type,
            "candidate_ids": [cid_a, cid_b],
            "reason": reason,
            "resolution_required": True,
        })
        conflicting_reasons.setdefault(cid_a, reason)
        conflicting_reasons.setdefault(cid_b, reason)

    consolidated_agents: Dict[str, str] = {}  # agent_id -> cons_cid
    model_targets: Dict[str, Tuple[str, str]] = {}  # agent_id -> (cid, model_spec)
    prompt_targets: Dict[str, str] = {}  # agent_id -> cid
    handoff_edges: Dict[str, str] = {}  # "producer->consumer" -> cid

    # Check within agent_consolidation first
    for cand in approved_candidates:
        cid = str(cand.get("candidate_id") or "")
        dim = _canonical_dimension(cand.get("dimension"))
        targets = [str(a) for a in (cand.get("target_agents") or []) if str(a).strip()]

        if dim == "agent_consolidation":
            for aid in targets:
                if aid in consolidated_agents:
                    other = consolidated_agents[aid]
                    _flag_pair(
                        other,
                        cid,
                        f"Overlapping agent consolidation target '{aid}' across {other} and {cid}.",
                        "overlapping_consolidation",
                    )
                else:
                    consolidated_agents[aid] = cid

    # Check intra-dimension and consolidation-vs-downstream conflicts
    for cand in approved_candidates:
        cid = str(cand.get("candidate_id") or "")
        dim = _canonical_dimension(cand.get("dimension"))
        targets = [str(a) for a in (cand.get("target_agents") or []) if str(a).strip()]
        supp = cand.get("supporting_evidence") or {}

        if dim in ("workflow_parallelization", "model_selection", "prompt_optimization"):
            for aid in targets:
                if aid in consolidated_agents:
                    cons_cid = consolidated_agents[aid]
                    _flag_pair(
                        cons_cid,
                        cid,
                        f"Agent '{aid}' is targeted by consolidation '{cons_cid}' and {dim} '{cid}'.",
                        "consolidation_target_conflict",
                    )

        if dim == "model_selection":
            proposed = str(ModelSelectionExecutor._resolve_proposed_model(cand) or "")
            for aid in targets:
                if aid in model_targets:
                    prev_cid, prev_model = model_targets[aid]
                    if prev_cid != cid:
                        _flag_pair(
                            prev_cid,
                            cid,
                            f"Multiple model_selection candidates target agent '{aid}' ({prev_model} vs {proposed}).",
                            "duplicate_model_override",
                        )
                else:
                    model_targets[aid] = (cid, proposed)

        elif dim == "prompt_optimization":
            for aid in targets:
                if aid in prompt_targets and prompt_targets[aid] != cid:
                    prev_cid = prompt_targets[aid]
                    _flag_pair(
                        prev_cid,
                        cid,
                        f"Multiple prompt_optimization candidates target agent '{aid}' ({prev_cid} and {cid}).",
                        "duplicate_prompt_override",
                    )
                else:
                    prompt_targets[aid] = cid

        elif dim == "communication_data_handoff":
            prod = supp.get("producer_agent") or (targets[0] if len(targets) >= 1 else None)
            cons = supp.get("consumer_agent") or (targets[1] if len(targets) >= 2 else None)
            if prod and cons:
                edge_key = f"{prod}->{cons}"
                if edge_key in handoff_edges and handoff_edges[edge_key] != cid:
                    prev_cid = handoff_edges[edge_key]
                    _flag_pair(
                        prev_cid,
                        cid,
                        f"Multiple communication_data_handoff candidates modify edge '{edge_key}'.",
                        "duplicate_handoff_edge",
                    )
                else:
                    handoff_edges[edge_key] = cid

    return conflicts, conflicting_reasons


class CandidateExecutionRouter:
    """Deterministic router dispatching approved candidates across the 5 dimension executors."""

    def __init__(self, registry: Optional[Dict[str, type]] = None):
        self.registry = dict(registry or EXECUTOR_REGISTRY)

    def execute_approved_candidates(
        self,
        env: SandboxEnvironment,
    ) -> Dict[str, Any]:
        scope = env.approved_scope
        approved_ids = list(scope.get("approved_candidate_ids") or [])
        approved_id_set = set(approved_ids)

        # Strictly reject/ignore any unapproved candidates
        candidates: List[Dict[str, Any]] = [
            copy.deepcopy(c)
            for c in (scope.get("approved_candidates") or [])
            if isinstance(c, dict) and c.get("candidate_id") in approved_id_set
        ]

        # Deterministic dimension ordering preserving intra-dimension approval order
        order_idx = {dim: i for i, dim in enumerate(DIMENSION_EXECUTION_ORDER)}
        ordered_candidates = sorted(
            candidates,
            key=lambda c: order_idx.get(_canonical_dimension(c.get("dimension")), 99),
        )

        conflicts, conflicting_reasons = detect_conflicts(ordered_candidates)

        results: List[Dict[str, Any]] = []
        applied_ids: List[str] = []
        failed_ids: List[str] = []
        manual_ids: List[str] = []
        conflicting_ids: List[str] = []
        modified_files_set: Set[str] = set()

        for cand in ordered_candidates:
            cid = str(cand.get("candidate_id") or "")
            raw_dim = str(cand.get("dimension") or "")
            canon_dim = _canonical_dimension(raw_dim)

            if cid in conflicting_reasons:
                reason = conflicting_reasons[cid]
                res = BaseOptimizationExecutor.make_result(
                    cand,
                    status="conflict",
                    description=f"Skipped due to detected modification conflict: {reason}",
                    error=reason,
                )
                results.append(res)
                conflicting_ids.append(cid)
                continue

            exec_cls = self.registry.get(canon_dim)
            if exec_cls is None:
                res = BaseOptimizationExecutor.make_result(
                    cand,
                    status="failed",
                    description=f"No executor registered for dimension '{raw_dim}'.",
                    error=f"unregistered_dimension:{raw_dim}",
                )
                results.append(res)
                failed_ids.append(cid)
                continue

            executor: BaseOptimizationExecutor = exec_cls()
            try:
                res = executor.execute(env, cand)
            except Exception as exc:
                res = BaseOptimizationExecutor.make_result(
                    cand,
                    status="failed",
                    description=f"Executor error while applying '{cid}': {exc}",
                    error=str(exc),
                )

            results.append(res)
            status = res.get("status")
            if status == "applied":
                applied_ids.append(cid)
                modified_files_set.update(res.get("modified_files") or [])
            elif status == "requires_manual_intervention":
                manual_ids.append(cid)
            elif status == "conflict":
                conflicting_ids.append(cid)
            else:
                failed_ids.append(cid)

        return {
            "workflow_id": env.workflow_id,
            "experiment_id": env.experiment_id,
            "approved_candidate_ids": approved_ids,
            "applied_candidate_ids": applied_ids,
            "failed_candidate_ids": failed_ids,
            "manual_intervention_candidate_ids": manual_ids,
            "conflicting_candidate_ids": conflicting_ids,
            "modified_files": sorted(modified_files_set),
            "conflicts": conflicts,
            "candidate_results": results,
            "modification_applied": len(applied_ids) > 0,
        }
