# Sandbox Optimization Experiment Report: `recruitment_screening`

- **Experiment ID:** `exp_20261123_133528_3a72c1`
- **Workflow ID:** `recruitment_screening`
- **Overall Status:** `completed`
- **Original Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\Agents\recruitment_screening`
- **Sandbox Workflow:** `C:\Users\radhi\Desktop\Target-MAS-Dataset-main\Target-MAS-Dataset-main\reports\experiments\recruitment_screening\exp_20261123_133528_3a72c1\sandbox_workflow`
- **Generated At:** 2026-11-23T13:35:52.247440+00:00

## 1. Independent Outcome Stages

| Stage Outcome | Status |
| :--- | :---: |
| `modification_applied` | `True` |
| `validation_passed` | `True` |
| `execution_passed` | `True` |
| `evaluation_passed` | `False` |

## 2. Candidate Execution Summary

- **Approved (4):** `PARALLEL-QUALIFICATION_AGENT-JOB_CRITERIA_AGENT`, `MODEL-RESUME_INTAKE_AGENT`, `HANDOFF-QUALIFICATION_AGENT-TO-EXPERIENCE_ASSESSMENT_AGENT`, `HANDOFF-EXPERIENCE_ASSESSMENT_AGENT-TO-SCREENING_REVIEW_AGENT`
- **Applied (4):** `PARALLEL-QUALIFICATION_AGENT-JOB_CRITERIA_AGENT`, `MODEL-RESUME_INTAKE_AGENT`, `HANDOFF-QUALIFICATION_AGENT-TO-EXPERIENCE_ASSESSMENT_AGENT`, `HANDOFF-EXPERIENCE_ASSESSMENT_AGENT-TO-SCREENING_REVIEW_AGENT`
- **Failed (0):** None
- **Conflicts (0):** None
- **Manual Intervention (0):** None

### Modified Sandbox Files

- `intake_agent.py`
- `sandbox_optimization_config.json`
- `workflow.json`
- `workflow.py`

### Candidate-Level Modifications & Outcomes

#### `PARALLEL-QUALIFICATION_AGENT-JOB_CRITERIA_AGENT` (`workflow_parallelization`) — Status: `applied`
- **Target Agents:** `qualification_agent`, `job_criteria_agent`
- **Description:** Configured concurrent scatter-gather group ['qualification_agent', 'job_criteria_agent'] in sandbox workflow after verifying strict DAG & I/O independence.
- **Files:** `workflow.json`, `workflow.py`, `sandbox_optimization_config.json`

#### `MODEL-RESUME_INTAKE_AGENT` (`model_selection`) — Status: `applied`
- **Target Agents:** `resume_intake_agent`
- **Description:** Updated model configuration for ['resume_intake_agent'] to 'llama-3.3-70b-versatile' (provider=Groq) in sandbox while preserving API key bindings.
- **Files:** `intake_agent.py`, `workflow.json`, `sandbox_optimization_config.json`

#### `HANDOFF-QUALIFICATION_AGENT-TO-EXPERIENCE_ASSESSMENT_AGENT` (`communication_data_handoff`) — Status: `applied`
- **Target Agents:** `qualification_agent`, `experience_assessment_agent`
- **Description:** Configured compact handoff projection on 'qualification_agent->experience_assessment_agent' retaining 3 field(s) and excluding ['education', 'certifications', 'projects', 'extraction_warnings'].
- **Files:** `workflow.json`, `workflow.py`, `sandbox_optimization_config.json`

#### `HANDOFF-EXPERIENCE_ASSESSMENT_AGENT-TO-SCREENING_REVIEW_AGENT` (`communication_data_handoff`) — Status: `applied`
- **Target Agents:** `experience_assessment_agent`, `screening_review_agent`
- **Description:** Configured compact handoff projection on 'experience_assessment_agent->screening_review_agent' retaining 4 field(s) and excluding ['relevance_summary', 'transferable_skills'].
- **Files:** `workflow.json`, `workflow.py`, `sandbox_optimization_config.json`

## 3. Validation Results

- **Original Workflow Unchanged (SHA-256 Verified):** `True`
- **Python Syntax Checks Passed:** `True` (10 files)
- **Configuration Validation Passed:** `True`
- **Reference & Dependency Integrity Passed:** `True`

## 4. Before-and-After Evaluation

| Metric | Baseline | Optimized (Sandbox) | Delta / Improvement |
| :--- | :--- | :--- | :--- |
| Mean Latency | 44.7989s | 11.8314s | 73.59% |
| Mean Tokens | 16909.5 | 16633.0 | 1.64% |
| Catalog-Normalized Cost | $0.005496 | $0.005453 | 0.78% |
| Execution Success Rate | 100.0% | 100.0% | 0.0 pp |
| Output Schema / Semantic Quality | Baseline N/A | Schema Valid: `False` | Semantic Eval: `unavailable` |

> **Execution Mode:** `['offline_trace_replay_sandbox']`  
> **Latency Note:** Measured wall-clock timing reflects simulated replay latency in offline mode rather than live API latency.  
> **Quality Note:** Structured schema validity verified where Pydantic output models exist; automated semantic output-quality scoring is unavailable.
