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
  signal?: AbortSignal;
};

export const listEntities = (options: ListOptions = {}) =>
  request<GraphEntity[]>(`/api/entities?limit=${options.limit ?? 50}`, {
    signal: options.signal,
  });
export const listRelations = (options: ListOptions = {}) =>
  request<GraphRelation[]>(
    `/api/knowledge-graph/relations?${new URLSearchParams({
      ...(options.entityId ? { entity_id: options.entityId } : {}),
      limit: String(options.limit ?? 100),
    })}`,
    { signal: options.signal },
  );
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

export const queryGraph = (
  entity: string,
  maxDepth = 3,
  options: { maxNodes?: number; signal?: AbortSignal } = {},
) =>
  request<GraphQueryResult>(
    `/api/knowledge-graph/query?entity=${encodeURIComponent(entity)}&max_depth=${maxDepth}&max_nodes=${options.maxNodes ?? 120}`,
    { signal: options.signal },
  );

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
