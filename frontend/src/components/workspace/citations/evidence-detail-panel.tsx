"use client";

import { BookMarked, ExternalLink, Loader2, X } from "lucide-react";
import { useEffect, useState } from "react";

import { getEvidenceDetail } from "@/core/knowledge-search/api";
import type { EvidenceDetail } from "@/core/knowledge-search/types";
import { sourceFileContentUrl } from "@/core/source-files/api";
import { cn } from "@/lib/utils";

export function EvidenceDetailPanel({
  evidenceId,
  onClose,
  className,
}: {
  evidenceId: string;
  onClose: () => void;
  className?: string;
}) {
  const [detail, setDetail] = useState<EvidenceDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setDetail(null);
    void getEvidenceDetail(evidenceId, controller.signal)
      .then((payload) => {
        setDetail(payload);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setError(err instanceof Error ? err.message : "资料出处详情加载失败");
        setLoading(false);
      });
    return () => controller.abort();
  }, [evidenceId]);

  return (
    <aside
      className={cn(
        "border-border/70 bg-background fixed inset-x-0 bottom-0 z-40 max-h-[70vh] overflow-y-auto rounded-t-xl border shadow-2xl sm:inset-x-auto sm:right-4 sm:bottom-4 sm:max-h-[80vh] sm:w-[420px] sm:rounded-xl",
        className,
      )}
      data-evidence-detail-id={evidenceId}
      aria-label="资料出处详情"
    >
      <div className="border-border/60 flex items-center justify-between border-b px-4 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <BookMarked className="text-primary size-4 shrink-0" />
          <h2 className="truncate text-sm font-semibold">资料出处详情</h2>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="text-muted-foreground hover:bg-muted rounded p-1"
          aria-label="关闭资料出处详情"
        >
          <X className="size-4" />
        </button>
      </div>

      <div className="space-y-3 px-4 py-4 text-sm">
        <div className="text-muted-foreground text-xs break-all">
          出处编号：{evidenceId}
        </div>
        {loading && (
          <div className="text-muted-foreground flex items-center gap-2 py-8">
            <Loader2 className="size-4 animate-spin" />
            正在加载资料出处详情…
          </div>
        )}
        {error && (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-3 text-amber-900">
            <p className="font-medium">暂无法打开该资料出处详情</p>
            <p className="mt-1 text-xs leading-5">{error}</p>
            <p className="mt-2 text-xs leading-5">
              引用协议仍有效：`evidence://{evidenceId}
              `。请确认该资料出处已发布到当前知识版本。
            </p>
          </div>
        )}
        {detail && (
          <>
            <div>
              <div className="text-muted-foreground text-xs">书名</div>
              <div className="font-medium">{detail.document_title}</div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <div className="text-muted-foreground text-xs">版本</div>
                <div>{detail.edition ?? "—"}</div>
              </div>
              <div>
                <div className="text-muted-foreground text-xs">卷目</div>
                <div>{detail.volume ?? "—"}</div>
              </div>
              <div>
                <div className="text-muted-foreground text-xs">页码</div>
                <div>
                  {detail.page_start === detail.page_end
                    ? detail.page_start
                    : `${detail.page_start}-${detail.page_end}`}
                </div>
              </div>
              <div>
                <div className="text-muted-foreground text-xs">叶码</div>
                <div>
                  {detail.folio_start
                    ? detail.folio_start === detail.folio_end ||
                      !detail.folio_end
                      ? detail.folio_start
                      : `${detail.folio_start}-${detail.folio_end}`
                    : "—"}
                </div>
              </div>
              <div>
                <div className="text-muted-foreground text-xs">等级 / 复核</div>
                <div>
                  {detail.source_level} / {detail.review_status}
                </div>
              </div>
            </div>
            {detail.section && (
              <div>
                <div className="text-muted-foreground text-xs">章节</div>
                <div>{detail.section}</div>
              </div>
            )}
            <div>
              <div className="text-muted-foreground text-xs">原文</div>
              <blockquote className="bg-muted/40 mt-1 rounded-md border px-3 py-2 leading-6 whitespace-pre-wrap">
                {detail.quote}
              </blockquote>
            </div>
            {detail.source_file_id && (
              <a
                href={sourceFileContentUrl(
                  detail.document_id,
                  detail.source_file_id,
                )}
                target="_blank"
                rel="noreferrer"
                className="text-primary flex w-fit items-center gap-1.5 text-sm hover:underline"
              >
                <ExternalLink className="size-4" />
                打开原件
              </a>
            )}
          </>
        )}
      </div>
    </aside>
  );
}
