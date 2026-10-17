"use client";

import {
  Check,
  History,
  LoaderCircle,
  PackageCheck,
  RotateCcw,
} from "lucide-react";
import { useEffect, useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  getKnowledgeReleaseState,
  listKnowledgeReleases,
  listSourceChunkSets,
  publishKnowledgeRelease,
  retryKnowledgeRelease,
  rollbackKnowledgeRelease,
  type KnowledgeRelease,
  type KnowledgeReleaseState,
} from "@/core/source-files/api";

export type ReleaseCandidate = {
  title: string;
  documentId: string;
  fileId: string;
};

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  candidates: ReleaseCandidate[];
};

export function KnowledgeReleaseDialog({
  open,
  onOpenChange,
  candidates,
}: Props) {
  const [releases, setReleases] = useState<KnowledgeRelease[]>([]);
  const [state, setState] = useState<KnowledgeReleaseState | null>(null);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function reload() {
    const [nextReleases, nextState] = await Promise.all([
      listKnowledgeReleases(),
      getKnowledgeReleaseState(),
    ]);
    setReleases(nextReleases);
    setState(nextState);
  }

  useEffect(() => {
    if (!open) return;
    setError("");
    void reload().catch((reason: unknown) =>
      setError(reason instanceof Error ? reason.message : "无法读取知识版本"),
    );
  }, [open]);

  async function publish() {
    if (!state || !notes.trim() || candidates.length === 0) return;
    setBusy(true);
    setError("");
    try {
      const versions = await Promise.all(
        candidates.map((item) =>
          listSourceChunkSets(item.documentId, item.fileId),
        ),
      );
      const chunkSetIds = versions.map((items, index) => {
        const latest = items.at(-1);
        const candidate = candidates[index];
        if (!latest)
          throw new Error(`${candidate?.title ?? "所选文献"} 尚无切分版本`);
        return latest.id;
      });
      await publishKnowledgeRelease(
        chunkSetIds,
        notes.trim(),
        state.state_version,
      );
      setNotes("");
      await reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "知识版本发布失败");
    } finally {
      setBusy(false);
    }
  }

  async function rollback(target: KnowledgeRelease) {
    if (!state) return;
    setBusy(true);
    setError("");
    try {
      await rollbackKnowledgeRelease(
        target.id,
        `回滚到 ${target.version}：${target.release_notes}`,
        state.state_version,
      );
      await reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "知识版本回滚失败");
    } finally {
      setBusy(false);
    }
  }

  async function retry(target: KnowledgeRelease) {
    if (!state) return;
    setBusy(true);
    setError("");
    try {
      await retryKnowledgeRelease(target.id, state.state_version);
      await reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "知识版本重试失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="admin-dialog release-workbench flex max-h-[90vh] w-[calc(100vw-1.5rem)] max-w-2xl flex-col overflow-hidden p-0">
        <DialogHeader className="border-border border-b px-5 py-4 pr-12">
          <DialogTitle className="flex items-center gap-2 text-base">
            <PackageCheck className="text-primary size-4" />
            知识版本
          </DialogTitle>
          <DialogDescription>
            当前版本 {state?.active_version ?? "尚未发布"}
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 overflow-y-auto px-5 py-4">
          <section className="border-border border-b pb-5">
            <p className="text-sm font-medium">发布所选文献</p>
            <p className="text-muted-foreground mt-1 text-xs">
              已选 {candidates.length} 份，发布时读取各自最新切分版本
            </p>
            <textarea
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              rows={3}
              placeholder="填写本次发布说明"
              className="border-border focus:border-primary/50 mt-3 w-full resize-y rounded-md border px-3 py-2 text-sm outline-none"
            />
            <button
              type="button"
              disabled={
                busy || candidates.length === 0 || !notes.trim() || !state
              }
              onClick={() => void publish()}
              className="bg-primary text-primary-foreground mt-3 flex h-9 items-center gap-2 rounded-md px-3 text-sm disabled:opacity-40"
            >
              {busy ? (
                <LoaderCircle className="size-4 animate-spin" />
              ) : (
                <Check className="size-4" />
              )}
              发布并启用
            </button>
          </section>

          {error && (
            <p className="text-heritage-rejected-foreground mt-3 text-sm">
              {error}
            </p>
          )}

          <section className="pt-5">
            <h3 className="flex items-center gap-2 text-sm font-medium">
              <History className="size-4" />
              版本历史
            </h3>
            {releases.length === 0 ? (
              <p className="text-muted-foreground mt-3 text-sm">尚无知识版本</p>
            ) : (
              <div className="divide-border border-border mt-3 divide-y border-y">
                {[...releases].reverse().map((release) => {
                  const active =
                    release.id === state?.active_release_id &&
                    release.status === "active";
                  const statusLabel = {
                    preparing: "准备中",
                    ready: "已就绪",
                    failed: "准备失败",
                    active: "当前",
                  }[release.status];
                  return (
                    <div
                      key={release.id}
                      className="flex items-center gap-3 py-3"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium">
                          {release.version} · {statusLabel}
                        </p>
                        <p className="text-muted-foreground mt-1 truncate text-xs">
                          {release.scope === "internal"
                            ? "内部工作版 · "
                            : "公开版 · "}
                          {release.release_notes} · {release.items.length}{" "}
                          个片段
                        </p>
                        {release.status === "failed" && (
                          <p className="text-heritage-rejected-foreground mt-1 text-xs leading-5">
                            {release.failure_message ?? "索引或资产准备失败"}
                          </p>
                        )}
                      </div>
                      {release.status === "failed" && (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void retry(release)}
                          className="border-border text-heritage-rejected-foreground flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-xs disabled:opacity-40"
                        >
                          <RotateCcw className="size-3.5" />
                          重试
                        </button>
                      )}
                      {!active &&
                        release.status === "ready" &&
                        state?.active_version &&
                        release.version_number <
                          Number(state.active_version.slice(1)) && (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => void rollback(release)}
                            className="border-border text-heritage-rejected-foreground flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-xs disabled:opacity-40"
                          >
                            <RotateCcw className="size-3.5" />
                            回滚
                          </button>
                        )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        </div>
      </DialogContent>
    </Dialog>
  );
}
