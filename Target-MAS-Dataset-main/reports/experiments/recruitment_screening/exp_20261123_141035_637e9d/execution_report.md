# Sandbox Optimization Experiment Report: `recruitment_screening`

## 1. Experiment Metadata

- **Workflow ID:** `recruitment_screening`
- **Experiment ID:** `exp_20261123_141035_637e9d`
- **Execution Mode(s):** `['offline_trace_replay_sandbox']`
- **Runs Executed:** `2`
- **Baseline Model / Provider:** `openai/gpt-oss-120b` / `Groq` (key env: `GROQ_API_KEY_5`)
- **Model Overrides Applied:** `{'resume_intake_agent': {'previous_model': 'openai/gpt-oss-120b', 'updated_model': 'llama-3.3-70b-versatile', 'provider': 'Groq', 'candidate_id': 'MODEL-RESUME_INTAKE_AGENT'}}`
- **Approved Candidate IDs (4):** `PARALLEL-QUALIFICATION_AGENT-JOB_CRITERIA_AGENT`, `MODEL-RESUME_INTAKE_AGENT`, `HANDOFF-QUALIFICATION_AGENT-TO-EXPERIENCE_ASSESSMENT_AGENT`, `HANDOFF-EXPERIENCE_ASSESSMENT_AGENT-TO-SCREENING_REVIEW_AGENT`
- **Original Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\Agents\recruitment_screening`
- **Sandbox Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\recruitment_screening\exp_20261123_141035_637e9d\sandbox_workflow`
- **Generated At:** 2026-11-23T14:11:28.287241+00:00

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

- **Baseline Execution:** runs=`2`, succeeded=`2`, mode=`['offline_trace_replay_sandbox']`
- **Optimized Execution:** runs=`2`, succeeded=`2`, failed=`0`, modes=`['offline_trace_replay_sandbox']`
- **API Errors Captured:** `16`
- **Incomplete / Invalid Replay Samples Flagged:** `2`
- **Workflow-Level vs. Agent-Level Latency:** Baseline WF mean `13.9897s` (Agent mean `1.7485s`) -> Optimized WF mean `12.0012s` (Agent mean `1.7067s`)

## 5. Output Quality Evaluation

| Quality Dimension | Baseline Status (Pass Rate) | Optimized Status (Pass Rate) |
| :--- | :--- | :--- |
| `structural_validity` | `failed` (87.5%) | `failed` (87.5%) |
| `correctness` | `failed` (50.0%) | `failed` (50.0%) |
| `completeness` | `failed` (87.5%) | `failed` (87.5%) |
| `consistency` | `passed` (100.0%) | `passed` (100.0%) |
| `instruction_adherence` | `failed` (87.5%) | `failed` (87.5%) |
| `semantic_quality` | `unavailable` (unavailable) | `unavailable` (unavailable) |

- **Identified Regressions:** `0`

## 6. Before-and-After Comparison

| Metric | Baseline | Optimized | Improvement |
| :--- | :--- | :--- | :--- |
| Mean Workflow Latency | 13.9897s | 12.0012s | unavailable |
| Median Workflow Latency | 13.9897s | 12.0012s | unavailable |
| Mean Agent Latency | 1.7485s | 1.7067s | unavailable |
| Input Tokens | 10335.0 | 10057.0 | unavailable |
| Output Tokens | 6576.0 | 6576.0 | unavailable |
| Total Tokens | 16911.0 | 16633.0 | unavailable |
| Execution Cost (estimated_from_historical_replay) | $0.005495 | $0.005453 | unavailable |
| Execution Success Rate | 100.0% | 100.0% | 0.0% |
| Structural Validity | 87.5% | 87.5% | 0.0% |
| Semantic Quality | `unavailable` | `unavailable` | unavailable |

## 7. Final Experiment Assessment

- **Final Assessment Status:** `inconclusive`
- **Stage Flags:** `modification_applied=True`, `validation_passed=True`, `execution_passed=True`, `evaluation_passed=False`
- **Rationale:**
  - Output schema validation failed (2 error(s)).
  - Execution used offline_trace_replay_sandbox rather than live LLM execution.
  - Replayed historical samples were incomplete / missing required schema fields.
  - Semantic quality evaluation is unavailable.

### Candidate-Level Traceability

- `PARALLEL-QUALIFICATION_AGENT-JOB_CRITERIA_AGENT` (`workflow_parallelization`): applied=`True`, validation=`passed`, execution=`passed`, evaluation=`applied_requires_further_validation`
- `MODEL-RESUME_INTAKE_AGENT` (`model_selection`): applied=`True`, validation=`passed`, execution=`passed`, evaluation=`applied_requires_further_validation`
- `HANDOFF-QUALIFICATION_AGENT-TO-EXPERIENCE_ASSESSMENT_AGENT` (`communication_data_handoff`): applied=`True`, validation=`passed`, execution=`passed`, evaluation=`applied_requires_further_validation`
- `HANDOFF-EXPERIENCE_ASSESSMENT_AGENT-TO-SCREENING_REVIEW_AGENT` (`communication_data_handoff`): applied=`True`, validation=`passed`, execution=`passed`, evaluation=`applied_requires_further_validation`