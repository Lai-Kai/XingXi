"use client";

import { ClipboardList, ExternalLink, Search } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  BusinessEmptyState,
  BusinessErrorState,
  BusinessLoadingState,
  BusinessMobileHeader,
  BusinessPageHeader,
} from "@/components/workspace/business-page";
import {
  listQualityFeedback,
  reviewQualityFeedback,
  type FeedbackCategory,
  type FeedbackData,
  type FeedbackStatus,
} from "@/core/api/feedback";
import { useAuth } from "@/core/auth/AuthProvider";
import { hasCapability } from "@/core/auth/permissions";

const categoryLabels: Record<FeedbackCategory, string> = {
  citation_error: "引用错误",
  factual_error: "事实错误",
  missing_source: "资料缺失",
  expression_issue: "表达问题",
  other: "其他问题",
};

const statusLabels: Record<FeedbackStatus, string> = {
  submitted: "待处理",
  reviewing: "复核中",
  accepted: "已确认",
  rejected: "不采纳",
};

export default function QualityPage() {
  const { user } = useAuth();
  const allowed = hasCapability(user, "quality:read");
  const canReview = hasCapability(user, "quality:review");
  const [items, setItems] = useState<FeedbackData[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<FeedbackStatus | "all">("submitted");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<FeedbackData | null>(null);
  const [reviewStatus, setReviewStatus] = useState<FeedbackStatus>("reviewing");
  const [reviewNote, setReviewNote] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pageSize = 20;

  const load = useCallback(async () => {
    if (!allowed) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await listQualityFeedback({
        status,
        query,
        page,
        pageSize,
      });
      setItems(result.items);
      setTotal(result.total);
    } catch (loadError) {
      setError(
        loadError instanceof Error ? loadError.message : "无法读取反馈队列",
      );
    } finally {
      setLoading(false);
    }
  }, [allowed, page, query, status]);

  useEffect(() => void load(), [load]);

  if (!allowed) {
    return (
      <main className="size-full overflow-y-auto bg-[#f7fafb]">
        <div className="mx-auto max-w-7xl px-4 py-8 sm:px-8">
          <BusinessEmptyState
            icon={ClipboardList}
            title="无质量治理权限"
            description="当前账号不能查看其他用户提交的反馈。"
          />
        </div>
      </main>
    );
  }

  return (
    <main className="size-full overflow-y-auto bg-[#f7fafb] text-[#202b2e]">
      <BusinessMobileHeader title="质量中心" />
      <div className="mx-auto min-h-full max-w-7xl px-4 py-7 sm:px-8 lg:px-10 lg:py-10">
        <BusinessPageHeader
          title="质量中心"
          description="处理用户对回答、引用和资料完整性的反馈"
          icon={ClipboardList}
        />

        <div className="mt-5 flex flex-col gap-3 border-b border-[#d7e1e2] pb-4 sm:flex-row">
          <label className="flex h-10 min-w-0 flex-1 items-center gap-2 rounded-md border border-[#d2dddf] bg-white px-3">
            <Search className="size-4 text-[#68797e]" />
            <input
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setPage(1);
              }}
              placeholder="搜索反馈内容、会话或运行编号"
              className="min-w-0 flex-1 bg-transparent text-sm outline-none"
            />
          </label>
          <select
            value={status}
            onChange={(event) => {
              setStatus(event.target.value as FeedbackStatus | "all");
              setPage(1);
            }}
            aria-label="处理状态"
            className="h-10 rounded-md border border-[#d2dddf] bg-white px-3 text-sm"
          >
            <option value="all">全部状态</option>
            {Object.entries(statusLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>

        {loading ? (
          <BusinessLoadingState label="正在读取反馈…" />
        ) : error ? (
          <BusinessErrorState description={error} onRetry={() => void load()} />
        ) : items.length === 0 ? (
          <BusinessEmptyState
            icon={ClipboardList}
            title="当前没有反馈"
            description="新的用户反馈会出现在这里。"
          />
        ) : (
          <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
            <div className="overflow-x-auto rounded-md border border-[#d7e1e2] bg-white">
              <div className="grid min-w-[720px] grid-cols-[110px_110px_minmax(240px,1fr)_150px_80px] gap-3 border-b bg-[#f1f6f7] px-4 py-3 text-xs font-medium text-[#607176]">
                <span>问题类型</span>
                <span>状态</span>
                <span>反馈内容</span>
                <span>提交时间</span>
                <span>操作</span>
              </div>
              {items.map((item) => (
                <div
                  key={item.feedback_id}
                  className="grid min-w-[720px] grid-cols-[110px_110px_minmax(240px,1fr)_150px_80px] items-center gap-3 border-b px-4 py-3 text-sm last:border-b-0"
                >
                  <span>
                    {item.category
                      ? categoryLabels[item.category]
                      : item.rating > 0
                        ? "有帮助"
                        : "未分类"}
                  </span>
                  <span>{statusLabels[item.status ?? "submitted"]}</span>
                  <span
                    className="truncate text-[#526469]"
                    title={item.comment ?? ""}
                  >
                    {item.comment ?? "未填写说明"}
                  </span>
                  <span className="text-xs text-[#718186]">
                    {item.created_at
                      ? new Intl.DateTimeFormat("zh-CN", {
                          dateStyle: "short",
                          timeStyle: "short",
                        }).format(new Date(item.created_at))
                      : "-"}
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      setSelected(item);
                      setReviewStatus(item.status ?? "reviewing");
                      setReviewNote(item.review_note ?? "");
                    }}
                    className="text-[#276f79] hover:underline"
                  >
                    {canReview ? "处理" : "查看"}
                  </button>
                </div>
              ))}
            </div>

            <aside className="border-l border-[#d7e1e2] bg-white p-4 lg:min-h-[420px]">
              {selected ? (
                <div className="grid gap-4">
                  <div>
                    <p className="text-xs text-[#718186]">反馈内容</p>
                    <p className="mt-1 text-sm leading-6">
                      {selected.comment ?? "未填写说明"}
                    </p>
                  </div>
                  {selected.thread_id && (
                    <Link
                      href={`/workspace/chats/${selected.thread_id}`}
                      className="flex items-center gap-1 text-sm text-[#276f79] hover:underline"
                    >
                      打开原会话 <ExternalLink className="size-3.5" />
                    </Link>
                  )}
                  {canReview ? (
                    <>
                      <label className="grid gap-2 text-sm">
                        <span>处理状态</span>
                        <select
                          value={reviewStatus}
                          onChange={(event) =>
                            setReviewStatus(
                              event.target.value as FeedbackStatus,
                            )
                          }
                          className="h-10 rounded-md border px-3"
                        >
                          {Object.entries(statusLabels).map(
                            ([value, label]) => (
                              <option key={value} value={value}>
                                {label}
                              </option>
                            ),
                          )}
                        </select>
                      </label>
                      <label className="grid gap-2 text-sm">
                        <span>处理意见</span>
                        <textarea
                          value={reviewNote}
                          onChange={(event) =>
                            setReviewNote(event.target.value)
                          }
                          rows={5}
                          className="resize-none rounded-md border px-3 py-2"
                          placeholder="记录核对结果或后续处理要求"
                        />
                      </label>
                      <button
                        type="button"
                        disabled={saving}
                        onClick={async () => {
                          setSaving(true);
                          setError(null);
                          try {
                            const updated = await reviewQualityFeedback(
                              selected.feedback_id,
                              reviewStatus,
                              reviewNote.trim(),
                            );
                            setSelected(updated);
                            await load();
                          } catch (saveError) {
                            setError(
                              saveError instanceof Error
                                ? saveError.message
                                : "无法保存处理结果",
                            );
                          } finally {
                            setSaving(false);
                          }
                        }}
                        className="h-10 rounded-md bg-[#276f79] px-4 text-sm text-white disabled:opacity-40"
                      >
                        {saving ? "保存中…" : "保存处理结果"}
                      </button>
                    </>
                  ) : (
                    <div className="grid gap-3 border-t border-[#d7e1e2] pt-4 text-sm">
                      <div>
                        <p className="text-xs text-[#718186]">处理状态</p>
                        <p className="mt-1">
                          {statusLabels[selected.status ?? "submitted"]}
                        </p>
                      </div>
                      {selected.review_note && (
                        <div>
                          <p className="text-xs text-[#718186]">处理意见</p>
                          <p className="mt-1 leading-6">
                            {selected.review_note}
                          </p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-sm text-[#718186]">
                  选择一条反馈查看并处理。
                </p>
              )}
            </aside>
          </div>
        )}

        {total > pageSize && (
          <div className="mt-4 flex items-center justify-end gap-3 text-sm">
            <span>
              第 {page} / {Math.ceil(total / pageSize)} 页
            </span>
            <button
              type="button"
              disabled={page === 1}
              onClick={() => setPage((value) => value - 1)}
              className="h-8 rounded border px-3 disabled:opacity-40"
            >
              上一页
            </button>
            <button
              type="button"
              disabled={page * pageSize >= total}
              onClick={() => setPage((value) => value + 1)}
              className="h-8 rounded border px-3 disabled:opacity-40"
            >
              下一页
            </button>
          </div>
        )}
      </div>
    </main>
  );
}
