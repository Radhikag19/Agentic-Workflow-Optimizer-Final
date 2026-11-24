"""
Static AST Metadata Extractor for Target MAS Agents.
Supports Pattern A (module constants + run_*), Pattern B (Agent/Task factories),
and Pattern C (workflow.py agent_span Task blocks) without executing any user code.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict, List, Optional

_HELPER_FUNC_PREFIXES = (
    "deterministic_",
    "calculate_",
    "query_",
    "compute_",
    "check_",
    "match_",
    "lookup_",
    "score_",
)


def ast_expr_to_text(node: Optional[ast.AST]) -> str:
    """Extract readable static text from string literals, binary concats, and f-strings."""
    if node is None:
        return ""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts: List[str] = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append(v.value)
            elif isinstance(v, ast.FormattedValue):
                try:
                    parts.append("{" + ast.unparse(v.value) + "}")
                except Exception:
                    parts.append("{...}")
        return "".join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return ast_expr_to_text(node.left) + ast_expr_to_text(node.right)
    if isinstance(node, ast.Tuple):
        return "".join(ast_expr_to_text(e) for e in node.elts)
    return ""


def normalize_responsibilities(raw: Any) -> List[str]:
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    return []


def _extract_workflow_span_prompts(tree: ast.AST) -> Dict[str, str]:
    """Extract Pattern C Task descriptions wrapped inside `with agent_span("<agent_id>", ...)`."""
    prompts: Dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.With):
            continue
        span_aid: Optional[str] = None
        for item in node.items:
            ctx = item.context_expr
            if isinstance(ctx, ast.Call) and isinstance(ctx.func, ast.Name) and ctx.func.id == "agent_span":
                if ctx.args and isinstance(ctx.args[0], ast.Constant) and isinstance(ctx.args[0].value, str):
                    span_aid = ctx.args[0].value
        if not span_aid:
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id == "Task":
                for kw in sub.keywords:
                    if kw.arg == "description":
                        txt = ast_expr_to_text(kw.value).strip()
                        if txt:
                            prompts[span_aid] = txt
    return prompts


def _parse_single_agent_file(pf: Path, ast_helper: Any) -> Optional[Dict[str, Any]]:
    try:
        tree = ast.parse(pf.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None

    consts = ast_helper.extract_agent_ast_constants(pf)
    role = str(consts.get("ROLE") or "")
    goal = str(consts.get("GOAL") or "")
    backstory = str(consts.get("BACKSTORY") or "")
    task_desc = ""
    helpers: List[str] = []
    aliases: List[str] = [pf.stem]
    if consts.get("AGENT_ID"):
        aliases.insert(0, str(consts["AGENT_ID"]))

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            fn = node.name
            if fn.startswith(_HELPER_FUNC_PREFIXES):
                helpers.append(fn)
            elif fn.startswith("create_") and fn.endswith("_agent"):
                aliases.append(fn[len("create_"):])

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "Agent":
                for kw in node.keywords:
                    val = ast_expr_to_text(kw.value).strip()
                    if kw.arg == "role" and not role:
                        role = val
                    elif kw.arg == "goal" and not goal:
                        goal = val
                    elif kw.arg == "backstory" and not backstory:
                        backstory = val
            elif node.func.id == "Task" and not task_desc:
                for kw in node.keywords:
                    if kw.arg == "description":
                        task_desc = ast_expr_to_text(kw.value).strip()
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id in ("task_desc", "description"):
                    cand_t = ast_expr_to_text(node.value).strip()
                    if len(cand_t) > len(task_desc):
                        task_desc = cand_t

    return {
        "stem": pf.stem,
        "aliases": aliases,
        "role": role,
        "goal": goal,
        "backstory": backstory,
        "task_desc": task_desc,
        "helpers": helpers,
    }


def _match_agent_file(aid: str, parsed_files: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for pf_info in parsed_files:
        if aid in pf_info["aliases"]:
            return pf_info
    for pf_info in parsed_files:
        stem = pf_info["stem"]
        core = stem.replace("_agent", "")
        if aid.endswith(stem) or aid.startswith(stem) or (core and core in aid):
            return pf_info
    for pf_info in parsed_files:
        tokens = [t for t in pf_info["stem"].replace("_agent", "").split("_") if t]
        if tokens and all(t in aid for t in tokens):
            return pf_info
    return None


def extract_workflow_agent_metadata(
    wf_dir: Path,
    wf_data: Dict[str, Any],
    ast_helper: Any,
) -> Dict[str, Dict[str, Any]]:
    """Extract role, goal, backstory, task prompt preview, and helper functions for every agent."""
    parsed_files: List[Dict[str, Any]] = []
    wf_task_prompts: Dict[str, str] = {}

    for pf in sorted(wf_dir.glob("*.py")):
        if pf.name == "__init__.py":
            continue
        if pf.name == "workflow.py":
            try:
                wf_tree = ast.parse(pf.read_text(encoding="utf-8", errors="replace"))
                wf_task_prompts = _extract_workflow_span_prompts(wf_tree)
            except Exception:
                wf_task_prompts = {}
            continue
        info = _parse_single_agent_file(pf, ast_helper)
        if info is not None:
            parsed_files.append(info)

    result: Dict[str, Dict[str, Any]] = {}
    for ag in wf_data.get("agents") or []:
        if not isinstance(ag, dict):
            continue
        aid_raw = ag.get("agent_id") or ag.get("id")
        if not aid_raw:
            continue
        aid = str(aid_raw)
        matched = _match_agent_file(aid, parsed_files) or {}
        result[aid] = {
            "role": matched.get("role") or "",
            "goal": matched.get("goal") or "",
            "backstory": matched.get("backstory") or "",
            "task_desc": wf_task_prompts.get(aid) or matched.get("task_desc") or "",
            "helpers": list(matched.get("helpers") or []),
        }
    return result
