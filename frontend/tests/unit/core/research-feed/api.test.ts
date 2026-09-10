import { afterEach, expect, test, rs } from "@rstest/core";

afterEach(() => {
  rs.unstubAllGlobals();
});

test("daily research feed loads the backend-generated date and topics", async () => {
  const requests: Array<{ url: string; init?: RequestInit }> = [];
  rs.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    requests.push({ url, init });
    return new Response(
      JSON.stringify({
        kind: "daily_grounded",
        generated_for: "2026-07-29",
        next_refresh_at: "2026-07-30T00:00:00+08:00",
        items: [
          {
            id: "daily-1",
            title: "木渎古桥名称沿革",
            summary: "核对不同文献中的桥名。",
            tag: "古迹考证",
            source_basis: "已发布历史文献",
            prompt: "考证木渎古桥名称沿革",
            origin: "evidence_backed_fallback",
            evidence_count: 4,
            knowledge_release_id: "release-1",
            popularity_users: null,
            popularity_searches: null,
          },
        ],
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  });

  const { fetchDailyResearchFeed } = await import("@/core/research-feed/api");
  const result = await fetchDailyResearchFeed();

  expect(requests[0]?.url).toBe("/api/research-feed/daily");
  expect(requests[0]?.init?.cache).toBe("no-store");
  expect(result.generated_for).toBe("2026-07-29");
  expect(result.items[0]?.title).toBe("木渎古桥名称沿革");
});

test("daily research feed does not silently reuse stale demo content", async () => {
  rs.stubGlobal(
    "fetch",
    async () =>
      new Response(JSON.stringify({ detail: "feed unavailable" }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      }),
  );

  const { fetchDailyResearchFeed } = await import("@/core/research-feed/api");

  await expect(fetchDailyResearchFeed()).rejects.toThrow("feed unavailable");
});

test("daily research history loads current expansion and previous days", async () => {
  let requestedUrl = "";
  rs.stubGlobal("fetch", async (url: string) => {
    requestedUrl = url;
    const feed = {
      kind: "daily_grounded",
      generated_for: "2026-07-30",
      next_refresh_at: "2026-07-31T00:00:00+08:00",
      items: [],
    };
    return new Response(
      JSON.stringify({
        kind: "daily_grounded_history",
        current: feed,
        previous: [
          { ...feed, generated_for: "2026-07-29" },
          { ...feed, generated_for: "2026-07-28" },
        ],
        history_days: 3,
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  });

  const { fetchDailyResearchHistory } =
    await import("@/core/research-feed/api");
  const result = await fetchDailyResearchHistory(3);

  expect(requestedUrl).toBe("/api/research-feed/history?days=3");
  expect(result.current.generated_for).toBe("2026-07-30");
  expect(result.previous).toHaveLength(2);
});
