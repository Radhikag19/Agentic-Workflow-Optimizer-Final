"""
Deterministic Candidate Review Session:
Manages workflow candidate inventory, dimension filtering, individual selections,
live summaries, risk acknowledgements, and final approval persistence.
"""

from __future__ import annotations

import copy
import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Union

from optimization_agent.report import _resolve_reports_dir
from optimization_agent.review.models import (
    CANONICAL_DIMENSIONS,
    ELIGIBLE_TIERS,
    TIER_ORDER,
    build_candidate_card_view,
    extract_candidates_from_report,
    get_dimension_label,
    get_risk_info,
    get_validation_info,
    normalize_dimension_key,
    normalize_tier,
)


class CandidateReviewSession:
    """
    Deterministic workflow-scoped session for reviewing, filtering, selecting,
    acknowledging risks, and approving optimization candidates.
    """

    def __init__(
        self,
        workflow_id: str,
        candidates: List[Dict[str, Any]],
        report_data: Optional[Dict[str, Any]] = None,
    ):
        wf_clean = str(workflow_id or "").strip()
        if not wf_clean:
            raise ValueError("workflow_id must be a non-empty string.")

        self.workflow_id: str = wf_clean
        self.report_data: Dict[str, Any] = copy.deepcopy(report_data) if isinstance(report_data, dict) else {}
        self.action_plan: Dict[str, Any] = (
            dict(self.report_data.get("prioritized_action_plan") or {})
            if isinstance(self.report_data, dict)
            else {}
        )

        self._candidates: List[Dict[str, Any]] = []
        self._candidates_by_id: Dict[str, Dict[str, Any]] = {}
        self.eligible_candidate_ids: List[str] = []
        self.exploratory_candidate_ids: List[str] = []

        for idx, cand in enumerate(candidates or []):
            if not isinstance(cand, dict):
                continue
            cand_wf = str(cand.get("workflow_id") or "").strip()
            if cand_wf and cand_wf != self.workflow_id:
                raise ValueError(
                    f"Cross-workflow candidate rejected: candidate belongs to '{cand_wf}', expected '{self.workflow_id}'."
                )

            cand_copy = copy.deepcopy(cand)
            cid = str(cand_copy.get("candidate_id") or f"CANDIDATE-{idx + 1}")
            if cid in self._candidates_by_id:
                continue

            self._candidates.append(cand_copy)
            self._candidates_by_id[cid] = cand_copy

            tier = normalize_tier(cand_copy)
            if tier in ELIGIBLE_TIERS:
                self.eligible_candidate_ids.append(cid)
            else:
                self.exploratory_candidate_ids.append(cid)

        # Default preselection: Tiers 1, 2, 3 preselected; Tier 4 excluded.
        # Preselection is NEVER approval.
        self.selected_candidate_ids: Set[str] = set(self.eligible_candidate_ids)
        self.risk_acknowledged_candidate_ids: Set[str] = set()
        self.active_dimension_filters: List[str] = []
        self.approval_status: str = "pending_user_review"
        self.approved_scope: Optional[Dict[str, Any]] = None

    @classmethod
    def from_report(cls, report_data: Dict[str, Any]) -> "CandidateReviewSession":
        """Construct a review session directly from a parsed optimization report dict."""
        workflow_id, candidates = extract_candidates_from_report(report_data)
        return cls(workflow_id=workflow_id, candidates=candidates, report_data=report_data)

    @classmethod
    def from_report_file(cls, report_path: Union[str, Path]) -> "CandidateReviewSession":
        """Load `<workflow_id>_optimization_report.json` and initialize review session."""
        path = Path(report_path)
        if not path.exists():
            raise FileNotFoundError(f"Optimization report not found: {path}")
        report_data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_report(report_data)

    @classmethod
    def from_workflow_id(
        cls,
        workflow_id: str,
        reports_dir: Optional[Union[str, Path]] = None,
    ) -> "CandidateReviewSession":
        """Resolve and load the discovery report for a workflow ID."""
        base_dir = Path(reports_dir).resolve() if reports_dir is not None else _resolve_reports_dir()
        path = base_dir / f"{workflow_id}_optimization_report.json"
        return cls.from_report_file(path)

    # ------------------------------------------------------------------
    # Read-only Queries & Summaries
    # ------------------------------------------------------------------

    @property
    def candidates(self) -> List[Dict[str, Any]]:
        """Return verbatim deep copies of all loaded candidates."""
        return copy.deepcopy(self._candidates)

    def get_candidate(self, candidate_id: str) -> Dict[str, Any]:
        """Retrieve a verbatim deep copy of a candidate by ID."""
        if candidate_id not in self._candidates_by_id:
            raise KeyError(
                f"Candidate '{candidate_id}' does not exist in workflow '{self.workflow_id}'."
            )
        return copy.deepcopy(self._candidates_by_id[candidate_id])

    def get_candidate_card(self, candidate_id: str) -> Dict[str, Any]:
        """Return structured card view (Sections A-E) for a candidate."""
        return build_candidate_card_view(
            self._candidates_by_id[candidate_id],
            action_plan=self.action_plan,
        )

    def get_workflow_summary(self) -> Dict[str, Any]:
        """Dynamically compute workflow summary metrics from loaded candidates."""
        tier_counts: Dict[str, int] = {t: 0 for t in TIER_ORDER}
        dims_present: Set[str] = set()

        for cand in self._candidates:
            tier_counts[normalize_tier(cand)] += 1
            dims_present.add(normalize_dimension_key(cand.get("dimension")))

        canonical_present_count = sum(
            1 for dim in CANONICAL_DIMENSIONS if dim["key"] in dims_present
        )

        return {
            "workflow_id": self.workflow_id,
            "total_candidates": len(self._candidates),
            "tier_counts": tier_counts,
            "tier_1_count": tier_counts["Tier 1"],
            "tier_2_count": tier_counts["Tier 2"],
            "tier_3_count": tier_counts["Tier 3"],
            "tier_4_count": tier_counts["Tier 4"],
            "dimensions_with_candidates": canonical_present_count,
            "total_dimensions": len(CANONICAL_DIMENSIONS),
        }

    def get_dimension_counts(self) -> List[Dict[str, Any]]:
        """Return the 5 canonical dimensions in order with dynamic candidate counts."""
        counts: Dict[str, int] = {dim["key"]: 0 for dim in CANONICAL_DIMENSIONS}
        for cand in self._candidates:
            dk = normalize_dimension_key(cand.get("dimension"))
            if dk in counts:
                counts[dk] += 1

        return [
            {
                "dimension_key": dim["key"],
                "label": dim["label"],
                "report_section": dim["report_section"],
                "count": counts[dim["key"]],
            }
            for dim in CANONICAL_DIMENSIONS
        ]

    # ------------------------------------------------------------------
    # Dimension Filtering (Non-Destructive)
    # ------------------------------------------------------------------

    def set_dimension_filter(self, dimensions: Optional[Sequence[str]]) -> None:
        """
        Filter displayed dimensions without mutating underlying candidate data or selections.
        Passing None or empty sequence clears the filter (shows all dimensions).
        """
        if not dimensions:
            self.active_dimension_filters = []
            return

        valid_keys = {d["key"] for d in CANONICAL_DIMENSIONS}
        normalized: List[str] = []
        for raw in dimensions:
            dk = normalize_dimension_key(raw)
            if dk not in valid_keys:
                raise ValueError(f"Unknown optimization dimension filter: '{raw}'")
            if dk not in normalized:
                normalized.append(dk)
        self.active_dimension_filters = normalized

    def reset_dimension_filter(self) -> None:
        """Reset active dimension filter so all dimensions are shown."""
        self.active_dimension_filters = []

    def _active_dimension_keys(self) -> List[str]:
        if not self.active_dimension_filters:
            return [d["key"] for d in CANONICAL_DIMENSIONS]
        return [d["key"] for d in CANONICAL_DIMENSIONS if d["key"] in self.active_dimension_filters]

    def get_filtered_candidates(self, include_tier_4: bool = True) -> List[Dict[str, Any]]:
        """Return verbatim copies of candidates matching the active dimension filter."""
        allowed_dims = set(self._active_dimension_keys())
        result: List[Dict[str, Any]] = []
        for cand in self._candidates:
            dk = normalize_dimension_key(cand.get("dimension"))
            if dk not in allowed_dims:
                continue
            if not include_tier_4 and normalize_tier(cand) == "Tier 4":
                continue
            result.append(copy.deepcopy(cand))
        return result

    def get_grouped_filtered_candidates(self, include_tier_4: bool = True) -> List[Dict[str, Any]]:
        """
        Return candidates grouped under each active dimension with empty-state
        messaging when a specifically selected dimension has zero candidates.
        """
        active_keys = self._active_dimension_keys()
        by_dim: Dict[str, List[Dict[str, Any]]] = {k: [] for k in active_keys}

        for cand in self._candidates:
            dk = normalize_dimension_key(cand.get("dimension"))
            if dk not in by_dim:
                continue
            if not include_tier_4 and normalize_tier(cand) == "Tier 4":
                continue
            by_dim[dk].append(copy.deepcopy(cand))

        grouped: List[Dict[str, Any]] = []
        for dk in active_keys:
            label = get_dimension_label(dk)
            cands = by_dim[dk]
            grouped.append({
                "dimension_key": dk,
                "label": label,
                "count": len(cands),
                "candidates": cands,
                "empty_state_message": (
                    f"No optimization candidates were discovered for {label} in this workflow report."
                    if not cands
                    else None
                ),
            })
        return grouped

    def get_tier_4_exploratory_candidates(self) -> List[Dict[str, Any]]:
        """Return Tier 4 exploratory candidates matching active dimension filter."""
        allowed_dims = set(self._active_dimension_keys())
        return [
            copy.deepcopy(c)
            for c in self._candidates
            if normalize_tier(c) == "Tier 4"
            and normalize_dimension_key(c.get("dimension")) in allowed_dims
        ]

    # ------------------------------------------------------------------
    # Individual Selection & Risk Acknowledgements
    # ------------------------------------------------------------------

    def _validate_known_candidate_id(self, candidate_id: str) -> None:
        if candidate_id not in self._candidates_by_id:
            raise KeyError(
                f"Candidate ID '{candidate_id}' not found in workflow '{self.workflow_id}' inventory."
            )

    def select_candidate(self, candidate_id: str) -> None:
        self._validate_known_candidate_id(candidate_id)
        self.selected_candidate_ids.add(candidate_id)
        self.approval_status = "pending_user_review"

    def deselect_candidate(self, candidate_id: str) -> None:
        self._validate_known_candidate_id(candidate_id)
        self.selected_candidate_ids.discard(candidate_id)
        self.approval_status = "pending_user_review"

    def set_candidate_selected(self, candidate_id: str, selected: bool) -> None:
        if selected:
            self.select_candidate(candidate_id)
        else:
            self.deselect_candidate(candidate_id)

    def select_all_eligible(self) -> None:
        """Select all Tier 1, Tier 2, and Tier 3 candidates (excludes Tier 4). Does NOT approve."""
        self.selected_candidate_ids = set(self.eligible_candidate_ids)
        self.approval_status = "pending_user_review"

    def clear_selection(self) -> None:
        """Deselect all candidates. Does NOT approve."""
        self.selected_candidate_ids.clear()
        self.approval_status = "pending_user_review"

    def acknowledge_risk(self, candidate_id: str, acknowledged: bool = True) -> None:
        self._validate_known_candidate_id(candidate_id)
        if acknowledged:
            self.risk_acknowledged_candidate_ids.add(candidate_id)
        else:
            self.risk_acknowledged_candidate_ids.discard(candidate_id)

    def acknowledge_all_selected_risks(self) -> None:
        """Convenience helper to acknowledge explicit risks on all currently selected candidates."""
        for cid in list(self.selected_candidate_ids):
            cand = self._candidates_by_id[cid]
            if get_risk_info(cand)["requires_risk_acknowledgement"]:
                self.risk_acknowledged_candidate_ids.add(cid)

    def get_unacknowledged_risk_candidate_ids(self) -> List[str]:
        """Return ordered selected candidate IDs requiring risk acknowledgement that are unacknowledged."""
        pending: List[str] = []
        for cand in self._candidates:
            cid = str(cand.get("candidate_id") or "")
            if cid not in self.selected_candidate_ids:
                continue
            if get_risk_info(cand)["requires_risk_acknowledgement"] and cid not in self.risk_acknowledged_candidate_ids:
                pending.append(cid)
        return pending

    def get_selection_summary(self) -> Dict[str, Any]:
        """
        Compute live selection metrics purely from individual selected candidate IDs.
        """
        selected_by_tier: Dict[str, int] = {t: 0 for t in TIER_ORDER}
        selected_by_dimension: Dict[str, int] = {d["key"]: 0 for d in CANONICAL_DIMENSIONS}
        req_validation_ids: List[str] = []
        explicit_risk_ids: List[str] = []
        unacknowledged_risk_ids: List[str] = []

        for cand in self._candidates:
            cid = str(cand.get("candidate_id") or "")
            if cid not in self.selected_candidate_ids:
                continue

            tier = normalize_tier(cand)
            selected_by_tier[tier] += 1

            dk = normalize_dimension_key(cand.get("dimension"))
            if dk in selected_by_dimension:
                selected_by_dimension[dk] += 1

            val_info = get_validation_info(cand, action_plan=self.action_plan)
            if val_info["requires_validation"]:
                req_validation_ids.append(cid)

            risk_info = get_risk_info(cand)
            if risk_info["has_explicit_risk"]:
                explicit_risk_ids.append(cid)
                if cid not in self.risk_acknowledged_candidate_ids:
                    unacknowledged_risk_ids.append(cid)

        return {
            "total_discovered": len(self._candidates),
            "selected_count": len(self.selected_candidate_ids),
            "selected_by_tier": selected_by_tier,
            "selected_by_dimension": selected_by_dimension,
            "selected_requiring_validation": len(req_validation_ids),
            "selected_requiring_validation_ids": req_validation_ids,
            "selected_with_explicit_risks": len(explicit_risk_ids),
            "selected_with_explicit_risk_ids": explicit_risk_ids,
            "unacknowledged_risk_count": len(unacknowledged_risk_ids),
            "unacknowledged_risk_candidate_ids": unacknowledged_risk_ids,
            "approval_status": self.approval_status,
        }

    # ------------------------------------------------------------------
    # Validation & Final Approval
    # ------------------------------------------------------------------

    def validate_approval_readiness(
        self,
        expected_workflow_id: Optional[str] = None,
        explicit_candidate_ids: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """
        Verify workflow isolation, inventory membership, non-empty selection,
        and risk acknowledgement completeness before final approval.
        """
        errors: List[str] = []

        if expected_workflow_id is not None and str(expected_workflow_id).strip() != self.workflow_id:
            errors.append(
                f"Workflow isolation mismatch: expected '{expected_workflow_id}', "
                f"but session is bound to '{self.workflow_id}'."
            )

        ids_to_check = (
            list(explicit_candidate_ids)
            if explicit_candidate_ids is not None
            else [
                str(c.get("candidate_id") or "")
                for c in self._candidates
                if str(c.get("candidate_id") or "") in self.selected_candidate_ids
            ]
        )

        unknown_ids = [cid for cid in ids_to_check if cid not in self._candidates_by_id]
        if unknown_ids:
            errors.append(
                f"Selected candidate ID(s) do not belong to workflow '{self.workflow_id}': {unknown_ids}"
            )

        for cid in ids_to_check:
            cand = self._candidates_by_id.get(cid)
            if not cand:
                continue
            cand_wf = str(cand.get("workflow_id") or "").strip()
            if cand_wf and cand_wf != self.workflow_id:
                errors.append(
                    f"Candidate '{cid}' belongs to workflow '{cand_wf}', not '{self.workflow_id}'."
                )

        if not ids_to_check:
            errors.append("At least one optimization candidate must be selected before approval.")

        unacknowledged: List[str] = []
        for cid in ids_to_check:
            cand = self._candidates_by_id.get(cid)
            if cand and get_risk_info(cand)["requires_risk_acknowledgement"]:
                if cid not in self.risk_acknowledged_candidate_ids:
                    unacknowledged.append(cid)

        if unacknowledged:
            errors.append(
                "Risk acknowledgement required before approval for candidate(s): "
                + ", ".join(unacknowledged)
            )

        return {
            "ready": len(errors) == 0,
            "errors": errors,
            "unacknowledged_risk_ids": unacknowledged,
        }

    def approve(
        self,
        expected_workflow_id: Optional[str] = None,
        persist: bool = True,
        output_dir: Optional[Union[str, Path]] = None,
    ) -> Dict[str, Any]:
        """
        Construct and optionally persist the structured Approved Optimization Scope.
        Does NOT mutate target workflow files or launch optimization experiments.
        """
        readiness = self.validate_approval_readiness(expected_workflow_id=expected_workflow_id)
        if not readiness["ready"]:
            raise ValueError("; ".join(readiness["errors"]))

        approved_candidates: List[Dict[str, Any]] = []
        approved_candidate_ids: List[str] = []
        excluded_candidate_ids: List[str] = []
        candidate_tiers: Dict[str, str] = {}
        validation_required_ids: List[str] = []
        risk_acknowledged_ids: List[str] = []
        dims_set: Set[str] = set()

        for cand in self._candidates:
            cid = str(cand.get("candidate_id") or "")
            if cid in self.selected_candidate_ids:
                approved_candidates.append(copy.deepcopy(cand))
                approved_candidate_ids.append(cid)
                tier = normalize_tier(cand)
                candidate_tiers[cid] = tier
                dims_set.add(normalize_dimension_key(cand.get("dimension")))
                if cand.get("requires_validation"):
                    validation_required_ids.append(cid)
                if cid in self.risk_acknowledged_candidate_ids:
                    risk_acknowledged_ids.append(cid)
            else:
                excluded_candidate_ids.append(cid)

        selected_dimensions = [
            dim["key"] for dim in CANONICAL_DIMENSIONS if dim["key"] in dims_set
        ]
        # Preserve any non-canonical dimension keys deterministically if present
        for extra_dim in sorted(dims_set):
            if extra_dim not in selected_dimensions:
                selected_dimensions.append(extra_dim)

        approved_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        scope: Dict[str, Any] = {
            "workflow_id": self.workflow_id,
            "selected_dimensions": selected_dimensions,
            "approved_candidate_ids": approved_candidate_ids,
            "excluded_candidate_ids": excluded_candidate_ids,
            "approved_candidates": approved_candidates,
            "candidate_tiers": candidate_tiers,
            "validation_required_candidate_ids": validation_required_ids,
            "risk_acknowledged_candidate_ids": risk_acknowledged_ids,
            "approval_status": "approved",
            "approved_at": approved_at,
        }

        if persist:
            dest_dir = Path(output_dir).resolve() if output_dir is not None else _resolve_reports_dir()
            dest_dir.mkdir(parents=True, exist_ok=True)
            scope_path = dest_dir / f"{self.workflow_id}_approved_optimization_scope.json"
            scope_path.write_text(json.dumps(scope, indent=2), encoding="utf-8")

        self.approval_status = "approved"
        self.approved_scope = copy.deepcopy(scope)
        return copy.deepcopy(scope)
