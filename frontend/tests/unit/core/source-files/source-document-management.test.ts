import { afterEach, expect, rs, test } from "@rstest/core";

import {
  pageSourceDocumentLibrary,
  pageSourceDocuments,
  updateSourceDocument,
} from "@/core/source-files/api";

afterEach(() => {
  rs.unstubAllGlobals();
});

function requestUrl(input: RequestInfo | URL) {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

test("requests a bounded filtered source page", async () => {
  const fetchFn = rs.fn(
    async (_input: RequestInfo | URL) =>
      new Response(
        JSON.stringify({ items: [], total: 0, limit: 10, offset: 20 }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
  );
  rs.stubGlobal("fetch", fetchFn);

  await pageSourceDocuments({
    query: "木渎",
    status: "registered",
    page: 3,
    pageSize: 10,
  });

  const url = new URL(
    requestUrl(fetchFn.mock.calls[0]![0]),
    "http://localhost",
  );
  expect(Object.fromEntries(url.searchParams)).toEqual({
    limit: "10",
    offset: "20",
    query: "木渎",
    status_filter: "registered",
  });
});

test("passes an abort signal to source page requests", async () => {
  const fetchFn = rs.fn(
    async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(
        JSON.stringify({ items: [], total: 0, limit: 10, offset: 0 }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
  );
  rs.stubGlobal("fetch", fetchFn);
  const controller = new AbortController();

  await pageSourceDocuments({ signal: controller.signal });

  expect(fetchFn.mock.calls[0]![1]?.signal).toBe(controller.signal);
});

test("requests the aggregated library endpoint", async () => {
  const fetchFn = rs.fn(
    async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(
        JSON.stringify({ items: [], total: 0, limit: 10, offset: 0 }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
  );
  rs.stubGlobal("fetch", fetchFn);

  await pageSourceDocumentLibrary({ query: "木渎", page: 2, pageSize: 10 });

  const url = new URL(
    requestUrl(fetchFn.mock.calls[0]![0]),
    "http://localhost",
  );
  expect(url.pathname).toBe("/api/source-documents/library/page");
  expect(Object.fromEntries(url.searchParams)).toEqual({
    limit: "10",
    offset: "10",
    query: "木渎",
  });
});

test("updates source metadata without replacing its file", async () => {
  const fetchFn = rs.fn(
    async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(JSON.stringify({ id: "source-1", title: "新标题" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
  );
  rs.stubGlobal("fetch", fetchFn);

  await updateSourceDocument("source-1", {
    title: "新标题",
    edition: "修订版",
  });

  expect(requestUrl(fetchFn.mock.calls[0]![0])).toContain(
    "/api/source-documents/source-1",
  );
  expect(fetchFn.mock.calls[0]![1]?.method).toBe("PATCH");
  expect(JSON.parse(fetchFn.mock.calls[0]![1]?.body as string)).toEqual({
    title: "新标题",
    edition: "修订版",
  });
});
