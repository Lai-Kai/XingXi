"use client";

import { BookOpenText, Layers3, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import {
  getKnowledgeReleaseState,
  listKnowledgeReleases,
  type KnowledgeRelease,
} from "@/core/source-files/api";

export function WorkbenchMetrics({
  items,
}: {
  items: { label: string; value: string | number | null; hint: string }[];
}) {
  return (
    <dl className="workbench-metrics grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {items.map((item, index) => (
        <div
          key={item.label}
          className="bg-card shadow-heritage-card min-w-0 rounded-xl border p-4 sm:p-5"
        >
          <dt className="text-muted-foreground flex items-center justify-between gap-2 text-xs">
            {item.label}
            <span className="text-primary/40 font-serif">0{index + 1}</span>
          </dt>
          <dd className="mt-3 font-serif text-3xl font-semibold tabular-nums">
            {item.value ?? "—"}
          </dd>
          <dd className="text-muted-foreground mt-2 text-xs leading-5">
            {item.hint}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function WorkbenchGuide({
  title,
  steps,
}: {
  title: string;
  steps: string[];
}) {
  return (
    <div
      className="bg-secondary/50 mb-6 flex flex-wrap items-center gap-x-5 gap-y-2 rounded-xl border px-4 py-3 text-xs"
      aria-label={title}
    >
      <span className="text-primary flex items-center gap-2 font-medium">
        <BookOpenText className="size-4" />
        {title}
      </span>
      <ol className="text-muted-foreground flex flex-wrap gap-x-5 gap-y-2">
        {steps.map((step, index) => (
          <li key={step}>
            <span className="text-primary mr-1.5 font-mono">{index + 1}.</span>
            {step}
          </li>
        ))}
      </ol>
    </div>
  );
}

export function LibraryReleaseSummary({ refreshKey }: { refreshKey: number }) {
  const [release, setRelease] = useState<KnowledgeRelease | null>(null);
  const [status, setStatus] = useState("正在核对当前版本…");
  useEffect(() => {
    let active = true;
    void Promise.all([getKnowledgeReleaseState(), listKnowledgeReleases()])
      .then(([state, releases]) => {
        if (!active) return;
        const current =
          releases.find(
            (item) =>
              item.id === state.active_release_id && item.status === "active",
          ) ?? null;
        setRelease(current);
        setStatus(
          current
            ? `当前生效 ${current.version}`
            : state.active_release_id
              ? "当前版本详情暂缺"
              : "尚未启用知识版本",
        );
      })
      .catch(() => {
        if (active) {
          setRelease(null);
          setStatus("当前知识版本暂不可用，请在知识版本中重试");
        }
      });
    return () => {
      active = false;
    };
  }, [refreshKey]);
  return (
    <section
      className="bg-card mb-5 flex flex-wrap items-center gap-3 rounded-xl border px-4 py-3"
      aria-label="当前知识版本"
    >
      <Layers3 className="text-primary size-5 shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="font-serif text-sm font-semibold">{status}</p>
        {release && (
          <p className="text-muted-foreground mt-1 font-mono text-[11px] break-all">
            SHA256 · {release.manifest_sha256}
          </p>
        )}
      </div>
      <span className="text-muted-foreground flex items-center gap-1.5 text-xs">
        <ShieldCheck className="size-4" />
        以服务端生效指针为准
      </span>
    </section>
  );
}
