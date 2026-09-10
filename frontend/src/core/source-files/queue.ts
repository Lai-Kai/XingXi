import type { IngestionJob, SourceFileRecord, SourceUploadLimits } from "./api";

export type SourceUploadQueueStatus =
  | "queued"
  | "uploading"
  | "uploaded"
  | "failed"
  | "cancelled";

export type SourceUploadQueueItem = {
  id: string;
  file: File;
  status: SourceUploadQueueStatus;
  progress: number;
  error?: string;
  uploaded?: SourceFileRecord;
  existingFile?: SourceFileRecord;
  conflictCode?: string;
  ingestionJob?: IngestionJob;
  ingestionError?: string;
};

export type SourceConflictAction = "reference_existing" | "new_version";

export function sourceConflictActions(
  code: string | undefined,
): SourceConflictAction[] {
  if (code === "duplicate_file") {
    return ["reference_existing", "new_version"];
  }
  if (code === "same_name_different_content") {
    return ["new_version"];
  }
  return [];
}

function extensionOf(filename: string) {
  const dot = filename.lastIndexOf(".");
  return dot >= 0 ? filename.slice(dot).toLowerCase() : "";
}

export function createSourceUploadQueue(
  files: File[],
  limits: SourceUploadLimits,
): SourceUploadQueueItem[] {
  const allowed = new Set(
    limits.allowed_extensions.map((value) => value.toLowerCase()),
  );
  let acceptedSize = 0;
  return files.map((file, index) => {
    let error: string | undefined;
    if (index >= limits.max_files) {
      error = `单次最多选择 ${limits.max_files} 个文件`;
    } else if (!allowed.has(extensionOf(file.name))) {
      error = "不支持该文件类型";
    } else if (file.size === 0) {
      error = "不能上传空文件";
    } else if (file.size > limits.max_file_size) {
      error = "文件大小超过单文件上限";
    } else if (acceptedSize + file.size > limits.max_total_size) {
      error = "文件总大小超过批次上限";
    } else {
      acceptedSize += file.size;
    }
    return {
      id: crypto.randomUUID(),
      file,
      status: error ? "failed" : "queued",
      progress: 0,
      error,
    };
  });
}
