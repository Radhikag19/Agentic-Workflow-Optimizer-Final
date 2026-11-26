# Sandbox Optimization Experiment Report: `order_fulfillment_synthetic`

## 1. Experiment Metadata

- **Workflow ID:** `order_fulfillment_synthetic`
- **Experiment ID:** `wp_20261125_213208_171f02__phase_c_combined`
- **Execution Backend:** `local_subprocess`
- **Python Executable:** `C:\Users\radhi\AppData\Local\Programs\Python\Python312\python.exe`
- **Execution Mode(s):** `['live_llm_execution']`
- **Runs Executed:** `2`
- **Baseline Model / Provider:** `openai/gpt-oss-120b` / `Groq` (key env: `GROQ_API_KEY_14`)
- **Model Overrides Applied:** `{'order_intake_agent': {'previous_model': 'openai/gpt-oss-120b', 'updated_model': 'openai/gpt-oss-20b', 'provider': 'Groq', 'candidate_id': 'MODEL-ORDER_INTAKE_AGENT'}}`
- **Approved Candidate IDs (5):** `CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT`, `MODEL-ORDER_INTAKE_AGENT`, `PROMPT-OPT-FULFILLMENT_SUMMARY_AGENT`, `HANDOFF-ORDER_INTAKE_AGENT-TO-INVENTORY_CHECK_AGENT`, `HANDOFF-ORDER_INTAKE_AGENT-TO-FRAUD_SCREEN_AGENT`
- **Original Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\Agents\order_fulfillment_synthetic`
- **Sandbox Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\order_fulfillment_synthetic\wp_20261125_213208_171f02\phase_c\combined\sandbox_workflow`
- **Generated At:** 2026-11-25T21:42:39.608728+00:00

## 2. Applied Modifications

- **Applied (5):** `CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT`, `MODEL-ORDER_INTAKE_AGENT`, `PROMPT-OPT-FULFILLMENT_SUMMARY_AGENT`, `HANDOFF-ORDER_INTAKE_AGENT-TO-INVENTORY_CHECK_AGENT`, `HANDOFF-ORDER_INTAKE_AGENT-TO-FRAUD_SCREEN_AGENT`
- **Failed (0):** None
- **Conflicts (0):** None
- **Manual Intervention (0):** None
- **Modified Files:** `consolidated_carrier_routing_tax_classify.py`, `fulfillment_summary_agent.py`, `order_intake_agent.py`, `sandbox_optimization_config.json`, `workflow.json`, `workflow.py`

- **`CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT`** (`agent_consolidation`) — Status: `applied` — Consolidated ['carrier_routing_agent', 'tax_classify_agent'] into 'consolidated_carrier_routing_tax_classify', rewired downstream dependencies, and persisted unified prompt inside sandbox.
- **`MODEL-ORDER_INTAKE_AGENT`** (`model_selection`) — Status: `applied` — Updated model configuration for ['order_intake_agent'] to 'openai/gpt-oss-20b' (provider=Groq, source=jev_agent2_cached_langgraph) in sandbox while preserving API key bindings.
- **`PROMPT-OPT-FULFILLMENT_SUMMARY_AGENT`** (`prompt_optimization`) — Status: `applied` — Applied OPTIMIZED_PROMPT exclusively to ['fulfillment_summary_agent'] inside sandbox.
- **`HANDOFF-ORDER_INTAKE_AGENT-TO-INVENTORY_CHECK_AGENT`** (`communication_data_handoff`) — Status: `applied` — Configured compact handoff projection on 'order_intake_agent->inventory_check_agent' retaining 7 field(s) and excluding ['request_id', 'customer_id', 'customer_tier', 'billing_country', 'shipping_speed', 'raw_audit_trail', 'debug_headers', 'internal_routing_flags', 'formatting_metadata'].
- **`HANDOFF-ORDER_INTAKE_AGENT-TO-FRAUD_SCREEN_AGENT`** (`communication_data_handoff`) — Status: `applied` — Configured compact handoff projection on 'order_intake_agent->fraud_screen_agent' retaining 7 field(s) and excluding ['request_id', 'shipping_region', 'warehouse_region', 'shipping_speed', 'sku_items', 'legacy_erp_dump', 'raw_audit_trail', 'debug_headers', 'formatting_metadata'].

## 3. Validation Results

- **Original Workflow Unchanged (SHA-256 Verified):** `True`
- **Python Syntax Checks Passed:** `True` (10 files)
- **Configuration Validation Passed:** `True`
- **Dependency & Reference Integrity Passed:** `True`
- **Output Schema Validation Passed (Optimized):** `True`

## 4. Runtime Execution & Baseline Evidence

### Fixed Historical Baseline Evidence
- **Source:** `historical_runtime_traces` | **Execution Mode:** `historical_recorded_execution` | **Re-executed:** `False` | **Groq API Calls:** `0`
- **Fixed Baseline Reference ID:** `hist_859e698746d5` | **Trace Directory:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Ingestion_Traces_final\Ingestion_Traces\order_fulfillment_synthetic`
- **Input Matching:** matched=`10`, unmatched=`0`, excluded=`0`

### Fresh Optimized Subprocess Execution
- **Source:** `current_experiment` | **Execution Mode(s):** `['live_llm_execution']` | **Re-executed:** `True` | **Groq API Calls:** `12`
- **Trace Directory:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\order_fulfillment_synthetic\wp_20261125_213208_171f02\phase_c\combined\runtime_traces`
- **Optimized Runs:** runs=`2`, succeeded=`2`, failed=`0`, process_exit=`0`, status=`SUCCESS`, duration=`52.4733s`
- **Optimized API Errors Captured:** `0`
- **Incomplete / Invalid Replay Samples Flagged:** `0`
- **Workflow-Level vs. Agent-Level Latency (Historical Baseline vs. Fresh Optimized):** Baseline WF mean `11.5005s` (Agent mean `1.6416s`) -> Optimized WF mean `26.1607s` (Agent mean `4.3562s`)

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
| Mean Workflow Latency | 11.5005s | 26.1607s | -127.47% |
| Median Workflow Latency | 11.5005s | 26.1607s | -127.47% |
| Mean Agent Latency | 1.6416s | 4.3562s | -165.36% |
| Input Tokens | 6414.5 | 4611.5 | 28.11% |
| Output Tokens | 2939.5 | 5063.0 | -72.24% |
| Total Tokens | 9354.0 | 14286.0 | -52.73% |
| Execution Cost (estimated_from_model_catalog_using_api_reported_tokens) | $0.002726 | $0.003885 | -42.52% |
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

- `CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT` (`agent_consolidation`): applied=`True`, validation=`passed`, execution=`passed`, evaluation=`applied_requires_further_validation`
- `MODEL-ORDER_INTAKE_AGENT` (`model_selection`): applied=`True`, validation=`passed`, execution=`passed`, evaluation=`applied_requires_further_validation`
- `PROMPT-OPT-FULFILLMENT_SUMMARY_AGENT` (`prompt_optimization`): applied=`True`, validation=`passed`, execution=`passed`, evaluation=`applied_requires_further_validation`
- `HANDOFF-ORDER_INTAKE_AGENT-TO-INVENTORY_CHECK_AGENT` (`communication_data_handoff`): applied=`True`, validation=`passed`, execution=`passed`, evaluation=`applied_requires_further_validation`
- `HANDOFF-ORDER_INTAKE_AGENT-TO-FRAUD_SCREEN_AGENT` (`communication_data_handoff`): applied=`True`, validation=`passed`, execution=`passed`, evaluation=`applied_requires_further_validation`