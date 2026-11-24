"""
Executor E: Communication & Data-Handoff Optimization.
Applies compact field projection strictly to approved `(producer_agent, consumer_agent)`
edges without altering unapproved handoffs or dropping consumer-required fields.
"""

from __future__ import annotations

import ast
from typing import Any, Dict

from optimization_agent.sandbox.executors.base import BaseOptimizationExecutor
from optimization_agent.sandbox.manager import SandboxEnvironment, assert_path_inside_sandbox


class DataHandoffExecutor(BaseOptimizationExecutor):
    """Applies approved communication_data_handoff candidates inside the sandbox."""

    dimension_name = "communication_data_handoff"

    def execute(self, env: SandboxEnvironment, candidate: Dict[str, Any]) -> Dict[str, Any]:
        supp = candidate.get("supporting_evidence") or {}
        schema = candidate.get("proposed_compact_payload_schema") or {}
        target_agents = list(candidate.get("target_agents") or [])

        producer = supp.get("producer_agent") or (target_agents[0] if len(target_agents) >= 1 else None)
        consumer = supp.get("consumer_agent") or (target_agents[1] if len(target_agents) >= 2 else None)
        if not producer or not consumer:
            return self.make_result(
                candidate,
                status="requires_manual_intervention",
                description="Handoff candidate lacks explicit producer_agent or consumer_agent.",
                error="missing_handoff_endpoints",
            )

        retained_fields = list(
            schema.get("retained_fields")
            or supp.get("fields_retained")
            or []
        )
        excluded_fields = list(
            schema.get("excluded_fields")
            or supp.get("fields_excluded")
            or []
        )
        required_fields = list(supp.get("consumer_required_fields") or [])

        if not retained_fields:
            return self.make_result(
                candidate,
                status="requires_manual_intervention",
                description=f"Handoff '{producer} -> {consumer}' has no retained_fields schema.",
                error="missing_retained_fields",
            )

        missing_required = [f for f in required_fields if f not in set(retained_fields)]
        if missing_required:
            return self.make_result(
                candidate,
                status="requires_manual_intervention",
                description=(
                    f"Proposed compact schema drops required consumer field(s) {missing_required} "
                    f"on handoff '{producer} -> {consumer}'."
                ),
                error="required_consumer_fields_dropped",
            )

        wf_data = self.load_workflow_json(env)
        agents_by_id = {
            a.get("agent_id"): a
            for a in (wf_data.get("agents") or [])
            if isinstance(a, dict) and a.get("agent_id")
        }
        if producer not in agents_by_id or consumer not in agents_by_id:
            return self.make_result(
                candidate,
                status="requires_manual_intervention",
                description=f"Endpoint '{producer}' or '{consumer}' missing from sandbox workflow.json.",
                error="missing_agents_in_workflow_json",
            )

        edge_key = f"{producer}->{consumer}"
        projection_spec = {
            "candidate_id": candidate.get("candidate_id"),
            "producer_agent": producer,
            "consumer_agent": consumer,
            "retained_fields": retained_fields,
            "excluded_fields": excluded_fields,
            "consumer_required_fields": required_fields,
            "typed_delta_projection": bool(schema.get("typed_delta_projection", True)),
        }

        wf_projections: Dict[str, Any] = dict(wf_data.get("handoff_projections") or {})
        wf_projections[edge_key] = projection_spec
        wf_data["handoff_projections"] = wf_projections
        wf_path = self.save_workflow_json(env, wf_data)
        modified_files = [wf_path.relative_to(env.sandbox_workflow_dir).as_posix()]

        # Inject non-breaking handoff projection table/helper into sandbox workflow.py if present
        wf_py = env.sandbox_workflow_dir / "workflow.py"
        if wf_py.exists():
            safe_wf_py = assert_path_inside_sandbox(wf_py, env.sandbox_workflow_dir)
            self.upsert_module_constant(safe_wf_py, env.sandbox_workflow_dir, "HANDOFF_PROJECTIONS", wf_projections)
            src = safe_wf_py.read_text(encoding="utf-8")
            if "def project_handoff_payload(" not in src:
                helper_src = (
                    "\ndef project_handoff_payload(producer, consumer, payload):\n"
                    '    """Project approved compact fields on configured edges; pass through unapproved edges unchanged."""\n'
                    "    if not isinstance(payload, dict):\n"
                    "        return payload\n"
                    "    spec = HANDOFF_PROJECTIONS.get(f'{producer}->{consumer}')\n"
                    "    if not spec:\n"
                    "        return payload\n"
                    "    retained = set(spec.get('retained_fields') or [])\n"
                    "    return {k: v for k, v in payload.items() if k in retained}\n"
                )
                updated_src = src.rstrip() + "\n" + helper_src
                ast.parse(updated_src, filename=str(safe_wf_py))
                safe_wf_py.write_text(updated_src, encoding="utf-8")
            modified_files.append(safe_wf_py.relative_to(env.sandbox_workflow_dir).as_posix())

        cfg = self.load_sandbox_config(env)
        cfg_projections: Dict[str, Any] = dict(cfg.get("handoff_projections") or {})
        cfg_projections[edge_key] = projection_spec
        cfg["handoff_projections"] = cfg_projections
        cfg.setdefault("applied_candidates", []).append(candidate.get("candidate_id"))
        cfg_path = self.save_sandbox_config(env, cfg)
        modified_files.append(cfg_path.relative_to(env.sandbox_workflow_dir).as_posix())

        return self.make_result(
            candidate,
            status="applied",
            modified_files=modified_files,
            description=(
                f"Configured compact handoff projection on '{edge_key}' retaining "
                f"{len(retained_fields)} field(s) and excluding {excluded_fields}."
            ),
            details=projection_spec,
        )
