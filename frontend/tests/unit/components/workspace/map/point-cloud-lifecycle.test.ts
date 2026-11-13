import { afterEach, expect, rs, test } from "@rstest/core";
import type * as React from "react";
import type * as Three from "three";

import { parseColoredPlyData } from "@/core/map/ply-data";

import { coloredPlyFixture } from "../../../../fixtures/map-ply";

afterEach(() => {
  rs.restoreAllMocks();
  rs.unstubAllGlobals();
  rs.resetModules();
  rs.doUnmock("react");
  rs.doUnmock("three");
  rs.doUnmock("three/addons/controls/OrbitControls.js");
  rs.doUnmock("@sparkjsdev/spark");
});

async function mount(gaussian = false) {
  const actual = await rs.importActual<typeof Three>("three");
  const react = await rs.importActual<typeof React>("react");
  const effects: Array<() => (() => void) | void> = [],
    refs: Array<{ current: unknown }> = [];
  const frames = new Map<number, FrameRequestCallback>();
  let nextFrame = 0;
  const canvas = {
    dataset: {} as Record<string, string>,
    style: {},
    parentElement: null as unknown,
    setAttribute: rs.fn(),
    remove: rs.fn(),
  };
  const host = {
    clientWidth: 400,
    clientHeight: 320,
    appendChild: rs.fn(() => {
      canvas.parentElement = host;
    }),
  };
  const render = rs.fn(),
    rendererDispose = rs.fn(),
    contextLoss = rs.fn(),
    controlsDispose = rs.fn();
  const disconnect = rs.fn();
  const geometryDispose = rs.spyOn(actual.BufferGeometry.prototype, "dispose");
  const materialDispose = rs.spyOn(actual.Material.prototype, "dispose");
  const construct = rs.fn();
  const sparkDispose = rs.fn(),
    meshDispose = rs.fn();
  let resolveMesh!: () => void,
    dirty = () => {
      /* Assigned by Spark. */
    };
  const initialized = new Promise<void>((resolve) => {
    resolveMesh = resolve;
  });
  rs.stubGlobal("devicePixelRatio", 3);
  rs.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
    frames.set(++nextFrame, callback);
    return nextFrame;
  });
  rs.stubGlobal("cancelAnimationFrame", (id: number) => frames.delete(id));
  rs.stubGlobal("document", {
    hidden: false,
    addEventListener: rs.fn(),
    removeEventListener: rs.fn(),
  });
  rs.stubGlobal("IntersectionObserver", undefined);
  rs.stubGlobal(
    "ResizeObserver",
    class {
      observe = rs.fn();
      disconnect = disconnect;
    },
  );
  rs.doMock("react", () => ({
    ...react,
    useRef: (current: unknown) => {
      const ref = { current };
      refs.push(ref);
      return ref;
    },
    useState: (value: unknown) => [value, rs.fn()],
    useEffect: (effect: () => (() => void) | void) => effects.push(effect),
  }));
  rs.doMock("three", () => ({
    ...actual,
    WebGLRenderer: class {
      constructor() {
        construct();
      }
      domElement = canvas;
      setPixelRatio = rs.fn();
      getPixelRatio = () => 1.25;
      setClearColor = rs.fn();
      setSize = rs.fn();
      render = render;
      dispose = rendererDispose;
      forceContextLoss = contextLoss;
    },
  }));
  rs.doMock("three/addons/controls/OrbitControls.js", () => ({
    OrbitControls: class {
      target = new actual.Vector3();
      enableDamping = false;
      update = () => false;
      addEventListener = rs.fn();
      removeEventListener = rs.fn();
      dispose = controlsDispose;
    },
  }));
  rs.doMock("@sparkjsdev/spark", () => ({
    SparkRenderer: class extends actual.Object3D {
      constructor(options: { onDirty: () => void }) {
        super();
        dirty = options.onDirty;
      }
      dispose = sparkDispose;
    },
    SplatMesh: class extends actual.Object3D {
      initialized = initialized;
      packedSplats = {
        numSplats: 8,
        getSplat: () => ({ opacity: 1, center: new actual.Vector3() }),
      };
      getBoundingBox = () =>
        new actual.Box3(
          new actual.Vector3(-1, -1, -1),
          new actual.Vector3(1, 1, 1),
        );
      dispose = meshDispose;
    },
  }));
  if (gaussian) {
    const { default: Viewer } =
      await import("@/components/workspace/map/gaussian-viewer");
    Viewer({ fileBytes: new ArrayBuffer(0), light: true });
  } else {
    const { default: Viewer } =
      await import("@/components/workspace/map/point-cloud-viewer");
    Viewer({
      data: parseColoredPlyData(coloredPlyFixture(100).buffer, 10),
      title: "软件夹具",
      light: true,
    });
  }
  refs[0]!.current = host;
  const cleanups = effects.map((effect) => effect());
  return {
    canvas,
    frames,
    render,
    construct,
    rendererDispose,
    contextLoss,
    controlsDispose,
    geometryDispose,
    materialDispose,
    disconnect,
    sparkDispose,
    meshDispose,
    initializeMesh: async () => {
      resolveMesh();
      await new Promise((resolve) => setTimeout(resolve, 0));
    },
    dirty: () => dirty(),
    cleanup: () => cleanups.forEach((cleanup) => cleanup?.()),
    ready: async () => {
      for (let index = 0; index < 20 && !construct.mock.calls.length; index++)
        await new Promise((resolve) => setTimeout(resolve, 0));
    },
  };
}

test("a point preview reaches idle and unmount releases WebGL, geometry, controls and observers", async () => {
  const app = await mount();
  await app.ready();
  expect(app.construct).toHaveBeenCalledTimes(1);
  expect(app.canvas.dataset.renderPointCount).toBe("10");
  expect(app.canvas.dataset.sourcePointCount).toBe("100");
  const [id, callback] = app.frames.entries().next().value!;
  app.frames.delete(id);
  callback(0);
  expect(app.render).toHaveBeenCalledTimes(1);
  expect(app.canvas.dataset.renderState).toBe("idle");
  app.cleanup();
  expect(app.frames.size).toBe(0);
  expect(app.rendererDispose).toHaveBeenCalledTimes(1);
  expect(app.contextLoss).toHaveBeenCalledTimes(1);
  expect(app.controlsDispose).toHaveBeenCalledTimes(1);
  expect(app.geometryDispose).toHaveBeenCalledTimes(1);
  expect(app.materialDispose).toHaveBeenCalledTimes(1);
  expect(app.canvas.remove).toHaveBeenCalledTimes(1);
  expect(app.disconnect).toHaveBeenCalled();
});

test("unmount while dynamic imports are pending never opens a stale WebGL context", async () => {
  const app = await mount();
  app.cleanup();
  await app.ready();
  expect(app.construct).not.toHaveBeenCalled();
  expect(app.frames.size).toBe(0);
});

test("Spark asynchronous initialization and sorting wake an idle viewer and disposal ignores late callbacks", async () => {
  const app = await mount(true);
  await app.ready();
  const tick = () => {
    const [id, callback] = app.frames.entries().next().value!;
    app.frames.delete(id);
    callback(0);
  };
  tick();
  expect(app.canvas.dataset.renderState).toBe("idle");
  await app.initializeMesh();
  expect(app.frames.size).toBe(1);
  tick();
  app.dirty();
  app.dirty();
  expect(app.frames.size).toBe(1);
  tick();
  expect(app.render).toHaveBeenCalledTimes(3);
  app.cleanup();
  app.dirty();
  expect(app.frames.size).toBe(0);
  expect(app.sparkDispose).toHaveBeenCalledTimes(1);
  expect(app.meshDispose).toHaveBeenCalledTimes(1);
  expect(app.rendererDispose).toHaveBeenCalledTimes(1);
  expect(app.contextLoss).toHaveBeenCalledTimes(1);
});

test("unmount while Spark initializes releases its mesh and cannot restore a stale frame", async () => {
  const app = await mount(true);
  await app.ready();
  app.cleanup();
  await app.initializeMesh();
  app.dirty();
  expect(app.frames.size).toBe(0);
  expect(app.meshDispose).toHaveBeenCalledTimes(1);
  expect(app.sparkDispose).toHaveBeenCalledTimes(1);
});
