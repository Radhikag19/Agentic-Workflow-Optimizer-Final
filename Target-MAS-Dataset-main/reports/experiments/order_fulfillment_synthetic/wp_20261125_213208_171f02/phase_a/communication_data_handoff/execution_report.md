# Sandbox Optimization Experiment Report: `order_fulfillment_synthetic`

## 1. Experiment Metadata

- **Workflow ID:** `order_fulfillment_synthetic`
- **Experiment ID:** `wp_20261125_213208_171f02__phase_a_communication_data_handoff`
- **Execution Backend:** `local_subprocess`
- **Python Executable:** `C:\Users\radhi\AppData\Local\Programs\Python\Python312\python.exe`
- **Execution Mode(s):** `['live_llm_execution']`
- **Runs Executed:** `2`
- **Baseline Model / Provider:** `openai/gpt-oss-120b` / `Groq` (key env: `GROQ_API_KEY_14`)
- **Model Overrides Applied:** `{}`
- **Approved Candidate IDs (2):** `HANDOFF-ORDER_INTAKE_AGENT-TO-INVENTORY_CHECK_AGENT`, `HANDOFF-ORDER_INTAKE_AGENT-TO-FRAUD_SCREEN_AGENT`
- **Original Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\Agents\order_fulfillment_synthetic`
- **Sandbox Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\order_fulfillment_synthetic\wp_20261125_213208_171f02\phase_a\communication_data_handoff\sandbox_workflow`
- **Generated At:** 2026-11-25T21:33:23.196048+00:00

## 2. Applied Modifications

- **Applied (2):** `HANDOFF-ORDER_INTAKE_AGENT-TO-INVENTORY_CHECK_AGENT`, `HANDOFF-ORDER_INTAKE_AGENT-TO-FRAUD_SCREEN_AGENT`
- **Failed (0):** None
- **Conflicts (0):** None
- **Manual Intervention (0):** None
- **Modified Files:** `sandbox_optimization_config.json`, `workflow.json`, `workflow.py`

- **`HANDOFF-ORDER_INTAKE_AGENT-TO-INVENTORY_CHECK_AGENT`** (`communication_data_handoff`) — Status: `applied` — Configured compact handoff projection on 'order_intake_agent->inventory_check_agent' retaining 7 field(s) and excluding ['request_id', 'customer_id', 'customer_tier', 'billing_country', 'shipping_speed', 'raw_audit_trail', 'debug_headers', 'internal_routing_flags', 'formatting_metadata'].
- **`HANDOFF-ORDER_INTAKE_AGENT-TO-FRAUD_SCREEN_AGENT`** (`communication_data_handoff`) — Status: `applied` — Configured compact handoff projection on 'order_intake_agent->fraud_screen_agent' retaining 7 field(s) and excluding ['request_id', 'shipping_region', 'warehouse_region', 'shipping_speed', 'sku_items', 'legacy_erp_dump', 'raw_audit_trail', 'debug_headers', 'formatting_metadata'].

## 3. Validation Results

- **Original Workflow Unchanged (SHA-256 Verified):** `True`
- **Python Syntax Checks Passed:** `True` (9 files)
- **Configuration Validation Passed:** `True`
- **Dependency & Reference Integrity Passed:** `True`
- **Output Schema Validation Passed (Optimized):** `True`

## 4. Runtime Execution & Baseline Evidence

### Fixed Historical Baseline Evidence
- **Source:** `historical_runtime_traces` | **Execution Mode:** `historical_recorded_execution` | **Re-executed:** `False` | **Groq API Calls:** `0`
- **Fixed Baseline Reference ID:** `hist_859e698746d5` | **Trace Directory:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Ingestion_Traces_final\Ingestion_Traces\order_fulfillment_synthetic`
- **Input Matching:** matched=`10`, unmatched=`0`, excluded=`0`

### Fresh Optimized Subprocess Execution
- **Source:** `current_experiment` | **Execution Mode(s):** `['live_llm_execution']` | **Re-executed:** `True` | **Groq API Calls:** `14`
- **Trace Directory:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\order_fulfillment_synthetic\wp_20261125_213208_171f02\phase_a\communication_data_handoff\runtime_traces`
- **Optimized Runs:** runs=`2`, succeeded=`2`, failed=`0`, process_exit=`0`, status=`SUCCESS`, duration=`58.6353s`
- **Optimized API Errors Captured:** `0`
- **Incomplete / Invalid Replay Samples Flagged:** `0`
- **Workflow-Level vs. Agent-Level Latency (Historical Baseline vs. Fresh Optimized):** Baseline WF mean `11.5005s` (Agent mean `1.6416s`) -> Optimized WF mean `29.2155s` (Agent mean `4.1702s`)

## 5. Output Quality Evaluation

| Quality Dimension | Baseline Status (Pass Rate) | Optimized Status (Pass Rate) |
| :--- | :--- | :--- |
| `structural_validity` | `passed` (100.0%) | `passed` (100.0%) |
| `correctness` | `unavailable` (unavailable) | `unavailable` (unavailable) |
| `completeness` | `passed` (100.0%) | `passed` (100.0%) |
| `consistency` | `unavailable` (unavailable) | `unavailable` (unavailable) |
| `instruction_adherence` | `passed` (100.0%) | `passed` (100.0%) |
| `semantic_quality` | `unavailable` (unavailable) | `unavailable` (unavailable) |

- **Identified Regressions:** `0`

## 6. Before-and-After Comparison

| Metric | Baseline | Optimized | Improvement |
| :--- | :--- | :--- | :--- |
| Mean Workflow Latency | 11.5005s | 29.2155s | -154.04% |
| Median Workflow Latency | 11.5005s | 29.2155s | -154.04% |
| Mean Agent Latency | 1.6416s | 4.1702s | -154.03% |
| Input Tokens | 6414.5 | 6168.0 | 3.84% |
| Output Tokens | 2939.5 | 5720.0 | -94.59% |
| Total Tokens | 9354.0 | 18056.0 | -93.03% |
| Execution Cost (estimated_from_model_catalog_using_api_reported_tokens) | $0.002726 | $0.005282 | -93.76% |
| Execution Success Rate | 100.0% | 100.0% | 0.0% |
| Structural Validity | 100.0% | 100.0% | 0.0% |
| Semantic Quality | `unavailable` | `unavailable` | unavailable |

## 7. Final Experiment Assessment

- **Final Assessment Status:** `no_significant_improvement`
- **Stage Flags:** `modification_applied=True`, `validation_passed=True`, `execution_passed=True`, `evaluation_passed=True`
- **Rationale:**
  - Semantic quality evaluation is unavailable.
  - Workflow executed reliably with acceptable quality, but no >=2% latency/token/cost gain observed.

### Candidate-Level Traceability

- `HANDOFF-ORDER_INTAKE_AGENT-TO-INVENTORY_CHECK_AGENT` (`communication_data_handoff`): applied=`True`, validation=`passed`, execution=`passed`, evaluation=`applied_requires_further_validation`
- `HANDOFF-ORDER_INTAKE_AGENT-TO-FRAUD_SCREEN_AGENT` (`communication_data_handoff`): applied=`True`, validation=`passed`, execution=`passed`, evaluation=`applied_requires_further_validation`