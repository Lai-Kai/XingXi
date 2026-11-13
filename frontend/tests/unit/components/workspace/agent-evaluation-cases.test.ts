import { expect, rs, test } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { AgentEvaluationCases } from "@/components/workspace/agent-evaluation-cases";
import type { AgentCaseCollection } from "@/core/operations/evaluations";

rs.mock("@/components/ui/sheet", () => ({
  Sheet: ({ children }: { children: ReactNode }) => children,
  SheetContent: "div",
  SheetHeader: "header",
  SheetTitle: "h2",
  SheetDescription: "p",
}));

const collection: AgentCaseCollection = {
  execution_mode: "replay",
  management_available: false,
  methods: [],
  cases: [
    {
      id: "server-question",
      version: 1,
      title: "真实目录中的问题",
      question: "服务端原始问题正文",
      mode: "pro",
      scenario: "grounded",
      review_rubric: "服务端原始判定规则",
      required_tool: "search_sources",
      expected_terms: ["原始必含词"],
      min_citations: 2,
      active: true,
      builtin: null,
    },
  ],
};

function render(data: AgentCaseCollection, canManage = true) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(["agent-evaluations", "cases"], data);
  try {
    return renderToStaticMarkup(
      createElement(
        QueryClientProvider,
        { client },
        createElement(AgentEvaluationCases, {
          open: true,
          onOpenChange: rs.fn(),
          canManage,
          canRun: true,
          onRun: rs.fn(),
        }),
      ),
    );
  } finally {
    client.clear();
  }
}

function buttons(html: string) {
  return [...html.matchAll(/<button\b[^>]*>([\s\S]*?)<\/button>/g)]
    .map((match) => match[1]!.replace(/<[^>]*>/g, ""))
    .join("\n");
}

test("catalog-only viewing preserves server questions and rules without offering unavailable mutations", () => {
  const html = render(collection);
  for (const value of [
    "服务端原始问题正文",
    "原始必含词",
    "至少 2 条有效引用",
    "需要查阅资料",
    "查看测试方法与判定规则",
    "重试读取",
  ]) {
    expect(html).toContain(value);
  }
  for (const value of ["新增问题", "删除问题", "恢复问题", "运行这题"]) {
    expect(buttons(html)).not.toContain(value);
  }
  expect(html).not.toContain("显示已删除问题");
  expect(html).not.toContain("自定义");
  expect(html).not.toContain("内置");
  expect(html).not.toContain("search_sources");
  expect(html).not.toContain("server-question");
  expect(html).not.toContain("服务端原始判定规则");
  expect(html).toContain("不衡量实际回答质量");
  expect(html).toContain("标准");
});

test("current services retain administrator controls while governance readers remain read-only", () => {
  const current = { ...collection, management_available: true };
  const admin = render(current);
  for (const value of ["新增问题", "删除问题", "运行这题", "显示已删除问题"]) {
    expect(admin).toContain(value);
  }
  const reader = render(current, false);
  expect(reader).toContain("服务端原始问题正文");
  expect(buttons(reader)).not.toContain("新增问题");
  expect(buttons(reader)).not.toContain("运行这题");
});
