import { type NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Stream video bodies directly. Next's generic rewrite clones/truncates at 10 MiB.
async function proxy(
  request: NextRequest,
  context: { params: Promise<{ segments?: string[] }> },
) {
  const { segments = [] } = await context.params;
  const suffix = segments.join("/");
  if (
    suffix &&
    suffix !== "capabilities" &&
    !/^[a-f0-9-]{36}(?:\/cancel|\/artifact\/final\.ply)?$/.test(suffix)
  ) {
    return Response.json({ detail: "重建入口不存在" }, { status: 404 });
  }
  const origin = (
    process.env.DEER_FLOW_INTERNAL_GATEWAY_BASE_URL ?? "http://127.0.0.1:8001"
  ).replace(/\/+$/, "");
  const headers = new Headers();
  for (const name of [
    "cookie",
    "content-type",
    "content-length",
    "x-csrf-token",
    "origin",
    "referer",
    "range",
    "if-range",
  ]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  headers.set("host", request.headers.get("host") ?? request.nextUrl.host);
  if (Number(headers.get("content-length")) > 2050 * 1024 ** 2) {
    return Response.json({ detail: "素材总大小超过上传限制" }, { status: 413 });
  }
  try {
    const init: RequestInit & { duplex?: "half" } = {
      method: request.method,
      headers,
      cache: "no-store",
      signal: request.signal,
      redirect: "manual",
    };
    if (request.method === "POST") {
      init.body = request.body;
      init.duplex = "half";
    }
    const upstream = await fetch(
      `${origin}/api/reconstructions${suffix ? `/${suffix}` : ""}${request.nextUrl.search}`,
      init,
    );
    const responseHeaders = new Headers();
    for (const name of [
      "content-type",
      "content-length",
      "content-disposition",
      "content-range",
      "accept-ranges",
      "etag",
      "last-modified",
    ]) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    responseHeaders.set("cache-control", "private, no-store");
    return new Response(upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return Response.json(
      { detail: "Gateway 连接暂不可用，请重试" },
      { status: 502 },
    );
  }
}
export { proxy as GET, proxy as POST, proxy as HEAD };
