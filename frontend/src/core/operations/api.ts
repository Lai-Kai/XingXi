import { throwGatewayApiError } from "@/core/api/errors";
import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

import type {
  AssetVersion,
  CorrectionRecord,
  EvaluationCase,
  EvaluationObservation,
  EvaluationRun,
  OperationTask,
  OperationsDashboard,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${getBackendBaseURL()}${path}`, {
    credentials: "include",
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    await throwGatewayApiError(response, `请求失败 (${response.status})`);
  }
  return response.json();
}

export const loadOperationsDashboard = (days = 30) =>
  request<OperationsDashboard>(`/api/operations/dashboard?days=${days}`);
export const listEvaluationCases = () =>
  request<EvaluationCase[]>("/api/operations/evaluations/cases");
export const listEvaluationRuns = () =>
  request<EvaluationRun[]>("/api/operations/evaluations/runs");
export const listCorrections = () =>
  request<CorrectionRecord[]>("/api/operations/corrections");
export const listAssetVersions = () =>
  request<AssetVersion[]>("/api/operations/asset-versions");
export const listOperationTasks = (
  status:
    | "all"
    | "pending"
    | "running"
    | "awaiting_review"
    | "completed"
    | "failed"
    | "cancelled" = "all",
) => request<OperationTask[]>(`/api/operations/tasks?status_filter=${status}`);

export const retryOperationTask = (taskId: string) =>
  request<OperationTask>(
    `/api/operations/tasks/${encodeURIComponent(taskId)}/retry`,
    { method: "POST", body: "{}" },
  );

export function createEvaluationCase(input: {
  name: string;
  question: string;
  expected_status: "answered" | "refused";
  min_citations: number;
  required_terms: string[];
}) {
  return request<EvaluationCase>("/api/operations/evaluations/cases", {
    method: "POST",
    body: JSON.stringify({ ...input, active: true }),
  });
}

export function createEvaluationRun(
  observations: EvaluationObservation[],
  releaseId?: string,
) {
  return request<EvaluationRun>("/api/operations/evaluations/runs", {
    method: "POST",
    body: JSON.stringify({ release_id: releaseId ?? null, observations }),
  });
}

export function createCorrection(input: {
  target_type: CorrectionRecord["target_type"];
  target_id: string;
  release_id?: string;
  summary: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
}) {
  return request<CorrectionRecord>("/api/operations/corrections", {
    method: "POST",
    body: JSON.stringify({ ...input, release_id: input.release_id ?? null }),
  });
}

export const reconcileAssetVersions = () =>
  request<AssetVersion[]>("/api/operations/asset-versions/reconcile", {
    method: "POST",
    body: "{}",
  });

export function recordOperationEvent(input: {
  event_type:
    | "answer_completed"
    | "citation_open"
    | "search_miss"
    | "map_point_click"
    | "entity_view";
  event_key?: string;
  thread_id?: string;
  run_id?: string;
  entity_id?: string;
  entity_name?: string;
  release_id?: string;
  metadata?: Record<string, unknown>;
  citation_count?: number;
  refused?: boolean;
}) {
  void fetch(`${getBackendBaseURL()}/api/operations/events`, {
    method: "POST",
    credentials: "include",
    keepalive: true,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  }).catch(() => undefined);
}
