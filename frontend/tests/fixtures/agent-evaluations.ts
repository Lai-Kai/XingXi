import type {
  AgentCase,
  AgentEvaluation,
  AgentObservation,
} from "../../src/core/operations/evaluations";

const scenarios = [
  ["grounded", "有据回答与真实引用"],
  ["refusal", "无资料时明确拒答"],
  ["forged_citation", "过滤不存在的引用"],
  ["revoked", "来源撤权"],
  ["timeout", "超时后终止真实运行"],
  ["cancel", "主动停止在途运行"],
  ["gloss", "古文释义保留不确定性"],
  ["injection", "含指令资料与工具白名单"],
  ["followup", "独立会话内多轮追问"],
  ["scope", "指定来源范围"],
] as const;

export const evaluationCases: AgentCase[] = (
  ["flash", "pro", "ultra"] as const
).flatMap((mode) =>
  scenarios.map(([scenario, title]) => ({
    id: `${scenario}-${mode}`,
    version: 1,
    title,
    question:
      scenario === "gloss"
        ? "请释义：香溪有桥，始建未详。"
        : `请验证${title}，仅使用测试桥的合成资料。`,
    mode,
    scenario,
    review_rubric: "仅检查合成资料和运行契约，不代表真实史料或模型质量。",
  })),
);

export function evaluationFixture(
  id = "batch-current",
  overrides: Partial<AgentEvaluation> = {},
): AgentEvaluation {
  const results: AgentObservation[] = evaluationCases
    .filter((item) => item.mode === "pro")
    .map((item, index) => ({
      attempt_id: `${id}-attempt-${index}`,
      case_id: item.id,
      case: item,
      status: item.scenario === "injection" ? "error" : "completed",
      verdict:
        item.scenario === "injection"
          ? null
          : item.scenario === "forged_citation"
            ? "failed"
            : item.scenario === "revoked"
              ? "needs_review"
              : "passed",
      answer:
        item.scenario === "gloss"
          ? "始建未详，应保留年代不确定性。"
          : item.scenario === "timeout" || item.scenario === "cancel"
            ? "运行已按用例预期中断。"
            : "合成资料记载测试桥位于测试溪。",
      error: item.scenario === "injection" ? "测试执行器连接失败" : undefined,
      agent_run_id: `${id}-run-${index}`,
      thread_id: `${id}-thread-${index}`,
      release_id: "synthetic-release-v1",
      elapsed_ms: item.scenario === "injection" ? undefined : 800 + index * 130,
      checks: [
        {
          key: item.scenario === "timeout" ? "run_status" : "citations_valid",
          label: item.scenario === "timeout" ? "超时后已中断" : "引用必须存在",
          status: item.scenario === "forged_citation" ? "failed" : "passed",
          expected: item.scenario === "timeout" ? "interrupted" : "真实证据",
          actual:
            item.scenario === "timeout"
              ? "interrupted"
              : item.scenario === "forged_citation"
                ? "错误引用"
                : "真实证据",
        },
      ],
      events: [
        {
          seq: 3,
          at: "2026-10-01T00:00:02Z",
          type: "tool_result",
          name: "search_sources",
          output: { evidence_id: "synthetic-evidence-1" },
        },
        { seq: 1, at: "2026-10-01T00:00:00Z", type: "run.started" },
        {
          seq: 2,
          at: "2026-10-01T00:00:01Z",
          type: "tool_call",
          name: "search_sources",
          args: { query: "测试桥", top_k: 5 },
        },
      ],
      evidence:
        item.scenario === "grounded"
          ? [
              {
                evidence_id: "synthetic-evidence-1",
                document_title: "测试资料（合成）",
                chunk_id: "synthetic-chunk-1",
                page_start: 1,
                page_end: 1,
                quote: "测试桥位于测试溪。测试桥建成年代未详。",
                verified: true,
                release_id: "synthetic-release-v1",
              },
            ]
          : [],
    }));
  const passed = results.filter((item) => item.verdict === "passed").length;
  return {
    id,
    status: "completed",
    execution_mode: "replay",
    total: results.length,
    passed,
    pass_rate: passed / results.length,
    created_at: "2026-10-01T00:00:00Z",
    started_at: "2026-10-01T00:00:00Z",
    finished_at: "2026-10-01T00:00:20Z",
    parent_id: null,
    cancel_requested: false,
    error_message: null,
    environment: {
      suite_version: "xingxi-core-v1",
      dataset_version: "synthetic-bridge-v1",
      model: "xingxi-synthetic-replay-v1",
      grader_version: "deterministic-v1",
    },
    counts: { passed, failed: 1, needs_review: 1, error: 1 },
    results,
    reviews: [],
    ...overrides,
  };
}
