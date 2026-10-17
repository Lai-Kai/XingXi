"use client";

import { useId, useState } from "react";

import {
  reviewActions,
  reviewNoteRequired,
} from "@/core/knowledge-graph/review";
import type { ReviewStatus } from "@/core/knowledge-graph/types";

export function GraphReviewControls({
  status,
  hasEvidence,
  disabled,
  onReview,
}: {
  status: ReviewStatus;
  hasEvidence: boolean;
  disabled: boolean;
  onReview: (status: ReviewStatus, note: string) => Promise<void>;
}) {
  const noteId = useId();
  const [open, setOpen] = useState(false);
  const [next, setNext] = useState<ReviewStatus | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const required = next !== null && reviewNoteRequired(status, next);

  async function submit() {
    if (!next || next === status || (required && !note.trim())) return;
    setError(null);
    try {
      await onReview(next, note.trim());
      setOpen(false);
      setNext(null);
      setNote("");
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "审核保存失败，请重试。",
      );
    }
  }

  return (
    <div className="graph-review-card bg-secondary/30 mt-3 rounded-lg border p-3 text-xs">
      <button
        type="button"
        disabled={disabled}
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="text-primary hover:underline disabled:opacity-50"
      >
        修改审核结果
      </button>
      {open && (
        <div className="border-border bg-card mt-2 space-y-2 rounded border p-2">
          <div
            className="flex flex-wrap gap-2"
            role="group"
            aria-label="新的审核结果"
          >
            {reviewActions(status).map((action) => (
              <button
                key={action.status}
                type="button"
                disabled={
                  disabled || (action.status === "reviewed" && !hasEvidence)
                }
                aria-pressed={next === action.status}
                onClick={() => setNext(action.status)}
                className={`rounded border px-2 py-1 disabled:cursor-not-allowed disabled:opacity-40 ${next === action.status ? "border-primary/50 bg-card text-primary" : "border-border"}`}
              >
                {action.label}
              </button>
            ))}
          </div>
          {!hasEvidence && <p>无资料出处，不能审核通过。</p>}
          <label htmlFor={noteId} className="block">
            审核备注{required ? "（必填）" : "（选填）"}
          </label>
          <textarea
            id={noteId}
            value={note}
            required={required}
            maxLength={2000}
            disabled={disabled}
            onChange={(event) => setNote(event.target.value)}
            className="bg-card min-h-20 w-full rounded border p-2"
          />
          {error && (
            <p role="alert" className="text-heritage-rejected-foreground">
              {error}
            </p>
          )}
          <button
            type="button"
            disabled={
              disabled ||
              !next ||
              next === status ||
              (next === "reviewed" && !hasEvidence) ||
              (required && !note.trim())
            }
            onClick={() => void submit()}
            className="bg-primary text-primary-foreground rounded px-3 py-1.5 disabled:opacity-40"
          >
            {disabled ? "保存中…" : "保存审核结果"}
          </button>
        </div>
      )}
    </div>
  );
}
