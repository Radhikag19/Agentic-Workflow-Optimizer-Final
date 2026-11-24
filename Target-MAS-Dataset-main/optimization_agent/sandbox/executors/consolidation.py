"""
Executor A: Agent Consolidation.
Merges approved sequential agent groups in the sandbox workflow while preserving
input/output schemas, dependencies, and unified prompts.
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List

from optimization_agent.sandbox.executors.base import BaseOptimizationExecutor
from optimization_agent.sandbox.manager import SandboxEnvironment, assert_path_inside_sandbox


class AgentConsolidationExecutor(BaseOptimizationExecutor):
    """Applies approved agent_consolidation candidates to the sandbox workflow."""

    dimension_name = "agent_consolidation"

    def execute(self, env: SandboxEnvironment, candidate: Dict[str, Any]) -> Dict[str, Any]:
        target_agents = [str(a) for a in (candidate.get("target_agents") or []) if str(a).strip()]
        if len(target_agents) < 2:
            return self.make_result(
                candidate,
                status="requires_manual_intervention",
                description="Consolidation candidate requires at least 2 target agents.",
                error="insufficient_target_agents",
            )

        supp = candidate.get("supporting_evidence") or {}
        comb_res = supp.get("groq_prompt_combination_result") if isinstance(supp, dict) else {}
        unified_prompt = (
            candidate.get("unified_prompt")
            or (comb_res.get("unified_prompt") if isinstance(comb_res, dict) else None)
        )
        if not isinstance(unified_prompt, str) or not unified_prompt.strip():
            return self.make_result(
                candidate,
                status="requires_manual_intervention",
                description="Approved consolidation candidate lacks a generated unified_prompt.",
                error="missing_unified_prompt",
            )

        wf_data = self.load_workflow_json(env)
        agents_list = list(wf_data.get("agents") or [])
        agents_by_id = {a.get("agent_id"): a for a in agents_list if isinstance(a, dict) and a.get("agent_id")}

        missing = [aid for aid in target_agents if aid not in agents_by_id]
        if missing:
            return self.make_result(
                candidate,
                status="requires_manual_intervention",
                description=f"Target agent(s) {missing} not found in sandbox workflow.json.",
                error="missing_agents_in_workflow_json",
            )

        first_id = target_agents[0]
        last_id = target_agents[-1]
        consolidated_id = f"consolidated_{first_id.replace('_agent', '')}_{last_id.replace('_agent', '')}"
        target_set = set(target_agents)

        # Preserve external inputs, terminal outputs, and external dependencies
        cons_resp = supp.get("consolidated_responsibilities") or {}
        merged_inputs: List[str] = []
        seen_in: set[str] = set()
        for aid in target_agents:
            for inp in agents_by_id[aid].get("input_fields") or []:
                if inp not in seen_in:
                    merged_inputs.append(inp)
                    seen_in.add(inp)

        merged_outputs = list(agents_by_id[last_id].get("output_fields") or [])
        merged_deps: List[str] = []
        seen_dep: set[str] = set()
        for aid in target_agents:
            for dep in agents_by_id[aid].get("dependencies") or []:
                if dep not in target_set and dep not in seen_dep:
                    merged_deps.append(dep)
                    seen_dep.add(dep)

        combined_role = (
            cons_resp.get("combined_role")
            or (comb_res.get("combined_role") if isinstance(comb_res, dict) else None)
            or " / ".join(str(agents_by_id[aid].get("role") or aid) for aid in target_agents)
        )
        combined_goal = (
            cons_resp.get("combined_goal")
            or (comb_res.get("combined_goal") if isinstance(comb_res, dict) else None)
            or unified_prompt[:300]
        )
        combined_resp = " ".join(
            str(agents_by_id[aid].get("responsibilities") or "").strip()
            for aid in target_agents
            if agents_by_id[aid].get("responsibilities")
        ).strip()

        new_agent_def = {
            "agent_id": consolidated_id,
            "agent_name": f"Consolidated {first_id}..{last_id}",
            "role": combined_role,
            "responsibilities": combined_resp,
            "goal": combined_goal,
            "unified_prompt": unified_prompt,
            "consolidated_from": target_agents,
            "input_fields": merged_inputs,
            "output_fields": merged_outputs,
            "dependencies": merged_deps,
            "model": wf_data.get("baseline_model", "openai/gpt-oss-120b"),
        }

        # Rebuild agents list & rewrite downstream references cleanly
        new_agents: List[Dict[str, Any]] = []
        inserted = False
        for ag in agents_list:
            aid = ag.get("agent_id")
            if aid in target_set:
                if not inserted:
                    new_agents.append(new_agent_def)
                    inserted = True
                continue
            updated_deps: List[str] = []
            for dep in ag.get("dependencies") or []:
                mapped_dep = consolidated_id if dep in target_set else dep
                if mapped_dep not in updated_deps:
                    updated_deps.append(mapped_dep)
            ag["dependencies"] = updated_deps
            new_agents.append(ag)

        wf_data["agents"] = new_agents
        wf_data["total_agents"] = len(new_agents)
        wf_data["agent_count"] = len(new_agents)

        for order_key in ("execution_order", "baseline_execution_order"):
            if isinstance(wf_data.get(order_key), list):
                new_order: List[str] = []
                ord_inserted = False
                for aid in wf_data[order_key]:
                    if aid in target_set:
                        if not ord_inserted:
                            new_order.append(consolidated_id)
                            ord_inserted = True
                    else:
                        new_order.append(aid)
                wf_data[order_key] = new_order

        wf_path = self.save_workflow_json(env, wf_data)

        # Write valid consolidated agent Python module in sandbox_workflow/
        cons_py_path = assert_path_inside_sandbox(
            env.sandbox_workflow_dir / f"{consolidated_id}.py",
            env.sandbox_workflow_dir,
        )
        module_src = (
            '"""Consolidated Agent Module generated by AWO Sandbox AgentConsolidationExecutor."""\n\n'
            f"AGENT_ID = {repr(consolidated_id)}\n"
            f"ROLE = {repr(combined_role)}\n"
            f"GOAL = {repr(combined_goal)}\n"
            f"CONSOLIDATED_FROM = {repr(target_agents)}\n"
            f"UNIFIED_PROMPT = {repr(unified_prompt)}\n"
        )
        ast.parse(module_src, filename=str(cons_py_path))
        cons_py_path.write_text(module_src, encoding="utf-8")

        cfg = self.load_sandbox_config(env)
        cfg.setdefault("consolidations", []).append({
            "candidate_id": candidate.get("candidate_id"),
            "consolidated_agent_id": consolidated_id,
            "target_agents": target_agents,
            "role": combined_role,
            "goal": combined_goal,
            "unified_prompt": unified_prompt,
            "input_fields": merged_inputs,
            "output_fields": merged_outputs,
            "dependencies": merged_deps,
        })
        cfg.setdefault("applied_candidates", []).append(candidate.get("candidate_id"))
        cfg_path = self.save_sandbox_config(env, cfg)

        modified_files = [
            wf_path.relative_to(env.sandbox_workflow_dir).as_posix(),
            cons_py_path.relative_to(env.sandbox_workflow_dir).as_posix(),
            cfg_path.relative_to(env.sandbox_workflow_dir).as_posix(),
        ]

        return self.make_result(
            candidate,
            status="applied",
            modified_files=modified_files,
            description=(
                f"Consolidated {target_agents} into '{consolidated_id}', rewired downstream "
                "dependencies, and persisted unified prompt inside sandbox."
            ),
            details={
                "consolidated_agent_id": consolidated_id,
                "merged_target_agents": target_agents,
                "preserved_inputs": merged_inputs,
                "preserved_outputs": merged_outputs,
                "preserved_dependencies": merged_deps,
            },
        )
