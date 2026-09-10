"use client";

import {
  Activity,
  BookCheck,
  Database,
  History,
  ListChecks,
  MapPinned,
  RefreshCw,
  Save,
  ShieldCheck,
  Target,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  BusinessEmptyState,
  BusinessErrorState,
  BusinessLoadingState,
  BusinessMobileHeader,
  BusinessPageHeader,
  BusinessStatusBadge,
} from "@/components/workspace/business-page";
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
  formatMetricRate,
  type AssetVersion,
  type CorrectionRecord,
  type EvaluationCase,
  type EvaluationObservation,
  type EvaluationRun,
  type OperationTask,
  type OperationsDashboard,
} from "@/core/operations/types";
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
            citation_count: item.min_citations,
            answer: "",
          };
        }
        return next;
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法读取运营数据");
    } finally {
      setLoading(false);
    }
  }, [allowed, days]);

  useEffect(() => void load(), [load]);

  if (!allowed) {
    return (
      <main className="size-full overflow-y-auto bg-[#f7fafb]">
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
    <main className="size-full overflow-y-auto bg-[#f7fafb] text-[#202b2e]">
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
            className="flex h-9 items-center gap-2 rounded-md border border-[#cbd8da] bg-white px-3 text-sm hover:bg-[#eef5f5]"
          >
            <RefreshCw className="size-4" />
            刷新
          </button>
        </div>

        <div
          className="mt-6 flex gap-1 overflow-x-auto border-b border-[#d6e0e2]"
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
                    ? "border-[#276f79] text-[#174e56]"
                    : "border-transparent text-[#66787d] hover:text-[#26383c]",
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
              <EvaluationPanel
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
                  } finally {
                    setSaving(false);
                  }
                }}
              />
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
    ["人工修订量", String(dashboard.manual_correction_count), "追加式修订记录"],
    ["三维加载成功率", "未接入", "三维完成后启用"],
  ];
  return (
    <>
      <div className="flex justify-end">
        <label className="flex items-center gap-2 text-sm text-[#617277]">
          统计范围
          <select
            value={days}
            onChange={(event) => onDaysChange(Number(event.target.value))}
            className="h-9 rounded-md border border-[#cad7d9] bg-white px-3"
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
            className="rounded-md border border-[#d7e1e2] bg-white p-4"
          >
            <p className="text-xs text-[#697b80]">{label}</p>
            <p className="mt-2 text-2xl font-semibold text-[#193f45]">
              {value}
            </p>
            <p className="mt-2 text-xs text-[#7a898d]">{hint}</p>
          </div>
        ))}
      </div>
      <section className="mt-7 border-t border-[#d7e1e2] pt-5">
        <h2 className="text-base font-semibold">热门实体</h2>
        {dashboard.hot_entities.length ? (
          <div className="mt-3 divide-y divide-[#e2e9ea] border-y border-[#d7e1e2] bg-white">
            {dashboard.hot_entities.map((item, index) => (
              <div
                key={item.entity_id}
                className="grid grid-cols-[36px_1fr_auto] items-center gap-3 px-4 py-3 text-sm"
              >
                <span className="text-[#819095]">{index + 1}</span>
                <span>{item.name}</span>
                <span className="text-[#527078]">{item.views} 次</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-3 text-sm text-[#718186]">暂无实体访问数据。</p>
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
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[#d7e1e2] pb-4">
        <div>
          <h2 className="text-base font-semibold">后台任务</h2>
          <p className="mt-1 text-sm text-[#697a7f]">
            解析、识别、清洗、切分、复核和索引统一显示。
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm text-[#617277]">
          筛选
          <select
            value={filter}
            onChange={(event) => setFilter(event.target.value as typeof filter)}
            className="h-9 rounded-md border border-[#cad7d9] bg-white px-3"
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

      <div className="mt-4 divide-y divide-[#dbe5e6] border-y border-[#d7e1e2] bg-white">
        {visibleTasks.map((task) => (
          <article key={task.id} className="p-4 sm:p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 className="truncate text-sm font-semibold text-[#193f45]">
                  {task.title}
                </h3>
                <p className="mt-1 truncate text-xs text-[#748489]">
                  {task.filename ?? "未记录文件名"} · 任务 {task.id}
                </p>
              </div>
              <BusinessStatusBadge status={task.status} />
            </div>

            <div className="mt-4 flex items-center gap-3">
              <div className="h-2 min-w-0 flex-1 overflow-hidden rounded-full bg-[#e7eeee]">
                <div
                  className="h-full rounded-full bg-[#4e8d96] transition-[width]"
                  style={{ width: `${task.progress_percent}%` }}
                />
              </div>
              <span className="w-12 text-right text-xs text-[#607176]">
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
                          ? "border-[#c6dfe2] bg-[#f0f8f9]"
                          : "border-[#e0e7e8] bg-[#fafcfc]",
                  )}
                >
                  <div className="flex items-center justify-between gap-2 text-xs">
                    <span className="truncate font-medium">{step.label}</span>
                    <span className="shrink-0 text-[#718186]">
                      {step.attempt_count} 次
                    </span>
                  </div>
                  {step.error_message && (
                    <p className="mt-1 line-clamp-2 text-xs text-[#934747]">
                      {step.error_message}
                    </p>
                  )}
                </div>
              ))}
            </div>

            {task.status === "failed" && (
              <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-md border border-[#e3bdbd] bg-[#fdf4f4] px-3 py-2.5">
                <div className="min-w-0 text-sm text-[#843f3f]">
                  <span className="font-medium">
                    {task.failure_step_label ?? "任务"}
                  </span>
                  {task.error_code && (
                    <span className="ml-2 font-mono text-xs">
                      {task.error_code}
                    </span>
                  )}
                  {task.error_message && (
                    <p className="mt-1 text-xs break-words">
                      {task.error_message}
                    </p>
                  )}
                </div>
                {task.retryable && canRetry ? (
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => void onRetry(task.id)}
                    className="inline-flex h-9 shrink-0 items-center gap-2 rounded-md bg-[#205f68] px-3 text-sm text-white disabled:opacity-40"
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
          <p className="p-6 text-sm text-[#718186]">暂无符合条件的后台任务。</p>
        )}
      </div>
    </section>
  );
}

function EvaluationPanel({
  cases,
  runs,
  observations,
  onObservation,
  saving,
  onCreateCase,
  onRun,
}: {
  cases: EvaluationCase[];
  runs: EvaluationRun[];
  observations: Record<string, EvaluationObservation>;
  onObservation: (value: EvaluationObservation) => void;
  saving: boolean;
  onCreateCase: (input: {
    name: string;
    question: string;
    expected_status: "answered" | "refused";
    min_citations: number;
    required_terms: string[];
  }) => Promise<void>;
  onRun: () => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [question, setQuestion] = useState("");
  const [expected, setExpected] = useState<"answered" | "refused">("answered");
  const [citations, setCitations] = useState(1);
  const [terms, setTerms] = useState("");
  return (
    <div className="grid gap-7 xl:grid-cols-[minmax(0,1fr)_340px]">
      <section>
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold">评测用例与本次观测</h2>
            <p className="mt-1 text-sm text-[#697a7f]">
              录入当前模型回答后，系统按状态、引用数和必含词自动评分并冻结结果。
            </p>
          </div>
          <button
            type="button"
            disabled={saving || !cases.length}
            onClick={() => void onRun()}
            className="flex h-9 items-center gap-2 rounded-md bg-[#205f68] px-4 text-sm text-white disabled:opacity-40"
          >
            <BookCheck className="size-4" />
            运行回归
          </button>
        </div>
        <div className="mt-4 space-y-3">
          {cases.map((item) => {
            const value = observations[item.id] ?? {
              case_id: item.id,
              actual_status: item.expected_status,
              citation_count: 0,
              answer: "",
            };
            return (
              <div
                key={item.id}
                className="rounded-md border border-[#d7e1e2] bg-white p-4"
              >
                <div className="flex flex-wrap justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-medium">{item.name}</h3>
                    <p className="mt-1 text-sm text-[#53676c]">
                      {item.question}
                    </p>
                  </div>
                  <span className="text-xs text-[#718186]">
                    期望：
                    {item.expected_status === "answered" ? "回答" : "拒答"} · ≥{" "}
                    {item.min_citations} 引用
                  </span>
                </div>
                <div className="mt-3 grid gap-3 sm:grid-cols-[130px_110px_1fr]">
                  <select
                    value={value.actual_status}
                    onChange={(event) =>
                      onObservation({
                        ...value,
                        actual_status: event.target.value as
                          | "answered"
                          | "refused",
                      })
                    }
                    className="h-9 rounded-md border px-2 text-sm"
                  >
                    <option value="answered">本次已回答</option>
                    <option value="refused">本次已拒答</option>
                  </select>
                  <input
                    type="number"
                    min={0}
                    value={value.citation_count}
                    onChange={(event) =>
                      onObservation({
                        ...value,
                        citation_count: Number(event.target.value),
                      })
                    }
                    aria-label="本次引用数"
                    className="h-9 rounded-md border px-2 text-sm"
                  />
                  <input
                    value={value.answer}
                    onChange={(event) =>
                      onObservation({ ...value, answer: event.target.value })
                    }
                    placeholder="粘贴或记录本次模型回答"
                    className="h-9 min-w-0 rounded-md border px-3 text-sm"
                  />
                </div>
              </div>
            );
          })}
          {!cases.length && (
            <p className="text-sm text-[#718186]">
              先在右侧创建至少一个评测用例。
            </p>
          )}
        </div>
      </section>
      <aside className="space-y-6 border-l border-[#d7e1e2] pl-0 xl:pl-6">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void onCreateCase({
              name,
              question,
              expected_status: expected,
              min_citations: citations,
              required_terms: terms
                .split(/[,，]/)
                .map((item) => item.trim())
                .filter(Boolean),
            }).then(() => {
              setName("");
              setQuestion("");
              setTerms("");
            });
          }}
        >
          <h2 className="text-base font-semibold">新增评测用例</h2>
          <div className="mt-3 grid gap-3">
            <input
              required
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="用例名称"
              className="h-9 rounded-md border px-3 text-sm"
            />
            <textarea
              required
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="固定测试问题"
              rows={3}
              className="rounded-md border px-3 py-2 text-sm"
            />
            <div className="grid grid-cols-2 gap-2">
              <select
                value={expected}
                onChange={(event) =>
                  setExpected(event.target.value as "answered" | "refused")
                }
                className="h-9 rounded-md border px-2 text-sm"
              >
                <option value="answered">期望回答</option>
                <option value="refused">期望拒答</option>
              </select>
              <input
                type="number"
                min={0}
                value={citations}
                onChange={(event) => setCitations(Number(event.target.value))}
                aria-label="最低引用数"
                className="h-9 rounded-md border px-2 text-sm"
              />
            </div>
            <input
              value={terms}
              onChange={(event) => setTerms(event.target.value)}
              placeholder="必含词，用逗号分隔"
              className="h-9 rounded-md border px-3 text-sm"
            />
            <button
              disabled={saving}
              className="h-9 rounded-md border border-[#276f79] text-sm text-[#205f68] disabled:opacity-40"
            >
              保存用例
            </button>
          </div>
        </form>
        <div>
          <h2 className="text-base font-semibold">最近运行</h2>
          <div className="mt-3 space-y-2">
            {runs.slice(0, 5).map((run) => (
              <div
                key={run.id}
                className="border-b border-[#dce5e6] pb-2 text-sm"
              >
                <div className="flex justify-between">
                  <span>
                    {new Date(run.created_at).toLocaleString("zh-CN")}
                  </span>
                  <span
                    className={
                      run.pass_rate === 1 ? "text-[#237052]" : "text-[#a05c22]"
                    }
                  >
                    {formatMetricRate(run.pass_rate)}
                  </span>
                </div>
                <p className="mt-1 text-xs text-[#76868a]">
                  {run.passed} / {run.total} 通过 ·{" "}
                  {run.release_id ?? "未绑定知识版本"}
                </p>
              </div>
            ))}
            {!runs.length && (
              <p className="text-sm text-[#718186]">尚未运行评测。</p>
            )}
          </div>
        </div>
      </aside>
    </div>
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
  const [before, setBefore] = useState("{}");
  const [after, setAfter] = useState("{}");
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
            before: JSON.parse(before),
            after: JSON.parse(after),
          }).then(() => {
            setTarget("");
            setSummary("");
          });
        }}
      >
        <h2 className="text-base font-semibold">登记人工修订</h2>
        <p className="text-sm text-[#697a7f]">
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
          placeholder="目标 ID"
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
          aria-label="修订前 JSON"
          rows={4}
          className="rounded-md border px-3 py-2 font-mono text-xs"
        />
        <textarea
          value={after}
          onChange={(event) => setAfter(event.target.value)}
          aria-label="修订后 JSON"
          rows={4}
          className="rounded-md border px-3 py-2 font-mono text-xs"
        />
        <button
          disabled={saving}
          className="flex h-9 items-center justify-center gap-2 rounded-md bg-[#205f68] text-sm text-white disabled:opacity-40"
        >
          <Save className="size-4" />
          保存修订记录
        </button>
      </form>
      <section>
        <h2 className="text-base font-semibold">历史修订</h2>
        <div className="mt-3 divide-y divide-[#dde5e6] border-y border-[#d7e1e2] bg-white">
          {records.map((item) => (
            <div key={item.id} className="p-4">
              <div className="flex flex-wrap justify-between gap-2">
                <span className="text-sm font-medium">
                  {item.target_type} · {item.target_id}
                </span>
                <span className="text-xs text-[#748489]">
                  {new Date(item.created_at).toLocaleString("zh-CN")}
                </span>
              </div>
              <p className="mt-2 text-sm text-[#52666b]">{item.summary}</p>
              <p className="mt-2 font-mono text-xs text-[#7b898d]">
                {JSON.stringify(item.before)} → {JSON.stringify(item.after)}
              </p>
            </div>
          ))}
          {!records.length && (
            <p className="p-4 text-sm text-[#718186]">暂无人工修订记录。</p>
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
          <p className="mt-1 text-sm text-[#697a7f]">
            每个知识发布版本绑定一份不可变的图谱和二维地图清单，可核验、可回溯。
          </p>
        </div>
        <button
          type="button"
          disabled={saving}
          onClick={() => void onReconcile()}
          className="flex h-9 items-center gap-2 rounded-md border border-[#276f79] px-3 text-sm text-[#205f68] disabled:opacity-40"
        >
          <RefreshCw className="size-4" />
          同步缺失版本
        </button>
      </div>
      <div className="mt-4 overflow-x-auto border-y border-[#d7e1e2] bg-white">
        <div className="grid min-w-[820px] grid-cols-[110px_180px_100px_110px_1fr_150px] gap-3 border-b bg-[#eff5f5] px-4 py-3 text-xs text-[#607176]">
          <span>知识版本</span>
          <span>发布 ID</span>
          <span>图谱实体</span>
          <span>地图点位</span>
          <span>清单校验</span>
          <span>生成时间</span>
        </div>
        {versions.map((item) => (
          <div
            key={item.id}
            className="grid min-w-[820px] grid-cols-[110px_180px_100px_110px_1fr_150px] items-center gap-3 border-b px-4 py-3 text-sm last:border-b-0"
          >
            <span className="font-medium">
              {item.knowledge_release_version}
            </span>
            <span
              className="truncate font-mono text-xs"
              title={item.knowledge_release_id}
            >
              {item.knowledge_release_id}
            </span>
            <span>{item.entity_count}</span>
            <span className="flex items-center gap-1">
              <MapPinned className="size-3.5" />
              {item.map_point_count}
            </span>
            <span
              className="truncate font-mono text-xs"
              title={`图谱 ${item.graph_manifest_sha256}\n地图 ${item.map_manifest_sha256}`}
            >
              {item.graph_manifest_sha256.slice(0, 12)} /{" "}
              {item.map_manifest_sha256.slice(0, 12)}
            </span>
            <span className="text-xs text-[#748489]">
              {new Date(item.created_at).toLocaleString("zh-CN")}
            </span>
          </div>
        ))}
        {!versions.length && (
          <p className="p-5 text-sm text-[#718186]">
            暂无资产快照。发布知识版本后会自动生成，也可点击“同步缺失版本”。
          </p>
        )}
      </div>
    </section>
  );
}
