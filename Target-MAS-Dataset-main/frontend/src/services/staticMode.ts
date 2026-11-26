import type {
  AgentProfile,
  ApproveScopeRequest,
  BaselineResponse,
  ExperimentResultsResponse,
  ExperimentStartRequest,
  ExperimentStatusResponse,
  OfficeEvent,
  ReportBundleResponse,
  WorkflowOverviewResponse,
  WorkflowReviewResponse,
  WorkflowSummary,
} from '../types/workplace';

export function isStaticDemoMode(): boolean {
  return import.meta.env.VITE_STATIC_MODE === 'true';
}

const staticJsonCache = new Map<string, any>();
const approvedScopeOverrides = new Map<string, string[]>();
const simulatedExperiments = new Map<
  string,
  {
    status: ExperimentStatusResponse;
    backingExperimentId: string | null;
    events: OfficeEvent[];
  }
>();

async function fetchDemoJson<T>(relativePath: string): Promise<T> {
  const base = import.meta.env.BASE_URL || '/';
  const normalizedBase = base.endsWith('/') ? base : `${base}/`;
  const url = `${normalizedBase}demo-data/${relativePath}`;
  if (staticJsonCache.has(url)) {
    return structuredClone(staticJsonCache.get(url)) as T;
  }
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Demo artifact missing (${res.status}): ${url}`);
  }
  const data = (await res.json()) as T;
  staticJsonCache.set(url, data);
  return structuredClone(data);
}

function applyScopeOverrideToOverview(
  workflowId: string,
  overview: WorkflowOverviewResponse
): WorkflowOverviewResponse {
  const overrideIds = approvedScopeOverrides.get(workflowId);
  if (!overrideIds) return overview;

  const idSet = new Set(overrideIds);
  const allDiscovered = Object.values(overview.discovered_candidates_by_dimension || {}).flat();
  const nextApproved = allDiscovered.filter((c) => idSet.has(c.candidate_id));
  return {
    ...overview,
    approved_scope: {
      ...(overview.approved_scope || {}),
      workflow_id: workflowId,
      approved_candidates: nextApproved,
    },
    approved_candidates: nextApproved,
  };
}

export const staticWorkplaceApi = {
  getHealth: async () => ({ status: 'ok', service: 'agentic-workplace-static-demo' }),

  listWorkflows: async (): Promise<WorkflowSummary[]> => {
    const items = await fetchDemoJson<WorkflowSummary[]>('workflows.json');
    return items.map((wf) => {
      const override = approvedScopeOverrides.get(wf.workflow_id);
      if (!override) return wf;
      return {
        ...wf,
        has_approved_scope: override.length > 0,
        approved_candidate_count: override.length,
      };
    });
  },

  getWorkflowOverview: async (workflowId: string): Promise<WorkflowOverviewResponse> => {
    const ov = await fetchDemoJson<WorkflowOverviewResponse>(
      `workflows/${encodeURIComponent(workflowId)}/overview.json`
    );
    return applyScopeOverrideToOverview(workflowId, ov);
  },

  getWorkflowBaseline: async (workflowId: string): Promise<BaselineResponse> =>
    fetchDemoJson<BaselineResponse>(`workflows/${encodeURIComponent(workflowId)}/baseline.json`),

  getWorkflowReview: async (workflowId: string): Promise<WorkflowReviewResponse> => {
    const rev = await fetchDemoJson<WorkflowReviewResponse>(
      `workflows/${encodeURIComponent(workflowId)}/review.json`
    );
    const override = approvedScopeOverrides.get(workflowId);
    if (!override) return rev;
    const idSet = new Set(override);
    return {
      ...rev,
      has_approved_scope: override.length > 0,
      approved_candidate_ids: [...override],
      candidates: (rev.candidates || []).map((c) => ({
        ...c,
        already_approved: idSet.has(c.candidate_id),
      })),
    };
  },

  approveWorkflowScope: async (
    workflowId: string,
    payload: ApproveScopeRequest
  ): Promise<Record<string, any>> => {
    const ids = [...(payload.selected_candidate_ids || [])];
    approvedScopeOverrides.set(workflowId, ids);
    return {
      workflow_id: workflowId,
      approved_candidate_ids: ids,
      simulated_persistence: true,
    };
  },

  getWorkflowAgents: async (workflowId: string): Promise<AgentProfile[]> =>
    fetchDemoJson<AgentProfile[]>(`workflows/${encodeURIComponent(workflowId)}/agents.json`),

  listExperiments: async (workflowId?: string): Promise<ExperimentStatusResponse[]> => {
    const index = await fetchDemoJson<ExperimentStatusResponse[]>('experiments/index.json');
    const simList = Array.from(simulatedExperiments.values()).map((s) => s.status);
    const merged = [...simList, ...index];
    return workflowId ? merged.filter((e) => e.workflow_id === workflowId) : merged;
  },

  startExperiment: async (payload: ExperimentStartRequest): Promise<ExperimentStatusResponse> => {
    const index = await fetchDemoJson<ExperimentStatusResponse[]>('experiments/index.json');
    const match =
      index.find(
        (e) =>
          e.workflow_id === payload.workflow_id && e.experiment_type === payload.experiment_type
      ) ||
      index.find((e) => e.workflow_id === payload.workflow_id) ||
      null;

    const nowIso = new Date().toISOString();
    const expId = `sim_${nowIso.replace(/[-:T.Z]/g, '').slice(0, 14)}_${Math.random()
      .toString(36)
      .slice(2, 6)}`;

    const created: ExperimentStatusResponse = {
      experiment_id: expId,
      workflow_id: payload.workflow_id,
      experiment_type: payload.experiment_type,
      status: 'running',
      created_at: nowIso,
      started_at: nowIso,
      completed_at: null,
      current_phase: 'sandbox_created',
      progress_pct: 5,
      error: null,
      has_results: Boolean(match),
      json_report_path: match?.json_report_path || null,
      markdown_report_path: match?.markdown_report_path || null,
    };

    simulatedExperiments.set(expId, {
      status: created,
      backingExperimentId: match?.experiment_id || null,
      events: [],
    });

    return structuredClone(created);
  },

  getExperimentStatus: async (experimentId: string): Promise<ExperimentStatusResponse> => {
    const sim = simulatedExperiments.get(experimentId);
    if (sim) return structuredClone(sim.status);
    return fetchDemoJson<ExperimentStatusResponse>(
      `experiments/${encodeURIComponent(experimentId)}/status.json`
    );
  },

  getExperimentResults: async (experimentId: string): Promise<ExperimentResultsResponse> => {
    const sim = simulatedExperiments.get(experimentId);
    const targetId = sim ? sim.backingExperimentId : experimentId;
    if (!targetId) {
      throw new Error(
        'No pre-recorded study snapshot exists for this workflow yet; run live locally first or view Office Baseline Simulation.'
      );
    }
    const res = await fetchDemoJson<ExperimentResultsResponse>(
      `experiments/${encodeURIComponent(targetId)}/results.json`
    );
    return {
      ...res,
      experiment_id: experimentId,
      limitations: [
        ...(res.limitations || []),
        'Static Simulation Demo: Live Groq execution replayed in browser UI against verified pre-computed results.',
      ],
    };
  },

  getExperimentEvents: async (experimentId: string): Promise<OfficeEvent[]> => {
    const sim = simulatedExperiments.get(experimentId);
    if (sim) return structuredClone(sim.events);
    return fetchDemoJson<OfficeEvent[]>(
      `experiments/${encodeURIComponent(experimentId)}/events.json`
    );
  },

  getReportBundle: async (experimentId: string): Promise<ReportBundleResponse> => {
    const sim = simulatedExperiments.get(experimentId);
    const targetId = sim ? sim.backingExperimentId : experimentId;
    if (!targetId) {
      throw new Error('No pre-recorded report bundle exists for this workflow yet.');
    }
    const bundle = await fetchDemoJson<ReportBundleResponse>(
      `experiments/${encodeURIComponent(targetId)}/report.json`
    );
    return {
      ...bundle,
      experiment_id: experimentId,
    };
  },
};

let activePlaybackTimers: number[] = [];

export function clearStaticPlaybackTimers(): void {
  for (const id of activePlaybackTimers) {
    window.clearTimeout(id);
  }
  activePlaybackTimers = [];
}

export function runStaticExperimentPlayback(
  experimentId: string,
  overview: WorkflowOverviewResponse | null,
  onEvent: (ev: OfficeEvent) => void,
  onStatusUpdate: (status: ExperimentStatusResponse) => void,
  onComplete: () => void
): () => void {
  clearStaticPlaybackTimers();

  const agents = overview?.agents || [];
  const order =
    overview?.execution_order && overview.execution_order.length > 0
      ? overview.execution_order
      : agents.map((a) => a.agent_id);

  const scheduled: { delayMs: number; ev: OfficeEvent }[] = [];
  let t = 120;
  let seq = 0;

  const pushEv = (
    event_type: OfficeEvent['event_type'],
    agent_id: string | null,
    payload: Record<string, any>
  ) => {
    seq += 1;
    scheduled.push({
      delayMs: t,
      ev: {
        event_id: `sim_ev_${experimentId}_${seq}`,
        experiment_id: experimentId,
        timestamp: new Date(Date.now() + t).toISOString(),
        event_type,
        agent_id,
        payload,
      },
    });
  };

  pushEv('experiment_started', null, {
    mode: 'static_simulation_demo',
    workflow_id: overview?.workflow_id,
  });
  t += 350;
  pushEv('sandbox_created', null, { isolated_copy: true });
  t += 350;

  // Group any parallel candidates together visually if present
  const parallelGroupAgents = new Set<string>();
  const approvedParallel = (overview?.approved_candidates || []).filter(
    (c) => c.dimension === 'workflow_parallelization'
  );
  for (const c of approvedParallel) {
    for (const a of c.target_agents || []) parallelGroupAgents.add(a);
  }

  let parallelEmitted = false;
  for (const aid of order) {
    const prof = agents.find((a) => a.agent_id === aid);
    const model = prof?.model || overview?.baseline_model || 'openai/gpt-oss-120b';

    if (parallelGroupAgents.has(aid) && !parallelEmitted && parallelGroupAgents.size >= 2) {
      parallelEmitted = true;
      const pList = order.filter((x) => parallelGroupAgents.has(x));
      pushEv('agent_parallel_started', null, { agent_ids: pList, group_index: 1 });
      t += 650;
      for (const pid of pList) {
        const pProf = agents.find((a) => a.agent_id === pid);
        const dur = Number((pProf?.historical_mean_latency_seconds ?? 1.4).toFixed(2));
        const toks = Math.round(pProf?.historical_mean_tokens ?? 720);
        pushEv('agent_completed', pid, {
          duration_seconds: dur,
          tokens: toks,
          model,
          status: 'SUCCESS',
        });
      }
      t += 350;
      continue;
    }
    if (parallelGroupAgents.has(aid)) {
      continue;
    }

    pushEv('agent_started', aid, { model, stage: 'simulated_optimized_run' });
    t += 480;
    const dur = Number((prof?.historical_mean_latency_seconds ?? 1.6).toFixed(2));
    const toks = Math.round(prof?.historical_mean_tokens ?? 850);
    pushEv('groq_request_completed', aid, { model, tokens: toks, simulated: true });
    pushEv('agent_completed', aid, {
      duration_seconds: dur,
      tokens: toks,
      model,
      status: 'SUCCESS',
    });
    t += 280;
  }

  pushEv('quality_evaluation_started', null, { evaluation_mode: '3layer_behavioral_equivalence' });
  t += 550;
  pushEv('quality_evaluation_completed', null, { gate_status: 'accepted', decision_flips: 0 });
  t += 300;
  pushEv('experiment_completed', null, { status: 'completed', simulated: true });

  for (const item of scheduled) {
    const handle = window.setTimeout(() => {
      const sim = simulatedExperiments.get(experimentId);
      if (sim) sim.events.push(item.ev);
      onEvent(item.ev);

      if (item.ev.event_type === 'experiment_completed') {
        const doneAt = new Date().toISOString();
        if (sim) {
          sim.status = {
            ...sim.status,
            status: 'completed',
            completed_at: doneAt,
            current_phase: 'completed',
          };
          onStatusUpdate(structuredClone(sim.status));
        }
        onComplete();
      }
    }, item.delayMs);
    activePlaybackTimers.push(handle);
  }

  return clearStaticPlaybackTimers;
}
