export type XingxiEntryMode = "flash" | "pro" | "ultra";

export const XINGXI_ENTRY_MODES: ReadonlyArray<{
  id: XingxiEntryMode;
  label: string;
}> = [
  { id: "flash", label: "快速问答" },
  { id: "pro", label: "专业研究" },
  { id: "ultra", label: "深度求索" },
];

export function parseEntryMode(
  value: string | null,
): XingxiEntryMode | undefined {
  return value === "flash" || value === "pro" || value === "ultra"
    ? value
    : undefined;
}

export function modeContextForEntry(mode: XingxiEntryMode) {
  return {
    mode,
    thinking_enabled: mode !== "flash",
    reasoning_effort:
      mode === "ultra"
        ? ("medium" as const)
        : mode === "pro"
          ? ("medium" as const)
          : ("minimal" as const),
  };
}

export function xingxiWorkspaceHref(mode: XingxiEntryMode) {
  return `/workspace?${new URLSearchParams({ mode }).toString()}`;
}

export type XingxiChatScope = {
  documentIds?: string[];
  evidenceIds?: string[];
  releaseId?: string;
  retrievalQuery?: string;
};

export function xingxiChatHref(
  prompt: string,
  mode: XingxiEntryMode,
  scope?: XingxiChatScope,
) {
  const params = new URLSearchParams({ mode });
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
  return `/workspace/chats/new?${params.toString()}`;
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
