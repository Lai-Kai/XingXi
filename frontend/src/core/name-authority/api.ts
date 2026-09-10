import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

import type { NameAuthorityResolution, NameVariantInput } from "./types";

export async function resolveNameAuthority(input: {
  variants: NameVariantInput[];
  research_context?: string;
}): Promise<NameAuthorityResolution> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/knowledge-graph/aliases/resolve-authority`,
    {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `异名辨析请求失败 (${response.status})`);
  }
  return response.json() as Promise<NameAuthorityResolution>;
}
