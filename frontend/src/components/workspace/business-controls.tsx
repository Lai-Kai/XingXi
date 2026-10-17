"use client";

import {
  BookOpenText,
  CheckCircle2,
  Clock3,
  RotateCcw,
  TriangleAlert,
  XCircle,
} from "lucide-react";
import type { ComponentProps } from "react";

import { Button } from "@/components/ui/button";
import { evidenceDetailPath } from "@/core/citations/sources";
import { reviewLabels } from "@/core/knowledge-graph/review";
import type { ReviewStatus } from "@/core/knowledge-graph/types";
import type { BusinessStatusTone } from "@/core/presentation/business-status";
import { cn } from "@/lib/utils";

export const businessToneClasses: Record<BusinessStatusTone, string> = {
  neutral:
    "border-heritage-pending-border bg-heritage-pending-surface text-heritage-pending-foreground",
  info: "border-heritage-citation-border bg-heritage-citation-surface text-heritage-citation-foreground",
  success:
    "border-heritage-approved-border bg-heritage-approved-surface text-heritage-approved-foreground",
  warning:
    "border-heritage-disputed-border bg-heritage-disputed-surface text-heritage-disputed-foreground",
  danger:
    "border-heritage-rejected-border bg-heritage-rejected-surface text-heritage-rejected-foreground",
};

export function BusinessButton({
  busy = false,
  disabled = false,
  type = "button",
  className,
  children,
  variant = "default",
  ...props
}: Omit<ComponentProps<typeof Button>, "asChild"> & { busy?: boolean }) {
  return (
    <Button
      {...props}
      type={type}
      variant={variant}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={cn(
        "xingxi-button focus-visible:outline-ring focus-visible:ring-0 focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-40",
        variant === "default" && "hover:bg-primary-hover",
        className,
      )}
    >
      {busy && <RotateCcw className="size-4 animate-spin" aria-hidden="true" />}
      {children}
    </Button>
  );
}

// Native handlers, names, validation, refs and IME behavior belong to the caller.
export function BusinessInput({
  className,
  ...props
}: ComponentProps<"input">) {
  return <input {...props} className={cn("field min-w-0", className)} />;
}

export function BusinessTextarea({
  className,
  ...props
}: ComponentProps<"textarea">) {
  return (
    <textarea
      {...props}
      className={cn(
        "field h-auto min-h-[110px] min-w-0 resize-y py-3 leading-7",
        className,
      )}
    />
  );
}

export function EvidenceCapsule({
  evidenceId,
  title,
  locator,
  className,
  ...props
}: Omit<ComponentProps<"a">, "href" | "children" | "title"> & {
  evidenceId: string;
  title: string;
  locator?: string;
}) {
  const label = [title, locator].filter(Boolean).join(" · ");
  return (
    <a
      aria-label={label}
      {...props}
      href={evidenceDetailPath(evidenceId)}
      title={label}
      className={cn(
        "xingxi-evidence border-heritage-citation-border bg-heritage-citation-surface text-heritage-citation-foreground focus-visible:outline-ring inline-flex min-h-6 max-w-full items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs transition-colors hover:underline focus-visible:outline-2 focus-visible:outline-offset-2",
        className,
      )}
    >
      <BookOpenText className="size-3 shrink-0" aria-hidden="true" />
      <span className="min-w-0 truncate">{label}</span>
    </a>
  );
}

const reviewTones: Record<ReviewStatus, BusinessStatusTone> = {
  pending: "neutral",
  reviewed: "success",
  disputed: "warning",
  rejected: "danger",
};
const reviewIcons = {
  pending: Clock3,
  reviewed: CheckCircle2,
  disputed: TriangleAlert,
  rejected: XCircle,
};

export function BusinessReviewBadge({
  status,
  className,
}: {
  status: ReviewStatus;
  className?: string;
}) {
  const Icon = reviewIcons[status];
  return (
    <span
      role="status"
      aria-label={reviewLabels[status]}
      className={cn(
        "inline-flex min-h-[22px] w-fit shrink-0 items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        businessToneClasses[reviewTones[status]],
        className,
      )}
    >
      <Icon className="size-3" aria-hidden="true" />
      {reviewLabels[status]}
    </span>
  );
}

export function BusinessPanel({
  className,
  ...props
}: ComponentProps<"section">) {
  return (
    <section
      {...props}
      className={cn(
        "bg-card text-card-foreground shadow-heritage-card rounded-lg border p-4 sm:p-6",
        className,
      )}
    />
  );
}

export function BusinessSkeleton({
  className,
  ...props
}: ComponentProps<"div">) {
  return (
    <div
      {...props}
      aria-hidden="true"
      className={cn("xingxi-skeleton rounded-md", className)}
    />
  );
}
