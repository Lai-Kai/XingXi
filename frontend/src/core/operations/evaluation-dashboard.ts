import type {
  AgentEvaluation,
  AgentEvaluationSummary,
  AgentObservation,
} from "./evaluations";

export const scenarioLabels: Record<string, string> = {
  grounded: "有据回答",
  refusal: "无证据拒答",
  forged_citation: "错误引用",
  revoked: "来源撤权",
  timeout: "超时终止",
  cancel: "主动取消",
  gloss: "古文释义",
  injection: "含指令资料",
  followup: "多轮追问",
  scope: "指定来源",
};

function validRate(rate: number | null | undefined) {
  return rate != null && Number.isFinite(rate) && rate >= 0 && rate <= 1
    ? rate * 100
    : null;
}

export function observationPassed(item: AgentObservation) {
  return item.status === "completed" && item.verdict === "passed";
}

export function evaluationMetrics(batch: AgentEvaluation | undefined) {
  const results = batch?.results ?? [];
  const durations = results
    .map((item) => item.elapsed_ms)
    .filter(
      (value): value is number =>
        value != null && Number.isFinite(value) && value >= 0,
    );
  const observed = results.length > 0;
  return {
    passRate:
      observed && batch && batch.total > 0 ? validRate(batch.pass_rate) : null,
    errors: observed
      ? results.filter((item) => item.status === "error").length
      : null,
    needsReview: observed
      ? results.filter((item) => item.verdict === "needs_review").length
      : null,
    averageMs: durations.length
      ? durations.reduce((sum, value) => sum + value, 0) / durations.length
      : null,
    durationSamples: durations.length,
  };
}

export type ObservationFilters = {
  scenario: string;
  mode: string;
  outcome: string;
  query: string;
};

export function filterObservations(
  results: AgentObservation[],
  filters: ObservationFilters,
) {
  const query = filters.query.trim().toLocaleLowerCase();
  return results.filter(
    (item) =>
      (filters.scenario === "all" || item.case.scenario === filters.scenario) &&
      (filters.mode === "all" || item.case.mode === filters.mode) &&
      (filters.outcome === "all" ||
        (filters.outcome === "unpassed"
          ? !observationPassed(item)
          : filters.outcome === item.verdict ||
            filters.outcome === item.status)) &&
      (!query ||
        `${item.case_id} ${item.case.title} ${item.case.question} ${item.answer ?? ""}`
          .toLocaleLowerCase()
          .includes(query)),
  );
}

export function orderedEvents(events: AgentObservation["events"]) {
  return [...events].sort((a, b) => a.seq - b.seq);
}

const categories = [
  { key: "failed", label: "规则失败", color: "#e11d48" },
  { key: "error", label: "执行错误", color: "#fb7185" },
  { key: "needs_review", label: "待复核", color: "#d97706" },
  { key: "running", label: "执行中", color: "#276f79" },
  { key: "queued", label: "排队中", color: "#94a3b8" },
  { key: "cancelled", label: "已取消", color: "#64748b" },
  { key: "skipped", label: "未执行", color: "#cbd5e1" },
  { key: "missing", label: "未判定 / 缺失记录", color: "#a8a29e" },
] as const;

export function evaluationDistribution(batch: AgentEvaluation | undefined) {
  if (!batch) return [];
  const counts: Record<string, number> = {};
  for (const item of batch.results) {
    if (observationPassed(item)) continue;
    const key =
      item.status !== "completed" ? item.status : (item.verdict ?? "missing");
    const category = categories.some((entry) => entry.key === key)
      ? key
      : "missing";
    counts[category] = (counts[category] ?? 0) + 1;
  }
  counts.missing =
    (counts.missing ?? 0) + Math.max(0, batch.total - batch.results.length);
  return categories
    .map((item) => ({ ...item, value: counts[item.key] ?? 0 }))
    .filter((item) => item.value > 0);
}

export function historyPoints(batches: AgentEvaluationSummary[]) {
  return [...batches]
    .sort((a, b) => a.created_at.localeCompare(b.created_at))
    .map((batch, index) => ({
      id: batch.id,
      label: `批次 ${index + 1}`,
      createdAt: batch.created_at,
      status: batch.status,
      planned: batch.total,
      passed: batch.passed,
      rate:
        batch.status === "completed" && batch.total > 0
          ? validRate(batch.pass_rate)
          : null,
    }));
}
