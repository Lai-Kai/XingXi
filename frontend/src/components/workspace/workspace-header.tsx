"use client";

import { Sparkles } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useState } from "react";

import { useSidebar } from "@/components/ui/sidebar";
import { cn } from "@/lib/utils";

import { WorkspaceSidebarToggle } from "./workspace-mobile-header";

function BrandMark() {
  const [failed, setFailed] = useState(false);
  return (
    <span className="bg-secondary text-primary flex size-9 shrink-0 items-center justify-center overflow-hidden rounded-full">
      {failed ? (
        <Sparkles className="size-5" aria-hidden="true" />
      ) : (
        <Image
          src="/brand/xingxi-celadon-emblem.jpg"
          alt=""
          width={36}
          height={36}
          className="size-9 rounded-full object-cover"
          onError={() => setFailed(true)}
        />
      )}
    </span>
  );
}

export function WorkspaceHeader({ className }: { className?: string }) {
  const { state, isMobile, setOpenMobile } = useSidebar();
  const isCollapsed = state === "collapsed" && !isMobile;

  return (
    <div
      className={cn(
        "flex shrink-0 items-center",
        isCollapsed ? "flex-col gap-1 py-3" : "h-20 justify-between gap-1 px-2",
        className,
      )}
    >
      <Link
        href="/workspace"
        aria-label="星羲弦沚首页"
        title="星羲弦沚首页"
        onClick={() => {
          if (isMobile) setOpenMobile(false);
        }}
        className="focus-visible:ring-ring flex min-h-11 min-w-11 items-center justify-center gap-2.5 rounded-lg outline-none focus-visible:ring-2"
      >
        <BrandMark />
        {!isCollapsed && (
          <span className="min-w-0">
            <span className="block truncate font-serif text-lg font-semibold tracking-widest">
              星羲弦沚
            </span>
            <span className="text-sidebar-foreground/70 block truncate text-[10px] tracking-wider">
              吴地文史 · 木渎
            </span>
          </span>
        )}
      </Link>
      <WorkspaceSidebarToggle />
    </div>
  );
}
