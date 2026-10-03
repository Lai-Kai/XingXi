import { type MapPoint } from "@/core/map/types";

export type GlbAssetDescriptor = {
  id: string;
  title: string;
  description?: string;
  src?: string;
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
    sizeBytes: 75036744,
    generator: "Tripo",
    license: "待确认",
    evidenceIds: [],
    provenance: "speculative",
  },
];

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
