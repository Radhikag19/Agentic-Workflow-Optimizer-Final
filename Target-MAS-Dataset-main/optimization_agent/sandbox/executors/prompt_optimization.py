"""
Executor D: Prompt Optimization.
Applies approved prompt compression updates strictly to the target agent inside
the sandbox while recording original vs. optimized prompts.
"""

from __future__ import annotations

from typing import Any, Dict, List

from optimization_agent.sandbox.executors.base import BaseOptimizationExecutor
from optimization_agent.sandbox.manager import SandboxEnvironment


class PromptOptimizationExecutor(BaseOptimizationExecutor):
    """Applies approved prompt_optimization candidates inside the sandbox."""

    dimension_name = "prompt_optimization"

    def execute(self, env: SandboxEnvironment, candidate: Dict[str, Any]) -> Dict[str, Any]:
        target_agents = [str(a) for a in (candidate.get("target_agents") or []) if str(a).strip()]
        if not target_agents:
            return self.make_result(
                candidate,
                status="requires_manual_intervention",
                description="Prompt optimization candidate specifies no target_agents.",
                error="missing_target_agents",
            )

        supp = candidate.get("supporting_evidence") or {}
        optimized_prompt = (
            candidate.get("optimized_prompt")
            or (supp.get("optimized_prompt") if isinstance(supp, dict) else None)
        )
        if not isinstance(optimized_prompt, str) or not optimized_prompt.strip():
            return self.make_result(
                candidate,
                status="requires_manual_intervention",
                description="Approved prompt_optimization candidate has no optimized_prompt payload.",
                error="missing_optimized_prompt",
            )

        wf_data = self.load_workflow_json(env)
        agents_by_id = {
            a.get("agent_id"): a
            for a in (wf_data.get("agents") or [])
            if isinstance(a, dict) and a.get("agent_id")
        }

        cfg = self.load_sandbox_config(env)
        prompt_overrides: Dict[str, Any] = dict(cfg.get("prompt_overrides") or {})
        modified_files: List[str] = []
        recorded_prompts: Dict[str, Dict[str, Any]] = {}

        for aid in target_agents:
            agent_py = self.find_agent_source_file(env, aid)
            if agent_py is None:
                return self.make_result(
                    candidate,
                    status="requires_manual_intervention",
                    description=f"Source Python file for target agent '{aid}' not found in sandbox.",
                    error="agent_source_not_found",
                )

            constants = self.extract_agent_ast_constants(agent_py)
            orig_prompt = (
                (supp.get("original_prompt") if isinstance(supp, dict) else None)
                or "\n".join(
                    p for p in [constants.get("GOAL"), constants.get("BACKSTORY")] if isinstance(p, str) and p
                )
                or constants.get("ROLE", "")
            )

            self.upsert_module_constant(agent_py, env.sandbox_workflow_dir, "OPTIMIZED_PROMPT", optimized_prompt)
            rel_py = agent_py.relative_to(env.sandbox_workflow_dir).as_posix()
            if rel_py not in modified_files:
                modified_files.append(rel_py)

            if aid in agents_by_id:
                agents_by_id[aid]["optimized_prompt"] = optimized_prompt

            record = {
                "candidate_id": candidate.get("candidate_id"),
                "original_prompt_preview": str(orig_prompt)[:500],
                "original_prompt_char_length": len(str(orig_prompt)),
                "optimized_prompt": optimized_prompt,
                "optimized_prompt_char_length": len(optimized_prompt),
            }
            prompt_overrides[aid] = record
            recorded_prompts[aid] = record

        wf_path = self.save_workflow_json(env, wf_data)
        modified_files.append(wf_path.relative_to(env.sandbox_workflow_dir).as_posix())

        cfg["prompt_overrides"] = prompt_overrides
        cfg.setdefault("applied_candidates", []).append(candidate.get("candidate_id"))
        cfg_path = self.save_sandbox_config(env, cfg)
        modified_files.append(cfg_path.relative_to(env.sandbox_workflow_dir).as_posix())

        return self.make_result(
            candidate,
            status="applied",
            modified_files=modified_files,
            description=f"Applied OPTIMIZED_PROMPT exclusively to {target_agents} inside sandbox.",
            details={"prompt_updates": recorded_prompts},
        )
