import { expect, test } from "@rstest/core";
import { createElement, Fragment } from "react";
import { renderToString } from "react-dom/server";

import {
  SourceProcessingStatus,
  SourceTextReviewStatus,
} from "@/components/workspace/source-library-status";
import { type IngestionJob } from "@/core/source-files/api";

test("reviewed text remains reviewed while an independent indexing attempt has failed", () => {
  const job = {
    status: "failed",
    error_message: "sqlite3.OperationalError: too many SQL variables",
  } as IngestionJob;
  const html = renderToString(
    createElement(
      Fragment,
      null,
      createElement(SourceTextReviewStatus, { status: "reviewed" }),
      createElement(SourceProcessingStatus, {
        job,
        showFailedAsSuccess: false,
      }),
    ),
  );
  expect(html).toContain("已复核");
  expect(html).toContain("处理失败");
  expect(html).toContain("索引构建失败，请重试处理");
  expect(html).not.toContain("sqlite3");
});

test("temporary success presentation hides the failure message without changing job or text-review data", () => {
  const job = Object.freeze({
    status: "failed",
    error_message: "sqlite3.OperationalError: too many SQL variables",
  }) as IngestionJob;
  const html = renderToString(
    createElement(
      Fragment,
      null,
      createElement(SourceTextReviewStatus, { status: "pending" }),
      createElement(SourceProcessingStatus, {
        job,
        showFailedAsSuccess: true,
      }),
    ),
  );
  expect(html).toContain("处理成功");
  expect(html).toContain("等待复核");
  expect(html).not.toContain("处理失败");
  expect(html).not.toContain("重试处理");
  expect(html).not.toContain("sqlite3");
  expect(job.status).toBe("failed");
  expect(job.error_message).toContain("too many SQL variables");
});

test("missing reviewable text and a missing job do not imply review or processing success", () => {
  expect(
    renderToString(createElement(SourceTextReviewStatus, { status: null })),
  ).toContain("未就绪");
  expect(renderToString(createElement(SourceProcessingStatus))).toContain(
    "未启动",
  );
  expect(
    renderToString(
      createElement(SourceTextReviewStatus, { status: "pending" }),
    ),
  ).toContain("等待复核");
});
