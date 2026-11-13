import type { IngestionJob } from "./api";

const preparationSteps = {
  parse: "读取文献",
  ocr: "识别文字",
  clean: "整理文字",
  chunk: "整理段落",
  review: "人工复核",
  index: "准备入库",
} as const;

export function sourcePreparationStatus(job: IngestionJob): string {
  if (job.status === "awaiting_review") return "待复核";
  if (job.status === "completed") return "入库完成";
  if (job.status === "cancelled") return "入库已取消";
  const step = job.current_step
    ? (preparationSteps[job.current_step] ?? "处理")
    : "处理";
  if (job.status === "failed") return `${step}失败`;
  if (job.status === "running") return `${step}中`;
  return `待${step}`;
}

export function sourceUploadConflictMessage(code?: string): string | null {
  if (code === "duplicate_file")
    return "该文件已上传，可引用已有文件或建立新版本。";
  if (code === "same_name_different_content")
    return "已有同名文件，但内容不同，可建立新版本。";
  return null;
}

export function corpusQualityMessage(code: string): string {
  const messages: Record<string, string> = {
    raw_line_prefix_b: "原始文字的行首可能有多余字符",
    empty_clean_page: "本页整理后的文字为空",
    missing_glyph_placeholder: "存在尚未辨认的缺字",
    unicode_replacement_character: "存在无法正常显示的文字",
  };
  return messages[code] ?? "本页文字需要核对";
}
