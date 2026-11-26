# Sandbox Optimization Experiment Report: `recruitment_screening`

## 1. Experiment Metadata

- **Workflow ID:** `recruitment_screening`
- **Experiment ID:** `wp_20261125_172742_e1478e__dim_workflow_parallelization`
- **Execution Backend:** `local_subprocess`
- **Python Executable:** `C:\Users\radhi\AppData\Local\Programs\Python\Python312\python.exe`
- **Execution Mode(s):** `['live_llm_execution']`
- **Runs Executed:** `2`
- **Baseline Model / Provider:** `openai/gpt-oss-120b` / `Groq` (key env: `GROQ_API_KEY_5`)
- **Model Overrides Applied:** `{}`
- **Approved Candidate IDs (1):** `PARALLEL-QUALIFICATION_AGENT-JOB_CRITERIA_AGENT`
- **Original Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\Agents\recruitment_screening`
- **Sandbox Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\recruitment_screening\wp_20261125_172742_e1478e\per_dimension\workflow_parallelization\sandbox_workflow`
- **Generated At:** 2026-11-25T17:35:49.700746+00:00

## 2. Applied Modifications

- **Applied (1):** `PARALLEL-QUALIFICATION_AGENT-JOB_CRITERIA_AGENT`
- **Failed (0):** None
- **Conflicts (0):** None
- **Manual Intervention (0):** None
- **Modified Files:** `sandbox_optimization_config.json`, `workflow.json`, `workflow.py`

- **`PARALLEL-QUALIFICATION_AGENT-JOB_CRITERIA_AGENT`** (`workflow_parallelization`) — Status: `applied` — Configured concurrent scatter-gather group ['qualification_agent', 'job_criteria_agent'] in sandbox workflow after verifying strict DAG & I/O independence.

## 3. Validation Results

- **Original Workflow Unchanged (SHA-256 Verified):** `True`
- **Python Syntax Checks Passed:** `True` (10 files)
- **Configuration Validation Passed:** `True`
- **Dependency & Reference Integrity Passed:** `True`
- **Output Schema Validation Passed (Optimized):** `False`

## 4. Runtime Execution & Baseline Evidence

### Fixed Historical Baseline Evidence
- **Source:** `historical_runtime_traces` | **Execution Mode:** `historical_recorded_execution` | **Re-executed:** `False` | **Groq API Calls:** `0`
- **Fixed Baseline Reference ID:** `hist_ef23650339c0` | **Trace Directory:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Ingestion_Traces_final\Ingestion_Traces\recruitment_screening`
- **Input Matching:** matched=`30`, unmatched=`0`, excluded=`0`

### Fresh Optimized Subprocess Execution
- **Source:** `current_experiment` | **Execution Mode(s):** `['live_llm_execution']` | **Re-executed:** `True` | **Groq API Calls:** `16`
- **Trace Directory:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\recruitment_screening\wp_20261125_172742_e1478e\per_dimension\workflow_parallelization\runtime_traces`
- **Optimized Runs:** runs=`2`, succeeded=`2`, failed=`0`, process_exit=`0`, status=`SUCCESS`, duration=`215.6045s`
- **Optimized API Errors Captured:** `0`
- **Incomplete / Invalid Replay Samples Flagged:** `0`
- **Workflow-Level vs. Agent-Level Latency (Historical Baseline vs. Fresh Optimized):** Baseline WF mean `22.7775s` (Agent mean `2.8453s`) -> Optimized WF mean `107.5203s` (Agent mean `13.9503s`)

## 5. Output Quality Evaluation

| Quality Dimension | Baseline Status (Pass Rate) | Optimized Status (Pass Rate) |
| :--- | :--- | :--- |
| `structural_validity` | `failed` (83.75%) | `failed` (93.75%) |
| `correctness` | `passed` (100.0%) | `passed` (100.0%) |
| `completeness` | `failed` (87.5%) | `passed` (100.0%) |
| `consistency` | `passed` (100.0%) | `failed` (75.0%) |
| `instruction_adherence` | `failed` (90.83%) | `passed` (100.0%) |
| `semantic_quality` | `unavailable` (unavailable) | `unavailable` (unavailable) |

- **Identified Regressions:** `3`
  - `evidence_mapping_agent.structural_validity`: 100.0% -> 50.0%
  - `evidence_mapping_agent.consistency`: 100.0% -> 50.0%
  - `recruiter_summary_agent.consistency`: 100.0% -> 0.0%

## 6. Before-and-After Comparison

| Metric | Baseline | Optimized | Improvement |
| :--- | :--- | :--- | :--- |
| Mean Workflow Latency | 22.7775s | 107.5203s | -372.05% |
| Median Workflow Latency | 22.7775s | 107.5203s | -372.05% |
| Mean Agent Latency | 2.8453s | 13.9503s | -390.29% |
| Input Tokens | 10078.0 | 11268.0 | -11.81% |
| Output Tokens | 6677.0 | 14973.0 | -124.25% |
| Total Tokens | 16755.0 | 37509.0 | -123.87% |
| Execution Cost (estimated_from_model_catalog_using_api_reported_tokens) | $0.005518 | $0.012364 | -124.07% |
| Execution Success Rate | 100.0% | 100.0% | 0.0% |
| Structural Validity | 83.75% | 93.75% | 11.94% |
| Semantic Quality | `unavailable` | `unavailable` | unavailable |

## 7. Final Experiment Assessment

- **Final Assessment Status:** `quality_regression`
- **Stage Flags:** `modification_applied=True`, `validation_passed=True`, `execution_passed=True`, `evaluation_passed=False`
- **Rationale:**
  - Semantic quality evaluation is unavailable.
  - Quality regression detected on 3 agent metric(s): evidence_mapping_agent.structural_validity, evidence_mapping_agent.consistency, recruiter_summary_agent.consistency

### Candidate-Level Traceability

- `PARALLEL-QUALIFICATION_AGENT-JOB_CRITERIA_AGENT` (`workflow_parallelization`): applied=`True`, validation=`passed`, execution=`passed`, evaluation=`applied_requires_further_validation`