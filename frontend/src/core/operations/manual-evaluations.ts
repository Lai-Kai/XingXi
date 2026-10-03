import type { EvaluationCase, EvaluationObservation } from "./types";

export function canSubmitManualEvaluation(
  cases: EvaluationCase[],
  observations: Record<string, EvaluationObservation>,
) {
  const active = cases.filter((item) => item.active);
  return (
    active.length > 0 &&
    active.every((item) => {
      const observation = observations[item.id];
      if (!observation) return false;
      return (
        Boolean(observation.answer.trim()) &&
        Number.isInteger(observation.citation_count) &&
        observation.citation_count >= 0
      );
    })
  );
}

export function manualFailureLabel(reason: string) {
  if (reason === "empty answer") return "没有填写本次回答";
  if (reason === "missing observation") return "没有录入本次观测";
  if (reason.startsWith("missing required terms: "))
    return `回答缺少必含词：${reason.slice(24)}`;
  const citations = /^expected at least (\d+) citations$/.exec(reason);
  if (citations) return `有效引用不足，需要至少 ${citations[1]} 条`;
  const status =
    /^expected status (answered|refused), got (answered|refused)$/.exec(reason);
  if (status)
    return `期望${status[1] === "answered" ? "回答" : "拒答"}，本次标记为${status[2] === "answered" ? "回答" : "拒答"}`;
  return reason;
}
