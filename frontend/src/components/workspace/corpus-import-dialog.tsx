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
import { sourceFileContentUrl } from "@/core/source-files/api";

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
      setError(reason instanceof Error ? reason.message : "无法读取导入批次");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) void loadBatches();
  }, [loadBatches, open]);

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
        if (active)
          setError(
            reason instanceof Error ? reason.message : "无法读取导入条目",
          );
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
        if (active)
          setError(
            reason instanceof Error ? reason.message : "无法读取质量问题",
          );
      });
    return () => {
      active = false;
    };
  }, [itemId, open]);

  const selectedItem = items.find((item) => item.id === itemId);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[92vh] w-[calc(100vw-1.5rem)] max-w-7xl flex-col overflow-hidden p-0">
        <DialogHeader className="border-b border-[#dbe4e5] px-5 py-4 pr-12">
          <DialogTitle className="text-base">府县志导入批次</DialogTitle>
          <DialogDescription>批次、书目与预计算文本质量记录</DialogDescription>
        </DialogHeader>
        <div className="flex items-center gap-3 border-b border-[#dbe4e5] px-5 py-3">
          <span className="text-sm text-[#637479]">
            {batches.length} 个批次
          </span>
          <button
            type="button"
            onClick={() => void loadBatches()}
            disabled={loading}
            title="刷新导入批次"
            className="ml-auto flex size-9 items-center justify-center rounded-md border border-[#ccd9db] text-[#456970] hover:bg-[#edf5f5] disabled:opacity-40"
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
          <div className="overflow-y-auto border-r border-[#dfe7e8]">
            {batches.map((batch) => (
              <button
                key={batch.id}
                type="button"
                onClick={() => setBatchId(batch.id)}
                className={`block w-full border-b border-[#e8eded] px-4 py-3 text-left ${batch.id === batchId ? "bg-[#eef5f5]" : "bg-white hover:bg-[#f7fafa]"}`}
              >
                <span className="block text-sm font-medium">
                  {statusLabel[batch.status]}
                </span>
                <span className="mt-1 block text-xs text-[#687a7f]">
                  {batch.item_count} 册 · {batch.page_count.toLocaleString()} 页
                </span>
                <span
                  className="mt-1 block truncate font-mono text-[11px] text-[#849195]"
                  title={batch.manifest_sha256}
                >
                  {batch.manifest_sha256.slice(0, 16)}
                </span>
              </button>
            ))}
            {!loading && batches.length === 0 && (
              <p className="px-4 py-8 text-center text-sm text-[#718186]">
                暂无导入批次
              </p>
            )}
          </div>
          <div className="overflow-y-auto border-r border-[#dfe7e8]">
            {items.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setItemId(item.id)}
                className={`block w-full border-b border-[#e8eded] px-4 py-3 text-left ${item.id === itemId ? "bg-[#eef5f5]" : "bg-white hover:bg-[#f7fafa]"}`}
              >
                <span
                  className="block truncate text-sm font-medium"
                  title={item.bundle_id}
                >
                  {item.bundle_id}
                </span>
                <span className="mt-1 block text-xs text-[#687a7f]">
                  {item.page_count} 页 · {item.quality_issue_count} 条质量提示
                </span>
              </button>
            ))}
            {batchId && items.length === 0 && (
              <p className="px-4 py-8 text-center text-sm text-[#718186]">
                该批次暂无书目
              </p>
            )}
          </div>
          <div className="overflow-y-auto bg-white px-5 py-4">
            {selectedItem && (
              <div className="mb-4 flex flex-wrap items-center gap-3 border-b border-[#dfe7e8] pb-4">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">
                    {selectedItem.document_id}
                  </p>
                  <p className="mt-1 text-xs text-[#718186]">
                    ChunkSet {selectedItem.chunk_set_id}
                  </p>
                </div>
                <a
                  href={sourceFileContentUrl(
                    selectedItem.document_id,
                    selectedItem.source_file_id,
                  )}
                  target="_blank"
                  rel="noreferrer"
                  className="flex h-9 items-center gap-2 rounded-md border border-[#8aafb4] px-3 text-sm text-[#275f68] hover:bg-[#edf5f5]"
                >
                  <ExternalLink className="size-4" />
                  打开原件
                </a>
              </div>
            )}
            {issues.map((issue) => (
              <div
                key={issue.id}
                className="grid grid-cols-[90px_90px_minmax(0,1fr)] gap-3 border-b border-[#edf1f2] py-3 text-sm"
              >
                <span>第 {issue.physical_page_number} 页</span>
                <span>叶码 {issue.folio_label}</span>
                <span className="text-[#566b70]">
                  {issue.message} ({issue.count})
                </span>
              </div>
            ))}
            {selectedItem && issues.length === 0 && (
              <p className="py-8 text-center text-sm text-[#718186]">
                该书目没有质量提示
              </p>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
