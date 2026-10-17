"use client";

import { SettingsIcon, UserRound } from "lucide-react";
import { useRef, useState } from "react";

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
  const [section, setSection] = useState<"appearance" | "account">(
    "appearance",
  );
  const [settingsOpen, setSettingsOpen] = useState(false);
  const settingsTriggerRef = useRef<HTMLElement | null>(null);
  const { open, isMobile } = useSidebar();
  const { user } = useAuth();
  const { t } = useI18n();
  const expanded = open || isMobile;
  const identity = user
    ? businessRoleLabel(user.business_role)
    : "尚未连接账户";
  const organization = user?.organization_name ?? user?.email;

  function openSettings(
    nextSection: "appearance" | "account",
    trigger: HTMLElement,
  ) {
    settingsTriggerRef.current = trigger;
    setSection(nextSection);
    setSettingsOpen(true);
  }

  return (
    <>
      <SettingsDialog
        key={section}
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
        defaultSection={section}
        restoreFocusRef={settingsTriggerRef}
      />
      <SidebarMenu className="w-full gap-1">
        <SidebarMenuItem>
          <SidebarMenuButton
            className="h-11 gap-3 px-3"
            onClick={(event) => openSettings("appearance", event.currentTarget)}
            tooltip={t.common.settings}
            aria-label={t.common.settings}
          >
            <SettingsIcon aria-hidden="true" />
            <span>{t.common.settings}</span>
          </SidebarMenuButton>
        </SidebarMenuItem>
        <SidebarMenuItem>
          <SidebarMenuButton
            className="h-14 gap-3 px-3"
            onClick={(event) => openSettings("account", event.currentTarget)}
            tooltip={`${identity}${organization ? ` · ${organization}` : ""}`}
            aria-label="账户设置"
          >
            <UserRound aria-hidden="true" />
            {expanded && (
              <span className="min-w-0">
                <span className="block truncate text-xs font-medium">
                  {identity}
                </span>
                {organization && (
                  <span className="text-sidebar-foreground/70 block truncate text-[10px]">
                    {organization}
                  </span>
                )}
              </span>
            )}
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    </>
  );
}
