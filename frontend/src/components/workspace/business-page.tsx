import {
  AlertCircle,
  Archive,
  CheckCircle2,
  CircleDashed,
  Clock3,
  FlaskConical,
  Info,
  RotateCcw,
  TriangleAlert,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";

import { SidebarTrigger } from "@/components/ui/sidebar";
import {
  getBusinessStatusPresentation,
  type BusinessStatus,
  type BusinessStatusTone,
} from "@/core/presentation/business-status";
import { cn } from "@/lib/utils";

const toneClasses: Record<BusinessStatusTone, string> = {
  neutral: "border-border bg-muted/60 text-muted-foreground",
  info: "border-border bg-accent text-primary",
  success: "border-[#b9d9ca] bg-[#e7f3ec] text-[#276947]",
  warning: "border-[#e4cf9d] bg-[#fbf4df] text-[#825f17]",
  danger: "border-[#e3bdbd] bg-[#f9eaea] text-[#934747]",
};

const toneIcons: Record<BusinessStatusTone, LucideIcon> = {
  neutral: CircleDashed,
  info: Info,
  success: CheckCircle2,
  warning: TriangleAlert,
  danger: XCircle,
};

const statusIcons: Partial<Record<BusinessStatus, LucideIcon>> = {
  pending: Clock3,
  running: RotateCcw,
  awaiting_review: Clock3,
  completed: CheckCircle2,
  reviewed: CheckCircle2,
  archived: Archive,
  demo: FlaskConical,
};

export function BusinessStatusBadge({
  status,
  className,
}: {
  status: BusinessStatus;
  className?: string;
}) {
  const presentation = getBusinessStatusPresentation(status);
  const Icon = statusIcons[status] ?? toneIcons[presentation.tone];

  return (
    <span
      className={cn(
        "inline-flex h-6 w-fit shrink-0 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium whitespace-nowrap",
        toneClasses[presentation.tone],
        className,
      )}
      role="status"
    >
      <Icon
        className={cn("size-3.5", status === "running" && "animate-spin")}
        aria-hidden="true"
      />
      {presentation.label}
    </span>
  );
}

export function BusinessMobileHeader({ title }: { title: string }) {
  return (
    <div className="border-border bg-muted/95 sticky top-0 z-20 flex h-12 items-center border-b px-4 backdrop-blur md:hidden">
      <SidebarTrigger />
      <span className="ml-2 truncate text-sm font-medium">{title}</span>
    </div>
  );
}

export function BusinessPageHeader({
  title,
  description,
  icon: Icon,
  actions,
}: {
  title: string;
  description: string;
  icon: LucideIcon;
  actions?: ReactNode;
}) {
  return (
    <header className="border-border flex flex-col gap-5 border-b pb-6 lg:flex-row lg:items-end lg:justify-between">
      <div className="flex min-w-0 items-center gap-3">
        <span className="border-primary/10 bg-accent text-primary flex size-11 shrink-0 items-center justify-center rounded-xl border">
          <Icon className="size-5" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold">{title}</h1>
          <p className="text-muted-foreground mt-1 text-sm leading-5">
            {description}
          </p>
        </div>
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

export function BusinessLoadingState({
  label = "正在加载…",
  className,
}: {
  label?: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex min-h-80 flex-col justify-center gap-4 px-5 py-10",
        className,
      )}
      aria-busy="true"
      aria-label={label}
    >
      <div className="text-muted-foreground flex items-center gap-2 text-sm">
        <RotateCcw className="size-4 animate-spin" aria-hidden="true" />
        <span>{label}</span>
      </div>
      <div className="space-y-3" aria-hidden="true">
        {["88%", "72%", "81%"].map((width) => (
          <div
            key={width}
            className="border-border bg-muted/60 h-12 animate-pulse rounded-md border"
            style={{ width }}
          />
        ))}
      </div>
    </div>
  );
}

export function BusinessErrorState({
  title = "暂时无法加载",
  description,
  onRetry,
  className,
}: {
  title?: string;
  description: string;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex min-h-80 flex-col items-center justify-center px-5 py-10 text-center",
        className,
      )}
      role="alert"
    >
      <span className="flex size-12 items-center justify-center rounded-full bg-[#f9eaea] text-[#934747]">
        <AlertCircle className="size-5" aria-hidden="true" />
      </span>
      <h2 className="mt-4 text-base font-medium">{title}</h2>
      <p className="text-muted-foreground mt-2 max-w-md text-sm leading-6">
        {description}
      </p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="border-border bg-card text-primary hover:bg-muted/60 mt-5 inline-flex h-9 items-center gap-2 rounded-md border px-4 text-sm"
        >
          <RotateCcw className="size-4" aria-hidden="true" />
          重新加载
        </button>
      )}
    </div>
  );
}

export function BusinessEmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex min-h-80 flex-col items-center justify-center px-5 py-10 text-center",
        className,
      )}
    >
      <span className="bg-accent text-muted-foreground flex size-14 items-center justify-center rounded-full">
        <Icon className="size-6" aria-hidden="true" />
      </span>
      <h2 className="mt-4 text-base font-medium">{title}</h2>
      <p className="text-muted-foreground mt-2 max-w-md text-sm leading-6">
        {description}
      </p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function BusinessInlineError({
  message,
  onDismiss,
}: {
  message: string;
  onDismiss?: () => void;
}) {
  return (
    <div
      className="flex items-start justify-between gap-3 rounded-md border border-[#e3bdbd] bg-[#f9eaea] px-3 py-2.5 text-sm text-[#843f3f]"
      role="alert"
    >
      <span className="flex min-w-0 items-start gap-2">
        <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>{message}</span>
      </span>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="shrink-0 font-medium hover:underline"
        >
          关闭
        </button>
      )}
    </div>
  );
}
