import { describe, expect, it } from "@rstest/core";

import { throwGatewayApiError } from "@/core/api/errors";

describe("GatewayApiError", () => {
  it("preserves the machine-readable error contract", async () => {
    const response = new Response(
      JSON.stringify({
        detail: "legacy message",
        error: {
          code: "release_preparation_failed",
          message: "Release preparation failed",
          trace_id: "trace-1",
          retryable: true,
        },
      }),
      { status: 503 },
    );

    await expect(
      throwGatewayApiError(response, "fallback"),
    ).rejects.toMatchObject({
      name: "GatewayApiError",
      code: "release_preparation_failed",
      traceId: "trace-1",
      retryable: true,
      status: 503,
      message: "Release preparation failed",
    });
  });
});
