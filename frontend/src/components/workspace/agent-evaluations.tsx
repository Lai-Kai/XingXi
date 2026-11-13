"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Download,
  FlaskConical,
  ListChecks,
  Play,
  RefreshCw,
  Search,
  ShieldCheck,
  Square,
  TriangleAlert,
} from "lucide-react";
import { useState } from "react";

import {
  evaluationMetrics,
  filterObservations,
  scenarioLabels,
} from "@/core/operations/evaluation-dashboard";
import { evaluationModeLabel } from "@/core/operations/evaluation-presentation";
import {
  cancelAgentEvaluation,
  downloadAgentReport,
  evaluationLabel,
  evaluationVerdict,
  getAgentEvaluation,
  listAgentEvaluations,
  loadAgentCatalog,
  rerunAgentEvaluation,
  startAgentEvaluation,
  type AgentEvaluation,
} from "@/core/operations/evaluations";
import { publicErrorMessage } from "@/core/ui/presentation";
import { cn } from "@/lib/utils";

import { AgentEvaluationCases } from "./agent-evaluation-cases";
import {
  EvaluationDistributionChart,
  EvaluationHistoryChart,
} from "./agent-evaluation-charts";
import { AgentEvaluationDetail } from "./agent-evaluation-detail";
import { EvaluationBadge, evaluationButton } from "./agent-evaluation-ui";
import { BusinessEmptyState, BusinessLoadingState } from "./business-page";

const selectStyle =
  "min-h-10 min-w-0 rounded-lg border border-border bg-card px-3 py-2 text-sm outline-ring";

export function AgentEvaluations({ canExecute }: { canExecute: boolean }) {
  const queryClient = useQueryClient();
  const [offset, setOffset] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [trajectory, setTrajectory] = useState<{
    batchId: string;
    caseId: string;
  } | null>(null);
  const [days, setDays] = useState(0);
  const [scenario, setScenario] = useState("all");
  const [mode, setMode] = useState("all");
  const [outcome, setOutcome] = useState("all");
  const [query, setQuery] = useState("");
  const [exportError, setExportError] = useState<string | null>(null);
  const [caseManagerOpen, setCaseManagerOpen] = useState(false);
  const catalog = useQuery({
    queryKey: ["agent-evaluations", "catalog"],
    queryFn: ({ signal }) => loadAgentCatalog(signal),
  });
  const batches = useQuery({
    queryKey: ["agent-evaluations", "list", offset],
    queryFn: ({ signal }) => listAgentEvaluations(offset, signal),
    refetchInterval: (current) =>
      current.state.data?.some((item) =>
        ["queued", "running"].includes(item.status),
      )
        ? 2000
        : false,
  });
  const history = (batches.data ?? []).filter(
    (item) =>
      !days ||
      new Date(item.created_at).getTime() >= Date.now() - days * 86400000,
  );
  const activeId = selectedId ?? history[0]?.id;
  const detail = useQuery({
    queryKey: ["agent-evaluations", "detail", activeId],
    queryFn: ({ signal }) => getAgentEvaluation(activeId!, signal),
    enabled: Boolean(activeId),
    refetchInterval: (current) =>
      current.state.data &&
      ["queued", "running"].includes(current.state.data.status)
        ? 1000
        : false,
  });
  const updateBatch = async (next: AgentEvaluation) => {
    await queryClient.cancelQueries({
      queryKey: ["agent-evaluations", "detail", next.id],
    });
    queryClient.setQueryData(["agent-evaluations", "detail", next.id], next);
    await queryClient.invalidateQueries({
      queryKey: ["agent-evaluations", "list"],
    });
  };
  const choose = (id: string) => {
    setSelectedId(id);
    setTrajectory(null);
    setExportError(null);
  };
  const adopt = async (next: AgentEvaluation) => {
    choose(next.id);
    await updateBatch(next);
  };
  const start = useMutation({
    mutationFn: (input: { smoke: boolean; caseIds?: string[] }) =>
      startAgentEvaluation(input.smoke, crypto.randomUUID(), input.caseIds),
    onSuccess: adopt,
  });
  const cancel = useMutation({
    mutationFn: cancelAgentEvaluation,
    onSuccess: updateBatch,
  });
  const rerun = useMutation({
    mutationFn: (id: string) => rerunAgentEvaluation(id, crypto.randomUUID()),
    onSuccess: adopt,
  });
  const busy = start.isPending || cancel.isPending || rerun.isPending;
  const coreCount = catalog.data?.core_count ?? 6;
  const totalCount = catalog.data?.cases.length ?? 30;
  const batch = detail.data;
  const metrics = evaluationMetrics(batch);
  const visible = filterObservations(batch?.results ?? [], {
    scenario,
    mode,
    outcome,
    query,
  });
  const observation =
    batch?.id === trajectory?.batchId
      ? batch?.results.find((item) => item.case_id === trajectory?.caseId)
      : undefined;
  const error =
    catalog.error ??
    batches.error ??
    detail.error ??
    start.error ??
    cancel.error ??
    rerun.error;
  const refresh = () => {
    setExportError(null);
    void queryClient.invalidateQueries({ queryKey: ["agent-evaluations"] });
  };
  const paginate = (nextOffset: number) => {
    setOffset(nextOffset);
    setSelectedId(null);
    setTrajectory(null);
  };
  const hasRecords = Boolean(batches.data?.length);
  const batchLabel =
    batch?.status === "completed" &&
    (batch.total === 0 || batch.results.length !== batch.total)
      ? "结果记录不完整"
      : batch
        ? evaluationVerdict(batch)
        : "";
  const scenarioOptions = [
    ...new Set(
      [
        ...(catalog.data?.cases ?? []),
        ...(batch?.results.map((item) => item.case) ?? []),
      ].map((item) => item.scenario),
    ),
  ];

  return (
    <>
      <AgentEvaluationCases
        open={caseManagerOpen}
        onOpenChange={setCaseManagerOpen}
        canManage={canExecute}
        canRun={Boolean(catalog.data?.available) && !busy}
        onRun={(id) => {
          start.mutate({ smoke: false, caseIds: [id] });
          setCaseManagerOpen(false);
        }}
      />
      <section className="space-y-5" aria-label="问答评测">
        <div className="border-border bg-muted/60 rounded-xl border p-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="max-w-2xl">
              <span className="border-border bg-card text-primary inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium">
                <FlaskConical className="size-3.5" />
                自动流程测试
              </span>
              <h2 className="mt-3 text-lg font-semibold">自动化测试监控大盘</h2>
              <p className="text-muted-foreground mt-2 text-sm leading-6">
                核对资料查阅、引用与取消流程。流程测试使用预设资料与回答，通过率不代表实际回答质量或线上回答准确率。
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className={evaluationButton}
                onClick={() => setCaseManagerOpen(true)}
              >
                <ListChecks className="size-4" />
                测试问题与方法
              </button>
              <button
                type="button"
                className={evaluationButton}
                onClick={refresh}
                disabled={batches.isFetching && detail.isFetching}
              >
                <RefreshCw className="size-4" />
                刷新记录
              </button>
              {canExecute && (
                <>
                  <button
                    type="button"
                    className={cn(
                      evaluationButton,
                      "border-primary bg-primary text-primary-foreground hover:bg-primary/90",
                    )}
                    disabled={
                      busy || !catalog.data?.available || coreCount === 0
                    }
                    onClick={() => start.mutate({ smoke: true })}
                  >
                    <Play className="size-4" />
                    运行核心 {coreCount} 项
                  </button>
                  <button
                    type="button"
                    className={evaluationButton}
                    disabled={
                      busy ||
                      !catalog.data?.available ||
                      totalCount === 0 ||
                      totalCount > 100
                    }
                    onClick={() => start.mutate({ smoke: false })}
                  >
                    <ListChecks className="size-4" />
                    运行全部 {totalCount} 项
                  </button>
                </>
              )}
            </div>
          </div>
          {!canExecute && (
            <p className="text-muted-foreground mt-3 text-xs">
              可查看和导出记录；启动、取消、重跑与人工复核需要管理员权限。
            </p>
          )}
          {catalog.data && !catalog.data.available && (
            <p className="mt-3 text-sm text-amber-800">
              自动评测暂不可用，请稍后重试或联系管理员。
            </p>
          )}
          <details className="text-muted-foreground mt-3 text-xs">
            <summary className="cursor-pointer">
              查看用例集与覆盖范围（{catalog.data?.cases.length ?? 0} 项）
            </summary>
            <p className="mt-2">
              当前启用 {totalCount} 项测试。内置方法为 10 类场景 × 3 种模式，
              可在“测试问题与方法”中查看完整题目和规则；管理员可新增、删除或恢复问题。
              测试结果仅反映流程检查。单批最多运行 100 项。
            </p>
            <ul className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {catalog.data?.cases.map((item) => (
                <li key={item.id}>
                  {item.title} · {evaluationModeLabel(item.mode)}
                </li>
              ))}
            </ul>
          </details>
        </div>

        {(error ?? exportError) && (
          <div
            role="alert"
            className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800"
          >
            <span>
              {error
                ? publicErrorMessage(
                    error,
                    "暂时无法读取或更新评测记录，请重试。",
                  )
                : exportError}
            </span>
            <button type="button" className="underline" onClick={refresh}>
              重试读取
            </button>
          </div>
        )}
        {batches.isLoading ? (
          <BusinessLoadingState label="正在读取评测记录…" />
        ) : !batches.error && !hasRecords && offset === 0 ? (
          <BusinessEmptyState
            icon={FlaskConical}
            title="暂无自动评测记录"
            description="管理员运行启用的测试问题后，这里会显示实际批次、指标与测试详情。"
          />
        ) : null}

        {(hasRecords || offset > 0) && (
          <>
            <div className="xingxi-panel border-border bg-card flex flex-wrap items-end gap-3 rounded-xl border p-4 shadow-sm">
              <label className="flex min-w-0 flex-1 flex-col gap-2 text-xs font-medium text-slate-500">
                评测批次
                <select
                  aria-label="评测批次"
                  className={selectStyle}
                  value={activeId ?? ""}
                  onChange={(event) => choose(event.target.value)}
                >
                  {!history.length && !selectedId && (
                    <option value="">当前时间范围内无批次</option>
                  )}
                  {selectedId &&
                    !history.some((item) => item.id === selectedId) && (
                      <option value={selectedId}>
                        所选批次 ·{" "}
                        {batch ? evaluationLabel(batch.status) : "读取中"}
                      </option>
                    )}
                  {history.map((item) => (
                    <option key={item.id} value={item.id}>
                      {new Date(item.created_at).toLocaleString()} ·{" "}
                      {evaluationLabel(item.status)} · {item.passed}/
                      {item.total}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-2 text-xs font-medium text-slate-500">
                历史时间范围
                <select
                  aria-label="历史时间范围"
                  className={selectStyle}
                  value={days}
                  onChange={(event) => {
                    setDays(Number(event.target.value));
                    setSelectedId(null);
                    setTrajectory(null);
                  }}
                >
                  <option value={0}>全部时间</option>
                  <option value={7}>最近 7 天</option>
                  <option value={30}>最近 30 天</option>
                </select>
              </label>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className={evaluationButton}
                  aria-label="上一页批次"
                  disabled={offset === 0 || batches.isFetching}
                  onClick={() => paginate(offset - 20)}
                >
                  <ChevronLeft className="size-4" />
                </button>
                <span className="text-xs text-slate-500">
                  第 {offset / 20 + 1} 页
                </span>
                <button
                  type="button"
                  className={evaluationButton}
                  aria-label="下一页批次"
                  disabled={batches.data?.length !== 20 || batches.isFetching}
                  onClick={() => paginate(offset + 20)}
                >
                  <ChevronRight className="size-4" />
                </button>
              </div>
              <p className="basis-full text-xs text-slate-500">
                时间筛选和趋势图仅覆盖当前历史页，每页最多 20
                个批次；下方指标统计所选批次，表格筛选不改变批次指标。
              </p>
            </div>

            <div
              className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"
              aria-label="当前批次指标"
            >
              <MetricCard
                title="规则通过率"
                value={
                  metrics.passRate == null
                    ? "未采集"
                    : `${metrics.passRate.toFixed(1)}%`
                }
                description={
                  batch
                    ? `通过 ${batch.passed} / 计划 ${batch.total}${batch.status !== "completed" ? " · 当前进度，尚未完成" : ""}`
                    : "当前批次"
                }
                icon={ShieldCheck}
                tone="emerald"
              />
              <MetricCard
                title="平均用例耗时"
                value={
                  metrics.averageMs == null
                    ? "未采集"
                    : `${(metrics.averageMs / 1000).toFixed(2)}s`
                }
                description={`测试耗时 · ${metrics.durationSamples} 个有效样本`}
                icon={Clock3}
                tone="teal"
              />
              <MetricCard
                title="执行错误数"
                value={
                  metrics.errors == null ? "未采集" : String(metrics.errors)
                }
                description="处理异常与规则未通过分别统计"
                icon={TriangleAlert}
                tone="rose"
              />
              <MetricCard
                title="待复核数"
                value={
                  metrics.needsReview == null
                    ? "未采集"
                    : String(metrics.needsReview)
                }
                description="需要进一步人工核查的规则判定"
                icon={Activity}
                tone="amber"
              />
            </div>

            <div className="grid gap-5 xl:grid-cols-[3fr_2fr]">
              <EvaluationHistoryChart
                batches={history}
                selectedId={activeId}
                onSelect={choose}
              />
              <EvaluationDistributionChart batch={batch} />
            </div>
            {detail.isLoading && (
              <BusinessLoadingState label="正在读取当前批次…" />
            )}
            {batch && (
              <>
                <div className="xingxi-panel border-border bg-card rounded-xl border p-5 shadow-sm">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h3 className="font-semibold">{batchLabel}</h3>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {canExecute &&
                        ["queued", "running"].includes(batch.status) && (
                          <button
                            type="button"
                            className={evaluationButton}
                            disabled={busy || batch.cancel_requested}
                            onClick={() => cancel.mutate(batch.id)}
                          >
                            <Square className="size-3.5" />
                            {batch.cancel_requested ? "正在停止" : "取消评测"}
                          </button>
                        )}
                      {canExecute &&
                        !["queued", "running"].includes(batch.status) &&
                        batch.passed < batch.total && (
                          <button
                            type="button"
                            className={evaluationButton}
                            disabled={busy}
                            onClick={() => rerun.mutate(batch.id)}
                          >
                            <RefreshCw className="size-3.5" />
                            重跑未通过项
                          </button>
                        )}
                      {(["markdown", "csv"] as const).map((format) => (
                        <button
                          type="button"
                          key={format}
                          className={evaluationButton}
                          onClick={() => {
                            setExportError(null);
                            void downloadAgentReport(batch.id, format).catch(
                              (reason: unknown) =>
                                setExportError(
                                  publicErrorMessage(
                                    reason,
                                    "报告导出失败，请重试。",
                                  ),
                                ),
                            );
                          }}
                        >
                          <Download className="size-3.5" />
                          {format === "markdown"
                            ? "下载文字报告"
                            : "下载表格报告"}
                        </button>
                      ))}
                    </div>
                  </div>
                  {batch.parent_id && (
                    <button
                      type="button"
                      className="text-primary mt-3 text-sm underline"
                      onClick={() => choose(batch.parent_id!)}
                    >
                      查看原批次及失败记录
                    </button>
                  )}
                  {batch.error_message && (
                    <p
                      role="alert"
                      className="mt-3 rounded-lg bg-rose-50 p-3 text-sm text-rose-800"
                    >
                      {publicErrorMessage(
                        batch.error_message,
                        "本批测试未能完成，请重试。",
                      )}
                    </p>
                  )}
                </div>

                <section
                  className="xingxi-panel border-border bg-card overflow-hidden rounded-xl border shadow-sm"
                  aria-label="测试记录"
                >
                  <div className="border-border border-b p-5">
                    <div className="flex items-center justify-between gap-3">
                      <h3 className="font-semibold">测试记录</h3>
                      <span className="text-xs text-slate-500">
                        显示 {visible.length} / {batch.results.length} 条 · 计划{" "}
                        {batch.total} 项
                      </span>
                    </div>
                    <div className="mt-4 flex flex-wrap gap-2">
                      <label className="relative min-w-48 flex-1">
                        <Search className="pointer-events-none absolute top-3 left-3 size-4 text-slate-400" />
                        <input
                          aria-label="搜索测试记录"
                          placeholder="搜索问题、用例或实际回答"
                          value={query}
                          onChange={(event) => setQuery(event.target.value)}
                          className={cn(selectStyle, "w-full pl-9")}
                        />
                      </label>
                      <select
                        aria-label="场景筛选"
                        className={selectStyle}
                        value={scenario}
                        onChange={(event) => setScenario(event.target.value)}
                      >
                        <option value="all">全部场景</option>
                        {scenarioOptions.map((item) => (
                          <option key={item} value={item}>
                            {scenarioLabels[item] ?? "其他场景"}
                          </option>
                        ))}
                      </select>
                      <select
                        aria-label="执行模式筛选"
                        className={selectStyle}
                        value={mode}
                        onChange={(event) => setMode(event.target.value)}
                      >
                        <option value="all">全部模式</option>
                        <option value="flash">快速</option>
                        <option value="pro">标准</option>
                        <option value="ultra">深入</option>
                      </select>
                      <select
                        aria-label="结果筛选"
                        className={selectStyle}
                        value={outcome}
                        onChange={(event) => setOutcome(event.target.value)}
                      >
                        <option value="all">全部结果</option>
                        <option value="unpassed">未通过 / 未完成</option>
                        {[
                          "passed",
                          "failed",
                          "needs_review",
                          "error",
                          "running",
                          "queued",
                          "cancelled",
                          "skipped",
                        ].map((item) => (
                          <option key={item} value={item}>
                            {evaluationLabel(item)}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[900px] text-left text-sm">
                      <thead className="bg-slate-50 text-xs text-slate-500">
                        <tr>
                          {[
                            "输入场景",
                            "测试方式",
                            "资料查阅",
                            "执行状态",
                            "规则判定",
                            "耗时",
                            "操作",
                          ].map((label) => (
                            <th
                              key={label}
                              scope="col"
                              className="px-4 py-3 font-medium"
                            >
                              {label}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {visible.map((item) => (
                          <tr
                            key={item.attempt_id}
                            className="hover:bg-muted/60 transition-colors"
                          >
                            <td className="max-w-72 px-4 py-4">
                              <p className="font-medium">{item.case.title}</p>
                              <p
                                className="mt-1 truncate text-xs text-slate-500"
                                title={item.case.question}
                              >
                                {item.case.question}
                              </p>
                              {item.error && (
                                <p className="mt-1 text-xs text-rose-700">
                                  {publicErrorMessage(
                                    item.error,
                                    "本题未能完成，请重试或人工复核。",
                                  )}
                                </p>
                              )}
                            </td>
                            <td className="px-4 py-4 whitespace-nowrap">
                              {evaluationModeLabel(item.case.mode)}
                            </td>
                            <td className="px-4 py-4 font-mono text-xs">
                              {item.events.length
                                ? item.events.filter(
                                    (event) => event.type === "tool_call",
                                  ).length
                                : "未采集"}
                            </td>
                            <td className="px-4 py-4">
                              <EvaluationBadge value={item.status} />
                            </td>
                            <td className="px-4 py-4">
                              <EvaluationBadge value={item.verdict} />
                            </td>
                            <td className="px-4 py-4 font-mono text-xs whitespace-nowrap">
                              {item.elapsed_ms != null &&
                              Number.isFinite(item.elapsed_ms) &&
                              item.elapsed_ms >= 0
                                ? `${(item.elapsed_ms / 1000).toFixed(2)}s`
                                : "未采集"}
                            </td>
                            <td className="px-4 py-4">
                              <button
                                type="button"
                                className="text-primary inline-flex items-center gap-1 text-xs font-medium whitespace-nowrap hover:underline"
                                aria-label={`${item.case.title} · 查看详情`}
                                onClick={() =>
                                  setTrajectory({
                                    batchId: batch.id,
                                    caseId: item.case_id,
                                  })
                                }
                              >
                                查看详情
                                <ArrowRight className="size-3" />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {!visible.length && (
                    <p className="p-8 text-center text-sm text-slate-500">
                      {batch.results.length
                        ? "没有符合筛选条件的测试记录。"
                        : "尚无用例执行记录，未执行不代表通过。"}
                    </p>
                  )}
                </section>
              </>
            )}
          </>
        )}
      </section>
      <AgentEvaluationDetail
        observation={observation}
        batch={batch}
        canReview={canExecute}
        onUpdated={updateBatch}
        onClose={() => setTrajectory(null)}
      />
    </>
  );
}

function MetricCard({
  title,
  value,
  description,
  icon: Icon,
  tone,
}: {
  title: string;
  value: string;
  description: string;
  icon: typeof Activity;
  tone: "emerald" | "teal" | "rose" | "amber";
}) {
  const tones = {
    emerald: "bg-emerald-50 text-emerald-700",
    teal: "bg-muted/60 text-primary",
    rose: "bg-rose-50 text-rose-700",
    amber: "bg-amber-50 text-amber-700",
  };
  return (
    <section
      className="xingxi-panel border-border bg-card rounded-xl border p-5 shadow-sm"
      aria-label={title}
    >
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-medium text-slate-500">{title}</h3>
        <span className={cn("rounded-lg p-2", tones[tone])}>
          <Icon className="size-4" aria-hidden="true" />
        </span>
      </div>
      <p className="mt-4 text-3xl font-semibold tracking-tight tabular-nums">
        {value}
      </p>
      <p className="mt-3 text-xs leading-5 text-slate-500">{description}</p>
    </section>
  );
}
