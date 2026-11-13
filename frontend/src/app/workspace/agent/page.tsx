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
import { useMemo, useState } from "react";

import {
  BusinessMobileHeader,
  BusinessStatusBadge,
} from "@/components/workspace/business-page";
import { xingxiChatHref } from "@/core/threads/xingxi-entry";
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
    icon: Map,
    tone: "border-sky-100 bg-sky-50 text-sky-600",
  },
  {
    tab: "featured" as const,
    title: "范仲淹与木渎关联史料复核",
    category: "人物研究",
    summary: "区分地方传说与可核验记载，梳理人物、地点、事件及材料成书年代。",
    icon: Users,
    tone: "border-rose-100 bg-rose-50 text-rose-600",
  },
  {
    tab: "featured" as const,
    title: "严家花园营建沿革证据链",
    category: "园林史",
    summary: "对读方志、园林档案和近现代调查材料，拆分始建、扩建与修缮阶段。",
    icon: BookOpenCheck,
    tone: "border-violet-100 bg-violet-50 text-violet-600",
  },
  {
    tab: "inspiration" as const,
    title: "从桥名异称发现木渎地方记忆线索",
    category: "研究选题",
    summary: "从同桥异名、旧名复用与民间称谓中生成可继续检索的研究问题。",
    icon: Lightbulb,
    tone: "border-amber-100 bg-amber-50 text-amber-700",
  },
  {
    tab: "verification" as const,
    title: "灵岩山馆娃宫相关记载可信度核查",
    category: "传说辨析",
    summary: "按材料年代和来源层级比较不同说法，明确事实、推定与后世附会。",
    icon: RotateCcw,
    tone: "border-sky-100 bg-sky-50 text-sky-600",
  },
  {
    tab: "review" as const,
    title: "木渎近代商业与市镇变迁研究综述",
    category: "专题综述",
    summary:
      "汇集商会名录、地方档案和既有研究，输出带出处的主题脉络与研究空白。",
    icon: FileSearch,
    tone: "border-violet-100 bg-violet-50 text-violet-600",
  },
];

export default function XingxiAgentPage() {
  const [tab, setTab] = useState<CaseTab>("featured");
  const visibleCases = useMemo(() => {
    if (tab === "featured") return cases.filter((item) => item.tab === tab);
    return cases.filter((item) => item.tab === tab);
  }, [tab]);

  return (
    <main className="xingxi-module bg-muted/60 text-foreground size-full overflow-y-auto">
      <BusinessMobileHeader title="星羲智能体" />

      <section className="px-4 pt-12 pb-8 sm:px-8 lg:pt-16">
        <div className="mx-auto max-w-6xl text-center">
          <div className="bg-primary text-primary-foreground mx-auto flex size-11 items-center justify-center rounded-2xl">
            <Sparkles className="size-5" />
          </div>
          <h1 className="mt-4 text-3xl font-semibold sm:text-4xl">
            星羲智能体
          </h1>
          <BusinessStatusBadge status="demo" className="mt-3" />
          <p className="text-primary mt-3 text-base sm:text-xl">
            面向吴文化与木渎地域文史的可信研究助手
          </p>

          <div className="mx-auto mt-8 max-w-sm">
            <Link
              href={xingxiChatHref("")}
              className="home-primary bg-primary text-primary-foreground hover:bg-primary/90 flex h-14 w-full items-center justify-center gap-2 rounded-xl px-5 text-sm font-medium transition sm:text-base"
            >
              <Sparkles className="size-4" />
              开始对话
            </Link>
          </div>
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
                      ? "bg-accent text-primary font-medium"
                      : "text-muted-foreground hover:bg-card/70 hover:text-foreground",
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
                  className="xingxi-panel border-border bg-card flex min-h-64 flex-col rounded-2xl border p-5 shadow-sm transition-all duration-200 hover:-translate-y-1 hover:shadow-md"
                >
                  <div className="flex items-start justify-between gap-3">
                    <span
                      className={cn(
                        "flex size-11 items-center justify-center rounded-xl border",
                        item.tone,
                      )}
                    >
                      <Icon className="size-4" />
                    </span>
                    <span className="text-muted-foreground text-xs">
                      研究示例
                    </span>
                  </div>
                  <h3 className="mt-5 text-base leading-6 font-medium">
                    {item.title}
                  </h3>
                  <span className="bg-accent text-primary mt-3 w-fit rounded-full px-2.5 py-1 text-xs">
                    {item.category}
                  </span>
                  <p className="text-muted-foreground mt-3 flex-1 text-sm leading-6">
                    {item.summary}
                  </p>
                  <Link
                    href={xingxiChatHref(
                      `请围绕“${item.title}”开展研究，并提供可核验的史料出处。`,
                    )}
                    className="border-border text-primary hover:text-primary mt-5 flex items-center justify-between border-t pt-4 text-sm font-medium"
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
