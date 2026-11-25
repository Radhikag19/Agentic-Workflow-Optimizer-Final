# Sandbox Optimization Experiment Report: `eq_demo_wf`

## 1. Experiment Metadata

- **Workflow ID:** `eq_demo_wf`
- **Experiment ID:** `eq_pareto_test__phase_b_model_selection`
- **Execution Backend:** `local_subprocess`
- **Python Executable:** `C:\Users\radhi\AppData\Local\Programs\Python\Python312\python.exe`
- **Execution Mode(s):** `['live_llm_execution']`
- **Runs Executed:** `1`
- **Baseline Model / Provider:** `openai/gpt-oss-120b` / `Groq` (key env: `None`)
- **Model Overrides Applied:** `{'a1': {'previous_model': 'openai/gpt-oss-120b', 'updated_model': 'openai/gpt-oss-20b', 'provider': 'Groq', 'candidate_id': 'M1'}}`
- **Approved Candidate IDs (1):** `M1`
- **Original Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\tmpqfex8nlj\Agents\eq_demo_wf`
- **Sandbox Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\tmpqfex8nlj\experiments\eq_demo_wf\eq_pareto_test\phase_b\model_selection\sandbox_workflow`
- **Generated At:** 2026-11-25T06:01:55.716151+00:00

## 2. Applied Modifications

- **Applied (1):** `M1`
- **Failed (0):** None
- **Conflicts (0):** None
- **Manual Intervention (0):** None
- **Modified Files:** `a1.py`, `sandbox_optimization_config.json`, `workflow.json`

- **`M1`** (`model_selection`) — Status: `applied` — Updated model configuration for ['a1'] to 'openai/gpt-oss-20b' (provider=Groq) in sandbox while preserving API key bindings.

## 3. Validation Results

- **Original Workflow Unchanged (SHA-256 Verified):** `True`
- **Python Syntax Checks Passed:** `True` (4 files)
- **Configuration Validation Passed:** `True`
- **Dependency & Reference Integrity Passed:** `True`
- **Output Schema Validation Passed (Optimized):** `True`

## 4. Runtime Execution & Baseline Evidence

### Fixed Historical Baseline Evidence
- **Source:** `historical_runtime_traces` | **Execution Mode:** `historical_recorded_execution` | **Re-executed:** `False` | **Groq API Calls:** `0`
- **Fixed Baseline Reference ID:** `hist_586e788e111c` | **Trace Directory:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\tmpqfex8nlj\traces`
- **Input Matching:** matched=`0`, unmatched=`1`, excluded=`1`

### Fresh Optimized Subprocess Execution
- **Source:** `current_experiment` | **Execution Mode(s):** `['live_llm_execution']` | **Re-executed:** `True` | **Groq API Calls:** `3`
- **Trace Directory:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\tmpqfex8nlj\experiments\eq_demo_wf\eq_pareto_test\phase_b\model_selection\runtime_traces`
- **Optimized Runs:** runs=`1`, succeeded=`1`, failed=`0`, process_exit=`0`, status=`SUCCESS`, duration=`1.7s`
- **Optimized API Errors Captured:** `0`
- **Incomplete / Invalid Replay Samples Flagged:** `0`
- **Workflow-Level vs. Agent-Level Latency (Historical Baseline vs. Fresh Optimized):** Baseline WF mean `unavailable` (Agent mean `unavailable`) -> Optimized WF mean `1.7s` (Agent mean `0.5667s`)

## 5. Output Quality Evaluation

| Quality Dimension | Baseline Status (Pass Rate) | Optimized Status (Pass Rate) |
| :--- | :--- | :--- |
| `structural_validity` | `unavailable` (unavailable) | `passed` (100.0%) |
| `correctness` | `unavailable` (unavailable) | `unavailable` (unavailable) |
| `completeness` | `unavailable` (unavailable) | `failed` (66.67%) |
| `consistency` | `unavailable` (unavailable) | `unavailable` (unavailable) |
| `instruction_adherence` | `unavailable` (unavailable) | `passed` (100.0%) |
| `semantic_quality` | `unavailable` (unavailable) | `unavailable` (unavailable) |

- **Identified Regressions:** `0`

## 6. Before-and-After Comparison

| Metric | Baseline | Optimized | Improvement |
| :--- | :--- | :--- | :--- |
| Mean Workflow Latency | unavailable | 1.7s | unavailable |
| Median Workflow Latency | unavailable | 1.7s | unavailable |
| Mean Agent Latency | unavailable | 0.5667s | unavailable |
| Input Tokens | unavailable | 420.0 | unavailable |
| Output Tokens | unavailable | 420.0 | unavailable |
| Total Tokens | unavailable | 840.0 | unavailable |
| Execution Cost (estimated_from_model_catalog_using_api_reported_tokens) | $None | $0.00084 | unavailable |
| Execution Success Rate | unavailable | 100.0% | unavailable |
| Structural Validity | unavailable | 100.0% | unavailable |
| Semantic Quality | `unavailable` | `unavailable` | unavailable |

## 7. Final Experiment Assessment

- **Final Assessment Status:** `inconclusive`
- **Stage Flags:** `modification_applied=True`, `validation_passed=True`, `execution_passed=True`, `evaluation_passed=True`
- **Rationale:**
  - Baseline and optimized runs were not executed on matched identical input datasets.
  - Semantic quality evaluation is unavailable.

### Candidate-Level Traceability

- `M1` (`model_selection`): applied=`True`, validation=`passed`, execution=`passed`, evaluation=`passed`