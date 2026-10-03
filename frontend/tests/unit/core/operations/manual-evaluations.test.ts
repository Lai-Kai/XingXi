import { describe, expect, it } from "@rstest/core";

import {
  canSubmitManualEvaluation,
  manualFailureLabel,
} from "@/core/operations/manual-evaluations";
import type {
  EvaluationCase,
  EvaluationObservation,
} from "@/core/operations/types";

const active: EvaluationCase = {
  id: "active",
  name: "无证据拒答",
  question: "请检索资料。",
  active: true,
  expected_status: "refused",
  min_citations: 0,
  required_terms: [],
  created_by: "admin",
  created_at: "2026-10-01T00:00:00Z",
};
const observation: EvaluationObservation = {
  case_id: active.id,
  actual_status: "refused",
  citation_count: 0,
  answer: "当前检索范围内暂无明确记载。",
};

describe("manual evaluation submission", () => {
  it("requires actual text rather than the preselected expected status", () => {
    expect(canSubmitManualEvaluation([active], {})).toBe(false);
    expect(
      canSubmitManualEvaluation([active], {
        active: { ...observation, answer: "  \n " },
      }),
    ).toBe(false);
  });
  it("accepts zero-citation refusals and ignores archived cases", () => {
    expect(
      canSubmitManualEvaluation(
        [active, { ...active, id: "archived", active: false }],
        { active: observation },
      ),
    ).toBe(true);
    expect(canSubmitManualEvaluation([{ ...active, active: false }], {})).toBe(
      false,
    );
  });
  it("blocks invalid citation counts", () => {
    for (const citation_count of [-1, 0.5, NaN]) {
      expect(
        canSubmitManualEvaluation([active], {
          active: { ...observation, citation_count },
        }),
      ).toBe(false);
    }
  });
  it("allows genuine mismatches to be graded as failures", () => {
    expect(
      canSubmitManualEvaluation([active], {
        active: { ...observation, actual_status: "answered" },
      }),
    ).toBe(true);
  });
  it("explains saved failure reasons in Chinese", () => {
    expect(manualFailureLabel("empty answer")).toBe("没有填写本次回答");
    expect(manualFailureLabel("missing required terms: 灵岩山")).toBe(
      "回答缺少必含词：灵岩山",
    );
    expect(manualFailureLabel("expected status refused, got answered")).toBe(
      "期望拒答，本次标记为回答",
    );
    expect(manualFailureLabel("expected at least 1 citations")).toBe(
      "有效引用不足，需要至少 1 条",
    );
  });
});
