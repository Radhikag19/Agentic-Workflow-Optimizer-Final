# Per-Dimension & Combined Optimization Ablation Report: `recruitment_screening`

## 1. Suite Metadata

- **Suite ID:** `wp_20261124_183147_914004`
- **Workflow ID:** `recruitment_screening`
- **Selected Dimensions Filter:** `['communication_data_handoff', 'workflow_parallelization', 'model_selection', 'agent_consolidation', 'prompt_optimization']` (`None` = all dimensions with approved candidates)
- **Executed Dimensions (3):** `communication_data_handoff`, `workflow_parallelization`, `model_selection`
- **Skipped Dimensions (2):** `agent_consolidation`, `prompt_optimization`
- **Combined Run Included:** `True`
- **Runs Per Configuration (`num_runs`):** `2`
- **Generated At:** 2026-11-24T18:39:57.388149+00:00

## 2. Fixed Historical Baseline Reference

- **Source:** `historical_runtime_traces` | **Execution Mode:** `historical_recorded_execution`
- **Re-executed:** `False` | **Groq API Calls:** `0`
- **Fixed Baseline Reference ID:** `hist_ef23650339c0`
- **Matched Inputs:** `30` (unmatched: `0`)

## 3. Isolated Per-Dimension vs. Combined Comparison

| Configuration | Scope | Applied Candidates | Runs Passed / Executed | Mean Latency (s) | Latency Delta (%) | Mean Tokens | Token Delta (%) | Mean Cost (USD) | Cost Delta (%) | Groq Calls | Structural Validity (%) | Assessment | Report |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `fixed_historical_baseline` | `historical_baseline` | - | 2/2 | 22.7775 | 0.0% | 16755.0 | 0.0% | 0.005518 | 0.0% | 0 | 83.75% | `HISTORICAL_FIXED` | - |
| `communication_data_handoff` | `isolated_dimension` | `HANDOFF-QUALIFICATION_AGENT-TO-EXPERIENCE_ASSESSMENT_AGENT`, `HANDOFF-EXPERIENCE_ASSESSMENT_AGENT-TO-SCREENING_REVIEW_AGENT` | 2/2 | 95.4369 | -319.0% | 34883.0 | -108.19% | 0.011188 | -102.75% | 16 | 100.0% | `quality_regression` | `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\recruitment_screening\wp_20261124_183147_914004\per_dimension\communication_data_handoff\execution_report.md` |
| `workflow_parallelization` | `isolated_dimension` | `PARALLEL-QUALIFICATION_AGENT-JOB_CRITERIA_AGENT` | 2/2 | 97.9727 | -330.13% | 35894.0 | -114.23% | 0.011497 | -108.35% | 16 | 100.0% | `quality_regression` | `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\recruitment_screening\wp_20261124_183147_914004\per_dimension\workflow_parallelization\execution_report.md` |
| `model_selection` | `isolated_dimension` | `MODEL-RESUME_INTAKE_AGENT` | 0/2 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 2 | 0.0% | `failed` | `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\recruitment_screening\wp_20261124_183147_914004\per_dimension\model_selection\execution_report.md` |
| `combined_all_selected_dimensions` | `combined_single_workflow` | `PARALLEL-QUALIFICATION_AGENT-JOB_CRITERIA_AGENT`, `MODEL-RESUME_INTAKE_AGENT`, `HANDOFF-QUALIFICATION_AGENT-TO-EXPERIENCE_ASSESSMENT_AGENT`, `HANDOFF-EXPERIENCE_ASSESSMENT_AGENT-TO-SCREENING_REVIEW_AGENT` | 0/2 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 2 | 0.0% | `failed` | `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\recruitment_screening\wp_20261124_183147_914004\combined\execution_report.md` |

## 4. Skipped Dimensions

- `agent_consolidation`: `no_approved_candidates`
- `prompt_optimization`: `no_approved_candidates`

## 5. Original Workflow Integrity

- **Original Workflow Unchanged (SHA-256 Verified):** `True` (files checked: `12`)