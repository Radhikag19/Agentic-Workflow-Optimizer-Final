# Sandbox Optimization Experiment Report: `recruitment_screening`

## 1. Experiment Metadata

- **Workflow ID:** `recruitment_screening`
- **Experiment ID:** `live_validation_recruitment_screening__phase_b_model_selection`
- **Execution Backend:** `local_subprocess`
- **Python Executable:** `C:\Users\radhi\AppData\Local\Programs\Python\Python312\python.exe`
- **Execution Mode(s):** `['live_llm_execution']`
- **Runs Executed:** `1`
- **Baseline Model / Provider:** `openai/gpt-oss-120b` / `Groq` (key env: `GROQ_API_KEY_5`)
- **Model Overrides Applied:** `{'resume_intake_agent': {'previous_model': 'openai/gpt-oss-120b', 'updated_model': 'openai/gpt-oss-20b', 'provider': 'Groq', 'candidate_id': 'MODEL-RESUME_INTAKE_AGENT'}}`
- **Approved Candidate IDs (1):** `MODEL-RESUME_INTAKE_AGENT`
- **Original Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\Agents\recruitment_screening`
- **Sandbox Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\recruitment_screening\live_validation_recruitment_screening\phase_b\model_selection\sandbox_workflow`
- **Generated At:** 2026-11-24T15:20:44.488466+00:00

## 2. Applied Modifications

- **Applied (1):** `MODEL-RESUME_INTAKE_AGENT`
- **Failed (0):** None
- **Conflicts (0):** None
- **Manual Intervention (0):** None
- **Modified Files:** `intake_agent.py`, `sandbox_optimization_config.json`, `workflow.json`

- **`MODEL-RESUME_INTAKE_AGENT`** (`model_selection`) — Status: `applied` — Updated model configuration for ['resume_intake_agent'] to 'openai/gpt-oss-20b' (provider=Groq) in sandbox while preserving API key bindings.

## 3. Validation Results

- **Original Workflow Unchanged (SHA-256 Verified):** `True`
- **Python Syntax Checks Passed:** `True` (10 files)
- **Configuration Validation Passed:** `True`
- **Dependency & Reference Integrity Passed:** `True`
- **Output Schema Validation Passed (Optimized):** `True`

## 4. Runtime Execution & Baseline Evidence

### Fixed Historical Baseline Evidence
- **Source:** `historical_runtime_traces` | **Execution Mode:** `historical_recorded_execution` | **Re-executed:** `False` | **Groq API Calls:** `0`
- **Fixed Baseline Reference ID:** `hist_ef23650339c0` | **Trace Directory:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Ingestion_Traces_final\Ingestion_Traces\recruitment_screening`
- **Input Matching:** matched=`30`, unmatched=`0`, excluded=`0`

### Fresh Optimized Subprocess Execution
- **Source:** `current_experiment` | **Execution Mode(s):** `['live_llm_execution']` | **Re-executed:** `True` | **Groq API Calls:** `8`
- **Trace Directory:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\recruitment_screening\live_validation_recruitment_screening\phase_b\model_selection\runtime_traces`
- **Optimized Runs:** runs=`1`, succeeded=`1`, failed=`0`, process_exit=`0`, status=`SUCCESS`, duration=`72.0633s`
- **Optimized API Errors Captured:** `0`
- **Incomplete / Invalid Replay Samples Flagged:** `0`
- **Workflow-Level vs. Agent-Level Latency (Historical Baseline vs. Fresh Optimized):** Baseline WF mean `21.751s` (Agent mean `2.7169s`) -> Optimized WF mean `71.9968s` (Agent mean `8.9994s`)

## 5. Output Quality Evaluation

| Quality Dimension | Baseline Status (Pass Rate) | Optimized Status (Pass Rate) |
| :--- | :--- | :--- |
| `structural_validity` | `failed` (83.75%) | `passed` (100.0%) |
| `correctness` | `passed` (100.0%) | `passed` (100.0%) |
| `completeness` | `failed` (87.5%) | `passed` (100.0%) |
| `consistency` | `passed` (100.0%) | `failed` (83.33%) |
| `instruction_adherence` | `failed` (90.83%) | `passed` (100.0%) |
| `semantic_quality` | `unavailable` (unavailable) | `unavailable` (unavailable) |

- **Identified Regressions:** `1`
  - `recruiter_summary_agent.consistency`: 100.0% -> 0.0%

## 6. Before-and-After Comparison

| Metric | Baseline | Optimized | Improvement |
| :--- | :--- | :--- | :--- |
| Mean Workflow Latency | 21.751s | 71.9968s | -231.0% |
| Median Workflow Latency | 21.751s | 71.9968s | -231.0% |
| Mean Agent Latency | 2.7169s | 8.9994s | -231.24% |
| Input Tokens | 9941.0 | 11527.0 | -15.95% |
| Output Tokens | 5980.0 | 7165.0 | -19.82% |
| Total Tokens | 15921.0 | 18692.0 | -17.4% |
| Execution Cost (estimated_from_model_catalog_using_api_reported_tokens) | $0.005079 | $0.005741 | -13.03% |
| Execution Success Rate | 100.0% | 100.0% | 0.0% |
| Structural Validity | 83.75% | 100.0% | 19.4% |
| Semantic Quality | `unavailable` | `unavailable` | unavailable |

## 7. Final Experiment Assessment

- **Final Assessment Status:** `quality_regression`
- **Stage Flags:** `modification_applied=True`, `validation_passed=True`, `execution_passed=True`, `evaluation_passed=False`
- **Rationale:**
  - Semantic quality evaluation is unavailable.
  - Quality regression detected on 1 agent metric(s): recruiter_summary_agent.consistency

### Candidate-Level Traceability

- `MODEL-RESUME_INTAKE_AGENT` (`model_selection`): applied=`True`, validation=`passed`, execution=`passed`, evaluation=`applied_requires_further_validation`