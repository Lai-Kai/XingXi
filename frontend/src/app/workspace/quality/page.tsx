"use client";

import { ClipboardList, ExternalLink, Search } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  Sheet,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import {
  WorkbenchMetrics,
  WorkbenchGuide,
} from "@/components/workspace/admin-workbench";
import {
  BusinessEmptyState,
  BusinessErrorState,
  BusinessLoadingState,
  BusinessMobileHeader,
  BusinessPageHeader,
} from "@/components/workspace/business-page";
import { BusinessSheetContent } from "@/components/workspace/business-surfaces";
import {
  listQualityFeedback,
  reviewQualityFeedback,
  type FeedbackCategory,
  type FeedbackData,
  type FeedbackStatus,
} from "@/core/api/feedback";
import { useAuth } from "@/core/auth/AuthProvider";
import { hasCapability } from "@/core/auth/permissions";
import { useIsMobile } from "@/hooks/use-mobile";

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
  const mobile = useIsMobile();
  const [detailOpen, setDetailOpen] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);

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

  const detail = (
    <>
      {selected ? (
        <div className="grid gap-4">
          <div>
            <p className="text-muted-foreground text-xs">反馈内容</p>
            <p className="mt-1 text-sm leading-6">
              {selected.comment ?? "未填写说明"}
            </p>
          </div>
          <dl className="bg-muted/40 rounded-lg border p-3 text-xs">
            <dt className="text-muted-foreground">关联运行</dt>
            <dd className="mt-1 font-mono break-all">
              {selected.run_id ?? "未记录"}
            </dd>
          </dl>
          {actionError && (
            <p role="alert" className="text-destructive text-sm">
              {actionError}
            </p>
          )}
          {selected.thread_id && (
            <Link
              href={`/workspace/chats/${selected.thread_id}`}
              className="text-primary flex items-center gap-1 text-sm hover:underline"
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
                    setReviewStatus(event.target.value as FeedbackStatus)
                  }
                  className="h-10 rounded-md border px-3"
                >
                  {Object.entries(statusLabels).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="grid gap-2 text-sm">
                <span>处理意见</span>
                <textarea
                  value={reviewNote}
                  onChange={(event) => setReviewNote(event.target.value)}
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
                  setActionError(null);
                  try {
                    const updated = await reviewQualityFeedback(
                      selected.feedback_id,
                      reviewStatus,
                      reviewNote.trim(),
                    );
                    setSelected(updated);
                    await load();
                  } catch (saveError) {
                    setActionError(
                      saveError instanceof Error
                        ? saveError.message
                        : "无法保存处理结果",
                    );
                  } finally {
                    setSaving(false);
                  }
                }}
                className="bg-primary text-primary-foreground h-10 rounded-md px-4 text-sm disabled:opacity-40"
              >
                {saving ? "保存中…" : "保存处理结果"}
              </button>
            </>
          ) : (
            <div className="border-border grid gap-3 border-t pt-4 text-sm">
              <div>
                <p className="text-muted-foreground text-xs">处理状态</p>
                <p className="mt-1">
                  {statusLabels[selected.status ?? "submitted"]}
                </p>
              </div>
              {selected.review_note && (
                <div>
                  <p className="text-muted-foreground text-xs">处理意见</p>
                  <p className="mt-1 leading-6">{selected.review_note}</p>
                </div>
              )}
            </div>
          )}
        </div>
      ) : (
        <p className="text-muted-foreground text-sm">
          选择一条反馈查看并处理。
        </p>
      )}
    </>
  );

  if (!allowed) {
    return (
      <main className="admin-workspace size-full overflow-y-auto">
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
    <main className="admin-workspace size-full overflow-y-auto">
      <BusinessMobileHeader title="质量中心" />
      <div className="admin-workbench mx-auto min-h-full max-w-7xl px-4 py-7 sm:px-8 lg:px-10 lg:py-10">
        <WorkbenchGuide
          title="质量复核"
          steps={["核对反馈", "回看原会话", "记录处理意见"]}
        />
        <BusinessPageHeader
          title="质量中心"
          description="处理用户对回答、引用和资料完整性的反馈"
          icon={ClipboardList}
        />

        <div className="my-6">
          <WorkbenchMetrics
            items={[
              {
                label: "匹配反馈",
                value: loading || error ? null : total,
                hint: "当前状态与搜索条件的服务端结果",
              },
              {
                label: "本页待处理",
                value:
                  loading || error
                    ? null
                    : items.filter(
                        (item) => (item.status ?? "submitted") === "submitted",
                      ).length,
                hint: "仅统计当前页",
              },
              {
                label: "本页复核中",
                value:
                  loading || error
                    ? null
                    : items.filter((item) => item.status === "reviewing")
                        .length,
                hint: "仅统计当前页",
              },
              {
                label: "本页已确认",
                value:
                  loading || error
                    ? null
                    : items.filter((item) => item.status === "accepted").length,
                hint: "仅统计当前页",
              },
            ]}
          />
        </div>
        <div className="border-border mt-5 flex flex-col gap-3 border-b pb-4 sm:flex-row">
          <label className="border-border bg-card flex h-10 min-w-0 flex-1 items-center gap-2 rounded-md border px-3">
            <Search className="text-muted-foreground size-4" />
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
            className="border-border bg-card h-10 rounded-md border px-3 text-sm"
          >
            <option value="all">全部状态</option>
            {Object.entries(statusLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>

        {loading && items.length === 0 ? (
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
          <div className="quality-workbench mt-5">
            <div
              className="border-border bg-card overflow-hidden rounded-xl border"
              aria-label="反馈队列"
            >
              {items.map((item) => (
                <div
                  key={item.feedback_id}
                  className="quality-record border-b text-sm last:border-b-0"
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
                    className="text-muted-foreground line-clamp-2"
                    data-quality-comment
                    title={item.comment ?? ""}
                  >
                    {item.comment ?? "未填写说明"}
                  </span>
                  <span className="text-muted-foreground text-xs">
                    {item.created_at
                      ? new Intl.DateTimeFormat("zh-CN", {
                          dateStyle: "short",
                          timeStyle: "short",
                        }).format(new Date(item.created_at))
                      : "-"}
                  </span>
                  <button
                    type="button"
                    onClick={(event) => {
                      triggerRef.current = event.currentTarget;
                      setDetailOpen(true);
                      setActionError(null);
                      setSelected(item);
                      setReviewStatus(item.status ?? "reviewing");
                      setReviewNote(item.review_note ?? "");
                    }}
                    className="admin-action"
                  >
                    {canReview ? "处理" : "查看"}
                  </button>
                </div>
              ))}
            </div>

            {!mobile && (
              <aside
                className="quality-inspector bg-card rounded-xl border p-5"
                aria-label="反馈核对与处理"
              >
                {detail}
              </aside>
            )}
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
      <Sheet open={mobile && detailOpen} onOpenChange={setDetailOpen}>
        <BusinessSheetContent
          side="bottom"
          className="admin-dialog max-h-[85dvh] overflow-y-auto rounded-t-xl p-5"
          onCloseAutoFocus={(event) => {
            if (triggerRef.current?.isConnected) {
              event.preventDefault();
              triggerRef.current.focus();
            }
          }}
        >
          <SheetHeader className="sr-only">
            <SheetTitle>反馈核对与处理</SheetTitle>
            <SheetDescription>核对原会话，记录处理意见。</SheetDescription>
          </SheetHeader>
          {detail}
        </BusinessSheetContent>
      </Sheet>
    </main>
  );
}
