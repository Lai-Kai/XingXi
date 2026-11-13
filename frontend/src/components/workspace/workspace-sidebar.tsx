"use client";

import {
  Sidebar,
  SidebarHeader,
  SidebarContent,
  SidebarFooter,
  useSidebar,
} from "@/components/ui/sidebar";
import { cn } from "@/lib/utils";

import { RecentChatList } from "./recent-chat-list";
import { WorkspaceSidebarRail } from "./resizable-sidebar";
import { WorkspaceAgentEntry } from "./workspace-agent-entry";
import { WorkspaceHeader } from "./workspace-header";
import { WorkspaceNavChatList } from "./workspace-nav-chat-list";
import { WorkspaceNavMenu } from "./workspace-nav-menu";

export function WorkspaceSidebar({
  className,
  ...props
}: React.ComponentProps<typeof Sidebar>) {
  const { open: isSidebarOpen, isMobile } = useSidebar();
  return (
    <>
      <Sidebar
        variant="sidebar"
        collapsible="icon"
        className={cn(
          "xingxi-sidebar z-30 group-data-[resizing=true]:transition-none",
          className,
        )}
        {...props}
      >
        <SidebarHeader className="px-3 pt-2 pb-0 group-data-[collapsible=icon]:px-2">
          <WorkspaceHeader />
          <WorkspaceAgentEntry />
        </SidebarHeader>
        <SidebarContent>
          <WorkspaceNavChatList />
          {(isSidebarOpen || isMobile) && <RecentChatList />}
        </SidebarContent>
        <SidebarFooter className="p-3 group-data-[collapsible=icon]:p-2">
          <WorkspaceNavMenu />
        </SidebarFooter>
        <WorkspaceSidebarRail />
      </Sidebar>
    </>
  );
}
