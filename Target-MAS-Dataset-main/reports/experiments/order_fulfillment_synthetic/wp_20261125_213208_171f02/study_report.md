# Dimension-Wise Optimization, RAGAS Quality & Pareto Selection Report: `order_fulfillment_synthetic`

## 1. Experimental Setup

- **Workflow ID:** `order_fulfillment_synthetic`
- **Study ID:** `wp_20261125_213208_171f02`
- **Fixed Baseline Reference:** `hist_859e698746d5` (re_executed=`False`, groq_api_calls=`0`)
- **Matched Inputs:** `10` | **Excluded / Unmatched Inputs:** `0`
- **Experiment IDs:** `wp_20261125_213208_171f02__phase_a_communication_data_handoff`, `wp_20261125_213208_171f02__phase_a_workflow_parallelization`, `wp_20261125_213208_171f02__phase_b_prompt_optimization`, `wp_20261125_213208_171f02__phase_b_agent_consolidation`, `wp_20261125_213208_171f02__phase_b_model_selection`, `wp_20261125_213208_171f02__phase_c_combined`
- **Optimized Runs Per Config (`num_runs`):** `2`
- **Execution Mode:** `local_subprocess_live_groq`
- **Quality Acceptance Criteria:** `{'min_structural_decision_score': 0.75, 'min_semantic_cosine': 0.75, 'min_llm_judge_score': 0.75, 'max_decision_flips': 5, 'max_regression_vs_foundation': 0.1}`

## 2. Fixed Foundation Evaluation

- **Accepted Fixed Optimization Foundation:** `communication_data_handoff`
- **`communication_data_handoff`**: accepted=`True`, status=`accepted`, latency_delta=`-154.04%`, token_delta=`-93.03%`, Equivalence=(L1:`1.0`, L2:`1.0`, L3:`1.0`, Flips:`0`)
- **`workflow_parallelization`**: accepted=`False`, status=`accepted`, latency_delta=`-117.93%`, token_delta=`-111.0%`, Equivalence=(L1:`1.0`, L2:`1.0`, L3:`1.0`, Flips:`0`)
- **`fixed_foundation` Combined Gate**: latency=`29.2155s`, tokens=`18056.0`, cost=`$0.005282`, Equivalence=(L1:`1.0`, L2:`1.0`, L3:`1.0`, Flips:`0`)

## 3. Individual Variable-Dimension Evaluation

- **Fixed Foundation + `prompt_optimization`**: accepted=`True`, quality_status=`accepted`, latency=`34.8633s` (-203.15%), tokens=`15582.0` (-66.58%), cost=`$0.00479` (-75.72%), Equivalence=(L1:`1.0`, L2:`1.0`, L3:`1.0`, Flips:`0`)
- **Fixed Foundation + `agent_consolidation`**: accepted=`True`, quality_status=`accepted`, latency=`73.1925s` (-536.43%), tokens=`16790.0` (-79.5%), cost=`$0.004928` (-80.78%), Equivalence=(L1:`0.9953`, L2:`0.9835`, L3:`0.9775`, Flips:`0`)
- **Fixed Foundation + `model_selection`**: accepted=`True`, quality_status=`accepted`, latency=`29.0054s` (-152.21%), tokens=`17587.0` (-88.02%), cost=`$0.004579` (-67.98%), Equivalence=(L1:`1.0`, L2:`1.0`, L3:`1.0`, Flips:`0`)

## 4. Combined Optimization

- **Applied Dimensions:** `communication_data_handoff`, `prompt_optimization`, `agent_consolidation`, `model_selection`
- **Performance & Quality:** latency=`26.1607s`, tokens=`14286.0`, cost=`$0.003885`, quality_accepted=`True`, Equivalence=(L1:`0.9953`, L2:`0.9835`, L3:`0.9812`, Flips:`0`)

## 5. Comparative Metrics

| Configuration | Scope | Execution Passed | Mean Latency (s) | Input Tokens | Output Tokens | Total Tokens | Cost (USD) | Struct/Decision (L1) | Semantic Cosine (L2) | LLM Judge (L3) | Decision Flips | Quality Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `fixed_historical_baseline` | `historical_baseline` | `True` | 11.5005 | 6414.5 | 2939.5 | 9354.0 | 0.002726 | `reference_only` | `reference_only` | `disabled` | `0` | `HISTORICAL_REFERENCE` |
| `phase_a_communication_data_handoff` | `phase_a_foundation_candidate` | `True` | 29.2155 | 6168.0 | 5720.0 | 18056.0 | 0.005282 | `1.0` | `1.0` | `1.0` | `0` | `accepted` |
| `phase_a_workflow_parallelization` | `phase_a_foundation_candidate` | `True` | 25.0626 | 7054.5 | 5628.0 | 19737.0 | 0.005494 | `1.0` | `1.0` | `1.0` | `0` | `accepted` |
| `foundation_plus_prompt_optimization` | `variable_on_foundation` | `True` | 34.8633 | 5064.0 | 5454.0 | 15582.0 | 0.00479 | `1.0` | `1.0` | `1.0` | `0` | `accepted` |
| `foundation_plus_agent_consolidation` | `variable_on_foundation` | `True` | 73.1925 | 5715.5 | 5359.0 | 16790.0 | 0.004928 | `0.9953` | `0.9835` | `0.9775` | `0` | `accepted` |
| `foundation_plus_model_selection` | `variable_on_foundation` | `True` | 29.0054 | 6168.0 | 5251.0 | 17587.0 | 0.004579 | `1.0` | `1.0` | `1.0` | `0` | `accepted` |
| `combined_workflow` | `combined` | `True` | 26.1607 | 4611.5 | 5063.0 | 14286.0 | 0.003885 | `0.9953` | `0.9835` | `0.9812` | `0` | `accepted` |

## 6. Best Configuration Selection

- **Pareto-Efficient Configurations (Non-Dominated, Quality-Accepted):** `combined_workflow`
- **Best Latency Configuration:** `combined_workflow`
- **Best Token-Efficiency Configuration:** `combined_workflow`
- **Best Cost-Efficiency Configuration:** `combined_workflow`
- **Recommended Overall Configuration:** `combined_workflow`
- **Selection Note:** Single Pareto-efficient configuration 'combined_workflow' dominates all other quality-accepted configurations across latency, tokens, and cost.

## 7. Limitations and Final Assessment

- **Original Workflow Unchanged (SHA-256 Verified):** `True`
- **Isolated RAGAS Evaluator Usage (Excluded from Workflow Tokens/Cost):** calls=`41`, tokens=`25160`, cost=`$0.008092`
- Historical baseline metrics are from prior recorded executions rather than live concurrent re-execution.
- Phase A foundation gate rejected/did not accept 'workflow_parallelization': ['All 3-layer behavioral equivalence thresholds satisfied.', 'Parallelization did not demonstrate positive latency benefit (latency_improvement_pct=-117.93).'].