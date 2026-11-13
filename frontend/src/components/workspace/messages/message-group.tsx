import type { Message } from "@langchain/langgraph-sdk";
import { Loader2Icon } from "lucide-react";

import { useI18n } from "@/core/i18n/hooks";
import type { TokenDebugStep } from "@/core/messages/usage-model";
import { cn } from "@/lib/utils";

export function MessageGroup({
  className,
  isLoading = false,
}: {
  className?: string;
  messages: Message[];
  isLoading?: boolean;
  tokenDebugSteps?: TokenDebugStep[];
  showTokenDebugSummaries?: boolean;
}) {
  const { t } = useI18n();
  if (!isLoading) return null;

  return (
    <div
      className={cn(
        "text-muted-foreground flex items-center gap-2 text-sm",
        className,
      )}
      role="status"
    >
      <Loader2Icon className="size-4 animate-spin" aria-hidden="true" />
      <span>{t.researchTrace.running}</span>
    </div>
  );
}
