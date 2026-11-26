# Per-Dimension & Combined Optimization Ablation Report: `recruitment_screening`

## 1. Suite Metadata

- **Suite ID:** `wp_20261125_091807_cbdcfb`
- **Workflow ID:** `recruitment_screening`
- **Selected Dimensions Filter:** `['model_selection', 'agent_consolidation', 'prompt_optimization']` (`None` = all dimensions with approved candidates)
- **Executed Dimensions (1):** `model_selection`
- **Skipped Dimensions (2):** `agent_consolidation`, `prompt_optimization`
- **Combined Run Included:** `True`
- **Runs Per Configuration (`num_runs`):** `2`
- **Generated At:** 2026-11-25T09:18:45.411894+00:00

## 2. Fixed Historical Baseline Reference

- **Source:** `historical_runtime_traces` | **Execution Mode:** `historical_recorded_execution`
- **Re-executed:** `False` | **Groq API Calls:** `0`
- **Fixed Baseline Reference ID:** `hist_ef23650339c0`
- **Matched Inputs:** `30` (unmatched: `0`)

## 3. Isolated Per-Dimension vs. Combined Comparison

| Configuration | Scope | Applied Candidates | Runs Passed / Executed | Mean Latency (s) | Latency Delta (%) | Mean Tokens | Token Delta (%) | Mean Cost (USD) | Cost Delta (%) | Groq Calls | Structural Validity (%) | Assessment | Report |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `fixed_historical_baseline` | `historical_baseline` | - | 2/2 | 22.7775 | 0.0% | 16755.0 | 0.0% | 0.005518 | 0.0% | 0 | 83.75% | `HISTORICAL_FIXED` | - |
| `model_selection` | `isolated_dimension` | `MODEL-RESUME_INTAKE_AGENT` | 0/2 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 2 | 0.0% | `failed` | `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\recruitment_screening\wp_20261125_091807_cbdcfb\per_dimension\model_selection\execution_report.md` |
| `combined_all_selected_dimensions` | `combined_single_workflow` | `MODEL-RESUME_INTAKE_AGENT` | 0/2 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 2 | 0.0% | `failed` | `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\recruitment_screening\wp_20261125_091807_cbdcfb\combined\execution_report.md` |

## 4. Skipped Dimensions

- `agent_consolidation`: `no_approved_candidates`
- `prompt_optimization`: `no_approved_candidates`

## 5. Original Workflow Integrity

- **Original Workflow Unchanged (SHA-256 Verified):** `True` (files checked: `12`)