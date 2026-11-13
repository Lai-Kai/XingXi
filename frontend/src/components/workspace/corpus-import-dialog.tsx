"use client";

import { ExternalLink, LoaderCircle, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  listCorpusImportBatches,
  listCorpusImportItems,
  listCorpusQualityIssues,
  type CorpusImportBatch,
  type CorpusImportItem,
  type CorpusQualityIssue,
} from "@/core/corpus-imports/api";
import {
  listSourceDocuments,
  sourceFileContentUrl,
  type SourceDocumentSummary,
} from "@/core/source-files/api";
import { corpusQualityMessage } from "@/core/source-files/presentation";
import { publicErrorMessage } from "@/core/ui/presentation";

const statusLabel = {
  running: "导入中",
  completed: "已完成",
  failed: "失败",
} as const;

export function CorpusImportDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [batches, setBatches] = useState<CorpusImportBatch[]>([]);
  const [items, setItems] = useState<CorpusImportItem[]>([]);
  const [issues, setIssues] = useState<CorpusQualityIssue[]>([]);
  const [sources, setSources] = useState<SourceDocumentSummary[]>([]);
  const [batchId, setBatchId] = useState("");
  const [itemId, setItemId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const loadBatches = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const next = await listCorpusImportBatches();
      setBatches(next);
      setBatchId((current) =>
        current && next.some((batch) => batch.id === current)
          ? current
          : (next[0]?.id ?? ""),
      );
    } catch (reason) {
      setError(publicErrorMessage(reason, "无法读取导入批次"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) void loadBatches();
  }, [loadBatches, open]);

  useEffect(() => {
    if (!open) return;
    let active = true;
    void listSourceDocuments()
      .then((next) => {
        if (active) setSources(next);
      })
      .catch(() => {
        if (active) setSources([]);
      });
    return () => {
      active = false;
    };
  }, [open]);

  useEffect(() => {
    if (!open || !batchId) {
      setItems([]);
      setItemId("");
      return;
    }
    let active = true;
    void listCorpusImportItems(batchId)
      .then((next) => {
        if (!active) return;
        setItems(next);
        setItemId(next[0]?.id ?? "");
      })
      .catch((reason: unknown) => {
        if (active) setError(publicErrorMessage(reason, "无法读取导入条目"));
      });
    return () => {
      active = false;
    };
  }, [batchId, open]);

  useEffect(() => {
    if (!open || !itemId) {
      setIssues([]);
      return;
    }
    let active = true;
    void listCorpusQualityIssues(itemId)
      .then((next) => {
        if (active) setIssues(next);
      })
      .catch((reason: unknown) => {
        if (active) setError(publicErrorMessage(reason, "无法读取质量问题"));
      });
    return () => {
      active = false;
    };
  }, [itemId, open]);

  const selectedItem = items.find((item) => item.id === itemId);
  const titleOfItem = (item: CorpusImportItem) =>
    sources.find((source) => source.id === item.document_id)?.title ??
    `第 ${items.indexOf(item) + 1} 册`;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[92vh] w-[calc(100vw-1.5rem)] max-w-7xl flex-col overflow-hidden p-0">
        <DialogHeader className="border-border border-b px-5 py-4 pr-12">
          <DialogTitle className="text-base">府县志导入批次</DialogTitle>
          <DialogDescription>查看已导入书目与文字核对提示</DialogDescription>
        </DialogHeader>
        <div className="border-border flex items-center gap-3 border-b px-5 py-3">
          <span className="text-muted-foreground text-sm">
            {batches.length} 个批次
          </span>
          <button
            type="button"
            onClick={() => void loadBatches()}
            disabled={loading}
            title="刷新导入批次"
            className="border-border text-muted-foreground hover:bg-muted/60 ml-auto flex size-9 items-center justify-center rounded-md border disabled:opacity-40"
          >
            {loading ? (
              <LoaderCircle className="size-4 animate-spin" />
            ) : (
              <RefreshCw className="size-4" />
            )}
          </button>
        </div>
        {error && (
          <div className="border-b border-[#f0c9c5] bg-[#fff3f2] px-5 py-2 text-sm text-[#963d36]">
            {error}
          </div>
        )}
        <div className="grid min-h-[520px] flex-1 overflow-hidden lg:grid-cols-[250px_360px_minmax(0,1fr)]">
          <div className="border-border overflow-y-auto border-r">
            {batches.map((batch, index) => (
              <button
                key={batch.id}
                type="button"
                onClick={() => setBatchId(batch.id)}
                className={`border-border block w-full border-b px-4 py-3 text-left ${batch.id === batchId ? "bg-muted/60" : "bg-card hover:bg-muted/60"}`}
              >
                <span className="block text-sm font-medium">
                  第 {index + 1} 批 · {statusLabel[batch.status]}
                </span>
                <span className="text-muted-foreground mt-1 block text-xs">
                  {batch.item_count} 册 · {batch.page_count.toLocaleString()} 页
                </span>
              </button>
            ))}
            {!loading && batches.length === 0 && (
              <p className="text-muted-foreground px-4 py-8 text-center text-sm">
                暂无导入批次
              </p>
            )}
          </div>
          <div className="border-border overflow-y-auto border-r">
            {items.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setItemId(item.id)}
                className={`border-border block w-full border-b px-4 py-3 text-left ${item.id === itemId ? "bg-muted/60" : "bg-card hover:bg-muted/60"}`}
              >
                <span
                  className="block truncate text-sm font-medium"
                  title={titleOfItem(item)}
                >
                  {titleOfItem(item)}
                </span>
                <span className="text-muted-foreground mt-1 block text-xs">
                  {item.page_count} 页 · {item.quality_issue_count} 条质量提示
                </span>
              </button>
            ))}
            {batchId && items.length === 0 && (
              <p className="text-muted-foreground px-4 py-8 text-center text-sm">
                该批次暂无书目
              </p>
            )}
          </div>
          <div className="bg-card overflow-y-auto px-5 py-4">
            {selectedItem && (
              <div className="border-border mb-4 flex flex-wrap items-center gap-3 border-b pb-4">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">
                    {titleOfItem(selectedItem)}
                  </p>
                </div>
                <a
                  href={sourceFileContentUrl(
                    selectedItem.document_id,
                    selectedItem.source_file_id,
                  )}
                  target="_blank"
                  rel="noreferrer"
                  className="border-primary text-primary hover:bg-muted/60 flex h-9 items-center gap-2 rounded-md border px-3 text-sm"
                >
                  <ExternalLink className="size-4" />
                  打开原件
                </a>
              </div>
            )}
            {issues.map((issue) => (
              <div
                key={issue.id}
                className="border-border grid grid-cols-[90px_90px_minmax(0,1fr)] gap-3 border-b py-3 text-sm"
              >
                <span>第 {issue.physical_page_number} 页</span>
                <span>叶码 {issue.folio_label}</span>
                <span className="text-muted-foreground">
                  {corpusQualityMessage(issue.code)}（{issue.count} 处）
                </span>
              </div>
            ))}
            {selectedItem && issues.length === 0 && (
              <p className="text-muted-foreground py-8 text-center text-sm">
                该书目没有质量提示
              </p>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
