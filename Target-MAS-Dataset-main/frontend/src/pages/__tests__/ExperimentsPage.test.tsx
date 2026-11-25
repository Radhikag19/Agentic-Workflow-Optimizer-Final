import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ExperimentsPage } from '../ExperimentsPage';
import { useWorkplaceStore } from '../../store/workplaceStore';

describe('ExperimentsPage execution modes & human gate approval', () => {
  beforeEach(() => {
    useWorkplaceStore.setState({
      selectedWorkflowId: 'contract_review',
      overview: {
        workflow_id: 'contract_review',
        workflow_name: 'Contract Review Workflow',
        baseline_model: 'openai/gpt-oss-120b',
        llm_provider: 'Groq',
        agents: [
          {
            agent_id: 'clause_extraction_agent',
            agent_name: 'Clause Extraction Agent',
            role: 'Extractor',
            responsibilities: ['Extract clauses'],
            dependencies: [],
            input_fields: ['contract_text'],
            output_fields: ['clauses'],
            model: 'openai/gpt-oss-120b',
          },
        ],
        execution_order: ['clause_extraction_agent'],
        historical_baseline: {
          source: 'historical_runtime_traces',
          re_executed: false,
          groq_api_calls: 0,
          matched_input_count: 5,
          metrics: {},
        },
        approved_scope: null,
        approved_candidates: [],
        discovered_candidates_by_dimension: {},
      },
      baseline: {
        workflow_id: 'contract_review',
        source: 'historical_runtime_traces',
        execution_mode: 'historical_recorded_execution',
        re_executed: false,
        groq_api_calls: 0,
        total_historical_traces_found: 5,
        matched_input_count: 5,
        unmatched_input_count: 0,
        excluded_records: [],
        execution_order: ['clause_extraction_agent'],
        historical_model: 'openai/gpt-oss-120b',
        metrics: {},
        traces: [],
      },
      reviewData: {
        workflow_id: 'contract_review',
        has_discovery_report: true,
        has_approved_scope: false,
        approved_candidate_ids: [],
        summary: {},
        dimension_counts: [],
        candidates: [
          {
            candidate_id: 'PROMPT-CLAUSE_EXTRACTION_AGENT',
            dimension: 'prompt_optimization',
            dimension_label: 'Prompt Optimization',
            title: 'Compress verbose clause extraction prompt',
            tier: 'Tier 1',
            target_agents: ['clause_extraction_agent'],
            requires_validation: false,
            requires_risk_acknowledgement: false,
            eligible: true,
            already_approved: false,
          },
        ],
      },
      experiments: [],
      activeExperimentId: null,
      activeExperimentStatus: null,
      startingExperiment: false,
      approvingScope: false,
    });
  });

  it('shows exactly two execution mode options and reveals dimension checkboxes only in Customized Optimizations', () => {
    render(<ExperimentsPage />);

    const modeSelect = screen.getByLabelText('Experiment Execution Mode') as HTMLSelectElement;
    const optionLabels = Array.from(modeSelect.options).map((o) => o.textContent);
    expect(optionLabels).toEqual(['Pareto Beam Search', 'Customized Optimizations']);

    // Hidden under default Pareto Beam Search
    expect(screen.queryByText('Select Optimization Dimensions (1 or more)')).toBeNull();
    expect(screen.queryByText('3. Model Selection')).toBeNull();

    // Shown when switching to Customized Optimizations
    fireEvent.change(modeSelect, { target: { value: 'dimension_ablation_suite' } });
    expect(screen.getByText('Select Optimization Dimensions (1 or more)')).toBeInTheDocument();
    expect(screen.getByText('3. Model Selection')).toBeInTheDocument();
  });

  it('renders Human Gate Approval panel when unapproved and calls approveWorkflowScope on click', async () => {
    const approveSpy = vi.fn().mockResolvedValue(true);
    useWorkplaceStore.setState({ approveWorkflowScope: approveSpy });

    render(<ExperimentsPage />);

    expect(screen.getByText('Human Gate Approval (Sandbox Scope)')).toBeInTheDocument();
    const approveBtn = screen.getByRole('button', {
      name: /Approve Selected for Sandbox Execution/i,
    });
    expect(approveBtn).not.toBeDisabled();

    fireEvent.click(approveBtn);
    expect(approveSpy).toHaveBeenCalledWith(['PROMPT-CLAUSE_EXTRACTION_AGENT'], []);
  });

  it('defaults Quality Evaluation Engine to 3-Layer Behavioral Equivalence and toggles cleanly with RAGAS', () => {
    render(<ExperimentsPage />);

    const evalSelect = screen.getByLabelText('Quality Evaluation Engine') as HTMLSelectElement;
    expect(evalSelect.value).toBe('equivalence');
    expect(screen.getByText('Min Structural/Decision Match')).toBeInTheDocument();
    expect(screen.getByText('Min Semantic Cosine')).toBeInTheDocument();
    expect(screen.getByText('Max Decision Flips')).toBeInTheDocument();

    fireEvent.change(evalSelect, { target: { value: 'ragas' } });
    expect(screen.getByText('Max Faithfulness Drop')).toBeInTheDocument();
  });
});
