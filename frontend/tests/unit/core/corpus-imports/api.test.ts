import { beforeEach, expect, test, rs } from "@rstest/core";

rs.mock("@/core/api/fetcher", () => ({
  fetch: rs.fn(),
}));

rs.mock("@/core/config", () => ({
  getBackendBaseURL: () => "/backend",
}));

import { fetch as fetcher } from "@/core/api/fetcher";
import {
  listCorpusImportBatches,
  listCorpusImportItems,
  listCorpusQualityIssues,
} from "@/core/corpus-imports/api";

const mockedFetch = rs.mocked(fetcher);

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  mockedFetch.mockReset();
});

test("loads corpus import batches, items, and paged quality issues", async () => {
  mockedFetch
    .mockResolvedValueOnce(jsonResponse([{ id: "batch-1" }]))
    .mockResolvedValueOnce(jsonResponse([{ id: "item-1" }]))
    .mockResolvedValueOnce(jsonResponse([{ id: "issue-1" }]));

  await expect(listCorpusImportBatches()).resolves.toEqual([{ id: "batch-1" }]);
  await expect(listCorpusImportItems("batch/1")).resolves.toEqual([
    { id: "item-1" },
  ]);
  await expect(listCorpusQualityIssues("item/1", 50, 100)).resolves.toEqual([
    { id: "issue-1" },
  ]);

  expect(mockedFetch).toHaveBeenNthCalledWith(1, "/backend/api/corpus-imports");
  expect(mockedFetch).toHaveBeenNthCalledWith(
    2,
    "/backend/api/corpus-imports/batch%2F1/items",
  );
  expect(mockedFetch).toHaveBeenNthCalledWith(
    3,
    "/backend/api/corpus-imports/items/item%2F1/quality-issues?limit=50&offset=100",
  );
});
