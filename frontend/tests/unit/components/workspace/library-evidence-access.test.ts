import { afterEach, expect, rs, test } from "@rstest/core";
import { useSearchParams } from "next/navigation";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import LibraryPage from "@/app/workspace/library/page";

rs.mock("next/navigation", () => ({
  useRouter: () => ({ replace: rs.fn() }),
  useSearchParams: rs.fn(),
}));
rs.mock("@/core/auth/AuthProvider", () => ({
  useAuth: () => ({ user: { system_role: "user", capabilities: [] } }),
}));
rs.mock("@/components/ui/sidebar", () => ({
  SidebarTrigger: "button",
}));

afterEach(() => {
  rs.clearAllMocks();
});

test("readers can open source details while library management remains restricted", () => {
  rs.mocked(useSearchParams).mockReturnValue(
    new URLSearchParams("evidence_id=private-evidence-id") as ReturnType<
      typeof useSearchParams
    >,
  );
  const html = renderToStaticMarkup(createElement(LibraryPage));
  expect(html).toContain('aria-label="资料出处详情"');
  expect(html).toContain("正在加载资料出处详情");
  expect(html).toContain("仅管理员可管理文献");
  expect(html).not.toContain(">上传文献<");
  expect(html).not.toContain(">发布并启用<");
  expect(html.replace(/<[^>]*>/g, "")).not.toContain("private-evidence-id");
});

test("a reader without a selected citation sees the management permission screen alone", () => {
  rs.mocked(useSearchParams).mockReturnValue(
    new URLSearchParams() as ReturnType<typeof useSearchParams>,
  );
  const html = renderToStaticMarkup(createElement(LibraryPage));
  expect(html).toContain("仅管理员可管理文献");
  expect(html).not.toContain('aria-label="资料出处详情"');
});
