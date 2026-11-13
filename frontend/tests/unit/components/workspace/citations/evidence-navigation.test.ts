import { afterEach, describe, expect, it, rs } from "@rstest/core";
import { isValidElement, type MouseEvent, type ReactNode } from "react";

import { CitationLink } from "@/components/workspace/citations/citation-link";
import { CitationSourcesPanel } from "@/components/workspace/citations/citation-sources-panel";
import { useEvidenceInspector } from "@/components/workspace/citations/evidence-inspector-context";
import { extractCitationSources } from "@/core/citations/sources";
import { zhCN } from "@/core/i18n/locales/zh-CN";
import { recordOperationEvent } from "@/core/operations/api";

rs.mock("@/components/workspace/citations/evidence-inspector-context", () => ({
  useEvidenceInspector: rs.fn(),
}));
rs.mock("@/core/i18n/hooks", () => ({ useI18n: () => ({ t: zhCN }) }));
rs.mock("@/core/operations/api", () => ({ recordOperationEvent: rs.fn() }));

type Anchor = {
  href: string;
  target?: string;
  children?: ReactNode;
  onClick?: (event: MouseEvent<HTMLAnchorElement>) => void;
};

function anchors(node: ReactNode): Anchor[] {
  if (Array.isArray(node)) return node.flatMap(anchors);
  if (!isValidElement<Anchor>(node)) return [];
  const children = anchors(node.props.children);
  return node.type === "a" ? [node.props, ...children] : children;
}

function click(overrides: Partial<MouseEvent<HTMLAnchorElement>> = {}) {
  const event = {
    button: 0,
    defaultPrevented: false,
    preventDefault: rs.fn(() => {
      event.defaultPrevented = true;
    }),
    stopPropagation: rs.fn(),
    currentTarget: {} as HTMLAnchorElement,
    ...overrides,
  };
  return event as unknown as MouseEvent<HTMLAnchorElement>;
}

function inspector() {
  const openEvidence = rs.fn();
  rs.mocked(useEvidenceInspector).mockReturnValue({
    open: false,
    openEvidence,
    close: rs.fn(),
  });
  return openEvidence;
}

afterEach(() => {
  rs.resetAllMocks();
});

describe("evidence navigation in a conversation", () => {
  it("opens both the inline citation and its hover action inside the inspector", () => {
    const openEvidence = inspector();
    const links = anchors(
      CitationLink({
        href: "/workspace/library?evidence_id=one%2Ftwo",
        children: "方志卷一",
      }),
    );
    expect(links).toHaveLength(2);
    for (const link of links) {
      const event = click();
      link.onClick?.(event);
      expect(event.defaultPrevented).toBe(true);
      expect(openEvidence).toHaveBeenLastCalledWith(
        { id: "one/two", title: "方志卷一" },
        event.currentTarget,
      );
    }
    expect(recordOperationEvent).toHaveBeenCalledTimes(2);
  });

  it.each([
    { ctrlKey: true },
    { metaKey: true },
    { shiftKey: true },
    { altKey: true },
    { button: 1 },
    { defaultPrevented: true },
  ])("preserves native navigation for modified clicks: %j", (modifiers) => {
    const openEvidence = inspector();
    const [link] = anchors(CitationLink({ href: "evidence://one" }));
    const event = click(modifiers);
    link!.onClick?.(event);
    expect(event.defaultPrevented).toBe(Boolean(modifiers.defaultPrevented));
    expect(openEvidence).not.toHaveBeenCalled();
  });

  it("preserves explicit new tabs, external links and navigation outside chat", () => {
    const openEvidence = inspector();
    for (const props of [
      { href: "evidence://one", target: "_blank" },
      { href: "https://example.org/source" },
    ]) {
      const [link] = anchors(CitationLink(props));
      const event = click();
      link!.onClick?.(event);
      expect(link!.target).toBe("_blank");
      expect(event.defaultPrevented).toBe(false);
    }
    expect(openEvidence).not.toHaveBeenCalled();
    rs.mocked(useEvidenceInspector).mockReturnValue(null);
    const [link] = anchors(CitationLink({ href: "evidence://one" }));
    expect(link!.href).toBe("/workspace/library?evidence_id=one");
    const event = click();
    link!.onClick?.(event);
    expect(event.defaultPrevented).toBe(false);
  });

  it("respects a caller's cancelled click", () => {
    const openEvidence = inspector();
    const [link] = anchors(
      CitationLink({
        href: "evidence://one",
        onClick: (event) => event.preventDefault(),
      }),
    );
    link!.onClick?.(click());
    expect(openEvidence).not.toHaveBeenCalled();
  });

  it("opens evidence from the source list while preserving external sources", () => {
    const openEvidence = inspector();
    const sources = extractCitationSources(
      "[citation:方志](evidence://one) [citation:网页](https://example.org)",
    );
    const [evidence, external] = anchors(CitationSourcesPanel({ sources }));
    const event = click();
    evidence!.onClick?.(event);
    expect(openEvidence).toHaveBeenCalledWith(
      { id: "one", title: "方志" },
      event.currentTarget,
    );
    openEvidence.mockClear();
    const modified = click({ metaKey: true });
    evidence!.onClick?.(modified);
    expect(modified.defaultPrevented).toBe(false);
    external!.onClick?.(click());
    expect(external!.target).toBe("_blank");
    expect(openEvidence).not.toHaveBeenCalled();
  });
});
