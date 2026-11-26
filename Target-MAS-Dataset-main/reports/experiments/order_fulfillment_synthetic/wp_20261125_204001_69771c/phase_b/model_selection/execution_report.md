# Sandbox Optimization Experiment Report: `order_fulfillment_synthetic`

## 1. Experiment Metadata

- **Workflow ID:** `order_fulfillment_synthetic`
- **Experiment ID:** `wp_20261125_204001_69771c__phase_b_model_selection`
- **Execution Backend:** `local_subprocess`
- **Python Executable:** `C:\Users\radhi\AppData\Local\Programs\Python\Python312\python.exe`
- **Execution Mode(s):** `['live_llm_execution']`
- **Runs Executed:** `2`
- **Baseline Model / Provider:** `openai/gpt-oss-120b` / `Groq` (key env: `GROQ_API_KEY_14`)
- **Model Overrides Applied:** `{'order_intake_agent': {'previous_model': 'openai/gpt-oss-120b', 'updated_model': 'openai/gpt-oss-20b', 'provider': 'Groq', 'candidate_id': 'MODEL-ORDER_INTAKE_AGENT'}}`
- **Approved Candidate IDs (1):** `MODEL-ORDER_INTAKE_AGENT`
- **Original Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\Agents\order_fulfillment_synthetic`
- **Sandbox Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\order_fulfillment_synthetic\wp_20261125_204001_69771c\phase_b\model_selection\sandbox_workflow`
- **Generated At:** 2026-11-25T20:48:06.832801+00:00

## 2. Applied Modifications

- **Applied (1):** `MODEL-ORDER_INTAKE_AGENT`
- **Failed (0):** None
- **Conflicts (0):** None
- **Manual Intervention (0):** None
- **Modified Files:** `order_intake_agent.py`, `sandbox_optimization_config.json`, `workflow.json`

- **`MODEL-ORDER_INTAKE_AGENT`** (`model_selection`) — Status: `applied` — Updated model configuration for ['order_intake_agent'] to 'openai/gpt-oss-20b' (provider=Groq, source=jev_agent2_cached_langgraph) in sandbox while preserving API key bindings.

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
- **Trace Directory:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\order_fulfillment_synthetic\wp_20261125_204001_69771c\phase_b\model_selection\runtime_traces`
- **Optimized Runs:** runs=`2`, succeeded=`2`, failed=`0`, process_exit=`0`, status=`SUCCESS`, duration=`54.8169s`
- **Optimized API Errors Captured:** `0`
- **Incomplete / Invalid Replay Samples Flagged:** `0`
- **Workflow-Level vs. Agent-Level Latency (Historical Baseline vs. Fresh Optimized):** Baseline WF mean `11.6505s` (Agent mean `1.6616s`) -> Optimized WF mean `27.315s` (Agent mean `3.8988s`)

## 5. Output Quality Evaluation

| Quality Dimension | Baseline Status (Pass Rate) | Optimized Status (Pass Rate) |
| :--- | :--- | :--- |
| `structural_validity` | `passed` (100.0%) | `passed` (100.0%) |
| `correctness` | `unavailable` (unavailable) | `unavailable` (unavailable) |
| `completeness` | `passed` (100.0%) | `failed` (92.86%) |
| `consistency` | `unavailable` (unavailable) | `unavailable` (unavailable) |
| `instruction_adherence` | `passed` (100.0%) | `passed` (100.0%) |
| `semantic_quality` | `unavailable` (unavailable) | `unavailable` (unavailable) |

- **Identified Regressions:** `1`
  - `fulfillment_summary_agent.completeness`: 100.0% -> 50.0%

## 6. Before-and-After Comparison

| Metric | Baseline | Optimized | Improvement |
| :--- | :--- | :--- | :--- |
| Mean Workflow Latency | 11.6505s | 27.315s | -134.45% |
| Median Workflow Latency | 11.6505s | 27.315s | -134.45% |
| Mean Agent Latency | 1.6616s | 3.8988s | -134.64% |
| Input Tokens | 5138.0 | 5390.5 | -4.91% |
| Output Tokens | 2393.5 | 4580.0 | -91.35% |
| Total Tokens | 7531.5 | 15361.0 | -103.96% |
| Execution Cost (estimated_from_model_catalog_using_api_reported_tokens) | $0.002207 | $0.004045 | -83.28% |
| Execution Success Rate | 100.0% | 100.0% | 0.0% |
| Structural Validity | 100.0% | 100.0% | 0.0% |
| Semantic Quality | `unavailable` | `unavailable` | unavailable |

## 7. Final Experiment Assessment

- **Final Assessment Status:** `quality_regression`
- **Stage Flags:** `modification_applied=True`, `validation_passed=True`, `execution_passed=True`, `evaluation_passed=False`
- **Rationale:**
  - Semantic quality evaluation is unavailable.
  - Quality regression detected on 1 agent metric(s): fulfillment_summary_agent.completeness

### Candidate-Level Traceability

- `MODEL-ORDER_INTAKE_AGENT` (`model_selection`): applied=`True`, validation=`passed`, execution=`passed`, evaluation=`applied_requires_further_validation`