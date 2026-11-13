export type MapPerformanceMode = "balanced" | "light";
export const MAP_PERFORMANCE_KEY = "xingxi.map.performance.v1";

export function mapPixelRatio(mode: MapPerformanceMode, deviceRatio: number) {
  const safeRatio =
    Number.isFinite(deviceRatio) && deviceRatio > 0 ? deviceRatio : 1;
  return Math.min(safeRatio, mode === "light" ? 1 : 1.5);
}

export function readMapPerformance(
  storage: Pick<Storage, "getItem">,
): MapPerformanceMode {
  try {
    return storage.getItem(MAP_PERFORMANCE_KEY) === "light"
      ? "light"
      : "balanced";
  } catch {
    return "balanced";
  }
}

export function saveMapPerformance(
  storage: Pick<Storage, "setItem">,
  mode: MapPerformanceMode,
) {
  try {
    storage.setItem(MAP_PERFORMANCE_KEY, mode);
  } catch {
    // The current session remains usable when browser storage is unavailable.
  }
}
