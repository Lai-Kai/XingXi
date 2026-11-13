"use client";

import { ArrowUpRight, BookOpen, FileText, X } from "lucide-react";
import { useRef } from "react";

import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { EvidenceDetailPanel } from "@/components/workspace/citations/evidence-detail-panel";
import { type HomeSource, sourcePageLabel } from "@/core/home/model";

export function HomeEvidencePreview({
  source,
  onOpen,
}: {
  source: HomeSource;
  onOpen: (source: HomeSource) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onOpen(source)}
      aria-label={`查看原文：${source.document_title}`}
      className="home-evidence group flex w-full items-center gap-4 rounded-2xl border border-white/80 bg-white/60 p-4 text-left shadow-sm transition-all duration-200 hover:border-blue-200 hover:bg-white/90 sm:gap-6 sm:px-6"
    >
      <span className="flex size-10 shrink-0 items-center justify-center rounded-xl border border-violet-100 bg-violet-50 text-violet-600">
        <BookOpen className="size-5" aria-hidden="true" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[11px] font-medium tracking-wider text-slate-500">
          从一页文献开始
        </span>
        <span className="mt-1 block truncate text-sm font-semibold text-slate-800">
          {source.document_title}
        </span>
        <span className="mt-1 block text-xs text-slate-500">
          {sourcePageLabel(source)}
          <span className="mx-2 text-slate-300">/</span>查看出处与原文
        </span>
      </span>
      <span
        aria-hidden="true"
        className="home-document-leaf hidden h-24 w-20 shrink-0 overflow-hidden rounded border border-slate-200/80 bg-[#fffefa] px-2.5 py-2 shadow-sm sm:block"
      >
        <span className="flex items-center gap-1 border-b border-slate-200/70 pb-1 text-[8px] text-slate-400">
          <FileText className="size-2.5" />
          {source.quote ? "文字摘录" : "书目线索"}
        </span>
        <span className="mt-1.5 line-clamp-3 font-serif text-[9px] leading-[1.7] text-slate-600">
          {source.quote ?? source.document_title}
        </span>
        <span className="mt-1 block text-[8px] text-slate-400">
          {sourcePageLabel(source)}
        </span>
      </span>
      <ArrowUpRight
        aria-hidden="true"
        className="size-4 shrink-0 text-slate-400 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-blue-600"
      />
    </button>
  );
}

export function HomeEvidenceSheet({
  source,
  onClose,
}: {
  source: HomeSource | null;
  onClose: () => void;
}) {
  const returnFocus = useRef<HTMLElement | null>(null);
  return (
    <Sheet
      open={source !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <SheetContent
        className="home-surface w-full gap-0 overflow-y-auto bg-[#f8faff] sm:max-w-xl [&>button]:hidden"
        onOpenAutoFocus={() => {
          returnFocus.current =
            document.activeElement instanceof HTMLElement
              ? document.activeElement
              : null;
        }}
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          returnFocus.current?.focus();
        }}
      >
        <SheetHeader className="border-b border-slate-200/70 px-6 py-6 pr-12">
          <SheetTitle>原文与出处</SheetTitle>
          <SheetDescription>
            {source?.document_title} · {source ? sourcePageLabel(source) : ""}
          </SheetDescription>
          <SheetClose asChild>
            <button
              type="button"
              aria-label="关闭原文"
              className="absolute top-5 right-5 rounded-lg p-2 text-slate-500 transition-colors hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-blue-500"
            >
              <X className="size-4" aria-hidden="true" />
            </button>
          </SheetClose>
        </SheetHeader>
        {source && (
          <>
            {source.quote && (
              <section className="mx-5 mt-5 rounded-xl border border-violet-100 bg-violet-50/60 p-4">
                <h2 className="text-xs font-medium text-violet-700">
                  选题摘录
                </h2>
                <blockquote className="mt-2 font-serif text-sm leading-7 whitespace-pre-wrap text-slate-700">
                  {source.quote}
                </blockquote>
              </section>
            )}
            <EvidenceDetailPanel
              evidenceId={source.evidence_id}
              onClose={onClose}
              embedded
            />
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
