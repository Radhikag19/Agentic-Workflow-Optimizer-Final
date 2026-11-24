"""
Sandbox Manager: Creates and manages isolated per-experiment copies of target MAS
workflows, preserves original source hashes, stores approved scopes & metadata,
and prevents writes outside the active sandbox directory.
"""

from __future__ import annotations

import copy
import datetime
import hashlib
import json
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from optimization_agent.report import _resolve_reports_dir


def resolve_original_workflow_dir(
    workflow_id: str,
    agents_base_dir: Optional[Union[str, Path]] = None,
) -> Path:
    """Resolve `Agents/<workflow_id>` directory without hardcoding workflow paths."""
    wf_clean = str(workflow_id or "").strip()
    if not wf_clean or "/" in wf_clean or "\\" in wf_clean or ".." in wf_clean:
        raise ValueError(f"Invalid workflow_id for sandbox resolution: {workflow_id!r}")

    if agents_base_dir is not None:
        base = Path(agents_base_dir).resolve()
        target = (base / wf_clean).resolve()
        if not target.exists() or not target.is_dir():
            raise FileNotFoundError(f"Original workflow directory not found: {target}")
        return target

    repo_root = Path(__file__).resolve().parent.parent.parent
    candidates = [
        repo_root / "Agents" / wf_clean,
        Path.cwd() / "Target-MAS-Dataset-main" / "Agents" / wf_clean,
        Path.cwd() / "Agents" / wf_clean,
    ]
    for cand in candidates:
        if cand.exists() and cand.is_dir():
            return cand.resolve()

    raise FileNotFoundError(
        f"Original workflow directory for '{wf_clean}' could not be located."
    )


def resolve_experiments_base_dir(
    reports_dir: Optional[Union[str, Path]] = None,
) -> Path:
    """Resolve `reports/experiments` directory."""
    if reports_dir is not None:
        base = Path(reports_dir).resolve() / "experiments"
    else:
        base = _resolve_reports_dir() / "experiments"
    base.mkdir(parents=True, exist_ok=True)
    return base.resolve()


def assert_path_inside_sandbox(target_path: Union[str, Path], sandbox_dir: Union[str, Path]) -> Path:
    """Ensure a filesystem target resides strictly inside `sandbox_dir`."""
    resolved_target = Path(target_path).resolve()
    resolved_sandbox = Path(sandbox_dir).resolve()
    if not resolved_target.is_relative_to(resolved_sandbox):
        raise PermissionError(
            f"Refused write outside sandbox directory: '{resolved_target}' is not inside '{resolved_sandbox}'."
        )
    return resolved_target


def compute_directory_hashes(directory: Union[str, Path]) -> Dict[str, str]:
    """Compute SHA-256 hex digests for all `.py` and `.json` files in `directory`."""
    base = Path(directory).resolve()
    hashes: Dict[str, str] = {}
    if not base.exists():
        return hashes

    for p in sorted(base.rglob("*")):
        if not p.is_file():
            continue
        if "__pycache__" in p.parts:
            continue
        if p.suffix.lower() not in (".py", ".json"):
            continue
        rel = p.relative_to(base).as_posix()
        hashes[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return hashes


def load_approved_scope(
    scope_or_path: Union[Dict[str, Any], str, Path],
) -> Dict[str, Any]:
    """
    Load and strictly validate an approved optimization scope object or JSON file.
    Accepts either direct `approved_optimization_scope` dicts or `next_stage_input` wrappers.
    Filters `approved_candidates` strictly to IDs listed in `approved_candidate_ids`.
    """
    if isinstance(scope_or_path, (str, Path)):
        p = Path(scope_or_path)
        if not p.exists():
            raise FileNotFoundError(f"Approved optimization scope file not found: {p}")
        raw = json.loads(p.read_text(encoding="utf-8"))
    elif isinstance(scope_or_path, dict):
        raw = copy.deepcopy(scope_or_path)
    else:
        raise ValueError("Approved scope must be a dict or file path.")

    if "approved_optimization_scope" in raw and isinstance(raw["approved_optimization_scope"], dict):
        scope = copy.deepcopy(raw["approved_optimization_scope"])
    else:
        scope = raw

    if scope.get("approval_status") != "approved":
        raise ValueError(
            f"Cannot execute sandbox experiment: approval_status is '{scope.get('approval_status')}', expected 'approved'."
        )

    wf_id = str(scope.get("workflow_id") or "").strip()
    if not wf_id:
        raise ValueError("Approved optimization scope is missing workflow_id.")

    approved_ids = list(scope.get("approved_candidate_ids") or [])
    if not approved_ids:
        raise ValueError("Approved optimization scope contains zero approved_candidate_ids.")

    approved_id_set = set(approved_ids)
    raw_cands = list(scope.get("approved_candidates") or [])
    filtered_cands: List[Dict[str, Any]] = []
    seen_cids: set[str] = set()

    for cand in raw_cands:
        if not isinstance(cand, dict):
            continue
        cid = str(cand.get("candidate_id") or "").strip()
        if not cid or cid not in approved_id_set or cid in seen_cids:
            continue
        cand_wf = str(cand.get("workflow_id") or "").strip()
        if cand_wf and cand_wf != wf_id:
            raise ValueError(
                f"Cross-workflow candidate '{cid}' (belongs to '{cand_wf}') cannot run under '{wf_id}'."
            )
        filtered_cands.append(copy.deepcopy(cand))
        seen_cids.add(cid)

    if not filtered_cands:
        raise ValueError("Approved optimization scope has no matching candidate objects for approved_candidate_ids.")

    scope["workflow_id"] = wf_id
    scope["approved_candidate_ids"] = [c["candidate_id"] for c in filtered_cands]
    scope["approved_candidates"] = filtered_cands
    return scope


@dataclass
class SandboxEnvironment:
    """Descriptor for an isolated workflow optimization experiment sandbox."""

    experiment_id: str
    workflow_id: str
    experiment_dir: Path
    sandbox_workflow_dir: Path
    runtime_traces_dir: Path
    original_workflow_dir: Path
    approved_scope: Dict[str, Any]
    approved_scope_path: Path
    experiment_metadata_path: Path
    original_file_hashes: Dict[str, str]
    original_to_sandbox_map: Dict[str, str]
    sandbox_to_original_map: Dict[str, str]
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "workflow_id": self.workflow_id,
            "experiment_dir": str(self.experiment_dir),
            "sandbox_workflow_dir": str(self.sandbox_workflow_dir),
            "runtime_traces_dir": str(self.runtime_traces_dir),
            "original_workflow_dir": str(self.original_workflow_dir),
            "approved_scope_path": str(self.approved_scope_path),
            "experiment_metadata_path": str(self.experiment_metadata_path),
            "approved_candidate_ids": list(self.approved_scope.get("approved_candidate_ids") or []),
            "original_to_sandbox_map": dict(self.original_to_sandbox_map),
            "created_at": self.created_at,
        }


class SandboxManager:
    """Manages creation, file isolation, metadata, and integrity verification of experiment sandboxes."""

    def __init__(
        self,
        agents_base_dir: Optional[Union[str, Path]] = None,
        experiments_base_dir: Optional[Union[str, Path]] = None,
    ):
        self.agents_base_dir = Path(agents_base_dir).resolve() if agents_base_dir is not None else None
        self.experiments_base_dir = (
            Path(experiments_base_dir).resolve()
            if experiments_base_dir is not None
            else resolve_experiments_base_dir()
        )

    def prepare_sandbox(
        self,
        approved_scope: Union[Dict[str, Any], str, Path],
        experiment_id: Optional[str] = None,
        experiment_dir_override: Optional[Union[str, Path]] = None,
    ) -> SandboxEnvironment:
        """Create an isolated sandbox copy of the target workflow for an approved scope."""
        scope = load_approved_scope(approved_scope)
        wf_id = scope["workflow_id"]
        orig_dir = resolve_original_workflow_dir(wf_id, agents_base_dir=self.agents_base_dir)

        exp_id = experiment_id or (
            f"exp_{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        )
        exp_dir = (
            Path(experiment_dir_override).resolve()
            if experiment_dir_override is not None
            else (self.experiments_base_dir / wf_id / exp_id).resolve()
        )
        sandbox_wf_dir = (exp_dir / "sandbox_workflow").resolve()
        traces_dir = (exp_dir / "runtime_traces").resolve()

        exp_dir.mkdir(parents=True, exist_ok=True)
        traces_dir.mkdir(parents=True, exist_ok=True)

        if sandbox_wf_dir.exists():
            shutil.rmtree(sandbox_wf_dir)

        orig_hashes = compute_directory_hashes(orig_dir)

        shutil.copytree(
            orig_dir,
            sandbox_wf_dir,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )

        # Remove workflow_context.json only? No, keep original config files intact in sandbox copy.
        orig_to_sb: Dict[str, str] = {}
        sb_to_orig: Dict[str, str] = {}
        for rel in sorted(orig_hashes.keys()):
            orig_p = (orig_dir / rel).resolve()
            sb_p = (sandbox_wf_dir / rel).resolve()
            if sb_p.exists():
                orig_to_sb[str(orig_p)] = str(sb_p)
                sb_to_orig[str(sb_p)] = str(orig_p)

        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        approved_scope_path = exp_dir / "approved_scope.json"
        approved_scope_path.write_text(json.dumps(scope, indent=2), encoding="utf-8")

        # Initialize sandbox optimization registry inside sandbox_workflow
        config_path = assert_path_inside_sandbox(
            sandbox_wf_dir / "sandbox_optimization_config.json",
            sandbox_wf_dir,
        )
        config_path.write_text(
            json.dumps(
                {
                    "workflow_id": wf_id,
                    "experiment_id": exp_id,
                    "consolidations": [],
                    "parallel_groups": [],
                    "model_overrides": {},
                    "prompt_overrides": {},
                    "handoff_projections": {},
                    "applied_candidates": [],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        metadata = {
            "experiment_id": exp_id,
            "workflow_id": wf_id,
            "original_workflow_dir": str(orig_dir),
            "sandbox_workflow_dir": str(sandbox_wf_dir),
            "runtime_traces_dir": str(traces_dir),
            "approved_candidate_ids": list(scope["approved_candidate_ids"]),
            "original_to_sandbox_map": orig_to_sb,
            "original_file_hashes": orig_hashes,
            "created_at": created_at,
        }
        metadata_path = exp_dir / "experiment_metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        return SandboxEnvironment(
            experiment_id=exp_id,
            workflow_id=wf_id,
            experiment_dir=exp_dir,
            sandbox_workflow_dir=sandbox_wf_dir,
            runtime_traces_dir=traces_dir,
            original_workflow_dir=orig_dir,
            approved_scope=scope,
            approved_scope_path=approved_scope_path,
            experiment_metadata_path=metadata_path,
            original_file_hashes=orig_hashes,
            original_to_sandbox_map=orig_to_sb,
            sandbox_to_original_map=sb_to_orig,
            created_at=created_at,
        )

    @staticmethod
    def verify_original_unchanged(env: SandboxEnvironment) -> Dict[str, Any]:
        """Re-hash original workflow files and verify zero modification occurred."""
        current_hashes = compute_directory_hashes(env.original_workflow_dir)
        expected_hashes = env.original_file_hashes

        changed: List[str] = []
        missing: List[str] = []
        added: List[str] = []

        for rel, digest in expected_hashes.items():
            if rel not in current_hashes:
                missing.append(rel)
            elif current_hashes[rel] != digest:
                changed.append(rel)

        for rel in current_hashes:
            if rel not in expected_hashes:
                added.append(rel)

        unchanged = not changed and not missing and not added
        return {
            "original_unchanged": unchanged,
            "checked_file_count": len(expected_hashes),
            "changed_files": changed,
            "missing_files": missing,
            "added_files": added,
        }
