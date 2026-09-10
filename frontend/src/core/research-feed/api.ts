import { getBackendBaseURL } from "@/core/config";

export type DailyResearchItem = {
  id: string;
  title: string;
  summary: string;
  tag: string;
  source_basis: string;
  prompt: string;
  origin: "yesterday_hot" | "evidence_backed_fallback";
  evidence_count: number;
  knowledge_release_id: string;
  popularity_users: number | null;
  popularity_searches: number | null;
};

export type DailyResearchFeed = {
  kind: "daily_grounded";
  generated_for: string;
  next_refresh_at: string;
  items: DailyResearchItem[];
};

export type DailyResearchHistory = {
  kind: "daily_grounded_history";
  current: DailyResearchFeed;
  previous: DailyResearchFeed[];
  history_days: number;
};

export async function fetchDailyResearchFeed(
  signal?: AbortSignal,
): Promise<DailyResearchFeed> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/research-feed/daily`,
    {
      cache: "no-store",
      signal,
    },
  );
  const payload = (await response.json().catch(() => null)) as
    | DailyResearchFeed
    | { detail?: string }
    | null;
  if (!response.ok) {
    const detail = payload && "detail" in payload ? payload.detail : undefined;
    throw new Error(detail ?? "今日选题暂时无法加载");
  }
  return payload as DailyResearchFeed;
}

export async function fetchDailyResearchHistory(
  days = 7,
  signal?: AbortSignal,
): Promise<DailyResearchHistory> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/research-feed/history?days=${days}`,
    { cache: "no-store", signal },
  );
  const payload = (await response.json().catch(() => null)) as
    | DailyResearchHistory
    | { detail?: string }
    | null;
  if (!response.ok) {
    const detail = payload && "detail" in payload ? payload.detail : undefined;
    throw new Error(detail ?? "往日选题暂时无法加载");
  }
  return payload as DailyResearchHistory;
}
