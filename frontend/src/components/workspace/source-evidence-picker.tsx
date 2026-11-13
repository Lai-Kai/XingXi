"use client";

import { LoaderCircle, Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { reviewLabels } from "@/core/knowledge-graph/review";
import { searchStructuredKnowledge } from "@/core/knowledge-search/api";
import type { StructuredSearchHit } from "@/core/knowledge-search/types";
import { publicErrorMessage } from "@/core/ui/presentation";

export type SourceEvidenceSelection = StructuredSearchHit["citation"];

export function SourceEvidencePicker({
  name,
  suggestedQuery,
  selected,
  onChange,
}: {
  name: string;
  suggestedQuery: string;
  selected: SourceEvidenceSelection[];
  onChange: (selected: SourceEvidenceSelection[]) => void;
}) {
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [hits, setHits] = useState<StructuredSearchHit[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);

  useEffect(() => () => request.current?.abort(), []);

  async function search(more = false) {
    const text = more ? submittedQuery : query.trim() || suggestedQuery.trim();
    if (!text || (more && !cursor)) return;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setError(null);
    if (!more) {
      setHits([]);
      setCursor(null);
      setSubmittedQuery(text);
    }
    try {
      const response = await searchStructuredKnowledge(
        { query: text, page_size: 10, ...(more && cursor ? { cursor } : {}) },
        controller.signal,
      );
      if (controller.signal.aborted) return;
      setHits((current) => {
        const next = new Map(
          (more ? current : []).map((hit) => [hit.citation.evidence_id, hit]),
        );
        for (const hit of response.hits)
          next.set(hit.citation.evidence_id, hit);
        return [...next.values()];
      });
      setCursor(response.next_cursor);
      setSearched(true);
    } catch (reason) {
      if (!controller.signal.aborted)
        setError(publicErrorMessage(reason, "暂时无法查找资料出处，请重试。"));
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }

  function toggle(citation: SourceEvidenceSelection) {
    onChange(
      selected.some((item) => item.evidence_id === citation.evidence_id)
        ? selected.filter((item) => item.evidence_id !== citation.evidence_id)
        : [...selected, citation],
    );
  }

  return (
    <div className="mt-3 space-y-2">
      <div className="flex gap-2">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={suggestedQuery.trim() || "输入名称或原文关键词"}
          aria-label={`${name} 出处关键词`}
          className="border-border bg-card focus:border-primary h-9 min-w-0 flex-1 rounded-md border px-3 text-xs outline-none"
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.nativeEvent.isComposing) {
              event.preventDefault();
              void search();
            }
          }}
        />
        <button
          type="button"
          disabled={loading || !(query.trim() || suggestedQuery.trim())}
          onClick={() => void search()}
          className="border-border text-primary inline-flex h-9 items-center gap-1 rounded-md border px-2 text-xs disabled:opacity-40"
        >
          {loading ? (
            <LoaderCircle className="size-3.5 animate-spin" />
          ) : (
            <Search className="size-3.5" />
          )}
          查找出处
        </button>
      </div>
      {selected.length > 0 && (
        <ul aria-label={`${name} 已选出处`} className="space-y-1">
          {selected.map((citation) => (
            <li
              key={citation.evidence_id}
              className="bg-muted/60 flex items-center gap-2 rounded px-2 py-1.5 text-xs"
            >
              <span className="min-w-0 flex-1">
                《{citation.document_title || "书名未详"}》 · 第{" "}
                {citation.page_start} 页
              </span>
              <button
                type="button"
                onClick={() => toggle(citation)}
                aria-label={`移除《${citation.document_title || "书名未详"}》第 ${citation.page_start} 页`}
                className="text-muted-foreground hover:text-foreground grid size-7 place-items-center"
              >
                <X className="size-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}
      {error && (
        <p role="alert" className="text-xs text-red-700">
          {error}
        </p>
      )}
      {hits.length > 0 && (
        <div
          className="border-border max-h-72 space-y-2 overflow-y-auto rounded-md border p-2"
          aria-label={`${name} 出处搜索结果`}
        >
          {hits.map(({ citation }) => (
            <label
              key={citation.evidence_id}
              className="hover:bg-muted/60 flex cursor-pointer items-start gap-2 rounded p-1 text-xs"
            >
              <input
                type="checkbox"
                checked={selected.some(
                  (item) => item.evidence_id === citation.evidence_id,
                )}
                onChange={() => toggle(citation)}
                className="accent-primary mt-0.5 size-4 shrink-0"
              />
              <span className="min-w-0 space-y-1">
                <span className="block font-medium">
                  《{citation.document_title || "书名未详"}》
                  {citation.edition ? ` · ${citation.edition}` : ""} · 第{" "}
                  {citation.page_start}
                  {citation.page_end !== citation.page_start
                    ? `–${citation.page_end}`
                    : ""}{" "}
                  页
                </span>
                <span className="text-muted-foreground block">
                  {reviewLabels[citation.review_status]}
                </span>
                <span className="text-muted-foreground line-clamp-3 block font-serif leading-6">
                  {citation.quote}
                </span>
              </span>
            </label>
          ))}
          {cursor && (
            <button
              type="button"
              disabled={loading}
              onClick={() => void search(true)}
              className="text-primary min-h-9 w-full text-xs disabled:opacity-40"
            >
              加载更多出处
            </button>
          )}
        </div>
      )}
      {searched && !loading && !error && hits.length === 0 && (
        <p className="text-muted-foreground text-xs">
          未找到可用出处，请更换关键词。
        </p>
      )}
      {!searched && selected.length === 0 && (
        <p className="text-muted-foreground text-xs">
          查找并勾选与此名称有关的原文。
        </p>
      )}
    </div>
  );
}
