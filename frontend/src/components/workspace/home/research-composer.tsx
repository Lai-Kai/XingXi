"use client";

import {
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Check,
  Compass,
  Search,
  ScrollText,
  Waves,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import {
  researchPrompt,
  sourcePreferences,
  type SourcePreference,
} from "@/core/home/model";
import { xingxiChatHref } from "@/core/threads/xingxi-entry";
import { isIMEComposing } from "@/lib/ime";
import { cn } from "@/lib/utils";

const starters = [
  {
    title: "方志与图册",
    description: "查卷目、比版本，循页码找到原始记载。",
    prompt: "如何利用地方志与历史舆图考察木渎镇区的变化？请列出文献与页码。",
    icon: BookOpen,
    tone: "violet",
  },
  {
    title: "人物与地方记忆",
    description: "从人物行迹与诗文，考察吴地往事。",
    prompt: "范仲淹与吴地有哪些联系？请区分文献记载与后世传说，并注明出处。",
    icon: ScrollText,
    tone: "rose",
  },
  {
    title: "河道与地名沿革",
    description: "对照香溪、胥江的记载，梳理地名变迁。",
    prompt: "地方文献如何记载木渎的香溪与胥江？请梳理名称、位置与年代依据。",
    icon: Waves,
    tone: "sky",
  },
] as const;

export function HomeResearchComposer() {
  const router = useRouter();
  const textarea = useRef<HTMLTextAreaElement>(null);
  const [query, setQuery] = useState("");
  const [preferences, setPreferences] = useState<SourcePreference[]>([]);

  function submitResearch() {
    const prompt = researchPrompt(query, preferences);
    if (prompt) router.push(xingxiChatHref(prompt));
  }

  return (
    <>
      <header className="text-center">
        <p className="inline-flex items-center gap-2 rounded-full border border-blue-100/80 bg-white/65 px-3.5 py-1.5 text-xs font-medium text-blue-700 shadow-sm">
          <span
            className="size-1.5 rounded-full bg-blue-400"
            aria-hidden="true"
          />
          吴文化 · 木渎地域文史
        </p>
        <h1
          id="home-title"
          className="mt-5 text-[26px] leading-snug font-semibold tracking-tight text-slate-900 sm:text-[32px]"
        >
          今天想查阅哪一段木渎历史？
        </h1>
        <p className="mt-3 text-sm leading-6 text-slate-500">
          你好，从地方志、人物记载与历史舆图中寻找线索。
        </p>
      </header>

      <div className="mt-8 grid grid-cols-1 gap-4 md:grid-cols-3">
        {starters.map(({ title, description, prompt, icon: Icon, tone }) => (
          <button
            key={title}
            type="button"
            onClick={() => {
              setQuery(prompt);
              textarea.current?.focus();
            }}
            className="home-quick-card group relative flex items-center gap-4 rounded-2xl border border-white/90 bg-white/75 p-4 text-left shadow-[0_6px_24px_rgb(30,64,120,0.035)] backdrop-blur-md transition-all duration-200 ease-in-out hover:-translate-y-1 hover:bg-white/95 hover:shadow-[0_10px_28px_rgb(30,64,120,0.08)] md:block md:p-5"
          >
            <span
              className={cn(
                "flex size-10 shrink-0 items-center justify-center rounded-xl border",
                tone === "violet"
                  ? "border-violet-100 bg-violet-50 text-violet-600"
                  : tone === "rose"
                    ? "border-rose-100 bg-rose-50 text-rose-600"
                    : "border-sky-100 bg-sky-50 text-sky-600",
              )}
            >
              <Icon className="size-5" aria-hidden="true" />
            </span>
            <ArrowUpRight
              className="absolute top-5 right-5 hidden size-4 text-slate-300 transition-colors group-hover:text-blue-500 md:block"
              aria-hidden="true"
            />
            <span className="min-w-0 md:mt-4 md:block">
              <span className="block text-[15px] font-semibold text-slate-800">
                {title}
              </span>
              <span className="mt-1.5 block text-xs leading-5 text-slate-500">
                {description}
              </span>
            </span>
          </button>
        ))}
      </div>

      <form
        className="home-composer mt-5 overflow-hidden rounded-2xl border border-blue-100/80 bg-white/90 shadow-[0_12px_40px_rgb(37,99,235,0.065)] transition-shadow focus-within:border-blue-300 focus-within:shadow-[0_12px_40px_rgb(37,99,235,0.10)]"
        onSubmit={(event) => {
          event.preventDefault();
          submitResearch();
        }}
      >
        <label htmlFor="home-query" className="sr-only">
          研究问题
        </label>
        <textarea
          ref={textarea}
          id="home-query"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (
              event.key === "Enter" &&
              !event.shiftKey &&
              !isIMEComposing(event)
            ) {
              event.preventDefault();
              submitResearch();
            }
          }}
          placeholder="例如：乾隆为什么多次到木渎？或输入文献段落进行考证…"
          className="min-h-32 w-full resize-y bg-transparent px-5 pt-5 pb-3 text-[15px] leading-7 text-slate-700 outline-none placeholder:text-slate-400 sm:min-h-36 sm:px-6"
        />
        <div className="flex flex-wrap items-center gap-3 border-t border-slate-100 px-4 py-3 sm:px-5">
          <fieldset className="flex min-w-0 flex-wrap items-center gap-1.5">
            <legend className="sr-only">优先查阅的资料</legend>
            <span
              className="mr-1 text-[11px] text-slate-500"
              aria-hidden="true"
            >
              优先查阅
            </span>
            {sourcePreferences.map((preference) => {
              const active = preferences.includes(preference);
              return (
                <button
                  type="button"
                  key={preference}
                  aria-pressed={active}
                  onClick={() =>
                    setPreferences((current) =>
                      current.includes(preference)
                        ? current.filter((item) => item !== preference)
                        : [...current, preference],
                    )
                  }
                  className={cn(
                    "inline-flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-xs transition-colors duration-200",
                    active
                      ? "border-blue-200 bg-blue-50 text-blue-700"
                      : "border-transparent text-slate-500 hover:border-slate-200 hover:bg-slate-50",
                  )}
                >
                  <span
                    className={cn(
                      "flex size-3.5 items-center justify-center rounded border",
                      active
                        ? "border-blue-500 bg-blue-500 text-white"
                        : "border-slate-300",
                    )}
                  >
                    {active && <Check className="size-3" aria-hidden="true" />}
                  </span>
                  {preference}
                </button>
              );
            })}
          </fieldset>
          <button
            type="submit"
            aria-label="开始研究"
            disabled={!query.trim()}
            className="home-primary ml-auto inline-flex h-10 items-center gap-2 rounded-xl px-5 text-sm font-medium text-white shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md disabled:translate-y-0 disabled:cursor-not-allowed disabled:opacity-45"
          >
            <Search className="size-4" aria-hidden="true" />
            查询
            <ArrowRight className="size-4" aria-hidden="true" />
          </button>
        </div>
      </form>
      <div className="mt-2.5 flex items-center justify-between px-1 text-[11px] text-slate-500">
        <span className="flex items-center gap-1.5">
          <span
            className="flex size-4 items-center justify-center rounded bg-emerald-100 text-emerald-700"
            aria-hidden="true"
          >
            <Compass className="size-3" />
          </span>
          星羲文史助手
        </span>
        <span className="hidden sm:inline">
          Enter 查询 · Shift + Enter 换行
        </span>
      </div>
    </>
  );
}
