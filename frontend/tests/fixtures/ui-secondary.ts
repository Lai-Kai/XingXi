import type { Page } from "@playwright/test";

import type { GlossLabelInput } from "../../src/core/glossary/types";
import { mockLangGraphAPI } from "../e2e/utils/mock-api";

export const secondaryProject = {
  id: "closeout-project",
  name: "木渎水系文献研究（软件测试）",
  archived: false,
  document_count: 0,
  created_at: "2026-10-15T03:00:00Z",
};

export async function mockSecondary(page: Page) {
  mockLangGraphAPI(page);
  await page.route("**/api/source-documents/page?**", (route) =>
    route.fulfill({ json: { items: [], total: 0, limit: 100, offset: 0 } }),
  );
  const state = {
    glossFailure: false,
    nameFailure: false,
    projectFailure: false,
    glossRequests: [] as GlossLabelInput[],
    nameRequests: [] as Record<string, unknown>[],
    projects: [secondaryProject],
  };
  await page.route("**/api/research-projects", async (route) => {
    if (state.projectFailure)
      return route.fulfill({
        status: 503,
        json: { detail: "测试：项目暂不可用" },
      });
    if (route.request().method() === "POST") {
      const created = {
        ...secondaryProject,
        id: "new-project",
        name: route.request().postDataJSON().name,
      };
      state.projects.push(created);
      return route.fulfill({ json: created });
    }
    return route.fulfill({ json: state.projects });
  });
  await page.route("**/api/research-projects/*", async (route) => {
    const request = route.request();
    if (request.method() === "PATCH") {
      const patch = request.postDataJSON();
      state.projects = state.projects.map((project) =>
        project.id === "closeout-project" ? { ...project, ...patch } : project,
      );
    }
    return route.fulfill({ json: state.projects[0] });
  });
  for (const suffix of ["documents", "records"])
    await page.route(`**/api/research-projects/*/${suffix}`, (route) =>
      route.fulfill({ json: [] }),
    );
  await page.route("**/api/knowledge-graph/gloss", async (route) => {
    const input = route.request().postDataJSON() as GlossLabelInput;
    state.glossRequests.push(input);
    if (state.glossFailure)
      return route.fulfill({
        status: 503,
        json: { detail: "测试：释读服务暂不可用" },
      });
    return route.fulfill({
      json: {
        ...input,
        status: "reading_aid",
        status_label: "辅助释读，需核对原文",
        gloss: {
          original: input.text,
          sentences: [
            {
              original: input.text,
              modern: "软件测试释读；未详之处保留待考。",
              keywords: [{ term: "水名", meaning: "具体所指未详" }],
              uncertain_terms: ["水名所指"],
            },
          ],
          notes: ["本释读仅作阅读辅助，不替代原文考据。"],
        },
      },
    });
  });
  await page.route(
    "**/api/knowledge-graph/aliases/resolve-authority",
    async (route) => {
      const input = route.request().postDataJSON();
      state.nameRequests.push(input);
      if (state.nameFailure)
        return route.fulfill({
          status: 503,
          json: { detail: "测试：异名服务暂不可用" },
        });
      return route.fulfill({
        json: {
          decision: "needs_review",
          preferred_name: null,
          confidence: "low",
          research_context: input.research_context ?? null,
          retained_names: input.variants.map((x: { name: string }) => x.name),
          explanation: "软件测试：出处势均力敌，保留异名并交人工复核。",
          requires_human_review: true,
          candidates: input.variants.map(
            (x: { name: string; evidence_ids: string[] }) => ({
              name: x.name,
              score: 50,
              eligible: true,
              best_source_level: "A",
              reviewed_document_count: 1,
              missing_evidence_ids: [],
              reasons: ["两份独立文献的依据相当"],
              evidence: x.evidence_ids.map((id) => ({
                evidence_id: id,
                document_id: "software-source",
                document_title: "方志软件测试样本",
                edition: "测试本",
                source_level: "A",
                review_status: "reviewed",
                page_start: 12,
                page_end: 13,
                contributes_to_score: true,
              })),
            }),
          ),
        },
      });
    },
  );
  return state;
}

export async function mockLogin(page: Page, needsSetup = false) {
  await page.route("**/api/v1/auth/setup-status", (route) =>
    route.fulfill({ json: { needs_setup: needsSetup } }),
  );
  await page.route("**/api/v1/auth/providers", (route) =>
    route.fulfill({
      json: {
        providers: [
          { id: "software-sso", display_name: "测试机构 SSO", type: "oidc" },
        ],
      },
    }),
  );
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({ status: 401, json: { detail: "unauthenticated" } }),
  );
  await page.route("**/api/v1/auth/login/local", (route) =>
    route.fulfill({
      status: 401,
      json: {
        detail: {
          code: "invalid_credentials",
          message: "测试：邮箱或密码不正确",
        },
      },
    }),
  );
}
