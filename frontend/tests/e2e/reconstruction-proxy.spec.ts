import { createServer, type Server } from "node:http";

import { expect, test } from "@playwright/test";

test.describe.configure({ mode: "serial" });
test.skip(
  !process.env.RECONSTRUCTION_PROXY_TEST,
  "Run with an isolated upstream on port 3118",
);
let server: Server;
let received = { size: 0, csrf: "", cookie: "" };
test.beforeAll(async () => {
  server = createServer((request, response) => {
    if (request.method === "POST") {
      let size = 0;
      request.on("data", (chunk: Buffer) => {
        size += chunk.length;
      });
      request.on("end", () => {
        received = {
          size,
          csrf: String(request.headers["x-csrf-token"]),
          cookie: String(request.headers.cookie),
        };
        response.writeHead(202, { "content-type": "application/json" });
        response.end(JSON.stringify(received));
      });
    } else if (
      request.url?.endsWith("/artifact/final.ply") ||
      request.url?.split("?")[0]?.endsWith("/file")
    ) {
      response.writeHead(206, {
        "content-type": "application/octet-stream",
        "content-range": "bytes 0-3/8",
        "accept-ranges": "bytes",
        "content-disposition": 'attachment; filename="final.ply"',
      });
      response.end("ply\n");
    } else {
      response.writeHead(403, { "content-type": "application/json" });
      response.end(JSON.stringify({ detail: "仅管理员可使用影像重建" }));
    }
  });
  await new Promise<void>((resolve) =>
    server.listen(3118, "127.0.0.1", resolve),
  );
});
test.afterAll(async () => {
  if (server)
    await new Promise<void>((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    );
});

test("streams a 12 MiB request without the generic rewrite truncation", async ({
  request,
}) => {
  const bytes = Buffer.alloc(12 * 1024 ** 2, 65);
  const response = await request.post("/api/reconstructions", {
    data: bytes,
    headers: {
      "content-type": "application/octet-stream",
      "x-csrf-token": "csrf-fixture",
      cookie: "access_token=synthetic; csrf_token=csrf-fixture",
    },
  });
  expect(response.status()).toBe(202);
  expect(received.size).toBe(bytes.length);
  expect(received.csrf).toBe("csrf-fixture");
  expect(received.cookie).toContain("access_token=synthetic");
});
test("preserves protected download range headers and backend permission denial", async ({
  request,
}) => {
  const response = await request.get(
    "/api/reconstructions/71ca3eba-2a96-4140-a558-ea8130863cc5/artifact/final.ply",
    { headers: { range: "bytes=0-3" } },
  );
  expect(response.status()).toBe(206);
  expect(await response.body()).toEqual(Buffer.from("ply\n"));
  expect(response.headers()["content-range"]).toBe("bytes 0-3/8");
  expect(response.headers()["cache-control"]).toBe("private, no-store");
  const denied = await request.get("/api/reconstructions");
  expect(denied.status()).toBe(403);
  expect(((await denied.json()) as { detail: string }).detail).toContain(
    "仅管理员",
  );
});

test("streams imported map models beyond 10 MiB and preserves authenticated file ranges", async ({
  request,
}) => {
  const bytes = Buffer.alloc(12 * 1024 ** 2, 66);
  const response = await request.post("/api/map/model-assets", {
    data: bytes,
    headers: {
      "content-type": "application/octet-stream",
      "x-csrf-token": "model-csrf",
      cookie: "access_token=synthetic; csrf_token=model-csrf",
    },
  });
  expect(response.status()).toBe(202);
  expect(received.size).toBe(bytes.length);
  expect(received.csrf).toBe("model-csrf");
  const ranged = await request.get(
    "/api/map/model-assets/71ca3eba-2a96-4140-a558-ea8130863cc5/file?download=true",
    { headers: { range: "bytes=0-3" } },
  );
  expect(ranged.status()).toBe(206);
  expect(await ranged.body()).toEqual(Buffer.from("ply\n"));
  expect(ranged.headers()["content-range"]).toBe("bytes 0-3/8");
  expect(ranged.headers()["cache-control"]).toBe("private, no-store");
  expect((await request.get("/api/map/model-assets")).status()).toBe(403);
  expect(
    (await request.get("/api/map/model-assets/not-a-uuid/file")).status(),
  ).toBe(404);
});
