import { afterEach, expect, rs, test } from "@rstest/core";
import { usePathname } from "next/navigation";
import { createElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { HomeEvidencePreview } from "@/components/workspace/home/evidence-preview";
import { HomeResearchComposer } from "@/components/workspace/home/research-composer";
import { WorkspaceAgentEntry } from "@/components/workspace/workspace-agent-entry";
import { buildLocalFallbackDailyResearchFeed } from "@/core/research-feed/fallback";

rs.mock("next/navigation", () => ({
  useRouter: () => ({ push: rs.fn() }),
  usePathname: rs.fn(),
}));
rs.mock("@/components/ui/sidebar", () => ({
  useSidebar: () => ({ setOpenMobile: rs.fn() }),
  SidebarMenu: "ul",
  SidebarMenuItem: "li",
  SidebarMenuButton: ({ children }: { children: ReactNode }) =>
    createElement("div", {}, children),
}));

afterEach(() => {
  rs.clearAllMocks();
});

test("the initial composer has an accessible blank question and no implied source selection", () => {
  const html = renderToStaticMarkup(createElement(HomeResearchComposer));
  expect(html).toContain('for="home-query"');
  expect(html).toContain('id="home-query"');
  expect(html).toMatch(/<button[^>]*aria-label="开始研究"[^>]*disabled/);
  expect(html.match(/aria-pressed="false"/g)).toHaveLength(3);
  expect(html).toContain("方志与图册");
  expect(html).toContain("人物与地方记忆");
  expect(html).toContain("河道与地名沿革");
});

test("the document preview renders supplied text and never invents a quote or confidence", () => {
  const source = buildLocalFallbackDailyResearchFeed().items[0]!.sources![0]!;
  const html = renderToStaticMarkup(
    createElement(HomeEvidencePreview, {
      source: {
        ...source,
        quote: "原始摘录内容",
        page_start: 12,
        page_end: 13,
      },
      onOpen: rs.fn(),
    }),
  );
  expect(html).toContain(source.document_title);
  expect(html).toContain("原始摘录内容");
  expect(html).toContain("12–13页");
  expect(html).not.toContain("部分内容暂时使用本地资料");
  expect(html).not.toContain("置信度");
  const withoutQuote = renderToStaticMarkup(
    createElement(HomeEvidencePreview, {
      source: { ...source, quote: null, page_start: null, page_end: null },
      onOpen: rs.fn(),
    }),
  );
  expect(withoutQuote).toContain("页码待核");
  expect(withoutQuote).not.toContain("原始摘录内容");
});

test("the highlighted entry opens the agent module directly", () => {
  rs.mocked(usePathname).mockReturnValue("/workspace");
  const html = renderToStaticMarkup(createElement(WorkspaceAgentEntry));
  expect(html).toContain('href="/workspace/agent"');
  expect(html).toContain("星羲智能体");
  expect(html).not.toContain("新建检索项目");
  expect(html).not.toContain('aria-current="page"');
});

test("the agent entry identifies the current module", () => {
  rs.mocked(usePathname).mockReturnValue("/workspace/agent");
  const html = renderToStaticMarkup(createElement(WorkspaceAgentEntry));
  expect(html).toContain('aria-current="page"');
});
