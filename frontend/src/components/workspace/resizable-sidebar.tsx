"use client";

import * as React from "react";

import { SidebarProvider, useSidebar } from "@/components/ui/sidebar";
import { cn } from "@/lib/utils";

const SIDEBAR_DEFAULT_WIDTH = 256;
const SIDEBAR_COLLAPSED_WIDTH = 48;
const SIDEBAR_MIN_EXPANDED_WIDTH = 224;
const SIDEBAR_MAX_WIDTH = 480;
const SIDEBAR_COLLAPSE_THRESHOLD = 160;

type SidebarResizeContextValue = {
  sidebarWidth: number;
  setSidebarWidth: (width: number) => void;
};

const SidebarResizeContext =
  React.createContext<SidebarResizeContextValue | null>(null);

function useSidebarResize() {
  const context = React.useContext(SidebarResizeContext);
  if (!context) {
    throw new Error(
      "useSidebarResize must be used within WorkspaceSidebarProvider.",
    );
  }
  return context;
}

export function WorkspaceSidebarProvider({
  defaultOpen = true,
  className,
  style,
  ...props
}: Omit<
  React.ComponentProps<typeof SidebarProvider>,
  "open" | "onOpenChange"
>) {
  const [open, setOpen] = React.useState(defaultOpen);
  const [sidebarWidth, setSidebarWidthState] = React.useState(
    SIDEBAR_DEFAULT_WIDTH,
  );

  const setSidebarWidth = React.useCallback((width: number) => {
    setSidebarWidthState(
      Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_EXPANDED_WIDTH, width)),
    );
  }, []);

  const resizeContext = React.useMemo(
    () => ({ sidebarWidth, setSidebarWidth }),
    [sidebarWidth, setSidebarWidth],
  );

  return (
    <SidebarResizeContext.Provider value={resizeContext}>
      <SidebarProvider
        {...props}
        open={open}
        onOpenChange={setOpen}
        className={cn(
          "has-data-[resizing=true]:[&_[data-slot=sidebar-gap]]:transition-none",
          className,
        )}
        style={
          {
            ...style,
            "--sidebar-width": `${sidebarWidth}px`,
            "--sidebar-width-icon": `${SIDEBAR_COLLAPSED_WIDTH}px`,
          } as React.CSSProperties
        }
      />
    </SidebarResizeContext.Provider>
  );
}

type ActiveSidebarResize = {
  pointerId: number;
  startX: number;
  startWidth: number;
  startExpandedWidth: number;
  startOpen: boolean;
  direction: 1 | -1;
  didDrag: boolean;
  bodyCursor: string;
  bodyUserSelect: string;
};

export function WorkspaceSidebarRail({ className }: { className?: string }) {
  const { open, setOpen, toggleSidebar } = useSidebar();
  const { sidebarWidth, setSidebarWidth } = useSidebarResize();
  const railRef = React.useRef<HTMLButtonElement | null>(null);
  const activeResizeRef = React.useRef<ActiveSidebarResize | null>(null);
  const openRef = React.useRef(open);
  const ignoreClickUntilRef = React.useRef(0);
  openRef.current = open;

  const updateOpen = React.useCallback(
    (nextOpen: boolean) => {
      if (openRef.current === nextOpen) return;
      openRef.current = nextOpen;
      setOpen(nextOpen);
    },
    [setOpen],
  );

  const finishResize = React.useCallback(
    ({ restore = false, ignoreClick = false } = {}) => {
      const activeResize = activeResizeRef.current;
      if (!activeResize) return;

      activeResizeRef.current = null;
      if (restore) {
        setSidebarWidth(activeResize.startExpandedWidth);
        updateOpen(activeResize.startOpen);
      }
      if (ignoreClick && activeResize.didDrag) {
        ignoreClickUntilRef.current = Date.now() + 1_000;
      }

      const rail = railRef.current;
      rail?.removeAttribute("data-resizing");
      rail
        ?.closest<HTMLElement>("[data-slot='sidebar'][data-state]")
        ?.removeAttribute("data-resizing");
      if (rail?.hasPointerCapture(activeResize.pointerId)) {
        rail.releasePointerCapture(activeResize.pointerId);
      }

      document.body.style.cursor = activeResize.bodyCursor;
      document.body.style.userSelect = activeResize.bodyUserSelect;
    },
    [setSidebarWidth, updateOpen],
  );

  React.useEffect(() => {
    const handleWindowBlur = () => finishResize({ ignoreClick: true });
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || !activeResizeRef.current) return;
      event.preventDefault();
      finishResize({ restore: true, ignoreClick: true });
    };

    window.addEventListener("blur", handleWindowBlur);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("blur", handleWindowBlur);
      window.removeEventListener("keydown", handleKeyDown);
      finishResize();
    };
  }, [finishResize]);

  return (
    <button
      ref={railRef}
      type="button"
      data-sidebar="rail"
      data-slot="sidebar-rail"
      aria-label="Resize or toggle Sidebar"
      draggable={false}
      tabIndex={-1}
      title="Resize or toggle Sidebar"
      className={cn(
        "data-[resizing=true]:after:bg-sidebar-border focus-visible:after:bg-sidebar-ring absolute inset-y-0 z-30 hidden w-4 -translate-x-1/2 touch-none select-none group-data-[side=left]:-right-4 group-data-[side=right]:left-0 after:pointer-events-none after:absolute after:inset-y-0 after:left-1/2 after:w-[2px] after:bg-transparent focus-visible:outline-none sm:flex",
        "in-data-[side=left]:cursor-w-resize in-data-[side=right]:cursor-e-resize",
        "[[data-side=left][data-state=collapsed]_&]:cursor-e-resize [[data-side=right][data-state=collapsed]_&]:cursor-w-resize",
        className,
      )}
      onClick={(event) => {
        if (Date.now() < ignoreClickUntilRef.current) {
          ignoreClickUntilRef.current = 0;
          event.preventDefault();
          event.stopPropagation();
          return;
        }
        toggleSidebar();
      }}
      onPointerDown={(event) => {
        if (
          !event.isPrimary ||
          (event.pointerType === "mouse" && event.button !== 0)
        ) {
          return;
        }

        event.preventDefault();
        finishResize();
        const side =
          event.currentTarget.closest<HTMLElement>("[data-side]")?.dataset.side;
        activeResizeRef.current = {
          pointerId: event.pointerId,
          startX: event.clientX,
          startWidth: open ? sidebarWidth : SIDEBAR_COLLAPSED_WIDTH,
          startExpandedWidth: sidebarWidth,
          startOpen: open,
          direction: side === "right" ? -1 : 1,
          didDrag: false,
          bodyCursor: document.body.style.cursor,
          bodyUserSelect: document.body.style.userSelect,
        };
        event.currentTarget.dataset.resizing = "true";
        event.currentTarget
          .closest<HTMLElement>("[data-slot='sidebar'][data-state]")
          ?.setAttribute("data-resizing", "true");
        document.body.style.cursor = "col-resize";
        document.body.style.userSelect = "none";
        try {
          event.currentTarget.setPointerCapture(event.pointerId);
        } catch {
          finishResize();
        }
      }}
      onPointerMove={(event) => {
        const activeResize = activeResizeRef.current;
        if (activeResize?.pointerId !== event.pointerId) return;

        event.preventDefault();
        const delta =
          (event.clientX - activeResize.startX) * activeResize.direction;
        if (Math.abs(delta) >= 2) activeResize.didDrag = true;

        const nextWidth = activeResize.startWidth + delta;
        if (nextWidth <= SIDEBAR_COLLAPSE_THRESHOLD) {
          updateOpen(false);
          return;
        }

        setSidebarWidth(nextWidth);
        updateOpen(true);
      }}
      onPointerUp={(event) => {
        const activeResize = activeResizeRef.current;
        if (activeResize?.pointerId !== event.pointerId) return;
        finishResize({ ignoreClick: true });
      }}
      onPointerCancel={(event) => {
        const activeResize = activeResizeRef.current;
        if (activeResize?.pointerId !== event.pointerId) return;
        finishResize({ ignoreClick: true });
      }}
      onLostPointerCapture={(event) => {
        const activeResize = activeResizeRef.current;
        if (activeResize?.pointerId !== event.pointerId) return;
        finishResize({ ignoreClick: true });
      }}
    />
  );
}
