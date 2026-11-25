# Dimension-Wise Optimization, RAGAS Quality & Pareto Selection Report: `recruitment_screening`

## 1. Experimental Setup

- **Workflow ID:** `recruitment_screening`
- **Study ID:** `wp_20261124_202205_8bd694`
- **Fixed Baseline Reference:** `hist_ef23650339c0` (re_executed=`False`, groq_api_calls=`0`)
- **Matched Inputs:** `30` | **Excluded / Unmatched Inputs:** `0`
- **Experiment IDs:** `wp_20261124_202205_8bd694__phase_a_communication_data_handoff`, `wp_20261124_202205_8bd694__phase_a_workflow_parallelization`, `wp_20261124_202205_8bd694__phase_b_model_selection`, `wp_20261124_202205_8bd694__phase_c_combined`
- **Optimized Runs Per Config (`num_runs`):** `2`
- **Execution Mode:** `local_subprocess_live_groq`
- **Quality Acceptance Criteria:** `{'min_faithfulness': 0.7, 'min_context_precision': 0.7, 'min_context_recall': 0.7, 'max_regression_vs_foundation': 0.1, 'require_all_metrics_available': True}`

## 2. Fixed Foundation Evaluation

- **Accepted Fixed Optimization Foundation:** None
- **`communication_data_handoff`**: accepted=`False`, status=`rejected`, latency_delta=`-231.58%`, token_delta=`-117.8%`, RAGAS=(F:`0.857`, CP:`0.9583`, CR:`0.6839`)
- **`workflow_parallelization`**: accepted=`False`, status=`rejected`, latency_delta=`-351.68%`, token_delta=`-115.32%`, RAGAS=(F:`0.9375`, CP:`0.7778`, CR:`0.6597`)

## 3. Individual Variable-Dimension Evaluation

- **Fixed Foundation + `model_selection`**: accepted=`False`, quality_status=`rejected`, latency=`unavailable` (unavailable), tokens=`unavailable` (unavailable), cost=`$unavailable` (unavailable), RAGAS=(F:`unavailable`, CP:`unavailable`, CR:`unavailable`)

## 4. Combined Optimization

- **Applied Dimensions:** `model_selection`
- **Performance & Quality:** latency=`unavailable`, tokens=`unavailable`, cost=`$unavailable`, quality_accepted=`False`, RAGAS=(F:`unavailable`, CP:`unavailable`, CR:`unavailable`)
- **Interactions / Regressions:** Combined configuration did not pass quality acceptance: ['Optimized runtime execution failed.', 'Optimized agent output schemas failed validation.'].

## 5. Comparative Metrics

| Configuration | Scope | Execution Passed | Mean Latency (s) | Input Tokens | Output Tokens | Total Tokens | Cost (USD) | Faithfulness | Context Precision | Context Recall | Quality Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `fixed_historical_baseline` | `historical_baseline` | `True` | 22.7775 | 10078.0 | 6677.0 | 16755.0 | 0.005518 | `reference_only` | `reference_only` | `reference_only` | `HISTORICAL_REFERENCE` |
| `phase_a_communication_data_handoff` | `phase_a_foundation_candidate` | `True` | 75.5258 | 11028.5 | 14436.0 | 36493.0 | 0.011971 | `0.857` | `0.9583` | `0.6839` | `rejected` |
| `phase_a_workflow_parallelization` | `phase_a_foundation_candidate` | `True` | 102.8806 | 11215.0 | 13647.0 | 36077.0 | 0.011554 | `0.9375` | `0.7778` | `0.6597` | `rejected` |
| `model_selection` | `variable_on_foundation` | `False` | unavailable | unavailable | unavailable | unavailable | unavailable | `unavailable` | `unavailable` | `unavailable` | `rejected` |
| `combined_workflow` | `combined` | `False` | unavailable | unavailable | unavailable | unavailable | unavailable | `unavailable` | `unavailable` | `unavailable` | `rejected` |

## 6. Best Configuration Selection

- **Pareto-Efficient Configurations (Non-Dominated, Quality-Accepted):** None
- **Best Latency Configuration:** `None`
- **Best Token-Efficiency Configuration:** `None`
- **Best Cost-Efficiency Configuration:** `None`
- **Recommended Overall Configuration:** `None (see selection note)`
- **Selection Note:** No quality-accepted, successfully executed configurations are eligible for Pareto selection.

## 7. Limitations and Final Assessment

- **Original Workflow Unchanged (SHA-256 Verified):** `True`
- **Isolated RAGAS Evaluator Usage (Excluded from Workflow Tokens/Cost):** calls=`88`, tokens=`238691`, cost=`$0.402329`
- Historical baseline metrics are from prior recorded executions rather than live concurrent re-execution.
- Phase A foundation gate rejected/did not accept 'communication_data_handoff': ['context_recall=0.6839 < configured minimum 0.7000'].
- Phase A foundation gate rejected/did not accept 'workflow_parallelization': ['context_recall=0.6597 < configured minimum 0.7000', 'Parallelization did not demonstrate positive latency benefit (latency_improvement_pct=-351.68).'].
- One or more RAGAS metrics were marked 'unavailable' due to missing RAGAS dependencies, contexts, or reference answers.