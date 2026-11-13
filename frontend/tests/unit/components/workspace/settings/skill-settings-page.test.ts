import { afterEach, expect, rs, test } from "@rstest/core";
import { createElement, isValidElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { SkillSettingsPage } from "@/components/workspace/settings/skill-settings-page";
import { zhCN } from "@/core/i18n/locales/zh-CN";
import { SkillRequestError } from "@/core/skills/api";
import { useSkills } from "@/core/skills/hooks";

rs.mock("@/core/i18n/hooks", () => ({
  useI18n: () => ({ t: zhCN, locale: "zh-CN" }),
}));
rs.mock("@/core/skills/hooks", () => ({
  useSkills: rs.fn(),
  useEnableSkill: () => ({ mutate: rs.fn() }),
}));
rs.mock("next/navigation", () => ({
  useRouter: () => ({ push: rs.fn() }),
}));
rs.mock("@/core/auth/AuthProvider", () => ({
  useAuth: () => ({ user: { system_role: "admin" } }),
}));

afterEach(() => {
  rs.clearAllMocks();
});

function state(overrides: Partial<ReturnType<typeof useSkills>> = {}) {
  const refetch = rs.fn();
  rs.mocked(useSkills).mockReturnValue({
    skills: [],
    isLoading: false,
    isFetching: false,
    error: new SkillRequestError(404, "Not Found"),
    refetch,
    ...overrides,
  } as ReturnType<typeof useSkills>);
  return refetch;
}

function retryAction(node: ReactNode): (() => void) | undefined {
  if (Array.isArray(node)) {
    return node.map(retryAction).find(Boolean);
  }
  if (!isValidElement<{ onClick?: () => void; children?: ReactNode }>(node))
    return undefined;
  return node.props.onClick ?? retryAction(node.props.children);
}

test("a failed list offers a Chinese reload action that retries the request", () => {
  const refetch = state();
  const html = renderToStaticMarkup(createElement(SkillSettingsPage));
  expect(html).toContain('role="alert"');
  expect(html).toContain("暂时无法读取研究能力");
  expect(html).toContain("重新加载");
  expect(html).not.toContain("Not Found");
  const retry = retryAction(SkillSettingsPage());
  expect(retry).toBeDefined();
  retry?.();
  expect(refetch).toHaveBeenCalledTimes(1);
});

test("a pending reload disables its button to prevent duplicate requests", () => {
  state({ isFetching: true });
  const html = renderToStaticMarkup(createElement(SkillSettingsPage));
  expect(html).toMatch(/<button[^>]*disabled/);
  expect(html).toContain(zhCN.common.loading);
});

test("permission failures retain the admin message", () => {
  state({ error: new SkillRequestError(403, "Forbidden") });
  const html = renderToStaticMarkup(createElement(SkillSettingsPage));
  expect(html).toContain(zhCN.settings.skills.adminRequired);
  expect(html).not.toContain("重新加载");
});

test("unknown built-in packages keep their enabled state without leaking internal metadata", () => {
  state({
    error: null,
    skills: [
      {
        name: "local-history",
        description: "本地研究能力",
        category: "public",
        license: "MIT",
        enabled: true,
        editable: false,
      },
    ],
  });
  const html = renderToStaticMarkup(createElement(SkillSettingsPage));
  expect(html).not.toContain("local-history");
  expect(html).toContain("扩展研究能力 1");
  expect(html).toContain('aria-checked="true"');
  expect(html).not.toContain("暂时无法读取");
});
