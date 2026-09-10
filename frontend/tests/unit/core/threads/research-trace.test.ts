import { describe, expect, it } from "@rstest/core";

import {
  describeResearchToolCall,
  isResearchTool,
} from "@/core/threads/research-trace";

describe("research trace", () => {
  it("maps Xingxi tools to user-facing research phases", () => {
    expect(
      describeResearchToolCall("search_sources", { query: "木渎街巷" }),
    ).toEqual({
      detail: "木渎街巷",
      phase: "sources",
    });
    expect(
      describeResearchToolCall("query_knowledge_graph", {
        entity_name: "严家花园",
      }),
    ).toEqual({
      detail: "严家花园",
      phase: "graph",
    });
    expect(describeResearchToolCall("compare_sources", {})).toEqual({
      phase: "comparison",
    });
  });

  it("recognizes only evidence-oriented Xingxi tools", () => {
    expect(isResearchTool("query_timeline")).toBe(true);
    expect(isResearchTool("view_image")).toBe(true);
    expect(isResearchTool("bash")).toBe(false);
  });

  it("does not expose raw or overly long arguments", () => {
    expect(
      describeResearchToolCall("search_sources", {
        query: "木".repeat(100),
        api_key: "secret",
      })?.detail,
    ).toBe(`${"木".repeat(57)}...`);
  });
});
