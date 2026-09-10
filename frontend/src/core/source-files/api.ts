import { fetch, readCsrfCookie } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

export type SourceDocumentSummary = {
  id: string;
  title: string;
  edition: string;
  source_institution: string;
  source_type: SourceType;
  source_type_label: string | null;
  source_level: SourceLevel;
  holder: string;
  status: SourceDocumentStatus;
  created_at: string;
  updated_at: string;
};

export type SourceDocumentStatus = "registered" | "archived";

export type SourceDocumentPage = {
  items: SourceDocumentSummary[];
  total: number;
  limit: number;
  offset: number;
};

export type SourceDocumentLibraryFile = {
  file: SourceFileRecord;
  ingestion_job: IngestionJob | null;
};

export type SourceDocumentLibraryItem = {
  source: SourceDocumentSummary;
  files: SourceDocumentLibraryFile[];
};

export type SourceDocumentLibraryPage = {
  items: SourceDocumentLibraryItem[];
  total: number;
  limit: number;
  offset: number;
};

export type SourceType =
  | "gazetteer"
  | "inscription"
  | "archive"
  | "heritage_record"
  | "scholarly_work"
  | "oral_history"
  | "web"
  | "inference"
  | "other";

export type SourceLevel = "A" | "B" | "C" | "D" | "E" | "U";

export type SourceDocumentCreateInput = {
  title: string;
  edition: string;
  source_institution: string;
  source_type: SourceType;
  source_type_label?: string | null;
  source_level: SourceLevel;
  holder: string;
};

export type SourceFileRecord = {
  id: string;
  document_id: string;
  object_key: string;
  original_filename: string;
  mime_type: string;
  size: number;
  sha256: string;
  duplicate_of_file_id: string | null;
  version_of_file_id: string | null;
  uploaded_by: string;
  uploaded_at: string;
};

export type SourceUploadLimits = {
  max_files: number;
  max_file_size: number;
  max_total_size: number;
  allowed_extensions: string[];
};

export type IngestionJobStatus =
  | "pending"
  | "running"
  | "awaiting_review"
  | "completed"
  | "failed"
  | "cancelled";

export type IngestionStepName =
  | "parse"
  | "ocr"
  | "clean"
  | "chunk"
  | "review"
  | "index";

export type ReviewStatus = "pending" | "reviewed" | "rejected" | "disputed";

export type IngestionStep = {
  name: IngestionStepName;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  attempt_count: number;
  worker_id: string | null;
  started_at: string | null;
  finished_at: string | null;
  output_ref: string | null;
  error_code: string | null;
  error_message: string | null;
  owner_worker_id: string | null;
  lease_expires_at: string | null;
  retryable: boolean;
};

export type IngestionJob = {
  id: string;
  document_id: string;
  source_file_id: string;
  status: IngestionJobStatus;
  current_step: IngestionStepName | null;
  progress_percent: number;
  steps: IngestionStep[];
  error_code: string | null;
  error_message: string | null;
  version: number;
  event_sequence: number;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};

type SourceUploadItem = {
  filename: string;
  status: "uploaded" | "failed";
  file?: SourceFileRecord;
  existing_file?: SourceFileRecord;
  error_code?: string;
  error?: string;
  ingestion_job?: IngestionJob;
  ingestion_error?: string;
};

type SourceUploadResponse = {
  success_count: number;
  failure_count: number;
  items: SourceUploadItem[];
};

export type SourceUploadTask = {
  promise: Promise<SourceUploadResult>;
  cancel: () => void;
};

export type SourceUploadResult = {
  file: SourceFileRecord;
  ingestionJob?: IngestionJob;
  ingestionError?: string;
};

export type SourceChunkSet = {
  id: string;
  source_file_id: string;
  policy: { split_version: string };
  generated_at: string;
};

export type ReviewPageTarget = {
  id: string;
  page_number: number;
  folio_label: string | null;
  generation_number: number;
  raw_text: string;
  clean_text: string;
  review_status: ReviewStatus;
  ocr_confidence: number | null;
  rotation_degrees: number;
  cleaning_change_count: number;
};

export function sourceFileContentUrl(documentId: string, fileId: string) {
  return `${getBackendBaseURL()}/api/source-documents/${encodeURIComponent(documentId)}/files/${encodeURIComponent(fileId)}/content`;
}

export type ReviewChunkTarget = {
  id: string;
  chunk_index: number;
  volume: string | null;
  item: string | null;
  raw_text: string;
  clean_text: string;
  page_start: number;
  page_end: number;
  cleaned_page_ids: string[];
  review_status: ReviewStatus;
};

export type ReviewQueue = {
  document_id: string;
  source_file_id: string;
  chunk_set_id: string;
  split_version: string;
  pages: ReviewPageTarget[];
  chunks: ReviewChunkTarget[];
};

export type ReviewDecision = {
  target_type: "page" | "chunk";
  target_id: string;
  decision: Exclude<ReviewStatus, "pending">;
  comment?: string;
};

export type ReviewRecord = ReviewDecision & {
  id: string;
  document_id: string;
  source_file_id: string;
  revision: number;
  previous_status: ReviewStatus;
  batch_id: string | null;
  reviewed_by: string;
  reviewed_at: string;
};

export type KnowledgeReleaseItem = {
  ordinal: number;
  document_id: string;
  source_file_id: string;
  chunk_set_id: string;
  chunk_id: string;
  content_sha256: string;
  cleaned_page_ids: string[];
};

export type KnowledgeRelease = {
  id: string;
  version_number: number;
  version: string;
  release_notes: string;
  scope: "public" | "internal";
  status: "preparing" | "ready" | "failed" | "active";
  failure_code: string | null;
  failure_message: string | null;
  preparation_attempts: number;
  ready_at: string | null;
  activated_at: string | null;
  manifest_sha256: string;
  items: KnowledgeReleaseItem[];
  created_by: string;
  created_at: string;
};

export type KnowledgeReleaseState = {
  active_release_id: string | null;
  active_version: string | null;
  state_version: number;
  updated_by: string | null;
  updated_at: string | null;
};

export type SourceUploadOptions = {
  duplicatePolicy?: "report" | "reference_existing" | "new_version";
  versionOfFileId?: string;
};

export class SourceUploadError extends Error {
  constructor(
    message: string,
    readonly code?: string,
    readonly existingFile?: SourceFileRecord,
  ) {
    super(message);
    this.name = "SourceUploadError";
  }
}

async function responseError(response: Response, fallback: string) {
  const payload = (await response.json().catch(() => null)) as {
    detail?: string | { message?: string };
  } | null;
  if (typeof payload?.detail === "string") return payload.detail;
  return payload?.detail?.message ?? fallback;
}

export async function listSourceDocuments(): Promise<SourceDocumentSummary[]> {
  const response = await fetch(`${getBackendBaseURL()}/api/source-documents`);
  if (!response.ok) {
    throw new Error(await responseError(response, "无法读取资料来源"));
  }
  return response.json();
}

export async function pageSourceDocuments(
  options: {
    query?: string;
    status?: SourceDocumentStatus | "all";
    page?: number;
    pageSize?: number;
    signal?: AbortSignal;
  } = {},
): Promise<SourceDocumentPage> {
  const pageSize = options.pageSize ?? 20;
  const params = new URLSearchParams({
    limit: String(pageSize),
    offset: String(Math.max(0, (options.page ?? 1) - 1) * pageSize),
  });
  if (options.query?.trim()) params.set("query", options.query.trim());
  if (options.status && options.status !== "all")
    params.set("status_filter", options.status);
  const response = await fetch(
    `${getBackendBaseURL()}/api/source-documents/page?${params}`,
    { signal: options.signal },
  );
  if (!response.ok)
    throw new Error(await responseError(response, "无法读取资料来源"));
  return response.json();
}

export async function pageSourceDocumentLibrary(
  options: {
    query?: string;
    status?: SourceDocumentStatus | "all";
    page?: number;
    pageSize?: number;
    signal?: AbortSignal;
  } = {},
): Promise<SourceDocumentLibraryPage> {
  const pageSize = options.pageSize ?? 20;
  const params = new URLSearchParams({
    limit: String(pageSize),
    offset: String(Math.max(0, (options.page ?? 1) - 1) * pageSize),
  });
  if (options.query?.trim()) params.set("query", options.query.trim());
  if (options.status && options.status !== "all")
    params.set("status_filter", options.status);
  const response = await fetch(
    `${getBackendBaseURL()}/api/source-documents/library/page?${params}`,
    { signal: options.signal },
  );
  if (!response.ok)
    throw new Error(await responseError(response, "无法读取文献库"));
  return response.json();
}

export async function updateSourceDocument(
  documentId: string,
  input: Partial<SourceDocumentCreateInput> & { status?: SourceDocumentStatus },
): Promise<SourceDocumentSummary> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/source-documents/${encodeURIComponent(documentId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
  );
  if (!response.ok)
    throw new Error(await responseError(response, "无法修改资料来源"));
  return response.json();
}

export async function createSourceDocument(
  input: SourceDocumentCreateInput,
): Promise<SourceDocumentSummary> {
  const response = await fetch(`${getBackendBaseURL()}/api/source-documents`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    throw new Error(await responseError(response, "无法登记资料来源"));
  }
  return response.json();
}

export async function listSourceFiles(
  documentId: string,
  options: { signal?: AbortSignal } = {},
): Promise<SourceFileRecord[]> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/source-documents/${encodeURIComponent(documentId)}/files`,
    { signal: options.signal },
  );
  if (!response.ok) {
    throw new Error(await responseError(response, "无法读取文献文件"));
  }
  return response.json();
}

export async function listIngestionJobs(
  documentId: string,
  fileId: string,
  options: { signal?: AbortSignal } = {},
): Promise<IngestionJob[]> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/source-documents/${encodeURIComponent(documentId)}/files/${encodeURIComponent(fileId)}/ingestion-jobs`,
    { signal: options.signal },
  );
  if (!response.ok) {
    throw new Error(await responseError(response, "无法读取入库状态"));
  }
  return response.json();
}

export async function getSourceUploadLimits(): Promise<SourceUploadLimits> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/source-documents/upload/limits`,
  );
  if (!response.ok) {
    throw new Error(await responseError(response, "无法读取上传限制"));
  }
  return response.json();
}

export function uploadSourceFile(
  documentId: string,
  file: File,
  onProgress: (percent: number) => void,
  options: SourceUploadOptions = {},
): SourceUploadTask {
  const request = new XMLHttpRequest();
  const promise = new Promise<SourceUploadResult>((resolve, reject) => {
    request.open(
      "POST",
      `${getBackendBaseURL()}/api/source-documents/${encodeURIComponent(documentId)}/files`,
    );
    request.withCredentials = true;
    const csrfToken = readCsrfCookie();
    if (csrfToken) request.setRequestHeader("X-CSRF-Token", csrfToken);

    request.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable && event.total > 0) {
        onProgress(
          Math.min(100, Math.round((event.loaded / event.total) * 100)),
        );
      }
    });
    request.addEventListener("load", () => {
      let payload: SourceUploadResponse | { detail?: string } | null = null;
      try {
        payload = JSON.parse(request.responseText) as SourceUploadResponse;
      } catch {
        payload = null;
      }
      if (request.status < 200 || request.status >= 300) {
        const detail =
          payload && "detail" in payload && typeof payload.detail === "string"
            ? payload.detail
            : "上传失败";
        reject(new Error(detail));
        return;
      }
      const uploadPayload = payload && "items" in payload ? payload : null;
      const item = uploadPayload?.items[0];
      if (!item?.file || item.status !== "uploaded") {
        reject(
          new SourceUploadError(
            item?.error ?? "上传失败",
            item?.error_code,
            item?.existing_file,
          ),
        );
        return;
      }
      onProgress(100);
      resolve({
        file: item.file,
        ingestionJob: item.ingestion_job,
        ingestionError: item.ingestion_error,
      });
    });
    request.addEventListener("error", () =>
      reject(new Error("网络错误，上传未完成")),
    );
    request.addEventListener("abort", () => reject(new Error("上传已取消")));

    const form = new FormData();
    form.append("files", file, file.name);
    form.append("duplicate_policy", options.duplicatePolicy ?? "report");
    if (options.versionOfFileId) {
      form.append("version_of_file_id", options.versionOfFileId);
    }
    request.send(form);
  });

  return {
    promise,
    cancel: () => request.abort(),
  };
}

export async function getIngestionJob(
  documentId: string,
  fileId: string,
  jobId: string,
): Promise<IngestionJob> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/source-documents/${encodeURIComponent(documentId)}/files/${encodeURIComponent(fileId)}/ingestion-jobs/${encodeURIComponent(jobId)}`,
  );
  if (!response.ok) {
    throw new Error(await responseError(response, "无法读取入库进度"));
  }
  return response.json();
}

export async function cancelIngestionJob(
  job: IngestionJob,
): Promise<IngestionJob> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/source-documents/${encodeURIComponent(job.document_id)}/files/${encodeURIComponent(job.source_file_id)}/ingestion-jobs/${encodeURIComponent(job.id)}/cancel`,
    { method: "POST" },
  );
  if (!response.ok) {
    throw new Error(await responseError(response, "无法取消入库任务"));
  }
  return response.json();
}

export async function retryIngestionStep(
  job: IngestionJob,
): Promise<IngestionJob> {
  if (!job.current_step) throw new Error("当前任务没有可重试步骤");
  const response = await fetch(
    `${getBackendBaseURL()}/api/source-documents/${encodeURIComponent(job.document_id)}/files/${encodeURIComponent(job.source_file_id)}/ingestion-jobs/${encodeURIComponent(job.id)}/steps/${encodeURIComponent(job.current_step)}/retry`,
    { method: "POST" },
  );
  if (!response.ok) {
    throw new Error(await responseError(response, "无法重试入库步骤"));
  }
  return response.json();
}

export async function listSourceChunkSets(
  documentId: string,
  fileId: string,
): Promise<SourceChunkSet[]> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/source-documents/${encodeURIComponent(documentId)}/files/${encodeURIComponent(fileId)}/chunks`,
  );
  if (!response.ok) {
    throw new Error(await responseError(response, "无法读取切分版本"));
  }
  return response.json();
}

function reviewBase(documentId: string, fileId: string) {
  return `${getBackendBaseURL()}/api/source-documents/${encodeURIComponent(documentId)}/files/${encodeURIComponent(fileId)}/review`;
}

export async function getReviewQueue(
  documentId: string,
  fileId: string,
  chunkSetId: string,
): Promise<ReviewQueue> {
  const params = new URLSearchParams({ chunk_set_id: chunkSetId });
  const response = await fetch(
    `${reviewBase(documentId, fileId)}/queue?${params.toString()}`,
  );
  if (!response.ok) {
    throw new Error(await responseError(response, "无法读取复核队列"));
  }
  return response.json();
}

export async function submitReviewDecisions(
  documentId: string,
  fileId: string,
  items: ReviewDecision[],
): Promise<ReviewRecord[]> {
  const response = await fetch(`${reviewBase(documentId, fileId)}/decisions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items }),
  });
  if (!response.ok) {
    throw new Error(await responseError(response, "无法提交复核结论"));
  }
  return response.json();
}

export async function listReviewHistory(
  documentId: string,
  fileId: string,
  targetType: "page" | "chunk",
  targetId: string,
): Promise<ReviewRecord[]> {
  const params = new URLSearchParams({
    target_type: targetType,
    target_id: targetId,
  });
  const response = await fetch(
    `${reviewBase(documentId, fileId)}/history?${params.toString()}`,
  );
  if (!response.ok) {
    throw new Error(await responseError(response, "无法读取复核历史"));
  }
  return response.json();
}

export async function finalizeReview(
  documentId: string,
  fileId: string,
  chunkSetId: string,
  ingestionJobId: string,
): Promise<IngestionJob> {
  const response = await fetch(`${reviewBase(documentId, fileId)}/finalize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chunk_set_id: chunkSetId,
      ingestion_job_id: ingestionJobId,
    }),
  });
  if (!response.ok) {
    throw new Error(await responseError(response, "复核门禁尚未通过"));
  }
  return response.json();
}

export async function listKnowledgeReleases(): Promise<KnowledgeRelease[]> {
  const response = await fetch(`${getBackendBaseURL()}/api/knowledge-releases`);
  if (!response.ok)
    throw new Error(await responseError(response, "无法读取知识版本"));
  return response.json();
}

export async function getKnowledgeReleaseState(): Promise<KnowledgeReleaseState> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/knowledge-releases/state`,
  );
  if (!response.ok)
    throw new Error(await responseError(response, "无法读取当前知识版本"));
  return response.json();
}

export async function publishKnowledgeRelease(
  chunkSetIds: string[],
  releaseNotes: string,
  expectedStateVersion: number,
): Promise<KnowledgeRelease> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/knowledge-releases`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chunk_set_ids: chunkSetIds,
        release_notes: releaseNotes,
        expected_state_version: expectedStateVersion,
        activate: true,
      }),
    },
  );
  if (!response.ok)
    throw new Error(await responseError(response, "知识版本发布失败"));
  return response.json();
}

export async function rollbackKnowledgeRelease(
  targetReleaseId: string,
  reason: string,
  expectedStateVersion: number,
): Promise<KnowledgeReleaseState> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/knowledge-releases/rollback`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target_release_id: targetReleaseId,
        reason,
        expected_state_version: expectedStateVersion,
      }),
    },
  );
  if (!response.ok)
    throw new Error(await responseError(response, "知识版本回滚失败"));
  return response.json();
}

export async function retryKnowledgeRelease(
  releaseId: string,
  expectedStateVersion: number,
): Promise<KnowledgeRelease> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/knowledge-releases/${encodeURIComponent(releaseId)}/retry`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        expected_state_version: expectedStateVersion,
        activate: true,
      }),
    },
  );
  if (!response.ok)
    throw new Error(await responseError(response, "知识版本重试失败"));
  return response.json();
}
