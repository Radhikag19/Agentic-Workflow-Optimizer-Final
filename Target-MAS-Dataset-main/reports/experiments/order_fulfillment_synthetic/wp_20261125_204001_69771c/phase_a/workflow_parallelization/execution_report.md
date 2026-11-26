# Sandbox Optimization Experiment Report: `order_fulfillment_synthetic`

## 1. Experiment Metadata

- **Workflow ID:** `order_fulfillment_synthetic`
- **Experiment ID:** `wp_20261125_204001_69771c__phase_a_workflow_parallelization`
- **Execution Backend:** `local_subprocess`
- **Python Executable:** `C:\Users\radhi\AppData\Local\Programs\Python\Python312\python.exe`
- **Execution Mode(s):** `['live_llm_execution']`
- **Runs Executed:** `2`
- **Baseline Model / Provider:** `openai/gpt-oss-120b` / `Groq` (key env: `GROQ_API_KEY_14`)
- **Model Overrides Applied:** `{}`
- **Approved Candidate IDs (1):** `PARALLEL-INVENTORY_CHECK_AGENT-FRAUD_SCREEN_AGENT`
- **Original Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\Agents\order_fulfillment_synthetic`
- **Sandbox Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\order_fulfillment_synthetic\wp_20261125_204001_69771c\phase_a\workflow_parallelization\sandbox_workflow`
- **Generated At:** 2026-11-25T20:42:44.298196+00:00

## 2. Applied Modifications

- **Applied (1):** `PARALLEL-INVENTORY_CHECK_AGENT-FRAUD_SCREEN_AGENT`
- **Failed (0):** None
- **Conflicts (0):** None
- **Manual Intervention (0):** None
- **Modified Files:** `sandbox_optimization_config.json`, `workflow.json`, `workflow.py`

- **`PARALLEL-INVENTORY_CHECK_AGENT-FRAUD_SCREEN_AGENT`** (`workflow_parallelization`) — Status: `applied` — Configured concurrent scatter-gather group ['inventory_check_agent', 'fraud_screen_agent'] in sandbox workflow after verifying strict DAG & I/O independence.

## 3. Validation Results

- **Original Workflow Unchanged (SHA-256 Verified):** `True`
- **Python Syntax Checks Passed:** `True` (9 files)
- **Configuration Validation Passed:** `True`
- **Dependency & Reference Integrity Passed:** `True`
- **Output Schema Validation Passed (Optimized):** `False`

## 4. Runtime Execution & Baseline Evidence

### Fixed Historical Baseline Evidence
- **Source:** `historical_runtime_traces` | **Execution Mode:** `historical_recorded_execution` | **Re-executed:** `False` | **Groq API Calls:** `0`
- **Fixed Baseline Reference ID:** `hist_c86f1f3af77b` | **Trace Directory:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Ingestion_Traces_final\Ingestion_Traces\order_fulfillment_synthetic`
- **Input Matching:** matched=`10`, unmatched=`0`, excluded=`0`

### Fresh Optimized Subprocess Execution
- **Source:** `current_experiment` | **Execution Mode(s):** `['live_llm_execution']` | **Re-executed:** `True` | **Groq API Calls:** `14`
- **Trace Directory:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\order_fulfillment_synthetic\wp_20261125_204001_69771c\phase_a\workflow_parallelization\runtime_traces`
- **Optimized Runs:** runs=`2`, succeeded=`1`, failed=`1`, process_exit=`0`, status=`FAILED`, duration=`82.2314s`
- **Optimized API Errors Captured:** `1`
- **Incomplete / Invalid Replay Samples Flagged:** `0`
- **Workflow-Level vs. Agent-Level Latency (Historical Baseline vs. Fresh Optimized):** Baseline WF mean `11.6505s` (Agent mean `1.6616s`) -> Optimized WF mean `38.1256s` (Agent mean `5.731s`)

## 5. Output Quality Evaluation

| Quality Dimension | Baseline Status (Pass Rate) | Optimized Status (Pass Rate) |
| :--- | :--- | :--- |
| `structural_validity` | `passed` (100.0%) | `failed` (92.86%) |
| `correctness` | `unavailable` (unavailable) | `failed` (0.0%) |
| `completeness` | `passed` (100.0%) | `failed` (85.71%) |
| `consistency` | `unavailable` (unavailable) | `failed` (0.0%) |
| `instruction_adherence` | `passed` (100.0%) | `failed` (92.86%) |
| `semantic_quality` | `unavailable` (unavailable) | `unavailable` (unavailable) |

- **Identified Regressions:** `3`
  - `fulfillment_summary_agent.structural_validity`: 100.0% -> 50.0%
  - `fulfillment_summary_agent.completeness`: 100.0% -> 0.0%
  - `fulfillment_summary_agent.instruction_adherence`: 100.0% -> 50.0%

## 6. Before-and-After Comparison

| Metric | Baseline | Optimized | Improvement |
| :--- | :--- | :--- | :--- |
| Mean Workflow Latency | 11.6505s | 38.1256s | -227.24% |
| Median Workflow Latency | 11.6505s | 38.1256s | -227.24% |
| Mean Agent Latency | 1.6616s | 5.731s | -244.91% |
| Input Tokens | 5138.0 | 5027.0 | 2.16% |
| Output Tokens | 2393.5 | 4832.0 | -101.88% |
| Total Tokens | 7531.5 | 14886.0 | -97.65% |
| Execution Cost (estimated_from_model_catalog_using_api_reported_tokens) | $0.002207 | $0.00441 | -99.82% |
| Execution Success Rate | 100.0% | 50.0% | -50.0% |
| Structural Validity | 100.0% | 92.86% | -7.14% |
| Semantic Quality | `unavailable` | `unavailable` | unavailable |

## 7. Final Experiment Assessment

- **Final Assessment Status:** `failed`
- **Stage Flags:** `modification_applied=True`, `validation_passed=True`, `execution_passed=False`, `evaluation_passed=False`
- **Rationale:**
  - Optimized workflow runtime execution failed or produced incomplete runs.

### Candidate-Level Traceability

- `PARALLEL-INVENTORY_CHECK_AGENT-FRAUD_SCREEN_AGENT` (`workflow_parallelization`): applied=`True`, validation=`passed`, execution=`failed`, evaluation=`applied`