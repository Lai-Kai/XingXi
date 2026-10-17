import {
  Activity,
  BookMarked,
  BookOpen,
  Bot,
  CalendarClock,
  ClipboardList,
  FlaskConical,
  FolderKanban,
  History,
  Map,
  Scale,
  Search,
  Share2,
  type LucideIcon,
} from "lucide-react";

import { hasCapability } from "@/core/auth/permissions";
import type { BusinessCapability, User } from "@/core/auth/types";

type WorkspaceNavigationItem = {
  label: string;
  href: string;
  icon: LucideIcon;
  capability?: BusinessCapability;
};

const navigationGroups: { label: string; items: WorkspaceNavigationItem[] }[] =
  [
    {
      label: "核心研究",
      items: [
        { label: "文史检索", href: "/workspace", icon: Search },
        { label: "星羲研究助手", href: "/workspace/agent", icon: Bot },
        { label: "最近研究", href: "/workspace/chats", icon: History },
        {
          label: "研究项目",
          href: "/workspace/projects",
          icon: FolderKanban,
          capability: "project:manage",
        },
      ],
    },
    {
      label: "时空人文",
      items: [
        { label: "古舆地图", href: "/workspace/map", icon: Map },
        { label: "知识图谱", href: "/workspace/knowledge-graph", icon: Share2 },
        { label: "古文展签", href: "/workspace/glossary", icon: BookMarked },
        { label: "异名辨析", href: "/workspace/name-authority", icon: Scale },
      ],
    },
    {
      label: "文献与治理",
      items: [
        {
          label: "文献库",
          href: "/workspace/library",
          icon: BookOpen,
          capability: "source:manage",
        },
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
        {
          label: "定时研究任务",
          href: "/workspace/scheduled-tasks",
          icon: CalendarClock,
        },
      ],
    },
  ];

export function navigationGroupsForUser(user: User | null) {
  return navigationGroups
    .map((group) => ({
      ...group,
      items: group.items.filter(
        (item) => !item.capability || hasCapability(user, item.capability),
      ),
    }))
    .filter((group) => group.items.length > 0);
}

export function navigationForUser(user: User | null) {
  return navigationGroupsForUser(user).flatMap((group) => group.items);
}

export function isWorkspaceRouteActive(pathname: string, href: string) {
  return (
    pathname === href ||
    (href !== "/workspace" && pathname.startsWith(`${href}/`))
  );
}

export function workspacePageTitle(pathname: string) {
  return (
    navigationGroups
      .flatMap((group) => group.items)
      .find((item) => isWorkspaceRouteActive(pathname, item.href))?.label ??
    "星羲工作区"
  );
}
