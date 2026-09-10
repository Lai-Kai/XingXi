export type CitationOccurrence = {
  index: number;
  title: string;
};

export type CitationSource = {
  id: string;
  title: string;
  url: string;
  domain: string;
  count: number;
  occurrences: CitationOccurrence[];
  /** Present when the citation targets a domain evidence pack item. */
  evidenceId?: string;
  protocol?: "http" | "evidence";
};

export const EVIDENCE_HREF_PREFIX = "evidence://";

// Uses a non-consuming lookbehind (?<!!) to skip image links (![citation:…])
// without eating the boundary char, so back-to-back citations both match. The
// URL sub-pattern consumes either non-paren chars or a balanced (…) group, so
// disambiguation URLs like .../Foo_(a)_(b) survive rather than truncating at
// the first inner paren. Also accepts evidence:// IDs for Xingxi locators.
const CITATION_LINK_RE =
  /(?<!!)\[citation:\s*([^\]]+?)\]\((https?:\/\/(?:[^\s()]|\([^\s()]*\))+|evidence:\/\/[^\s)]+)\)/gi;

const GENERIC_CITATION_TITLES = new Set(["source", "来源"]);

export function parseEvidenceHref(
  href: string | null | undefined,
): string | null {
  if (!href) {
    return null;
  }
  const trimmed = href.trim();
  if (!trimmed.toLowerCase().startsWith(EVIDENCE_HREF_PREFIX)) {
    return null;
  }
  const raw = trimmed.slice(EVIDENCE_HREF_PREFIX.length);
  const id = raw.split(/[?#]/, 1)[0]?.replace(/^\/+/, "").trim();
  return id !== undefined && id.length > 0 ? id : null;
}

export function formatEvidenceHref(evidenceId: string): string {
  return `${EVIDENCE_HREF_PREFIX}${evidenceId}`;
}

export function evidenceDetailPath(evidenceId: string): string {
  const params = new URLSearchParams({ evidence_id: evidenceId });
  return `/workspace/library?${params.toString()}`;
}

export function extractCitationSources(markdown: string): CitationSource[] {
  if (!markdown) {
    return [];
  }

  const searchable = maskCode(markdown);
  const sourcesByUrl = new Map<string, CitationSource>();

  for (const match of searchable.matchAll(CITATION_LINK_RE)) {
    const rawTitle = (match[1] ?? "").trim();
    const rawUrl = match[2] ?? "";
    const evidenceId = parseEvidenceHref(rawUrl);
    const url = evidenceId
      ? formatEvidenceHref(evidenceId)
      : normalizeUrl(rawUrl);
    if (!url) {
      continue;
    }

    const domain = evidenceId ? "evidence" : extractDomain(url);
    const title = normalizeTitle(rawTitle, domain);
    const index = match.index ?? 0;
    const existing = sourcesByUrl.get(url);

    if (existing) {
      existing.count += 1;
      existing.occurrences.push({ index, title });
      continue;
    }

    const source: CitationSource = {
      id: url,
      title,
      url,
      domain,
      count: 1,
      occurrences: [{ index, title }],
    };
    if (evidenceId) {
      source.evidenceId = evidenceId;
      source.protocol = "evidence";
    }
    sourcesByUrl.set(url, source);
  }

  return Array.from(sourcesByUrl.values());
}

export function formatCitationMarkdownReference(
  source: CitationSource,
): string {
  return `[${source.title}](${source.url})`;
}

function normalizeTitle(title: string, domain: string): string {
  const compact = title.replace(/\s+/g, " ").trim();
  if (!compact || GENERIC_CITATION_TITLES.has(compact.toLowerCase())) {
    return domain;
  }
  return compact;
}

function normalizeUrl(value: string): string | null {
  try {
    const url = new URL(value);
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return null;
    }
    return url.href;
  } catch {
    return null;
  }
}

function extractDomain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./i, "");
  } catch {
    return url;
  }
}

// Blanks out code regions so example citations inside code aren't scraped as
// real sources, while preserving string length (and newlines) so occurrence
// indices stay aligned with the original markdown.
function maskCode(markdown: string): string {
  return maskInlineCode(maskFencedCodeBlocks(markdown));
}

function maskFencedCodeBlocks(markdown: string): string {
  // Match a fenced block up to its matching closing fence, or — while the
  // message is still streaming — to end of input when the fence is unclosed.
  return markdown.replace(
    /(^|\n)(`{3,}|~{3,})[^\n]*(?:\n[\s\S]*?\n\2[^\n]*(?=\n|$)|[\s\S]*$)/g,
    maskKeepingNewlines,
  );
}

function maskInlineCode(markdown: string): string {
  // Only mask closed spans: an unclosed backtick run renders as literal text,
  // so a citation after it is a real, rendered link and must not be masked.
  return markdown.replace(/(`+)[\s\S]*?\1/g, maskKeepingNewlines);
}

function maskKeepingNewlines(block: string): string {
  return block.replace(/[^\n]/g, " ");
}
