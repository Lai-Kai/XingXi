"use client";

import {
  ArrowRight,
  BookOpenCheck,
  FileSearch,
  Lightbulb,
  Map,
  Play,
  RotateCcw,
  Sparkles,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import {
  BusinessMobileHeader,
  BusinessStatusBadge,
} from "@/components/workspace/business-page";
import {
  xingxiChatHref,
  xingxiWorkspaceHref,
} from "@/core/threads/xingxi-entry";
import { cn } from "@/lib/utils";

type CaseTab = "featured" | "inspiration" | "verification" | "review";

const tabs = [
  { id: "featured" as const, label: "精选", icon: BookOpenCheck },
  { id: "inspiration" as const, label: "灵感发现", icon: Lightbulb },
  { id: "verification" as const, label: "史料复核", icon: RotateCcw },
  { id: "review" as const, label: "专题综述", icon: FileSearch },
];

const cases = [
  {
    tab: "featured" as const,
    title: "木渎古镇水系与街巷格局演变",
    category: "空间考证",
    summary:
      "综合地方志、历史舆图与现状地名，建立香溪、胥江及镇区河道的时序关系。",
    runs: "1.8K",
    icon: Map,
  },
  {
    tab: "featured" as const,
    title: "范仲淹与木渎关联史料复核",
    category: "人物研究",
    summary: "区分地方传说与可核验记载，梳理人物、地点、事件及材料成书年代。",
    runs: "1.2K",
    icon: Users,
  },
  {
    tab: "featured" as const,
    title: "严家花园营建沿革证据链",
    category: "园林史",
    summary: "对读方志、园林档案和近现代调查材料，拆分始建、扩建与修缮阶段。",
    runs: "986",
    icon: BookOpenCheck,
  },
  {
    tab: "inspiration" as const,
    title: "从桥名异称发现木渎地方记忆线索",
    category: "研究选题",
    summary: "从同桥异名、旧名复用与民间称谓中生成可继续检索的研究问题。",
    runs: "734",
    icon: Lightbulb,
  },
  {
    tab: "verification" as const,
    title: "灵岩山馆娃宫相关记载可信度核查",
    category: "传说辨析",
    summary: "按材料年代和来源层级比较不同说法，明确事实、推定与后世附会。",
    runs: "815",
    icon: RotateCcw,
  },
  {
    tab: "review" as const,
    title: "木渎近代商业与市镇变迁研究综述",
    category: "专题综述",
    summary:
      "汇集商会名录、地方档案和既有研究，输出带出处的主题脉络与研究空白。",
    runs: "642",
    icon: FileSearch,
  },
];

export default function XingxiAgentPage() {
  const router = useRouter();
  const [tab, setTab] = useState<CaseTab>("featured");
  const visibleCases = useMemo(() => {
    if (tab === "featured") return cases.filter((item) => item.tab === tab);
    return cases.filter((item) => item.tab === tab);
  }, [tab]);

  return (
    <main className="size-full overflow-y-auto bg-[#edf4f5] text-[#202b2e]">
      <BusinessMobileHeader title="星羲智能体" />

      <section className="px-4 pt-12 pb-8 sm:px-8 lg:pt-16">
        <div className="mx-auto max-w-6xl text-center">
          <div className="mx-auto flex size-11 items-center justify-center rounded-md bg-[#202b2e] text-white">
            <Sparkles className="size-5" />
          </div>
          <h1 className="mt-4 text-3xl font-semibold sm:text-4xl">
            星羲智能体
          </h1>
          <BusinessStatusBadge status="demo" className="mt-3" />
          <p className="mt-3 text-base text-[#247f8c] sm:text-xl">
            面向吴文化与木渎地域文史的可信研究助手
          </p>

          <div className="mx-auto mt-8 grid max-w-2xl gap-3 sm:grid-cols-2">
            <button
              type="button"
              onClick={() => router.push(xingxiWorkspaceHref("pro"))}
              className="flex h-14 items-center justify-center gap-2 rounded-md bg-[#202b2e] px-5 text-sm font-medium text-white transition hover:bg-[#344145] sm:text-base"
            >
              <Sparkles className="size-4" />
              启动专业研究
            </button>
            <button
              type="button"
              onClick={() => router.push(xingxiWorkspaceHref("flash"))}
              className="flex h-14 items-center justify-center gap-2 rounded-md bg-[#247f8c] px-5 text-sm font-medium text-white transition hover:bg-[#1d6d78] sm:text-base"
            >
              <Sparkles className="size-4" />
              启动轻量问答
            </button>
          </div>
          <p className="mt-4 text-xs text-[#6a7b80] sm:text-sm">
            专业模式会持续检索、交叉核验并整理出处，直至形成可追溯结论
          </p>
        </div>
      </section>

      <section className="px-4 pb-12 sm:px-8">
        <div className="mx-auto max-w-6xl">
          <h2 className="text-center text-xl font-medium">研究场景</h2>
          <div
            className="mt-6 flex flex-wrap justify-center gap-2 sm:gap-4"
            role="tablist"
            aria-label="研究场景"
          >
            {tabs.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  type="button"
                  role="tab"
                  aria-selected={tab === item.id}
                  onClick={() => setTab(item.id)}
                  className={cn(
                    "flex h-10 items-center gap-2 rounded-full px-4 text-sm transition",
                    tab === item.id
                      ? "bg-[#dce8ea] font-medium text-[#234f57]"
                      : "text-[#66777c] hover:bg-white/70 hover:text-[#263438]",
                  )}
                >
                  <Icon className="size-4" />
                  {item.label}
                </button>
              );
            })}
          </div>

          <div className="mt-7 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {visibleCases.map((item) => {
              const Icon = item.icon;
              return (
                <article
                  key={item.title}
                  className="flex min-h-64 flex-col rounded-md border border-[#d3dfe1] bg-white p-5 shadow-[0_12px_30px_rgba(44,76,82,0.06)]"
                >
                  <div className="flex items-start justify-between gap-3">
                    <span className="flex size-10 items-center justify-center rounded-full bg-[#202b2e] text-white">
                      <Icon className="size-4" />
                    </span>
                    <span className="text-xs text-[#6d7c81]">研究示例</span>
                  </div>
                  <h3 className="mt-5 text-base leading-6 font-medium">
                    {item.title}
                  </h3>
                  <span className="mt-3 w-fit rounded-full bg-[#e2f0f1] px-2.5 py-1 text-xs text-[#24717b]">
                    {item.category}
                  </span>
                  <p className="mt-3 flex-1 text-sm leading-6 text-[#5b6d72]">
                    {item.summary}
                  </p>
                  <Link
                    href={xingxiChatHref(
                      `请围绕“${item.title}”开展研究，并提供可核验的史料出处。`,
                      "pro",
                    )}
                    className="mt-5 flex items-center justify-between border-t border-[#e1e8e9] pt-4 text-sm font-medium text-[#276f79] hover:text-[#174f57]"
                  >
                    <span className="flex items-center gap-2">
                      <Play className="size-4" />
                      开始研究
                    </span>
                    <ArrowRight className="size-4" />
                  </Link>
                </article>
              );
            })}
          </div>
        </div>
      </section>
    </main>
  );
}
