"use client";

import {
  ArrowUp,
  Bot,
  CalendarDays,
  Check,
  ChevronDown,
  ChevronUp,
  FileText,
  Settings2,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import {
  BusinessButton,
  BusinessSkeleton,
  BusinessTextarea,
} from "@/components/workspace/business-controls";
import { BusinessMobileHeader } from "@/components/workspace/business-page";
import { ResearchHero } from "@/components/workspace/research-hero";
import { useI18n } from "@/core/i18n/hooks";
import {
  type DailyResearchHistory,
  type DailyResearchFeed,
  fetchDailyResearchHistory,
  fetchDailyResearchFeed,
  readCachedDailyResearchFeed,
} from "@/core/research-feed/api";
import { buildLocalFallbackDailyResearchFeed } from "@/core/research-feed/fallback";
import {
  type XingxiChatScope,
  xingxiChatHref,
} from "@/core/threads/xingxi-entry";
import { isIMEComposing } from "@/lib/ime";
import { cn } from "@/lib/utils";

type FeedTab = "trends" | "latest" | "collections";

const tabs = [
  { id: "trends" as const, label: "今日选题" },
  { id: "latest" as const, label: "最新收录" },
  { id: "collections" as const, label: "智能推荐" },
];

type ResearchItem = {
  id: string;
  tab: FeedTab;
  title: string;
  date: string;
  source: string;
  tag: string;
  summary: string;
  prompt?: string;
  count?: number;
  sourceCount?: number;
  context?: string;
  sources?: Array<{
    evidence_id: string;
    document_id: string;
    document_title: string;
    chunk_id: string;
    page_start: number | null;
    page_end: number | null;
    quote?: string | null;
  }>;
  scope?: XingxiChatScope;
};

function sourcePageLabel(source: NonNullable<ResearchItem["sources"]>[number]) {
  if (source.page_start === null) return "页码待核";
  if (source.page_end === null || source.page_end === source.page_start) {
    return `${source.page_start}页`;
  }
  return `${source.page_start}-${source.page_end}页`;
}

const researchItems: ResearchItem[] = [
  {
    id: "latest-shops",
    tab: "latest" as const,
    title: "民国时期木渎镇区商号与街巷名称索引",
    date: "2026-07-18",
    source: "苏州地方文献数字化项目",
    tag: "新收文献",
    summary:
      "从新入库的商会名录与旧地图中抽取商号、业别和街巷信息，保留原页码并关联现代地名。",
    count: 54,
  },
  {
    id: "latest-lingyan",
    tab: "latest" as const,
    title: "灵岩山历代题咏中的地景名称整理",
    date: "2026-07-16",
    source: "诗文总集、地方志艺文卷",
    tag: "诗文地理",
    summary:
      "整理馆娃宫、琴台、玩月池等地景在历代诗文中的称谓变化，并列出作品年代与作者信息。",
    count: 71,
  },
  {
    id: "collection-documents",
    tab: "collections" as const,
    title: "首批地方文献的卷目、版本与可用数字资源",
    date: "馆藏专题",
    source: "国家图书馆、苏州图书馆",
    tag: "方志",
    summary:
      "汇总现存版本、馆藏机构与数字影像状态，提示版次差异，为后续原文定位建立基础。",
    count: 143,
  },
  {
    id: "collection-maps",
    tab: "collections" as const,
    title: "木渎水系相关历史舆图的检索路径",
    date: "馆藏专题",
    source: "地方舆图与水利图册",
    tag: "历史地图",
    summary:
      "按年代列出可用于复原胥江、香溪与镇区河道关系的舆图，并说明比例、图例和使用限制。",
    count: 89,
  },
];

export default function XingxiHomePage() {
  const router = useRouter();
  const { t } = useI18n();
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState<FeedTab>("trends");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [preferences, setPreferences] = useState(["古迹", "方志"]);
  const [votes, setVotes] = useState<Record<string, "up" | "down">>({});
  const [dailyFeed, setDailyFeed] = useState<DailyResearchFeed | null>(null);
  const [dailyFeedError, setDailyFeedError] = useState<string | null>(null);
  const [dailyFeedLoading, setDailyFeedLoading] = useState(true);
  const [dailyFeedAttempt, setDailyFeedAttempt] = useState(0);
  const [dailyHistory, setDailyHistory] = useState<DailyResearchHistory | null>(
    null,
  );
  const [dailyHistoryLoading, setDailyHistoryLoading] = useState(false);
  const [dailyHistoryError, setDailyHistoryError] = useState<string | null>(
    null,
  );
  const [showDailyHistory, setShowDailyHistory] = useState(false);
  const [historyDate, setHistoryDate] = useState("all");

  useEffect(() => {
    document.title = `${t.pages.newChat} - ${t.pages.appName}`;
  }, [t.pages.appName, t.pages.newChat]);

  useEffect(() => {
    const controller = new AbortController();
    const cachedFeed = readCachedDailyResearchFeed();
    const usableCachedFeed = cachedFeed?.items.length ? cachedFeed : null;
    const localFallback = buildLocalFallbackDailyResearchFeed();
    if (usableCachedFeed) setDailyFeed(usableCachedFeed);
    setDailyFeedLoading(true);
    setDailyFeedError(usableCachedFeed ? "部分内容暂时使用本地资料" : null);
    fetchDailyResearchFeed(controller.signal)
      .then((feed) => {
        if (feed.items.length) {
          setDailyFeed(feed);
          setDailyFeedError(feed.notice ?? null);
        } else {
          setDailyFeed(usableCachedFeed ?? localFallback);
          setDailyFeedError("部分内容暂时使用本地资料");
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setDailyFeed(usableCachedFeed ?? localFallback);
        setDailyFeedError(
          usableCachedFeed || localFallback.items.length
            ? "部分内容暂时使用本地资料"
            : error instanceof Error
              ? error.message
              : "今日选题暂时无法加载",
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setDailyFeedLoading(false);
      });
    return () => controller.abort();
  }, [dailyFeedAttempt]);

  useEffect(() => {
    if (!dailyFeed) return;
    const refreshAt = Date.parse(dailyFeed.next_refresh_at);
    const delay = Math.max(1_000, refreshAt - Date.now());
    const timer = window.setTimeout(
      () => setDailyFeedAttempt((attempt) => attempt + 1),
      Math.min(delay, 2_147_483_647),
    );
    return () => window.clearTimeout(timer);
  }, [dailyFeed]);

  const visibleItems = useMemo(() => {
    if (tab === "trends") {
      const feeds =
        showDailyHistory && dailyHistory
          ? [dailyHistory.current, ...dailyHistory.previous]
          : dailyFeed
            ? [dailyFeed]
            : [];
      return feeds
        .filter(
          (feed) =>
            !showDailyHistory ||
            historyDate === "all" ||
            feed.generated_for === historyDate,
        )
        .flatMap((feed) =>
          feed.items.map<ResearchItem>((item) => ({
            id: `${feed.generated_for}-${item.id}`,
            tab: "trends",
            title: item.title,
            date: feed.generated_for,
            source: item.source_basis,
            tag: item.tag,
            summary: item.summary,
            prompt: item.prompt,
            scope: {
              documentIds: item.sources?.map((source) => source.document_id),
              evidenceIds: item.sources?.map((source) => source.evidence_id),
              releaseId: item.knowledge_release_id,
              retrievalQuery: item.retrieval_query,
            },
            sourceCount: item.sources?.length ?? item.evidence_count,
            context: [item.time_label, item.place, ...(item.people ?? [])]
              .filter(Boolean)
              .join(" · "),
            sources: item.sources ?? [],
          })),
        );
    }
    return researchItems.filter((item) => item.tab === tab);
  }, [dailyFeed, dailyHistory, showDailyHistory, tab, historyDate]);

  async function toggleDailyHistory() {
    if (showDailyHistory) {
      setShowDailyHistory(false);
      return;
    }
    if (dailyHistory) {
      setShowDailyHistory(true);
      return;
    }
    setDailyHistoryLoading(true);
    setDailyHistoryError(null);
    try {
      const history = await fetchDailyResearchHistory(7);
      setDailyHistory(history);
      setShowDailyHistory(true);
    } catch (reason) {
      setDailyHistoryError(
        reason instanceof Error ? reason.message : "往日选题暂时无法加载",
      );
    } finally {
      setDailyHistoryLoading(false);
    }
  }

  function submitResearch(prompt = query) {
    const value = prompt.trim();
    if (!value) return;
    router.push(xingxiChatHref(value));
  }

  function togglePreference(value: string) {
    setPreferences((current) =>
      current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value],
    );
  }

  return (
    <main className="research-home bg-background text-foreground size-full overflow-y-auto">
      <BusinessMobileHeader title="文史检索" />
      <div className="mx-auto max-w-[1280px] px-4 py-5 sm:px-7 sm:py-8 lg:px-10">
        <div className="mx-auto max-w-[960px]">
          <ResearchHero>
            <form
              className="bg-card/95 shadow-heritage-card mt-6 rounded-xl border p-3 sm:p-4"
              onSubmit={(event) => {
                event.preventDefault();
                submitResearch();
              }}
            >
              <BusinessTextarea
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (
                    event.key === "Enter" &&
                    !event.shiftKey &&
                    !isIMEComposing(event)
                  ) {
                    event.preventDefault();
                    submitResearch();
                  }
                }}
                aria-label="研究问题"
                placeholder="例如：乾隆为什么多次到木渎？"
                className="min-h-24 resize-none border-0 bg-transparent px-2 shadow-none sm:text-base"
              />
              <div className="mt-2 flex flex-wrap items-center gap-2 border-t pt-3">
                <span className="text-primary inline-flex items-center gap-1.5 px-2 text-sm">
                  <Bot className="size-4" />
                  星羲文史助手
                </span>
                <BusinessButton
                  type="submit"
                  aria-label="开始研究"
                  disabled={!query.trim()}
                  className="ml-auto min-h-11 gap-2"
                >
                  <span>开始考据</span>
                  <ArrowUp className="size-4" />
                </BusinessButton>
              </div>
            </form>
            <div
              className="mt-4 flex flex-wrap gap-2"
              aria-label="文史研究方向"
            >
              {["古迹", "方志", "人物", "园林", "水系"].map((topic) => (
                <BusinessButton
                  key={topic}
                  size="sm"
                  variant="outline"
                  className="bg-card/85 min-h-9 rounded-full"
                  onClick={() =>
                    setQuery((current) =>
                      current
                        ? `${current} ${topic}`
                        : `请考证木渎${topic}，并列出可核验的出处。`,
                    )
                  }
                >
                  {topic}
                </BusinessButton>
              ))}
            </div>
          </ResearchHero>

          <section className="mt-8" aria-label="研究动态">
            <div className="relative flex flex-wrap items-center justify-between gap-3 border-b pb-4">
              <div
                role="tablist"
                aria-label="研究动态"
                className="bg-muted flex max-w-full gap-1 overflow-x-auto rounded-lg p-1"
              >
                {tabs.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    role="tab"
                    id={`feed-tab-${item.id}`}
                    aria-controls="research-feed"
                    aria-selected={tab === item.id}
                    tabIndex={tab === item.id ? 0 : -1}
                    onClick={() => setTab(item.id)}
                    onKeyDown={(event) => {
                      if (
                        !["ArrowLeft", "ArrowRight", "Home", "End"].includes(
                          event.key,
                        )
                      )
                        return;
                      event.preventDefault();
                      const current = tabs.findIndex(
                        (candidate) => candidate.id === item.id,
                      );
                      const index =
                        event.key === "Home"
                          ? 0
                          : event.key === "End"
                            ? tabs.length - 1
                            : (current +
                                (event.key === "ArrowRight" ? 1 : -1) +
                                tabs.length) %
                              tabs.length;
                      const next = tabs[index]!;
                      setTab(next.id);
                      document.getElementById(`feed-tab-${next.id}`)?.focus();
                    }}
                    className={cn(
                      "research-touch focus-visible:ring-ring min-h-10 shrink-0 rounded-md px-3 text-sm outline-none focus-visible:ring-2 sm:px-4",
                      tab === item.id
                        ? "bg-card text-primary shadow-sm"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
              <BusinessButton
                variant="outline"
                aria-expanded={settingsOpen}
                aria-controls="research-preferences"
                onClick={() => setSettingsOpen((open) => !open)}
                className="gap-2"
              >
                <Settings2 className="size-4" />
                个性化设置
              </BusinessButton>
              {settingsOpen && (
                <div
                  id="research-preferences"
                  className="bg-card shadow-heritage-overlay absolute top-full right-0 z-20 mt-2 w-full max-w-sm rounded-xl border p-4"
                >
                  <p className="text-sm font-medium">关注的研究方向</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {["古迹", "方志", "人物", "园林", "水系"].map((item) => (
                      <BusinessButton
                        key={item}
                        size="sm"
                        variant={
                          preferences.includes(item) ? "secondary" : "outline"
                        }
                        aria-pressed={preferences.includes(item)}
                        onClick={() => togglePreference(item)}
                      >
                        {preferences.includes(item) && (
                          <Check className="size-3.5" />
                        )}
                        {item}
                      </BusinessButton>
                    ))}
                  </div>
                  <BusinessButton
                    variant="ghost"
                    size="sm"
                    className="mt-3"
                    onClick={() => setSettingsOpen(false)}
                  >
                    收起设置
                  </BusinessButton>
                </div>
              )}
            </div>
            <div className="text-muted-foreground flex flex-wrap items-center justify-between gap-2 py-4 text-xs">
              <span>
                {tab === "trends"
                  ? "循着出处，发现今日可研读的课题"
                  : "既有文献专题线索，实时收录状态以文献库为准"}
              </span>
              {tab === "trends" && dailyFeed && (
                <span className="inline-flex items-center gap-1">
                  <CalendarDays className="size-3.5" />
                  {dailyFeed.generated_for}
                </span>
              )}
            </div>
            <div
              id="research-feed"
              role="tabpanel"
              aria-labelledby={`feed-tab-${tab}`}
              className="space-y-4 pb-6"
            >
              {tab === "trends" && showDailyHistory && dailyHistory && (
                <label className="text-muted-foreground flex flex-wrap items-center gap-2 text-sm">
                  选题日期
                  <select
                    aria-label="选题日期"
                    className="field max-w-64"
                    value={historyDate}
                    onChange={(event) => setHistoryDate(event.target.value)}
                  >
                    <option value="all">全部已加载日期</option>
                    {[dailyHistory.current, ...dailyHistory.previous].map(
                      (feed) => (
                        <option
                          key={feed.generated_for}
                          value={feed.generated_for}
                        >
                          {feed.generated_for}
                        </option>
                      ),
                    )}
                  </select>
                </label>
              )}
              {tab === "trends" &&
                dailyFeedLoading &&
                visibleItems.length === 0 && (
                  <div
                    role="status"
                    aria-label="正在加载今日选题"
                    className="grid gap-4 sm:grid-cols-2"
                  >
                    {[1, 2, 3, 4].map((item) => (
                      <div
                        key={item}
                        className="bg-card space-y-4 rounded-xl border p-5"
                      >
                        <BusinessSkeleton className="h-3 w-28" />
                        <BusinessSkeleton className="h-6 w-3/4" />
                        <BusinessSkeleton className="h-16 w-full" />
                      </div>
                    ))}
                  </div>
                )}
              {tab === "trends" && dailyFeedError && (
                <div
                  role={visibleItems.length ? "status" : "alert"}
                  className="bg-heritage-pending-surface text-heritage-pending-foreground flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3 text-sm"
                >
                  <span>{dailyFeedError}</span>
                  <BusinessButton
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      setDailyFeedAttempt((attempt) => attempt + 1)
                    }
                  >
                    重新加载
                  </BusinessButton>
                </div>
              )}
              {tab === "trends" &&
                !dailyFeedLoading &&
                !dailyFeedError &&
                visibleItems.length === 0 && (
                  <p
                    role="status"
                    className="text-muted-foreground py-10 text-center"
                  >
                    暂无今日选题
                  </p>
                )}
              <div className="grid gap-4 sm:grid-cols-2">
                {visibleItems.map((item) => (
                  <article
                    key={item.id}
                    className="research-topic bg-card shadow-heritage-card hover:shadow-heritage-overlay flex min-w-0 flex-col rounded-xl border p-5 transition-shadow"
                  >
                    <div className="text-muted-foreground mb-3 flex flex-wrap items-center justify-between gap-2 text-xs">
                      <span>{item.date}</span>
                      <span className="bg-secondary text-secondary-foreground rounded-full px-2.5 py-1">
                        {item.tag}
                      </span>
                    </div>
                    <h2 className="font-serif text-lg leading-7 font-semibold">
                      <Link
                        className="focus-visible:ring-ring hover:text-primary rounded focus-visible:ring-2 focus-visible:outline-none"
                        href={xingxiChatHref(
                          item.prompt ??
                            `请围绕“${item.title}”开展研究，并列出可核验的原始出处。`,
                          item.scope,
                        )}
                      >
                        {item.title}
                      </Link>
                    </h2>
                    {item.context && (
                      <p className="text-muted-foreground mt-2 text-xs">
                        {item.context}
                      </p>
                    )}
                    <p className="text-muted-foreground mt-3 flex-1 text-sm leading-6">
                      {item.summary}
                    </p>
                    <div className="bg-muted/45 mt-4 rounded-lg p-3 text-xs leading-5">
                      <p className="text-muted-foreground flex items-center gap-1.5">
                        <FileText className="size-3.5 shrink-0" />
                        <span>{item.source}</span>
                      </p>
                      {item.sourceCount !== undefined && (
                        <p className="text-primary mt-1 font-medium">
                          资料依据 {item.sourceCount} 条
                        </p>
                      )}
                      {item.sources?.slice(0, 2).map((source) => (
                        <Link
                          key={source.evidence_id}
                          href={`/workspace/library?evidence_id=${encodeURIComponent(source.evidence_id)}`}
                          className="text-primary mt-1 block break-words underline underline-offset-4"
                        >
                          {source.document_title}（{sourcePageLabel(source)}）
                        </Link>
                      ))}
                    </div>
                    <div className="mt-4 flex flex-wrap items-center gap-2 border-t pt-3">
                      <Link
                        className="research-touch bg-primary text-primary-foreground inline-flex min-h-10 items-center gap-2 rounded-md px-3 text-sm"
                        href={xingxiChatHref(
                          item.prompt ??
                            `请介绍“${item.title}”，并引用本地资料。`,
                          item.scope,
                        )}
                      >
                        开始了解<span aria-hidden="true">↗</span>
                      </Link>
                      <Link
                        href={xingxiChatHref(
                          `查找“${item.title}”对应的原始文献和页码。`,
                          item.scope,
                        )}
                        aria-label={`查看 ${item.title} 的文献线索`}
                        className="text-primary research-touch inline-flex min-h-10 items-center rounded px-2 text-xs underline underline-offset-4"
                      >
                        文献线索
                      </Link>
                      <div className="ml-auto flex gap-1">
                        <BusinessButton
                          size="icon"
                          variant="ghost"
                          aria-label={`推荐 ${item.title}`}
                          aria-pressed={votes[item.title] === "up"}
                          className={cn(
                            "size-10",
                            votes[item.title] === "up" &&
                              "bg-secondary text-primary",
                          )}
                          onClick={() =>
                            setVotes((current) => ({
                              ...current,
                              [item.title]: "up",
                            }))
                          }
                        >
                          <ThumbsUp className="size-4" />
                        </BusinessButton>
                        <BusinessButton
                          size="icon"
                          variant="ghost"
                          aria-label={`减少推荐 ${item.title}`}
                          aria-pressed={votes[item.title] === "down"}
                          className={cn(
                            "size-10",
                            votes[item.title] === "down" &&
                              "bg-secondary text-primary",
                          )}
                          onClick={() =>
                            setVotes((current) => ({
                              ...current,
                              [item.title]: "down",
                            }))
                          }
                        >
                          <ThumbsDown className="size-4" />
                        </BusinessButton>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
              {tab === "trends" && showDailyHistory && dailyHistory && (
                <p className="text-muted-foreground pt-2 text-center text-xs">
                  已显示今日全部 {dailyHistory.current.items.length} 条及最近
                  {dailyHistory.history_days - 1} 天选题
                </p>
              )}
            </div>
            {tab === "trends" && !dailyFeedLoading && !dailyFeedError && (
              <div className="flex flex-col items-center py-4">
                {dailyHistoryError && (
                  <p role="alert" className="text-destructive mb-3 text-xs">
                    {dailyHistoryError}
                  </p>
                )}
                <BusinessButton
                  variant="outline"
                  disabled={dailyHistoryLoading}
                  aria-expanded={showDailyHistory}
                  onClick={() => void toggleDailyHistory()}
                >
                  <CalendarDays className="size-4" />
                  {dailyHistoryLoading
                    ? "正在加载更多选题…"
                    : showDailyHistory
                      ? "收起更多选题"
                      : "查看更多今日与往日选题"}
                  {showDailyHistory ? (
                    <ChevronUp className="size-4" />
                  ) : (
                    <ChevronDown className="size-4" />
                  )}
                </BusinessButton>
              </div>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
