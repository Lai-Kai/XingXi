export type ReviewStatus = "pending" | "reviewed" | "disputed" | "rejected";
export type EntityType =
  | "person"
  | "family"
  | "place"
  | "waterway"
  | "bridge"
  | "building"
  | "garden"
  | "relic"
  | "organization"
  | "work"
  | "event";

export interface GraphEntity {
  id: string;
  canonical_name: string;
  entity_type: EntityType;
  dynasty: string | null;
  extant_status: string | null;
  summary: string | null;
  review_status: ReviewStatus;
  release_id: string | null;
  evidence_ids: string[];
}

export interface GraphRelation {
  id: string;
  subject_id: string;
  relation_type:
    | "located_in"
    | "built_by"
    | "repaired_in"
    | "crosses"
    | "related_to"
    | "sibling_of"
    | "spouse_of"
    | "parent_of"
    | "lived_in"
    | "visited"
    | "born_in"
    | "worked_at"
    | "studied_at"
    | "died_at"
    | "composed_at"
    | "mentioned_in_poetry"
    | "documented_in";
  object_id: string;
  start_time: string | null;
  end_time: string | null;
  confidence: number;
  evidence_ids: string[];
  is_inferred: boolean;
  review_status: ReviewStatus;
  release_id: string | null;
}

export interface HistoricalEvent {
  id: string;
  title: string;
  event_type: string;
  start_time: string | null;
  end_time: string | null;
  time_certainty: "exact" | "approximate" | "unknown";
  place_entity_id: string | null;
  participant_entity_ids: string[];
  summary: string | null;
  evidence_ids: string[];
  is_inferred: boolean;
  review_status: ReviewStatus;
  release_id: string | null;
}

export interface GeoFeature {
  entity_id: string;
  name: string;
  lon: number;
  lat: number;
  confidence: "exact" | "approximate" | "speculative";
  basis: string;
  geometry_type: "point" | "uncertainty_radius" | "historical_area";
  uncertainty_radius_m: number | null;
  area_coordinates: Array<[number, number]>;
  extent_source:
    | "evidence"
    | "historical_map"
    | "editorial_estimate"
    | "confidence_default"
    | null;
  extent_basis: string | null;
  evidence_ids: string[];
  review_status: ReviewStatus;
  release_id: string | null;
}

export interface GraphQueryResult {
  query: string;
  status: "supported" | "empty" | "ambiguous";
  message: string;
  candidates: GraphEntity[];
  nodes: GraphEntity[];
  edges: GraphRelation[];
  evidence: Array<Record<string, unknown>>;
  truncated: boolean;
}

export interface KnowledgeExtraction {
  text: string;
  entities: Array<{ name: string; entity_type: EntityType; reason: string }>;
  relations: Array<{
    subject_name: string;
    relation_type: GraphRelation["relation_type"];
    object_name: string;
    source_text: string;
  }>;
  events: Array<{
    title: string;
    start_time: string | null;
    time_certainty: string;
    place_name: string | null;
    source_text: string;
  }>;
  aliases: Array<{
    canonical_name: string;
    alias: string;
    source_text: string;
  }>;
}

export interface ExtractionResponse {
  extraction: KnowledgeExtraction;
  entity_ids: Record<string, string>;
  relation_ids: string[];
  event_ids: string[];
  alias_notice: string | null;
}

export function sortHistoricalEvents(
  events: HistoricalEvent[],
): HistoricalEvent[] {
  const year = (value: string | null) => {
    const match = value?.match(/(?:^|\D)(-?\d{1,4})(?!\d)/);
    return match ? Number(match[1]) : null;
  };
  return [...events].sort((left, right) => {
    const leftYear = year(left.start_time);
    const rightYear = year(right.start_time);
    if (leftYear === null && rightYear !== null) return 1;
    if (leftYear !== null && rightYear === null) return -1;
    return (
      (leftYear ?? 0) - (rightYear ?? 0) ||
      left.title.localeCompare(right.title, "zh-CN") ||
      left.id.localeCompare(right.id)
    );
  });
}
