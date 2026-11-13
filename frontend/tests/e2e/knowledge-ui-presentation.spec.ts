import { expect, test } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";
import { refreshMockUser } from "./utils/refresh-mock-user";

test("name authority selects real source text without asking readers for internal identifiers", async ({
  page,
}) => {
  mockLangGraphAPI(page);
  let failSearch = false;
  await page.route("**/api/knowledge-search/structured", async (route) => {
    if (failSearch) {
      await route.fulfill({
        status: 500,
        json: { detail: "SQL worker failed at /srv/private/collection.db" },
      });
      return;
    }
    const { query } = route.request().postDataJSON() as { query: string };
    await route.fulfill({
      json: {
        hits: [
          {
            chunk_id: "private-chunk-key",
            citation: {
              evidence_id:
                query === "香溪" ? "private-source-one" : "private-source-two",
              document_id: "private-document-key",
              source_file_id: null,
              document_title: "测试木渎志",
              edition: "清代本",
              page_start: query === "香溪" ? 1 : 2,
              page_end: query === "香溪" ? 1 : 2,
              quote: `${query}，流经镇中。`,
              source_level: "A",
              review_status: "reviewed",
            },
          },
        ],
        next_cursor: null,
      },
    });
  });
  let submitted: unknown;
  await page.route(
    "**/api/knowledge-graph/aliases/resolve-authority",
    async (route) => {
      submitted = route.request().postDataJSON();
      await route.fulfill({
        json: {
          decision: "needs_review",
          preferred_name: null,
          explanation: "两种名称的文献依据需要继续核对。",
          retained_names: ["香溪", "胥溪"],
          candidates: [],
          requires_human_review: true,
        },
      });
    },
  );
  await page.goto("/workspace/name-authority");
  for (const [index, name] of ["香溪", "胥溪"].entries()) {
    const variant = page.locator("fieldset").nth(index);
    await variant
      .getByRole("textbox", { name: `候选 ${index + 1} 名称` })
      .fill(name);
    await variant.getByRole("button", { name: "查找出处" }).click();
    await variant.getByRole("checkbox").check();
    await expect(
      variant.getByRole("list", { name: `候选 ${index + 1} 已选出处` }),
    ).toContainText("测试木渎志");
  }
  await expect(page.locator("main")).not.toContainText("private-");
  await expect(page.getByPlaceholder("资料出处编号")).toHaveCount(0);
  await page.getByRole("button", { name: "依据资料出处辨析" }).click();
  await expect(page.getByText("需要人工复核", { exact: true })).toBeVisible();
  expect(submitted).toEqual({
    variants: [
      { name: "香溪", evidence_ids: ["private-source-one"] },
      { name: "胥溪", evidence_ids: ["private-source-two"] },
    ],
  });

  failSearch = true;
  await page
    .locator("fieldset")
    .first()
    .getByRole("button", { name: "查找出处" })
    .click();
  await expect(page.getByRole("alert")).toContainText("暂时无法查找资料出处");
  await expect(page.locator("main")).not.toContainText("/srv/private");
  await expect(
    page.locator("fieldset").first().getByRole("list"),
  ).toContainText("测试木渎志");
  await expect(page.getByText("需要人工复核", { exact: true })).toBeVisible();
});

for (const authorized of [true, false]) {
  test(`readers ${authorized ? "can open" : "cannot read restricted"} source details without library management access`, async ({
    page,
  }) => {
    mockLangGraphAPI(page);
    await page.route("**/api/v1/auth/me", (route) =>
      route.fulfill({
        json: {
          id: "public-reader",
          email: "reader@test.local",
          system_role: "user",
          business_role: "public",
          capabilities: [],
          needs_setup: false,
        },
      }),
    );
    await page.route(
      "**/api/knowledge-search/evidence/private-source-one",
      (route) =>
        authorized
          ? route.fulfill({
              json: {
                evidence_id: "private-source-one",
                document_id: "private-document-key",
                source_file_id: null,
                document_title: "测试木渎志",
                edition: "清代本",
                page_start: 1,
                page_end: 1,
                quote: "香溪，流经镇中。",
                source_level: "A",
                review_status: "reviewed",
              },
            })
          : route.fulfill({
              status: 403,
              json: { detail: "private-source-one forbidden at /srv/private" },
            }),
    );
    await page.goto("/workspace/library?evidence_id=private-source-one");
    await refreshMockUser(page);
    await expect(
      page.getByText("仅管理员可管理文献", { exact: true }),
    ).toBeVisible();
    const detail = page.getByRole("complementary", { name: "资料出处详情" });
    await expect(detail).toBeVisible();
    if (authorized) {
      await expect(detail).toContainText("香溪，流经镇中。");
      await expect(detail).toContainText("已通过");
    } else {
      await expect(detail).toContainText("确认访问权限");
      await expect(detail).not.toContainText("香溪，流经镇中。");
    }
    await expect(detail).not.toContainText("private-");
    await expect(
      page.getByRole("button", { name: "上传文献", exact: true }),
    ).toHaveCount(0);
    await detail.getByRole("button", { name: "关闭资料出处详情" }).click();
    await expect(page).toHaveURL(/\/workspace\/library$/);
    await expect(detail).toHaveCount(0);
  });
}
