export type ResearchToolPhase =
  | "planning"
  | "sources"
  | "graph"
  | "timeline"
  | "map"
  | "gloss"
  | "names"
  | "comparison"
  | "image";

export interface ResearchToolDescription {
  phase: ResearchToolPhase;
  detail?: string;
}

const RESEARCH_TOOL_PHASES: Readonly<Record<string, ResearchToolPhase>> = {
  write_todos: "planning",
  search_sources: "sources",
  query_knowledge_graph: "graph",
  query_timeline: "timeline",
  query_map_features: "map",
  gloss_ancient_text: "gloss",
  resolve_name_variants: "names",
  compare_sources: "comparison",
  view_image: "image",
};

const SAFE_DETAIL_KEYS: Readonly<Partial<Record<ResearchToolPhase, string[]>>> =
  {
    sources: ["query"],
    graph: ["entity_name", "entity_id", "query"],
    timeline: ["query", "entity_name"],
    map: ["query", "place_name"],
    names: ["name", "query"],
    comparison: ["query"],
  };

function compactDetail(value: unknown): string | undefined {
  if (typeof value !== "string") {
    return undefined;
  }
  const compact = value.replace(/\s+/g, " ").trim();
  if (!compact) {
    return undefined;
  }
  return compact.length > 60 ? `${compact.slice(0, 57)}...` : compact;
}

export function isResearchTool(name: string): boolean {
  return name in RESEARCH_TOOL_PHASES;
}

export function describeResearchToolCall(
  name: string,
  args: Record<string, unknown>,
): ResearchToolDescription | undefined {
  const phase = RESEARCH_TOOL_PHASES[name];
  if (!phase) {
    return undefined;
  }
  const detail = (SAFE_DETAIL_KEYS[phase] ?? [])
    .map((key) => compactDetail(args[key]))
    .find((value) => value !== undefined);
  return detail ? { phase, detail } : { phase };
}
