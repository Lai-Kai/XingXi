import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

import type {
  EvidenceDetail,
  StructuredSearchRequest,
  StructuredSearchResponse,
} from "./types";

export async function searchStructuredKnowledge(
  request: StructuredSearchRequest,
  signal?: AbortSignal,
): Promise<StructuredSearchResponse> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/knowledge-search/structured`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      signal,
    },
  );
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: string | { message?: string };
    } | null;
    const detail = payload?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : (detail?.message ?? "结构化检索失败");
    throw new Error(message);
  }
  return (await response.json()) as StructuredSearchResponse;
}

export async function getEvidenceDetail(
  evidenceId: string,
  signal?: AbortSignal,
): Promise<EvidenceDetail> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/knowledge-search/evidence/${encodeURIComponent(evidenceId)}`,
    {
      method: "GET",
      signal,
    },
  );
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: string | { message?: string; code?: string };
    } | null;
    const detail = payload?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : (detail?.message ?? "证据详情加载失败");
    throw new Error(message);
  }
  return (await response.json()) as EvidenceDetail;
}
