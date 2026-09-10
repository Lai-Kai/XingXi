import { describe, expect, it } from "@rstest/core";

import {
  getBusinessStatusPresentation,
  type BusinessStatus,
} from "@/core/presentation/business-status";

describe("getBusinessStatusPresentation", () => {
  it.each<[BusinessStatus, string]>([
    ["pending", "等待处理"],
    ["running", "正在处理"],
    ["awaiting_review", "等待复核"],
    ["completed", "已完成"],
    ["failed", "处理失败"],
    ["supported", "证据充分"],
    ["conflicting", "证据冲突"],
    ["archived", "已归档"],
    ["demo", "演示数据"],
  ])("maps %s to user-facing Chinese", (status, label) => {
    expect(getBusinessStatusPresentation(status).label).toBe(label);
  });

  it("uses a warning tone for content that must not look authoritative", () => {
    expect(getBusinessStatusPresentation("demo").tone).toBe("warning");
    expect(getBusinessStatusPresentation("insufficient").tone).toBe("warning");
  });

  it("does not present failure and conflict as success", () => {
    expect(getBusinessStatusPresentation("failed").tone).toBe("danger");
    expect(getBusinessStatusPresentation("conflicting").tone).toBe("danger");
  });
});
