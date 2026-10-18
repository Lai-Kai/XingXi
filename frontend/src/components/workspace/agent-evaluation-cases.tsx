"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, Plus, RotateCcw, Trash2 } from "lucide-react";
import { useState } from "react";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { scenarioLabels } from "@/core/operations/evaluation-dashboard";
import {
  createAgentCase,
  deleteAgentCase,
  loadAgentCases,
  restoreAgentCase,
  type AgentCase,
  type AgentCaseInput,
} from "@/core/operations/evaluations";

import { evaluationButton } from "./agent-evaluation-ui";

const field =
  "w-full rounded-md border border-[#cbd8da] bg-white px-3 py-2 text-sm";
const displayTerms = (
  values: string[] | undefined,
  separator: string,
  fallback: string,
) => (values?.length ? values.join(separator) : fallback);
const terms = (value: string) => [
  ...new Set(
    value
      .split("\n")
      .map((term) => term.trim())
      .filter(Boolean),
  ),
];

export function AgentEvaluationCases({
  open,
  onOpenChange,
  canManage,
  canRun,
  onRun,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  canManage: boolean;
  canRun: boolean;
  onRun: (id: string) => void;
}) {
  const queryClient = useQueryClient();
  const [showDeleted, setShowDeleted] = useState(false);
  const [query, setQuery] = useState("");
  const [adding, setAdding] = useState(false);
  const [title, setTitle] = useState("");
  const [question, setQuestion] = useState("");
  const [scenario, setScenario] = useState("grounded");
  const [mode, setMode] = useState<AgentCase["mode"]>("pro");
  const [expected, setExpected] = useState("");
  const [forbidden, setForbidden] = useState("");
  const collection = useQuery({
    queryKey: ["agent-evaluations", "cases"],
    queryFn: ({ signal }) => loadAgentCases(signal),
    enabled: open,
  });
  const changed = async () => {
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: ["agent-evaluations", "cases"],
      }),
      queryClient.invalidateQueries({
        queryKey: ["agent-evaluations", "catalog"],
      }),
    ]);
  };
  const create = useMutation({
    mutationFn: createAgentCase,
    onSuccess: async () => {
      setTitle("");
      setQuestion("");
      setExpected("");
      setForbidden("");
      setAdding(false);
      await changed();
    },
  });
  const remove = useMutation({
    mutationFn: deleteAgentCase,
    onSuccess: changed,
  });
  const restore = useMutation({
    mutationFn: restoreAgentCase,
    onSuccess: changed,
  });
  const busy = create.isPending || remove.isPending || restore.isPending;
  const error =
    collection.error ?? create.error ?? remove.error ?? restore.error;
  const method = collection.data?.methods.find(
    (item) => item.scenario === scenario,
  );
  const filtered = (collection.data?.cases ?? []).filter(
    (item) =>
      (showDeleted || item.active) &&
      `${item.title} ${item.question} ${item.mode} ${scenarioLabels[item.scenario] ?? item.scenario}`
        .toLowerCase()
        .includes(query.trim().toLowerCase()),
  );

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full gap-0 bg-[#f7fafb] sm:max-w-[900px]">
        <SheetHeader className="border-b bg-white p-5 pr-12">
          <SheetTitle>测试问题与方法</SheetTitle>
          <SheetDescription>
            查看完整题目、测试方法和判定规则。当前使用合成资料与固定模型回放；新增问题沿用所选方法的检索和回答脚本，不会查询真实文献库或调用真实模型。
          </SheetDescription>
        </SheetHeader>
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4 sm:p-5">
          <div className="flex flex-wrap items-center gap-3">
            <input
              aria-label="搜索测试问题"
              placeholder="搜索问题、方法或模式"
              className={`${field} min-w-40 flex-1`}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={showDeleted}
                onChange={(event) => setShowDeleted(event.target.checked)}
              />
              显示已删除问题
            </label>
            {canManage && (
              <button
                type="button"
                className={evaluationButton}
                onClick={() => {
                  create.reset();
                  setAdding((value) => !value);
                }}
              >
                <Plus className="size-4" />
                新增问题
              </button>
            )}
          </div>
          {error && (
            <p
              role="alert"
              className="rounded-md bg-rose-50 p-3 text-sm text-rose-800"
            >
              {error.message}
              <button
                type="button"
                className="ml-3 underline"
                onClick={() => {
                  void collection.refetch();
                  create.reset();
                  remove.reset();
                  restore.reset();
                }}
              >
                重试读取
              </button>
            </p>
          )}
          {adding && canManage && (
            <form
              aria-label="新增测试问题"
              className="space-y-4 rounded-xl border bg-white p-4"
              onSubmit={(event) => {
                event.preventDefault();
                const input: AgentCaseInput = {
                  title: title.trim(),
                  question: question.trim(),
                  scenario,
                  mode,
                };
                if (expected.trim()) input.expected_terms = terms(expected);
                if (forbidden.trim()) input.forbidden_terms = terms(forbidden);
                create.mutate(input);
              }}
            >
              <label className="block space-y-1 text-sm">
                <span>题目名称</span>
                <input
                  required
                  maxLength={120}
                  className={field}
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                />
              </label>
              <label className="block space-y-1 text-sm">
                <span>测试问题</span>
                <textarea
                  required
                  maxLength={4000}
                  rows={3}
                  className={field}
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                />
              </label>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="space-y-1 text-sm">
                  <span>测试方法</span>
                  <select
                    className={field}
                    value={scenario}
                    onChange={(event) => {
                      setScenario(event.target.value);
                      setExpected("");
                      setForbidden("");
                    }}
                  >
                    {collection.data?.methods.map((item) => (
                      <option key={item.scenario} value={item.scenario}>
                        {scenarioLabels[item.scenario] ?? item.title}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="space-y-1 text-sm">
                  <span>运行模式</span>
                  <select
                    className={field}
                    value={mode}
                    onChange={(event) =>
                      setMode(event.target.value as AgentCase["mode"])
                    }
                  >
                    <option value="flash">flash</option>
                    <option value="pro">pro</option>
                    <option value="ultra">ultra</option>
                  </select>
                </label>
              </div>
              {method && (
                <p className="rounded-md bg-[#edf5f5] p-3 text-sm leading-6">
                  {method.description}
                </p>
              )}
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="space-y-1 text-sm">
                  <span>回答必含词（每行一项，留空沿用默认）</span>
                  <textarea
                    rows={2}
                    maxLength={4000}
                    className={field}
                    placeholder={displayTerms(
                      method?.expected_terms,
                      "\n",
                      "无默认必含词",
                    )}
                    value={expected}
                    onChange={(event) => setExpected(event.target.value)}
                  />
                </label>
                <label className="space-y-1 text-sm">
                  <span>回答禁含词（每行一项，留空沿用默认）</span>
                  <textarea
                    rows={2}
                    maxLength={4000}
                    className={field}
                    placeholder={displayTerms(
                      method?.forbidden_terms,
                      "\n",
                      "无默认禁含词",
                    )}
                    value={forbidden}
                    onChange={(event) => setForbidden(event.target.value)}
                  />
                </label>
              </div>
              <p className="text-xs text-slate-500">
                每题绑定一种运行模式。保存后可单独运行，或随“运行全部”执行。
              </p>
              <div className="flex gap-2">
                <button
                  type="submit"
                  className={evaluationButton}
                  disabled={
                    busy || !method || !title.trim() || !question.trim()
                  }
                >
                  {create.isPending ? "正在保存…" : "保存问题"}
                </button>
                <button
                  type="button"
                  className={evaluationButton}
                  disabled={busy}
                  onClick={() => setAdding(false)}
                >
                  取消新增
                </button>
              </div>
            </form>
          )}
          {collection.isLoading ? (
            <p className="p-5 text-sm">正在读取测试问题…</p>
          ) : !collection.error && !filtered.length ? (
            <p className="p-5 text-sm text-slate-500">
              当前筛选下没有测试问题。
            </p>
          ) : null}
          {filtered.map((item) => (
            <article
              key={item.id}
              className="space-y-3 rounded-xl border bg-white p-4"
              aria-label={`测试问题：${item.title} · ${item.mode}`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="font-semibold">{item.title}</h3>
                <span className="text-xs text-slate-500">
                  {item.builtin ? "内置" : "自定义"} · {item.mode} ·{" "}
                  {scenarioLabels[item.scenario] ?? item.scenario} ·{" "}
                  {item.active ? "启用中" : "已删除"}
                </span>
              </div>
              <p className="text-sm leading-6 whitespace-pre-wrap">
                {item.question}
              </p>
              <details className="text-sm">
                <summary className="cursor-pointer text-[#276f79]">
                  查看测试方法与判定规则
                </summary>
                <div className="mt-2 space-y-2 rounded-md bg-[#f4f8f8] p-3 text-slate-600">
                  <p>
                    {
                      collection.data?.methods.find(
                        (candidate) => candidate.scenario === item.scenario,
                      )?.description
                    }
                  </p>
                  <p>
                    预期工具：{item.required_tool ?? "无工具要求"}；预期终态：
                    {item.expected_run_status === "interrupted"
                      ? "已中断"
                      : "成功完成"}
                    ；超时：{item.timeout_seconds ?? 30} 秒。
                  </p>
                  <p>
                    至少 {item.min_citations ?? 0} 条有效引用
                    {item.expect_empty_evidence ? "；检索证据必须为空" : ""}。
                  </p>
                  <p>
                    必含词：{displayTerms(item.expected_terms, "、", "无")}
                    ；禁含词：
                    {displayTerms(item.forbidden_terms, "、", "无")}。
                  </p>
                  <p>{item.review_rubric}</p>
                </div>
              </details>
              {canManage && (
                <div className="flex flex-wrap gap-2">
                  {item.active ? (
                    <>
                      <button
                        type="button"
                        className={evaluationButton}
                        disabled={!canRun || busy}
                        onClick={() => onRun(item.id)}
                        aria-label={`运行题目：${item.title} · ${item.mode}`}
                      >
                        <Play className="size-3.5" />
                        运行这题
                      </button>
                      <button
                        type="button"
                        className={evaluationButton}
                        disabled={busy}
                        onClick={() => {
                          restore.reset();
                          remove.mutate(item.id);
                        }}
                        aria-label={`删除题目：${item.title} · ${item.mode}`}
                      >
                        <Trash2 className="size-3.5" />
                        删除问题
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      className={evaluationButton}
                      disabled={busy}
                      onClick={() => {
                        remove.reset();
                        restore.mutate(item.id);
                      }}
                      aria-label={`恢复题目：${item.title} · ${item.mode}`}
                    >
                      <RotateCcw className="size-3.5" />
                      恢复问题
                    </button>
                  )}
                </div>
              )}
            </article>
          ))}
          <p className="text-xs leading-5 text-slate-500">
            删除只影响后续新批次，可在“显示已删除问题”中恢复。历史批次和历史重跑继续使用原题目快照。
          </p>
        </div>
      </SheetContent>
    </Sheet>
  );
}
