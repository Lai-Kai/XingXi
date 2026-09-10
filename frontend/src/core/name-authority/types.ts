export type NameVariantInput = {
  name: string;
  evidence_ids: string[];
};

export type AuthorityEvidence = {
  evidence_id: string;
  document_id: string;
  document_title: string;
  edition: string | null;
  source_level: "A" | "B" | "C" | "D" | "E" | "U";
  review_status: "pending" | "reviewed" | "disputed" | "rejected";
  page_start: number;
  page_end: number;
  contributes_to_score: boolean;
};

export type NameAuthorityCandidate = {
  name: string;
  score: number;
  eligible: boolean;
  best_source_level: "A" | "B" | "C" | "D" | "E" | "U" | null;
  reviewed_document_count: number;
  evidence: AuthorityEvidence[];
  missing_evidence_ids: string[];
  reasons: string[];
};

export type NameAuthorityResolution = {
  decision: "selected" | "needs_review" | "insufficient_evidence";
  preferred_name: string | null;
  confidence: "high" | "medium" | "low" | "none";
  research_context: string | null;
  candidates: NameAuthorityCandidate[];
  retained_names: string[];
  explanation: string;
  requires_human_review: boolean;
};

export function parseEvidenceIds(value: string): string[] {
  return Array.from(
    new Set(
      value
        .split(/[，,\s]+/)
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  );
}
