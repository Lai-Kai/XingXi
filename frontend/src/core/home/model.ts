import type {
  DailyResearchFeed,
  DailyResearchItem,
} from "@/core/research-feed/api";
import type { XingxiChatScope } from "@/core/threads/xingxi-entry";

export type HomeSource = NonNullable<DailyResearchItem["sources"]>[number];
export type HomeTopic = DailyResearchItem & {
  date: string;
  sources: HomeSource[];
  scope: XingxiChatScope;
};

export const sourcePreferences = ["地方志", "碑刻拓片", "家族谱牒"] as const;
export type SourcePreference = (typeof sourcePreferences)[number];

export function researchPrompt(query: string, preferences: SourcePreference[]) {
  const value = query.trim();
  if (!value) return "";
  return preferences.length
    ? `${value}\n\n优先查阅：${preferences.join("、")}。请注明出处与页码。`
    : value;
}

export function sourcePageLabel(source: HomeSource) {
  if (source.page_start == null) return "页码待核";
  if (source.page_end == null || source.page_end === source.page_start) {
    return `${source.page_start}页`;
  }
  return `${source.page_start}–${source.page_end}页`;
}

export function homeTopics(feeds: DailyResearchFeed[]): HomeTopic[] {
  return feeds.flatMap((feed) =>
    feed.items
      .filter((item) => item.sources?.length)
      .map((item) => ({
        ...item,
        id: `${feed.generated_for}:${item.id}`,
        date: feed.generated_for,
        sources: item.sources!,
        scope: {
          documentIds: [
            ...new Set(item.sources!.map((source) => source.document_id)),
          ],
          evidenceIds: [
            ...new Set(item.sources!.map((source) => source.evidence_id)),
          ],
          releaseId: item.knowledge_release_id,
          retrievalQuery: item.retrieval_query,
        },
      })),
  );
}

export function documentLeads(topics: HomeTopic[]) {
  const documents = new Map<
    string,
    {
      id: string;
      title: string;
      sources: HomeSource[];
      topics: HomeTopic[];
    }
  >();
  for (const topic of topics) {
    for (const source of topic.sources) {
      let document = documents.get(source.document_id);
      if (!document) {
        document = {
          id: source.document_id,
          title: source.document_title,
          sources: [],
          topics: [],
        };
        documents.set(document.id, document);
      }
      if (
        !document.sources.some(
          (item) => item.evidence_id === source.evidence_id,
        )
      ) {
        document.sources.push(source);
      }
      if (!document.topics.some((item) => item.id === topic.id)) {
        document.topics.push(topic);
      }
    }
  }
  return [...documents.values()];
}

export function topicCollections(topics: HomeTopic[]) {
  const groups = new Map<string, HomeTopic[]>();
  for (const topic of topics) {
    const tag = topic.tag || "文史考证";
    groups.set(tag, [...(groups.get(tag) ?? []), topic]);
  }
  return [...groups].map(([title, items]) => ({ title, items }));
}
