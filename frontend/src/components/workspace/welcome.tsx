"use client";

import { BookOpenText } from "lucide-react";

import { useI18n } from "@/core/i18n/hooks";
import { cn } from "@/lib/utils";

export function Welcome({
  className,
}: {
  className?: string;
  mode?: "ultra" | "pro" | "thinking" | "flash";
}) {
  const { t } = useI18n();

  return (
    <div
      className={cn(
        "mx-auto flex w-full max-w-full flex-col items-center justify-center gap-3 px-4 py-5 text-center sm:px-8",
        className,
      )}
    >
      <BookOpenText className="text-primary size-6" aria-hidden="true" />
      <div className="text-2xl font-semibold">{t.welcome.greeting}</div>
      <p className="text-muted-foreground max-w-md text-sm leading-6 text-wrap">
        {t.welcome.description}
      </p>
    </div>
  );
}
