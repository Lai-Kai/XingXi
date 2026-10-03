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
    label: "Agent 评测",
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
  const visibleNavigation = navigationForUser(user);

  return (
    <SidebarGroup className="pt-2">
      <SidebarMenu className="gap-1.5">
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
                className="h-10 px-3"
                asChild
              >
                <Link href={item.href}>
                  <Icon />
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
