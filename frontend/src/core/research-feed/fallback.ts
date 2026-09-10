import { type DailyResearchFeed, type DailyResearchItem } from "./api";

const LOCAL_SEED_RELEASE_ID = "release-2c7aafe43b4247fa86ab0d6b951590e7";
const LOCAL_SEED_NOTICE = "部分内容暂时使用本地资料";

type LocalSource = NonNullable<DailyResearchItem["sources"]>[number];

const source = (values: Omit<LocalSource, "quote">): LocalSource => values;

const LOCAL_SEED_ITEMS: DailyResearchItem[] = [
  {
    id: "local-seed-zhumaichen",
    title: "地方文献怎样记载朱买臣与吴地的联系？",
    summary:
      "从地方文献中看看这位人物与吴地的真实联系。《康熙吴县志》记木渎北会稽太守庙祀朱买臣，并载其往来木渎藏书的地方传说。",
    tag: "人物故事",
    source_basis: "项目本地审核种子 · 府县志语料",
    prompt:
      "请用通俗方式介绍“地方文献怎样记载朱买臣与吴地的联系？”，只引用随附的本地资料，并标出文献和段落出处。",
    retrieval_query: "朱买臣",
    origin: "evidence_backed_fallback",
    evidence_count: 1,
    knowledge_release_id: LOCAL_SEED_RELEASE_ID,
    popularity_users: null,
    popularity_searches: null,
    dynasty: "汉",
    time_label: "汉",
    place: "木渎北会稽太守庙",
    people: ["朱买臣"],
    entities: [
      {
        id: "fuxianzhi-person-zhumaichen",
        name: "朱买臣",
        entity_type: "person",
      },
      {
        id: "fuxianzhi-building-kuaijitaishoumiao",
        name: "会稽太守庙",
        entity_type: "building",
      },
      {
        id: "fuxianzhi-place-mudu",
        name: "木渎",
        entity_type: "place",
      },
    ],
    sources: [
      source({
        evidence_id:
          "fulltext-release-2c7aafe43b4247fa86ab0d6b951590e7-chunk-5761d13fe538db2c0f117857e3dbafbb51ace2f45a0e4dd8d3002abd3677388d",
        document_id:
          "fuxianzhi-1cf5a30e0f34568117d3d715cee43718936c24812160fc6934edf79b6e8165ce",
        document_title: "（康熙）吳縣志",
        chunk_id:
          "chunk-5761d13fe538db2c0f117857e3dbafbb51ace2f45a0e4dd8d3002abd3677388d",
        page_start: 1639,
        page_end: 1645,
      }),
    ],
    degraded: true,
    notice: LOCAL_SEED_NOTICE,
  },
  {
    id: "local-seed-guanwa",
    title: "馆娃宫和西施的故事在地方志中有哪些记载？",
    summary:
      "从灵岩山相关地方志中了解馆娃宫、西施和夫差的地方记忆，并区分传说与确证年代。这是方志所汇录的历史记忆，不等同于已证实的精确年代事件。",
    tag: "地方记忆",
    source_basis: "项目本地审核种子 · 府县志语料",
    prompt:
      "请用通俗方式介绍“馆娃宫和西施的故事在地方志中有哪些记载？”，只引用随附的本地资料，并标出文献和段落出处。",
    retrieval_query: "西施 灵岩山",
    origin: "evidence_backed_fallback",
    evidence_count: 1,
    knowledge_release_id: LOCAL_SEED_RELEASE_ID,
    popularity_users: null,
    popularity_searches: null,
    dynasty: "春秋",
    time_label: "年代待考",
    place: "灵岩山",
    people: ["西施", "夫差"],
    entities: [
      {
        id: "fuxianzhi-event-guanwa-memory",
        name: "馆娃宫与西施叙事见于地方志汇录",
        entity_type: "event",
      },
      {
        id: "fuxianzhi-place-lingyanshan",
        name: "灵岩山",
        entity_type: "place",
      },
      {
        id: "fuxianzhi-person-xishi",
        name: "西施",
        entity_type: "person",
      },
      {
        id: "fuxianzhi-person-fuchai",
        name: "夫差",
        entity_type: "person",
      },
    ],
    sources: [
      source({
        evidence_id:
          "fulltext-release-2c7aafe43b4247fa86ab0d6b951590e7-chunk-0625e762d386f7873718b935a571c03aca0b4eabf76b91d1e3fd018c569796b9",
        document_id:
          "fuxianzhi-14c3406ddba068ef1758e22a9dc22c4fd91bf7fb4d106fd2d4484b3109932267",
        document_title: "（民國）宋平江城坊考",
        chunk_id:
          "chunk-0625e762d386f7873718b935a571c03aca0b4eabf76b91d1e3fd018c569796b9",
        page_start: 275,
        page_end: 278,
      }),
    ],
    degraded: true,
    notice: LOCAL_SEED_NOTICE,
  },
  {
    id: "local-seed-fanzhongyan",
    title: "地方文献怎样记载范仲淹与吴地的联系？",
    summary:
      "从地方文献中看看这位人物与吴地的真实联系。《宋平江城坊考》引《吴郡志》，记景祐年间范仲淹守乡郡并奏请立学。",
    tag: "人物故事",
    source_basis: "项目本地审核种子 · 府县志语料",
    prompt:
      "请用通俗方式介绍“地方文献怎样记载范仲淹与吴地的联系？”，只引用随附的本地资料，并标出文献和段落出处。",
    retrieval_query: "范仲淹",
    origin: "evidence_backed_fallback",
    evidence_count: 1,
    knowledge_release_id: LOCAL_SEED_RELEASE_ID,
    popularity_users: null,
    popularity_searches: null,
    dynasty: "宋",
    time_label: "宋",
    place: "苏州府学",
    people: ["范仲淹"],
    entities: [
      {
        id: "fuxianzhi-person-fanzhongyan",
        name: "范仲淹",
        entity_type: "person",
      },
      {
        id: "fuxianzhi-building-suzhou-fuxue",
        name: "苏州府学",
        entity_type: "building",
      },
    ],
    sources: [
      source({
        evidence_id:
          "fulltext-release-2c7aafe43b4247fa86ab0d6b951590e7-chunk-39bd7fa575d6852559e122a32d4d08e2adbbbfabcd2a424595afa3a12d1ee7a3",
        document_id:
          "fuxianzhi-14c3406ddba068ef1758e22a9dc22c4fd91bf7fb4d106fd2d4484b3109932267",
        document_title: "（民國）宋平江城坊考",
        chunk_id:
          "chunk-39bd7fa575d6852559e122a32d4d08e2adbbbfabcd2a424595afa3a12d1ee7a3",
        page_start: 55,
        page_end: 58,
      }),
    ],
    degraded: true,
    notice: LOCAL_SEED_NOTICE,
  },
  {
    id: "local-seed-luwan",
    title: "陆玩和灵岩寺有什么历史联系？",
    summary:
      "地方志以“或曰”记下这段说法，适合结合原文了解它的来历与不确定性。《宋平江城坊考》保留了这条待考记载。",
    tag: "寺院沿革",
    source_basis: "项目本地审核种子 · 府县志语料",
    prompt:
      "请用通俗方式介绍“陆玩和灵岩寺有什么历史联系？”，只引用随附的本地资料，并标出文献和段落出处。",
    retrieval_query: "陆玩 灵岩山",
    origin: "evidence_backed_fallback",
    evidence_count: 1,
    knowledge_release_id: LOCAL_SEED_RELEASE_ID,
    popularity_users: null,
    popularity_searches: null,
    dynasty: "晋",
    time_label: "年代待考",
    place: "灵岩山",
    people: ["陆玩"],
    entities: [
      {
        id: "fuxianzhi-event-luwan-lingyan",
        name: "陆玩施宅为灵岩寺之说",
        entity_type: "event",
      },
      {
        id: "fuxianzhi-place-lingyanshan",
        name: "灵岩山",
        entity_type: "place",
      },
      {
        id: "fuxianzhi-person-luwan",
        name: "陆玩",
        entity_type: "person",
      },
    ],
    sources: [
      source({
        evidence_id:
          "fulltext-release-2c7aafe43b4247fa86ab0d6b951590e7-chunk-0625e762d386f7873718b935a571c03aca0b4eabf76b91d1e3fd018c569796b9",
        document_id:
          "fuxianzhi-14c3406ddba068ef1758e22a9dc22c4fd91bf7fb4d106fd2d4484b3109932267",
        document_title: "（民國）宋平江城坊考",
        chunk_id:
          "chunk-0625e762d386f7873718b935a571c03aca0b4eabf76b91d1e3fd018c569796b9",
        page_start: 275,
        page_end: 278,
      }),
    ],
    degraded: true,
    notice: LOCAL_SEED_NOTICE,
  },
  {
    id: "local-seed-fengguifen",
    title: "地方文献怎样记载冯桂芬与吴地的联系？",
    summary:
      "从地方文献中看看这位人物与吴地的真实联系。《民国吴县志》记清同治六年冯桂芬建六烈祠。",
    tag: "人物故事",
    source_basis: "项目本地审核种子 · 府县志语料",
    prompt:
      "请用通俗方式介绍“地方文献怎样记载冯桂芬与吴地的联系？”，只引用随附的本地资料，并标出文献和段落出处。",
    retrieval_query: "冯桂芬",
    origin: "evidence_backed_fallback",
    evidence_count: 1,
    knowledge_release_id: LOCAL_SEED_RELEASE_ID,
    popularity_users: null,
    popularity_searches: null,
    dynasty: "清",
    time_label: "清",
    place: "六烈祠",
    people: ["冯桂芬"],
    entities: [
      {
        id: "fuxianzhi-person-fengguifen",
        name: "冯桂芬",
        entity_type: "person",
      },
      {
        id: "fuxianzhi-building-liulieci",
        name: "六烈祠",
        entity_type: "building",
      },
    ],
    sources: [
      source({
        evidence_id:
          "fulltext-release-2c7aafe43b4247fa86ab0d6b951590e7-chunk-e227b047f9dc293782804eed7daa6557d4e774eed9e9f16849ffa517e960e214",
        document_id:
          "fuxianzhi-531cd6a2b0de9a1bcece4cb2b8b2d350225c90b9c7d3c8667d9ba1f0cba121fb",
        document_title: "（民國）吳縣志",
        chunk_id:
          "chunk-e227b047f9dc293782804eed7daa6557d4e774eed9e9f16849ffa517e960e214",
        page_start: 2107,
        page_end: 2107,
      }),
    ],
    degraded: true,
    notice: LOCAL_SEED_NOTICE,
  },
  {
    id: "local-seed-fan-fuxue",
    title: "范仲淹守乡郡并筹建府学发生了什么？",
    summary:
      "按时间、地点和人物梳理文献中可以核验的记载。景祐元年任职、次年奏请立学的连续过程，暂以 1034 年作为时间起点。",
    tag: "历史事件",
    source_basis: "项目本地审核种子 · 府县志语料",
    prompt:
      "请用通俗方式介绍“范仲淹守乡郡并筹建府学发生了什么？”，只引用随附的本地资料，并标出文献和段落出处。",
    retrieval_query: "范仲淹 苏州府学",
    origin: "evidence_backed_fallback",
    evidence_count: 1,
    knowledge_release_id: LOCAL_SEED_RELEASE_ID,
    popularity_users: null,
    popularity_searches: null,
    dynasty: "宋",
    time_label: "约1034年",
    place: "苏州府学",
    people: ["范仲淹"],
    entities: [
      {
        id: "fuxianzhi-event-fan-fuxue",
        name: "范仲淹守乡郡并筹建府学",
        entity_type: "event",
      },
      {
        id: "fuxianzhi-building-suzhou-fuxue",
        name: "苏州府学",
        entity_type: "building",
      },
      {
        id: "fuxianzhi-person-fanzhongyan",
        name: "范仲淹",
        entity_type: "person",
      },
    ],
    sources: [
      source({
        evidence_id:
          "fulltext-release-2c7aafe43b4247fa86ab0d6b951590e7-chunk-39bd7fa575d6852559e122a32d4d08e2adbbbfabcd2a424595afa3a12d1ee7a3",
        document_id:
          "fuxianzhi-14c3406ddba068ef1758e22a9dc22c4fd91bf7fb4d106fd2d4484b3109932267",
        document_title: "（民國）宋平江城坊考",
        chunk_id:
          "chunk-39bd7fa575d6852559e122a32d4d08e2adbbbfabcd2a424595afa3a12d1ee7a3",
        page_start: 55,
        page_end: 58,
      }),
    ],
    degraded: true,
    notice: LOCAL_SEED_NOTICE,
  },
];

function shanghaiDate(value: Date) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(value);
  const part = (type: string) =>
    parts.find((item) => item.type === type)?.value ?? "00";
  return `${part("year")}-${part("month")}-${part("day")}`;
}

export function buildLocalFallbackDailyResearchFeed(
  value = new Date(),
): DailyResearchFeed {
  const generatedFor = shanghaiDate(value);
  const nextRefresh = new Date(`${generatedFor}T00:00:00+08:00`);
  nextRefresh.setUTCDate(nextRefresh.getUTCDate() + 1);
  return {
    kind: "daily_grounded",
    generated_for: generatedFor,
    next_refresh_at: nextRefresh.toISOString(),
    items: LOCAL_SEED_ITEMS,
    notice: LOCAL_SEED_NOTICE,
  };
}
