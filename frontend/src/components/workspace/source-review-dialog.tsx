"use client";

import {
  AlertTriangle,
  Check,
  ClipboardCheck,
  ExternalLink,
  LoaderCircle,
  RotateCcw,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  finalizeReview,
  getReviewQueue,
  listReviewHistory,
  listSourceChunkSets,
  sourceFileContentUrl,
  submitReviewDecisions,
  type ReviewDecision,
  type ReviewQueue,
  type ReviewRecord,
  type ReviewStatus,
  type SourceChunkSet,
} from "@/core/source-files/api";

import { businessToneClasses } from "./business-controls";
import { SourceFacsimile } from "./source-facsimile";

type SourceReviewDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  documentId: string;
  fileId: string;
  title: string;
  fileType?: string;
  ingestionJobId?: string;
  onFinalized?: () => void;
};

const statusText: Record<ReviewStatus, string> = {
  pending: "待复核",
  reviewed: "已通过",
  rejected: "已退回",
  disputed: "有争议",
};

const statusClass: Record<ReviewStatus, string> = {
  pending: businessToneClasses.neutral,
  reviewed: businessToneClasses.success,
  rejected: businessToneClasses.danger,
  disputed: businessToneClasses.warning,
};

export function SourceReviewDialog({
  open,
  onOpenChange,
  documentId,
  fileId,
  title,
  fileType,
  ingestionJobId,
  onFinalized,
}: SourceReviewDialogProps) {
  const [versions, setVersions] = useState<SourceChunkSet[]>([]);
  const [chunkSetId, setChunkSetId] = useState("");
  const [queue, setQueue] = useState<ReviewQueue | null>(null);
  const [mode, setMode] = useState<"page" | "chunk">("page");
  const [activeId, setActiveId] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [comment, setComment] = useState("");
  const [history, setHistory] = useState<ReviewRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [leftView, setLeftView] = useState<"text" | "facsimile">("text");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!open) return;
    let active = true;
    setLoading(true);
    setError("");
    void listSourceChunkSets(documentId, fileId)
      .then(async (items) => {
        if (!active) return;
        setVersions(items);
        const latest = items.at(-1);
        if (!latest) {
          setQueue(null);
          setChunkSetId("");
          return;
        }
        setChunkSetId(latest.id);
        const nextQueue = await getReviewQueue(documentId, fileId, latest.id);
        if (active) setQueue(nextQueue);
      })
      .catch((reason: unknown) => {
        if (active)
          setError(
            reason instanceof Error ? reason.message : "无法读取复核资料",
          );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [documentId, fileId, open, attempt]);

  const targets = useMemo(
    () => (mode === "page" ? (queue?.pages ?? []) : (queue?.chunks ?? [])),
    [mode, queue],
  );
  const activeTarget = targets.find((target) => target.id === activeId);

  useEffect(() => {
    const firstId = targets[0]?.id ?? "";
    if (!targets.some((target) => target.id === activeId)) setActiveId(firstId);
    setSelected([]);
  }, [activeId, targets]);

  useEffect(() => {
    if (!open || !activeId) {
      setHistory([]);
      return;
    }
    let active = true;
    void listReviewHistory(documentId, fileId, mode, activeId)
      .then((records) => {
        if (active) setHistory(records);
      })
      .catch(() => {
        if (active) setHistory([]);
      });
    return () => {
      active = false;
    };
  }, [activeId, documentId, fileId, mode, open, queue]);

  async function changeVersion(nextId: string) {
    setChunkSetId(nextId);
    setLoading(true);
    setError("");
    try {
      setQueue(await getReviewQueue(documentId, fileId, nextId));
      setActiveId("");
      setSelected([]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法读取复核队列");
    } finally {
      setLoading(false);
    }
  }

  async function applyDecision(decision: ReviewDecision["decision"]) {
    const targetIds =
      selected.length > 0 ? selected : activeId ? [activeId] : [];
    if (targetIds.length === 0) return;
    if (
      (decision === "rejected" || decision === "disputed") &&
      !comment.trim()
    ) {
      setError("退回或标记争议时必须填写复核意见");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await submitReviewDecisions(
        documentId,
        fileId,
        targetIds.map((targetId) => ({
          target_type: mode,
          target_id: targetId,
          decision,
          ...(comment.trim() ? { comment: comment.trim() } : {}),
        })),
      );
      setQueue(await getReviewQueue(documentId, fileId, chunkSetId));
      setSelected([]);
      setComment("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法提交复核结论");
    } finally {
      setSaving(false);
    }
  }

  async function finalize() {
    if (!ingestionJobId || !chunkSetId) return;
    setSaving(true);
    setError("");
    try {
      await finalizeReview(documentId, fileId, chunkSetId, ingestionJobId);
      onFinalized?.();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "复核门禁尚未通过");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="admin-dialog review-workbench flex max-h-[92vh] w-[calc(100vw-1.5rem)] max-w-6xl flex-col overflow-hidden p-0">
        <DialogHeader className="border-border border-b px-5 py-4 pr-12">
          <DialogTitle className="flex items-center gap-2 text-base">
            <ClipboardCheck className="text-primary size-4" />
            文本人工复核
          </DialogTitle>
          <DialogDescription className="truncate">{title}</DialogDescription>
        </DialogHeader>

        <div className="border-border flex flex-wrap items-center gap-3 border-b px-5 py-3">
          <div className="border-border bg-card flex rounded-md border p-0.5">
            {(["page", "chunk"] as const).map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={mode === value}
                onClick={() => setMode(value)}
                className={`h-8 rounded px-3 text-sm ${mode === value ? "bg-card text-primary shadow-sm" : "text-muted-foreground"}`}
              >
                {value === "page" ? "按页复核" : "按片段复核"}
              </button>
            ))}
          </div>
          <select
            value={chunkSetId}
            onChange={(event) => void changeVersion(event.target.value)}
            disabled={loading || versions.length === 0}
            className="border-border bg-card h-9 rounded-md border px-3 text-sm"
          >
            {versions.length === 0 && <option value="">暂无切分版本</option>}
            {versions.map((version) => (
              <option key={version.id} value={version.id}>
                {version.policy.split_version}
              </option>
            ))}
          </select>
          <span className="text-muted-foreground text-xs">
            已选 {selected.length} 项
          </span>
          <a
            href={sourceFileContentUrl(documentId, fileId)}
            target="_blank"
            rel="noreferrer"
            className="border-border text-primary hover:bg-secondary flex h-9 items-center gap-2 rounded-md border px-3 text-sm"
          >
            <ExternalLink className="size-4" />
            打开原件
          </a>
          <button
            type="button"
            disabled={!ingestionJobId || !queue || saving}
            onClick={() => void finalize()}
            className="bg-primary text-primary-foreground ml-auto flex h-9 items-center gap-2 rounded-md px-3 text-sm disabled:opacity-40"
          >
            <Check className="size-4" />
            完成复核
          </button>
        </div>

        {error && (
          <div
            role="alert"
            className="border-border bg-card text-heritage-rejected-foreground border-b px-5 py-2 text-sm"
          >
            {error}
            <button
              type="button"
              className="ml-3 underline"
              onClick={() => setAttempt((value) => value + 1)}
            >
              重新读取
            </button>
          </div>
        )}

        {loading ? (
          <div className="text-muted-foreground flex min-h-96 items-center justify-center text-sm">
            <LoaderCircle className="mr-2 size-4 animate-spin" />
            正在读取复核资料
          </div>
        ) : !queue ? (
          <div className="text-muted-foreground flex min-h-96 items-center justify-center px-6 text-center text-sm">
            该文件尚无可复核的切分版本
          </div>
        ) : (
          <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[280px_minmax(0,1fr)]">
            <div className="border-border max-h-56 overflow-y-auto border-b lg:max-h-none lg:border-r lg:border-b-0">
              {targets.map((target) => (
                <div
                  key={target.id}
                  className={`border-border grid grid-cols-[24px_minmax(0,1fr)] gap-2 border-b px-3 py-3 ${activeId === target.id ? "bg-secondary" : "bg-card"}`}
                >
                  <input
                    type="checkbox"
                    checked={selected.includes(target.id)}
                    onChange={() =>
                      setSelected((current) =>
                        current.includes(target.id)
                          ? current.filter((id) => id !== target.id)
                          : [...current, target.id],
                      )
                    }
                    className="accent-primary mt-0.5 size-4"
                    aria-label={`选择 ${target.id}`}
                  />
                  <button
                    type="button"
                    onClick={() => setActiveId(target.id)}
                    className="min-w-0 text-left"
                  >
                    <span className="block truncate text-sm font-medium">
                      {mode === "page"
                        ? `第 ${"page_number" in target ? target.page_number : ""} 页`
                        : `${"volume" in target && target.volume ? target.volume : "未标卷"} · 片段 ${"chunk_index" in target ? target.chunk_index + 1 : ""}`}
                    </span>
                    <span
                      className={`mt-1 inline-block rounded px-1.5 py-0.5 text-xs ${statusClass[target.review_status]}`}
                    >
                      {statusText[target.review_status]}
                    </span>
                  </button>
                </div>
              ))}
            </div>

            <div className="min-h-0 overflow-y-auto px-4 py-4 sm:px-5">
              {activeTarget && (
                <>
                  <div className="text-muted-foreground flex flex-wrap items-center gap-2 text-xs">
                    {"ocr_confidence" in activeTarget && (
                      <span>
                        OCR{" "}
                        {activeTarget.ocr_confidence === null
                          ? "未采集"
                          : `${Math.round(activeTarget.ocr_confidence * 100)}%`}
                      </span>
                    )}
                    {"folio_label" in activeTarget &&
                      activeTarget.folio_label && (
                        <span>叶码 {activeTarget.folio_label}</span>
                      )}
                    {"rotation_degrees" in activeTarget &&
                      activeTarget.rotation_degrees !== 0 && (
                        <span>旋转 {activeTarget.rotation_degrees}°</span>
                      )}
                    {"cleaning_change_count" in activeTarget && (
                      <span>
                        清洗变更 {activeTarget.cleaning_change_count} 处
                      </span>
                    )}
                    {"page_start" in activeTarget && (
                      <span>
                        页码 {activeTarget.page_start}–{activeTarget.page_end}
                      </span>
                    )}
                  </div>
                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    <section>
                      <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
                        <button
                          type="button"
                          aria-pressed={leftView === "text"}
                          onClick={() => setLeftView("text")}
                          className="admin-action"
                        >
                          原始文本
                        </button>
                        <button
                          type="button"
                          aria-pressed={leftView === "facsimile"}
                          onClick={() => setLeftView("facsimile")}
                          className="admin-action"
                        >
                          原件影印
                        </button>
                      </div>
                      {leftView === "facsimile" ? (
                        <SourceFacsimile
                          key={`${fileId}-${activeTarget.id}`}
                          documentId={documentId}
                          fileId={fileId}
                          fileType={fileType}
                          page={
                            "page_number" in activeTarget
                              ? activeTarget.page_number
                              : activeTarget.page_start
                          }
                        />
                      ) : (
                        <pre className="border-border bg-card text-foreground min-h-52 border-l-2 p-3 font-serif text-sm leading-7 whitespace-pre-wrap">
                          {activeTarget.raw_text}
                        </pre>
                      )}
                    </section>
                    <section>
                      <h3 className="text-muted-foreground mb-2 text-xs font-medium">
                        清洗文本
                      </h3>
                      <pre className="border-primary/50 bg-card text-primary min-h-52 border-l-2 p-3 font-serif text-sm leading-7 whitespace-pre-wrap">
                        {activeTarget.clean_text}
                      </pre>
                    </section>
                  </div>
                  <label className="mt-4 block">
                    <span className="text-muted-foreground mb-1.5 block text-xs font-medium">
                      复核意见
                    </span>
                    <textarea
                      value={comment}
                      onChange={(event) => setComment(event.target.value)}
                      rows={3}
                      placeholder="退回或争议时必填"
                      className="border-border focus:border-primary/50 w-full resize-y rounded-md border px-3 py-2 text-sm outline-none"
                    />
                  </label>
                  <div className="border-border bg-card sticky bottom-0 z-10 -mx-4 mt-3 flex flex-wrap gap-2 border-t px-4 py-3 sm:-mx-5 sm:px-5">
                    <button
                      type="button"
                      disabled={saving}
                      onClick={() => void applyDecision("reviewed")}
                      className="bg-primary text-primary-foreground flex h-9 items-center gap-2 rounded-md px-3 text-sm disabled:opacity-40"
                    >
                      <Check className="size-4" />
                      通过
                    </button>
                    <button
                      type="button"
                      disabled={saving}
                      onClick={() => void applyDecision("rejected")}
                      className="border-border text-heritage-rejected-foreground flex h-9 items-center gap-2 rounded-md border px-3 text-sm disabled:opacity-40"
                    >
                      <RotateCcw className="size-4" />
                      退回
                    </button>
                    <button
                      type="button"
                      disabled={saving}
                      onClick={() => void applyDecision("disputed")}
                      className="border-border text-heritage-rejected-foreground flex h-9 items-center gap-2 rounded-md border px-3 text-sm disabled:opacity-40"
                    >
                      <AlertTriangle className="size-4" />
                      标记争议
                    </button>
                  </div>
                  {history.length > 0 && (
                    <section className="border-border mt-5 border-t pt-4">
                      <h3 className="text-muted-foreground text-xs font-medium">
                        复核历史
                      </h3>
                      {history.map((record) => (
                        <div
                          key={record.id}
                          className="text-primary mt-2 flex gap-3 text-xs"
                        >
                          <span>v{record.revision}</span>
                          <span>{statusText[record.decision]}</span>
                          <span className="min-w-0 flex-1 truncate">
                            {record.comment ?? "无意见"}
                          </span>
                        </div>
                      ))}
                    </section>
                  )}
                </>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
