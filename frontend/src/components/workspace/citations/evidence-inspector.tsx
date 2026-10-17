"use client";

import type { Message } from "@langchain/langgraph-sdk";
import {
  BookOpenText,
  ExternalLink,
  PanelRightClose,
  PanelRightOpen,
  X,
} from "lucide-react";
import Link from "next/link";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";

import {
  Sheet,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import {
  evidenceDetailPath,
  extractCitationSources,
  type CitationSource,
} from "@/core/citations/sources";
import {
  extractContentFromMessage,
  isHiddenFromUIMessage,
} from "@/core/messages/utils";
import { useIsMobile } from "@/hooks/use-mobile";

import { useArtifacts } from "../artifacts";
import { BusinessButton } from "../business-controls";
import { BusinessSheetContent } from "../business-surfaces";
import { useMaybeSidecar } from "../sidecar";

import { EvidenceDetailPanel } from "./evidence-detail-panel";
import {
  EvidenceInspectorContext as Context,
  useEvidenceInspector,
  type EvidenceSelection,
} from "./evidence-inspector-context";

const WIDE_QUERY = "(min-width: 1280px)";
function subscribeWide(callback: () => void) {
  const media = window.matchMedia(WIDE_QUERY);
  media.addEventListener("change", callback);
  return () => media.removeEventListener("change", callback);
}
function wideSnapshot() {
  return window.matchMedia(WIDE_QUERY).matches;
}
function serverSnapshot() {
  return false;
}

export function EvidenceInspectorProvider({
  children,
  messages,
  defaultOpen = false,
}: {
  children: ReactNode;
  messages: Message[];
  defaultOpen?: boolean;
}) {
  const wide = useSyncExternalStore(
    subscribeWide,
    wideSnapshot,
    serverSnapshot,
  );
  const mobile = useIsMobile();
  const [open, setOpen] = useState(false);
  const [selection, setSelection] = useState<EvidenceSelection | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  const dragStartRef = useRef<number | null>(null);
  const artifacts = useArtifacts();
  const sidecar = useMaybeSidecar();
  useEffect(() => {
    setOpen(wide && defaultOpen);
  }, [wide, defaultOpen]);
  const close = useCallback(() => {
    setOpen(false);
    if (wide) triggerRef.current?.focus();
  }, [wide]);
  const openEvidence = useCallback(
    (next?: EvidenceSelection, trigger?: HTMLElement) => {
      if (next) setSelection(next);
      if (trigger) triggerRef.current = trigger;
      artifacts.setOpen(false);
      sidecar?.close();
      setOpen(true);
    },
    [artifacts, sidecar],
  );
  const sources = useMemo(() => {
    const unique = new Map<string, CitationSource>();
    for (const message of messages) {
      if (message.type !== "ai" || isHiddenFromUIMessage(message)) continue;
      for (const source of extractCitationSources(
        extractContentFromMessage(message),
      )) {
        const previous = unique.get(source.id);
        unique.set(
          source.id,
          previous
            ? { ...previous, count: previous.count + source.count }
            : source,
        );
      }
    }
    return [...unique.values()];
  }, [messages]);
  const visible = open && !artifacts.open && !sidecar?.open;
  const context = useMemo(
    () => ({ open: visible, openEvidence, close }),
    [visible, openEvidence, close],
  );
  const panel = (
    <>
      <header className="bg-card flex shrink-0 items-center justify-between gap-2 border-b px-4 py-3">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 font-serif text-base font-semibold">
            <BookOpenText className="text-primary size-4" />
            史料考据视窗
          </h2>
          <p className="text-muted-foreground mt-1 text-xs">
            循引文定位原始出处
          </p>
        </div>
        <BusinessButton
          variant="ghost"
          size="icon"
          className="size-11"
          aria-label="关闭史料考据视窗"
          onClick={close}
        >
          <X className="size-4" />
        </BusinessButton>
      </header>
      {selection ? (
        <div key={selection.id} className="flex min-h-0 flex-1 flex-col">
          <div className="bg-secondary/40 shrink-0 border-b px-4 py-3">
            <p className="text-primary text-xs">正在核对</p>
            <p className="mt-1 truncate font-serif font-semibold">
              {selection.title ?? "引用出处"}
            </p>
            <Link
              href={evidenceDetailPath(selection.id)}
              className="text-primary mt-2 inline-flex min-h-9 items-center gap-1 text-xs underline underline-offset-4"
            >
              在文献库中查看
              <ExternalLink className="size-3" />
            </Link>
          </div>
          <EvidenceDetailPanel
            evidenceId={selection.id}
            embedded
            onClose={close}
          />
          <BusinessButton
            variant="ghost"
            className="m-2 shrink-0"
            onClick={() => setSelection(null)}
          >
            返回本次对话出处
          </BusinessButton>
        </div>
      ) : (
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
          <p className="text-muted-foreground text-xs leading-6">
            {sources.length
              ? `已识别 ${sources.length} 项引用；来源等级与复核结论以出处详情为准。`
              : "点击回答中的引文，可在此核对书名、版本、卷页与证据原文。"}
          </p>
          {sources.length === 0 && (
            <div className="text-muted-foreground rounded-lg border border-dashed p-6 text-center">
              <BookOpenText className="mx-auto mb-3 size-7 opacity-50" />
              <p className="font-serif text-sm">等待一条可核验的引文</p>
              <p className="mt-2 text-xs leading-5">
                尚无引用时，不生成史料或置信度结论。
              </p>
            </div>
          )}
          <ol className="space-y-3">
            {sources.map((source, index) => (
              <li key={source.id} className="bg-muted/30 rounded-lg border p-3">
                <p className="text-muted-foreground mb-2 text-[11px]">
                  出处 {String(index + 1).padStart(2, "0")} · 引用{" "}
                  {source.count} 次
                </p>
                {source.evidenceId ? (
                  <button
                    type="button"
                    className="research-touch text-primary w-full rounded text-left font-serif text-sm font-medium underline underline-offset-4"
                    onClick={(event) =>
                      openEvidence(
                        { id: source.evidenceId!, title: source.title },
                        event.currentTarget,
                      )
                    }
                  >
                    {source.title}
                  </button>
                ) : (
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary text-sm break-words underline"
                  >
                    {source.title} ↗
                  </a>
                )}
                <p className="text-muted-foreground mt-2 text-xs">
                  {source.evidenceId ? "馆藏与文献证据" : source.domain}
                </p>
              </li>
            ))}
          </ol>
        </div>
      )}
    </>
  );
  return (
    <Context.Provider value={context}>
      <div className="research-chat bg-background flex size-full min-h-0 min-w-0">
        <div className="min-h-0 min-w-0 flex-1">{children}</div>
        {wide && visible && (
          <aside
            aria-label="史料考据视窗"
            className="bg-card flex h-full w-[380px] shrink-0 flex-col border-l"
          >
            {panel}
          </aside>
        )}
      </div>
      <Sheet
        open={!wide && visible}
        onOpenChange={(value) => {
          if (!value) close();
        }}
      >
        <BusinessSheetContent
          side={mobile ? "bottom" : "right"}
          className={
            mobile
              ? "flex h-[65dvh] max-h-[85dvh] flex-col gap-0 rounded-t-xl p-0 [&>button:last-child]:hidden"
              : "flex w-[420px] max-w-full flex-col gap-0 p-0 [&>button:last-child]:hidden"
          }
          onCloseAutoFocus={(event) => {
            if (triggerRef.current?.isConnected) {
              event.preventDefault();
              triggerRef.current.focus();
            }
          }}
        >
          <SheetHeader className="sr-only">
            <SheetTitle>史料考据视窗</SheetTitle>
            <SheetDescription>
              查看对话引用的文献、卷页与原文。
            </SheetDescription>
          </SheetHeader>
          {mobile && (
            <button
              type="button"
              aria-label="下滑关闭史料考据视窗"
              onClick={close}
              className="flex h-11 shrink-0 touch-none items-center justify-center"
              onPointerDown={(event) => {
                if (!event.isPrimary) return;
                dragStartRef.current = event.clientY;
                event.currentTarget.setPointerCapture(event.pointerId);
              }}
              onPointerUp={(event) => {
                if (
                  dragStartRef.current !== null &&
                  event.clientY - dragStartRef.current > 60
                )
                  close();
                dragStartRef.current = null;
              }}
              onPointerCancel={() => {
                dragStartRef.current = null;
              }}
            >
              <span className="bg-muted-foreground/35 h-1 w-12 rounded-full" />
            </button>
          )}
          {panel}
        </BusinessSheetContent>
      </Sheet>
    </Context.Provider>
  );
}

export function EvidenceInspectorTrigger() {
  const inspector = useEvidenceInspector();
  if (!inspector) return null;
  const Icon = inspector.open ? PanelRightClose : PanelRightOpen;
  return (
    <BusinessButton
      variant="ghost"
      size="icon"
      className="size-9 shrink-0"
      aria-label="史料考据"
      title="史料考据"
      aria-expanded={inspector.open}
      onClick={(event) =>
        inspector.open
          ? inspector.close()
          : inspector.openEvidence(undefined, event.currentTarget)
      }
    >
      <Icon className="size-4" />
    </BusinessButton>
  );
}
