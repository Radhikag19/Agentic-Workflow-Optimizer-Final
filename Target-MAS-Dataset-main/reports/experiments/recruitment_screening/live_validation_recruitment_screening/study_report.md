# Dimension-Wise Optimization, RAGAS Quality & Pareto Selection Report: `recruitment_screening`

## 1. Experimental Setup

- **Workflow ID:** `recruitment_screening`
- **Study ID:** `live_validation_recruitment_screening`
- **Fixed Baseline Reference:** `hist_ef23650339c0` (re_executed=`False`, groq_api_calls=`0`)
- **Matched Inputs:** `30` | **Excluded / Unmatched Inputs:** `0`
- **Experiment IDs:** `live_validation_recruitment_screening__phase_a_communication_data_handoff`, `live_validation_recruitment_screening__phase_a_workflow_parallelization`, `live_validation_recruitment_screening__phase_b_model_selection`, `live_validation_recruitment_screening__phase_c_combined`
- **Optimized Runs Per Config (`num_runs`):** `1`
- **Execution Mode:** `local_subprocess_live_groq`
- **Quality Acceptance Criteria:** `{'min_faithfulness': 0.7, 'min_context_precision': 0.7, 'min_context_recall': 0.7, 'max_regression_vs_foundation': 0.1, 'require_all_metrics_available': True}`

## 2. Fixed Foundation Evaluation

- **Accepted Fixed Optimization Foundation:** None
- **`communication_data_handoff`**: accepted=`False`, status=`rejected`, latency_delta=`-244.63%`, token_delta=`-13.14%`, RAGAS=(F:`0.9167`, CP:`0.9302`, CR:`0.5563`)
- **`workflow_parallelization`**: accepted=`False`, status=`rejected`, latency_delta=`-236.47%`, token_delta=`-11.9%`, RAGAS=(F:`1.0`, CP:`0.7778`, CR:`0.6667`)

## 3. Individual Variable-Dimension Evaluation

- **Fixed Foundation + `model_selection`**: accepted=`False`, quality_status=`rejected`, latency=`71.9968s` (-231.0%), tokens=`18692.0` (-17.4%), cost=`$0.005741` (-13.03%), RAGAS=(F:`0.973`, CP:`1.0`, CR:`0.5`)

## 4. Combined Optimization

- **Applied Dimensions:** `model_selection`
- **Performance & Quality:** latency=`60.7981s`, tokens=`17543.0`, cost=`$0.005126`, quality_accepted=`False`, RAGAS=(F:`1.0`, CP:`1.0`, CR:`0.5`)
- **Interactions / Regressions:** Combined configuration did not pass quality acceptance: ['context_recall=0.5000 < configured minimum 0.7000'].

## 5. Comparative Metrics

| Configuration | Scope | Execution Passed | Mean Latency (s) | Input Tokens | Output Tokens | Total Tokens | Cost (USD) | Faithfulness | Context Precision | Context Recall | Quality Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `fixed_historical_baseline` | `historical_baseline` | `True` | 21.751 | 9941.0 | 5980.0 | 15921.0 | 0.005079 | `reference_only` | `reference_only` | `reference_only` | `HISTORICAL_REFERENCE` |
| `phase_a_communication_data_handoff` | `phase_a_foundation_candidate` | `True` | 74.9607 | 11183.0 | 6830.0 | 18013.0 | 0.005774 | `0.9167` | `0.9302` | `0.5563` | `rejected` |
| `phase_a_workflow_parallelization` | `phase_a_foundation_candidate` | `True` | 73.1854 | 11516.0 | 6299.0 | 17815.0 | 0.005507 | `1.0` | `0.7778` | `0.6667` | `rejected` |
| `model_selection` | `variable_on_foundation` | `True` | 71.9968 | 11527.0 | 7165.0 | 18692.0 | 0.005741 | `0.973` | `1.0` | `0.5` | `rejected` |
| `combined_workflow` | `combined` | `True` | 60.7981 | 11271.0 | 6272.0 | 17543.0 | 0.005126 | `1.0` | `1.0` | `0.5` | `rejected` |

## 6. Best Configuration Selection

- **Pareto-Efficient Configurations (Non-Dominated, Quality-Accepted):** None
- **Best Latency Configuration:** `None`
- **Best Token-Efficiency Configuration:** `None`
- **Best Cost-Efficiency Configuration:** `None`
- **Recommended Overall Configuration:** `None (see selection note)`
- **Selection Note:** No quality-accepted, successfully executed configurations are eligible for Pareto selection.

## 7. Limitations and Final Assessment

- **Original Workflow Unchanged (SHA-256 Verified):** `True`
- **Isolated RAGAS Evaluator Usage (Excluded from Workflow Tokens/Cost):** calls=`66`, tokens=`181778`, cost=`$0.314411`
- Historical baseline metrics are from prior recorded executions rather than live concurrent re-execution.
- Phase A foundation gate rejected/did not accept 'communication_data_handoff': ['context_recall=0.5563 < configured minimum 0.7000'].
- Phase A foundation gate rejected/did not accept 'workflow_parallelization': ['context_recall=0.6667 < configured minimum 0.7000', 'Parallelization did not demonstrate positive latency benefit (latency_improvement_pct=-236.47).'].