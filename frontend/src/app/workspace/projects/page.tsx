"use client";

import {
  ArrowRight,
  Archive,
  BookOpenText,
  FolderKanban,
  MoreHorizontal,
  Plus,
  ShieldAlert,
} from "lucide-react";
import Link from "next/link";
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
import {
  BusinessEmptyState,
  BusinessErrorState,
  BusinessInlineError,
  BusinessLoadingState,
  BusinessMobileHeader,
  BusinessPageHeader,
  BusinessStatusBadge,
} from "@/components/workspace/business-page";
import { useAuth } from "@/core/auth/AuthProvider";
import { hasCapability } from "@/core/auth/permissions";
import {
  createResearchProject,
  listResearchProjects,
  setResearchProjectArchived,
  type ResearchProject as ApiResearchProject,
} from "@/core/projects/api";
import { isIMEComposing } from "@/lib/ime";

type ResearchProject = ApiResearchProject & {
  id: string;
  createdAt: string;
  documentCount: number;
};

export default function ProjectsPage() {
  const { user } = useAuth();
  const mayManageProjects = hasCapability(user, "project:manage");
  const [projects, setProjects] = useState<ResearchProject[]>([]);
  const [showArchived, setShowArchived] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [archivingId, setArchivingId] = useState<string | null>(null);

  const loadProjects = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const items = await listResearchProjects();
      setProjects(
        items.map((item) => ({
          ...item,
          createdAt: new Intl.DateTimeFormat("zh-CN").format(
            new Date(item.created_at),
          ),
          documentCount: item.document_count ?? 0,
        })),
      );
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "无法读取研究项目");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!mayManageProjects) {
      setLoading(false);
      return;
    }
    void loadProjects();
  }, [loadProjects, mayManageProjects]);

  const visibleProjects = useMemo(
    () => projects.filter((project) => project.archived === showArchived),
    [projects, showArchived],
  );
  const activeCount = projects.filter((project) => !project.archived).length;

  async function createProject() {
    const name = projectName.trim();
    if (!name) return;
    setCreating(true);
    setActionError(null);
    try {
      const created = await createResearchProject(name);
      setProjects((current) => [
        {
          ...created,
          createdAt: new Intl.DateTimeFormat("zh-CN").format(
            new Date(created.created_at),
          ),
          documentCount: 0,
        },
        ...current,
      ]);
      setProjectName("");
      setShowArchived(false);
      setDialogOpen(false);
    } catch (error) {
      setActionError(
        error instanceof Error ? error.message : "无法创建研究项目",
      );
    } finally {
      setCreating(false);
    }
  }

  async function toggleArchive(id: string) {
    const project = projects.find((item) => item.id === id);
    if (!project) return;
    setArchivingId(id);
    setActionError(null);
    try {
      const updated = await setResearchProjectArchived(id, !project.archived);
      setProjects((current) =>
        current.map((item) =>
          item.id === id ? { ...item, archived: updated.archived } : item,
        ),
      );
    } catch (error) {
      setActionError(
        error instanceof Error ? error.message : "无法更新项目状态",
      );
    } finally {
      setArchivingId(null);
    }
  }

  if (!mayManageProjects) {
    return (
      <main className="size-full overflow-y-auto bg-[#f7fafb] text-[#202b2e]">
        <BusinessMobileHeader title="研究项目" />
        <div className="mx-auto min-h-full max-w-7xl px-4 py-7 sm:px-8 lg:px-10 lg:py-10">
          <BusinessPageHeader
            title="研究项目"
            description="按专题组织文献、问题与研究结论"
            icon={FolderKanban}
          />
          <BusinessEmptyState
            icon={ShieldAlert}
            title="当前角色不使用研究项目"
            description="研究人员和研学团队可以建立项目；游客/公众可继续使用文史检索、智能问答与古舆地图。"
            className="mt-6 min-h-[440px] border-t border-[#dbe4e5]"
          />
        </div>
      </main>
    );
  }

  return (
    <main className="size-full overflow-y-auto bg-[#f7fafb] text-[#202b2e]">
      <BusinessMobileHeader title="研究项目" />

      <div className="mx-auto min-h-full max-w-7xl px-4 py-7 sm:px-8 lg:px-10 lg:py-10">
        <BusinessPageHeader
          title="研究项目"
          description="按专题组织文献、问题与研究结论"
          icon={FolderKanban}
          actions={
            <button
              type="button"
              onClick={() => setDialogOpen(true)}
              className="flex h-10 w-fit items-center gap-2 rounded-md bg-[#202b2e] px-4 text-sm text-white hover:bg-[#354347]"
            >
              <Plus className="size-4" />
              新建项目
            </button>
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

        <section className="mt-6">
          <div className="flex items-center gap-2 border-b border-[#dbe4e5] pb-3">
            <button
              type="button"
              onClick={() => setShowArchived(false)}
              className={`h-9 rounded-md px-4 text-sm ${
                !showArchived
                  ? "bg-[#dfeaec] font-medium text-[#285f68]"
                  : "text-[#68797e] hover:bg-[#edf3f4]"
              }`}
            >
              {activeCount} 个项目
            </button>
            <button
              type="button"
              onClick={() => setShowArchived(true)}
              className={`flex h-9 items-center gap-2 rounded-md px-4 text-sm ${
                showArchived
                  ? "bg-[#dfeaec] font-medium text-[#285f68]"
                  : "text-[#68797e] hover:bg-[#edf3f4]"
              }`}
            >
              <Archive className="size-4" />
              已归档
            </button>
          </div>

          {loading ? (
            <BusinessLoadingState label="正在读取研究项目…" />
          ) : loadError ? (
            <BusinessErrorState
              description={loadError}
              onRetry={() => void loadProjects()}
            />
          ) : visibleProjects.length === 0 ? (
            <BusinessEmptyState
              icon={showArchived ? Archive : FolderKanban}
              title={showArchived ? "暂无归档项目" : "还没有研究项目"}
              description={
                showArchived
                  ? "完成的研究项目可以归档，并随时在这里恢复。"
                  : "为一个人物、地点或历史问题建立项目，集中管理相关文献与研究过程。"
              }
              className="min-h-[440px]"
              action={
                !showArchived ? (
                  <button
                    type="button"
                    onClick={() => setDialogOpen(true)}
                    className="mt-5 flex h-10 items-center gap-2 rounded-md border border-[#80aeb5] px-4 text-sm text-[#286873] hover:bg-[#edf5f5]"
                  >
                    <Plus className="size-4" />
                    创建第一个项目
                  </button>
                ) : undefined
              }
            />
          ) : (
            <div className="mt-5 grid gap-4 md:grid-cols-2">
              {visibleProjects.map((project) => (
                <article
                  key={project.id}
                  className="relative rounded-md border border-[#d5e0e1] bg-white p-5 transition hover:border-[#8fb4ba] hover:shadow-[0_8px_24px_rgba(44,76,82,0.08)]"
                >
                  <div className="flex items-start justify-between gap-3">
                    <span className="flex size-10 items-center justify-center rounded-md bg-[#e4eff0] text-[#356f77]">
                      <BookOpenText className="size-5" />
                    </span>
                    <button
                      type="button"
                      disabled={archivingId === project.id}
                      onClick={() => void toggleArchive(project.id)}
                      title={project.archived ? "取消归档" : "归档项目"}
                      className="relative z-10 flex size-8 items-center justify-center rounded-md text-[#718186] hover:bg-[#edf3f4] hover:text-[#2d5960] disabled:cursor-wait disabled:opacity-50"
                    >
                      {project.archived ? (
                        <Archive className="size-4" />
                      ) : (
                        <MoreHorizontal className="size-4" />
                      )}
                    </button>
                  </div>
                  <h3 className="mt-4 text-base font-medium">
                    <Link
                      href={`/workspace/projects/${encodeURIComponent(project.id)}`}
                      className="after:absolute after:inset-0"
                    >
                      {project.name}
                    </Link>
                  </h3>
                  <BusinessStatusBadge
                    status={project.archived ? "archived" : "active"}
                    className="mt-3"
                  />
                  <div className="mt-5 flex items-center justify-between border-t border-[#e4eaeb] pt-4 text-xs text-[#718186]">
                    <span>{project.documentCount} 份文献</span>
                    <span className="flex items-center gap-2">
                      创建于 {project.createdAt}
                      <ArrowRight className="size-3.5" />
                    </span>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>新建研究项目</DialogTitle>
            <DialogDescription>
              建立专题空间，用于组织相关文献和后续研究。
            </DialogDescription>
          </DialogHeader>
          <div className="py-3">
            <label className="text-sm font-medium" htmlFor="project-name">
              项目名称
            </label>
            <Input
              id="project-name"
              autoFocus
              value={projectName}
              onChange={(event) => setProjectName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !isIMEComposing(event)) {
                  event.preventDefault();
                  void createProject();
                }
              }}
              placeholder="例如：木渎古桥沿革研究"
              className="mt-2"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              取消
            </Button>
            <Button
              disabled={!projectName.trim() || creating}
              onClick={() => void createProject()}
            >
              {creating ? "正在创建…" : "创建项目"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}
