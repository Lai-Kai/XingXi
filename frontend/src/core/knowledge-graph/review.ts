import type { ReviewStatus } from "./types";

export type ReviewFilterValue = "all" | "reviewed" | "draft" | "rejected";

export const reviewLabels: Record<ReviewStatus, string> = {
  pending: "待复核",
  reviewed: "已通过",
  disputed: "有争议",
  rejected: "已驳回",
};

const actions: Array<{ status: ReviewStatus; label: string }> = [
  { status: "reviewed", label: "通过" },
  { status: "rejected", label: "驳回" },
  { status: "disputed", label: "有争议" },
  { status: "pending", label: "恢复待复核" },
];

export function reviewActions(current: ReviewStatus) {
  return actions.filter((action) => action.status !== current);
}

export function reviewNoteRequired(current: ReviewStatus, next: ReviewStatus) {
  return current !== "pending" || next === "rejected" || next === "disputed";
}

export function matchesReviewFilter(
  status: ReviewStatus,
  filter: ReviewFilterValue,
  isAdmin: boolean,
) {
  if (filter === "rejected") return isAdmin && status === "rejected";
  if (status === "rejected") return false;
  if (filter === "all") return true;
  if (filter === "reviewed") return status === "reviewed";
  return status === "pending" || status === "disputed";
}
