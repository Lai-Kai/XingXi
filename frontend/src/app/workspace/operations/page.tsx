"use client";

import {
  Activity,
  Database,
  History,
  ListChecks,
  MapPinned,
  RefreshCw,
  Save,
  ShieldCheck,
  Target,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  BusinessEmptyState,
  BusinessErrorState,
  BusinessLoadingState,
  BusinessMobileHeader,
  BusinessPageHeader,
  BusinessStatusBadge,
} from "@/components/workspace/business-page";
import { ManualEvaluations } from "@/components/workspace/manual-evaluations";
import { useAuth } from "@/core/auth/AuthProvider";
import {
  canManageSourceDocuments,
  hasCapability,
} from "@/core/auth/permissions";
import {
  createCorrection,
  createEvaluationCase,
  createEvaluationRun,
  listAssetVersions,
  listCorrections,
  listEvaluationCases,
  listEvaluationRuns,
  loadOperationsDashboard,
  listOperationTasks,
  reconcileAssetVersions,
  retryOperationTask,
} from "@/core/operations/api";
import {
  correctionText,
  operationStepLabel,
} from "@/core/operations/evaluation-presentation";
import {
  formatMetricRate,
  type AssetVersion,
  type CorrectionRecord,
  type EvaluationCase,
  type EvaluationObservation,
  type EvaluationRun,
  type OperationTask,
  type OperationsDashboard,
} from "@/core/operations/types";
import { publicErrorMessage } from "@/core/ui/presentation";
import { cn } from "@/lib/utils";

type View = "tasks" | "overview" | "evaluation" | "corrections" | "versions";

const views: Array<{ id: View; label: string; icon: typeof Activity }> = [
  { id: "tasks", label: "任务恢复", icon: ListChecks },
  { id: "overview", label: "指标总览", icon: Activity },
  { id: "evaluation", label: "回归评测", icon: Target },
  { id: "corrections", label: "修订记录", icon: History },
  { id: "versions", label: "资产版本", icon: Database },
];

export default function OperationsPage() {
  const { user } = useAuth();
  const allowed = hasCapability(user, "governance:read");
  const [view, setView] = useState<View>("overview");
  const [days, setDays] = useState(30);
  const [dashboard, setDashboard] = useState<OperationsDashboard | null>(null);
  const [cases, setCases] = useState<EvaluationCase[]>([]);
  const [runs, setRuns] = useState<EvaluationRun[]>([]);
  const [corrections, setCorrections] = useState<CorrectionRecord[]>([]);
  const [versions, setVersions] = useState<AssetVersion[]>([]);
  const [tasks, setTasks] = useState<OperationTask[]>([]);
  const [observations, setObservations] = useState<
    Record<string, EvaluationObservation>
  >({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!allowed) return setLoading(false);
    setLoading(true);
    setError(null);
    try {
      const [
        nextDashboard,
        nextCases,
        nextRuns,
        nextCorrections,
        nextVersions,
        nextTasks,
      ] = await Promise.all([
        loadOperationsDashboard(days),
        listEvaluationCases(),
        listEvaluationRuns(),
        listCorrections(),
        listAssetVersions(),
        listOperationTasks(),
      ]);
      setDashboard(nextDashboard);
      setCases(nextCases);
      setRuns(nextRuns);
      setCorrections(nextCorrections);
      setVersions(nextVersions);
      setTasks(nextTasks);
      setObservations((current) => {
        const next = { ...current };
        for (const item of nextCases) {
          next[item.id] ??= {
            case_id: item.id,
            actual_status: item.expected_status,
            citation_count: 0,
            answer: "",
          };
        }
        return next;
      });
    } catch (reason) {
      setError(publicErrorMessage(reason, "无法读取运营数据，请重试。"));
    } finally {
      setLoading(false);
    }
  }, [allowed, days]);

  useEffect(() => void load(), [load]);

  if (!allowed) {
    return (
      <main className="xingxi-module bg-muted/60 size-full overflow-y-auto">
        <BusinessMobileHeader title="运营中心" />
        <div className="mx-auto max-w-7xl px-4 py-8 sm:px-8">
          <BusinessEmptyState
            icon={ShieldCheck}
            title="无运营治理权限"
            description="运营指标、人工修订和版本同步仅对治理人员开放。"
          />
        </div>
      </main>
    );
  }

  return (
    <main className="xingxi-module bg-muted/60 text-foreground size-full overflow-y-auto">
      <BusinessMobileHeader title="运营中心" />
      <div className="mx-auto min-h-full max-w-7xl px-4 py-7 sm:px-8 lg:px-10 lg:py-10">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <BusinessPageHeader
            title="运营中心"
            description="反馈、复核、修订、评测与版本发布的持续优化闭环"
            icon={Activity}
          />
          <button
            type="button"
            onClick={() => void load()}
            className="border-border bg-card hover:bg-muted/60 flex h-9 items-center gap-2 rounded-md border px-3 text-sm"
          >
            <RefreshCw className="size-4" />
            刷新
          </button>
        </div>

        <div
          className="border-border mt-6 flex gap-1 overflow-x-auto border-b"
          role="tablist"
        >
          {views.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setView(item.id)}
                className={cn(
                  "flex h-10 shrink-0 items-center gap-2 border-b-2 px-3 text-sm",
                  view === item.id
                    ? "border-primary text-primary"
                    : "text-muted-foreground hover:text-foreground border-transparent",
                )}
              >
                <Icon className="size-4" />
                {item.label}
              </button>
            );
          })}
        </div>

        {loading ? (
          <BusinessLoadingState label="正在汇总运营数据..." />
        ) : error ? (
          <BusinessErrorState description={error} onRetry={() => void load()} />
        ) : (
          <div className="py-5">
            {view === "tasks" && (
              <TaskPanel
                tasks={tasks}
                saving={saving}
                canRetry={canManageSourceDocuments(user)}
                onRetry={async (taskId) => {
                  setSaving(true);
                  try {
                    await retryOperationTask(taskId);
                    await load();
                  } finally {
                    setSaving(false);
                  }
                }}
              />
            )}
            {view === "overview" && dashboard && (
              <Overview
                dashboard={dashboard}
                days={days}
                onDaysChange={setDays}
              />
            )}
            {view === "evaluation" && (
              <div className="space-y-6">
                <ManualEvaluations
                  cases={cases}
                  runs={runs}
                  observations={observations}
                  onObservation={(value) =>
                    setObservations((current) => ({
                      ...current,
                      [value.case_id]: value,
                    }))
                  }
                  saving={saving}
                  onCreateCase={async (input) => {
                    setSaving(true);
                    try {
                      await createEvaluationCase(input);
                      await load();
                    } catch (reason) {
                      setError(
                        publicErrorMessage(reason, "保存问题失败，请重试。"),
                      );
                      throw reason;
                    } finally {
                      setSaving(false);
                    }
                  }}
                  onRun={async () => {
                    setSaving(true);
                    try {
                      await createEvaluationRun(
                        cases
                          .filter((item) => item.active)
                          .map((item) => observations[item.id]!)
                          .filter(Boolean),
                        versions[0]?.knowledge_release_id,
                      );
                      await load();
                    } catch (reason) {
                      setError(
                        publicErrorMessage(reason, "保存评测失败，请重试。"),
                      );
                    } finally {
                      setSaving(false);
                    }
                  }}
                />
                <div className="xingxi-panel border-border bg-card rounded-xl border p-5">
                  <h3 className="font-semibold">自动流程评测已移至独立栏目</h3>
                  <p className="text-muted-foreground mt-2 text-sm">
                    从左侧「问答评测」查看批次指标、测试轨迹、证据和复核记录。
                  </p>
                  <Link
                    href="/workspace/evaluations"
                    className="text-primary mt-3 inline-flex items-center gap-2 text-sm font-medium hover:underline"
                  >
                    <Target className="size-4" />
                    打开问答评测
                  </Link>
                </div>
              </div>
            )}
            {view === "corrections" && (
              <CorrectionsPanel
                records={corrections}
                saving={saving}
                onCreate={async (input) => {
                  setSaving(true);
                  try {
                    await createCorrection(input);
                    await load();
                  } finally {
                    setSaving(false);
                  }
                }}
              />
            )}
            {view === "versions" && (
              <VersionsPanel
                versions={versions}
                saving={saving}
                onReconcile={async () => {
                  setSaving(true);
                  try {
                    await reconcileAssetVersions();
                    await load();
                  } finally {
                    setSaving(false);
                  }
                }}
              />
            )}
          </div>
        )}
      </div>
    </main>
  );
}

function Overview({
  dashboard,
  days,
  onDaysChange,
}: {
  dashboard: OperationsDashboard;
  days: number;
  onDaysChange: (value: number) => void;
}) {
  const metrics = [
    [
      "回答准确率",
      formatMetricRate(dashboard.answer_accuracy_rate),
      "经人工或评测确认",
    ],
    [
      "出处引用率",
      formatMetricRate(dashboard.citation_rate),
      `${dashboard.answer_count} 次已采集回答`,
    ],
    [
      "拒答合规率",
      formatMetricRate(dashboard.refusal_compliance_rate),
      "仅统计触发拒答的回答",
    ],
    [
      "用户满意度",
      formatMetricRate(dashboard.user_satisfaction_rate),
      "来自回答反馈",
    ],
    ["未命中问题", String(dashboard.unanswered_count), "进入资料补充线索"],
    [
      "地图点位点击",
      String(dashboard.map_point_click_count),
      "二维地图真实交互",
    ],
    [
      "人工修订量",
      String(dashboard.manual_correction_count),
      "保留每次修订记录",
    ],
    ["三维加载成功率", "暂无数据", "尚无可用统计"],
  ];
  return (
    <>
      <div className="flex justify-end">
        <label className="text-muted-foreground flex items-center gap-2 text-sm">
          统计范围
          <select
            value={days}
            onChange={(event) => onDaysChange(Number(event.target.value))}
            className="border-border bg-card h-9 rounded-md border px-3"
          >
            <option value={7}>近 7 天</option>
            <option value={30}>近 30 天</option>
            <option value={90}>近 90 天</option>
          </select>
        </label>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {metrics.map(([label, value, hint]) => (
          <div
            key={label}
            className="xingxi-panel border-border bg-card rounded-2xl border p-4"
          >
            <p className="text-muted-foreground text-xs">{label}</p>
            <p className="text-primary mt-2 text-2xl font-semibold">{value}</p>
            <p className="text-muted-foreground mt-2 text-xs">{hint}</p>
          </div>
        ))}
      </div>
      <section className="border-border mt-7 border-t pt-5">
        <h2 className="text-base font-semibold">热门实体</h2>
        {dashboard.hot_entities.length ? (
          <div className="xingxi-panel divide-border border-border bg-card mt-3 divide-y rounded-2xl border-y">
            {dashboard.hot_entities.map((item, index) => (
              <div
                key={item.entity_id}
                className="grid grid-cols-[36px_1fr_auto] items-center gap-3 px-4 py-3 text-sm"
              >
                <span className="text-muted-foreground">{index + 1}</span>
                <span>{item.name}</span>
                <span className="text-muted-foreground">{item.views} 次</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-muted-foreground mt-3 text-sm">
            暂无实体访问数据。
          </p>
        )}
      </section>
    </>
  );
}

function TaskPanel({
  tasks,
  saving,
  canRetry,
  onRetry,
}: {
  tasks: OperationTask[];
  saving: boolean;
  canRetry: boolean;
  onRetry: (taskId: string) => Promise<void>;
}) {
  const [filter, setFilter] = useState<
    | "all"
    | "pending"
    | "running"
    | "awaiting_review"
    | "completed"
    | "failed"
    | "cancelled"
  >("all");
  const visibleTasks = useMemo(
    () => tasks.filter((task) => filter === "all" || task.status === filter),
    [filter, tasks],
  );

  return (
    <section>
      <div className="border-border flex flex-wrap items-start justify-between gap-3 border-b pb-4">
        <div>
          <h2 className="text-base font-semibold">后台任务</h2>
          <p className="text-muted-foreground mt-1 text-sm">
            查看资料整理、人工复核和检索准备的处理进度。
          </p>
        </div>
        <label className="text-muted-foreground flex items-center gap-2 text-sm">
          筛选
          <select
            value={filter}
            onChange={(event) => setFilter(event.target.value as typeof filter)}
            className="border-border bg-card h-9 rounded-md border px-3"
            aria-label="任务状态筛选"
          >
            <option value="all">全部</option>
            <option value="failed">失败待处理</option>
            <option value="running">处理中</option>
            <option value="pending">等待处理</option>
            <option value="awaiting_review">等待复核</option>
            <option value="completed">已完成</option>
            <option value="cancelled">已取消</option>
          </select>
        </label>
      </div>

      <div className="xingxi-panel divide-border border-border bg-card mt-4 divide-y rounded-2xl border-y">
        {visibleTasks.map((task) => (
          <article key={task.id} className="p-4 sm:p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 className="text-primary truncate text-sm font-semibold">
                  {task.title}
                </h3>
                <p className="text-muted-foreground mt-1 truncate text-xs">
                  {task.filename ?? "未记录文件名"}
                </p>
              </div>
              <BusinessStatusBadge status={task.status} />
            </div>

            <div className="mt-4 flex items-center gap-3">
              <div className="bg-accent h-2 min-w-0 flex-1 overflow-hidden rounded-full">
                <div
                  className="bg-primary h-full rounded-full transition-[width]"
                  style={{ width: `${task.progress_percent}%` }}
                />
              </div>
              <span className="text-muted-foreground w-12 text-right text-xs">
                {task.progress_percent}%
              </span>
            </div>

            <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-6">
              {task.steps.map((step) => (
                <div
                  key={step.name}
                  className={cn(
                    "min-w-0 rounded-md border px-3 py-2",
                    step.status === "failed"
                      ? "border-[#e3bdbd] bg-[#fdf1f1]"
                      : step.status === "completed"
                        ? "border-[#cce1d4] bg-[#f2f8f3]"
                        : step.status === "running"
                          ? "border-border bg-muted/60"
                          : "border-border bg-muted/60",
                  )}
                >
                  <div className="flex items-center justify-between gap-2 text-xs">
                    <span className="truncate font-medium">
                      {operationStepLabel(step.name)}
                    </span>
                    <span className="text-muted-foreground shrink-0">
                      {step.attempt_count} 次
                    </span>
                  </div>
                  {step.error_message && (
                    <p className="mt-1 line-clamp-2 text-xs text-[#934747]">
                      {publicErrorMessage(
                        step.error_message,
                        "本步骤未能完成，请重试。",
                      )}
                    </p>
                  )}
                </div>
              ))}
            </div>

            {task.status === "failed" && (
              <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-md border border-[#e3bdbd] bg-[#fdf4f4] px-3 py-2.5">
                <div className="min-w-0 text-sm text-[#843f3f]">
                  <span className="font-medium">资料处理未完成</span>
                  {task.error_message && (
                    <p className="mt-1 text-xs break-words">
                      {publicErrorMessage(
                        task.error_message,
                        "请检查资料后重试，或联系管理员。",
                      )}
                    </p>
                  )}
                </div>
                {task.retryable && canRetry ? (
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => void onRetry(task.id)}
                    className="bg-primary text-primary-foreground inline-flex h-9 shrink-0 items-center gap-2 rounded-md px-3 text-sm disabled:opacity-40"
                  >
                    <RefreshCw className="size-4" />
                    {saving
                      ? "正在恢复"
                      : `重试（第 ${task.retry_count + 1} 次）`}
                  </button>
                ) : task.retryable ? (
                  <span className="shrink-0 text-xs text-[#843f3f]">
                    请联系资料管理员恢复任务
                  </span>
                ) : (
                  <span className="shrink-0 text-xs text-[#843f3f]">
                    需要修正资料后重新入库
                  </span>
                )}
              </div>
            )}
          </article>
        ))}
        {!visibleTasks.length && (
          <p className="text-muted-foreground p-6 text-sm">
            暂无符合条件的后台任务。
          </p>
        )}
      </div>
    </section>
  );
}

function CorrectionsPanel({
  records,
  saving,
  onCreate,
}: {
  records: CorrectionRecord[];
  saving: boolean;
  onCreate: (input: {
    target_type: CorrectionRecord["target_type"];
    target_id: string;
    summary: string;
    before: Record<string, unknown>;
    after: Record<string, unknown>;
  }) => Promise<void>;
}) {
  const [type, setType] =
    useState<CorrectionRecord["target_type"]>("knowledge");
  const [target, setTarget] = useState("");
  const [summary, setSummary] = useState("");
  const [before, setBefore] = useState("");
  const [after, setAfter] = useState("");
  return (
    <div className="grid gap-7 lg:grid-cols-[360px_minmax(0,1fr)]">
      <form
        className="grid content-start gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          void onCreate({
            target_type: type,
            target_id: target,
            summary,
            before: { text: before },
            after: { text: after },
          }).then(() => {
            setTarget("");
            setSummary("");
          });
        }}
      >
        <h2 className="text-base font-semibold">登记人工修订</h2>
        <p className="text-muted-foreground text-sm">
          修订记录只追加、不覆盖，用于追踪每次知识变化。
        </p>
        <select
          value={type}
          onChange={(event) =>
            setType(event.target.value as CorrectionRecord["target_type"])
          }
          className="h-9 rounded-md border px-3 text-sm"
        >
          <option value="source">史料</option>
          <option value="knowledge">知识</option>
          <option value="entity">实体</option>
          <option value="graph">图谱</option>
          <option value="map">地图</option>
        </select>
        <input
          required
          value={target}
          onChange={(event) => setTarget(event.target.value)}
          placeholder="修订对象名称或资料编号"
          className="h-9 rounded-md border px-3 text-sm"
        />
        <textarea
          required
          value={summary}
          onChange={(event) => setSummary(event.target.value)}
          placeholder="修订原因与核验依据"
          rows={3}
          className="rounded-md border px-3 py-2 text-sm"
        />
        <textarea
          value={before}
          onChange={(event) => setBefore(event.target.value)}
          aria-label="修订前内容"
          placeholder="填写修订前的内容"
          rows={4}
          className="rounded-md border px-3 py-2 text-sm"
        />
        <textarea
          value={after}
          onChange={(event) => setAfter(event.target.value)}
          aria-label="修订后内容"
          placeholder="填写修订后的内容"
          rows={4}
          className="rounded-md border px-3 py-2 text-sm"
        />
        <button
          disabled={saving}
          className="bg-primary text-primary-foreground flex h-9 items-center justify-center gap-2 rounded-md text-sm disabled:opacity-40"
        >
          <Save className="size-4" />
          保存修订记录
        </button>
      </form>
      <section>
        <h2 className="text-base font-semibold">历史修订</h2>
        <div className="xingxi-panel divide-border border-border bg-card mt-3 divide-y rounded-2xl border-y">
          {records.map((item) => (
            <div key={item.id} className="p-4">
              <div className="flex flex-wrap justify-between gap-2">
                <span className="text-sm font-medium">
                  {(
                    {
                      source: "史料修订",
                      knowledge: "知识修订",
                      entity: "人物地点修订",
                      graph: "图谱修订",
                      map: "地图修订",
                    } as Record<string, string>
                  )[item.target_type] ?? "内容修订"}
                </span>
                <span className="text-muted-foreground text-xs">
                  {new Date(item.created_at).toLocaleString("zh-CN")}
                </span>
              </div>
              <p className="text-muted-foreground mt-2 text-sm">
                {item.summary}
              </p>
              <p className="text-muted-foreground mt-2 font-mono text-xs">
                {correctionText(item.before)} → {correctionText(item.after)}
              </p>
            </div>
          ))}
          {!records.length && (
            <p className="text-muted-foreground p-4 text-sm">
              暂无人工修订记录。
            </p>
          )}
        </div>
      </section>
    </div>
  );
}

function VersionsPanel({
  versions,
  saving,
  onReconcile,
}: {
  versions: AssetVersion[];
  saving: boolean;
  onReconcile: () => Promise<void>;
}) {
  return (
    <section>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">知识、图谱与地图资产版本</h2>
          <p className="text-muted-foreground mt-1 text-sm">
            按发布版本查看关联的图谱和地图资料，保留历史记录。
          </p>
        </div>
        <button
          type="button"
          disabled={saving}
          onClick={() => void onReconcile()}
          className="border-primary text-primary flex h-9 items-center gap-2 rounded-md border px-3 text-sm disabled:opacity-40"
        >
          <RefreshCw className="size-4" />
          同步缺失版本
        </button>
      </div>
      <div className="xingxi-panel border-border bg-card mt-4 overflow-x-auto rounded-2xl border-y">
        <div className="bg-muted/60 text-muted-foreground grid min-w-[520px] grid-cols-[110px_100px_110px_1fr] gap-3 border-b px-4 py-3 text-xs">
          <span>知识版本</span>
          <span>图谱实体</span>
          <span>地图点位</span>
          <span>生成时间</span>
        </div>
        {versions.map((item) => (
          <div
            key={item.id}
            className="grid min-w-[520px] grid-cols-[110px_100px_110px_1fr] items-center gap-3 border-b px-4 py-3 text-sm last:border-b-0"
          >
            <span className="font-medium">
              {item.knowledge_release_version}
            </span>
            <span>{item.entity_count}</span>
            <span className="flex items-center gap-1">
              <MapPinned className="size-3.5" />
              {item.map_point_count}
            </span>
            <span className="text-muted-foreground text-xs">
              {new Date(item.created_at).toLocaleString("zh-CN")}
            </span>
          </div>
        ))}
        {!versions.length && (
          <p className="text-muted-foreground p-5 text-sm">
            暂无版本记录。发布资料后会自动生成，也可点击“同步缺失版本”。
          </p>
        )}
      </div>
    </section>
  );
}
