import { type IncomingMessage, type ServerResponse } from "node:http";

import {
  afterEach,
  beforeEach,
  describe,
  expect,
  rs,
  test,
} from "@rstest/core";
import { blockCrossSiteDEV } from "next/dist/server/lib/router-utils/block-cross-site-dev";

rs.mock("nextra", () => ({
  default: () => (config: unknown) => config,
}));
rs.mock("../../../src/env.js", () => ({}));

async function blocksDevRequest(origin: string) {
  rs.resetModules();
  const { default: config } = await import("../../../next.config.js");
  const request = {
    url: "/_next/webpack-hmr",
    headers: { origin },
  } as IncomingMessage;
  const response = { statusCode: 200, end: rs.fn() };
  return blockCrossSiteDEV(
    request,
    response as unknown as ServerResponse,
    config.allowedDevOrigins,
    "127.0.0.1",
  );
}

describe("development origins behind a Tunnel", () => {
  let savedOrigins: string | undefined;

  beforeEach(() => {
    savedOrigins = process.env.DEER_FLOW_DEV_ORIGINS;
    delete process.env.DEER_FLOW_DEV_ORIGINS;
  });

  afterEach(() => {
    if (savedOrigins === undefined) {
      delete process.env.DEER_FLOW_DEV_ORIGINS;
    } else {
      process.env.DEER_FLOW_DEV_ORIGINS = savedOrigins;
    }
  });

  test("allows the configured public hostname to connect the development client", async () => {
    process.env.DEER_FLOW_DEV_ORIGINS =
      " research.example.com , , other.example.com ";

    expect(await blocksDevRequest("https://research.example.com")).toBe(false);
    expect(await blocksDevRequest("https://other.example.com")).toBe(false);
  });

  test("keeps unconfigured public hostnames blocked", async () => {
    process.env.DEER_FLOW_DEV_ORIGINS = "research.example.com";

    expect(await blocksDevRequest("https://unrelated.example.com")).toBe(true);
  });

  test("retains local access without a public origin configuration", async () => {
    expect(await blocksDevRequest("http://localhost:12027")).toBe(false);
    expect(await blocksDevRequest("http://127.0.0.1:12026")).toBe(false);
    expect(await blocksDevRequest("https://research.example.com")).toBe(true);
  });
});
