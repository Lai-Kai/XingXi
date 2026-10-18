import { afterEach, expect, rs, test } from "@rstest/core";

rs.mock("nextra", () => ({ default: () => (config: unknown) => config }));
rs.mock("../../../src/env.js", () => ({}));

const savedBackend = process.env.NEXT_PUBLIC_BACKEND_BASE_URL;
afterEach(() => {
  if (savedBackend === undefined)
    delete process.env.NEXT_PUBLIC_BACKEND_BASE_URL;
  else process.env.NEXT_PUBLIC_BACKEND_BASE_URL = savedBackend;
});

test("streaming upload handlers precede the generic Gateway fallback", async () => {
  delete process.env.NEXT_PUBLIC_BACKEND_BASE_URL;
  const { default: config } = await import("../../../next.config.js");
  if (!config.rewrites) throw new Error("Gateway rewrites must be configured");
  const rules = await config.rewrites();
  if (Array.isArray(rules))
    throw new Error("Uploads require an explicit Gateway fallback");
  expect(rules.beforeFiles).toEqual([]);
  expect(
    rules.afterFiles?.some(
      (rule: { source: string }) => rule.source === "/api/:path*",
    ),
  ).toBe(false);
  expect(rules.fallback).toEqual([
    expect.objectContaining({ source: "/api/:path*" }),
  ]);
});
