"use client";

import dynamic from "next/dynamic";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { type GlbAssetDescriptor } from "@/core/map/model-assets";
import {
  modelFileUrl,
  type RegisteredMapModel,
} from "@/core/map/registered-models";

import { GlbViewerSlot } from "./glb-viewer-slot";

const PlyViewer = dynamic(() => import("./ply-viewer"), {
  ssr: false,
  loading: () => <p role="status">正在准备 PLY 预览…</p>,
});

export function PointModelPreview({
  asset,
  models = [],
}: {
  asset: GlbAssetDescriptor | null;
  models?: RegisteredMapModel[];
}) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const model =
    selectedId === "original-glb"
      ? null
      : (models.find((item) => item.id === selectedId) ?? models[0]);
  const glb =
    model?.kind === "mesh"
      ? {
          id: model.id,
          title: model.title,
          src: modelFileUrl(model),
          license: "由上传者确认",
          evidenceIds: [],
          generator: "用户接入",
          sizeBytes: model.size_bytes,
        }
      : asset;
  return (
    <section aria-label="点位三维预览" className="space-y-4">
      {models.length > 0 && (
        <div className="space-y-2">
          <label className="block space-y-2 text-sm">
            <span>已接入模型</span>
            <select
              aria-label="已接入模型"
              className="bg-background min-h-11 w-full rounded-md border px-2"
              value={
                selectedId === "original-glb" ? selectedId : (model?.id ?? "")
              }
              onChange={(event) => {
                setSelectedId(event.target.value);
                setFile(null);
                if (input.current) input.current.value = "";
              }}
            >
              {models.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title} · {item.format.toUpperCase()}
                </option>
              ))}
              {asset && <option value="original-glb">原有点位模型</option>}
            </select>
          </label>
          {model && (
            <p className="text-muted-foreground text-xs">
              {model.source === "upload" ? "文件接入" : "影像重建"} ·{" "}
              {(model.size_bytes / 1024 ** 2).toFixed(1)} MiB ·{" "}
              <a
                className="text-primary underline"
                href={modelFileUrl(model, true)}
              >
                下载模型原件
              </a>
            </p>
          )}
        </div>
      )}
      <div className="space-y-2 rounded-md border p-3">
        <label className="block space-y-2 text-sm">
          <span className="font-medium">打开本地 PLY</span>
          <input
            ref={input}
            type="file"
            accept=".ply"
            className="block min-h-11 w-full min-w-0 rounded border p-2 text-xs"
            onChange={(event) => {
              const selected = event.target.files?.[0];
              if (!selected) return;
              if (!/\.ply$/i.test(selected.name)) {
                setError("请选择 .ply 文件");
                return;
              }
              if (!selected.size || selected.size > 256 * 1024 ** 2) {
                setError("请选择非空且不超过 256 MiB 的 PLY 文件");
                return;
              }
              setError("");
              setFile(selected);
            }}
          />
        </label>
        <p className="text-muted-foreground text-xs leading-5">
          支持彩色 RGB/RGBA 点云与高斯 PLY；本地文件仅在当前预览中打开。
        </p>
        {error && (
          <p role="alert" className="text-destructive text-xs">
            {error}
          </p>
        )}
        {file && (
          <div className="space-y-1">
            <p className="text-xs break-all">
              {file.name} · {(file.size / 1024 ** 2).toFixed(1)} MiB
            </p>
            <Button
              variant="outline"
              className="min-h-11"
              onClick={() => {
                setFile(null);
                if (input.current) input.current.value = "";
              }}
            >
              {asset ? "返回点位模型" : "关闭本地文件"}
            </Button>
          </div>
        )}
      </div>
      {file ? (
        <PlyViewer source={file} title={file.name} />
      ) : model && model.kind !== "mesh" ? (
        <PlyViewer
          key={model.id}
          source={modelFileUrl(model)}
          title={model.title}
        />
      ) : glb ? (
        <GlbViewerSlot asset={glb} />
      ) : (
        <p className="text-muted-foreground text-sm">
          选择已有 PLY 文件，即可在地图工作区查看三维成果。
        </p>
      )}
    </section>
  );
}
