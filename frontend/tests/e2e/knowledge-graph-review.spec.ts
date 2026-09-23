import { expect, test, type Page } from "@playwright/test";

import type {
  GraphRelation,
  HistoricalEvent,
  ReviewStatus,
} from "../../src/core/knowledge-graph/types";

import { mockLangGraphAPI } from "./utils/mock-api";

async function mockReviewAPI(page: Page, role = "admin", hasEvidence = true) {
  mockLangGraphAPI(page);
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({
      json: {
        id: "reviewer",
        email: "reviewer@test.local",
        system_role: role,
        needs_setup: false,
      },
    }),
  );
  const entities = ["a", "b"].map((id) => ({
    id,
    canonical_name: `测试人物${id}`,
    entity_type: "person",
    summary: "测试",
    review_status: "reviewed",
    evidence_ids: ["ev"],
    release_id: null,
    dynasty: null,
    extant_status: null,
  }));
  const state = {
    failNext: false,
    requests: [] as Array<{
      review_status: ReviewStatus;
      expected_status: ReviewStatus;
      review_note: string;
    }>,
    privilegedReads: 0,
    relation: {
      id: "relation",
      subject_id: "a",
      object_id: "b",
      relation_type: "related_to",
      confidence: 0.8,
      start_time: null,
      end_time: null,
      evidence_ids: hasEvidence ? ["ev"] : [],
      is_inferred: !hasEvidence,
      review_status: "pending",
      release_id: null,
    } as GraphRelation,
    event: {
      id: "event",
      title: "测试历史事件",
      event_type: "visit",
      start_time: "1900",
      end_time: null,
      time_certainty: "exact",
      place_entity_id: null,
      participant_entity_ids: ["a"],
      summary: "史料中的事件",
      evidence_ids: hasEvidence ? ["ev"] : [],
      is_inferred: !hasEvidence,
      review_status: "pending",
      release_id: null,
    } as HistoricalEvent,
  };
  await page.route("**/api/entities*", (route) =>
    route.fulfill({ json: entities }),
  );
  await page.route("**/api/knowledge-graph/query*", (route) =>
    route.fulfill({
      json: {
        query: "a",
        status: "supported",
        message: "测试关系",
        candidates: [entities[0]],
        nodes: entities,
        edges:
          state.relation.review_status === "rejected" ? [] : [state.relation],
        evidence: [],
        truncated: false,
        max_depth: 2,
        max_nodes: 200,
        release_id: "release-1",
      },
    }),
  );
  for (const kind of ["relation", "event"] as const) {
    await page.route(`**/api/knowledge-graph/${kind}s**`, async (route) => {
      const url = new URL(route.request().url());
      if (route.request().method() === "PATCH") {
        const body = route
          .request()
          .postDataJSON() as (typeof state.requests)[number];
        state.requests.push(body);
        if (role !== "admin")
          return route.fulfill({
            status: 403,
            json: { detail: "需要管理员权限" },
          });
        if (state.failNext) {
          state.failNext = false;
          return route.fulfill({
            status: 500,
            json: { detail: "审核保存失败，请重试。" },
          });
        }
        if (body.expected_status !== state[kind].review_status)
          return route.fulfill({
            status: 409,
            json: { detail: "审核状态已改变" },
          });
        if (!hasEvidence && body.review_status === "reviewed")
          return route.fulfill({
            status: 400,
            json: { detail: "无 Evidence 不能通过" },
          });
        if (
          (state[kind].review_status !== "pending" ||
            body.review_status !== "reviewed") &&
          !body.review_note.trim()
        )
          return route.fulfill({
            status: 400,
            json: { detail: "必须填写备注" },
          });
        if (kind === "relation")
          state.relation = {
            ...state.relation,
            review_status: body.review_status,
          };
        else
          state.event = { ...state.event, review_status: body.review_status };
        return route.fulfill({ json: state[kind] });
      }
      const includeRejected =
        url.searchParams.get("include_rejected") === "true";
      if (includeRejected) state.privilegedReads += 1;
      if (includeRejected && role !== "admin")
        return route.fulfill({
          status: 403,
          json: { detail: "需要管理员权限" },
        });
      return route.fulfill({
        json:
          state[kind].review_status === "rejected" && !includeRejected
            ? []
            : [state[kind]],
      });
    });
  }
  return state;
}

for (const kind of ["relation", "event"] as const) {
  test(`${kind}: repeated corrections survive every reload`, async ({
    page,
  }) => {
    const state = await mockReviewAPI(page);
    await page.goto(
      `/workspace/knowledge-graph?view=${kind === "event" ? "events" : "graph"}`,
    );
    const card = page.locator(
      kind === "event" ? "#graph-event-event" : "#graph-relation-relation",
    );
    await expect(card.getByText(/待复核/)).toBeVisible();
    const steps = [
      ["rejected", "驳回", "已驳回"],
      ["reviewed", "通过", "已通过"],
      ["pending", "恢复待复核", "待复核"],
      ["disputed", "有争议", "有争议"],
      ["reviewed", "通过", "已通过"],
    ] as const;
    for (const [status, action, label] of steps) {
      await card.getByRole("button", { name: "修改审核结果" }).click();
      const currentAction = {
        pending: "恢复待复核",
        reviewed: "通过",
        rejected: "驳回",
        disputed: "有争议",
      }[state[kind].review_status];
      await expect(
        card.getByRole("button", { name: currentAction, exact: true }),
      ).toHaveCount(0);
      await card.getByRole("button", { name: action, exact: true }).click();
      const required =
        state[kind].review_status !== "pending" || status !== "reviewed";
      if (required)
        await expect(
          card.getByRole("button", { name: "保存审核结果" }),
        ).toBeDisabled();
      await card.getByLabel(/审核备注/).fill(`根据史料改判为${label}`);
      await card.getByRole("button", { name: "保存审核结果" }).click();
      await expect(card.getByText(new RegExp(label))).toBeVisible();
      await expect(
        card.getByRole("button", { name: "修改审核结果" }),
      ).toBeVisible();
      if (kind === "relation") await expect(page).toHaveURL(/entity=a/);
      await page.reload();
      await expect(card.getByText(new RegExp(label))).toBeVisible();
      await expect(
        card.getByRole("button", { name: "修改审核结果" }),
      ).toBeVisible();
      if (status === "rejected" && kind === "relation") {
        await expect(page.locator(".react-flow__edge")).toHaveCount(0);
        await page
          .getByRole("button", { name: "全部状态", exact: true })
          .click();
        await expect(card).toHaveCount(0);
        await expect(
          page.locator('.react-flow__edge[data-id="relation"]'),
        ).toHaveCount(0);
        await page
          .getByRole("button", { name: "待复核/争议", exact: true })
          .click();
        await expect(card).toHaveCount(0);
        await page.getByRole("button", { name: "已驳回", exact: true }).click();
        await expect(card).toBeVisible();
      }
    }
    expect(state.requests.map((item) => item.review_status)).toEqual(
      steps.map(([status]) => status),
    );
    expect(state.privilegedReads).toBeGreaterThan(0);
  });

  test(`${kind}: failed correction retains status, note and retry controls`, async ({
    page,
  }) => {
    const state = await mockReviewAPI(page);
    state.failNext = true;
    await page.goto(
      `/workspace/knowledge-graph?view=${kind === "event" ? "events" : "graph"}`,
    );
    const card = page.locator(
      kind === "event" ? "#graph-event-event" : "#graph-relation-relation",
    );
    await card.getByRole("button", { name: "修改审核结果" }).click();
    await card.getByRole("button", { name: "驳回", exact: true }).click();
    await card.getByLabel(/审核备注/).fill("测试纠错依据");
    await card.getByRole("button", { name: "保存审核结果" }).click();
    await expect(card.getByRole("alert")).toHaveText("审核保存失败，请重试。");
    await expect(card.getByLabel(/审核备注/)).toHaveValue("测试纠错依据");
    expect(state[kind].review_status).toBe("pending");
    await expect(card.getByText(/待复核/)).toBeVisible();
    await page.reload();
    await expect(card.getByText(/待复核/)).toBeVisible();
    await expect(
      card.getByRole("button", { name: "修改审核结果" }),
    ).toBeVisible();
  });

  test(`${kind}: no Evidence disables approval`, async ({ page }) => {
    await mockReviewAPI(page, "admin", false);
    await page.goto(
      `/workspace/knowledge-graph?view=${kind === "event" ? "events" : "graph"}`,
    );
    const card = page.locator(
      kind === "event" ? "#graph-event-event" : "#graph-relation-relation",
    );
    await card.getByRole("button", { name: "修改审核结果" }).click();
    await expect(
      card.getByRole("button", { name: "通过", exact: true }),
    ).toBeDisabled();
    await expect(card.getByText("无资料出处，不能审核通过。")).toBeVisible();
  });
}

test("ordinary users have no review controls or rejected query", async ({
  page,
}) => {
  const state = await mockReviewAPI(page, "user");
  await page.goto("/workspace/knowledge-graph");
  await expect(page.locator("#graph-relation-relation")).toBeVisible();
  await expect(page.getByRole("button", { name: "修改审核结果" })).toHaveCount(
    0,
  );
  await expect(
    page.getByRole("button", { name: "已驳回", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "时间事件", exact: true }).click();
  await expect(page.locator("#graph-event-event")).toBeVisible();
  await expect(page.getByRole("button", { name: "修改审核结果" })).toHaveCount(
    0,
  );
  expect(state.privilegedReads).toBe(0);
  expect(state.requests).toHaveLength(0);
});
