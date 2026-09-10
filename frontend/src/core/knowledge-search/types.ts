export const dynastyValues = [
  "pre_qin",
  "qin",
  "han",
  "three_kingdoms",
  "jin",
  "southern_northern",
  "sui",
  "tang",
  "five_dynasties_ten_kingdoms",
  "song",
  "yuan",
  "ming",
  "qing",
  "republic_of_china",
  "prc",
] as const;

export type Dynasty = (typeof dynastyValues)[number];
export type SourceLevel = "A" | "B" | "C" | "D" | "E" | "U";
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
export type SourceType =
  | "gazetteer"
  | "inscription"
  | "archive"
  | "heritage_record"
  | "scholarly_work"
  | "oral_history"
  | "web"
  | "inference"
  | "other";

export interface StructuredSearchFilters {
  document_ids?: string[];
  editions?: string[];
  source_types?: SourceType[];
  source_levels?: SourceLevel[];
  dynasties?: Dynasty[];
  entity_types?: EntityType[];
  review_statuses?: ReviewStatus[];
  min_spatial_confidence?: number;
  max_spatial_confidence?: number;
}

export interface StructuredSearchRequest {
  query: string;
  release_id?: string;
  filters?: StructuredSearchFilters;
  page_size?: number;
  cursor?: string;
  candidate_k?: number;
  min_vector_similarity?: number;
  max_alias_expansions?: number;
}

export interface StructuredSearchHit {
  release_id: string;
  chunk_id: string;
  fused_score: number;
  channels: Array<"fulltext" | "vector">;
  fulltext_rank?: number;
  fulltext_score?: number;
  vector_rank?: number;
  vector_similarity?: number;
  citation: {
    evidence_id: string;
    document_id: string;
    source_file_id: string | null;
    document_title: string;
    edition: string | null;
    volume: string | null;
    section: string | null;
    page_start: number;
    page_end: number;
    folio_start: string | null;
    folio_end: string | null;
    quote: string;
    source_level: SourceLevel;
    review_status: ReviewStatus;
  };
  ranking?: {
    policy_version: string;
    final_score: number;
    temporal_match: "match" | "unknown" | "conflict";
    reasons: string[];
    warnings: string[];
  };
}

export interface StructuredSearchResponse {
  query: string;
  release_id: string;
  filters: StructuredSearchFilters;
  page_size: number;
  returned_count: number;
  candidate_count: number;
  has_more: boolean;
  next_cursor: string | null;
  degraded: boolean;
  evidence_status: "supported" | "insufficient" | "conflicting" | "inferred";
  message: string;
  hits: StructuredSearchHit[];
  alias_expansion: {
    original_query: string;
    release_id: string;
    resolved_query: string | null;
    expanded_terms: string[];
    requires_disambiguation: boolean;
    truncated: boolean;
    candidates: Array<{
      alias_id: string;
      matched_alias: string;
      entity_id: string;
      canonical_name: string;
      entity_type: EntityType;
      evidence_ids: string[];
      eligible: boolean;
      reason: string;
    }>;
  } | null;
}

export interface EvidenceDetail {
  evidence_id: string;
  chunk_id: string;
  document_id: string;
  source_file_id: string | null;
  document_title: string;
  edition: string | null;
  volume: string | null;
  section: string | null;
  page_start: number;
  page_end: number;
  folio_start: string | null;
  folio_end: string | null;
  quote: string;
  source_level: SourceLevel;
  review_status: ReviewStatus;
  href: string;
}
