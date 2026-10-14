"use client";

import dynamic from "next/dynamic";

import { type GlbAssetDescriptor } from "@/core/map/model-assets";

export { type GlbAssetDescriptor } from "@/core/map/model-assets";

const ModelViewer = dynamic(
  () => import("./model-viewer").then((module) => module.ModelViewer),
  {
    ssr: false,
    loading: () => (
      <div
        role="status"
        className="grid h-[300px] place-items-center rounded-md border bg-[#edf3f2] text-sm text-[#52686c]"
      >
        正在准备模型预览…
      </div>
    ),
  },
);

export function GlbViewerSlot({ asset }: { asset: GlbAssetDescriptor | null }) {
  if (!asset) return null;
  if (!asset.src || asset.status === "failed") {
    return (
      <div
        className="rounded-md border border-dashed p-3 text-sm"
        data-glb-state={asset.status === "failed" ? "failed" : "missing-source"}
      >
        <div className="font-medium">{asset.title}</div>
        <p className="text-muted-foreground mt-1 text-xs">
          模型暂时无法预览，景点资料仍可查看。
        </p>
      </div>
    );
  }
  return (
    <section
      className="space-y-3 text-sm"
      aria-label="三维模型预览"
      data-glb-id={asset.id}
      data-glb-src={asset.src}
      data-glb-state="available"
    >
      <h3 className="font-medium">{asset.title}</h3>
      {asset.description && (
        <p className="text-muted-foreground text-xs leading-5">
          {asset.description}
        </p>
      )}
      {asset.status === "loading" ? (
        <p role="status">正在准备模型资源…</p>
      ) : (
        <ModelViewer key={asset.id} asset={asset} />
      )}
      {asset.provenance === "speculative" && (
        <p className="rounded-md border border-[#e1d5af] bg-[#fffaf0] px-3 py-2 text-xs leading-5 text-[#755f26]">
          生成示意：模型未经实测核验，不作为现状或史实证据。
        </p>
      )}
      <details className="text-muted-foreground border-t pt-2 text-xs">
        <summary className="cursor-pointer">模型来源与许可</summary>
        <div className="mt-2 space-y-1 leading-5">
          <p>来源：{asset.generator ?? "待确认"}</p>
          <p>许可：{asset.license}</p>
          <p>证据：{asset.evidenceIds.join(", ") || "待补充"}</p>
        </div>
      </details>
    </section>
  );
}
