"use client";

import { useRef } from "react";

import {
  Sheet,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import {
  Sidebar,
  SidebarHeader,
  SidebarContent,
  SidebarFooter,
  useSidebar,
} from "@/components/ui/sidebar";
import { cn } from "@/lib/utils";

import { BusinessSheetContent } from "./business-surfaces";
import { RecentChatList } from "./recent-chat-list";
import { WorkspaceSidebarRail } from "./resizable-sidebar";
import { WorkspaceHeader } from "./workspace-header";
import { WorkspaceNavChatList } from "./workspace-nav-chat-list";
import { WorkspaceNavMenu } from "./workspace-nav-menu";

export function WorkspaceSidebar({
  className,
  ...props
}: React.ComponentProps<typeof Sidebar>) {
  const { open, isMobile, openMobile, setOpenMobile } = useSidebar();
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const content = (
    <>
      <SidebarHeader className="border-sidebar-border border-b px-2 py-0">
        <WorkspaceHeader />
      </SidebarHeader>
      <SidebarContent className="gap-0 overscroll-contain">
        <WorkspaceNavChatList />
        {(open || isMobile) && <RecentChatList />}
      </SidebarContent>
      <SidebarFooter className="border-sidebar-border shrink-0 border-t">
        <WorkspaceNavMenu />
      </SidebarFooter>
    </>
  );

  if (isMobile) {
    return (
      <Sheet open={openMobile} onOpenChange={setOpenMobile}>
        <BusinessSheetContent
          side="left"
          data-sidebar="sidebar"
          data-mobile="true"
          className="bg-sidebar text-sidebar-foreground w-72 overflow-hidden p-0 sm:max-w-72 [&>button]:hidden"
          onOpenAutoFocus={() => {
            returnFocusRef.current =
              document.activeElement instanceof HTMLElement
                ? document.activeElement
                : null;
          }}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            const target = returnFocusRef.current;
            if (target?.isConnected) target.focus();
            else document.getElementById("workspace-content")?.focus();
          }}
        >
          <SheetHeader className="sr-only">
            <SheetTitle>工作区导航</SheetTitle>
            <SheetDescription>
              按功能分组的星羲工作区导航与账户设置。
            </SheetDescription>
          </SheetHeader>
          <div className="flex h-full min-h-0 w-full flex-col">{content}</div>
        </BusinessSheetContent>
      </Sheet>
    );
  }
  return (
    <>
      <Sidebar
        variant="sidebar"
        collapsible="icon"
        className={cn(
          "workspace-sidebar z-30 group-data-[resizing=true]:transition-none",
          className,
        )}
        {...props}
      >
        {content}
        <WorkspaceSidebarRail />
      </Sidebar>
    </>
  );
}
