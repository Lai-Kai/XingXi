export type OperationsDashboard = {
  answer_accuracy_rate: number | null;
  citation_rate: number | null;
  refusal_compliance_rate: number | null;
  user_satisfaction_rate: number | null;
  answer_count: number;
  unanswered_count: number;
  map_point_click_count: number;
  manual_correction_count: number;
  three_dimensional_load_success_rate: null;
  hot_entities: Array<{ entity_id: string; name: string; views: number }>;
};

export type OperationTaskStep = {
  name: string;
  label: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  attempt_count: number;
  error_code: string | null;
  error_message: string | null;
  retryable: boolean;
};

export type OperationTask = {
  id: string;
  kind: "ingestion";
  title: string;
  document_id: string;
  source_file_id: string;
  filename: string | null;
  status:
    | "pending"
    | "running"
    | "awaiting_review"
    | "completed"
    | "failed"
    | "cancelled";
  current_step: string | null;
  current_step_label: string | null;
  progress_percent: number;
  attempt_count: number;
  retry_count: number;
  failure_step: string | null;
  failure_step_label: string | null;
  error_code: string | null;
  error_message: string | null;
  retryable: boolean;
  steps: OperationTaskStep[];
  created_at: string;
  updated_at: string;
};

export type EvaluationCase = {
  id: string;
  name: string;
  question: string;
  expected_status: "answered" | "refused";
  min_citations: number;
  required_terms: string[];
  active: boolean;
  created_by: string;
  created_at: string;
};

export type EvaluationObservation = {
  case_id: string;
  actual_status: "answered" | "refused";
  citation_count: number;
  answer: string;
};

export type EvaluationRun = {
  id: string;
  release_id: string | null;
  asset_version_id: string | null;
  status: "completed";
  total: number;
  passed: number;
  pass_rate: number | null;
  created_by: string;
  created_at: string;
  results: Array<{
    case_id: string;
    actual_status: "answered" | "refused";
    citation_count: number;
    answer: string;
    passed: boolean;
    failure_reasons: string[];
  }>;
};

export type CorrectionRecord = {
  id: string;
  target_type: "source" | "knowledge" | "entity" | "graph" | "map";
  target_id: string;
  release_id: string | null;
  summary: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  actor_id: string;
  created_at: string;
};

export type AssetVersion = {
  id: string;
  knowledge_release_id: string;
  knowledge_release_version: string;
  graph_manifest_sha256: string;
  map_manifest_sha256: string;
  entity_count: number;
  map_point_count: number;
  created_by: string;
  created_at: string;
};

export function formatMetricRate(value: number | null) {
  return value === null ? "暂无数据" : `${(value * 100).toFixed(1)}%`;
}
