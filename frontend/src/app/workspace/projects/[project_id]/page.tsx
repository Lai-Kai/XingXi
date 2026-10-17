"use client";

import {
  ArrowLeft,
  BookOpenText,
  Check,
  FilePlus2,
  FileSearch,
  Lightbulb,
  Loader2,
  MessageSquareText,
  NotebookPen,
  Plus,
  Search,
  Sparkles,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  BusinessEmptyState,
  BusinessErrorState,
  BusinessInlineError,
  BusinessLoadingState,
  BusinessMobileHeader,
  BusinessStatusBadge,
} from "@/components/workspace/business-page";
import { searchStructuredKnowledge } from "@/core/knowledge-search/api";
import type { StructuredSearchHit } from "@/core/knowledge-search/types";
import {
  addDocumentToResearchProject,
  createResearchProjectRecord,
  deleteResearchProjectRecord,
  getResearchProject,
  listResearchProjectDocuments,
  listResearchProjectRecords,
  removeDocumentFromResearchProject,
  type ResearchProject,
  type ResearchProjectDocument,
  type ResearchProjectRecord,
  type ResearchRecordKind,
} from "@/core/projects/api";
import {
  pageSourceDocuments,
  type SourceDocumentSummary,
} from "@/core/source-files/api";

const recordKinds: Array<{
  id: ResearchRecordKind;
  label: string;
  placeholder: string;
  icon: typeof Lightbulb;
}> = [
  {
    id: "question",
    label: "研究问题",
    placeholder: "记录接下来需要查证的问题",
    icon: Lightbulb,
  },
  {
    id: "note",
    label: "研究笔记",
    placeholder: "记录阅读发现、线索或待办",
    icon: NotebookPen,
  },
  {
    id: "conclusion",
    label: "阶段结论",
    placeholder: "记录已有资料出处支持的阶段性结论",
    icon: Check,
  },
];

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(value));
}

function recordLabel(kind: ResearchRecordKind) {
  return recordKinds.find((item) => item.id === kind)?.label ?? kind;
}

export default function ResearchProjectWorkspacePage() {
  const params = useParams<{ project_id: string }>();
  const projectId = decodeURIComponent(params.project_id);
  const [project, setProject] = useState<ResearchProject | null>(null);
  const [documents, setDocuments] = useState<ResearchProjectDocument[]>([]);
  const [records, setRecords] = useState<ResearchProjectRecord[]>([]);
  const [availableDocuments, setAvailableDocuments] = useState<
    SourceDocumentSummary[]
  >([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [documentDialogOpen, setDocumentDialogOpen] = useState(false);
  const [documentQuery, setDocumentQuery] = useState("");
  const [addingDocumentId, setAddingDocumentId] = useState<string | null>(null);
  const [removingDocumentId, setRemovingDocumentId] = useState<string | null>(
    null,
  );
  const [recordKind, setRecordKind] = useState<ResearchRecordKind>("question");
  const [recordContent, setRecordContent] = useState("");
  const [savingRecord, setSavingRecord] = useState(false);
  const [deletingRecordId, setDeletingRecordId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchMessage, setSearchMessage] = useState("");
  const [searchHits, setSearchHits] = useState<StructuredSearchHit[]>([]);

  const loadWorkspace = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [nextProject, nextDocuments, nextRecords, sourcePage] =
        await Promise.all([
          getResearchProject(projectId),
          listResearchProjectDocuments(projectId),
          listResearchProjectRecords(projectId),
          pageSourceDocuments({ page: 1, pageSize: 100, status: "registered" }),
        ]);
      setProject(nextProject);
      setDocuments(nextDocuments);
      setRecords(nextRecords);
      setAvailableDocuments(sourcePage.items);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "无法读取研究项目");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void loadWorkspace();
  }, [loadWorkspace]);

  const documentIds = useMemo(
    () => new Set(documents.map((document) => document.id)),
    [documents],
  );
  const selectableDocuments = useMemo(() => {
    const query = documentQuery.trim().toLocaleLowerCase("zh-CN");
    return availableDocuments.filter(
      (document) =>
        !documentIds.has(document.id) &&
        (!query ||
          document.title.toLocaleLowerCase("zh-CN").includes(query) ||
          document.edition.toLocaleLowerCase("zh-CN").includes(query)),
    );
  }, [availableDocuments, documentIds, documentQuery]);

  async function addDocument(document: SourceDocumentSummary) {
    setAddingDocumentId(document.id);
    setActionError(null);
    try {
      await addDocumentToResearchProject(projectId, document.id);
      const nextDocuments = await listResearchProjectDocuments(projectId);
      setDocuments(nextDocuments);
      setProject((current) =>
        current
          ? { ...current, document_count: nextDocuments.length }
          : current,
      );
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "无法添加文献");
    } finally {
      setAddingDocumentId(null);
    }
  }

  async function removeDocument(documentId: string) {
    setRemovingDocumentId(documentId);
    setActionError(null);
    try {
      await removeDocumentFromResearchProject(projectId, documentId);
      setDocuments((current) =>
        current.filter((document) => document.id !== documentId),
      );
      setProject((current) =>
        current
          ? {
              ...current,
              document_count: Math.max(0, (current.document_count ?? 1) - 1),
            }
          : current,
      );
      setSearchHits([]);
      setSearchMessage("");
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "无法移除文献");
    } finally {
      setRemovingDocumentId(null);
    }
  }

  async function addRecord() {
    const content = recordContent.trim();
    if (!content) return;
    setSavingRecord(true);
    setActionError(null);
    try {
      const created = await createResearchProjectRecord(
        projectId,
        recordKind,
        content,
      );
      setRecords((current) => [created, ...current]);
      setRecordContent("");
    } catch (error) {
      setActionError(
        error instanceof Error ? error.message : "无法保存研究记录",
      );
    } finally {
      setSavingRecord(false);
    }
  }

  async function deleteRecord(recordId: string) {
    setDeletingRecordId(recordId);
    setActionError(null);
    try {
      await deleteResearchProjectRecord(projectId, recordId);
      setRecords((current) =>
        current.filter((record) => record.id !== recordId),
      );
    } catch (error) {
      setActionError(
        error instanceof Error ? error.message : "无法删除研究记录",
      );
    } finally {
      setDeletingRecordId(null);
    }
  }

  async function searchProject() {
    const query = searchQuery.trim();
    if (!query || documents.length === 0) return;
    setSearching(true);
    setActionError(null);
    setSearchMessage("");
    try {
      const result = await searchStructuredKnowledge({
        query,
        filters: { document_ids: documents.map((document) => document.id) },
        page_size: 8,
      });
      setSearchHits(result.hits);
      setSearchMessage(result.message);
    } catch (error) {
      setSearchHits([]);
      setActionError(error instanceof Error ? error.message : "项目内检索失败");
    } finally {
      setSearching(false);
    }
  }

  if (loading) {
    return (
      <main className="admin-workspace bg-background size-full overflow-y-auto">
        <BusinessMobileHeader title="研究项目" />
        <BusinessLoadingState label="正在读取项目工作区…" />
      </main>
    );
  }

  if (loadError || !project) {
    return (
      <main className="admin-workspace bg-background size-full overflow-y-auto">
        <BusinessMobileHeader title="研究项目" />
        <BusinessErrorState
          description={loadError ?? "研究项目不存在"}
          onRetry={() => void loadWorkspace()}
        />
      </main>
    );
  }

  const agentParams = new URLSearchParams({
    project_id: project.id,
    prompt: `请围绕“${project.name}”开展研究，仅使用本项目关联文献检索资料出处。`,
  });

  return (
    <main className="admin-workspace bg-background text-foreground size-full overflow-y-auto">
      <BusinessMobileHeader title={project.name} />
      <div className="mx-auto min-h-full max-w-7xl px-4 py-7 sm:px-8 lg:px-10 lg:py-10">
        <Link
          href="/workspace/projects"
          className="text-muted-foreground hover:text-primary inline-flex items-center gap-2 text-sm"
        >
          <ArrowLeft className="size-4" />
          返回研究项目
        </Link>

        <header className="border-border mt-5 flex flex-col justify-between gap-5 border-b pb-7 md:flex-row md:items-end">
          <div>
            <div className="flex items-center gap-3">
              <span className="bg-secondary text-primary flex size-11 items-center justify-center rounded-md">
                <BookOpenText className="size-5" />
              </span>
              <div>
                <h1 className="text-2xl font-semibold sm:text-3xl">
                  {project.name}
                </h1>
                <p className="text-muted-foreground mt-1 text-sm">
                  {documents.length} 份文献 · {records.length} 条研究记录 ·
                  创建于 {formatDate(project.created_at)}
                </p>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              onClick={() => setDocumentDialogOpen(true)}
            >
              <FilePlus2 className="size-4" />
              添加文献
            </Button>
            <Button asChild disabled={documents.length === 0}>
              <Link href={`/workspace/chats/new?${agentParams.toString()}`}>
                <Sparkles className="size-4" />
                用项目文献研究
              </Link>
            </Button>
          </div>
        </header>

        {actionError && (
          <div className="mt-4">
            <BusinessInlineError
              message={actionError}
              onDismiss={() => setActionError(null)}
            />
          </div>
        )}

        <section className="border-border mt-8 border-b pb-9">
          <div className="flex items-center gap-2">
            <FileSearch className="text-primary size-5" />
            <h2 className="text-lg font-medium">项目内检索</h2>
            <BusinessStatusBadge status="active" />
          </div>
          <div className="mt-4 flex max-w-3xl gap-2">
            <Input
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void searchProject();
              }}
              placeholder={
                documents.length
                  ? "输入人物、地点、事件或史料原文"
                  : "请先向项目添加文献"
              }
              disabled={documents.length === 0 || searching}
            />
            <Button
              onClick={() => void searchProject()}
              disabled={
                !searchQuery.trim() || documents.length === 0 || searching
              }
              title="在项目文献中检索"
            >
              {searching ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Search className="size-4" />
              )}
              检索
            </Button>
          </div>
          {(searchMessage || searchHits.length > 0) && (
            <div className="mt-5 max-w-4xl space-y-3">
              {searchMessage && (
                <p className="text-muted-foreground text-sm">{searchMessage}</p>
              )}
              {searchHits.map((hit) => (
                <article
                  key={hit.citation.evidence_id}
                  className="border-border bg-card rounded-md border p-4"
                >
                  <div className="text-muted-foreground flex flex-wrap items-center justify-between gap-2 text-xs">
                    <span>
                      {hit.citation.document_title}
                      {hit.citation.edition ? ` · ${hit.citation.edition}` : ""}
                    </span>
                    <span>
                      第 {hit.citation.page_start}
                      {hit.citation.page_end !== hit.citation.page_start
                        ? `-${hit.citation.page_end}`
                        : ""}{" "}
                      页
                    </span>
                  </div>
                  <p className="text-foreground mt-2 text-sm leading-7">
                    {hit.citation.quote}
                  </p>
                  <Link
                    href={`/workspace/library?evidence_id=${encodeURIComponent(hit.citation.evidence_id)}`}
                    className="text-primary hover:text-primary mt-3 inline-flex text-xs font-medium"
                  >
                    查看关联资料出处
                  </Link>
                </article>
              ))}
            </div>
          )}
        </section>

        <div className="grid gap-10 py-8 lg:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.65fr)]">
          <section>
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-medium">项目文献</h2>
                <p className="text-muted-foreground mt-1 text-sm">
                  检索和智能体研究只使用这里关联的文献。
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setDocumentDialogOpen(true)}
              >
                <Plus className="size-4" />
                添加
              </Button>
            </div>
            {documents.length === 0 ? (
              <BusinessEmptyState
                icon={BookOpenText}
                title="项目还没有文献"
                description="添加文献后，可以限定范围检索并启动智能体研究。"
                className="border-border mt-5 min-h-72 border-t"
                action={
                  <Button
                    variant="outline"
                    onClick={() => setDocumentDialogOpen(true)}
                  >
                    <FilePlus2 className="size-4" />
                    选择文献
                  </Button>
                }
              />
            ) : (
              <div className="mt-5 space-y-3">
                {documents.map((document) => (
                  <article
                    key={document.id}
                    className="border-border bg-card flex items-start justify-between gap-4 rounded-md border p-4"
                  >
                    <div className="min-w-0">
                      <h3 className="text-foreground font-medium">
                        {document.title}
                      </h3>
                      <p className="text-muted-foreground mt-1 text-xs leading-5">
                        {document.edition} · {document.source_institution} ·
                        来源等级 {document.source_level}
                      </p>
                      <p className="text-muted-foreground mt-2 text-xs">
                        加入于 {formatDate(document.added_at)}
                      </p>
                    </div>
                    <button
                      type="button"
                      title="从项目移除"
                      disabled={removingDocumentId === document.id}
                      onClick={() => void removeDocument(document.id)}
                      className="text-muted-foreground hover:bg-accent hover:text-destructive flex size-8 shrink-0 items-center justify-center rounded-md disabled:cursor-wait disabled:opacity-50"
                    >
                      {removingDocumentId === document.id ? (
                        <Loader2 className="size-4 animate-spin" />
                      ) : (
                        <Trash2 className="size-4" />
                      )}
                    </button>
                  </article>
                ))}
              </div>
            )}
          </section>

          <section>
            <div>
              <h2 className="text-lg font-medium">研究记录</h2>
              <p className="text-muted-foreground mt-1 text-sm">
                保存问题、阅读笔记和有资料出处支持的阶段结论。
              </p>
            </div>
            <div className="bg-secondary mt-5 flex gap-1 rounded-md p-1">
              {recordKinds.map((kind) => {
                const Icon = kind.icon;
                return (
                  <button
                    key={kind.id}
                    type="button"
                    onClick={() => setRecordKind(kind.id)}
                    className={`flex h-9 flex-1 items-center justify-center gap-1.5 rounded-md px-2 text-xs ${
                      recordKind === kind.id
                        ? "bg-card text-primary font-medium shadow-sm"
                        : "text-muted-foreground hover:text-primary"
                    }`}
                  >
                    <Icon className="size-3.5" />
                    {kind.label}
                  </button>
                );
              })}
            </div>
            <Textarea
              value={recordContent}
              onChange={(event) => setRecordContent(event.target.value)}
              placeholder={
                recordKinds.find((item) => item.id === recordKind)?.placeholder
              }
              className="bg-card mt-3 min-h-28 resize-y"
            />
            <Button
              className="mt-2 w-full"
              disabled={!recordContent.trim() || savingRecord}
              onClick={() => void addRecord()}
            >
              {savingRecord ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <MessageSquareText className="size-4" />
              )}
              保存{recordLabel(recordKind)}
            </Button>

            {records.length === 0 ? (
              <p className="border-border text-muted-foreground mt-6 border-t pt-6 text-center text-sm">
                暂无研究记录
              </p>
            ) : (
              <div className="border-border mt-6 space-y-3 border-t pt-5">
                {records.map((record) => (
                  <article
                    key={record.id}
                    className="border-border bg-card rounded-md border p-4"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-primary text-xs font-medium">
                        {recordLabel(record.kind)}
                      </span>
                      <button
                        type="button"
                        title="删除记录"
                        disabled={deletingRecordId === record.id}
                        onClick={() => void deleteRecord(record.id)}
                        className="text-muted-foreground hover:bg-accent hover:text-destructive flex size-7 items-center justify-center rounded-md"
                      >
                        {deletingRecordId === record.id ? (
                          <Loader2 className="size-3.5 animate-spin" />
                        ) : (
                          <Trash2 className="size-3.5" />
                        )}
                      </button>
                    </div>
                    <p className="text-foreground mt-2 text-sm leading-6 whitespace-pre-wrap">
                      {record.content}
                    </p>
                    <p className="text-muted-foreground mt-3 text-xs">
                      {formatDate(record.updated_at)}
                    </p>
                  </article>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>

      <Dialog open={documentDialogOpen} onOpenChange={setDocumentDialogOpen}>
        <DialogContent className="admin-dialog sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>添加项目文献</DialogTitle>
            <DialogDescription>
              从文献库选择资料。加入后，项目检索和智能体研究将限定在这些文献中。
            </DialogDescription>
          </DialogHeader>
          <Input
            value={documentQuery}
            onChange={(event) => setDocumentQuery(event.target.value)}
            placeholder="按题名或版本搜索"
          />
          <div className="max-h-[420px] space-y-2 overflow-y-auto pr-1">
            {selectableDocuments.length === 0 ? (
              <p className="text-muted-foreground py-12 text-center text-sm">
                没有可添加的文献
              </p>
            ) : (
              selectableDocuments.map((document) => (
                <div
                  key={document.id}
                  className="border-border flex items-center justify-between gap-4 rounded-md border p-3"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">
                      {document.title}
                    </p>
                    <p className="text-muted-foreground mt-1 truncate text-xs">
                      {document.edition} · {document.source_institution}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={addingDocumentId === document.id}
                    onClick={() => void addDocument(document)}
                  >
                    {addingDocumentId === document.id ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <Plus className="size-4" />
                    )}
                    添加
                  </Button>
                </div>
              ))
            )}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDocumentDialogOpen(false)}
            >
              完成
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}
