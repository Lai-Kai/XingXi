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

  it("preserves the future asset descriptor surface", () => {
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
    expect(html).toContain('data-glb-state="ready"');
    expect(html).toContain("CC BY 4.0");
  });
});
