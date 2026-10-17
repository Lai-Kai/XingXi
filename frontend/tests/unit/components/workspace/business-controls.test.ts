import { mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

import { afterAll, describe, expect, it } from "@rstest/core";
import { BookOpen } from "lucide-react";
import { createElement as h, createRef } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  BusinessButton,
  BusinessInput,
  BusinessPanel,
  BusinessReviewBadge,
  BusinessSkeleton,
  BusinessTextarea,
  EvidenceCapsule,
} from "@/components/workspace/business-controls";
import {
  BusinessEmptyState,
  BusinessErrorState,
  BusinessInlineError,
  BusinessLoadingState,
  BusinessPageHeader,
  BusinessStatusBadge,
} from "@/components/workspace/business-page";
import { BusinessTable } from "@/components/workspace/business-surfaces";

describe("business foundation interaction contracts", () => {
  it("defaults to a non-submit button and retains an explicit submit type", () => {
    expect(renderToStaticMarkup(h(BusinessButton, null, "操作"))).toContain(
      'type="button"',
    );
    expect(
      renderToStaticMarkup(h(BusinessButton, { type: "submit" }, "提交")),
    ).toContain('type="submit"');
  });
  it("prevents repeat submission while busy and keeps an accessible name", () => {
    const html = renderToStaticMarkup(
      h(BusinessButton, { busy: true }, "保存审核"),
    );
    expect(html).toContain('disabled=""');
    expect(html).toContain('aria-busy="true"');
    expect(html).toContain("保存审核");
    expect(html).toContain('aria-hidden="true"');
  });
  it("preserves a caller's disabled state without showing a false busy state", () => {
    const html = renderToStaticMarkup(
      h(BusinessButton, { disabled: true }, "保存"),
    );
    expect(html).toContain('disabled=""');
    expect(html).not.toContain('aria-busy="true"');
  });
  it("forwards field identity, refs, native validation and callbacks", () => {
    const ref = createRef<HTMLInputElement>();
    const onChange = () => undefined;
    const element = BusinessInput({
      id: "source-name",
      name: "source",
      ref,
      onChange,
      required: true,
      "aria-invalid": true,
      "aria-describedby": "source-error",
    });
    expect(element.props.ref).toBe(ref);
    expect(element.props.onChange).toBe(onChange);
    const html = renderToStaticMarkup(element);
    expect(html).toContain('required=""');
    expect(html).toContain('aria-describedby="source-error"');
    expect(html).toContain('aria-invalid="true"');
    expect(html).toContain('name="source"');
  });
  it("does not replace composer keyboard or IME handling", () => {
    const onKeyDown = () => undefined;
    const element = BusinessTextarea({
      onKeyDown,
      defaultValue: "原有研究问题",
    });
    expect(element.props.onKeyDown).toBe(onKeyDown);
    expect(renderToStaticMarkup(element)).toContain("原有研究问题");
  });
  it("uses the existing evidence deep-link contract including escaped IDs", () => {
    const html = renderToStaticMarkup(
      h(EvidenceCapsule, {
        evidenceId: "ev/卷一?片段",
        title: "木渎镇志",
        locator: "卷一 · 12页",
      }),
    );
    expect(html).toContain("/workspace/library?evidence_id=ev%2F");
    expect(html).toContain("%3F");
    expect(html).toContain('aria-label="木渎镇志 · 卷一 · 12页"');
    expect(html).not.toContain("evidence://");
  });
  for (const [status, label] of [
    ["pending", "待复核"],
    ["reviewed", "已通过"],
    ["disputed", "有争议"],
    ["rejected", "已驳回"],
  ] as const) {
    it(`keeps ${status} review semantics visible without relying on color`, () => {
      const html = renderToStaticMarkup(h(BusinessReviewBadge, { status }));
      expect(html).toContain('role="status"');
      expect(html).toContain(`aria-label="${label}"`);
      expect(html).toContain(label);
      expect(html).toContain('aria-hidden="true"');
    });
  }
  it("preserves generic business status labels and accessible loading/error feedback", () => {
    expect(
      renderToStaticMarkup(
        h(BusinessStatusBadge, { status: "awaiting_review" }),
      ),
    ).toContain("等待复核");
    const loading = renderToStaticMarkup(
      h(BusinessLoadingState, { label: "文献加载中" }),
    );
    expect(loading).toContain('aria-busy="true"');
    expect(loading).toContain('aria-label="文献加载中"');
    const error = renderToStaticMarkup(
      h(BusinessErrorState, {
        description: "网络断开",
        onRetry: () => undefined,
      }),
    );
    expect(error).toContain('role="alert"');
    expect(error).toContain("重新加载");
    expect(
      renderToStaticMarkup(
        h(BusinessErrorState, { description: "没有重试权限" }),
      ),
    ).not.toContain("重新加载");
  });
  it("keeps decorative skeletons out of the accessibility tree", () => {
    expect(renderToStaticMarkup(h(BusinessSkeleton))).toContain(
      'aria-hidden="true"',
    );
  });
  it("keeps native table semantics and names the keyboard-scrollable region", () => {
    const html = renderToStaticMarkup(
      h(
        BusinessTable,
        { caption: "审核队列" },
        h("tbody", null, h("tr", null, h("td", null, "卷一"))),
      ),
    );
    expect(html).toContain('role="region" aria-label="审核队列" tabindex="0"');
    expect(html).toContain('<caption class="sr-only">审核队列</caption>');
    expect(html).toContain("<tbody><tr><td>卷一</td></tr></tbody>");
  });
});

// Opt-in, offline review fixture. It is never registered as a product route.
afterAll(() => {
  const preview = process.env.FOUNDATION_PREVIEW_PATH;
  if (!preview) return;
  const markup = renderToStaticMarkup(
    h(
      "main",
      { className: "mx-auto max-w-5xl space-y-6 p-4 sm:p-8" },
      h(
        "h1",
        { className: "font-serif text-2xl font-semibold" },
        "星羲 · 基础组件核对（测试夹具／非生产数据）",
      ),
      h(
        BusinessPanel,
        { "aria-label": "表单和操作" },
        h(
          "form",
          { id: "foundation-form", className: "space-y-4" },
          h("label", { htmlFor: "sample-input" }, "研究题目"),
          h(BusinessInput, {
            id: "sample-input",
            name: "topic",
            required: true,
            placeholder: "输入研究题目",
          }),
          h("label", { htmlFor: "sample-textarea" }, "研究问题"),
          h(BusinessTextarea, {
            id: "sample-textarea",
            defaultValue: "中文长文、证据与不确定性均应清楚可读。",
          }),
          h(
            "div",
            { className: "flex flex-wrap gap-3" },
            h(BusinessButton, { type: "submit" }, "开始考据"),
            h(BusinessButton, { variant: "outline" }, "次要操作"),
            h(BusinessButton, { busy: true }, "正在保存"),
            h(BusinessButton, { disabled: true }, "禁止操作"),
          ),
          h("output", { id: "submission-result" }),
        ),
      ),
      h(
        BusinessPanel,
        { "aria-label": "审核与证据" },
        h(
          "div",
          { className: "flex flex-wrap items-center gap-3" },
          ...(["pending", "reviewed", "disputed", "rejected"] as const).map(
            (status) => h(BusinessReviewBadge, { key: status, status }),
          ),
          h(EvidenceCapsule, {
            evidenceId: "fixture-evidence",
            title: "方志测试资料",
            locator: "卷二 · 18页",
          }),
        ),
      ),
      h(BusinessInlineError, { message: "示例错误：请核实输入。" }),
      h(
        BusinessTable,
        { caption: "测试文献列表" },
        h(
          "thead",
          null,
          h(
            "tr",
            null,
            h("th", { scope: "col" }, "卷册"),
            h("th", { scope: "col" }, "状态"),
          ),
        ),
        h(
          "tbody",
          null,
          h(
            "tr",
            { "data-state": "selected" },
            h("td", null, "演示卷一"),
            h("td", null, "待复核"),
          ),
        ),
      ),
      h(BusinessLoadingState, { label: "正在加载测试资料" }),
      h(BusinessEmptyState, {
        icon: BookOpen,
        title: "暂无资料",
        description: "尚无可核验资料，请调整检索条件。",
      }),
      h(
        "section",
        {
          id: "legacy-header",
          style: {
            backgroundColor: "#f7fafb",
            color: "#20282b",
            padding: "1rem",
          },
        },
        h(BusinessPageHeader, {
          title: "旧页面兼容核对",
          description: "页头沿用调用页面的文字与背景。",
          icon: BookOpen,
          actions: h(
            "button",
            { type: "button", style: { backgroundColor: "white" } },
            "旧版操作",
          ),
        }),
      ),
    ),
  );
  mkdirSync(dirname(preview), { recursive: true });
  writeFileSync(preview, markup, "utf8");
});
