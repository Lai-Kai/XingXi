"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  fetchCustomMapPoints,
  fetchMapCatalog,
  readCachedMapCatalog,
} from "./api";
import { type MapCatalog, type MapPoint } from "./types";

export function useMapCatalog() {
  const [baseCatalog, setBaseCatalog] = useState<MapCatalog | null>(
    readCachedMapCatalog,
  );
  const [customPoints, setCustomPoints] = useState<MapPoint[]>([]);
  const [createdPoints, setCreatedPoints] = useState<MapPoint[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [customPointsError, setCustomPointsError] = useState<string | null>(
    null,
  );
  const [reloadKey, setReloadKey] = useState(0);
  const [customPointsReload, setCustomPointsReload] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    void fetchMapCatalog(controller.signal, { force: reloadKey > 0 })
      .then((nextCatalog) => {
        if (controller.signal.aborted) return;
        setBaseCatalog(nextCatalog);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "无法读取地图资料");
      });
    return () => controller.abort();
  }, [reloadKey]);

  useEffect(() => {
    const controller = new AbortController();
    setCustomPointsError(null);
    void fetchCustomMapPoints(controller.signal)
      .then((points) => {
        if (!controller.signal.aborted) setCustomPoints(points);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setCustomPointsError(
          reason instanceof Error ? reason.message : "暂时无法读取自建点位",
        );
      });
    return () => controller.abort();
  }, [reloadKey, customPointsReload]);

  const catalog = useMemo(() => {
    if (!baseCatalog) return null;
    const points = new Map(
      [...baseCatalog.points, ...customPoints, ...createdPoints].map(
        (point) => [point.id, point],
      ),
    );
    return { ...baseCatalog, points: [...points.values()] };
  }, [baseCatalog, customPoints, createdPoints]);

  const reload = useCallback(() => setReloadKey((value) => value + 1), []);
  const retryCustomPoints = useCallback(
    () => setCustomPointsReload((value) => value + 1),
    [],
  );
  const addCustomPoint = useCallback((point: MapPoint) => {
    setCreatedPoints((current) => [
      ...current.filter((item) => item.id !== point.id),
      point,
    ]);
  }, []);

  return {
    baseCatalog,
    catalog,
    error,
    customPointsError,
    reloadKey,
    reload,
    retryCustomPoints,
    addCustomPoint,
  };
}
