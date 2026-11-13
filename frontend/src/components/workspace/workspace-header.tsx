"use client";

import { Compass } from "lucide-react";
import Link from "next/link";

import { SidebarTrigger, useSidebar } from "@/components/ui/sidebar";
import { useAuth } from "@/core/auth/AuthProvider";
import { businessRoleLabel } from "@/core/auth/permissions";
import { cn } from "@/lib/utils";

export function WorkspaceHeader({ className }: { className?: string }) {
  const { state, isMobile, setOpenMobile } = useSidebar();
  const { user } = useAuth();
  const isCollapsed = state === "collapsed" && !isMobile;

  return (
    <div
      className={cn(
        "flex h-16 items-center gap-2 text-slate-800",
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
            onClick={() => setOpenMobile(false)}
            aria-label="星羲弦沚首页"
            className="flex min-w-0 items-center gap-2.5"
          >
            <span className="home-primary flex size-9 shrink-0 items-center justify-center rounded-xl text-white shadow-sm">
              <Compass className="size-5" aria-hidden="true" />
            </span>
            <span className="min-w-0">
              <span className="block truncate text-base font-semibold">
                星羲弦沚
              </span>
              {user && (
                <span
                  className="mt-0.5 block w-fit max-w-full truncate rounded border border-blue-100 bg-blue-50/70 px-1.5 py-0.5 text-[9px] font-medium text-blue-600"
                  title={user.organization_name ?? undefined}
                >
                  {businessRoleLabel(user.business_role)}
                </span>
              )}
            </span>
          </Link>
          <SidebarTrigger
            className="size-7 shrink-0 text-slate-400 hover:bg-blue-50 hover:text-blue-600"
            aria-label="收起侧栏"
          />
        </>
      )}
    </div>
  );
}
