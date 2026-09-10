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
  neutral: "border-[#d5dfe1] bg-[#f2f5f5] text-[#5f7075]",
  info: "border-[#b9d3d7] bg-[#e5f0f1] text-[#276b75]",
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
    <div className="sticky top-0 z-20 flex h-12 items-center border-b border-[#dce5e6] bg-[#f7fafb]/95 px-4 backdrop-blur md:hidden">
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
    <header className="flex flex-col gap-5 border-b border-[#dbe4e5] pb-6 lg:flex-row lg:items-end lg:justify-between">
      <div className="flex min-w-0 items-center gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-[#e0edef] text-[#276f79]">
          <Icon className="size-5" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold">{title}</h1>
          <p className="mt-1 text-sm leading-5 text-[#68797e]">{description}</p>
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
      <div className="flex items-center gap-2 text-sm text-[#68797e]">
        <RotateCcw className="size-4 animate-spin" aria-hidden="true" />
        <span>{label}</span>
      </div>
      <div className="space-y-3" aria-hidden="true">
        {["88%", "72%", "81%"].map((width) => (
          <div
            key={width}
            className="h-12 animate-pulse rounded-md border border-[#e1e8e9] bg-[#f0f5f5]"
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
      <p className="mt-2 max-w-md text-sm leading-6 text-[#748388]">
        {description}
      </p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-5 inline-flex h-9 items-center gap-2 rounded-md border border-[#c9d6d8] bg-white px-4 text-sm text-[#315f67] hover:bg-[#edf4f5]"
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
      <span className="flex size-14 items-center justify-center rounded-full bg-[#e8f1f2] text-[#49757c]">
        <Icon className="size-6" aria-hidden="true" />
      </span>
      <h2 className="mt-4 text-base font-medium">{title}</h2>
      <p className="mt-2 max-w-md text-sm leading-6 text-[#748388]">
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
