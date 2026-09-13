export const XINGXI_CHAT_PATH = "/workspace/chats/new";

export type XingxiChatScope = {
  documentIds?: string[];
  evidenceIds?: string[];
  releaseId?: string;
  retrievalQuery?: string;
};

export function xingxiChatHref(prompt: string, scope?: XingxiChatScope) {
  const params = new URLSearchParams();
  if (prompt.trim()) params.set("prompt", prompt);
  for (const documentId of new Set(scope?.documentIds ?? [])) {
    if (documentId) params.append("document_id", documentId);
  }
  for (const evidenceId of new Set(scope?.evidenceIds ?? [])) {
    if (evidenceId) params.append("evidence_id", evidenceId);
  }
  if (scope?.releaseId) params.set("release_id", scope.releaseId);
  if (scope?.retrievalQuery) {
    params.set("topic_query", scope.retrievalQuery);
  }
  const query = params.toString();
  return `${XINGXI_CHAT_PATH}${query ? `?${query}` : ""}`;
}

type NextSearchParams = Readonly<Record<string, string | string[] | undefined>>;

const LEGACY_ENTRY_MODES = new Set(["flash", "pro", "ultra"]);

export function legacyModeRedirectHref(
  searchParams: NextSearchParams,
): string | null {
  const rawMode = searchParams.mode;
  const mode = Array.isArray(rawMode) ? rawMode[0] : rawMode;
  if (!mode || !LEGACY_ENTRY_MODES.has(mode)) return null;

  const normalized = new URLSearchParams();
  for (const [key, rawValue] of Object.entries(searchParams)) {
    if (key === "mode" || rawValue === undefined) continue;
    const values = Array.isArray(rawValue) ? rawValue : [rawValue];
    for (const value of values) normalized.append(key, value);
  }
  const query = normalized.toString();
  return `${XINGXI_CHAT_PATH}${query ? `?${query}` : ""}`;
}

type SearchParamsReader = Pick<URLSearchParams, "get" | "getAll">;

function nonEmptyParam(value: string | null): string | undefined {
  const normalized = value?.trim();
  if (!normalized) return undefined;
  return normalized;
}

export function parseXingxiChatScope(
  searchParams: SearchParamsReader,
): XingxiChatScope | null {
  const documentIds = [...new Set(searchParams.getAll("document_id"))].filter(
    Boolean,
  );
  const evidenceIds = [...new Set(searchParams.getAll("evidence_id"))].filter(
    Boolean,
  );
  const releaseId = nonEmptyParam(searchParams.get("release_id"));
  const retrievalQuery = nonEmptyParam(searchParams.get("topic_query"));
  if (!documentIds.length || !evidenceIds.length || !retrievalQuery)
    return null;
  return { documentIds, evidenceIds, releaseId, retrievalQuery };
}

export type DailyTopicEntryContext = {
  daily_topic_query?: string;
  daily_topic_document_ids?: string[];
  daily_topic_evidence_ids?: string[];
  daily_topic_release_id?: string;
};

export function dailyTopicContextForEntry(
  scope: XingxiChatScope | null,
): DailyTopicEntryContext {
  if (!scope?.retrievalQuery || !scope.documentIds?.length) return {};
  return {
    daily_topic_query: scope.retrievalQuery,
    daily_topic_document_ids: scope.documentIds,
    daily_topic_evidence_ids: scope.evidenceIds ?? [],
    ...(scope.releaseId ? { daily_topic_release_id: scope.releaseId } : {}),
  };
}
