"use client";

import { AlertTriangle, CheckCircle2, Plus, Scale, Trash2 } from "lucide-react";
import { type FormEvent, useState } from "react";

import {
  BusinessInlineError,
  BusinessMobileHeader,
  BusinessPageHeader,
} from "@/components/workspace/business-page";
import { resolveNameAuthority } from "@/core/name-authority/api";
import {
  parseEvidenceIds,
  type NameAuthorityResolution,
} from "@/core/name-authority/types";
import { cn } from "@/lib/utils";

type VariantDraft = { id: number; name: string; evidence: string };

const decisionLabel = {
  selected: "已形成首选名",
  needs_review: "需要人工复核",
  insufficient_evidence: "证据不足",
} as const;

export default function NameAuthorityPage() {
  const [variants, setVariants] = useState<VariantDraft[]>([
    { id: 1, name: "", evidence: "" },
    { id: 2, name: "", evidence: "" },
  ]);
  const [nextId, setNextId] = useState(3);
  const [context, setContext] = useState("");
  const [result, setResult] = useState<NameAuthorityResolution | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function updateVariant(id: number, patch: Partial<VariantDraft>) {
    setVariants((current) =>
      current.map((variant) =>
        variant.id === id ? { ...variant, ...patch } : variant,
      ),
    );
  }

  function addVariant() {
    setVariants((current) => [
      ...current,
      { id: nextId, name: "", evidence: "" },
    ]);
    setNextId((value) => value + 1);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      setResult(
        await resolveNameAuthority({
          variants: variants.map((variant) => ({
            name: variant.name.trim(),
            evidence_ids: parseEvidenceIds(variant.evidence),
          })),
          ...(context.trim() ? { research_context: context.trim() } : {}),
        }),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法完成异名辨析");
    } finally {
      setLoading(false);
    }
  }

  const valid = variants.every(
    (variant) =>
      variant.name.trim() && parseEvidenceIds(variant.evidence).length,
  );

  return (
    <main className="admin-workspace bg-background text-foreground size-full overflow-y-auto">
      <BusinessMobileHeader title="异名辨析" />
      <div className="mx-auto max-w-7xl px-4 py-7 sm:px-8 lg:px-10 lg:py-9">
        <BusinessPageHeader
          title="古籍异名辨析"
          description="依据已审核原文、来源等级和独立文献互证确定当前语境的首选名称，同时保留全部历史异名"
          icon={Scale}
        />

        {error && (
          <div className="mt-5">
            <BusinessInlineError
              message={error}
              onDismiss={() => setError(null)}
            />
          </div>
        )}

        <div className="mt-7 grid gap-7 lg:grid-cols-[24rem_minmax(0,1fr)]">
          <form onSubmit={(event) => void submit(event)} className="space-y-5">
            <div>
              <h2 className="text-sm font-semibold">候选名称与资料出处</h2>
              <p className="text-muted-foreground mt-1 text-xs leading-5">
                资料出处编号来自文史检索结果；多个编号可用空格、逗号或换行分隔。
              </p>
            </div>

            <label className="text-muted-foreground block text-xs font-medium">
              研究语境
              <input
                value={context}
                onChange={(event) => setContext(event.target.value)}
                maxLength={500}
                placeholder="例如：清代木渎镇区水系名称"
                className="border-border bg-card focus:border-primary/50 mt-1.5 h-10 w-full rounded-md border px-3 text-sm outline-none"
              />
            </label>

            <div className="space-y-3">
              {variants.map((variant, index) => (
                <fieldset
                  key={variant.id}
                  className="border-border border-t pt-3"
                >
                  <legend className="text-muted-foreground pr-2 text-xs font-semibold">
                    候选 {index + 1}
                  </legend>
                  <div className="mt-2 flex gap-2">
                    <input
                      value={variant.name}
                      onChange={(event) =>
                        updateVariant(variant.id, { name: event.target.value })
                      }
                      maxLength={255}
                      required
                      placeholder="古籍中的名称"
                      aria-label={`候选 ${index + 1} 名称`}
                      className="border-border bg-card focus:border-primary/50 h-10 min-w-0 flex-1 rounded-md border px-3 text-sm outline-none"
                    />
                    {variants.length > 2 && (
                      <button
                        type="button"
                        title="移除候选"
                        onClick={() =>
                          setVariants((current) =>
                            current.filter((item) => item.id !== variant.id),
                          )
                        }
                        className="border-border bg-card text-destructive hover:bg-accent grid size-10 shrink-0 place-items-center rounded-md border"
                      >
                        <Trash2 className="size-4" />
                      </button>
                    )}
                  </div>
                  <textarea
                    value={variant.evidence}
                    onChange={(event) =>
                      updateVariant(variant.id, {
                        evidence: event.target.value,
                      })
                    }
                    required
                    rows={2}
                    placeholder="资料出处编号"
                    aria-label={`候选 ${index + 1} 资料出处编号`}
                    className="border-border bg-card focus:border-primary/50 mt-2 w-full resize-y rounded-md border p-3 font-mono text-xs outline-none"
                  />
                </fieldset>
              ))}
            </div>

            <button
              type="button"
              onClick={addVariant}
              disabled={variants.length >= 20}
              className="border-border bg-card text-primary hover:bg-accent inline-flex h-9 items-center gap-2 rounded-md border px-3 text-sm disabled:opacity-40"
            >
              <Plus className="size-4" /> 添加候选名称
            </button>
            <button
              type="submit"
              disabled={!valid || loading}
              className="bg-primary text-primary-foreground hover:bg-primary inline-flex h-10 w-full items-center justify-center gap-2 rounded-md px-4 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-45"
            >
              <Scale className="size-4" />
              {loading ? "正在核验…" : "依据资料出处辨析"}
            </button>
          </form>

          <section aria-live="polite" className="min-w-0">
            {result ? (
              <div className="border-border bg-card border">
                <header className="border-border border-b px-6 py-5 sm:px-8">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-muted-foreground text-xs font-medium">
                        辨析结论
                      </p>
                      <h2 className="mt-2 text-xl font-semibold">
                        {result.preferred_name ?? "暂不自动确定首选名"}
                      </h2>
                    </div>
                    <span
                      className={cn(
                        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs",
                        result.decision === "selected"
                          ? "border-heritage-approved-border bg-heritage-approved-surface text-heritage-approved-foreground"
                          : "border-heritage-disputed-border bg-heritage-disputed-surface text-heritage-disputed-foreground",
                      )}
                    >
                      {result.decision === "selected" ? (
                        <CheckCircle2 className="size-3.5" />
                      ) : (
                        <AlertTriangle className="size-3.5" />
                      )}
                      {decisionLabel[result.decision]}
                    </span>
                  </div>
                  <p className="text-muted-foreground mt-4 text-sm leading-6">
                    {result.explanation}
                  </p>
                  <p className="text-muted-foreground mt-2 text-xs">
                    全部保留：{result.retained_names.join("、")}
                  </p>
                </header>

                <div className="divide-border divide-y">
                  {result.candidates.map((candidate) => (
                    <article key={candidate.name} className="px-6 py-5 sm:px-8">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <h3 className="font-serif text-lg font-semibold">
                          {candidate.name}
                        </h3>
                        <span className="text-primary text-sm font-semibold">
                          {candidate.score.toFixed(0)} 分
                        </span>
                      </div>
                      <p className="text-muted-foreground mt-1 text-xs">
                        最高来源等级：{candidate.best_source_level ?? "无"} ·
                        已审核独立文献：{candidate.reviewed_document_count}
                      </p>
                      <div className="mt-3 space-y-2">
                        {candidate.evidence.map((evidence) => (
                          <div
                            key={evidence.evidence_id}
                            className="border-primary/50 grid gap-1 border-l-2 pl-3 text-xs leading-5 sm:grid-cols-[1fr_auto]"
                          >
                            <span>
                              《{evidence.document_title}》
                              {evidence.edition ? ` · ${evidence.edition}` : ""}{" "}
                              · 第 {evidence.page_start}
                              {evidence.page_end !== evidence.page_start
                                ? `-${evidence.page_end}`
                                : ""}
                              页
                            </span>
                            <span className="text-muted-foreground">
                              {evidence.source_level}级 ·{" "}
                              {evidence.review_status}
                            </span>
                          </div>
                        ))}
                      </div>
                      {candidate.missing_evidence_ids.length > 0 && (
                        <p className="text-heritage-disputed-foreground mt-3 text-xs">
                          未找到资料出处：
                          {candidate.missing_evidence_ids.join("、")}
                        </p>
                      )}
                    </article>
                  ))}
                </div>
              </div>
            ) : (
              <div className="border-border bg-card/60 grid min-h-[32rem] place-items-center border border-dashed px-6 text-center">
                <div className="max-w-sm">
                  <Scale className="text-primary mx-auto size-9" />
                  <h2 className="mt-4 text-base font-medium">
                    不按出现次数决定名称
                  </h2>
                  <p className="text-muted-foreground mt-2 text-sm leading-6">
                    系统只使用真实、已审核的资料出处计算来源权威度；出处势均力敌时必须人工复核。
                  </p>
                </div>
              </div>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
