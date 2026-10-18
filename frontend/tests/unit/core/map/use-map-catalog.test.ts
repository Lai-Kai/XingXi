import { afterEach, expect, rs, test } from "@rstest/core";

import { type MapCatalog, type MapPoint } from "@/core/map/types";

const catalog: MapCatalog = {
  updatedAt: "release-1",
  dataNotice: "已发布资料",
  points: [],
  layers: [],
  events: [],
  relations: [],
  trajectories: [],
  routes: [],
};
const customPoint = {
  id: "custom-point-1",
  entityId: "custom-place-1",
  recordKind: "custom",
} as MapPoint;

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}

async function mount(
  loadCustomPoints: (signal?: AbortSignal) => Promise<MapPoint[]>,
  loadCatalog: (signal?: AbortSignal) => Promise<MapCatalog> = async () =>
    catalog,
) {
  let slot = 0;
  const values: unknown[] = [];
  const effects = new Map<number, { deps: unknown[]; cleanup?: () => void }>();
  const pendingEffects: Array<() => void> = [];
  const fetchCatalog = rs.fn(loadCatalog);
  const fetchPoints = rs.fn(loadCustomPoints);
  rs.resetModules();
  rs.doMock("react", () => ({
    useState: (initial: unknown) => {
      const index = slot++;
      if (!(index in values))
        values[index] = typeof initial === "function" ? initial() : initial;
      return [
        values[index],
        (value: unknown) => {
          values[index] =
            typeof value === "function" ? value(values[index]) : value;
        },
      ];
    },
    useMemo: (compute: () => unknown) => compute(),
    useCallback: (callback: unknown) => callback,
    useEffect: (effect: () => () => void, deps: unknown[]) => {
      const index = slot++;
      const previous = effects.get(index);
      if (
        !previous ||
        deps.some((dep, i) => !Object.is(dep, previous.deps[i]))
      ) {
        pendingEffects.push(() => {
          previous?.cleanup?.();
          effects.set(index, { deps, cleanup: effect() });
        });
      }
    },
  }));
  rs.doMock("@/core/map/api", () => ({
    readCachedMapCatalog: () => null,
    fetchMapCatalog: fetchCatalog,
    fetchCustomMapPoints: fetchPoints,
  }));
  const { useMapCatalog: invokeCatalog } =
    await import("@/core/map/use-map-catalog");
  const render = () => {
    slot = 0;
    const result = invokeCatalog();
    pendingEffects.splice(0).forEach((effect) => effect());
    return result;
  };
  render();
  return {
    render,
    fetchCatalog,
    fetchPoints,
    async flush() {
      await new Promise((resolve) => setTimeout(resolve, 0));
      return render();
    },
    unmount() {
      effects.forEach((effect) => effect.cleanup?.());
    },
  };
}

afterEach(() => {
  rs.doUnmock("react");
  rs.doUnmock("@/core/map/api");
  rs.resetModules();
});

test("a missing custom-points endpoint leaves the published map visible", async () => {
  const page = await mount(async () => {
    throw new Error("自建点位暂时无法加载");
  });
  const state = await page.flush();
  expect(state.catalog).toEqual(catalog);
  expect(state.error).toBeNull();
  expect(state.customPointsError).toBe("自建点位暂时无法加载");
  page.unmount();
});

test("a slow custom-points request does not delay the map", async () => {
  const pending = deferred<MapPoint[]>();
  const page = await mount(() => pending.promise);
  expect((await page.flush()).catalog).toEqual(catalog);
  pending.resolve([customPoint]);
  expect((await page.flush()).catalog?.points).toEqual([customPoint]);
  page.unmount();
});

test("retrying custom points recovers them without fetching the catalog again", async () => {
  let attempts = 0;
  const page = await mount(async () => {
    if (++attempts === 1) throw new Error("HTTP 404");
    return [customPoint];
  });
  const failed = await page.flush();
  failed.retryCustomPoints();
  page.render();
  const recovered = await page.flush();
  expect(recovered.customPointsError).toBeNull();
  expect(recovered.catalog?.points).toEqual([customPoint]);
  expect(recovered.reloadKey).toBe(failed.reloadKey);
  expect(page.fetchCatalog).toHaveBeenCalledTimes(1);
  expect(page.fetchPoints).toHaveBeenCalledTimes(2);
  page.unmount();
});

test("a catalog failure stays fatal even when custom points load", async () => {
  const page = await mount(
    async () => [customPoint],
    async () => {
      throw new Error("无法读取古舆地图资料");
    },
  );
  const failed = await page.flush();
  expect(failed.catalog).toBeNull();
  expect(failed.error).toBe("无法读取古舆地图资料");
  expect(failed.customPointsError).toBeNull();
  page.unmount();
});

test("creating a point during a slow list request preserves it without duplicates", async () => {
  const pending = deferred<MapPoint[]>();
  const page = await mount(() => pending.promise);
  const loaded = await page.flush();
  loaded.addCustomPoint(customPoint);
  pending.resolve([]);
  expect((await page.flush()).catalog?.points).toEqual([customPoint]);
  loaded.addCustomPoint(customPoint);
  expect(page.render().catalog?.points).toEqual([customPoint]);
  page.unmount();
});

test("a failed custom-points retry retains previously loaded custom points", async () => {
  let attempts = 0;
  const page = await mount(async () => {
    if (++attempts > 1) throw new Error("offline");
    return [customPoint];
  });
  (await page.flush()).retryCustomPoints();
  page.render();
  const failed = await page.flush();
  expect(failed.catalog?.points).toEqual([customPoint]);
  expect(failed.error).toBeNull();
  expect(failed.customPointsError).toBe("offline");
  page.unmount();
});

test("an aborted request cannot replace a newer custom-points result", async () => {
  const pending = deferred<MapPoint[]>();
  let attempts = 0;
  const page = await mount(async () =>
    ++attempts === 1 ? pending.promise : [customPoint],
  );
  page.render().retryCustomPoints();
  page.render();
  expect((await page.flush()).catalog?.points).toEqual([customPoint]);
  pending.resolve([]);
  expect((await page.flush()).catalog?.points).toEqual([customPoint]);
  expect(page.fetchPoints.mock.calls[0]?.[0]?.aborted).toBe(true);
  page.unmount();
});
