import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

export type CorpusImportBatch = {
  id: string;
  corpus_root_id: string;
  manifest_sha256: string;
  status: "running" | "completed" | "failed";
  created_by: string;
  created_at: string;
  completed_at: string | null;
  item_count: number;
  page_count: number;
  quality_issue_count: number;
};

export type CorpusImportItem = {
  id: string;
  batch_id: string;
  bundle_id: string;
  document_id: string;
  source_file_id: string;
  chunk_set_id: string;
  page_count: number;
  quality_issue_count: number;
  status: "completed" | "failed";
  imported_by: string;
  imported_at: string;
  error_code: string | null;
  error_message: string | null;
};

export type CorpusQualityIssue = {
  id: string;
  import_item_id: string;
  bundle_id: string;
  source_file_id: string;
  code: string;
  severity: "warning";
  field: string;
  count: number;
  physical_page_number: number;
  folio_label: string;
  message: string;
};

async function readJson<T>(response: Response, fallback: string): Promise<T> {
  if (response.ok) return (await response.json()) as T;
  const payload = (await response.json().catch(() => null)) as {
    detail?: string | { message?: string };
  } | null;
  const detail = payload?.detail;
  throw new Error(
    typeof detail === "string" ? detail : (detail?.message ?? fallback),
  );
}

export async function listCorpusImportBatches(): Promise<CorpusImportBatch[]> {
  const response = await fetch(`${getBackendBaseURL()}/api/corpus-imports`);
  return readJson(response, "无法读取导入批次");
}

export async function listCorpusImportItems(
  batchId: string,
): Promise<CorpusImportItem[]> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/corpus-imports/${encodeURIComponent(batchId)}/items`,
  );
  return readJson(response, "无法读取导入条目");
}

export async function listCorpusQualityIssues(
  itemId: string,
  limit = 100,
  offset = 0,
): Promise<CorpusQualityIssue[]> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  const response = await fetch(
    `${getBackendBaseURL()}/api/corpus-imports/items/${encodeURIComponent(itemId)}/quality-issues?${params}`,
  );
  return readJson(response, "无法读取质量问题");
}
