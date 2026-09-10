"use client";

import {
  BookMarked,
  Clipboard,
  Printer,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import { type FormEvent, useState } from "react";
import { toast } from "sonner";

import {
  BusinessInlineError,
  BusinessMobileHeader,
  BusinessPageHeader,
} from "@/components/workspace/business-page";
import { createGlossLabel } from "@/core/glossary/api";
import type { GlossLabel, GlossLabelInput } from "@/core/glossary/types";

const initialForm: GlossLabelInput = {
  title: "桃花源记释读",
  object_name: "《桃花源记》选段",
  source_title: "晋·陶渊明《桃花源记》",
  volume: "",
  page: "",
  text: "缘溪行，忘路之远近。忽逢桃花林，夹岸数百步，中无杂树，芳草鲜美，落英缤纷。",
};

function labelText(label: GlossLabel): string {
  const source = [label.source_title, label.volume, label.page]
    .filter(Boolean)
    .join(" · ");
  const sentences = label.gloss.sentences
    .map((sentence) => `${sentence.original}\n释读：${sentence.modern}`)
    .join("\n\n");
  return [
    label.title,
    label.object_name,
    source ? `出处：${source}` : null,
    "",
    sentences,
    "",
    label.status_label,
  ]
    .filter((value) => value !== null)
    .join("\n");
}

export default function GlossaryPage() {
  const [form, setForm] = useState(initialForm);
  const [label, setLabel] = useState<GlossLabel | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function update<Key extends keyof GlossLabelInput>(
    key: Key,
    value: GlossLabelInput[Key],
  ) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!form.text.trim()) return;
    setLoading(true);
    setError(null);
    try {
      setLabel(await createGlossLabel(form));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法生成释读展签");
    } finally {
      setLoading(false);
    }
  }

  async function copyLabel() {
    if (!label) return;
    await navigator.clipboard.writeText(labelText(label));
    toast.success("展签内容已复制");
  }

  return (
    <main className="size-full overflow-y-auto bg-[#f4f7f6] text-[#203033]">
      <BusinessMobileHeader title="古文展签" />
      <div className="mx-auto max-w-7xl px-4 py-7 sm:px-8 lg:px-10 lg:py-9">
        <BusinessPageHeader
          title="古文释读展签"
          description="为古籍选段、碑刻题记和文物铭文制作出处清楚、原文与释读并列的阅读说明"
          icon={BookMarked}
          actions={
            label ? (
              <>
                <button
                  type="button"
                  onClick={() => void copyLabel()}
                  className="inline-flex h-9 items-center gap-2 rounded-md border border-[#c9d6d8] bg-white px-3 text-sm text-[#315f67] hover:bg-[#edf4f5]"
                >
                  <Clipboard className="size-4" /> 复制展签
                </button>
                <button
                  type="button"
                  onClick={() => window.print()}
                  className="inline-flex h-9 items-center gap-2 rounded-md bg-[#285f66] px-3 text-sm text-white hover:bg-[#1f5056]"
                >
                  <Printer className="size-4" /> 打印
                </button>
              </>
            ) : undefined
          }
        />

        {error && (
          <div className="mt-5">
            <BusinessInlineError
              message={error}
              onDismiss={() => setError(null)}
            />
          </div>
        )}

        <div className="mt-7 grid gap-6 lg:grid-cols-[21rem_minmax(0,1fr)]">
          <form
            onSubmit={(event) => void submit(event)}
            className="space-y-5 border-r-0 border-[#d8e1e1] lg:border-r lg:pr-6"
          >
            <div>
              <h2 className="text-sm font-semibold">展签信息</h2>
              <p className="mt-1 text-xs leading-5 text-[#708084]">
                出处信息会和释读一起展示；不清楚的字段可以留空。
              </p>
            </div>

            <label className="block text-xs font-medium text-[#52666a]">
              展签标题
              <input
                value={form.title}
                onChange={(event) => update("title", event.target.value)}
                maxLength={120}
                required
                className="mt-1.5 h-10 w-full rounded-md border border-[#cfdadb] bg-white px-3 text-sm outline-none focus:border-[#377780]"
              />
            </label>
            <label className="block text-xs font-medium text-[#52666a]">
              文物、篇名或对象
              <input
                value={form.object_name ?? ""}
                onChange={(event) => update("object_name", event.target.value)}
                maxLength={120}
                className="mt-1.5 h-10 w-full rounded-md border border-[#cfdadb] bg-white px-3 text-sm outline-none focus:border-[#377780]"
              />
            </label>
            <label className="block text-xs font-medium text-[#52666a]">
              书名或资料来源
              <input
                value={form.source_title ?? ""}
                onChange={(event) => update("source_title", event.target.value)}
                maxLength={255}
                className="mt-1.5 h-10 w-full rounded-md border border-[#cfdadb] bg-white px-3 text-sm outline-none focus:border-[#377780]"
              />
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="block text-xs font-medium text-[#52666a]">
                卷目
                <input
                  value={form.volume ?? ""}
                  onChange={(event) => update("volume", event.target.value)}
                  maxLength={120}
                  className="mt-1.5 h-10 w-full rounded-md border border-[#cfdadb] bg-white px-3 text-sm outline-none focus:border-[#377780]"
                />
              </label>
              <label className="block text-xs font-medium text-[#52666a]">
                页码
                <input
                  value={form.page ?? ""}
                  onChange={(event) => update("page", event.target.value)}
                  maxLength={60}
                  className="mt-1.5 h-10 w-full rounded-md border border-[#cfdadb] bg-white px-3 text-sm outline-none focus:border-[#377780]"
                />
              </label>
            </div>
            <label className="block text-xs font-medium text-[#52666a]">
              古文原文
              <textarea
                value={form.text}
                onChange={(event) => update("text", event.target.value)}
                maxLength={10_000}
                required
                rows={8}
                className="mt-1.5 w-full resize-y rounded-md border border-[#cfdadb] bg-white p-3 font-serif text-base leading-8 outline-none focus:border-[#377780]"
              />
              <span className="mt-1 block text-right font-normal text-[#879397]">
                {form.text.length}/10000
              </span>
            </label>
            <button
              type="submit"
              disabled={loading || !form.text.trim()}
              className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-md bg-[#285f66] px-4 text-sm font-medium text-white hover:bg-[#1f5056] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Sparkles className="size-4" />
              {loading ? "正在生成…" : "生成释读展签"}
            </button>
          </form>

          <section aria-live="polite" className="min-w-0">
            {label ? (
              <article className="border border-[#cad5d4] bg-white shadow-sm print:border-black print:shadow-none">
                <header className="border-b border-[#d9e2e1] px-6 py-5 sm:px-8">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-medium text-[#4c777c]">
                        星羲数字文史 · 释读展签
                      </p>
                      <h2 className="mt-2 font-serif text-2xl font-semibold">
                        {label.title}
                      </h2>
                      {label.object_name && (
                        <p className="mt-2 text-sm text-[#5f7074]">
                          {label.object_name}
                        </p>
                      )}
                    </div>
                    <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-300 bg-amber-50 px-2.5 py-1 text-xs text-amber-900">
                      <TriangleAlert className="size-3.5" />
                      {label.status_label}
                    </span>
                  </div>
                  {[label.source_title, label.volume, label.page].some(
                    Boolean,
                  ) && (
                    <p className="mt-4 border-l-2 border-[#6f9ba0] pl-3 text-xs leading-5 text-[#65777a]">
                      出处：
                      {[label.source_title, label.volume, label.page]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                  )}
                </header>

                <div className="divide-y divide-[#e2e8e7]">
                  {label.gloss.sentences.map((sentence, index) => (
                    <section
                      key={`${sentence.original}-${index}`}
                      className="grid gap-5 px-6 py-6 sm:px-8 md:grid-cols-2"
                    >
                      <div>
                        <p className="text-xs font-medium text-[#718084]">
                          原文
                        </p>
                        <p className="mt-2 font-serif text-lg leading-9 text-[#253638]">
                          {sentence.original}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs font-medium text-[#718084]">
                          释读
                        </p>
                        <p className="mt-2 text-sm leading-7 text-[#405659]">
                          {sentence.modern}
                        </p>
                        {sentence.keywords.length > 0 && (
                          <dl className="mt-4 space-y-2 border-t border-dashed border-[#d7dfde] pt-3">
                            {sentence.keywords.map((keyword) => (
                              <div
                                key={keyword.term}
                                className="grid grid-cols-[4.5rem_1fr] gap-2 text-xs leading-5"
                              >
                                <dt className="font-serif font-semibold text-[#28656c]">
                                  {keyword.term}
                                </dt>
                                <dd className="text-[#647578]">
                                  {keyword.meaning}
                                </dd>
                              </div>
                            ))}
                          </dl>
                        )}
                        {sentence.uncertain_terms.length > 0 && (
                          <p className="mt-3 text-xs text-amber-800">
                            待考：{sentence.uncertain_terms.join("、")}
                          </p>
                        )}
                      </div>
                    </section>
                  ))}
                </div>

                <footer className="bg-[#f1f5f4] px-6 py-4 text-xs leading-5 text-[#68787b] sm:px-8">
                  {label.gloss.notes.map((note) => (
                    <p key={note}>· {note}</p>
                  ))}
                </footer>
              </article>
            ) : (
              <div className="grid min-h-[34rem] place-items-center border border-dashed border-[#cbd7d7] bg-white/60 px-6 text-center">
                <div className="max-w-sm">
                  <BookMarked className="mx-auto size-9 text-[#679198]" />
                  <h2 className="mt-4 text-base font-medium">
                    生成后在这里查看博物馆式展签
                  </h2>
                  <p className="mt-2 text-sm leading-6 text-[#738286]">
                    原文不会被覆盖，释读、词语解释、出处和待考信息会并列呈现。
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
