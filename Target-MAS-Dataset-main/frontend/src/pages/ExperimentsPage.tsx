import React, { useEffect, useMemo, useState } from 'react';
import {
  Play,
  AlertTriangle,
  CheckCircle2,
  Layers,
  ShieldCheck,
  Edit3,
} from 'lucide-react';
import { useWorkplaceStore } from '../store/workplaceStore';
import type { OptimizationDimension } from '../types/workplace';

const ALL_DIMENSIONS: { id: OptimizationDimension; label: string }[] = [
  { id: 'communication_data_handoff', label: '1. Communication / Data Handoff' },
  { id: 'workflow_parallelization', label: '2. Workflow Parallelization' },
  { id: 'model_selection', label: '3. Model Selection' },
  { id: 'agent_consolidation', label: '4. Agent Consolidation' },
  { id: 'prompt_optimization', label: '5. Prompt Optimization' },
];

type ExperimentMode = 'two_phase_study' | 'dimension_ablation_suite';

export const ExperimentsPage: React.FC = () => {
  const {
    overview,
    baseline,
    reviewData,
    experiments,
    activeExperimentId,
    activeExperimentStatus,
    startingExperiment,
    approvingScope,
    selectExperiment,
    startExperiment,
    approveWorkflowScope,
  } = useWorkplaceStore();

  const [experimentType, setExperimentType] = useState<ExperimentMode>('two_phase_study');
  const [selectedDims, setSelectedDims] = useState<OptimizationDimension[]>([
    'communication_data_handoff',
    'workflow_parallelization',
    'model_selection',
    'agent_consolidation',
    'prompt_optimization',
  ]);
  const [numRuns, setNumRuns] = useState<number>(2);
  const [maxFaithfulnessDrop, setMaxFaithfulnessDrop] = useState<number>(0.1);
  const [maxPrecisionDrop, setMaxPrecisionDrop] = useState<number>(0.1);
  const [maxRecallDrop, setMaxRecallDrop] = useState<number>(0.1);

  const [editingScope, setEditingScope] = useState<boolean>(false);
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<string[]>([]);
  const [riskAcknowledgedIds, setRiskAcknowledgedIds] = useState<string[]>([]);
  const [approvalSuccessMsg, setApprovalSuccessMsg] = useState<string | null>(null);

  const hasApprovedScope = Boolean(overview?.approved_scope && overview.approved_candidates.length > 0);
  const candidates = reviewData?.candidates ?? [];

  // Re-initialize human gate selections cleanly whenever the active workflow or review inventory changes.
  useEffect(() => {
    setEditingScope(false);
    setApprovalSuccessMsg(null);
    if (!reviewData || !reviewData.has_discovery_report) {
      setSelectedCandidateIds([]);
      setRiskAcknowledgedIds([]);
      return;
    }
    const existingApproved = reviewData.approved_candidate_ids || [];
    const preselected =
      existingApproved.length > 0
        ? existingApproved
        : reviewData.candidates.filter((c) => c.eligible).map((c) => c.candidate_id);
    setSelectedCandidateIds(preselected);

    const existingRiskAck = ((overview?.approved_scope?.risk_acknowledged_candidate_ids as string[]) || []);
    setRiskAcknowledgedIds(existingRiskAck);
  }, [overview?.workflow_id, reviewData?.has_discovery_report, reviewData?.approved_candidate_ids.join(',')]);

  const unacknowledgedSelectedRisks = useMemo(() => {
    const selectedSet = new Set(selectedCandidateIds);
    const ackSet = new Set(riskAcknowledgedIds);
    return candidates
      .filter((c) => selectedSet.has(c.candidate_id) && c.requires_risk_acknowledgement && !ackSet.has(c.candidate_id))
      .map((c) => c.candidate_id);
  }, [candidates, selectedCandidateIds, riskAcknowledgedIds]);

  const toggleDimension = (dim: OptimizationDimension) => {
    setSelectedDims((prev) =>
      prev.includes(dim) ? prev.filter((d) => d !== dim) : [...prev, dim]
    );
  };

  const toggleCandidate = (candidateId: string) => {
    setSelectedCandidateIds((prev) =>
      prev.includes(candidateId) ? prev.filter((id) => id !== candidateId) : [...prev, candidateId]
    );
  };

  const toggleRiskAck = (candidateId: string) => {
    setRiskAcknowledgedIds((prev) =>
      prev.includes(candidateId) ? prev.filter((id) => id !== candidateId) : [...prev, candidateId]
    );
  };

  const handleStart = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!overview) return;
    await startExperiment({
      workflow_id: overview.workflow_id,
      experiment_type: experimentType,
      selected_dimensions: experimentType === 'dimension_ablation_suite' ? selectedDims : undefined,
      num_runs: numRuns,
      quality_criteria: {
        max_faithfulness_drop: maxFaithfulnessDrop,
        max_context_precision_drop: maxPrecisionDrop,
        max_context_recall_drop: maxRecallDrop,
      },
      enable_trace_replay_fallback: false,
    });
  };

  const handleApproveScope = async () => {
    if (selectedCandidateIds.length === 0 || unacknowledgedSelectedRisks.length > 0) return;
    const ok = await approveWorkflowScope(selectedCandidateIds, riskAcknowledgedIds);
    if (ok) {
      setEditingScope(false);
      setApprovalSuccessMsg(
        `Approved ${selectedCandidateIds.length} candidate(s) for sandbox execution.`
      );
    }
  };

  const showHumanGateEditor = !hasApprovedScope || editingScope;
  const startDisabled =
    !hasApprovedScope ||
    startingExperiment ||
    (experimentType === 'dimension_ablation_suite' && selectedDims.length === 0);

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: 14 }}>
      {/* Left: Start Experiment Form */}
      <form onSubmit={handleStart} className="pixel-panel" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div className="pixel-title" style={{ fontSize: 11 }}>
          Optimization Experiment Runner
        </div>

        <div className="pixel-panel-inset mono" style={{ padding: 10, fontSize: 11 }}>
          <div>
            Workflow: <strong>{overview?.workflow_name}</strong> ({overview?.agents.length ?? 0} agents)
          </div>
          <div style={{ marginTop: 4 }}>
            Historical Baseline: <strong>{baseline?.matched_input_count ?? 0} matched records</strong> (Read-only • 0 Groq API calls)
          </div>
        </div>

        {!hasApprovedScope && (
          <div className="pixel-badge pixel-badge-warn" style={{ padding: 8, whiteSpace: 'normal' }}>
            <AlertTriangle size={15} />
            No approved_optimization_scope JSON exists for {overview?.workflow_id} yet. Review and approve candidates in the Human Gate Approval panel on the right to unlock sandbox execution.
          </div>
        )}

        {approvalSuccessMsg && (
          <div className="pixel-badge pixel-badge-pass" style={{ padding: 8, whiteSpace: 'normal' }}>
            <ShieldCheck size={15} />
            {approvalSuccessMsg}
          </div>
        )}

        <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 13 }}>
          <strong>Experiment Execution Mode</strong>
          <select
            className="pixel-select"
            aria-label="Experiment Execution Mode"
            value={experimentType}
            onChange={(e) => setExperimentType(e.target.value as ExperimentMode)}
          >
            <option value="two_phase_study">Pareto Beam Search</option>
            <option value="dimension_ablation_suite">Customized Optimizations</option>
          </select>
          <span className="mono" style={{ fontSize: 11, color: 'var(--ink-muted)' }}>
            {experimentType === 'two_phase_study'
              ? 'Complete optimization workflow: locks Fixed Foundation (Data Handoff + Parallelization) and evaluates remaining dimensions via Pareto search automatically.'
              : 'Run custom sandbox optimization across your selected dimensions below plus combined comparison.'}
          </span>
        </label>

        {experimentType === 'dimension_ablation_suite' && (
          <div>
            <strong style={{ fontSize: 13 }}>Select Optimization Dimensions (1 or more)</strong>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginTop: 6 }}>
              {ALL_DIMENSIONS.map((d) => (
                <label key={d.id} className="mono" style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
                  <input
                    type="checkbox"
                    checked={selectedDims.includes(d.id)}
                    onChange={() => toggleDimension(d.id)}
                  />
                  {d.label}
                </label>
              ))}
            </div>
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 8 }}>
          <label style={{ fontSize: 12 }}>
            <strong>Evaluated Runs (num_runs)</strong>
            <input
              type="number"
              min={1}
              max={10}
              className="pixel-input"
              style={{ width: '100%', marginTop: 4 }}
              value={numRuns}
              onChange={(e) => setNumRuns(Math.max(1, Math.min(10, Number(e.target.value) || 1)))}
            />
          </label>
          <label style={{ fontSize: 12 }}>
            <strong>Max Faithfulness Drop</strong>
            <input
              type="number"
              step="0.01"
              min={0}
              max={0.5}
              className="pixel-input"
              style={{ width: '100%', marginTop: 4 }}
              value={maxFaithfulnessDrop}
              onChange={(e) => setMaxFaithfulnessDrop(Number(e.target.value))}
            />
          </label>
          <label style={{ fontSize: 12 }}>
            <strong>Max Context Precision Drop</strong>
            <input
              type="number"
              step="0.01"
              min={0}
              max={0.5}
              className="pixel-input"
              style={{ width: '100%', marginTop: 4 }}
              value={maxPrecisionDrop}
              onChange={(e) => setMaxPrecisionDrop(Number(e.target.value))}
            />
          </label>
          <label style={{ fontSize: 12 }}>
            <strong>Max Context Recall Drop</strong>
            <input
              type="number"
              step="0.01"
              min={0}
              max={0.5}
              className="pixel-input"
              style={{ width: '100%', marginTop: 4 }}
              value={maxRecallDrop}
              onChange={(e) => setMaxRecallDrop(Number(e.target.value))}
            />
          </label>
        </div>

        <button
          type="submit"
          disabled={startDisabled}
          className="pixel-btn pixel-btn-primary"
          style={{ justifyContent: 'center', marginTop: 4 }}
        >
          <Play size={15} />
          {startingExperiment ? 'Launching Optimized Subprocess...' : 'Start Optimized Experiment (Live Groq)'}
        </button>

        {activeExperimentStatus && (
          <div className="pixel-panel-inset mono" style={{ padding: 10, fontSize: 11 }}>
            <div>
              Selected Run: <strong>{activeExperimentStatus.experiment_id}</strong> ({activeExperimentStatus.status})
            </div>
            {activeExperimentStatus.current_phase && (
              <div style={{ marginTop: 3 }}>Phase: {activeExperimentStatus.current_phase}</div>
            )}
            {activeExperimentStatus.error && (
              <div className="pixel-badge pixel-badge-fail" style={{ marginTop: 6 }}>
                Failure Diagnostics: {activeExperimentStatus.error}
              </div>
            )}
          </div>
        )}
      </form>

      {/* Right: Saved Experiments + Human Gate Approval / Approved Scope */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div className="pixel-panel" style={{ padding: 16 }}>
          <div className="pixel-title" style={{ fontSize: 11, marginBottom: 10 }}>
            Experiment History & Live Studies
          </div>
          {experiments.length === 0 ? (
            <div className="mono" style={{ fontSize: 12, color: 'var(--ink-muted)' }}>
              No saved experiments found for {overview?.workflow_id} yet.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {experiments.map((exp) => {
                const selected = exp.experiment_id === activeExperimentId;
                return (
                  <button
                    key={exp.experiment_id}
                    type="button"
                    onClick={() => selectExperiment(exp.experiment_id)}
                    className={`pixel-btn ${selected ? 'pixel-btn-amber' : ''}`}
                    style={{
                      width: '100%',
                      justifyContent: 'space-between',
                      textAlign: 'left',
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 700 }}>{exp.experiment_id}</div>
                      <div className="mono" style={{ fontSize: 11 }}>
                        {exp.experiment_type} • {exp.status}
                      </div>
                    </div>
                    {exp.has_results && <CheckCircle2 size={15} />}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <div className="pixel-panel" style={{ padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              {showHumanGateEditor ? <ShieldCheck size={15} /> : <Layers size={15} />}
              <span className="pixel-title" style={{ fontSize: 11 }}>
                {showHumanGateEditor
                  ? 'Human Gate Approval (Sandbox Scope)'
                  : `Approved Scope (${overview?.approved_candidates.length} candidates)`}
              </span>
            </div>
            {hasApprovedScope && (
              <button
                type="button"
                className="pixel-btn"
                style={{ fontSize: 11, padding: '4px 8px' }}
                onClick={() => setEditingScope((v) => !v)}
              >
                <Edit3 size={12} />
                {editingScope ? 'Cancel Edit' : 'Edit Approved Scope'}
              </button>
            )}
          </div>

          {!showHumanGateEditor ? (
            <div style={{ maxHeight: 320, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6 }}>
              {(overview?.approved_candidates || []).map((c, idx) => (
                <div key={c.candidate_id || idx} className="pixel-panel-inset mono" style={{ padding: 8, fontSize: 11 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <strong>{c.candidate_id}</strong>
                    <span className="pixel-badge pixel-badge-pass">
                      {c.optimization_type || c.dimension}
                    </span>
                  </div>
                  <div style={{ marginTop: 3 }}>
                    Agents: {(c.target_agents || []).join(', ') || 'workflow-wide'}
                  </div>
                  {c.title && <div style={{ color: 'var(--ink-muted)', marginTop: 2 }}>{c.title}</div>}
                </div>
              ))}
            </div>
          ) : !reviewData?.has_discovery_report ? (
            <div className="pixel-panel-inset mono" style={{ padding: 10, fontSize: 12, color: 'var(--ink-muted)' }}>
              No optimization discovery report (<code>{overview?.workflow_id}_optimization_report.json</code>) exists yet. Run discovery first to generate candidates for human approval.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                <button
                  type="button"
                  className="pixel-btn"
                  style={{ fontSize: 11, padding: '4px 8px' }}
                  onClick={() =>
                    setSelectedCandidateIds(candidates.filter((c) => c.eligible).map((c) => c.candidate_id))
                  }
                >
                  Select Eligible (Tier 1–3)
                </button>
                <button
                  type="button"
                  className="pixel-btn"
                  style={{ fontSize: 11, padding: '4px 8px' }}
                  onClick={() => setSelectedCandidateIds(candidates.map((c) => c.candidate_id))}
                >
                  Select All
                </button>
                <button
                  type="button"
                  className="pixel-btn"
                  style={{ fontSize: 11, padding: '4px 8px' }}
                  onClick={() => setSelectedCandidateIds([])}
                >
                  Clear
                </button>
              </div>

              <div style={{ maxHeight: 320, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
                {candidates.map((c) => {
                  const isSelected = selectedCandidateIds.includes(c.candidate_id);
                  const isRiskAck = riskAcknowledgedIds.includes(c.candidate_id);
                  return (
                    <div key={c.candidate_id} className="pixel-panel-inset mono" style={{ padding: 9, fontSize: 11 }}>
                      <label style={{ display: 'flex', alignItems: 'flex-start', gap: 8, cursor: 'pointer' }}>
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleCandidate(c.candidate_id)}
                        />
                        <div style={{ flex: 1 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 4 }}>
                            <strong>{c.candidate_id}</strong>
                            <div style={{ display: 'flex', gap: 4 }}>
                              <span className="pixel-badge pixel-badge-pass">{c.dimension_label}</span>
                              <span className="pixel-badge pixel-badge-warn">{c.tier}</span>
                            </div>
                          </div>
                          <div style={{ marginTop: 3 }}>
                            Agents: {(c.target_agents || []).join(', ') || 'workflow-wide'}
                          </div>
                          {c.title && (
                            <div style={{ color: 'var(--ink-muted)', marginTop: 2 }}>{c.title}</div>
                          )}
                          {(c.proposed_solution || c.observed_problem) && (
                            <div style={{ color: 'var(--ink-muted)', marginTop: 3 }}>
                              {c.proposed_solution || c.observed_problem}
                            </div>
                          )}
                        </div>
                      </label>

                      {isSelected && c.requires_risk_acknowledgement && (
                        <label
                          className="pixel-badge pixel-badge-warn"
                          style={{
                            display: 'flex',
                            alignItems: 'flex-start',
                            gap: 6,
                            marginTop: 6,
                            padding: 6,
                            whiteSpace: 'normal',
                            cursor: 'pointer',
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={isRiskAck}
                            onChange={() => toggleRiskAck(c.candidate_id)}
                          />
                          <span>
                            <strong>Acknowledge Risk:</strong>{' '}
                            {c.risk_warning || `Explicit risk review required (${c.risk_level || c.tier}).`}
                          </span>
                        </label>
                      )}
                    </div>
                  );
                })}
              </div>

              {unacknowledgedSelectedRisks.length > 0 && (
                <div className="mono" style={{ fontSize: 11, color: '#fbbf24' }}>
                  Acknowledge risks above before approving: {unacknowledgedSelectedRisks.join(', ')}
                </div>
              )}

              <button
                type="button"
                disabled={
                  approvingScope ||
                  selectedCandidateIds.length === 0 ||
                  unacknowledgedSelectedRisks.length > 0
                }
                onClick={handleApproveScope}
                className="pixel-btn pixel-btn-primary"
                style={{ justifyContent: 'center' }}
              >
                <ShieldCheck size={15} />
                {approvingScope
                  ? 'Saving Approved Scope...'
                  : `Approve Selected for Sandbox Execution (${selectedCandidateIds.length})`}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
