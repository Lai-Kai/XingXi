"use client";

import { useEffect, useRef, useState } from "react";

import {
  createDemandRenderer,
  createRenderResources,
  observeRenderVisibility,
  previewPixelRatio,
} from "@/core/map/demand-render";

export default function GaussianViewer({
  url,
  fileBytes,
  light = true,
}: {
  url?: string;
  fileBytes?: ArrayBuffer;
  light?: boolean;
}) {
  const host = useRef<HTMLDivElement>(null);
  const frame = useRef<((subject: boolean) => void) | null>(null);
  const [state, setState] = useState("正在加载高斯模型…");
  const [retry, setRetry] = useState(0);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let stopped = false;
    const resources = createRenderResources();
    resources.add(() => {
      frame.current = null;
    });
    const controller = new AbortController();
    setFailed(false);
    setState("正在加载高斯模型…");
    void (async () => {
      const [THREE, { SparkRenderer, SplatMesh }, { OrbitControls }] =
        await Promise.all([
          import("three"),
          import("@sparkjsdev/spark"),
          import("three/addons/controls/OrbitControls.js"),
        ]);
      const element = host.current;
      if (stopped || !element) return;
      const renderer = new THREE.WebGLRenderer({ antialias: false });
      resources.add(() => {
        renderer.dispose();
        renderer.forceContextLoss();
        renderer.domElement.remove();
      });
      renderer.setPixelRatio(previewPixelRatio(light, devicePixelRatio));
      renderer.setClearColor(0x172422);
      renderer.domElement.setAttribute("aria-label", "高斯三维场景");
      element.appendChild(renderer.domElement);
      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(50, 1, 0.001, 10000);
      const controls = new OrbitControls(camera, renderer.domElement);
      resources.add(() => controls.dispose());
      controls.enableDamping = true;
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
      renderer.domElement.dataset.pixelRatio = String(renderer.getPixelRatio());
      controls.addEventListener("change", demand.invalidate);
      resources.add(() =>
        controls.removeEventListener("change", demand.invalidate),
      );
      const stopVisibility = observeRenderVisibility(
        element,
        demand.setVisible,
      );
      resources.add(stopVisibility);
      // Spark signals asynchronous initialization, sorting and LOD completions.
      // Waking onDirty avoids freezing an empty/unsorted first frame when idle.
      const spark = new SparkRenderer({ renderer, onDirty: demand.invalidate });
      resources.add(() => spark.dispose());
      scene.add(spark);
      let mesh: InstanceType<typeof SplatMesh> | null = null;
      const observer = new ResizeObserver(() => {
        const width = element.clientWidth,
          height = element.clientHeight;
        if (width && height) {
          renderer.setSize(width, height);
          camera.aspect = width / height;
          camera.updateProjectionMatrix();
          demand.invalidate();
        }
      });
      resources.add(() => observer.disconnect());
      observer.observe(element);
      // Authenticated same-origin bytes, cancellable when switching points/tabs.
      let bytes: Uint8Array;
      if (fileBytes) bytes = new Uint8Array(fileBytes);
      else {
        if (!url) throw new Error("缺少 PLY 模型来源");
        const response = await fetch(url, {
          credentials: "include",
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`模型下载失败 (${response.status})`);
        bytes = new Uint8Array(await response.arrayBuffer());
      }
      if (stopped) return;
      mesh = new SplatMesh({ fileBytes: bytes, fileName: "final.ply" });
      resources.add(() => mesh?.dispose());
      scene.add(mesh);
      await mesh.initialized;
      if (stopped) return;
      renderer.domElement.dataset.sourcePointCount = String(
        mesh.packedSplats?.numSplats ?? 0,
      );
      mesh.quaternion.set(1, 0, 0, 0);
      mesh.updateMatrixWorld(true);
      const box = mesh.getBoundingBox().applyMatrix4(mesh.matrixWorld);
      // Frame the dense center without changing or deleting any model geometry.
      // The complete bounds remain available for inspecting outliers.
      const axes: number[][] = [[], [], []];
      const packed = mesh.packedSplats;
      if (packed) {
        const stride = Math.max(1, Math.ceil(packed.numSplats / 4096));
        for (let index = 0; index < packed.numSplats; index += stride) {
          const splat = packed.getSplat(index);
          if (
            splat.opacity < 0.1 ||
            !splat.center.toArray().every(Number.isFinite)
          )
            continue;
          axes[0]!.push(splat.center.x);
          axes[1]!.push(splat.center.y);
          axes[2]!.push(splat.center.z);
        }
      }
      axes.forEach((axis) => axis.sort((a, b) => a - b));
      const focus =
        axes[0]!.length > 20
          ? new THREE.Box3(
              new THREE.Vector3(
                ...(axes.map(
                  (axis) => axis[Math.floor(axis.length * 0.05)]!,
                ) as [number, number, number]),
              ),
              new THREE.Vector3(
                ...(axes.map(
                  (axis) => axis[Math.floor(axis.length * 0.95)]!,
                ) as [number, number, number]),
              ),
            ).applyMatrix4(mesh.matrixWorld)
          : box;
      frame.current = (subject) => {
        const bounds = subject ? focus : box;
        const center = bounds.getCenter(new THREE.Vector3());
        const radius = Math.max(
          bounds.getSize(new THREE.Vector3()).length() / 2,
          0.01,
        );
        const fov = Math.min(
          (camera.fov * Math.PI) / 180,
          2 * Math.atan(Math.tan((camera.fov * Math.PI) / 360) * camera.aspect),
        );
        const distance = radius / Math.sin(fov / 2);
        camera.near = Math.max(radius / 1000, 0.0001);
        camera.far = Math.max(
          box.getSize(new THREE.Vector3()).length() * 100,
          distance * 100,
        );
        camera.position
          .copy(center)
          .add(new THREE.Vector3(0, distance * 0.12, distance));
        camera.lookAt(center);
        camera.updateProjectionMatrix();
        controls.target.copy(center);
        controls.update();
        demand.invalidate();
      };
      frame.current(true);
      demand.invalidate();
      setState(
        `${light ? "轻量分辨率预览" : "完整精度"} · 拖动旋转 · 滚轮缩放`,
      );
    })().catch((error: unknown) => {
      if (!stopped) {
        resources.dispose();
        setFailed(true);
        setState(
          error instanceof Error
            ? error.message
            : "当前设备无法预览，请下载结果查看",
        );
      }
    });
    return () => {
      stopped = true;
      controller.abort();
      resources.dispose();
    };
  }, [url, fileBytes, light, retry]);
  return (
    <section aria-label="高斯模型预览" className="space-y-2">
      <div
        ref={host}
        className="h-[320px] w-full overflow-hidden rounded-md bg-[#172422] [&_canvas]:touch-none"
      />
      <p role="status" className="text-muted-foreground text-xs">
        {state}
      </p>
      <div className="flex gap-3 text-xs">
        <button
          type="button"
          className="text-primary min-h-11 underline"
          disabled={!frame.current}
          onClick={() => frame.current?.(true)}
        >
          聚焦主体
        </button>
        <button
          type="button"
          className="text-primary min-h-11 underline"
          disabled={!frame.current}
          onClick={() => frame.current?.(false)}
        >
          完整范围
        </button>
      </div>
      {failed && (
        <button
          type="button"
          className="text-primary min-h-11 underline"
          onClick={() => setRetry((value) => value + 1)}
        >
          重试预览
        </button>
      )}
    </section>
  );
}
