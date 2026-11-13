import { expect, rs, test } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { AgentEvaluationDetail } from "@/components/workspace/agent-evaluation-detail";
import type { AgentEvaluation } from "@/core/operations/evaluations";

rs.mock("@/components/ui/sheet", () => ({
  Sheet: ({ children }: { children: ReactNode }) => children,
  SheetContent: "div",
  SheetHeader: "header",
  SheetTitle: "h2",
  SheetDescription: "p",
}));

test("test details retain answers and source locators without exposing implementation metadata", () => {
  const batch: AgentEvaluation = {
    id: "private-batch-id",
    status: "completed",
    execution_mode: "replay",
    total: 1,
    passed: 1,
    pass_rate: 1,
    created_at: "2026-10-29T00:00:00Z",
    started_at: null,
    finished_at: null,
    parent_id: null,
    cancel_requested: false,
    error_message: null,
    environment: { worker: "private-worker" },
    counts: {},
    reviews: [],
    results: [
      {
        case_id: "private-case-id",
        attempt_id: "private-attempt-id",
        status: "completed",
        verdict: "passed",
        thread_id: "private-thread-id",
        agent_run_id: "private-run-id",
        release_id: "private-release-id",
        elapsed_ms: 100,
        case: {
          id: "private-case-id",
          title: "出处核对",
          question: "这座桥建于何时？",
          mode: "pro",
          scenario: "grounded",
          version: 1,
          review_rubric: "private-rubric",
        },
        answer: "据地方志记载，建于清代。[出处](evidence://private-answer-id)",
        events: [
          {
            seq: 1,
            at: "2026-10-29T00:00:00Z",
            type: "tool_result",
            name: "private-tool",
            args: { debug: "private-args" },
            output: { id: "private-output" },
          },
        ],
        checks: [
          {
            key: "private-check",
            label: "出处核对",
            status: "passed",
            expected: { id: "private-expected" },
            actual: { id: "private-actual" },
          },
        ],
        evidence: [
          {
            evidence_id: "private-evidence-id",
            chunk_id: "private-chunk-id",
            release_id: "private-release-id",
            document_title: "地方志",
            page_start: 5,
            page_end: 6,
            quote: "桥建于清代。",
            verified: true,
          },
        ],
      },
    ],
  };
  const client = new QueryClient();
  try {
    const html = renderToStaticMarkup(
      createElement(
        QueryClientProvider,
        { client },
        createElement(AgentEvaluationDetail, {
          batch,
          observation: batch.results[0],
          canReview: false,
          onClose: rs.fn(),
          onUpdated: () => Promise.resolve(),
        }),
      ),
    );
    expect(html).toContain("据地方志记载，建于清代。");
    expect(html).toContain("地方志");
    expect(html).toContain("5–6");
    expect(html).toContain("资料查阅完成");
    expect(html).toContain("不衡量实际回答质量");
    expect(html).not.toContain("private-");
    expect(html).not.toContain("调用参数");
  } finally {
    client.clear();
  }
});
