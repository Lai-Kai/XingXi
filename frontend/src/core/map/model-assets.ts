import { type MapPoint } from "@/core/map/types";

export type GlbAssetDescriptor = {
  id: string;
  title: string;
  description?: string;
  src?: string;
  previewSrc?: string;
  previewSizeBytes?: number;
  poster?: string;
  generator?: string;
  license: string;
  evidenceIds: string[];
  sizeBytes?: number;
  provenance?: "surveyed" | "reconstructed" | "speculative";
  status?: "ready" | "loading" | "failed";
};

export type MapModelAsset = GlbAssetDescriptor & {
  pointId: string;
  entityId: string;
};

// These are actual supplied files, independent of the historical catalog.
export const MAP_MODEL_ASSETS: readonly MapModelAsset[] = [
  {
    id: "model-mudu-gate-v1",
    pointId: "pt-mudu-old-town",
    entityId: "entity-place-mudu-old-town",
    title: "木渎古镇 · 大门模型",
    description: "古镇入口示意，关联到木渎古镇点位；具体门址待核实。",
    src: "/models/mudu-gate/v1/model.3966d61b08b7.glb",
    previewSrc: "/models/mudu-gate/v1/preview.9cf1b0ace04a.glb",
    previewSizeBytes: 1263212,
    sizeBytes: 20577288,
    generator: "Tripo",
    license: "待确认",
    evidenceIds: [],
    provenance: "speculative",
  },
  {
    id: "model-hongyin-v1",
    pointId: "pt-hongyin",
    entityId: "entity-garden-hongyin",
    title: "虹饮山房 · 模型预览",
    description: "根据照片生成的建筑示意，不表示完整园林。",
    src: "/models/hongyin/v1/model.af8089412860.glb",
    previewSrc: "/models/hongyin/v1/preview.630df9ef7231.glb",
    previewSizeBytes: 3411684,
    sizeBytes: 59741080,
    generator: "Tripo",
    license: "待确认",
    evidenceIds: [],
    provenance: "speculative",
  },
  {
    id: "model-gusong-tree-v1",
    pointId: "pt-gusong-garden",
    entityId: "entity-garden-gusong",
    title: "古松园 · 古松示意",
    description: "模型对象为古松，不表示整个古松园。",
    src: "/models/gusong-tree/v1/model.59f2b1689b0f.glb",
    previewSrc: "/models/gusong-tree/v1/preview.343e015c347e.glb",
    previewSizeBytes: 3862136,
    sizeBytes: 71633044,
    generator: "Tripo",
    license: "待确认",
    evidenceIds: [],
    provenance: "speculative",
  },
  {
    id: "model-bangyan-v1",
    pointId: "pt-bangyan-mansion",
    entityId: "entity-residence-bangyan",
    title: "榜眼府第 · 模型预览",
    description: "根据照片生成的示意，具体建筑范围待核实。",
    src: "/models/bangyan/v1/model.c6345f1a451d.glb",
    previewSrc: "/models/bangyan/v1/preview.3a1b0f52d3fc.glb",
    previewSizeBytes: 5639684,
    sizeBytes: 65870372,
    generator: "Tripo",
    license: "待确认",
    evidenceIds: [],
    provenance: "speculative",
  },
  {
    id: "model-mingyue-v1",
    pointId: "pt-mingyue-temple",
    entityId: "entity-temple-mingyue",
    title: "明月古寺 · 模型预览",
    description: "根据照片生成的示意，不表示完整寺院。",
    src: "/models/mingyue/v1/model.b2c499e22f05.glb",
    previewSrc: "/models/mingyue/v1/preview.8a3168870452.glb",
    previewSizeBytes: 2531800,
    sizeBytes: 58305884,
    generator: "Tripo",
    license: "待确认",
    evidenceIds: [],
    provenance: "speculative",
  },
  {
    id: "model-lingyan-gate-v1",
    pointId: "pt-lingyan-temple",
    entityId: "entity-temple-lingyan",
    title: "灵岩山寺 · 山门模型",
    description: "模型对象为山门，不表示整个灵岩山寺。",
    src: "/models/lingyan-gate/v1/model.00f2396c74d0.glb",
    previewSrc: "/models/lingyan-gate/v1/preview.517ce2299ead.glb",
    previewSizeBytes: 1098512,
    sizeBytes: 67757752,
    generator: "Tripo",
    license: "待确认",
    evidenceIds: [],
    provenance: "speculative",
  },
  {
    id: "model-yongan-bridge-v1",
    pointId: "pt-yongan-bridge",
    entityId: "entity-bridge-yongan",
    title: "永安桥 · 模型预览",
    description: "桥梁生成示意；地图上的位置仍为近似定位，待实地核实。",
    src: "/models/yongan-bridge/v1/model.39ae9c010f74.glb",
    previewSrc: "/models/yongan-bridge/v1/preview.fd3b7fc4b565.glb",
    previewSizeBytes: 6141388,
    sizeBytes: 75036744,
    generator: "Tripo",
    license: "待确认",
    evidenceIds: [],
    provenance: "speculative",
  },
];

const BYTES_PER_MEBIBYTE = 1024 * 1024;

/**
 * Human-readable size of a supplied GLB, e.g. `68.3MB`. Returns null when the
 * descriptor carries no usable size, so callers can fall back to the bare label.
 */
export function formatModelAssetSize(sizeBytes?: number): string | null {
  if (
    typeof sizeBytes !== "number" ||
    !Number.isFinite(sizeBytes) ||
    sizeBytes <= 0
  ) {
    return null;
  }
  return `${(sizeBytes / BYTES_PER_MEBIBYTE).toFixed(1)}MB`;
}

export function getPointModelAsset(
  point: Pick<MapPoint, "id" | "entityId" | "recordKind"> | null | undefined,
): MapModelAsset | null {
  if (point?.recordKind !== "reference") return null;
  return (
    MAP_MODEL_ASSETS.find(
      (asset) =>
        asset.pointId === point.id && asset.entityId === point.entityId,
    ) ?? null
  );
}
