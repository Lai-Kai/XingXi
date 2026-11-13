import { GatewayApiError, throwGatewayApiError } from "@/core/api/errors";
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
  required_tool?: string | null;
  expected_terms?: string[];
  forbidden_terms?: string[];
  min_citations?: number;
  expect_empty_evidence?: boolean;
  timeout_seconds?: number;
  expected_run_status?: string;
};

export type ManagedAgentCase = AgentCase & {
  active: boolean;
  builtin: boolean | null;
};
export type AgentCaseMethod = AgentCase & { description: string };
export type AgentCaseInput = {
  title: string;
  question: string;
  scenario: string;
  mode: AgentCase["mode"];
  expected_terms?: string[];
  forbidden_terms?: string[];
};
export type AgentCaseCollection = {
  execution_mode: "replay";
  cases: ManagedAgentCase[];
  methods: AgentCaseMethod[];
  management_available?: boolean;
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
  core_count?: number;
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

const invalidQuestions = "暂时无法读取测试问题与方法，请重试。";

function isCatalogCase(
  value: unknown,
): value is AgentCase & Partial<ManagedAgentCase> {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return (
    ["id", "title", "question", "scenario", "review_rubric"].every(
      (key) => typeof item[key] === "string",
    ) &&
    typeof item.version === "number" &&
    Number.isFinite(item.version) &&
    typeof item.mode === "string" &&
    ["flash", "pro", "ultra"].includes(item.mode) &&
    ["expected_terms", "forbidden_terms"].every(
      (key) =>
        item[key] === undefined ||
        (Array.isArray(item[key]) &&
          item[key].every((term) => typeof term === "string")),
    ) &&
    ["min_citations", "timeout_seconds"].every(
      (key) =>
        item[key] === undefined ||
        (typeof item[key] === "number" && Number.isFinite(item[key])),
    ) &&
    (item.required_tool == null || typeof item.required_tool === "string") &&
    (item.expected_run_status === undefined ||
      typeof item.expected_run_status === "string") &&
    ["active", "expect_empty_evidence"].every(
      (key) => item[key] === undefined || typeof item[key] === "boolean",
    ) &&
    (item.builtin == null || typeof item.builtin === "boolean")
  );
}

async function readCatalogQuestions(
  signal?: AbortSignal,
): Promise<AgentCaseCollection> {
  let data: unknown;
  try {
    data = await request<unknown>("/catalog", { signal });
  } catch (error) {
    if (error instanceof GatewayApiError && error.status === 404) {
      throw new Error("评测题库暂不可用，请更新并重启评测服务后重试。");
    }
    throw error;
  }
  if (
    !data ||
    typeof data !== "object" ||
    !("execution_mode" in data) ||
    data.execution_mode !== "replay" ||
    !("cases" in data) ||
    !Array.isArray(data.cases) ||
    !data.cases.every(isCatalogCase)
  )
    throw new Error(invalidQuestions);
  return {
    execution_mode: "replay",
    management_available: false,
    methods: [],
    cases: data.cases.map((item) => ({
      ...item,
      active: item.active ?? true,
      builtin: item.builtin ?? null,
    })),
  };
}

export async function loadAgentCases(signal?: AbortSignal) {
  let data: unknown;
  try {
    data = await request<unknown>("/questions", { signal });
  } catch (error) {
    // Older Gateways expose the real replay catalog without question management.
    // Never fall back to /cases: it is the unrelated manual-evaluation API.
    if (error instanceof GatewayApiError && error.status === 404) {
      return readCatalogQuestions(signal);
    }
    throw error;
  }
  // A manual evaluation list is an array. Reject incompatible responses here
  // so the Sheet can show its normal error/retry state instead of crashing.
  if (
    !data ||
    typeof data !== "object" ||
    !("cases" in data) ||
    !Array.isArray(data.cases) ||
    !("methods" in data) ||
    !Array.isArray(data.methods)
  ) {
    throw new Error(invalidQuestions);
  }
  return data as AgentCaseCollection;
}
export const createAgentCase = (input: AgentCaseInput) =>
  request<ManagedAgentCase>("/questions", {
    method: "POST",
    body: JSON.stringify(input),
  });
export const deleteAgentCase = (id: string) =>
  request<ManagedAgentCase>(`/questions/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
export const restoreAgentCase = (id: string) =>
  request<ManagedAgentCase>(`/questions/${encodeURIComponent(id)}/restore`, {
    method: "POST",
    body: "{}",
  });
export const listAgentEvaluations = (offset = 0, signal?: AbortSignal) =>
  request<AgentEvaluationSummary[]>(`/executions?limit=20&offset=${offset}`, {
    signal,
  });
export const getAgentEvaluation = (id: string, signal?: AbortSignal) =>
  request<AgentEvaluation>(`/executions/${encodeURIComponent(id)}`, { signal });
export const startAgentEvaluation = (
  smoke: boolean,
  requestKey: string,
  caseIds?: string[],
) =>
  request<AgentEvaluation>("/executions", {
    method: "POST",
    body: JSON.stringify({
      smoke,
      request_key: requestKey,
      ...(caseIds ? { case_ids: caseIds } : {}),
    }),
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
