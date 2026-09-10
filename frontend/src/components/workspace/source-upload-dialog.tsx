"use client";

import {
  BookPlus,
  FileText,
  FileUp,
  GitBranch,
  Link2,
  RotateCcw,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import {
  cancelIngestionJob,
  createSourceDocument,
  getIngestionJob,
  getSourceUploadLimits,
  listSourceDocuments,
  retryIngestionStep,
  SourceUploadError,
  uploadSourceFile,
  type IngestionJob,
  type IngestionStepName,
  type SourceDocumentSummary,
  type SourceDocumentCreateInput,
  type SourceUploadLimits,
  type SourceUploadOptions,
  type SourceUploadResult,
  type SourceUploadTask,
} from "@/core/source-files/api";
import {
  createSourceUploadQueue,
  sourceConflictActions,
  type SourceUploadQueueItem,
} from "@/core/source-files/queue";

const emptySourceRegistration: SourceDocumentCreateInput = {
  title: "",
  edition: "",
  source_institution: "",
  source_type: "gazetteer",
  source_type_label: null,
  source_level: "C",
  holder: "",
};

type SourceUploadDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUploaded: (result: SourceUploadResult) => void;
  initialSourceId?: string;
  versionOfFileId?: string;
};

function readableSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

const statusText = {
  queued: "待上传",
  uploading: "上传中",
  uploaded: "已上传",
  failed: "失败",
  cancelled: "已取消",
} as const;

const ingestionStepText: Record<IngestionStepName, string> = {
  parse: "解析",
  ocr: "OCR",
  clean: "清洗",
  chunk: "切分",
  review: "复核",
  index: "索引",
};

function ingestionStatusText(job: IngestionJob) {
  if (job.status === "awaiting_review") return "待复核";
  if (job.status === "completed") return "入库完成";
  if (job.status === "cancelled") return "入库已取消";
  const step = job.current_step ? ingestionStepText[job.current_step] : "处理";
  if (job.status === "failed") return `${step}失败`;
  if (job.status === "running") return `${step}中`;
  return `待${step}`;
}

export function SourceUploadDialog({
  open,
  onOpenChange,
  onUploaded,
  initialSourceId,
  versionOfFileId,
}: SourceUploadDialogProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const tasksRef = useRef(new Map<string, SourceUploadTask>());
  const queueRef = useRef<SourceUploadQueueItem[]>([]);
  const [sources, setSources] = useState<SourceDocumentSummary[]>([]);
  const [limits, setLimits] = useState<SourceUploadLimits | null>(null);
  const [sourceId, setSourceId] = useState("");
  const [queue, setQueue] = useState<SourceUploadQueueItem[]>([]);
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showRegistration, setShowRegistration] = useState(false);
  const [registration, setRegistration] = useState<SourceDocumentCreateInput>(
    emptySourceRegistration,
  );
  const [registering, setRegistering] = useState(false);
  const [registrationError, setRegistrationError] = useState("");

  queueRef.current = queue;

  useEffect(() => {
    if (!open || limits) return;
    let active = true;
    setLoading(true);
    setLoadError("");
    void Promise.all([listSourceDocuments(), getSourceUploadLimits()])
      .then(([nextSources, nextLimits]) => {
        if (!active) return;
        setSources(nextSources);
        setLimits(nextLimits);
        setSourceId(
          initialSourceId &&
            nextSources.some((source) => source.id === initialSourceId)
            ? initialSourceId
            : (nextSources[0]?.id ?? ""),
        );
      })
      .catch((error: unknown) => {
        if (active)
          setLoadError(error instanceof Error ? error.message : "加载失败");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [initialSourceId, open, limits]);

  useEffect(() => {
    if (!open) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      const items = queueRef.current.filter((item) =>
        ["pending", "running"].includes(item.ingestionJob?.status ?? ""),
      );
      await Promise.all(
        items.map(async (item) => {
          const job = item.ingestionJob;
          if (!job) return;
          try {
            const updated = await getIngestionJob(
              job.document_id,
              job.source_file_id,
              job.id,
            );
            if (active)
              updateItem(item.id, {
                ingestionJob: updated,
                ingestionError: undefined,
              });
          } catch (error) {
            if (active)
              updateItem(item.id, {
                ingestionError:
                  error instanceof Error ? error.message : "无法读取入库进度",
              });
          }
        }),
      );
      if (active) timer = setTimeout(() => void poll(), 2000);
    }

    timer = setTimeout(() => void poll(), 2000);
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [open]);

  function updateItem(id: string, update: Partial<SourceUploadQueueItem>) {
    setQueue((current) =>
      current.map((item) => (item.id === id ? { ...item, ...update } : item)),
    );
  }

  async function startItem(
    item: SourceUploadQueueItem,
    options?: SourceUploadOptions,
  ) {
    if (!sourceId || item.status === "uploading") return;
    updateItem(item.id, {
      status: "uploading",
      progress: 0,
      error: undefined,
      conflictCode: undefined,
    });
    const resolvedOptions =
      options ??
      (versionOfFileId
        ? { duplicatePolicy: "new_version", versionOfFileId }
        : {});
    const task = uploadSourceFile(
      sourceId,
      item.file,
      (progress) => {
        updateItem(item.id, { progress });
      },
      resolvedOptions,
    );
    tasksRef.current.set(item.id, task);
    try {
      const result = await task.promise;
      updateItem(item.id, {
        status: "uploaded",
        progress: 100,
        uploaded: result.file,
        ingestionJob: result.ingestionJob,
        ingestionError: result.ingestionError,
      });
      onUploaded(result);
    } catch (error) {
      const message = error instanceof Error ? error.message : "上传失败";
      updateItem(item.id, {
        status: message === "上传已取消" ? "cancelled" : "failed",
        error: message,
        existingFile:
          error instanceof SourceUploadError ? error.existingFile : undefined,
        conflictCode:
          error instanceof SourceUploadError ? error.code : undefined,
      });
    } finally {
      tasksRef.current.delete(item.id);
    }
  }

  async function cancelProcessing(item: SourceUploadQueueItem) {
    if (!item.ingestionJob) return;
    try {
      const ingestionJob = await cancelIngestionJob(item.ingestionJob);
      updateItem(item.id, { ingestionJob, ingestionError: undefined });
    } catch (error) {
      updateItem(item.id, {
        ingestionError:
          error instanceof Error ? error.message : "无法取消入库任务",
      });
    }
  }

  async function retryProcessing(item: SourceUploadQueueItem) {
    if (!item.ingestionJob) return;
    try {
      const ingestionJob = await retryIngestionStep(item.ingestionJob);
      updateItem(item.id, { ingestionJob, ingestionError: undefined });
    } catch (error) {
      updateItem(item.id, {
        ingestionError:
          error instanceof Error ? error.message : "无法重试入库步骤",
      });
    }
  }

  function selectFiles(files: FileList | null) {
    if (!files || !limits) return;
    setQueue(createSourceUploadQueue(Array.from(files), limits));
  }

  async function registerSource() {
    if (
      !registration.title.trim() ||
      !registration.edition.trim() ||
      !registration.source_institution.trim() ||
      !registration.holder.trim()
    ) {
      return;
    }
    setRegistering(true);
    setRegistrationError("");
    try {
      const source = await createSourceDocument({
        ...registration,
        title: registration.title.trim(),
        edition: registration.edition.trim(),
        source_institution: registration.source_institution.trim(),
        holder: registration.holder.trim(),
      });
      setSources((current) => [source, ...current]);
      setSourceId(source.id);
      setRegistration(emptySourceRegistration);
      setShowRegistration(false);
    } catch (error) {
      setRegistrationError(
        error instanceof Error ? error.message : "无法登记资料来源",
      );
    } finally {
      setRegistering(false);
    }
  }

  const isUploading = queue.some((item) => item.status === "uploading");
  const canUpload = Boolean(
    sourceId && queue.some((item) => item.status === "queued"),
  );

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen && isUploading) return;
        onOpenChange(nextOpen);
      }}
    >
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>上传文献文件</DialogTitle>
          <DialogDescription>
            文件将绑定到已登记的资料来源，上传成功不代表已入库发布。
          </DialogDescription>
        </DialogHeader>

        {loadError ? (
          <div className="border-l-2 border-[#b84b4b] bg-[#fff4f3] px-3 py-2 text-sm text-[#8c3030]">
            {loadError}
          </div>
        ) : (
          <div className="space-y-4">
            <div className="text-sm">
              <div className="mb-1.5 flex items-center justify-between gap-3">
                <label
                  htmlFor="source-document"
                  className="font-medium text-[#344247]"
                >
                  资料来源
                </label>
                {(sources.length > 0 || showRegistration) && (
                  <button
                    type="button"
                    disabled={isUploading || registering}
                    onClick={() => {
                      setRegistrationError("");
                      setShowRegistration((current) => !current);
                    }}
                    className="inline-flex h-8 items-center gap-1.5 rounded-md border border-[#9ab9bd] px-2.5 text-xs text-[#285f68] hover:bg-[#edf5f5] disabled:opacity-40"
                  >
                    <BookPlus className="size-3.5" />
                    {showRegistration ? "取消登记" : "登记资料来源"}
                  </button>
                )}
              </div>
              <select
                id="source-document"
                value={sourceId}
                disabled={loading || sources.length === 0 || isUploading}
                onChange={(event) => setSourceId(event.target.value)}
                className="h-10 w-full rounded-md border border-[#cfdadc] bg-white px-3 outline-none focus:border-[#4f929b]"
              >
                {sources.length === 0 && (
                  <option value="">暂无已登记来源</option>
                )}
                {sources.map((source) => (
                  <option key={source.id} value={source.id}>
                    {source.title} · {source.edition ?? "未标版本"} ·{" "}
                    {source.source_institution}
                  </option>
                ))}
              </select>
              {sources.length === 0 && !showRegistration && !loading && (
                <div className="mt-3 flex flex-col gap-3 border-l-2 border-[#c39b47] bg-[#fff9eb] px-3 py-3 sm:flex-row sm:items-center sm:justify-between">
                  <p className="text-xs leading-5 text-[#6f5a2e]">
                    当前库中还没有资料来源。你可以先选择文件，但开始上传前需要登记来源。
                  </p>
                  <button
                    type="button"
                    onClick={() => {
                      setRegistrationError("");
                      setShowRegistration(true);
                    }}
                    className="inline-flex h-9 shrink-0 items-center justify-center gap-1.5 rounded-md bg-[#245f68] px-3 text-sm text-white hover:bg-[#1d5159]"
                  >
                    <BookPlus className="size-4" />
                    先登记资料来源
                  </button>
                </div>
              )}
            </div>

            {showRegistration && (
              <form
                className="space-y-3 border-y border-[#dce5e6] bg-[#f5f8f8] px-3 py-4"
                onSubmit={(event) => {
                  event.preventDefault();
                  void registerSource();
                }}
              >
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="text-xs font-medium text-[#435358]">
                    来源标题
                    <input
                      required
                      value={registration.title}
                      onChange={(event) =>
                        setRegistration((current) => ({
                          ...current,
                          title: event.target.value,
                        }))
                      }
                      className="mt-1.5 h-9 w-full rounded-md border border-[#cbd8da] bg-white px-3 text-sm outline-none focus:border-[#4f929b]"
                    />
                  </label>
                  <label className="text-xs font-medium text-[#435358]">
                    版本信息
                    <input
                      required
                      value={registration.edition}
                      onChange={(event) =>
                        setRegistration((current) => ({
                          ...current,
                          edition: event.target.value,
                        }))
                      }
                      placeholder="例如：1996 年版"
                      className="mt-1.5 h-9 w-full rounded-md border border-[#cbd8da] bg-white px-3 text-sm outline-none focus:border-[#4f929b]"
                    />
                  </label>
                  <label className="text-xs font-medium text-[#435358]">
                    来源机构
                    <input
                      required
                      value={registration.source_institution}
                      onChange={(event) =>
                        setRegistration((current) => ({
                          ...current,
                          source_institution: event.target.value,
                        }))
                      }
                      className="mt-1.5 h-9 w-full rounded-md border border-[#cbd8da] bg-white px-3 text-sm outline-none focus:border-[#4f929b]"
                    />
                  </label>
                  <label className="text-xs font-medium text-[#435358]">
                    资料持有人
                    <input
                      required
                      value={registration.holder}
                      onChange={(event) =>
                        setRegistration((current) => ({
                          ...current,
                          holder: event.target.value,
                        }))
                      }
                      className="mt-1.5 h-9 w-full rounded-md border border-[#cbd8da] bg-white px-3 text-sm outline-none focus:border-[#4f929b]"
                    />
                  </label>
                  <label className="text-xs font-medium text-[#435358]">
                    来源类型
                    <select
                      value={registration.source_type}
                      onChange={(event) =>
                        setRegistration((current) => ({
                          ...current,
                          source_type: event.target
                            .value as SourceDocumentCreateInput["source_type"],
                          source_type_label:
                            event.target.value === "other"
                              ? current.source_type_label
                              : null,
                        }))
                      }
                      className="mt-1.5 h-9 w-full rounded-md border border-[#cbd8da] bg-white px-3 text-sm outline-none focus:border-[#4f929b]"
                    >
                      <option value="gazetteer">地方志</option>
                      <option value="inscription">碑刻题记</option>
                      <option value="archive">档案</option>
                      <option value="heritage_record">文保记录</option>
                      <option value="scholarly_work">研究著作</option>
                      <option value="oral_history">口述史</option>
                      <option value="web">网络资料</option>
                      <option value="inference">推断材料</option>
                      <option value="other">其他资料</option>
                    </select>
                  </label>
                  {registration.source_type === "other" && (
                    <label className="text-xs font-medium text-[#435358]">
                      自定义资料类型
                      <input
                        required
                        maxLength={100}
                        value={registration.source_type_label ?? ""}
                        onChange={(event) =>
                          setRegistration((current) => ({
                            ...current,
                            source_type_label: event.target.value,
                          }))
                        }
                        placeholder="例如：家谱、报刊、书信、照片集"
                        className="mt-1.5 h-9 w-full rounded-md border border-[#cbd8da] bg-white px-3 text-sm outline-none focus:border-[#4f929b]"
                      />
                    </label>
                  )}
                  <label className="text-xs font-medium text-[#435358]">
                    来源等级
                    <select
                      value={registration.source_level}
                      onChange={(event) =>
                        setRegistration((current) => ({
                          ...current,
                          source_level: event.target
                            .value as SourceDocumentCreateInput["source_level"],
                        }))
                      }
                      className="mt-1.5 h-9 w-full rounded-md border border-[#cbd8da] bg-white px-3 text-sm outline-none focus:border-[#4f929b]"
                    >
                      <option value="A">A · 原始权威资料</option>
                      <option value="B">B · 可靠整理资料</option>
                      <option value="C">C · 一般参考资料</option>
                      <option value="D">D · 待进一步核验</option>
                      <option value="E">E · 线索或推断</option>
                    </select>
                  </label>
                </div>
                {registrationError && (
                  <p role="alert" className="text-xs text-[#9a3f3f]">
                    {registrationError}
                  </p>
                )}
                <div className="flex justify-end">
                  <button
                    type="submit"
                    disabled={
                      registering ||
                      !registration.title.trim() ||
                      !registration.edition.trim() ||
                      !registration.source_institution.trim() ||
                      !registration.holder.trim()
                    }
                    className="h-9 rounded-md bg-[#245f68] px-4 text-sm text-white hover:bg-[#1d5159] disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {registering ? "正在保存…" : "保存来源"}
                  </button>
                </div>
              </form>
            )}

            <div className="flex items-center justify-between gap-3 border-b border-[#e0e7e8] pb-3">
              <div className="min-w-0 text-xs text-[#697a7e]">
                {limits
                  ? `最多 ${limits.max_files} 个，单个不超过 ${readableSize(limits.max_file_size)}`
                  : "正在读取上传限制"}
              </div>
              <input
                ref={inputRef}
                type="file"
                multiple
                accept={limits?.allowed_extensions.join(",")}
                className="sr-only"
                onChange={(event) => {
                  selectFiles(event.target.files);
                  event.target.value = "";
                }}
              />
              <button
                type="button"
                disabled={!limits || isUploading}
                onClick={() => inputRef.current?.click()}
                className="flex h-9 shrink-0 items-center gap-2 rounded-md border border-[#8aafb4] px-3 text-sm text-[#275f68] hover:bg-[#edf5f5] disabled:cursor-not-allowed disabled:opacity-40"
              >
                <FileUp className="size-4" />
                选择文件
              </button>
            </div>

            <div className="min-h-28">
              {queue.length === 0 ? (
                <div className="flex min-h-28 items-center justify-center text-sm text-[#7a898d]">
                  尚未选择文件
                </div>
              ) : (
                queue.map((item) => (
                  <div
                    key={item.id}
                    className="grid grid-cols-[minmax(0,1fr)_96px_36px] items-center gap-3 border-b border-[#e7ecec] py-3 last:border-b-0"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <FileText className="size-4 shrink-0 text-[#568087]" />
                        <span
                          className="truncate text-sm font-medium"
                          title={item.file.name}
                        >
                          {item.file.name}
                        </span>
                        <span className="shrink-0 text-xs text-[#7b898d]">
                          {readableSize(item.file.size)}
                        </span>
                      </div>
                      {item.status === "uploading" && (
                        <Progress
                          value={item.progress}
                          className="mt-2 h-1.5"
                        />
                      )}
                      {item.status === "uploaded" && item.ingestionJob && (
                        <Progress
                          value={item.ingestionJob.progress_percent}
                          className="mt-2 h-1.5"
                        />
                      )}
                      {item.error && (
                        <p className="mt-1 text-xs text-[#a13d3d]">
                          {item.error}
                        </p>
                      )}
                      {item.ingestionError && (
                        <p className="mt-1 text-xs text-[#a13d3d]">
                          {item.ingestionError}
                        </p>
                      )}
                      {item.existingFile && (
                        <div className="mt-2 flex flex-wrap gap-2">
                          {sourceConflictActions(item.conflictCode).includes(
                            "reference_existing",
                          ) && (
                            <button
                              type="button"
                              onClick={() =>
                                void startItem(item, {
                                  duplicatePolicy: "reference_existing",
                                })
                              }
                              className="flex h-7 items-center gap-1.5 rounded-md border border-[#8aafb4] px-2.5 text-xs text-[#275f68] hover:bg-[#edf5f5]"
                            >
                              <Link2 className="size-3.5" />
                              引用已有
                            </button>
                          )}
                          {sourceConflictActions(item.conflictCode).includes(
                            "new_version",
                          ) && (
                            <button
                              type="button"
                              onClick={() =>
                                void startItem(item, {
                                  duplicatePolicy: "new_version",
                                  versionOfFileId: item.existingFile?.id,
                                })
                              }
                              className="flex h-7 items-center gap-1.5 rounded-md border border-[#8aafb4] px-2.5 text-xs text-[#275f68] hover:bg-[#edf5f5]"
                            >
                              <GitBranch className="size-3.5" />
                              建立新版本
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                    <span
                      className={`text-xs ${
                        item.status === "uploaded"
                          ? "text-[#28734e]"
                          : item.status === "failed"
                            ? "text-[#a13d3d]"
                            : "text-[#617277]"
                      }`}
                    >
                      {item.status === "uploaded" && item.ingestionJob
                        ? ingestionStatusText(item.ingestionJob)
                        : item.status === "uploading"
                          ? `${item.progress}%`
                          : statusText[item.status]}
                    </span>
                    {item.status === "uploading" || item.status === "queued" ? (
                      <button
                        type="button"
                        title="取消上传"
                        onClick={() => {
                          const task = tasksRef.current.get(item.id);
                          if (task) task.cancel();
                          else updateItem(item.id, { status: "cancelled" });
                        }}
                        className="flex size-8 items-center justify-center rounded-md text-[#6a787c] hover:bg-[#eef3f3]"
                      >
                        <X className="size-4" />
                      </button>
                    ) : item.ingestionJob?.status === "failed" &&
                      item.ingestionJob.current_step &&
                      item.ingestionJob.steps.find(
                        (step) => step.name === item.ingestionJob?.current_step,
                      )?.retryable ? (
                      <button
                        type="button"
                        title="重试当前入库步骤"
                        onClick={() => void retryProcessing(item)}
                        className="flex size-8 items-center justify-center rounded-md text-[#356f77] hover:bg-[#e9f2f3]"
                      >
                        <RotateCcw className="size-4" />
                      </button>
                    ) : item.ingestionJob &&
                      ["pending", "running", "awaiting_review"].includes(
                        item.ingestionJob.status,
                      ) ? (
                      <button
                        type="button"
                        title="取消入库任务"
                        onClick={() => void cancelProcessing(item)}
                        className="flex size-8 items-center justify-center rounded-md text-[#6a787c] hover:bg-[#eef3f3]"
                      >
                        <X className="size-4" />
                      </button>
                    ) : (item.status === "failed" && !item.existingFile) ||
                      item.status === "cancelled" ? (
                      <button
                        type="button"
                        title="重试上传"
                        onClick={() => void startItem(item)}
                        className="flex size-8 items-center justify-center rounded-md text-[#356f77] hover:bg-[#e9f2f3]"
                      >
                        <RotateCcw className="size-4" />
                      </button>
                    ) : (
                      <span />
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        <DialogFooter>
          <button
            type="button"
            disabled={isUploading}
            onClick={() => onOpenChange(false)}
            className="h-9 rounded-md border border-[#ccd7d9] px-4 text-sm hover:bg-[#f0f4f4] disabled:opacity-40"
          >
            关闭
          </button>
          <button
            type="button"
            disabled={!canUpload || isUploading}
            onClick={() => {
              queue
                .filter((item) => item.status === "queued")
                .forEach((item) => void startItem(item));
            }}
            className="h-9 rounded-md bg-[#202b2e] px-4 text-sm text-white hover:bg-[#354347] disabled:cursor-not-allowed disabled:opacity-40"
          >
            {isUploading ? "正在上传" : "开始上传"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
