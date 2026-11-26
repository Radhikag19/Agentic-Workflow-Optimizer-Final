# Dimension-Wise Optimization, RAGAS Quality & Pareto Selection Report: `order_fulfillment_synthetic`

## 1. Experimental Setup

- **Workflow ID:** `order_fulfillment_synthetic`
- **Study ID:** `wp_20261125_204001_69771c`
- **Fixed Baseline Reference:** `hist_c86f1f3af77b` (re_executed=`False`, groq_api_calls=`0`)
- **Matched Inputs:** `10` | **Excluded / Unmatched Inputs:** `0`
- **Experiment IDs:** `wp_20261125_204001_69771c__phase_a_communication_data_handoff`, `wp_20261125_204001_69771c__phase_a_workflow_parallelization`, `wp_20261125_204001_69771c__phase_b_prompt_optimization`, `wp_20261125_204001_69771c__phase_b_agent_consolidation`, `wp_20261125_204001_69771c__phase_b_model_selection`, `wp_20261125_204001_69771c__phase_c_combined`
- **Optimized Runs Per Config (`num_runs`):** `2`
- **Execution Mode:** `local_subprocess_live_groq`
- **Quality Acceptance Criteria:** `{'min_structural_decision_score': 0.75, 'min_semantic_cosine': 0.75, 'min_llm_judge_score': 0.75, 'max_decision_flips': 0, 'max_regression_vs_foundation': 0.1}`

## 2. Fixed Foundation Evaluation

- **Accepted Fixed Optimization Foundation:** None
- **`communication_data_handoff`**: accepted=`False`, status=`rejected`, latency_delta=`-41.89%`, token_delta=`-94.61%`, Equivalence=(L1:`0.852`, L2:`0.8398`, L3:`disabled`, Flips:`13`)
- **`workflow_parallelization`**: accepted=`False`, status=`rejected`, latency_delta=`-227.24%`, token_delta=`-97.65%`, Equivalence=(L1:`0.7333`, L2:`0.6571`, L3:`disabled`, Flips:`2`)

## 3. Individual Variable-Dimension Evaluation

- **Fixed Foundation + `prompt_optimization`**: accepted=`False`, quality_status=`rejected`, latency=`47.1371s` (-304.59%), tokens=`17622.0` (-133.98%), cost=`$0.00565` (-156.0%), Equivalence=(L1:`0.5697`, L2:`0.5422`, L3:`disabled`, Flips:`11`)
- **Fixed Foundation + `agent_consolidation`**: accepted=`False`, quality_status=`rejected`, latency=`42.2737s` (-262.85%), tokens=`15681.0` (-108.21%), cost=`$0.004786` (-116.86%), Equivalence=(L1:`0.86`, L2:`0.8414`, L3:`disabled`, Flips:`10`)
- **Fixed Foundation + `model_selection`**: accepted=`False`, quality_status=`rejected`, latency=`27.315s` (-134.45%), tokens=`15361.0` (-103.96%), cost=`$0.004045` (-83.28%), Equivalence=(L1:`0.7167`, L2:`0.6336`, L3:`disabled`, Flips:`2`)

## 4. Combined Optimization

- **Applied Dimensions:** `prompt_optimization`, `agent_consolidation`, `model_selection`
- **Performance & Quality:** latency=`unavailable`, tokens=`unavailable`, cost=`$unavailable`, quality_accepted=`False`, Equivalence=(L1:`0.8219`, L2:`0.86`, L3:`disabled`, Flips:`6`)
- **Interactions / Regressions:** Combined configuration did not pass quality acceptance: ['Optimized runtime execution failed.', 'Optimized agent output schemas failed validation.'].

## 5. Comparative Metrics

| Configuration | Scope | Execution Passed | Mean Latency (s) | Input Tokens | Output Tokens | Total Tokens | Cost (USD) | Struct/Decision (L1) | Semantic Cosine (L2) | LLM Judge (L3) | Decision Flips | Quality Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `fixed_historical_baseline` | `historical_baseline` | `True` | 11.6505 | 5138.0 | 2393.5 | 7531.5 | 0.002207 | `reference_only` | `reference_only` | `disabled` | `0` | `HISTORICAL_REFERENCE` |
| `phase_a_communication_data_handoff` | `phase_a_foundation_candidate` | `True` | 16.5311 | 4937.0 | 4783.0 | 14657.0 | 0.004351 | `0.852` | `0.8398` | `disabled` | `13` | `rejected` |
| `phase_a_workflow_parallelization` | `phase_a_foundation_candidate` | `False` | 38.1256 | 5027.0 | 4832.0 | 14886.0 | 0.00441 | `0.7333` | `0.6571` | `disabled` | `2` | `rejected` |
| `prompt_optimization` | `variable_on_foundation` | `False` | 47.1371 | 5468.0 | 6686.0 | 17622.0 | 0.00565 | `0.5697` | `0.5422` | `disabled` | `11` | `rejected` |
| `agent_consolidation` | `variable_on_foundation` | `True` | 42.2737 | 5136.5 | 5408.0 | 15681.0 | 0.004786 | `0.86` | `0.8414` | `disabled` | `10` | `rejected` |
| `model_selection` | `variable_on_foundation` | `True` | 27.315 | 5390.5 | 4580.0 | 15361.0 | 0.004045 | `0.7167` | `0.6336` | `disabled` | `2` | `rejected` |
| `combined_workflow` | `combined` | `False` | unavailable | unavailable | unavailable | unavailable | unavailable | `0.8219` | `0.86` | `disabled` | `6` | `rejected` |

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
- Phase A foundation gate rejected/did not accept 'communication_data_handoff': ['decision_flip_count=13 > allowed 0'].
- Phase A foundation gate rejected/did not accept 'workflow_parallelization': ['Optimized runtime execution failed.', 'Optimized agent output schemas failed validation.', 'Parallelization did not demonstrate positive latency benefit (latency_improvement_pct=-227.24).'].