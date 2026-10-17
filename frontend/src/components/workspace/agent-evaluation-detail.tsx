"use client";

import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, FileText, MessageSquare, Wrench } from "lucide-react";
import { useState } from "react";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { orderedEvents } from "@/core/operations/evaluation-dashboard";
import {
  evaluationLabel,
  reviewAgentEvaluation,
  type AgentEvaluation,
  type AgentObservation,
} from "@/core/operations/evaluations";

import {
  EvaluationBadge,
  evaluationButton,
  EvaluationJson,
} from "./agent-evaluation-ui";

const formatValue = (value: unknown) =>
  typeof value === "string" ? value : JSON.stringify(value ?? null, null, 2);
const eventLabels: Record<string, string> = {
  tool_call: "工具调用",
  tool_result: "工具返回",
  "run.started": "运行开始",
  "run.completed": "运行结束",
  "run.cancelled": "运行取消",
  "run.interrupted": "运行中断",
};

export function AgentEvaluationDetail({
  observation,
  batch,
  canReview,
  onUpdated,
  onClose,
}: {
  observation?: AgentObservation;
  batch?: AgentEvaluation;
  canReview: boolean;
  onUpdated: (batch: AgentEvaluation) => Promise<void>;
  onClose: () => void;
}) {
  return (
    <Sheet
      open={Boolean(observation && batch)}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <SheetContent className="bg-card w-full gap-0 sm:max-w-[760px]">
        <SheetHeader className="border-border bg-card border-b p-6 pr-12">
          <SheetTitle>{observation?.case.title} · 轨迹详情</SheetTitle>
          <SheetDescription>
            可观察的运行事件、工具、回答与证据；固定模型回放不代表真实模型质量。
          </SheetDescription>
        </SheetHeader>
        <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6">
          {observation && batch && (
            <ObservationDetail
              key={`${batch.id}:${observation.attempt_id}`}
              observation={observation}
              batch={batch}
              canReview={canReview}
              onUpdated={onUpdated}
            />
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function ObservationDetail({
  observation,
  batch,
  canReview,
  onUpdated,
}: {
  observation: AgentObservation;
  batch: AgentEvaluation;
  canReview: boolean;
  onUpdated: (batch: AgentEvaluation) => Promise<void>;
}) {
  const [note, setNote] = useState("");
  const [decision, setDecision] = useState<
    "confirmed" | "disagreed" | "needs_review"
  >("confirmed");
  const review = useMutation({
    mutationFn: () =>
      reviewAgentEvaluation(batch.id, {
        case_id: observation.case_id,
        decision,
        note,
      }),
    onSuccess: async (next) => {
      setNote("");
      await onUpdated(next);
    },
  });
  const events = orderedEvents(observation.events);
  const reviews = batch.reviews.filter(
    (item) => item.case_id === observation.case_id,
  );
  const box = "rounded-xl border border-border bg-card p-4 shadow-sm";
  return (
    <article className="space-y-5" aria-label="用例详情">
      <section className={box}>
        <div className="flex flex-wrap gap-2">
          <EvaluationBadge value={observation.status} />
          <EvaluationBadge value={observation.verdict} />
        </div>
        <dl className="text-muted-foreground mt-4 grid gap-2 font-mono text-xs break-all">
          <div>
            <dt className="inline">Batch：</dt>
            <dd className="inline">{batch.id}</dd>
          </div>
          <div>
            <dt className="inline">Case：</dt>
            <dd className="inline">
              {observation.case_id} · v{observation.case.version} ·{" "}
              {observation.case.mode}
            </dd>
          </div>
          <div>
            <dt className="inline">Run：</dt>
            <dd className="inline">{observation.agent_run_id ?? "尚未创建"}</dd>
          </div>
          <div>
            <dt className="inline">Thread：</dt>
            <dd className="inline">{observation.thread_id ?? "未采集"}</dd>
          </div>
          <div>
            <dt className="inline">Release：</dt>
            <dd className="inline">{observation.release_id ?? "未采集"}</dd>
          </div>
        </dl>
        <p className="text-muted-foreground mt-3 text-xs leading-5">
          {observation.case.review_rubric}
        </p>
        {observation.error && (
          <p
            role="alert"
            className="bg-heritage-rejected-surface text-heritage-rejected-foreground mt-3 rounded-lg p-3 text-sm"
          >
            {observation.error}
          </p>
        )}
      </section>
      <section className={box}>
        <h3 className="font-semibold">执行时间线</h3>
        <p className="text-muted-foreground mt-1 text-xs">
          事件按持久化序号排列；缺失事件不补造。
        </p>
        <ol className="border-border mt-5 ml-3 border-l-2">
          <li className="relative pb-6 pl-7">
            <TimelineDot icon={MessageSquare} />
            <h4 className="text-sm font-semibold">用户输入</h4>
            <p className="mt-2 text-sm leading-6 whitespace-pre-wrap">
              {observation.case.question}
            </p>
          </li>
          {events.map((event, index) => (
            <li key={`${event.seq}:${index}`} className="relative pb-6 pl-7">
              <TimelineDot
                icon={
                  event.type === "tool_call" || event.type === "tool_result"
                    ? Wrench
                    : CheckCircle2
                }
              />
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h4 className="text-sm font-semibold">
                  {eventLabels[event.type] ?? event.type}
                  {event.name ? ` · ${event.name}` : ""}
                </h4>
                <span className="font-mono text-xs text-slate-400">
                  #{event.seq} ·{" "}
                  {event.at
                    ? new Date(event.at).toLocaleTimeString()
                    : "未采集时间"}
                </span>
              </div>
              <div className="mt-2 space-y-2">
                {event.args != null && (
                  <EvaluationJson label="调用参数" value={event.args} />
                )}
                {event.output != null && (
                  <EvaluationJson label="返回结果" value={event.output} />
                )}
              </div>
            </li>
          ))}
          {!events.length && (
            <li className="text-muted-foreground pb-6 pl-7 text-sm">
              尚无执行事件。
            </li>
          )}
          <li className="relative pl-7">
            <TimelineDot icon={FileText} />
            <h4 className="text-sm font-semibold">最终回答</h4>
            <p className="mt-2 text-sm leading-6 break-words whitespace-pre-wrap">
              {observation.answer?.trim() ? observation.answer : "尚无回答记录"}
            </p>
          </li>
        </ol>
      </section>
      <section className={box}>
        <h3 className="font-semibold">逐项检查</h3>
        <div className="mt-3 space-y-2">
          {observation.checks.map((check) => (
            <details
              key={check.key}
              className="border-border rounded-lg border p-3 text-sm"
            >
              <summary className="cursor-pointer">
                <EvaluationBadge value={check.status} />
                <span className="ml-2">{check.label}</span>
              </summary>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                {[
                  { label: "期望", value: check.expected },
                  { label: "实际", value: check.actual },
                ].map((item) => (
                  <div key={item.label} className="bg-muted rounded-lg p-3">
                    <strong className="text-muted-foreground text-xs">
                      {item.label}
                    </strong>
                    <pre className="mt-2 text-xs break-all whitespace-pre-wrap">
                      {formatValue(item.value)}
                    </pre>
                  </div>
                ))}
              </div>
            </details>
          ))}
        </div>
        {!observation.checks.length && (
          <p className="text-muted-foreground mt-3 text-sm">尚未完成判定。</p>
        )}
      </section>
      <section className={box}>
        <h3 className="font-semibold">引用证据核对</h3>
        {observation.evidence.map((item) => (
          <div
            key={item.evidence_id}
            className="border-border mt-3 rounded-lg border p-3 text-sm"
          >
            <p className="font-medium">
              {item.document_title} · 第 {item.page_start}
              {item.page_end === item.page_start ? "" : `–${item.page_end}`} 页
            </p>
            <p
              className={`mt-2 text-xs ${item.verified ? "text-heritage-approved-foreground" : "text-heritage-rejected-foreground"}`}
            >
              {item.verified ? "已核对版本、授权与原文" : "证据核对失败"}
            </p>
            <blockquote className="border-border mt-3 border-l-2 pl-3 leading-6 whitespace-pre-wrap">
              {item.quote}
            </blockquote>
            <p className="text-muted-foreground mt-3 font-mono text-xs leading-5 break-all">
              Evidence：{item.evidence_id}
              <br />
              Chunk：{item.chunk_id}
              <br />
              Release：{item.release_id}
            </p>
          </div>
        ))}
        {!observation.evidence.length && (
          <p className="text-muted-foreground mt-3 text-sm">
            本次没有取得可核对的证据。
          </p>
        )}
      </section>
      <section className={box}>
        <h3 className="font-semibold">人工复核记录</h3>
        <p className="text-muted-foreground mt-1 text-xs">
          复核追加保存，原始规则判定保持可追溯。
        </p>
        {reviews.map((item) => (
          <div key={item.id} className="bg-muted mt-3 rounded-lg p-3 text-sm">
            <p className="text-muted-foreground text-xs">
              {evaluationLabel(item.decision)} · {item.actor_id} ·{" "}
              {new Date(item.created_at).toLocaleString()}
            </p>
            <p className="mt-2 whitespace-pre-wrap">{item.note}</p>
          </div>
        ))}
        {!reviews.length && (
          <p className="text-muted-foreground mt-3 text-sm">暂无人工复核。</p>
        )}
        {canReview && !["queued", "running"].includes(observation.status) && (
          <form
            className="mt-4 space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              if (note.trim()) review.mutate();
            }}
          >
            <select
              aria-label="复核结论"
              value={decision}
              onChange={(event) =>
                setDecision(event.target.value as typeof decision)
              }
              className="bg-card min-h-9 w-full rounded-lg border p-2 text-sm"
              disabled={review.isPending}
            >
              <option value="confirmed">确认原判定</option>
              <option value="disagreed">与原判定有分歧</option>
              <option value="needs_review">需要进一步复核</option>
            </select>
            <textarea
              aria-label="复核意见"
              placeholder="说明复核依据；原始测试结果会保留。"
              value={note}
              onChange={(event) => setNote(event.target.value)}
              maxLength={4000}
              className="block min-h-24 w-full rounded-lg border p-3 text-sm"
              disabled={review.isPending}
            />
            <button
              className={evaluationButton}
              disabled={!note.trim() || review.isPending}
            >
              {review.isPending ? "正在保存…" : "保存复核"}
            </button>
            {review.error && (
              <p
                role="alert"
                className="text-heritage-rejected-foreground text-sm"
              >
                {review.error.message}
              </p>
            )}
          </form>
        )}
      </section>
    </article>
  );
}

function TimelineDot({ icon: Icon }: { icon: typeof Wrench }) {
  return (
    <span className="bg-secondary text-primary absolute -left-[15px] flex size-7 items-center justify-center rounded-full border-2 border-white">
      <Icon className="size-3.5" aria-hidden="true" />
    </span>
  );
}
