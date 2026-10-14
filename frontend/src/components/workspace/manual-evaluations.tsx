"use client";

import { BookCheck, CheckCircle2, XCircle } from "lucide-react";
import { useState } from "react";

import {
  canSubmitManualEvaluation,
  manualFailureLabel,
} from "@/core/operations/manual-evaluations";
import {
  formatMetricRate,
  type EvaluationCase,
  type EvaluationObservation,
  type EvaluationRun,
} from "@/core/operations/types";

type Props = {
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
};

const field =
  "w-full rounded-md border border-[#cbd8da] bg-white px-3 py-2 text-sm";
const button =
  "rounded-md border border-[#cbd8da] px-3 py-2 text-sm disabled:opacity-40";

function RecordedResults({
  run,
  cases,
}: {
  run: EvaluationRun;
  cases: EvaluationCase[];
}) {
  return (
    <div className="space-y-4">
      {run.results.map((result) => {
        const item = cases.find((candidate) => candidate.id === result.case_id);
        const Icon = result.passed ? CheckCircle2 : XCircle;
        return (
          <article
            key={result.case_id}
            className="rounded-lg border border-[#d7e1e2] bg-white p-5"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="font-semibold">{item?.name ?? "历史用例"}</h3>
                {item && (
                  <p className="mt-2 text-sm text-[#53676c]">{item.question}</p>
                )}
              </div>
              <span
                className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-sm ${result.passed ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-900"}`}
              >
                <Icon className="size-4" />
                {result.passed ? "通过" : "未通过"}
              </span>
            </div>
            <p className="mt-3 text-xs text-[#697a7f]">
              本次标记：{result.actual_status === "refused" ? "拒答" : "回答"} ·
              有效引用 {result.citation_count} 条
            </p>
            <div className="mt-4 rounded-md bg-[#f5f8f8] p-4">
              <p className="mb-2 text-xs font-semibold text-[#53676c]">
                已记录的模型回答
              </p>
              <p className="text-sm leading-7 break-words whitespace-pre-wrap">
                {result.answer || "未填写回答"}
              </p>
            </div>
            {result.passed ? (
              <p className="mt-4 text-sm text-emerald-800">
                录入内容满足此用例的状态、引用数和必含词要求。
              </p>
            ) : (
              <ul className="mt-4 list-inside list-disc space-y-1 text-sm text-amber-900">
                {result.failure_reasons.map((reason) => (
                  <li key={reason}>{manualFailureLabel(reason)}</li>
                ))}
              </ul>
            )}
          </article>
        );
      })}
    </div>
  );
}

export function ManualEvaluations({
  cases,
  runs,
  observations,
  onObservation,
  saving,
  onCreateCase,
  onRun,
}: Props) {
  const [name, setName] = useState("");
  const [question, setQuestion] = useState("");
  const [expected, setExpected] = useState<"answered" | "refused">("refused");
  const [citations, setCitations] = useState(0);
  const [terms, setTerms] = useState("");
  const active = cases.filter((item) => item.active);
  const latest = runs[0];
  const ready = canSubmitManualEvaluation(cases, observations);
  const complete =
    latest && latest.total > 0 && latest.results.length === latest.total;

  return (
    <section aria-label="人工观测评测" className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">简单测试</h2>
        <p className="mt-2 text-sm text-[#697a7f]">
          查看已录入回答的测试结果，也可以粘贴下一次回答再测。
        </p>
      </div>
      {latest && (
        <div className="space-y-4" aria-label="最近一次结果">
          <div
            className={`flex flex-wrap items-center justify-between gap-4 rounded-lg border p-5 ${complete && latest.passed === latest.total ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`}
          >
            <div>
              <p className="text-xs text-[#53676c]">
                {latest.created_by === "local-demo"
                  ? "使用你提供的回答 · 演示记录"
                  : "最近一次人工观测"}
              </p>
              <h3 className="mt-2 text-lg font-semibold">
                {complete
                  ? `${latest.passed} / ${latest.total} 条规则通过`
                  : "结果记录不完整"}
              </h3>
              <p className="mt-2 text-xs text-[#697a7f]">
                {new Date(latest.created_at).toLocaleString("zh-CN")}
              </p>
            </div>
            <div className="text-right">
              <p className="text-3xl font-semibold">
                {complete ? formatMetricRate(latest.pass_rate) : "未取得结果"}
              </p>
              <p className="mt-1 text-xs text-[#53676c]">规则通过率</p>
            </div>
          </div>
          <RecordedResults run={latest} cases={cases} />
          <p className="text-xs leading-6 text-[#697a7f]">
            判定只比较录入状态、引用数和必含词；回答中的史料与出处仍需核验。这条记录没有发起新的模型调用。
          </p>
        </div>
      )}
      <details
        open={!latest}
        className="rounded-lg border border-[#d7e1e2] bg-white p-5"
      >
        <summary className="cursor-pointer font-semibold">
          {latest ? "录入下一次回答" : "填写回答并测试"}
        </summary>
        <div className="mt-4 space-y-5">
          {active.map((item) => {
            const value = observations[item.id] ?? {
              case_id: item.id,
              actual_status: item.expected_status,
              citation_count: 0,
              answer: "",
            };
            const previous = latest?.results.find(
              (result) => result.case_id === item.id,
            );
            return (
              <article key={item.id} className="space-y-3">
                <h3 className="text-sm font-semibold">{item.name}</h3>
                <p className="text-sm text-[#53676c]">{item.question}</p>
                <p className="text-xs text-[#697a7f]">
                  期望{item.expected_status === "refused" ? "拒答" : "回答"} ·{" "}
                  {item.min_citations === 0
                    ? "不要求引用"
                    : `至少 ${item.min_citations} 条有效引用`}{" "}
                  ·{" "}
                  {item.required_terms.length
                    ? `必含词：${item.required_terms.join("、")}`
                    : "不要求固定措辞"}
                </p>
                <textarea
                  aria-label={`${item.name}的本次回答`}
                  rows={5}
                  value={value.answer}
                  onChange={(event) =>
                    onObservation({ ...value, answer: event.target.value })
                  }
                  placeholder="粘贴完整模型回答"
                  className={field}
                />
                <div className="flex flex-wrap items-end gap-3">
                  <label className="space-y-1 text-xs text-[#53676c]">
                    <span className="block">本次回答状态</span>
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
                      className={field}
                    >
                      <option value="refused">本次已拒答</option>
                      <option value="answered">本次已回答</option>
                    </select>
                  </label>
                  <label className="w-28 space-y-1 text-xs text-[#53676c]">
                    <span className="block">有效引用数</span>
                    <input
                      type="number"
                      min={0}
                      step={1}
                      value={value.citation_count}
                      onChange={(event) =>
                        onObservation({
                          ...value,
                          citation_count: Number(event.target.value),
                        })
                      }
                      className={field}
                    />
                  </label>
                  {previous?.answer && (
                    <button
                      type="button"
                      className={button}
                      onClick={() =>
                        onObservation({
                          case_id: item.id,
                          answer: previous.answer,
                          actual_status: previous.actual_status,
                          citation_count: previous.citation_count,
                        })
                      }
                    >
                      使用上次回答
                    </button>
                  )}
                </div>
              </article>
            );
          })}
          {!active.length && (
            <p className="text-sm text-[#697a7f]">
              暂无启用用例，可在下方新增。
            </p>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              disabled={saving || !ready}
              onClick={() => void onRun()}
              className="flex items-center gap-2 rounded-md bg-[#205f68] px-4 py-2 text-sm text-white disabled:opacity-40"
            >
              <BookCheck className="size-4" />
              {saving ? "正在保存…" : "保存并查看结果"}
            </button>
            {!ready && active.length > 0 && (
              <p className="text-xs text-[#697a7f]">
                请先填写每条启用用例的回答，并填入非负整数引用数。
              </p>
            )}
          </div>
        </div>
      </details>
      <details className="rounded-lg border border-[#d7e1e2] bg-white p-5">
        <summary className="cursor-pointer text-sm font-semibold">
          查看历史记录（{runs.length} 次）
        </summary>
        <div className="mt-4 space-y-3">
          {runs.map((run) => (
            <details
              key={run.id}
              className="rounded-md border border-[#d7e1e2] p-3"
            >
              <summary className="cursor-pointer text-sm">
                {new Date(run.created_at).toLocaleString("zh-CN")} ·{" "}
                {run.passed} / {run.total} 通过
              </summary>
              <p className="my-3 text-xs break-all text-[#697a7f]">
                知识版本：{run.release_id ?? "未绑定"}
              </p>
              <RecordedResults run={run} cases={cases} />
            </details>
          ))}
          {!runs.length && (
            <p className="text-sm text-[#697a7f]">尚未保存测试记录。</p>
          )}
        </div>
      </details>
      <details className="rounded-lg border border-[#d7e1e2] bg-white p-5">
        <summary className="cursor-pointer text-sm font-semibold">
          高级设置：新增用例
        </summary>
        <form
          className="mt-4 grid max-w-xl gap-3"
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
            })
              .then(() => {
                setName("");
                setQuestion("");
                setTerms("");
              })
              .catch(() => undefined);
          }}
        >
          <input
            aria-label="用例名称"
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="用例名称"
            className={field}
          />
          <textarea
            aria-label="固定测试问题"
            required
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="固定测试问题"
            rows={3}
            className={field}
          />
          <div className="grid grid-cols-2 gap-3">
            <select
              aria-label="期望状态"
              value={expected}
              onChange={(event) =>
                setExpected(event.target.value as "answered" | "refused")
              }
              className={field}
            >
              <option value="refused">期望拒答</option>
              <option value="answered">期望回答</option>
            </select>
            <input
              type="number"
              min={0}
              step={1}
              value={citations}
              onChange={(event) => setCitations(Number(event.target.value))}
              aria-label="最低引用数"
              className={field}
            />
          </div>
          <input
            value={terms}
            onChange={(event) => setTerms(event.target.value)}
            aria-label="必含词"
            placeholder="必含词（可不填），用逗号分隔"
            className={field}
          />
          <button disabled={saving} className={button}>
            保存用例
          </button>
        </form>
      </details>
    </section>
  );
}
