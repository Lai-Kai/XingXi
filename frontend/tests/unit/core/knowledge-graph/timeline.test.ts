import { describe, expect, it } from "@rstest/core";

import { sortHistoricalEvents } from "@/core/knowledge-graph/types";

const base = {
  event_type: "visit",
  end_time: null,
  time_certainty: "exact" as const,
  place_entity_id: null,
  participant_entity_ids: [] as string[],
  summary: null,
  evidence_ids: ["evidence-1"],
  is_inferred: false,
  review_status: "pending" as const,
  release_id: "release-working",
};

describe("knowledge graph timeline", () => {
  it("orders dated events first and keeps unknown dates visible", () => {
    const rows = sortHistoricalEvents([
      { ...base, id: "unknown", title: "年代待考", start_time: null },
      { ...base, id: "later", title: "同治六年", start_time: "1867" },
      { ...base, id: "early", title: "景祐元年", start_time: "1034" },
    ]);

    expect(rows.map((row) => row.id)).toEqual(["early", "later", "unknown"]);
  });
});
