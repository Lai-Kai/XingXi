import { getBackendBaseURL } from "../config";

import { fetch } from "./fetcher";

export interface FeedbackData {
  feedback_id: string;
  run_id?: string;
  thread_id?: string;
  user_id?: string | null;
  rating: number;
  comment: string | null;
  category?: FeedbackCategory | null;
  status?: FeedbackStatus;
  assignee_id?: string | null;
  review_note?: string | null;
  created_at?: string;
  updated_at?: string | null;
}

export type FeedbackCategory =
  | "citation_error"
  | "factual_error"
  | "missing_source"
  | "expression_issue"
  | "other";

export type FeedbackStatus =
  | "submitted"
  | "reviewing"
  | "accepted"
  | "rejected";

export interface QualityFeedbackPage {
  items: FeedbackData[];
  total: number;
  limit: number;
  offset: number;
}

export async function upsertFeedback(
  threadId: string,
  runId: string,
  rating: number,
  comment?: string,
  category?: FeedbackCategory,
): Promise<FeedbackData> {
  const res = await fetch(
    `${getBackendBaseURL()}/api/threads/${encodeURIComponent(threadId)}/runs/${encodeURIComponent(runId)}/feedback`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        rating,
        comment: comment ?? null,
        category: category ?? null,
      }),
    },
  );
  if (!res.ok) {
    throw new Error(`Failed to submit feedback: ${res.status}`);
  }
  return res.json();
}

export async function listQualityFeedback(options: {
  status?: FeedbackStatus | "all";
  category?: FeedbackCategory | "all";
  query?: string;
  page?: number;
  pageSize?: number;
} = {}): Promise<QualityFeedbackPage> {
  const pageSize = options.pageSize ?? 20;
  const params = new URLSearchParams({
    limit: String(pageSize),
    offset: String(Math.max(0, (options.page ?? 1) - 1) * pageSize),
  });
  if (options.status && options.status !== "all") params.set("status", options.status);
  if (options.category && options.category !== "all") params.set("category", options.category);
  if (options.query?.trim()) params.set("query", options.query.trim());
  const res = await fetch(
    `${getBackendBaseURL()}/api/threads/feedback/quality-queue?${params}`,
  );
  if (!res.ok) throw new Error(`Failed to load feedback queue: ${res.status}`);
  return res.json();
}

export async function reviewQualityFeedback(
  feedbackId: string,
  status: FeedbackStatus,
  reviewNote?: string,
): Promise<FeedbackData> {
  const res = await fetch(
    `${getBackendBaseURL()}/api/threads/feedback/${encodeURIComponent(feedbackId)}/review`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status, review_note: reviewNote ?? null }),
    },
  );
  if (!res.ok) throw new Error(`Failed to review feedback: ${res.status}`);
  return res.json();
}

export async function deleteFeedback(
  threadId: string,
  runId: string,
): Promise<void> {
  const res = await fetch(
    `${getBackendBaseURL()}/api/threads/${encodeURIComponent(threadId)}/runs/${encodeURIComponent(runId)}/feedback`,
    { method: "DELETE" },
  );
  if (!res.ok && res.status !== 404) {
    throw new Error(`Failed to delete feedback: ${res.status}`);
  }
}
