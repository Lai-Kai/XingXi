import type { Message } from "@langchain/langgraph-sdk";
import { describe, expect, it } from "@rstest/core";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { ResearchTurnHeading } from "@/components/workspace/citations/research-turn-heading";

const render = (messages: Message[], loading = false) =>
  renderToStaticMarkup(
    createElement(ResearchTurnHeading, { messages, loading }),
  );
describe("research provenance headings", () => {
  it("counts distinct actual citations without synthesizing a confidence score", () => {
    const html = render([
      {
        type: "ai",
        content:
          "[citation:方志](evidence://one) [citation:方志](evidence://one) [citation:馆藏](https://example.test/book)",
      },
    ]);
    expect(html).toContain("2 项引文");
    expect(html).not.toMatch(/96%|置信度：高|已核验/);
  });
  it("does not expose hidden control messages or user supplied references as research provenance", () => {
    const html = render([
      { type: "human", content: "[citation:输入](evidence://user-input)" },
      {
        type: "ai",
        content: "[citation:控制](evidence://secret)",
        additional_kwargs: { hide_from_ui: true },
      },
      { type: "ai", content: "尚待核对史料。" },
    ]);
    expect(html).toContain("尚未附可核验引文");
    expect(html).not.toContain("secret");
  });
  it("does not present an unfinished streaming turn as a verified conclusion", () => {
    expect(
      render(
        [{ type: "ai", content: "[citation:方志](evidence://one)" }],
        true,
      ),
    ).toContain("正在研究，出处随回答更新");
  });
});
