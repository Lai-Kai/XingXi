"use client";

import {
  ArrowUp,
  BrainCircuit,
  Bot,
  CalendarDays,
  Check,
  ChevronDown,
  ChevronUp,
  FileText,
  GraduationCap,
  Settings2,
  ThumbsDown,
  ThumbsUp,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { BusinessMobileHeader } from "@/components/workspace/business-page";
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
  type XingxiEntryMode,
  type XingxiChatScope,
  XINGXI_ENTRY_MODES,
  parseEntryMode,
  xingxiChatHref,
  xingxiWorkspaceHref,
} from "@/core/threads/xingxi-entry";
import { cn } from "@/lib/utils";

type FeedTab = "trends" | "latest" | "collections";

const modeIcons = {
  flash: Zap,
  pro: GraduationCap,
  ultra: BrainCircuit,
} satisfies Record<XingxiEntryMode, typeof Zap>;

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
  const searchParams = useSearchParams();
  const { t } = useI18n();
  const requestedMode = parseEntryMode(searchParams.get("mode")) ?? "pro";
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<XingxiEntryMode>(requestedMode);
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

  useEffect(() => {
    setMode(requestedMode);
  }, [requestedMode]);

  useEffect(() => {
    const modeLabel =
      XINGXI_ENTRY_MODES.find((item) => item.id === mode)?.label ??
      t.pages.newChat;
    document.title = `${modeLabel} - ${t.pages.appName}`;
  }, [mode, t.pages.appName, t.pages.newChat]);

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
      return feeds.flatMap((feed) =>
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
  }, [dailyFeed, dailyHistory, showDailyHistory, tab]);

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
    router.push(xingxiChatHref(value, mode));
  }

  function togglePreference(value: string) {
    setPreferences((current) =>
      current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value],
    );
  }

  return (
    <main className="size-full overflow-y-auto bg-[#edf4f5] text-[#20282b]">
      <BusinessMobileHeader title="文史检索" />

      <section className="min-h-full px-4 py-9 sm:px-7 lg:px-10 lg:py-12">
        <div className="mx-auto max-w-6xl">
          <div className="mx-auto max-w-4xl text-center">
            <div className="mb-3 flex flex-wrap items-center justify-center gap-2">
              <p className="text-xs font-medium text-[#247f8c]">
                吴文化 · 木渎地域文史
              </p>
            </div>
            <h1 className="text-2xl font-semibold text-[#202b2e] sm:text-4xl">
              今天想查阅哪一段木渎历史？
            </h1>

            <form
              className="mt-8 rounded-md border border-[#cbd9db] bg-white p-3 text-left shadow-[0_16px_38px_rgba(31,72,78,0.07)] sm:p-4"
              onSubmit={(event) => {
                event.preventDefault();
                submitResearch();
              }}
            >
              <textarea
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    submitResearch();
                  }
                }}
                aria-label="研究问题"
                placeholder="例如：乾隆为什么多次到木渎？"
                className="min-h-28 w-full resize-none bg-transparent px-1 py-1 text-sm leading-6 outline-none placeholder:text-[#8b999d] sm:min-h-32 sm:text-base"
              />
              <div className="flex flex-wrap items-center gap-2">
                <span className="flex h-9 items-center gap-1.5 px-2 text-xs font-medium text-[#40575d] sm:text-sm">
                  <Bot className="size-4 text-[#247f8c]" />
                  星羲
                </span>
                <span className="h-5 w-px bg-[#d6e1e2]" aria-hidden="true" />
                {XINGXI_ENTRY_MODES.map((item) => {
                  const Icon = modeIcons[item.id];
                  return (
                    <button
                      key={item.id}
                      type="button"
                      aria-pressed={mode === item.id}
                      onClick={() => {
                        setMode(item.id);
                        router.replace(xingxiWorkspaceHref(item.id), {
                          scroll: false,
                        });
                      }}
                      className={cn(
                        "flex h-9 items-center gap-1.5 rounded-full border px-3 text-xs transition-colors sm:text-sm",
                        mode === item.id
                          ? "border-[#70aeb7] bg-[#e5f1f2] text-[#175e68]"
                          : "border-[#dce5e6] text-[#607176] hover:bg-[#f3f7f7]",
                      )}
                    >
                      <Icon className="size-4" />
                      {item.label}
                    </button>
                  );
                })}
                <button
                  type="submit"
                  aria-label="开始研究"
                  disabled={!query.trim()}
                  className="ml-auto flex size-10 shrink-0 items-center justify-center rounded-full bg-[#20282b] text-white transition hover:bg-[#247f8c] disabled:cursor-not-allowed disabled:opacity-35"
                >
                  <ArrowUp className="size-5" />
                </button>
              </div>
            </form>
          </div>

          <div className="relative mt-9 flex flex-col gap-3 border-b border-[#cfdcde] pb-4 sm:flex-row sm:items-center sm:justify-between">
            <div
              className="flex w-fit rounded-md bg-[#dfe8ea] p-1"
              role="tablist"
              aria-label="研究动态"
            >
              {tabs.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  role="tab"
                  aria-selected={tab === item.id}
                  onClick={() => setTab(item.id)}
                  className={cn(
                    "h-8 rounded px-4 text-sm transition-colors",
                    tab === item.id
                      ? "bg-white font-medium text-[#176d79] shadow-sm"
                      : "text-[#64757a] hover:text-[#20282b]",
                  )}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <button
              type="button"
              aria-expanded={settingsOpen}
              onClick={() => setSettingsOpen((open) => !open)}
              className="flex h-9 w-fit items-center gap-2 rounded-full border border-[#8ebbc1] bg-[#e8f3f4] px-4 text-sm text-[#176d79] hover:bg-[#dcecee]"
            >
              <Settings2 className="size-4" />
              个性化设置
            </button>

            {settingsOpen && (
              <div className="absolute top-full right-0 z-10 mt-2 w-full max-w-sm rounded-md border border-[#ccdadd] bg-white p-4 shadow-lg">
                <p className="text-sm font-medium">关注的研究方向</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {["古迹", "方志", "人物", "园林", "水系"].map((item) => {
                    const active = preferences.includes(item);
                    return (
                      <button
                        key={item}
                        type="button"
                        aria-pressed={active}
                        onClick={() => togglePreference(item)}
                        className={cn(
                          "flex h-8 items-center gap-1 rounded border px-3 text-xs",
                          active
                            ? "border-[#70aeb7] bg-[#e5f1f2] text-[#175e68]"
                            : "border-[#dce5e6] text-[#607176]",
                        )}
                      >
                        {active && <Check className="size-3.5" />}
                        {item}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          <div className="space-y-4 py-5">
            {tab === "trends" &&
              dailyFeedLoading &&
              visibleItems.length === 0 && (
                <div
                  role="status"
                  aria-label="正在加载今日选题"
                  className="space-y-4"
                >
                  {[1, 2, 3, 4].map((item) => (
                    <div
                      key={item}
                      className="animate-pulse rounded-md border border-[#d2dfe1] bg-white p-5"
                    >
                      <div className="h-3 w-40 rounded bg-[#e4ecec]" />
                      <div className="mt-4 h-6 w-3/4 rounded bg-[#e4ecec]" />
                      <div className="mt-3 h-4 w-full rounded bg-[#edf2f2]" />
                      <div className="mt-2 h-4 w-2/3 rounded bg-[#edf2f2]" />
                    </div>
                  ))}
                </div>
              )}
            {tab === "trends" && dailyFeedError && visibleItems.length > 0 && (
              <div
                role="status"
                className="rounded-md border border-[#e2d9b8] bg-[#fffaf0] px-3 py-2 text-sm text-[#755f26]"
              >
                {dailyFeedError}
              </div>
            )}
            {tab === "trends" &&
              !dailyFeedLoading &&
              dailyFeedError &&
              visibleItems.length === 0 && (
                <div role="alert" className="py-10 text-center">
                  <p className="text-sm text-[#607176]">{dailyFeedError}</p>
                  <button
                    type="button"
                    onClick={() =>
                      setDailyFeedAttempt((attempt) => attempt + 1)
                    }
                    className="mt-3 h-9 rounded border border-[#8ebbc1] px-4 text-sm text-[#176d79] hover:bg-white"
                  >
                    重新加载
                  </button>
                </div>
              )}
            {tab === "trends" &&
              !dailyFeedLoading &&
              !dailyFeedError &&
              visibleItems.length === 0 && (
                <div role="status" className="py-10 text-center">
                  <p className="text-sm text-[#607176]">暂无今日选题</p>
                </div>
              )}
            {visibleItems.map((item) => (
              <article
                key={item.id}
                className="grid gap-5 rounded-md border border-[#d2dfe1] bg-white p-5 shadow-[0_8px_24px_rgba(44,76,82,0.04)] sm:grid-cols-[minmax(0,1fr)_138px]"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-[#66777b]">
                    <span>{item.date}</span>
                    <span>{item.source}</span>
                    {item.context && <span>{item.context}</span>}
                    <span className="rounded-full bg-[#e0eef0] px-2.5 py-1 text-[#176d79]">
                      {item.tag}
                    </span>
                    {item.sourceCount !== undefined && (
                      <span>资料依据 {item.sourceCount} 条</span>
                    )}
                  </div>
                  <Link
                    href={xingxiChatHref(
                      item.prompt ??
                        `请围绕“${item.title}”开展研究，并列出可核验的原始出处。`,
                      "ultra",
                      item.scope,
                    )}
                    className="mt-3 block text-lg leading-7 font-semibold hover:text-[#176d79] sm:text-xl"
                  >
                    {item.title}
                  </Link>
                  <p className="mt-2 max-w-4xl text-sm leading-6 text-[#4f6267] sm:text-[15px]">
                    {item.summary}
                  </p>
                  {item.sources?.length ? (
                    <p className="mt-2 text-xs leading-5 text-[#66777b]">
                      资料依据：
                      {item.sources.slice(0, 2).map((source, index) => (
                        <span key={source.evidence_id}>
                          {index > 0 ? "；" : ""}
                          <Link
                            href={`/workspace/library?evidence_id=${encodeURIComponent(source.evidence_id)}`}
                            className="underline decoration-[#9eb8bc] underline-offset-2 hover:text-[#176d79]"
                          >
                            {source.document_title}（{sourcePageLabel(source)}）
                          </Link>
                        </span>
                      ))}
                    </p>
                  ) : null}
                  <div className="mt-4 flex flex-wrap items-center gap-2">
                    <Link
                      href={xingxiChatHref(
                        item.prompt ??
                          `请介绍“${item.title}”，并引用本地资料。`,
                        "pro",
                        item.scope,
                      )}
                      className="inline-flex h-9 items-center rounded-md bg-[#1f696f] px-3 text-sm font-medium text-white hover:bg-[#18565c]"
                    >
                      开始了解
                    </Link>
                    <button
                      type="button"
                      aria-label={`推荐 ${item.title}`}
                      aria-pressed={votes[item.title] === "up"}
                      onClick={() =>
                        setVotes((current) => ({
                          ...current,
                          [item.title]: "up",
                        }))
                      }
                      className={cn(
                        "flex h-8 items-center gap-1.5 rounded-l-full border px-3 text-xs",
                        votes[item.title] === "up"
                          ? "border-[#70aeb7] bg-[#e5f1f2] text-[#175e68]"
                          : "border-[#d3dfe0] text-[#65767a] hover:bg-white",
                      )}
                    >
                      <ThumbsUp className="size-3.5" />
                      {item.count ?? "推荐"}
                    </button>
                    <button
                      type="button"
                      aria-label={`减少推荐 ${item.title}`}
                      aria-pressed={votes[item.title] === "down"}
                      onClick={() =>
                        setVotes((current) => ({
                          ...current,
                          [item.title]: "down",
                        }))
                      }
                      className={cn(
                        "flex size-8 items-center justify-center rounded-r-full border",
                        votes[item.title] === "down"
                          ? "border-[#70aeb7] bg-[#e5f1f2] text-[#175e68]"
                          : "border-[#d3dfe0] text-[#65767a] hover:bg-white",
                      )}
                    >
                      <ThumbsDown className="size-3.5" />
                    </button>
                  </div>
                </div>

                <Link
                  href={xingxiChatHref(
                    `查找“${item.title}”对应的原始文献和页码。`,
                    "ultra",
                    item.scope,
                  )}
                  aria-label={`查看 ${item.title} 的文献线索`}
                  className="hidden h-40 rounded-md border border-[#cbd8da] bg-[#fbfdfd] p-3 shadow-sm transition hover:border-[#70aeb7] sm:block"
                >
                  <div className="flex items-center justify-between border-b border-[#d9e2e3] pb-2 text-[9px] text-[#66777b]">
                    <FileText className="size-3.5" />
                    <span>文献摘录</span>
                  </div>
                  <div className="mt-3 space-y-2">
                    <div className="h-1.5 w-full bg-[#d6dfe0]" />
                    <div className="h-1.5 w-5/6 bg-[#d6dfe0]" />
                    <div className="h-1.5 w-full bg-[#e2e8e9]" />
                    <div className="h-1.5 w-3/4 bg-[#d6dfe0]" />
                    <div className="mt-3 grid grid-cols-3 gap-1">
                      <div className="h-10 bg-[#dbe9ea]" />
                      <div className="col-span-2 h-10 border border-[#dbe3e4]" />
                    </div>
                  </div>
                </Link>
              </article>
            ))}
            {tab === "trends" && showDailyHistory && dailyHistory && (
              <p className="pt-2 text-center text-xs text-[#75868a]">
                已显示今日全部 {dailyHistory.current.items.length} 条及最近
                {dailyHistory.history_days - 1} 天选题
              </p>
            )}
          </div>

          {tab === "trends" && !dailyFeedLoading && !dailyFeedError && (
            <div className="flex flex-col items-center py-5">
              {dailyHistoryError && (
                <p role="alert" className="mb-3 text-xs text-amber-800">
                  {dailyHistoryError}
                </p>
              )}
              <button
                type="button"
                onClick={() => void toggleDailyHistory()}
                disabled={dailyHistoryLoading}
                aria-expanded={showDailyHistory}
                className="flex h-10 items-center gap-2 rounded-md border border-[#c6d6d8] bg-white px-4 text-sm text-[#42676d] hover:border-[#86b2b8] hover:text-[#176d79] disabled:opacity-50"
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
              </button>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
