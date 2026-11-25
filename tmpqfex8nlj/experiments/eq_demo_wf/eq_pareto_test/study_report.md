# Dimension-Wise Optimization, RAGAS Quality & Pareto Selection Report: `eq_demo_wf`

## 1. Experimental Setup

- **Workflow ID:** `eq_demo_wf`
- **Study ID:** `eq_pareto_test`
- **Fixed Baseline Reference:** `hist_586e788e111c` (re_executed=`False`, groq_api_calls=`0`)
- **Matched Inputs:** `0` | **Excluded / Unmatched Inputs:** `1`
- **Experiment IDs:** `eq_pareto_test__phase_a_communication_data_handoff`, `eq_pareto_test__phase_a_workflow_parallelization`, `eq_pareto_test__phase_b_model_selection`, `eq_pareto_test__phase_c_combined`
- **Optimized Runs Per Config (`num_runs`):** `1`
- **Execution Mode:** `local_subprocess_live_groq`
- **Quality Acceptance Criteria:** `{'min_structural_decision_score': 0.75, 'min_semantic_cosine': 0.7, 'min_llm_judge_score': 0.75, 'max_decision_flips': 0, 'max_regression_vs_foundation': 0.1}`

## 2. Fixed Foundation Evaluation

- **Accepted Fixed Optimization Foundation:** None
- **`communication_data_handoff`**: accepted=`False`, status=`inconclusive`, latency_delta=`unavailable`, token_delta=`unavailable`, Equivalence=(L1:`unavailable`, L2:`unavailable`, L3:`unavailable`, Flips:`0`)
- **`workflow_parallelization`**: accepted=`False`, status=`inconclusive`, latency_delta=`unavailable`, token_delta=`unavailable`, Equivalence=(L1:`unavailable`, L2:`unavailable`, L3:`unavailable`, Flips:`0`)

## 3. Individual Variable-Dimension Evaluation

- **Fixed Foundation + `model_selection`**: accepted=`False`, quality_status=`inconclusive`, latency=`1.7s` (unavailable), tokens=`840.0` (unavailable), cost=`$0.00084` (unavailable), Equivalence=(L1:`unavailable`, L2:`unavailable`, L3:`unavailable`, Flips:`0`)

## 4. Combined Optimization

- **Applied Dimensions:** `model_selection`
- **Performance & Quality:** latency=`1.7s`, tokens=`840.0`, cost=`$0.00084`, quality_accepted=`False`, Equivalence=(L1:`unavailable`, L2:`unavailable`, L3:`unavailable`, Flips:`0`)
- **Interactions / Regressions:** Combined configuration did not pass quality acceptance: ['Matched baseline/optimized outputs unavailable for behavioral equivalence evaluation.'].

## 5. Comparative Metrics

| Configuration | Scope | Execution Passed | Mean Latency (s) | Input Tokens | Output Tokens | Total Tokens | Cost (USD) | Struct/Decision (L1) | Semantic Cosine (L2) | LLM Judge (L3) | Decision Flips | Quality Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `fixed_historical_baseline` | `historical_baseline` | `True` | unavailable | unavailable | unavailable | unavailable | unavailable | `reference_only` | `reference_only` | `disabled` | `0` | `HISTORICAL_REFERENCE` |
| `phase_a_communication_data_handoff` | `phase_a_foundation_candidate` | `True` | 1.7 | 390.0 | 390.0 | 780.0 | 0.00078 | `unavailable` | `unavailable` | `unavailable` | `0` | `inconclusive` |
| `phase_a_workflow_parallelization` | `phase_a_foundation_candidate` | `True` | 1.6 | 450.0 | 450.0 | 900.0 | 0.0009 | `unavailable` | `unavailable` | `unavailable` | `0` | `inconclusive` |
| `model_selection` | `variable_on_foundation` | `True` | 1.7 | 420.0 | 420.0 | 840.0 | 0.00084 | `unavailable` | `unavailable` | `unavailable` | `0` | `inconclusive` |
| `combined_workflow` | `combined` | `True` | 1.7 | 420.0 | 420.0 | 840.0 | 0.00084 | `unavailable` | `unavailable` | `unavailable` | `0` | `inconclusive` |

## 6. Best Configuration Selection

- **Pareto-Efficient Configurations (Non-Dominated, Quality-Accepted):** None
- **Best Latency Configuration:** `None`
- **Best Token-Efficiency Configuration:** `None`
- **Best Cost-Efficiency Configuration:** `None`
- **Recommended Overall Configuration:** `None (see selection note)`
- **Selection Note:** No quality-accepted, successfully executed configurations are eligible for Pareto selection.

## 7. Limitations and Final Assessment

- **Original Workflow Unchanged (SHA-256 Verified):** `True`
- **Isolated RAGAS Evaluator Usage (Excluded from Workflow Tokens/Cost):** calls=`0`, tokens=`0`, cost=`$0.0`
- Historical baseline metrics are from prior recorded executions rather than live concurrent re-execution.
- Phase A foundation gate rejected/did not accept 'communication_data_handoff': ['Matched baseline/optimized outputs unavailable for behavioral equivalence evaluation.'].
- Phase A foundation gate rejected/did not accept 'workflow_parallelization': ['Matched baseline/optimized outputs unavailable for behavioral equivalence evaluation.', 'Parallelization did not demonstrate positive latency benefit (latency_improvement_pct=None).'].
- 1 historical trace(s) could not be matched by identifier and were excluded.