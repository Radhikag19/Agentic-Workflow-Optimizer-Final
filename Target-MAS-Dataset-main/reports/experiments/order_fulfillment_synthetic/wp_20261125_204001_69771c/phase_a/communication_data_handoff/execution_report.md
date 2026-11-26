# Sandbox Optimization Experiment Report: `order_fulfillment_synthetic`

## 1. Experiment Metadata

- **Workflow ID:** `order_fulfillment_synthetic`
- **Experiment ID:** `wp_20261125_204001_69771c__phase_a_communication_data_handoff`
- **Execution Backend:** `local_subprocess`
- **Python Executable:** `C:\Users\radhi\AppData\Local\Programs\Python\Python312\python.exe`
- **Execution Mode(s):** `['live_llm_execution']`
- **Runs Executed:** `2`
- **Baseline Model / Provider:** `openai/gpt-oss-120b` / `Groq` (key env: `GROQ_API_KEY_14`)
- **Model Overrides Applied:** `{}`
- **Approved Candidate IDs (6):** `HANDOFF-ORDER_INTAKE_AGENT-TO-INVENTORY_CHECK_AGENT`, `HANDOFF-ORDER_INTAKE_AGENT-TO-FRAUD_SCREEN_AGENT`, `HANDOFF-INVENTORY_CHECK_AGENT-TO-CARRIER_ROUTING_AGENT`, `HANDOFF-FRAUD_SCREEN_AGENT-TO-CARRIER_ROUTING_AGENT`, `HANDOFF-CARRIER_ROUTING_AGENT-TO-TAX_CLASSIFY_AGENT`, `HANDOFF-INVOICE_TAG_AGENT-TO-FULFILLMENT_SUMMARY_AGENT`
- **Original Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\Agents\order_fulfillment_synthetic`
- **Sandbox Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\order_fulfillment_synthetic\wp_20261125_204001_69771c\phase_a\communication_data_handoff\sandbox_workflow`
- **Generated At:** 2026-11-25T20:40:54.494538+00:00

## 2. Applied Modifications

- **Applied (6):** `HANDOFF-ORDER_INTAKE_AGENT-TO-INVENTORY_CHECK_AGENT`, `HANDOFF-ORDER_INTAKE_AGENT-TO-FRAUD_SCREEN_AGENT`, `HANDOFF-INVENTORY_CHECK_AGENT-TO-CARRIER_ROUTING_AGENT`, `HANDOFF-FRAUD_SCREEN_AGENT-TO-CARRIER_ROUTING_AGENT`, `HANDOFF-CARRIER_ROUTING_AGENT-TO-TAX_CLASSIFY_AGENT`, `HANDOFF-INVOICE_TAG_AGENT-TO-FULFILLMENT_SUMMARY_AGENT`
- **Failed (0):** None
- **Conflicts (0):** None
- **Manual Intervention (0):** None
- **Modified Files:** `sandbox_optimization_config.json`, `workflow.json`, `workflow.py`

- **`HANDOFF-ORDER_INTAKE_AGENT-TO-INVENTORY_CHECK_AGENT`** (`communication_data_handoff`) — Status: `applied` — Configured compact handoff projection on 'order_intake_agent->inventory_check_agent' retaining 7 field(s) and excluding ['request_id', 'customer_id', 'customer_tier', 'billing_country', 'shipping_speed', 'raw_audit_trail', 'debug_headers', 'internal_routing_flags', 'formatting_metadata'].
- **`HANDOFF-ORDER_INTAKE_AGENT-TO-FRAUD_SCREEN_AGENT`** (`communication_data_handoff`) — Status: `applied` — Configured compact handoff projection on 'order_intake_agent->fraud_screen_agent' retaining 7 field(s) and excluding ['request_id', 'shipping_region', 'warehouse_region', 'shipping_speed', 'sku_items', 'legacy_erp_dump', 'raw_audit_trail', 'debug_headers', 'formatting_metadata'].
- **`HANDOFF-INVENTORY_CHECK_AGENT-TO-CARRIER_ROUTING_AGENT`** (`communication_data_handoff`) — Status: `applied` — Configured compact handoff projection on 'inventory_check_agent->carrier_routing_agent' retaining 3 field(s) and excluding ['backorder_skus', 'inventory_note'].
- **`HANDOFF-FRAUD_SCREEN_AGENT-TO-CARRIER_ROUTING_AGENT`** (`communication_data_handoff`) — Status: `applied` — Configured compact handoff projection on 'fraud_screen_agent->carrier_routing_agent' retaining 3 field(s) and excluding ['screen_note'].
- **`HANDOFF-CARRIER_ROUTING_AGENT-TO-TAX_CLASSIFY_AGENT`** (`communication_data_handoff`) — Status: `applied` — Configured compact handoff projection on 'carrier_routing_agent->tax_classify_agent' retaining 3 field(s) and excluding ['estimated_days'].
- **`HANDOFF-INVOICE_TAG_AGENT-TO-FULFILLMENT_SUMMARY_AGENT`** (`communication_data_handoff`) — Status: `applied` — Configured compact handoff projection on 'invoice_tag_agent->fulfillment_summary_agent' retaining 3 field(s) and excluding ['billing_batch'].

## 3. Validation Results

- **Original Workflow Unchanged (SHA-256 Verified):** `True`
- **Python Syntax Checks Passed:** `True` (9 files)
- **Configuration Validation Passed:** `True`
- **Dependency & Reference Integrity Passed:** `True`
- **Output Schema Validation Passed (Optimized):** `True`

## 4. Runtime Execution & Baseline Evidence

### Fixed Historical Baseline Evidence
- **Source:** `historical_runtime_traces` | **Execution Mode:** `historical_recorded_execution` | **Re-executed:** `False` | **Groq API Calls:** `0`
- **Fixed Baseline Reference ID:** `hist_c86f1f3af77b` | **Trace Directory:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Ingestion_Traces_final\Ingestion_Traces\order_fulfillment_synthetic`
- **Input Matching:** matched=`10`, unmatched=`0`, excluded=`0`

### Fresh Optimized Subprocess Execution
- **Source:** `current_experiment` | **Execution Mode(s):** `['live_llm_execution']` | **Re-executed:** `True` | **Groq API Calls:** `14`
- **Trace Directory:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\order_fulfillment_synthetic\wp_20261125_204001_69771c\phase_a\communication_data_handoff\runtime_traces`
- **Optimized Runs:** runs=`2`, succeeded=`2`, failed=`0`, process_exit=`0`, status=`SUCCESS`, duration=`33.1719s`
- **Optimized API Errors Captured:** `0`
- **Incomplete / Invalid Replay Samples Flagged:** `0`
- **Workflow-Level vs. Agent-Level Latency (Historical Baseline vs. Fresh Optimized):** Baseline WF mean `11.6505s` (Agent mean `1.6616s`) -> Optimized WF mean `16.5311s` (Agent mean `2.3558s`)

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
| Mean Workflow Latency | 11.6505s | 16.5311s | -41.89% |
| Median Workflow Latency | 11.6505s | 16.5311s | -41.89% |
| Mean Agent Latency | 1.6616s | 2.3558s | -41.78% |
| Input Tokens | 5138.0 | 4937.0 | 3.91% |
| Output Tokens | 2393.5 | 4783.0 | -99.83% |
| Total Tokens | 7531.5 | 14657.0 | -94.61% |
| Execution Cost (estimated_from_model_catalog_using_api_reported_tokens) | $0.002207 | $0.004351 | -97.15% |
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
- `HANDOFF-INVENTORY_CHECK_AGENT-TO-CARRIER_ROUTING_AGENT` (`communication_data_handoff`): applied=`True`, validation=`passed`, execution=`passed`, evaluation=`applied_requires_further_validation`
- `HANDOFF-FRAUD_SCREEN_AGENT-TO-CARRIER_ROUTING_AGENT` (`communication_data_handoff`): applied=`True`, validation=`passed`, execution=`passed`, evaluation=`applied_requires_further_validation`
- `HANDOFF-CARRIER_ROUTING_AGENT-TO-TAX_CLASSIFY_AGENT` (`communication_data_handoff`): applied=`True`, validation=`passed`, execution=`passed`, evaluation=`applied_requires_further_validation`
- `HANDOFF-INVOICE_TAG_AGENT-TO-FULFILLMENT_SUMMARY_AGENT` (`communication_data_handoff`): applied=`True`, validation=`passed`, execution=`passed`, evaluation=`applied_requires_further_validation`