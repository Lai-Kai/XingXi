import { describe, expect, it } from "@rstest/core";

import { formatMetricRate } from "@/core/operations/types";

describe("formatMetricRate", () => {
  it("distinguishes missing data from a measured zero", () => {
    expect(formatMetricRate(null)).toBe("暂无数据");
    expect(formatMetricRate(0)).toBe("0.0%");
    expect(formatMetricRate(0.875)).toBe("87.5%");
  });
});
