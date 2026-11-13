"use client";

import {
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  CalendarDays,
  ChevronDown,
  ChevronUp,
  Compass,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { BusinessMobileHeader } from "@/components/workspace/business-page";
import {
  HomeEvidencePreview,
  HomeEvidenceSheet,
} from "@/components/workspace/home/evidence-preview";
import { HomeResearchComposer } from "@/components/workspace/home/research-composer";
import {
  documentLeads,
  homeTopics,
  sourcePageLabel,
  topicCollections,
  type HomeSource,
} from "@/core/home/model";
import { useI18n } from "@/core/i18n/hooks";
import {
  type DailyResearchHistory,
  type DailyResearchFeed,
  fetchDailyResearchHistory,
  fetchDailyResearchFeed,
  readCachedDailyResearchFeed,
} from "@/core/research-feed/api";
import { buildLocalFallbackDailyResearchFeed } from "@/core/research-feed/fallback";
import { xingxiChatHref } from "@/core/threads/xingxi-entry";
import { publicErrorMessage } from "@/core/ui/presentation";
import { cn } from "@/lib/utils";

const tabs = [
  { id: "trends", label: "今日选题" },
  { id: "documents", label: "文献线索" },
  { id: "collections", label: "专题阅读" },
] as const;
type FeedTab = (typeof tabs)[number]["id"];

export default function XingxiHomePage() {
  const { t } = useI18n();
  const historyRequest = useRef<AbortController | null>(null);
  const [tab, setTab] = useState<FeedTab>("trends");
  const [selectedSource, setSelectedSource] = useState<HomeSource | null>(null);
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
    document.title = `${t.pages.newChat} - ${t.pages.appName}`;
  }, [t.pages.appName, t.pages.newChat]);
  useEffect(() => () => historyRequest.current?.abort(), []);

  useEffect(() => {
    const controller = new AbortController();
    const cached = readCachedDailyResearchFeed();
    const fallback = cached?.items.length
      ? cached
      : buildLocalFallbackDailyResearchFeed();
    // Keep source-bound content available while the current feed refreshes.
    setDailyFeed(fallback);
    setDailyFeedLoading(true);
    setDailyFeedError(null);
    historyRequest.current?.abort();
    setDailyHistory(null);
    setShowDailyHistory(false);
    setDailyHistoryLoading(false);
    setDailyHistoryError(null);
    void fetchDailyResearchFeed(controller.signal)
      .then((feed) => {
        if (!controller.signal.aborted)
          setDailyFeed(feed.items.length ? feed : fallback);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted && !fallback.items.length)
          setDailyFeedError(
            publicErrorMessage(error, "今日选题暂时无法加载，请稍后重试"),
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setDailyFeedLoading(false);
      });
    return () => controller.abort();
  }, [dailyFeedAttempt]);

  useEffect(() => {
    if (!dailyFeed) return;
    const delay = Math.max(
      1_000,
      Date.parse(dailyFeed.next_refresh_at) - Date.now(),
    );
    const timer = window.setTimeout(
      () => setDailyFeedAttempt((attempt) => attempt + 1),
      Math.min(delay, 2_147_483_647),
    );
    return () => window.clearTimeout(timer);
  }, [dailyFeed]);

  const currentTopics = useMemo(
    () => homeTopics(dailyFeed ? [dailyFeed] : []),
    [dailyFeed],
  );
  const visibleTopics = useMemo(
    () =>
      showDailyHistory && dailyHistory
        ? homeTopics([dailyHistory.current, ...dailyHistory.previous])
        : currentTopics,
    [currentTopics, dailyHistory, showDailyHistory],
  );
  const documents = useMemo(
    () => documentLeads(currentTopics),
    [currentTopics],
  );
  const collections = useMemo(
    () => topicCollections(currentTopics),
    [currentTopics],
  );
  const firstSource = currentTopics[0]?.sources[0];

  async function toggleDailyHistory() {
    if (showDailyHistory) {
      setShowDailyHistory(false);
      return;
    }
    if (dailyHistory) {
      setShowDailyHistory(true);
      return;
    }
    const controller = new AbortController();
    historyRequest.current = controller;
    setDailyHistoryLoading(true);
    setDailyHistoryError(null);
    try {
      const history = await fetchDailyResearchHistory(7, controller.signal);
      if (controller.signal.aborted) return;
      setDailyHistory(history);
      setShowDailyHistory(true);
    } catch (reason) {
      if (!controller.signal.aborted)
        setDailyHistoryError(
          publicErrorMessage(reason, "往日选题暂时无法加载，请稍后重试"),
        );
    } finally {
      if (!controller.signal.aborted) setDailyHistoryLoading(false);
    }
  }

  return (
    <main className="xingxi-home size-full overflow-y-auto text-slate-800">
      <BusinessMobileHeader title="文史检索" />
      <div className="relative mx-auto max-w-[1120px] px-4 pb-12 sm:px-8 lg:px-12">
        <div className="flex items-center justify-between gap-4 pt-6 text-xs text-slate-500 sm:pt-7">
          <span className="flex items-center gap-2">
            <Compass className="size-4 text-blue-500" aria-hidden="true" />
            文史检索<span className="mx-1 text-slate-300">/</span>研究工作台
          </span>
          <Link
            href="/workspace/map"
            className="hidden items-center gap-1.5 transition-colors hover:text-blue-600 sm:flex"
          >
            古舆地图
            <ArrowUpRight className="size-3.5" aria-hidden="true" />
          </Link>
        </div>
        <section
          aria-labelledby="home-title"
          className="mx-auto max-w-[920px] pt-10 sm:pt-12"
        >
          <HomeResearchComposer />
          {firstSource && (
            <div className="mt-5">
              <HomeEvidencePreview
                source={firstSource}
                onOpen={setSelectedSource}
              />
            </div>
          )}
        </section>

        <section aria-label="文史阅读线索" className="mt-10 sm:mt-12">
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200/70">
            <div
              role="tablist"
              aria-label="研究动态"
              className="flex gap-5 sm:gap-7"
            >
              {tabs.map((item, index) => (
                <button
                  key={item.id}
                  id={`home-tab-${item.id}`}
                  type="button"
                  role="tab"
                  aria-selected={tab === item.id}
                  aria-controls="home-feed-panel"
                  tabIndex={tab === item.id ? 0 : -1}
                  onClick={() => setTab(item.id)}
                  onKeyDown={(event) => {
                    const nextIndex =
                      event.key === "ArrowRight"
                        ? (index + 1) % tabs.length
                        : event.key === "ArrowLeft"
                          ? (index + tabs.length - 1) % tabs.length
                          : event.key === "Home"
                            ? 0
                            : event.key === "End"
                              ? tabs.length - 1
                              : null;
                    if (nextIndex === null) return;
                    event.preventDefault();
                    const next = tabs[nextIndex]!;
                    setTab(next.id);
                    document.getElementById(`home-tab-${next.id}`)?.focus();
                  }}
                  className={cn(
                    "relative pb-3 text-sm transition-colors after:absolute after:inset-x-0 after:bottom-[-1px] after:h-0.5 after:rounded-full",
                    tab === item.id
                      ? "font-semibold text-blue-700 after:bg-blue-600"
                      : "text-slate-500 hover:text-slate-800",
                  )}
                >
                  {item.label}
                </button>
              ))}
            </div>
            {dailyFeed && (
              <span className="mb-3 flex items-center gap-1.5 text-[11px] text-slate-500">
                <CalendarDays className="size-3.5" aria-hidden="true" />
                <time dateTime={dailyFeed.generated_for}>
                  {dailyFeed.generated_for}
                </time>
              </span>
            )}
          </div>
          <div
            id="home-feed-panel"
            role="tabpanel"
            aria-labelledby={`home-tab-${tab}`}
            className="py-5"
          >
            {dailyFeedLoading && !currentTopics.length && (
              <div
                role="status"
                aria-label="正在加载今日选题"
                className="grid gap-4 sm:grid-cols-2"
              >
                {[1, 2].map((id) => (
                  <div
                    key={id}
                    className="xingxi-panel bg-card/60 h-48 animate-pulse rounded-2xl border border-white"
                  />
                ))}
              </div>
            )}
            {!dailyFeedLoading && !currentTopics.length && (
              <div
                role={dailyFeedError ? "alert" : "status"}
                className="py-12 text-center text-sm text-slate-500"
              >
                <p>{dailyFeedError ?? "暂无可用的文献线索"}</p>
                <button
                  type="button"
                  onClick={() => setDailyFeedAttempt((attempt) => attempt + 1)}
                  className="mt-3 rounded-lg border border-blue-200 px-4 py-2 text-blue-700"
                >
                  重新加载
                </button>
              </div>
            )}

            {tab === "trends" && (
              <div className="grid gap-4 lg:grid-cols-2">
                {visibleTopics.map((item) => (
                  <article
                    key={item.id}
                    className="xingxi-panel home-feed-card bg-card/70 hover:bg-card/95 flex min-w-0 flex-col rounded-2xl border border-white/90 p-5 shadow-[0_4px_20px_rgb(30,64,120,0.025)] transition-colors"
                  >
                    <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                      <span className="rounded-md bg-blue-50 px-2 py-1 font-medium text-blue-700">
                        {item.tag}
                      </span>
                      <span>
                        {[item.time_label, item.place]
                          .filter(Boolean)
                          .join(" · ")}
                      </span>
                      {showDailyHistory && (
                        <time dateTime={item.date} className="ml-auto">
                          {item.date}
                        </time>
                      )}
                    </div>
                    <h2 className="mt-3 text-base leading-7 font-semibold text-slate-800">
                      <Link
                        href={xingxiChatHref(item.prompt, item.scope)}
                        className="transition-colors hover:text-blue-700"
                      >
                        {item.title}
                      </Link>
                    </h2>
                    <p className="mt-2 text-[13px] leading-6 text-slate-500">
                      {item.summary}
                    </p>
                    <div className="mt-4 flex flex-wrap gap-x-2 gap-y-1 text-[11px] leading-5 text-slate-500">
                      <span>资料依据：</span>
                      {item.sources.slice(0, 2).map((source) => (
                        <button
                          key={source.evidence_id}
                          type="button"
                          onClick={() => setSelectedSource(source)}
                          className="text-left underline decoration-slate-300 underline-offset-4 transition-colors hover:text-blue-700"
                        >
                          {source.document_title}（{sourcePageLabel(source)}）
                        </button>
                      ))}
                    </div>
                    <div className="mt-auto flex items-center justify-between gap-3 pt-5">
                      <span className="text-[11px] text-slate-500">
                        资料依据 {item.sources.length} 条
                      </span>
                      <Link
                        href={xingxiChatHref(item.prompt, item.scope)}
                        className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium text-blue-700 transition-colors hover:bg-blue-50"
                      >
                        开始了解
                        <ArrowRight className="size-3.5" aria-hidden="true" />
                      </Link>
                    </div>
                  </article>
                ))}
              </div>
            )}

            {tab === "documents" && (
              <div className="grid gap-4 sm:grid-cols-2">
                {documents.map((document) => (
                  <article
                    key={document.id}
                    className="xingxi-panel bg-card/75 rounded-2xl border border-white/90 p-5 shadow-sm"
                  >
                    <span className="inline-flex size-9 items-center justify-center rounded-xl border border-violet-100 bg-violet-50 text-violet-600">
                      <BookOpen className="size-4" aria-hidden="true" />
                    </span>
                    <h2 className="mt-3 text-base font-semibold">
                      {document.title}
                    </h2>
                    <p className="mt-1 text-xs text-slate-500">
                      本页选题引用的 {document.sources.length} 条文献线索
                    </p>
                    <div className="mt-4 flex flex-wrap gap-2">
                      {document.sources.map((source) => (
                        <button
                          key={source.evidence_id}
                          type="button"
                          onClick={() => setSelectedSource(source)}
                          className="rounded-lg border border-violet-100 bg-violet-50/50 px-3 py-2 text-xs text-violet-700 transition-colors hover:bg-violet-100"
                        >
                          {sourcePageLabel(source)} · 查看原文
                        </button>
                      ))}
                    </div>
                  </article>
                ))}
              </div>
            )}

            {tab === "collections" && (
              <div className="grid gap-4 sm:grid-cols-2">
                {collections.map((collection) => (
                  <article
                    key={collection.title}
                    className="xingxi-panel bg-card/75 rounded-2xl border border-white/90 p-5 shadow-sm"
                  >
                    <h2 className="flex items-center gap-2.5 text-sm font-semibold">
                      <span
                        className="size-2 rounded-full bg-sky-400"
                        aria-hidden="true"
                      />
                      {collection.title}
                    </h2>
                    <ul className="mt-3 divide-y divide-slate-100">
                      {collection.items.map((item) => (
                        <li key={item.id}>
                          <Link
                            href={xingxiChatHref(item.prompt, item.scope)}
                            className="group flex items-start justify-between gap-4 py-3 text-sm leading-6 text-slate-600 transition-colors hover:text-blue-700"
                          >
                            <span>{item.title}</span>
                            <ArrowUpRight
                              className="mt-1 size-4 shrink-0 text-slate-400 group-hover:text-blue-600"
                              aria-hidden="true"
                            />
                          </Link>
                        </li>
                      ))}
                    </ul>
                  </article>
                ))}
              </div>
            )}
          </div>

          {tab === "trends" && currentTopics.length > 0 && (
            <div className="flex flex-col items-center pt-3">
              {showDailyHistory && dailyHistory && (
                <p className="mb-4 text-xs text-slate-500">
                  已显示今日全部 {dailyHistory.current.items.length} 条及最近{" "}
                  {dailyHistory.history_days - 1} 天选题
                </p>
              )}
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
                className="bg-card/65 hover:bg-card inline-flex min-h-10 items-center gap-2 rounded-xl border border-slate-200/80 px-4 text-xs text-slate-500 transition-all hover:border-blue-200 hover:text-blue-700 disabled:opacity-50"
              >
                <CalendarDays className="size-3.5" aria-hidden="true" />
                {dailyHistoryLoading
                  ? "正在加载更多选题…"
                  : showDailyHistory
                    ? "收起更多选题"
                    : "查看更多今日与往日选题"}
                {showDailyHistory ? (
                  <ChevronUp className="size-3.5" aria-hidden="true" />
                ) : (
                  <ChevronDown className="size-3.5" aria-hidden="true" />
                )}
              </button>
            </div>
          )}
        </section>
        <footer className="mt-12 border-t border-slate-200/60 pt-5 text-center text-[11px] text-slate-500">
          星羲弦沚<span className="mx-2 text-slate-300">·</span>吴文化文史知识库
        </footer>
      </div>
      <HomeEvidenceSheet
        source={selectedSource}
        onClose={() => setSelectedSource(null)}
      />
    </main>
  );
}
