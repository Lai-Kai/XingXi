"use client";

/**
 * Stage 59: controlled interface for future GLB 3D assets.
 * Does not ship a full custom 3D engine; host page can later mount
 * model-viewer / three.js / ogl when authorized models exist.
 */
export type GlbAssetDescriptor = {
  id: string;
  title: string;
  src?: string;
  poster?: string;
  license: string;
  evidenceIds: string[];
  sizeBytes?: number;
  provenance?: "surveyed" | "reconstructed" | "speculative";
  status?: "ready" | "loading" | "failed";
};

export function GlbViewerSlot({ asset }: { asset: GlbAssetDescriptor | null }) {
  if (!asset) return null;
  const status = asset.status ?? "ready";
  const speculative = asset.provenance === "speculative";
  if (!asset.src || status === "failed") {
    return (
      <div
        className="rounded-md border border-dashed p-3 text-sm"
        data-glb-state={status === "failed" ? "failed" : "missing-source"}
      >
        <div className="font-medium">{asset.title}</div>
        <p className="text-muted-foreground mt-1 text-xs">
          {status === "failed"
            ? "三维模型加载失败，当前仅保留资产记录。"
            : "三维模型地址缺失，无法加载预览。"}
        </p>
      </div>
    );
  }
  if (status === "loading") {
    return (
      <div className="rounded-md border p-3 text-sm" data-glb-state="loading">
        <div className="font-medium">{asset.title}</div>
        <p className="text-muted-foreground mt-1 text-xs">
          正在加载授权三维模型…
        </p>
      </div>
    );
  }
  return (
    <div
      className="rounded-md border p-3 text-sm"
      data-glb-id={asset.id}
      data-glb-src={asset.src}
      data-glb-state="ready"
    >
      <div className="font-medium">{asset.title}</div>
      <div className="text-muted-foreground mt-1 text-xs">
        许可：{asset.license}
      </div>
      <div className="text-muted-foreground mt-1 text-xs break-all">
        资源：{asset.src}
      </div>
      <div className="text-muted-foreground mt-1 text-xs">
        证据：{asset.evidenceIds.join(", ") || "无"}
      </div>
      {typeof asset.sizeBytes === "number" && (
        <div className="text-muted-foreground mt-1 text-xs">
          文件大小：{(asset.sizeBytes / 1024 / 1024).toFixed(1)} MB
        </div>
      )}
      {speculative && (
        <div className="mt-2 rounded bg-amber-50 px-2 py-1 text-xs text-amber-900">
          推测复原：此模型不是实测外观，不可作为现状或史实证据。
        </div>
      )}
      <p className="text-muted-foreground mt-2 text-xs leading-5">
        三维查看器插槽已就绪。正式环境可挂载 model-viewer / three.js / ogl，
        禁止在无授权模型时伪造历史外观。
      </p>
    </div>
  );
}
