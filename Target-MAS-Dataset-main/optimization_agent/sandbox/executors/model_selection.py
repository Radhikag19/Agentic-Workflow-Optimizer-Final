"""
Executor C: Model Selection.
Updates the target agent's model configuration in the sandbox while preserving
provider, API key bindings, and schema contracts. Never hardcodes credentials.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from optimization_agent.model_selection.groq_catalog import MODEL_CATALOG
from optimization_agent.sandbox.executors.base import BaseOptimizationExecutor
from optimization_agent.sandbox.manager import SandboxEnvironment

SUPPORTED_GROQ_MODELS = set(MODEL_CATALOG.keys()) | {
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
}


class ModelSelectionExecutor(BaseOptimizationExecutor):
    """Applies approved model_selection candidates inside the sandbox."""

    dimension_name = "model_selection"

    @staticmethod
    def _resolve_proposed_model(candidate: Dict[str, Any]) -> Optional[str]:
        supp = candidate.get("supporting_evidence") or {}
        explicit = candidate.get("selected_model") or (
            supp.get("selected_model") if isinstance(supp, dict) else None
        )
        if isinstance(explicit, str) and explicit.strip():
            cand_id = explicit.strip()
            return cand_id if cand_id in SUPPORTED_GROQ_MODELS else None

        proposed_list = supp.get("proposed_candidate_models") if isinstance(supp, dict) else None
        if isinstance(proposed_list, list):
            for m in proposed_list:
                if isinstance(m, str) and m.strip() in SUPPORTED_GROQ_MODELS:
                    return m.strip()
        return None

    def execute(self, env: SandboxEnvironment, candidate: Dict[str, Any]) -> Dict[str, Any]:
        target_agents = [str(a) for a in (candidate.get("target_agents") or []) if str(a).strip()]
        if not target_agents:
            return self.make_result(
                candidate,
                status="requires_manual_intervention",
                description="Model selection candidate specifies no target_agents.",
                error="missing_target_agents",
            )

        proposed_model = self._resolve_proposed_model(candidate)
        if not proposed_model:
            return self.make_result(
                candidate,
                status="requires_manual_intervention",
                description="Proposed model is missing or not in supported Groq LLM catalog.",
                error="unsupported_or_missing_model",
            )

        wf_data = self.load_workflow_json(env)
        agents_by_id = {
            a.get("agent_id"): a
            for a in (wf_data.get("agents") or [])
            if isinstance(a, dict) and a.get("agent_id")
        }

        missing = [aid for aid in target_agents if aid not in agents_by_id]
        if missing:
            return self.make_result(
                candidate,
                status="requires_manual_intervention",
                description=f"Target agent(s) {missing} not found in sandbox workflow.json.",
                error="missing_agents_in_workflow_json",
            )

        provider = str(wf_data.get("llm_provider") or "Groq")
        key_env = wf_data.get("assigned_groq_key_env")
        overrides: Dict[str, Any] = dict(wf_data.get("agent_model_overrides") or {})
        cfg = self.load_sandbox_config(env)
        cfg_overrides: Dict[str, Any] = dict(cfg.get("model_overrides") or {})

        modified_files: List[str] = []
        transitions: Dict[str, Dict[str, str]] = {}

        for aid in target_agents:
            agent_entry = agents_by_id[aid]
            prev_model = str(
                agent_entry.get("model")
                or wf_data.get("baseline_model")
                or wf_data.get("fixed_model")
                or "openai/gpt-oss-120b"
            )
            agent_entry["model"] = proposed_model
            agent_entry["llm_provider"] = provider

            overrides[aid] = {
                "previous_model": prev_model,
                "updated_model": proposed_model,
                "provider": provider,
                "candidate_id": candidate.get("candidate_id"),
            }
            cfg_overrides[aid] = {
                "previous_model": prev_model,
                "updated_model": proposed_model,
                "provider": provider,
                "assigned_key_env": key_env,
                "candidate_id": candidate.get("candidate_id"),
            }
            transitions[aid] = {"previous_model": prev_model, "updated_model": proposed_model}

            agent_py = self.find_agent_source_file(env, aid)
            if agent_py is not None:
                self.upsert_module_constant(agent_py, env.sandbox_workflow_dir, "MODEL_OVERRIDE", proposed_model)
                rel_py = agent_py.relative_to(env.sandbox_workflow_dir).as_posix()
                if rel_py not in modified_files:
                    modified_files.append(rel_py)

        wf_data["agent_model_overrides"] = overrides
        wf_path = self.save_workflow_json(env, wf_data)
        modified_files.append(wf_path.relative_to(env.sandbox_workflow_dir).as_posix())

        cfg["model_overrides"] = cfg_overrides
        cfg.setdefault("applied_candidates", []).append(candidate.get("candidate_id"))
        cfg_path = self.save_sandbox_config(env, cfg)
        modified_files.append(cfg_path.relative_to(env.sandbox_workflow_dir).as_posix())

        return self.make_result(
            candidate,
            status="applied",
            modified_files=modified_files,
            description=(
                f"Updated model configuration for {target_agents} to '{proposed_model}' "
                f"(provider={provider}) in sandbox while preserving API key bindings."
            ),
            details={"model_transitions": transitions, "provider": provider},
        )
