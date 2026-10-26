"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  createDemandRenderer,
  createRenderResources,
  observeRenderVisibility,
  previewPixelRatio,
} from "@/core/map/demand-render";
import { coloredPlyGeometry } from "@/core/map/ply";
import type { ColoredPlyData } from "@/core/map/ply-data";

type ViewerControls = {
  move: (element: HTMLDivElement) => void;
  reset: () => void;
  flip: () => void;
  size: (value: number) => void;
  background: (value: string) => void;
  alpha: (value: boolean) => void;
};

export default function PointCloudViewer({
  data,
  title,
  light = true,
}: {
  data: ColoredPlyData;
  title: string;
  light?: boolean;
}) {
  const host = useRef<HTMLDivElement>(null);
  const expandedHost = useRef<HTMLDivElement>(null);
  const runtime = useRef<ViewerControls | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [state, setState] = useState("正在准备彩色点云…");
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  const [pointSize, setPointSize] = useState(2);
  const [background, setBackground] = useState("#172422");
  const [useFileAlpha, setUseFileAlpha] = useState(false);

  useEffect(() => {
    let stopped = false;
    const resources = createRenderResources();
    resources.add(() => {
      runtime.current = null;
    });
    setReady(false);
    setFailed(false);
    setState("正在准备彩色点云…");
    setPointSize(2);
    setBackground("#172422");
    setUseFileAlpha(false);
    void (async () => {
      const [THREE, { OrbitControls }] = await Promise.all([
        import("three"),
        import("three/addons/controls/OrbitControls.js"),
      ]);
      if (stopped || !host.current) return;
      const geometry = coloredPlyGeometry(data);
      resources.add(() => geometry.dispose());
      const renderer = new THREE.WebGLRenderer({ antialias: !light });
      resources.add(() => {
        renderer.dispose();
        renderer.forceContextLoss();
        renderer.domElement.remove();
      });
      renderer.setPixelRatio(previewPixelRatio(light, devicePixelRatio));
      renderer.setClearColor("#172422");
      renderer.domElement.setAttribute("aria-label", "彩色点云三维场景");
      renderer.domElement.style.touchAction = "none";
      const material = new THREE.PointsMaterial({
        size: 2,
        sizeAttenuation: false,
        vertexColors: true,
        // Converted Gaussian opacity is not surface coverage for equal-size points.
        // Show solid RGB by default; retain Alpha as an explicit viewing option.
        transparent: false,
        alphaTest: 0,
        depthWrite: true,
      });
      resources.add(() => material.dispose());
      material.onBeforeCompile = (shader) => {
        shader.fragmentShader = shader.fragmentShader.replace(
          "#include <clipping_planes_fragment>",
          "#include <clipping_planes_fragment>\nif (length(gl_PointCoord - vec2(0.5)) > 0.5) discard;",
        );
      };
      const points = new THREE.Points(geometry, material);
      // Match the COLMAP/OOOSplat coordinate convention; users can flip Y/Z together.
      points.rotation.x = Math.PI;
      const scene = new THREE.Scene();
      scene.add(points);
      const camera = new THREE.PerspectiveCamera(50, 1, 0.001, 10000);
      const controls = new OrbitControls(camera, renderer.domElement);
      resources.add(() => controls.dispose());
      controls.enableDamping = true;
      let activeHost = host.current;
      const demand = createDemandRenderer({
        render: () => {
          const changed = controls.update();
          renderer.render(scene, camera);
          return changed;
        },
        onState: (state, frames) => {
          renderer.domElement.dataset.renderState = state;
          renderer.domElement.dataset.renderFrames = String(frames);
        },
      });
      resources.add(() => demand.dispose());
      renderer.domElement.dataset.renderPointCount = String(data.count);
      renderer.domElement.dataset.sourcePointCount = String(data.totalCount);
      renderer.domElement.dataset.pixelRatio = String(renderer.getPixelRatio());
      renderer.domElement.dataset.parseThread = "worker";
      let stopVisibility = () => {
        /* Assigned after attaching the canvas to its active host. */
      };
      controls.addEventListener("change", demand.invalidate);
      resources.add(() =>
        controls.removeEventListener("change", demand.invalidate),
      );
      resources.add(() => stopVisibility());
      const resize = () => {
        const width = activeHost.clientWidth,
          height = activeHost.clientHeight;
        if (!width || !height) return;
        renderer.setSize(width, height);
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
        demand.invalidate();
      };
      const observer = new ResizeObserver(resize);
      resources.add(() => observer.disconnect());
      const reset = () => {
        points.updateMatrixWorld(true);
        const sphere = geometry
          .boundingSphere!.clone()
          .applyMatrix4(points.matrixWorld);
        const radius = Math.max(sphere.radius, 0.001);
        const fov = Math.min(
          (camera.fov * Math.PI) / 180,
          2 * Math.atan(Math.tan((camera.fov * Math.PI) / 360) * camera.aspect),
        );
        const distance = (radius / Math.sin(fov / 2)) * 1.1;
        camera.near = Math.max(radius / 1000, 0.000001);
        camera.far = Math.max(radius * 1000, distance * 10);
        camera.position
          .copy(sphere.center)
          .add(new THREE.Vector3(0, distance * 0.1, distance));
        camera.updateProjectionMatrix();
        controls.target.copy(sphere.center);
        controls.update();
        demand.invalidate();
      };
      runtime.current = {
        move: (element) => {
          if (
            activeHost === element &&
            renderer.domElement.parentElement === element
          )
            return;
          observer.disconnect();
          stopVisibility();
          activeHost = element;
          element.appendChild(renderer.domElement);
          resize();
          reset();
          observer.observe(element);
          stopVisibility = observeRenderVisibility(element, demand.setVisible);
        },
        reset,
        flip: () => {
          points.rotation.x += Math.PI;
          reset();
        },
        size: (value) => {
          material.size = value;
          demand.invalidate();
        },
        background: (value) => {
          renderer.setClearColor(value);
          demand.invalidate();
        },
        alpha: (value) => {
          material.transparent = value;
          material.alphaTest = value ? 0.01 : 0;
          material.needsUpdate = true;
          demand.invalidate();
        },
      };
      runtime.current.move(expandedHost.current ?? host.current);
      reset();
      setState(
        `${data.count.toLocaleString("zh-CN")} / ${data.totalCount.toLocaleString("zh-CN")} 个彩色点 · ${light ? "轻量预览" : "完整精度"} · 拖动旋转 · 滚轮或双指缩放`,
      );
      setReady(true);
    })().catch((error: unknown) => {
      if (stopped) return;
      resources.dispose();
      setFailed(true);
      setState(
        error instanceof Error
          ? error.message
          : "当前设备无法预览彩色点云，请下载查看",
      );
    });
    return () => {
      stopped = true;
      resources.dispose();
    };
  }, [data, light, retry]);

  useEffect(() => {
    const element = expanded ? expandedHost.current : host.current;
    if (element) runtime.current?.move(element);
  }, [expanded]);

  const controls = (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
      <label className="inline-flex min-h-11 items-center gap-2">
        <input
          type="checkbox"
          aria-label="使用文件透明度"
          checked={useFileAlpha}
          disabled={!ready}
          onChange={(event) => {
            setUseFileAlpha(event.target.checked);
            runtime.current?.alpha(event.target.checked);
          }}
        />
        使用文件透明度
      </label>
      <Button
        variant="outline"
        className="min-h-11"
        disabled={!ready}
        onClick={() => runtime.current?.reset()}
      >
        复位视角
      </Button>
      <Button
        variant="outline"
        className="min-h-11"
        disabled={!ready}
        onClick={() => runtime.current?.flip()}
      >
        翻转上下
      </Button>
      <label className="flex min-h-11 items-center gap-2">
        <span>点大小</span>
        <input
          type="range"
          aria-label="点大小"
          min="1"
          max="8"
          step="0.5"
          value={pointSize}
          disabled={!ready}
          className="min-h-11 w-24 accent-teal-700"
          onChange={(event) => {
            const value = Number(event.target.value);
            setPointSize(value);
            runtime.current?.size(value);
          }}
        />
      </label>
      <label className="flex min-h-11 items-center gap-2">
        <span>背景</span>
        <select
          aria-label="点云背景"
          className="bg-background min-h-11 rounded border px-2"
          value={background}
          onChange={(event) => {
            setBackground(event.target.value);
            runtime.current?.background(event.target.value);
          }}
        >
          <option value="#172422">深色</option>
          <option value="#f4f1e9">浅色</option>
        </select>
      </label>
    </div>
  );

  return (
    <section aria-label="彩色点云预览" className="space-y-2">
      <Dialog open={expanded} onOpenChange={setExpanded}>
        <div hidden={expanded} className="space-y-2">
          <div
            ref={host}
            className="h-[320px] w-full overflow-hidden rounded-md bg-[#172422] [&_canvas]:block"
          />
          <p
            role={failed ? "alert" : "status"}
            className="text-muted-foreground text-xs"
          >
            {state}
          </p>
          {controls}
          <Button
            variant="outline"
            className="min-h-11"
            disabled={!ready}
            onClick={() => setExpanded(true)}
          >
            放大查看点云
          </Button>
          {failed && (
            <Button
              variant="outline"
              className="min-h-11"
              onClick={() => setRetry((value) => value + 1)}
            >
              重试预览
            </Button>
          )}
        </div>
        <DialogContent className="research-model-dialog flex h-[88dvh] w-[94vw] max-w-none flex-col gap-2 p-4 sm:max-w-[1200px]">
          <DialogTitle className="truncate pr-8">{title}</DialogTitle>
          <DialogDescription>
            彩色点云 · 拖动旋转，滚轮或双指缩放
          </DialogDescription>
          <div
            ref={(element) => {
              expandedHost.current = element;
              if (element) runtime.current?.move(element);
            }}
            className="min-h-0 w-full flex-1 overflow-hidden rounded-md bg-[#172422] [&_canvas]:block"
          />
          <p role="status" className="text-muted-foreground text-xs">
            {state}
          </p>
          {controls}
          <Button
            variant="outline"
            className="min-h-11 self-end"
            onClick={() => setExpanded(false)}
          >
            返回点位详情
          </Button>
        </DialogContent>
      </Dialog>
    </section>
  );
}
