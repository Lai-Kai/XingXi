import { beforeEach, describe, expect, it, rs } from "@rstest/core";

rs.mock("@/core/api/fetcher", () => ({
  fetch: rs.fn(),
  readCsrfCookie: rs.fn(),
}));
rs.mock("@/core/config", () => ({ getBackendBaseURL: () => "/backend" }));

import { fetch as fetcher } from "@/core/api/fetcher";
import {
  modelsForPoint,
  modelFileUrl,
  listMapModels,
  type RegisteredMapModel,
} from "@/core/map/registered-models";

const mockedFetch = rs.mocked(fetcher);
const page = (data: RegisteredMapModel[], next_cursor: string | null) =>
  new Response(JSON.stringify({ data, next_cursor }), {
    headers: { "Content-Type": "application/json" },
  });

beforeEach(() => {
  mockedFetch.mockReset();
});

const asset: RegisteredMapModel = {
  id: "asset-1",
  point_id: "point-1",
  entity_id: "entity-1",
  title: "三维模型",
  kind: "point_cloud",
  format: "ply",
  size_bytes: 100,
  sha256: "hash",
  source: "upload",
  created_at: "2026-10-17",
  preview_url: "https://untrusted.test/model",
  download_url: "https://untrusted.test/download",
};
describe("registered map model binding", () => {
  it("binds only exact point and entity pairs", () => {
    expect(
      modelsForPoint([asset], { id: "point-1", entityId: "entity-1" }),
    ).toEqual([asset]);
    expect(
      modelsForPoint([asset], { id: "other", entityId: "entity-1" }),
    ).toEqual([]);
    expect(
      modelsForPoint([asset], { id: "point-1", entityId: "other" }),
    ).toEqual([]);
  });
  it("builds authenticated same-service URLs rather than trusting arbitrary record URLs", () => {
    expect(modelFileUrl(asset)).toContain("/api/map/model-assets/asset-1/file");
    expect(modelFileUrl(asset, true)).toContain("/file?download=true");
    expect(modelFileUrl(asset)).not.toContain("untrusted.test");
  });

  it("loads every page with exact point filtering, abort support and duplicate model protection", async () => {
    const signal = new AbortController().signal;
    const other = { ...asset, id: "asset-2" };
    mockedFetch
      .mockResolvedValueOnce(page([asset], "next+cursor"))
      .mockResolvedValueOnce(page([asset, other], null));
    expect(await listMapModels(signal, "point/1")).toEqual([asset, other]);
    expect(mockedFetch).toHaveBeenCalledTimes(2);
    const firstInput = mockedFetch.mock.calls[0]![0];
    const secondInput = mockedFetch.mock.calls[1]![0];
    const firstUrl = new URL(
      typeof firstInput === "string" ? firstInput : firstInput.url,
      "https://example.test",
    );
    const secondUrl = new URL(
      typeof secondInput === "string" ? secondInput : secondInput.url,
      "https://example.test",
    );
    expect(firstUrl.pathname).toBe("/backend/api/map/model-assets/page");
    expect(firstUrl.searchParams.get("point_id")).toBe("point/1");
    expect(secondUrl.searchParams.get("cursor")).toBe("next+cursor");
    expect(mockedFetch.mock.calls[0]![1]?.signal).toBe(signal);
    expect(mockedFetch.mock.calls[1]![1]?.signal).toBe(signal);
  });

  it("rejects repeated cursors rather than looping forever", async () => {
    mockedFetch
      .mockResolvedValueOnce(page([asset], "repeat"))
      .mockResolvedValueOnce(page([], "repeat"));
    await expect(listMapModels()).rejects.toThrow("分页");
    expect(mockedFetch).toHaveBeenCalledTimes(2);
  });

  it("stops before fetching another page after cancellation", async () => {
    const controller = new AbortController();
    mockedFetch.mockImplementationOnce(async () => {
      controller.abort();
      return page([asset], "next");
    });
    await expect(listMapModels(controller.signal)).rejects.toMatchObject({
      name: "AbortError",
    });
    expect(mockedFetch).toHaveBeenCalledTimes(1);
  });
});
