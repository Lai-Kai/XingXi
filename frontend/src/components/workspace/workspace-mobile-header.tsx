"use client";

import { Menu, PanelLeftClose, PanelLeftOpen, Search, X } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { useSidebar } from "@/components/ui/sidebar";
import { cn } from "@/lib/utils";

export function WorkspaceSidebarToggle({ className }: { className?: string }) {
  const { isMobile, open, openMobile, toggleSidebar } = useSidebar();
  const expanded = isMobile ? openMobile : open;
  const Icon = isMobile
    ? expanded
      ? X
      : Menu
    : expanded
      ? PanelLeftClose
      : PanelLeftOpen;
  const label = expanded ? "收起侧栏" : "展开侧栏";

  return (
    <Button
      variant="ghost"
      size="icon"
      className={cn("size-11 shrink-0 text-inherit", className)}
      data-sidebar="trigger"
      data-slot="sidebar-trigger"
      aria-label={label}
      aria-expanded={expanded}
      title={label}
      onClick={(event) => {
        event.currentTarget.focus();
        toggleSidebar();
      }}
    >
      <Icon className="size-5" aria-hidden="true" />
    </Button>
  );
}

export function WorkspaceSearchLink({ className }: { className?: string }) {
  return (
    <Link
      href="/workspace"
      aria-label="文史检索"
      title="文史检索"
      className={cn(
        "hover:bg-accent focus-visible:ring-ring ml-auto flex size-11 shrink-0 items-center justify-center rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-offset-2",
        className,
      )}
    >
      <Search className="size-4" aria-hidden="true" />
    </Link>
  );
}
