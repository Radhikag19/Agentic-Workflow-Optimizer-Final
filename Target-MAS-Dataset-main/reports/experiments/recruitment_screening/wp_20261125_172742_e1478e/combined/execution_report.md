# Sandbox Optimization Experiment Report: `recruitment_screening`

## 1. Experiment Metadata

- **Workflow ID:** `recruitment_screening`
- **Experiment ID:** `wp_20261125_172742_e1478e__combined`
- **Execution Backend:** `local_subprocess`
- **Python Executable:** `C:\Users\radhi\AppData\Local\Programs\Python\Python312\python.exe`
- **Execution Mode(s):** `['live_llm_execution']`
- **Runs Executed:** `2`
- **Baseline Model / Provider:** `openai/gpt-oss-120b` / `Groq` (key env: `GROQ_API_KEY_5`)
- **Model Overrides Applied:** `{'resume_intake_agent': {'previous_model': 'openai/gpt-oss-120b', 'updated_model': 'openai/gpt-oss-20b', 'provider': 'Groq', 'candidate_id': 'MODEL-RESUME_INTAKE_AGENT'}}`
- **Approved Candidate IDs (4):** `PARALLEL-QUALIFICATION_AGENT-JOB_CRITERIA_AGENT`, `MODEL-RESUME_INTAKE_AGENT`, `HANDOFF-QUALIFICATION_AGENT-TO-EXPERIENCE_ASSESSMENT_AGENT`, `HANDOFF-EXPERIENCE_ASSESSMENT_AGENT-TO-SCREENING_REVIEW_AGENT`
- **Original Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\Agents\recruitment_screening`
- **Sandbox Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\recruitment_screening\wp_20261125_172742_e1478e\combined\sandbox_workflow`
- **Generated At:** 2026-11-25T17:44:17.690465+00:00

## 2. Applied Modifications

- **Applied (4):** `PARALLEL-QUALIFICATION_AGENT-JOB_CRITERIA_AGENT`, `MODEL-RESUME_INTAKE_AGENT`, `HANDOFF-QUALIFICATION_AGENT-TO-EXPERIENCE_ASSESSMENT_AGENT`, `HANDOFF-EXPERIENCE_ASSESSMENT_AGENT-TO-SCREENING_REVIEW_AGENT`
- **Failed (0):** None
- **Conflicts (0):** None
- **Manual Intervention (0):** None
- **Modified Files:** `intake_agent.py`, `sandbox_optimization_config.json`, `workflow.json`, `workflow.py`

- **`PARALLEL-QUALIFICATION_AGENT-JOB_CRITERIA_AGENT`** (`workflow_parallelization`) — Status: `applied` — Configured concurrent scatter-gather group ['qualification_agent', 'job_criteria_agent'] in sandbox workflow after verifying strict DAG & I/O independence.
- **`MODEL-RESUME_INTAKE_AGENT`** (`model_selection`) — Status: `applied` — Updated model configuration for ['resume_intake_agent'] to 'openai/gpt-oss-20b' (provider=Groq, source=jev_agent2_cached_langgraph) in sandbox while preserving API key bindings.
- **`HANDOFF-QUALIFICATION_AGENT-TO-EXPERIENCE_ASSESSMENT_AGENT`** (`communication_data_handoff`) — Status: `applied` — Configured compact handoff projection on 'qualification_agent->experience_assessment_agent' retaining 3 field(s) and excluding ['education', 'certifications', 'projects', 'extraction_warnings'].
- **`HANDOFF-EXPERIENCE_ASSESSMENT_AGENT-TO-SCREENING_REVIEW_AGENT`** (`communication_data_handoff`) — Status: `applied` — Configured compact handoff projection on 'experience_assessment_agent->screening_review_agent' retaining 4 field(s) and excluding ['relevance_summary', 'transferable_skills'].

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
- **Source:** `current_experiment` | **Execution Mode(s):** `['live_llm_execution']` | **Re-executed:** `True` | **Groq API Calls:** `16`
- **Trace Directory:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\recruitment_screening\wp_20261125_172742_e1478e\combined\runtime_traces`
- **Optimized Runs:** runs=`2`, succeeded=`2`, failed=`0`, process_exit=`0`, status=`SUCCESS`, duration=`201.6379s`
- **Optimized API Errors Captured:** `0`
- **Incomplete / Invalid Replay Samples Flagged:** `0`
- **Workflow-Level vs. Agent-Level Latency (Historical Baseline vs. Fresh Optimized):** Baseline WF mean `22.7775s` (Agent mean `2.8453s`) -> Optimized WF mean `100.6971s` (Agent mean `13.5554s`)

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
| Mean Workflow Latency | 22.7775s | 100.6971s | -342.09% |
| Median Workflow Latency | 22.7775s | 100.6971s | -342.09% |
| Mean Agent Latency | 2.8453s | 13.5554s | -376.41% |
| Input Tokens | 10078.0 | 11094.0 | -10.08% |
| Output Tokens | 6677.0 | 15796.0 | -136.57% |
| Total Tokens | 16755.0 | 37984.0 | -126.7% |
| Execution Cost (estimated_from_model_catalog_using_api_reported_tokens) | $0.005518 | $0.011954 | -116.64% |
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

- `PARALLEL-QUALIFICATION_AGENT-JOB_CRITERIA_AGENT` (`workflow_parallelization`): applied=`True`, validation=`passed`, execution=`passed`, evaluation=`applied_requires_further_validation`
- `MODEL-RESUME_INTAKE_AGENT` (`model_selection`): applied=`True`, validation=`passed`, execution=`passed`, evaluation=`applied_requires_further_validation`
- `HANDOFF-QUALIFICATION_AGENT-TO-EXPERIENCE_ASSESSMENT_AGENT` (`communication_data_handoff`): applied=`True`, validation=`passed`, execution=`passed`, evaluation=`applied_requires_further_validation`
- `HANDOFF-EXPERIENCE_ASSESSMENT_AGENT-TO-SCREENING_REVIEW_AGENT` (`communication_data_handoff`): applied=`True`, validation=`passed`, execution=`passed`, evaluation=`applied_requires_further_validation`