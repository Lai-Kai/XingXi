"use client";

import {
  ArrowRightLeft,
  BookOpen,
  ClipboardCheck,
  FileText,
  FileUp,
  GitBranch,
  Import,
  Network,
  PackageCheck,
  Pencil,
  Plus,
  Search,
  ShieldAlert,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  BusinessEmptyState,
  BusinessErrorState,
  BusinessInlineError,
  BusinessLoadingState,
  BusinessMobileHeader,
  BusinessPageHeader,
} from "@/components/workspace/business-page";
import { EvidenceDetailPanel } from "@/components/workspace/citations/evidence-detail-panel";
import { CorpusImportDialog } from "@/components/workspace/corpus-import-dialog";
import { KnowledgeReleaseDialog } from "@/components/workspace/knowledge-release-dialog";
import { SourceEditDialog } from "@/components/workspace/source-edit-dialog";
import {
  SourceProcessingStatus,
  SourceTextReviewStatus,
  TEMPORARY_LIBRARY_SUCCESS_PREVIEW,
} from "@/components/workspace/source-library-status";
import { SourceReviewDialog } from "@/components/workspace/source-review-dialog";
import { SourceUploadDialog } from "@/components/workspace/source-upload-dialog";
import { useAuth } from "@/core/auth/AuthProvider";
import { canManageSourceDocuments } from "@/core/auth/permissions";
import {
  addDocumentToResearchProject,
  listResearchProjects,
} from "@/core/projects/api";
import {
  type IngestionJobStatus,
  type IngestionJob,
  type ReviewStatus,
  generateSourceGraph,
  getIngestionJob,
  pageSourceDocumentLibrary,
  type SourceDocumentStatus,
  type SourceDocumentSummary,
  type SourceUploadResult,
} from "@/core/source-files/api";
import { createLatestRequestTracker } from "@/core/source-files/latest-request";

type LibraryDocument = {
  id: string;
  title: string;
  type: string;
  size: string;
  status: IngestionJobStatus | null;
  ingestionJob?: IngestionJob | null;
  reviewStatus: ReviewStatus | null;
  addedAt: string;
  note: string;
  documentId: string;
  sourceFileId: string;
  ingestionJobId?: string;
  source: SourceDocumentSummary;
};

function readableSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function documentStatus(
  job?: {
    status: IngestionJobStatus;
  } | null,
): LibraryDocument["status"] {
  if (!job) return null;
  return job.status;
}

export default function LibraryPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { user } = useAuth();
  const mayManageSources = canManageSourceDocuments(user);
  const evidenceId = searchParams.get("evidence_id")?.trim() ?? null;
  const [documents, setDocuments] = useState<LibraryDocument[]>([]);
  const [sources, setSources] = useState<SourceDocumentSummary[]>([]);
  const [totalSources, setTotalSources] = useState(0);
  const [page, setPage] = useState(1);
  const [sourceStatus, setSourceStatus] = useState<
    SourceDocumentStatus | "all"
  >("all");
  const [selected, setSelected] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [showNotes, setShowNotes] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  useEffect(() => {
    if (mayManageSources && searchParams.get("upload") === "1") {
      setUploadOpen(true);
    }
  }, [mayManageSources, searchParams]);
  const [editSource, setEditSource] = useState<SourceDocumentSummary | null>(
    null,
  );
  const [versionDocument, setVersionDocument] =
    useState<LibraryDocument | null>(null);
  const [releaseOpen, setReleaseOpen] = useState(false);
  const [corpusImportsOpen, setCorpusImportsOpen] = useState(false);
  const [reviewDocument, setReviewDocument] = useState<LibraryDocument | null>(
    null,
  );
  const [projectOptions, setProjectOptions] = useState<
    { id: string; name: string }[]
  >([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [transferring, setTransferring] = useState(false);
  const [graphBusy, setGraphBusy] = useState<string | null>(null);
  const [graphNotice, setGraphNotice] = useState("");
  const loadTracker = useRef(createLatestRequestTracker());

  const loadDocuments = useCallback(async () => {
    const request = loadTracker.current.start();
    setLoading(true);
    setLoadError(null);
    try {
      const sourcePage = await pageSourceDocumentLibrary({
        query,
        status: sourceStatus,
        page,
        pageSize: 10,
        signal: request.signal,
      });
      const sources = sourcePage.items.map((item) => item.source);
      const rows = sourcePage.items.flatMap(({ source, files }) =>
        files.map(
          ({ file, ingestion_job: latestJob, review_status }) =>
            ({
              id: file.id,
              title: file.original_filename ?? source.title,
              type:
                file.original_filename.split(".").pop()?.toUpperCase() ??
                "文件",
              size: readableSize(file.size),
              status: documentStatus(latestJob),
              ingestionJob: latestJob,
              reviewStatus: review_status ?? null,
              addedAt: new Intl.DateTimeFormat("zh-CN").format(
                new Date(file.uploaded_at),
              ),
              note: "",
              documentId: source.id,
              sourceFileId: file.id,
              ingestionJobId: latestJob?.id,
              source,
            }) satisfies LibraryDocument,
        ),
      );
      if (!loadTracker.current.isCurrent(request.sequence)) return;
      setSources(sources);
      setTotalSources(sourcePage.total);
      setDocuments(rows);
    } catch (error) {
      if (
        request.signal.aborted ||
        !loadTracker.current.isCurrent(request.sequence)
      ) {
        return;
      }
      setLoadError(error instanceof Error ? error.message : "无法读取文献库");
    } finally {
      if (loadTracker.current.isCurrent(request.sequence)) {
        setLoading(false);
        loadTracker.current.finish(request.sequence);
      }
    }
  }, [page, query, sourceStatus]);

  useEffect(() => {
    if (!mayManageSources) {
      setLoading(false);
      setDocuments([]);
      setProjectOptions([]);
      return;
    }
    const tracker = loadTracker.current;
    const timer = window.setTimeout(() => void loadDocuments(), 250);
    return () => {
      window.clearTimeout(timer);
      tracker.cancel();
    };
  }, [mayManageSources, loadDocuments]);

  useEffect(() => {
    if (!mayManageSources) return;
    void listResearchProjects()
      .then((items) =>
        setProjectOptions(items.filter((item) => !item.archived)),
      )
      .catch((error: unknown) => {
        setActionError(
          error instanceof Error ? error.message : "无法读取研究项目",
        );
      });
  }, [mayManageSources]);

  const visibleDocuments = useMemo(() => documents, [documents]);

  useEffect(() => {
    const pending = documents.filter(
      (document) =>
        document.ingestionJobId &&
        (document.status === "pending" || document.status === "running"),
    );
    if (!mayManageSources || pending.length === 0) return;
    let active = true;
    const timer = window.setTimeout(() => {
      void (async () => {
        const results = await Promise.allSettled(
          pending.map((document) =>
            getIngestionJob(
              document.documentId,
              document.sourceFileId,
              document.ingestionJobId!,
            ),
          ),
        );
        if (!active) return;
        const updates = new Map(
          results.flatMap((result) =>
            result.status === "fulfilled"
              ? [[result.value.id, result.value] as const]
              : [],
          ),
        );
        setDocuments((current) =>
          current.map((item) => {
            const job = item.ingestionJobId
              ? updates.get(item.ingestionJobId)
              : undefined;
            return job
              ? { ...item, ingestionJob: job, status: job.status }
              : item;
          }),
        );
        if (
          [...updates.values()].some(
            (job) => job.status !== "pending" && job.status !== "running",
          )
        ) {
          void loadDocuments();
        }
        const failure = results.find((result) => result.status === "rejected");
        if (failure?.status === "rejected")
          setActionError(
            failure.reason instanceof Error
              ? failure.reason.message
              : "无法读取图谱生成进度",
          );
      })();
    }, 2000);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [documents, mayManageSources, loadDocuments]);

  async function generateGraph(document: LibraryDocument) {
    setGraphBusy(document.id);
    setActionError(null);
    setGraphNotice("");
    try {
      const job = await generateSourceGraph(
        document.documentId,
        document.sourceFileId,
      );
      setDocuments((current) =>
        current.map((item) =>
          item.id === document.id
            ? {
                ...item,
                ingestionJobId: job.id,
                ingestionJob: job,
                status: job.status,
              }
            : item,
        ),
      );
      setGraphNotice(
        "已提交自动解析与图谱生成任务。处理完成后，关系网会自动更新并保留待复核标记。",
      );
    } catch (error) {
      setActionError(
        error instanceof Error ? error.message : "无法启动图谱生成",
      );
    } finally {
      setGraphBusy(null);
    }
  }

  function addUploadedFile(result: SourceUploadResult) {
    const file = result.file;
    const source = sources.find((item) => item.id === file.document_id);
    if (!source) {
      void loadDocuments();
      return;
    }
    const today = new Intl.DateTimeFormat("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date());
    const next = {
      id: file.id,
      title: file.original_filename,
      type: file.original_filename.split(".").pop()?.toUpperCase() ?? "文件",
      size: readableSize(file.size),
      status: result.ingestionJob?.status ?? null,
      ingestionJob: result.ingestionJob,
      reviewStatus: null,
      addedAt: today,
      note: "",
      documentId: file.document_id,
      sourceFileId: file.id,
      ingestionJobId: result.ingestionJob?.id,
      source,
    };
    setDocuments((current) =>
      current.some((document) => document.id === next.id)
        ? current
        : [next, ...current],
    );
  }

  function toggleSelected(id: string) {
    setSelected((current) =>
      current.includes(id)
        ? current.filter((item) => item !== id)
        : [...current, id],
    );
  }

  async function transferSelected() {
    if (!selectedProjectId) return;
    setActionError(null);
    setTransferring(true);
    try {
      const selectedDocuments = documents.filter((document) =>
        selected.includes(document.id),
      );
      await Promise.all(
        selectedDocuments.map((document) =>
          addDocumentToResearchProject(selectedProjectId, document.documentId),
        ),
      );
      setSelected([]);
    } catch (error) {
      setActionError(
        error instanceof Error ? error.message : "无法将文献加入研究项目",
      );
    } finally {
      setTransferring(false);
    }
  }

  if (!mayManageSources) {
    return (
      <main className="size-full overflow-y-auto bg-[#f7fafb] text-[#202b2e]">
        <BusinessMobileHeader title="文献库" />
        <div className="mx-auto min-h-full max-w-7xl px-4 py-7 sm:px-8 lg:px-10 lg:py-10">
          <BusinessPageHeader
            title="文献库"
            description="管理地方志、碑刻、档案与研究资料"
            icon={BookOpen}
          />
          <BusinessEmptyState
            icon={ShieldAlert}
            title="仅管理员可管理文献"
            description="当前账号是普通用户，不能登记来源、上传文件、复核或发布知识版本。请使用管理员账号登录；已发布资料仍可通过文史检索查看。"
            className="mt-6 min-h-[440px] border-t border-[#dbe4e5]"
          />
        </div>
      </main>
    );
  }

  return (
    <main className="size-full overflow-y-auto bg-[#f7fafb] text-[#202b2e]">
      <BusinessMobileHeader title="文献库" />

      <div className="mx-auto min-h-full max-w-7xl px-4 py-7 sm:px-8 lg:px-10 lg:py-10">
        <BusinessPageHeader
          title="文献库"
          description="管理地方志、碑刻、档案与研究资料"
          icon={BookOpen}
          actions={
            <>
              <button
                type="button"
                onClick={() => setCorpusImportsOpen(true)}
                className="flex h-10 items-center gap-2 rounded-md border border-[#80adb4] bg-white px-4 text-sm text-[#245e67] hover:bg-[#edf4f5]"
              >
                <Import className="size-4" />
                导入批次
              </button>
              <button
                type="button"
                onClick={() => setReleaseOpen(true)}
                className="flex h-10 items-center gap-2 rounded-md border border-[#80adb4] bg-white px-4 text-sm text-[#245e67] hover:bg-[#edf4f5]"
              >
                <PackageCheck className="size-4" />
                知识版本{selected.length > 0 ? ` (${selected.length})` : ""}
              </button>
              <select
                value={selectedProjectId}
                onChange={(event) => setSelectedProjectId(event.target.value)}
                className="h-10 rounded-md border px-2 text-sm"
                aria-label="目标研究项目"
              >
                <option value="">选择目标项目</option>
                {projectOptions.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => setUploadOpen(true)}
                className="flex h-10 items-center gap-2 rounded-md bg-[#202b2e] px-4 text-sm text-white hover:bg-[#354347]"
              >
                <FileUp className="size-4" />
                上传文献
              </button>
              <button
                type="button"
                aria-pressed={showNotes}
                onClick={() => setShowNotes((current) => !current)}
                className="flex h-10 items-center gap-2 rounded-md border border-[#cedadd] bg-white px-4 text-sm hover:bg-[#edf4f5]"
              >
                <Plus className="size-4" />
                {showNotes ? "移除备注字段" : "添加备注字段"}
              </button>
              <button
                type="button"
                disabled={
                  selected.length === 0 || !selectedProjectId || transferring
                }
                onClick={() => void transferSelected()}
                className="flex h-10 items-center gap-2 rounded-md border border-[#80adb4] bg-[#e2eff0] px-4 text-sm text-[#245e67] hover:bg-[#d6e9eb] disabled:cursor-not-allowed disabled:opacity-40"
              >
                <ArrowRightLeft className="size-4" />
                {transferring ? "正在转入…" : "转入项目"}
                {!transferring && selected.length > 0
                  ? ` (${selected.length})`
                  : ""}
              </button>
            </>
          }
        />

        {actionError && (
          <div className="mt-4">
            <BusinessInlineError
              message={actionError}
              onDismiss={() => setActionError(null)}
            />
          </div>
        )}

        <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-[#66777c]">共 {documents.length} 份文献</p>
          <label className="flex h-10 w-full max-w-sm items-center gap-2 rounded-md border border-[#d2dddf] bg-white px-3 text-[#67787c] focus-within:border-[#6ea7af]">
            <Search className="size-4 shrink-0" />
            <input
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setPage(1);
              }}
              placeholder="搜索标题或文件名"
              className="min-w-0 flex-1 bg-transparent text-sm text-[#243236] outline-none placeholder:text-[#95a1a4]"
            />
          </label>
          <select
            value={sourceStatus}
            onChange={(event) => {
              setSourceStatus(
                event.target.value as SourceDocumentStatus | "all",
              );
              setPage(1);
            }}
            aria-label="资料状态"
            className="h-10 rounded-md border border-[#d2dddf] bg-white px-3 text-sm"
          >
            <option value="all">全部资料状态</option>
            <option value="registered">已登记</option>
            <option value="archived">已归档</option>
          </select>
        </div>

        <p className="mt-4 text-xs text-[#68797e]">
          文本复核检查文献页与片段；知识图谱中的关系复核单独记录。
        </p>
        <div className="mt-2 overflow-x-auto rounded-md border border-[#d7e1e2] bg-white">
          <div
            className="grid min-w-[1180px] grid-cols-[48px_minmax(240px,1fr)_70px_70px_100px_170px_100px_270px] items-center border-b border-[#dce5e6] bg-[#f1f6f7] px-3 py-3 text-xs font-medium text-[#607176]"
            style={
              showNotes
                ? {
                    gridTemplateColumns:
                      "48px minmax(240px,1fr) 70px 70px 100px 170px minmax(180px,.65fr) 100px 270px",
                  }
                : undefined
            }
          >
            <span />
            <span>标题</span>
            <span>类型</span>
            <span>大小</span>
            <span>文本复核</span>
            <span>入库处理</span>
            {showNotes && <span>备注</span>}
            <span>添加时间</span>
            <span>操作</span>
          </div>

          {graphNotice && (
            <p role="status" className="px-4 py-3 text-sm text-[#286846]">
              {graphNotice}{" "}
              <Link href="/workspace/knowledge-graph" className="underline">
                查看关系图谱
              </Link>
            </p>
          )}
          <div>
            {loading ? (
              <BusinessLoadingState label="正在读取文献库…" />
            ) : loadError ? (
              <BusinessErrorState
                description={loadError}
                onRetry={() => void loadDocuments()}
              />
            ) : visibleDocuments.length === 0 ? (
              <BusinessEmptyState
                icon={FileText}
                title={query ? "未找到匹配文献" : "文献库暂无资料"}
                description={
                  query
                    ? "尝试更换关键词，或清空搜索条件。"
                    : "上传地方志、碑刻拓片、档案或研究文献，建立可追溯的资料基础。"
                }
                action={
                  !query ? (
                    <button
                      type="button"
                      onClick={() => setUploadOpen(true)}
                      className="mt-5 flex h-9 items-center gap-2 rounded-md border border-[#87afb5] px-4 text-sm text-[#286873] hover:bg-[#edf5f5]"
                    >
                      <FileUp className="size-4" />
                      选择文件
                    </button>
                  ) : undefined
                }
              />
            ) : (
              visibleDocuments.map((document) => (
                <div
                  key={document.id}
                  className="grid min-w-[1180px] grid-cols-[48px_minmax(240px,1fr)_70px_70px_100px_170px_100px_270px] items-center border-b border-[#edf1f2] px-3 py-3 text-sm last:border-b-0"
                  style={
                    showNotes
                      ? {
                          gridTemplateColumns:
                            "48px minmax(240px,1fr) 70px 70px 100px 170px minmax(180px,.65fr) 100px 270px",
                        }
                      : undefined
                  }
                >
                  <input
                    type="checkbox"
                    checked={selected.includes(document.id)}
                    onChange={() => toggleSelected(document.id)}
                    aria-label={`选择 ${document.title}`}
                    className="size-4 accent-[#247f8c]"
                  />
                  <span className="flex min-w-0 items-center gap-2">
                    <FileText className="size-4 shrink-0 text-[#568087]" />
                    <span className="min-w-0">
                      <span
                        className="block truncate font-medium"
                        title={document.title}
                      >
                        {document.title}
                      </span>
                      <span
                        className="block truncate text-xs text-[#78878b]"
                        title={`${document.source.title} · ${document.source.edition ?? "版本未详"}`}
                      >
                        {document.source.title} ·{" "}
                        {document.source.edition ?? "版本未详"}
                      </span>
                    </span>
                  </span>
                  <span className="text-[#68797e]">{document.type}</span>
                  <span className="text-[#68797e]">{document.size}</span>
                  <SourceTextReviewStatus status={document.reviewStatus} />
                  <SourceProcessingStatus job={document.ingestionJob} />
                  {showNotes && (
                    <input
                      value={document.note}
                      onChange={(event) =>
                        setDocuments((current) =>
                          current.map((item) =>
                            item.id === document.id
                              ? { ...item, note: event.target.value }
                              : item,
                          ),
                        )
                      }
                      placeholder="添加备注"
                      className="mr-4 min-w-0 rounded border border-[#d8e2e3] px-2 py-1.5 text-xs outline-none focus:border-[#74aab1]"
                    />
                  )}
                  <span className="text-xs text-[#78878b]">
                    {document.addedAt}
                  </span>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      disabled={
                        graphBusy !== null ||
                        document.status === "pending" ||
                        document.status === "running"
                      }
                      title="允许内部解析文献、抽取主体与关系，生成待复核图谱"
                      onClick={() => void generateGraph(document)}
                      className="flex h-8 shrink-0 items-center gap-1 rounded-md border border-[#8aafb4] px-2 text-xs text-[#275f68] hover:bg-[#edf5f5] disabled:opacity-40"
                    >
                      <Network className="size-3.5" />
                      {graphBusy === document.id
                        ? "提交中"
                        : document.status === "failed" &&
                            !TEMPORARY_LIBRARY_SUCCESS_PREVIEW
                          ? "重试处理"
                          : "生成图谱"}
                    </button>
                    <button
                      type="button"
                      title="编辑资料信息"
                      aria-label="编辑资料信息"
                      onClick={() => setEditSource(document.source)}
                      className="flex size-8 items-center justify-center rounded-md text-[#526b70] hover:bg-[#edf5f5]"
                    >
                      <Pencil className="size-3.5" />
                    </button>
                    <button
                      type="button"
                      title="上传新版本"
                      onClick={() => setVersionDocument(document)}
                      className="flex size-8 items-center justify-center rounded-md text-[#526b70] hover:bg-[#edf5f5]"
                    >
                      <GitBranch className="size-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => setReviewDocument(document)}
                      className="flex h-8 w-fit items-center gap-1.5 rounded-md border border-[#8aafb4] px-2.5 text-xs text-[#275f68] hover:bg-[#edf5f5]"
                    >
                      <ClipboardCheck className="size-3.5" />
                      复核
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
        {totalSources > 10 && (
          <div className="mt-4 flex items-center justify-end gap-3 text-sm">
            <span>
              第 {page} / {Math.ceil(totalSources / 10)} 页，共 {totalSources}{" "}
              个来源
            </span>
            <button
              type="button"
              disabled={page === 1}
              onClick={() => setPage((value) => value - 1)}
              className="h-8 rounded-md border px-3 disabled:opacity-40"
            >
              上一页
            </button>
            <button
              type="button"
              disabled={page * 10 >= totalSources}
              onClick={() => setPage((value) => value + 1)}
              className="h-8 rounded-md border px-3 disabled:opacity-40"
            >
              下一页
            </button>
          </div>
        )}
      </div>
      <SourceUploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        onUploaded={addUploadedFile}
      />
      <CorpusImportDialog
        open={corpusImportsOpen}
        onOpenChange={setCorpusImportsOpen}
      />
      {versionDocument && (
        <SourceUploadDialog
          open
          onOpenChange={(nextOpen) => {
            if (!nextOpen) setVersionDocument(null);
          }}
          onUploaded={(result) => {
            addUploadedFile(result);
            setVersionDocument(null);
          }}
          initialSourceId={versionDocument.documentId}
          versionOfFileId={versionDocument.sourceFileId}
        />
      )}
      {editSource && (
        <SourceEditDialog
          source={editSource}
          open
          onOpenChange={(nextOpen) => {
            if (!nextOpen) setEditSource(null);
          }}
          onSaved={(updated) => {
            setSources((current) =>
              current.map((source) =>
                source.id === updated.id ? updated : source,
              ),
            );
            setDocuments((current) =>
              current.map((document) =>
                document.documentId === updated.id
                  ? { ...document, source: updated }
                  : document,
              ),
            );
          }}
        />
      )}
      <KnowledgeReleaseDialog
        open={releaseOpen}
        onOpenChange={setReleaseOpen}
        candidates={documents
          .filter((document) => selected.includes(document.id))
          .map((document) => ({
            title: document.title,
            documentId: document.documentId,
            fileId: document.sourceFileId,
          }))}
      />
      {evidenceId && (
        <EvidenceDetailPanel
          evidenceId={evidenceId}
          onClose={() => {
            const params = new URLSearchParams(searchParams.toString());
            params.delete("evidence_id");
            const query = params.toString();
            router.replace(
              query ? `/workspace/library?${query}` : "/workspace/library",
            );
          }}
        />
      )}
      {reviewDocument && (
        <SourceReviewDialog
          open
          onOpenChange={(nextOpen) => {
            if (!nextOpen) setReviewDocument(null);
          }}
          documentId={reviewDocument.documentId}
          fileId={reviewDocument.sourceFileId}
          title={reviewDocument.title}
          ingestionJobId={reviewDocument.ingestionJobId}
          onReviewed={() => void loadDocuments()}
          onFinalized={() => void loadDocuments()}
        />
      )}
    </main>
  );
}
