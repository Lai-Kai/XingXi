"use client";

import {
  Activity,
  BookMarked,
  BookOpen,
  Bot,
  ClipboardList,
  FolderKanban,
  FlaskConical,
  History,
  Map,
  Search,
  Share2,
  Scale,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  SidebarGroup,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";
import { useAuth } from "@/core/auth/AuthProvider";
import { hasCapability } from "@/core/auth/permissions";
import type { BusinessCapability, User } from "@/core/auth/types";

const navigation: Array<{
  label: string;
  href: string;
  icon: typeof Search;
  capability?: BusinessCapability;
}> = [
  { label: "文史检索", href: "/workspace", icon: Search },
  {
    label: "文献库",
    href: "/workspace/library",
    icon: BookOpen,
    capability: "source:manage",
  },
  { label: "星羲智能体", href: "/workspace/agent", icon: Bot },
  {
    label: "研究项目",
    href: "/workspace/projects",
    icon: FolderKanban,
    capability: "project:manage",
  },
  { label: "古舆地图", href: "/workspace/map", icon: Map },
  { label: "古文展签", href: "/workspace/glossary", icon: BookMarked },
  { label: "知识图谱", href: "/workspace/knowledge-graph", icon: Share2 },
  { label: "异名辨析", href: "/workspace/name-authority", icon: Scale },
  {
    label: "质量中心",
    href: "/workspace/quality",
    icon: ClipboardList,
    capability: "quality:read",
  },
  {
    label: "问答评测",
    href: "/workspace/evaluations",
    icon: FlaskConical,
    capability: "governance:read",
  },
  {
    label: "运营中心",
    href: "/workspace/operations",
    icon: Activity,
    capability: "governance:read",
  },
  { label: "最近研究", href: "/workspace/chats", icon: History },
];

export function navigationForUser(user: User | null) {
  return navigation.filter(
    (item) => !item.capability || hasCapability(user, item.capability),
  );
}

export function WorkspaceNavChatList() {
  const pathname = usePathname();
  const { user } = useAuth();
  const { setOpenMobile } = useSidebar();
  const visibleNavigation = navigationForUser(user).filter(
    (item) => item.href !== "/workspace/agent",
  );

  return (
    <SidebarGroup className="px-3 pt-3 group-data-[collapsible=icon]:px-2">
      <SidebarMenu className="gap-1">
        {visibleNavigation.map((item) => {
          const active =
            item.href === "/workspace"
              ? pathname === "/workspace"
              : pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <SidebarMenuItem key={item.label}>
              <SidebarMenuButton
                isActive={active}
                tooltip={item.label}
                className="h-9 rounded-xl px-3 text-[13px] text-slate-600 transition-colors duration-200 hover:bg-white/80 hover:text-blue-700 data-[active=true]:bg-blue-50/90 data-[active=true]:font-medium data-[active=true]:text-blue-700"
                asChild
              >
                <Link
                  href={item.href}
                  onClick={() => setOpenMobile(false)}
                  aria-current={active ? "page" : undefined}
                >
                  <Icon className="stroke-[1.7]" />
                  <span>{item.label}</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          );
        })}
      </SidebarMenu>
    </SidebarGroup>
  );
}
