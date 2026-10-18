"use client";

import { type ModelViewerElement } from "@google/model-viewer";
import { LoaderCircle, Maximize2, RotateCcw, Orbit } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { type GlbAssetDescriptor } from "@/core/map/model-assets";
import { cn } from "@/lib/utils";

const INITIAL_ORBIT = "90deg 75deg 105%";
const INITIAL_FIELD_OF_VIEW = "30deg";

export function ModelViewer({ asset }: { asset: GlbAssetDescriptor }) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const viewerRef = useRef<ModelViewerElement | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "failed">("loading");
  const [progress, setProgress] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const [autoRotate, setAutoRotate] = useState(false);
  const expandedHostRef = useRef<HTMLDivElement | null>(null);
  const expandedRef = useRef(false);

  useEffect(() => {
    let disposed = false;
    let viewer: ModelViewerElement | null = null;
    setState("loading");
    setProgress(0);
    setAutoRotate(false);
    const timeout = window.setTimeout(() => {
      if (!disposed) setState("failed");
    }, 120_000);

    const onLoad = () => {
      if (disposed) return;
      window.clearTimeout(timeout);
      setProgress(100);
      setState("ready");
    };
    const onError = () => {
      if (disposed) return;
      window.clearTimeout(timeout);
      setState("failed");
    };
    const onProgress = (event: Event) => {
      const total = (event as CustomEvent<{ totalProgress: number }>).detail
        ?.totalProgress;
      if (!disposed && typeof total === "number" && Number.isFinite(total)) {
        setProgress(Math.round(Math.min(1, Math.max(0, total)) * 100));
      }
    };

    void import("@google/model-viewer")
      .then(({ ModelViewerElement }) => {
        if (disposed) return;
        // Do not retain unused multi-million-triangle models in the shared cache.
        ModelViewerElement.modelCacheSize = 0;
        viewer = document.createElement("model-viewer");
        viewerRef.current = viewer;
        viewer.style.width = "100%";
        viewer.style.height = "100%";
        viewer.setAttribute("alt", asset.title);
        viewer.setAttribute("camera-controls", "");
        viewer.setAttribute("touch-action", "none");
        viewer.setAttribute("interaction-prompt", "none");
        viewer.setAttribute("loading", "eager");
        viewer.setAttribute("reveal", "auto");
        viewer.setAttribute("environment-image", "neutral");
        viewer.setAttribute("camera-orbit", INITIAL_ORBIT);
        viewer.setAttribute("field-of-view", INITIAL_FIELD_OF_VIEW);
        if (asset.poster) viewer.setAttribute("poster", asset.poster);
        viewer.addEventListener("load", onLoad);
        viewer.addEventListener("error", onError);
        viewer.addEventListener("progress", onProgress);
        const source = new URL(asset.src!, window.location.href);
        if (attempt > 0) {
          // A failed parse can stay in the viewer library cache. Retry a fresh
          // URL for the same immutable file rather than reusing that entry.
          source.searchParams.set("preview_retry", `${Date.now()}-${attempt}`);
        }
        viewer.setAttribute("src", attempt > 0 ? source.href : asset.src!);
        (expandedRef.current
          ? expandedHostRef.current
          : hostRef.current
        )?.appendChild(viewer);
      })
      .catch(onError);

    return () => {
      disposed = true;
      window.clearTimeout(timeout);
      if (viewer) {
        viewer.removeEventListener("load", onLoad);
        viewer.removeEventListener("error", onError);
        viewer.removeEventListener("progress", onProgress);
        viewer.removeAttribute("src");
        viewer.remove();
      }
      viewerRef.current = null;
    };
  }, [asset.src, asset.poster, asset.title, attempt]);

  useEffect(() => {
    expandedRef.current = expanded;
    if (!expanded && viewerRef.current && hostRef.current) {
      hostRef.current.appendChild(viewerRef.current);
    }
  }, [expanded]);

  const reset = () => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    viewer.cameraOrbit = INITIAL_ORBIT;
    viewer.cameraTarget = "auto auto auto";
    viewer.fieldOfView = INITIAL_FIELD_OF_VIEW;
    viewer.jumpCameraToGoal();
    viewer.removeAttribute("auto-rotate");
    setAutoRotate(false);
  };

  const feedback = (
    <>
      {state === "loading" && (
        <div
          role="status"
          className="bg-muted text-muted-foreground pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-3 text-sm"
        >
          <LoaderCircle className="size-6 animate-spin motion-reduce:animate-none" />
          <span>正在加载模型{progress > 0 ? ` · ${progress}%` : "…"}</span>
        </div>
      )}
      {state === "failed" && (
        <div
          role="alert"
          className="bg-muted text-muted-foreground absolute inset-0 flex flex-col items-center justify-center gap-3 px-4 text-center text-sm"
        >
          <span>模型暂时无法加载，请检查网络后重试。</span>
          <button
            type="button"
            onClick={() => setAttempt((value) => value + 1)}
            className="border-border bg-card text-primary hover:bg-accent rounded-md border px-3 py-2 text-xs font-medium"
          >
            重试加载模型
          </button>
        </div>
      )}
    </>
  );
  const controls = (
    <div className="research-model-controls flex flex-wrap items-center justify-between gap-2 py-2">
      <span className="text-muted-foreground text-[11px]">
        拖动旋转 · 滚轮/双指缩放
      </span>
      <button
        type="button"
        disabled={state !== "ready"}
        aria-pressed={autoRotate}
        onClick={() => {
          const next = !autoRotate;
          setAutoRotate(next);
          viewerRef.current?.toggleAttribute("auto-rotate", next);
        }}
        className="text-primary hover:bg-accent inline-flex min-h-10 items-center gap-1 rounded-md px-2 text-xs disabled:opacity-40"
      >
        <Orbit className="size-3.5" />
        自动旋转
      </button>
      <button
        type="button"
        onClick={reset}
        disabled={state !== "ready"}
        className="text-primary hover:bg-accent inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-1.5 text-xs disabled:opacity-40"
      >
        <RotateCcw className="size-3.5" /> 复位
      </button>
    </div>
  );

  return (
    <Dialog open={expanded} onOpenChange={setExpanded}>
      <div data-model-state={state} data-model-id={asset.id}>
        <div className={cn(expanded && "hidden")}>
          <div className="bg-muted relative h-[300px] overflow-hidden rounded-md border">
            <div ref={hostRef} className="h-full w-full" />
            {feedback}
            {state === "ready" && (
              <DialogTrigger asChild>
                <button
                  type="button"
                  aria-label="放大查看模型"
                  className="bg-card/95 text-primary hover:bg-accent absolute top-2 right-2 grid size-8 place-items-center rounded-md border shadow-sm"
                >
                  <Maximize2 className="size-4" />
                </button>
              </DialogTrigger>
            )}
          </div>
          {controls}
        </div>
        <DialogContent className="research-model-dialog flex h-[88dvh] w-[94vw] max-w-none flex-col gap-2 p-4 sm:max-w-[1200px]">
          <DialogTitle className="pr-8">{asset.title}</DialogTitle>
          <DialogDescription>
            模型预览 · 拖动旋转，滚轮或双指缩放
          </DialogDescription>
          <div className="bg-muted relative min-h-0 flex-1 overflow-hidden rounded-md border">
            <div
              ref={(host) => {
                expandedHostRef.current = host;
                if (expanded && host && viewerRef.current)
                  host.appendChild(viewerRef.current);
              }}
              className="h-full w-full"
            />
            {feedback}
          </div>
          {controls}
          <button
            type="button"
            onClick={() => setExpanded(false)}
            className="text-primary hover:bg-accent self-end rounded-md border px-3 py-2 text-xs"
          >
            返回点位详情
          </button>
        </DialogContent>
      </div>
    </Dialog>
  );
}
