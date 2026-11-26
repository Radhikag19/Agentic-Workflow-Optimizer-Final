# Per-Dimension & Combined Optimization Ablation Report: `recruitment_screening`

## 1. Suite Metadata

- **Suite ID:** `wp_20261125_172742_e1478e`
- **Workflow ID:** `recruitment_screening`
- **Selected Dimensions Filter:** `['communication_data_handoff', 'workflow_parallelization', 'model_selection', 'agent_consolidation', 'prompt_optimization']` (`None` = all dimensions with approved candidates)
- **Executed Dimensions (3):** `communication_data_handoff`, `workflow_parallelization`, `model_selection`
- **Skipped Dimensions (2):** `agent_consolidation`, `prompt_optimization`
- **Combined Run Included:** `True`
- **Runs Per Configuration (`num_runs`):** `2`
- **Generated At:** 2026-11-25T17:44:20.246270+00:00

## 2. Fixed Historical Baseline Reference

- **Source:** `historical_runtime_traces` | **Execution Mode:** `historical_recorded_execution`
- **Re-executed:** `False` | **Groq API Calls:** `0`
- **Fixed Baseline Reference ID:** `hist_ef23650339c0`
- **Matched Inputs:** `30` (unmatched: `0`)

## 3. Isolated Per-Dimension vs. Combined Comparison

| Configuration | Scope | Applied Candidates | Runs Passed / Executed | Mean Latency (s) | Latency Delta (%) | Mean Tokens | Token Delta (%) | Mean Cost (USD) | Cost Delta (%) | Groq Calls | Structural Validity (%) | Assessment | Report |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `fixed_historical_baseline` | `historical_baseline` | - | 2/2 | 22.7775 | 0.0% | 16755.0 | 0.0% | 0.005518 | 0.0% | 0 | 83.75% | `HISTORICAL_FIXED` | - |
| `communication_data_handoff` | `isolated_dimension` | `HANDOFF-QUALIFICATION_AGENT-TO-EXPERIENCE_ASSESSMENT_AGENT`, `HANDOFF-EXPERIENCE_ASSESSMENT_AGENT-TO-SCREENING_REVIEW_AGENT` | 2/2 | 101.885 | -347.31% | 35030.0 | -109.07% | 0.011281 | -104.44% | 16 | 100.0% | `quality_regression` | `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\recruitment_screening\wp_20261125_172742_e1478e\per_dimension\communication_data_handoff\execution_report.md` |
| `workflow_parallelization` | `isolated_dimension` | `PARALLEL-QUALIFICATION_AGENT-JOB_CRITERIA_AGENT` | 2/2 | 107.5203 | -372.05% | 37509.0 | -123.87% | 0.012364 | -124.07% | 16 | 93.75% | `quality_regression` | `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\recruitment_screening\wp_20261125_172742_e1478e\per_dimension\workflow_parallelization\execution_report.md` |
| `model_selection` | `isolated_dimension` | `MODEL-RESUME_INTAKE_AGENT` | 2/2 | 99.1027 | -335.09% | 37369.0 | -123.03% | 0.011595 | -110.13% | 16 | 100.0% | `quality_regression` | `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\recruitment_screening\wp_20261125_172742_e1478e\per_dimension\model_selection\execution_report.md` |
| `combined_all_selected_dimensions` | `combined_single_workflow` | `PARALLEL-QUALIFICATION_AGENT-JOB_CRITERIA_AGENT`, `MODEL-RESUME_INTAKE_AGENT`, `HANDOFF-QUALIFICATION_AGENT-TO-EXPERIENCE_ASSESSMENT_AGENT`, `HANDOFF-EXPERIENCE_ASSESSMENT_AGENT-TO-SCREENING_REVIEW_AGENT` | 2/2 | 100.6971 | -342.09% | 37984.0 | -126.7% | 0.011954 | -116.64% | 16 | 100.0% | `quality_regression` | `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\recruitment_screening\wp_20261125_172742_e1478e\combined\execution_report.md` |

## 4. Skipped Dimensions

- `agent_consolidation`: `no_approved_candidates`
- `prompt_optimization`: `no_approved_candidates`

## 5. Original Workflow Integrity

- **Original Workflow Unchanged (SHA-256 Verified):** `True` (files checked: `12`)