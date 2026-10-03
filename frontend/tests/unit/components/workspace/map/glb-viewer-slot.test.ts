import { describe, expect, it } from "@rstest/core";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  type GlbAssetDescriptor,
  GlbViewerSlot,
} from "@/components/workspace/map/glb-viewer-slot";

describe("GlbViewerSlot", () => {
  it("does not reserve layout space when no asset is available", () => {
    const html = renderToStaticMarkup(
      createElement(GlbViewerSlot, { asset: null }),
    );

    expect(html).toBe("");
  });

  it("preserves asset provenance without claiming a render has completed", () => {
    const asset: GlbAssetDescriptor = {
      id: "model-yan-garden",
      title: "严家花园三维资产",
      src: "/models/yan-garden.glb",
      license: "CC BY 4.0",
      evidenceIds: ["evidence-yan-garden"],
      provenance: "surveyed",
    };

    const html = renderToStaticMarkup(createElement(GlbViewerSlot, { asset }));

    expect(html).toContain('data-glb-id="model-yan-garden"');
    expect(html).toContain('data-glb-state="available"');
    expect(html).toContain("CC BY 4.0");
  });

  it("keeps missing model addresses as a recoverable detail state", () => {
    const html = renderToStaticMarkup(
      createElement(GlbViewerSlot, {
        asset: {
          id: "missing",
          title: "缺少模型地址",
          license: "待确认",
          evidenceIds: [],
        },
      }),
    );
    expect(html).toContain('data-glb-state="missing-source"');
    expect(html).toContain("景点资料仍可查看");
  });
});
