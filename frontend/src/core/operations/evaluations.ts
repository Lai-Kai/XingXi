import { throwGatewayApiError } from "@/core/api/errors";
import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

export type AgentCase = {
  id: string;
  version: number;
  title: string;
  question: string;
  mode: "flash" | "pro" | "ultra";
  scenario: string;
  review_rubric: string;
};

export type AgentCheck = {
  key: string;
  label: string;
  status: "passed" | "failed" | "needs_review";
  expected: unknown;
  actual: unknown;
};

export type AgentObservation = {
  attempt_id: string;
  case_id: string;
  case: AgentCase;
  status:
    | "queued"
    | "running"
    | "completed"
    | "error"
    | "cancelled"
    | "skipped";
  verdict: "passed" | "failed" | "needs_review" | null;
  answer?: string;
  error?: string;
  agent_run_id?: string;
  thread_id?: string;
  release_id?: string;
  elapsed_ms?: number;
  checks: AgentCheck[];
  events: Array<{
    seq: number;
    at: string;
    type: string;
    name?: string;
    args?: unknown;
    output?: unknown;
  }>;
  evidence: Array<{
    evidence_id: string;
    document_title: string;
    chunk_id: string;
    page_start: number;
    page_end: number;
    quote: string;
    verified: boolean;
    release_id: string;
  }>;
};

export type AgentEvaluation = {
  id: string;
  status: "queued" | "running" | "completed" | "error" | "cancelled";
  execution_mode: "replay";
  total: number;
  passed: number;
  pass_rate: number | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  parent_id: string | null;
  cancel_requested: boolean;
  error_message: string | null;
  environment: Record<string, unknown>;
  counts: Record<string, number>;
  results: AgentObservation[];
  reviews: Array<{
    id: string;
    case_id: string;
    actor_id: string;
    decision: string;
    note: string;
    created_at: string;
  }>;
};

export type AgentCatalog = {
  version: string;
  available: boolean;
  execution_mode: "replay";
  cases: AgentCase[];
};

export type AgentEvaluationSummary = Omit<
  AgentEvaluation,
  "environment" | "counts" | "results" | "reviews"
>;

const root = "/api/operations/evaluations";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${getBackendBaseURL()}${root}${path}`, {
    credentials: "include",
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok)
    await throwGatewayApiError(response, "无法读取 Agent 评测记录");
  return response.json();
}

export const loadAgentCatalog = (signal?: AbortSignal) =>
  request<AgentCatalog>("/catalog", { signal });
export const listAgentEvaluations = (offset = 0, signal?: AbortSignal) =>
  request<AgentEvaluationSummary[]>(`/executions?limit=20&offset=${offset}`, {
    signal,
  });
export const getAgentEvaluation = (id: string, signal?: AbortSignal) =>
  request<AgentEvaluation>(`/executions/${encodeURIComponent(id)}`, { signal });
export const startAgentEvaluation = (smoke: boolean, requestKey: string) =>
  request<AgentEvaluation>("/executions", {
    method: "POST",
    body: JSON.stringify({ smoke, request_key: requestKey }),
  });
export const cancelAgentEvaluation = (id: string) =>
  request<AgentEvaluation>(`/executions/${encodeURIComponent(id)}/cancel`, {
    method: "POST",
    body: "{}",
  });
export const rerunAgentEvaluation = (id: string, requestKey: string) =>
  request<AgentEvaluation>(`/executions/${encodeURIComponent(id)}/rerun`, {
    method: "POST",
    body: JSON.stringify({ request_key: requestKey, failed_only: true }),
  });
export const reviewAgentEvaluation = (
  id: string,
  input: {
    case_id: string;
    decision: "confirmed" | "disagreed" | "needs_review";
    note: string;
  },
) =>
  request<AgentEvaluation>(`/executions/${encodeURIComponent(id)}/reviews`, {
    method: "POST",
    body: JSON.stringify(input),
  });

export async function downloadAgentReport(
  id: string,
  format: "markdown" | "json" | "csv" | "html",
) {
  const response = await fetch(
    `${getBackendBaseURL()}${root}/executions/${encodeURIComponent(id)}/export?format=${format}`,
    { credentials: "include" },
  );
  if (!response.ok) await throwGatewayApiError(response, "报告导出失败");
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `evaluation-${id}.${format === "markdown" ? "md" : format}`;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function evaluationLabel(value: string | null | undefined): string {
  return (
    (
      {
        queued: "排队中",
        running: "执行中",
        completed: "已完成",
        error: "执行错误",
        cancelled: "已取消",
        skipped: "未执行",
        passed: "通过",
        failed: "失败",
        needs_review: "待复核",
        confirmed: "确认原判定",
        disagreed: "与原判定有分歧",
      } as Record<string, string>
    )[value ?? ""] ?? "未判定"
  );
}

export function evaluationVerdict(
  batch: Pick<AgentEvaluation, "status" | "total" | "passed">,
): string {
  if (batch.status !== "completed") return evaluationLabel(batch.status);
  return batch.total > 0 && batch.passed === batch.total
    ? "全部通过"
    : "未全部通过";
}
