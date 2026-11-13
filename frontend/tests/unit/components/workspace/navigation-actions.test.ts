import { existsSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, expect, rs, test } from "@rstest/core";
import { isValidElement, type ReactNode } from "react";

import { useSidebar } from "@/components/ui/sidebar";
import { WorkspaceHeader } from "@/components/workspace/workspace-header";
import { WorkspaceNavChatList } from "@/components/workspace/workspace-nav-chat-list";

rs.mock("next/navigation", () => ({ usePathname: () => "/workspace/agent" }));
rs.mock("@/core/auth/AuthProvider", () => ({
  useAuth: () => ({ user: { system_role: "admin", business_role: "public" } }),
}));
rs.mock("@/components/ui/sidebar", () => ({
  useSidebar: rs.fn(),
  SidebarGroup: "div",
  SidebarMenu: "ul",
  SidebarMenuItem: "li",
  SidebarMenuButton: "div",
  SidebarTrigger: "button",
}));

type LinkProps = { href: string; onClick?: () => void; children?: ReactNode };

function links(node: ReactNode): LinkProps[] {
  if (Array.isArray(node)) return node.flatMap(links);
  if (!isValidElement<Partial<LinkProps>>(node)) return [];
  const children = links(node.props.children);
  return typeof node.props.href === "string"
    ? [node.props as LinkProps, ...children]
    : children;
}

function sidebar() {
  const setOpenMobile = rs.fn();
  rs.mocked(useSidebar).mockReturnValue({
    state: "expanded",
    isMobile: true,
    setOpenMobile,
  } as unknown as ReturnType<typeof useSidebar>);
  return setOpenMobile;
}

afterEach(() => {
  rs.clearAllMocks();
});

test("every standard module link has a real page and dismisses mobile navigation", () => {
  const setOpenMobile = sidebar();
  const navigation = links(WorkspaceNavChatList());
  expect(navigation).toHaveLength(11);
  for (const link of navigation) {
    expect(link.href).not.toContain("/workspace/agents");
    expect(existsSync(resolve("src/app", `.${link.href}`, "page.tsx"))).toBe(
      true,
    );
    expect(link.onClick).toBeDefined();
    link.onClick?.();
    expect(setOpenMobile).toHaveBeenLastCalledWith(false);
  }
  expect(setOpenMobile).toHaveBeenCalledTimes(navigation.length);
});

test("the homepage logo also dismisses mobile navigation", () => {
  const setOpenMobile = sidebar();
  const [home] = links(WorkspaceHeader({}));
  expect(home?.href).toBe("/workspace");
  home?.onClick?.();
  expect(setOpenMobile).toHaveBeenCalledWith(false);
});
