"""
Executor B: Workflow Parallelization.
Modifies sandbox workflow orchestration so strictly independent verified agents run concurrently.
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Set, Tuple

from optimization_agent.sandbox.executors.base import BaseOptimizationExecutor
from optimization_agent.sandbox.manager import SandboxEnvironment, assert_path_inside_sandbox


def _verify_sandbox_agents_independent(
    agent_ids: List[str],
    wf_data: Dict[str, Any],
) -> Tuple[bool, str]:
    """Verify mutual DAG & I/O independence of `agent_ids` in `workflow.json`."""
    agents_by_id = {
        a.get("agent_id"): a
        for a in (wf_data.get("agents") or [])
        if isinstance(a, dict) and a.get("agent_id")
    }
    for aid in agent_ids:
        if aid not in agents_by_id:
            return False, f"Agent '{aid}' not found in sandbox workflow.json."

    # Build downstream reachability map (producer -> transitive consumers)
    downstream: Dict[str, Set[str]] = {aid: set() for aid in agents_by_id}
    for aid, info in agents_by_id.items():
        for dep in info.get("dependencies") or []:
            if dep in downstream:
                downstream[dep].add(aid)

    def _reachable(start: str) -> Set[str]:
        seen: Set[str] = set()
        stack = list(downstream.get(start, set()))
        while stack:
            cur = stack.pop()
            if cur not in seen:
                seen.add(cur)
                stack.extend(downstream.get(cur, set()))
        return seen

    reach_map = {aid: _reachable(aid) for aid in agents_by_id}

    for i in range(len(agent_ids)):
        for j in range(i + 1, len(agent_ids)):
            a, b = agent_ids[i], agent_ids[j]
            if b in reach_map.get(a, set()):
                return False, f"Direct or transitive dependency detected: {a} -> ... -> {b}"
            if a in reach_map.get(b, set()):
                return False, f"Direct or transitive dependency detected: {b} -> ... -> {a}"

            a_outs = set(agents_by_id[a].get("output_fields") or [])
            b_ins = set(agents_by_id[b].get("input_fields") or [])
            b_outs = set(agents_by_id[b].get("output_fields") or [])
            a_ins = set(agents_by_id[a].get("input_fields") or [])
            if a_outs.intersection(b_ins) or b_outs.intersection(a_ins):
                return False, f"Data I/O overlap between '{a}' and '{b}' prevents safe parallelization."

    return True, f"Verified mutually independent in sandbox DAG: {agent_ids}"


class ParallelizationExecutor(BaseOptimizationExecutor):
    """Applies approved workflow_parallelization candidates inside the sandbox."""

    dimension_name = "workflow_parallelization"

    def execute(self, env: SandboxEnvironment, candidate: Dict[str, Any]) -> Dict[str, Any]:
        target_agents = [str(a) for a in (candidate.get("target_agents") or []) if str(a).strip()]
        if len(target_agents) < 2:
            return self.make_result(
                candidate,
                status="requires_manual_intervention",
                description="Parallelization candidate requires at least 2 target agents.",
                error="insufficient_target_agents",
            )

        wf_data = self.load_workflow_json(env)
        is_indep, reason = _verify_sandbox_agents_independent(target_agents, wf_data)
        if not is_indep:
            return self.make_result(
                candidate,
                status="failed",
                description=f"Refused unsafe parallelization: {reason}",
                error=reason,
            )

        groups: List[List[str]] = list(wf_data.get("parallel_groups") or [])
        if target_agents not in groups:
            groups.append(target_agents)
        wf_data["parallel_groups"] = groups
        wf_data["execution_pattern"] = "dag_parallel"
        wf_path = self.save_workflow_json(env, wf_data)

        modified_files = [wf_path.relative_to(env.sandbox_workflow_dir).as_posix()]

        # Inject non-breaking concurrent helper metadata into sandbox workflow.py if present
        wf_py = env.sandbox_workflow_dir / "workflow.py"
        if wf_py.exists():
            safe_wf_py = assert_path_inside_sandbox(wf_py, env.sandbox_workflow_dir)
            self.upsert_module_constant(safe_wf_py, env.sandbox_workflow_dir, "PARALLEL_GROUPS", groups)
            src = safe_wf_py.read_text(encoding="utf-8")
            if "def run_parallel_group(" not in src:
                helper_src = (
                    "\nfrom concurrent.futures import ThreadPoolExecutor as _AWOThreadPoolExecutor\n\n"
                    "def run_parallel_group(tasks_map):\n"
                    '    """Execute independent agent callables concurrently and synchronize outputs."""\n'
                    "    with _AWOThreadPoolExecutor(max_workers=max(1, len(tasks_map))) as pool:\n"
                    "        futures = {name: pool.submit(fn) for name, fn in tasks_map.items()}\n"
                    "        return {name: fut.result() for name, fut in futures.items()}\n"
                )
                updated_src = src.rstrip() + "\n" + helper_src
                ast.parse(updated_src, filename=str(safe_wf_py))
                safe_wf_py.write_text(updated_src, encoding="utf-8")
            modified_files.append(safe_wf_py.relative_to(env.sandbox_workflow_dir).as_posix())

        cfg = self.load_sandbox_config(env)
        cfg.setdefault("parallel_groups", []).append({
            "candidate_id": candidate.get("candidate_id"),
            "agents": target_agents,
            "verification_reason": reason,
        })
        cfg.setdefault("applied_candidates", []).append(candidate.get("candidate_id"))
        cfg_path = self.save_sandbox_config(env, cfg)
        modified_files.append(cfg_path.relative_to(env.sandbox_workflow_dir).as_posix())

        return self.make_result(
            candidate,
            status="applied",
            modified_files=modified_files,
            description=(
                f"Configured concurrent scatter-gather group {target_agents} in sandbox workflow "
                "after verifying strict DAG & I/O independence."
            ),
            details={
                "parallel_group": target_agents,
                "dependency_verification": reason,
            },
        )
