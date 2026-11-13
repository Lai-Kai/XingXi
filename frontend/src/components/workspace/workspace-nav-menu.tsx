"use client";

import { SettingsIcon } from "lucide-react";
import { useState } from "react";

import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";
import { useAuth } from "@/core/auth/AuthProvider";
import { businessRoleLabel } from "@/core/auth/permissions";
import { useI18n } from "@/core/i18n/hooks";

import { SettingsDialog } from "./settings";

export function WorkspaceNavMenu() {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const { open, isMobile } = useSidebar();
  const isSidebarOpen = open || isMobile;
  const { t } = useI18n();
  const { user } = useAuth();
  const name = user?.email.split("@")[0] ?? "当前用户";

  return (
    <>
      <SettingsDialog
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
        defaultSection="appearance"
      />
      <SidebarMenu className="w-full">
        <SidebarMenuItem>
          <SidebarMenuButton
            size="lg"
            onClick={() => setSettingsOpen(true)}
            tooltip={t.common.settings}
            aria-label={t.common.settings}
            className="h-16 rounded-xl border border-white/80 bg-linear-to-br from-white/90 to-blue-50/50 px-3 text-slate-600 shadow-[0_2px_12px_rgb(30,64,120,0.025)] group-data-[collapsible=icon]:border-transparent group-data-[collapsible=icon]:p-2! hover:bg-white hover:text-blue-700"
          >
            {isSidebarOpen ? (
              <>
                <span
                  aria-hidden="true"
                  className="flex size-8 shrink-0 items-center justify-center rounded-full border border-blue-100 bg-blue-100/60 text-xs font-semibold text-blue-700"
                >
                  {name.slice(0, 1).toUpperCase()}
                </span>
                <span className="min-w-0 flex-1 text-left">
                  <span className="block truncate text-xs font-medium text-slate-700">
                    {name}
                  </span>
                  <span className="mt-0.5 block truncate text-[10px] text-slate-500">
                    {user?.organization_name ??
                      (user
                        ? businessRoleLabel(user.business_role)
                        : "账户设置")}
                  </span>
                </span>
                <SettingsIcon className="size-4 shrink-0 text-slate-400" />
              </>
            ) : (
              <SettingsIcon className="size-4" />
            )}
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    </>
  );
}
