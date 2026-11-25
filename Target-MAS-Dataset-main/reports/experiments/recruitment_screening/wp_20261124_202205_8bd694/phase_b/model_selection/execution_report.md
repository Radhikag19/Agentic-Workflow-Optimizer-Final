# Sandbox Optimization Experiment Report: `recruitment_screening`

## 1. Experiment Metadata

- **Workflow ID:** `recruitment_screening`
- **Experiment ID:** `wp_20261124_202205_8bd694__phase_b_model_selection`
- **Execution Backend:** `local_subprocess`
- **Python Executable:** `C:\Users\radhi\AppData\Local\Programs\Python\Python312\python.exe`
- **Execution Mode(s):** `['live_llm_execution']`
- **Runs Executed:** `2`
- **Baseline Model / Provider:** `openai/gpt-oss-120b` / `Groq` (key env: `GROQ_API_KEY_5`)
- **Model Overrides Applied:** `{'resume_intake_agent': {'previous_model': 'openai/gpt-oss-120b', 'updated_model': 'llama-3.3-70b-versatile', 'provider': 'Groq', 'candidate_id': 'MODEL-RESUME_INTAKE_AGENT'}}`
- **Approved Candidate IDs (1):** `MODEL-RESUME_INTAKE_AGENT`
- **Original Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\Agents\recruitment_screening`
- **Sandbox Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\recruitment_screening\wp_20261124_202205_8bd694\phase_b\model_selection\sandbox_workflow`
- **Generated At:** 2026-11-24T20:35:14.914700+00:00

## 2. Applied Modifications

- **Applied (1):** `MODEL-RESUME_INTAKE_AGENT`
- **Failed (0):** None
- **Conflicts (0):** None
- **Manual Intervention (0):** None
- **Modified Files:** `intake_agent.py`, `sandbox_optimization_config.json`, `workflow.json`

- **`MODEL-RESUME_INTAKE_AGENT`** (`model_selection`) — Status: `applied` — Updated model configuration for ['resume_intake_agent'] to 'llama-3.3-70b-versatile' (provider=Groq) in sandbox while preserving API key bindings.

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
- **Source:** `current_experiment` | **Execution Mode(s):** `['live_llm_execution']` | **Re-executed:** `True` | **Groq API Calls:** `2`
- **Trace Directory:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\recruitment_screening\wp_20261124_202205_8bd694\phase_b\model_selection\runtime_traces`
- **Optimized Runs:** runs=`2`, succeeded=`0`, failed=`2`, process_exit=`0`, status=`FAILED`, duration=`1.4023s`
- **Optimized API Errors Captured:** `2`
- **Incomplete / Invalid Replay Samples Flagged:** `0`
- **Workflow-Level vs. Agent-Level Latency (Historical Baseline vs. Fresh Optimized):** Baseline WF mean `22.7775s` (Agent mean `2.8453s`) -> Optimized WF mean `unavailable` (Agent mean `unavailable`)

## 5. Output Quality Evaluation

| Quality Dimension | Baseline Status (Pass Rate) | Optimized Status (Pass Rate) |
| :--- | :--- | :--- |
| `structural_validity` | `failed` (83.75%) | `failed` (0.0%) |
| `correctness` | `passed` (100.0%) | `failed` (0.0%) |
| `completeness` | `failed` (87.5%) | `failed` (0.0%) |
| `consistency` | `passed` (100.0%) | `failed` (0.0%) |
| `instruction_adherence` | `failed` (90.83%) | `failed` (0.0%) |
| `semantic_quality` | `unavailable` (unavailable) | `unavailable` (unavailable) |

- **Identified Regressions:** `4`
  - `resume_intake_agent.structural_validity`: 100.0% -> 0.0%
  - `resume_intake_agent.correctness`: 100.0% -> 0.0%
  - `resume_intake_agent.completeness`: 100.0% -> 0.0%
  - `resume_intake_agent.instruction_adherence`: 100.0% -> 0.0%

## 6. Before-and-After Comparison

| Metric | Baseline | Optimized | Improvement |
| :--- | :--- | :--- | :--- |
| Mean Workflow Latency | 22.7775s | unavailable | unavailable |
| Median Workflow Latency | 22.7775s | unavailable | unavailable |
| Mean Agent Latency | 2.8453s | unavailable | unavailable |
| Input Tokens | 10078.0 | unavailable | unavailable |
| Output Tokens | 6677.0 | unavailable | unavailable |
| Total Tokens | 16755.0 | unavailable | unavailable |
| Execution Cost (unavailable) | $0.005518 | $None | unavailable |
| Execution Success Rate | 100.0% | 0.0% | -100.0% |
| Structural Validity | 83.75% | 0.0% | -100.0% |
| Semantic Quality | `unavailable` | `unavailable` | unavailable |

## 7. Final Experiment Assessment

- **Final Assessment Status:** `failed`
- **Stage Flags:** `modification_applied=True`, `validation_passed=True`, `execution_passed=False`, `evaluation_passed=False`
- **Rationale:**
  - Optimized workflow runtime execution failed or produced incomplete runs.

### Candidate-Level Traceability

- `MODEL-RESUME_INTAKE_AGENT` (`model_selection`): applied=`True`, validation=`passed`, execution=`failed`, evaluation=`applied`