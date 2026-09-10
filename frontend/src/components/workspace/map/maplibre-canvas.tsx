"use client";

import maplibregl, { type Map, type Marker } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";

import {
  buildUncertaintyFeatureCollection,
  spatialExtentCoordinates,
} from "@/core/map/geometry";
import {
  buildMapStyle,
  defaultMapLayerOpacity,
  MAP_BASE_LAYER_ID,
  mapLayerStyleId,
} from "@/core/map/layers";
import {
  type MapLayer,
  type MapPoint,
  type PlannedMapRoute,
  type TimelineEvent,
  type UserMapLocation,
} from "@/core/map/types";
import { cn } from "@/lib/utils";

const UNCERTAINTY_SOURCE_ID = "xingxi-historical-uncertainty";
const UNCERTAINTY_FILL_LAYER_ID = `${UNCERTAINTY_SOURCE_ID}-fill`;
const UNCERTAINTY_LINE_LAYER_ID = `${UNCERTAINTY_SOURCE_ID}-line`;

function syncUncertaintyAreas(
  map: Map,
  points: MapPoint[],
  selectedId: string | null | undefined,
) {
  if (map.getLayer(UNCERTAINTY_LINE_LAYER_ID))
    map.removeLayer(UNCERTAINTY_LINE_LAYER_ID);
  if (map.getLayer(UNCERTAINTY_FILL_LAYER_ID))
    map.removeLayer(UNCERTAINTY_FILL_LAYER_ID);
  if (map.getSource(UNCERTAINTY_SOURCE_ID))
    map.removeSource(UNCERTAINTY_SOURCE_ID);
  const data = buildUncertaintyFeatureCollection(points, selectedId);
  if (data.features.length === 0) return;
  map.addSource(UNCERTAINTY_SOURCE_ID, { type: "geojson", data });
  map.addLayer({
    id: UNCERTAINTY_FILL_LAYER_ID,
    type: "fill",
    source: UNCERTAINTY_SOURCE_ID,
    paint: {
      "fill-color": [
        "match",
        ["get", "geometryType"],
        "historical_area",
        "#4f7d72",
        ["match", ["get", "confidence"], "speculative", "#be123c", "#d97706"],
      ],
      "fill-opacity": [
        "case",
        ["boolean", ["get", "selected"], false],
        0.24,
        0.12,
      ],
    },
  });
  map.addLayer({
    id: UNCERTAINTY_LINE_LAYER_ID,
    type: "line",
    source: UNCERTAINTY_SOURCE_ID,
    paint: {
      "line-color": [
        "match",
        ["get", "geometryType"],
        "historical_area",
        "#275e57",
        ["match", ["get", "confidence"], "speculative", "#9f1239", "#b45309"],
      ],
      "line-dasharray": [2, 2],
      "line-opacity": 0.9,
      "line-width": ["case", ["boolean", ["get", "selected"], false], 3, 2],
    },
  });
}

function syncMapLayerControls(
  map: Map,
  layers: MapLayer[],
  visibleLayerIds: string[],
  layerOpacity: Record<string, number>,
) {
  const visible = new Set(visibleLayerIds);
  const baseLayer = layers.find(
    (layer) => layer.kind === "base" && layer.available && layer.tileUrl,
  );
  if (baseLayer && map.getLayer(MAP_BASE_LAYER_ID)) {
    map.setLayoutProperty(
      MAP_BASE_LAYER_ID,
      "visibility",
      visible.has(baseLayer.id) ? "visible" : "none",
    );
    map.setPaintProperty(
      MAP_BASE_LAYER_ID,
      "raster-opacity",
      layerOpacity[baseLayer.id] ?? defaultMapLayerOpacity(baseLayer),
    );
  }

  layers
    .filter(
      (layer) =>
        layer.kind === "historical" && layer.available && layer.tileUrl,
    )
    .forEach((layer) => {
      const styleId = mapLayerStyleId(layer);
      if (!map.getLayer(styleId)) return;
      map.setLayoutProperty(
        styleId,
        "visibility",
        visible.has(layer.id) ? "visible" : "none",
      );
      map.setPaintProperty(
        styleId,
        "raster-opacity",
        layerOpacity[layer.id] ?? defaultMapLayerOpacity(layer),
      );
    });
}

function syncLine(
  map: Map,
  id: string,
  points: MapPoint[],
  color: string,
  dashed: boolean,
) {
  if (map.getLayer(id)) map.removeLayer(id);
  if (map.getSource(id)) map.removeSource(id);
  if (points.length < 2) return;
  map.addSource(id, {
    type: "geojson",
    data: {
      type: "Feature",
      properties: {},
      geometry: {
        type: "LineString",
        coordinates: points.map((point) => [point.lon, point.lat]),
      },
    },
  });
  map.addLayer({
    id,
    type: "line",
    source: id,
    paint: {
      "line-color": color,
      "line-width": 3,
      "line-opacity": 0.8,
      ...(dashed ? { "line-dasharray": [2, 2] } : {}),
    },
  });
}

function syncCoordinateLine(
  map: Map,
  id: string,
  coordinates: Array<[number, number]>,
  color: string,
  dashed: boolean,
) {
  if (map.getLayer(id)) map.removeLayer(id);
  if (map.getSource(id)) map.removeSource(id);
  if (coordinates.length < 2) return;
  map.addSource(id, {
    type: "geojson",
    data: {
      type: "Feature",
      properties: {},
      geometry: { type: "LineString", coordinates },
    },
  });
  map.addLayer({
    id,
    type: "line",
    source: id,
    paint: {
      "line-color": color,
      "line-width": 5,
      "line-opacity": 0.88,
      ...(dashed ? { "line-dasharray": [2, 2] } : {}),
    },
  });
}

const MARKER_LABEL_MIN_ZOOM = 16.25;
const SELECTED_POINT_MIN_ZOOM = 15.5;

const confidenceDotClass: Record<MapPoint["confidence"], string> = {
  exact: "border-teal-800 bg-teal-600",
  approximate: "border-amber-700 border-dashed bg-amber-50",
  speculative: "border-rose-700 border-dotted bg-rose-50",
};

const confidenceLabelClass: Record<MapPoint["confidence"], string> = {
  exact: "border-teal-700 bg-white text-teal-950",
  approximate: "border-amber-600 border-dashed bg-amber-50 text-amber-950",
  speculative: "border-rose-600 border-dotted bg-rose-50 text-rose-950",
};

type MarkerView = {
  activeEvent: boolean;
  button: HTMLButtonElement;
  focused: boolean;
  hovered: boolean;
  label: HTMLSpanElement;
  selected: boolean;
  wrapper: HTMLDivElement;
};

function shouldShowMapMarkerLabel({
  focused,
  hovered,
  selected,
  zoom,
}: {
  focused: boolean;
  hovered: boolean;
  selected: boolean;
  zoom: number;
}) {
  return selected || hovered || focused || zoom >= MARKER_LABEL_MIN_ZOOM;
}

function getSelectedPointCamera(
  point: Pick<MapPoint, "lat" | "lon">,
  currentZoom: number,
) {
  return {
    center: [point.lon, point.lat] as [number, number],
    duration: 600,
    zoom: Math.max(currentZoom, SELECTED_POINT_MIN_ZOOM),
  };
}

function focusMapPoint(map: Map, point: MapPoint, duration = 600) {
  const extent = spatialExtentCoordinates(point);
  if (extent.length >= 4) {
    const bounds = new maplibregl.LngLatBounds();
    extent.forEach((coordinate) => bounds.extend(coordinate));
    map.fitBounds(bounds, { duration, maxZoom: 15, padding: 72 });
    return;
  }
  map.easeTo(getSelectedPointCamera(point, map.getZoom()));
}

function syncMarkerLabel(view: MarkerView, zoom: number) {
  const visible =
    !view.activeEvent &&
    shouldShowMapMarkerLabel({
      focused: view.focused,
      hovered: view.hovered,
      selected: view.selected,
      zoom,
    });
  view.label.hidden = !visible;
  view.button.dataset.labelVisible = String(visible);
  view.wrapper.style.zIndex = view.activeEvent
    ? "50"
    : view.hovered || view.focused
      ? "30"
      : view.selected
        ? "20"
        : "1";
}

export function MapLibreCanvas({
  points,
  layers = [],
  visibleLayerIds = [],
  layerOpacity = {},
  routePoints = [],
  trajectoryPoints = [],
  plannedRoute = null,
  userLocation = null,
  locationFocusToken = 0,
  events = [],
  historyYear = null,
  activeEventId = null,
  selectedId,
  onSelect,
  onSelectEvent,
  className,
}: {
  points: MapPoint[];
  layers?: MapLayer[];
  visibleLayerIds?: string[];
  layerOpacity?: Record<string, number>;
  routePoints?: MapPoint[];
  trajectoryPoints?: MapPoint[];
  plannedRoute?: PlannedMapRoute | null;
  userLocation?: UserMapLocation | null;
  locationFocusToken?: number;
  events?: TimelineEvent[];
  historyYear?: number | null;
  activeEventId?: string | null;
  selectedId?: string | null;
  onSelect?: (point: MapPoint) => void;
  onSelectEvent?: (event: TimelineEvent) => void;
  className?: string;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);
  const markersRef = useRef<Marker[]>([]);
  const markerViewsRef = useRef<MarkerView[]>([]);
  const userMarkerRef = useRef<Marker | null>(null);
  const hasFittedRef = useRef(false);
  const focusedPointIdRef = useRef<string | null>(null);
  const focusedEventIdRef = useRef<string | null>(null);
  const initialLayersRef = useRef(layers);
  const onSelectRef = useRef(onSelect);
  const onSelectEventRef = useRef(onSelectEvent);
  const pointsRef = useRef(points);
  const selectedIdRef = useRef(selectedId);
  const [status, setStatus] = useState<"loading" | "ready" | "error">(
    "loading",
  );
  onSelectRef.current = onSelect;
  onSelectEventRef.current = onSelectEvent;
  pointsRef.current = points;
  selectedIdRef.current = selectedId;

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: buildMapStyle(initialLayersRef.current),
      center: [120.5067, 31.255],
      zoom: 14,
      attributionControl: { compact: true },
    });
    map.addControl(
      new maplibregl.NavigationControl({ showCompass: false }),
      "top-right",
    );
    map.addControl(
      new maplibregl.ScaleControl({ unit: "metric" }),
      "bottom-left",
    );
    const syncMarkerLabels = () => {
      const zoom = map.getZoom();
      markerViewsRef.current.forEach((view) => syncMarkerLabel(view, zoom));
    };
    const syncCameraState = () => {
      if (!containerRef.current) return;
      containerRef.current.dataset.mapCameraPitch = map.getPitch().toFixed(0);
      containerRef.current.dataset.mapCameraBearing = map
        .getBearing()
        .toFixed(0);
    };
    const resizeObserver = new ResizeObserver(() => {
      map.resize();
      const currentSelectedId = selectedIdRef.current;
      const selectedPoint = pointsRef.current.find(
        (point) => point.id === currentSelectedId,
      );
      if (selectedPoint) {
        focusMapPoint(map, selectedPoint, 0);
      }
    });
    resizeObserver.observe(containerRef.current);
    map.on("zoom", syncMarkerLabels);
    map.on("move", syncCameraState);
    syncCameraState();
    void map.once("load", () => setStatus("ready"));
    map.on("error", (event) => {
      if (!event.error.message.includes("Failed to fetch")) return;
      setStatus("error");
    });
    mapRef.current = map;
    return () => {
      markersRef.current.forEach((marker) => marker.remove());
      markersRef.current = [];
      markerViewsRef.current = [];
      userMarkerRef.current?.remove();
      resizeObserver.disconnect();
      map.off("zoom", syncMarkerLabels);
      map.off("move", syncCameraState);
      map.remove();
      mapRef.current = null;
      focusedPointIdRef.current = null;
      focusedEventIdRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const renderLayerControls = () =>
      syncMapLayerControls(map, layers, visibleLayerIds, layerOpacity);
    if (map.isStyleLoaded()) renderLayerControls();
    else void map.once("load", renderLayerControls);
    return () => {
      map.off("load", renderLayerControls);
    };
  }, [layerOpacity, layers, visibleLayerIds]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const renderMarkers = () => {
      markersRef.current.forEach((marker) => marker.remove());
      markersRef.current = [];
      markerViewsRef.current = [];
      for (const point of points) {
        const activeEvent = events.find(
          (event) => event.id === activeEventId && event.pointId === point.id,
        );
        const wrapper = document.createElement("div");
        wrapper.className = "relative grid size-8 place-items-center";

        const element = document.createElement("button");
        element.type = "button";
        element.className =
          "relative grid size-8 animate-[xingxi-history-entry_700ms_ease-out] place-items-center rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-700 focus-visible:ring-offset-2 motion-reduce:animate-none";
        element.setAttribute(
          "aria-label",
          point.geometryType === "point"
            ? `地图点位 ${point.name}`
            : `地图范围 ${point.name}`,
        );
        element.dataset.confidence = point.confidence;
        element.dataset.spatialGeometry = point.geometryType;
        element.dataset.reviewStatus = point.reviewStatus ?? "reference";
        element.dataset.activeEvent = activeEvent?.id ?? "";
        element.dataset.historyYear =
          historyYear === null ? "" : String(historyYear);

        const routeIndex = routePoints.findIndex(
          (item) => item.id === point.id,
        );
        const dot = document.createElement("span");
        dot.className = cn(
          "pointer-events-none grid rounded-full border-2 shadow-sm transition-transform",
          routeIndex >= 0
            ? "size-5 place-items-center bg-teal-700 text-[10px] font-semibold text-white"
            : point.geometryType === "point"
              ? "size-3"
              : "size-4 place-items-center bg-white text-[11px] font-bold",
          point.id === selectedId
            ? "scale-125 border-teal-950 bg-teal-950 ring-2 ring-white"
            : confidenceDotClass[point.confidence],
          point.recordKind === "corpus" && point.reviewStatus !== "reviewed"
            ? "ring-2 ring-amber-300/80 [border-style:dashed]"
            : "",
        );
        dot.setAttribute("aria-hidden", "true");
        if (routeIndex >= 0) dot.textContent = String(routeIndex + 1);
        else if (point.geometryType !== "point") dot.textContent = "×";

        if (activeEvent) {
          const pulse = document.createElement("span");
          pulse.className =
            "pointer-events-none absolute size-10 animate-ping rounded-full border-2 border-[#c75832] bg-[#e8a17d]/35 motion-reduce:animate-none";
          pulse.setAttribute("aria-hidden", "true");
          element.appendChild(pulse);
        }

        const label = document.createElement("span");
        label.className = cn(
          "pointer-events-none absolute bottom-full left-1/2 mb-1 max-w-40 -translate-x-1/2 truncate rounded-full border-2 px-2 py-1 text-[11px] whitespace-nowrap shadow-sm backdrop-blur",
          point.id === selectedId
            ? "border-teal-950 bg-teal-950 text-white"
            : confidenceLabelClass[point.confidence],
        );
        label.dataset.mapMarkerLabel = "true";
        label.setAttribute("aria-hidden", "true");
        label.textContent = point.name;
        element.append(dot, label);

        if (activeEvent) {
          const bubble = document.createElement("button");
          bubble.type = "button";
          bubble.className =
            "absolute bottom-full left-1/2 mb-4 w-[min(18rem,calc(100vw-2rem))] -translate-x-1/2 rounded-md border border-[#b67a5e] bg-[#fffdf8] p-3 text-left text-[#372b27] shadow-[0_10px_30px_rgba(48,37,31,0.22)] transition motion-reduce:transition-none after:absolute after:top-full after:left-1/2 after:-translate-x-1/2 after:border-8 after:border-transparent after:border-t-[#b67a5e] hover:border-[#8f553d] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1d6267]";
          bubble.dataset.mapEventBubble = "true";
          bubble.dataset.eventId = activeEvent.id;
          bubble.setAttribute(
            "aria-label",
            `历史事件：${activeEvent.timeLabel}，${activeEvent.title}`,
          );

          const meta = document.createElement("span");
          meta.className =
            "mb-1 flex items-center justify-between gap-2 text-[11px] leading-4 text-[#80533f]";
          const time = document.createElement("span");
          time.className = "font-medium";
          time.textContent = activeEvent.timeLabel;
          const status = document.createElement("span");
          status.className =
            "shrink-0 rounded border border-[#dcc4b7] bg-[#f8eee8] px-1.5 py-0.5";
          status.textContent =
            activeEvent.recordKind === "corpus" &&
            activeEvent.reviewStatus !== "reviewed"
              ? "待复核语料草稿"
              : "历史事件";
          meta.append(time, status);

          const title = document.createElement("span");
          title.className = "block text-sm font-semibold leading-5";
          title.textContent = activeEvent.title;
          const summary = document.createElement("span");
          summary.className =
            "mt-1 block line-clamp-3 text-xs leading-5 text-[#5e4b43]";
          summary.textContent = activeEvent.summary;
          bubble.append(meta, title, summary);
          bubble.addEventListener("click", (event) => {
            event.stopPropagation();
            onSelectEventRef.current?.(activeEvent);
          });
          wrapper.appendChild(bubble);
        }

        const view: MarkerView = {
          activeEvent: Boolean(activeEvent),
          button: element,
          focused: false,
          hovered: false,
          label,
          selected: point.id === selectedId,
          wrapper,
        };
        const updateView = () => syncMarkerLabel(view, map.getZoom());
        element.addEventListener("mouseenter", () => {
          view.hovered = true;
          updateView();
        });
        element.addEventListener("mouseleave", () => {
          view.hovered = false;
          updateView();
        });
        element.addEventListener("focus", () => {
          view.focused = true;
          updateView();
        });
        element.addEventListener("blur", () => {
          view.focused = false;
          updateView();
        });
        element.addEventListener("click", (event) => {
          event.stopPropagation();
          onSelectRef.current?.(point);
        });
        wrapper.appendChild(element);
        markerViewsRef.current.push(view);
        updateView();
        markersRef.current.push(
          new maplibregl.Marker({ element: wrapper, anchor: "bottom" })
            .setLngLat([point.lon, point.lat])
            .addTo(map),
        );
      }
      if (!hasFittedRef.current && points.length > 0) {
        const bounds = new maplibregl.LngLatBounds();
        points.forEach((point) => {
          const extent = spatialExtentCoordinates(point);
          if (extent.length)
            extent.forEach((coordinate) => bounds.extend(coordinate));
          else bounds.extend([point.lon, point.lat]);
        });
        map.fitBounds(bounds, { padding: 56, maxZoom: 15, duration: 0 });
        hasFittedRef.current = true;
      }
    };
    const renderLines = () => {
      syncUncertaintyAreas(map, points, selectedId);
      syncLine(map, "xingxi-study-route", routePoints, "#0f766e", false);
      syncLine(
        map,
        "xingxi-person-trajectory",
        trajectoryPoints,
        "#a16207",
        true,
      );
      syncCoordinateLine(
        map,
        "xingxi-road-route",
        plannedRoute?.coordinates ?? [],
        plannedRoute?.routingStatus === "routed" ? "#2563eb" : "#dc2626",
        plannedRoute?.routingStatus !== "routed",
      );
    };
    renderMarkers();
    if (map.isStyleLoaded()) renderLines();
    else void map.once("load", renderLines);
    return () => {
      map.off("load", renderLines);
    };
  }, [
    activeEventId,
    events,
    historyYear,
    plannedRoute,
    points,
    routePoints,
    selectedId,
    trajectoryPoints,
  ]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (!userLocation) {
      userMarkerRef.current?.remove();
      userMarkerRef.current = null;
      return;
    }

    let element = userMarkerRef.current?.getElement();
    if (!element) {
      element = document.createElement("div");
      element.className = "relative grid size-9 place-items-center";
      element.setAttribute("role", "img");
      element.dataset.userLocation = "true";

      const pulse = document.createElement("span");
      pulse.className =
        "absolute size-8 animate-ping rounded-full bg-blue-500/30 motion-reduce:animate-none";
      pulse.setAttribute("aria-hidden", "true");

      const dot = document.createElement("span");
      dot.className =
        "relative size-4 rounded-full border-[3px] border-white bg-blue-600 shadow-[0_1px_5px_rgba(15,23,42,0.45)]";
      dot.setAttribute("aria-hidden", "true");
      element.append(pulse, dot);
      userMarkerRef.current = new maplibregl.Marker({ element })
        .setLngLat([userLocation.lon, userLocation.lat])
        .addTo(map);
    } else {
      userMarkerRef.current?.setLngLat([userLocation.lon, userLocation.lat]);
    }

    const accuracy = Math.round(userLocation.accuracyMeters);
    const label = `我的实时位置，精度约 ${accuracy} 米`;
    element.setAttribute("aria-label", label);
    element.title = label;
    element.dataset.locationLon = userLocation.lon.toFixed(6);
    element.dataset.locationLat = userLocation.lat.toFixed(6);
  }, [userLocation]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const syncConnector = () => {
      const firstStop = routePoints[0];
      const coordinates =
        userLocation && firstStop && plannedRoute === null
          ? ([
              [userLocation.lon, userLocation.lat],
              [firstStop.lon, firstStop.lat],
            ] as Array<[number, number]>)
          : [];
      syncCoordinateLine(
        map,
        "xingxi-user-route-connector",
        coordinates,
        "#2563eb",
        true,
      );
    };
    if (map.isStyleLoaded()) syncConnector();
    else void map.once("load", syncConnector);
    return () => {
      map.off("load", syncConnector);
    };
  }, [plannedRoute, routePoints, userLocation]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !userLocation || locationFocusToken < 1) return;
    const focusUserLocation = () => {
      map.easeTo({
        center: [userLocation.lon, userLocation.lat],
        duration: 500,
        zoom: Math.max(map.getZoom(), 16),
      });
    };
    if (map.isStyleLoaded()) focusUserLocation();
    else void map.once("load", focusUserLocation);
    return () => {
      map.off("load", focusUserLocation);
    };
  }, [locationFocusToken, userLocation]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !selectedId || focusedPointIdRef.current === selectedId) return;
    const selectedPoint = points.find((point) => point.id === selectedId);
    if (!selectedPoint) return;

    const focusSelectedPoint = () => {
      focusMapPoint(map, selectedPoint);
      focusedPointIdRef.current = selectedId;
    };
    if (map.isStyleLoaded()) focusSelectedPoint();
    else {
      void map.once("load", focusSelectedPoint);
      void map.once("error", focusSelectedPoint);
    }
    return () => {
      map.off("load", focusSelectedPoint);
      map.off("error", focusSelectedPoint);
    };
  }, [points, selectedId]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !activeEventId || focusedEventIdRef.current === activeEventId) {
      return;
    }
    const activeEvent = events.find((event) => event.id === activeEventId);
    const eventPoint = points.find(
      (point) => point.id === activeEvent?.pointId,
    );
    if (!eventPoint) return;

    let focused = false;
    const focusEvent = () => {
      if (focused) return;
      focused = true;
      const eventIndex = Math.max(
        0,
        events.findIndex((event) => event.id === activeEventId),
      );
      map.flyTo({
        center: [eventPoint.lon, eventPoint.lat],
        zoom: Math.max(map.getZoom(), 15.8),
        pitch: 42,
        bearing: ((eventIndex * 37 + 18) % 120) - 60,
        speed: 0.58,
        curve: 1.35,
        duration: 1400,
        essential: true,
      });
      focusedEventIdRef.current = activeEventId;
    };
    if (map.isStyleLoaded()) focusEvent();
    else {
      void map.once("load", focusEvent);
      void map.once("error", focusEvent);
    }
    return () => {
      map.off("load", focusEvent);
      map.off("error", focusEvent);
    };
  }, [activeEventId, events, points]);

  return (
    <div className={cn("relative h-full w-full overflow-hidden", className)}>
      <div
        ref={containerRef}
        className="h-full w-full"
        data-map-engine="maplibre-gl"
        data-map-status={status}
        aria-label="古舆地图画布"
      />
      {status === "loading" && (
        <div className="bg-background/90 text-muted-foreground absolute inset-0 grid place-items-center text-sm">
          正在加载地图…
        </div>
      )}
      {status === "error" && (
        <div
          data-map-error="true"
          className="bg-background/90 absolute inset-x-4 top-20 rounded border px-3 py-2 text-sm leading-5"
        >
          现代底图暂时无法加载。点位与来源列表仍可使用，请检查网络后刷新。
        </div>
      )}
    </div>
  );
}
