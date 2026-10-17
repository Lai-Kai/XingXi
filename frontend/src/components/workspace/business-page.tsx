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

import {
  BusinessButton,
  BusinessSkeleton,
  businessToneClasses,
} from "@/components/workspace/business-controls";
import { WorkspaceMobileHeader } from "@/components/workspace/workspace-mobile-header";
import {
  getBusinessStatusPresentation,
  type BusinessStatus,
  type BusinessStatusTone,
} from "@/core/presentation/business-status";
import { cn } from "@/lib/utils";

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
        "inline-flex min-h-[22px] w-fit shrink-0 items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        businessToneClasses[presentation.tone],
        className,
      )}
      role="status"
      aria-label={presentation.label}
    >
      <Icon
        className={cn("size-3", status === "running" && "animate-spin")}
        aria-hidden="true"
      />
      {presentation.label}
    </span>
  );
}

export function BusinessMobileHeader({ title }: { title: string }) {
  return <WorkspaceMobileHeader title={title} />;
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
    <header className="flex flex-col gap-5 border-b pb-6 lg:flex-row lg:items-end lg:justify-between">
      <div className="flex min-w-0 items-center gap-3">
        <span className="bg-secondary text-secondary-foreground flex size-10 shrink-0 items-center justify-center rounded-md">
          <Icon className="size-5" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h1 className="font-serif text-2xl font-semibold">{title}</h1>
          <p className="mt-1 text-sm leading-5 opacity-75">{description}</p>
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
        "bg-card text-card-foreground flex min-h-80 flex-col justify-center gap-4 rounded-lg px-5 py-10",
        className,
      )}
      aria-busy="true"
      aria-label={label}
      role="status"
    >
      <div className="text-muted-foreground flex items-center gap-2 text-sm">
        <RotateCcw className="size-4 animate-spin" aria-hidden="true" />
        <span>{label}</span>
      </div>
      <div className="space-y-3" aria-hidden="true">
        {["88%", "72%", "81%"].map((width) => (
          <BusinessSkeleton
            key={width}
            className="h-12 border"
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
        "bg-card text-card-foreground flex min-h-80 flex-col items-center justify-center rounded-lg px-5 py-10 text-center",
        className,
      )}
      role="alert"
    >
      <span className="bg-heritage-rejected-surface text-heritage-rejected-foreground flex size-12 items-center justify-center rounded-full">
        <AlertCircle className="size-5" aria-hidden="true" />
      </span>
      <h2 className="mt-4 text-base font-medium">{title}</h2>
      <p className="text-muted-foreground mt-2 max-w-md text-sm leading-6">
        {description}
      </p>
      {onRetry && (
        <BusinessButton variant="outline" onClick={onRetry} className="mt-5">
          <RotateCcw className="size-4" aria-hidden="true" />
          重新加载
        </BusinessButton>
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
        "bg-card text-card-foreground flex min-h-80 flex-col items-center justify-center rounded-lg px-5 py-10 text-center",
        className,
      )}
    >
      <span className="bg-secondary text-secondary-foreground flex size-14 items-center justify-center rounded-full">
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
      className={cn(
        "flex items-start justify-between gap-3 rounded-md border px-3 py-2.5 text-sm",
        businessToneClasses.danger,
      )}
      role="alert"
    >
      <span className="flex min-w-0 items-start gap-2">
        <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>{message}</span>
      </span>
      {onDismiss && (
        <BusinessButton
          variant="ghost"
          onClick={onDismiss}
          className="h-auto shrink-0 px-2 py-0.5 text-current hover:underline"
        >
          关闭
        </BusinessButton>
      )}
    </div>
  );
}
