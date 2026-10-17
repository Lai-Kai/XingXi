"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";
import { useAuth } from "@/core/auth/AuthProvider";

import {
  isWorkspaceRouteActive,
  navigationGroupsForUser,
} from "./workspace-navigation";

export { navigationForUser } from "./workspace-navigation";

export function WorkspaceNavChatList() {
  const pathname = usePathname();
  const { user } = useAuth();
  const { isMobile, setOpenMobile } = useSidebar();

  return (
    <nav aria-label="工作区导航">
      {navigationGroupsForUser(user).map((group) => (
        <SidebarGroup key={group.label} className="workspace-nav-group py-2">
          <SidebarGroupLabel className="px-3 text-xs tracking-widest">
            {group.label}
          </SidebarGroupLabel>
          <SidebarMenu className="gap-1">
            {group.items.map((item) => {
              const active = isWorkspaceRouteActive(pathname, item.href);
              const Icon = item.icon;
              return (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton
                    isActive={active}
                    tooltip={item.label}
                    className="h-10 gap-3 rounded-lg px-3"
                    asChild
                  >
                    <Link
                      href={item.href}
                      aria-label={item.label}
                      aria-current={active ? "page" : undefined}
                      onClick={() => {
                        if (isMobile) setOpenMobile(false);
                      }}
                    >
                      <Icon aria-hidden="true" />
                      <span>{item.label}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              );
            })}
          </SidebarMenu>
        </SidebarGroup>
      ))}
    </nav>
  );
}
