"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

import {
  inspectPly,
  LIGHT_PLY_POINT_BUDGET,
  MAX_PLY_PREVIEW_BYTES,
  type ColoredPlyData,
} from "@/core/map/ply-data";
import { parsePlyInWorker } from "@/core/map/ply-worker-client";

const GaussianViewer = dynamic(() => import("./gaussian-viewer"), {
  ssr: false,
});
const PointCloudViewer = dynamic(() => import("./point-cloud-viewer"), {
  ssr: false,
});
type Loaded = { source: string | File; mode: boolean } & (
  | { kind: "gaussian"; bytes: ArrayBuffer }
  | { kind: "point_cloud"; data: ColoredPlyData }
);

export default function PlyViewer({
  source,
  title,
}: {
  source: string | File;
  title: string;
}) {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [light, setLight] = useState(true);
  const [phase, setPhase] = useState("正在读取 PLY 模型…");
  useEffect(() => {
    const controller = new AbortController();
    setLoaded(null);
    setError("");
    setPhase("正在读取 PLY 模型…");
    void (async () => {
      let bytes: ArrayBuffer;
      if (typeof source === "string") {
        const response = await fetch(source, {
          credentials: "include",
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`模型下载失败 (${response.status})`);
        if (
          Number(response.headers.get("content-length")) > MAX_PLY_PREVIEW_BYTES
        )
          throw new Error("PLY 超过浏览器预览上限（256 MiB），请下载查看");
        bytes = await response.arrayBuffer();
      } else {
        if (source.size > MAX_PLY_PREVIEW_BYTES)
          throw new Error(
            "PLY 超过浏览器预览上限（256 MiB），请使用桌面查看器",
          );
        bytes = await source.arrayBuffer();
      }
      if (controller.signal.aborted) return;
      const { kind } = inspectPly(bytes);
      if (kind === "gaussian") setLoaded({ source, mode: light, kind, bytes });
      else {
        setPhase("正在后台解析彩色点云…");
        // Transfer bytes, do not retain an extra source copy on the UI thread.
        // Switching fidelity reads source again; the downloadable file is unchanged.
        const data = await parsePlyInWorker(
          bytes,
          light ? LIGHT_PLY_POINT_BUDGET : 5_000_000,
          controller.signal,
        );
        if (!controller.signal.aborted)
          setLoaded({ source, mode: light, kind, data });
      }
    })().catch((failure: unknown) => {
      if (!controller.signal.aborted)
        setError(failure instanceof Error ? failure.message : "PLY 加载失败");
    });
    return () => controller.abort();
  }, [source, retry, light]);
  const current =
    loaded?.source === source && loaded.mode === light ? loaded : null;
  return (
    <div
      className="space-y-2"
      data-preview-mode={light ? "light" : "full"}
      data-parse-thread={current?.kind === "point_cloud" ? "worker" : undefined}
    >
      <label className="flex min-h-11 items-center gap-2 text-xs">
        <span>预览精度</span>
        <select
          aria-label="PLY 预览精度"
          className="bg-background min-h-11 rounded border px-2"
          value={light ? "light" : "full"}
          onChange={(event) => setLight(event.target.value === "light")}
        >
          <option value="light">轻量预览</option>
          <option value="full">完整精度</option>
        </select>
        <span className="text-muted-foreground">
          仅影响预览，原模型可完整下载
        </span>
      </label>
      {error ? (
        <div role="alert" className="space-y-2 rounded border p-3 text-sm">
          <p>{error}</p>
          <button
            type="button"
            className="text-primary min-h-11 underline"
            onClick={() => setRetry((value) => value + 1)}
          >
            重试预览
          </button>
        </div>
      ) : !current ? (
        <p role="status" className="text-muted-foreground py-3 text-sm">
          {phase}
        </p>
      ) : current.kind === "gaussian" ? (
        <GaussianViewer fileBytes={current.bytes} light={light} />
      ) : (
        <PointCloudViewer data={current.data} title={title} light={light} />
      )}
    </div>
  );
}
