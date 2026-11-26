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
import { isStaticDemoMode, staticWorkplaceApi } from './staticMode';

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) {
        detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      // keep default HTTP status message
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

const liveWorkplaceApi = {
  getHealth: () => requestJson<{ status: string; service: string }>('/api/health'),
  listWorkflows: () => requestJson<WorkflowSummary[]>('/api/workflows'),
  getWorkflowOverview: (workflowId: string) =>
    requestJson<WorkflowOverviewResponse>(`/api/workflows/${encodeURIComponent(workflowId)}/overview`),
  getWorkflowBaseline: (workflowId: string, maxTraces = 10) =>
    requestJson<BaselineResponse>(
      `/api/workflows/${encodeURIComponent(workflowId)}/baseline?max_traces=${maxTraces}`
    ),
  getWorkflowReview: (workflowId: string) =>
    requestJson<WorkflowReviewResponse>(`/api/workflows/${encodeURIComponent(workflowId)}/review`),
  approveWorkflowScope: (workflowId: string, payload: ApproveScopeRequest) =>
    requestJson<Record<string, any>>(`/api/workflows/${encodeURIComponent(workflowId)}/approve`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getWorkflowAgents: (workflowId: string) =>
    requestJson<AgentProfile[]>(`/api/agents/${encodeURIComponent(workflowId)}`),
  listExperiments: (workflowId?: string) =>
    requestJson<ExperimentStatusResponse[]>(
      workflowId ? `/api/experiments?workflow_id=${encodeURIComponent(workflowId)}` : '/api/experiments'
    ),
  startExperiment: (payload: ExperimentStartRequest) =>
    requestJson<ExperimentStatusResponse>('/api/experiments/start', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getExperimentStatus: (experimentId: string) =>
    requestJson<ExperimentStatusResponse>(`/api/experiments/${encodeURIComponent(experimentId)}`),
  getExperimentResults: (experimentId: string) =>
    requestJson<ExperimentResultsResponse>(
      `/api/experiments/${encodeURIComponent(experimentId)}/results`
    ),
  getExperimentEvents: (experimentId: string) =>
    requestJson<OfficeEvent[]>(`/api/experiments/${encodeURIComponent(experimentId)}/events`),
  getReportBundle: (experimentId: string) =>
    requestJson<ReportBundleResponse>(`/api/reports/${encodeURIComponent(experimentId)}`),
};

export const workplaceApi = {
  getHealth: () =>
    isStaticDemoMode() ? staticWorkplaceApi.getHealth() : liveWorkplaceApi.getHealth(),
  listWorkflows: () =>
    isStaticDemoMode() ? staticWorkplaceApi.listWorkflows() : liveWorkplaceApi.listWorkflows(),
  getWorkflowOverview: (workflowId: string) =>
    isStaticDemoMode()
      ? staticWorkplaceApi.getWorkflowOverview(workflowId)
      : liveWorkplaceApi.getWorkflowOverview(workflowId),
  getWorkflowBaseline: (workflowId: string, maxTraces = 10) =>
    isStaticDemoMode()
      ? staticWorkplaceApi.getWorkflowBaseline(workflowId)
      : liveWorkplaceApi.getWorkflowBaseline(workflowId, maxTraces),
  getWorkflowReview: (workflowId: string) =>
    isStaticDemoMode()
      ? staticWorkplaceApi.getWorkflowReview(workflowId)
      : liveWorkplaceApi.getWorkflowReview(workflowId),
  approveWorkflowScope: (workflowId: string, payload: ApproveScopeRequest) =>
    isStaticDemoMode()
      ? staticWorkplaceApi.approveWorkflowScope(workflowId, payload)
      : liveWorkplaceApi.approveWorkflowScope(workflowId, payload),
  getWorkflowAgents: (workflowId: string) =>
    isStaticDemoMode()
      ? staticWorkplaceApi.getWorkflowAgents(workflowId)
      : liveWorkplaceApi.getWorkflowAgents(workflowId),
  listExperiments: (workflowId?: string) =>
    isStaticDemoMode()
      ? staticWorkplaceApi.listExperiments(workflowId)
      : liveWorkplaceApi.listExperiments(workflowId),
  startExperiment: (payload: ExperimentStartRequest) =>
    isStaticDemoMode()
      ? staticWorkplaceApi.startExperiment(payload)
      : liveWorkplaceApi.startExperiment(payload),
  getExperimentStatus: (experimentId: string) =>
    isStaticDemoMode()
      ? staticWorkplaceApi.getExperimentStatus(experimentId)
      : liveWorkplaceApi.getExperimentStatus(experimentId),
  getExperimentResults: (experimentId: string) =>
    isStaticDemoMode()
      ? staticWorkplaceApi.getExperimentResults(experimentId)
      : liveWorkplaceApi.getExperimentResults(experimentId),
  getExperimentEvents: (experimentId: string) =>
    isStaticDemoMode()
      ? staticWorkplaceApi.getExperimentEvents(experimentId)
      : liveWorkplaceApi.getExperimentEvents(experimentId),
  getReportBundle: (experimentId: string) =>
    isStaticDemoMode()
      ? staticWorkplaceApi.getReportBundle(experimentId)
      : liveWorkplaceApi.getReportBundle(experimentId),
};

export function buildExperimentWebSocketUrl(experimentId: string): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${window.location.host}/ws/experiments/${encodeURIComponent(experimentId)}`;
}
