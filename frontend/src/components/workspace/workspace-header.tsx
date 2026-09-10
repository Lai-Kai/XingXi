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

  return (
    <div
      className={cn(
        "flex h-16 items-center justify-between gap-2 px-1",
        className,
      )}
    >
      <Link
        href="/workspace"
        aria-label="星羲弦沚首页"
        className="flex min-w-0 items-center gap-2.5"
      >
        <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-[#20282b] text-white">
          <Sparkles className="size-5" />
        </span>
        {state !== "collapsed" && (
          <span className="min-w-0">
            <span className="block truncate text-base font-semibold">星羲弦沚</span>
            {user && (
              <span className="block truncate text-[11px] text-[#648087]">
                {businessRoleLabel(user.business_role)}
                {user.organization_name ? ` · ${user.organization_name}` : ""}
              </span>
            )}
          </span>
        )}
      </Link>
      {state !== "collapsed" && <SidebarTrigger />}
    </div>
  );
}
