import {
  evidenceDetailPath,
  parseEvidenceHref,
} from "@/core/citations/sources";

type MarkdownNode = {
  type: string;
  tagName?: string;
  properties?: Record<string, unknown>;
  children?: MarkdownNode[];
};

// Translate the domain locator before the renderer's standard URL sanitizer.
// Code/text and image nodes are unchanged; other schemes use the original policy.
export function rehypeEvidenceLinks() {
  return (tree: MarkdownNode) => {
    function visit(node: MarkdownNode) {
      if (
        node.type === "element" &&
        node.tagName === "a" &&
        typeof node.properties?.href === "string"
      ) {
        const id = parseEvidenceHref(node.properties.href);
        if (id) node.properties.href = evidenceDetailPath(id);
      }
      node.children?.forEach(visit);
    }
    visit(tree);
  };
}

export function evidenceIdFromDetailPath(href: string | undefined) {
  if (!href?.startsWith("/workspace/library?")) return null;
  const url = new URL(href, "https://xingxi.invalid");
  return url.pathname === "/workspace/library"
    ? (url.searchParams.get("evidence_id")?.trim() ?? null)
    : null;
}
