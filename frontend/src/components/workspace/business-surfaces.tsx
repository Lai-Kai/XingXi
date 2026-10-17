"use client";

import type { ComponentProps } from "react";

import { DialogContent } from "@/components/ui/dialog";
import { SheetContent } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

// Keep Radix's focus trap, Escape handling and trigger focus restoration.
// Callers continue to provide DialogTitle / SheetTitle and descriptions.
export function BusinessDialogContent({
  className,
  ...props
}: ComponentProps<typeof DialogContent>) {
  return (
    <DialogContent
      {...props}
      className={cn(
        "bg-card text-card-foreground shadow-heritage-overlay max-h-[90dvh] overflow-y-auto rounded-xl duration-[var(--duration-panel)] sm:max-w-[40rem]",
        className,
      )}
    />
  );
}

export function BusinessSheetContent({
  className,
  side = "right",
  ...props
}: ComponentProps<typeof SheetContent>) {
  return (
    <SheetContent
      {...props}
      side={side}
      className={cn(
        "bg-card text-card-foreground shadow-heritage-overlay overflow-y-auto data-[state=closed]:duration-[var(--duration-panel)] data-[state=open]:duration-[var(--duration-panel)]",
        (side === "right" || side === "left") && "w-full sm:max-w-[30rem]",
        (side === "top" || side === "bottom") && "max-h-[90dvh]",
        className,
      )}
    />
  );
}

export function BusinessTable({
  caption,
  className,
  children,
  ...props
}: ComponentProps<"table"> & { caption: string }) {
  return (
    <div
      role="region"
      aria-label={caption}
      tabIndex={0}
      className="bg-card text-card-foreground focus-visible:outline-ring overflow-auto rounded-lg border focus-visible:outline-2 focus-visible:outline-offset-2"
    >
      <table
        {...props}
        className={cn("xingxi-table w-full text-sm", className)}
      >
        <caption className="sr-only">{caption}</caption>
        {children}
      </table>
    </div>
  );
}
