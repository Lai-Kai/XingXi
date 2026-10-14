"use client";

import {
  Check,
  CheckCircle2,
  CircleDashed,
  Clock3,
  Copy,
  LoaderCircle,
  TriangleAlert,
  XCircle,
} from "lucide-react";
import { useState } from "react";

import { evaluationLabel } from "@/core/operations/evaluations";
import { cn } from "@/lib/utils";

export const evaluationButton =
  "inline-flex min-h-9 items-center justify-center gap-2 rounded-lg border border-[#cbd8da] bg-white px-3 py-2 text-sm transition-colors hover:bg-[#eef5f5] focus-visible:outline-2 focus-visible:outline-[#276f79] disabled:cursor-not-allowed disabled:opacity-50";

export function EvaluationBadge({
  value,
}: {
  value: string | null | undefined;
}) {
  const Icon =
    value === "passed"
      ? CheckCircle2
      : value === "failed" || value === "error"
        ? XCircle
        : value === "needs_review"
          ? TriangleAlert
          : value === "running"
            ? LoaderCircle
            : value === "queued"
              ? Clock3
              : CircleDashed;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium whitespace-nowrap",
        value === "passed"
          ? "border-emerald-200 bg-emerald-50 text-emerald-800"
          : value === "failed" || value === "error"
            ? "border-rose-200 bg-rose-50 text-rose-800"
            : value === "needs_review"
              ? "border-amber-200 bg-amber-50 text-amber-800"
              : value === "running"
                ? "border-cyan-200 bg-cyan-50 text-cyan-800"
                : "border-slate-200 bg-slate-50 text-slate-600",
      )}
    >
      <Icon
        className={cn("size-3.5", value === "running" && "animate-spin")}
        aria-hidden="true"
      />
      {evaluationLabel(value)}
    </span>
  );
}

export function EvaluationJson({
  label,
  value,
}: {
  label: string;
  value: unknown;
}) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "error">(
    "idle",
  );
  const json = JSON.stringify(value, null, 2) ?? "null";
  const tokens = json.split(
    /("(?:\\.|[^"\\])*"\s*:|"(?:\\.|[^"\\])*"|\b(?:true|false|null)\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g,
  );
  return (
    <details
      className="overflow-hidden rounded-lg border border-slate-700 bg-slate-950"
      open
    >
      <summary className="cursor-pointer bg-slate-900 px-3 py-2 text-xs font-medium text-slate-300">
        {label}
      </summary>
      <div className="flex justify-end px-3 pt-2">
        <button
          type="button"
          className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-white"
          aria-label={`复制${label}`}
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(json);
              setCopyState("copied");
            } catch {
              setCopyState("error");
            }
          }}
        >
          {copyState === "copied" ? (
            <Check className="size-3" />
          ) : (
            <Copy className="size-3" />
          )}
          {copyState === "copied" ? "已复制" : "复制"}
        </button>
      </div>
      {copyState === "error" && (
        <p role="alert" className="px-3 text-xs text-amber-300">
          复制失败，请手动选择代码。
        </p>
      )}
      <pre className="max-h-72 overflow-auto p-3 text-xs leading-6 text-slate-200">
        <code>
          {tokens.map((token, index) => (
            <span
              key={index}
              className={
                token.startsWith('"')
                  ? token.trimEnd().endsWith(":")
                    ? "text-sky-300"
                    : "text-emerald-300"
                  : /^(true|false|null|-?\d)/.test(token)
                    ? "text-amber-300"
                    : undefined
              }
            >
              {token}
            </span>
          ))}
        </code>
      </pre>
    </details>
  );
}
