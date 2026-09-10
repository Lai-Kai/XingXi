import { expect, test } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

test("an administrator can choose files before registering the first source", async ({
  page,
}) => {
  mockLangGraphAPI(page);
  let sources: unknown[] = [];
  let submittedSource: Record<string, unknown> | null = null;

  await page.route(/\/api\/source-documents$/, async (route) => {
    if (route.request().method() === "POST") {
      submittedSource = route.request().postDataJSON() as Record<
        string,
        unknown
      >;
      const source = {
        id: "source-1",
        ...submittedSource,
      };
      sources = [source];
      return route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(source),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(sources),
    });
  });
  await page.route("**/api/source-documents/upload/limits", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        max_files: 5,
        max_file_size: 10_000_000,
        max_total_size: 20_000_000,
        allowed_extensions: [".pdf"],
      }),
    }),
  );
  await page.route("**/api/research-projects", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );

  await page.goto("/workspace/library");
  await page.getByRole("button", { name: "上传文献" }).click();

  await expect(page.getByRole("button", { name: "选择文件" })).toBeEnabled();
  await page.locator('input[type="file"]').setInputFiles({
    name: "木渎资料.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.7\n"),
  });
  await expect(page.getByText("木渎资料.pdf")).toBeVisible();
  await expect(page.getByRole("button", { name: "开始上传" })).toBeDisabled();

  await page.getByRole("button", { name: "先登记资料来源" }).click();
  await page.getByLabel("来源标题").fill("震泽商会会员名录");
  await page.getByLabel("版本信息").fill("民国二十三年抄本");
  await page.getByLabel("来源机构").fill("私人授权收藏");
  await page.getByLabel("资料持有人").fill("资料授权人");
  await page.getByLabel("来源类型").selectOption("other");
  await page.getByLabel("自定义资料类型").fill("商会名录");
  await page.getByRole("button", { name: "保存来源" }).click();

  await expect(page.getByLabel("资料来源")).toContainText("震泽商会会员名录");
  await expect(page.getByRole("button", { name: "选择文件" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "开始上传" })).toBeEnabled();
  expect(submittedSource).toMatchObject({
    title: "震泽商会会员名录",
    source_type: "other",
    source_type_label: "商会名录",
  });
});
