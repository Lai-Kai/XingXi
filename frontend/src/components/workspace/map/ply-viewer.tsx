"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

import {
  inspectPly,
  MAX_PLY_PREVIEW_BYTES,
  type PlyKind,
} from "@/core/map/ply";

const GaussianViewer = dynamic(() => import("./gaussian-viewer"), {
  ssr: false,
});
const PointCloudViewer = dynamic(() => import("./point-cloud-viewer"), {
  ssr: false,
});

export default function PlyViewer({
  source,
  title,
}: {
  source: string | File;
  title: string;
}) {
  const [loaded, setLoaded] = useState<{
    source: string | File;
    bytes: ArrayBuffer;
    kind: PlyKind;
  } | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoaded(null);
    setError("");
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
      if (bytes.byteLength > MAX_PLY_PREVIEW_BYTES)
        throw new Error("PLY 超过浏览器预览上限（256 MiB）");
      const { kind } = inspectPly(bytes);
      setLoaded({ source, bytes, kind });
    })().catch((failure: unknown) => {
      if (!controller.signal.aborted)
        setError(failure instanceof Error ? failure.message : "PLY 加载失败");
    });
    return () => controller.abort();
  }, [source, retry]);
  if (error)
    return (
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
    );
  if (loaded?.source !== source)
    return (
      <p role="status" className="text-muted-foreground py-3 text-sm">
        正在读取 PLY 模型…
      </p>
    );
  return loaded.kind === "gaussian" ? (
    <GaussianViewer fileBytes={loaded.bytes} />
  ) : (
    <PointCloudViewer bytes={loaded.bytes} title={title} />
  );
}
