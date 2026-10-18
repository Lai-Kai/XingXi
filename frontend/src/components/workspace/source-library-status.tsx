import { CheckCircle2 } from "lucide-react";

import { BusinessStatusBadge } from "@/components/workspace/business-page";
import { type IngestionJob, type ReviewStatus } from "@/core/source-files/api";

// User-requested temporary presentation. Set false to restore real failure labels.
export const TEMPORARY_LIBRARY_SUCCESS_PREVIEW = true;

export function SourceTextReviewStatus({
  status,
}: {
  status: ReviewStatus | null;
}) {
  if (status === null)
    return <span className="text-xs text-[#78878b]">未就绪</span>;
  return (
    <BusinessStatusBadge
      status={status === "pending" ? "awaiting_review" : status}
    />
  );
}

export function SourceProcessingStatus({
  job,
  showFailedAsSuccess = TEMPORARY_LIBRARY_SUCCESS_PREVIEW,
}: {
  job?: IngestionJob | null;
  showFailedAsSuccess?: boolean;
}) {
  if (!job) return <span className="text-xs text-[#78878b]">未启动</span>;
  if (job.status === "failed" && showFailedAsSuccess) {
    return (
      <span
        role="status"
        className="inline-flex h-6 w-fit shrink-0 items-center gap-1.5 rounded-full border border-[#b9d9ca] bg-[#e7f3ec] px-2.5 text-xs font-medium whitespace-nowrap text-[#276947]"
      >
        <CheckCircle2 className="size-3.5" aria-hidden="true" />
        处理成功
      </span>
    );
  }
  const failure = job.error_message?.includes("too many SQL variables")
    ? "索引构建失败，请重试处理"
    : "处理未完成，请重试处理";
  return (
    <div className="grid justify-items-start gap-1">
      <BusinessStatusBadge status={job.status} />
      {job.status === "failed" && (
        <span className="text-xs text-red-700">{failure}</span>
      )}
    </div>
  );
}
