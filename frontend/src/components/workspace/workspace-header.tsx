"use client";

import { Sparkles } from "lucide-react";
import Link from "next/link";

import { SidebarTrigger, useSidebar } from "@/components/ui/sidebar";
import { useAuth } from "@/core/auth/AuthProvider";
import { businessRoleLabel } from "@/core/auth/permissions";
import { cn } from "@/lib/utils";

export function WorkspaceHeader({ className }: { className?: string }) {
  const { state } = useSidebar();
  const { user } = useAuth();
  const isCollapsed = state === "collapsed";

  return (
    <div
      className={cn(
        "flex h-16 items-center gap-2 px-1",
        isCollapsed ? "justify-center" : "justify-between",
        className,
      )}
    >
      {isCollapsed ? (
        <SidebarTrigger
          className="size-8 opacity-100"
          aria-label="展开侧栏"
          title="展开侧栏"
        />
      ) : (
        <>
          <Link
            href="/workspace"
            aria-label="星羲弦沚首页"
            className="flex min-w-0 items-center gap-2.5"
          >
            <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-[#20282b] text-white">
              <Sparkles className="size-5" />
            </span>
            <span className="min-w-0">
              <span className="block truncate text-base font-semibold">
                星羲弦沚
              </span>
              {user && (
                <span className="block truncate text-[11px] text-[#648087]">
                  {businessRoleLabel(user.business_role)}
                  {user.organization_name ? ` · ${user.organization_name}` : ""}
                </span>
              )}
            </span>
          </Link>
          <SidebarTrigger />
        </>
      )}
    </div>
  );
}
