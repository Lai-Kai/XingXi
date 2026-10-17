import { describe, expect, it } from "@rstest/core";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  evidenceIdFromDetailPath,
  rehypeEvidenceLinks,
} from "@/components/workspace/citations/evidence-markdown";
import { MarkdownContent } from "@/components/workspace/messages/markdown-content";

describe("evidence links through the markdown URL policy", () => {
  it("preserves locators through the real rich text renderer", () => {
    const html = renderToStaticMarkup(
      createElement(MarkdownContent, {
        content: "[citation:方志](evidence://evidence-one)",
        isLoading: false,
      }),
    );
    expect(html).toContain('data-evidence-id="evidence-one"');
    expect(html).toContain(
      'href="/workspace/library?evidence_id=evidence-one"',
    );
  });
  it("does not turn image or code examples into evidence navigation", () => {
    const image = {
      type: "element",
      tagName: "img",
      properties: { src: "evidence://image" },
    };
    const text = { type: "text", value: "[citation:例](evidence://example)" };
    rehypeEvidenceLinks()({ type: "root", children: [image, text] });
    expect(image.properties.src).toBe("evidence://image");
    expect(text.value).toContain("evidence://example");
  });
  it("keeps dangerous URLs subject to the existing sanitizer", () => {
    const html = renderToStaticMarkup(
      createElement(MarkdownContent, {
        content: "[citation:危险](javascript:alert%281%29)",
        isLoading: false,
      }),
    );
    expect(html).not.toContain('href="javascript:');
    expect(html).not.toContain("data-evidence-id=");
  });
  it("recognizes only the canonical internal route, preserving encoded IDs", () => {
    expect(
      evidenceIdFromDetailPath(
        "/workspace/library?evidence_id=one%2Ftwo%20three",
      ),
    ).toBe("one/two three");
    expect(
      evidenceIdFromDetailPath(
        "https://example.test/workspace/library?evidence_id=one",
      ),
    ).toBeNull();
    expect(
      evidenceIdFromDetailPath("/workspace/library-extra?evidence_id=one"),
    ).toBeNull();
  });
});
