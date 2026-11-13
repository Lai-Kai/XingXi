"use client";

import {
  CheckCircle2,
  CircleDashed,
  Clock3,
  LoaderCircle,
  TriangleAlert,
  XCircle,
} from "lucide-react";

import { evaluationLabel } from "@/core/operations/evaluations";
import { cn } from "@/lib/utils";

export const evaluationButton =
  "inline-flex min-h-9 items-center justify-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-sm transition-colors hover:bg-muted/60 focus-visible:outline-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-50";

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
