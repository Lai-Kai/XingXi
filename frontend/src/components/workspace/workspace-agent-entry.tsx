"use client";

import { Bot } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";

export function WorkspaceAgentEntry() {
  const pathname = usePathname();
  const { setOpenMobile } = useSidebar();
  const active = pathname === "/workspace/agent";

  return (
    <SidebarMenu className="py-2">
      <SidebarMenuItem>
        <SidebarMenuButton
          asChild
          tooltip="星羲智能体"
          isActive={active}
          className="home-primary h-11 justify-center rounded-xl text-white shadow-[0_4px_12px_rgb(37,99,235,0.15)] transition-all duration-200 hover:-translate-y-0.5 hover:text-white hover:shadow-md active:text-white data-[active=true]:text-white"
        >
          <Link
            href="/workspace/agent"
            aria-current={active ? "page" : undefined}
            onClick={() => setOpenMobile(false)}
          >
            <Bot className="size-4" />
            <span>星羲智能体</span>
          </Link>
        </SidebarMenuButton>
      </SidebarMenuItem>
    </SidebarMenu>
  );
}
