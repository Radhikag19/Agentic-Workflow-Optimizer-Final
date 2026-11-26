"""
Executor C: Model Selection.
Updates the target agent's model configuration in the sandbox while preserving
provider, API key bindings, and schema contracts. Never hardcodes credentials.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from optimization_agent.model_selection.groq_catalog import (
    GENERAL_PURPOSE_GROQ_MODELS,
    MODEL_CATALOG,
)
from optimization_agent.model_selection.orchestrator import resolve_jev_agent2_recommendation
from optimization_agent.sandbox.executors.base import BaseOptimizationExecutor
from optimization_agent.sandbox.manager import SandboxEnvironment

SUPPORTED_GROQ_MODELS = set(GENERAL_PURPOSE_GROQ_MODELS)


class ModelSelectionExecutor(BaseOptimizationExecutor):
    """Applies approved model_selection candidates inside the sandbox using JEV Agent 2 models."""

    dimension_name = "model_selection"

    def __init__(
        self,
        jev_caller: Optional[Any] = None,
        jev_live_groq_models: Optional[Dict[str, Any]] = None,
        jev_results_dir: Optional[Any] = None,
        use_cached_jev: bool = True,
    ) -> None:
        super().__init__()
        self.jev_caller = jev_caller
        self.jev_live_groq_models = jev_live_groq_models
        self.jev_results_dir = jev_results_dir
        self.use_cached_jev = use_cached_jev

    @staticmethod
    def _extract_explicit_model_candidate(candidate: Dict[str, Any]) -> Optional[str]:
        supp = candidate.get("supporting_evidence") or {}
        jev_rec_top = candidate.get("jev_model_selection") or {}
        top_model_rec = candidate.get("model_recommendation") or {}
        jev_rec_supp = supp.get("jev_agent2_recommendation") if isinstance(supp, dict) else {}
        jev_bundle_supp = supp.get("jev_recommendation") if isinstance(supp, dict) else {}

        raw_values = [
            (jev_rec_top.get("model_recommendation") or {}).get("selected_model")
            if isinstance(jev_rec_top, dict)
            else None,
            top_model_rec.get("selected_model") if isinstance(top_model_rec, dict) else None,
            jev_rec_supp.get("selected_model") if isinstance(jev_rec_supp, dict) else None,
            (jev_bundle_supp.get("model_recommendation") or {}).get("selected_model")
            if isinstance(jev_bundle_supp, dict)
            else None,
            supp.get("jev_selected_model") if isinstance(supp, dict) else None,
            candidate.get("selected_model"),
            supp.get("selected_model") if isinstance(supp, dict) else None,
        ]
        for val in raw_values:
            if isinstance(val, str) and val.strip():
                return val.strip()
        return None

    @classmethod
    def _resolve_proposed_model(cls, candidate: Dict[str, Any]) -> Optional[str]:
        explicit = cls._extract_explicit_model_candidate(candidate)
        if explicit is not None:
            return explicit if explicit in SUPPORTED_GROQ_MODELS else None

        supp = candidate.get("supporting_evidence") or {}
        proposed_list = supp.get("proposed_candidate_models") if isinstance(supp, dict) else None
        if isinstance(proposed_list, list):
            for entry in proposed_list:
                raw_id = entry.get("model") if isinstance(entry, dict) else entry
                if isinstance(raw_id, str) and raw_id.strip() in SUPPORTED_GROQ_MODELS:
                    return raw_id.strip()
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

        explicit_raw = self._extract_explicit_model_candidate(candidate)
        if explicit_raw is not None and explicit_raw not in SUPPORTED_GROQ_MODELS:
            return self.make_result(
                candidate,
                status="requires_manual_intervention",
                description=(
                    f"Proposed model '{explicit_raw}' is not in supported general-purpose "
                    f"Groq MODEL_CATALOG ({sorted(SUPPORTED_GROQ_MODELS)})."
                ),
                error="unsupported_or_missing_model",
            )

        proposed_model = self._resolve_proposed_model(candidate)
        selection_source = candidate.get("selection_source") or (
            (candidate.get("supporting_evidence") or {}).get("selection_source")
            if isinstance(candidate.get("supporting_evidence"), dict)
            else None
        ) or "candidate_payload"
        jev_agent2_resolved: Optional[Dict[str, Any]] = None

        if not proposed_model:
            try:
                jev_res = resolve_jev_agent2_recommendation(
                    workflow_id=env.workflow_id,
                    agent_id=target_agents[0],
                    custom_call_jev=self.jev_caller,
                    live_groq_models=self.jev_live_groq_models,
                    jev_results_dir=self.jev_results_dir,
                    use_cached_jev=self.use_cached_jev,
                )
                rec = jev_res.get("model_recommendation") or {}
                jev_choice = rec.get("selected_model")
                if (
                    rec.get("selection_validated") is True
                    and isinstance(jev_choice, str)
                    and jev_choice.strip() in SUPPORTED_GROQ_MODELS
                ):
                    proposed_model = jev_choice.strip()
                    selection_source = str(jev_res.get("resolution_source") or "jev_agent2_langgraph")
                    jev_agent2_resolved = rec
            except Exception:
                proposed_model = None

        if not proposed_model:
            return self.make_result(
                candidate,
                status="requires_manual_intervention",
                description="Proposed model is missing or not in supported general-purpose Groq LLM catalog.",
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
                f"(provider={provider}, source={selection_source}) in sandbox while preserving API key bindings."
            ),
            details={
                "model_transitions": transitions,
                "provider": provider,
                "selection_source": selection_source,
                "jev_agent2_resolved": jev_agent2_resolved,
            },
        )
