import { expect, test } from "@rstest/core";

import type { IngestionJob } from "@/core/source-files/api";
import {
  corpusQualityMessage,
  sourcePreparationStatus,
  sourceUploadConflictMessage,
} from "@/core/source-files/presentation";

test("preparation labels explain the task and preserve failure and review states", () => {
  expect(
    sourcePreparationStatus({
      status: "running",
      current_step: "ocr",
    } as IngestionJob),
  ).toBe("识别文字中");
  expect(
    sourcePreparationStatus({
      status: "failed",
      current_step: "index",
    } as IngestionJob),
  ).toBe("准备入库失败");
  expect(
    sourcePreparationStatus({
      status: "awaiting_review",
      current_step: "review",
    } as IngestionJob),
  ).toBe("待复核");
  expect(
    sourcePreparationStatus({
      status: "cancelled",
      current_step: "chunk",
    } as IngestionJob),
  ).toBe("入库已取消");
});

test("duplicate guidance retains the distinction between identical and changed contents", () => {
  expect(sourceUploadConflictMessage("duplicate_file")).toContain(
    "引用已有文件",
  );
  expect(sourceUploadConflictMessage("same_name_different_content")).toContain(
    "内容不同",
  );
  expect(
    sourceUploadConflictMessage("same_name_different_content"),
  ).not.toContain("引用已有文件");
  expect(sourceUploadConflictMessage("worker_database_error")).toBeNull();
});

test("quality prompts retain actionable text issues without exposing arbitrary server messages", () => {
  expect(corpusQualityMessage("missing_glyph_placeholder")).toBe(
    "存在尚未辨认的缺字",
  );
  expect(corpusQualityMessage("empty_clean_page")).toContain("为空");
  expect(
    corpusQualityMessage("RuntimeError: SQL /srv/private/config.yaml"),
  ).toBe("本页文字需要核对");
});
