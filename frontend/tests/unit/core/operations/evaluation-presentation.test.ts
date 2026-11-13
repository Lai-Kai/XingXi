import { describe, expect, it } from "@rstest/core";

import {
  correctionText,
  evaluationEventLabel,
  evaluationMethodDescription,
  evaluationModeLabel,
  evaluationAnswerText,
  evaluationCheckLabel,
  operationStepLabel,
} from "@/core/operations/evaluation-presentation";
import { manualFailureLabel } from "@/core/operations/manual-evaluations";

describe("business presentation of evaluation and operations records", () => {
  it("uses familiar labels and never displays unknown implementation identifiers", () => {
    expect(evaluationModeLabel("pro")).toBe("标准");
    expect(evaluationEventLabel("tool_result")).toBe("资料查阅完成");
    expect(operationStepLabel("index")).toBe("准备检索");
    for (const label of [
      evaluationModeLabel,
      evaluationEventLabel,
      evaluationMethodDescription,
      evaluationCheckLabel,
      operationStepLabel,
      manualFailureLabel,
    ]) {
      expect(label("private-engine-v3 /api/debug")).not.toContain(
        "private-engine",
      );
      expect(label("private-engine-v3 /api/debug")).not.toContain("/api/");
    }
  });

  it("retains citation labels without showing internal locators", () => {
    expect(
      evaluationAnswerText(
        "据[地方志](evidence://private-id)记载；evidence://other-id",
      ),
    ).toBe("据地方志记载；相关出处");
    expect(evaluationCheckLabel("real_run")).toBe("测试记录完整");
  });

  it("shows the authored correction content without exposing stored metadata", () => {
    expect(correctionText({ text: "改为清代", internal_id: "secret-id" })).toBe(
      "改为清代",
    );
    expect(
      correctionText({ internal_id: "secret-id", sha256: "secret-hash" }),
    ).toBe("已保留修订内容");
  });
});
