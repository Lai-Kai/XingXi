import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

import type { GlossLabel, GlossLabelInput } from "./types";

export async function createGlossLabel(
  input: GlossLabelInput,
): Promise<GlossLabel> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/knowledge-graph/gloss`,
    {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `释读请求失败 (${response.status})`);
  }
  return response.json() as Promise<GlossLabel>;
}
