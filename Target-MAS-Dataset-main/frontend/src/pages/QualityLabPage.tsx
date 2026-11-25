import React, { useMemo, useState } from 'react';
import { ShieldCheck, AlertCircle, HelpCircle, Cpu } from 'lucide-react';
import { useWorkplaceStore } from '../store/workplaceStore';

function formatScoreValue(
  val: unknown,
  highThreshold = 0.85,
  minThreshold = 0.75
): { text: string; tone: 'pass' | 'warn' | 'fail' | 'unavail' } {
  if (val === null || val === undefined || val === 'unavailable' || val === 'disabled' || val === 'not_used') {
    return { text: val === 'disabled' ? 'Disabled (0 Calls)' : 'Unavailable', tone: 'unavail' };
  }
  if (val === 'reference_only') {
    return { text: 'Historical Ref', tone: 'unavail' };
  }
  if (typeof val === 'number' && Number.isFinite(val)) {
    const tone = val >= highThreshold ? 'pass' : val >= minThreshold ? 'warn' : 'fail';
    return { text: val.toFixed(4), tone };
  }
  return { text: String(val), tone: 'unavail' };
}

interface CollectedQualityEntry {
  key: string;
  label: string;
  metrics: Record<string, any>;
  evalRecord?: Record<string, any>;
}

export const QualityLabPage: React.FC = () => {
  const { activeExperimentId, activeExperimentResults } = useWorkplaceStore();
  const [selectedKey, setSelectedKey] = useState<string>('');

  const qualityEntries = useMemo<CollectedQualityEntry[]>(() => {
    if (!activeExperimentResults) return [];
    const list: CollectedQualityEntry[] = [];

    const paRagas = activeExperimentResults.phase_a_foundation?.ragas_evaluations || {};
    const paEvals = activeExperimentResults.phase_a_foundation?.dimension_evaluations || {};
    for (const [dim, rag] of Object.entries(paRagas)) {
      if (rag && typeof rag === 'object') {
        list.push({
          key: `phase_a:${dim}`,
          label: `Phase A — ${dim.replace(/_/g, ' ')}`,
          metrics: rag as Record<string, any>,
          evalRecord: paEvals[dim],
        });
      }
    }

    const pbRagas = activeExperimentResults.phase_b_variable_dimensions?.ragas_evaluations || {};
    const pbEvals = activeExperimentResults.phase_b_variable_dimensions?.dimension_evaluations || {};
    for (const [dim, rag] of Object.entries(pbRagas)) {
      if (rag && typeof rag === 'object') {
        list.push({
          key: `phase_b:${dim}`,
          label: `Phase B — ${dim.replace(/_/g, ' ')}`,
          metrics: rag as Record<string, any>,
          evalRecord: pbEvals[dim],
        });
      }
    }

    const perDim = activeExperimentResults.per_dimension_results || {};
    for (const [dim, item] of Object.entries(perDim)) {
      const rag = (item as any)?.ragas_evaluation;
      if (rag && typeof rag === 'object') {
        list.push({
          key: `per_dim:${dim}`,
          label: `Ablation — ${dim.replace(/_/g, ' ')}`,
          metrics: rag,
          evalRecord: item as Record<string, any>,
        });
      }
    }

    const combRag =
      activeExperimentResults.combined_result?.ragas_evaluation ||
      activeExperimentResults.phase_c_combined?.ragas_evaluation;
    if (combRag && typeof combRag === 'object') {
      list.push({
        key: 'combined',
        label: 'Combined Workflow',
        metrics: combRag,
        evalRecord: activeExperimentResults.phase_c_combined || activeExperimentResults.combined_result,
      });
    }

    return list;
  }, [activeExperimentResults]);

  const activeEntry =
    qualityEntries.find((e) => e.key === selectedKey) || qualityEntries[0] || null;

  const compRows = (activeExperimentResults?.comparative_configurations || []).filter(
    (r) => r.scope_kind !== 'historical_baseline'
  );

  const isEquivalenceMode =
    activeExperimentResults?.evaluation_mode === 'equivalence' ||
    activeEntry?.metrics?.evaluation_mode === 'equivalence' ||
    compRows.some((r) => typeof r.structural_decision_score === 'number');

  const judgeUsage = activeExperimentResults?.ragas_evaluation_model_usage || {};

  if (!activeExperimentResults) {
    return (
      <div className="pixel-panel" style={{ padding: 20 }}>
        <div className="pixel-title" style={{ fontSize: 11, marginBottom: 8 }}>
          Quality Lab (3-Layer Equivalence & RAGAS Engine)
        </div>
        <div className="mono" style={{ fontSize: 12, color: 'var(--ink-muted)' }}>
          Select or run an experiment in the Experiments tab to inspect 3-Layer Behavioral Equivalence (Structural/Decision Match, Semantic Cosine Similarity, Optional Pairwise LLM Judge) or legacy RAGAS verdicts.
        </div>
      </div>
    );
  }

  const samples: Record<string, any>[] =
    activeEntry?.metrics?.samples ||
    activeEntry?.metrics?.per_sample_scores ||
    [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* Metric Definitions & Judge Resource Banner */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
          gap: 12,
        }}
      >
        {isEquivalenceMode ? (
          <>
            <div className="pixel-panel" style={{ padding: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, fontSize: 13 }}>
                <HelpCircle size={15} /> Layer 1: Structural & Decision Match
              </div>
              <div className="mono" style={{ fontSize: 11, color: 'var(--ink-muted)', marginTop: 4 }}>
                Deterministic Key F1, exact equality on boolean/enum decisions, and numeric tolerance vs. baseline output (catches decision flips instantly, 0 Groq calls).
              </div>
            </div>
            <div className="pixel-panel" style={{ padding: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, fontSize: 13 }}>
                <HelpCircle size={15} /> Layer 2: Semantic Cosine Similarity
              </div>
              <div className="mono" style={{ fontSize: 11, color: 'var(--ink-muted)', marginTop: 4 }}>
                Compares Before vs. After narrative prose directly using local vector cosine similarity (0 Groq calls; never penalizes trimmed intermediate handoffs).
              </div>
            </div>
            <div className="pixel-panel" style={{ padding: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, fontSize: 13 }}>
                <HelpCircle size={15} /> Layer 3: Pairwise LLM Judge (Optional)
              </div>
              <div className="mono" style={{ fontSize: 11, color: 'var(--ink-muted)', marginTop: 4 }}>
                Optional 1-call pairwise check on decision agreement, key fact retention, and hallucination guard vs. historical baseline reference.
              </div>
            </div>
          </>
        ) : (
          <>
            <div className="pixel-panel" style={{ padding: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, fontSize: 13 }}>
                <HelpCircle size={15} /> Faithfulness
              </div>
              <div className="mono" style={{ fontSize: 11, color: 'var(--ink-muted)', marginTop: 4 }}>
                Measures whether every claim in the optimized agent response is grounded strictly in its upstream handoff context.
              </div>
            </div>
            <div className="pixel-panel" style={{ padding: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, fontSize: 13 }}>
                <HelpCircle size={15} /> Context Precision
              </div>
              <div className="mono" style={{ fontSize: 11, color: 'var(--ink-muted)', marginTop: 4 }}>
                Measures whether relevant context fields are preserved upfront without noisy filler in the agent handoff payload.
              </div>
            </div>
            <div className="pixel-panel" style={{ padding: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, fontSize: 13 }}>
                <HelpCircle size={15} /> Context Recall
              </div>
              <div className="mono" style={{ fontSize: 11, color: 'var(--ink-muted)', marginTop: 4 }}>
                Measures whether all essential historical reference information survived in intermediate contexts.
              </div>
            </div>
          </>
        )}

        <div className="pixel-panel" style={{ padding: 12, background: '#ece6f4' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, fontSize: 13 }}>
            <Cpu size={15} /> Separate Judge Usage
          </div>
          <div className="mono" style={{ fontSize: 11, marginTop: 4 }}>
            Calls: <strong>{judgeUsage.api_calls ?? 0}</strong> • Tokens:{' '}
            <strong>{judgeUsage.total_tokens ?? 0}</strong> • Cost:{' '}
            <strong>
              {typeof judgeUsage.estimated_cost_usd === 'number'
                ? `$${judgeUsage.estimated_cost_usd.toFixed(4)}`
                : '$0.0000'}
            </strong>
          </div>
          <div className="mono" style={{ fontSize: 10, color: 'var(--ink-muted)', marginTop: 2 }}>
            {isEquivalenceMode
              ? 'Layers 1 & 2 require 0 Groq calls; optional Layer 3 is tracked separately.'
              : 'Tracked separately — never mixed into MAS optimization metrics.'}
          </div>
        </div>
      </div>

      {/* Comparative Quality Gate Table across All Configurations */}
      {compRows.length > 0 && (
        <div className="pixel-panel" style={{ padding: 14 }}>
          <div className="pixel-title" style={{ fontSize: 11, marginBottom: 10 }}>
            {isEquivalenceMode ? '3-Layer Behavioral Equivalence Gate' : 'Quality Gate Verdicts'} — {activeExperimentId}
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }} className="mono">
              <thead>
                <tr style={{ background: 'var(--bg-inset)', textAlign: 'left' }}>
                  <th style={{ padding: 8, border: '2px solid var(--border-pixel)' }}>Configuration</th>
                  {isEquivalenceMode ? (
                    <>
                      <th style={{ padding: 8, border: '2px solid var(--border-pixel)' }}>Struct/Decision (L1)</th>
                      <th style={{ padding: 8, border: '2px solid var(--border-pixel)' }}>Semantic Cosine (L2)</th>
                      <th style={{ padding: 8, border: '2px solid var(--border-pixel)' }}>LLM Judge (L3)</th>
                      <th style={{ padding: 8, border: '2px solid var(--border-pixel)' }}>Decision Flips</th>
                    </>
                  ) : (
                    <>
                      <th style={{ padding: 8, border: '2px solid var(--border-pixel)' }}>Faithfulness</th>
                      <th style={{ padding: 8, border: '2px solid var(--border-pixel)' }}>Context Precision</th>
                      <th style={{ padding: 8, border: '2px solid var(--border-pixel)' }}>Context Recall</th>
                    </>
                  )}
                  <th style={{ padding: 8, border: '2px solid var(--border-pixel)' }}>Quality Gate</th>
                  <th style={{ padding: 8, border: '2px solid var(--border-pixel)' }}>Gate Reasons</th>
                </tr>
              </thead>
              <tbody>
                {compRows.map((row, idx) => {
                  const accepted = Boolean(row.quality_accepted);
                  if (isEquivalenceMode) {
                    const l1 = formatScoreValue(row.structural_decision_score, 0.9, 0.75);
                    const l2 = formatScoreValue(row.semantic_cosine_similarity, 0.9, 0.75);
                    const l3 = formatScoreValue(row.llm_judge_equivalence, 0.9, 0.75);
                    const flips = Number(row.decision_flip_count ?? 0);
                    return (
                      <tr key={idx}>
                        <td style={{ padding: 8, border: '1px solid #bfb59b', fontWeight: 700 }}>{row.name}</td>
                        <td style={{ padding: 8, border: '1px solid #bfb59b' }}>
                          <span className={`pixel-badge pixel-badge-${l1.tone}`}>{l1.text}</span>
                        </td>
                        <td style={{ padding: 8, border: '1px solid #bfb59b' }}>
                          <span className={`pixel-badge pixel-badge-${l2.tone}`}>{l2.text}</span>
                        </td>
                        <td style={{ padding: 8, border: '1px solid #bfb59b' }}>
                          <span className={`pixel-badge pixel-badge-${l3.tone}`}>{l3.text}</span>
                        </td>
                        <td style={{ padding: 8, border: '1px solid #bfb59b' }}>
                          <span className={`pixel-badge ${flips === 0 ? 'pixel-badge-pass' : 'pixel-badge-fail'}`}>
                            {flips}
                          </span>
                        </td>
                        <td style={{ padding: 8, border: '1px solid #bfb59b' }}>
                          <span className={`pixel-badge ${accepted ? 'pixel-badge-pass' : 'pixel-badge-fail'}`}>
                            {String(row.quality_status || (accepted ? 'ACCEPTED' : 'REJECTED'))}
                          </span>
                        </td>
                        <td style={{ padding: 8, border: '1px solid #bfb59b', fontSize: 11 }}>
                          {Array.isArray(row.quality_reasons) && row.quality_reasons.length > 0
                            ? row.quality_reasons.join('; ')
                            : accepted
                            ? 'Equivalent outputs preserved'
                            : 'Check sub-report'}
                        </td>
                      </tr>
                    );
                  }
                  const f = formatScoreValue(row.faithfulness, 0.85, 0.7);
                  const p = formatScoreValue(row.context_precision, 0.85, 0.7);
                  const r = formatScoreValue(row.context_recall, 0.85, 0.7);
                  return (
                    <tr key={idx}>
                      <td style={{ padding: 8, border: '1px solid #bfb59b', fontWeight: 700 }}>{row.name}</td>
                      <td style={{ padding: 8, border: '1px solid #bfb59b' }}>
                        <span className={`pixel-badge pixel-badge-${f.tone}`}>{f.text}</span>
                      </td>
                      <td style={{ padding: 8, border: '1px solid #bfb59b' }}>
                        <span className={`pixel-badge pixel-badge-${p.tone}`}>{p.text}</span>
                      </td>
                      <td style={{ padding: 8, border: '1px solid #bfb59b' }}>
                        <span className={`pixel-badge pixel-badge-${r.tone}`}>{r.text}</span>
                      </td>
                      <td style={{ padding: 8, border: '1px solid #bfb59b' }}>
                        <span className={`pixel-badge ${accepted ? 'pixel-badge-pass' : 'pixel-badge-fail'}`}>
                          {String(row.quality_status || (accepted ? 'ACCEPTED' : 'REJECTED'))}
                        </span>
                      </td>
                      <td style={{ padding: 8, border: '1px solid #bfb59b', fontSize: 11 }}>
                        {Array.isArray(row.quality_reasons) && row.quality_reasons.length > 0
                          ? row.quality_reasons.join('; ')
                          : accepted
                          ? 'Meets all configured thresholds'
                          : 'Unavailable / check sub-report'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Detailed Sample-Level Equivalence / RAGAS Drilldown */}
      {activeEntry && (
        <div className="pixel-panel" style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <ShieldCheck size={16} />
              <span className="pixel-title" style={{ fontSize: 11 }}>
                {isEquivalenceMode
                  ? 'Sample-Level Before vs. After Equivalence Inspector'
                  : 'Sample-Level RAGAS Context Inspector'}
              </span>
            </div>

            <select
              className="pixel-select"
              value={activeEntry.key}
              onChange={(e) => setSelectedKey(e.target.value)}
            >
              {qualityEntries.map((ent) => (
                <option key={ent.key} value={ent.key}>
                  {ent.label}
                </option>
              ))}
            </select>
          </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
            {activeEntry.metrics?.evaluation_mode === 'equivalence' || isEquivalenceMode ? (
              <>
                <span className={`pixel-badge pixel-badge-${formatScoreValue(activeEntry.metrics?.structural_decision_score, 0.9, 0.75).tone}`}>
                  L1 Struct/Decision: {formatScoreValue(activeEntry.metrics?.structural_decision_score, 0.9, 0.75).text}
                </span>
                <span className={`pixel-badge pixel-badge-${formatScoreValue(activeEntry.metrics?.semantic_cosine_similarity, 0.9, 0.75).tone}`}>
                  L2 Semantic Cosine: {formatScoreValue(activeEntry.metrics?.semantic_cosine_similarity, 0.9, 0.75).text}
                </span>
                <span className={`pixel-badge pixel-badge-${formatScoreValue(activeEntry.metrics?.llm_judge_equivalence, 0.9, 0.75).tone}`}>
                  L3 LLM Judge: {formatScoreValue(activeEntry.metrics?.llm_judge_equivalence, 0.9, 0.75).text}
                </span>
                <span className="pixel-badge pixel-badge-unavail">
                  Flips: {String(activeEntry.metrics?.decision_flip_count ?? 0)} • Backend: {String(activeEntry.metrics?.semantic_backend || 'tfidf')}
                </span>
              </>
            ) : (
              <>
                <span className={`pixel-badge pixel-badge-${formatScoreValue(activeEntry.metrics?.faithfulness, 0.85, 0.7).tone}`}>
                  Faithfulness: {formatScoreValue(activeEntry.metrics?.faithfulness, 0.85, 0.7).text}
                </span>
                <span className={`pixel-badge pixel-badge-${formatScoreValue(activeEntry.metrics?.context_precision, 0.85, 0.7).tone}`}>
                  Context Precision: {formatScoreValue(activeEntry.metrics?.context_precision, 0.85, 0.7).text}
                </span>
                <span className={`pixel-badge pixel-badge-${formatScoreValue(activeEntry.metrics?.context_recall, 0.85, 0.7).tone}`}>
                  Context Recall: {formatScoreValue(activeEntry.metrics?.context_recall, 0.85, 0.7).text}
                </span>
                <span className="pixel-badge pixel-badge-unavail">
                  RAGAS Status: {String(activeEntry.metrics?.status || 'unknown')}
                </span>
              </>
            )}
          </div>

          {Array.isArray(activeEntry.metrics?.missing_context_samples) &&
            activeEntry.metrics.missing_context_samples.length > 0 && (
              <div className="pixel-badge pixel-badge-warn" style={{ padding: 8 }}>
                <AlertCircle size={14} />
                Missing context detected on {activeEntry.metrics.missing_context_samples.length} sample(s); never interpolated to 0.
              </div>
            )}

          {samples.length === 0 ? (
            <div className="mono" style={{ fontSize: 12, color: 'var(--ink-muted)' }}>
              No sample-level payload records included in this section.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 360, overflowY: 'auto' }}>
              {samples.slice(0, 12).map((samp, idx) => (
                <div key={idx} className="pixel-panel-inset mono" style={{ padding: 10, fontSize: 11 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 6 }}>
                    <strong>
                      Sample #{idx + 1} {samp.agent_id ? `• ${samp.agent_id}` : ''}
                    </strong>
                    <div style={{ display: 'flex', gap: 8 }}>
                      {typeof samp.structural_decision_score === 'number' ? (
                        <>
                          <span>L1: {formatScoreValue(samp.structural_decision_score, 0.9, 0.75).text}</span>
                          <span>L2: {formatScoreValue(samp.semantic_cosine_similarity, 0.9, 0.75).text}</span>
                          <span>Flips: {samp.decision_flip_count ?? 0}</span>
                        </>
                      ) : (
                        <>
                          <span>F: {formatScoreValue(samp.faithfulness, 0.85, 0.7).text}</span>
                          <span>P: {formatScoreValue(samp.context_precision, 0.85, 0.7).text}</span>
                          <span>R: {formatScoreValue(samp.context_recall, 0.85, 0.7).text}</span>
                        </>
                      )}
                    </div>
                  </div>
                  {Array.isArray(samp.decision_mismatches) && samp.decision_mismatches.length > 0 && (
                    <div className="pixel-badge pixel-badge-fail" style={{ marginTop: 4, padding: 4, whiteSpace: 'normal' }}>
                      Decision Mismatch: {JSON.stringify(samp.decision_mismatches[0])}
                    </div>
                  )}
                  {samp.reference && (
                    <div style={{ marginTop: 3, color: 'var(--ink-espresso)' }}>
                      <strong>Before (Baseline Ref):</strong> {String(samp.reference).slice(0, 180)}
                    </div>
                  )}
                  {samp.response && (
                    <div style={{ marginTop: 3, color: 'var(--accent-forest)' }}>
                      <strong>After (Optimized):</strong> {String(samp.response).slice(0, 180)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
