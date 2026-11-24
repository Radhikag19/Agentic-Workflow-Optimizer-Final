"""
Shared Base Executor & Utilities for Deterministic Sandbox Modification.
"""

from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from optimization_agent.sandbox.manager import SandboxEnvironment, assert_path_inside_sandbox


class BaseOptimizationExecutor:
    """Base helper providing sandbox-guarded JSON/AST/file operations for executors."""

    dimension_name: str = ""

    def load_workflow_json(self, env: SandboxEnvironment) -> Dict[str, Any]:
        wf_path = assert_path_inside_sandbox(
            env.sandbox_workflow_dir / "workflow.json",
            env.sandbox_workflow_dir,
        )
        if not wf_path.exists():
            raise FileNotFoundError(f"Sandbox workflow.json not found: {wf_path}")
        return json.loads(wf_path.read_text(encoding="utf-8"))

    def save_workflow_json(self, env: SandboxEnvironment, data: Dict[str, Any]) -> Path:
        wf_path = assert_path_inside_sandbox(
            env.sandbox_workflow_dir / "workflow.json",
            env.sandbox_workflow_dir,
        )
        wf_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return wf_path

    def load_sandbox_config(self, env: SandboxEnvironment) -> Dict[str, Any]:
        cfg_path = assert_path_inside_sandbox(
            env.sandbox_workflow_dir / "sandbox_optimization_config.json",
            env.sandbox_workflow_dir,
        )
        if not cfg_path.exists():
            return {
                "workflow_id": env.workflow_id,
                "experiment_id": env.experiment_id,
                "consolidations": [],
                "parallel_groups": [],
                "model_overrides": {},
                "prompt_overrides": {},
                "handoff_projections": {},
                "applied_candidates": [],
            }
        return json.loads(cfg_path.read_text(encoding="utf-8"))

    def save_sandbox_config(self, env: SandboxEnvironment, cfg: Dict[str, Any]) -> Path:
        cfg_path = assert_path_inside_sandbox(
            env.sandbox_workflow_dir / "sandbox_optimization_config.json",
            env.sandbox_workflow_dir,
        )
        cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        return cfg_path

    def find_agent_source_file(
        self,
        env: SandboxEnvironment,
        agent_id: str,
    ) -> Optional[Path]:
        """
        Locate an agent's Python source module inside sandbox_workflow/ via AST
        inspection of `AGENT_ID = "<agent_id>"`, falling back to filename matching.
        """
        sb_dir = env.sandbox_workflow_dir
        for py_file in sorted(sb_dir.glob("*.py")):
            if py_file.name in ("__init__.py", "workflow.py"):
                continue
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
                for node in tree.body:
                    if isinstance(node, ast.Assign):
                        for tgt in node.targets:
                            if isinstance(tgt, ast.Name) and tgt.id == "AGENT_ID":
                                val = ast.literal_eval(node.value)
                                if val == agent_id:
                                    return assert_path_inside_sandbox(py_file, sb_dir)
            except Exception:
                continue

        # Filename fallback (e.g. screening_review_agent -> review_agent.py)
        direct = sb_dir / f"{agent_id}.py"
        if direct.exists():
            return assert_path_inside_sandbox(direct, sb_dir)

        short_stem = agent_id.replace("_agent", "")
        for py_file in sorted(sb_dir.glob("*.py")):
            if short_stem and short_stem in py_file.stem:
                return assert_path_inside_sandbox(py_file, sb_dir)
        return None

    @staticmethod
    def extract_agent_ast_constants(py_path: Path) -> Dict[str, Any]:
        """Extract top-level literal constants (`ROLE`, `GOAL`, `BACKSTORY`, etc.) from an agent file."""
        info: Dict[str, Any] = {}
        try:
            tree = ast.parse(py_path.read_text(encoding="utf-8"), filename=str(py_path))
            for node in tree.body:
                if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                    name = node.targets[0].id
                    if name in ("AGENT_ID", "ROLE", "GOAL", "BACKSTORY", "OPTIMIZED_PROMPT", "MODEL_OVERRIDE", "UNIFIED_PROMPT"):
                        try:
                            info[name] = ast.literal_eval(node.value)
                        except Exception:
                            pass
        except Exception:
            pass
        return info

    @staticmethod
    def upsert_module_constant(
        py_path: Path,
        sandbox_dir: Path,
        const_name: str,
        value: Any,
    ) -> None:
        """
        Safely insert or update a module-level constant in a sandbox Python file
        without disturbing existing imports, functions, or docstrings.
        """
        target = assert_path_inside_sandbox(py_path, sandbox_dir)
        source = target.read_text(encoding="utf-8")
        lines = source.splitlines()
        marker = f"{const_name} = "
        replacement_line = f"{const_name} = {json.dumps(value, ensure_ascii=False)}"

        # Use repr() for multi-line / exact Python string safety
        replacement_line = f"{const_name} = {repr(value)}"

        updated = False
        new_lines: List[str] = []
        skip_multiline = False
        for ln in lines:
            if ln.startswith(marker):
                new_lines.append(replacement_line)
                updated = True
                # Handle rare triple-quoted multi-line literal if previously written
                if ln.count('"""') == 1 or ln.count("'''") == 1:
                    skip_multiline = True
                continue
            if skip_multiline:
                if '"""' in ln or "'''" in ln:
                    skip_multiline = False
                continue
            new_lines.append(ln)

        if not updated:
            new_lines.extend(["", f"# Applied by AWO Sandbox Executor", replacement_line])

        new_source = "\n".join(new_lines) + "\n"
        ast.parse(new_source, filename=str(target))
        target.write_text(new_source, encoding="utf-8")

    @staticmethod
    def make_result(
        candidate: Dict[str, Any],
        *,
        status: str,
        modified_files: Optional[List[str]] = None,
        description: str = "",
        details: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "candidate_id": candidate.get("candidate_id", "UNKNOWN"),
            "dimension": candidate.get("dimension", ""),
            "title": candidate.get("title", ""),
            "status": status,  # applied | failed | requires_manual_intervention | conflict
            "target_agents": list(candidate.get("target_agents") or []),
            "modified_files": list(modified_files or []),
            "description": description,
            "details": copy.deepcopy(details or {}),
            "supporting_evidence": copy.deepcopy(candidate.get("supporting_evidence") or {}),
            "expected_benefit": copy.deepcopy(candidate.get("expected_benefit") or {}),
            "requires_validation": bool(candidate.get("requires_validation", False)),
            "error": error,
        }

    def execute(self, env: SandboxEnvironment, candidate: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError
