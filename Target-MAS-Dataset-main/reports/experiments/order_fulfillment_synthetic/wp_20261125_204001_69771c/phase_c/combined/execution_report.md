# Sandbox Optimization Experiment Report: `order_fulfillment_synthetic`

## 1. Experiment Metadata

- **Workflow ID:** `order_fulfillment_synthetic`
- **Experiment ID:** `wp_20261125_204001_69771c__phase_c_combined`
- **Execution Backend:** `local_subprocess`
- **Python Executable:** `C:\Users\radhi\AppData\Local\Programs\Python\Python312\python.exe`
- **Execution Mode(s):** `['live_llm_execution']`
- **Runs Executed:** `2`
- **Baseline Model / Provider:** `openai/gpt-oss-120b` / `Groq` (key env: `GROQ_API_KEY_14`)
- **Model Overrides Applied:** `{'order_intake_agent': {'previous_model': 'openai/gpt-oss-120b', 'updated_model': 'openai/gpt-oss-20b', 'provider': 'Groq', 'candidate_id': 'MODEL-ORDER_INTAKE_AGENT'}}`
- **Approved Candidate IDs (6):** `CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT`, `CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT-INVOICE_TAG_AGENT`, `CONSOLIDATE-TAX_CLASSIFY_AGENT-INVOICE_TAG_AGENT`, `MODEL-ORDER_INTAKE_AGENT`, `PROMPT-OPT-CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT-INVOICE_TAG_AGENT`, `PROMPT-OPT-FULFILLMENT_SUMMARY_AGENT`
- **Original Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\Agents\order_fulfillment_synthetic`
- **Sandbox Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\order_fulfillment_synthetic\wp_20261125_204001_69771c\phase_c\combined\sandbox_workflow`
- **Generated At:** 2026-11-25T20:49:09.329904+00:00

## 2. Applied Modifications

- **Applied (2):** `MODEL-ORDER_INTAKE_AGENT`, `PROMPT-OPT-FULFILLMENT_SUMMARY_AGENT`
- **Failed (0):** None
- **Conflicts (4):** `CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT`, `CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT-INVOICE_TAG_AGENT`, `CONSOLIDATE-TAX_CLASSIFY_AGENT-INVOICE_TAG_AGENT`, `PROMPT-OPT-CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT-INVOICE_TAG_AGENT`
- **Manual Intervention (0):** None
- **Modified Files:** `fulfillment_summary_agent.py`, `order_intake_agent.py`, `sandbox_optimization_config.json`, `workflow.json`

- **`CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT`** (`agent_consolidation`) — Status: `conflict` — Skipped due to detected modification conflict: Overlapping agent consolidation target 'carrier_routing_agent' across CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT and CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT-INVOICE_TAG_AGENT.
- **`CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT-INVOICE_TAG_AGENT`** (`agent_consolidation`) — Status: `conflict` — Skipped due to detected modification conflict: Overlapping agent consolidation target 'carrier_routing_agent' across CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT and CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT-INVOICE_TAG_AGENT.
- **`CONSOLIDATE-TAX_CLASSIFY_AGENT-INVOICE_TAG_AGENT`** (`agent_consolidation`) — Status: `conflict` — Skipped due to detected modification conflict: Overlapping agent consolidation target 'tax_classify_agent' across CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT and CONSOLIDATE-TAX_CLASSIFY_AGENT-INVOICE_TAG_AGENT.
- **`MODEL-ORDER_INTAKE_AGENT`** (`model_selection`) — Status: `applied` — Updated model configuration for ['order_intake_agent'] to 'openai/gpt-oss-20b' (provider=Groq, source=jev_agent2_cached_langgraph) in sandbox while preserving API key bindings.
- **`PROMPT-OPT-CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT-INVOICE_TAG_AGENT`** (`prompt_optimization`) — Status: `conflict` — Skipped due to detected modification conflict: Agent 'carrier_routing_agent' is targeted by consolidation 'CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT' and prompt_optimization 'PROMPT-OPT-CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT-INVOICE_TAG_AGENT'.
- **`PROMPT-OPT-FULFILLMENT_SUMMARY_AGENT`** (`prompt_optimization`) — Status: `applied` — Applied OPTIMIZED_PROMPT exclusively to ['fulfillment_summary_agent'] inside sandbox.

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
- **Trace Directory:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\order_fulfillment_synthetic\wp_20261125_204001_69771c\phase_c\combined\runtime_traces`
- **Optimized Runs:** runs=`2`, succeeded=`0`, failed=`2`, process_exit=`0`, status=`FAILED`, duration=`43.1297s`
- **Optimized API Errors Captured:** `2`
- **Incomplete / Invalid Replay Samples Flagged:** `0`
- **Workflow-Level vs. Agent-Level Latency (Historical Baseline vs. Fresh Optimized):** Baseline WF mean `11.6505s` (Agent mean `1.6616s`) -> Optimized WF mean `unavailable` (Agent mean `unavailable`)

## 5. Output Quality Evaluation

| Quality Dimension | Baseline Status (Pass Rate) | Optimized Status (Pass Rate) |
| :--- | :--- | :--- |
| `structural_validity` | `passed` (100.0%) | `failed` (85.71%) |
| `correctness` | `unavailable` (unavailable) | `failed` (0.0%) |
| `completeness` | `passed` (100.0%) | `failed` (85.71%) |
| `consistency` | `unavailable` (unavailable) | `failed` (0.0%) |
| `instruction_adherence` | `passed` (100.0%) | `failed` (85.71%) |
| `semantic_quality` | `unavailable` (unavailable) | `unavailable` (unavailable) |

- **Identified Regressions:** `3`
  - `fulfillment_summary_agent.structural_validity`: 100.0% -> 0.0%
  - `fulfillment_summary_agent.completeness`: 100.0% -> 0.0%
  - `fulfillment_summary_agent.instruction_adherence`: 100.0% -> 0.0%

## 6. Before-and-After Comparison

| Metric | Baseline | Optimized | Improvement |
| :--- | :--- | :--- | :--- |
| Mean Workflow Latency | 11.6505s | unavailable | unavailable |
| Median Workflow Latency | 11.6505s | unavailable | unavailable |
| Mean Agent Latency | 1.6616s | unavailable | unavailable |
| Input Tokens | 5138.0 | unavailable | unavailable |
| Output Tokens | 2393.5 | unavailable | unavailable |
| Total Tokens | 7531.5 | unavailable | unavailable |
| Execution Cost (estimated_from_model_catalog_using_api_reported_tokens) | $0.002207 | $None | unavailable |
| Execution Success Rate | 100.0% | 0.0% | -100.0% |
| Structural Validity | 100.0% | 85.71% | -14.29% |
| Semantic Quality | `unavailable` | `unavailable` | unavailable |

## 7. Final Experiment Assessment

- **Final Assessment Status:** `failed`
- **Stage Flags:** `modification_applied=True`, `validation_passed=True`, `execution_passed=False`, `evaluation_passed=False`
- **Rationale:**
  - Optimized workflow runtime execution failed or produced incomplete runs.

### Candidate-Level Traceability

- `CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT` (`agent_consolidation`): applied=`False`, validation=`passed`, execution=`failed`, evaluation=`failed`
- `CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT-INVOICE_TAG_AGENT` (`agent_consolidation`): applied=`False`, validation=`passed`, execution=`failed`, evaluation=`failed`
- `CONSOLIDATE-TAX_CLASSIFY_AGENT-INVOICE_TAG_AGENT` (`agent_consolidation`): applied=`False`, validation=`passed`, execution=`failed`, evaluation=`failed`
- `MODEL-ORDER_INTAKE_AGENT` (`model_selection`): applied=`True`, validation=`passed`, execution=`failed`, evaluation=`applied`
- `PROMPT-OPT-CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT-INVOICE_TAG_AGENT` (`prompt_optimization`): applied=`False`, validation=`passed`, execution=`failed`, evaluation=`failed`
- `PROMPT-OPT-FULFILLMENT_SUMMARY_AGENT` (`prompt_optimization`): applied=`True`, validation=`passed`, execution=`failed`, evaluation=`applied`