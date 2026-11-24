# Sandbox Optimization Experiment Report: `recruitment_screening`

## 1. Experiment Metadata

- **Workflow ID:** `recruitment_screening`
- **Experiment ID:** `exp_20261123_141027_eeafbb`
- **Execution Mode(s):** `['live_llm_execution']`
- **Runs Executed:** `2`
- **Baseline Model / Provider:** `openai/gpt-oss-120b` / `Groq` (key env: `GROQ_API_KEY_5`)
- **Model Overrides Applied:** `{'resume_intake_agent': {'previous_model': 'openai/gpt-oss-120b', 'updated_model': 'llama-3.3-70b-versatile', 'provider': 'Groq', 'candidate_id': 'MODEL-RESUME_INTAKE_AGENT'}}`
- **Approved Candidate IDs (4):** `PARALLEL-QUALIFICATION_AGENT-JOB_CRITERIA_AGENT`, `MODEL-RESUME_INTAKE_AGENT`, `HANDOFF-QUALIFICATION_AGENT-TO-EXPERIENCE_ASSESSMENT_AGENT`, `HANDOFF-EXPERIENCE_ASSESSMENT_AGENT-TO-SCREENING_REVIEW_AGENT`
- **Original Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\Agents\recruitment_screening`
- **Sandbox Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\recruitment_screening\exp_20261123_141027_eeafbb\sandbox_workflow`
- **Generated At:** 2026-11-23T14:10:35.802768+00:00

## 2. Applied Modifications

- **Applied (4):** `PARALLEL-QUALIFICATION_AGENT-JOB_CRITERIA_AGENT`, `MODEL-RESUME_INTAKE_AGENT`, `HANDOFF-QUALIFICATION_AGENT-TO-EXPERIENCE_ASSESSMENT_AGENT`, `HANDOFF-EXPERIENCE_ASSESSMENT_AGENT-TO-SCREENING_REVIEW_AGENT`
- **Failed (0):** None
- **Conflicts (0):** None
- **Manual Intervention (0):** None
- **Modified Files:** `intake_agent.py`, `sandbox_optimization_config.json`, `workflow.json`, `workflow.py`

- **`PARALLEL-QUALIFICATION_AGENT-JOB_CRITERIA_AGENT`** (`workflow_parallelization`) — Status: `applied` — Configured concurrent scatter-gather group ['qualification_agent', 'job_criteria_agent'] in sandbox workflow after verifying strict DAG & I/O independence.
- **`MODEL-RESUME_INTAKE_AGENT`** (`model_selection`) — Status: `applied` — Updated model configuration for ['resume_intake_agent'] to 'llama-3.3-70b-versatile' (provider=Groq) in sandbox while preserving API key bindings.
- **`HANDOFF-QUALIFICATION_AGENT-TO-EXPERIENCE_ASSESSMENT_AGENT`** (`communication_data_handoff`) — Status: `applied` — Configured compact handoff projection on 'qualification_agent->experience_assessment_agent' retaining 3 field(s) and excluding ['education', 'certifications', 'projects', 'extraction_warnings'].
- **`HANDOFF-EXPERIENCE_ASSESSMENT_AGENT-TO-SCREENING_REVIEW_AGENT`** (`communication_data_handoff`) — Status: `applied` — Configured compact handoff projection on 'experience_assessment_agent->screening_review_agent' retaining 4 field(s) and excluding ['relevance_summary', 'transferable_skills'].

## 3. Validation Results

- **Original Workflow Unchanged (SHA-256 Verified):** `True`
- **Python Syntax Checks Passed:** `True` (10 files)
- **Configuration Validation Passed:** `True`
- **Dependency & Reference Integrity Passed:** `True`
- **Output Schema Validation Passed (Optimized):** `False`

## 4. Runtime Execution

- **Baseline Execution:** runs=`2`, succeeded=`0`, mode=`['live_llm_execution']`
- **Optimized Execution:** runs=`2`, succeeded=`0`, failed=`2`, modes=`['live_llm_execution']`
- **API Errors Captured:** `2`
- **Incomplete / Invalid Replay Samples Flagged:** `0`
- **Workflow-Level vs. Agent-Level Latency:** Baseline WF mean `unavailable` (Agent mean `unavailable`) -> Optimized WF mean `unavailable` (Agent mean `unavailable`)

## 5. Output Quality Evaluation

| Quality Dimension | Baseline Status (Pass Rate) | Optimized Status (Pass Rate) |
| :--- | :--- | :--- |
| `structural_validity` | `failed` (0.0%) | `failed` (0.0%) |
| `correctness` | `failed` (0.0%) | `failed` (0.0%) |
| `completeness` | `failed` (0.0%) | `failed` (0.0%) |
| `consistency` | `failed` (0.0%) | `failed` (0.0%) |
| `instruction_adherence` | `failed` (0.0%) | `failed` (0.0%) |
| `semantic_quality` | `unavailable` (unavailable) | `unavailable` (unavailable) |

- **Identified Regressions:** `0`

## 6. Before-and-After Comparison

| Metric | Baseline | Optimized | Improvement |
| :--- | :--- | :--- | :--- |
| Mean Workflow Latency | unavailable | unavailable | unavailable |
| Median Workflow Latency | unavailable | unavailable | unavailable |
| Mean Agent Latency | unavailable | unavailable | unavailable |
| Input Tokens | unavailable | unavailable | unavailable |
| Output Tokens | unavailable | unavailable | unavailable |
| Total Tokens | unavailable | unavailable | unavailable |
| Execution Cost (estimated_from_historical_replay) | $None | $None | unavailable |
| Execution Success Rate | 0.0% | 0.0% | 0.0% |
| Structural Validity | 0.0% | 0.0% | 0.0% |
| Semantic Quality | `unavailable` | `unavailable` | unavailable |

## 7. Final Experiment Assessment

- **Final Assessment Status:** `failed`
- **Stage Flags:** `modification_applied=True`, `validation_passed=True`, `execution_passed=False`, `evaluation_passed=False`
- **Rationale:**
  - Optimized workflow runtime execution failed or produced incomplete runs.

### Candidate-Level Traceability

- `PARALLEL-QUALIFICATION_AGENT-JOB_CRITERIA_AGENT` (`workflow_parallelization`): applied=`True`, validation=`passed`, execution=`failed`, evaluation=`applied`
- `MODEL-RESUME_INTAKE_AGENT` (`model_selection`): applied=`True`, validation=`passed`, execution=`failed`, evaluation=`applied`
- `HANDOFF-QUALIFICATION_AGENT-TO-EXPERIENCE_ASSESSMENT_AGENT` (`communication_data_handoff`): applied=`True`, validation=`passed`, execution=`failed`, evaluation=`applied`
- `HANDOFF-EXPERIENCE_ASSESSMENT_AGENT-TO-SCREENING_REVIEW_AGENT` (`communication_data_handoff`): applied=`True`, validation=`passed`, execution=`failed`, evaluation=`applied`