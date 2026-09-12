import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

import type {
  EntityType,
  ExtractionResponse,
  GeoFeature,
  GraphEntity,
  GraphQueryResult,
  GraphRelation,
  HistoricalEvent,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${getBackendBaseURL()}${path}`, {
    credentials: "include",
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(
      payload?.detail?.message ??
        payload?.detail ??
        `请求失败 (${response.status})`,
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

type ListOptions = {
  entityId?: string;
  limit?: number;
  offset?: number;
  signal?: AbortSignal;
};

export type GraphCatalog = {
  entities: GraphEntity[];
  relations: GraphRelation[];
};

const GRAPH_CATALOG_CACHE_TTL_MS = 5 * 60 * 1000;
const GRAPH_QUERY_CACHE_TTL_MS = 5 * 60 * 1000;
let graphCatalogCache: {
  expiresAt: number;
  value: GraphCatalog;
} | null = null;
let graphCatalogInFlight: Promise<GraphCatalog> | null = null;
const graphQueryCache = new Map<
  string,
  { expiresAt: number; value: GraphQueryResult }
>();
const graphQueryInFlight = new Map<string, Promise<GraphQueryResult>>();

function awaitWithAbort<T>(
  promise: Promise<T>,
  signal?: AbortSignal,
): Promise<T> {
  if (!signal) return promise;
  if (signal.aborted) {
    return Promise.reject(new Error("请求已取消"));
  }
  return new Promise<T>((resolve, reject) => {
    const onAbort = () => reject(new Error("请求已取消"));
    signal.addEventListener("abort", onAbort, { once: true });
    promise.then(resolve, reject).finally(() => {
      signal.removeEventListener("abort", onAbort);
    });
  });
}

export function readCachedGraphCatalog(): GraphCatalog | null {
  if (!graphCatalogCache || graphCatalogCache.expiresAt <= Date.now()) {
    graphCatalogCache = null;
    return null;
  }
  return graphCatalogCache.value;
}

export function invalidateGraphCatalogCache() {
  graphCatalogCache = null;
  graphQueryCache.clear();
}

export const listEntities = (options: ListOptions = {}) =>
  request<GraphEntity[]>(
    `/api/entities?${new URLSearchParams({
      limit: String(options.limit ?? 50),
      offset: String(options.offset ?? 0),
    })}`,
    { signal: options.signal },
  );
export const listRelations = (options: ListOptions = {}) =>
  request<GraphRelation[]>(
    `/api/knowledge-graph/relations?${new URLSearchParams({
      ...(options.entityId ? { entity_id: options.entityId } : {}),
      limit: String(options.limit ?? 100),
      offset: String(options.offset ?? 0),
    })}`,
    { signal: options.signal },
  );

async function listAllPages<T>(
  pageSize: number,
  fetchPage: (offset: number) => Promise<T[]>,
): Promise<T[]> {
  const items: T[] = [];
  let offset = 0;
  while (true) {
    const page = await fetchPage(offset);
    items.push(...page);
    if (page.length < pageSize) return items;
    offset += page.length;
  }
}

export async function fetchGraphCatalog(
  options: { force?: boolean; signal?: AbortSignal } = {},
): Promise<GraphCatalog> {
  const cached = readCachedGraphCatalog();
  if (cached && !options.force) return cached;
  graphCatalogInFlight ??= Promise.all([
    listAllPages(1000, (offset) =>
      listEntities({ limit: 1000, offset, signal: options.signal }),
    ),
    listAllPages(2000, (offset) =>
      listRelations({ limit: 2000, offset, signal: options.signal }),
    ),
  ])
    .then(([entities, relations]) => {
      const value = { entities, relations };
      graphCatalogCache = {
        expiresAt: Date.now() + GRAPH_CATALOG_CACHE_TTL_MS,
        value,
      };
      return value;
    })
    .finally(() => {
      graphCatalogInFlight = null;
    });
  return await awaitWithAbort(graphCatalogInFlight, options.signal);
}
export const listEvents = (options: ListOptions = {}) =>
  request<HistoricalEvent[]>(
    `/api/knowledge-graph/events?limit=${options.limit ?? 100}`,
    { signal: options.signal },
  );
export const listGeoFeatures = (options: ListOptions = {}) =>
  request<GeoFeature[]>(
    `/api/knowledge-graph/geo?limit=${options.limit ?? 200}`,
    { signal: options.signal },
  );

export async function queryGraph(
  entity: string,
  maxDepth = 3,
  options: { maxNodes?: number; releaseId?: string; signal?: AbortSignal } = {},
): Promise<GraphQueryResult> {
  const maxNodes = options.maxNodes ?? 120;
  const key = JSON.stringify([entity, maxDepth, maxNodes, options.releaseId]);
  const cached = graphQueryCache.get(key);
  if (cached && cached.expiresAt > Date.now()) {
    return cached.value;
  }
  if (cached) graphQueryCache.delete(key);
  let inFlight = graphQueryInFlight.get(key);
  if (!inFlight) {
    inFlight = request<GraphQueryResult>(
      `/api/knowledge-graph/query?${new URLSearchParams({
        entity,
        max_depth: String(maxDepth),
        max_nodes: String(maxNodes),
        ...(options.releaseId ? { release_id: options.releaseId } : {}),
      })}`,
      { signal: options.signal },
    )
      .then((value) => {
        graphQueryCache.set(key, {
          expiresAt: Date.now() + GRAPH_QUERY_CACHE_TTL_MS,
          value,
        });
        return value;
      })
      .finally(() => {
        graphQueryInFlight.delete(key);
      });
    graphQueryInFlight.set(key, inFlight);
  }
  return await awaitWithAbort(inFlight, options.signal);
}

export const createEntity = (input: {
  canonical_name: string;
  entity_type: EntityType;
  summary?: string;
}) =>
  request<GraphEntity>("/api/entities", {
    method: "POST",
    body: JSON.stringify(input),
  });

export const createRelation = (
  input: Omit<
    GraphRelation,
    "id" | "start_time" | "end_time" | "evidence_ids" | "release_id"
  >,
) =>
  request<GraphRelation>("/api/knowledge-graph/relations", {
    method: "POST",
    body: JSON.stringify(input),
  });

export const createEvent = (input: {
  title: string;
  event_type: string;
  place_entity_id?: string;
  summary?: string;
}) =>
  request<HistoricalEvent>("/api/knowledge-graph/events", {
    method: "POST",
    body: JSON.stringify({
      ...input,
      is_inferred: true,
      review_status: "pending",
    }),
  });

export const upsertGeoFeature = (
  input: Omit<GeoFeature, "evidence_ids" | "release_id">,
) =>
  request<GeoFeature>(
    `/api/knowledge-graph/geo/${encodeURIComponent(input.entity_id)}`,
    {
      method: "PUT",
      body: JSON.stringify(input),
    },
  );

export const extractTextKnowledge = (
  text: string,
  persist: boolean,
  evidenceIds: string[] = [],
) =>
  request<ExtractionResponse>("/api/knowledge-graph/extract", {
    method: "POST",
    body: JSON.stringify({ text, persist, evidence_ids: evidenceIds }),
  });

export const reviewRelation = (
  relationId: string,
  reviewStatus: "reviewed" | "rejected",
) =>
  request<GraphRelation>(
    `/api/knowledge-graph/relations/${encodeURIComponent(relationId)}/review`,
    {
      method: "PATCH",
      body: JSON.stringify({ review_status: reviewStatus }),
    },
  );

export const reviewEvent = (
  eventId: string,
  reviewStatus: "reviewed" | "rejected",
) =>
  request<HistoricalEvent>(
    `/api/knowledge-graph/events/${encodeURIComponent(eventId)}/review`,
    {
      method: "PATCH",
      body: JSON.stringify({ review_status: reviewStatus }),
    },
  );
