import { getBackendBaseURL } from "@/core/config";

export type DailyResearchItem = {
  id: string;
  title: string;
  summary: string;
  tag: string;
  source_basis: string;
  prompt: string;
  retrieval_query: string;
  origin: "yesterday_hot" | "evidence_backed_fallback";
  evidence_count: number;
  knowledge_release_id: string;
  popularity_users: number | null;
  popularity_searches: number | null;
  dynasty?: string | null;
  time_label?: string;
  place?: string | null;
  people?: string[];
  entities?: Array<{ id: string; name: string; entity_type: string }>;
  sources?: Array<{
    evidence_id: string;
    document_id: string;
    document_title: string;
    chunk_id: string;
    page_start: number | null;
    page_end: number | null;
    quote?: string | null;
  }>;
  degraded?: boolean;
  notice?: string | null;
};

export type DailyResearchFeed = {
  kind: "daily_grounded";
  generated_for: string;
  next_refresh_at: string;
  items: DailyResearchItem[];
  notice?: string | null;
};

export type DailyResearchHistory = {
  kind: "daily_grounded_history";
  current: DailyResearchFeed;
  previous: DailyResearchFeed[];
  history_days: number;
};

const DAILY_FEED_CACHE_KEY = "xingxi:daily-research-feed";

function shanghaiDate(value = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(value);
  const part = (type: string) =>
    parts.find((item) => item.type === type)?.value ?? "00";
  return `${part("year")}-${part("month")}-${part("day")}`;
}

function datedCacheKey(day: string) {
  return `${DAILY_FEED_CACHE_KEY}:${day}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isDailyResearchFeed(value: unknown): value is DailyResearchFeed {
  if (
    !isRecord(value) ||
    value.kind !== "daily_grounded" ||
    typeof value.generated_for !== "string" ||
    typeof value.next_refresh_at !== "string" ||
    !Array.isArray(value.items)
  ) {
    return false;
  }
  return value.items.every(
    (item) =>
      isRecord(item) &&
      typeof item.id === "string" &&
      typeof item.title === "string" &&
      typeof item.summary === "string" &&
      typeof item.prompt === "string" &&
      typeof item.retrieval_query === "string" &&
      item.retrieval_query.trim().length > 0 &&
      typeof item.evidence_count === "number" &&
      typeof item.knowledge_release_id === "string" &&
      Array.isArray(item.sources) &&
      item.sources.length > 0 &&
      item.sources.every(
        (source) =>
          isRecord(source) &&
          typeof source.evidence_id === "string" &&
          typeof source.document_id === "string" &&
          typeof source.document_title === "string" &&
          typeof source.chunk_id === "string",
      ),
  );
}

export function readCachedDailyResearchFeed(): DailyResearchFeed | null {
  if (typeof window === "undefined") return null;
  try {
    const raw =
      window.localStorage.getItem(datedCacheKey(shanghaiDate())) ??
      window.localStorage.getItem(DAILY_FEED_CACHE_KEY);
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    return isDailyResearchFeed(value) ? value : null;
  } catch {
    return null;
  }
}

export async function fetchDailyResearchFeed(
  signal?: AbortSignal,
  timeoutMs = 6_000,
): Promise<DailyResearchFeed> {
  const timeoutController = new AbortController();
  let timedOut = false;
  const timeout = setTimeout(() => {
    timedOut = true;
    timeoutController.abort();
  }, timeoutMs);
  const abort = () => timeoutController.abort();
  signal?.addEventListener("abort", abort, { once: true });
  try {
    const response = await fetch(
      `${getBackendBaseURL()}/api/research-feed/daily?limit=6`,
      {
        cache: "no-store",
        signal: timeoutController.signal,
      },
    );
    const payload = (await response.json().catch(() => null)) as
      | DailyResearchFeed
      | { detail?: string }
      | null;
    if (!response.ok) {
      const detail =
        payload && "detail" in payload ? payload.detail : undefined;
      throw new Error(detail ?? "今日选题暂时无法加载");
    }
    if (!isDailyResearchFeed(payload)) {
      throw new Error("今日选题接口返回了无效数据");
    }
    const feed = payload;
    try {
      window.localStorage.setItem(DAILY_FEED_CACHE_KEY, JSON.stringify(feed));
      window.localStorage.setItem(
        datedCacheKey(feed.generated_for),
        JSON.stringify(feed),
      );
    } catch {
      // Storage can be unavailable in private browsing; the network result is usable.
    }
    return feed;
  } catch (error) {
    if (timedOut) throw new Error("今日选题加载超时");
    throw error;
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener("abort", abort);
  }
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
