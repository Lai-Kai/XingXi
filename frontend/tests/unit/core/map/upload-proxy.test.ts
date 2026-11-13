import { ReadableStream } from "node:stream/web";

import { afterEach, expect, rs, test } from "@rstest/core";
import { type NextRequest } from "next/server";

import {
  POST as uploadModel,
  GET as readModel,
} from "@/app/api/map/model-assets/[[...segments]]/route";
import { POST as uploadReconstruction } from "@/app/api/reconstructions/[[...segments]]/route";

afterEach(() => {
  rs.restoreAllMocks();
});

test.each([
  ["/api/map/model-assets", uploadModel],
  ["/api/reconstructions", uploadReconstruction],
] as const)(
  "%s forwards a large upload as the original stream with authentication",
  async (path, handler) => {
    const body = new ReadableStream();
    const upstream = rs
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response('{"id":"saved"}', { status: 201 }));
    const request = {
      method: "POST",
      headers: new Headers({
        "content-type": "multipart/form-data; boundary=test",
        "content-length": String(12 * 1024 ** 2),
        cookie: "session=private",
        "x-csrf-token": "csrf-value",
        host: "research.example.com",
        origin: "https://research.example.com",
      }),
      body,
      signal: new AbortController().signal,
      nextUrl: new URL(`https://research.example.com${path}`),
    } as unknown as NextRequest;
    const response = await handler(request, { params: Promise.resolve({}) });
    expect(response.status).toBe(201);
    const [target, init] = upstream.mock.calls[0]!;
    expect(
      new URL(target instanceof Request ? target.url : target).pathname,
    ).toBe(path);
    expect(init?.body).toBe(body);
    expect(init?.signal).toBe(request.signal);
    const headers = init?.headers as Headers;
    expect(headers.get("cookie")).toBe("session=private");
    expect(headers.get("x-csrf-token")).toBe("csrf-value");
    expect(headers.get("host")).toBe("research.example.com");
    expect(response.headers.get("cache-control")).toBe("private, no-store");
  },
);

test("model downloads preserve partial-response bytes and Range headers", async () => {
  const bytes = new Uint8Array([1, 2, 3]);
  const upstream = rs.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(bytes, {
      status: 206,
      headers: {
        "content-range": "bytes 0-2/100",
        "accept-ranges": "bytes",
        "content-type": "model/gltf-binary",
      },
    }),
  );
  const request = {
    method: "GET",
    headers: new Headers({ range: "bytes=0-2", cookie: "session=private" }),
    signal: new AbortController().signal,
    nextUrl: new URL(
      "https://research.example.com/api/map/model-assets/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/file?download=true",
    ),
  } as unknown as NextRequest;
  const response = await readModel(request, {
    params: Promise.resolve({
      segments: ["aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "file"],
    }),
  });
  expect(response.status).toBe(206);
  expect(response.headers.get("content-range")).toBe("bytes 0-2/100");
  expect(new Uint8Array(await response.arrayBuffer())).toEqual(bytes);
  const [target, init] = upstream.mock.calls[0]!;
  expect(target instanceof Request ? target.url : target.toString()).toContain(
    "/file?download=true",
  );
  expect((init?.headers as Headers).get("range")).toBe("bytes=0-2");
});

test("unknown model paths never forward requests to the Gateway", async () => {
  const upstream = rs.spyOn(globalThis, "fetch");
  const response = await readModel({} as NextRequest, {
    params: Promise.resolve({ segments: ["arbitrary", "path"] }),
  });
  expect(response.status).toBe(404);
  expect(upstream).not.toHaveBeenCalled();
});

test("model pages preserve point, limit and cursor query parameters", async () => {
  const upstream = rs
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(Response.json({ data: [], next_cursor: null }));
  const request = {
    method: "GET",
    headers: new Headers({ cookie: "session=private" }),
    signal: new AbortController().signal,
    nextUrl: new URL(
      "https://research.example.com/api/map/model-assets/page?point_id=point-1&limit=20&cursor=next",
    ),
  } as unknown as NextRequest;
  const response = await readModel(request, {
    params: Promise.resolve({ segments: ["page"] }),
  });
  expect(response.status).toBe(200);
  expect(await response.json()).toEqual({ data: [], next_cursor: null });
  const target = upstream.mock.calls[0]![0];
  expect(target instanceof Request ? target.url : target.toString()).toContain(
    "/api/map/model-assets/page?point_id=point-1&limit=20&cursor=next",
  );
});
