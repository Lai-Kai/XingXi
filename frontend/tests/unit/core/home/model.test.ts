import { expect, test } from "@rstest/core";

import {
  documentLeads,
  homeTopics,
  researchPrompt,
  sourcePageLabel,
  topicCollections,
} from "@/core/home/model";
import { buildLocalFallbackDailyResearchFeed } from "@/core/research-feed/fallback";
import { xingxiChatHref } from "@/core/threads/xingxi-entry";

test("daily and historical starters retain their exact bound evidence scope", () => {
  const feed = buildLocalFallbackDailyResearchFeed();
  const topics = homeTopics([feed, { ...feed, generated_for: "2020-01-01" }]);
  expect(new Set(topics.map((topic) => topic.id)).size).toBe(topics.length);
  const item = topics[0]!;
  const original = feed.items[0]!;
  expect(item.sources).toEqual(original.sources);
  expect(item.scope.retrievalQuery).toBe(original.retrieval_query);
  const url = new URL(
    xingxiChatHref(item.prompt, item.scope),
    "https://example.test",
  );
  expect(url.searchParams.get("prompt")).toBe(original.prompt);
  expect(url.searchParams.get("release_id")).toBe(
    original.knowledge_release_id,
  );
  expect(url.searchParams.getAll("evidence_id")).toEqual([
    ...new Set(original.sources!.map((source) => source.evidence_id)),
  ]);
  expect(url.searchParams.getAll("document_id")).toEqual([
    ...new Set(original.sources!.map((source) => source.document_id)),
  ]);
});

test("a topic without an actual citation never becomes a reading recommendation", () => {
  const feed = buildLocalFallbackDailyResearchFeed();
  const unbound = { ...feed.items[0]!, id: "unbound", sources: [] };
  expect(homeTopics([{ ...feed, items: [unbound] }])).toEqual([]);
});

test("book leads deduplicate evidence without conflating distinct documents sharing a title", () => {
  const feed = buildLocalFallbackDailyResearchFeed();
  const first = feed.items[0]!;
  const source = first.sources![0]!;
  const topics = homeTopics([
    {
      ...feed,
      items: [
        first,
        { ...first, id: "another-topic" },
        {
          ...first,
          id: "another-book",
          sources: [
            {
              ...source,
              document_id: "another-edition",
              evidence_id: "another-evidence",
            },
          ],
        },
      ],
    },
  ]);
  const leads = documentLeads(topics);
  const original = leads.find(
    (document) => document.id === source.document_id,
  )!;
  expect(
    original.sources.filter((item) => item.evidence_id === source.evidence_id),
  ).toHaveLength(1);
  expect(original.topics).toHaveLength(2);
  expect(
    leads.find((document) => document.id === "another-edition")?.sources[0]
      ?.evidence_id,
  ).toBe("another-evidence");
});

test("collections use actual tags and preserve all scoped question links", () => {
  const topics = homeTopics([buildLocalFallbackDailyResearchFeed()]);
  const groups = topicCollections(topics);
  expect(groups.flatMap((group) => group.items)).toHaveLength(topics.length);
  expect(
    groups.every((group) =>
      group.items.every((item) => item.tag === group.title),
    ),
  ).toBe(true);
});

test("empty questions cannot become requests even when source preferences are selected", () => {
  expect(researchPrompt("  \n ", ["地方志"])).toBe("");
});

test("unselected preferences leave the researcher's question intact", () => {
  expect(researchPrompt("  香溪古桥\n有哪些记载？ ", [])).toBe(
    "香溪古桥\n有哪些记载？",
  );
});

test("selected sources travel as an explicit reading preference", () => {
  expect(researchPrompt("香溪古桥", ["地方志", "碑刻拓片"])).toBe(
    "香溪古桥\n\n优先查阅：地方志、碑刻拓片。请注明出处与页码。",
  );
});

test("unknown pages stay unknown and single or ranged pages remain distinct", () => {
  const source = buildLocalFallbackDailyResearchFeed().items[0]!.sources![0]!;
  expect(sourcePageLabel({ ...source, page_start: null, page_end: null })).toBe(
    "页码待核",
  );
  expect(sourcePageLabel({ ...source, page_start: 12, page_end: null })).toBe(
    "12页",
  );
  expect(sourcePageLabel({ ...source, page_start: 12, page_end: 12 })).toBe(
    "12页",
  );
  expect(sourcePageLabel({ ...source, page_start: 12, page_end: 13 })).toBe(
    "12–13页",
  );
});
