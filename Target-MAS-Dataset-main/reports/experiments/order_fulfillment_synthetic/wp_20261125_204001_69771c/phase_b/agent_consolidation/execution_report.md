# Sandbox Optimization Experiment Report: `order_fulfillment_synthetic`

## 1. Experiment Metadata

- **Workflow ID:** `order_fulfillment_synthetic`
- **Experiment ID:** `wp_20261125_204001_69771c__phase_b_agent_consolidation`
- **Execution Backend:** `local_subprocess`
- **Python Executable:** `C:\Users\radhi\AppData\Local\Programs\Python\Python312\python.exe`
- **Execution Mode(s):** `['live_llm_execution']`
- **Runs Executed:** `2`
- **Baseline Model / Provider:** `openai/gpt-oss-120b` / `Groq` (key env: `GROQ_API_KEY_14`)
- **Model Overrides Applied:** `{}`
- **Approved Candidate IDs (3):** `CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT`, `CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT-INVOICE_TAG_AGENT`, `CONSOLIDATE-TAX_CLASSIFY_AGENT-INVOICE_TAG_AGENT`
- **Original Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\Agents\order_fulfillment_synthetic`
- **Sandbox Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\order_fulfillment_synthetic\wp_20261125_204001_69771c\phase_b\agent_consolidation\sandbox_workflow`
- **Generated At:** 2026-11-25T20:46:43.196971+00:00

## 2. Applied Modifications

- **Applied (0):** None
- **Failed (0):** None
- **Conflicts (3):** `CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT`, `CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT-INVOICE_TAG_AGENT`, `CONSOLIDATE-TAX_CLASSIFY_AGENT-INVOICE_TAG_AGENT`
- **Manual Intervention (0):** None
- **Modified Files:** None

- **`CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT`** (`agent_consolidation`) — Status: `conflict` — Skipped due to detected modification conflict: Overlapping agent consolidation target 'carrier_routing_agent' across CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT and CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT-INVOICE_TAG_AGENT.
- **`CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT-INVOICE_TAG_AGENT`** (`agent_consolidation`) — Status: `conflict` — Skipped due to detected modification conflict: Overlapping agent consolidation target 'carrier_routing_agent' across CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT and CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT-INVOICE_TAG_AGENT.
- **`CONSOLIDATE-TAX_CLASSIFY_AGENT-INVOICE_TAG_AGENT`** (`agent_consolidation`) — Status: `conflict` — Skipped due to detected modification conflict: Overlapping agent consolidation target 'tax_classify_agent' across CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT and CONSOLIDATE-TAX_CLASSIFY_AGENT-INVOICE_TAG_AGENT.

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
- **Trace Directory:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\order_fulfillment_synthetic\wp_20261125_204001_69771c\phase_b\agent_consolidation\runtime_traces`
- **Optimized Runs:** runs=`2`, succeeded=`2`, failed=`0`, process_exit=`0`, status=`SUCCESS`, duration=`84.7989s`
- **Optimized API Errors Captured:** `0`
- **Incomplete / Invalid Replay Samples Flagged:** `0`
- **Workflow-Level vs. Agent-Level Latency (Historical Baseline vs. Fresh Optimized):** Baseline WF mean `11.6505s` (Agent mean `1.6616s`) -> Optimized WF mean `42.2737s` (Agent mean `6.0347s`)

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
| Mean Workflow Latency | 11.6505s | 42.2737s | -262.85% |
| Median Workflow Latency | 11.6505s | 42.2737s | -262.85% |
| Mean Agent Latency | 1.6616s | 6.0347s | -263.19% |
| Input Tokens | 5138.0 | 5136.5 | 0.03% |
| Output Tokens | 2393.5 | 5408.0 | -125.95% |
| Total Tokens | 7531.5 | 15681.0 | -108.21% |
| Execution Cost (estimated_from_model_catalog_using_api_reported_tokens) | $0.002207 | $0.004786 | -116.86% |
| Execution Success Rate | 100.0% | 100.0% | 0.0% |
| Structural Validity | 100.0% | 100.0% | 0.0% |
| Semantic Quality | `unavailable` | `unavailable` | unavailable |

## 7. Final Experiment Assessment

- **Final Assessment Status:** `failed`
- **Stage Flags:** `modification_applied=False`, `validation_passed=True`, `execution_passed=True`, `evaluation_passed=False`
- **Rationale:**
  - No approved modifications were applied.

### Candidate-Level Traceability

- `CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT` (`agent_consolidation`): applied=`False`, validation=`passed`, execution=`passed`, evaluation=`failed`
- `CONSOLIDATE-CARRIER_ROUTING_AGENT-TAX_CLASSIFY_AGENT-INVOICE_TAG_AGENT` (`agent_consolidation`): applied=`False`, validation=`passed`, execution=`passed`, evaluation=`failed`
- `CONSOLIDATE-TAX_CLASSIFY_AGENT-INVOICE_TAG_AGENT` (`agent_consolidation`): applied=`False`, validation=`passed`, execution=`passed`, evaluation=`failed`