# Dimension-Wise Optimization, RAGAS Quality & Pareto Selection Report: `order_fulfillment_synthetic`

## 1. Experimental Setup

- **Workflow ID:** `order_fulfillment_synthetic`
- **Study ID:** `wp_synth_5dim_live_20261126_024837`
- **Fixed Baseline Reference:** `hist_859e698746d5` (re_executed=`False`, groq_api_calls=`0`)
- **Matched Inputs:** `10` | **Excluded / Unmatched Inputs:** `0`
- **Experiment IDs:** `wp_synth_5dim_live_20261126_024837__phase_a_communication_data_handoff`, `wp_synth_5dim_live_20261126_024837__phase_a_workflow_parallelization`, `wp_synth_5dim_live_20261126_024837__phase_b_prompt_optimization`, `wp_synth_5dim_live_20261126_024837__phase_b_agent_consolidation`, `wp_synth_5dim_live_20261126_024837__phase_b_model_selection`, `wp_synth_5dim_live_20261126_024837__phase_c_combined`
- **Optimized Runs Per Config (`num_runs`):** `2`
- **Execution Mode:** `local_subprocess_live_groq`
- **Quality Acceptance Criteria:** `{'min_structural_decision_score': 0.75, 'min_semantic_cosine': 0.75, 'min_llm_judge_score': 0.75, 'max_decision_flips': 0, 'max_regression_vs_foundation': 0.1}`

## 2. Fixed Foundation Evaluation

- **Accepted Fixed Optimization Foundation:** `communication_data_handoff`
- **`communication_data_handoff`**: accepted=`True`, status=`accepted`, latency_delta=`-219.66%`, token_delta=`-91.48%`, Equivalence=(L1:`1.0`, L2:`1.0`, L3:`disabled`, Flips:`0`)
- **`workflow_parallelization`**: accepted=`False`, status=`accepted`, latency_delta=`-408.46%`, token_delta=`-99.71%`, Equivalence=(L1:`1.0`, L2:`1.0`, L3:`disabled`, Flips:`0`)
- **`fixed_foundation` Combined Gate**: latency=`36.7625s`, tokens=`17911.0`, cost=`$0.005194`, Equivalence=(L1:`1.0`, L2:`1.0`, L3:`disabled`, Flips:`0`)

## 3. Individual Variable-Dimension Evaluation

- **Fixed Foundation + `prompt_optimization`**: accepted=`True`, quality_status=`accepted`, latency=`35.7069s` (-210.48%), tokens=`15861.0` (-69.56%), cost=`$0.004959` (-81.91%), Equivalence=(L1:`1.0`, L2:`1.0`, L3:`disabled`, Flips:`0`)
- **Fixed Foundation + `agent_consolidation`**: accepted=`True`, quality_status=`accepted`, latency=`57.9047s` (-403.5%), tokens=`17154.0` (-83.39%), cost=`$0.005147` (-88.81%), Equivalence=(L1:`0.9953`, L2:`0.9835`, L3:`disabled`, Flips:`0`)
- **Fixed Foundation + `model_selection`**: accepted=`True`, quality_status=`accepted`, latency=`38.2211s` (-232.34%), tokens=`17834.0` (-90.66%), cost=`$0.004579` (-67.98%), Equivalence=(L1:`1.0`, L2:`1.0`, L3:`disabled`, Flips:`0`)

## 4. Combined Optimization

- **Applied Dimensions:** `communication_data_handoff`, `prompt_optimization`, `agent_consolidation`, `model_selection`
- **Performance & Quality:** latency=`38.142s`, tokens=`14443.0`, cost=`$0.00399`, quality_accepted=`True`, Equivalence=(L1:`0.9953`, L2:`0.9835`, L3:`disabled`, Flips:`0`)

## 5. Comparative Metrics

| Configuration | Scope | Execution Passed | Mean Latency (s) | Input Tokens | Output Tokens | Total Tokens | Cost (USD) | Struct/Decision (L1) | Semantic Cosine (L2) | LLM Judge (L3) | Decision Flips | Quality Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `fixed_historical_baseline` | `historical_baseline` | `True` | 11.5005 | 6414.5 | 2939.5 | 9354.0 | 0.002726 | `reference_only` | `reference_only` | `disabled` | `0` | `HISTORICAL_REFERENCE` |
| `phase_a_communication_data_handoff` | `phase_a_foundation_candidate` | `True` | 36.7625 | 6168.0 | 5575.0 | 17911.0 | 0.005194 | `1.0` | `1.0` | `disabled` | `0` | `accepted` |
| `phase_a_workflow_parallelization` | `phase_a_foundation_candidate` | `True` | 58.4753 | 6414.5 | 5852.0 | 18681.0 | 0.005433 | `1.0` | `1.0` | `disabled` | `0` | `accepted` |
| `foundation_plus_prompt_optimization` | `variable_on_foundation` | `True` | 35.7069 | 5064.0 | 5733.0 | 15861.0 | 0.004959 | `1.0` | `1.0` | `disabled` | `0` | `accepted` |
| `foundation_plus_agent_consolidation` | `variable_on_foundation` | `True` | 57.9047 | 5715.5 | 5723.0 | 17154.0 | 0.005147 | `0.9953` | `0.9835` | `disabled` | `0` | `accepted` |
| `foundation_plus_model_selection` | `variable_on_foundation` | `True` | 38.2211 | 6168.0 | 5498.0 | 17834.0 | 0.004579 | `1.0` | `1.0` | `disabled` | `0` | `accepted` |
| `combined_workflow` | `combined` | `True` | 38.142 | 4611.5 | 5220.0 | 14443.0 | 0.00399 | `0.9953` | `0.9835` | `disabled` | `0` | `accepted` |

## 6. Best Configuration Selection

- **Pareto-Efficient Configurations (Non-Dominated, Quality-Accepted):** `foundation_plus_prompt_optimization`, `combined_workflow`
- **Best Latency Configuration:** `foundation_plus_prompt_optimization`
- **Best Token-Efficiency Configuration:** `combined_workflow`
- **Best Cost-Efficiency Configuration:** `combined_workflow`
- **Recommended Overall Configuration:** `None (see selection note)`
- **Selection Note:** Multiple Pareto-efficient configurations exist (['foundation_plus_prompt_optimization', 'combined_workflow']); reporting all non-dominated alternatives cleanly rather than inventing an arbitrary weighted preference.

## 7. Limitations and Final Assessment

- **Original Workflow Unchanged (SHA-256 Verified):** `True`
- **Isolated RAGAS Evaluator Usage (Excluded from Workflow Tokens/Cost):** calls=`0`, tokens=`0`, cost=`$0.0`
- Historical baseline metrics are from prior recorded executions rather than live concurrent re-execution.
- Phase A foundation gate rejected/did not accept 'workflow_parallelization': ['All 3-layer behavioral equivalence thresholds satisfied.', 'Parallelization did not demonstrate positive latency benefit (latency_improvement_pct=-408.46).'].