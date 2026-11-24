"""
Code-Level & Configuration Validator for Sandbox Workflows.
Verifies original workflow integrity, Python syntax, config schemas, imports,
agent reference consistency, acyclic DAG dependency order, and secret hygiene.
"""

from __future__ import annotations

import ast
import json
from collections import deque
from typing import Any, Dict, List, Set

from optimization_agent.key_manager import get_default_key_manager
from optimization_agent.sandbox.executors.parallelization import _verify_sandbox_agents_independent
from optimization_agent.sandbox.manager import SandboxEnvironment, SandboxManager


def validate_sandbox(
    env: SandboxEnvironment,
    execution_results: Dict[str, Any],
) -> Dict[str, Any]:
    """Run all static code, config, DAG, modification, and isolation checks on the sandbox."""
    sb_dir = env.sandbox_workflow_dir
    key_mgr = get_default_key_manager()

    # 1. Original workflow unchanged
    orig_check = SandboxManager.verify_original_unchanged(env)

    # 2. Python syntax & 3. Import parse checks across all sandbox .py files
    syntax_errors: List[Dict[str, str]] = []
    import_warnings_or_errors: List[Dict[str, str]] = []
    py_files = sorted(sb_dir.glob("*.py"))

    for py_file in py_files:
        rel = py_file.relative_to(sb_dir).as_posix()
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
            # Check relative imports stay valid
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level and node.level > 2:
                    import_warnings_or_errors.append({
                        "file": rel,
                        "error": f"Excessive relative import level ({node.level}).",
                    })
        except SyntaxError as exc:
            syntax_errors.append({
                "file": rel,
                "error": f"Line {exc.lineno}: {exc.msg}",
            })
        except Exception as exc:
            syntax_errors.append({"file": rel, "error": str(exc)})

    # 4. Configuration schema checks & agent reference integrity
    config_errors: List[str] = []
    reference_errors: List[str] = []
    dependency_errors: List[str] = []

    wf_json_path = sb_dir / "workflow.json"
    cfg_json_path = sb_dir / "sandbox_optimization_config.json"

    wf_data: Dict[str, Any] = {}
    cfg_data: Dict[str, Any] = {}

    if not wf_json_path.exists():
        config_errors.append("Missing workflow.json in sandbox.")
    else:
        try:
            wf_data = json.loads(wf_json_path.read_text(encoding="utf-8"))
        except Exception as exc:
            config_errors.append(f"Invalid workflow.json JSON: {exc}")

    if not cfg_json_path.exists():
        config_errors.append("Missing sandbox_optimization_config.json in sandbox.")
    else:
        try:
            cfg_data = json.loads(cfg_json_path.read_text(encoding="utf-8"))
        except Exception as exc:
            config_errors.append(f"Invalid sandbox_optimization_config.json JSON: {exc}")

    if wf_data:
        agents = wf_data.get("agents") or []
        valid_agent_ids: Set[str] = {
            a.get("agent_id") for a in agents if isinstance(a, dict) and a.get("agent_id")
        }
        if not valid_agent_ids:
            config_errors.append("workflow.json defines zero agents.")

        # Collect consolidated-away obsolete IDs
        obsolete_ids: Set[str] = set()
        for cons in (cfg_data.get("consolidations") or []):
            for old_id in (cons.get("target_agents") or []):
                obsolete_ids.add(old_id)

        for order_key in ("execution_order", "baseline_execution_order"):
            order_list = wf_data.get(order_key) or []
            for aid in order_list:
                if aid not in valid_agent_ids:
                    reference_errors.append(
                        f"{order_key} references unknown or obsolete agent '{aid}'."
                    )
                if aid in obsolete_ids:
                    reference_errors.append(
                        f"Obsolete consolidated agent '{aid}' remains in {order_key}."
                    )

        # Dependency integrity & cycle check (Kahn's algorithm)
        indegree: Dict[str, int] = {aid: 0 for aid in valid_agent_ids}
        adj: Dict[str, List[str]] = {aid: [] for aid in valid_agent_ids}
        for ag in agents:
            aid = ag.get("agent_id")
            if not aid:
                continue
            for dep in ag.get("dependencies") or []:
                if dep not in valid_agent_ids:
                    reference_errors.append(
                        f"Agent '{aid}' depends on unknown or obsolete agent '{dep}'."
                    )
                else:
                    adj[dep].append(aid)
                    indegree[aid] += 1

        q = deque([aid for aid, deg in indegree.items() if deg == 0])
        visited = 0
        while q:
            cur = q.popleft()
            visited += 1
            for nxt in adj[cur]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    q.append(nxt)
        if visited != len(valid_agent_ids):
            dependency_errors.append("Cycle detected in sandbox workflow agent dependencies.")

        # Parallel groups independence re-verification
        for pgroup in wf_data.get("parallel_groups") or []:
            if isinstance(pgroup, list) and len(pgroup) >= 2:
                ok_indep, reason = _verify_sandbox_agents_independent(pgroup, wf_data)
                if not ok_indep:
                    dependency_errors.append(f"Parallel group {pgroup} invalid: {reason}")

        # Handoff projection endpoint check
        for edge_key in (wf_data.get("handoff_projections") or {}):
            if "->" not in edge_key:
                config_errors.append(f"Malformed handoff projection key '{edge_key}'.")
                continue
            prod, cons = edge_key.split("->", 1)
            if prod not in valid_agent_ids or cons not in valid_agent_ids:
                reference_errors.append(
                    f"Handoff projection '{edge_key}' references unknown agent."
                )

    # 5. Modification verification for applied candidates
    mod_errors: List[str] = []
    for res in execution_results.get("candidate_results") or []:
        if res.get("status") != "applied":
            continue
        mod_files = res.get("modified_files") or []
        if not mod_files:
            mod_errors.append(f"Candidate '{res.get('candidate_id')}' reported applied with no modified_files.")
        for rel_f in mod_files:
            if not (sb_dir / rel_f).exists():
                mod_errors.append(f"Expected modified sandbox file missing: '{rel_f}'.")

    # 6. Secret hygiene across sandbox files
    secret_leaks: List[str] = []
    for p in list(sb_dir.glob("*.py")) + list(sb_dir.glob("*.json")):
        try:
            if key_mgr.contains_raw_secrets(p.read_text(encoding="utf-8", errors="ignore")):
                secret_leaks.append(p.name)
        except Exception:
            pass

    validation_passed = (
        orig_check["original_unchanged"]
        and not syntax_errors
        and not import_warnings_or_errors
        and not config_errors
        and not reference_errors
        and not dependency_errors
        and not mod_errors
        and not secret_leaks
    )

    return {
        "validation_passed": validation_passed,
        "original_workflow_integrity": orig_check,
        "python_syntax_checks": {
            "passed": len(syntax_errors) == 0,
            "files_checked": len(py_files),
            "errors": syntax_errors,
        },
        "import_checks": {
            "passed": len(import_warnings_or_errors) == 0,
            "errors": import_warnings_or_errors,
        },
        "configuration_validation": {
            "passed": len(config_errors) == 0,
            "errors": config_errors,
        },
        "reference_integrity": {
            "passed": len(reference_errors) == 0,
            "errors": reference_errors,
        },
        "dependency_integrity": {
            "passed": len(dependency_errors) == 0,
            "errors": dependency_errors,
        },
        "modification_verification": {
            "passed": len(mod_errors) == 0,
            "errors": mod_errors,
        },
        "secret_hygiene": {
            "passed": len(secret_leaks) == 0,
            "leaked_files": secret_leaks,
        },
    }
