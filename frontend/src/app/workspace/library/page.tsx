"use client";

import {
  ArrowRightLeft,
  BookOpen,
  ClipboardCheck,
  FileText,
  FileUp,
  GitBranch,
  Import,
  PackageCheck,
  Pencil,
  Plus,
  Search,
  ShieldAlert,
} from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  WorkbenchMetrics,
  WorkbenchGuide,
  LibraryReleaseSummary,
} from "@/components/workspace/admin-workbench";
import {
  BusinessEmptyState,
  BusinessErrorState,
  BusinessInlineError,
  BusinessLoadingState,
  BusinessMobileHeader,
  BusinessPageHeader,
  BusinessStatusBadge,
} from "@/components/workspace/business-page";
import { EvidenceDetailPanel } from "@/components/workspace/citations/evidence-detail-panel";
import { CorpusImportDialog } from "@/components/workspace/corpus-import-dialog";
import { KnowledgeReleaseDialog } from "@/components/workspace/knowledge-release-dialog";
import { SourceEditDialog } from "@/components/workspace/source-edit-dialog";
import { SourceReviewDialog } from "@/components/workspace/source-review-dialog";
import { SourceUploadDialog } from "@/components/workspace/source-upload-dialog";
import { useAuth } from "@/core/auth/AuthProvider";
import { canManageSourceDocuments } from "@/core/auth/permissions";
import { type BusinessStatus } from "@/core/presentation/business-status";
import {
  addDocumentToResearchProject,
  listResearchProjects,
} from "@/core/projects/api";
import {
  type IngestionJobStatus,
  pageSourceDocumentLibrary,
  type SourceDocumentStatus,
  type SourceDocumentSummary,
  type SourceUploadResult,
} from "@/core/source-files/api";
import { createLatestRequestTracker } from "@/core/source-files/latest-request";

const sourceTypeLabels = {
  gazetteer: "地方志",
  inscription: "碑刻",
  archive: "档案",
  heritage_record: "文保记录",
  scholarly_work: "研究著作",
  oral_history: "口述史",
  web: "网络资料",
  inference: "推断资料",
  other: "其他资料",
};

type LibraryDocument = {
  id: string;
  title: string;
  type: string;
  size: string;
  status: BusinessStatus;
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
  if (!job) return "pending";
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
  const [uploadSourceId, setUploadSourceId] = useState<string | undefined>();
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
  const loadTracker = useRef(createLatestRequestTracker());

  async function loadDocuments() {
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
          ({ file, ingestion_job: latestJob }) =>
            ({
              id: file.id,
              title: file.original_filename ?? source.title,
              type:
                file.original_filename.split(".").pop()?.toUpperCase() ??
                "文件",
              size: readableSize(file.size),
              status: documentStatus(latestJob),
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
  }

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
    // loadDocuments is intentionally recreated from the current paging filters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mayManageSources, page, query, sourceStatus]);

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
      status: (result.ingestionJob?.status ?? "pending") as BusinessStatus,
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
      setDocuments((current) =>
        current.map((document) =>
          selected.includes(document.id)
            ? { ...document, status: "in_project" }
            : document,
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
      <main className="admin-workspace size-full overflow-y-auto">
        <BusinessMobileHeader title="文献库" />
        <div className="admin-workbench mx-auto min-h-full max-w-7xl px-4 py-7 sm:px-8 lg:px-10 lg:py-10">
          <BusinessPageHeader
            title="文献库"
            description="管理地方志、碑刻、档案与研究资料"
            icon={BookOpen}
          />
          <BusinessEmptyState
            icon={ShieldAlert}
            title="仅管理员可管理文献"
            description="当前账号是普通用户，不能登记来源、上传文件、复核或发布知识版本。请使用管理员账号登录；已发布资料仍可通过文史检索查看。"
            className="border-border mt-6 min-h-[440px] border-t"
          />
        </div>
      </main>
    );
  }

  return (
    <main className="admin-workspace size-full overflow-y-auto">
      <BusinessMobileHeader title="文献库" />
      <div className="admin-workbench min-h-full px-4 py-7 sm:px-8 lg:px-10 lg:py-9">
        <WorkbenchGuide
          title="文献入藏与校勘"
          steps={["登记来源", "原件与 OCR", "逐页校勘", "审核后发布"]}
        />
        <BusinessPageHeader
          title="文献库"
          description="古籍有本，考据有源。整理地方志、碑刻与档案，核对每一页文字。"
          icon={BookOpen}
          actions={
            <>
              <button
                type="button"
                onClick={() => setCorpusImportsOpen(true)}
                className="admin-action"
              >
                <Import className="size-4" />
                导入批次
              </button>
              <button
                type="button"
                onClick={() => setReleaseOpen(true)}
                className="admin-action"
              >
                <PackageCheck className="size-4" />
                知识版本{selected.length > 0 ? ` (${selected.length})` : ""}
              </button>
              <button
                type="button"
                onClick={() => {
                  setUploadSourceId(undefined);
                  setUploadOpen(true);
                }}
                className="admin-action admin-primary"
              >
                <FileUp className="size-4" />
                上传文献
              </button>
            </>
          }
        />
        <div className="my-6">
          <WorkbenchMetrics
            items={[
              {
                label: "匹配来源",
                value: loading || loadError ? null : totalSources,
                hint: "服务端目录 · 随搜索与资料状态变化",
              },
              {
                label: "本页原件",
                value: loading || loadError ? null : documents.length,
                hint: "当前来源页已上传的文件",
              },
              {
                label: "本页待复核",
                value:
                  loading || loadError
                    ? null
                    : documents.filter(
                        (item) => item.status === "awaiting_review",
                      ).length,
                hint: "导入流程已到人工复核阶段",
              },
              {
                label: "本页已完成",
                value:
                  loading || loadError
                    ? null
                    : documents.filter((item) => item.status === "completed")
                        .length,
                hint: "流程完成不等于已发布",
              },
            ]}
          />
        </div>
        <LibraryReleaseSummary refreshKey={releaseOpen ? 1 : 0} />
        {actionError && (
          <BusinessInlineError
            message={actionError}
            onDismiss={() => setActionError(null)}
          />
        )}
        <section
          className="bg-card mb-5 flex flex-wrap items-center gap-3 rounded-xl border p-4"
          aria-label="目录检索与批量操作"
        >
          <label className="bg-background flex min-h-11 min-w-0 flex-1 items-center gap-2 rounded-lg border px-3">
            <Search className="text-muted-foreground size-4" />
            <input
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setPage(1);
              }}
              aria-label="搜索标题或文件名"
              placeholder="搜索标题或文件名"
              className="min-w-0 flex-1 bg-transparent text-sm outline-none"
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
            className="admin-field"
          >
            <option value="all">全部资料状态</option>
            <option value="registered">已登记</option>
            <option value="archived">已归档</option>
          </select>
          <button
            type="button"
            aria-pressed={showNotes}
            onClick={() => setShowNotes((current) => !current)}
            className="admin-action"
          >
            <Plus className="size-4" />
            {showNotes ? "移除备注字段" : "添加备注字段"}
          </button>
          <div className="flex w-full flex-wrap items-center gap-2 border-t pt-3">
            <span className="text-muted-foreground mr-auto text-xs">
              已选 {selected.length} 份原件 · 来源等级与复核状态独立记录
            </span>
            <select
              value={selectedProjectId}
              onChange={(event) => setSelectedProjectId(event.target.value)}
              className="admin-field max-w-full"
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
              disabled={
                selected.length === 0 || !selectedProjectId || transferring
              }
              onClick={() => void transferSelected()}
              className="admin-action"
            >
              <ArrowRightLeft className="size-4" />
              {transferring ? "正在转入…" : "转入项目"}
              {!transferring && selected.length ? ` (${selected.length})` : ""}
            </button>
          </div>
        </section>
        {loading ? (
          <BusinessLoadingState label="正在读取文献库…" />
        ) : loadError ? (
          <BusinessErrorState
            description={loadError}
            onRetry={() => void loadDocuments()}
          />
        ) : sources.length === 0 ? (
          <BusinessEmptyState
            icon={FileText}
            title={query ? "未找到匹配文献" : "文献库暂无资料"}
            description={
              query
                ? "尝试更换关键词，或清空搜索条件。"
                : "先登记文献来源，再上传原件，开始逐页校勘。"
            }
            action={
              !query ? (
                <button
                  type="button"
                  onClick={() => setUploadOpen(true)}
                  className="admin-action mt-5"
                >
                  <FileUp className="size-4" />
                  选择文件
                </button>
              ) : undefined
            }
          />
        ) : (
          <div className="library-catalog" aria-label="古籍方志目录">
            {visibleDocuments.map((document) => (
              <article
                key={document.id}
                className="library-volume"
                data-library-file={document.id}
              >
                <div className="mb-4 flex items-start justify-between gap-3">
                  <label className="flex min-h-11 items-center gap-2">
                    <input
                      type="checkbox"
                      checked={selected.includes(document.id)}
                      onChange={() => toggleSelected(document.id)}
                      aria-label={`选择 ${document.title}`}
                      className="accent-primary size-4"
                    />
                    <span className="text-muted-foreground text-xs">
                      {document.type} · {document.size}
                    </span>
                  </label>
                  <BusinessStatusBadge status={document.status} />
                </div>
                <div className="library-bookmark">
                  <p className="text-primary mb-2 text-xs">
                    {document.source.source_type_label ??
                      sourceTypeLabels[document.source.source_type]}{" "}
                    · 来源等级 {document.source.source_level}
                  </p>
                  <h2 className="font-serif text-lg leading-7 font-semibold break-words">
                    {document.source.title}
                  </h2>
                  <p className="text-muted-foreground mt-2 text-xs">
                    {document.source.edition || "版本待核"} ·{" "}
                    {document.source.source_institution || "馆藏待登记"}
                  </p>
                </div>
                <p
                  className="text-muted-foreground mt-4 truncate text-xs"
                  title={document.title}
                >
                  {document.title}
                </p>
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
                    className="admin-field mt-3 w-full"
                  />
                )}
                <footer className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t pt-3">
                  <span className="text-muted-foreground text-xs">
                    入藏 {document.addedAt}
                  </span>
                  <div className="flex flex-wrap gap-1">
                    <button
                      type="button"
                      title="编辑资料信息"
                      aria-label={`编辑资料信息 ${document.title}`}
                      onClick={() => setEditSource(document.source)}
                      className="admin-icon"
                    >
                      <Pencil className="size-4" />
                    </button>
                    <button
                      type="button"
                      title="上传新版本"
                      aria-label={`上传新版本 ${document.title}`}
                      onClick={() => setVersionDocument(document)}
                      className="admin-icon"
                    >
                      <GitBranch className="size-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => setReviewDocument(document)}
                      className="admin-action"
                    >
                      <ClipboardCheck className="size-4" />
                      复核
                    </button>
                  </div>
                </footer>
              </article>
            ))}
            {sources
              .filter(
                (source) =>
                  !documents.some(
                    (document) => document.documentId === source.id,
                  ),
              )
              .map((source) => (
                <article key={source.id} className="library-volume">
                  <p className="text-muted-foreground mb-3 text-xs">
                    已登记 · 尚无原件
                  </p>
                  <h2 className="font-serif text-lg font-semibold">
                    {source.title}
                  </h2>
                  <p className="text-muted-foreground mt-2 text-sm">
                    {source.edition} · {source.source_institution}
                  </p>
                  <button
                    type="button"
                    className="admin-action mt-5"
                    onClick={() => {
                      setUploadSourceId(source.id);
                      setUploadOpen(true);
                    }}
                  >
                    <FileUp className="size-4" />
                    上传原件
                  </button>
                </article>
              ))}
          </div>
        )}
        {totalSources > 10 && (
          <div className="mt-5 flex flex-wrap items-center justify-end gap-3 text-sm">
            <span>
              第 {page} / {Math.ceil(totalSources / 10)} 页，共 {totalSources}{" "}
              个来源
            </span>
            <button
              type="button"
              disabled={page === 1}
              onClick={() => setPage((value) => value - 1)}
              className="admin-action"
            >
              上一页
            </button>
            <button
              type="button"
              disabled={page * 10 >= totalSources}
              onClick={() => setPage((value) => value + 1)}
              className="admin-action"
            >
              下一页
            </button>
          </div>
        )}
      </div>

      <SourceUploadDialog
        initialSourceId={uploadSourceId}
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
          fileType={reviewDocument.type}
          ingestionJobId={reviewDocument.ingestionJobId}
          onFinalized={() => {
            setDocuments((current) =>
              current.map((document) =>
                document.id === reviewDocument.id
                  ? { ...document, status: "completed" }
                  : document,
              ),
            );
          }}
        />
      )}
    </main>
  );
}
