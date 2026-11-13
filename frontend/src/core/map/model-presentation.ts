import { type GlbAssetDescriptor } from "@/core/map/model-assets";

const stages: Record<string, string> = {
  starting: "准备重建",
  preparing: "准备素材与拍摄视角",
  starting_flux: "准备图片处理",
  resuming: "恢复已完成进度",
  preparing_frames: "准备原始图片",
  original_cameras: "还原拍摄视角",
  preprocessing: "主体提取与背景整理",
  extracting: "提取视频画面",
  frames: "提取视频画面",
  features: "分析画面特征",
  matching: "匹配拍摄视角",
  reconstruction: "还原拍摄视角",
  training: "构建三维场景",
  brush: "构建三维场景",
  completed: "已完成",
  transferring: "传送素材",
  cancelled: "已取消",
  failed: "处理失败",
};

export function reconstructionStageLabel(stage: string): string {
  return stages[stage.toLowerCase()] ?? "正在处理";
}

/** Keep arbitrary worker messages, paths and implementation names out of the UI. */
export function modelErrorMessage(
  failure: unknown,
  fallback = "处理未完成，请稍后重试。",
  source: "request" | "worker" = "request",
): string {
  const message =
    failure instanceof Error
      ? failure.message
      : typeof failure === "string"
        ? failure
        : "";
  const serviceAccess =
    "处理服务无法访问所需资源，请联系管理员修复服务端权限后重试。";
  if (/Errno\s*13|PermissionError|\bEACCES\b/i.test(message))
    return serviceAccess;
  if (/permission denied/i.test(message) && !/\b403\b/i.test(message))
    return serviceAccess;
  if (/csrf/i.test(message))
    return source === "worker"
      ? serviceAccess
      : "登录状态已更新，请刷新页面后重试。";
  if (
    /\b401\b|未登录|请先登录|unauthenticated|not authenticated/i.test(message)
  )
    return source === "worker" ? serviceAccess : "请先登录后再操作。";
  if (/\b403\b|管理员|权限|forbidden|permission denied/i.test(message))
    return source === "worker"
      ? serviceAccess
      : "当前账号无权执行此操作，请联系管理员。";
  if (/显存|20480|20\s*GiB|GPU|CUDA|out of memory|VRAM/i.test(message))
    return "当前暂时无法处理，请稍后重试。";
  if (/磁盘|空间不足|disk space|no space left|配额|quota/i.test(message))
    return "存储空间不足，请联系管理员处理后重试。";
  if (/尚未配置|未配置|not configured|disabled/i.test(message))
    return "当前功能暂不可用，请联系管理员。";
  if (/host key|fingerprint|主机指纹|可信主机/i.test(message))
    return "暂时无法连接，请联系管理员。";
  if (
    /连接|网络|SSH|SFTP|timed? ?out|ECONN|network|fetch failed/i.test(message)
  )
    return "连接暂时中断，请稍后重试。";
  if (/PLY 文件头/i.test(message))
    return "模型文件无法读取，请选择完整有效的文件。";
  if (/超过.*(?:上限|MiB)|too large|\b413\b/i.test(message))
    return "文件超过大小限制，请压缩素材或下载后使用本地查看器。";
  if (/PLY|GLB/i.test(message))
    return "模型文件无法读取，请检查文件格式与完整性后重试。";
  if (/素材|图片|图像|照片|视频|文件/i.test(message))
    return "素材不符合处理要求，请检查格式、数量和大小后重试。";
  return fallback;
}

export function modelSourceLabel(
  asset: Pick<GlbAssetDescriptor, "generator" | "provenance">,
): string {
  if (asset.generator === "用户接入") return "用户接入";
  if (asset.provenance === "surveyed") return "实测资料";
  if (asset.provenance === "reconstructed") return "影像重建";
  if (asset.provenance === "speculative") return "生成示意";
  return asset.generator ? "三维素材" : "待确认";
}

/** Retain source and review caveats while translating storage terminology. */
export function mapDataNotice(notice: string): string {
  return notice
    .replace(/（internal）/g, "（内部工作版本）")
    .replace(/（public）/g, "（公开版本）")
    .replace(/\s*active 知识版本/g, "正在使用的资料版本");
}
