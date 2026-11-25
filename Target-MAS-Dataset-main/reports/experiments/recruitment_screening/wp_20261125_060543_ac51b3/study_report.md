# Dimension-Wise Optimization, RAGAS Quality & Pareto Selection Report: `recruitment_screening`

## 1. Experimental Setup

- **Workflow ID:** `recruitment_screening`
- **Study ID:** `wp_20261125_060543_ac51b3`
- **Fixed Baseline Reference:** `hist_ef23650339c0` (re_executed=`False`, groq_api_calls=`0`)
- **Matched Inputs:** `30` | **Excluded / Unmatched Inputs:** `0`
- **Experiment IDs:** `wp_20261125_060543_ac51b3__phase_a_communication_data_handoff`, `wp_20261125_060543_ac51b3__phase_a_workflow_parallelization`, `wp_20261125_060543_ac51b3__phase_b_model_selection`, `wp_20261125_060543_ac51b3__phase_c_combined`
- **Optimized Runs Per Config (`num_runs`):** `2`
- **Execution Mode:** `local_subprocess_live_groq`
- **Quality Acceptance Criteria:** `{'min_structural_decision_score': 0.75, 'min_semantic_cosine': 0.75, 'min_llm_judge_score': 0.75, 'max_decision_flips': 0, 'max_regression_vs_foundation': 0.1}`

## 2. Fixed Foundation Evaluation

- **Accepted Fixed Optimization Foundation:** None
- **`communication_data_handoff`**: accepted=`False`, status=`rejected`, latency_delta=`-351.94%`, token_delta=`-115.37%`, Equivalence=(L1:`0.7949`, L2:`0.7066`, L3:`0.2733`, Flips:`10`)
- **`workflow_parallelization`**: accepted=`False`, status=`rejected`, latency_delta=`-424.22%`, token_delta=`-121.52%`, Equivalence=(L1:`0.823`, L2:`0.8567`, L3:`0.2833`, Flips:`18`)

## 3. Individual Variable-Dimension Evaluation

- **Fixed Foundation + `model_selection`**: accepted=`False`, quality_status=`rejected`, latency=`unavailable` (unavailable), tokens=`unavailable` (unavailable), cost=`$unavailable` (unavailable), Equivalence=(L1:`unavailable`, L2:`unavailable`, L3:`unavailable`, Flips:`0`)

## 4. Combined Optimization

- **Applied Dimensions:** `model_selection`
- **Performance & Quality:** latency=`unavailable`, tokens=`unavailable`, cost=`$unavailable`, quality_accepted=`False`, Equivalence=(L1:`unavailable`, L2:`unavailable`, L3:`unavailable`, Flips:`0`)
- **Interactions / Regressions:** Combined configuration did not pass quality acceptance: ['Optimized runtime execution failed.', 'Optimized agent output schemas failed validation.'].

## 5. Comparative Metrics

| Configuration | Scope | Execution Passed | Mean Latency (s) | Input Tokens | Output Tokens | Total Tokens | Cost (USD) | Struct/Decision (L1) | Semantic Cosine (L2) | LLM Judge (L3) | Decision Flips | Quality Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `fixed_historical_baseline` | `historical_baseline` | `True` | 22.7775 | 10078.0 | 6677.0 | 16755.0 | 0.005518 | `reference_only` | `reference_only` | `disabled` | `0` | `HISTORICAL_REFERENCE` |
| `phase_a_communication_data_handoff` | `phase_a_foundation_candidate` | `True` | 102.9413 | 10882.0 | 14321.0 | 36085.0 | 0.011856 | `0.7949` | `0.7066` | `0.2733` | `10` | `rejected` |
| `phase_a_workflow_parallelization` | `phase_a_foundation_candidate` | `True` | 119.4049 | 11184.0 | 14748.0 | 37116.0 | 0.012203 | `0.823` | `0.8567` | `0.2833` | `18` | `rejected` |
| `model_selection` | `variable_on_foundation` | `False` | unavailable | unavailable | unavailable | unavailable | unavailable | `unavailable` | `unavailable` | `unavailable` | `0` | `rejected` |
| `combined_workflow` | `combined` | `False` | unavailable | unavailable | unavailable | unavailable | unavailable | `unavailable` | `unavailable` | `unavailable` | `0` | `rejected` |

## 6. Best Configuration Selection

- **Pareto-Efficient Configurations (Non-Dominated, Quality-Accepted):** None
- **Best Latency Configuration:** `None`
- **Best Token-Efficiency Configuration:** `None`
- **Best Cost-Efficiency Configuration:** `None`
- **Recommended Overall Configuration:** `None (see selection note)`
- **Selection Note:** No quality-accepted, successfully executed configurations are eligible for Pareto selection.

## 7. Limitations and Final Assessment

- **Original Workflow Unchanged (SHA-256 Verified):** `True`
- **Isolated RAGAS Evaluator Usage (Excluded from Workflow Tokens/Cost):** calls=`6`, tokens=`10056`, cost=`$0.002827`
- Historical baseline metrics are from prior recorded executions rather than live concurrent re-execution.
- Phase A foundation gate rejected/did not accept 'communication_data_handoff': ['semantic_cosine_similarity=0.7066 < required 0.75', 'llm_judge_equivalence=0.2733 < required 0.75', 'decision_flip_count=10 > allowed 0'].
- Phase A foundation gate rejected/did not accept 'workflow_parallelization': ['llm_judge_equivalence=0.2833 < required 0.75', 'decision_flip_count=18 > allowed 0', 'Parallelization did not demonstrate positive latency benefit (latency_improvement_pct=-424.22).'].